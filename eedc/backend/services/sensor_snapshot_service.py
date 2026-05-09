"""
Sensor Snapshot Service (Issue #135) — Re-Export-Fassade.

Logik wurde 2026-05-09 (Etappe 3c Päckchen 1) in das `backend.services.snapshot`-
Package zerlegt. Bestehende Importer können weiterhin diesen Modul-Pfad
verwenden, neue Code-Stellen sollten direkt aus `backend.services.snapshot`
oder den jeweiligen Slices importieren.

Sensor-Key-Schema:
    "basis:einspeisung", "basis:netzbezug"
    "inv:<inv_id>:<feld>"  (z.B. "inv:4:pv_erzeugung_kwh", "inv:5:ladung_kwh")
"""

from backend.services.snapshot import (  # noqa: F401  (Re-Export)
    BASIS_ZAEHLER_FELDER,
    KUMULATIVE_COUNTER_FELDER,
    KUMULATIVE_ZAEHLER_FELDER,
    cleanup_5min_snapshots,
    delta,
    get_counter_lifetime,
    get_daily_counter_deltas_by_inv,
    get_hourly_counter_sum_by_feld,
    get_hourly_kwh_by_category,
    get_reaggregate_preview,
    get_snapshot,
    live_snapshot_if_missing,
    resnap_anlage_range,
    snapshot_anlage,
    snapshot_anlage_5min,
)

__all__ = [
    "BASIS_ZAEHLER_FELDER",
    "KUMULATIVE_COUNTER_FELDER",
    "KUMULATIVE_ZAEHLER_FELDER",
    "cleanup_5min_snapshots",
    "delta",
    "get_counter_lifetime",
    "get_daily_counter_deltas_by_inv",
    "get_hourly_counter_sum_by_feld",
    "get_hourly_kwh_by_category",
    "get_reaggregate_preview",
    "get_snapshot",
    "live_snapshot_if_missing",
    "resnap_anlage_range",
    "snapshot_anlage",
    "snapshot_anlage_5min",
]
