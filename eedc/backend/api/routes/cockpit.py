"""
Cockpit API Routes

Aggregierte Übersicht aller Komponenten für das Cockpit-Dashboard.
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.models.monatsdaten import Monatsdaten
from backend.models.anlage import Anlage
from backend.models.strompreis import Strompreis
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.core.calculations import CO2_FAKTOR_STROM_KG_KWH, CO2_FAKTOR_GAS_KG_KWH, CO2_FAKTOR_BENZIN_KG_LITER
from backend.models.pvgis_prognose import PVGISPrognose as PVGISPrognoseModel


# =============================================================================
# Pydantic Schemas
# =============================================================================

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
    netto_ertrag_euro: float
    roi_fortschritt_prozent: Optional[float]
    investition_gesamt_euro: float

    # Umwelt (kg CO2)
    co2_pv_kg: float
    co2_wp_kg: float
    co2_emob_kg: float
    co2_gesamt_kg: float

    # Meta
    anzahl_monate: int
    zeitraum_von: Optional[str]
    zeitraum_bis: Optional[str]


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


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

    # Aktuellen Strompreis laden
    preis_query = select(Strompreis).where(
        Strompreis.anlage_id == anlage_id
    ).order_by(Strompreis.gueltig_ab.desc()).limit(1)
    preis_result = await db.execute(preis_query)
    strompreis = preis_result.scalar_one_or_none()

    # Default-Preise falls nicht konfiguriert
    netzbezug_preis_cent = strompreis.netzbezug_arbeitspreis_cent_kwh if strompreis else 30.0
    einspeise_verguetung_cent = strompreis.einspeiseverguetung_cent_kwh if strompreis else 8.2

    # ==========================================================================
    # Alle InvestitionMonatsdaten laden (eine Query für alle!)
    # ==========================================================================

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

    # ==========================================================================
    # Daten aus InvestitionMonatsdaten aggregieren
    # ==========================================================================

    # Initialisierung
    pv_erzeugung_inv = 0.0  # aus PV-Module InvestitionMonatsdaten
    speicher_ladung = 0.0
    speicher_entladung = 0.0
    wp_waerme = 0.0
    wp_strom = 0.0
    emob_km = 0.0
    emob_ladung = 0.0
    emob_pv_ladung = 0.0
    bkw_erzeugung = 0.0
    bkw_eigenverbrauch = 0.0

    # Zeitraum aus InvestitionMonatsdaten ermitteln
    zeitraum_monate = set()

    for imd in all_imd:
        inv = inv_by_id.get(imd.investition_id)
        if not inv:
            continue

        data = imd.verbrauch_daten or {}
        zeitraum_monate.add((imd.jahr, imd.monat))

        if inv.typ == "pv-module":
            pv_erzeugung_inv += data.get("pv_erzeugung_kwh", 0) or 0

        elif inv.typ == "speicher":
            speicher_ladung += data.get("ladung_kwh", 0) or 0
            speicher_entladung += data.get("entladung_kwh", 0) or 0

        elif inv.typ == "waermepumpe":
            wp_waerme += (
                data.get("waerme_kwh", 0) or
                (data.get("heizenergie_kwh", 0) or data.get("heizung_kwh", 0)) +
                (data.get("warmwasser_kwh", 0) or 0)
            )
            wp_strom += (
                data.get("stromverbrauch_kwh", 0) or
                data.get("strom_kwh", 0) or
                data.get("verbrauch_kwh", 0) or 0
            )

        elif inv.typ in ("e-auto", "wallbox"):
            emob_km += data.get("km_gefahren", 0) or 0
            emob_ladung += (
                data.get("ladung_kwh", 0) or
                data.get("verbrauch_kwh", 0) or 0
            )
            emob_pv_ladung += data.get("ladung_pv_kwh", 0) or 0

        elif inv.typ == "balkonkraftwerk":
            bkw_erzeugung += data.get("pv_erzeugung_kwh", 0) or data.get("erzeugung_kwh", 0) or 0
            bkw_eigenverbrauch += data.get("eigenverbrauch_kwh", 0) or 0

    # ==========================================================================
    # Monatsdaten NUR für Anlagen-Energiebilanz (Einspeisung, Netzbezug)
    # ==========================================================================

    md_query = select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    if jahr:
        md_query = md_query.where(Monatsdaten.jahr == jahr)
    md_query = md_query.order_by(Monatsdaten.jahr, Monatsdaten.monat)

    md_result = await db.execute(md_query)
    monatsdaten_list = md_result.scalars().all()

    # Kern-Energiebilanz aus Monatsdaten (das sind Zähler-Werte!)
    einspeisung = sum(m.einspeisung_kwh or 0 for m in monatsdaten_list)
    netzbezug = sum(m.netzbezug_kwh or 0 for m in monatsdaten_list)

    # PV-Erzeugung: Bevorzuge InvestitionMonatsdaten, Fallback auf Monatsdaten
    pv_erzeugung_md = sum(m.pv_erzeugung_kwh or 0 for m in monatsdaten_list)
    pv_erzeugung = pv_erzeugung_inv if pv_erzeugung_inv > 0 else pv_erzeugung_md

    # Berechnete Werte (basierend auf korrekten Speicher-Daten aus InvestitionMonatsdaten)
    direktverbrauch = max(0, pv_erzeugung - einspeisung - speicher_ladung) if pv_erzeugung > 0 else 0
    eigenverbrauch = direktverbrauch + speicher_entladung
    gesamtverbrauch = eigenverbrauch + netzbezug

    # Quoten berechnen
    autarkie = (eigenverbrauch / gesamtverbrauch * 100) if gesamtverbrauch > 0 else 0
    ev_quote = (eigenverbrauch / pv_erzeugung * 100) if pv_erzeugung > 0 else 0
    dv_quote = (direktverbrauch / pv_erzeugung * 100) if pv_erzeugung > 0 else 0

    # ==========================================================================
    # Anlagenleistung aus Investitionen
    # ==========================================================================

    anlagenleistung_kwp = 0.0
    for inv in investitionen:
        if inv.typ == "pv-module" and inv.leistung_kwp:
            anlagenleistung_kwp += inv.leistung_kwp
        elif inv.typ == "balkonkraftwerk":
            params = inv.parameter or {}
            bkw_leistung = params.get("leistung_wp", 0) / 1000
            anlagenleistung_kwp += bkw_leistung

    # Fallback auf Anlage.leistung_kwp wenn keine PV-Module als Investitionen
    if anlagenleistung_kwp == 0 and anlage.leistung_kwp:
        anlagenleistung_kwp = anlage.leistung_kwp

    spez_ertrag = (pv_erzeugung / anlagenleistung_kwp) if anlagenleistung_kwp > 0 else None

    # ==========================================================================
    # Komponenten-Flags und Berechnungen
    # ==========================================================================

    # Speicher
    speicher_invs = [i for i in investitionen if i.typ == "speicher"]
    hat_speicher = len(speicher_invs) > 0
    speicher_kapazitaet = sum(
        (i.parameter or {}).get("kapazitaet_kwh", 0)
        for i in speicher_invs
    )
    speicher_effizienz = (speicher_entladung / speicher_ladung * 100) if speicher_ladung > 0 else None
    speicher_vollzyklen = (speicher_ladung / speicher_kapazitaet) if speicher_kapazitaet > 0 else None

    # Wärmepumpe
    wp_invs = [i for i in investitionen if i.typ == "waermepumpe"]
    hat_waermepumpe = len(wp_invs) > 0
    wp_cop = (wp_waerme / wp_strom) if wp_strom > 0 else None
    gas_preis_cent = 10.0
    wp_ersparnis = ((wp_waerme / 0.9 * gas_preis_cent) - (wp_strom * netzbezug_preis_cent)) / 100 if wp_waerme > 0 else 0

    # E-Mobilität
    emob_invs = [i for i in investitionen if i.typ in ("e-auto", "wallbox")]
    hat_emobilitaet = len(emob_invs) > 0
    emob_pv_anteil = (emob_pv_ladung / emob_ladung * 100) if emob_ladung > 0 else None
    benzin_verbrauch = emob_km * 7 / 100
    benzin_kosten = benzin_verbrauch * 1.80
    strom_kosten = (emob_ladung - emob_pv_ladung) * netzbezug_preis_cent / 100
    emob_ersparnis = benzin_kosten - strom_kosten if emob_km > 0 else 0

    # Balkonkraftwerk
    bkw_invs = [i for i in investitionen if i.typ == "balkonkraftwerk"]
    hat_balkonkraftwerk = len(bkw_invs) > 0

    # ==========================================================================
    # Finanzen
    # ==========================================================================

    einspeise_erloes = einspeisung * einspeise_verguetung_cent / 100
    ev_ersparnis = eigenverbrauch * netzbezug_preis_cent / 100
    netto_ertrag = einspeise_erloes + ev_ersparnis

    investition_gesamt = sum(i.anschaffungskosten_gesamt or 0 for i in investitionen)

    kumulative_ersparnis = netto_ertrag + wp_ersparnis + emob_ersparnis
    roi_fortschritt = (kumulative_ersparnis / investition_gesamt * 100) if investition_gesamt > 0 else None

    # ==========================================================================
    # CO2-Bilanz
    # ==========================================================================

    co2_pv = eigenverbrauch * CO2_FAKTOR_STROM_KG_KWH
    co2_wp = (wp_waerme / 0.9 * CO2_FAKTOR_GAS_KG_KWH) - (wp_strom * CO2_FAKTOR_STROM_KG_KWH) if wp_waerme > 0 else 0
    co2_emob = (benzin_verbrauch * CO2_FAKTOR_BENZIN_KG_LITER) - ((emob_ladung - emob_pv_ladung) * CO2_FAKTOR_STROM_KG_KWH) if emob_km > 0 else 0
    co2_gesamt = co2_pv + max(0, co2_wp) + max(0, co2_emob)

    # ==========================================================================
    # Zeitraum (aus InvestitionMonatsdaten ODER Monatsdaten)
    # ==========================================================================

    zeitraum_von = None
    zeitraum_bis = None
    anzahl_monate = 0

    # Primär: Zeitraum aus InvestitionMonatsdaten
    if zeitraum_monate:
        sorted_monate = sorted(zeitraum_monate)
        first = sorted_monate[0]
        last = sorted_monate[-1]
        zeitraum_von = f"{first[0]}-{first[1]:02d}"
        zeitraum_bis = f"{last[0]}-{last[1]:02d}"
        anzahl_monate = len(zeitraum_monate)
    # Fallback: Zeitraum aus Monatsdaten
    elif monatsdaten_list:
        first = monatsdaten_list[0]
        last = monatsdaten_list[-1]
        zeitraum_von = f"{first.jahr}-{first.monat:02d}"
        zeitraum_bis = f"{last.jahr}-{last.monat:02d}"
        anzahl_monate = len(monatsdaten_list)

    return CockpitUebersichtResponse(
        # Energie
        pv_erzeugung_kwh=round(pv_erzeugung, 1),
        gesamtverbrauch_kwh=round(gesamtverbrauch, 1),
        netzbezug_kwh=round(netzbezug, 1),
        einspeisung_kwh=round(einspeisung, 1),
        direktverbrauch_kwh=round(direktverbrauch, 1),
        eigenverbrauch_kwh=round(eigenverbrauch, 1),

        # Quoten
        autarkie_prozent=round(autarkie, 1),
        eigenverbrauch_quote_prozent=round(ev_quote, 1),
        direktverbrauch_quote_prozent=round(dv_quote, 1),
        spezifischer_ertrag_kwh_kwp=round(spez_ertrag, 1) if spez_ertrag else None,
        anlagenleistung_kwp=round(anlagenleistung_kwp, 2),

        # Speicher
        speicher_ladung_kwh=round(speicher_ladung, 1),
        speicher_entladung_kwh=round(speicher_entladung, 1),
        speicher_effizienz_prozent=round(speicher_effizienz, 1) if speicher_effizienz else None,
        speicher_vollzyklen=round(speicher_vollzyklen, 1) if speicher_vollzyklen else None,
        speicher_kapazitaet_kwh=round(speicher_kapazitaet, 1),
        hat_speicher=hat_speicher,

        # Wärmepumpe
        wp_waerme_kwh=round(wp_waerme, 1),
        wp_strom_kwh=round(wp_strom, 1),
        wp_cop=round(wp_cop, 2) if wp_cop else None,
        wp_ersparnis_euro=round(wp_ersparnis, 2),
        hat_waermepumpe=hat_waermepumpe,

        # E-Mobilität
        emob_km=round(emob_km, 0),
        emob_ladung_kwh=round(emob_ladung, 1),
        emob_pv_anteil_prozent=round(emob_pv_anteil, 1) if emob_pv_anteil else None,
        emob_ersparnis_euro=round(emob_ersparnis, 2),
        hat_emobilitaet=hat_emobilitaet,

        # Balkonkraftwerk
        bkw_erzeugung_kwh=round(bkw_erzeugung, 1),
        bkw_eigenverbrauch_kwh=round(bkw_eigenverbrauch, 1),
        hat_balkonkraftwerk=hat_balkonkraftwerk,

        # Finanzen
        einspeise_erloes_euro=round(einspeise_erloes, 2),
        ev_ersparnis_euro=round(ev_ersparnis, 2),
        netto_ertrag_euro=round(netto_ertrag, 2),
        roi_fortschritt_prozent=round(roi_fortschritt, 1) if roi_fortschritt else None,
        investition_gesamt_euro=round(investition_gesamt, 2),

        # Umwelt
        co2_pv_kg=round(co2_pv, 1),
        co2_wp_kg=round(co2_wp, 1),
        co2_emob_kg=round(co2_emob, 1),
        co2_gesamt_kg=round(co2_gesamt, 1),

        # Meta
        anzahl_monate=anzahl_monate,
        zeitraum_von=zeitraum_von,
        zeitraum_bis=zeitraum_bis,
    )


# =============================================================================
# Prognose vs. IST
# =============================================================================

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

    # Jahres-Summen
    prognose_jahresertrag_kwh: float
    ist_jahresertrag_kwh: float
    abweichung_kwh: float
    abweichung_prozent: Optional[float]
    performance_ratio: Optional[float]  # IST / Prognose

    # Monatswerte
    monatswerte: list[MonatsvergleichItem]

    # Meta
    prognose_quelle: Optional[str]  # "PVGIS" oder None
    prognose_datum: Optional[str]


MONATSNAMEN = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember"
]


@router.get("/prognose-vs-ist/{anlage_id}", response_model=PrognoseVsIstResponse)
async def get_prognose_vs_ist(
    anlage_id: int,
    jahr: int = Query(..., description="Jahr für den Vergleich"),
    db: AsyncSession = Depends(get_db)
):
    """
    Vergleicht PVGIS-Prognose mit tatsächlichen Monatsdaten.

    Berechnet Performance-Ratio und Abweichungen pro Monat.
    """
    # Aktive PVGIS-Prognose laden
    prognose_result = await db.execute(
        select(PVGISPrognoseModel)
        .where(PVGISPrognoseModel.anlage_id == anlage_id)
        .where(PVGISPrognoseModel.ist_aktiv == True)
    )
    prognose = prognose_result.scalar_one_or_none()

    # IST-Daten für das Jahr laden
    md_result = await db.execute(
        select(Monatsdaten)
        .where(Monatsdaten.anlage_id == anlage_id)
        .where(Monatsdaten.jahr == jahr)
        .order_by(Monatsdaten.monat)
    )
    monatsdaten_list = md_result.scalars().all()

    # Monatsdaten in Dict umwandeln
    ist_pro_monat = {m.monat: m.pv_erzeugung_kwh or 0 for m in monatsdaten_list}

    # Prognose-Monatswerte extrahieren
    prognose_pro_monat = {}
    if prognose and prognose.monatswerte:
        for mw in prognose.monatswerte:
            prognose_pro_monat[mw["monat"]] = mw["e_m"]

    # Monatsvergleich erstellen
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

    # Jahres-Totals
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


# =============================================================================
# Nachhaltigkeit / CO2-Bilanz Zeitreihe
# =============================================================================

class NachhaltigkeitMonat(BaseModel):
    """CO2-Bilanz für einen Monat."""
    jahr: int
    monat: int
    monat_name: str

    # CO2-Einsparungen in kg
    co2_pv_kg: float
    co2_wp_kg: float
    co2_emob_kg: float
    co2_gesamt_kg: float

    # Kumulierte Werte
    co2_kumuliert_kg: float

    # Autarkie
    autarkie_prozent: float


class NachhaltigkeitResponse(BaseModel):
    """Nachhaltigkeits-Übersicht mit Zeitreihe."""
    anlage_id: int

    # Lifetime-Totals
    co2_gesamt_kg: float
    co2_pv_kg: float
    co2_wp_kg: float
    co2_emob_kg: float

    # Äquivalente (anschauliche Darstellung)
    aequivalent_baeume: int  # ~20 kg CO2/Baum/Jahr
    aequivalent_auto_km: int  # ~0.12 kg CO2/km
    aequivalent_fluege_km: int  # ~0.25 kg CO2/km

    # Zeitreihe
    monatswerte: list[NachhaltigkeitMonat]

    # Durchschnittliche Autarkie
    autarkie_durchschnitt_prozent: float


@router.get("/nachhaltigkeit/{anlage_id}", response_model=NachhaltigkeitResponse)
async def get_nachhaltigkeit(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Nachhaltigkeits-Übersicht mit CO2-Zeitreihe.

    Berechnet monatliche und kumulierte CO2-Einsparungen.

    Datenquellen:
    - InvestitionMonatsdaten: PV-Erzeugung pro String, Speicher, WP, E-Auto
    - Monatsdaten: NUR für Einspeisung/Netzbezug zur Autarkie-Berechnung
    """
    # Investitionen laden
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.aktiv == True)
    )
    investitionen = inv_result.scalars().all()
    inv_by_id = {i.id: i for i in investitionen}

    # Alle InvestitionMonatsdaten laden
    all_inv_ids = [i.id for i in investitionen]
    all_imd = []
    if all_inv_ids:
        imd_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id.in_(all_inv_ids))
            .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
        )
        all_imd = imd_result.scalars().all()

    # Daten nach Monat aggregieren
    data_by_month: dict[tuple[int, int], dict] = {}

    for imd in all_imd:
        key = (imd.jahr, imd.monat)
        if key not in data_by_month:
            data_by_month[key] = {
                "pv_erzeugung": 0, "speicher_ladung": 0, "speicher_entladung": 0,
                "wp_waerme": 0, "wp_strom": 0,
                "emob_km": 0, "emob_ladung": 0, "emob_pv_ladung": 0,
            }

        inv = inv_by_id.get(imd.investition_id)
        if not inv:
            continue

        data = imd.verbrauch_daten or {}

        if inv.typ == "pv-module":
            data_by_month[key]["pv_erzeugung"] += data.get("pv_erzeugung_kwh", 0) or 0

        elif inv.typ == "speicher":
            data_by_month[key]["speicher_ladung"] += data.get("ladung_kwh", 0) or 0
            data_by_month[key]["speicher_entladung"] += data.get("entladung_kwh", 0) or 0

        elif inv.typ == "balkonkraftwerk":
            data_by_month[key]["pv_erzeugung"] += data.get("pv_erzeugung_kwh", 0) or data.get("erzeugung_kwh", 0) or 0

        elif inv.typ == "waermepumpe":
            data_by_month[key]["wp_waerme"] += (
                data.get("waerme_kwh", 0) or
                (data.get("heizenergie_kwh", 0) or data.get("heizung_kwh", 0)) +
                (data.get("warmwasser_kwh", 0) or 0)
            )
            data_by_month[key]["wp_strom"] += (
                data.get("stromverbrauch_kwh", 0) or
                data.get("strom_kwh", 0) or
                data.get("verbrauch_kwh", 0) or 0
            )

        elif inv.typ in ("e-auto", "wallbox"):
            data_by_month[key]["emob_km"] += data.get("km_gefahren", 0) or 0
            data_by_month[key]["emob_ladung"] += (
                data.get("ladung_kwh", 0) or data.get("verbrauch_kwh", 0) or 0
            )
            data_by_month[key]["emob_pv_ladung"] += data.get("ladung_pv_kwh", 0) or 0

    # Monatsdaten für Einspeisung/Netzbezug laden (für Autarkie-Berechnung)
    md_result = await db.execute(
        select(Monatsdaten)
        .where(Monatsdaten.anlage_id == anlage_id)
        .order_by(Monatsdaten.jahr, Monatsdaten.monat)
    )
    monatsdaten_list = md_result.scalars().all()
    md_by_month = {(m.jahr, m.monat): m for m in monatsdaten_list}

    # Monatswerte berechnen (Zeitreihe aus InvestitionMonatsdaten)
    monatswerte = []
    co2_kumuliert = 0.0
    co2_pv_total = 0.0
    co2_wp_total = 0.0
    co2_emob_total = 0.0
    autarkie_summe = 0.0
    autarkie_count = 0

    for key in sorted(data_by_month.keys()):
        jahr, monat = key
        d = data_by_month[key]

        # Eigenverbrauch berechnen (PV - Einspeisung - Speicherladung + Speicherentladung)
        md = md_by_month.get(key)
        einspeisung = md.einspeisung_kwh or 0 if md else 0
        netzbezug = md.netzbezug_kwh or 0 if md else 0

        pv_erzeugung = d["pv_erzeugung"]
        direktverbrauch = max(0, pv_erzeugung - einspeisung - d["speicher_ladung"])
        eigenverbrauch = direktverbrauch + d["speicher_entladung"]
        gesamtverbrauch = eigenverbrauch + netzbezug

        # PV CO2 (Eigenverbrauch erspart Netzstrom)
        co2_pv = eigenverbrauch * CO2_FAKTOR_STROM_KG_KWH

        # WP CO2 (vs. Gasheizung)
        wp_waerme = d["wp_waerme"]
        wp_strom = d["wp_strom"]
        co2_wp = (wp_waerme / 0.9 * CO2_FAKTOR_GAS_KG_KWH) - (wp_strom * CO2_FAKTOR_STROM_KG_KWH) if wp_waerme > 0 else 0
        co2_wp = max(0, co2_wp)

        # E-Mob CO2 (vs. Benziner)
        emob_km = d["emob_km"]
        emob_ladung = d["emob_ladung"]
        emob_pv = d["emob_pv_ladung"]
        benzin_verbrauch = emob_km * 7 / 100
        co2_emob = (benzin_verbrauch * CO2_FAKTOR_BENZIN_KG_LITER) - ((emob_ladung - emob_pv) * CO2_FAKTOR_STROM_KG_KWH) if emob_km > 0 else 0
        co2_emob = max(0, co2_emob)

        co2_monat = co2_pv + co2_wp + co2_emob
        co2_kumuliert += co2_monat

        # Autarkie
        autarkie = (eigenverbrauch / gesamtverbrauch * 100) if gesamtverbrauch > 0 else 0
        autarkie_summe += autarkie
        autarkie_count += 1

        monatswerte.append(NachhaltigkeitMonat(
            jahr=jahr,
            monat=monat,
            monat_name=MONATSNAMEN[monat],
            co2_pv_kg=round(co2_pv, 1),
            co2_wp_kg=round(co2_wp, 1),
            co2_emob_kg=round(co2_emob, 1),
            co2_gesamt_kg=round(co2_monat, 1),
            co2_kumuliert_kg=round(co2_kumuliert, 1),
            autarkie_prozent=round(autarkie, 1),
        ))

        co2_pv_total += co2_pv
        co2_wp_total += co2_wp
        co2_emob_total += co2_emob

    co2_gesamt = co2_pv_total + co2_wp_total + co2_emob_total

    # Äquivalente berechnen
    aequivalent_baeume = int(co2_gesamt / 20)
    aequivalent_auto_km = int(co2_gesamt / 0.12)
    aequivalent_fluege_km = int(co2_gesamt / 0.25)

    # Durchschnittliche Autarkie
    autarkie_avg = autarkie_summe / autarkie_count if autarkie_count > 0 else 0

    return NachhaltigkeitResponse(
        anlage_id=anlage_id,
        co2_gesamt_kg=round(co2_gesamt, 1),
        co2_pv_kg=round(co2_pv_total, 1),
        co2_wp_kg=round(co2_wp_total, 1),
        co2_emob_kg=round(co2_emob_total, 1),
        aequivalent_baeume=aequivalent_baeume,
        aequivalent_auto_km=aequivalent_auto_km,
        aequivalent_fluege_km=aequivalent_fluege_km,
        monatswerte=monatswerte,
        autarkie_durchschnitt_prozent=round(autarkie_avg, 1),
    )


# =============================================================================
# Komponenten-Zeitreihe (für Auswertungen)
# =============================================================================

class KomponentenMonat(BaseModel):
    """Monatswerte für alle Komponenten (NUR aus InvestitionMonatsdaten)."""
    jahr: int
    monat: int
    monat_name: str

    # Speicher
    speicher_ladung_kwh: float
    speicher_entladung_kwh: float
    speicher_effizienz_prozent: Optional[float]
    speicher_arbitrage_kwh: float  # Netzladung für Arbitrage
    speicher_arbitrage_preis_cent: Optional[float]  # Durchschn. Ladepreis

    # Wärmepumpe
    wp_waerme_kwh: float
    wp_strom_kwh: float
    wp_cop: Optional[float]
    wp_heizung_kwh: float  # NEU: getrennt
    wp_warmwasser_kwh: float  # NEU: getrennt

    # E-Mobilität
    emob_km: float
    emob_ladung_kwh: float
    emob_pv_anteil_prozent: Optional[float]
    emob_ladung_pv_kwh: float  # NEU: aus PV
    emob_ladung_netz_kwh: float  # NEU: aus Netz
    emob_ladung_extern_kwh: float  # NEU: extern/öffentlich
    emob_ladung_extern_euro: float  # NEU: Kosten extern
    emob_v2h_kwh: float  # NEU: Vehicle-to-Home

    # Balkonkraftwerk
    bkw_erzeugung_kwh: float
    bkw_eigenverbrauch_kwh: float
    bkw_speicher_ladung_kwh: float  # NEU: integrierter Speicher
    bkw_speicher_entladung_kwh: float  # NEU

    # Sonstiges - aggregiert
    sonstiges_erzeugung_kwh: float
    sonstiges_verbrauch_kwh: float

    # Sonderkosten (alle Komponenten aggregiert)
    sonderkosten_euro: float  # NEU


class KomponentenZeitreiheResponse(BaseModel):
    """Zeitreihe aller Komponenten für Auswertungen."""
    anlage_id: int

    # Verfügbare Komponenten
    hat_speicher: bool
    hat_waermepumpe: bool
    hat_emobilitaet: bool
    hat_balkonkraftwerk: bool
    hat_sonstiges: bool

    # Feature-Flags
    hat_arbitrage: bool  # NEU: Mind. 1 Speicher mit Arbitrage-Daten
    hat_v2h: bool  # NEU: Mind. 1 E-Auto mit V2H-Daten

    # Monatliche Zeitreihe
    monatswerte: list[KomponentenMonat]

    # Meta
    anzahl_monate: int


@router.get("/komponenten-zeitreihe/{anlage_id}", response_model=KomponentenZeitreiheResponse)
async def get_komponenten_zeitreihe(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Zeitreihe aller Komponenten für Auswertungen.

    Datenquelle: NUR InvestitionMonatsdaten (nicht Monatsdaten!).
    Enthält alle verfügbaren Felder inkl. Arbitrage, V2H, externe Ladung, etc.
    """
    # Investitionen laden
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.aktiv == True)
    )
    investitionen = inv_result.scalars().all()

    # Komponenten-IDs nach Typ sammeln
    speicher_ids = [i.id for i in investitionen if i.typ == "speicher"]
    wp_ids = [i.id for i in investitionen if i.typ == "waermepumpe"]
    emob_ids = [i.id for i in investitionen if i.typ in ("e-auto", "wallbox")]
    bkw_ids = [i.id for i in investitionen if i.typ == "balkonkraftwerk"]
    sonstiges_ids = [i.id for i in investitionen if i.typ == "sonstiges"]

    all_inv_ids = speicher_ids + wp_ids + emob_ids + bkw_ids + sonstiges_ids

    hat_speicher = len(speicher_ids) > 0
    hat_waermepumpe = len(wp_ids) > 0
    hat_emobilitaet = len(emob_ids) > 0
    hat_balkonkraftwerk = len(bkw_ids) > 0
    hat_sonstiges = len(sonstiges_ids) > 0

    # Keine Komponenten → leere Response
    if not all_inv_ids:
        return KomponentenZeitreiheResponse(
            anlage_id=anlage_id,
            hat_speicher=False,
            hat_waermepumpe=False,
            hat_emobilitaet=False,
            hat_balkonkraftwerk=False,
            hat_sonstiges=False,
            hat_arbitrage=False,
            hat_v2h=False,
            monatswerte=[],
            anzahl_monate=0,
        )

    # Alle InvestitionMonatsdaten laden
    imd_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(all_inv_ids))
        .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    all_imd = imd_result.scalars().all()

    inv_by_id = {i.id: i for i in investitionen}

    # Initialisierung der erweiterten Datenstruktur
    def empty_month_data():
        return {
            # Speicher
            "speicher_ladung": 0, "speicher_entladung": 0,
            "speicher_arbitrage": 0, "speicher_arbitrage_preis_sum": 0, "speicher_arbitrage_count": 0,
            # Wärmepumpe
            "wp_waerme": 0, "wp_strom": 0, "wp_heizung": 0, "wp_warmwasser": 0,
            # E-Mobilität
            "emob_km": 0, "emob_ladung": 0, "emob_pv_ladung": 0,
            "emob_netz_ladung": 0, "emob_extern_ladung": 0, "emob_extern_euro": 0, "emob_v2h": 0,
            # Balkonkraftwerk
            "bkw_erzeugung": 0, "bkw_eigenverbrauch": 0, "bkw_speicher_ladung": 0, "bkw_speicher_entladung": 0,
            # Sonstiges
            "sonstiges_erzeugung": 0, "sonstiges_verbrauch": 0,
            # Sonderkosten
            "sonderkosten": 0,
        }

    inv_data_by_month: dict[tuple[int, int], dict] = {}

    # Feature-Flags
    hat_arbitrage = False
    hat_v2h = False

    for imd in all_imd:
        key = (imd.jahr, imd.monat)
        if key not in inv_data_by_month:
            inv_data_by_month[key] = empty_month_data()

        inv = inv_by_id.get(imd.investition_id)
        if not inv:
            continue

        data = imd.verbrauch_daten or {}
        d = inv_data_by_month[key]

        # Sonderkosten (alle Typen)
        d["sonderkosten"] += data.get("sonderkosten_euro", 0) or 0

        if inv.typ == "speicher":
            d["speicher_ladung"] += data.get("ladung_kwh", 0) or 0
            d["speicher_entladung"] += data.get("entladung_kwh", 0) or 0
            # Arbitrage
            arbitrage_kwh = data.get("speicher_ladung_netz_kwh", 0) or 0
            if arbitrage_kwh > 0:
                hat_arbitrage = True
                d["speicher_arbitrage"] += arbitrage_kwh
                preis = data.get("speicher_ladepreis_cent", 0) or 0
                if preis > 0:
                    d["speicher_arbitrage_preis_sum"] += preis * arbitrage_kwh
                    d["speicher_arbitrage_count"] += arbitrage_kwh

        elif inv.typ == "waermepumpe":
            heizung = data.get("heizenergie_kwh", 0) or data.get("heizung_kwh", 0) or 0
            warmwasser = data.get("warmwasser_kwh", 0) or 0
            waerme_gesamt = data.get("waerme_kwh", 0) or (heizung + warmwasser)
            d["wp_heizung"] += heizung
            d["wp_warmwasser"] += warmwasser
            d["wp_waerme"] += waerme_gesamt
            d["wp_strom"] += (
                data.get("stromverbrauch_kwh", 0) or
                data.get("strom_kwh", 0) or
                data.get("verbrauch_kwh", 0) or 0
            )

        elif inv.typ in ("e-auto", "wallbox"):
            d["emob_km"] += data.get("km_gefahren", 0) or 0
            d["emob_ladung"] += data.get("ladung_kwh", 0) or data.get("verbrauch_kwh", 0) or 0
            d["emob_pv_ladung"] += data.get("ladung_pv_kwh", 0) or 0
            d["emob_netz_ladung"] += data.get("ladung_netz_kwh", 0) or 0
            d["emob_extern_ladung"] += data.get("ladung_extern_kwh", 0) or 0
            d["emob_extern_euro"] += data.get("ladung_extern_euro", 0) or 0
            # V2H
            v2h = data.get("v2h_entladung_kwh", 0) or 0
            if v2h > 0:
                hat_v2h = True
                d["emob_v2h"] += v2h

        elif inv.typ == "balkonkraftwerk":
            d["bkw_erzeugung"] += data.get("pv_erzeugung_kwh", 0) or data.get("erzeugung_kwh", 0) or 0
            d["bkw_eigenverbrauch"] += data.get("eigenverbrauch_kwh", 0) or 0
            d["bkw_speicher_ladung"] += data.get("speicher_ladung_kwh", 0) or 0
            d["bkw_speicher_entladung"] += data.get("speicher_entladung_kwh", 0) or 0

        elif inv.typ == "sonstiges":
            params = inv.parameter or {}
            kategorie = params.get("kategorie", "")
            if kategorie == "erzeuger":
                d["sonstiges_erzeugung"] += data.get("erzeugung_kwh", 0) or 0
            elif kategorie == "verbraucher":
                d["sonstiges_verbrauch"] += data.get("verbrauch_sonstig_kwh", 0) or data.get("verbrauch_kwh", 0) or 0
            else:
                d["sonstiges_erzeugung"] += data.get("erzeugung_kwh", 0) or 0
                d["sonstiges_verbrauch"] += data.get("verbrauch_sonstig_kwh", 0) or data.get("verbrauch_kwh", 0) or 0

    # Monatswerte erstellen
    monatswerte = []
    for key in sorted(inv_data_by_month.keys()):
        jahr, monat = key
        d = inv_data_by_month[key]

        # Berechnete Werte
        speicher_effizienz = (
            d["speicher_entladung"] / d["speicher_ladung"] * 100
        ) if d["speicher_ladung"] > 0 else None

        speicher_arbitrage_preis = (
            d["speicher_arbitrage_preis_sum"] / d["speicher_arbitrage_count"]
        ) if d["speicher_arbitrage_count"] > 0 else None

        wp_cop = (d["wp_waerme"] / d["wp_strom"]) if d["wp_strom"] > 0 else None

        emob_pv_anteil = (
            d["emob_pv_ladung"] / d["emob_ladung"] * 100
        ) if d["emob_ladung"] > 0 else None

        monatswerte.append(KomponentenMonat(
            jahr=jahr,
            monat=monat,
            monat_name=MONATSNAMEN[monat],
            # Speicher
            speicher_ladung_kwh=round(d["speicher_ladung"], 1),
            speicher_entladung_kwh=round(d["speicher_entladung"], 1),
            speicher_effizienz_prozent=round(speicher_effizienz, 1) if speicher_effizienz else None,
            speicher_arbitrage_kwh=round(d["speicher_arbitrage"], 1),
            speicher_arbitrage_preis_cent=round(speicher_arbitrage_preis, 2) if speicher_arbitrage_preis else None,
            # Wärmepumpe
            wp_waerme_kwh=round(d["wp_waerme"], 1),
            wp_strom_kwh=round(d["wp_strom"], 1),
            wp_cop=round(wp_cop, 2) if wp_cop else None,
            wp_heizung_kwh=round(d["wp_heizung"], 1),
            wp_warmwasser_kwh=round(d["wp_warmwasser"], 1),
            # E-Mobilität
            emob_km=round(d["emob_km"], 0),
            emob_ladung_kwh=round(d["emob_ladung"], 1),
            emob_pv_anteil_prozent=round(emob_pv_anteil, 1) if emob_pv_anteil else None,
            emob_ladung_pv_kwh=round(d["emob_pv_ladung"], 1),
            emob_ladung_netz_kwh=round(d["emob_netz_ladung"], 1),
            emob_ladung_extern_kwh=round(d["emob_extern_ladung"], 1),
            emob_ladung_extern_euro=round(d["emob_extern_euro"], 2),
            emob_v2h_kwh=round(d["emob_v2h"], 1),
            # Balkonkraftwerk
            bkw_erzeugung_kwh=round(d["bkw_erzeugung"], 1),
            bkw_eigenverbrauch_kwh=round(d["bkw_eigenverbrauch"], 1),
            bkw_speicher_ladung_kwh=round(d["bkw_speicher_ladung"], 1),
            bkw_speicher_entladung_kwh=round(d["bkw_speicher_entladung"], 1),
            # Sonstiges
            sonstiges_erzeugung_kwh=round(d["sonstiges_erzeugung"], 1),
            sonstiges_verbrauch_kwh=round(d["sonstiges_verbrauch"], 1),
            # Sonderkosten
            sonderkosten_euro=round(d["sonderkosten"], 2),
        ))

    return KomponentenZeitreiheResponse(
        anlage_id=anlage_id,
        hat_speicher=hat_speicher,
        hat_waermepumpe=hat_waermepumpe,
        hat_emobilitaet=hat_emobilitaet,
        hat_balkonkraftwerk=hat_balkonkraftwerk,
        hat_sonstiges=hat_sonstiges,
        hat_arbitrage=hat_arbitrage,
        hat_v2h=hat_v2h,
        monatswerte=monatswerte,
        anzahl_monate=len(monatswerte),
    )
