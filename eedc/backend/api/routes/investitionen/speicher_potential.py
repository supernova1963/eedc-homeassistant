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
    leer_schwelle_prozent,
)
from backend.core.investition_kennwerte import (
    get_speicher_kapazitaet_kwh,
    get_speicher_nutzbare_kapazitaet_kwh,
)
from backend.models.investition import Investition, InvestitionTyp
from backend.services.speicher_potential_service import lade_potential_auswertung

router = APIRouter()


class MonatsPotentialResponse(BaseModel):
    """Eine Monatsspalte der Spannen-Grafik.

    ⚠ **`soc_bins` ist mit v4.0.15 entfallen** (zehn Stundenzähler je
    SoC-Zehntel). Die Sicht malte daraus eine Heatmap mit **global** normierter
    Deckkraft — ein Winter-Extremwert bestimmte die Skala aller Monate, und
    benachbarte Monate waren nicht mehr unterscheidbar. Ersetzt durch
    `soc_p10/p50/p90` je Monat, die ohne gemeinsame Skala auskommen.
    """

    jahr: int
    monat: int
    nutzbares_zusatzpotential_kwh: float
    ueberschuss_kwh: float
    stunden_voll: int
    zyklen_gesamt: int
    zyklen_leergelaufen: int

    stunden_mit_soc: int = Field(
        description="Stunden mit gemessenem Ladestand — Nenner der beiden Anteile"
    )
    soc_p10: Optional[float] = None
    soc_p50: Optional[float] = None
    soc_p90: Optional[float] = None
    anteil_voll_prozent: Optional[float] = Field(
        default=None, description=f"Anteil der Stunden ≥ {SOC_VOLL_PROZENT} % Ladestand"
    )
    anteil_leer_prozent: Optional[float] = Field(
        default=None,
        description=(
            "Anteil der Stunden ≤ der Leer-Schwelle dieser Anlage — der Wert steht "
            "als `soc_leer_prozent` in der Antwort. Bewusst **nicht** als feste Zahl "
            "hier: seit #379 hängt sie an der gepflegten nutzbaren Kapazität."
        ),
    )
    vollzyklen: Optional[float] = Field(
        default=None,
        description=(
            "Durchsatz als Vollzyklen-Äquivalent (Entladung ÷ Brutto-Kapazität), "
            "derselbe Kanon wie Cockpit, HA-Sensor und PDF. `null` ohne gepflegte "
            "Kapazität oder ohne Entladung im Monat — kein 0-Ersatz."
        ),
    )
    ladung_kwh: float = 0.0
    netz_ladung_kwh: float = Field(
        default=0.0,
        description=(
            "Teil der Ladung, der **höchstens** aus dem Netz kam (min(Ladung, "
            "Netzbezug) je Stunde). Obergrenze, keine Messung."
        ),
    )
    netz_ladung_anteil_prozent: Optional[float] = None


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

    #: Anzahl Speicher der Anlage. Seit N-239 ist der Ladestand darüber das
    #: kapazitätsgewichtete Mittel; ältere Tage können noch ein Gerät tragen.
    anzahl_speicher: int
    kapazitaet_kwh: Optional[float]
    #: Brutto-Kapazität — der Nenner der Vollzyklen. Getrennt ausgewiesen, damit
    #: die Sicht „keine Kapazität gepflegt" von „nichts entladen" unterscheiden
    #: kann, statt beide als leere Spur zu zeigen.
    kapazitaet_brutto_kwh: Optional[float]
    soc_voll_prozent: float
    #: Ab diesem Ladestand gilt der Speicher als leer — **anlagenspezifisch**
    #: seit #379, abgeleitet aus dem Verhältnis nutzbarer zu Brutto-Kapazität.
    #: Bis dahin lieferte das Feld konstant 5,0 und die Sicht schrieb die Zahl
    #: als feste Legende hin.
    soc_leer_prozent: float
    #: True = die Schwelle stammt aus der gepflegten nutzbaren Kapazität,
    #: False = Rückfall auf 5 %. Die Sicht braucht die Unterscheidung, um „gilt
    #: für deinen Speicher" von „Standardannahme" zu trennen — ohne sie müsste
    #: sie den Wert gegen die Konstante vergleichen und die Regel nachbauen.
    soc_leer_ist_abgeleitet: bool = False


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

    # NETTO, nicht brutto: Diese Sicht fährt den Speicher rechnerisch durch
    # („wie viel wäre zusätzlich hindurchgegangen?"), und für genau diese Klasse
    # gilt laut `investition_kennwerte` der nutzbare Hub. Der Helper fällt still
    # auf brutto zurück, wenn das optionale Feld leer ist.
    kapazitaet = None
    if speicher:
        summe = sum(get_speicher_nutzbare_kapazitaet_kwh(s) or 0 for s in speicher)
        kapazitaet = round(summe, 1) if summe else None

    # BRUTTO daneben — und zwar **nur** für die Vollzyklen. Zwei Nenner in einer
    # Antwort sind erklärungsbedürftig, ein abweichender Zyklenwert gegenüber
    # Cockpit/HA-Sensor/PDF wäre schlimmer: `vollzyklen()` ist auf brutto
    # festgelegt, weil der Netto-Wert selten gepflegt ist.
    kapazitaet_brutto = None
    if speicher:
        summe_brutto = sum(get_speicher_kapazitaet_kwh(s) or 0 for s in speicher)
        kapazitaet_brutto = round(summe_brutto, 1) if summe_brutto else None

    # Die Untergrenze, ab der dieser Speicher nichts mehr abgibt (#379). Beide
    # Kapazitäten liegen hier ohnehin schon vor — die Ableitung braucht keine
    # zusätzliche Abfrage und kein neues Eingabefeld.
    leer_schwelle = leer_schwelle_prozent(kapazitaet_brutto, kapazitaet)
    abgeleitet = leer_schwelle > SOC_LEER_PROZENT

    auswertung = await lade_potential_auswertung(
        db,
        anlage_id,
        von=von,
        bis=bis,
        kapazitaet_brutto_kwh=kapazitaet_brutto,
        leer_schwelle_prozent=leer_schwelle,
    )

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
        monate=[
            MonatsPotentialResponse(
                jahr=m.jahr,
                monat=m.monat,
                nutzbares_zusatzpotential_kwh=m.nutzbares_zusatzpotential_kwh,
                ueberschuss_kwh=m.ueberschuss_kwh,
                stunden_voll=m.stunden_voll,
                zyklen_gesamt=m.zyklen_gesamt,
                zyklen_leergelaufen=m.zyklen_leergelaufen,
                stunden_mit_soc=m.stunden_mit_soc,
                soc_p10=m.spanne.p10 if m.spanne else None,
                soc_p50=m.spanne.p50 if m.spanne else None,
                soc_p90=m.spanne.p90 if m.spanne else None,
                anteil_voll_prozent=m.anteil_voll_prozent,
                anteil_leer_prozent=m.anteil_leer_prozent,
                vollzyklen=m.vollzyklen,
                ladung_kwh=m.ladung_kwh,
                netz_ladung_kwh=m.netz_ladung_kwh,
                netz_ladung_anteil_prozent=(
                    round(m.netz_ladung_anteil_prozent, 1)
                    if m.netz_ladung_anteil_prozent is not None else None
                ),
            )
            for m in auswertung.monate
        ],
        anzahl_speicher=len(speicher),
        kapazitaet_kwh=kapazitaet,
        kapazitaet_brutto_kwh=kapazitaet_brutto,
        soc_voll_prozent=SOC_VOLL_PROZENT,
        soc_leer_prozent=round(leer_schwelle, 1),
        soc_leer_ist_abgeleitet=abgeleitet,
    )
