# Audit Energieprofil + Reparatur-Werkbank (v3.33.0 → v3.34)

> **Stand:** 2026-05-24, nach Release v3.33.0 (commit `5cb5afc0`). Reine Inventur — kein Code geändert.
> **Quelle:** Code-Lesung gegen den aktuellen `main`-HEAD. Konzept-Docs `KONZEPT-ENERGIEPROFIL-3C.md`, `KONZEPT-DATENPIPELINE.md`, `KONZEPT-ETAPPE-4-HA-LTS-SOT.md`, `ADR-001-BERECHNUNGS-LAYER.md` als Soll-Referenz.
> **Zweck:** Sichtungsbasis vor strukturellem v3.34-Refactor; KEIN Auftrag.
>
> Vorgaben aus dem Auftrag: Scope strikt auf Energieprofil + Reparatur-Werkbank. Skeptisch lesen: Defense-in-Depth-Begründungen sind verdächtig. Hypothesen zurückweisen, wenn etwas nicht passt.

## 0. Hypothesen-Review zum Auftrag

Der Auftrag liest die zwei Subsysteme als „über mehrere Releases organisch gewachsen mit mehreren parallelen Schreib-/Lese-Pfaden und Übergangs-Patches" und postuliert für v3.34 „ein zentraler Schreibpfad und dünne Quellen-Adapter". Nach der Inventur:

- **Stimmt im Grundsatz.** Es existieren tatsächlich zwei vollständig parallele Schreib-Pipelines (`energie_profil/aggregator.py::aggregate_day` und `energie_profil/backfill.py::backfill_from_statistics`), die TEP+TZ duplizieren — sowie zwei Schichten von Quellenwahl (Hourly-kWh: LTS vs Snapshot; Boundary-kWh: LTS vs Snapshot). v3.33.0 hat die Boundary-Symmetrie wiederhergestellt, die Hourly-Symmetrie ist noch latent verletzt (siehe §6.2).
- **Scope-Erweiterung empfohlen.** `services/sensor_snapshot_service` (Re-Export-Fassade aus 3c P1) ist im Auftrag nicht erwähnt, lebt aber als Fassade über `services/snapshot/*` und wird vom Aggregator + Backfill konsumiert — sie ist Teil derselben Werkbank-Kette. Habe sie mit aufgenommen.
- **Schnitt-Frage zurück an dich:** Der Auftrag listet `backend/services/monatsabschluss_aggregator.py` als In-Scope, schließt aber „Monatsabschluss-Wizard" aus. Das Modul macht beides — es triggert `backfill_range` + `rollup_month` + ggf. `resolve_and_backfill_from_statistics`. Ich habe nur die TEP/TZ-Aspekte aufgenommen; der Monatsdaten-Rollup-Teil (`rollup.py`) bleibt aus dem Audit ausgespart, weil er auf `Monatsdaten` schreibt und damit eher zum Monatsabschluss-Subsystem gehört. **Bitte bestätigen oder korrigieren.**
- **Zwei Handover-Dokumente offen.** [`HANDOVER-lts-aggregator-fix.md`](HANDOVER-lts-aggregator-fix.md) ist mit v3.33.0 abgearbeitet (verifiziert: `komponenten_beitraege.py` existiert, beide Aggregatoren konsumieren ihn, Invariante ist erweitert). [`HANDOVER-hourly-categorize-eauto-doppelmapping.md`](HANDOVER-hourly-categorize-eauto-doppelmapping.md) ist offen und ein **strukturelles Argument**, den Helper auch in den Hourly-Pfad zu ziehen (siehe §6.2 + §10).

## 0.5 Pattern-Diagnose aus der Vorgeschichte

> Reine Befundlage aus Memory und CHANGELOG. **Keine Empfehlung an dieser Stelle** — die Frage „lokale Tests vs strukturellem Schnitt" beantwortet die Fix-Session aus diesen Daten heraus.

- **Memory `feedback_aggregations_drift`:** zählt 10+ dokumentierte Drift-Vorfälle auf den Aggregat-Tabellen; letzter Eintrag #290 (LTS-Aggregator-Drift v3.33.0). Eingang in Memory bedeutet: jeder Vorfall wurde im Moment des Fix als „strukturell, nicht zufällig" eingestuft.
- **Memory `feedback_aggregator_symmetrie`:** entstand erst nach #290 als ausdrückliche Lehre — bei zwei parallelen Implementierungen derselben Aggregations-Logik müssen Symmetrie-Tests existieren. Bedeutet: bis v3.33.0 lief das Subsystem **ohne** diese Sicherung, und die Lehre wurde von einem konkreten Anwender-Bug erzwungen, nicht prophylaktisch gezogen.
- **CHANGELOG-Sequenz:** v3.31.7 (Korrekturprofil-Stundenprofil verloren) → v3.32.4 (vier parallele Symptompatches für #290: preserve, Skip today, Field-Restore, Docstring) → v3.33.0 (strukturelle Sanierung des Daily-Pfads, Datenmigration) — alle innerhalb von 13 Tagen, derselbe Aggregator-Komplex.
- **Offene Handover-Dokumente:** [`HANDOVER-hourly-categorize-eauto-doppelmapping.md`](HANDOVER-hourly-categorize-eauto-doppelmapping.md) — der nächste latente Drift-Vorfall ist schon dokumentiert (`_categorize_counter` Hourly-Pfad), wartet auf eigene Session. Pattern-Bestätigung: dieselbe Bug-Klasse wie der gerade in v3.33.0 strukturell sanierte Daily-Pfad, eine Etage tiefer, noch nicht erschlagen.
- **Vorfallsdichte:** geschätzt ~1 Aggregator-Drift-Vorfall pro Monat über die letzten ~10 Monate. Jeder Fix war lokal — Symptompatches in §4 dokumentieren das Pattern: 12 isolierte Konstrukte, davon mindestens sechs eindeutig symptomatisch (kein dokumentierter struktureller Folge-Plan).

→ Die Vorgeschichte legt die Vermutung nahe, dass jeder neue lokale Fix die Bugfläche nicht reduziert, sondern um eine weitere Sonderfall-Verzweigung erweitert. Strukturschnitt (siehe §10) oder weitere Konformitäts-Tests in der heutigen Doppel-Pipeline — die Wahl gehört in die Fix-Session, nicht in den Audit.

---

## 1. Inventur der Schreibpfade auf `tages_energie_profil` (TEP) und `tages_zusammenfassung` (TZ)

| # | Trigger | Funktion / Code-Stelle | Was wird geschrieben | Quelle (kWh) | Provenance-Source |
|---|---|---|---|---|---|
| 1 | Scheduler 00:15 täglich (Vortag) | `scheduler_jobs.aggregate_yesterday_all` → `aggregate_day(datenquelle="scheduler")` | TEP × 24 + TZ (komplettes Delete+Insert), `komponenten_kwh`, `komponenten_starts` | LTS bevorzugt, Snapshot-Fallback | TEP: `external:ha_statistics:hourly` oder `auto:monatsabschluss`; TZ: `external:ha_statistics:daily` oder `auto:monatsabschluss` |
| 2 | Scheduler alle 15 min (heute) | `scheduler_jobs.aggregate_today_all` → `aggregate_day(datenquelle="scheduler")` | wie #1 | wie #1 | wie #1 |
| 3 | Monatsabschluss-Wizard Save (Background) | `monatsabschluss_aggregator.run_post_monatsabschluss_aggregation` → `backfill_range` → `aggregate_day(datenquelle="monatsabschluss")` | wie #1, pro Tag des Monats | wie #1 | TEP: gleich; TZ: `external:ha_statistics:daily` oder `auto:monatsabschluss` |
| 4 | Reparatur-Werkbank „Tag neu aggregieren" | `repair_orchestrator._execute_reaggregate_day` → optional `resnap_anlage_range` + `aggregate_day(datenquelle="manuell")` | wie #1 | wie #1 | TZ: Writer `energieprofil:manuell`; Source siehe #1 |
| 5 | Reparatur-Werkbank „Mehrere Tage neu aggregieren" | `repair_orchestrator._execute_reaggregate_range` → Schleife wie #4, per-Tag-commit | wie #1 | wie #1 | wie #4 |
| 6 | Reparatur-Werkbank „Heutigen Tag neu aggregieren" | `repair_orchestrator._execute_reaggregate_today` → `aggregate_today_all` (alle Anlagen!) | wie #1 | wie #1 | wie #1 |
| 7 | Reparatur-Werkbank „Vollbackfill" + Monatsabschluss-Erstlauf | `_execute_vollbackfill` → `resolve_and_backfill_from_statistics` → `backfill_from_statistics` | TEP × 24 + TZ pro **fehlendem** Tag im Range (additiv); Tage mit existierendem TZ werden übersprungen | HA-LTS hourly direkt (`get_hourly_sensor_data` 1-Schwung), Snapshot-Boundary-Diff für `komponenten_kwh` | TEP + TZ: `external:ha_statistics`, Writer `ha_statistics_backfill` |
| 8 | Live-Wetter-Endpoint Prognose-Push | `live_wetter._speichere_prognose` (Z. 873) → INSERT TZ nur mit Prognose-Feldern wenn TZ noch nicht existiert; sonst UPDATE per Feld | TZ-Felder `pv_prognose_kwh`, `sfml_prognose_kwh`, `solcast_prognose_kwh`, `solcast_p10/p90`, `pv_prognose_stundenprofil`, `solcast_prognose_stundenprofil`, `datenquelle="wetter_prognose"` | Wetter-/Solcast-/SFML-Services | je Feld: `external:openmeteo` / `external:sfml` / `external:solcast` |
| 9 | Kraftstoffpreis-Backfill (Werkbank `KRAFTSTOFFPREIS_BACKFILL`) | `kraftstoff_preis_service.backfill_kraftstoffpreise` (Z. 346) | TZ.`kraftstoffpreis_euro` pro Tag (via `write_with_provenance`) | EU Oil Bulletin | `external:eu_oil_bulletin` |
| 10 | DELETE-Endpoints | `routes/energie_profil/repair.delete_rohdaten` / `delete_alle_rohdaten` | TEP + TZ Bulk-Delete | — | — (löscht alles inkl. Provenance) |

### Beobachtungen Schreibseite

- **#1, #2, #3, #4, #5, #6 sind alle derselbe Code-Pfad** — `aggregate_day` mit nur dem `datenquelle`-String unterschiedlich. Gut. Aber: drei der sechs Trigger setzen `datenquelle="scheduler"`, einer `"monatsabschluss"`, einer `"manuell"`. Der String wandert in `TagesZusammenfassung.datenquelle` (String-Spalte VARCHAR(30)) **und** wird im selben Modul (`aggregator.py:581/589`) als Verzweigungs-Trigger für die `preserved_komponenten_kwh`-Logik verwendet. Das ist eine semantische Doppelnutzung: das Feld dient gleichzeitig der UI-Anzeige der Datenquelle UND der Steuerung des Schreib-Verhaltens. Saubere Trennung wäre ein eigener Parameter `is_manual_repair: bool`.
- **#7 ist eine vollständige Code-Kopie von #1.** `backfill_from_statistics` hat eine eigene Stunden-Schleife, eigene Pre-Aggregation, eigene Komponenten-Aggregation, eigene Peak-Berechnung, eigenes Delete-and-Recreate, eigene Prognose-Rettungsliste (mit **nur 5 Feldern** statt 7 wie in `_PROGNOSE_FELDER_RETTEN`, siehe §5). Lt. CHANGELOG ein Drift-Vorfall ist genau in dieser Asymmetrie schon einmal entstanden (Korrekturprofil leer, 2026-05-21, v3.31.7). Die strukturelle Lehre wurde NICHT gezogen — der Code-Pfad bleibt dupliziert.
- **#8 ist der zweite Schreiber auf TZ neben dem Aggregator.** Er hängt nicht am Aggregator-Lebenszyklus und erklärt die `_PROGNOSE_FELDER_RETTEN`-Liste: Aggregator macht Delete-and-Recreate; um die asynchron geschriebenen Prognose-Felder nicht zu verlieren, werden sie pro Tag in den Aggregator hineingelesen, im Speicher gehalten, und nach dem Recreate wieder zurückgeschrieben. **Diese Konstruktion ist die strukturelle Wurzel mehrerer Vorfälle** (siehe §4) — die Liste muss perfekt mit `live_wetter._speichere_prognose` synchron bleiben, jeder neue Prognose-Pfad braucht hier einen Eintrag, sonst geht der Wert jede Nacht verloren.

## 2. Inventur der Lesepfade

### 2.1 Lesepfade direkt im Energieprofil-Scope

| Konsument | API/Code-Stelle | Liest aus | Wo angezeigt |
|---|---|---|---|
| Tage-Tab | `GET /api/energie-profil/{id}/tage` ([views.py:56](../../eedc/backend/api/routes/energie_profil/views.py#L56)) | TZ direkt (alle Felder + `komponenten_kwh` + `komponenten_starts`) | Energieprofil-Tab → „Tage"-Untertab + `EnergieprofilTageTabelle.tsx` |
| Stunden-Tab (TD) | `GET /api/energie-profil/{id}/stunden` ([views.py:169](../../eedc/backend/api/routes/energie_profil/views.py#L169)) | TEP × 24 + `komponenten`-JSON pro Stunde + aufgelöste Serien-Labels | Energieprofil-Tab → „TD"-Untertab |
| Komponenten-Serien | `GET /api/energie-profil/{id}/komponenten-serien` ([views.py:119](../../eedc/backend/api/routes/energie_profil/views.py#L119)) | TZ.komponenten_kwh-Keys über Range | Tagestab als Spalten-Definition |
| Wochenmuster | `GET /api/energie-profil/{id}/wochenmuster` ([views.py:245](../../eedc/backend/api/routes/energie_profil/views.py#L245)) | TEP über Range, gruppiert Wochentag × Stunde | Energieprofil-Tab → Wochenvergleich-Chart |
| Monatsauswertung | `GET /api/energie-profil/{id}/monat` ([views.py:310](../../eedc/backend/api/routes/energie_profil/views.py#L310)) | TEP + TZ (Peaks, Vollzyklen, PR, Börsenpreis, Komponenten-Aggregat, Heatmap) | `EnergieprofilMonat.tsx` (Heatmap + KPIs + Top-N-Peaks) |
| Tagesprognose | `GET /api/energie-profil/{id}/tagesprognose` ([views.py:915](../../eedc/backend/api/routes/energie_profil/views.py#L915)) | TEP.soc_prozent + Verbrauchsprofil-Service + PV-Forecast | `EnergieprofilPrognose.tsx` |
| Reaggregate-Preview | `GET /api/energie-profil/{id}/reaggregate-tag/preview` ([views.py:803](../../eedc/backend/api/routes/energie_profil/views.py#L803)) | `get_reaggregate_preview` (DB-Snapshots **vs.** Live-HA-LTS-Read) | `ReaggregatePreviewModal.tsx` (alt/neu-Diff-Tabelle) |
| Debug-Rohdaten | `GET /api/energie-profil/{id}/debug-rohdaten` | TEP letzte 7 Tage roh | Diagnose, unsichtbar im UI |
| Verfügbare Monate | `GET /api/energie-profil/{id}/verfuegbare-monate` | TZ-Distinct-Jahr/Monat | Selektor |
| Stats | `GET /api/energie-profil/{id}/stats` | Counts + Min/Max-Datum | Energieprofil-Datenverwaltung-Sektion |
| Reaggregate-Repair-Response | `POST /api/energie-profil/{id}/reaggregate-tag` (Response-Felder `pv_kwh_alt/neu` + `stunden_mit_messdaten`) | TZ + TEP nach Aggregat — eigener `_pv_tagessumme`-Helper + `_stunden_mit_messdaten`-Helper in [repair.py](../../eedc/backend/api/routes/energie_profil/repair.py) | Reaggregate-Preview-Modal Erfolgsmeldung |

### 2.2 Lesepfade aus dem Energieprofil-Datenmodell ausserhalb des Scope (Notiz)

Aus Vollständigkeit, weil sie das Refactor-Risiko bestimmen — aber NICHT im Audit-Scope:

- `routes/prognosen.py:643` liest `tz.komponenten_kwh` via `summe_pv_bkw_kwh` für Genauigkeits-Tracking
- `services/daten_checker.py:2014, 2136` liest `tz.komponenten_kwh` für Drift-Erkennung + ruft `get_komponenten_tageskwh_lts` für Live-Vergleich
- `routes/energie_profil/repair.py:226-228` (`_pv_tagessumme`) liest dieselbe Funktion für Reaggregate-Alt/Neu-Anzeige
- Cockpit-Übersicht + Aussichten konsumieren ebenfalls TZ (`summe_pv_bkw_kwh`, `summe_waermepumpe_kwh`, …), siehe `core/berechnungen/energie.py`

→ TZ.komponenten_kwh ist das **zentrale verteilte JSON-Aggregat** der Anwendung; die Berechnungs-Layer-Wrapper sind die einzige saubere Read-Schnittstelle. Jede strukturelle Änderung am Aggregator-Schema bricht alle Read-Sites.

## 3. Quellen-Switches und Fallback-Ketten

Ein wichtiger Befund — es gibt **drei Switch-Schichten**, die alle dieselbe Quellenwahl-Frage in unterschiedlicher Granularität abbilden.

### 3.1 Schicht A — Hourly-kWh (TEP × 24)

[`energie_profil/aggregator.py:200-233`](../../eedc/backend/services/energie_profil/aggregator.py#L200-L233):

```text
try:    kwh_pro_stunde = get_hourly_kwh_by_category_lts(...)    → kwh_source_label = "external:ha_statistics:hourly"
except: kwh_pro_stunde = {}
if not kwh_pro_stunde:
    try:    kwh_pro_stunde = get_hourly_kwh_by_category(...)    → kwh_source_label = "auto:monatsabschluss"
    except: kwh_pro_stunde = {}
```

- **HA-Add-on-Pfad:** LTS gewinnt (Etappe 4)
- **Standalone-Pfad:** Snapshot-Variante gewinnt
- **Standalone-mit-degradiertem-Snapshot-Pfad:** weder LTS noch Snapshot — leeres Dict, alle Stunden None

### 3.2 Schicht B — Live-Σ-Riemann-Bypass

[`energie_profil/aggregator.py:397`](../../eedc/backend/services/energie_profil/aggregator.py#L397):

```python
if werte and kwh_source_label != "external:ha_statistics:hourly":
    for komp_key, komp_kw in werte.items():
        komponenten_summen[komp_key] = ... + komp_kw
```

- **Wenn HA-LTS-Pfad aktiv:** Live-Σ-Riemann wird **übersprungen**, Komponenten kommen exklusiv aus Boundary (Schicht C)
- **Wenn Snapshot-Pfad aktiv:** Live-Σ-Riemann läuft mit, `werte`-Keys aus dem Live-Tagesverlauf-Service landen direkt in `komponenten_summen`
- **Kommentar im Code:** „bei Schema-Mismatch zwischen Live-Service-Key und Boundary-Key (z.B. balkonkraftwerk → Live `pv_<id>`, Boundary `bkw_<id>`) blieben beide Keys parallel in `komponenten_summen` und wurden von Whitelist-Konsumenten doppelt gezählt (BKW-Bug 2026-05-19, Rainer-PN)." → Die Bypass-Bedingung ist der Patch dieses Bugs. **Sie verschiebt die Drift in den Standalone-Pfad**, statt sie strukturell zu lösen.

### 3.3 Schicht C — Boundary-kWh (TZ.komponenten_kwh)

[`energie_profil/aggregator.py:508-535`](../../eedc/backend/services/energie_profil/aggregator.py#L508-L535):

```text
boundary_kwh = {}
if datum >= today:                                          → SKIP (Bug B Symptompatch; siehe §4)
elif kwh_source_label == "external:ha_statistics:hourly":
    boundary_kwh = get_komponenten_tageskwh_lts(...)
if not boundary_kwh and datum < today:                       → Fallback wenn LTS leer
    boundary_kwh = get_komponenten_tageskwh(...)             → Snapshot-Variante
```

- Drei Verzweigungspunkte: `datum >= today`, `kwh_source_label`-Wert, `boundary_kwh` empty.
- Die `boundary_kwh`-Werte **überschreiben** die Live-Σ-Riemann-Werte aus Schicht B im selben `komponenten_summen`-Dict (Z. 536-537). Reihenfolge der Schichten ist die einzige Konfliktauflösung.

### 3.4 Schicht D — Backfill-Pfad hat seine **eigene** Boundary-Logik

[`energie_profil/backfill.py:605-617`](../../eedc/backend/services/energie_profil/backfill.py#L605-L617): nutzt **immer** die Snapshot-Variante `get_komponenten_tageskwh`, **nie** die LTS-Variante. Asymmetrisch zu Aggregator-Schicht C. Begründung im Code: keine.

### 3.5 Schicht E — Snapshot-Read selbst hat noch eine Heilkaskade

[`snapshot/reader.py:79-163`](../../eedc/backend/services/snapshot/reader.py#L79):

1. DB-Lookup `sensor_snapshots` (±5 min)
2. HA-Statistics (±10 min) — bei Treffer wird zusätzlich **upsert** in DB (selbstheilend)
3. MQTT-Energy-Snapshot (±10 min)

Markert die geheilte Zeile mit `SnapshotSource.HA_STATISTICS` oder `SnapshotSource.LIVE_FALLBACK`.

### 3.6 Karte: welche Quelle gewinnt wann

| Modus | Hourly kWh | Live-Σ Bypass | Boundary kWh |
|---|---|---|---|
| HA-Add-on, normal | LTS direkt | übersprungen | LTS direkt |
| HA-Add-on, LTS-Lücke (ein Sensor fehlt LTS) | Snapshot mit Self-Heal aus LTS+MQTT | Live-Σ aktiv | Snapshot mit Self-Heal |
| HA-Add-on, `datum >= today` | LTS direkt | übersprungen | **SKIP** — komponenten_kwh kommt allein aus Σ-Hourly (Schicht A summiert in 397-400) |
| Backfill HA-LTS (manueller Vollbackfill) | LTS direkt (`get_hourly_sensor_data` einmal pro Range) | nie aktiv (eigener Codepfad) | **Snapshot-Variante**, asymmetrisch zu Aggregator |
| Standalone-MQTT | Snapshot aus MQTT-Snapshots | Live-Σ aktiv | Snapshot, kein LTS-Versuch |
| Manuelle Reaggregation, HA-LTS leer + Snapshot korrupt | leeres `kwh_pro_stunde`, dann leeres `boundary_kwh`, dann `preserve_komponenten_kwh` greift (#290 Bug A) | übersprungen | preserve |

→ **Sechs distinkte Pfade**, davon ist nur einer im Standardfall klar dokumentiert (HA-Add-on normal). Alle anderen sind aus Inline-Kommentaren rekonstruierbar.

## 4. Skip-/Preserve-/Delete-and-Recreate-Logiken

Dies ist der dichteste Symptompatch-Cluster. Ich liste alle gefundenen Stellen, bewerte als **strukturell** (die Wurzelursache lebt anderswo, der Schutz hier ist legitim) oder **symptomatisch** (lokal eingepflasterter Workaround).

### 4.1 `_PROGNOSE_FELDER_RETTEN` ([aggregator.py:42-50](../../eedc/backend/services/energie_profil/aggregator.py#L42))

```python
_PROGNOSE_FELDER_RETTEN: tuple[str, ...] = (
    "pv_prognose_kwh", "sfml_prognose_kwh", "solcast_prognose_kwh",
    "solcast_p10_kwh", "solcast_p90_kwh",
    "pv_prognose_stundenprofil", "solcast_prognose_stundenprofil",
)
```

**Wogegen schützt es?** Aggregator macht Delete+Insert auf TZ. Ohne diese Liste verlöre der Aggregator alle Felder, die der Wetter-Endpoint asynchron in dieselbe TZ-Zeile geschrieben hat.

**Bewertung:** Symptomatisch. Die Wurzel ist die Konstruktion „TZ wird von zwei verschiedenen Schreibern bedient und der eine macht Delete+Insert". Ein UPDATE-statt-DELETE+INSERT-Schema, oder ein eigener `tages_prognose`-Table, würde die Rettungsliste obsolet machen. Vorfall 2026-05-21 (`pv_prognose_stundenprofil` fehlte → Korrekturprofil-Heatmap dauerhaft leer) zeigt, dass die Liste in der Praxis bricht — sie verlangt manuelle Synchronität mit einer remote Codestelle. Backfill hat **eine eigene Kopie der Liste** mit nur 5 Feldern (Z. 543-547 in [backfill.py](../../eedc/backend/services/energie_profil/backfill.py#L543)), die seit dem #190-Fix nie aktualisiert wurde.

**Korrektur gegenüber der ersten Audit-Lesung:** der Backfill-Code-Pfad, der die 5-Felder-Liste anwendet, wird durch den `existing_dates`-Skip oben (Z. 311-315) heute **strukturell neutralisiert** — Backfill verarbeitet nur Tage ohne existierende TZ, und auf diesen Tagen ist `existing_tz_row` (Z. 541) konsequent `None`, also die preserve-Schleife läuft leer. Der einzige Pfad, in dem die Liste real greift, ist ein enges Race-Fenster (Wetter-Endpoint legt zwischen `existing_dates`-Range-Lookup und Pro-Tag-Verarbeitung eine TZ mit Stundenprofil an). Praktisch eng, weil Vollbackfill typisch auf historische Tage (bis gestern) läuft und `_speichere_prognose` typisch auf heute/morgen. **Drift-Risiko-Stelle ohne akuten Schaden** — wird sofort scharf, sobald jemand den Skip lockert (z.B. wenn ein Overwrite-Modus jemals re-introduziert wird, gegen `feedback_vollbackfill_nur_additiv`). Konformitäts-Test als günstige Vorab-Sicherung ist sinnvoll; ein Hotfix-Release rechtfertigt der Befund nicht.

### 4.2 `preserved_komponenten_kwh` + `preserved_komponenten_starts` ([aggregator.py:260-273, 575-592](../../eedc/backend/services/energie_profil/aggregator.py#L260))

```python
preserved_komponenten_kwh = (
    dict(existing_tz_row.komponenten_kwh)
    if existing_tz_row and existing_tz_row.komponenten_kwh else None
)
...
komponenten_kwh=(
    {k: round(v, 2) for k, v in komponenten_summen.items()}
    if komponenten_summen
    else (preserved_komponenten_kwh if datenquelle == "manuell" else None)
),
```

**Wogegen schützt es?** „HA-LTS nicht erreichbar + alte Snapshots in DB inkonsistent → Boundary-Diff liefert Müll, Σ-Hourly liefert 0" (#290 detLAN Punkt 4). Ohne Preserve würde der manuelle Reaggregations-Knopf existierende richtige Werte mit None überschreiben.

**Bewertung:** Symptomatisch, aber **legitim und stabil** — solange das Snapshot-System sich nicht selbst heilen kann, bleibt die Konstellation real. Das CHANGELOG sagt explizit „Die Preserve-Logik bleibt als defensiver Schutz" — bewusste Entscheidung. Allerdings: die `datenquelle == "manuell"`-Verzweigung ist nicht symmetrisch — auch ein `scheduler`-Lauf für gestern bei nicht erreichbarem HA überschreibt mit None. Der Schutz greift nur, wenn der User selbst „neu aggregieren" klickt.

**Klärung in v3.34.0-Sichtungs-Session (2026-05-24):** Die Asymmetrie ist eine **Pattern-Adaption aus dem Monatsdaten-Kontext**, nicht eine eigenständige TZ-Entscheidung. Im Monatsdaten-Kontext schützt das Preserve-Pattern manuell editierte Werte (User-Eingabe in der Monats-Editor-UI) vor Scheduler-Überschreibung. In `TagesZusammenfassung` gibt es keine manuelle Werteingabe; „manuell" bedeutet hier „Werkbank-Trigger" (heute `Source.MANUAL_REPAIR`). Die Übertragung in den TZ-Aggregator erfolgte in v3.32.4 (#290) als defensive Maßnahme bei nicht erreichbarem HA-LTS + inkonsistenten Snapshots — also als vorsichtige Pattern-Adaption aus einem semantisch verwandten Bereich, ohne dass die Adaption im TZ-Kontext eigens durchargumentiert wurde. Der `aggregator.py:582`-Kommentar trägt diese Geschichte seit v3.34.0. **Folge-Frage für Phase B / spätere Etappe:** Mit verbessertem Snapshot-Self-Healing seit v3.33.0 (geteilter Helper, Symmetrie-Tests) könnte der Schutz im TZ-Kontext heute überflüssig sein. Eigene Sichtung wert, weil die Adaption ohne TZ-Vorfall entstand und damit auch ohne TZ-Vorfall überprüft werden sollte.

### 4.3 Skip von Boundary-Diff für `datum >= today` ([aggregator.py:509-513](../../eedc/backend/services/energie_profil/aggregator.py#L509))

```python
if datum >= date.today():
    logger.debug(... "Boundary-Diff übersprungen für laufenden Tag")
elif kwh_source_label == "external:ha_statistics:hourly":
    boundary_kwh = get_komponenten_tageskwh_lts(...)
```

**Wogegen schützt es?** „bei `datum >= today` existiert `snap[Folgetag 00:00]` noch nicht. Self-Healing fällt auf HA-history zurück und liefert den AKTUELLEN Counter-Stand statt einen sauberen Tagesgrenz-Wert → Drift gegen Σ-Hourly" (#290 Bug B).

**Bewertung:** Mischmasch. Die Wurzelursache ist **nicht** „Boundary-Diff für heute ist sinnlos" (das ist sie), sondern „Self-Healing-Read greift bei nicht existenter Boundary auf nearest-now-Wert zurück und das wird semantisch nicht erkannt". Sauberer wäre: `get_snapshot()` würde für einen Zeitpunkt in der Zukunft einfach `None` zurückgeben, ohne Heilung. Oder: `get_komponenten_tageskwh{,_lts}` würden selbst erkennen, dass die End-Boundary in der Zukunft liegt. Stattdessen wird die Verantwortung an den Aufrufer geschoben.

### 4.4 Tagesreset-Schutz in `_diff` ([snapshot/aggregator.py:215-225, 408-411, 543-545](../../eedc/backend/services/snapshot/aggregator.py#L215))

```python
if d < -0.01:
    # Tagesreset-Zähler (HA utility_meter mit daily cycle): s0 ≈ Tagesendwert,
    # s1 ≈ 0 nach Mitternachts-Reset. Slot wird mit s1 gewertet statt verworfen...
    if s1 < 0.5 and s0 > 0.5:
        d = max(0.0, s1)
```

**Wogegen schützt es?** HA `utility_meter` mit daily cycle resettet um Mitternacht; ohne Schutz würde Slot 0 dauerhaft None ergeben.

**Bewertung:** Strukturell. Die Heuristik (`s1 < 0.5`) ist eine pragmatische Magic-Number, aber das Pattern ist real und betrifft auch andere Counter-Typen. Akzeptabel.

### 4.5 Self-Healing-Read mit Toleranz-Fenstern ([reader.py:60, 86, 103](../../eedc/backend/services/snapshot/reader.py#L86))

```python
toleranz_minuten: int = 5,           # DB-Lookup
ha_toleranz_minuten: int = 10,       # HA-Statistics-Fallback
toleranz_minuten: int = 10,          # MQTT-Snapshot-Fallback
```

**Wogegen schützt es?** Verschiedene Latenzen der Quellen.

**Bewertung:** Strukturell, aber die drei Magic-Numbers sind voneinander entkoppelt und alle inline. Sauberer wäre ein Konstanten-Block oben in `reader.py` oder in `snapshot/source.py`. Außerdem: der `_get_mqtt_snapshot_at`-Docstring erklärt, dass das Fenster mal `30` war und auf `10` reduziert wurde — bei jeder Anpassung müssen drei Stellen synchron gehalten werden.

### 4.6 Spike-Cap als Lücke ([snapshot/plausibility.py:43-71](../../eedc/backend/services/snapshot/plausibility.py#L43))

```python
SPIKE_FAKTOR_STUNDE = 1.5
...
if abs(wert_kwh) <= schwelle_kwh:
    return wert_kwh
logger.warning(...)
return None
```

**Wogegen schützt es?** HA-Counter-Off-by-ones nach Restarts (Forum #529 Klausnn, dietmar1968).

**Bewertung:** Symptomatisch, aber gut isoliert. Das Konstrukt setzt den Wert auf `None`, was zur Lücke führt, die Selbstheilung dann später auffüllen sollte. **Verdächtig: feedback_grenze_externe_daten_diagnose-Memory** sagt „kein stummes Cap, lieber Diagnose". Hier ist der Cap zwar mit `logger.warning` versehen, aber Daten-Checker zeigt ihn nicht prominent dem User. Frage zurück: ist der jetzige Mechanismus konform mit der Memory-Regel, oder ist das eine Ausnahme die dokumentiert werden müsste?

### 4.7 Counter-Plausibilitäts-Cap ([snapshot/aggregator.py:532-552](../../eedc/backend/services/snapshot/aggregator.py#L532))

```python
MAX_PLAUSIBLE_COUNTER_PER_HOUR = 200
...
elif d > MAX_PLAUSIBLE_COUNTER_PER_HOUR:
    logger.warning(...)
    d = 0
```

**Wogegen schützt es?** „HA-Statistics-Spikes nach Restarts (sum=NULL → state-Fallback, #184) können dagegen Werte in der Größenordnung 10⁴ produzieren".

**Bewertung:** Symptomatisch. Wurzel ist HA-recorder-Verhalten, lokal abgefangen.

### 4.8 Backfill-Boundary-Fallback (Schicht D, [backfill.py:601-617](../../eedc/backend/services/energie_profil/backfill.py#L601))

Backfill nutzt fest die Snapshot-Variante `get_komponenten_tageskwh`, nicht die LTS-Variante — obwohl es vorher per HA-Statistics-Direct-Read die Stunden-Werte holt.

**Wogegen schützt es?** Vermutlich nichts; das ist schlicht eine Asymmetrie, die nie aktualisiert wurde, als die LTS-Variante in v3.31.0 entstand. Da Backfill nur additiv läuft (auf Tagen ohne TZ), war der Pfad nie offensichtlich auffällig.

**Bewertung:** Latenter Drift-Risiko (siehe §8.2).

### 4.9 Live-Σ-Bypass bei LTS-Pfad ([aggregator.py:397](../../eedc/backend/services/energie_profil/aggregator.py#L397))

Siehe §3.2.

**Bewertung:** Symptomatisch — Wurzel ist BKW-Schema-Mismatch zwischen `live_tagesverlauf_service` (`pv_<id>` für BKW) und `snapshot/aggregator.py` (`bkw_<id>` für BKW). Sauberer wäre, die Key-Konvention zwischen beiden Pfaden zu harmonisieren statt den parallelen Schreiber zu deaktivieren. Heute funktioniert es, weil der HA-Add-on-Pfad nur einen Pfad nutzt — aber im Standalone-Pfad lebt das Drift-Risiko weiter.

### 4.10 Pool-Doppelzählungs-Schutz ([live_tagesverlauf_service.py:166-180](../../eedc/backend/services/live_tagesverlauf_service.py#L166))

```python
_serie_priority = {"wallbox": 0, "e-auto": 1}
...
for serie in serien:
    primary = eids[0] if eids else None
    if primary and primary in _seen_entity:
        serie_entities.pop(serie["key"], None)
        continue
```

**Wogegen schützt es?** Wallbox + E-Auto teilen sich denselben Sensor (z.B. evcc-Pool), wenn `parent_investition_id` nicht gesetzt ist.

**Bewertung:** Symptomatisch. Wurzel ist „Anwender hat parent-Verknüpfung nicht gesetzt". Lösung: ihn dazu zwingen (Setup-Wizard-Validierung). Aktuell läuft die Anwendung schweigend mit dedupliziertem Live-Pfad, während Hourly-/Daily-Pfad davon nichts wissen.

### 4.11 E-Auto-Skip wenn parent_investition_id

Drei Code-Stellen — alle separat implementiert: [`backfill.py:183`](../../eedc/backend/services/energie_profil/backfill.py#L183), [`live_tagesverlauf_service.py:131`](../../eedc/backend/services/live_tagesverlauf_service.py#L131), [`komponenten_beitraege.py:155`](../../eedc/backend/services/snapshot/komponenten_beitraege.py#L155). Konsistenz nur durch Aufmerksamkeit, kein Test.

**Bewertung:** Wäre ein Fall fürs Berechnungs-Layer / Mapping-Normalisierung. Siehe Handover hourly-categorize, der genau das vorschlägt.

## 5. Symptompatches mit/ohne dokumentiertem Folge-Plan

| Patch | Stelle | Folge-Plan dokumentiert? | Bewertung |
|---|---|---|---|
| `preserved_komponenten_kwh` für `datenquelle=="manuell"` | aggregator.py:580 | CHANGELOG v3.33.0 sagt „bleibt als defensiver Schutz" | Akzeptiert, aber Asymmetrie zu Scheduler unklar |
| Skip Boundary-Diff für `datum >= today` | aggregator.py:509 | CHANGELOG: „strukturell, nicht symptomatisch" | Diskussionswürdig — die strukturelle Stelle wäre `_diff`/`get_snapshot`, nicht der Aufrufer |
| Live-Σ-Bypass bei `kwh_source_label != "external:ha_statistics:hourly"` | aggregator.py:397 | Inline-Kommentar nennt BKW-Bug; **kein Ticket**, kein Folge-Plan | OFFEN — Drift-Risiko Standalone bleibt |
| `_PROGNOSE_FELDER_RETTEN` mit 7 Einträgen | aggregator.py:42 | Inline-Kommentar nennt Vorfall 2026-05-21 | Pattern bleibt; jeder neuer Prognose-Pfad braucht hier einen Eintrag |
| **Backfill-Variante der Rettungsliste mit nur 5 Einträgen** | backfill.py:543-544 | KEIN Kommentar, KEIN Hinweis | Drift-Risiko-Stelle, heute durch `existing_dates`-Skip neutralisiert (siehe §4.1-Korrektur). Wird scharf, falls Skip jemals gelockert wird. Konformitäts-Test sinnvoll, kein Hotfix nötig. |
| Snapshot-Spike-Cap | plausibility.py | Inline-Kommentar (Forum #529); Daten-Checker liest dieselbe Schwelle | Akzeptabel, aber konfligiert teils mit `feedback_grenze_externe_daten_diagnose` |
| Counter-Spike-Cap 200/h | snapshot/aggregator.py:532 | Inline-Kommentar (Forum Martin) | Akzeptabel |
| `_categorize_counter` mappt e-auto `verbrauch_kwh` UND `ladung_kwh` auf `verbrauch_eauto` | snapshot/keys.py:150 | EIGENES Handover-Doc: `HANDOVER-hourly-categorize-eauto-doppelmapping.md` | Folge-Plan dokumentiert, eigene Session geplant — noch offen |
| `database is locked` Per-Tag-Commit in Backfill+Scheduler | backfill.py:83 / scheduler_jobs.py:57 | CHANGELOG v3.32.4 (#291) | Akzeptiert, behoben |
| `_stunden_mit_messdaten` als API-Helper | repair.py:175 | CHANGELOG v3.32.4 (Refactor-Regress aus 17db2350) | Restauriert, akzeptiert. **Aber:** Beweist, dass die Orchestrator-Response-Form nicht typsicher mit der Repair-API-Response synchron gehalten wird. Folge-Diagnose im Handover als „API-Vertrags-Tests" erwähnt — offen. |
| Pool-Dedup im Live-Tagesverlauf | live_tagesverlauf_service.py:166 | Inline-Kommentar #227 | Verdeckt Setup-Wizard-Lücke |
| MQTT-Live-Snapshot „nur falls fehlt" + Add-on-Variante deaktiviert | fallback.py:33-65 | Inline-Kommentar #184 (Rainer 1.5.2026) — HA-Counter-Pfad in v3.25.18 entfernt | Bewusst eng eingegrenzt, dokumentiert |
| `live_snapshot_if_missing` schreibt jüngsten MQTT-Wert als Snapshot für anstehende volle Stunde | fallback.py | Erfunden für Standalone, keine Issue-Referenz | Lebt allein für MQTT-Modus |

## 6. Parallele Implementierungen

### 6.1 `aggregate_day` vs `backfill_from_statistics` — Top-Level-Klasse

Das ist die größte parallele Implementierung im Subsystem. Beide:

| Aspekt | `aggregate_day` ([aggregator.py:53](../../eedc/backend/services/energie_profil/aggregator.py#L53)) | `backfill_from_statistics` ([backfill.py:95](../../eedc/backend/services/energie_profil/backfill.py#L95)) |
|---|---|---|
| Investitionen laden | per `aktiv_jetzt`-Filter über live-service-Aufruf | per `aktiv_im_zeitraum(von, bis)` |
| Stunden-Quelle | LTS bevorzugt, dann Snapshot-Fallback | HA-Statistics direkt (eigene `get_hourly_sensor_data`-Schicht) |
| Live-Σ-Bypass | Bedingung `kwh_source_label != ha_statistics:hourly` | Σ läuft IMMER |
| Boundary-kWh | LTS oder Snapshot je `kwh_source_label` | nur Snapshot |
| Wetter-IST | gemeinsamer Helper `_get_wetter_ist` (gut) | gleicher Helper |
| Counter-Snapshots (`wp_starts_anzahl`-Hourly + `get_daily_counter_deltas_by_inv`) | beide aufgerufen | beide aufgerufen |
| Peaks aus HA-LTS-Min/Max | aufgerufen (`_get_tagespeaks_aus_ha_lts`) | **NICHT aufgerufen** — Peaks bleiben aus Live-Pfad-W-Integration |
| Strompreis-Stunden | aufgerufen (`_get_strompreis_stunden`) | **NICHT aufgerufen** — TEP-Spalten `strompreis_cent`/`boersenpreis_cent` bleiben NULL |
| `boersenpreis_avg_cent`, `negative_preis_stunden`, `einspeisung_neg_preis_kwh` auf TZ | berechnet + geschrieben | **NICHT gesetzt** — Spalten bleiben NULL |
| `wp_starts_anzahl`-Stunden-Counter | gesetzt | gesetzt (v3.27.x retroaktiv ergänzt, #259) |
| Prognose-Felder retten | `_PROGNOSE_FELDER_RETTEN` (7 Einträge) | Inline-Hardcode (5 Einträge) |
| Invariante prüfen am Ende | `pruefe_tep_tz_konsistenz` + `pruefe_tep_tz_komponenten_konsistenz` | **NICHT geprüft** |
| Per-Tag-Commit (#291) | Caller-Verantwortung (Scheduler/Backfill-Range) | im selben Modul mit eigenem commit() |
| Source-Label | `external:ha_statistics:hourly/daily` oder `auto:monatsabschluss` | `external:ha_statistics` |
| `datenquelle`-Spalte | `"scheduler"`/`"monatsabschluss"`/`"manuell"` | `"ha_statistiken"` |

→ **Backfill ist eine Code-Kopie aus der Pre-Etappe-4-Zeit, die seit v3.31.0 strukturell hinter Aggregate hinterherhinkt.** Es gibt **keinen Symmetrie-Test** zwischen den beiden. Lehre aus #290 (v3.33.0): genau diese Konstellation hat zur Wärmepumpen-Drift geführt.

**Priorisierung:** HOCH. Backfill sollte entweder (a) auf `aggregate_day` umgestellt werden (per-Tag-Schleife mit `datenquelle="monatsabschluss"`), oder (b) der gemeinsame Kern in einen geteilten Helper extrahiert werden — analog zu `komponenten_beitraege.py`. Variante (a) ist kleiner aber riskanter wegen unterschiedlicher Sensor-Read-Strategie (HA-Statistics Range-Bulk-Read in Backfill vs Tagesverlauf-Service in Aggregate).

### 6.2 Hourly-Aggregator-Symmetrie (`get_hourly_kwh_by_category` vs `get_hourly_kwh_by_category_lts`)

[`snapshot/aggregator.py:75`](../../eedc/backend/services/snapshot/aggregator.py#L75) vs [`snapshot/lts_aggregator.py:46`](../../eedc/backend/services/snapshot/lts_aggregator.py#L46).

Beide haben unterschiedliche Quelle (sensor_snapshots vs HA-LTS direkt), aber identische **Kategorisierungs-Logik** über `_categorize_counter` aus [`snapshot/keys.py:106`](../../eedc/backend/services/snapshot/keys.py#L106). Genau hier lebt der dokumentierte latente Bug: `_categorize_counter` mappt `e-auto` mit `verbrauch_kwh` UND `ladung_kwh` auf dieselbe Kategorie `"verbrauch_eauto"` — Doppelzählung bei Doppelmapping.

**Symmetrie-Test:** EXISTIERT (`test_aggregator_symmetrie.py`, 17 Parametrisierungen laut CHANGELOG), aber **NUR für den Daily-Pfad (`get_komponenten_tageskwh{,_lts}`)**, nicht für den Hourly-Pfad. Der Hourly-Pfad ist nicht parametrisiert auf Either-Or-Konstellationen getestet.

**Priorisierung:** MITTEL. Latenter Bug ohne Anwenderbericht. Strukturell ist die Lösung dieselbe wie Daily — `komponenten_beitraege.py`-analoge Mapping-Normalisierung für `_categorize_counter`. Eigene Session laut Handover.

### 6.3 `get_reaggregate_preview` enthält eigene Snapshot-Lese- und Tagesreset-Logik

[`snapshot/reaggregator.py:160-238`](../../eedc/backend/services/snapshot/reaggregator.py#L160) lädt 25 Boundaries pro Counter selber (eigener DB-SELECT mit `julianday`-Toleranz), eigene Tagesreset-Heuristik (`d < -0.01 and s1 < 0.5 and s0 > 0.5`), eigene Kategorisierung. Die Vorschau ist semantisch ein read-only-Spiegel von `get_hourly_kwh_by_category` + `get_komponenten_tageskwh`, aber sie nutzt sie nicht — sie reimplementiert.

**Symmetrie-Test:** Keiner.

**Priorisierung:** MITTEL. Der Sinn der Vorschau ist die alt/neu-Anzeige (DB-Wert vs HA-Live), nicht alt/neu in **derselben** Quelle. Die Reimplementierung hat damit eine Existenzberechtigung — aber die Tagesreset-Heuristik und Kategorisierung könnte geteilt werden, statt dreimal mit jeweils kleinen Abweichungen zu existieren.

### 6.4 Anlage-Aktiv-Filter

Drei Wege:
- `Investition.ist_aktiv_an(datum)` (Model-Methode)
- `aktiv_im_zeitraum(von, bis)` (SQL-Constraint in `utils/investition_filter`)
- `aktiv_jetzt()` (SQL-Constraint)

Backfill nutzt `aktiv_im_zeitraum`, Aggregator (via Live-Service) nutzt `aktiv_jetzt`, Live-Tagesverlauf-Service nutzt `aktiv_jetzt`. Bei historischen Tagen mit zwischenzeitlich stillgelegten Investitionen entsteht eine Asymmetrie: Backfill sieht stillgelegte Investitionen, Aggregator nicht. Wirkung: bei Reaggregat-Knopf für einen alten Tag mit stillgelegtem Sensor wäre der Wert anders als beim Vollbackfill desselben Tags.

**Priorisierung:** NIEDRIG bis MITTEL. Anwenderbericht würde sich wie #236 äußern, das dort jedoch bereits adressiert wurde.

### 6.5 Drei Snapshot-Read-Funktionen mit ähnlicher DB-Logik

`reader.get_snapshot()`, `reader._get_mqtt_snapshot_at()`, `reaggregator._db_snap_at()` haben alle ähnliche SQL-Lookup-Logik mit Toleranzfenster und `julianday`-Abstand. Reaggregator-Inline-Funktion ist 100% Kopie der Reader-Logik ohne Self-Healing-Kaskade.

## 7. Reparatur-Werkbank: pro Operation

| Operation | Plan-Funktion | Execute-Funktion | Vor-/Nachbedingungen | Idempotenz | Beobachtbare Auswirkungen |
|---|---|---|---|---|---|
| `REAGGREGATE_DAY` | `_plan_reaggregate_day` ruft `get_reaggregate_preview` (read-only, 25 Boundaries × n_counter Reads aus DB + HA-LTS) | `_execute_reaggregate_day`: optional `resnap_anlage_range(±1h)` (schreibt sensor_snapshots aus HA-LTS) → `aggregate_day(datenquelle="manuell")` (Delete+Insert TEP+TZ) | Vor: Anlage existiert. Nach: TEP für `datum` 24 Zeilen aktualisiert, TZ aktualisiert oder preserve-Logik greift | **Idempotent** — Delete+Insert pro Tag; Resnap überschreibt via Upsert | Audit-Log via `data_provenance_log` (durch `seed_*_provenance` initialisiert; Delete-and-Recreate löscht alte Provenance-Einträge nicht aus dem Log) |
| `REAGGREGATE_RANGE` | `_plan_reaggregate_range` validiert `von < bis < today`, `≤31 Tage`, zählt vorhandene TZ-Rows | `_execute_reaggregate_range`: Schleife pro Tag, optional Resnap, `aggregate_day(datenquelle="manuell")`, per-Tag-commit, sammelt Fehler-Details | wie oben + max-31-Tage-Cap | Idempotent pro Tag; bei Abbruch sind verarbeitete Tage drin (per-Tag-commit) | Cap der Detail-Liste auf 20, restliche Fehler nur im Backend-Log |
| `REAGGREGATE_TODAY` | leerer Plan (`{"anlagen_geplant": 0}`) | ruft `aggregate_today_all()` — **system-weit**, **alle Anlagen** | Vor: kein anlage_id nötig | Idempotent | Antwort enthält Per-Anlage-Status, keine Plan-Diff-Vorschau möglich |
| `VOLLBACKFILL` | `_plan_vollbackfill` zählt Tage im Range; **keine** echte Vorschau | `_execute_vollbackfill` → `resolve_and_backfill_from_statistics` → `backfill_from_statistics`; setzt am Ende `anlage.vollbackfill_durchgefuehrt = True` | Range optional; bei None automatisch ermittelt | Additiv — bestehende Tage werden übersprungen (`uebersprungen_existiert`-Counter); per-Tag-commit | Status-Map mit `geschrieben`/`uebersprungen_*` |
| `KRAFTSTOFFPREIS_BACKFILL` | zählt offene Tages-/Monats-Zeilen pro scope | ruft `backfill_kraftstoffpreise` und/oder `backfill_monatsdaten_kraftstoffpreise` | scope in `{tages, monats, beides}` | Idempotent (nur NULL-Zeilen werden befüllt) | Per-Feld-write-with-provenance |
| `DELETE_MONATSDATEN` | sucht `Monatsdaten`-Row, prüft Anlagen-Zugehörigkeit | `log_delete` + `db.delete` + commit | `monatsdaten_id` Pflicht | Nicht idempotent (zweiter Aufruf 404) | Audit-Log-Eintrag; **außerhalb der UI-Werkbank** (siehe `OPERATION_META.inWorkbench=false`) |
| `RESET_CLOUD_IMPORT` | scant `source_provenance` aller MD+IMD-Rows nach `external:cloud_import:*`-Markern, liefert echten Field-Diff (capped 200) | scannt neu (Stale-Diff-Schutz), schreibt per Feld mit `force_override=True` + Source `"repair"` | optional `providers`-Filter | Idempotent (zweiter Aufruf zeigt 0 betroffene Felder) | Per-Feld-Provenance auf `"repair"` gestempelt; **durchbricht** die Hierarchie |
| `SOLCAST_REWRITE` | wirft `NotImplementedError` | dito | — | — | Stub für Päckchen 6 |

### Werkbank-Eigenschaften

- **Plan/Execute-Trennung** über in-memory UUID-Map mit 1h-TTL und `_purge_expired_unlocked`. Single-Worker-Annahme — kein Redis, kein DB-Cache. Wenn jemals Multi-Worker, brechen alle bestehenden Plans als 404.
- **Audit-Marker:** `_audit_id_marker` + `_audit_ids_since` über `DataProvenanceLog.id`. Korrekt, aber gibt einen subtilen Bug-Vector: wenn ein paralleler Schreiber (z.B. der Scheduler) während des Execute schreibt, landen seine Audit-IDs ebenfalls im `audit_log_ids`-Result. Bei single-worker und seriellem Aggregate-Trigger praktisch nicht relevant, aber dokumentiert nirgendwo.
- **Werkbank verlässt sich auf `aggregate_day`-Verhalten** an mehreren Stellen, ohne dass die Werkbank dieses Verhalten dokumentiert:
  - Per-Tag-Delete-Recreate-Semantik (Plan kann nicht versprechen, was geschieht ohne Boundary-Diff-Vorschau)
  - Preserve-Logik bei `datenquelle="manuell"` (Werkbank-User sieht diesen Skip nirgends)
  - Skip Boundary für `datum >= today` (REAGGREGATE_RANGE verbietet `today` ohnehin, REAGGREGATE_DAY nicht — Anwender kann `datum=today` schicken und der Knopf läuft, aber liefert ggf. unverändertes komponenten_kwh)
  - LTS-vs-Snapshot-Fallback (Werkbank weiß nicht, welcher Pfad gerade aktiv ist)

### Warnungs-Liste in `_plan_reaggregate_range`

Sechs sehr lange Warnungen, fast alle technisch („Per-Feld-Provenance älterer Verfahrensläufe wird überschrieben"). Für den User schwer einzuschätzen. Der Pflicht-Checkbox-Schritt `range_confirmed` verlangt dann Pauschal-Quittierung. Das kollidiert mit `feedback_daten_checker_kein_akzeptiert`-Memory-Regel im Geist: hier ist es nicht „akzeptiert" sondern „bestätigt", aber die UX-Logik ähnelt sich.

### `vollbackfill_durchgefuehrt`-Flag

Wird beim ersten Vollbackfill auf True gesetzt — danach läuft im Monatsabschluss-Hintergrundjob (`monatsabschluss_aggregator.run_post_monatsabschluss_aggregation:92`) der Auto-Vollbackfill nicht mehr. Das Flag wird auch bei Fehler gesetzt, damit Endlos-Retry vermieden wird. Reset auf False passiert nur beim DELETE `/rohdaten`-Endpoint. Effekt: wenn der erste Vollbackfill mit leerem HA-Statistics startet (z.B. neue HA-Installation), wird der Flag gesetzt, und ein späterer Run mit gefüllter HA-Statistics findet nie statt. Workaround: User muss Werkbank manuell triggern.

## 8. Beobachtete Risiko-Stellen

### 8.1 Drift-Risiko-Stelle: 5-statt-7 Prognose-Felder im Backfill

[`backfill.py:543`](../../eedc/backend/services/energie_profil/backfill.py#L543):

```python
for field in ("pv_prognose_kwh", "sfml_prognose_kwh",
               "solcast_prognose_kwh", "solcast_p10_kwh", "solcast_p90_kwh"):
```

Fehlt: `pv_prognose_stundenprofil`, `solcast_prognose_stundenprofil` — gegenüber der vollständigen Liste in `_PROGNOSE_FELDER_RETTEN` (Aggregator, 7 Einträge).

**Klassifikation:** Drift-Risiko-Stelle, nicht akuter Bug. Begründung siehe §4.1-Korrektur: der `existing_dates`-Skip oben (Z. 311-315) neutralisiert den Code-Pfad heute strukturell — Backfill verarbeitet nur Tage ohne existierende TZ, also läuft die preserve-Schleife (Z. 542) ohnehin leer. Race-Fenster mit `_speichere_prognose` zwischen Range-Lookup und Pro-Tag-Verarbeitung existiert, ist aber praktisch eng (Vollbackfill = historische Tage, Wetter = heute/morgen).

**Implikation:** kein Hotfix-Release. Schaden wird scharf, falls der Skip jemals gelockert wird (z.B. Overwrite-Modus reaktiviert). Konformitäts-Test als günstige Vorab-Sicherung ist sinnvoll und im Normalrhythmus releasebar.

### 8.2 Backfill-Boundary nutzt Snapshot-Variante, nicht LTS

[`backfill.py:606-609`](../../eedc/backend/services/energie_profil/backfill.py#L606):

```python
from backend.services.snapshot.aggregator import get_komponenten_tageskwh
boundary_kwh = await get_komponenten_tageskwh(db, anlage, investitionen, current)
```

Nach Etappe 4 ist LTS-Variante die SoT. Wenn die Snapshot-DB für den Backfill-Tag leer ist (typisch — Backfill läuft auf alten Tagen, deren Snapshots noch nie geschrieben wurden), liefert die Snapshot-Variante leere/gestaffelte Werte, während Live-Σ-Riemann aus dem HA-Statistics-Hourly-Pull die `komponenten_summen` füllt. Resultat: `komponenten_kwh` ist im Backfill aus Σ-Hourly-Riemann (was teilweise mit `_sonderschluessel` gefiltert wird, teilweise nicht). Asymmetrisch zum Aggregator und ohne Symmetrie-Test.

### 8.3 `_sonderschluessel` im Backfill enthält `sonstige_keys`, im Aggregator NICHT

Bugfix-Kommentar in [backfill.py:288](../../eedc/backend/services/energie_profil/backfill.py#L286-L288):

```python
# Bugfix: sonstige_keys fehlten hier (führte dazu, dass "sonstiges"-Erzeuger
# doppelt in pv_kw einflossen). Nun analog zu aggregate_day.
sonstige_keys = {s["key"] for s in serien if s["kategorie"] == "sonstige"}
```

Vergleich mit Aggregator [aggregator.py:167-170](../../eedc/backend/services/energie_profil/aggregator.py#L167):

```python
sonstige_keys = {s["key"] for s in serien if s["kategorie"] == "sonstige"}
_sonderschluessel = batterie_keys | v2h_keys | netz_keys | pv_keys | wp_keys | wallbox_keys | sonstige_keys | {"strompreis", "haushalt"}
```

Aggregator hat zusätzlich `{"strompreis", "haushalt"}` im `_sonderschluessel`. Backfill nicht. → wenn der Live-Pfad einen `haushalt`-Schlüssel an den Backfill-Pfad reicht (was er heute nicht tut, weil Backfill nicht über Live-Service läuft, sondern direkt HA-Statistics-Hourly liest und einen eigenen `werte`-Dict aufbaut), würde der Backfill `haushalt`-kWh in `pv_kw_h` zählen. **Heute latent, da `werte`-Dict im Backfill nur Serie-Keys enthält. Aber das Asymmetrie-Risiko ist nicht im Code dokumentiert.**

### 8.4 Aktiv-Filter-Asymmetrie

Siehe §6.4.

### 8.5 `live_snapshot_if_missing` läuft nur im MQTT-Modus

[`fallback.py:33`](../../eedc/backend/services/snapshot/fallback.py#L33) — der Add-on-Pfad wurde wegen #184 (HA `state` vs `sum`-Mismatch) deaktiviert. Es gibt keinen Hinweis, dass jemand prüft, ob er jemals wieder aktiviert werden könnte; der Inline-Kommentar liest sich wie eine endgültige Designentscheidung. Aber: die Funktion existiert noch, wird also weiter gewartet — das ist toter Code, wenn er nicht für Standalone gebraucht würde.

### 8.6 `_categorize_counter` für E-Auto-Doppelmapping

Siehe §6.2 + Handover-Doc. **Bekannt, dokumentiert, eigene Session.**

### 8.7 In-Memory-Plan-Cache des Orchestrators

Single-Worker-Annahme — bei Multi-Worker bricht alles. Im CHANGELOG für v3.34 wäre das ein Tier-1-Risiko, wenn parallel Uvicorn-Worker auf Add-on möglich werden sollen. Heute Add-on = single Worker, OK.

### 8.8 Provenance-Skip-Liste in `_provenance_helpers`

`_TZ_SKIP_COLUMNS` listet `pv_prognose_stundenprofil`, `solcast_prognose_stundenprofil` als „interne Caches, keine Aggregat-Werte" und überspringt sie damit. **Aber:** `_PROGNOSE_FELDER_RETTEN` listet beide, weil sie sehr wohl gerettet werden müssen. Inkonsistente Behandlung — interner Cache, der aber per Hand gerettet wird, aber dessen Provenance nicht getrackt wird. Bei einer späteren Rückverfolgungs-Frage „wer hat das Stundenprofil zuletzt geschrieben" liefert das Audit-Log nichts.

### 8.9 Kraftstoffpreis-Backfill schreibt auf `Monatsdaten` (Out-of-Scope-Effekt)

`backfill_monatsdaten_kraftstoffpreise` schreibt auf `Monatsdaten` — eine Tabelle, die im Audit-Scope nicht direkt liegt, aber von der Werkbank getriggert wird. Konsistenz mit dem Monatsabschluss-Wizard ist Sache des `write_with_provenance`-Resolvers (Source-Hierarchie). OK, aber als „Werkbank-Operation schreibt auf eine Tabelle außerhalb ihres Scope" erwähnenswert.

### 8.10 Reaggregate-Today schreibt für ALLE Anlagen ohne anlage_id

`_execute_reaggregate_today` ruft `aggregate_today_all` ohne Filter. Wenn ein User in der Werkbank für Anlage 1 den Button drückt, läuft die Aggregation auch für Anlage 2..N. Plan-Anzeige sagt das nicht, der Endpoint ist auch nicht in OPERATION_META.inWorkbench enthalten — der Pfad lebt vermutlich nur über den alten `/api/energie-profil/reaggregate-heute`-Endpoint. **Aber:** Der ist im Frontend unter dem Werkbank-System-weiten Knopf aufrufbar, wenn jemand ihn baut. Solange der Knopf nur in der Werkbank-UI versteckt ist, OK.

### 8.11 Vollbackfill-Flag wird auch bei Fehler gesetzt

Siehe §7. Strukturell der Tradeoff „Endlos-Retry vs einmaliger Verlust". Akzeptiert, aber für die nächste Major-Welle erwähnenswert: ein expliziter Status (statt boolean Flag) würde dem User erlauben, manuell einen erneuten Lauf zu triggern, ohne `vollbackfill_durchgefuehrt=False` ad-hoc zurücksetzen zu müssen.

### 8.12 `datenquelle`-String als Steuerungs-Trigger

`aggregate_day(datenquelle="manuell")` triggert preserve-Logik. Wenn jemand mal aus Versehen `datenquelle="repair"` oder einen Tippfehler übergibt, fällt die Schutzlogik still aus. Magic-String ohne Enum-Schutz.

## 9. Outside-Scope-Funde

> Nur kurz notiert, nicht verfolgt — folgte ich nur, soweit ich beim Lesen darauf stieß.

- **`services/energie_profil/rollup.py`** — **tangentialer Konsument mit Pflicht-Notiz für den späteren Refactor:** liest 5 Skalar-Felder aus TZ (`ueberschuss_kwh`, `defizit_kwh`, `batterie_vollzyklen`, `performance_ratio`, `peak_netzbezug_kw`) und schreibt sie via `write_with_provenance(auto:monatsabschluss)` auf `Monatsdaten`. Bewusst Out-of-Scope (Ziel-Tabelle gehört zum Monatsabschluss-Subsystem, eigener Lifecycle), aber **wenn die TZ-Schreibseite umgebaut wird**, muss diese 5-Felder-Liste mitgehalten werden — sonst entsteht ein neuer Drift auf der Achse Monatsdaten vs Tageswerte. Leichter Konformitäts-Test wäre denkbar (alle 5 Feldnamen müssen auf `TagesZusammenfassung` als nullable-Float-Spalte existieren), aber nicht Refactor-Voraussetzung.
- **`live_history_service.py:get_history_normalized`** — Bietet ein normalisiertes HA-History-API, wird vom Tagesverlauf-Service genutzt. Im Audit nicht weiter untersucht; vermutlich solide.
- **`prefetch_service.py`** — Macht im Hintergrund Cache-Warming für Verbrauchsprognose. Berührt TEP/TZ nicht direkt.
- **`mqtt_live_history_service.py`** + **`mqtt_inbound_service.py`** — Standalone-Lifeline. Nicht im Detail gelesen.
- **`ha_statistics_service.py`** — Read-only Wrapper über die HA-recorder-DB. Pflegt Versions-Differenzen ab. Wird vom LTS-Aggregator + Backfill konsumiert.
- **`live_wetter._speichere_prognose`** — Direkter zweiter Schreiber auf TZ. Ist Out-of-Scope (Wetter/Prognosen-Subsystem) — aber sein Schreib-Verhalten zwingt dem Aggregator die `_PROGNOSE_FELDER_RETTEN`-Konstruktion auf. Strukturelle Co-Abhängigkeit, sollte beim Refactor mitgedacht werden.
- **`daten_checker.py:1983` + `:2136`** — Liest direkt `tz.komponenten_kwh` UND ruft `get_komponenten_tageskwh_lts` für Live-Vergleich. Liegt Out-of-Scope, ist aber der primäre Konsument der Drift-Diagnose. Erweiterung um `pruefe_tep_tz_komponenten_konsistenz`-Bericht laut Handover ist offen.
- **`Anlage.vollbackfill_durchgefuehrt`-Flag** — Lebt auf der `Anlage`-Model, nicht im Energieprofil-Scope. Verhalten siehe §8.11.
- **`prognosen.py:640-644`** — Bug aus dem ETAPPE-4-Konzept: Filter schließt Batterie-Netto-Ladung nicht aus → IST-Erzeugung fälschlich. CHANGELOG Etappe 4 sagte er sei in v3.31.0 gefixt; im aktuellen Code wird `summe_pv_bkw_kwh` aus dem Berechnungs-Layer benutzt (Z. 643-644). Vermutlich behoben. Nicht weiter geprüft.
- **`source_priority.py`** + **`provenance.py`** — Komplette Per-Feld-Provenance-Layer; Out-of-Scope, aber Werkbank-RESET_CLOUD_IMPORT verlässt sich darauf.

## 10. Vorschlag Soll-Architektur (Strukturskizze, keine Spec)

Auf Basis der Befunde — als Diskussions-Startpunkt, nicht als Plan.

### 10.1 Ein Schreibpfad

```text
TEP+TZ-Schreiber ::= aggregate_day(anlage, datum, *, source: Source, hourly_provider: HourlyProvider)

    HourlyProvider ::= LtsProvider() | SnapshotProvider() | HaStatisticsRangeProvider(range)
    Source ::= Scheduler | MonatsabschlussBackfill | ManualRepair | VollbackfillFromLts
```

- `aggregate_day` ist die einzige Funktion, die TEP-Stunden und TZ-Tag schreibt.
- Der Hourly-Provider ist injizierbar — drei konkrete Implementierungen: LTS (per Tag), Snapshot (per Tag), Range-Bulk (heute in `backfill_from_statistics`).
- `Source` ist ein Enum, das (a) auf `TagesZusammenfassung.datenquelle` projiziert wird (existing Anzeige), (b) auf den Provenance-Source projiziert wird, (c) das Verhalten der preserve-Logik typsicher steuert (kein Magic-String mehr).
- `backfill_from_statistics` wird zur dünnen Schleife `for tag in range: aggregate_day(anlage, tag, source=VollbackfillFromLts, hourly_provider=HaStatisticsRangeProvider(prefetched_data))`. Die ganze redundante Stunden-Schleife + Komponenten-Aggregation entfällt.

### 10.2 Boundary-Pfad nur über `komponenten_beitraege`

Der in v3.33.0 eingeführte Helper bleibt SoT. Der Aufrufer wählt nur noch zwischen zwei Delta-Quellen (DB-Snapshots vs HA-LTS-Hourly), aber die Per-Typ-Beitragsliste lebt nur einmal. Symmetrie ist strukturell garantiert. **Gilt heute schon für Boundary** — der Aggregator-Code in `aggregator.py:508-535` ist die einzige Stelle, die noch Wahl trifft, und sie sollte aufgehoben sein (gleiche Quelle wie hourly).

### 10.3 Hourly-Pfad zieht den Helper nach

`_categorize_counter` und die Hourly-Aggregatoren werden auf Mapping-Pre-Normalisierung umgestellt: das `sensor_mapping`-Dict wird einmalig durch `komponenten_beitraege` gefiltert (Either-Or aufgelöst, E-Auto-Parent-Skip angewandt, ungenutzte Felder rausgefiltert), die Aggregatoren konsumieren das normalisierte Mapping. Symmetrie-Test wie für Daily-Pfad. → adressiert den dokumentierten Handover-Bug strukturell statt punktuell.

### 10.4 Prognose-Felder aus TZ herauslösen

Strukturelle Alternative zur Rettungsliste: eine eigene `tages_prognose`-Tabelle mit `(anlage_id, datum)` als PK, eigenem Lebenszyklus. Aggregator schreibt sie nicht. Live-Wetter-Service besitzt sie. Read-Sites (Korrekturprofil, Genauigkeits-Tracking, Cockpit-Prognose) joinen.

- **Vorteil:** Aggregator wird zu einem reinen TZ-Schreiber für reale Messdaten. Die Delete-and-Recreate-Semantik bricht keinen Prognose-Pfad mehr. Keine Sync-Liste, kein Backfill-Korrekturprofil-Bug.
- **Kosten:** DB-Migration; alle Konsumenten auf Join umstellen; Provenance-Modell verdoppelt.

### 10.5 Reparatur-Werkbank: Plan-Differenz, nicht Operation-Liste

Heute baut die Werkbank pro Operation eine eigene Preview-Form. Soll: Werkbank baut auf einer **Diff-API** auf (was würde geschrieben werden, wenn die Operation jetzt liefe — zeile pro betroffenem TEP-Feld, zeile pro TZ-Feld, zeile pro IMD-Feld), die für alle Reaggregat-Operationen identisch ist. Die einzigen operations-spezifischen Plan-Daten sind dann „Welcher Range, welche Quelle, welche Filter". Vorteil: ein UI für alle Reaggregat-Pfade, gemeinsame Vorschau-Komponente. Kosten: Diff-Berechnung pro Operation muss in der Plan-Phase laufen — bei RANGE 31 Tage kostet das Zeit.

### 10.6 Scheduler-Single-Path

`aggregate_today_all` + `aggregate_yesterday_all` werden zu reinen `for anlage in anlagen: aggregate_day(anlage, today_or_yesterday, source=Scheduler)`-Wrappern. Heute schon der Fall, aber sie haben jeweils eigene Retention-Cleanup-Logik. Cleanup könnte in eigene Maintenance-Funktion.

### 10.7 Was bewusst NICHT angefasst wird

- **Snapshot-Subsystem (`services/snapshot/*`)** — funktioniert nach Etappe 3c sauber, ist die Quelle der Self-Healing-Kaskade. Die Symptompatches dort sind klein und gut isoliert. Anfassen nur, wenn `_categorize_counter`-Helper-Migration es erzwingt.
- **`live_*`-Services** — sie sind Konsumenten, nicht Schreiber. Sauberkeit der Pool-Dedup u.ä. lebt dort, kann separat angegangen werden.
- **`source_priority.py` + `provenance.py`** — eigener Layer, sauber, kein Refactor-Bedarf.

---

## Zurück an dich, Gernot

Drei Stellen, wo der Audit nach deinem Sichten-Feedback nochmal nachfasst:

1. **Backfill-vs-Aggregate-Asymmetrie** (§6.1, §8.1-8.3) — drei latente Bugs aus reinem Code-Lesen. Wenn du sie als „bekannt aber nicht aktuell anwender-relevant" einschätzt, bleibt der Refactor-Druck moderat. Sonst werden sie zu Tier-1-Fixes für v3.34.
2. **Scope-Schnitt** (§0): Soll der `rollup.py` (Monatsdaten-Schreiber) wirklich draußen bleiben, oder ist er strukturell Teil des Energieprofil-Subsystems? Ich habe ihn rausgelassen, weil sein Ziel-Table `Monatsdaten` heißt.
3. **Soll-Architektur §10.4** (Prognose-Felder aus TZ herauslösen): das wäre der größte Schnitt — Datenmodell-Migration. Wenn dir das zu groß ist, bleibt die Rettungsliste, und wir investieren in einen automatisierten Sync-Test zwischen `_PROGNOSE_FELDER_RETTEN` und `live_wetter._speichere_prognose`-Feldern (kleiner Konformitäts-Test, analog ADR-001-Test).

---

## 11. Entschieden in der Sichtungs-Session (2026-05-24)

> Festgehalten, damit die nachfolgende Fix-Session diese drei Punkte nicht erneut diskutiert. Alles Weitere ist offen.

1. **Kein v3.33.1-Hotfix für die Backfill-Rettungsliste.** Re-Analyse hat ergeben: der Code-Pfad ist durch den `existing_dates`-Skip heute strukturell neutralisiert (siehe §4.1-Korrektur, §5, §8.1). Konformitäts-Test als günstige Vorab-Sicherung fließt in den Refactor mit ein, kein eigenes Patch-Release.
2. **`services/energie_profil/rollup.py` bleibt Out-of-Scope** (Ziel-Tabelle `Monatsdaten` ≠ Energieprofil-Subsystem) — mit expliziter **Pflicht-Notiz für den späteren Refactor** in §9: bei Umbau der TZ-Schreibseite muss die 5-Felder-Liste in `rollup.py` konsistent gehalten werden.
3. **Prognose-Felder bleiben in TZ.** Tabellen-Auslagerung (§10.4) wird **nicht** im selben Bündel wie der Energieprofil-Refactor gemacht — zu kurz hintereinander auf v3.33.0-Migration. Konformitäts-Test gegen die Drift-Klasse (Liste hier, Liste dort) ist das Mittel der Wahl. Falls jemals eine eigene Prognose-Tabelle aus anderen Gründen sinnvoll wird (neue Modelle, Retention, Performance), eigene Etappe.

Pattern-Diagnose siehe §0.5 — die Entscheidung „strukturelle Vereinfachung als eigene v3.34-Etappe" gegenüber „weitere lokale Konformitäts-Tests in der heutigen Doppel-Pipeline" gehört in die Fix-Session, nicht in den Audit-Bericht.
