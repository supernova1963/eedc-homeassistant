"""
Energie-Profil-Service Backbone — Re-Export-Fassade.

Die eigentlichen Schreib-Pfade leben in `services/energie_profil/`:
- `aggregate_day` (Etappe 3c P3) — Tag-Aggregator aus Snapshots/Live-Daten
- `rollup_month` (Etappe 3d P3) — Monats-Aggregation in Monatsdaten
- `backfill_range` / `backfill_from_statistics` /
  `resolve_and_backfill_from_statistics` (Etappe 3d P3) — Vollbackfill aus
  HA Long-Term Statistics
- `aggregate_yesterday_all` / `aggregate_today_all` (Etappe 3d P3) —
  Scheduler-Wrapper

Geteilte Helper (Wetter-IST, SoC-History, Strompreis-Stunden, `_tage_zurueck`,
`StrompreisStunden`-Datenklasse) wurden im 3d-Etappenabschluss-Tail (2026-05-10)
in `services/energie_profil/_helpers.py` ausgelagert.

Diese Datei bleibt erhalten, damit bestehende externe Importer
(`routes/energie_profil/*`, `services/repair_orchestrator.py`,
`services/scheduler.py`) unverändert weiterlaufen.
"""

from backend.services.energie_profil.aggregator import aggregate_day  # noqa: F401
from backend.services.energie_profil.backfill import (  # noqa: F401
    BackfillResult,
    BackfillStatus,
    backfill_from_statistics,
    backfill_range,
    resolve_and_backfill_from_statistics,
)
from backend.services.energie_profil.rollup import rollup_month  # noqa: F401
from backend.services.energie_profil.scheduler_jobs import (  # noqa: F401
    aggregate_today_all,
    aggregate_yesterday_all,
)

# Helper-Re-Exports für rückwärtskompatible Importer (kein Treffer im aktuellen
# Code-Stand, aber günstig zu pflegen falls externer Konsument lazy importiert).
from backend.services.energie_profil._helpers import (  # noqa: F401
    StrompreisStunden,
    _get_soc_history,
    _get_strompreis_stunden,
    _get_wetter_ist,
    _tage_zurueck,
)
