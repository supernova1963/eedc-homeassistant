"""
Daten-Checker API Route.

Endpoint für Datenqualitäts-Prüfung aller Anlage-Daten.
"""

import logging
from typing import Callable

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers
from starlette.types import Message, Receive, Scope, Send

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


class _DateiMitAbschluss(FileResponse):
    """``FileResponse``, die ``bei_abschluss`` erst ruft, wenn die Datei **ganz** gesendet ist (Abschluss-Meldung, Lab rc36).

    Ein Abbruch des Clients wirft nicht: uvicorn verwirft nach dem Verbindungsende jede weitere Sendung still, die Antwort
    liefe also scheinbar zu Ende (eine ``BackgroundTask`` zählte den Abbruch mit). Deshalb lauscht die Antwort neben dem
    Senden auf ``http.disconnect``: kommt er, bevor das letzte Stück übergeben ist, war es ein Abbruch und zählt nicht.
    Nur ein ganzer GET zählt — ein Kopf- oder Teilabruf (``Range``) ist keine vollständige Auslieferung. Grenze: «ganz
    gesendet» heißt an den Server übergeben; was danach in Puffern von Netz und Ingress liegt, sieht eedc nicht.
    """

    def __init__(self, *args, bei_abschluss: Callable[[], None], **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._bei_abschluss = bei_abschluss

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("method", "GET").upper() != "GET" or Headers(scope=scope).get("range") is not None:
            await super().__call__(scope, receive, send)
            return
        # Ohne ``pathsend`` sendet die Antwort selbst in Stücken — nur so ist das letzte Stück sichtbar.
        erweiterungen = {k: v for k, v in (scope.get("extensions") or {}).items() if k != "http.response.pathsend"}
        stand = {"letztes_stueck": False, "abgebrochen": False}

        async def senden(nachricht: Message) -> None:
            if nachricht["type"] == "http.response.body" and not nachricht.get("more_body", False):
                stand["letztes_stueck"] = True
            await send(nachricht)

        async def lauschen() -> None:
            try:
                while (await receive())["type"] != "http.disconnect":
                    pass
            except Exception:  # noqa: BLE001 — Empfang gestört: Ende unbekannt, zählt nicht; das Senden läuft weiter
                stand["abgebrochen"] = True
                return
            stand["abgebrochen"] = not stand["letztes_stueck"]

        fehler: Exception | None = None
        async with anyio.create_task_group() as gruppe:
            gruppe.start_soon(lauschen)
            try:
                await super().__call__({**scope, "extensions": erweiterungen}, receive, senden)
            except Exception as e:  # noqa: BLE001 — nach dem Schließen der Gruppe unverändert weiter (keine ExceptionGroup)
                fehler = e
            gruppe.cancel_scope.cancel()
        if fehler is not None:
            raise fehler
        if not stand["abgebrochen"]:
            self._bei_abschluss()


@router.get("/diagnose-paket/{anlage_id}")
async def diagnose_paket(
    anlage_id: int,
    marke: str = Query("", description="Marke aus `…/bereitstellen`"),
    pruefen: bool = Query(False, description="nur prüfen: 200 `{ausgeliefert}` gültig, 404 sonst"),
):
    """
    Das bereitgestellte Diagnose-Paket herunterladen (`application/zip`, Anhang). Marke falsch, abgelaufen (15 Minuten),
    ersetzt oder Anlage unbekannt ⇒ 404. Die Marke gilt mehrfach bis zum Ablauf; die Datei bleibt beim Herunterladen stehen.
    Mit `pruefen=1` nur der Prüfabruf: 200 mit `{"ausgeliefert": n}` — so oft wurde die Datei dieser Marke vollständig
    ausgeliefert (ein abgebrochener Abruf zählt nicht); der Dialog erkennt daran das Ende des Downloads.
    """
    from backend.services.diagnose_paket import ablage

    eintrag = ablage.gueltig(anlage_id, marke)
    if eintrag is None:
        raise HTTPException(status_code=404, detail="Diagnose-Paket nicht (mehr) bereit")
    if pruefen:
        return {"ausgeliefert": eintrag.ausgeliefert}
    return _DateiMitAbschluss(
        eintrag.pfad, media_type="application/zip", filename=eintrag.dateiname,
        bei_abschluss=lambda: ablage.zaehle_auslieferung(anlage_id, eintrag.marke),
    )
