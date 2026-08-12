"""
Investitionen API — Package.

main.py importiert `investitionen.router`; dieses Package stellt denselben
Router wie das frühere investitionen.py bereit, 2026-05-20 aufgeteilt in:
- crud.py       — CRUD-Endpoints, Schemas, ROI-Dashboard
- dashboards.py — Pro-Investitionstyp-Dashboards + Monatsdaten-Abfrage
- speicher_potential.py — „hätte mehr Kapazität geholfen?" (#358 Phase 2, Stundendaten)
- speicher_sizing.py    — „lohnt sich ein größerer Speicher?" (#358 Phase 3, Simulation)
"""

from fastapi import APIRouter

from backend.api.routes.investitionen.crud import router as crud_router
from backend.api.routes.investitionen.speicher_potential import (
    router as speicher_potential_router,
    get_speicher_potential,
)
from backend.api.routes.investitionen.speicher_sizing import (
    router as speicher_sizing_router,
    get_speicher_sizing,
)
from backend.api.routes.investitionen.dashboards import (
    router as dashboards_router,
    get_eauto_dashboard,
    get_waermepumpe_dashboard,
    get_speicher_dashboard,
    get_wallbox_dashboard,
    get_balkonkraftwerk_dashboard,
    get_sonstiges_dashboard,
    get_investition_monatsdaten_by_month,
)

router = APIRouter()
router.include_router(crud_router)
router.include_router(dashboards_router)
router.include_router(speicher_potential_router)
router.include_router(speicher_sizing_router)

__all__ = [
    "router",
    "get_eauto_dashboard",
    "get_waermepumpe_dashboard",
    "get_speicher_dashboard",
    "get_wallbox_dashboard",
    "get_balkonkraftwerk_dashboard",
    "get_sonstiges_dashboard",
    "get_investition_monatsdaten_by_month",
    "get_speicher_potential",
    "get_speicher_sizing",
]
