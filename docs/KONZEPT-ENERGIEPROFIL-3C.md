# Konzept: Architektur-Konsolidierung Energieprofil-Read-/Write-Pfade (Etappe 3c)

> **Status:** Konzept-Phase, Aufräum-Sprint Phase C+ (2026-05-09).
> **Voraussetzung Implementierung:** keine — v3.26.6 (Reload-Self-Healing) hat Bug A („Folgetag-Boundary fehlt im Resnap-Range") und den „Nur neu rechnen"-Pfad bereits ausgeliefert. 3c liefert die strukturelle Konsolidierung darüber hinaus.
> **Ziel:** Slot-Konvention im gesamten Code an die #144-Entscheidung angleichen, Tagesgesamt vs. Slot-Verteilung semantisch trennen, Snapshot-Quelle nachverfolgbar machen, UI-Trennung Resnap/Reaggregat explizit anbieten.
> **Bezug 3d:** Diese Etappe liefert das **Schema-Vorlagen-Pattern** für [`KONZEPT-DATENPIPELINE.md`](KONZEPT-DATENPIPELINE.md) Päckchen 1 — `source_provenance` auf den 4 Aggregat-Tabellen wird auf demselben Pattern aufgesetzt, das hier auf `sensor_snapshots` zum ersten Mal landet.

Vier Architektur-Entscheidungen tragen dieses Konzept:

- **E1: Backward-Konvention einheitlich (#144).** Counter-Pfad ist gegenüber #144 gedriftet und wird angeglichen. Slot-Indices werden niemals von Konsumenten selbst gerechnet, sondern über eine typed `BoundaryRange`-Klasse bereitgestellt.
- **E2: Tagesgesamt = Boundary-Differenz (HA-konform).** Slot-Σ und Tagesgesamt sind semantisch verschiedene Zeitfenster und dürfen nicht miteinander verwechselt werden. Daten-Checker meldet Drift nur über das HA-Tagesfenster.
- **E3: `quelle`-Spalte auf `sensor_snapshots`.** Minimaler Source-Marker (`VARCHAR(20)`), weil die Tabelle pro Zeile genau ein Datenfeld hält — keine JSON-Spalte nötig. 3d wird das Pattern auf Aggregat-Tabellen mit Per-Feld-Provenance erweitern.
- **E4: UI-Trennung Resnap vs. Reaggregat als zwei Modal-Buttons.** Backend behält Status quo (`mit_resnap`-Query-Param + Frontend-Auto-Erkennung), Frontend-UX wird transparent.

Implementierung in vier nummerierten Päckchen mit Refactoring-Tail vorab pro Päckchen (siehe Sektion 8). Refactoring der zwei Monster-Services ist Querschnitt von P1+P3, kein eigener Vor-Sprint.

## 1. Ist-Inventur

### 1.1 Slot-Konventions-Pfade (Read)

| Funktion | Code-Stelle | Snapshot-Range | Slot-Definition | Konvention | Konformität #144 |
|---|---|---|---|---|---|
| `get_hourly_kwh_by_category` | [`sensor_snapshot_service.py:454`](../eedc/backend/services/sensor_snapshot_service.py) | `h=-1..23` | `slot[h] = snap[h] − snap[h-1]` | **Backward** | ✓ konform |
| `get_hourly_counter_sum_by_feld` | [`sensor_snapshot_service.py:1008`](../eedc/backend/services/sensor_snapshot_service.py) | `h=0..24` | `slot[h] = snap[h+1] − snap[h]` | **Forward** | ✗ **gedriftet** |
| `get_daily_counter_deltas_by_inv` | [`sensor_snapshot_service.py:948`](../eedc/backend/services/sensor_snapshot_service.py) | `[Tag 00:00, Folgetag 00:00]` | `delta = snap[Folgetag 00] − snap[Tag 00]` | Boundary-Diff (Tagesfenster) | ✓ HA-konform |
| `get_reaggregate_preview` | [`sensor_snapshot_service.py:659`](../eedc/backend/services/sensor_snapshot_service.py) | 25 Boundaries (Vortag 23 → Folgetag 00) | mixed | mixed | ⚠ folgt Konsumenten |

→ **Eine Drift-Stelle:** `get_hourly_counter_sum_by_feld` ist nach #144 (April 2026) gegen die Backward-Festlegung als Forward implementiert worden. Der nachträgliche Inline-Kommentar in [`routes/energie_profil.py:1168-1171`](../eedc/backend/api/routes/energie_profil.py) rationalisiert die Asymmetrie als bewusst — `routes/energie_profil.py` ist aber nicht der Source-of-Truth für Slot-Konventionen, [`sensor_snapshot_service.py`](../eedc/backend/services/sensor_snapshot_service.py) ist es. #144 (Forum-Issue, dokumentierte Entscheidung) gilt.

### 1.2 Snapshot-Schreiber (auf `sensor_snapshots`)

| # | Pfad | Code-Stelle | Quellen-Charakter | Heute markiert? |
|---|---|---|---|---|
| 1 | Stündlicher Job (HA-Statistics) | `snapshot_anlage` ([`sensor_snapshot_service.py:1141`](../eedc/backend/services/sensor_snapshot_service.py)) | Maschinen-bestätigt, präzise | ✗ |
| 2 | 5-Min-Job (HA-Statistics short_term) | `snapshot_anlage_5min` ([`sensor_snapshot_service.py:1243`](../eedc/backend/services/sensor_snapshot_service.py)) | Maschinen-bestätigt, kurzfristig | ✗ |
| 3 | Resnap-Recovery (HA-Statistics) | `resnap_anlage_range` ([`sensor_snapshot_service.py:1314`](../eedc/backend/services/sensor_snapshot_service.py)) | Maschinen-bestätigt, force | ✗ |
| 4 | MQTT-Live-Fallback (Standalone) | `live_snapshot_if_missing` ([`sensor_snapshot_service.py:1448`](../eedc/backend/services/sensor_snapshot_service.py)) | Best-Effort, MQTT-Topic | ✗ |
| 5 | MQTT-Inbound-Service | [`services/mqtt_inbound_service.py`](../eedc/backend/services/mqtt_inbound_service.py) (indirekter Pfad über `mqtt_energy_snapshots` → Aggregator) | Standalone-Lifeline | ✗ |
| 6 | Backfill aus HA-Long-Term-Statistics | innerhalb `snapshot_anlage` mit `force_resnap=True` | Maschinen-bestätigt, historisch | ✗ |

→ **Sechs Schreiber, kein Marker.** Diagnose-Frage „Welche Snapshots kommen aus welchem Pfad?" ist nicht beantwortbar; Sensor-Wechsel (Vicare → Optisplitter MartyBr 7.5.2026) wird nicht erkannt.

### 1.3 Repair-Pfade auf TagesEnergieProfil/TagesZusammenfassung

| Endpoint | Operation | v3.26.6-Update |
|---|---|---|
| `POST /reaggregate-heute` | Heute aus Snapshots neu zusammenrechnen | unverändert |
| `GET /reaggregate-tag/preview` | Vorschau (alt vs. neu) | Counter-Tagesdelta-Spalte (`fbfc172a`) |
| `POST /reaggregate-tag` | Tag neu aggregieren, optional mit Resnap | `mit_resnap=True` Default + Frontend-Auto-Erkennung „nur rechnen" wenn alt=neu (`ed5cc241`) |
| `POST /vollbackfill` | Komplette Historie neu bauen, additiv | unverändert |

Frontend (Datenverwaltung-Seite, `ReaggregatePreviewModal`):
- Auto-Erkennung „Resnap-Differenz=0 → mit_resnap=False" in v3.26.6 ✅
- **Nicht** umgesetzt: explizite Button-Trennung, AbortController, Modal-Cancel-Knopf bei langem Apply

### 1.4 Modul-Größen-Audit (Energieprofil-Subsystem)

| Datei | Zeilen | Verantwortlichkeiten heute (vermischt) |
|---|---:|---|
| [`routes/energie_profil.py`](../eedc/backend/api/routes/energie_profil.py) | 1741 | Read-Endpoints + Repair-Endpoints + Diagnose |
| [`services/energie_profil_service.py`](../eedc/backend/services/energie_profil_service.py) | 1621 | Tag-Aggregation + HA-Stats-Backfill + Read-Helper + Reaggregator + Diagnose |
| [`services/sensor_snapshot_service.py`](../eedc/backend/services/sensor_snapshot_service.py) | 1530 | Snapshot-Schreiben + HA-zu-MQTT-Fallback + Hourly-Aggregation + Reaggregate-Tag + Backfill |

Davon **direkt 3c-betroffen:**
- `services/sensor_snapshot_service.py` — Source-Marker landet hier (E3) + Slot-Konvention (E1) + BoundaryRange (E1).
- `services/energie_profil_service.py:aggregate_day` — Tagesgesamt-Trennung (E2) muss hier sauber durchgezogen werden.

## 2. Drift-Befunde (Soll/Ist)

| # | Befund | Akute Folge | Code-Stelle | Status | Päckchen |
|---|---|---|---|---|---|
| 1 | Counter-Pfad nutzt Forward statt Backward (#144-Drift) | Hourly-Verteilung Counter ↔ kWh um eine Stunde verschoben — visuell im Tagesverlauf, in Heatmaps unsichtbar weil eigene Achse | [`sensor_snapshot_service.py:1054`](../eedc/backend/services/sensor_snapshot_service.py) | offen | P2 |
| 2 | Tagesgesamt-Wege gemischt: `komponenten_starts` per Boundary-Diff, `wp_starts_anzahl[h]` per Hourly-Σ | Bei Lücken/NULL-Slots können beide auseinanderlaufen — UI zeigt verschiedene Werte für „dasselbe" KPI | [`sensor_snapshot_service.py:991-995`](../eedc/backend/services/sensor_snapshot_service.py) + [`:1060-1073`](../eedc/backend/services/sensor_snapshot_service.py) + [`energie_profil_service.py:404`](../eedc/backend/services/energie_profil_service.py) | offen | P3 |
| 3 | Quellen-Hierarchie auf `sensor_snapshots` nicht explizit | Drift-Quelle bei Sensor-Wechsel/Migration nicht zuordenbar; Diagnose „MQTT-Fallback vs. HA-Native" nicht möglich | [`models/sensor_snapshot.py`](../eedc/backend/models/sensor_snapshot.py) — kein `quelle`-Feld | offen | P1 |
| 4a | Resnap- vs. Reaggregat-Pfad strukturell nicht getrennt (Backend) | Hänger im Resnap blockierte ganze Reparatur (MartyBr „Bug D") | [`routes/energie_profil.py:1121-1227`](../eedc/backend/api/routes/energie_profil.py) | **gelöst v3.26.6** (`mit_resnap`-Param + Auto-Erkennung) | — |
| 4b | UI bietet die Trennung nicht explizit an | „Auto-Magic"-Verhalten — User sieht nicht, was passiert ist | `ReaggregatePreviewModal.tsx` | offen | P4 |
| 4c | Frontend kann lange Resnap-Calls nicht abbrechen | User muss Browser-Reload — Spinner ewig | `ReaggregatePreviewModal.tsx` (kein AbortController) | offen | P4 |
| 4d | Modal-X im Apply-Zustand nicht klickbar | Backend-Antwort verloren → User stuck | `ReaggregatePreviewModal.tsx:onClose={applying ? () => {} : onClose}` | offen | P4 |

Befund 4 ist nach v3.26.6 in vier Sub-Punkte zerfallen: Backend-Anteil (4a) ist erledigt, drei Frontend-UX-Items (4b/c/d) bleiben in P4.

## 3. E1 — Slot-Konvention vereinheitlichen auf Backward (#144)

### 3.1 Historische Entscheidung (Issue #144, April 2026)

Vor #144 verwendeten EEDC-Komponenten drei verschiedene Konventionen — OpenMeteo Backward, Solcast Center, IST-Snapshots Forward. Im Stundenvergleich-Chart standen die drei Spalten unter falschen Slot-Labeln nebeneinander (MartyBr/rapahl Forum-Bericht). Die Vereinheitlichung auf **Backward** wurde mit folgender Begründung beschlossen:

- Industriestandard: HA Energy Dashboard, SolarEdge, SMA Sunny Portal, Fronius Solar.web, Tibber-Verbrauchshistorie, EPEX Spotmarkt-Auktion
- OpenMeteo + Solcast nutzen Backward per API-Definition → keine Übersetzung nötig
- HA-Statistics ist Backward → konsistente Read-Pipeline
- Slot 0 = Energie [23:00 Vortag, 00:00 heute) ≈ 0 → semantisch sauber am Tagesübergang
- Strom-/Gas-Rechnung des Versorgers nutzt Backward (Verbrauch der vergangenen Stunde)

**Nicht** Backward: Strompreis-Slots (Forward, weil Tarif „ab jetzt gilt"-Semantik). Diese Ausnahme ist isoliert und nicht 3c-betroffen.

### 3.2 Counter-Pfad-Drift

`get_hourly_counter_sum_by_feld` wurde für Issue #136 (WP-Kompressor-Starts pro Stunde) **nach** #144 implementiert, hat die Backward-Festlegung aber nicht übernommen:

```python
# heute (Forward, gedriftet):
for h in range(25):  # 0..24, damit jede Stunde h ein Boundary-Paar (h, h+1) hat
    snaps[h] = await get_snapshot(...)
for h in range(24):
    total = snaps[h+1] − snaps[h]  # Slot h = Energie [h, h+1)
```

Soll-Verhalten (Backward, #144-konform):

```python
# soll (Backward):
for h in range(-1, 24):  # -1..23, identisch zu get_hourly_kwh_by_category
    snaps[h] = await get_snapshot(...)
for h in range(24):
    total = snaps[h] − snaps[h-1]  # Slot h = Counter-Inkremente [h-1, h)
```

Folge der Umstellung:
- Counter-Hourly-Slot-23 = Inkremente [22, 23) statt [23, 24).
- Bug A („Folgetag-00:00 fehlt im Resnap-Range" für Counter) existiert strukturell nicht mehr — Backward-Counter braucht **kein** Folgetag-00:00.
- Resnap-Range-Erweiterung in v3.26.6 (`bis_dt = tag_start + 25h`) bleibt aus Backward-Sicht überflüssig, kann aber für Robustheit (5-Min-Slots am Tagesende) bestehen bleiben.

### 3.3 BoundaryRange-Klasse

Konsumenten sollen niemals selbst Slot-Indices rechnen. Neue Hilfsklasse:

```python
# backend/services/snapshot/boundary_range.py (neu, in P1-Refactoring landet er hier)
from dataclasses import dataclass
from datetime import datetime, date, timedelta

@dataclass(frozen=True)
class BoundaryRange:
    """Typed Range über Snapshot-Boundaries für Hourly-Slot-Aggregation oder Tagesgesamt."""
    von: datetime           # erster zu lesender Snapshot (inklusiv)
    bis: datetime           # letzter zu lesender Snapshot (inklusiv)
    slot_offsets: list[int] # für Hourly: [-1..23]; für Tagesgesamt: [0, 24]

    @classmethod
    def for_hourly_slots(cls, datum: date) -> "BoundaryRange":
        """Backward-Slots: 25 Boundaries (Vortag 23:00 .. Heute 23:00). Slot h = snap[h] − snap[h-1]."""
        tag0 = datetime.combine(datum, datetime.min.time())
        return cls(von=tag0 - timedelta(hours=1), bis=tag0 + timedelta(hours=23),
                   slot_offsets=list(range(-1, 24)))

    @classmethod
    def for_day_total(cls, datum: date) -> "BoundaryRange":
        """Boundary-Diff: 2 Boundaries (Tag 00:00, Folgetag 00:00). Tagesgesamt = snap[24] − snap[0]."""
        tag0 = datetime.combine(datum, datetime.min.time())
        return cls(von=tag0, bis=tag0 + timedelta(hours=24), slot_offsets=[0, 24])

    def hour_for_offset(self, offset: int) -> int:
        """Slot-Index für Konsument: Backward-Slot h = Energie [h-1, h)."""
        if offset == -1:
            return 0
        return offset
```

Konsumenten:
- `get_hourly_kwh_by_category` — nutzt `BoundaryRange.for_hourly_slots(datum)`
- `get_hourly_counter_sum_by_feld` — nutzt `BoundaryRange.for_hourly_slots(datum)` (gleiche Range — Drift behoben)
- `get_daily_counter_deltas_by_inv` — nutzt `BoundaryRange.for_day_total(datum)`
- `get_reaggregate_preview` — nutzt beide, je nach Zweck

### 3.4 Migration

- Bestehende `TagesEnergieProfil`-Zeilen mit `wp_starts_anzahl[h]` haben Forward-Werte, müssen auf Backward umgerechnet werden.
- Ansatz: einmaliger Migrations-Job — für jeden Tag mit `wp_starts_anzahl IS NOT NULL` die Slots aus aktuellen Snapshots neu rechnen via Backward-Pfad. Identisch zu „Vollbackfill für Counter-Felder".
- Migration läuft idempotent (gleiche Logik wie Reaggregate-Tag, nur über alle Tage).
- Forum-Banner: einmalig „Counter-Stundenwerte werden umgerechnet (Slot-Konvention vereinheitlicht). Tagessummen bleiben unverändert." analog #144-Release.

## 4. E2 — Tagesgesamt = Boundary-Differenz (HA-konform)

### 4.1 Semantische Trennung

In Backward-Konvention umfassen die 24 Hourly-Slots das Fenster **[Vortag-23:00, Heute-23:00)**:

```
Σ slot[h=0..23] = snap[23] − snap[-1] = Energie [Vortag-23, Heute-23)
```

HA-Tagesgesamt umfasst dagegen **[Heute-00:00, Folgetag-00:00)**:

```
Boundary-Diff = snap[24] − snap[0] = Energie [Heute-00, Folgetag-00)
```

Beide 24 Stunden, aber **um eine Stunde verschoben**. Σ-Slot ist nicht Tagesgesamt — das ist mathematische Konsequenz von Backward, kein Bug.

**Folge für Code:**
- **Tagesgesamt-Felder** (`TagesZusammenfassung.komponenten_starts`, alle `_kwh`-Felder): immer aus `BoundaryRange.for_day_total(datum)` ableiten.
- **Slot-Verteilung** (`TagesEnergieProfil[h].*`): immer aus `BoundaryRange.for_hourly_slots(datum)` ableiten.
- Beide Pfade sind **disjunkt** und dürfen sich semantisch unterscheiden.

### 4.2 Aktuelle Soll/Ist-Differenz

Heute ist es vermischt:

| Feld | Heute | Soll |
|---|---|---|
| `TagesZusammenfassung.komponenten_starts` | Boundary-Diff ✓ | Boundary-Diff ✓ (unverändert) |
| `TagesEnergieProfil[h].wp_starts_anzahl` | Σ-Vorgriff via Forward-Slots ✗ | Backward-Slots (P2 löst das automatisch) |
| `TagesZusammenfassung.komponenten_kwh` | Σ über `werte`-Dict aus Stunden-Bucket (nicht aus Snapshots!) — vermischt mit Leistungs-Mittelwerten | **Boundary-Diff aus Snapshots** (neu) — eigene Service-Funktion `get_komponenten_tageskwh()` |
| `TagesZusammenfassung.peak_*_kw` | Aus Leistungs-Mittelwerten (W-Integration) | unverändert (Peaks sind keine kWh-Frage) |

`komponenten_kwh` ist heute aus Stunden-Bucket-Mittelwerten × 1h gebaut (siehe [`energie_profil_service.py:329-334`](../eedc/backend/services/energie_profil_service.py)) — ein W-Integrations-Pfad, keine Snapshot-Boundary-Diff. Bei lückenlosen Stunden ist das näherungsweise korrekt; bei Lücken weicht es ab. Umstellung auf Boundary-Diff aus `sensor_snapshots` macht es HA-konform und schließt Drift-Befund 2 für kWh-Felder gleich mit.

### 4.3 Daten-Checker-Konsistenz-Check

Optional in P3 mitnehmen: neuer Check `EP_HOURLY_DAY_DRIFT` im [`services/daten_checker.py`](../eedc/backend/services/daten_checker.py):

```
Σ slot[h=1..23] + (snap[24] − snap[23])  vs.  Boundary-Diff (snap[24] − snap[0])

Wenn |Δ| > 0.5 % UND alle 24 Slots gefüllt:
    → Anomalie "EP_HOURLY_DAY_DRIFT" für (anlage_id, datum, kategorie)
```

Bei lückenlosen Snapshots ist das mathematisch identisch. Anomalie schlägt nur an, wenn Daten inkonsistent geschrieben wurden — echter Bug-Indikator. UI-Behandlung: nur Hinweis, kein Quittier-Knopf (gemäß interner Konvention für den Daten-Checker).

## 5. E3 — `quelle`-Spalte auf `sensor_snapshots`

### 5.1 Schema-Erweiterung

```python
# eedc/backend/models/sensor_snapshot.py
class SensorSnapshot(Base):
    # ... bestehend
    quelle: Mapped[str | None] = mapped_column(
        String(20), nullable=True,
        comment="Schreib-Pfad: ha_statistics | mqtt_inbound | mqtt_live | live_fallback | unknown"
    )
```

Migration in [`core/database.py`](../eedc/backend/core/database.py) (analog `sfml_prognose_kwh`-Migration):
1. `ALTER TABLE sensor_snapshots ADD COLUMN quelle VARCHAR(20)`
2. Bestehende Zeilen erhalten `quelle = 'unknown'` (Initial-Backfill, eine UPDATE-Statement).

### 5.2 Schreiber setzen den Marker

| Schreiber | Konstante | Anmerkung |
|---|---|---|
| `snapshot_anlage` (HA-Stats) | `"ha_statistics"` | Default-Pfad für Add-on |
| `snapshot_anlage_5min` | `"ha_statistics"` | gleicher Pfad, 5-Min-Auflösung |
| `resnap_anlage_range` | `"ha_statistics"` (force) | Recovery, gleiche Quelle |
| `live_snapshot_if_missing` | `"mqtt_live"` | nur Standalone-Pfad |
| MQTT-Inbound-Service | `"mqtt_inbound"` | indirekter Schreib-Pfad |
| Fallback bei HA-None + MQTT-Fallback aktiv | `"live_fallback"` | siehe `_categorize_counter`-Pfad |

Konstanten-Definition in einem neuen `backend/services/snapshot/source.py`:

```python
class SnapshotSource:
    HA_STATISTICS = "ha_statistics"
    MQTT_INBOUND = "mqtt_inbound"
    MQTT_LIVE = "mqtt_live"
    LIVE_FALLBACK = "live_fallback"
    UNKNOWN = "unknown"

ALL = {HA_STATISTICS, MQTT_INBOUND, MQTT_LIVE, LIVE_FALLBACK, UNKNOWN}
```

`_upsert_snapshot` ([`sensor_snapshot_service.py:261`](../eedc/backend/services/sensor_snapshot_service.py)) bekommt zusätzlichen `quelle`-Parameter; alle Aufrufer setzen ihn explizit.

### 5.3 Diagnose-Funktion

Read-Helper in `services/snapshot/diagnose.py`:

```python
async def get_snapshot_source_distribution(
    db: AsyncSession, anlage_id: int, von: date, bis: date,
) -> dict[str, int]:
    """Liefert {quelle: count} pro Anlage und Zeitraum — für Datenverwaltung-UI."""
```

Frontend zeigt die Verteilung in der Datenverwaltung-Seite als kleine Statistik („87 % HA-Native, 13 % MQTT-Fallback in den letzten 30 Tagen") — Diagnose-Hilfe ohne Aktions-Pflicht.

### 5.4 Schablone für 3d

[`KONZEPT-DATENPIPELINE.md`](KONZEPT-DATENPIPELINE.md) Päckchen 1 generalisiert das Pattern auf vier Aggregat-Tabellen mit Per-Feld-Provenance (JSON-Spalte `source_provenance` + Append-Only `data_provenance_log`). 3c liefert dafür:

- die Erfahrung mit Migration einer existierenden Tabelle auf einen Source-Marker,
- den Pattern „dünner Marker reicht, wenn die Tabelle konzeptionell ein Datenfeld pro Zeile hat",
- den Aufrufer-Disziplin-Test (alle Schreiber gehen über einen typed `_upsert`-Helper, kein direkter ORM-INSERT).

## 6. E4 — UI-Trennung Resnap vs. Reaggregat

### 6.1 Backend-Status quo (v3.26.6)

`POST /reaggregate-tag?mit_resnap=true|false` ist semantisch ausreichend — Frontend wählt den Pfad. Auto-Erkennung „alt=neu → mit_resnap=False" ist sinnvoll als Default (reduziert HA-Stats-Last für triviale Fälle), wird in P4 als „Empfehlung" sichtbar gemacht statt automatisch unsichtbar zu schalten.

### 6.2 Frontend-Erweiterung

`ReaggregatePreviewModal.tsx` bekommt:

- **Zwei Apply-Buttons** statt einem:
  - **„Aus HA neu laden + neu rechnen"** (Default, `mit_resnap=true`)
  - **„Nur neu rechnen"** (`mit_resnap=false`) — disabled mit Tooltip „keine Änderungen in Snapshots gefunden", wenn alt-/neu-Vergleich identisch
- **AbortController** mit `useRef`, der in `onClose` gefeuert wird — bricht laufenden Fetch sauber ab
- **Modal-X im Apply-Zustand klickbar nach 30s applying-Dauer**, mit Hinweis „Backend läuft im Hintergrund weiter — bitte später Vorschau erneut öffnen, um Endzustand zu prüfen"
- **Sichtbare Restzeit-Schätzung** während des Resnap-Calls (basierend auf #stunden im Range × empirischem Mittel ~200 ms/Stunde) — Diagnose-Hilfe für Hänger

Das Backend bleibt unverändert; alle Items sind Frontend-only.

## 7. Modul-Refactoring (Vertical Slicing)

### 7.1 Pattern (analog [`KONZEPT-DATENPIPELINE.md`](KONZEPT-DATENPIPELINE.md) Sektion 7)

`services/sensor_snapshot_service.py` (1530) und `services/energie_profil_service.py:aggregate_day` (innerhalb 1621) werden **vor** den Architektur-Eingriffen in Verantwortlichkeits-Slices zerlegt. Pattern:

- `services/snapshot/` als Package mit Re-Export-Fassade in `__init__.py`. Bestehende Importer (`from backend.services.sensor_snapshot_service import X`) bleiben funktionsfähig, weil das Modul-File durch ein Stub-Re-Export ersetzt wird.
- Slice-Schnitt nach realer Verantwortlichkeit, die heute schon im File existiert. Keine spekulativen Slices.

### 7.2 Zerlegungs-Plan

| Heute | Soll-Struktur | Zugeordnet zu |
|---|---|---|
| `services/sensor_snapshot_service.py` (1530) | `services/snapshot/writer.py` (Snapshot-Schreiben pro Sensor + `_upsert_snapshot` mit `quelle`-Marker), `services/snapshot/aggregator.py` (Snapshots → Hourly + Tagesgesamt + BoundaryRange-Konsumenten), `services/snapshot/fallback.py` (HA → MQTT-Fallback-Logik, MQTT-Live-Snapshot), `services/snapshot/reaggregator.py` (`get_reaggregate_preview` + `resnap_anlage_range`), `services/snapshot/backfill.py` (Backfill aus Long-Term-Statistics), `services/snapshot/source.py` (E3-Konstanten), `services/snapshot/boundary_range.py` (E1-Klasse), `services/snapshot/diagnose.py` (E3-Read-Helper), `__init__.py` Re-Export | P1 (Zerlegung), P2+E1+E3 integrieren in die jeweiligen Slices |
| `services/energie_profil_service.py:aggregate_day` (innerhalb 1621) | `services/energie_profil/aggregator.py` (E2-Trennung Tagesgesamt vs. Slot-Verteilung; nutzt `BoundaryRange` aus snapshot-Package) | P3 |

`services/energie_profil_service.py` als Ganzes wird in dieser Etappe **nicht** vollständig zerlegt — nur die `aggregate_day`-Funktion (P3-relevant). Die Zerlegung in `aggregator.py / backfill.py / reader.py / reaggregator.py` ist Teil von [`KONZEPT-DATENPIPELINE.md`](KONZEPT-DATENPIPELINE.md) Päckchen 3 (Konflikt-Resolver).

### 7.3 Refactoring-Disziplin

- **Pro Päckchen:** Refactoring-PR landet **vor** der Architektur-Integration (zwei distincte Commits).
- **Verhalten unverändert:** Refactoring-PR ist reines Verschieben + Re-Export, alle Tests grün, kein Verhaltens-Diff. CI-Smoke + manueller Round-Trip in HA-Add-on.
- **Re-Export-Fassade testen:** Smoke-Test importiert alle bisherigen Symbol-Namen und prüft Aufrufbarkeit — schützt vor stillem Verlust eines Symbols.

## 8. Migrations-Roadmap

Reihenfolge: P1 → P2 → P3 → P4. P4 unabhängig, kann parallel zu P3 laufen.

### Päckchen 1 — Source-Marker auf SensorSnapshot (E3)

**Refactoring-Tail:**
- `services/sensor_snapshot_service.py` zerlegen (Sektion 7.2). Re-Export-Fassade in `__init__.py`. Smoke-Test für Symbol-Aufrufbarkeit.

**Architektur-Integration:**
- Migration: `quelle VARCHAR(20)` auf `sensor_snapshots` + Backfill `'unknown'` für bestehende Zeilen.
- `services/snapshot/source.py` mit Konstanten + ALLOWED-Set + Validation.
- `_upsert_snapshot` (in `writer.py`) bekommt Pflicht-Parameter `quelle`. Alle Aufrufer setzen ihn (siehe Sektion 5.2).
- `services/snapshot/diagnose.py` mit `get_snapshot_source_distribution()`.
- Frontend Datenverwaltung-Seite zeigt Verteilung als kleine Stats-Box (optional in P1, alternativ P4).

**Akzeptanz:**
- Alle Tests grün, Schema migriert.
- Neue Snapshots haben gesetztes `quelle`-Feld (DB-Audit).
- Diagnose-Endpoint liefert sinnvolle Verteilung.
- Re-Export-Fassade: alle bisherigen Importe funktionieren.

### Päckchen 2 — Slot-Konvention vereinheitlichen auf Backward (E1)

**Refactoring-Tail:** keiner — `services/snapshot/` ist durch P1 schon zerlegt.

**Architektur-Integration:**
- `services/snapshot/boundary_range.py`: typed `BoundaryRange`-Klasse mit `for_hourly_slots()` und `for_day_total()` (Sektion 3.3).
- `get_hourly_counter_sum_by_feld` von Forward auf Backward umstellen (Range `-1..23`, Slot `snap[h] − snap[h-1]`). Konsumiert `BoundaryRange.for_hourly_slots()`.
- `get_hourly_kwh_by_category` ebenfalls auf `BoundaryRange.for_hourly_slots()` umbauen — Verhalten identisch, aber via typed Range statt inline-Schleife.
- Counter-Migrations-Job: alle bestehenden `TagesEnergieProfil[h].wp_starts_anzahl` aus aktuellen Snapshots neu rechnen (Backward). Idempotent.
- v3.26.6's Resnap-Range-Erweiterung (`bis_dt = tag_start + 25h`) bleibt — schadet nicht, schützt 5-Min-Slots.
- Inline-Kommentar in [`routes/energie_profil.py:1168-1171`](../eedc/backend/api/routes/energie_profil.py) entfernen / aktualisieren (beschreibt nicht mehr die Realität).
- Forum-/Release-Banner: „Counter-Stundenwerte umgestellt auf Backward (#144-konform). Tagessummen unverändert."

**Akzeptanz:**
- `get_hourly_counter_sum_by_feld` und `get_hourly_kwh_by_category` lesen identische Range.
- Counter-Migration: alle Tage mit `wp_starts_anzahl IS NOT NULL` neu gerechnet, keine Datenkollision.
- Stundenvergleich-Chart in Aussichten zeigt OM/SC/IST/Counter unter konsistenten Slot-Labels.

### Päckchen 3 — Tagesgesamt = Boundary-Differenz (E2)

**Refactoring-Tail:**
- `aggregate_day` aus [`services/energie_profil_service.py`](../eedc/backend/services/energie_profil_service.py) in `services/energie_profil/aggregator.py` extrahieren. Re-Export im Modul-File. Smoke-Test wie P1.

**Architektur-Integration:**
- Neuer Read-Helper `services/snapshot/aggregator.py:get_komponenten_tageskwh(anlage, datum)` — Boundary-Diff pro Komponenten-Key aus `sensor_snapshots`.
- `aggregate_day` schreibt `TagesZusammenfassung.komponenten_kwh` aus diesem Helper, **nicht** aus Stunden-Bucket-Σ. Stunden-Bucket-Σ wird gleichzeitig in `TagesEnergieProfil[h].komponenten` (Slot-Verteilung) geschrieben — verschiedene Quelle, verschiedener Zweck.
- `komponenten_starts` bleibt unverändert (war schon Boundary-Diff).
- Daten-Checker `EP_HOURLY_DAY_DRIFT` (Sektion 4.3) als optionaler Zusatz — kann in einem späteren Patch nachgereicht werden, wenn der reine E2-Schnitt sauber läuft.
- Vollbackfill-Pfad ([`routes/energie_profil.py:1230`](../eedc/backend/api/routes/energie_profil.py)) prüfen: schreibt heute Σ-aus-Stunden-Bucket. Auch hier auf Boundary-Diff umstellen, damit historische Tagesgesamt HA-konform werden.
- Eine Daten-Sanierung historischer `komponenten_kwh` ist optional — kann via Reaggregate-Tag pro Tag durchgeführt werden, kein zwangsläufiger Migrations-Lauf.

**Akzeptanz:**
- Tagesgesamt-Vergleich EEDC ↔ HA Energy Dashboard: Δ < 0,1 % bei lückenlosen Snapshots.
- Bei künstlich erzeugten Snapshot-Lücken: Tagesgesamt bleibt korrekt (Boundary-Diff stabil), Slot-Σ reflektiert Lücken sichtbar.

### Päckchen 4 — Frontend-UX (E4)

**Refactoring-Tail:** keiner (Frontend).

**Architektur-Integration:**
- `ReaggregatePreviewModal.tsx`: zwei Apply-Buttons (Sektion 6.2), AbortController, Modal-X-Re-Aktivierung nach 30 s applying.
- Sichtbare Restzeit-Schätzung im Resnap-Pfad.
- Hinweistext: „EEDC erkennt automatisch, dass keine Snapshot-Änderungen vorliegen, und empfiehlt 'Nur neu rechnen'." statt unsichtbarer Auto-Switch.

**Akzeptanz:**
- User kann Resnap-Call mit Modal-Schließen abbrechen — Spinner endet sofort, kein Browser-Reload.
- Lange Resnap-Hänger zeigen eine sichtbare Restzeit, Modal-X wird nach 30 s wieder aktiv.
- Auto-Erkennung „alt=neu" ist als Empfehlung sichtbar, nicht als unsichtbarer Bypass.

## 9. Verhältnis zu anderen Konzepten

[`KONZEPT-DATENPIPELINE.md`](KONZEPT-DATENPIPELINE.md) Etappe 3d setzt auf 3c auf — Päckchen 1 dort baut auf der Source-Marker-Erfahrung aus 3c-Päckchen-1, generalisiert das Pattern auf vier Aggregat-Tabellen mit Per-Feld-Provenance. Der hier gewählte VARCHAR-Marker ist nicht Limitierung, sondern bewusst minimaler Schnitt.

[`KONZEPT-PROGNOSEQUELLEN-WAHL.md`](KONZEPT-PROGNOSEQUELLEN-WAHL.md) ist disjunkt — betrifft Lese-Resolver pro Anlage über drei Prognose-Quellen, kein Berührungspunkt zu Slot-Konvention oder Snapshot-Marker.

[`KONZEPT-LIVE-SNAPSHOT-5MIN.md`](KONZEPT-LIVE-SNAPSHOT-5MIN.md) Phase-1-Frontend bleibt parallel offen — die `live_tagesverlauf_service`-Umstellung auf 5-Min-Counter-Snapshots nutzt dasselbe `sensor_snapshots`-Schema, profitiert in P1 vom Source-Marker (5-Min-Slots werden als `ha_statistics` markiert), aber ist semantisch eigenständig.

[`KONZEPT-KORREKTURPROFIL.md`](KONZEPT-KORREKTURPROFIL.md) und [`KONZEPT-MQTT-GATEWAY.md`](KONZEPT-MQTT-GATEWAY.md) sind unabhängig.

[Issue #144](https://github.com/supernova1963/eedc-homeassistant/issues/144) ist die Source-of-Truth für die Slot-Konvention — diese Etappe vollendet die in #144 begonnene Vereinheitlichung um den Counter-Pfad und um die typisierte Helper-Klasse.
