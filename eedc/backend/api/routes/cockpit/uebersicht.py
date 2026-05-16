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
from backend.core.investition_parameter import PARAM_E_AUTO, PARAM_WAERMEPUMPE
from backend.core.field_definitions import (
    get_pv_erzeugung_kwh,
    get_sonstiges_verbrauch_kwh,
    get_wp_heizenergie_kwh,
    get_wp_strom_kwh,
)
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
    WP_WIRKUNGSGRAD_GAS_DEFAULT,
)
from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis
from backend.services.eauto_wirtschaftlichkeit import berechne_eauto_ersparnis

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

    # Sonstiges aggregiert (Pool, Sauna, Klima — wenn nicht als WP/Luft-Luft
    # geführt, etc.). Erzeuger und Verbraucher getrennt, weil pro Investition
    # nur eine Seite aktiv ist (siehe inv.parameter.kategorie).
    sonstiges_erzeugung_kwh: float
    sonstiges_verbrauch_kwh: float
    hat_sonstiges: bool

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
    investition_vollkosten_euro: float
    investition_mehrkosten_euro: float
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

    # Investitionen laden — KEIN aktiv-Filter (Issue #123): historische KPIs
    # dürfen später deaktivierte/stillgelegte Komponenten nicht rückwirkend ausblenden.
    inv_query = select(Investition).where(
        Investition.anlage_id == anlage_id,
    )
    inv_result = await db.execute(inv_query)
    investitionen = inv_result.scalars().all()
    inv_by_id = {i.id: i for i in investitionen}

    # Tarife laden (allgemein + Spezialtarife für WP/Wallbox)
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein_tarif = tarife.get("allgemein")
    wp_tarif = tarife.get("waermepumpe")
    wallbox_tarif = tarife.get("wallbox")

    netzbezug_preis_cent = allgemein_tarif.netzbezug_arbeitspreis_cent_kwh if allgemein_tarif else NETZBEZUG_DEFAULT_CENT
    einspeise_verguetung_cent = allgemein_tarif.einspeiseverguetung_cent_kwh if allgemein_tarif else EINSPEISEVERGUETUNG_DEFAULT_CENT
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
    # E-Mobilität: getrennt nach E-Auto (Vehicle-Sicht) und Wallbox (Loadpoint-
    # Sicht) sammeln, danach pro Feld die größere Quelle als Wahrheit + PV ≤
    # Gesamt erzwingen. Identische Logik wie in
    # `aktueller_monat._collect_saved_data` (Commit 92d522a8); ohne diese
    # Trennung würde 1 EAuto + 1 WB mit ähnlich gepflegten Werten doppelt
    # zählen (Joachim/Gernot 2026-05-02). Saubere Trennung pro Fahrzeug folgt
    # in Phase 2 des Wallbox/E-Auto-Konzepts.
    eauto_ladung = 0.0
    eauto_pv_ladung = 0.0
    eauto_km = 0.0
    wb_ladung = 0.0
    wb_pv_ladung = 0.0
    bkw_erzeugung = 0.0
    bkw_eigenverbrauch = 0.0
    sonstiges_erzeugung = 0.0
    sonstiges_verbrauch = 0.0
    sonstige_ertraege_gesamt = 0.0
    sonstige_ausgaben_gesamt = 0.0
    dienstlich_ladekosten_euro = 0.0
    zeitraum_monate = set()

    for imd in all_imd:
        inv = inv_by_id.get(imd.investition_id)
        if not inv:
            continue

        # Issue #153 / #155 / #236: IMD vor anschaffungsdatum / nach
        # stilllegungsdatum überspringen — sonst fließen vor-Inbetriebnahme-
        # bzw. nach-Stilllegungs-Werte in JAZ/Aggregate ein und verfälschen
        # die Cockpit-Übersicht. SoT-Helper statt inline-Check
        # (feedback_aggregations_drift.md).
        if not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
            continue

        data = imd.verbrauch_daten or {}
        zeitraum_monate.add((imd.jahr, imd.monat))

        if inv.typ == "pv-module":
            pv_erzeugung_inv += data.get("pv_erzeugung_kwh", 0) or 0

        if inv.typ == "speicher":
            speicher_ladung += data.get("ladung_kwh", 0) or 0
            speicher_entladung += data.get("entladung_kwh", 0) or 0

        elif inv.typ == "waermepumpe":
            heizung = get_wp_heizenergie_kwh(data)
            warmwasser = data.get("warmwasser_kwh", 0) or 0
            wp_heizung += heizung
            wp_warmwasser += warmwasser
            wp_waerme += data.get("waerme_kwh", 0) or (heizung + warmwasser)
            wp_strom += get_wp_strom_kwh(data, inv.parameter)

        elif inv.typ in ("e-auto", "wallbox"):
            if (inv.parameter or {}).get("ist_dienstlich", False):
                netz_kwh = data.get("ladung_netz_kwh", 0) or 0
                pv_kwh = data.get("ladung_pv_kwh", 0) or 0
                dienstlich_ladekosten_euro += (
                    netz_kwh * wallbox_preis_cent +
                    pv_kwh * einspeise_verguetung_cent
                ) / 100
            elif inv.typ == "e-auto":
                eauto_ladung += (
                    data.get("ladung_kwh", 0) or
                    data.get("verbrauch_kwh", 0) or 0
                )
                eauto_pv_ladung += data.get("ladung_pv_kwh", 0) or 0
                eauto_km += data.get("km_gefahren", 0) or 0
            else:  # wallbox (nicht-dienstlich)
                wb_ladung += data.get("ladung_kwh", 0) or 0
                wb_pv_ladung += data.get("ladung_pv_kwh", 0) or 0

        elif inv.typ == "balkonkraftwerk":
            bkw_kwh = get_pv_erzeugung_kwh(data)
            bkw_erzeugung += bkw_kwh
            bkw_eigenverbrauch += data.get("eigenverbrauch_kwh", 0) or 0
            pv_erzeugung_inv += bkw_kwh

        elif inv.typ == "sonstiges":
            # Pro Investition entweder Erzeuger- oder Verbraucher-Seite
            # (siehe inv.parameter.kategorie) — Werte sind sich gegenseitig
            # ausschließend, beide Felder bleiben bei der jeweils anderen
            # Sicht 0. SoT-Helper liest auch Legacy-Felder mit.
            sonstiges_erzeugung += data.get("erzeugung_kwh", 0) or 0
            sonstiges_verbrauch += get_sonstiges_verbrauch_kwh(data)

        summen = berechne_sonstige_summen(data)
        sonstige_ertraege_gesamt += summen["ertraege_euro"]
        sonstige_ausgaben_gesamt += summen["ausgaben_euro"]

    sonstige_ausgaben_gesamt += dienstlich_ladekosten_euro

    # E-Mobilitäts-Pool: pro Feld die größere Quelle gewinnt (analog zu
    # `aktueller_monat._collect_saved_data`). Wallbox liefert üblicherweise
    # Loadpoint-Wahrheit, E-Auto die Vehicle-Sicht; ist nur eine gepflegt,
    # gewinnt sie automatisch. PV ≤ Gesamt erzwingen.
    emob_ladung = max(eauto_ladung, wb_ladung)
    emob_pv_ladung = max(eauto_pv_ladung, wb_pv_ladung)
    if emob_pv_ladung > emob_ladung:
        emob_pv_ladung = emob_ladung
    emob_km = eauto_km

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

    # Anlagenleistung aus Investitionen (nur aktive — stillgelegte nicht mitzählen)
    today = date.today()
    anlagenleistung_kwp = 0.0
    for inv in investitionen:
        if not inv.ist_aktiv_an(today):
            continue
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

    # Komponenten-Flags und Berechnungen (nur aktive Investitionen)
    speicher_invs = [i for i in investitionen if i.typ == "speicher" and i.ist_aktiv_an(today)]
    hat_speicher = len(speicher_invs) > 0
    speicher_kapazitaet = sum(
        (i.parameter or {}).get("kapazitaet_kwh", 0) for i in speicher_invs
    )
    speicher_effizienz = (speicher_entladung / speicher_ladung * 100) if speicher_ladung > 0 else None
    speicher_vollzyklen = (speicher_ladung / speicher_kapazitaet) if speicher_kapazitaet > 0 else None

    wp_invs = [i for i in investitionen if i.typ == "waermepumpe" and i.ist_aktiv_an(today)]
    hat_waermepumpe = len(wp_invs) > 0
    # JAZ/COP nur wenn beide Seiten gemessen sind. Bei Split-Klimaanlagen
    # (wp_art="luft_luft") ist Wärmemengenzähler typischerweise nicht
    # vorhanden → wp_waerme=0 obwohl Stromverbrauch läuft. Heute lieferte
    # die Formel dann 0.0 (irreführende JAZ), jetzt None ("—" im UI).
    wp_cop = (wp_waerme / wp_strom) if wp_strom > 0 and wp_waerme > 0 else None
    # Multi-WP: erste WP als Parameter-Referenz (Wirkungsgrad/Gas-Default).
    # Drift-Audit Domäne A1 / Issue #178: vorher 10ct hartcodiert + ignorierte
    # User-Param `alter_preis_cent_kwh`.
    wp_ref_parameter = wp_invs[0].parameter if wp_invs else None
    wp_ersparnis_result = berechne_wp_ersparnis(
        wp_waerme_kwh=wp_waerme,
        wp_strom_kwh=wp_strom,
        wp_strompreis_cent=wp_preis_cent,
        wp_parameter=wp_ref_parameter,
    )
    wp_ersparnis = wp_ersparnis_result.ersparnis_euro

    emob_invs = [
        i for i in investitionen
        if i.typ in ("e-auto", "wallbox")
        and i.ist_aktiv_an(today)
        and not (i.parameter or {}).get("ist_dienstlich", False)
    ]
    hat_emobilitaet = len(emob_invs) > 0
    emob_pv_anteil = (emob_pv_ladung / emob_ladung * 100) if emob_ladung > 0 else None
    # Drift-Audit Domäne A2: vorher 7 L/100km + 1,80 €/L hartcodiert.
    # Multi-E-Auto: erste Investition als Parameter-Referenz.
    emob_ref_parameter = emob_invs[0].parameter if emob_invs else None
    emob_result = berechne_eauto_ersparnis(
        km_gefahren=emob_km,
        ladung_netz_kwh=emob_ladung - emob_pv_ladung,
        ladung_extern_euro=0.0,  # Cockpit-Übersicht aggregiert über Heim-Ladung
        wallbox_strompreis_cent=wallbox_preis_cent,
        eauto_parameter=emob_ref_parameter,
    )
    emob_ersparnis = emob_result.ersparnis_euro
    benzin_verbrauch = (emob_km / 100) * emob_result.verwendeter_verbrauch_l_100km

    bkw_invs = [i for i in investitionen if i.typ == "balkonkraftwerk" and i.ist_aktiv_an(today)]
    hat_balkonkraftwerk = len(bkw_invs) > 0

    sonstiges_invs = [i for i in investitionen if i.typ == "sonstiges" and i.ist_aktiv_an(today)]
    hat_sonstiges = len(sonstiges_invs) > 0

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
        m_preis_cent = m_allgemein.netzbezug_arbeitspreis_cent_kwh if m_allgemein else NETZBEZUG_DEFAULT_CENT
        m_grundpreis = (m_allgemein.grundpreis_euro_monat or 0) if m_allgemein else 0
        m_einspeis_cent = m_allgemein.einspeiseverguetung_cent_kwh if m_allgemein else EINSPEISEVERGUETUNG_DEFAULT_CENT
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
                alternativ_kosten = inv.parameter.get(PARAM_WAERMEPUMPE["ALTERNATIV_KOSTEN_EURO"], 8000.0)
            investition_wp_mehrkosten += max(0, kosten - alternativ_kosten)
        elif inv.typ == "e-auto":
            alternativ_kosten = 35000.0
            if inv.parameter:
                alternativ_kosten = inv.parameter.get(PARAM_E_AUTO["ALTERNATIV_KOSTEN_EURO"], 35000.0)
            investition_eauto_mehrkosten += max(0, kosten - alternativ_kosten)
        else:
            investition_sonstige += kosten
    investition_gesamt = (
        investition_pv_system + investition_wp_mehrkosten +
        investition_eauto_mehrkosten + investition_sonstige
    )
    if investition_gesamt <= 0:
        investition_gesamt = sum(i.anschaffungskosten_gesamt or 0 for i in investitionen)

    investition_vollkosten = sum(i.anschaffungskosten_gesamt or 0 for i in investitionen)
    investition_mehrkosten = sum(
        max(0, (i.anschaffungskosten_gesamt or 0) - (i.anschaffungskosten_alternativ or 0))
        for i in investitionen
    )

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
    co2_wp = (wp_waerme / WP_WIRKUNGSGRAD_GAS_DEFAULT * CO2_FAKTOR_GAS_KG_KWH) - (wp_strom * CO2_FAKTOR_STROM_KG_KWH) if wp_waerme > 0 else 0
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
        sonstiges_erzeugung_kwh=round(sonstiges_erzeugung, 1),
        sonstiges_verbrauch_kwh=round(sonstiges_verbrauch, 1),
        hat_sonstiges=hat_sonstiges,
        einspeise_erloes_euro=round(einspeise_erloes, 2),
        ev_ersparnis_euro=round(ev_ersparnis, 2),
        netzbezug_kosten_euro=round(netzbezug_kosten, 2),
        ust_eigenverbrauch_euro=round(ust_eigenverbrauch, 2) if ust_eigenverbrauch > 0 else None,
        netto_ertrag_euro=round(netto_ertrag, 2),
        bkw_ersparnis_euro=round(bkw_ersparnis, 2),
        sonstige_netto_euro=round(sonstige_netto, 2),
        jahres_rendite_prozent=round(roi_fortschritt, 1) if roi_fortschritt else None,
        investition_gesamt_euro=round(investition_gesamt, 2),
        investition_vollkosten_euro=round(investition_vollkosten, 2),
        investition_mehrkosten_euro=round(investition_mehrkosten, 2),
        steuerliche_behandlung=steuerliche_beh if steuerliche_beh != "keine_ust" else None,
        co2_pv_kg=round(co2_pv, 1),
        co2_wp_kg=round(co2_wp, 1),
        co2_emob_kg=round(co2_emob, 1),
        co2_gesamt_kg=round(co2_gesamt, 1),
        anzahl_monate=anzahl_monate,
        zeitraum_von=zeitraum_von,
        zeitraum_bis=zeitraum_bis,
    )
