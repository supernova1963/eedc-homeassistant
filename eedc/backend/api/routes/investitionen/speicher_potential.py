"""Speicher-Potentialanalyse — „hätte mehr Kapazität geholfen?" (#358 Phase 2).

Eigene Route statt eines weiteren Blocks in `dashboards.py`: Die Analyse liest
**Stundendaten** über die ganze Lebensdauer und ist damit deutlich teurer als die
Monats-Dashboards daneben — sie soll nur laufen, wenn die Sicht sie anfordert.
(Und `dashboards.py` steht bei ~2000 Zeilen; das Backend-Refactoring großer
Service-Dateien ist ein offener Roadmap-Punkt, dem hier nicht vorgearbeitet wird.)
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.core.berechnungen.speicher_potential import (
    SOC_LEER_PROZENT,
    SOC_VOLL_PROZENT,
)
from backend.core.investition_kennwerte import get_speicher_nutzbare_kapazitaet_kwh
from backend.models.investition import Investition, InvestitionTyp
from backend.services.speicher_potential_service import (
    SOC_BIN_ANZAHL,
    lade_potential_auswertung,
)

router = APIRouter()


class MonatsPotentialResponse(BaseModel):
    jahr: int
    monat: int
    nutzbares_zusatzpotential_kwh: float
    ueberschuss_kwh: float
    stunden_voll: int
    zyklen_gesamt: int
    zyklen_leergelaufen: int
    soc_bins: list[int] = Field(
        description=f"Stunden je SoC-Zehntel (0–10 %, …, 90–100 %), {SOC_BIN_ANZAHL} Werte"
    )


class SpeicherPotentialResponse(BaseModel):
    """Antwort der Potentialanalyse.

    ``nutzbares_zusatzpotential_kwh`` ist die Zahl, an der eine Kaufentscheidung
    hängen darf; ``ueberschuss_kwh`` steht als Obergrenze daneben, damit die Sicht
    den Unterschied zeigen kann statt ihn zu verschweigen.
    """

    nutzbares_zusatzpotential_kwh: float
    ueberschuss_kwh: float
    stunden_voll: int
    zyklen_gesamt: int
    zyklen_leergelaufen: int
    deckelung_greift: bool
    tage_mit_daten: int
    von: Optional[date]
    bis: Optional[date]
    monate: list[MonatsPotentialResponse]

    #: Anzahl Speicher der Anlage — ab 2 beschreibt der SoC nur EINES der Geräte
    #: (N-239, s. Service-Docstring), nicht die Anlage.
    anzahl_speicher: int
    kapazitaet_kwh: Optional[float]
    soc_voll_prozent: float
    soc_leer_prozent: float


@router.get("/speicher-potential/{anlage_id}", response_model=SpeicherPotentialResponse)
async def get_speicher_potential(
    anlage_id: int,
    von: Optional[date] = Query(None, description="Erster Tag (Vorgabe: gesamte Historie)"),
    bis: Optional[date] = Query(None, description="Letzter Tag"),
    db: AsyncSession = Depends(get_db),
):
    """Wertet aus, wie viel ein **größerer** Speicher zusätzlich durchgesetzt hätte.

    Die gelieferte Zahl ist gedeckelt: Überschuss, den der volle Speicher nicht
    aufnehmen konnte, zählt nur so weit, wie er vor dem nächsten Sonnenaufgang
    auch wieder abgegeben worden wäre. Begründung und Messung stehen im Docstring
    von `core/berechnungen/speicher_potential.py`.
    """
    speicher = list((await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.SPEICHER.value)
    )).scalars().all())

    auswertung = await lade_potential_auswertung(db, anlage_id, von=von, bis=bis)

    # NETTO, nicht brutto: Diese Sicht fährt den Speicher rechnerisch durch
    # („wie viel wäre zusätzlich hindurchgegangen?"), und für genau diese Klasse
    # gilt laut `investition_kennwerte` der nutzbare Hub. Der Helper fällt still
    # auf brutto zurück, wenn das optionale Feld leer ist.
    kapazitaet = None
    if speicher:
        summe = sum(get_speicher_nutzbare_kapazitaet_kwh(s) or 0 for s in speicher)
        kapazitaet = round(summe, 1) if summe else None

    return SpeicherPotentialResponse(
        nutzbares_zusatzpotential_kwh=round(
            auswertung.gesamt.nutzbares_zusatzpotential_kwh, 1
        ),
        ueberschuss_kwh=round(auswertung.gesamt.ueberschuss_gesamt_kwh, 1),
        stunden_voll=auswertung.gesamt.stunden_voll,
        zyklen_gesamt=auswertung.gesamt.zyklen_gesamt,
        zyklen_leergelaufen=auswertung.gesamt.zyklen_leergelaufen,
        deckelung_greift=auswertung.gesamt.deckelung_greift,
        tage_mit_daten=auswertung.tage_mit_daten,
        von=auswertung.von,
        bis=auswertung.bis,
        monate=[MonatsPotentialResponse(**vars(m)) for m in auswertung.monate],
        anzahl_speicher=len(speicher),
        kapazitaet_kwh=kapazitaet,
        soc_voll_prozent=SOC_VOLL_PROZENT,
        soc_leer_prozent=SOC_LEER_PROZENT,
    )
