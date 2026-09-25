"""Aussichten — die Finanz-Prognose (Auswertungen → Finanzen).

GET /api/aussichten/finanzen/{anlage_id} — Hochrechnung aus Monats-Fakten und Finanz-Zeilen (ADR-002/P10), Alternativkosten,
Ertragszerlegung je Investition, Amortisation (Kapitalrechnung-SoT).

Seit Vorlage 7b (18.09.2026) ist `get_finanz_prognose` ein Orchestrator: Kopf (Anlage, heutige Tarife) und Response
stehen hier, die zehn Phasen liegen byte-identisch in `finanz_eingaenge.py` (Laden, Quoten und PVGIS, Kosten und
Parameter), `finanz_rueckblick.py` (bisherige Erträge in drei Schritten), `finanz_prognose.py` (Monatsprognose,
Jahres-Alternativkosten) und `finanz_zerlegung.py` (Komponenten-Beiträge, ROI und Fortschritt je Investition).
Schnittstelle je Phase: Schlüsselwort-Parameter hinein, Rückgabe-Dict heraus; Gate ist der Golden Master
`plans/skript-golden-master-aussichten.py`.
"""
# Reiner Umzug aus `api/routes/aussichten.py` (18.09.2026, Vorlage 7 des Refactorings grosser Dateien):
# Code 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py` haengt den Router ein und exportiert
# die Namen weiter, die Aufrufer und Tests bisher aus dem Modul importierten.

import logging
from collections import defaultdict
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.core.berechnungen.investitions_jahresertrag import jahresertrag_posten
from backend.core.berechnungen.kapitalrechnung import jahres_ersparnis_euro
from backend.models.investition import ERTRAGSFELD_TYPEN, Investition, InvestitionMonatsdaten
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.models.monatsdaten import Monatsdaten
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_einspeise_preis_cent,
    resolve_netzbezug_preis_cent,
    resolve_strompreis_for_komponente,
)
from backend.core.berechnungen import (
    DienstlicheLadungZeile,
    FinanzMonatsZeile,
    annahme_dauer_text,
    berechne_amortisations_fortschritt,
    berechne_dienstliche_ladekosten,
    berechne_finanz_aggregat,
    kapitaleinsatz_euro,
    relevante_kosten_aus_investitionen,
    alter_wirkungsgrad,
    ersetzt_keine_heizung,
    berechne_wp_alternativkosten_ersparnis,
    eigenverbrauchsquote_prozent,
    einspeise_erloes_euro,
    gas_kosten_altanlage,
    verteile_nach_gewichten,
)
from backend.services.strompreis_aggregator import lade_preis_aggregate_je_monat
from backend.services.finanz_zeilen import baue_finanz_zeile
from backend.services.monats_fakten import finanz_zeile_eingabe, lade_monats_fakten
from backend.core.berechnungen.ust_eigenverbrauch import (
    UstJahresanteil,
    bemessungsgrundlage_aus_investitionen,
    ust_eigenverbrauch_fuer_anlage,
)
from backend.core.berechnungen.waermepumpe_kennzahl import heizwaerme_kwh, waerme_gesamt_kwh
from backend.core.field_definitions import (
    get_wp_strom_kwh,
    get_wp_warmwasser_kwh,
)
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
)
from backend.core.berechnungen.speicher_wirtschaftlichkeit import (
    berechne_speicher_ersparnis,
    berechne_v2h_ersparnis,
)
from backend.services.speicher_wirtschaftlichkeit import berechne_effektiver_ladepreis
from backend.core.investition_parameter import (
    PARAM_E_AUTO,
    PARAM_E_AUTO_DEFAULTS,
    PARAM_SPEICHER,
    PARAM_SPEICHER_DEFAULTS,
    PARAM_WAERMEPUMPE,
    PARAM_WAERMEPUMPE_DEFAULTS,
    ist_dienstlich,
)
from backend.services.wetter.pvgis import get_pvgis_tmy_defaults
from backend.core.berechnungen.erzeuger_traeger import erzeuger_traeger
from backend.core.investition_kennwerte import get_erzeuger_kwp
from backend.api.routes.aussichten.basis import MONATSNAMEN
from backend.api.routes.aussichten.schemas import ErtragJeInvestitionSchema, FinanzPrognoseMonatSchema, FinanzPrognoseResponse, KomponentenBeitragSchema
# Vorlage 7b: die Phasen der Finanz-Prognose (Bauform wie `investitionen/roi_*.py`, nur ohne Lazy-Import —
# die Phasenmodule brauchen nichts aus diesem Modul, ein Zyklus entsteht nicht).
from backend.api.routes.aussichten.finanz_eingaenge import (
    lade_finanz_eingaenge,
    quoten_und_pvgis,
    investitionen_und_parameter,
)
from backend.api.routes.aussichten.finanz_rueckblick import (
    finanz_zeilen_und_tarife,
    alternativkosten_rueckblick,
    bisherige_ertraege_summe,
)
from backend.api.routes.aussichten.finanz_prognose import monatsprognose, jahres_alternativkosten
from backend.api.routes.aussichten.finanz_zerlegung import (
    komponenten_beitraege_zusammenstellen,
    roi_und_fortschritt,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/finanzen/{anlage_id}", response_model=FinanzPrognoseResponse)
async def get_finanz_prognose(
    anlage_id: int,
    monate: int = Query(default=12, ge=1, le=24, description="Anzahl Monate (1-24)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Finanzprognose für PV-Erträge inkl. aller Komponenten.

    Berücksichtigt:
    - PV-Erzeugung (aus PVGIS oder historisch)
    - Speicher (Eigenverbrauchserhöhung)
    - E-Auto mit V2H (Rückspeisung ins Haus)
    - Wärmepumpe (PV-Direktverbrauch)
    - ROI-Fortschritt und Amortisations-Prognose
    """

    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise not_found("Anlage")

    # Tarife laden (allgemein + Spezialtarife)
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein_tarif = tarife.get("allgemein")
    wp_tarif = tarife.get("waermepumpe")

    # #392: bewusst der HEUTIGE Stammwert — diese Variable speist die
    # Hochrechnung nach vorn, und künftige Monate haben keinen Monatswert.
    einspeiseverguetung = allgemein_tarif.einspeiseverguetung_cent_kwh if allgemein_tarif else EINSPEISEVERGUETUNG_DEFAULT_CENT
    netzbezug_preis = allgemein_tarif.netzbezug_arbeitspreis_cent_kwh if allgemein_tarif else NETZBEZUG_DEFAULT_CENT
    wp_netzbezug_preis = wp_tarif.netzbezug_arbeitspreis_cent_kwh if wp_tarif else netzbezug_preis

    # ── lade_finanz_eingaenge (Vorlage 7b: Phase in finanz_eingaenge.py, Schnittstelle 3 ein / 25 aus) ──
    _out = await lade_finanz_eingaenge(anlage=anlage, anlage_id=anlage_id, db=db)
    if "_heute" in _out: _heute = _out["_heute"]
    if "_preis_messung" in _out: _preis_messung = _out["_preis_messung"]
    if "alle_investitionen" in _out: alle_investitionen = _out["alle_investitionen"]
    if "anlagenleistung_kwp" in _out: anlagenleistung_kwp = _out["anlagenleistung_kwp"]
    if "balkonkraftwerke" in _out: balkonkraftwerke = _out["balkonkraftwerke"]
    if "e_autos" in _out: e_autos = _out["e_autos"]
    if "eauto_pv_pro_inv" in _out: eauto_pv_pro_inv = _out["eauto_pv_pro_inv"]
    if "eigenverbrauch_pro_monat" in _out: eigenverbrauch_pro_monat = _out["eigenverbrauch_pro_monat"]
    if "emob_pool_ctx" in _out: emob_pool_ctx = _out["emob_pool_ctx"]
    if "fakten" in _out: fakten = _out["fakten"]
    if "gesamt_eauto_pv" in _out: gesamt_eauto_pv = _out["gesamt_eauto_pv"]
    if "gesamt_ev" in _out: gesamt_ev = _out["gesamt_ev"]
    if "gesamt_pv" in _out: gesamt_pv = _out["gesamt_pv"]
    if "gesamt_speicher_entladung" in _out: gesamt_speicher_entladung = _out["gesamt_speicher_entladung"]
    if "gesamt_speicher_ladung" in _out: gesamt_speicher_ladung = _out["gesamt_speicher_ladung"]
    if "gesamt_v2h" in _out: gesamt_v2h = _out["gesamt_v2h"]
    if "gesamt_wp_strom" in _out: gesamt_wp_strom = _out["gesamt_wp_strom"]
    if "historische_inv_daten" in _out: historische_inv_daten = _out["historische_inv_daten"]
    if "inv_by_id_hist" in _out: inv_by_id_hist = _out["inv_by_id_hist"]
    if "monatsdaten" in _out: monatsdaten = _out["monatsdaten"]
    if "monatsdaten_dict" in _out: monatsdaten_dict = _out["monatsdaten_dict"]
    if "pv_pro_monat" in _out: pv_pro_monat = _out["pv_pro_monat"]
    if "speicher" in _out: speicher = _out["speicher"]
    if "waermepumpen" in _out: waermepumpen = _out["waermepumpen"]
    if "wp_strom_pro_inv" in _out: wp_strom_pro_inv = _out["wp_strom_pro_inv"]
    # ── quoten_und_pvgis (Vorlage 7b: Phase in finanz_eingaenge.py, Schnittstelle 15 ein / 10 aus) ──
    _out = await quoten_und_pvgis(
        anlage_id=anlage_id,
        db=db,
        e_autos=e_autos,
        eigenverbrauch_pro_monat=eigenverbrauch_pro_monat,
        gesamt_eauto_pv=gesamt_eauto_pv,
        gesamt_ev=gesamt_ev,
        gesamt_pv=gesamt_pv,
        gesamt_speicher_entladung=gesamt_speicher_entladung,
        gesamt_speicher_ladung=gesamt_speicher_ladung,
        gesamt_v2h=gesamt_v2h,
        gesamt_wp_strom=gesamt_wp_strom,
        monatsdaten=monatsdaten,
        pv_pro_monat=pv_pro_monat,
        speicher=speicher,
        waermepumpen=waermepumpen,
    )
    if "anzahl_monate_hist" in _out: anzahl_monate_hist = _out["anzahl_monate_hist"]
    if "avg_hist_ev_quote" in _out: avg_hist_ev_quote = _out["avg_hist_ev_quote"]
    if "basis_ev_quote" in _out: basis_ev_quote = _out["basis_ev_quote"]
    if "eauto_pv_monat" in _out: eauto_pv_monat = _out["eauto_pv_monat"]
    if "hist_ev_quoten" in _out: hist_ev_quoten = _out["hist_ev_quoten"]
    if "pvgis" in _out: pvgis = _out["pvgis"]
    if "pvgis_monatswerte" in _out: pvgis_monatswerte = _out["pvgis_monatswerte"]
    if "speicher_ev_erhohung_monat" in _out: speicher_ev_erhohung_monat = _out["speicher_ev_erhohung_monat"]
    if "v2h_beitrag_monat" in _out: v2h_beitrag_monat = _out["v2h_beitrag_monat"]
    if "wp_strom_monat_avg" in _out: wp_strom_monat_avg = _out["wp_strom_monat_avg"]
    # ── investitionen_und_parameter (Vorlage 7b: Phase in finanz_eingaenge.py, Schnittstelle 6 ein / 10 aus) ──
    _out = investitionen_und_parameter(
        alle_investitionen=alle_investitionen,
        anzahl_monate_hist=anzahl_monate_hist,
        e_autos=e_autos,
        eauto_pv_pro_inv=eauto_pv_pro_inv,
        waermepumpen=waermepumpen,
        wp_strom_pro_inv=wp_strom_pro_inv,
    )
    if "eauto_aggregate" in _out: eauto_aggregate = _out["eauto_aggregate"]
    if "investition_eauto_mehrkosten" in _out: investition_eauto_mehrkosten = _out["investition_eauto_mehrkosten"]
    if "investition_gesamt" in _out: investition_gesamt = _out["investition_gesamt"]
    if "investition_pv_system" in _out: investition_pv_system = _out["investition_pv_system"]
    if "investition_sonstige" in _out: investition_sonstige = _out["investition_sonstige"]
    if "investition_wp_mehrkosten" in _out: investition_wp_mehrkosten = _out["investition_wp_mehrkosten"]
    if "wp_aggregate" in _out: wp_aggregate = _out["wp_aggregate"]
    if "wp_alternativ_zusatzkosten_jahr" in _out: wp_alternativ_zusatzkosten_jahr = _out["wp_alternativ_zusatzkosten_jahr"]
    if "wp_mit_ersatz" in _out: wp_mit_ersatz = _out["wp_mit_ersatz"]
    if "wp_strom_mit_ersatz_monat_avg" in _out: wp_strom_mit_ersatz_monat_avg = _out["wp_strom_mit_ersatz_monat_avg"]
    # ── finanz_zeilen_und_tarife (Vorlage 7b: Phase in finanz_rueckblick.py, Schnittstelle 7 ein / 7 aus) ──
    _out = await finanz_zeilen_und_tarife(
        _heute=_heute,
        _preis_messung=_preis_messung,
        alle_investitionen=alle_investitionen,
        anlage_id=anlage_id,
        db=db,
        fakten=fakten,
        monatsdaten=monatsdaten,
    )
    if "_tarife_fuer_stichtag" in _out: _tarife_fuer_stichtag = _out["_tarife_fuer_stichtag"]
    if "betriebskosten_ges" in _out: betriebskosten_ges = _out["betriebskosten_ges"]
    if "bisherige_eauto_ersparnis" in _out: bisherige_eauto_ersparnis = _out["bisherige_eauto_ersparnis"]
    if "bisherige_ertraege" in _out: bisherige_ertraege = _out["bisherige_ertraege"]
    if "ertrag_jahr_ges" in _out: ertrag_jahr_ges = _out["ertrag_jahr_ges"]
    if "finanz_zeilen" in _out: finanz_zeilen = _out["finanz_zeilen"]
    if "finanz_zeilen_je_jahr" in _out: finanz_zeilen_je_jahr = _out["finanz_zeilen_je_jahr"]
    # ── alternativkosten_rueckblick (Vorlage 7b: Phase in finanz_rueckblick.py, Schnittstelle 13 ein / 7 aus) ──
    _out = await alternativkosten_rueckblick(
        _tarife_fuer_stichtag=_tarife_fuer_stichtag,
        e_autos=e_autos,
        eauto_aggregate=eauto_aggregate,
        emob_pool_ctx=emob_pool_ctx,
        historische_inv_daten=historische_inv_daten,
        inv_by_id_hist=inv_by_id_hist,
        monatsdaten=monatsdaten,
        monatsdaten_dict=monatsdaten_dict,
        netzbezug_preis=netzbezug_preis,
        waermepumpen=waermepumpen,
        wp_aggregate=wp_aggregate,
        wp_mit_ersatz=wp_mit_ersatz,
        wp_netzbezug_preis=wp_netzbezug_preis,
    )
    if "bisherige_eauto_ersparnis" in _out: bisherige_eauto_ersparnis = _out["bisherige_eauto_ersparnis"]
    if "bisherige_wp_ersparnis" in _out: bisherige_wp_ersparnis = _out["bisherige_wp_ersparnis"]
    if "gaspreis_by_periode" in _out: gaspreis_by_periode = _out["gaspreis_by_periode"]
    if "gesamt_eauto_netz" in _out: gesamt_eauto_netz = _out["gesamt_eauto_netz"]
    if "gesamt_km" in _out: gesamt_km = _out["gesamt_km"]
    if "gesamt_wp_thermisch" in _out: gesamt_wp_thermisch = _out["gesamt_wp_thermisch"]
    if "wp_preis_by_periode" in _out: wp_preis_by_periode = _out["wp_preis_by_periode"]
    # ── bisherige_ertraege_summe (Vorlage 7b: Phase in finanz_rueckblick.py, Schnittstelle 9 ein / 8 aus) ──
    _out = bisherige_ertraege_summe(
        alle_investitionen=alle_investitionen,
        anlage=anlage,
        betriebskosten_ges=betriebskosten_ges,
        bisherige_eauto_ersparnis=bisherige_eauto_ersparnis,
        bisherige_wp_ersparnis=bisherige_wp_ersparnis,
        fakten=fakten,
        finanz_zeilen=finanz_zeilen,
        finanz_zeilen_je_jahr=finanz_zeilen_je_jahr,
        pv_pro_monat=pv_pro_monat,
    )
    if "_finanz" in _out: _finanz = _out["_finanz"]
    if "betriebskosten_hist_je_inv" in _out: betriebskosten_hist_je_inv = _out["betriebskosten_hist_je_inv"]
    if "bisherige_bkw_ersparnis" in _out: bisherige_bkw_ersparnis = _out["bisherige_bkw_ersparnis"]
    if "bisherige_dienstlich_ladekosten" in _out: bisherige_dienstlich_ladekosten = _out["bisherige_dienstlich_ladekosten"]
    if "bisherige_ertraege" in _out: bisherige_ertraege = _out["bisherige_ertraege"]
    if "bisherige_sonstige_ausgaben" in _out: bisherige_sonstige_ausgaben = _out["bisherige_sonstige_ausgaben"]
    if "bisherige_sonstige_ertraege" in _out: bisherige_sonstige_ertraege = _out["bisherige_sonstige_ertraege"]
    if "bisherige_ust_eigenverbrauch" in _out: bisherige_ust_eigenverbrauch = _out["bisherige_ust_eigenverbrauch"]
    # ── monatsprognose (Vorlage 7b: Phase in finanz_prognose.py, Schnittstelle 18 ein / 15 aus) ──
    _out = monatsprognose(
        anlage=anlage,
        anlagenleistung_kwp=anlagenleistung_kwp,
        avg_hist_ev_quote=avg_hist_ev_quote,
        basis_ev_quote=basis_ev_quote,
        e_autos=e_autos,
        eauto_pv_monat=eauto_pv_monat,
        einspeiseverguetung=einspeiseverguetung,
        hist_ev_quoten=hist_ev_quoten,
        monate=monate,
        netzbezug_preis=netzbezug_preis,
        pvgis_monatswerte=pvgis_monatswerte,
        speicher=speicher,
        speicher_ev_erhohung_monat=speicher_ev_erhohung_monat,
        v2h_beitrag_monat=v2h_beitrag_monat,
        waermepumpen=waermepumpen,
        wp_mit_ersatz=wp_mit_ersatz,
        wp_strom_mit_ersatz_monat_avg=wp_strom_mit_ersatz_monat_avg,
        wp_strom_monat_avg=wp_strom_monat_avg,
    )
    if "_gepflegter_pv_anteil" in _out: _gepflegter_pv_anteil = _out["_gepflegter_pv_anteil"]
    if "heute" in _out: heute = _out["heute"]
    if "jahres_eauto_pv" in _out: jahres_eauto_pv = _out["jahres_eauto_pv"]
    if "jahres_eigenverbrauch" in _out: jahres_eigenverbrauch = _out["jahres_eigenverbrauch"]
    if "jahres_einspeise_erloes" in _out: jahres_einspeise_erloes = _out["jahres_einspeise_erloes"]
    if "jahres_einspeisung" in _out: jahres_einspeisung = _out["jahres_einspeisung"]
    if "jahres_erzeugung" in _out: jahres_erzeugung = _out["jahres_erzeugung"]
    if "jahres_ev_ersparnis" in _out: jahres_ev_ersparnis = _out["jahres_ev_ersparnis"]
    if "jahres_speicher_beitrag" in _out: jahres_speicher_beitrag = _out["jahres_speicher_beitrag"]
    if "jahres_v2h_beitrag" in _out: jahres_v2h_beitrag = _out["jahres_v2h_beitrag"]
    if "jahres_wp_verbrauch" in _out: jahres_wp_verbrauch = _out["jahres_wp_verbrauch"]
    if "jahres_wp_verbrauch_mit_ersatz" in _out: jahres_wp_verbrauch_mit_ersatz = _out["jahres_wp_verbrauch_mit_ersatz"]
    if "monatswerte" in _out: monatswerte = _out["monatswerte"]
    if "start_jahr" in _out: start_jahr = _out["start_jahr"]
    if "start_monat" in _out: start_monat = _out["start_monat"]
    # ── jahres_alternativkosten (Vorlage 7b: Phase in finanz_prognose.py, Schnittstelle 32 ein / 7 aus) ──
    _out = jahres_alternativkosten(
        _gepflegter_pv_anteil=_gepflegter_pv_anteil,
        alle_investitionen=alle_investitionen,
        anlage=anlage,
        anzahl_monate_hist=anzahl_monate_hist,
        balkonkraftwerke=balkonkraftwerke,
        betriebskosten_ges=betriebskosten_ges,
        bisherige_bkw_ersparnis=bisherige_bkw_ersparnis,
        bisherige_dienstlich_ladekosten=bisherige_dienstlich_ladekosten,
        e_autos=e_autos,
        eauto_aggregate=eauto_aggregate,
        ertrag_jahr_ges=ertrag_jahr_ges,
        gesamt_eauto_netz=gesamt_eauto_netz,
        gesamt_eauto_pv=gesamt_eauto_pv,
        gesamt_km=gesamt_km,
        gesamt_wp_strom=gesamt_wp_strom,
        gesamt_wp_thermisch=gesamt_wp_thermisch,
        heute=heute,
        jahres_eauto_pv=jahres_eauto_pv,
        jahres_eigenverbrauch=jahres_eigenverbrauch,
        jahres_einspeise_erloes=jahres_einspeise_erloes,
        jahres_erzeugung=jahres_erzeugung,
        jahres_ev_ersparnis=jahres_ev_ersparnis,
        jahres_wp_verbrauch=jahres_wp_verbrauch,
        jahres_wp_verbrauch_mit_ersatz=jahres_wp_verbrauch_mit_ersatz,
        monatsdaten=monatsdaten,
        netzbezug_preis=netzbezug_preis,
        waermepumpen=waermepumpen,
        wp_aggregate=wp_aggregate,
        wp_alternativ_zusatzkosten_jahr=wp_alternativ_zusatzkosten_jahr,
        wp_mit_ersatz=wp_mit_ersatz,
        wp_netzbezug_preis=wp_netzbezug_preis,
        wp_strom_pro_inv=wp_strom_pro_inv,
    )
    if "jahres_eauto_km_ersparnis" in _out: jahres_eauto_km_ersparnis = _out["jahres_eauto_km_ersparnis"]
    if "jahres_netto_ertrag" in _out: jahres_netto_ertrag = _out["jahres_netto_ertrag"]
    if "jahres_wp_ersparnis" in _out: jahres_wp_ersparnis = _out["jahres_wp_ersparnis"]
    if "ust_eigenverbrauch" in _out: ust_eigenverbrauch = _out["ust_eigenverbrauch"]
    if "wp_ersparnis_je_inv" in _out: wp_ersparnis_je_inv = _out["wp_ersparnis_je_inv"]
    if "wp_pv_kwh_je_inv" in _out: wp_pv_kwh_je_inv = _out["wp_pv_kwh_je_inv"]
    if "wp_pv_kwh_total" in _out: wp_pv_kwh_total = _out["wp_pv_kwh_total"]
    # ── komponenten_beitraege_zusammenstellen (Vorlage 7b: Phase in finanz_zerlegung.py, Schnittstelle 14 ein / 4 aus) ──
    _out = await komponenten_beitraege_zusammenstellen(
        anlage_id=anlage_id,
        db=db,
        e_autos=e_autos,
        eauto_aggregate=eauto_aggregate,
        einspeiseverguetung=einspeiseverguetung,
        historische_inv_daten=historische_inv_daten,
        jahres_eauto_pv=jahres_eauto_pv,
        jahres_speicher_beitrag=jahres_speicher_beitrag,
        jahres_v2h_beitrag=jahres_v2h_beitrag,
        netzbezug_preis=netzbezug_preis,
        speicher=speicher,
        waermepumpen=waermepumpen,
        wp_ersparnis_je_inv=wp_ersparnis_je_inv,
        wp_pv_kwh_je_inv=wp_pv_kwh_je_inv,
    )
    if "komponenten_beitraege" in _out: komponenten_beitraege = _out["komponenten_beitraege"]
    if "prog_speicher_netzladung" in _out: prog_speicher_netzladung = _out["prog_speicher_netzladung"]
    if "speicher_lade_preis_cent" in _out: speicher_lade_preis_cent = _out["speicher_lade_preis_cent"]
    if "speicher_wirkungsgrad_avg" in _out: speicher_wirkungsgrad_avg = _out["speicher_wirkungsgrad_avg"]
    # ── roi_und_fortschritt (Vorlage 7b: Phase in finanz_zerlegung.py, Schnittstelle 17 ein / 7 aus) ──
    _out = roi_und_fortschritt(
        _finanz=_finanz,
        alle_investitionen=alle_investitionen,
        betriebskosten_hist_je_inv=betriebskosten_hist_je_inv,
        bisherige_ertraege=bisherige_ertraege,
        bisherige_sonstige_ausgaben=bisherige_sonstige_ausgaben,
        bisherige_sonstige_ertraege=bisherige_sonstige_ertraege,
        bisherige_ust_eigenverbrauch=bisherige_ust_eigenverbrauch,
        eauto_aggregate=eauto_aggregate,
        fakten=fakten,
        gaspreis_by_periode=gaspreis_by_periode,
        heute=heute,
        historische_inv_daten=historische_inv_daten,
        investition_gesamt=investition_gesamt,
        jahres_netto_ertrag=jahres_netto_ertrag,
        waermepumpen=waermepumpen,
        wp_netzbezug_preis=wp_netzbezug_preis,
        wp_preis_by_periode=wp_preis_by_periode,
    )
    if "_zerlegung" in _out: _zerlegung = _out["_zerlegung"]
    if "amortisation_erreicht" in _out: amortisation_erreicht = _out["amortisation_erreicht"]
    if "amortisation_prognose_jahr" in _out: amortisation_prognose_jahr = _out["amortisation_prognose_jahr"]
    if "fortschritt_je_investition" in _out: fortschritt_je_investition = _out["fortschritt_je_investition"]
    if "kapitaleinsatz" in _out: kapitaleinsatz = _out["kapitaleinsatz"]
    if "restlaufzeit_monate" in _out: restlaufzeit_monate = _out["restlaufzeit_monate"]
    if "roi_fortschritt" in _out: roi_fortschritt = _out["roi_fortschritt"]
    # =====================================================================
    # RESPONSE
    # =====================================================================
    datenquellen = ["strompreise", "historische-daten"]
    if pvgis:
        datenquellen.insert(0, "pvgis-prognose")
    else:
        datenquellen.insert(0, "pvgis-tmy")

    # Drift-Audit D: Spread-Modell für Speicher + V2H (Bezug − Einspeise).
    # Etappe B (#264): mit PV/Netz-Anteil aus der historischen Aufteilung
    # (siehe Speicher-Netz-Anteil-Block oben — gleiche Args).
    speicher_ersparnis_euro = berechne_speicher_ersparnis(
        entladung_kwh=jahres_speicher_beitrag,
        bezug_preis_cent=netzbezug_preis,
        einspeise_verg_cent=einspeiseverguetung,
        ladung_netz_kwh=prog_speicher_netzladung,
        wirkungsgrad_prozent=speicher_wirkungsgrad_avg,
        lade_preis_cent=speicher_lade_preis_cent,
    ).ersparnis_euro
    v2h_ersparnis_euro = berechne_v2h_ersparnis(
        v2h_entladung_kwh=jahres_v2h_beitrag,
        bezug_preis_cent=netzbezug_preis,
        einspeise_verg_cent=einspeiseverguetung,
    ).ersparnis_euro
    eauto_ersparnis_euro = jahres_eauto_pv * netzbezug_preis / 100
    # N-354: `wp_pv_kwh_total` ist Σ der Gerätebeiträge von oben — dieselbe
    # Quelle wie die Liste, keine zweite Bildungsvorschrift.
    wp_pv_ersparnis_euro = wp_pv_kwh_total * netzbezug_preis / 100

    return FinanzPrognoseResponse(
        anlage_id=anlage_id,
        anlagenname=anlage.anlagenname or f"Anlage {anlage_id}",
        prognose_zeitraum={
            "von": f"{start_jahr}-{start_monat:02d}",
            "bis": f"{monatswerte[-1].jahr}-{monatswerte[-1].monat:02d}" if monatswerte else None,
        },
        einspeiseverguetung_cent_kwh=einspeiseverguetung,
        netzbezug_preis_cent_kwh=netzbezug_preis,
        grundpreis_euro_monat=allgemein_tarif.grundpreis_euro_monat or 0 if allgemein_tarif else 0,
        jahres_erzeugung_kwh=round(jahres_erzeugung, 0),
        jahres_eigenverbrauch_kwh=round(jahres_eigenverbrauch, 0),
        jahres_einspeisung_kwh=round(jahres_einspeisung, 0),
        eigenverbrauchsquote_prozent=round(
            eigenverbrauchsquote_prozent(jahres_eigenverbrauch, jahres_erzeugung), 1
        ),
        jahres_einspeise_erloes_euro=round(jahres_einspeise_erloes, 2),
        jahres_ev_ersparnis_euro=round(jahres_ev_ersparnis, 2),
        ust_eigenverbrauch_euro=round(ust_eigenverbrauch, 2) if ust_eigenverbrauch > 0 else None,
        jahres_netto_ertrag_euro=round(jahres_netto_ertrag, 2),
        komponenten_beitraege=komponenten_beitraege,
        speicher_ev_erhoehung_kwh=round(jahres_speicher_beitrag, 0),
        speicher_ev_erhoehung_euro=round(speicher_ersparnis_euro, 2),
        v2h_rueckspeisung_kwh=round(jahres_v2h_beitrag, 0),
        v2h_ersparnis_euro=round(v2h_ersparnis_euro, 2),
        eauto_ladung_pv_kwh=round(jahres_eauto_pv, 0),
        eauto_ersparnis_euro=round(eauto_ersparnis_euro, 2),
        wp_stromverbrauch_kwh=round(jahres_wp_verbrauch, 0),
        wp_pv_anteil_kwh=round(wp_pv_kwh_total, 0),
        wp_pv_ersparnis_euro=round(wp_pv_ersparnis_euro, 2),
        wp_alternativ_ersparnis_euro=round(jahres_wp_ersparnis, 2),
        eauto_alternativ_ersparnis_euro=round(jahres_eauto_km_ersparnis, 2),
        investition_pv_system_euro=round(investition_pv_system, 2),
        investition_wp_mehrkosten_euro=round(investition_wp_mehrkosten, 2),
        investition_eauto_mehrkosten_euro=round(investition_eauto_mehrkosten, 2),
        investition_sonstige_euro=round(investition_sonstige, 2),
        investition_gesamt_euro=round(investition_gesamt, 2),  # PV + Mehrkosten + Sonstige
        kapitaleinsatz_euro=round(kapitaleinsatz, 2),
        bisherige_ertraege_euro=round(bisherige_ertraege, 2),
        amortisations_fortschritt_prozent=round(roi_fortschritt, 1),
        amortisation_erreicht=amortisation_erreicht,
        amortisation_prognose_jahr=amortisation_prognose_jahr,
        restlaufzeit_bis_amortisation_monate=restlaufzeit_monate,
        # `betriebskosten_ges` ist genau der Betrag, der oben in
        # `jahres_netto_ertrag` abgezogen wurde — die Restlaufzeit rechnet mit
        # dieser Zahl, also beschreibt der Satz ihre eigene Grundlage.
        amortisation_annahme=annahme_dauer_text(
            betriebskosten_jahr_euro=betriebskosten_ges,
        ),
        ertraege_je_investition=fortschritt_je_investition,
        ertraege_nicht_zurechenbar_euro=_zerlegung.nicht_zurechenbar_euro,
        monatswerte=monatswerte,
        datenquellen=datenquellen,
    )
