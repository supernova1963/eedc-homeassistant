"""
Monatsabschluss-Routes — gemeinsame Models, Helpers, Konstanten.

Genutzt von views.py (Read-/Vorschau-Endpoints) und wizard.py
(Save-Endpoint mit Plausibilitätsprüfung + Provenance-Schreib-Pfad).
"""

import logging
from typing import Optional

from pydantic import BaseModel

from backend.services.vorschlag_service import PlausibilitaetsWarnung, Vorschlag

logger = logging.getLogger(__name__)


MONAT_NAMEN = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


# =============================================================================
# Pydantic-Models — gemeinsam zwischen views (FeldStatus.vorschlaege/warnungen)
# und wizard (MonatsabschlussResult.warnungen) genutzt.
# =============================================================================

class VorschlagResponse(BaseModel):
    """Vorschlag für einen Feldwert."""
    wert: float
    quelle: str
    konfidenz: int
    beschreibung: str
    details: Optional[dict] = None


class WarnungResponse(BaseModel):
    """Plausibilitätswarnung."""
    typ: str
    schwere: str
    meldung: str
    details: Optional[dict] = None


def _vorschlag_to_response(v: Vorschlag) -> VorschlagResponse:
    """Konvertiert Vorschlag zu Response-Model."""
    return VorschlagResponse(
        wert=v.wert,
        quelle=v.quelle.value,
        konfidenz=v.konfidenz,
        beschreibung=v.beschreibung,
        details=v.details,
    )


def _warnung_to_response(w: PlausibilitaetsWarnung) -> WarnungResponse:
    """Konvertiert Warnung zu Response-Model."""
    return WarnungResponse(
        typ=w.typ,
        schwere=w.schwere,
        meldung=w.meldung,
        details=w.details,
    )
