"""
Import/Export API Routes

Modulare Struktur für Import/Export-Operationen:
- csv_operations: CSV Import/Export/Template
- json_operations: JSON Import/Export (vollständige Anlage)
- demo_data: Demo-Daten Erstellung/Löschung
- schemas: Pydantic-Modelle
- helpers: Gemeinsame Hilfsfunktionen
"""

from fastapi import APIRouter

from .csv_operations import router as csv_router
from .json_operations import router as json_router
from .demo_data import router as demo_router

# Re-export schemas for backwards compatibility
from .schemas import (
    ImportResult,
    JSONImportResult,
    DemoDataResult,
    CSVTemplateInfo,
)

# Kombinierter Router
router = APIRouter()

# CSV-Operationen (Template, Import, Export)
router.include_router(csv_router)

# JSON-Operationen (Full Export, Import)
router.include_router(json_router)

# Demo-Daten
router.include_router(demo_router)

__all__ = [
    "router",
    "ImportResult",
    "JSONImportResult",
    "DemoDataResult",
    "CSVTemplateInfo",
]
