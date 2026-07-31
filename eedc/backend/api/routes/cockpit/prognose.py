"""
Cockpit Prognose — PVGIS-Prognose vs. IST + EEDC vs. ML vs. IST Vergleich.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.services.monats_fakten import lade_monats_fakten
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.api.routes.cockpit._shared import MONATSNAMEN

router = APIRouter()


async def _ist_pv_je_monat(
    db: AsyncSession, anlage_id: int, jahr: int
) -> dict[int, float]:
    """Gemessene PV je Monat des Jahres — aus den Monats-Fakten (ADR-002/**P10**).

    Beide Prognose-Vergleiche brauchen dieselbe IST-Achse, und bis 2026-07-31
    hatte jeder seine eigene Kopie: eine rohe Summe über
    ``verbrauch_daten["pv_erzeugung_kwh"]`` der PV-/BKW-IMD-Zeilen. Die liefert
    **0**, wenn die Erzeugung nur als Anlagen-Aggregat
    (``Monatsdaten.pv_erzeugung_kwh``) gepflegt ist — der Normalfall bei
    manueller Pflege und beim Import mit einem einzigen Gesamt-PV-Sensor. Der
    Vergleich stellte dort also eine Prognose gegen ein IST von 0 und wies
    −100 % Abweichung aus (Befund-Klasse **F-5** der Drift-Inventur
    2026-07-31, hier nachträglich erhoben — im Register **N-14**).

    ``erzeugung.pv_kwh`` ist Module **und** Balkonkraftwerk, deckungsgleich mit
    dem früheren Typ-Filter, und die P7-Auflösung füllt die Lücken der Module
    ohne eigenen Wert aus dem Aggregat. Der Anschaffungs-/Stilllegungs-Filter
    steckt in der Schicht (``ist_aktiv_im_monat``, monatsgenau statt
    jahresweise wie der frühere ``aktiv_im_jahr``-Vorfilter).
    """
    fakten = await lade_monats_fakten(db, anlage_id, von=(jahr, 1), bis=(jahr, 12))
    return {f.monat: f.erzeugung.pv_kwh for f in fakten if f.erzeugung.pv_kwh}


class MonatsvergleichItem(BaseModel):
    """Vergleich Prognose vs. IST für einen Monat."""
    monat: int
    monat_name: str
    prognose_kwh: float
    ist_kwh: float
    abweichung_kwh: float
    abweichung_prozent: Optional[float]
    performance_ratio: Optional[float]


class PrognoseVsIstResponse(BaseModel):
    """Prognose vs. IST Vergleich."""
    anlage_id: int
    jahr: int
    hat_prognose: bool
    prognose_jahresertrag_kwh: float
    ist_jahresertrag_kwh: float
    abweichung_kwh: float
    abweichung_prozent: Optional[float]
    performance_ratio: Optional[float]
    monatswerte: list[MonatsvergleichItem]
    prognose_quelle: Optional[str]
    prognose_datum: Optional[str]


class PrognoseVergleichMonat(BaseModel):
    """Vergleich EEDC-Forecast vs. IST für einen Monat."""
    monat: int
    monat_name: str
    eedc_kwh: float
    ist_kwh: float
    eedc_abweichung_pct: Optional[float]
    tage_mit_daten: int


class PrognoseVergleichResponse(BaseModel):
    """EEDC vs. IST Prognose-Vergleich."""
    anlage_id: int
    jahr: int
    eedc_jahres_kwh: float
    ist_jahres_kwh: float
    eedc_abweichung_pct: Optional[float]
    monatswerte: list[PrognoseVergleichMonat]
    tage_mit_eedc: int


@router.get("/prognose-vs-ist/{anlage_id}", response_model=PrognoseVsIstResponse)
async def get_prognose_vs_ist(
    anlage_id: int,
    jahr: int = Query(..., description="Jahr für den Vergleich"),
    db: AsyncSession = Depends(get_db)
):
    """Vergleicht PVGIS-Prognose mit tatsächlichen Monatsdaten."""
    prognose = await lade_aktive_prognose(db, anlage_id)

    ist_pro_monat = await _ist_pv_je_monat(db, anlage_id, jahr)

    prognose_pro_monat = {}
    if prognose and prognose.monatswerte:
        for mw in prognose.monatswerte:
            prognose_pro_monat[mw["monat"]] = mw["e_m"]

    monatswerte = []
    prognose_summe = 0.0
    ist_summe = 0.0

    for monat in range(1, 13):
        prog_kwh = prognose_pro_monat.get(monat, 0)
        ist_kwh = ist_pro_monat.get(monat, 0)
        abweichung = ist_kwh - prog_kwh
        abweichung_pct = (abweichung / prog_kwh * 100) if prog_kwh > 0 else None
        perf_ratio = (ist_kwh / prog_kwh) if prog_kwh > 0 else None

        monatswerte.append(MonatsvergleichItem(
            monat=monat,
            monat_name=MONATSNAMEN[monat],
            prognose_kwh=round(prog_kwh, 1),
            ist_kwh=round(ist_kwh, 1),
            abweichung_kwh=round(abweichung, 1),
            abweichung_prozent=round(abweichung_pct, 1) if abweichung_pct is not None else None,
            performance_ratio=round(perf_ratio, 3) if perf_ratio is not None else None,
        ))
        prognose_summe += prog_kwh
        ist_summe += ist_kwh

    jahres_abweichung = ist_summe - prognose_summe
    jahres_abweichung_pct = (jahres_abweichung / prognose_summe * 100) if prognose_summe > 0 else None
    jahres_perf_ratio = (ist_summe / prognose_summe) if prognose_summe > 0 else None

    return PrognoseVsIstResponse(
        anlage_id=anlage_id,
        jahr=jahr,
        hat_prognose=prognose is not None,
        prognose_jahresertrag_kwh=round(prognose_summe, 1),
        ist_jahresertrag_kwh=round(ist_summe, 1),
        abweichung_kwh=round(jahres_abweichung, 1),
        abweichung_prozent=round(jahres_abweichung_pct, 1) if jahres_abweichung_pct is not None else None,
        performance_ratio=round(jahres_perf_ratio, 3) if jahres_perf_ratio is not None else None,
        monatswerte=monatswerte,
        prognose_quelle="PVGIS" if prognose else None,
        prognose_datum=prognose.abgerufen_am.strftime("%Y-%m-%d") if prognose else None,
    )


@router.get("/prognose-vergleich/{anlage_id}", response_model=PrognoseVergleichResponse)
async def get_prognose_vergleich(
    anlage_id: int,
    jahr: int = Query(..., description="Jahr für den Vergleich"),
    db: AsyncSession = Depends(get_db),
):
    """Vergleicht EEDC-Forecast vs. ML-Forecast vs. IST auf Monatsbasis."""
    from backend.models.tages_energie_profil import TagesZusammenfassung

    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not anlage_result.scalar_one_or_none():
        raise not_found("Anlage")

    tz_result = await db.execute(
        select(TagesZusammenfassung)
        .where(
            TagesZusammenfassung.anlage_id == anlage_id,
            func.extract("year", TagesZusammenfassung.datum) == jahr,
        )
        .order_by(TagesZusammenfassung.datum)
    )
    tages_daten = tz_result.scalars().all()

    eedc_pro_monat: dict[int, float] = {}
    tage_eedc_pro_monat: dict[int, int] = {}

    for tz in tages_daten:
        monat = tz.datum.month
        if tz.pv_prognose_kwh is not None and tz.pv_prognose_kwh > 0:
            eedc_pro_monat[monat] = eedc_pro_monat.get(monat, 0) + tz.pv_prognose_kwh
            tage_eedc_pro_monat[monat] = tage_eedc_pro_monat.get(monat, 0) + 1

    ist_pro_monat = await _ist_pv_je_monat(db, anlage_id, jahr)

    monatswerte = []
    eedc_summe = 0.0
    ist_summe = 0.0
    gesamt_tage_eedc = 0

    for monat in range(1, 13):
        eedc = eedc_pro_monat.get(monat, 0)
        ist = ist_pro_monat.get(monat, 0)
        tage_eedc = tage_eedc_pro_monat.get(monat, 0)

        eedc_abw = ((ist - eedc) / eedc * 100) if eedc > 0 and ist > 0 else None

        monatswerte.append(PrognoseVergleichMonat(
            monat=monat,
            monat_name=MONATSNAMEN[monat],
            eedc_kwh=round(eedc, 1),
            ist_kwh=round(ist, 1),
            eedc_abweichung_pct=round(eedc_abw, 1) if eedc_abw is not None else None,
            tage_mit_daten=tage_eedc,
        ))

        eedc_summe += eedc
        ist_summe += ist
        gesamt_tage_eedc += tage_eedc

    eedc_jahres_abw = ((ist_summe - eedc_summe) / eedc_summe * 100) if eedc_summe > 0 and ist_summe > 0 else None

    return PrognoseVergleichResponse(
        anlage_id=anlage_id,
        jahr=jahr,
        eedc_jahres_kwh=round(eedc_summe, 1),
        ist_jahres_kwh=round(ist_summe, 1),
        eedc_abweichung_pct=round(eedc_jahres_abw, 1) if eedc_jahres_abw is not None else None,
        monatswerte=monatswerte,
        tage_mit_eedc=gesamt_tage_eedc,
    )
