"""
Custom-Import API — aggregierter Router.

Vor dem 3d-Etappenabschluss-Refactor lebte der Endpoint-Bestand in einer
einzigen `routes/custom_import.py`. Im Rahmen des Aufräum-Sprints
(Konzept-Doc Sektion 7.4) zerlegt in vier Verantwortlichkeits-Slices:

  - analyze.py   → POST /analyze + GET /fields (Datei-Inspektion,
                   Auto-Mapping, Investitions-Spalten-Erkennung)
  - preview.py   → POST /preview (Mapping-Anwendung ohne DB-Schreibung)
  - apply.py     → POST /apply/{anlage_id} (Provenance-Schreib-Pfad
                   via services/import_writer.py)
  - templates.py → GET/POST/DELETE /templates[/<name>]

Externer Zugriffspfad bleibt unverändert: `from backend.api.routes
import custom_import` plus `custom_import.router`. main.py:334
unangetastet — Endpoints weiterhin unter /api/custom-import/...
"""

from fastapi import APIRouter

from .analyze import router as _analyze_router
from .apply import router as _apply_router
from .preview import router as _preview_router
from .templates import router as _templates_router

router = APIRouter()
router.include_router(_analyze_router)
router.include_router(_preview_router)
router.include_router(_apply_router)
router.include_router(_templates_router)

__all__ = ["router"]
