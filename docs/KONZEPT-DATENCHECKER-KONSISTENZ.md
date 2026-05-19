# Konzept Datenchecker-Konsistenz — Sensor-Mapping-Strategien, Custom-Import, Refactor

**Status:** Konzept-Phase, 2026-05-19
**Ziel-Release:** offen (siehe Abschnitt 6)
**Trigger:** Steffen2 #534/#604 (15./17.05.2026) — `Sensor-Mapping – HA-Statistics: OK` + `Energieprofil – Zähler-Abdeckung: 1 Warnung` wirken auf den Anwender widersprüchlich. Audit dieser scheinbaren Inkonsistenz hat tieferliegende strukturelle Drift-Befunde aufgedeckt.

---

## 1. Problem-Aufhänger

Steffen2s Daten-Checker zeigte zwei sensor-bezogene Kategorien gleichzeitig als „OK" und „Warnung":

- **„Sensor-Mapping – HA-Statistics" (OK)** prüft: „Sind die eingetragenen Sensoren in HA-LTS verfügbar?" — schweigt über Slots, die leer sind.
- **„Energieprofil – Zähler-Abdeckung" (Warnung)** prüft: „Hat jede aktive Komponente überhaupt einen `strategie=sensor`-Eintrag?" — schweigt über Komponenten, die per Custom-Import befüllt werden.

Beide Aussagen sind in sich korrekt, aber zusammen erzeugen sie eine UX, in der ein Anwender denkt: „Mein Sensor-Mapping ist OK — wieso fehlt dann was?" Eine Konsistenz-Untersuchung über den ganzen Datenchecker und die angrenzenden Pfade ergab drei separate Drift-Achsen.

---

## 2. Befund A — Sensor-Mapping-Strategien: 5 von 6 sind Dead Code

`StrategieTyp`-Enum in [`backend/api/routes/sensor_mapping.py:39-46`](../eedc/backend/api/routes/sensor_mapping.py#L39-L46):

| Strategie | Bedeutung (Enum-Kommentar) | Aggregator | Checker | Frontend bietet an |
|---|---|:---:|:---:|:---:|
| `sensor` | Direkter HA-Sensor | ✓ | ✓ | ✓ |
| `kwp_verteilung` | Anteilig nach kWp | — | — | ✓ |
| `cop_berechnung` | COP × Stromverbrauch | — | — | ✓ |
| `manuell` | Manuelle Eingabe im Wizard | — | — | ✓ |
| `ev_quote` | Nach Eigenverbrauchsquote | — | — | — (Phantom) |
| `keine` | Nicht erfassen | — | — | ✓ |

**Belege:** Alle aggregierenden Code-Stellen prüfen ausschließlich `strategie == "sensor"`:

- `services/snapshot/aggregator.py:109`
- `services/snapshot/writer.py:63`
- `services/snapshot/reaggregator.py:88`
- `services/snapshot/lts_aggregator.py:76, 232`
- `services/live_history_service.py:51`
- `services/daten_checker.py:952, 1335, 1578`
- `api/routes/aktueller_monat.py:219, 225`
- `api/routes/ha_statistics.py:155, 163, 194, 218`
- `api/routes/monatsabschluss/views.py:240, 245, 292, 339, 421`

Lediglich [`api/routes/sensor_mapping.py:540-568`](../eedc/backend/api/routes/sensor_mapping.py#L540-L568) zählt die anderen Strategien für UI-Statistik-Anzeige — wertet sie aber nicht aus.

**Anwender-Risiko:** Ein Anwender, der für seine WP-Komponente `cop_berechnung` wählt (weil er glaubt, eedc rechnet COP × Stromverbrauch selbst), bekommt leere Daten ohne Hinweis. Der Datenchecker meldet „kein kWh-Counter" — UI suggeriert aber, die Wahl sei valide. **Das ist Drift vom Typ [[feedback_aggregations_drift]]**.

---

## 3. Befund B — Custom-Import läuft am Sensor-Mapping vorbei

Custom-Import schreibt direkt auf `Monatsdaten.datenquelle`:

```python
# api/routes/custom_import/apply.py:356
md.datenquelle = "custom_import"
```

Das Sensor-Mapping bleibt für diese Komponente leer. Andere parallele `datenquelle`-Werte aus dem Code:

| Wert | Pfad | Code-Stelle |
|---|---|---|
| `custom_import` | CSV-Import via UI | `custom_import/apply.py:356` |
| `csv` | Legacy-CSV-Import-Export | `import_export/csv_operations.py:494, 512` |
| `ha_statistics` | Vollbackfill aus HA-LTS | `ha_statistics.py:946, 988` |
| `json_import` | Backup-Restore | `import_export/json_operations.py:728` |
| `demo` | Demo-Daten | `import_export/demo_data.py:422` |
| `manuell` | Reparatur-Werkbank | `services/repair_orchestrator.py:289, 411` |
| `scheduler` | Auto-Aggregation täglich | `services/energie_profil/scheduler_jobs.py:49, 102` |

**Kein einziger der 12 Datenchecker-Checks liest `monatsdaten.datenquelle`.** Konsequenz:

- Anwender mit reiner Custom-Import-Befüllung → Checker meldet „alle Komponenten ohne Mapping" als WARNING, obwohl die Daten da sind.
- Anwender, deren Monat gemischt aus `sensor`-Aggregation + `custom_import`-Override stammt → keine Sichtbarkeit der Provenance pro Komponente.

Anmerkung: Die Kategorie `PROVENANCE_CONFLICT` (Etappe 3d) liest zwar das Audit-Log, prüft aber Drift *innerhalb* eines Feldes über die Zeit — nicht die Frage „welcher Pfad befüllt die Komponente gerade".

---

## 4. Befund C — Datenchecker-Struktur: 1984 Zeilen, 12 Funktionen

`services/daten_checker.py`:
- 12 `async`/`sync`-Check-Funktionen in einer Datei
- Mapping-Iteration in 3 Funktionen wiederholt: `_check_energieprofil_abdeckung`, `_check_sensor_mapping_lts`, plus impliziter Schreib-Pfad in `monatsabschluss/views.py`
- Investitions-Filter-Konventionen verteilt: `aktiv == True` (6×), `ist_dienstlich` (2×), `typ == "sonstiges"` (1×), WP-`getrennte_strommessung` (1×) — alle konsistent angewendet, aber dupliziert
- Erwartete-Felder-Map ([`daten_checker.py:987-994`](../eedc/backend/services/daten_checker.py#L987-L994)) ist die einzige Stelle, die typ→Feld-Erwartung definiert. Bei Investitions-Typ-Erweiterung Drift-Risiko.

**Kein akutes Problem**, aber jeder neue Check verschärft die Wartungslast.

---

## 5. Lösungs-Achsen

> **Querverweis 2026-05-19 (ADR-001):** Beim Achse-A-/B-/C-Refactor MUSS der Daten-Checker bestehende Aggregat-Helper aus dem Berechnungs-Layer (`backend/core/berechnungen/`) benutzen — nicht eigene Σ-Logik inline implementieren. `_summe_pv_bkw_kwh` ist seit 2026-05-19 bereits ein Re-Export aus `core/berechnungen.energie`; neue PV-/BKW-/Counter-Aggregate, die im Refactor entstehen, gehören auch dorthin. Siehe [`KONZEPT-BERECHNUNGS-LAYER.md`](KONZEPT-BERECHNUNGS-LAYER.md) und [`ADR-001-BERECHNUNGS-LAYER.md`](ADR-001-BERECHNUNGS-LAYER.md).

### 5.1 Achse A — Strategie-Schema aufräumen

**Drei Varianten, sich gegenseitig ausschließend:**

**A1 — Komplett auf `sensor` reduzieren (Empfehlung)**

- Strategien `kwp_verteilung`, `ev_quote`, `cop_berechnung`, `manuell` aus Enum entfernen
- `keine` als Opt-out behalten (semantisch sinnvoll: „Diese Komponente bewusst leer lassen, nicht warnen")
- Wizard-UI: Auswahl auf `sensor` oder `keine` reduzieren
- Migration: vorhandene Drift-Strategie-Werte beim ersten Save auf `keine` migrieren (entspricht heutigem Faktum: sie haben ohnehin keine Daten geliefert)
- **Aufwand:** ~80 Zeilen Backend (Enum + Wizard + Migration) + ~40 Zeilen Frontend + Tests

**A2 — Dead-Strategies tatsächlich implementieren**

- `kwp_verteilung` wäre wertvoll (1 String-Sensor am WR → anteilig auf mehrere PV-Module verteilen, Anwendungsfall: JanKgh [[project_jankgh_pv_string_verteilung]])
- `cop_berechnung` wäre wertvoll für WP-Anwender ohne separaten Strom-Counter
- `manuell` ist redundant mit Monatsdaten-Eingabe — eher streichen
- `ev_quote` und `keine` siehe A1
- **Aufwand:** mehrere Tage (jeder Aggregations-Pfad + Datenchecker + UI muss Strategien akzeptieren)

**A3 — Status quo dokumentieren, nicht ändern**

- Im Wizard sichtbar machen: „Diese Strategie wird derzeit nicht ausgewertet (kommt mit Roadmap-Punkt X)"
- **Risiko:** [[feedback_externer_druck_reflex]] — wir versprechen Roadmap, ohne wirklich bauen zu wollen

**Empfehlung A1.** Argument: `kwp_verteilung` ist die einzige der vier mit echtem Bedarf, aber JanKgh [[project_jankgh_pv_string_verteilung]] verfolgt einen anderen Lösungs-Pfad (SoT-Helper für Spalten-Wert statt Strategie). Wenn `kwp_verteilung` später doch gebraucht wird, kann es separat ergänzt werden — heute steht es nur als Anwender-Falle im Wizard.

### 5.2 Achse B — Datenquellen-Sicht im Checker

**Empfehlung:** Neue Kategorie **`DATENQUELLE_ABDECKUNG`** ergänzen (oder die bestehende `ENERGIEPROFIL_ABDECKUNG` erweitern).

Logik pro Komponente:
1. Hat sie ein `strategie=sensor`-Mapping? → OK (Sensor)
2. Sonst: existiert Monatsdaten mit `datenquelle ∈ {custom_import, csv, json_import, manuell}`? → OK (manuelle Quelle: <wert>)
3. Sonst: nichts da → WARNING

Auf der UI-Ebene: Komponenten mit manueller Quelle bekommen ein kleines Badge „CSV-Import" / „manuelle Eingabe" — Anwender sehen sofort, woher die Daten kommen.

**Aufwand:** ~50 Zeilen Backend + 1 Helper + ~30 Zeilen Tests. Frontend-Badge optional, ~20 Zeilen.

### 5.3 Achse C — Datenchecker-Refactor

**Vorschlag:** Modulaufteilung in `backend/services/daten_checker/`:

```
backend/services/daten_checker/
├── __init__.py        # DatenChecker-Klasse + run-Methode
├── kategorien.py      # CheckKategorie-Enum + CheckErgebnis-Dataclass
├── helpers.py         # Gemeinsame Helper: iterate_aktive_invs, get_zaehler_strategie, has_dienstlich_skip
├── stammdaten.py      # _check_stammdaten + _check_strompreise + _check_investitionen
├── monatsdaten.py     # _check_monatsdaten_vollstaendigkeit + _check_monatsdaten_plausibilitaet
├── energieprofil.py   # _check_energieprofil_abdeckung + _check_energieprofil_plausibilitaet + _check_datenquelle_abdeckung (neu)
├── sensoren.py        # _check_sensor_mapping_lts + _check_mqtt_topic_abdeckung
└── datenquelle.py     # _check_provenance_conflicts + _check_datenquelle_status + _check_datenquelle_drift
```

Gemeinsame Helper (in `helpers.py`):

```python
def iterate_aktive_invs(anlage, *, mit_dienstwagen=False):
    """SoT-Iterator für aktive Investitionen mit konsistenten Skip-Konventionen.
    Dienstwagen werden standardmäßig übersprungen — übergibt `mit_dienstwagen=True`,
    wenn der Check Dienstwagen einschließen soll."""

ERWARTETE_FELDER = {
    "pv-module": [["pv_erzeugung_kwh"]],
    ...
}  # SoT für typ→Feld-Erwartung, von beiden Abdeckungs-Checks geteilt

def get_befuellungs_quelle(anlage, inv, db) -> Literal["sensor", "custom_import", "csv", "manuell", "keine"]:
    """SoT für die Frage 'wie wird diese Komponente befüllt?'
    Liest sensor_mapping + Monatsdaten.datenquelle."""
```

**Aufwand:** ~1 Tag Refactor, vorhandene Tests laufen weiter (Public API der `DatenChecker`-Klasse bleibt). Keine Funktionsänderung.

---

## 6. Migrations-Pfad / Empfehlung Reihenfolge

| Schritt | Inhalt | Trigger | Release-Kandidat |
|---|---|---|---|
| 1 | **Achse B** umsetzen (Custom-Import sichtbar) | Sofort (kleine PR), unmittelbarer Anwender-Schutz | v3.31.5-Sammler |
| 2 | **Achse A1** umsetzen (Dead-Strategies entfernen) | Nach Achse B, vermeidet Doppelaufwand | v3.32.0 (Minor, weil Schema-Migration) |
| 3 | **Achse C** umsetzen (Refactor) | Nach Achse A+B, dann ist auch die Helper-Logik klarer | v3.32.x |

**Begründung der Reihenfolge:** Achse B schützt Anwender direkt vor false-positive Warnings. Achse A ist eine Schema-Bereinigung, die UI-Refactor mitnimmt und am besten als eigene Minor-Version released wird (Versionierungs-Signal für Anwender, deren Wizard-Auswahl sich reduziert). Achse C ist reine Wartungs-Investition und sollte erst nach A+B, damit der Refactor die neuen Helper sofort mit aufnimmt.

**Alternative:** Achse C zuerst, dann A+B im aufgeräumten Code. Vorteil: kleinere Folge-PRs. Nachteil: Anwender warten länger auf B (Schutz vor false-positive Warnings).

---

## 7. Test-Strategie

### Achse B
- **Akzeptanz-Test:** Anlage mit 0 Sensor-Mappings + Monatsdaten mit `datenquelle=custom_import` → Datenchecker meldet OK (nicht WARNING)
- **Akzeptanz-Test:** Anlage mit Mix: PV-Süd per Sensor + PV-Nord per Custom-Import → Datenchecker meldet beide als OK mit Quellen-Hinweis
- **Akzeptanz-Test:** Anlage mit weder Sensor noch Datenquelle → WARNING wie bisher
- **Drift-Test:** Erwartete-Felder-Map als Single Source of Truth, beide Abdeckungs-Checks lesen aus derselben Konstante

### Achse A
- **Migrations-Test:** Anlage mit `kwp_verteilung`-Strategie → nach Migration auf `keine`, Anwender bekommt Info-Hinweis
- **UI-Test:** Wizard zeigt nur noch `sensor` und `keine` als Auswahl
- **Schema-Test:** `StrategieTyp`-Enum hat nur noch zwei Werte

### Achse C
- **Regressions-Test:** Bestehende Datenchecker-Tests laufen ohne Änderung (Public API stabil)
- **Modul-Test:** Jedes Submodul hat eigenen Test-File, kein Test-File > 500 Zeilen

---

## 8. Memory-Linien (Begründungen)

- [[feedback_aggregations_drift]] — Achse A+B sind klassische Drift-Fälle. SoT-Helper + Single-Source-Maps verhindern Wiederholung.
- [[feedback_user_fehlermeldungen]] — Achse B verhindert false-positive Warnings (Custom-Import-Anwender denken, sie hätten was falsch gemacht).
- [[feedback_daten_checker_kein_akzeptiert]] — keine Quittier-Knöpfe, auch nicht für „Strategie X bewusst gewählt".
- [[feedback_release_bundling]] — Achse B als Teil des v3.31.5-Sammlers, Achse A als eigene v3.32.0 (Versionierungs-Signal für Wizard-Reduktion).
- [[feedback_externer_druck_reflex]] — A3 (Roadmap-Versprechen für Dead-Strategies) wäre genau dieser Anti-Pattern. Daher Empfehlung A1.

---

## 9. Offene Entscheidungen

1. **Achse A: A1 (Empfehlung) oder A2 (Dead-Strategies bauen)?** Wenn A2, dann welche Strategie zuerst?
2. **Achse B: neue Kategorie `DATENQUELLE_ABDECKUNG` oder Erweiterung der bestehenden `ENERGIEPROFIL_ABDECKUNG`?** Argument für neue Kategorie: Klarheit in der UI. Argument gegen: noch eine Kategorie in der ohnehin langen Liste.
3. **Achse C: jetzt mit A+B verbinden oder später separat?**
4. **Reihenfolge:** B-A-C (vom Anwender-Impact getrieben) oder C-A-B (vom Wartbarkeit getrieben)?

---

## 10. Anhang — Vollständige Bestandsaufnahme der 12 Check-Funktionen

Wurde im Vorlauf-Audit erstellt. Bei Bedarf als separates Dokument oder Inline-Tabelle hier ergänzen. Kernergebnis: Skip-Konventionen (aktiv/Dienstwagen/getrennte_strommessung) sind konsistent angewendet, OK-Rückgaben durchgängig, nur 1 Check (`_check_datenquelle_drift`) nutzt Inline-Actions. Die zentrale Drift sitzt nicht im Datenchecker selbst, sondern in den **Strategien**, die er prüft.
