"""
Cockpit PV-Strings — SOLL vs. IST Vergleich pro PV-Modul (Jahressicht + Gesamtlaufzeit).
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.pvgis_prognose import PVGISPrognose as PVGISPrognoseModel
from backend.api.routes.cockpit._shared import MONATSNAMEN

router = APIRouter()


class PVStringMonat(BaseModel):
    monat: int
    monat_name: str
    prognose_kwh: float
    ist_kwh: float
    abweichung_kwh: float
    abweichung_prozent: Optional[float]
    performance_ratio: Optional[float]


class PVStringDaten(BaseModel):
    investition_id: int
    bezeichnung: str
    leistung_kwp: float
    ausrichtung: Optional[str]
    neigung_grad: Optional[int]
    wechselrichter_id: Optional[int]
    wechselrichter_name: Optional[str]
    prognose_jahr_kwh: float
    ist_jahr_kwh: float
    abweichung_jahr_kwh: float
    abweichung_jahr_prozent: Optional[float]
    performance_ratio_jahr: Optional[float]
    spezifischer_ertrag_kwh_kwp: Optional[float]
    monatswerte: list[PVStringMonat]


class PVStringsResponse(BaseModel):
    anlage_id: int
    jahr: int
    hat_prognose: bool
    anlagen_leistung_kwp: float
    prognose_gesamt_kwh: float
    ist_gesamt_kwh: float
    abweichung_gesamt_kwh: float
    abweichung_gesamt_prozent: Optional[float]
    strings: list[PVStringDaten]
    bester_string: Optional[str]
    schlechtester_string: Optional[str]


class PVStringJahreswert(BaseModel):
    jahr: int
    prognose_kwh: float
    ist_kwh: float
    abweichung_prozent: Optional[float]
    performance_ratio: Optional[float]


class PVStringSaisonalwert(BaseModel):
    monat: int
    monat_name: str
    prognose_kwh: float
    ist_durchschnitt_kwh: float
    ist_summe_kwh: float
    anzahl_jahre: int


class PVStringGesamtlaufzeit(BaseModel):
    investition_id: int
    bezeichnung: str
    leistung_kwp: float
    ausrichtung: Optional[str]
    neigung_grad: Optional[int]
    wechselrichter_name: Optional[str]
    prognose_gesamt_kwh: float
    ist_gesamt_kwh: float
    abweichung_gesamt_prozent: Optional[float]
    performance_ratio_gesamt: Optional[float]
    spezifischer_ertrag_kwh_kwp: Optional[float]
    jahreswerte: list[PVStringJahreswert]
    saisonalwerte: list[PVStringSaisonalwert]


class PVStringsGesamtlaufzeitResponse(BaseModel):
    anlage_id: int
    hat_prognose: bool
    anlagen_leistung_kwp: float
    erstes_jahr: int
    letztes_jahr: int
    anzahl_jahre: int
    anzahl_monate: int
    prognose_gesamt_kwh: float
    ist_gesamt_kwh: float
    abweichung_gesamt_kwh: float
    abweichung_gesamt_prozent: Optional[float]
    strings: list[PVStringGesamtlaufzeit]
    saisonal_aggregiert: list[PVStringSaisonalwert]
    bester_string: Optional[str]
    schlechtester_string: Optional[str]


@router.get("/pv-strings/{anlage_id}", response_model=PVStringsResponse)
async def get_pv_strings(
    anlage_id: int,
    jahr: int = Query(default=None, description="Jahr (Default: aktuelles Jahr)"),
    db: AsyncSession = Depends(get_db)
):
    """PV-String-Vergleich: SOLL vs IST pro PV-Modul."""
    if jahr is None:
        jahr = date.today().year

    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    # KEIN aktiv-Filter (Issue #123): historische PV-String-Auswertung darf
    # später stillgelegte Strings nicht aus Vergangenheits-Vergleichen ausblenden.
    result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == "pv-module")
    )
    pv_module = result.scalars().all()

    if not pv_module:
        return PVStringsResponse(
            anlage_id=anlage_id, jahr=jahr, hat_prognose=False,
            anlagen_leistung_kwp=anlage.leistung_kwp or 0,
            prognose_gesamt_kwh=0, ist_gesamt_kwh=0, abweichung_gesamt_kwh=0,
            abweichung_gesamt_prozent=None, strings=[],
            bester_string=None, schlechtester_string=None,
        )

    wr_ids = [m.parent_investition_id for m in pv_module if m.parent_investition_id]
    wechselrichter_map = {}
    if wr_ids:
        result = await db.execute(select(Investition).where(Investition.id.in_(wr_ids)))
        for wr in result.scalars().all():
            wechselrichter_map[wr.id] = wr.bezeichnung

    result = await db.execute(
        select(PVGISPrognoseModel)
        .where(PVGISPrognoseModel.anlage_id == anlage_id)
        .order_by(PVGISPrognoseModel.abgerufen_am.desc())
        .limit(1)
    )
    prognose = result.scalar_one_or_none()
    hat_prognose = prognose is not None

    prognose_monate = {}
    if prognose and prognose.monatswerte:
        for mw in prognose.monatswerte:
            prognose_monate[mw["monat"]] = mw.get("e_m", 0)

    prognose_per_modul: dict[int, dict[int, float]] = {}
    if prognose and prognose.module_monatswerte:
        for inv_id_str, monatsdaten in prognose.module_monatswerte.items():
            try:
                inv_id = int(inv_id_str)
                prognose_per_modul[inv_id] = {mw["monat"]: mw.get("e_m", 0) for mw in monatsdaten}
            except (ValueError, TypeError):
                pass

    gesamt_kwp = sum(m.leistung_kwp or 0 for m in pv_module)
    if gesamt_kwp == 0:
        gesamt_kwp = anlage.leistung_kwp or 1

    pv_ids = [m.id for m in pv_module]
    result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(pv_ids))
        .where(InvestitionMonatsdaten.jahr == jahr)
    )
    inv_monatsdaten = result.scalars().all()

    md_by_inv: dict[int, dict[int, float]] = {m.id: {} for m in pv_module}
    for imd in inv_monatsdaten:
        data = imd.verbrauch_daten or {}
        pv_erzeugt = data.get("pv_erzeugung_kwh", 0) or 0
        if imd.investition_id in md_by_inv:
            md_by_inv[imd.investition_id][imd.monat] = pv_erzeugt

    strings_data = []
    prognose_gesamt = 0
    ist_gesamt = 0

    for modul in pv_module:
        modul_kwp = modul.leistung_kwp or 0
        kwp_anteil = modul_kwp / gesamt_kwp if gesamt_kwp > 0 else 0
        params = modul.parameter or {}
        ausrichtung = modul.ausrichtung or params.get("ausrichtung")
        neigung = modul.neigung_grad or params.get("neigung_grad")
        monatswerte = []
        prognose_jahr = 0
        ist_jahr = 0
        modul_prognose = prognose_per_modul.get(modul.id)
        months_with_data = set(md_by_inv.get(modul.id, {}).keys())

        for monat in range(1, 13):
            if monat in months_with_data:
                if modul_prognose is not None:
                    prog_monat = modul_prognose.get(monat, 0)
                else:
                    prog_monat = prognose_monate.get(monat, 0) * kwp_anteil
            else:
                prog_monat = 0.0
            ist_monat = md_by_inv.get(modul.id, {}).get(monat, 0)
            abweichung = ist_monat - prog_monat
            abweichung_pct = (abweichung / prog_monat * 100) if prog_monat > 0 else None
            perf_ratio = (ist_monat / prog_monat) if prog_monat > 0 else None
            monatswerte.append(PVStringMonat(
                monat=monat, monat_name=MONATSNAMEN[monat],
                prognose_kwh=round(prog_monat, 1), ist_kwh=round(ist_monat, 1),
                abweichung_kwh=round(abweichung, 1),
                abweichung_prozent=round(abweichung_pct, 1) if abweichung_pct is not None else None,
                performance_ratio=round(perf_ratio, 3) if perf_ratio is not None else None,
            ))
            prognose_jahr += prog_monat
            ist_jahr += ist_monat

        abweichung_jahr = ist_jahr - prognose_jahr
        abweichung_jahr_pct = (abweichung_jahr / prognose_jahr * 100) if prognose_jahr > 0 else None
        perf_ratio_jahr = (ist_jahr / prognose_jahr) if prognose_jahr > 0 else None
        spez_ertrag = (ist_jahr / modul_kwp) if modul_kwp > 0 else None

        strings_data.append(PVStringDaten(
            investition_id=modul.id, bezeichnung=modul.bezeichnung,
            leistung_kwp=modul_kwp, ausrichtung=ausrichtung, neigung_grad=neigung,
            wechselrichter_id=modul.parent_investition_id,
            wechselrichter_name=wechselrichter_map.get(modul.parent_investition_id) if modul.parent_investition_id else None,
            prognose_jahr_kwh=round(prognose_jahr, 1), ist_jahr_kwh=round(ist_jahr, 1),
            abweichung_jahr_kwh=round(abweichung_jahr, 1),
            abweichung_jahr_prozent=round(abweichung_jahr_pct, 1) if abweichung_jahr_pct is not None else None,
            performance_ratio_jahr=round(perf_ratio_jahr, 3) if perf_ratio_jahr is not None else None,
            spezifischer_ertrag_kwh_kwp=round(spez_ertrag, 0) if spez_ertrag is not None else None,
            monatswerte=monatswerte,
        ))
        prognose_gesamt += prognose_jahr
        ist_gesamt += ist_jahr

    abweichung_gesamt = ist_gesamt - prognose_gesamt
    abweichung_gesamt_pct = (abweichung_gesamt / prognose_gesamt * 100) if prognose_gesamt > 0 else None
    strings_with_perf = [(s.bezeichnung, s.performance_ratio_jahr) for s in strings_data if s.performance_ratio_jahr]
    bester_string = None
    schlechtester_string = None
    if strings_with_perf:
        strings_sorted = sorted(strings_with_perf, key=lambda x: x[1] or 0, reverse=True)
        bester_string = strings_sorted[0][0]
        schlechtester_string = strings_sorted[-1][0] if len(strings_sorted) > 1 else None

    return PVStringsResponse(
        anlage_id=anlage_id, jahr=jahr, hat_prognose=hat_prognose,
        anlagen_leistung_kwp=gesamt_kwp,
        prognose_gesamt_kwh=round(prognose_gesamt, 1),
        ist_gesamt_kwh=round(ist_gesamt, 1),
        abweichung_gesamt_kwh=round(abweichung_gesamt, 1),
        abweichung_gesamt_prozent=round(abweichung_gesamt_pct, 1) if abweichung_gesamt_pct is not None else None,
        strings=strings_data, bester_string=bester_string, schlechtester_string=schlechtester_string,
    )


@router.get("/pv-strings-gesamtlaufzeit/{anlage_id}", response_model=PVStringsGesamtlaufzeitResponse)
async def get_pv_strings_gesamtlaufzeit(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """PV-String-Vergleich über die gesamte Laufzeit."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    # KEIN aktiv-Filter (Issue #123): historische PV-String-Auswertung darf
    # später stillgelegte Strings nicht aus Vergangenheits-Vergleichen ausblenden.
    result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == "pv-module")
    )
    pv_module = result.scalars().all()

    _empty = PVStringsGesamtlaufzeitResponse(
        anlage_id=anlage_id, hat_prognose=False,
        anlagen_leistung_kwp=anlage.leistung_kwp or 0,
        erstes_jahr=date.today().year, letztes_jahr=date.today().year,
        anzahl_jahre=0, anzahl_monate=0,
        prognose_gesamt_kwh=0, ist_gesamt_kwh=0,
        abweichung_gesamt_kwh=0, abweichung_gesamt_prozent=None,
        strings=[], saisonal_aggregiert=[],
        bester_string=None, schlechtester_string=None,
    )
    if not pv_module:
        return _empty

    wr_ids = [m.parent_investition_id for m in pv_module if m.parent_investition_id]
    wechselrichter_map = {}
    if wr_ids:
        result = await db.execute(select(Investition).where(Investition.id.in_(wr_ids)))
        for wr in result.scalars().all():
            wechselrichter_map[wr.id] = wr.bezeichnung

    result = await db.execute(
        select(PVGISPrognoseModel)
        .where(PVGISPrognoseModel.anlage_id == anlage_id)
        .order_by(PVGISPrognoseModel.abgerufen_am.desc())
        .limit(1)
    )
    prognose = result.scalar_one_or_none()
    hat_prognose = prognose is not None

    prognose_monate = {}
    if prognose and prognose.monatswerte:
        for mw in prognose.monatswerte:
            prognose_monate[mw["monat"]] = mw.get("e_m", 0)

    prognose_per_modul: dict[int, dict[int, float]] = {}
    if prognose and prognose.module_monatswerte:
        for inv_id_str, monatsdaten in prognose.module_monatswerte.items():
            try:
                inv_id = int(inv_id_str)
                prognose_per_modul[inv_id] = {mw["monat"]: mw.get("e_m", 0) for mw in monatsdaten}
            except (ValueError, TypeError):
                pass

    gesamt_kwp = sum(m.leistung_kwp or 0 for m in pv_module)
    if gesamt_kwp == 0:
        gesamt_kwp = anlage.leistung_kwp or 1

    pv_ids = [m.id for m in pv_module]
    result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(pv_ids))
        .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    alle_monatsdaten = result.scalars().all()

    jahre_set = set()
    for imd in alle_monatsdaten:
        jahre_set.add(imd.jahr)
    jahre = sorted(jahre_set)

    if not jahre:
        return _empty

    erstes_jahr = jahre[0]
    letztes_jahr = jahre[-1]
    anzahl_jahre = len(jahre)

    md_by_inv: dict[int, dict[int, dict[int, float]]] = {m.id: {} for m in pv_module}
    for imd in alle_monatsdaten:
        data = imd.verbrauch_daten or {}
        pv_erzeugt = data.get("pv_erzeugung_kwh", 0) or 0
        if imd.investition_id in md_by_inv:
            if imd.jahr not in md_by_inv[imd.investition_id]:
                md_by_inv[imd.investition_id][imd.jahr] = {}
            md_by_inv[imd.investition_id][imd.jahr][imd.monat] = pv_erzeugt

    strings_data = []
    prognose_gesamt_total = 0
    ist_gesamt_total = 0
    saisonal_agg: dict[int, dict] = {m: {"prognose": 0, "ist_summe": 0, "anzahl": 0} for m in range(1, 13)}

    for modul in pv_module:
        modul_kwp = modul.leistung_kwp or 0
        kwp_anteil = modul_kwp / gesamt_kwp if gesamt_kwp > 0 else 0
        params = modul.parameter or {}
        ausrichtung = modul.ausrichtung or params.get("ausrichtung")
        neigung = modul.neigung_grad or params.get("neigung_grad")
        jahreswerte = []
        prognose_string_gesamt = 0
        ist_string_gesamt = 0
        string_saisonal: dict[int, dict] = {m: {"ist_summe": 0, "anzahl": 0} for m in range(1, 13)}
        modul_prognose = prognose_per_modul.get(modul.id)

        for jahr in jahre:
            months_with_data_year = set(md_by_inv.get(modul.id, {}).get(jahr, {}).keys())
            if modul_prognose is not None:
                prognose_jahr = sum(modul_prognose.get(m, 0) for m in months_with_data_year)
            else:
                prognose_jahr = sum(prognose_monate.get(m, 0) for m in months_with_data_year) * kwp_anteil
            ist_jahr = sum(md_by_inv.get(modul.id, {}).get(jahr, {}).get(m, 0) for m in range(1, 13))
            abweichung_pct = ((ist_jahr - prognose_jahr) / prognose_jahr * 100) if prognose_jahr > 0 else None
            perf_ratio = (ist_jahr / prognose_jahr) if prognose_jahr > 0 else None
            jahreswerte.append(PVStringJahreswert(
                jahr=jahr, prognose_kwh=round(prognose_jahr, 1), ist_kwh=round(ist_jahr, 1),
                abweichung_prozent=round(abweichung_pct, 1) if abweichung_pct is not None else None,
                performance_ratio=round(perf_ratio, 3) if perf_ratio is not None else None,
            ))
            prognose_string_gesamt += prognose_jahr
            ist_string_gesamt += ist_jahr
            for monat in range(1, 13):
                ist_monat = md_by_inv.get(modul.id, {}).get(jahr, {}).get(monat, 0)
                if ist_monat > 0 or monat in md_by_inv.get(modul.id, {}).get(jahr, {}):
                    string_saisonal[monat]["ist_summe"] += ist_monat
                    string_saisonal[monat]["anzahl"] += 1

        saisonalwerte = []
        for monat in range(1, 13):
            if modul_prognose is not None:
                prognose_monat = modul_prognose.get(monat, 0)
            else:
                prognose_monat = prognose_monate.get(monat, 0) * kwp_anteil
            ist_summe = string_saisonal[monat]["ist_summe"]
            anzahl = string_saisonal[monat]["anzahl"]
            ist_durchschnitt = ist_summe / anzahl if anzahl > 0 else 0
            saisonalwerte.append(PVStringSaisonalwert(
                monat=monat, monat_name=MONATSNAMEN[monat],
                prognose_kwh=round(prognose_monat, 1),
                ist_durchschnitt_kwh=round(ist_durchschnitt, 1),
                ist_summe_kwh=round(ist_summe, 1), anzahl_jahre=anzahl,
            ))
            saisonal_agg[monat]["prognose"] += prognose_monat
            saisonal_agg[monat]["ist_summe"] += ist_summe
            saisonal_agg[monat]["anzahl"] = max(saisonal_agg[monat]["anzahl"], anzahl)

        abweichung_gesamt_pct = ((ist_string_gesamt - prognose_string_gesamt) / prognose_string_gesamt * 100) if prognose_string_gesamt > 0 else None
        perf_ratio_gesamt = (ist_string_gesamt / prognose_string_gesamt) if prognose_string_gesamt > 0 else None
        spez_ertrag = (ist_string_gesamt / modul_kwp) if modul_kwp > 0 else None
        strings_data.append(PVStringGesamtlaufzeit(
            investition_id=modul.id, bezeichnung=modul.bezeichnung,
            leistung_kwp=modul_kwp, ausrichtung=ausrichtung, neigung_grad=neigung,
            wechselrichter_name=wechselrichter_map.get(modul.parent_investition_id) if modul.parent_investition_id else None,
            prognose_gesamt_kwh=round(prognose_string_gesamt, 1),
            ist_gesamt_kwh=round(ist_string_gesamt, 1),
            abweichung_gesamt_prozent=round(abweichung_gesamt_pct, 1) if abweichung_gesamt_pct is not None else None,
            performance_ratio_gesamt=round(perf_ratio_gesamt, 3) if perf_ratio_gesamt is not None else None,
            spezifischer_ertrag_kwh_kwp=round(spez_ertrag, 0) if spez_ertrag is not None else None,
            jahreswerte=jahreswerte, saisonalwerte=saisonalwerte,
        ))
        prognose_gesamt_total += prognose_string_gesamt
        ist_gesamt_total += ist_string_gesamt

    saisonal_aggregiert = []
    for monat in range(1, 13):
        prognose_s = saisonal_agg[monat]["prognose"]
        ist_summe = saisonal_agg[monat]["ist_summe"]
        anzahl = saisonal_agg[monat]["anzahl"]
        ist_durchschnitt = ist_summe / anzahl if anzahl > 0 else 0
        saisonal_aggregiert.append(PVStringSaisonalwert(
            monat=monat, monat_name=MONATSNAMEN[monat],
            prognose_kwh=round(prognose_s, 1),
            ist_durchschnitt_kwh=round(ist_durchschnitt, 1),
            ist_summe_kwh=round(ist_summe, 1), anzahl_jahre=anzahl,
        ))

    abweichung_gesamt = ist_gesamt_total - prognose_gesamt_total
    abweichung_gesamt_pct = (abweichung_gesamt / prognose_gesamt_total * 100) if prognose_gesamt_total > 0 else None
    strings_with_perf = [(s.bezeichnung, s.performance_ratio_gesamt) for s in strings_data if s.performance_ratio_gesamt]
    bester_string = None
    schlechtester_string = None
    if strings_with_perf:
        strings_sorted = sorted(strings_with_perf, key=lambda x: x[1] or 0, reverse=True)
        bester_string = strings_sorted[0][0]
        schlechtester_string = strings_sorted[-1][0] if len(strings_sorted) > 1 else None

    return PVStringsGesamtlaufzeitResponse(
        anlage_id=anlage_id, hat_prognose=hat_prognose,
        anlagen_leistung_kwp=gesamt_kwp,
        erstes_jahr=erstes_jahr, letztes_jahr=letztes_jahr,
        anzahl_jahre=anzahl_jahre, anzahl_monate=len(alle_monatsdaten),
        prognose_gesamt_kwh=round(prognose_gesamt_total, 1),
        ist_gesamt_kwh=round(ist_gesamt_total, 1),
        abweichung_gesamt_kwh=round(abweichung_gesamt, 1),
        abweichung_gesamt_prozent=round(abweichung_gesamt_pct, 1) if abweichung_gesamt_pct is not None else None,
        strings=strings_data, saisonal_aggregiert=saisonal_aggregiert,
        bester_string=bester_string, schlechtester_string=schlechtester_string,
    )
