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

class ZielResponse(BaseModel):
    """E2: Sprung-Ziel eines Befunds (`services/daten_checker/ziele.py`); den Pfad bildet der Client (`lib/zielPfad.ts`, Wächter W-5)."""
    bereich: str
    block: Optional[str] = None
    params: dict = {}
    anker: Optional[str] = None


class AktionResponse(BaseModel):
    """E2: Inline-Handgriff eines Befunds. E3: Plan/Execute-Form (`operation` = Reparatur-Operation, `params` =
    Plan-Parameter); `label` ist der Knopf-Text aus dem Katalog (= `knopf` des Befunds)."""
    operation: str
    params: dict
    label: str


class GruppeResponse(BaseModel):
    """E5 V2: Gruppenzeile eines Befunds (`services/daten_checker/gruppen.py`) — gleiche `schluessel` = eine Zeile."""
    schluessel: str
    titel: str
    glied: str
    weitere: int = 0
    details: Optional[str] = None


class CheckErgebnisResponse(BaseModel):
    """Ein Befund. Seit E5 ohne die Altfelder `link`/`action_*` (Wächter W-3): der Handgriff steht in `ziel` (Sprung)
    bzw. `action` (Aktion), der Knopf-Text aller Klassen in `knopf` (E5.7 L1)."""
    kategorie: str
    schwere: str
    meldung: str
    details: Optional[str] = None
    # IA-V4 #243: Komponenten-Zuordnung für den Komponenten-Hub-Filter.
    investition_id: Optional[int] = None
    # E1 «Diagnose-Paket»: die Zahlen der Meldung strukturiert und der Befund-Schlüssel.
    werte: Optional[dict] = None
    code: Optional[str] = None
    # E2 (Befund-Schlüssel, Ziel-Bauer): Sprung-Ziel bzw. Aktion (Plan/Execute-Form seit E3).
    ziel: Optional[ZielResponse] = None
    action: Optional[AktionResponse] = None
    knopf: Optional[str] = None
    gruppe: Optional[GruppeResponse] = None


class NichtAusfuehrbarResponse(BaseModel):
    """E5 V4: eine Prüfung, die in dieser Installation nicht laufen kann."""
    pruefung: str
    grund: str


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
    nicht_ausfuehrbar: list[NichtAusfuehrbarResponse] = []


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
                investition_id=e.investition_id,
                werte=e.werte,
                code=e.code,
                ziel=ZielResponse(**vars(e.ziel)) if e.ziel else None,
                action=AktionResponse(**vars(e.action), label=e.knopf) if e.action else None,
                knopf=e.knopf,
                gruppe=GruppeResponse(**vars(e.gruppe)) if e.gruppe else None,
            )
            for e in result.ergebnisse
        ],
        zusammenfassung=result.zusammenfassung,
        monatsdaten_abdeckung=MonatsdatenAbdeckungResponse(
            vorhanden=result.monatsdaten_abdeckung.vorhanden,
            erwartet=result.monatsdaten_abdeckung.erwartet,
            prozent=result.monatsdaten_abdeckung.prozent,
        ) if result.monatsdaten_abdeckung else None,
        nicht_ausfuehrbar=[NichtAusfuehrbarResponse(**n) for n in result.nicht_ausfuehrbar],
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
