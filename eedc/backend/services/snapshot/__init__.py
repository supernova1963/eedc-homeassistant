"""
Snapshot-Subsystem (Issue #135).

Bündelt alle Module rund um SensorSnapshot-Tabelle: Schreib-Jobs, Read mit
Self-Healing, Hourly-/Tagesgesamt-Aggregation, MQTT-Live-Fallback und
Reaggregate/Resnap-Pfad. Zerlegung aus dem ehemaligen Monster-File
`sensor_snapshot_service.py` (1530 Zeilen) im Rahmen Etappe 3c P1.

Importe von außen können entweder direkt aus den Slices oder aus diesem
Package kommen — der ältere Pfad `backend.services.sensor_snapshot_service`
bleibt als Re-Export-Fassade ebenfalls funktionsfähig.

Slice-Struktur:
- `keys.py`         — Konstanten (KUMULATIVE_*, BASIS_*) + Key-Mapping-Helper
- `writer.py`       — _upsert_snapshot, snapshot_anlage, snapshot_anlage_5min,
                      cleanup_5min_snapshots
- `reader.py`       — get_snapshot (Self-Healing-Read), delta, get_counter_lifetime
- `aggregator.py`   — get_hourly_kwh_by_category, get_hourly_counter_sum_by_feld,
                      get_daily_counter_deltas_by_inv
- `fallback.py`     — live_snapshot_if_missing (MQTT-Live-Pfad)
- `reaggregator.py` — get_reaggregate_preview, resnap_anlage_range
- `source.py`       — SnapshotSource-Konstanten + Validation (Etappe 3c P1, E3)
- `diagnose.py`     — get_snapshot_source_distribution (Read-Helper für UI)
- `boundary_range.py` — typed Snapshot-Boundary-Range nach #144 (Etappe 3c P2, E1)
- `migrate.py`      — einmalige Daten-Migrationen (Etappe 3c P2)
"""

from backend.services.snapshot.keys import (
    BASIS_ZAEHLER_FELDER,
    KUMULATIVE_COUNTER_FELDER,
    KUMULATIVE_ZAEHLER_FELDER,
)
from backend.services.snapshot.writer import (
    cleanup_5min_snapshots,
    snapshot_anlage,
    snapshot_anlage_5min,
)
from backend.services.snapshot.reader import (
    delta,
    get_counter_lifetime,
    get_snapshot,
)
from backend.services.snapshot.aggregator import (
    get_daily_counter_deltas_by_inv,
    get_hourly_counter_sum_by_feld,
    get_hourly_kwh_by_category,
    get_komponenten_tageskwh,
)
from backend.services.snapshot.fallback import live_snapshot_if_missing
from backend.services.snapshot.reaggregator import (
    get_reaggregate_preview,
    resnap_anlage_range,
)
from backend.services.snapshot.source import (
    ALL_SOURCES,
    SnapshotSource,
    assert_valid_source,
)
from backend.services.snapshot.diagnose import (
    get_snapshot_source_distribution,
    get_snapshot_source_distribution_recent,
)
from backend.services.snapshot.boundary_range import BoundaryRange

__all__ = [
    # Konstanten
    "BASIS_ZAEHLER_FELDER",
    "KUMULATIVE_COUNTER_FELDER",
    "KUMULATIVE_ZAEHLER_FELDER",
    # Writer
    "cleanup_5min_snapshots",
    "snapshot_anlage",
    "snapshot_anlage_5min",
    # Reader
    "delta",
    "get_counter_lifetime",
    "get_snapshot",
    # Aggregator
    "get_daily_counter_deltas_by_inv",
    "get_hourly_counter_sum_by_feld",
    "get_hourly_kwh_by_category",
    "get_komponenten_tageskwh",
    # Fallback
    "live_snapshot_if_missing",
    # Reaggregator
    "get_reaggregate_preview",
    "resnap_anlage_range",
    # Source-Marker (E3)
    "ALL_SOURCES",
    "SnapshotSource",
    "assert_valid_source",
    "get_snapshot_source_distribution",
    "get_snapshot_source_distribution_recent",
    # BoundaryRange (E1)
    "BoundaryRange",
]
