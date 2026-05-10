"""
Energie-Profil-Subsystem.

Aggregation eines Tages aus Snapshot-Boundaries + Tagesverlauf-Daten zur
TagesZusammenfassung + 24 TagesEnergieProfil-Zeilen, plus Monats-Rollup,
Vollbackfill aus HA Long-Term Statistics und Scheduler-Jobs.

Refactoring-Etappen:
- 3c P3 (v3.26.8): `aggregate_day` extrahiert (`aggregator.py`).
- 3d P3: `rollup_month`, `backfill_*`, `aggregate_yesterday_all` /
  `aggregate_today_all` extrahiert (`rollup.py`, `backfill.py`,
  `scheduler_jobs.py`).
- 3d-Etappenabschluss-Tail (2026-05-10): Internal helpers (`_get_wetter_ist`,
  `_get_soc_history`, `_get_strompreis_stunden`, `_tage_zurueck`,
  `StrompreisStunden`) in `_helpers.py` ausgelagert; das alte Modul
  `services/energie_profil_service.py` bleibt als Re-Export-Fassade erhalten.
"""

from backend.services.energie_profil.aggregator import aggregate_day
from backend.services.energie_profil.backfill import (
    BackfillResult,
    BackfillStatus,
    backfill_from_statistics,
    backfill_range,
    resolve_and_backfill_from_statistics,
)
from backend.services.energie_profil.rollup import rollup_month
from backend.services.energie_profil.scheduler_jobs import (
    aggregate_today_all,
    aggregate_yesterday_all,
)

__all__ = [
    "aggregate_day",
    "aggregate_today_all",
    "aggregate_yesterday_all",
    "backfill_from_statistics",
    "backfill_range",
    "BackfillResult",
    "BackfillStatus",
    "resolve_and_backfill_from_statistics",
    "rollup_month",
]
