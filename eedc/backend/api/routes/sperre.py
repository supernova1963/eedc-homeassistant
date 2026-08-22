"""
Einstellungs-Sperre — Status, Entsperren, Sperren, PIN verwalten.

Fachliche Begründung und Abgrenzung stehen in ``core/sperre.py``. Hier nur die
Besonderheit der Routen: **Nur ``/entsperren`` und ``/sperren`` sind von der Middleware
ausgenommen.** Das Setzen, Ändern und Entfernen der PIN läuft bewusst *durch* sie —
solange keine PIN gesetzt ist, greift sie ohnehin nicht (jeder darf eine erste PIN
setzen), und sobald eine gesetzt ist, muss man entsperrt sein, um sie zu ändern oder zu
entfernen. Das ergibt sich von selbst und braucht keine Sonderregel.
"""

import logging

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core import sperre as sperre_core
from backend.core.database import get_db
from backend.core.exceptions import bad_request

logger = logging.getLogger(__name__)

router = APIRouter()


class SperreStatus(BaseModel):
    pin_gesetzt: bool
    entsperrt: bool
    mindest_laenge: int


class EntsperrenRequest(BaseModel):
    pin: str


class PinRequest(BaseModel):
    pin: str = Field(..., description="Neue PIN, mindestens vier Zeichen.")


class NachweisResponse(BaseModel):
    nachweis: str


class ErfolgResponse(BaseModel):
    erfolg: bool


@router.get("/status", response_model=SperreStatus)
async def status(request: Request, db: AsyncSession = Depends(get_db)):
    """Ist eine PIN gesetzt, und ist diese Sitzung entsperrt?

    Bewusst ohne PIN abrufbar — der Client muss vor dem ersten Klick wissen, ob er
    Bedienelemente ausblenden soll.
    """
    gesetzt = await sperre_core.ist_gesetzt(db)
    nachweis = request.headers.get(sperre_core.HEADER)
    return SperreStatus(
        pin_gesetzt=gesetzt,
        entsperrt=(not gesetzt) or await sperre_core.nachweis_gueltig(db, nachweis),
        mindest_laenge=sperre_core.MIN_LAENGE,
    )


@router.post("/entsperren", response_model=NachweisResponse)
async def entsperren(daten: EntsperrenRequest, db: AsyncSession = Depends(get_db)):
    """Prüft die PIN und gibt den Nachweis für diese Browser-Sitzung zurück."""
    if not await sperre_core.ist_gesetzt(db):
        raise bad_request("Es ist keine PIN gesetzt.")
    if not await sperre_core.pin_stimmt(db, daten.pin):
        # Kein Hinweis darauf, ob die PIN zu kurz, zu lang oder nur falsch war.
        raise bad_request("PIN stimmt nicht.")
    return NachweisResponse(nachweis=await sperre_core.erzeuge_nachweis(db))


@router.post("/sperren", response_model=ErfolgResponse)
async def sperren():
    """Wieder sperren.

    Serverseitig ist nichts zu tun — der Nachweis liegt beim Client, und *er* verwirft
    ihn. Die Route existiert trotzdem, damit der Client einen benannten Weg hat und
    nicht selbst entscheidet, was „sperren" bedeutet.
    """
    return ErfolgResponse(erfolg=True)


@router.post("/pin", response_model=ErfolgResponse)
async def pin_setzen(daten: PinRequest, db: AsyncSession = Depends(get_db)):
    """Setzt die erste PIN oder ändert eine bestehende.

    Das Ändern ist selbst ein schreibender Aufruf und damit gesperrt, solange die
    Sitzung nicht entsperrt ist — die Middleware erledigt das, nicht diese Funktion.
    """
    pin = daten.pin.strip()
    if len(pin) < sperre_core.MIN_LAENGE:
        raise bad_request(
            f"Die PIN braucht mindestens {sperre_core.MIN_LAENGE} Zeichen."
        )
    await sperre_core.setze_pin(db, pin)
    logger.info("Einstellungs-PIN gesetzt bzw. geändert.")
    return ErfolgResponse(erfolg=True)


@router.delete("/pin", response_model=ErfolgResponse)
async def pin_entfernen(db: AsyncSession = Depends(get_db)):
    """Entfernt die PIN. Danach ist wieder alles offen — wie vor dem Einschalten."""
    await sperre_core.entferne_pin(db)
    logger.info("Einstellungs-PIN entfernt.")
    return ErfolgResponse(erfolg=True)
