"""
Monatsabschluss API — aggregierter Router.

Vor dem 3d-Etappenabschluss-Refactor lebte der Endpoint-Bestand in einer
einzigen `routes/monatsabschluss.py`. Im Rahmen des Aufräum-Sprints
(Konzept-Doc Sektion 7.4) zerlegt in zwei Verantwortlichkeits-Slices:

  - views.py  → Read- und Vorschau-Endpoints (status, cloud-fetch,
                naechster, historie)
  - wizard.py → Save-Pfad mit Provenance-Resolver + Background-Task
                (MQTT-Publish, Auto-Aggregation, Community-Share)

Externer Zugriffspfad bleibt unverändert: `from backend.api.routes
import monatsabschluss` plus `monatsabschluss.router`. Der Aggregations-
Router führt das `prefix="/monatsabschluss"` weiter, damit `main.py:329`
unverändert bleibt (`app.include_router(monatsabschluss.router,
prefix="/api", tags=["Monatsabschluss"])` → Endpoints unter
`/api/monatsabschluss/...`).
"""

from fastapi import APIRouter

from .views import router as _views_router
from .wizard import router as _wizard_router

router = APIRouter(prefix="/monatsabschluss", tags=["Monatsabschluss"])
router.include_router(_views_router)
router.include_router(_wizard_router)

__all__ = ["router"]
