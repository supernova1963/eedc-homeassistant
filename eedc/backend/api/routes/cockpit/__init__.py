"""
Cockpit Package — aggregiert alle Sub-Router.

main.py importiert `cockpit.router` — dieses Package stellt denselben
Router wie das frühere cockpit.py bereit, nun aufgeteilt in 6 Module.
"""

from fastapi import APIRouter

from backend.api.routes.cockpit.uebersicht import router as uebersicht_router
from backend.api.routes.cockpit.prognose import router as prognose_router
from backend.api.routes.cockpit.nachhaltigkeit import router as nachhaltigkeit_router
from backend.api.routes.cockpit.komponenten import router as komponenten_router
from backend.api.routes.cockpit.pv_strings import router as pv_strings_router
from backend.api.routes.cockpit.social import router as social_router

router = APIRouter()
router.include_router(uebersicht_router)
router.include_router(prognose_router)
router.include_router(nachhaltigkeit_router)
router.include_router(komponenten_router)
router.include_router(pv_strings_router)
router.include_router(social_router)
