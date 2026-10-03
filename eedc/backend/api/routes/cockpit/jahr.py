"""Cockpit → Jahr — die Jahresroute (Paket „Ergebnisgrößen Monat/Jahr in den Layer", 03.10.2026, Vorlage B3).

``GET /api/cockpit/jahr/{anlage_id}?jahr=YYYY`` liefert **dieselben Monatsantworten**, die der Browser bis dahin im
6er-Pool lud (Wärme-Verlauf und Speicher-Monatstabelle lesen sie roh, Gegenprüfung G3), und dazu ihre Faltung aus dem
Layer: ``kopf`` (das Jahr bis heute), ``vergleich`` (nur abgeschlossene Monate; ``null`` = wie ``kopf``), ``vorjahr``
und ``oe_jahr`` aus der Monatsreihe. Quoten paarweise (N-584), Ergebnisgrößen über die Leiter mit derselben
None-Regel wie im Monat (G2/E10).

Die Monate werden **sequenziell in derselben Sitzung** berechnet (Präzedenz ``pdf/builders/monatsbericht.py``), mit
einem Vorlade-Kontext, damit die Fakten J−1…J nur einmal geladen werden. Aufbereitung: ``services/jahres_aggregat.py``.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.api.routes.aktueller_monat.schemas import AktuellerMonatResponse
from backend.services.jahres_aggregat import baue_jahr

router = APIRouter()


class JahrVergleich(BaseModel):
    """Σ der Monatsreihe EINES Jahres über die Vergleichs-Grundgesamtheit (Autarkie paarweise)."""
    jahr: int
    pv: Optional[float] = None
    ev: Optional[float] = None
    direkt: Optional[float] = None
    einsp: Optional[float] = None
    netz: Optional[float] = None
    gesamt: Optional[float] = None
    autarkie: Optional[float] = None
    autarkie_zaehler: Optional[float] = None
    autarkie_nenner: Optional[float] = None
    monate: list[int] = []


class JahrVergleichMittel(JahrVergleich):
    """Ø über die übrigen Jahre, die die Grundgesamtheit GANZ abdecken — ``count`` sagt, wie viele."""
    count: int = 0


class CockpitJahrResponse(BaseModel):
    jahr: int
    #: Die geladenen Monatsantworten (nur Monate mit gemessenen Mengen), aufsteigend.
    monate: list[AktuellerMonatResponse] = []
    #: „Das Jahr bis heute" — Faltung aller Monate, mit den WP-Kennzahlen der Übersicht (P12).
    kopf: AktuellerMonatResponse
    #: Faltung nur der abgeschlossenen Monate; ``None`` heißt „dieselben Monate wie ``kopf``".
    vergleich: Optional[AktuellerMonatResponse] = None
    monate_nr: list[int] = []
    vergleichs_monate: list[int] = []
    vorjahr: Optional[JahrVergleich] = None
    oe_jahr: Optional[JahrVergleichMittel] = None


@router.get("/jahr/{anlage_id}", response_model=CockpitJahrResponse)
async def get_cockpit_jahr(
    anlage_id: int,
    jahr: int = Query(..., description="Kalenderjahr"),
    db: AsyncSession = Depends(get_db),
):
    """Cockpit → Jahr und Auswertungen → Finanzen (Jahr) — ein Abruf statt zwölf, gefaltet im Layer."""
    return await baue_jahr(db, anlage_id, jahr)
