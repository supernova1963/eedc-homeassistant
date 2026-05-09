# Konzept: Daten-Pipeline & Reparatur-Architektur (Etappe 3d)

> **Status:** Päckchen 1 in Arbeit ab 2026-05-09. Re-Inventur (Sektion 1) abgeschlossen, Schema-Fundament + `source_priority.py` + `write_with_provenance()` Lieferung dieses Päckchens.
> **Voraussetzung Implementierung:** Etappe 3c abgeschlossen ✅ v3.26.8 (Detail-Konzept: [`KONZEPT-ENERGIEPROFIL-3C.md`](KONZEPT-ENERGIEPROFIL-3C.md) — Slot-Konvention an [#144](https://github.com/supernova1963/eedc-homeassistant/issues/144) angleichen + `quelle`-Marker auf `sensor_snapshots` als Schema-Vorlage).
> **Ziel:** Provenance, Konflikt-Resolver, Reparatur-Orchestrator, Idempotenz und Aufräumen der Monster-Module der gesamten Aggregat-Daten-Schicht.

Vier Architektur-Entscheidungen tragen dieses Konzept:

- **Hierarchie der Schreib-Quellen ist hartcoded** in `source_priority.py` — kein Quellen-Picker pro Anlage. (Quellenwahl im UI-Sinne ist Sache von [`KONZEPT-PROGNOSEQUELLEN-WAHL.md`](KONZEPT-PROGNOSEQUELLEN-WAHL.md), anderer Scope.)
- **Provenance lebt hybrid:** `source_provenance` JSON-Spalte pro Aggregat-Tabelle für Live-Resolution + Append-Only `data_provenance_log` für historische Diagnose.
- **Konflikt-Resolver hybrid:** synchroner Hierarchie-Check beim Schreiben (verhindert stilles Überschreiben) + asynchrone Daten-Checker-Sichtbarkeit für Doppel-Schreiber.
- **Reparatur über Orchestrator** mit Plan + Execute (Vorschau-Pflicht analog Vollbackfill-Pattern aus #190).

Implementierung sequenziell **nach** Etappe 3c, kein Quick-Win-Vorziehen. Refactoring der Monster-Module ist Querschnitt pro Päckchen, kein eigener Vor-Sprint.

## 1. Ist-Inventur

> Vollständige Re-Inventur durchgeführt 2026-05-09 zu Beginn von Päckchen 1. Tabellen unten zeigen alle gefundenen Schreib-/Lösch-/Reparatur-Pfade; spätere Päckchen (insb. P2 + P3) müssen sich an dieser Liste messen lassen, nicht an früheren Best-Effort-Skizzen.

### 1.1 Eingabe-Pfade (Schreiber auf Aggregat-Tabellen)

#### `monatsdaten` — 8 Schreiber

| # | Pfad | Code-Stelle | Schreib-Modus heute |
|---|---|---|---|
| 1 | Manual-Form | [`routes/monatsdaten.py:435`](../eedc/backend/api/routes/monatsdaten.py) | INSERT (Update über ID-Pfad in derselben Datei) |
| 2 | Auto-Aggregation Monatsabschluss | [`routes/monatsabschluss.py:883`](../eedc/backend/api/routes/monatsabschluss.py) | INSERT, kein Konflikt-Check |
| 3 | CSV-Import (eigene Datei) | [`routes/custom_import.py:1000`](../eedc/backend/api/routes/custom_import.py) | INSERT (Apply-Schritt) |
| 4 | HA-Statistics-Import | [`routes/ha_statistics.py:928`](../eedc/backend/api/routes/ha_statistics.py) | INSERT (Backfill) |
| 5 | Demo-Data-Loader | [`routes/import_export/demo_data.py:393`](../eedc/backend/api/routes/import_export/demo_data.py) | INSERT (Standalone-Erstinstallation) |
| 6 | CSV-Operations (Backup-CSV) | [`routes/import_export/csv_operations.py:455`](../eedc/backend/api/routes/import_export/csv_operations.py) | INSERT (separater Pfad vom Custom-Import) |
| 7 | JSON-Backup-Restore | [`routes/import_export/json_operations.py:695`](../eedc/backend/api/routes/import_export/json_operations.py) | INSERT (Anlagen-Backup einspielen) |
| 8 | Cloud-Import Apply | [`routes/data_import.py:316`](../eedc/backend/api/routes/data_import.py) | INSERT-or-UPDATE über `_upsert_investition_monatsdaten`-Pattern |

#### `investition_monatsdaten` — 6 Constructor-Stellen + 11 Cloud-Importer (indirekt)

| # | Pfad | Code-Stelle | Schreib-Modus heute |
|---|---|---|---|
| 1 | Manual-Form | [`routes/monatsdaten.py:497`](../eedc/backend/api/routes/monatsdaten.py) | INSERT |
| 2 | Auto-Aggregation | [`routes/monatsabschluss.py:921`](../eedc/backend/api/routes/monatsabschluss.py) | INSERT |
| 3 | HA-Statistics-Import | [`routes/ha_statistics.py:1016`](../eedc/backend/api/routes/ha_statistics.py) | INSERT (Backfill) |
| 4 | `_upsert_investition_monatsdaten` (zentraler Helper) | [`routes/import_export/helpers.py:97`](../eedc/backend/api/routes/import_export/helpers.py) | UPDATE-or-INSERT mit Skip-/Merge-Logik. **Konsumenten:** [`routes/custom_import.py`](../eedc/backend/api/routes/custom_import.py) (CSV) + [`routes/data_import.py`](../eedc/backend/api/routes/data_import.py) (Cloud-Apply) |
| 5 | Demo-Data | [`routes/import_export/demo_data.py:434/457/476/491/510/527/537`](../eedc/backend/api/routes/import_export/demo_data.py) | 7 INSERT-Stellen (verschiedene Investitionstypen) |
| 6 | JSON-Backup-Restore | [`routes/import_export/json_operations.py:649`](../eedc/backend/api/routes/import_export/json_operations.py) | INSERT |

**11 Cloud-Importer** in [`services/cloud_import/`](../eedc/backend/services/cloud_import/): `anker_solix`, `deye_solarman`, `ecoflow_powerocean`, `ecoflow_powerstream`, `fronius_solarweb`, `growatt`, `hoymiles_smiles`, `huawei_fusionsolar`, `solaredge`, `sungrow_isolarcloud`, `viessmann_gridbox`. **Bestätigt: keiner schreibt direkt** (`grep -n "InvestitionMonatsdaten(" services/cloud_import/*.py` = leer). Alle liefern Daten an [`routes/data_import.py`](../eedc/backend/api/routes/data_import.py) Apply-Pfad → `_upsert_investition_monatsdaten`.

**Hierarchie-Verletzung (Risiko #2):** Der `_upsert_*`-Helper hat ein `ueberschreiben`-Flag. Bei `true` werden Felder ohne Source-Klassen-Check ersetzt — auch wenn die bestehende Source `manual:form` war. Das ist der Anker-Punkt von Päckchen 2.

#### `tages_zusammenfassung` — 4 Schreiber

| # | Pfad | Code-Stelle | Schreib-Modus heute |
|---|---|---|---|
| 1 | Aggregator (Etappe-3c-Slice, aktiv) | [`services/energie_profil/aggregator.py:437`](../eedc/backend/services/energie_profil/aggregator.py) | INSERT/UPDATE pro Tag |
| 2 | Energie-Profil-Service (Pre-3c-Pfad, möglicherweise teilweise tot) | [`services/energie_profil_service.py:756`](../eedc/backend/services/energie_profil_service.py) | INSERT/UPDATE — überlappt mit (1), Sauberkeits-Befund für P3 |
| 3 | live_wetter Tagesprognose-Persistenz | [`routes/live_wetter.py:820/834`](../eedc/backend/api/routes/live_wetter.py) | UPDATE/INSERT für **alle drei** Prognose-Felder: `pv_prognose_kwh` (Z. 816, OpenMeteo+EEDC), `sfml_prognose_kwh` (Z. 818, Tom-HA-Sensor), `solcast_prognose_kwh` (Z. 820, Solcast-API oder HA-Sensor) |
| 4 | Kraftstoffpreis-Service | [`services/kraftstoff_preis_service.py:339`](../eedc/backend/services/kraftstoff_preis_service.py) | UPDATE pro TZ-Zeile (`tz.kraftstoffpreis_euro = preis`) |

**Korrektur Konzept v1 → v2:** [`services/solcast_service.py`](../eedc/backend/services/solcast_service.py) ist Read-only Provider (API + HA-Sensor), schreibt **nicht** selbst in `tages_zusammenfassung`. Einziger Persistenz-Pfad für Solcast-Werte ist [`routes/live_wetter.py:820`](../eedc/backend/api/routes/live_wetter.py). Konzept v1 hatte hier eine Doppel-Schreiber-Lage angenommen, die de facto nicht existiert. Risiko #3 wird in Sektion 2 entsprechend reframed.

#### `tages_energie_profil` — 3 Schreib-Pfade

| # | Pfad | Code-Stelle | Schreib-Modus heute |
|---|---|---|---|
| 1 | Aggregator (Etappe-3c-Slice, aktiv) | [`services/energie_profil/aggregator.py:340`](../eedc/backend/services/energie_profil/aggregator.py) | INSERT pro Stunde |
| 2 | Energie-Profil-Service (Pre-3c-Pfad) | [`services/energie_profil_service.py:642`](../eedc/backend/services/energie_profil_service.py) | INSERT — überlappt mit (1) |
| 3 | 3c-P2-Daten-Migration | [`services/snapshot/migrate.py:97`](../eedc/backend/services/snapshot/migrate.py) | UPDATE (idempotent über `migrations`-Tabelle, einmalig pro Installation) |

**Befund Doppel-Implementierung:** `services/energie_profil_service.py` und der neue 3c-Slice in `services/energie_profil/aggregator.py` schreiben beide auf `tages_energie_profil` und `tages_zusammenfassung`. Ob `_service.py` noch echte Aufrufer hat oder ob seine Schreib-Pfade nach 3c reine Tot-Code sind: Folge-Prüfung in Päckchen 3 (Refactoring `energie_profil_service.py`).

#### `sensor_snapshots` (für Vollständigkeit, nicht 3d-Ziel)

`sensor_snapshots` hat seit Etappe 3c einen `quelle`-VARCHAR-Marker (Werte: `ha_statistics` / `mqtt_inbound` / `mqtt_live` / `live_fallback` / `unknown`). Diese Tabelle ist **nicht** Ziel von 3d-`source_provenance` — pro Zeile genau ein Datenfeld, JSON-Spalte wäre Overhead. 3d-Vokabular auf den 4 Aggregat-Tabellen (`external:ha_statistics`, `fallback:sensor_snapshot`, ...) ist disjunkt vom 3c-`quelle`-Vokabular auf `sensor_snapshots` — keine Migration auf `sensor_snapshots`, keine 1:1-Übersetzung.

→ **Größenordnung: 21 distinct Schreib-Pfade** auf 4 Aggregat-Tabellen (`monatsdaten` 8 + `investition_monatsdaten` 6 + `tages_zusammenfassung` 4 + `tages_energie_profil` 3). Hinzu kommen 11 Cloud-Importer (indirekt über `_upsert_*`-Helper) und der Sensor-Snapshot-Pfad mit eigener Marker-Lösung.

### 1.2 Reparatur- + Lösch-Pfade

#### Reparatur-Endpoints in `routes/energie_profil.py` (9, nicht 7)

| Endpoint | Operation | Code-Stelle |
|---|---|---|
| `POST /reaggregate-heute` | Heute aus Snapshots neu zusammenrechnen | [Z. 1008](../eedc/backend/api/routes/energie_profil.py) |
| `GET /{id}/reaggregate-tag/preview` | Vorschau Tages-Reaggregation | [Z. 1047](../eedc/backend/api/routes/energie_profil.py) |
| `POST /{id}/reaggregate-tag` | Tag-Reagg additiv (#190) | [Z. 1121](../eedc/backend/api/routes/energie_profil.py) |
| `POST /{id}/vollbackfill` | Komplett-Historie aus HA-Statistics, additiv | [Z. 1230](../eedc/backend/api/routes/energie_profil.py) |
| `POST /{id}/kraftstoffpreis-backfill/tages` | EU Oil Bulletin → TZ | [Z. 1340](../eedc/backend/api/routes/energie_profil.py) |
| `POST /{id}/kraftstoffpreis-backfill/monats` | EU Oil Bulletin → MD | [Z. 1365](../eedc/backend/api/routes/energie_profil.py) |
| `POST /{id}/kraftstoffpreis-backfill` | Wrapper (Tages+Monats) | [Z. 1390](../eedc/backend/api/routes/energie_profil.py) |
| `DELETE /{id}/rohdaten` | TEP+TZ einer Anlage löschen | [Z. 883](../eedc/backend/api/routes/energie_profil.py) |
| `DELETE /rohdaten` | Global-Lösch (alle Anlagen) | [Z. 1417](../eedc/backend/api/routes/energie_profil.py) |

#### Weitere Reparatur-/Lösch-Pfade

| Endpoint | Operation | Code-Stelle |
|---|---|---|
| `DELETE /api/monatsdaten/{id}` | Single-Datensatz löschen | [`routes/monatsdaten.py:558`](../eedc/backend/api/routes/monatsdaten.py) |
| `DELETE /api/cloud-import/credentials/{anlage_id}` | **NUR Credentials**, keine Daten | [`routes/cloud_import.py:221`](../eedc/backend/api/routes/cloud_import.py) |
| Anlagen-Backup-Restore (JSON) | Komplettes Anlagen-Backup einspielen | [`routes/import_export/json_operations.py`](../eedc/backend/api/routes/import_export/json_operations.py) |

**Korrektur Konzept v1 → v2:** Konzept v1 nannte „DELETE /api/cloud-import/anlage/{id} (sinngemäß)". Dieser Endpoint existiert nicht. Cloud-Daten-Reset geschieht heute nur indirekt über `DELETE /{id}/rohdaten` oder per InvestitionMonatsdaten-Cascade beim Investitions-Delete. **Folge:** der dedizierte `RESET_CLOUD_IMPORT`-Operationstyp aus Sektion 5.1 ist eine **neue** Operation, kein Wrapper über Bestehendem.

→ **Verteilte Reparatur-Logik:** 9 Endpoints im Energieprofil-Bereich + 2 weitere Lösch-/Restore-Pfade, **keine zentrale Plan-/Vorschau-Schicht**.

### 1.3 Aggregat-Tabellen-Übersicht (Schreib-Fan-In)

| Tabelle | Heutige Schreiber | Konflikt-Potenzial |
|---|---|---|
| `monatsdaten` | Manual-Form, Auto-Aggregation, CSV-Import | **Hoch** (Risiko #1: Manual ↔ Auto, Risiko #2: Manual ↔ Cloud/CSV) |
| `investition_monatsdaten` | Manual-Form, CSV-Import, 10× Cloud-Importer | **Hoch** (Risiko #2: Manual ↔ Cloud/CSV-Override). Doppel-Klick-Schutz ist durch UNIQUE-Constraint + Skip-/Merge-Logik bereits gegeben. |
| `tages_zusammenfassung` | HA-Stats-Import, Solcast-Service, `live_wetter`, Kraftstoffpreis-Service | **Hoch** (Risiko #3) |
| `tages_energie_profil` | Connector + Snapshot-Service, MQTT-Inbound, HA-Stats-Backfill, Reaggregate-Endpoints | **Hoch** (Risiko #4 + Etappe-3c-Themen) |
| `sensor_snapshots` | Connector | Niedrig — eindeutiger Schreiber, Etappe 3c ergänzt Source-Marker |

### 1.4 Modul-Größen-Audit (Monster-PYs)

| Datei | Zeilen | Verantwortlichkeiten heute (vermischt) |
|---|---:|---|
| `routes/energie_profil.py` | 1741 | Read-Endpoints + Repair-Endpoints (reaggregate, vollbackfill, kraftstoffpreis-backfill) + Diagnose |
| `services/energie_profil_service.py` | 1621 | Tag-Aggregation aus Snapshots + HA-Stats-Backfill + Read-Helper + Reaggregator + Diagnose |
| `services/sensor_snapshot_service.py` | 1530 | Snapshot-Schreiben + HA-zu-MQTT-Fallback-Logik + Hourly-Aggregation + Reaggregate-Tag + Backfill aus HA-Stats |
| `routes/monatsabschluss.py` | 1092 | Wizard-Steps + Read-Endpoints + Auto-Aggregations-Logik (gehört in Service-Schicht) |
| `routes/custom_import.py` | 1046 | Analyze + Preview + Apply + Template-CRUD + DB-Schreib-Pfad |
| `services/solcast_service.py` | 593 | API-Fetch + Cache + DB-Write + Stundenprofil + Kalibrierung |

Diese Module sind **direkt betroffen** von 3d — Provenance-Helper, Provenance-Wrapper für Cloud-/CSV-Import und Orchestrator-Wrapping müssen hier integriert werden. Integration in Files mit > 1000 Zeilen ist praktisch nicht testbar und produziert Konflikt-Reibung. Refactoring ist daher nicht „nice to have", sondern Voraussetzung jedes betroffenen Päckchens (siehe Sektion 7 + Roadmap-Tails).

## 2. Die vier strukturellen Drift-Risiken

| # | Befund | Akute Folge | Code-Stelle | Päckchen |
|---|---|---|---|---|
| 1 | **Manual-Eingabe vs. Auto-Aggregation** — `monatsdaten` wird sowohl von User-Form als auch von Auto-Roll-up beschrieben, keine Konflikt-Auflösung | Manuelle Korrektur kann stillschweigend von nächtlichem Auto-Job überschrieben werden | `routes/monatsdaten.py` + Monatsabschluss-Logik | 3 |
| 2 | **Cloud-/CSV-Import überschreibt manuelle Werte** — bei `ueberschreiben=true` im Wizard werden manuelle Werte mit Cloud-/CSV-Werten ersetzt, ohne Hierarchie-Check | Manuelle Korrektur geht beim nächsten Cloud-Sync verloren | `routes/data_import.py` + `routes/custom_import.py` + `_upsert_investition_monatsdaten` | 3 |
| 3 | **Drei Prognose-Felder, ein Schreibpfad — prospektives Doppel-Schreiber-Risiko bei Quellenwahl-Schritt 4** — `tages_zusammenfassung.{pv,sfml,solcast}_prognose_kwh` werden heute alle exklusiv aus [`routes/live_wetter.py:816-820`](../eedc/backend/api/routes/live_wetter.py) geschrieben (kein Doppel-Schreiber heute, vgl. Sektion 1.1 Korrektur). Quellenwahl-Roadmap Schritt 4 (SFML-Connector) ergänzt einen zweiten Schreiber auf `sfml_prognose_kwh` parallel zum HA-Sensor-Pfad. Ohne 3d-Helper wäre das ein Drift-Pfad. **3d sperrt Risiko #3 prospektiv** — Memory-Linie `feedback_aggregations_drift.md`: SoT-Helper VOR neuen Schreibern. | Last-Writer-Wins ohne Hierarchie sobald SFML-Connector live geht | [`routes/live_wetter.py:818`](../eedc/backend/api/routes/live_wetter.py) + geplanter SFML-Connector | 6 |
| 4 | **Snapshot-Fallback unsichtbar war** — `sensor_snapshot_service` wechselt zu MQTT wenn HA unvollständig, kein Source-Marker. **Mit Etappe 3c P1 erledigt:** `sensor_snapshots.quelle`-VARCHAR ist seit v3.26.8 produktiv. 3d generalisiert das Pattern auf die 4 Aggregat-Tabellen mit Per-Feld-Provenance — disjunktes Vokabular. | Diagnose-Frage „MQTT-Fallback vs. HA-Native" bereits beantwortbar (P5 baut nur die UI-Sichtbarmachung) | [`models/sensor_snapshot.py`](../eedc/backend/models/sensor_snapshot.py), [`services/snapshot/source.py`](../eedc/backend/services/snapshot/source.py) | 5 |

**Wichtige Klarstellung:** Doppel-Klick-Schutz auf `investition_monatsdaten` und `monatsdaten` ist bereits gegeben — beide Tabellen haben UNIQUE-Constraints (`uq_inv_monatsdaten_periode`, `uq_monatsdaten_anlage_periode`), und der Apply-Pfad in `data_import.py:298–310` macht expliziten Skip-if-exists. Datenverdoppelung durch Doppel-Klick ist physisch unmöglich. Was die Risiken #1+#2 oben adressieren, ist **Hierarchie-Verletzung** beim absichtlichen Schreiben aus dem jeweiligen Pfad — kein Idempotenz-Problem.

**Risiko #3 ist prospektiv, Risiko #4 ist mit 3c bereits adressiert** (Status-Spalte oben):

- Risiko #1 + #2 sind die akut wirksamen Drift-Vektoren — ihre strukturelle Auflösung ist Päckchen 2 (Cloud/CSV-Anschluss) + Päckchen 3 (Konflikt-Resolver auf allen Aggregat-Schreibern).
- Risiko #3 wirkt erst mit Quellenwahl-Schritt 4. Genau diese Sequenz-Abhängigkeit ist die Begründung der Reihenfolgen-Entscheidung 2026-05-09: **3d komplett vor Quellenwahl**, damit der SFML-Connector beim Anlegen sofort über `write_with_provenance()` läuft, statt nachträglich migriert werden zu müssen.
- Risiko #4 ist seit v3.26.8 (Etappe 3c P1) auf Datenebene gelöst (`sensor_snapshots.quelle`); was offen bleibt, ist die UI-Sichtbarkeit (Päckchen 5 baut Daten-Checker-Sicht + Quellen-Badge).

Alle vier Risiken bleiben relevant — keines ist akut datenkorrumpierend, aber alle vier untergraben Vertrauen in die Daten über Zeit.

### 2.1 Sekundärbefunde aus Re-Inventur

Drei Befunde aus der Päckchen-1-Inventur, die Konzept v1 nicht hatte und die in nachfolgende Päckchen einfließen müssen:

- **Doppel-Implementierung Energie-Profil-Service:** [`services/energie_profil_service.py`](../eedc/backend/services/energie_profil_service.py) und [`services/energie_profil/aggregator.py`](../eedc/backend/services/energie_profil/aggregator.py) schreiben beide auf `tages_zusammenfassung` und `tages_energie_profil`. Nach Etappe 3c P3 (`aggregate_day` in eigenen Slice) sollte der `_service.py`-Pfad nur noch alte Konsumenten haben. **Päckchen 3 muss prüfen**, ob die `_service.py`-Schreib-Pfade Tot-Code sind, bevor `write_with_provenance()` integriert wird — sonst wird derselbe Provenance-Anschluss zweimal gemacht.
- **Demo-Data + JSON-Backup-Restore + CSV-Operations als zusätzliche Aggregat-Schreiber:** Diese drei Pfade sind in Konzept v1 nicht gelistet, schreiben aber in produktive Aggregat-Tabellen. **Päckchen 2** muss sie mit-anschließen: JSON-Backup-Restore ist produktiver Pfad (User-Backup einspielen → Source `manual:json_backup`), Demo-Data ist Erstinstallations-Pfad (Source `auto:demo_data`, niedrige Priorität ist OK), CSV-Operations ist separater Backup-Pfad (Source `manual:csv_backup`). Vokabular wird in Päckchen 2 ergänzt.
- **Cloud-Daten-Reset hat keinen Endpoint:** Konzept v1 ging von einem `DELETE /cloud-import/anlage/{id}` aus. Tatsächlich gibt es nur `DELETE /cloud-import/credentials/{anlage_id}`, was nur Credentials löscht. **Päckchen 4** muss `RESET_CLOUD_IMPORT` als neue Operation im Repair-Orchestrator anlegen, nicht als Wrapper über Bestehendem.

## 3. Quellen-Hierarchie & Provenance-Tracking

### 3.1 Hierarchie pro Feld

Fünf Stufen, niedrigere Zahl = höhere Priorität:

| Priorität | Source-Klasse | Beispiele | Begründung |
|---|---|---|---|
| 0 | `repair` | Repair-Orchestrator mit `force_override=True` | Korrektur-Lauf steht über allem — ein expliziter User-„Reset" muss jede Hierarchie durchbrechen können. Audit-Log-pflichtig mit Operation-ID. |
| 1 | `manual` | Monatsdaten-Form, Investitions-Form, CSV-Import-Wizard | User-Eingabe ist Wahrheit — niemals von Maschine überschreiben. CSV gleichauf, weil bewusst gewählter Klick-Pfad. |
| 2 | `external_authoritative` | Cloud-Portale (Solaredge/Fronius/...), HA-Statistics-LTS-Backfill | Maschinen-bestätigte Quelle, aber nicht User-bestätigt. Konflikt zwischen Cloud + HA-Stats: Last-Writer-Wins (selten, in Praxis eindeutiger Pfad pro Anlage). |
| 3 | `auto_aggregation` | Monatsabschluss-Roll-up aus Tageswerten, abgeleitete Berechnungen | Berechnet, Annahmen-behaftet. |
| 4 | `fallback` | Sensor-Snapshot Live-Aggregator, MQTT-Fallback bei HA-Lücken | Best-Effort, lückenanfällig. |

Last-Writer-Wins innerhalb einer Stufe ist akzeptiert (gleiche „Vertrauensklasse" → kein zwingender Tiebreaker nötig). Wer wirklich entscheiden muss, kann den Repair-Orchestrator (Stufe 0) gezielt einsetzen.

Definiert in neuem Modul `backend/core/source_priority.py` (analog `field_definitions.py`, `mqtt_topic_registry.py`):

```python
# backend/core/source_priority.py
from enum import IntEnum

class SourcePriority(IntEnum):
    REPAIR = 0
    MANUAL = 1
    EXTERNAL_AUTHORITATIVE = 2
    AUTO_AGGREGATION = 3
    FALLBACK = 4

SOURCE_LABELS: dict[str, SourcePriority] = {
    "repair": SourcePriority.REPAIR,                                # Repair-Orchestrator force_override
    "manual:form": SourcePriority.MANUAL,                           # Monatsdaten/Investitions-Form
    "manual:csv_import": SourcePriority.MANUAL,                     # CSV-Wizard
    # 11 Cloud-Provider aus services/cloud_import/
    "external:cloud_import:anker_solix":         SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:deye_solarman":       SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:ecoflow_powerocean":  SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:ecoflow_powerstream": SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:fronius_solarweb":    SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:growatt":             SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:hoymiles_smiles":     SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:huawei_fusionsolar":  SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:solaredge":           SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:sungrow_isolarcloud": SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:cloud_import:viessmann_gridbox":   SourcePriority.EXTERNAL_AUTHORITATIVE,
    "external:ha_statistics": SourcePriority.EXTERNAL_AUTHORITATIVE,
    "auto:monatsabschluss":  SourcePriority.AUTO_AGGREGATION,
    "fallback:sensor_snapshot": SourcePriority.FALLBACK,
    "fallback:mqtt_inbound":    SourcePriority.FALLBACK,
}
```

`repair` als eigene Stufe (statt nur `force_override=True`-Flag auf einer anderen Quelle) macht Korrektur-Läufe im Audit-Log auf den ersten Blick erkennbar — relevant für Diagnose-Frage „warum hat dieser Wert seine Provenance verloren?".

### 3.2 Inline-Provenance: `source_provenance`-Spalte

Neue JSON-Spalte in den 4 Aggregat-Tabellen (`monatsdaten`, `investition_monatsdaten`, `tages_zusammenfassung`, `tages_energie_profil`):

```python
class Monatsdaten(Base):
    # ... bestehende Felder
    source_provenance = Column(JSON, nullable=False, default=dict)
    # Inhalt:
    # {
    #   "netzbezug_kwh":   {"source": "manual",
    #                        "writer": "user@email",
    #                        "at": "2026-05-09T10:33:00Z"},
    #   "pv_erzeugung_kwh": {"source": "auto_aggregation:monatsabschluss",
    #                        "writer": "monatsabschluss_service",
    #                        "at": "2026-05-08T03:00:00Z",
    #                        "input_hash": "sha256:..."}
    # }
```

Pro Feld: `source` (Label aus `SOURCE_LABELS`), `writer` (User-Email für `manual`, Service-Name für `auto`, Provider-Account-ID für Cloud), `at` (ISO-Timestamp), optional `input_hash` (für idempotente Sources, siehe Sektion 6).

### 3.3 Audit-Log: `data_provenance_log`

Neue Append-Only-Tabelle für historische Diagnose („wer hat im Februar mein Investitions-Monatsdatum überschrieben?"):

```sql
CREATE TABLE data_provenance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,           -- "monatsdaten" | "investition_monatsdaten" | ...
    row_pk_json TEXT NOT NULL,          -- JSON: {"anlage_id": 1, "jahr": 2026, "monat": 4}
    field_name TEXT NOT NULL,
    source TEXT NOT NULL,
    writer TEXT NOT NULL,
    written_at TEXT NOT NULL,           -- ISO-Timestamp
    old_value TEXT,                     -- JSON-encoded (nullable für Initial-Insert)
    new_value TEXT,                     -- JSON-encoded
    input_hash TEXT,                    -- für idempotente Sources
    decision TEXT NOT NULL,             -- "applied" | "rejected_lower_priority" | "no_op_same_value"
    decision_reason TEXT
);

CREATE INDEX idx_provlog_lookup
    ON data_provenance_log (table_name, row_pk_json, written_at DESC);
CREATE INDEX idx_provlog_audit
    ON data_provenance_log (writer, written_at DESC);
```

**Append-only Garantie:** Keine UPDATE/DELETE-Pfade auf diese Tabelle, weder im Code noch via Migration. Eine spätere Retention-Policy (z. B. „älter als 24 Monate → archivieren") ist möglich, selektive Löschung nicht.

### 3.4 Zentraler Helper Pflicht

Pattern aus `feedback_aggregations_drift.md` und `mqtt_topic_registry.py`: ein einziger SoT-Helper, alle Schreiber gehen darüber.

```python
# backend/services/provenance.py

@dataclass
class WriteResult:
    applied: bool
    decision: Literal["applied", "rejected_lower_priority", "no_op_same_value"]
    reason: str
    conflicting_source: Optional[str] = None  # bei rejected_lower_priority

def write_with_provenance(
    db: Session,
    obj: Base,
    field: str,
    value: Any,
    source: str,
    writer: str,
    input_hash: Optional[str] = None,
    *,
    force_override: bool = False,  # nur für Repair-Orchestrator
) -> WriteResult:
    """
    Atomarer Write mit Hierarchie-Check + Audit-Log + JSON-Source-Update.

    - Liest aktuelle source_provenance[field] aus obj
    - Vergleicht via SOURCE_LABELS[new_source].priority vs. existing
    - Bei höherer oder gleicher Priorität: schreibt + Audit-Log "applied"
    - Bei niedrigerer Priorität: kein Schreiben + Audit-Log "rejected_lower_priority"
    - Bei identischem Wert + Hash: kein Schreiben + Audit-Log "no_op_same_value"
    - flag_modified(obj, "source_provenance") wegen JSON-Falle
    """
```

`force_override=True` ist allein dem Repair-Orchestrator (Sektion 5) vorbehalten und immer mit explizitem Audit-Log-Eintrag inklusive Operation-ID.

## 4. Konflikt-Resolver-Architektur

### 4.1 Synchroner Resolver im Write-Pfad

`provenance.write_with_provenance()` (Sektion 3.4) ist der Resolver. Konkret:

```
existing = obj.source_provenance.get(field)
if existing is None:
    → applied (Initial-Write, immer)
elif SOURCE_LABELS[new].priority < SOURCE_LABELS[existing.source].priority:
    → applied (höhere Priorität gewinnt — niedrigere Zahl ist höher)
elif SOURCE_LABELS[new].priority == SOURCE_LABELS[existing.source].priority:
    → applied (gleiche Source-Klasse, Last-Writer-Wins ist OK)
else:
    → rejected_lower_priority + Audit-Log + WriteResult(applied=False, ...)
```

**Folge:** Auto-Aggregation kann manuell gepflegte Werte nicht mehr überschreiben (Risiko #1 gelöst). Cloud-/CSV-Import kann manuell gepflegte Werte nicht überschreiben (Risiko #2 gelöst). Sensor-Snapshot kann nicht versehentlich Cloud-Werte verdrängen.

### 4.2 Asynchrone Sichtbarkeit: Daten-Checker `PROVENANCE_CONFLICT`

Neue Kategorie in `services/daten_checker.py`:

```python
def check_provenance_conflicts(db: Session, anlage_id: int, days: int = 30) -> list[Anomaly]:
    """
    Scannt data_provenance_log auf Felder mit ≥ 2 distinct sources im Zeitraum.
    Meldet pro Konflikt: Tabelle, Row-PK, Feld, Quellen, letzte Entscheidung.
    """
```

UI-Behandlung folgt `feedback_daten_checker_kein_akzeptiert.md`: **kein Quittier-Knopf**, nur Hinweis + Link zur Reparatur-Werkbank (Sektion 5). Konflikte verschwinden erst, wenn die strukturelle Ursache adressiert ist (Quelle deaktivieren / Hierarchie anpassen / Reparatur durchführen).

### 4.3 UI-Sichtbarkeit der Provenance pro Datensatz

Quellen-Badge pro Wert mit Hover-Tooltip („zuletzt geschrieben von X via Y am Z") in Monatsdaten-/Investitions-/Energieprofil-Detail-Ansichten. UX-Polish, kein Critical-Path — landet in Päckchen 7.

## 5. Reparatur-Orchestrator

### 5.1 Service-Schnitt

```python
# backend/services/repair_orchestrator.py

class RepairOperationType(str, Enum):
    REAGGREGATE_DAY = "reaggregate_day"
    REAGGREGATE_TODAY = "reaggregate_today"
    VOLLBACKFILL = "vollbackfill"
    KRAFTSTOFFPREIS_BACKFILL = "kraftstoffpreis_backfill"
    DELETE_MONATSDATEN = "delete_monatsdaten"
    RESET_CLOUD_IMPORT = "reset_cloud_import"
    SOLCAST_REWRITE = "solcast_rewrite"  # Risiko #3

class FieldDiff(BaseModel):
    table: str
    row_pk: dict
    field: str
    old_value: Any
    new_value: Any
    source_before: Optional[str]
    source_after: str
    decision: Literal["applied", "rejected_lower_priority", "no_op_same_value"]

class RepairPlan(BaseModel):
    plan_id: UUID
    anlage_id: int
    operation: RepairOperationType
    operation_params: dict
    created_at: datetime
    expires_at: datetime                # z. B. +1h
    estimated_changes: dict[str, int]
    diff_preview: list[FieldDiff]       # paginiert / capped (z. B. 200 Einträge)
    diff_total_count: int
    warnings: list[str]                 # z. B. "12 Felder werden Auto-Aggregation
                                        #        überschreiben — ist das gewollt?"

class RepairResult(BaseModel):
    plan_id: UUID
    executed_at: datetime
    actual_changes: dict[str, int]
    audit_log_ids: list[int]            # Verknüpfung in data_provenance_log

async def plan(req: RepairOperationRequest) -> RepairPlan: ...
async def execute(plan_id: UUID) -> RepairResult: ...
async def list_plans(anlage_id: int, limit: int = 20) -> list[RepairPlan]: ...
async def discard_plan(plan_id: UUID) -> None: ...
```

**Plan-Lebenszyklus:** in-memory + Lock (analog Snapshot-Cache). Expiry verhindert „Stale Plan trifft veränderten Datenbestand".

### 5.2 Bestehende Endpoints werden Wrapper

Backward-Kompat: alte Reparatur-Endpoints rufen intern Orchestrator auf, Frontend stellt schrittweise um.

| Alter Endpoint | Neuer Pfad |
|---|---|
| `POST /reaggregate-tag` | intern `plan()` + sofortiges `execute()` (kein Frontend-Break); parallel neue API `/repair/plan` + `/repair/execute/{plan_id}` für Plan-Vorschau |
| `POST /vollbackfill` | analog — alte Body-Parameter mappen 1:1 auf `RepairOperationRequest` |
| `POST /kraftstoffpreis-backfill[/tages\|/monats]` | analog |
| `POST /reaggregate-heute` | analog |
| `DELETE /monatsdaten/{id}` | bleibt direkt (kein Orchestrator-Bedarf für Single-Row-Delete), schreibt aber Audit-Log |
| `DELETE /cloud-import/anlage/{id}` | wird Orchestrator-Operation `RESET_CLOUD_IMPORT` (mit Vorschau!) |

### 5.3 Vereinheitlichte Reparatur-Werkbank im Frontend

Erweiterung der heutigen Datenverwaltung-Seite (`pages/Datenverwaltung.tsx`):

- **Operation-Auswahl** als Liste verfügbarer Reparaturen mit Kurzbeschreibung
- **Plan-Vorschau** als Tabelle der Field-Diffs, gruppiert nach Tabelle, mit Decision-Anzeige (`applied` / `rejected_lower_priority`)
- **Bestätigungs-Knopf** „Diese 47 Änderungen anwenden" statt heutigem Direkt-Klick
- **Verlauf** der letzten Reparaturen mit Verknüpfung zum Audit-Log

## 6. Cloud-/CSV-Import an Provenance anschließen

> **Korrektur gegenüber Übergabe-Notiz:** Die ursprünglich angenommene Idempotenz-Lücke existiert nicht — UNIQUE-Constraints und Skip-/Merge-Logik im Apply-Pfad sind schon da. Was bleibt zu tun, ist der Hierarchie-Anschluss (Risiko #2): Cloud-/CSV-Import muss `write_with_provenance()` verwenden, damit das `ueberschreiben=true`-Häkchen manuelle Werte nicht stillschweigend ersetzt.

### 6.1 Schema-Ergänzung

```sql
-- Optional, für Provenance-Drill-Down: erkennt ob ein Re-Import
-- denselben Datensatz nochmal liefert (ohne Wertänderung)
ALTER TABLE investition_monatsdaten ADD COLUMN source_hash TEXT;
ALTER TABLE monatsdaten ADD COLUMN source_hash TEXT;
```

UNIQUE-Constraints auf `(investition_id, jahr, monat)` und `(anlage_id, jahr, monat)` sind **bereits vorhanden** — kein Schema-Change nötig.

### 6.2 Gemeinsamer Provenance-Wrapper für Cloud + CSV

Heutiger `_upsert_investition_monatsdaten` in [`routes/import_export/helpers.py:60`](../eedc/backend/api/routes/import_export/helpers.py) wird zur Provenance-Variante umgebaut:

```python
# backend/services/import_writer.py (neu — gemeinsam für Cloud + CSV)

async def upsert_investition_monatsdaten_with_provenance(
    db: AsyncSession,
    *,
    investition_id: int,
    jahr: int,
    monat: int,
    payload: dict[str, Any],
    source: str,           # "external:cloud_import:solaredge" | "manual:csv_import" | ...
    writer: str,           # Account-ID / User-Email / Connector-Run-ID
    ueberschreiben: bool,  # Wizard-Flag — wirkt nur als zusätzliche Erlaubnis,
                           # ersetzt die Hierarchie nicht
) -> WriteResult:
    """
    1. Berechnet source_hash = sha256(canonical_json(payload))
    2. SELECT existing WHERE (investition_id, jahr, monat)
    3. Wenn existing.source_hash == source_hash → No-Op + Audit-Log("no_op_same_value")
    4. Sonst: für jedes Feld in payload → write_with_provenance()
       — Hierarchie blockiert Überschreiben manueller Werte trotz ueberschreiben=true
       — gleiche Source-Klasse + ueberschreiben=true: erlaubt
    5. existing.source_hash = source_hash, db.commit()
    """
```

**Verhalten gegenüber heute:**
- **Doppel-Klick mit unverändertem Payload:** war schon idempotent, ist jetzt zusätzlich im Audit-Log als „no_op_same_value" sichtbar.
- **`ueberschreiben=true` auf manuell gepflegtem Wert:** war bisher destruktiv, wird jetzt durch Hierarchie blockiert. User sieht in der Wizard-Antwort „X Felder durch manuelle Eingabe geschützt — Reset über Reparatur-Werkbank wenn gewollt".
- **`ueberschreiben=true` auf Cloud-/CSV-Wert (gleiche Source-Klasse):** erlaubt wie heute.

### 6.3 Migration der 11 Cloud-Importer + CSV-Importer + Backup-/Restore-Pfade

Cloud-Importer schreiben heute nicht direkt in die DB — sie liefern Daten an den Apply-Pfad in `data_import.py`, der `_upsert_investition_monatsdaten` ruft. Migration daher punktuell:

1. **`routes/import_export/helpers.py:_upsert_investition_monatsdaten`** auf Provenance-Wrapper umstellen — wirkt für CSV (`routes/custom_import.py`) und Cloud-Apply (`routes/data_import.py`) gleichermaßen.
2. **`routes/data_import.py`** Skip-Logic für `monatsdaten` ebenfalls auf `write_with_provenance` umstellen (Konstruktor-Stelle [Z. 316](../eedc/backend/api/routes/data_import.py)).
3. **`routes/custom_import.py`** (CSV) — gleicher Helper, Source-Tag `manual:csv_import`. Konstruktor-Stelle [Z. 1000](../eedc/backend/api/routes/custom_import.py).
4. **`routes/import_export/json_operations.py`** (Anlagen-JSON-Backup-Restore) — produktiver User-Pfad. Source-Tag `manual:json_backup`. Zwei Konstruktor-Stellen [Z. 649 + Z. 695](../eedc/backend/api/routes/import_export/json_operations.py).
5. **`routes/import_export/csv_operations.py`** (Backup-CSV, separater Pfad vom Custom-Import) — Source-Tag `manual:csv_backup`. [Z. 455](../eedc/backend/api/routes/import_export/csv_operations.py).
6. **`routes/import_export/demo_data.py`** (Standalone-Erstinstallations-Demo) — Source-Tag `auto:demo_data` mit Priorität `AUTO_AGGREGATION`, damit ein nachträgliches manuelles Bearbeiten den Demo-Wert sauber schlägt. 8 Konstruktor-Stellen.
7. Wizard-Texte anpassen: „X von Y Feldern durch manuelle Werte geschützt" als sichtbares Ergebnis im Apply-Schritt.

Die 11 Connector-Files in `services/cloud_import/*.py` (`anker_solix`, `deye_solarman`, `ecoflow_powerocean`, `ecoflow_powerstream`, `fronius_solarweb`, `growatt`, `hoymiles_smiles`, `huawei_fusionsolar`, `solaredge`, `sungrow_isolarcloud`, `viessmann_gridbox`) selbst müssen nicht angefasst werden — sie produzieren nur Daten, persistieren nicht.

`SOURCE_LABELS` in [`source_priority.py`](../eedc/backend/core/source_priority.py) muss damit erweitert werden um `manual:json_backup` (MANUAL), `manual:csv_backup` (MANUAL), `auto:demo_data` (AUTO_AGGREGATION). Diese drei Labels sind Päckchen-2-Lieferung, nicht Päckchen-1 — Päckchen 1 trägt nur das Vokabular ein, das im Konzept Sektion 3.1 explizit benannt ist (`manual:form`, `manual:csv_import`, 11× `external:cloud_import:*`, `external:ha_statistics`, `auto:monatsabschluss`, `fallback:sensor_snapshot`, `fallback:mqtt_inbound`, `repair`).

## 7. Modul-Refactoring (Monster-PYs zerlegen)

### 7.1 Pattern: Vertical Slicing nach Verantwortlichkeit

Jedes betroffene Monster-PY (Sektion 1.4) wird **vor** der Provenance-/Resolver-/Orchestrator-Integration in Verantwortlichkeits-Slices zerlegt. Pattern bewusst gleich für alle Files:

- **Routes** zerfallen in `views.py` (Read-only GET) + `repair.py` / `wizard.py` (Write-Endpoints) + `__init__.py` (Router-Aggregation).
- **Services** zerfallen in `<slice>.py` pro Verantwortlichkeit, mit `__init__.py` als Re-Export-Fassade — bestehende Importer im restlichen Code bleiben unverändert (`from services.energie_profil_service import X` funktioniert weiter).
- **Tests** ziehen mit, pro Slice eigenes `test_<slice>.py`.

Slice-Schnitte werden so gewählt, dass die Provenance-Integration danach **eine** Datei pro Aggregat-Schreibstelle anfasst, nicht mehrere parallel.

### 7.2 Zerlegungs-Plan pro Monster-PY

| Heute | Soll-Struktur | Zugeordnet zu |
|---|---|---|
| `routes/energie_profil.py` (1741) | `routes/energie_profil/views.py` (Read), `routes/energie_profil/repair.py` (alle Repair-Endpoints — wird in Päckchen 4 zu Orchestrator-Wrapper), `__init__.py` | Päckchen 4 |
| `services/energie_profil_service.py` (1621) | `services/energie_profil/aggregator.py` (Tag-Aggregation aus Snapshots), `services/energie_profil/backfill.py` (HA-Stats-Backfill), `services/energie_profil/reader.py` (Read-Helper), `services/energie_profil/reaggregator.py` (Reaggregate-Tag), `__init__.py` Re-Export | Päckchen 3 |
| `services/sensor_snapshot_service.py` (1530) | `services/snapshot/writer.py` (Snapshot-Schreiben pro Sensor), `services/snapshot/aggregator.py` (Snapshots → Hourly), `services/snapshot/fallback.py` (HA → MQTT-Fallback-Logik, **Source-Marker landet hier**), `services/snapshot/reaggregator.py`, `services/snapshot/backfill.py`, `__init__.py` | Päckchen 3 (Zerlegung), Päckchen 5 (Source-Marker integrieren) |
| `routes/monatsabschluss.py` (1092) | `routes/monatsabschluss/wizard.py` (Multi-Step), `routes/monatsabschluss/views.py` (Read), **plus** Auslagerung der Auto-Aggregations-Logik aus der Route nach `services/monatsabschluss_aggregator.py` (gehört nicht in einen Route-Layer) | Päckchen 3 |
| `routes/custom_import.py` (1046) | `routes/custom_import/analyze.py`, `routes/custom_import/preview.py`, `routes/custom_import/apply.py`, `routes/custom_import/templates.py`, **plus** Auslagerung des DB-Schreib-Pfads nach `services/import_writer.py` (gemeinsamer Provenance-Wrapper für Cloud + CSV, siehe Päckchen 2) | Päckchen 2 |
| `services/solcast_service.py` (593) | `services/solcast/api.py` (API-Fetch + Quota), `services/solcast/cache.py`, `services/solcast/writer.py` (DB-Write — landet in Päckchen 6 als alleiniger Schreiber), `services/solcast/kalibrierung.py` | Päckchen 6 |

### 7.3 Refactoring-Disziplin

- **Pro Päckchen:** Refactoring-PR landet **vor** der Architektur-PR (zwei distincte Commits oder zwei distincte PRs). Kein Vermischen.
- **Verhalten unverändert:** Refactoring-PR ist reines Verschieben + Re-Export, alle Tests grün, kein Verhaltens-Diff. CI-Smoke + manueller Round-Trip in HA-Add-on.
- **Keine spekulativen Slices:** ein Slice pro Verantwortlichkeit, die heute schon im File existiert. Nicht „könnte mal jemand brauchen". Memory-Linie `feedback_pfadabhaengigkeits_reflex.md` gilt auch hier.

## 8. Migrations-Roadmap

Reihenfolge: Etappe 3c zuerst abschließen, dann Etappe 3d in nummerierten Päckchen. Pro Päckchen: **Refactoring-Tail** zuerst (Sektion 7.2), dann Architektur-Integration.

### Päckchen 1 — Datenmodell-Fundament
**Voraussetzung:** Etappe 3c abgeschlossen ✅ (v3.26.8, 2026-05-09).

- ✅ Lückenlose Re-Inventur aller Schreiber + Reparatur-Pfade (Sektion 1 entsprechend nachgezogen 2026-05-09; präzise Schreib-Pfad-Tabellen statt Best-Effort)
- Migration: `data_provenance_log`-Tabelle anlegen
- Migration: `source_provenance` JSON-Spalte in 4 Aggregat-Tabellen (`monatsdaten`, `investition_monatsdaten`, `tages_zusammenfassung`, `tages_energie_profil`)
- Migration: `source_hash` TEXT-Spalte in `monatsdaten` + `investition_monatsdaten`
- Modul `backend/core/source_priority.py` mit Hierarchie-Konstanten — initiales Vokabular: `repair`, `manual:form`, `manual:csv_import`, 11× `external:cloud_import:*`, `external:ha_statistics`, `auto:monatsabschluss`, `fallback:sensor_snapshot`, `fallback:mqtt_inbound`. Zusätzliche Labels (`manual:json_backup`, `manual:csv_backup`, `auto:demo_data`) folgen in Päckchen 2.
- Modul `backend/services/provenance.py` mit `write_with_provenance()` + Unit-Tests
- **Refactoring-Tail:** keiner (nur neue Module).

→ **Akzeptanz:** Alle Tests grün, Schema migriert, Helper aufrufbar, kein Verhaltens-Diff. Helper wird in P1 von keinem Schreib-Pfad bereits gerufen — das ist Päckchen 3.

### Päckchen 2 — Cloud-/CSV-Import an Provenance anschließen
- **Refactoring-Tail:** `routes/custom_import.py` zerlegen (Sektion 7.2).
- `source_hash`-Spalte in `investition_monatsdaten` + `monatsdaten` (für Provenance-Drill-Down, optional)
- `services/import_writer.py` als gemeinsamer Provenance-Wrapper (siehe 6.2)
- `_upsert_investition_monatsdaten` in `routes/import_export/helpers.py` auf Provenance-Wrapper umstellen
- CSV-Apply-Pfad (`routes/custom_import.py`) auf Provenance-Wrapper umstellen
- Wizard-Texte: „X von Y Feldern durch manuelle Werte geschützt" als sichtbares Ergebnis im Apply-Schritt
- Daten-Checker: optionaler `import_no_op_same_value`-Counter pro Anlage (Diagnose, ob Re-Imports etwas ändern)

→ **Akzeptanz:** `ueberschreiben=true` auf einem manuell gepflegten Feld lässt den manuellen Wert stehen + Wizard zeigt Schutz-Hinweis. Audit-Log dokumentiert die `rejected_lower_priority`-Entscheidung. UNIQUE-Constraint-Schutz aus dem Status quo bleibt unverändert wirksam.

### Päckchen 3 — Konflikt-Resolver aktivieren
- **Refactoring-Tail:** `services/energie_profil_service.py` + `services/sensor_snapshot_service.py` + `routes/monatsabschluss.py` zerlegen (Sektion 7.2). Auto-Aggregations-Logik aus der Monatsabschluss-Route in den neuen Service auslagern.
- `write_with_provenance()` in alle 4 Aggregat-Schreib-Pfade einsetzen:
  - Manual-Form (`routes/monatsdaten.py`)
  - Auto-Aggregation (`services/monatsabschluss_aggregator.py` neu)
  - HA-Stats-Import (`services/ha_statistics_service.py`)
  - Solcast-Service (Stub für Risiko #3, finale Auflösung in Päckchen 6)
- Daten-Checker: `PROVENANCE_CONFLICT`-Kategorie aktivieren
- Migration: bestehende Datenbestände bekommen Initial-`source_provenance` mit Konvention `"legacy:unknown"` (niedrigste Priorität)

→ **Akzeptanz:** Manuelle Korrektur überlebt nächtlichen Auto-Aggregations-Job. Daten-Checker meldet Doppel-Schreiber-Felder.

### Päckchen 4 — Reparatur-Orchestrator
- **Refactoring-Tail:** `routes/energie_profil.py` zerlegen (Sektion 7.2). Repair-Endpoints landen in `routes/energie_profil/repair.py`.
- `RepairOrchestrator`-Service mit Plan + Execute
- Bestehende Repair-Endpoints zu Wrapper umstellen (kein Frontend-Break)
- Neue Plan-API + Vorschau-API
- Frontend: zentrale Reparatur-Werkbank in Datenverwaltung
- Verlauf-Ansicht mit Audit-Log-Verknüpfung

→ **Akzeptanz:** Vor jeder Reparatur sieht User Diff-Vorschau. Verlauf zeigt mindestens letzte 20 Operationen.

### Päckchen 5 — Snapshot-Source-Marker (Risiko #4)
- **Refactoring-Tail:** keiner — `sensor_snapshot_service` ist bereits in Päckchen 3 zerlegt.
- `services/snapshot/fallback.py` schreibt Source-Marker `sensor_snapshot` vs. `mqtt_fallback` in `source_provenance`
- Daten-Checker zeigt Fallback-Quote pro Anlage und Zeitraum

→ **Akzeptanz:** Diagnose „Welche meiner Tagesprofile basieren auf MQTT-Fallback statt HA-Native?" ist beantwortbar.

### Päckchen 6 — Solcast-Doppel-Schreiber auflösen (Risiko #3)
- **Refactoring-Tail:** `services/solcast_service.py` zerlegen (Sektion 7.2).
- `tages_zusammenfassung.solcast_prognose_kwh` bekommt eindeutigen Schreiber via Resolver
- Entscheidung: gewinnt `services/solcast/writer.py` (geplanter Schreiber) immer, `routes/live_wetter.py`-Logging-Pfad wird stillgelegt — analog zum geplanten `sfml_prognose_kwh`-Cleanup aus dem Quellenwahl-Konzept
- Migration: bestehende Datenbestände bekommen Source-Tag

→ **Akzeptanz:** Nur ein Pfad schreibt in `solcast_prognose_kwh`; Audit-Log bestätigt.

### Päckchen 7 — Provenance-UI-Polish
- **Refactoring-Tail:** keiner (Frontend).
- Quellen-Badge in Monatsdaten-/Investitions-/Energieprofil-Detail-Views
- Hover-Tooltip mit Source + Writer + Timestamp
- Audit-Log-Drill-Down per Feld
- Optional: „Show all changes for this field"-Modal

→ **Akzeptanz:** User kann pro Wert einsehen, wer ihn zuletzt warum gesetzt hat.

## 9. Verhältnis zu anderen Konzepten

[`KONZEPT-ENERGIEPROFIL.md`](KONZEPT-ENERGIEPROFIL.md) Etappe 3c liefert Slot-Konvention + Source-Tracking auf `sensor_snapshots` als Schema-Vorlage; 3d generalisiert auf alle Aggregat-Tabellen. [`KONZEPT-PROGNOSEQUELLEN-WAHL.md`](KONZEPT-PROGNOSEQUELLEN-WAHL.md) ist Lese-Resolver pro Anlage über drei alternative Prognose-Quellen — disjunkt zum Schreib-Resolver hier, Berührungspunkt nur in Päckchen 6 (Solcast-Cleanup). [`KONZEPT-KORREKTURPROFIL.md`](KONZEPT-KORREKTURPROFIL.md), [`KONZEPT-LIVE-SNAPSHOT-5MIN.md`](KONZEPT-LIVE-SNAPSHOT-5MIN.md) und [`KONZEPT-MQTT-GATEWAY.md`](KONZEPT-MQTT-GATEWAY.md) sind unabhängig; MQTT-Gateway wird in Päckchen 5 lose berührt (Source-Marker `mqtt_fallback`).
