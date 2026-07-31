"""
Cockpit Package — aggregiert alle Sub-Router.

main.py importiert `cockpit.router` — dieses Package stellt denselben
Router wie das frühere cockpit.py bereit, nun aufgeteilt in Module.

`social.py` (kopierfertiger Social-Media-Monatstext) ist am 2026-07-31
**zurückgebaut** worden: die auslösende Oberfläche — Teilen-Symbol und
`ShareTextModal` — ist mit dem IA-V4-Flip entfallen, der Endpoint hatte
seither keinen Konsumenten mehr und wird nicht wieder eingeführt
(Entscheid Gernot). Nicht zu verwechseln mit dem **Community-Teilen**
(`api/routes/community.py`) — das ist eine andere Funktion und bleibt.
"""

from fastapi import APIRouter

from backend.api.routes.cockpit.uebersicht import router as uebersicht_router
from backend.api.routes.cockpit.prognose import router as prognose_router
from backend.api.routes.cockpit.nachhaltigkeit import router as nachhaltigkeit_router
from backend.api.routes.cockpit.komponenten import router as komponenten_router
from backend.api.routes.cockpit.pv_strings import router as pv_strings_router

router = APIRouter()
router.include_router(uebersicht_router)
router.include_router(prognose_router)
router.include_router(nachhaltigkeit_router)
router.include_router(komponenten_router)
router.include_router(pv_strings_router)
