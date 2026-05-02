"""
Cockpit Komponenten-Zeitreihe — Monatliche Zeitreihe aller Investitions-Komponenten.
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.api.routes.strompreise import lade_tarife_fuer_anlage, resolve_netzbezug_preis_cent
from backend.utils.sonstige_positionen import berechne_sonstige_summen
from backend.api.routes.cockpit._shared import MONATSNAMEN
from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
)
from backend.core.field_definitions import (
    get_eauto_ladung_kwh,
    get_pv_erzeugung_kwh,
    get_sonstiges_verbrauch_kwh,
    get_speicher_netzladung_kwh,
    get_wp_heizenergie_kwh,
    get_wp_strom_kwh,
)

router = APIRouter()


class KomponentenMonat(BaseModel):
    """Monatswerte für alle Komponenten (NUR aus InvestitionMonatsdaten)."""
    jahr: int
    monat: int
    monat_name: str
    speicher_ladung_kwh: float
    speicher_entladung_kwh: float
    speicher_effizienz_prozent: Optional[float]
    speicher_arbitrage_kwh: float
    speicher_arbitrage_preis_cent: Optional[float]
    wp_waerme_kwh: float
    wp_strom_kwh: float
    wp_cop: Optional[float]
    wp_heizung_kwh: float
    wp_warmwasser_kwh: float
    wp_strom_heizen_kwh: float
    wp_strom_warmwasser_kwh: float
    # WP-Ersparnis vs. fossile Heizung — pro Monat berechnet (Drift-Audit A1).
    # Frontend muss nicht selbst rechnen → Auswertungen→Komponenten + Cockpit nutzen
    # denselben Wert wie Monatsbericht/Übersicht.
    wp_ersparnis_euro: float = 0
    emob_km: float
    emob_ladung_kwh: float
    emob_pv_anteil_prozent: Optional[float]
    emob_ladung_pv_kwh: float
    emob_ladung_netz_kwh: float
    emob_ladung_extern_kwh: float
    emob_ladung_extern_euro: float
    emob_v2h_kwh: float
    bkw_erzeugung_kwh: float
    bkw_eigenverbrauch_kwh: float
    bkw_speicher_ladung_kwh: float
    bkw_speicher_entladung_kwh: float
    sonstiges_erzeugung_kwh: float
    sonstiges_verbrauch_kwh: float
    sonderkosten_euro: float
    sonstige_ertraege_euro: float = 0
    sonstige_ausgaben_euro: float = 0
    sonstige_netto_euro: float = 0
    netzbezug_kosten_euro: float = 0
    einspeise_erloes_euro: float = 0


class KomponentenZeitreiheResponse(BaseModel):
    """Zeitreihe aller Komponenten für Auswertungen."""
    anlage_id: int
    hat_speicher: bool
    hat_waermepumpe: bool
    hat_emobilitaet: bool
    hat_balkonkraftwerk: bool
    hat_sonstiges: bool
    hat_arbitrage: bool
    hat_v2h: bool
    monatswerte: list[KomponentenMonat]
    anzahl_monate: int


@router.get("/komponenten-zeitreihe/{anlage_id}", response_model=KomponentenZeitreiheResponse)
async def get_komponenten_zeitreihe(
    anlage_id: int,
    jahr: Optional[int] = Query(None, description="Jahr filtern (None = alle Jahre)"),
    db: AsyncSession = Depends(get_db)
):
    """Zeitreihe aller Komponenten für Auswertungen."""
    # Issue #123: historische Zeitreihe — kein aktiv-Filter, damit spätere
    # Stilllegungen Vergangenheitsdaten nicht rückwirkend entfernen.
    inv_stmt = select(Investition).where(Investition.anlage_id == anlage_id)
    if jahr is not None:
        from backend.utils.investition_filter import aktiv_im_jahr
        inv_stmt = inv_stmt.where(aktiv_im_jahr(jahr))
    inv_result = await db.execute(inv_stmt)
    investitionen = inv_result.scalars().all()

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

    if not all_inv_ids:
        return KomponentenZeitreiheResponse(
            anlage_id=anlage_id,
            hat_speicher=False, hat_waermepumpe=False, hat_emobilitaet=False,
            hat_balkonkraftwerk=False, hat_sonstiges=False, hat_arbitrage=False,
            hat_v2h=False, monatswerte=[], anzahl_monate=0,
        )

    imd_query = select(InvestitionMonatsdaten).where(
        InvestitionMonatsdaten.investition_id.in_(all_inv_ids)
    )
    if jahr is not None:
        imd_query = imd_query.where(InvestitionMonatsdaten.jahr == jahr)
    imd_query = imd_query.order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)

    imd_result = await db.execute(imd_query)
    all_imd = imd_result.scalars().all()

    md_query = select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    if jahr is not None:
        md_query = md_query.where(Monatsdaten.jahr == jahr)
    md_result = await db.execute(md_query)
    monatsdaten_by_key: dict[tuple[int, int], Monatsdaten] = {
        (m.jahr, m.monat): m for m in md_result.scalars().all()
    }

    inv_by_id = {i.id: i for i in investitionen}

    def empty_month_data():
        return {
            "speicher_ladung": 0, "speicher_entladung": 0,
            "speicher_arbitrage": 0, "speicher_arbitrage_preis_sum": 0, "speicher_arbitrage_count": 0,
            "wp_waerme": 0, "wp_strom": 0, "wp_heizung": 0, "wp_warmwasser": 0,
            "wp_strom_heizen": 0, "wp_strom_warmwasser": 0,
            "emob_km": 0, "emob_ladung": 0, "emob_pv_ladung": 0,
            "emob_netz_ladung": 0, "emob_extern_ladung": 0, "emob_extern_euro": 0, "emob_v2h": 0,
            "bkw_erzeugung": 0, "bkw_eigenverbrauch": 0, "bkw_speicher_ladung": 0, "bkw_speicher_entladung": 0,
            "sonstiges_erzeugung": 0, "sonstiges_verbrauch": 0,
            "sonderkosten": 0, "sonstige_ertraege": 0, "sonstige_ausgaben": 0,
        }

    inv_data_by_month: dict[tuple[int, int], dict] = {}
    hat_arbitrage = False
    hat_v2h = False

    for imd in all_imd:
        inv = inv_by_id.get(imd.investition_id)
        if not inv:
            continue

        # Issue #153: Daten vor Anschaffungsdatum ignorieren — sonst fließen
        # historische, vor-Inbetriebnahme-Werte (z. B. unvollständige Test-Daten,
        # Sensor mit anderer Erfassungsmethode) in JAZ/Aggregate ein und
        # verfälschen die Komponenten-Auswertung.
        if inv.anschaffungsdatum:
            anschaffung_jahr = inv.anschaffungsdatum.year
            anschaffung_monat = inv.anschaffungsdatum.month
            if (imd.jahr, imd.monat) < (anschaffung_jahr, anschaffung_monat):
                continue

        key = (imd.jahr, imd.monat)
        if key not in inv_data_by_month:
            inv_data_by_month[key] = empty_month_data()

        data = imd.verbrauch_daten or {}
        d = inv_data_by_month[key]

        summen = berechne_sonstige_summen(data)
        d["sonderkosten"] += summen["ausgaben_euro"]
        d["sonstige_ertraege"] += summen["ertraege_euro"]
        d["sonstige_ausgaben"] += summen["ausgaben_euro"]

        if inv.typ == "speicher":
            d["speicher_ladung"] += data.get("ladung_kwh", 0) or 0
            d["speicher_entladung"] += data.get("entladung_kwh", 0) or 0
            arbitrage_kwh = get_speicher_netzladung_kwh(data)
            if arbitrage_kwh > 0:
                hat_arbitrage = True
                d["speicher_arbitrage"] += arbitrage_kwh
                preis = data.get("speicher_ladepreis_cent", 0) or 0
                if preis > 0:
                    d["speicher_arbitrage_preis_sum"] += preis * arbitrage_kwh
                    d["speicher_arbitrage_count"] += arbitrage_kwh

        elif inv.typ == "waermepumpe":
            heizung = get_wp_heizenergie_kwh(data)
            warmwasser = data.get("warmwasser_kwh", 0) or 0
            waerme_gesamt = data.get("waerme_kwh", 0) or (heizung + warmwasser)
            d["wp_heizung"] += heizung
            d["wp_warmwasser"] += warmwasser
            d["wp_waerme"] += waerme_gesamt
            # #183: bei getrennter Strommessung Gesamt-Strom aus den Einzel-
            # Sensoren bilden — alter Gesamt-Sensor wird ignoriert, sonst
            # driften JAZ-Gesamt und JAZ-Einzel gegeneinander.
            d["wp_strom"] += get_wp_strom_kwh(data, inv.parameter)
            if "strom_heizen_kwh" in data:
                d["wp_strom_heizen"] += data.get("strom_heizen_kwh", 0) or 0
                d["wp_strom_warmwasser"] += data.get("strom_warmwasser_kwh", 0) or 0

        elif inv.typ in ("e-auto", "wallbox"):
            d["emob_km"] += data.get("km_gefahren", 0) or 0
            d["emob_ladung"] += get_eauto_ladung_kwh(data)
            d["emob_pv_ladung"] += data.get("ladung_pv_kwh", 0) or 0
            d["emob_netz_ladung"] += data.get("ladung_netz_kwh", 0) or 0
            d["emob_extern_ladung"] += data.get("ladung_extern_kwh", 0) or 0
            d["emob_extern_euro"] += data.get("ladung_extern_euro", 0) or 0
            v2h = data.get("v2h_entladung_kwh", 0) or 0
            if v2h > 0:
                hat_v2h = True
                d["emob_v2h"] += v2h

        elif inv.typ == "balkonkraftwerk":
            d["bkw_erzeugung"] += get_pv_erzeugung_kwh(data)
            d["bkw_eigenverbrauch"] += data.get("eigenverbrauch_kwh", 0) or 0
            d["bkw_speicher_ladung"] += data.get("speicher_ladung_kwh", 0) or 0
            d["bkw_speicher_entladung"] += data.get("speicher_entladung_kwh", 0) or 0

        elif inv.typ == "sonstiges":
            params = inv.parameter or {}
            kategorie = params.get("kategorie", "")
            if kategorie == "erzeuger":
                d["sonstiges_erzeugung"] += data.get("erzeugung_kwh", 0) or 0
            elif kategorie == "verbraucher":
                d["sonstiges_verbrauch"] += get_sonstiges_verbrauch_kwh(data)
            else:
                d["sonstiges_erzeugung"] += data.get("erzeugung_kwh", 0) or 0
                d["sonstiges_verbrauch"] += get_sonstiges_verbrauch_kwh(data)

    monatswerte = []
    _tarif_cache_kz: dict[date, dict] = {}

    for key in sorted(inv_data_by_month.keys()):
        jahr, monat = key
        d = inv_data_by_month[key]

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

        stichtag = date(jahr, monat, 1)
        if stichtag not in _tarif_cache_kz:
            _tarif_cache_kz[stichtag] = await lade_tarife_fuer_anlage(db, anlage_id, target_date=stichtag)
        m_tarife = _tarif_cache_kz[stichtag]
        m_allgemein = m_tarife.get("allgemein")
        m_preis_cent = m_allgemein.netzbezug_arbeitspreis_cent_kwh if m_allgemein else NETZBEZUG_DEFAULT_CENT
        m_grundpreis = (m_allgemein.grundpreis_euro_monat or 0) if m_allgemein else 0
        m_einspeis_cent = m_allgemein.einspeiseverguetung_cent_kwh if m_allgemein else EINSPEISEVERGUETUNG_DEFAULT_CENT
        m_wp_tarif = m_tarife.get("waermepumpe")
        m_wp_preis_cent = (
            m_wp_tarif.netzbezug_arbeitspreis_cent_kwh
            if m_wp_tarif and m_wp_tarif.netzbezug_arbeitspreis_cent_kwh is not None
            else m_preis_cent
        )
        md = monatsdaten_by_key.get((jahr, monat))
        if md:
            eff_preis = resolve_netzbezug_preis_cent(md, m_preis_cent)
            m_netzbezug_kosten = (md.netzbezug_kwh or 0) * eff_preis / 100 + m_grundpreis
            m_einspeise_erloes = (md.einspeisung_kwh or 0) * m_einspeis_cent / 100
        else:
            m_netzbezug_kosten = 0.0
            m_einspeise_erloes = 0.0

        # WP-Ersparnis pro Monat (Drift-Audit A1, Issue #178).
        # Aggregat über alle WPs, Parameter aus erster aktiver WP als Referenz.
        m_wp_ersparnis = 0.0
        if d["wp_waerme"] > 0:
            wp_invs_in_monat = [
                i for i in investitionen
                if i.typ == "waermepumpe" and (
                    not i.anschaffungsdatum or
                    (jahr, monat) >= (i.anschaffungsdatum.year, i.anschaffungsdatum.month)
                )
            ]
            wp_ref_param = wp_invs_in_monat[0].parameter if wp_invs_in_monat else None
            wp_result = berechne_wp_ersparnis(
                wp_waerme_kwh=d["wp_waerme"],
                wp_strom_kwh=d["wp_strom"],
                wp_strompreis_cent=m_wp_preis_cent,
                wp_parameter=wp_ref_param,
                monats_gaspreis_cent=md.gaspreis_cent_kwh if md else None,
            )
            m_wp_ersparnis = wp_result.ersparnis_euro

        monatswerte.append(KomponentenMonat(
            jahr=jahr, monat=monat, monat_name=MONATSNAMEN[monat],
            speicher_ladung_kwh=round(d["speicher_ladung"], 1),
            speicher_entladung_kwh=round(d["speicher_entladung"], 1),
            speicher_effizienz_prozent=round(speicher_effizienz, 1) if speicher_effizienz else None,
            speicher_arbitrage_kwh=round(d["speicher_arbitrage"], 1),
            speicher_arbitrage_preis_cent=round(speicher_arbitrage_preis, 2) if speicher_arbitrage_preis else None,
            wp_waerme_kwh=round(d["wp_waerme"], 1),
            wp_strom_kwh=round(d["wp_strom"], 1),
            wp_cop=round(wp_cop, 2) if wp_cop else None,
            wp_heizung_kwh=round(d["wp_heizung"], 1),
            wp_warmwasser_kwh=round(d["wp_warmwasser"], 1),
            wp_strom_heizen_kwh=round(d["wp_strom_heizen"], 1),
            wp_strom_warmwasser_kwh=round(d["wp_strom_warmwasser"], 1),
            wp_ersparnis_euro=round(m_wp_ersparnis, 2),
            emob_km=round(d["emob_km"], 0),
            emob_ladung_kwh=round(d["emob_ladung"], 1),
            emob_pv_anteil_prozent=round(emob_pv_anteil, 1) if emob_pv_anteil else None,
            emob_ladung_pv_kwh=round(d["emob_pv_ladung"], 1),
            emob_ladung_netz_kwh=round(d["emob_netz_ladung"], 1),
            emob_ladung_extern_kwh=round(d["emob_extern_ladung"], 1),
            emob_ladung_extern_euro=round(d["emob_extern_euro"], 2),
            emob_v2h_kwh=round(d["emob_v2h"], 1),
            bkw_erzeugung_kwh=round(d["bkw_erzeugung"], 1),
            bkw_eigenverbrauch_kwh=round(d["bkw_eigenverbrauch"], 1),
            bkw_speicher_ladung_kwh=round(d["bkw_speicher_ladung"], 1),
            bkw_speicher_entladung_kwh=round(d["bkw_speicher_entladung"], 1),
            sonstiges_erzeugung_kwh=round(d["sonstiges_erzeugung"], 1),
            sonstiges_verbrauch_kwh=round(d["sonstiges_verbrauch"], 1),
            sonderkosten_euro=round(d["sonderkosten"], 2),
            sonstige_ertraege_euro=round(d["sonstige_ertraege"], 2),
            sonstige_ausgaben_euro=round(d["sonstige_ausgaben"], 2),
            sonstige_netto_euro=round(d["sonstige_ertraege"] - d["sonstige_ausgaben"], 2),
            netzbezug_kosten_euro=round(m_netzbezug_kosten, 2),
            einspeise_erloes_euro=round(m_einspeise_erloes, 2),
        ))

    return KomponentenZeitreiheResponse(
        anlage_id=anlage_id,
        hat_speicher=hat_speicher, hat_waermepumpe=hat_waermepumpe,
        hat_emobilitaet=hat_emobilitaet, hat_balkonkraftwerk=hat_balkonkraftwerk,
        hat_sonstiges=hat_sonstiges, hat_arbitrage=hat_arbitrage, hat_v2h=hat_v2h,
        monatswerte=monatswerte, anzahl_monate=len(monatswerte),
    )
