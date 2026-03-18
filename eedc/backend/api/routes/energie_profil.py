"""
Energie-Profil API - Tägliche Energiedaten pro Komponente.

GET /api/energie-profil/{anlage_id}/tage — Tageszusammenfassungen mit Per-Komponenten-kWh.
"""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesZusammenfassung

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Response Models ──────────────────────────────────────────────────────────

class TagesZusammenfassungResponse(BaseModel):
    """Tageszusammenfassung mit Per-Komponenten-kWh."""
    datum: date
    ueberschuss_kwh: Optional[float] = None
    defizit_kwh: Optional[float] = None
    peak_pv_kw: Optional[float] = None
    peak_netzbezug_kw: Optional[float] = None
    peak_einspeisung_kw: Optional[float] = None
    batterie_vollzyklen: Optional[float] = None
    temperatur_min_c: Optional[float] = None
    temperatur_max_c: Optional[float] = None
    strahlung_summe_wh_m2: Optional[float] = None
    performance_ratio: Optional[float] = None
    stunden_verfuegbar: int = 0
    datenquelle: Optional[str] = None
    komponenten_kwh: Optional[dict] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/{anlage_id}/tage", response_model=list[TagesZusammenfassungResponse])
async def get_tages_zusammenfassungen(
    anlage_id: int,
    von: date = Query(..., description="Startdatum (inklusiv)"),
    bis: date = Query(..., description="Enddatum (inklusiv)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Tageszusammenfassungen für einen Zeitraum zurück.

    Enthält Per-Komponenten-kWh (z.B. pv_3, waermepumpe_5, wallbox_7)
    sowie Gesamtkennzahlen (Überschuss, Defizit, Peaks, Performance Ratio).
    """
    # Anlage prüfen
    result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    # Maximal 366 Tage (ein Jahr)
    if (bis - von).days > 366:
        raise HTTPException(status_code=400, detail="Zeitraum darf maximal 366 Tage umfassen")

    # Tageszusammenfassungen laden
    result = await db.execute(
        select(TagesZusammenfassung)
        .where(and_(
            TagesZusammenfassung.anlage_id == anlage_id,
            TagesZusammenfassung.datum >= von,
            TagesZusammenfassung.datum <= bis,
        ))
        .order_by(TagesZusammenfassung.datum)
    )
    tage = result.scalars().all()

    return [
        TagesZusammenfassungResponse(
            datum=t.datum,
            ueberschuss_kwh=t.ueberschuss_kwh,
            defizit_kwh=t.defizit_kwh,
            peak_pv_kw=t.peak_pv_kw,
            peak_netzbezug_kw=t.peak_netzbezug_kw,
            peak_einspeisung_kw=t.peak_einspeisung_kw,
            batterie_vollzyklen=t.batterie_vollzyklen,
            temperatur_min_c=t.temperatur_min_c,
            temperatur_max_c=t.temperatur_max_c,
            strahlung_summe_wh_m2=t.strahlung_summe_wh_m2,
            performance_ratio=t.performance_ratio,
            stunden_verfuegbar=t.stunden_verfuegbar,
            datenquelle=t.datenquelle,
            komponenten_kwh=t.komponenten_kwh,
        )
        for t in tage
    ]
