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
from backend.core.berechnungen import eauto_effizienz_100km, einspeise_erloes_euro
from backend.services.einspeise_erloes_service import get_neg_preis_einspeisung_monat
from backend.utils.sonstige_positionen import aggregiere_sonstige_je_monat
from backend.api.routes.cockpit._shared import MONATSNAMEN
from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis
from backend.services.eauto_wirtschaftlichkeit import get_emob_heimladung_canonical
from backend.core.investition_parameter import ist_dienstlich
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
)
from backend.core.field_definitions import (
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
    # Ø Verbrauch (kWh/100 km) zentral via core/berechnungen/emob.py — gemessener
    # verbrauch_kwh hat Vorrang, sonst Ladungs-Näherung. `quelle` ∈ gemessen|ladung|keine
    # für ehrliches UI-Label; Frontend rechnet NICHT mehr selbst (Drift-Schutz).
    emob_verbrauch_kwh: float = 0
    emob_verbrauch_100km: Optional[float] = None
    emob_verbrauch_quelle: str = "keine"
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
    # Aggregat über alle Monate via Helper (Σverbrauch/Σladung/Σkm) — Bild „Auswertungen
    # → Komponenten" zeigt diesen Wert, statt im Frontend zu summieren+teilen.
    emob_verbrauch_100km_gesamt: Optional[float] = None
    emob_verbrauch_quelle_gesamt: str = "keine"


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

    # Early-Return nur bei GAR keiner Investition. Bei reinen PV-/WR-Anlagen
    # (all_inv_ids leer, aber investitionen vorhanden) NICHT abbrechen — sonst
    # gingen am PV-Modul/Wechselrichter gepflegte Sonstige-Positionen verloren
    # (#310). Der Energie-Loop bleibt dann leer, die Sonstige-Aggregation läuft.
    if not investitionen:
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
            # E-Mobilität: rohe IMD-`verbrauch_daten` je Quelle sammeln, erst
            # beim Konsolidieren unten via `get_emob_heimladung_canonical` zu EINER
            # konsistenten Trias poolen. Wallbox-IMD und E-Auto-IMD messen oft
            # denselben Stromfluss aus zwei Perspektiven → feldweises max()
            # über pv/netz konnte sie mischen (#262 junky84: PV-Anteil > 100 %).
            # km + v2h kommen nur vom E-Auto.
            "eauto_imds": [], "wb_imds": [],
            "eauto_km": 0, "eauto_v2h": 0, "eauto_verbrauch": 0,
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

        # Issue #153 / #236: SoT-Filter inkl. stilllegungsdatum — vor-Inbetriebnahme-
        # bzw. nach-Stilllegungs-Werte sollen nicht in JAZ/Aggregate fließen.
        if not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
            continue

        key = (imd.jahr, imd.monat)
        if key not in inv_data_by_month:
            inv_data_by_month[key] = empty_month_data()

        data = imd.verbrauch_daten or {}
        d = inv_data_by_month[key]

        # Sonstige Erträge/Ausgaben NICHT hier — dieser Loop ist typ-gefiltert
        # (all_inv_ids ohne PV/WR) und laufzeit-gefiltert (ist_aktiv_im_monat).
        # Finanzpositionen werden unten entkoppelt über ALLE Investitionen
        # aggregiert (#310). Siehe `aggregiere_sonstige_je_monat`.
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
            # Dienstwagen rausfiltern (Joachim-Pattern, feedback_dienstwagen_alle_checks.md):
            # ist_dienstlich-Komponenten gehören in dienstliche Ladekosten,
            # nicht in den E-Mobilitäts-Pool der eigenen Anlage.
            if ist_dienstlich(inv):
                continue
            # Rohe IMD je Quelle sammeln — Pooling zentral via
            # `get_emob_heimladung_canonical` weiter unten. km + v2h nur vom E-Auto.
            if inv.typ == "e-auto":
                d["eauto_imds"].append(data)
                d["eauto_km"] += data.get("km_gefahren", 0) or 0
                # Gemessener Fahrverbrauch (für Ø Verbrauch kWh/100 km mit Vorrang
                # vor der Ladungs-Näherung — selbe Quelle wie E-Auto-Dashboard).
                d["eauto_verbrauch"] += data.get("verbrauch_kwh", 0) or 0
                v2h = data.get("v2h_entladung_kwh", 0) or 0
                if v2h > 0:
                    hat_v2h = True
                    d["eauto_v2h"] += v2h
            else:  # wallbox
                d["wb_imds"].append(data)

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
    # E-Mobilität: Σ über alle Monate für das Komponenten-Aggregat (Ø Verbrauch
    # via Helper über die Summen — nicht das Mittel der Monats-Prozente).
    agg_emob_verbrauch = 0.0
    agg_emob_ladung = 0.0
    agg_emob_km = 0.0
    _tarif_cache_kz: dict[date, dict] = {}

    # Sonstige Erträge/Ausgaben (#310 rilmor-mhrs) — entkoppelt vom TYP-gefilterten
    # Energie-Loop (der `all_inv_ids` ohne PV-Modul/Wechselrichter kennt): über
    # ALLE Investitionstypen, sonst zählt diese Sicht einen am Wechselrichter
    # gepflegten Ertrag NICHT mit, obwohl der Monatsbericht ihn zeigt.
    # ABER: dieselbe Sichtbarkeitsregel wie überall (detLAN [[feedback_anschaffungsdatum_grenze]],
    # #236/#308) — nur `aktiv` (aktiv=False = wie gelöscht) und nur innerhalb der
    # Laufzeit Anschaffung→Stilllegung. Finanzpositionen sind KEINE Ausnahme.
    # Symmetrie zum Monatsbericht: test_sonstige_readsite_symmetrie.
    aktive_inv_ids = [i.id for i in investitionen if i.aktiv]
    if aktive_inv_ids:
        sonstige_query = select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id.in_(aktive_inv_ids)
        )
        if jahr is not None:
            sonstige_query = sonstige_query.where(InvestitionMonatsdaten.jahr == jahr)
        sonstige_rows = [
            imd for imd in (await db.execute(sonstige_query)).scalars().all()
            if inv_by_id[imd.investition_id].ist_aktiv_im_monat(imd.jahr, imd.monat)
        ]
        for (s_jahr, s_monat), summen in aggregiere_sonstige_je_monat(sonstige_rows).items():
            # Monat muss in der Response existieren, auch wenn er KEINE
            # Komponenten-Energiedaten hat (reiner Sonstige-Monat).
            d = inv_data_by_month.setdefault((s_jahr, s_monat), empty_month_data())
            d["sonstige_ertraege"] = summen["ertraege_euro"]
            d["sonstige_ausgaben"] = summen["ausgaben_euro"]
            d["sonderkosten"] = summen["ausgaben_euro"]

    for key in sorted(inv_data_by_month.keys()):
        jahr, monat = key
        d = inv_data_by_month[key]

        speicher_effizienz = (
            d["speicher_entladung"] / d["speicher_ladung"] * 100
        ) if d["speicher_ladung"] > 0 else None

        speicher_arbitrage_preis = (
            d["speicher_arbitrage_preis_sum"] / d["speicher_arbitrage_count"]
        ) if d["speicher_arbitrage_count"] > 0 else None

        # JAZ/COP nur wenn beide Seiten gemessen sind (siehe uebersicht.py
        # für Erklärung — bei Split-Klimaanlagen kein Wärmemengenzähler).
        wp_cop = (d["wp_waerme"] / d["wp_strom"]) if d["wp_strom"] > 0 and d["wp_waerme"] > 0 else None

        # E-Mobilitäts-Pool: EINE Quelle gewinnt die konsistente Trias
        # (#262 — feldweises max() über pv/netz ergab PV-Anteil > 100 %).
        # km + v2h kommen nur vom E-Auto (Vehicle-to-Home-Sicht).
        emob_pool = get_emob_heimladung_canonical(
            eauto_imd_data=d["eauto_imds"],
            wallbox_imd_data=d["wb_imds"],
        )
        emob_ladung = emob_pool.ladung_kwh
        emob_pv_ladung = emob_pool.pv_kwh
        emob_netz_ladung = emob_pool.netz_kwh
        emob_extern_ladung = emob_pool.extern_kwh
        emob_extern_euro = emob_pool.extern_euro
        emob_km = d["eauto_km"]
        emob_v2h = d["eauto_v2h"]
        emob_verbrauch = d["eauto_verbrauch"]
        emob_pv_anteil = (emob_pv_ladung / emob_ladung * 100) if emob_ladung > 0 else None
        # Ø Verbrauch pro Monat via zentralem Helper (gemessen > Ladungs-Näherung).
        eff_m = eauto_effizienz_100km(emob_verbrauch, emob_ladung, emob_km)
        agg_emob_verbrauch += emob_verbrauch
        agg_emob_ladung += emob_ladung
        agg_emob_km += emob_km

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
            # §51 EEG: Einspeisung in Negativpreis-Stunden ist unvergütet.
            # Ohne Tages-Aggregat (m_neg=None) greift alte Berechnung.
            m_neg = await get_neg_preis_einspeisung_monat(db, anlage_id, jahr, monat)
            m_erloes_calc = einspeise_erloes_euro(
                einspeisung_kwh=md.einspeisung_kwh or 0,
                neg_preis_kwh=m_neg,
                verguetung_ct_kwh=m_einspeis_cent,
            )
            m_einspeise_erloes = m_erloes_calc.erloes_euro
        else:
            m_netzbezug_kosten = 0.0
            m_einspeise_erloes = 0.0

        # WP-Ersparnis pro Monat (Drift-Audit A1, Issue #178).
        # Aggregat über alle WPs, Parameter aus erster aktiver WP als Referenz.
        m_wp_ersparnis = 0.0
        if d["wp_waerme"] > 0:
            wp_invs_in_monat = [
                i for i in investitionen
                if i.typ == "waermepumpe" and i.ist_aktiv_im_monat(jahr, monat)
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
            emob_km=round(emob_km, 0),
            emob_ladung_kwh=round(emob_ladung, 1),
            emob_pv_anteil_prozent=round(emob_pv_anteil, 1) if emob_pv_anteil else None,
            emob_ladung_pv_kwh=round(emob_pv_ladung, 1),
            emob_ladung_netz_kwh=round(emob_netz_ladung, 1),
            emob_ladung_extern_kwh=round(emob_extern_ladung, 1),
            emob_ladung_extern_euro=round(emob_extern_euro, 2),
            emob_v2h_kwh=round(emob_v2h, 1),
            emob_verbrauch_kwh=round(emob_verbrauch, 1),
            emob_verbrauch_100km=round(eff_m.wert, 1) if eff_m.wert is not None else None,
            emob_verbrauch_quelle=eff_m.quelle,
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

    # Aggregat-Effizienz via Helper über die Summen (gemessen > Ladungs-Näherung).
    eff_gesamt = eauto_effizienz_100km(agg_emob_verbrauch, agg_emob_ladung, agg_emob_km)

    return KomponentenZeitreiheResponse(
        anlage_id=anlage_id,
        hat_speicher=hat_speicher, hat_waermepumpe=hat_waermepumpe,
        hat_emobilitaet=hat_emobilitaet, hat_balkonkraftwerk=hat_balkonkraftwerk,
        hat_sonstiges=hat_sonstiges, hat_arbitrage=hat_arbitrage, hat_v2h=hat_v2h,
        monatswerte=monatswerte, anzahl_monate=len(monatswerte),
        emob_verbrauch_100km_gesamt=round(eff_gesamt.wert, 1) if eff_gesamt.wert is not None else None,
        emob_verbrauch_quelle_gesamt=eff_gesamt.quelle,
    )
