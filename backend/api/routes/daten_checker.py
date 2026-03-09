"""
Daten-Checker API Route.

Endpoint für Datenqualitäts-Prüfung aller Anlage-Daten.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.services.daten_checker import DatenChecker

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================

class CheckErgebnisResponse(BaseModel):
    kategorie: str
    schwere: str
    meldung: str
    details: Optional[str] = None
    link: Optional[str] = None


class MonatsdatenAbdeckungResponse(BaseModel):
    vorhanden: int
    erwartet: int
    prozent: float


class DatenCheckResponse(BaseModel):
    anlage_id: int
    anlage_name: str
    ergebnisse: list[CheckErgebnisResponse]
    zusammenfassung: dict
    monatsdaten_abdeckung: Optional[MonatsdatenAbdeckungResponse] = None


# =============================================================================
# Endpoint
# =============================================================================

@router.get("/daten-check/{anlage_id}", response_model=DatenCheckResponse)
async def daten_check(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Prüft alle Daten einer Anlage auf Vollständigkeit und Plausibilität.

    Gibt eine kategorisierte Liste von Ergebnissen zurück mit den
    Schweregraden: error, warning, info, ok.
    """
    checker = DatenChecker(db)
    try:
        result = await checker.check_anlage(anlage_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return DatenCheckResponse(
        anlage_id=result.anlage_id,
        anlage_name=result.anlage_name,
        ergebnisse=[
            CheckErgebnisResponse(
                kategorie=e.kategorie,
                schwere=e.schwere,
                meldung=e.meldung,
                details=e.details,
                link=e.link,
            )
            for e in result.ergebnisse
        ],
        zusammenfassung=result.zusammenfassung,
        monatsdaten_abdeckung=MonatsdatenAbdeckungResponse(
            vorhanden=result.monatsdaten_abdeckung.vorhanden,
            erwartet=result.monatsdaten_abdeckung.erwartet,
            prozent=result.monatsdaten_abdeckung.prozent,
        ) if result.monatsdaten_abdeckung else None,
    )
