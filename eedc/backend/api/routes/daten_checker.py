"""
Daten-Checker API Route.

Endpoint für Datenqualitäts-Prüfung aller Anlage-Daten.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.antwort import (  # noqa: F401 — Modelle hier weiter importierbar
    AktionResponse,
    CheckErgebnisResponse,
    DatenCheckResponse,
    GruppeResponse,
    MonatsdatenAbdeckungResponse,
    NichtAusfuehrbarResponse,
    ZielResponse,
    checker_antwort,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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

    return checker_antwort(result)


@router.get("/diagnose-paket/{anlage_id}/bereitstellen")
async def diagnose_paket_bereitstellen(anlage_id: int):
    """
    Diagnose-Paket v4 einer Anlage bereitstellen (Konzept E9, Variante A synchron) — nur lesend.

    Baut die ZIP-Datei in die Ablage und antwortet mit Marke, Dateiname, Größe, `gueltig_s`, Versandweg, Inhaltsliste und
    Teilfehlern; heruntergeladen wird mit `GET /diagnose-paket/{anlage_id}?marke=…`. GET, weil die Einstellungs-Sperre nach
    Methode greift — ein Paket muss auch bei gesetzter PIN entstehen. Zugangsdaten enthält es nie (W-7).
    """
    from backend.services.diagnose_paket.bereinigung import bereinige_log
    from backend.services.diagnose_paket.paket import bereitstellen

    try:
        return await bereitstellen(anlage_id)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:  # noqa: BLE001 — G5: Fehlertext im Dialog, keine Datei
        logger.warning("Diagnose-Paket Anlage %s: %s", anlage_id, type(e).__name__, exc_info=True)
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {bereinige_log(str(e))}")


@router.get("/diagnose-paket/{anlage_id}")
async def diagnose_paket(
    anlage_id: int,
    marke: str = Query("", description="Marke aus `…/bereitstellen`"),
    pruefen: bool = Query(False, description="nur prüfen: 204 gültig, 404 sonst (ohne Body)"),
):
    """
    Das bereitgestellte Diagnose-Paket herunterladen (`application/zip`, Anhang). Marke falsch, abgelaufen (15 Minuten),
    ersetzt oder Anlage unbekannt ⇒ 404. Die Marke gilt mehrfach bis zum Ablauf; die Datei bleibt beim Herunterladen stehen.
    """
    from backend.services.diagnose_paket import ablage

    eintrag = ablage.gueltig(anlage_id, marke)
    if eintrag is None:
        raise HTTPException(status_code=404, detail="Diagnose-Paket nicht (mehr) bereit")
    if pruefen:
        return Response(status_code=204)
    return FileResponse(eintrag.pfad, media_type="application/zip", filename=eintrag.dateiname)
