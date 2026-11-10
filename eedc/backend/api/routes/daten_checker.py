"""
Daten-Checker API Route.

Endpoint für Datenqualitäts-Prüfung aller Anlage-Daten.
"""

import logging
import re
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
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
    # Etappe 6 v3.31.1 (Schema-Durchreichung in v3.31.2 nachgereicht):
    # optionale Inline-Reparatur-Action. Bestehende Kategorien lassen leer.
    action_kind: Optional[str] = None
    action_params: Optional[dict] = None
    action_label: Optional[str] = None
    # IA-V4 #243: Komponenten-Zuordnung für den Komponenten-Hub-Filter.
    investition_id: Optional[int] = None
    # E1 «Diagnose-Paket»: die Zahlen der Meldung strukturiert und der Befund-Schlüssel (optional, Altfelder unverändert).
    werte: Optional[dict] = None
    code: Optional[str] = None


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
                action_kind=e.action_kind,
                action_params=e.action_params,
                action_label=e.action_label,
                investition_id=e.investition_id,
                werte=e.werte,
                code=e.code,
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


_MONAT = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


@router.get("/diagnose-paket/{anlage_id}")
async def diagnose_paket(
    anlage_id: int,
    fassung: Literal["datei", "kopie"] = Query("datei"),
    monate: Optional[str] = Query(None, description="Monate der Tagesreihen, z. B. 2026-10,2026-09 (höchstens zwei)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Diagnose-Paket einer Anlage als Markdown (Etappe E1, Konzept Daten-Checker §8) — nur lesend.

    `fassung=datei` ungekürzt, `fassung=kopie` höchstens 20 KB (Kürzung steht im Kopf). Zugangsdaten enthält es nie.
    """
    from backend.services.diagnose_paket import baue_paket

    gewaehlt = None
    if monate:
        teile = [m.strip() for m in monate.split(",") if m.strip()]
        treffer = [_MONAT.match(m) for m in teile]
        if not all(treffer):
            raise HTTPException(status_code=422, detail="monate: Form JJJJ-MM, durch Komma getrennt")
        gewaehlt = [(int(t.group(1)), int(t.group(2))) for t in treffer]
    try:
        paket = await baue_paket(db, anlage_id, fassung=fassung, monate=gewaehlt)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return Response(
        content=paket.text,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{paket.dateiname}"'},
    )
