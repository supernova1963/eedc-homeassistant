"""
Cockpit Übersicht — Aggregierte KPI-Übersicht für eine Anlage.
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.models.monatsdaten import Monatsdaten
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.api.routes.strompreise import lade_tarife_fuer_anlage, resolve_netzbezug_preis_cent
from backend.core.calculations import (
    CO2_FAKTOR_STROM_KG_KWH, CO2_FAKTOR_GAS_KG_KWH,
    CO2_FAKTOR_BENZIN_KG_LITER, berechne_ust_eigenverbrauch,
)
from backend.utils.sonstige_positionen import berechne_sonstige_summen

router = APIRouter()


class CockpitUebersichtResponse(BaseModel):
    """Aggregierte Cockpit-Übersicht."""

    # Energie-Bilanz (kWh)
    pv_erzeugung_kwh: float
    gesamtverbrauch_kwh: float
    netzbezug_kwh: float
    einspeisung_kwh: float
    direktverbrauch_kwh: float
    eigenverbrauch_kwh: float

    # Quoten (%)
    autarkie_prozent: float
    eigenverbrauch_quote_prozent: float
    direktverbrauch_quote_prozent: float
    spezifischer_ertrag_kwh_kwp: Optional[float]
    anlagenleistung_kwp: float

    # Speicher aggregiert
    speicher_ladung_kwh: float
    speicher_entladung_kwh: float
    speicher_effizienz_prozent: Optional[float]
    speicher_vollzyklen: Optional[float]
    speicher_kapazitaet_kwh: float
    hat_speicher: bool

    # Wärmepumpe aggregiert
    wp_waerme_kwh: float
    wp_strom_kwh: float
    wp_heizung_kwh: float
    wp_warmwasser_kwh: float
    wp_cop: Optional[float]
    wp_ersparnis_euro: float
    hat_waermepumpe: bool

    # E-Mobilität aggregiert (E-Auto + Wallbox)
    emob_km: float
    emob_ladung_kwh: float
    emob_pv_anteil_prozent: Optional[float]
    emob_ersparnis_euro: float
    hat_emobilitaet: bool

    # Balkonkraftwerk aggregiert
    bkw_erzeugung_kwh: float
    bkw_eigenverbrauch_kwh: float
    hat_balkonkraftwerk: bool

    # Finanzen (Euro)
    einspeise_erloes_euro: float
    ev_ersparnis_euro: float
    netzbezug_kosten_euro: float = 0
    ust_eigenverbrauch_euro: Optional[float] = None
    netto_ertrag_euro: float
    bkw_ersparnis_euro: float = 0
    sonstige_netto_euro: float = 0
    jahres_rendite_prozent: Optional[float]
    investition_gesamt_euro: float
    steuerliche_behandlung: Optional[str] = None

    # Umwelt (kg CO2)
    co2_pv_kg: float
    co2_wp_kg: float
    co2_emob_kg: float
    co2_gesamt_kg: float

    # Meta
    anzahl_monate: int
    zeitraum_von: Optional[str]
    zeitraum_bis: Optional[str]


@router.get("/uebersicht/{anlage_id}", response_model=CockpitUebersichtResponse)
async def get_cockpit_uebersicht(
    anlage_id: int,
    jahr: Optional[int] = Query(None, description="Filter nach Jahr (leer = alle)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Aggregierte Cockpit-Übersicht für eine Anlage.

    Berechnet alle KPIs über den gesamten Zeitraum oder ein einzelnes Jahr.

    Datenquellen:
    - Monatsdaten: NUR für Anlagen-Energiebilanz (einspeisung, netzbezug)
    - InvestitionMonatsdaten: ALLE Komponenten-Details (Speicher, WP, E-Auto, PV-Strings, etc.)
    """
    # Anlage laden
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Investitionen laden
    inv_query = select(Investition).where(
        Investition.anlage_id == anlage_id,
        Investition.aktiv == True
    )
    inv_result = await db.execute(inv_query)
    investitionen = inv_result.scalars().all()
    inv_by_id = {i.id: i for i in investitionen}

    # Tarife laden (allgemein + Spezialtarife für WP/Wallbox)
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein_tarif = tarife.get("allgemein")
    wp_tarif = tarife.get("waermepumpe")
    wallbox_tarif = tarife.get("wallbox")

    netzbezug_preis_cent = allgemein_tarif.netzbezug_arbeitspreis_cent_kwh if allgemein_tarif else 30.0
    einspeise_verguetung_cent = allgemein_tarif.einspeiseverguetung_cent_kwh if allgemein_tarif else 8.2
    wp_preis_cent = wp_tarif.netzbezug_arbeitspreis_cent_kwh if wp_tarif else netzbezug_preis_cent
    wallbox_preis_cent = wallbox_tarif.netzbezug_arbeitspreis_cent_kwh if wallbox_tarif else netzbezug_preis_cent

    # Alle InvestitionMonatsdaten laden (eine Query für alle!)
    all_inv_ids = [i.id for i in investitionen]
    imd_query = select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id.in_(all_inv_ids)
    ) if all_inv_ids else None

    if jahr and imd_query is not None:
        imd_query = imd_query.where(InvestitionMonatsdaten.jahr == jahr)

    all_imd = []
    if imd_query is not None:
        imd_result = await db.execute(imd_query)
        all_imd = imd_result.scalars().all()

    # Daten aus InvestitionMonatsdaten aggregieren
    pv_erzeugung_inv = 0.0
    speicher_ladung = 0.0
    speicher_entladung = 0.0
    wp_waerme = 0.0
    wp_strom = 0.0
    wp_heizung = 0.0
    wp_warmwasser = 0.0
    emob_km = 0.0
    emob_ladung = 0.0
    emob_pv_ladung = 0.0
    bkw_erzeugung = 0.0
    bkw_eigenverbrauch = 0.0
    sonstige_ertraege_gesamt = 0.0
    sonstige_ausgaben_gesamt = 0.0
    dienstlich_ladekosten_euro = 0.0
    zeitraum_monate = set()

    for imd in all_imd:
        inv = inv_by_id.get(imd.investition_id)
        if not inv:
            continue

        data = imd.verbrauch_daten or {}
        zeitraum_monate.add((imd.jahr, imd.monat))

        if inv.typ == "pv-module":
            pv_erzeugung_inv += data.get("pv_erzeugung_kwh", 0) or 0

        if inv.typ == "speicher":
            speicher_ladung += data.get("ladung_kwh", 0) or 0
            speicher_entladung += data.get("entladung_kwh", 0) or 0

        elif inv.typ == "waermepumpe":
            heizung = data.get("heizenergie_kwh", 0) or data.get("heizung_kwh", 0) or 0
            warmwasser = data.get("warmwasser_kwh", 0) or 0
            wp_heizung += heizung
            wp_warmwasser += warmwasser
            wp_waerme += data.get("waerme_kwh", 0) or (heizung + warmwasser)
            wp_strom += (
                data.get("stromverbrauch_kwh", 0) or
                data.get("strom_kwh", 0) or
                data.get("verbrauch_kwh", 0) or 0
            )

        elif inv.typ in ("e-auto", "wallbox"):
            if (inv.parameter or {}).get("ist_dienstlich", False):
                netz_kwh = data.get("ladung_netz_kwh", 0) or 0
                pv_kwh = data.get("ladung_pv_kwh", 0) or 0
                dienstlich_ladekosten_euro += (
                    netz_kwh * wallbox_preis_cent +
                    pv_kwh * einspeise_verguetung_cent
                ) / 100
            else:
                emob_km += data.get("km_gefahren", 0) or 0
                emob_ladung += (
                    data.get("ladung_kwh", 0) or
                    data.get("verbrauch_kwh", 0) or 0
                )
                emob_pv_ladung += data.get("ladung_pv_kwh", 0) or 0

        elif inv.typ == "balkonkraftwerk":
            bkw_kwh = data.get("pv_erzeugung_kwh", 0) or data.get("erzeugung_kwh", 0) or 0
            bkw_erzeugung += bkw_kwh
            bkw_eigenverbrauch += data.get("eigenverbrauch_kwh", 0) or 0
            pv_erzeugung_inv += bkw_kwh

        summen = berechne_sonstige_summen(data)
        sonstige_ertraege_gesamt += summen["ertraege_euro"]
        sonstige_ausgaben_gesamt += summen["ausgaben_euro"]

    sonstige_ausgaben_gesamt += dienstlich_ladekosten_euro

    # Monatsdaten NUR für Anlagen-Energiebilanz
    md_query = select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    if jahr:
        md_query = md_query.where(Monatsdaten.jahr == jahr)
    md_query = md_query.order_by(Monatsdaten.jahr, Monatsdaten.monat)

    md_result = await db.execute(md_query)
    monatsdaten_list = md_result.scalars().all()

    einspeisung = sum(m.einspeisung_kwh or 0 for m in monatsdaten_list)
    netzbezug = sum(m.netzbezug_kwh or 0 for m in monatsdaten_list)

    pv_erzeugung_md = sum(m.pv_erzeugung_kwh or 0 for m in monatsdaten_list)
    pv_erzeugung = pv_erzeugung_inv if pv_erzeugung_inv > 0 else pv_erzeugung_md

    direktverbrauch = max(0, pv_erzeugung - einspeisung - speicher_ladung) if pv_erzeugung > 0 else 0
    eigenverbrauch = direktverbrauch + speicher_entladung
    gesamtverbrauch = eigenverbrauch + netzbezug

    autarkie = (eigenverbrauch / gesamtverbrauch * 100) if gesamtverbrauch > 0 else 0
    ev_quote = min(eigenverbrauch / pv_erzeugung * 100, 100) if pv_erzeugung > 0 else 0
    dv_quote = (direktverbrauch / pv_erzeugung * 100) if pv_erzeugung > 0 else 0

    # Anlagenleistung aus Investitionen
    anlagenleistung_kwp = 0.0
    for inv in investitionen:
        if inv.typ == "pv-module" and inv.leistung_kwp:
            anlagenleistung_kwp += inv.leistung_kwp
        elif inv.typ == "balkonkraftwerk":
            if inv.leistung_kwp:
                anlagenleistung_kwp += inv.leistung_kwp
            else:
                params = inv.parameter or {}
                bkw_anzahl = params.get("anzahl", 1) or 1
                anlagenleistung_kwp += params.get("leistung_wp", 0) * bkw_anzahl / 1000

    if anlagenleistung_kwp == 0 and anlage.leistung_kwp:
        anlagenleistung_kwp = anlage.leistung_kwp

    spez_ertrag = (pv_erzeugung / anlagenleistung_kwp) if anlagenleistung_kwp > 0 else None

    # Komponenten-Flags und Berechnungen
    speicher_invs = [i for i in investitionen if i.typ == "speicher"]
    hat_speicher = len(speicher_invs) > 0
    speicher_kapazitaet = sum(
        (i.parameter or {}).get("kapazitaet_kwh", 0) for i in speicher_invs
    )
    speicher_effizienz = (speicher_entladung / speicher_ladung * 100) if speicher_ladung > 0 else None
    speicher_vollzyklen = (speicher_ladung / speicher_kapazitaet) if speicher_kapazitaet > 0 else None

    wp_invs = [i for i in investitionen if i.typ == "waermepumpe"]
    hat_waermepumpe = len(wp_invs) > 0
    wp_cop = (wp_waerme / wp_strom) if wp_strom > 0 else None
    gas_preis_cent = 10.0
    wp_ersparnis = ((wp_waerme / 0.9 * gas_preis_cent) - (wp_strom * wp_preis_cent)) / 100 if wp_waerme > 0 else 0

    emob_invs = [
        i for i in investitionen
        if i.typ in ("e-auto", "wallbox")
        and not (i.parameter or {}).get("ist_dienstlich", False)
    ]
    hat_emobilitaet = len(emob_invs) > 0
    emob_pv_anteil = (emob_pv_ladung / emob_ladung * 100) if emob_ladung > 0 else None
    benzin_verbrauch = emob_km * 7 / 100
    benzin_kosten = benzin_verbrauch * 1.80
    strom_kosten = (emob_ladung - emob_pv_ladung) * wallbox_preis_cent / 100
    emob_ersparnis = benzin_kosten - strom_kosten if emob_km > 0 else 0

    bkw_invs = [i for i in investitionen if i.typ == "balkonkraftwerk"]
    hat_balkonkraftwerk = len(bkw_invs) > 0

    # Finanzen
    _tarif_cache: dict[date, dict] = {}

    async def _tarif_fuer_monat(m: Monatsdaten) -> dict:
        stichtag = date(m.jahr, m.monat, 1)
        if stichtag not in _tarif_cache:
            _tarif_cache[stichtag] = await lade_tarife_fuer_anlage(db, anlage_id, target_date=stichtag)
        return _tarif_cache[stichtag]

    gew_preis_sum = 0.0
    gew_kwh_sum = 0.0
    netzbezug_kosten = 0.0
    einspeise_erloes_sum = 0.0

    for m in monatsdaten_list:
        m_tarife = await _tarif_fuer_monat(m)
        m_allgemein = m_tarife.get("allgemein")
        m_preis_cent = m_allgemein.netzbezug_arbeitspreis_cent_kwh if m_allgemein else 30.0
        m_grundpreis = (m_allgemein.grundpreis_euro_monat or 0) if m_allgemein else 0
        m_einspeis_cent = m_allgemein.einspeiseverguetung_cent_kwh if m_allgemein else 8.2
        eff_preis = resolve_netzbezug_preis_cent(m, m_preis_cent)
        kwh = m.netzbezug_kwh or 0
        gew_preis_sum += eff_preis * kwh
        gew_kwh_sum += kwh
        netzbezug_kosten += kwh * eff_preis / 100 + m_grundpreis
        einspeise_erloes_sum += (m.einspeisung_kwh or 0) * m_einspeis_cent / 100

    eff_netzbezug_preis = gew_preis_sum / gew_kwh_sum if gew_kwh_sum > 0 else netzbezug_preis_cent

    einspeise_erloes = einspeise_erloes_sum
    ev_ersparnis = eigenverbrauch * eff_netzbezug_preis / 100
    netto_ertrag = einspeise_erloes + ev_ersparnis

    PV_RELEVANTE_TYPEN = ["pv-module", "wechselrichter", "speicher", "wallbox", "balkonkraftwerk"]
    investition_pv_system = 0.0
    investition_wp_mehrkosten = 0.0
    investition_eauto_mehrkosten = 0.0
    investition_sonstige = 0.0
    for inv in investitionen:
        kosten = inv.anschaffungskosten_gesamt or 0
        if inv.typ in PV_RELEVANTE_TYPEN:
            investition_pv_system += kosten
        elif inv.typ == "waermepumpe":
            alternativ_kosten = 8000.0
            if inv.parameter:
                alternativ_kosten = inv.parameter.get("alternativ_kosten_euro", 8000.0)
            investition_wp_mehrkosten += max(0, kosten - alternativ_kosten)
        elif inv.typ == "e-auto":
            alternativ_kosten = 35000.0
            if inv.parameter:
                alternativ_kosten = inv.parameter.get("alternativ_kosten_euro", 35000.0)
            investition_eauto_mehrkosten += max(0, kosten - alternativ_kosten)
        else:
            investition_sonstige += kosten
    investition_gesamt = (
        investition_pv_system + investition_wp_mehrkosten +
        investition_eauto_mehrkosten + investition_sonstige
    )
    if investition_gesamt <= 0:
        investition_gesamt = sum(i.anschaffungskosten_gesamt or 0 for i in investitionen)

    betriebskosten_ges = sum(i.betriebskosten_jahr or 0 for i in investitionen)

    ust_eigenverbrauch = 0.0
    steuerliche_beh = getattr(anlage, 'steuerliche_behandlung', None) or 'keine_ust'
    if steuerliche_beh == "regelbesteuerung":
        _ust = getattr(anlage, 'ust_satz_prozent', None)
        ust_eigenverbrauch = berechne_ust_eigenverbrauch(
            eigenverbrauch_kwh=eigenverbrauch,
            investition_gesamt_euro=investition_gesamt,
            betriebskosten_jahr_euro=betriebskosten_ges,
            pv_erzeugung_jahr_kwh=pv_erzeugung,
            ust_satz_prozent=_ust if _ust is not None else 19.0,
        )
        netto_ertrag -= ust_eigenverbrauch

    bkw_ersparnis = bkw_eigenverbrauch * eff_netzbezug_preis / 100
    sonstige_netto = sonstige_ertraege_gesamt - sonstige_ausgaben_gesamt

    # CO2-Bilanz
    co2_pv = eigenverbrauch * CO2_FAKTOR_STROM_KG_KWH
    co2_wp = (wp_waerme / 0.9 * CO2_FAKTOR_GAS_KG_KWH) - (wp_strom * CO2_FAKTOR_STROM_KG_KWH) if wp_waerme > 0 else 0
    co2_emob = (benzin_verbrauch * CO2_FAKTOR_BENZIN_KG_LITER) - ((emob_ladung - emob_pv_ladung) * CO2_FAKTOR_STROM_KG_KWH) if emob_km > 0 else 0
    co2_gesamt = co2_pv + max(0, co2_wp) + max(0, co2_emob)

    # Zeitraum
    zeitraum_von = None
    zeitraum_bis = None
    anzahl_monate = 0
    alle_monate: set[tuple[int, int]] = set(zeitraum_monate)
    for md in monatsdaten_list:
        alle_monate.add((md.jahr, md.monat))

    if alle_monate:
        sorted_alle = sorted(alle_monate)
        first = sorted_alle[0]
        last = sorted_alle[-1]
        zeitraum_von = f"{first[0]}-{first[1]:02d}"
        zeitraum_bis = f"{last[0]}-{last[1]:02d}"
        anzahl_monate = len(alle_monate)

    betriebskosten_zeitraum = betriebskosten_ges * anzahl_monate / 12 if anzahl_monate > 0 else 0
    kumulative_ersparnis = netto_ertrag + wp_ersparnis + emob_ersparnis + bkw_ersparnis + sonstige_netto - betriebskosten_zeitraum
    roi_fortschritt = (kumulative_ersparnis / investition_gesamt * 100) if investition_gesamt > 0 else None

    return CockpitUebersichtResponse(
        pv_erzeugung_kwh=round(pv_erzeugung, 1),
        gesamtverbrauch_kwh=round(gesamtverbrauch, 1),
        netzbezug_kwh=round(netzbezug, 1),
        einspeisung_kwh=round(einspeisung, 1),
        direktverbrauch_kwh=round(direktverbrauch, 1),
        eigenverbrauch_kwh=round(eigenverbrauch, 1),
        autarkie_prozent=round(autarkie, 1),
        eigenverbrauch_quote_prozent=round(ev_quote, 1),
        direktverbrauch_quote_prozent=round(dv_quote, 1),
        spezifischer_ertrag_kwh_kwp=round(spez_ertrag, 1) if spez_ertrag else None,
        anlagenleistung_kwp=round(anlagenleistung_kwp, 2),
        speicher_ladung_kwh=round(speicher_ladung, 1),
        speicher_entladung_kwh=round(speicher_entladung, 1),
        speicher_effizienz_prozent=round(speicher_effizienz, 1) if speicher_effizienz else None,
        speicher_vollzyklen=round(speicher_vollzyklen, 1) if speicher_vollzyklen else None,
        speicher_kapazitaet_kwh=round(speicher_kapazitaet, 1),
        hat_speicher=hat_speicher,
        wp_waerme_kwh=round(wp_waerme, 1),
        wp_strom_kwh=round(wp_strom, 1),
        wp_heizung_kwh=round(wp_heizung, 1),
        wp_warmwasser_kwh=round(wp_warmwasser, 1),
        wp_cop=round(wp_cop, 2) if wp_cop else None,
        wp_ersparnis_euro=round(wp_ersparnis, 2),
        hat_waermepumpe=hat_waermepumpe,
        emob_km=round(emob_km, 0),
        emob_ladung_kwh=round(emob_ladung, 1),
        emob_pv_anteil_prozent=round(emob_pv_anteil, 1) if emob_pv_anteil else None,
        emob_ersparnis_euro=round(emob_ersparnis, 2),
        hat_emobilitaet=hat_emobilitaet,
        bkw_erzeugung_kwh=round(bkw_erzeugung, 1),
        bkw_eigenverbrauch_kwh=round(bkw_eigenverbrauch, 1),
        hat_balkonkraftwerk=hat_balkonkraftwerk,
        einspeise_erloes_euro=round(einspeise_erloes, 2),
        ev_ersparnis_euro=round(ev_ersparnis, 2),
        netzbezug_kosten_euro=round(netzbezug_kosten, 2),
        ust_eigenverbrauch_euro=round(ust_eigenverbrauch, 2) if ust_eigenverbrauch > 0 else None,
        netto_ertrag_euro=round(netto_ertrag, 2),
        bkw_ersparnis_euro=round(bkw_ersparnis, 2),
        sonstige_netto_euro=round(sonstige_netto, 2),
        jahres_rendite_prozent=round(roi_fortschritt, 1) if roi_fortschritt else None,
        investition_gesamt_euro=round(investition_gesamt, 2),
        steuerliche_behandlung=steuerliche_beh if steuerliche_beh != "keine_ust" else None,
        co2_pv_kg=round(co2_pv, 1),
        co2_wp_kg=round(co2_wp, 1),
        co2_emob_kg=round(co2_emob, 1),
        co2_gesamt_kg=round(co2_gesamt, 1),
        anzahl_monate=anzahl_monate,
        zeitraum_von=zeitraum_von,
        zeitraum_bis=zeitraum_bis,
    )
