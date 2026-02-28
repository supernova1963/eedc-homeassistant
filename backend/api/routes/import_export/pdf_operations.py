"""
PDF Export Operations

Generiert vollstaendige PDF-Jahresberichte fuer PV-Anlagen.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.strompreis import Strompreis
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.pdf_service import (
    PDFService,
    AnlagenDokumentation,
    StromtarifDaten,
    InvestitionDokumentation,
    JahresKPIs,
    MonatsZeile,
    FinanzPrognose,
    StringVergleich,
)
from backend.core.calculations import (
    CO2_FAKTOR_STROM_KG_KWH,
    CO2_FAKTOR_GAS_KG_KWH,
    CO2_FAKTOR_BENZIN_KG_LITER,
)

logger = logging.getLogger(__name__)
router = APIRouter()

MONATSNAMEN = [
    "", "Januar", "Februar", "Maerz", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember"
]


@router.get("/pdf/{anlage_id}")
async def export_pdf(
    anlage_id: int,
    jahr: Optional[int] = Query(None, description="Jahr fuer den Bericht (leer = Gesamtzeitraum)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Generiert einen vollstaendigen PDF-Bericht fuer eine Anlage.

    Parameter:
    - jahr: Optional. Wenn nicht angegeben, wird der Gesamtzeitraum seit Installation verwendet.

    Enthaelt:
    - Anlagen-Dokumentation (Stammdaten, Versorger, Tarif, HA-Sensoren)
    - Investitionen (alle Komponenten mit Details)
    - Jahresuebersicht (alle KPIs) - bei Gesamtzeitraum: alle Jahre + Summen
    - Diagramme (PV-Erzeugung, Energie-Fluss, Autarkie)
    - Monatsuebersicht (bei Gesamtzeitraum: letzte 24 Monate oder alle)
    - Finanz-Prognose & Amortisation (kumuliert)
    - PV-String Vergleich (SOLL vs. IST)
    """
    # ==========================================================================
    # 1. Anlage laden
    # ==========================================================================
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Wenn kein Jahr angegeben, ermittle Zeitraum aus vorhandenen Daten
    ist_gesamtzeitraum = jahr is None

    # ==========================================================================
    # 2. Strompreis laden
    # ==========================================================================
    preis_query = select(Strompreis).where(
        Strompreis.anlage_id == anlage_id
    ).order_by(Strompreis.gueltig_ab.desc()).limit(1)
    preis_result = await db.execute(preis_query)
    strompreis = preis_result.scalar_one_or_none()

    netzbezug_preis_cent = strompreis.netzbezug_arbeitspreis_cent_kwh if strompreis else 30.0
    einspeise_verguetung_cent = strompreis.einspeiseverguetung_cent_kwh if strompreis else 8.2

    # ==========================================================================
    # 3. Investitionen laden
    # ==========================================================================
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.aktiv == True)
    )
    investitionen = inv_result.scalars().all()
    inv_by_id = {i.id: i for i in investitionen}

    # ==========================================================================
    # 4. PVGIS-Prognosen laden
    # ==========================================================================
    pvgis_result = await db.execute(
        select(PVGISPrognose).where(PVGISPrognose.anlage_id == anlage_id)
    )
    pvgis_prognosen = pvgis_result.scalars().all()

    # Monatliche Prognose-Summen berechnen
    pvgis_by_month = {}
    for p in pvgis_prognosen:
        if p.monatswerte:
            for mw in p.monatswerte:
                monat = mw.get("monat", 0)
                kwh = mw.get("e_month_kwh", 0) or 0
                pvgis_by_month[monat] = pvgis_by_month.get(monat, 0) + kwh

    # ==========================================================================
    # 5. InvestitionMonatsdaten laden
    # ==========================================================================
    all_inv_ids = [i.id for i in investitionen]
    all_imd = []
    if all_inv_ids:
        if ist_gesamtzeitraum:
            # Alle Daten laden
            imd_result = await db.execute(
                select(InvestitionMonatsdaten).where(
                    InvestitionMonatsdaten.investition_id.in_(all_inv_ids)
                )
            )
        else:
            imd_result = await db.execute(
                select(InvestitionMonatsdaten).where(
                    InvestitionMonatsdaten.investition_id.in_(all_inv_ids),
                    InvestitionMonatsdaten.jahr == jahr
                )
            )
        all_imd = imd_result.scalars().all()

    # ==========================================================================
    # 6. Monatsdaten laden
    # ==========================================================================
    if ist_gesamtzeitraum:
        md_result = await db.execute(
            select(Monatsdaten)
            .where(Monatsdaten.anlage_id == anlage_id)
            .order_by(Monatsdaten.jahr, Monatsdaten.monat)
        )
    else:
        md_result = await db.execute(
            select(Monatsdaten)
            .where(Monatsdaten.anlage_id == anlage_id)
            .where(Monatsdaten.jahr == jahr)
            .order_by(Monatsdaten.monat)
        )
    monatsdaten_list = md_result.scalars().all()

    # Bei Gesamtzeitraum: Jahre ermitteln
    if ist_gesamtzeitraum and monatsdaten_list:
        alle_jahre = sorted(set(m.jahr for m in monatsdaten_list))
        start_jahr = alle_jahre[0] if alle_jahre else 2023
        end_jahr = alle_jahre[-1] if alle_jahre else 2025
    elif ist_gesamtzeitraum:
        # Keine Daten - nutze Installationsdatum
        start_jahr = anlage.installationsdatum.year if anlage.installationsdatum else 2023
        end_jahr = 2025
        alle_jahre = list(range(start_jahr, end_jahr + 1))
    else:
        alle_jahre = [jahr]
        start_jahr = end_jahr = jahr

    # Monatsdaten indexieren
    md_by_year_month = {}
    for m in monatsdaten_list:
        md_by_year_month[(m.jahr, m.monat)] = m

    # Fuer Einzel-Jahr-Kompatibilitaet
    if not ist_gesamtzeitraum:
        md_by_month = {m.monat: m for m in monatsdaten_list}
    else:
        md_by_month = {}

    # ==========================================================================
    # 7. Daten aggregieren
    # ==========================================================================

    hat_speicher = any(i.typ == "speicher" for i in investitionen)
    hat_waermepumpe = any(i.typ == "waermepumpe" for i in investitionen)
    hat_emobilitaet = any(i.typ in ("e-auto", "wallbox") for i in investitionen)

    # Speicher-Kapazitaet ermitteln
    speicher_kapazitaet = 0.0
    for inv in investitionen:
        if inv.typ == "speicher":
            params = inv.parameter or {}
            speicher_kapazitaet += params.get("kapazitaet_kwh", 0) or 0

    # PV-Erzeugung nach Jahr/Monat indexieren
    pv_erzeugung_by_year_month = {}
    for imd in all_imd:
        inv = inv_by_id.get(imd.investition_id)
        if inv and inv.typ in ("pv-module", "balkonkraftwerk"):
            data = imd.verbrauch_daten or {}
            pv_kwh = data.get("pv_erzeugung_kwh", 0) or 0
            key = (imd.jahr, imd.monat)
            pv_erzeugung_by_year_month[key] = pv_erzeugung_by_year_month.get(key, 0) + pv_kwh

    # Gesamtsummen initialisieren
    pv_gesamt = 0.0
    einsp_gesamt = 0.0
    netz_gesamt = 0.0
    ev_gesamt = 0.0
    speicher_ladung_total = 0.0
    speicher_entladung_total = 0.0
    wp_waerme_total = 0.0
    wp_heizung_total = 0.0
    wp_warmwasser_total = 0.0
    wp_strom_total = 0.0
    emob_km_total = 0.0
    emob_ladung_total = 0.0
    emob_pv_total = 0.0
    emob_netz_total = 0.0
    emob_v2h_total = 0.0

    # Investition-Monatsdaten fuer Gesamtsummen aggregieren
    for imd in all_imd:
        inv = inv_by_id.get(imd.investition_id)
        if not inv:
            continue
        data = imd.verbrauch_daten or {}

        if inv.typ == "speicher":
            speicher_ladung_total += data.get("ladung_kwh", 0) or 0
            speicher_entladung_total += data.get("entladung_kwh", 0) or 0
        elif inv.typ == "waermepumpe":
            heiz = data.get("heizenergie_kwh", 0) or data.get("heizung_kwh", 0) or 0
            ww = data.get("warmwasser_kwh", 0) or 0
            wp_heizung_total += heiz
            wp_warmwasser_total += ww
            wp_waerme_total += data.get("waerme_kwh", 0) or (heiz + ww)
            wp_strom_total += data.get("stromverbrauch_kwh", 0) or 0
        elif inv.typ in ("e-auto", "wallbox"):
            emob_km_total += data.get("km_gefahren", 0) or 0
            emob_ladung_total += data.get("ladung_kwh", 0) or 0
            emob_pv_total += data.get("ladung_pv_kwh", 0) or 0
            emob_netz_total += data.get("ladung_netz_kwh", 0) or 0
            emob_v2h_total += data.get("v2h_entladung_kwh", 0) or 0

    # Monatsdaten-Struktur erstellen
    # Bei Gesamtzeitraum: Zeile pro Jahr/Monat
    # Bei Einzeljahr: Zeile pro Monat
    monats_daten: List[MonatsZeile] = []

    if ist_gesamtzeitraum:
        # Alle Monate chronologisch
        for j in alle_jahre:
            for m in range(1, 13):
                if (j, m) in md_by_year_month or (j, m) in pv_erzeugung_by_year_month:
                    md = md_by_year_month.get((j, m))
                    pv_kwh = pv_erzeugung_by_year_month.get((j, m), 0)
                    einspeisung = md.einspeisung_kwh or 0 if md else 0
                    netzbezug = md.netzbezug_kwh or 0 if md else 0
                    eigenverbrauch = max(0, pv_kwh - einspeisung) if pv_kwh > 0 else 0
                    gesamtverbrauch = eigenverbrauch + netzbezug
                    autarkie = (eigenverbrauch / gesamtverbrauch * 100) if gesamtverbrauch > 0 else 0
                    spez_ertrag = (pv_kwh / anlage.leistung_kwp) if anlage.leistung_kwp > 0 else 0
                    einsp_erloes = einspeisung * einspeise_verguetung_cent / 100
                    ev_ersparnis = eigenverbrauch * netzbezug_preis_cent / 100

                    zeile = MonatsZeile(
                        monat=m,
                        monat_name=f"{MONATSNAMEN[m]} {j}",
                        jahr=j,
                        pv_erzeugung_kwh=pv_kwh,
                        pvgis_prognose_kwh=pvgis_by_month.get(m, 0),
                        eigenverbrauch_kwh=eigenverbrauch,
                        einspeisung_kwh=einspeisung,
                        netzbezug_kwh=netzbezug,
                        autarkie_prozent=autarkie,
                        spezifischer_ertrag=spez_ertrag,
                        einsp_erloes_euro=einsp_erloes,
                        ev_ersparnis_euro=ev_ersparnis,
                        netto_ertrag_euro=einsp_erloes + ev_ersparnis,
                    )
                    monats_daten.append(zeile)

                    pv_gesamt += pv_kwh
                    einsp_gesamt += einspeisung
                    netz_gesamt += netzbezug
                    ev_gesamt += eigenverbrauch
    else:
        # Einzeljahr: 12 Monate
        pv_erzeugung_by_month = {m: pv_erzeugung_by_year_month.get((jahr, m), 0) for m in range(1, 13)}

        for monat in range(1, 13):
            pv_kwh = pv_erzeugung_by_month[monat]
            md = md_by_year_month.get((jahr, monat))
            einspeisung = md.einspeisung_kwh or 0 if md else 0
            netzbezug = md.netzbezug_kwh or 0 if md else 0
            eigenverbrauch = max(0, pv_kwh - einspeisung) if pv_kwh > 0 else 0
            gesamtverbrauch = eigenverbrauch + netzbezug
            autarkie = (eigenverbrauch / gesamtverbrauch * 100) if gesamtverbrauch > 0 else 0
            spez_ertrag = (pv_kwh / anlage.leistung_kwp) if anlage.leistung_kwp > 0 else 0
            einsp_erloes = einspeisung * einspeise_verguetung_cent / 100
            ev_ersparnis = eigenverbrauch * netzbezug_preis_cent / 100

            zeile = MonatsZeile(
                monat=monat,
                monat_name=MONATSNAMEN[monat],
                jahr=jahr,
                pv_erzeugung_kwh=pv_kwh,
                pvgis_prognose_kwh=pvgis_by_month.get(monat, 0),
                eigenverbrauch_kwh=eigenverbrauch,
                einspeisung_kwh=einspeisung,
                netzbezug_kwh=netzbezug,
                autarkie_prozent=autarkie,
                spezifischer_ertrag=spez_ertrag,
                einsp_erloes_euro=einsp_erloes,
                ev_ersparnis_euro=ev_ersparnis,
                netto_ertrag_euro=einsp_erloes + ev_ersparnis,
            )
            monats_daten.append(zeile)

            pv_gesamt += pv_kwh
            einsp_gesamt += einspeisung
            netz_gesamt += netzbezug
            ev_gesamt += eigenverbrauch

    # Speicher/WP/E-Mob Monatsdaten aggregieren (nur Gesamtsummen, keine Einzelmonate)
    # Bei Bedarf koennte hier eine detaillierte Aufschuesselung erfolgen

    # ==========================================================================
    # 8. Jahres-KPIs berechnen
    # ==========================================================================
    gesamtverbrauch = ev_gesamt + netz_gesamt
    autarkie_jahr = (ev_gesamt / gesamtverbrauch * 100) if gesamtverbrauch > 0 else 0
    ev_quote = (ev_gesamt / pv_gesamt * 100) if pv_gesamt > 0 else 0
    spez_ertrag_jahr = (pv_gesamt / anlage.leistung_kwp) if anlage.leistung_kwp > 0 else 0

    einspeise_erloes = einsp_gesamt * einspeise_verguetung_cent / 100
    ev_ersparnis_euro = ev_gesamt * netzbezug_preis_cent / 100
    netto_ertrag = einspeise_erloes + ev_ersparnis_euro

    # Investitionen
    investition_gesamt = sum(i.anschaffungskosten_gesamt or 0 for i in investitionen)
    investition_alternativ = sum(i.anschaffungskosten_alternativ or 0 for i in investitionen if i.anschaffungskosten_alternativ)
    investition_mehrkosten = investition_gesamt - investition_alternativ

    rendite = (netto_ertrag / investition_mehrkosten * 100) if investition_mehrkosten > 0 else None

    # CO2
    co2_pv = ev_gesamt * CO2_FAKTOR_STROM_KG_KWH
    co2_wp = wp_waerme_total * CO2_FAKTOR_GAS_KG_KWH if hat_waermepumpe else 0  # Ersparnis vs. Gas
    co2_emob = emob_km_total * 0.12 if hat_emobilitaet else 0  # ~120g/km Benziner
    co2_gesamt = co2_pv + co2_wp + co2_emob

    # Speicher-Metriken
    speicher_vollzyklen = (speicher_ladung_total / speicher_kapazitaet) if speicher_kapazitaet > 0 else None
    speicher_effizienz = (speicher_entladung_total / speicher_ladung_total * 100) if speicher_ladung_total > 0 else None

    # WP-Metriken
    wp_cop = (wp_waerme_total / wp_strom_total) if wp_strom_total > 0 else None
    wp_ersparnis = 0  # TODO: vs. Gas berechnen

    # E-Mob-Metriken
    emob_pv_anteil = (emob_pv_total / emob_ladung_total * 100) if emob_ladung_total > 0 else None
    emob_ersparnis = 0  # TODO: vs. Benzin berechnen

    jahres_kpis = JahresKPIs(
        pv_erzeugung_kwh=pv_gesamt,
        eigenverbrauch_kwh=ev_gesamt,
        einspeisung_kwh=einsp_gesamt,
        netzbezug_kwh=netz_gesamt,
        gesamtverbrauch_kwh=gesamtverbrauch,
        autarkie_prozent=autarkie_jahr,
        eigenverbrauch_quote_prozent=ev_quote,
        spezifischer_ertrag_kwh_kwp=spez_ertrag_jahr,
        hat_speicher=hat_speicher,
        speicher_kapazitaet_kwh=speicher_kapazitaet,
        speicher_ladung_kwh=speicher_ladung_total,
        speicher_entladung_kwh=speicher_entladung_total,
        speicher_vollzyklen=speicher_vollzyklen,
        speicher_effizienz_prozent=speicher_effizienz,
        hat_waermepumpe=hat_waermepumpe,
        wp_waerme_kwh=wp_waerme_total,
        wp_heizung_kwh=wp_heizung_total,
        wp_warmwasser_kwh=wp_warmwasser_total,
        wp_strom_kwh=wp_strom_total,
        wp_cop=wp_cop,
        wp_ersparnis_euro=wp_ersparnis,
        hat_emobilitaet=hat_emobilitaet,
        emob_km=emob_km_total,
        emob_ladung_kwh=emob_ladung_total,
        emob_pv_kwh=emob_pv_total,
        emob_netz_kwh=emob_netz_total,
        emob_v2h_kwh=emob_v2h_total,
        emob_pv_anteil_prozent=emob_pv_anteil,
        emob_ersparnis_euro=emob_ersparnis,
        einspeise_erloes_euro=einspeise_erloes,
        ev_ersparnis_euro=ev_ersparnis_euro,
        netto_ertrag_euro=netto_ertrag,
        jahres_rendite_prozent=rendite,
        investition_gesamt_euro=investition_gesamt,
        investition_mehrkosten_euro=investition_mehrkosten,
        co2_pv_kg=co2_pv,
        co2_wp_kg=co2_wp,
        co2_emob_kg=co2_emob,
        co2_gesamt_kg=co2_gesamt,
    )

    # ==========================================================================
    # 9. Datenklassen befuellen
    # ==========================================================================

    # Anlagen-Dokumentation
    anlage_dok = AnlagenDokumentation(
        name=anlage.anlagenname,
        leistung_kwp=anlage.leistung_kwp,
        installationsdatum=anlage.installationsdatum,
        mastr_id=anlage.mastr_id,
        wetter_provider=anlage.wetter_provider,
        standort_plz=anlage.standort_plz,
        standort_ort=anlage.standort_ort,
        standort_strasse=anlage.standort_strasse,
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        versorger_daten=anlage.versorger_daten,
        ha_sensor_pv_erzeugung=anlage.ha_sensor_pv_erzeugung,
        ha_sensor_einspeisung=anlage.ha_sensor_einspeisung,
        ha_sensor_netzbezug=anlage.ha_sensor_netzbezug,
        ha_sensor_batterie_ladung=anlage.ha_sensor_batterie_ladung,
        ha_sensor_batterie_entladung=anlage.ha_sensor_batterie_entladung,
    )

    # Stromtarif
    tarif_dok = StromtarifDaten(
        tarifname=strompreis.tarifname if strompreis else None,
        anbieter=strompreis.anbieter if strompreis else None,
        netzbezug_cent_kwh=netzbezug_preis_cent,
        einspeiseverguetung_cent_kwh=einspeise_verguetung_cent,
        grundpreis_euro_monat=strompreis.grundpreis_euro_monat if strompreis else None,
        gueltig_ab=strompreis.gueltig_ab if strompreis else None,
    )

    # Investitionen
    inv_dok_list: List[InvestitionDokumentation] = []
    for inv in investitionen:
        params = inv.parameter or {}
        parent_name = None
        if inv.parent_investition_id:
            parent = inv_by_id.get(inv.parent_investition_id)
            parent_name = parent.bezeichnung if parent else None

        inv_dok = InvestitionDokumentation(
            typ=inv.typ,
            bezeichnung=inv.bezeichnung,
            anschaffungsdatum=inv.anschaffungsdatum,
            anschaffungskosten=inv.anschaffungskosten_gesamt,
            alternativkosten=inv.anschaffungskosten_alternativ,
            betriebskosten_jahr=inv.betriebskosten_jahr,
            leistung_kwp=inv.leistung_kwp if inv.typ != "speicher" else params.get("kapazitaet_kwh"),
            ausrichtung=inv.ausrichtung,
            neigung_grad=inv.neigung_grad,
            parent_bezeichnung=parent_name,
            parameter=params,
            stamm_hersteller=params.get("stamm_hersteller"),
            stamm_modell=params.get("stamm_modell"),
            stamm_seriennummer=params.get("stamm_seriennummer"),
            stamm_garantie_bis=params.get("stamm_garantie_bis"),
            stamm_mastr_id=params.get("stamm_mastr_id"),
            ansprechpartner_firma=params.get("ansprechpartner_firma"),
            ansprechpartner_name=params.get("ansprechpartner_name"),
            ansprechpartner_telefon=params.get("ansprechpartner_telefon"),
            ansprechpartner_email=params.get("ansprechpartner_email"),
            ansprechpartner_kundennummer=params.get("ansprechpartner_kundennummer"),
            wartung_vertragsnummer=params.get("wartung_vertragsnummer"),
            wartung_anbieter=params.get("wartung_anbieter"),
            wartung_gueltig_bis=params.get("wartung_gueltig_bis"),
            wartung_leistungsumfang=params.get("wartung_leistungsumfang"),
        )
        inv_dok_list.append(inv_dok)

    # Finanz-Prognose (vereinfacht)
    finanz_prognose = FinanzPrognose(
        investition_mehrkosten_euro=investition_mehrkosten,
        bisherige_ertraege_euro=netto_ertrag,  # Nur aktuelles Jahr, TODO: kumulieren
        amortisations_fortschritt_prozent=(netto_ertrag / investition_mehrkosten * 100) if investition_mehrkosten > 0 else 0,
        amortisation_erreicht=netto_ertrag >= investition_mehrkosten,
        jahres_ertrag_prognose_euro=netto_ertrag,
        jahres_rendite_prognose_prozent=rendite,
    )

    # String-Vergleiche
    # PVGIS-Prognose ist pro Anlage, wird anteilig nach kWp auf Strings verteilt
    string_vergleiche: List[StringVergleich] = []

    # Neueste PVGIS-Prognose finden
    pvgis_prognose = None
    if pvgis_prognosen:
        pvgis_prognose = max(pvgis_prognosen, key=lambda p: p.abgerufen_am)

    # Gesamt-kWp aller PV-Module
    pv_module = [inv for inv in investitionen if inv.typ == "pv-module"]
    gesamt_kwp = sum(inv.leistung_kwp or 0 for inv in pv_module)
    if gesamt_kwp == 0:
        gesamt_kwp = anlage.leistung_kwp or 1

    # Prognose-Monatswerte laden
    prognose_monate = {}
    if pvgis_prognose and pvgis_prognose.monatswerte:
        for mw in pvgis_prognose.monatswerte:
            prognose_monate[mw.get("monat", 0)] = mw.get("e_m", 0) or 0

    # Anzahl vollstaendiger Jahre fuer Prognose-Skalierung
    anzahl_jahre = len(alle_jahre) if ist_gesamtzeitraum else 1

    for inv in pv_module:
        modul_kwp = inv.leistung_kwp or 0
        kwp_anteil = modul_kwp / gesamt_kwp if gesamt_kwp > 0 else 0

        # IST-Erzeugung fuer diesen String (alle Jahre oder nur das angefragte)
        ist_kwh = sum(
            (imd.verbrauch_daten or {}).get("pv_erzeugung_kwh", 0) or 0
            for imd in all_imd
            if imd.investition_id == inv.id
        )

        # PVGIS-Prognose anteilig nach kWp, skaliert nach Anzahl Jahre
        prognose_kwh_pro_jahr = sum(prognose_monate.values()) * kwp_anteil
        prognose_kwh = prognose_kwh_pro_jahr * anzahl_jahre

        if prognose_kwh > 0 or ist_kwh > 0:
            abw_kwh = ist_kwh - prognose_kwh
            abw_pct = (abw_kwh / prognose_kwh * 100) if prognose_kwh > 0 else 0
            spez = (ist_kwh / modul_kwp / anzahl_jahre) if modul_kwp > 0 else 0  # Spez. Ertrag pro Jahr

            string_vergleiche.append(StringVergleich(
                bezeichnung=inv.bezeichnung,
                leistung_kwp=modul_kwp,
                ausrichtung=inv.ausrichtung,
                neigung_grad=inv.neigung_grad,
                prognose_kwh=prognose_kwh,
                ist_kwh=ist_kwh,
                abweichung_kwh=abw_kwh,
                abweichung_prozent=abw_pct,
                spezifischer_ertrag=spez,
            ))

    # ==========================================================================
    # 10. PDF generieren
    # ==========================================================================
    pdf_service = PDFService()
    pdf_buffer = pdf_service.generate_jahresbericht(
        anlage=anlage_dok,
        stromtarif=tarif_dok,
        investitionen=inv_dok_list,
        jahres_kpis=jahres_kpis,
        monats_daten=monats_daten,
        finanz_prognose=finanz_prognose,
        string_vergleiche=string_vergleiche,
        jahr=jahr if not ist_gesamtzeitraum else None,
        start_jahr=start_jahr if ist_gesamtzeitraum else None,
        end_jahr=end_jahr if ist_gesamtzeitraum else None,
    )

    # ==========================================================================
    # 11. Response
    # ==========================================================================
    # Dateiname ohne Umlaute und Sonderzeichen
    safe_name = anlage.anlagenname.replace(" ", "_").replace("/", "-")
    for umlaut, ersatz in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss"),
                           ("Ä", "Ae"), ("Ö", "Oe"), ("Ü", "Ue")]:
        safe_name = safe_name.replace(umlaut, ersatz)

    if ist_gesamtzeitraum:
        filename = f"eedc_anlagenbericht_{safe_name}_{start_jahr}-{end_jahr}.pdf"
    else:
        filename = f"eedc_jahresbericht_{safe_name}_{jahr}.pdf"

    return StreamingResponse(
        pdf_buffer,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
