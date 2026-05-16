# Konzept Etappe 6 — Datenquelle-Drift-Anzeige + Per-Tag-Reparatur

**Status:** Konzept-Phase, 2026-05-17 Abend
**Ziel-Release:** v3.31.1 (Same-Day-Override gegen Bundling-Regel — siehe Abschnitt 8)
**Trigger:** Etappe 4+5 macht die Drift architektonisch sichtbar (Σ Hourly = Daily per Konstruktion *für neue Tage*), aber bestehende Tage bleiben auf dem alten Mix-Source-Wert. Anwender brauchen ein Werkzeug, um zu sehen *welche* Tage betroffen sind und sie *gezielt* zu reparieren.

## 1. Problem

Nach v3.31.0:

- **Neue Tage** (ab Update-Zeitpunkt) → automatisch aus HA-LTS, sauber
- **Bestehende Tage** → auf altem Mix-Source-Wert. Auto-Vollbackfill beim Monatsabschluss ist additiv (#190), füllt nur Lücken, ersetzt keine vorhandenen Tage
- **Drift-Diagnose** existiert nicht: Anwender weiß nicht, welche seiner Tage abweichen — er sieht im Cockpit nur einen Wert, ohne Vergleich gegen HA

**Konsequenz ohne Etappe 6:** Rainer schaut nach dem Update auf seinen 15.05.2026 und sieht weiter 64,49 kWh. Er denkt: „eedc hat den Bug nicht gefixt, sie haben nur viel Text geschrieben." Vertrauen weg, obwohl die Architektur stimmt.

**Konsequenz mit Etappe 6:** Rainer öffnet den Daten-Checker, sieht eine Zeile *„15.05.2026 PV-Erzeugung: eedc 64,49 kWh / HA 67,0 kWh / Δ −3,8 %"*, klickt *„Tag reparieren"*, fertig.

## 2. Lösungs-Architektur

### 2.1 Drei Bausteine, scharf getrennt

```
                         Etappe 6
              ┌──────────────────────────────┐
              │                              │
   Diagnose ──┤    Liste mit Drift-Tagen    ├── Pro Zeile ein
   (Kategorie │    (sortiert nach Δ desc.)   │   Reparatur-Knopf
   im Daten-  │                              │   (= /reaggregate-tag)
   Checker)   │                              │
              └──────────────────────────────┘
                            │
                            │ Verweis (kein Knopf)
                            ▼
              ┌──────────────────────────────┐
              │    Reparatur-Werkbank        │
              │    Bereich neu aggregieren   │  ← schon vorhanden,
              │    (für „alles auf einmal")  │    keine neue Funktion
              └──────────────────────────────┘
```

Bewusst: **kein Sammel-Reparatur-Knopf in der Diff-Liste**. Massen-Aktion erfordert aktive Bereichs-Wahl in der Werkbank (zwei Klicks weiter weg) — Anti-Pattern „großer Heiler-Knopf" (Memory `feedback_kein_grosser_heiler_knopf.md`) bleibt vermieden.

### 2.2 Was wird verglichen

Pro Tag wird **PV-Erzeugung** verglichen (das ist der visible/leidende Indikator bei Rainer und vermutlich dem Großteil der Anwender):

| Quelle | Berechnung |
|---|---|
| eedc-Wert | `Σ TagesZusammenfassung.komponenten_kwh[k]` für alle `k` mit Prefix `pv_*` oder `bkw_*` (gleiche Logik wie Genauigkeits-Tracking IST nach Etappe-4-Bug-Fix) |
| HA-LTS-Wert | `Σ HA-LTS-Daily-Sum` für alle PV-Investitions-Sensoren der Anlage (über `get_komponenten_tageskwh_lts`) |

Andere Kategorien (Verbrauch, Netzbezug, Einspeisung) **bewusst nicht in v1**:
- Halten die Liste fokussiert
- PV ist der politisch sensitive Wert (Ertrag = Geld)
- Wenn PV stimmt, stimmt der Rest meistens mit (über die Tagessumme)
- v2 kann erweitert werden, wenn ein Anwender es konkret braucht

### 2.3 Schwelle — was gilt als Drift

Eintrag erscheint, wenn **gleichzeitig**:

- `|Δ| ≥ 2 kWh` (absolut — kleine Anlagen werden nicht über-warnt)
- `|Δ| / max(eedc, HA) ≥ 5 %` (relativ — große Anlagen werden nicht unter-warnt)

Beide Bedingungen schließen Boundary-Rauschen (Counter-Reset um Mitternacht, Sub-Stunden-Snapshot-Versatz) systematisch aus. Bei Rainer waren es 2,5 kWh / 3,8 % → sichtbar. Tage mit 0,3 kWh / 0,4 % → nicht sichtbar.

### 2.4 Zeitfenster

Geprüft werden die **letzten 90 Tage**. Begründung:

- Weiter zurück: meistens schon manuell korrigierte Werte oder Werte aus pre-v3.19-Zeit (Riemann), die eine andere Drift-Charakteristik haben — würden falsche Hits geben
- 90 Tage: reicht für ein Quartal, deckt typische Anwender-Erinnerung („mein Mai sah komisch aus") ab

### 2.5 Anzahl der Einträge

**Max 20 Einträge**, sortiert nach `|Δ|` absteigend (große Drift zuerst). Begründung:

- Bei pathologischem Drift-Verhalten ist die Liste noch lesbar
- Anwender bekommt zuerst die Tage zu sehen, deren Reparatur den größten Effekt hat
- Fußnote in der Detail-Anzeige: *„20 Tage angezeigt; falls weitere existieren, hilft Wartung → Reparatur-Werkbank → Bereich neu aggregieren"*

## 3. Backend-Implementation

### 3.1 Neue Daten-Checker-Kategorie

`backend/services/daten_checker.py`:

```python
class CheckKategorie(str, Enum):
    # ... bestehende ...
    # Etappe 6 v3.31.1: Per-Tag-Drift zwischen TagesZusammenfassung und HA-LTS-Daily.
    # Pro betroffenem Tag ein eigener Eintrag mit Reparatur-Action.
    DATENQUELLE_DRIFT = "datenquelle_drift"
```

### 3.2 Neue Check-Methode

```python
async def _check_datenquelle_drift(self, anlage: Anlage) -> list[CheckErgebnis]:
    """Etappe 6 v3.31.1: Vergleicht TagesZusammenfassung PV-Tagessumme mit
    HA-LTS-Daily-Read für die letzten 90 Tage. Tage über Schwelle bekommen
    einen eigenen Eintrag mit Reparatur-Link.

    Memory-Linien:
      - feedback_reparatur_statt_loesch_features.md (Reparatur-Pfad statt
        Quittier-Button)
      - feedback_kein_grosser_heiler_knopf.md (kein Massen-Reparatur-Knopf
        in der Liste)
      - feedback_daten_checker_kein_akzeptiert.md (keine Quittier-/
        Akzeptiert-Aktion)
    """
```

Pseudocode:

```python
1. Wenn HA-LTS nicht verfügbar → leeres Ergebnis (Standalone, kein Vergleich möglich)
2. von = today - 90 Tage, bis = today - 1 Tag
3. eedc_tageswerte = SELECT TagesZusammenfassung WHERE anlage_id=X AND datum IN [von, bis]
   → pro Tag: pv_eedc = Σ komponenten_kwh[k] für k.startswith(("pv_", "bkw_"))
4. PV-Investitions-Sensor-Map aus sensor_mapping bauen
5. ha_tageswerte = get_komponenten_tageskwh_lts(anlage, invs_by_id, von..bis)
   → pro Tag: pv_ha = Σ komponenten_kwh[k] für k.startswith(("pv_", "bkw_"))
   (Helper-Funktion: bestehender lts_aggregator-Pfad pro Tag oder neuer Bulk-Read)
6. Pro Tag delta = abs(pv_eedc - pv_ha), rel = delta / max(pv_eedc, pv_ha)
7. Filter: delta >= 2.0 AND rel >= 0.05
8. Sortiere nach delta desc, slice [:20]
9. Pro betroffenen Tag: CheckErgebnis(
     kategorie=DATENQUELLE_DRIFT,
     schwere=INFO,  # NICHT Warning — sonst rote Ampeln bei normalem Update-Fall
     meldung=f"{datum}: PV {pv_eedc:.1f} → HA {pv_ha:.1f} kWh (Δ {delta:+.1f}, {rel*100:+.1f}%)",
     link=f"/aussichten/energieprofil?datum={datum}",  # Tagestabelle springt zum Tag
     # NEU: action_payload für Frontend
     action_kind="reaggregate_day",
     action_params={"anlage_id": anlage.id, "datum": datum.isoformat()},
   )
10. Wenn Liste leer → einen OK-Eintrag: "Keine signifikanten Abweichungen zu HA-Statistics in den letzten 90 Tagen"
```

### 3.3 CheckErgebnis um Action-Felder erweitern

Wichtig: **rückwärtskompatibel**, alle anderen Kategorien ignorieren die neuen Felder.

```python
@dataclass
class CheckErgebnis:
    kategorie: str
    schwere: str
    meldung: str
    details: Optional[str] = None
    link: Optional[str] = None
    # Etappe 6 v3.31.1: optionale Inline-Action.
    action_kind: Optional[str] = None       # z.B. "reaggregate_day"
    action_params: Optional[dict] = None    # z.B. {"anlage_id": 1, "datum": "2026-05-15"}
    action_label: Optional[str] = None      # z.B. "Tag reparieren"
```

### 3.4 Register in `_check_all`

```python
ergebnisse.extend(await self._check_datenquelle_drift(anlage))
```

Reihenfolge: **nach** `_check_datenquelle_status` (Logik baut darauf auf).

### 3.5 Performance-Überlegung

90 Tage × Anzahl PV-Sensoren = O(100–1000) Statistics-Reads. Lösung: ein einziger Bulk-Read über `get_hourly_sensor_data(sensor_ids, von, bis)` oder besser einen neuen `get_daily_sum_for_range(sensor_ids, von, bis)` falls noch nicht vorhanden. Im Notfall reicht es, `get_komponenten_tageskwh_lts` 90× zu rufen — bei In-Memory-SQLite-LTS-Read sind das < 200 ms.

## 4. Frontend-Implementation

### 4.1 `CheckErgebnis`-Typ erweitern

`eedc/frontend/src/api/datenChecker.ts`:

```typescript
export interface CheckErgebnis {
  kategorie: string
  schwere: 'ok' | 'info' | 'warning' | 'error'
  meldung: string
  details?: string
  link?: string
  // Etappe 6 v3.31.1
  action_kind?: 'reaggregate_day'
  action_params?: Record<string, unknown>
  action_label?: string
}
```

### 4.2 Kategorie-Label

```typescript
const KATEGORIE_LABELS: Record<string, string> = {
  // ... bestehend ...
  datenquelle_drift: 'Datenquelle – Drift zu HA-Statistics',
}
```

### 4.3 Per-Eintrag-Action-Knopf

In `DatenChecker.tsx` (oder Sub-Komponente, je nach Datei-Struktur): pro `CheckErgebnis` mit `action_kind === 'reaggregate_day'` einen Knopf rendern:

```tsx
{ergebnis.action_kind === 'reaggregate_day' && (
  <Button
    size="sm"
    variant="secondary"
    disabled={busy}
    onClick={() => handleReaggregateDay(ergebnis.action_params)}
  >
    {busy ? <Loader2 className="h-3 w-3 mr-1 animate-spin"/> : null}
    {ergebnis.action_label ?? 'Tag reparieren'}
  </Button>
)}
```

`handleReaggregateDay` ruft den **bestehenden** Endpoint `POST /api/energie-profil/{anlage_id}/reaggregate-tag?datum=YYYY-MM-DD`. Nach erfolgreichem Aufruf:

- Toast: *„Tag 15.05.2026 wurde aus HA-Statistics neu aggregiert"*
- Daten-Checker neu laden (der Eintrag verschwindet, weil Drift jetzt unter Schwelle)

### 4.4 Sammel-Verweis als reiner Text (kein Knopf)

Unter der Liste der Drift-Einträge:

> Mehrere Tage betroffen? Über *Wartung → Reparatur-Werkbank → Bereich neu aggregieren* kannst du einen Datumsbereich am Stück reparieren — bewusst getrennt von dieser Diagnose-Liste, damit nicht versehentlich Massen-Aktionen ausgelöst werden.

## 5. Anti-Patterns explizit vermieden

| Anti-Pattern | Wo verlinkt | Wie vermieden |
|---|---|---|
| „Akzeptiert"-Button quittiert Anomalie | `feedback_daten_checker_kein_akzeptiert.md` | Keine Quittier-Aktion — nur Reparatur. Liste verschwindet *durch* Reparatur. |
| „Großer Heiler-Knopf" Sammel-Reparatur | `feedback_kein_grosser_heiler_knopf.md` | Sammel-Aktion *bewusst nicht* in der Liste — Verweis auf Werkbank statt Inline-Knopf. |
| Lösch-Feature statt Reparatur | `feedback_reparatur_statt_loesch_features.md` | Reparatur-Pfad ist der einzige Pfad. Kein „Drift ignorieren", kein „Tag löschen". |
| Massen-Aktion auf Eingangsdaten | `feedback_grenze_externe_daten_diagnose.md` | Diagnose-Liste; Aktion modifiziert nur die eedc-Aggregat-Tabellen, nicht HA-Daten. |
| Reflexhafte Schwelle ohne Begründung | (`feedback_aggregations_drift.md` Tonalität) | Schwelle 5 % AND 2 kWh in Abschnitt 2.3 begründet, nicht aus dem Bauch. |

## 6. Test-Plan

Backend-Tests (`backend/tests/test_etappe_6_drift_check.py`):

1. **Keine Drift → OK-Meldung**: TagesZusammenfassung-Wert ≈ HA-LTS-Wert für alle Tage → eine OK-Zeile
2. **Drift unter Schwelle → keine Anzeige**: 1 kWh / 3 % drift → nicht in Liste
3. **Drift über Schwelle → Eintrag mit Action**: 3 kWh / 8 % drift → CheckErgebnis mit `action_kind="reaggregate_day"` und korrekten `action_params`
4. **Sortierung nach |Δ| desc**: drei drift-Tage (1,5/6/3 kWh) → Reihenfolge 6, 3, 1,5
5. **Max 20 Einträge**: 25 drift-Tage → 20 Einträge + Footer-Hinweis im letzten `details`
6. **HA-LTS nicht verfügbar → leere Ergebnisliste**: kein Crash, kein Fehler
7. **Frischer User ohne TagesZusammenfassung → leere Ergebnisliste**: kein Crash
8. **Anlage ohne PV-Investition → leere Ergebnisliste**: kein Vergleich möglich

Frontend: kein Unit-Test erforderlich (Render-Layer), nur Smoketest im Add-on.

Suite wächst von 125 auf ~133 Tests.

## 7. Akzeptanz-Kriterien

- [ ] Daten-Checker zeigt neue Kategorie *„Datenquelle – Drift zu HA-Statistics"*
- [ ] Bei aktiver Drift > Schwelle: Liste mit Per-Tag-Einträgen, Δ in kWh und %
- [ ] Reparieren-Knopf neben jedem Eintrag → ein Klick reaggregiert
- [ ] Nach Reparatur: Daten-Checker neu lädt, Eintrag verschwindet
- [ ] Bei keiner Drift: OK-Meldung *„Keine signifikanten Abweichungen"*
- [ ] Keine Massen-Reparatur-Funktion in der Liste
- [ ] Verweis-Text auf Reparatur-Werkbank für Bereichs-Aktion
- [ ] 8 neue Tests grün, bestehende 125 Tests bleiben grün
- [ ] Schwelle (5 % AND 2 kWh) in Tests verankert

## 8. Release-Strategie — Override Bundling-Regel

Memory `feedback_release_bundling.md` sagt: „max 1 Release/Tag, kleine Fixes sammeln". Etappe 6 ist **kein kleiner Fix**, sondern der „so reparierst du die Drift, die wir gerade sichtbar gemacht haben"-Pfad. Ohne ihn nach v3.31.0 hat der Anwender:

- Bessere Architektur ✅
- Aber keine Möglichkeit, *bestehende* Tage sichtbar zu kontrollieren oder zu reparieren ohne externes HA-Energy-Dashboard daneben zu öffnen

**Override begründet**, wenn:

- v3.31.0 morgen früh smoke-grün ist (Add-on startet, Daten-Checker zeigt neue Kategorie)
- Code für Etappe 6 sauber liegt (Tests grün)
- WAS-IST-NEU v3.31.1 klar sagt, was zu tun ist (siehe Abschnitt 9)

**Override nicht zulässig**, wenn:

- v3.31.0-Smoketest Probleme zeigt → erst Hotfix v3.31.1 für die Probleme, Etappe 6 wandert auf v3.31.2 nächsten Tag

Nach Release: Memory-Notiz in `feedback_release_bundling.md` ergänzen — diese Override war begründet, bei Folge-Cases prüfen ob ähnliche Lücke vorliegt.

## 9. WAS-IST-NEU v3.31.1 — Anwender-Anweisung

Eintrag muss **konkret handlungsanleitend** sein, nicht Architektur-Erklärung. Vorschlag:

```markdown
## v3.31.1 — Drift-Diagnose: welche Tage sind betroffen, welche nicht (Mai 2026)

### Sieh dir die Abweichungen zu HA-Statistics an und repariere sie tagesweise

> 🔍 **Direkt nach dem Update v3.31.0 hattest du womöglich Tage in deinem
> Energieprofil, die noch auf den alten Mix-Source-Werten stehen** —
> der Auto-Vollbackfill beim Monatsabschluss füllt nur Lücken, nicht
> bestehende Werte. v3.31.1 macht jetzt im Daten-Checker sichtbar,
> welche Tage signifikant vom HA-Energy-Dashboard abweichen, und legt
> einen Reparieren-Knopf direkt daneben.

#### Was du tun kannst

1. Öffne **Einstellungen → Daten-Checker**
2. Schau nach der neuen Kategorie *„Datenquelle – Drift zu HA-Statistics"*
3. Pro Eintrag ein Klick auf *„Tag reparieren"* — eedc holt die Werte
   direkt aus HA-Statistics und schreibt sie in deine Tages-Zusammenfassung
4. Liste leer → alles sauber, kein Handlungsbedarf

#### Schwelle

Angezeigt werden nur Tage, die *gleichzeitig* mindestens **2 kWh** und
mindestens **5 %** von der HA-Statistics-Tagessumme abweichen — kleine
Boundary-Rauschen wird unterdrückt, damit die Liste fokussiert bleibt.

#### Mehrere Tage auf einmal

Wenn du z. B. einen ganzen Monat reparieren willst, ist
*Wartung → Reparatur-Werkbank → Bereich neu aggregieren* der schnellere
Weg. Bewusst nicht als Massen-Knopf in der Diff-Liste — Massen-Aktionen
sollen aktiv gewählt werden, nicht versehentlich passieren.
```

## 10. Risiken

| Risiko | Wahrscheinlich | Schwere | Gegenmaßnahme |
|---|---|---|---|
| Lange Liste bei Anwendern mit viel altem Drift | mittel | mittel | Schwelle 5 % AND 2 kWh + Max 20 + Sortierung nach |Δ| |
| HA-LTS-Daily-Bulk-Read langsam bei 90 Tagen | niedrig | mittel | Bei > 500 ms: Result-Caching im Service (60-Sek-TTL für Daten-Checker-Ausführung) |
| Reaggregation eines Tages schlägt fehl | niedrig | mittel | Fehler-Toast, Eintrag bleibt in der Liste (kein false „repariert") |
| Anwender klickt Reparieren auf manuell überschriebenen Tag | mittel | hoch | `manual:*`-Provenance gewinnt unbedingt (v3.30.3) — Reaggregation überschreibt manuelle Werte *nicht* |
| Drift-Anzeige für Tage vor erstem HA-Add-on-Tag | mittel | niedrig | HA-LTS-Read liefert für solche Tage keine Daten → Tage werden korrekt nicht in der Liste landen |

## 11. Verbundene Memory-Linien

- [[etappe-4-ha-lts-sot]] — Architektur-Grundlage; Etappe 6 schließt die Anwender-Lücke
- [[user_rainer]] — primärer Beneficiary; Vertrauen wegen Drift verloren
- [[feedback_reparatur_statt_loesch_features.md]] — Reparatur-Pfad ist der einzige Pfad
- [[feedback_kein_grosser_heiler_knopf.md]] — kein Sammel-Reparatur in der Liste
- [[feedback_daten_checker_kein_akzeptiert.md]] — keine Quittier-Aktion
- [[feedback_release_bundling.md]] — Override für diesen Use-Case begründet
- [[feedback_grenze_externe_daten_diagnose.md]] — Diagnose statt stillem Cap, gleiche Linie

## 12. Implementierungs-Reihenfolge (für morgen)

Wenn v3.31.0-Smoketest grün ist:

1. **Backend** — `_check_datenquelle_drift` in `daten_checker.py`, Kategorie ergänzen, in `_check_all` registrieren (~80 Zeilen)
2. **Backend** — `CheckErgebnis` um `action_kind`/`action_params`/`action_label` erweitern (~5 Zeilen)
3. **Tests** — `test_etappe_6_drift_check.py` mit 8 Tests
4. **Frontend** — `datenChecker.ts` Typ-Erweiterung (~5 Zeilen)
5. **Frontend** — `DatenChecker.tsx` Action-Knopf-Rendering + Reaggregate-Aufruf (~50 Zeilen)
6. **Docs** — CHANGELOG.md + WAS-IST-NEU.md v3.31.1-Eintrag (Abschnitt 9 oben kopieren)
7. **Release** — `./scripts/release.sh 3.31.1`
8. **Smoketest v3.31.1** — Daten-Checker → Drift-Kategorie sichtbar → Reparieren-Knopf funktioniert

Geschätzter Aufwand: 2–3 Stunden bis Release.

## Anti-Pattern dokumentiert

**„Sichtbare Probleme ohne Reparatur-Pfad"** — Etappe 4 hätte die Drift-Wahrheit beobachtbar machen können (z. B. durch Logging oder Telemetrie), ohne dem Anwender ein Werkzeug zu geben. Das wäre die nächste Stufe der Lach-Nummer gewesen: „eedc weiß dass deine Werte falsch sind, sagt es dir aber nicht." Etappe 6 schließt diese Lücke — und stellt damit das Prinzip wieder her, dass jede sichtbare Diagnose einen begehbaren Reparatur-Pfad hat.
