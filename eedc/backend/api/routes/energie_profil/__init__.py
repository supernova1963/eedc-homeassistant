"""
Energie-Profil API — aggregierter Router.

Vor v3.27 lebte der gesamte Endpoint-Bestand in einer einzigen
`routes/energie_profil.py`. Im Zuge der Etappe-3d-Päckchen-4-Refactor-Tail
wurde der File in zwei Verantwortlichkeits-Slices zerlegt:

  - views.py  → Read-Endpoints (tage / stunden / monat /
                debug-rohdaten / verfuegbare-monate / stats /
                reaggregate-tag/preview / kraftstoffpreis-status / tagesprognose)
  - repair.py → Repair- / Write-Endpoints (delete-rohdaten,
                reaggregate-heute, reaggregate-tag, vollbackfill,
                kraftstoffpreis-backfill[/tages|/monats], delete-alle-rohdaten)

Externer Zugriffspfad bleibt unverändert: `from backend.api.routes import
energie_profil` plus `energie_profil.router`.
"""

from fastapi import APIRouter

from .repair import router as _repair_router
from .views import router as _views_router

router = APIRouter()
router.include_router(_views_router)
router.include_router(_repair_router)

__all__ = ["router"]
