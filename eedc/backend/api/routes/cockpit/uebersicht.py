"""
Cockpit Übersicht — Aggregierte KPI-Übersicht für eine Anlage.
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.monatsdaten import Monatsdaten
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.pvgis_prognose import PVGISPrognose
from backend.api.routes.strompreise import lade_tarife_fuer_anlage, resolve_netzbezug_preis_cent
from backend.core.berechnungen import (
    FinanzMonatsZeile,
    berechne_finanz_aggregat,
    berechne_spez_ertrag_annualisiert,
    berechne_verbrauchs_kennzahlen,
    berechne_netzbezug_kosten,
    eauto_effizienz_100km,
    imd_typ_beitrag,
    monatsgewichte_aus_pvgis,
)
from backend.core.calculations import (
    CO2_FAKTOR_STROM_KG_KWH, CO2_FAKTOR_GAS_KG_KWH,
    CO2_FAKTOR_BENZIN_KG_LITER, berechne_ust_eigenverbrauch,
)
from backend.utils.sonstige_positionen import berechne_sonstige_summen
from backend.core.investition_parameter import PARAM_E_AUTO, PARAM_WAERMEPUMPE, ist_dienstlich
from backend.core.field_definitions import get_emob_pv_netz_kwh
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
    WP_WIRKUNGSGRAD_GAS_DEFAULT,
)
from backend.services.einspeise_erloes_service import get_neg_preis_einspeisung_monat
from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis
from backend.services.eauto_wirtschaftlichkeit import (
    berechne_eauto_ersparnis_periode,
    get_emob_heimladung_canonical,
    pick_emob_ref_parameter,
)

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
    # Ø Verbrauch (kWh/100 km) zentral via core/berechnungen/emob.py (gemessen > Ladung).
    emob_verbrauch_100km: Optional[float] = None
    emob_verbrauch_quelle: str = "keine"
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
    # §51 EEG: nicht vergüteter Erlös (Einspeisung in Negativpreis-Stunden).
    # `None` = keine Tages-Aggregate vorhanden (Anwender ohne Strompreis-
    # Sensor / Börsenpreis-Mitschrift); `0.0` = vorhanden, aber keine
    # Negativpreis-Einspeisung im Zeitraum.
    einspeise_neg_preis_kwh: Optional[float] = None
    nicht_vergueteter_erloes_euro: Optional[float] = None
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
        raise not_found("Anlage")

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
    # E-Mobilität: rohe IMD je Quelle (E-Auto / Wallbox) sammeln, danach
    # zentral via `get_emob_heimladung_canonical` zu EINER konsistenten Heimladungs-
    # Trias poolen. E-Auto- und Wallbox-IMD messen oft denselben Stromfluss
    # aus zwei Perspektiven — der Helper wählt die Quelle mit der größeren
    # Heimladung komplett (gleiche Logik wie Wallbox-Dashboard, Komponenten,
    # aktueller_monat, EAutoDashboard). km kommt nur vom E-Auto.
    eauto_imd_data: list[dict] = []
    wb_imd_data: list[dict] = []
    eauto_km = 0.0
    eauto_verbrauch = 0.0  # gemessener Fahrverbrauch (Vorrang vor Ladungs-Näherung)
    v2h_entladung = 0.0  # E-Auto → Haus, zählt wie Speicher-Entladung als Eigenverbrauch
    # #260: km pro (jahr, monat) für die per-Monat-korrekte Benzinpreis-
    # Gewichtung (EU-OB-Monatspreis aus Monatsdaten statt statischem Param).
    eauto_km_pro_monat: dict[tuple[int, int], float] = {}
    # #326: per-Monat-Aggregate für die korrekte EV-/BKW-Ersparnis. Die Ersparnis
    # muss `Σ(eigenverbrauch_m × flexpreis_m)` sein — NICHT `Σ(EV) × netzbezug-
    # gewichteter Ø-Preis`, sonst driftet das Cockpit bei Flex-Tarifen gegen die
    # Auswertungen (rilmor-mhrs: Sommer-EV fällt aus der netzbezug-Gewichtung).
    pv_erzeugung_inv_by_ym: dict[tuple[int, int], float] = {}
    speicher_ladung_by_ym: dict[tuple[int, int], float] = {}
    speicher_entladung_by_ym: dict[tuple[int, int], float] = {}
    v2h_by_ym: dict[tuple[int, int], float] = {}
    bkw_eigenverbrauch_by_ym: dict[tuple[int, int], float] = {}
    bkw_erzeugung = 0.0
    bkw_eigenverbrauch = 0.0
    sonstiges_erzeugung = 0.0
    sonstiges_verbrauch = 0.0
    sonstige_ertraege_gesamt = 0.0
    sonstige_ausgaben_gesamt = 0.0
    dienstlich_pv_netz_by_ym: dict[tuple[int, int], tuple[float, float]] = {}
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
        key = (imd.jahr, imd.monat)
        zeitraum_monate.add(key)

        # Per-Typ-Feld-Auflösung zentral ([[imd_typ_beitrag]], Block 1).
        b = imd_typ_beitrag(inv, data)

        if inv.typ == "pv-module":
            pv_erzeugung_inv += b.pv_erzeugung
            pv_erzeugung_inv_by_ym[key] = pv_erzeugung_inv_by_ym.get(key, 0) + b.pv_erzeugung

        if inv.typ == "speicher":
            speicher_ladung += b.speicher_ladung
            speicher_entladung += b.speicher_entladung
            speicher_ladung_by_ym[key] = speicher_ladung_by_ym.get(key, 0) + b.speicher_ladung
            speicher_entladung_by_ym[key] = speicher_entladung_by_ym.get(key, 0) + b.speicher_entladung

        elif inv.typ == "waermepumpe":
            wp_heizung += b.wp_heizung
            wp_warmwasser += b.wp_warmwasser
            wp_waerme += b.wp_waerme
            wp_strom += b.wp_strom

        elif inv.typ in ("e-auto", "wallbox"):
            if ist_dienstlich(inv):
                # #262: SoT-Helper liefert (pv, netz) inkl. Fallback für
                # evcc-Imports ohne expliziten `ladung_netz_kwh`-Key.
                # Kosten erst NACH dem Monatsdaten-Load berechnen — der
                # Netzbezug-Anteil läuft per-Monat über den Flexpreis
                # (gleichzeitig mit aussichten.get_finanz_prognose umgestellt).
                pv_kwh, netz_kwh = get_emob_pv_netz_kwh(data)
                d_pv, d_netz = dienstlich_pv_netz_by_ym.get(key, (0.0, 0.0))
                dienstlich_pv_netz_by_ym[key] = (d_pv + pv_kwh, d_netz + netz_kwh)
            elif inv.typ == "e-auto":
                eauto_imd_data.append(data)
                eauto_km += b.eauto_km
                eauto_verbrauch += b.eauto_verbrauch
                v2h_entladung += b.eauto_v2h
                v2h_by_ym[key] = v2h_by_ym.get(key, 0) + b.eauto_v2h
                if b.eauto_km:
                    eauto_km_pro_monat[(imd.jahr, imd.monat)] = (
                        eauto_km_pro_monat.get((imd.jahr, imd.monat), 0.0) + b.eauto_km
                    )
            else:  # wallbox (nicht-dienstlich)
                wb_imd_data.append(data)

        elif inv.typ == "balkonkraftwerk":
            bkw_erzeugung += b.bkw_erzeugung
            bkw_eigenverbrauch += b.bkw_eigenverbrauch
            pv_erzeugung_inv += b.bkw_erzeugung
            pv_erzeugung_inv_by_ym[key] = pv_erzeugung_inv_by_ym.get(key, 0) + b.bkw_erzeugung
            bkw_eigenverbrauch_by_ym[key] = bkw_eigenverbrauch_by_ym.get(key, 0) + b.bkw_eigenverbrauch

        elif inv.typ == "sonstiges":
            # D4 (Block 1): zentraler Resolver ist kategorie-bewusst (wie Site
            # Komponenten) — verbraucher liefert nur Verbrauch, erzeuger nur
            # Erzeugung. Für gültige Daten (sich ausschließende Felder) identisch
            # zum bisherigen kategorie-blinden Σ; minimal-strenger im Misch-Edge.
            sonstiges_erzeugung += b.sonstiges_erzeugung
            sonstiges_verbrauch += b.sonstiges_verbrauch

        summen = berechne_sonstige_summen(data)
        sonstige_ertraege_gesamt += summen["ertraege_euro"]
        sonstige_ausgaben_gesamt += summen["ausgaben_euro"]

    # E-Mobilitäts-Pool: EINE Quelle liefert die konsistente Heimladungs-
    # Trias (pv + netz == ladung). Früher feldweises max() über pv/netz —
    # das konnte pv aus der einen, netz aus der anderen Quelle nehmen und
    # PV-Anteil > 100 % erzeugen (#262 junky84). Externe Lade-Kosten (#260)
    # kommen paarweise aus der Quelle mit den höheren Extern-Kosten.
    emob_pool = get_emob_heimladung_canonical(
        eauto_imd_data=eauto_imd_data,
        wallbox_imd_data=wb_imd_data,
    )
    emob_ladung = emob_pool.ladung_kwh
    emob_pv_ladung = emob_pool.pv_kwh
    emob_netz_ladung = emob_pool.netz_kwh
    emob_km = eauto_km
    # Ø Verbrauch (kWh/100 km) via zentralem Helper — gemessener Fahrverbrauch hat
    # Vorrang, sonst Ladungs-Näherung; konsistent zu E-Auto-Dashboard + Komponenten.
    emob_eff = eauto_effizienz_100km(eauto_verbrauch, emob_ladung, emob_km)
    emob_extern_euro_total = emob_pool.extern_euro

    # Monatsdaten NUR für Anlagen-Energiebilanz
    md_query = select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    if jahr:
        md_query = md_query.where(Monatsdaten.jahr == jahr)
    md_query = md_query.order_by(Monatsdaten.jahr, Monatsdaten.monat)

    md_result = await db.execute(md_query)
    monatsdaten_list = md_result.scalars().all()
    monatsdaten_by_ym = {(m.jahr, m.monat): m for m in monatsdaten_list}

    # Dienstliche Ladekosten: Netzbezug-Anteil per-Monat über den Flexpreis
    # (`resolve_netzbezug_preis_cent`), Fallback Wallbox-Tarif; entgangene
    # Einspeisung bleibt statisch (Vertragswert). Gleichzeitig mit
    # aussichten.get_finanz_prognose umgestellt ([[feedback_aggregations_drift]]).
    dienstlich_ladekosten_euro = 0.0
    for d_key, (d_pv, d_netz) in dienstlich_pv_netz_by_ym.items():
        d_md = monatsdaten_by_ym.get(d_key)
        d_preis = resolve_netzbezug_preis_cent(d_md, wallbox_preis_cent) if d_md else wallbox_preis_cent
        dienstlich_ladekosten_euro += (
            d_netz * d_preis + d_pv * einspeise_verguetung_cent
        ) / 100
    sonstige_ausgaben_gesamt += dienstlich_ladekosten_euro

    # Anschaffungsdatum-Grenze: Energiebilanz + Erträge nur über Monate, in denen
    # mindestens ein PV-Erzeuger (PV-Module ∪ Balkonkraftwerke) aktiv war.
    # Konsequente Anwendung des einzigen Manipulationshebels „Anschaffungsdatum"
    # (Gernot 2026-06-07, [[feedback_anschaffungsdatum_grenze]]) — symmetrisch zum
    # kumulierten Amortisations-Pfad in aussichten.get_finanz_prognose und zur
    # bestehenden covered_months-Logik unten ([[feedback_aggregator_symmetrie]]).
    # WP/E-Auto/BKW/Sonstige filtern ihre Monate bereits über ist_aktiv_im_monat
    # (#236). ist_aktiv_im_monat deckt alle drei Zustände ab: stillgelegt → bis
    # Stilllegungsdatum aktiv (Daten fließen ein), aktiv=False → komplett
    # ausgeblendet. Ohne registrierte PV-Quelle oder ohne gesetztes
    # Anschaffungsdatum bleibt das Verhalten unverändert (Filter greift nicht).
    _pv_erzeuger = [i for i in investitionen if i.typ in ("pv-module", "balkonkraftwerk")]

    def _pv_aktiv_im_monat(jahr: int, monat: int) -> bool:
        if not _pv_erzeuger:
            return True
        return any(p.ist_aktiv_im_monat(jahr, monat) for p in _pv_erzeuger)

    md_pv = [m for m in monatsdaten_list if _pv_aktiv_im_monat(m.jahr, m.monat)]

    einspeisung = sum(m.einspeisung_kwh or 0 for m in md_pv)
    netzbezug = sum(m.netzbezug_kwh or 0 for m in md_pv)

    pv_erzeugung_md = sum(m.pv_erzeugung_kwh or 0 for m in md_pv)
    pv_erzeugung = pv_erzeugung_inv if pv_erzeugung_inv > 0 else pv_erzeugung_md

    # Kanonische Verbrauchs-Kennzahlen über den SoT-Helper (ADR-001) statt der
    # früher hier duplizierten Inline-Formel — inkl. V2H (E-Auto → Haus) als
    # Eigenverbrauch, einheitlich mit HA-Export/Aussichten/Jahresbericht.
    _kz = berechne_verbrauchs_kennzahlen(
        pv_erzeugung_kwh=pv_erzeugung,
        einspeisung_kwh=einspeisung,
        netzbezug_kwh=netzbezug,
        speicher_ladung_kwh=speicher_ladung,
        speicher_entladung_kwh=speicher_entladung,
        v2h_entladung_kwh=v2h_entladung,
    )
    direktverbrauch = _kz.direktverbrauch_kwh
    eigenverbrauch = _kz.eigenverbrauch_kwh
    gesamtverbrauch = _kz.gesamtverbrauch_kwh
    autarkie = _kz.autarkie_prozent
    ev_quote = _kz.eigenverbrauchsquote_prozent
    dv_quote = _kz.direktverbrauchsquote_prozent

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

    # Spezifischer Ertrag periodengenau & jahresverlauf-gewichtet (#YTD-spez-ertrag):
    # Roh-Division pv_erzeugung / kWp ergibt im laufenden Jahr einen viel zu
    # niedrigen Wert, weil der Nenner für 12 Monate ausgelegt ist. Naive
    # Proration (Monate/12) ignoriert den Jahresverlauf — Jan–Mai sind ~30%
    # des Jahresertrags, nicht 42%. Daher Periodenanteil über die
    # PVGIS-Monatsverteilung gewichten; Fallback auf typische 52°N-Verteilung
    # bzw. Gleichverteilung wenn keine PVGIS-Prognose vorliegt.
    #
    # WICHTIG (Folge-Bug "alle Jahre"): covered_months darf NUR Monate
    # enthalten, in denen tatsächlich eine PV-/BKW-Investition aktiv war.
    # Sonst rutschen WP-/Speicher-/Zähler-Monate aus der Zeit vor PV-Inbetrieb-
    # nahme rein, periode_anteil wird zu groß und spez_ertrag zu klein
    # (Symptom: ~300 kWh/kWp bei "alle Jahre").
    covered_months: set[tuple[int, int]] = set()
    for imd in all_imd:
        inv = inv_by_id.get(imd.investition_id)
        if not inv or inv.typ not in ("pv-module", "balkonkraftwerk"):
            continue
        if not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
            continue
        covered_months.add((imd.jahr, imd.monat))
    # Fallback für Setups ohne PV-IMDs (nur Anlagen-Zähler):
    # Monate mit pv_erzeugung > 0 aus Monatsdaten heranziehen.
    if not covered_months:
        for md in md_pv:
            if (md.pv_erzeugung_kwh or 0) > 0:
                covered_months.add((md.jahr, md.monat))

    # Annualisierung über den SoT-Helper (per-Monat-aktives kWp + saisonale
    # Gewichtung) — deckungsgleich mit dem HA-Export-Sensor
    # ([[feedback_aggregator_symmetrie]], Rainer-PN 2026-06-11).
    monatsgewichte: Optional[dict[int, float]] = None
    if covered_months and anlagenleistung_kwp > 0:
        pvgis_res = await db.execute(
            select(PVGISPrognose)
            .where(PVGISPrognose.anlage_id == anlage_id, PVGISPrognose.ist_aktiv == True)
            .order_by(PVGISPrognose.abgerufen_am.desc())
            .limit(1)
        )
        pvgis = pvgis_res.scalar_one_or_none()
        monatsgewichte = monatsgewichte_aus_pvgis(
            pvgis.monatswerte if pvgis else None
        ) or None

    spez_ertrag = berechne_spez_ertrag_annualisiert(
        pv_erzeugung_kwh=pv_erzeugung,
        covered_months=covered_months if anlagenleistung_kwp > 0 else set(),
        investitionen=investitionen,
        fallback_kwp=anlagenleistung_kwp,
        monatsgewichte=monatsgewichte,
    )

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
        and not ist_dienstlich(i)
    ]
    hat_emobilitaet = len(emob_invs) > 0
    emob_pv_anteil = (emob_pv_ladung / emob_ladung * 100) if emob_ladung > 0 else None
    # #260: per-Monat-korrekter Benzinpreis (EU-OB-Monatspreis aus Monatsdaten),
    # km-gewichtet — derselbe Pfad wie E-Auto-Dashboard + Monatsberichte. Vorher
    # rief die Übersicht den Skalar-Helper mit dem statischen Inv-Parameter-Preis
    # (1,80 €-Default) auf → Drift gegen die Monatsberichte (NongJoWo).
    benzinpreis_lookup = {
        (m.jahr, m.monat): m.kraftstoffpreis_euro for m in monatsdaten_list
    }
    emob_result = berechne_eauto_ersparnis_periode(
        km_pro_monat=[(j, mo, km) for (j, mo), km in eauto_km_pro_monat.items()],
        ladung_netz_kwh_gesamt=emob_netz_ladung,
        ladung_extern_euro_gesamt=emob_extern_euro_total,
        wallbox_strompreis_cent=wallbox_preis_cent,
        eauto_parameter=pick_emob_ref_parameter(emob_invs),
        monats_benzinpreis_lookup=benzinpreis_lookup,
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

    netzbezug_kosten = 0.0
    # PV-Quelle pro Monat wie beim Aggregat wählen (IMD bevorzugt, sonst Zähler).
    use_inv_pv = pv_erzeugung_inv > 0
    # #326: Finanz-Aggregation (Einspeise-Erlös §51 + EV-/BKW-Ersparnis) über den
    # SoT-Helper `berechne_finanz_aggregat` — per-Monat mit dem Monats-Flexpreis
    # (Σ EV_m × p_m), deckungsgleich mit Jahresbericht-PDF, HA-Export und
    # Auswertungen→Finanzen. Kein netzbezug-gewichteter Ø-Preis mehr.
    finanz_zeilen: list[FinanzMonatsZeile] = []

    # PV-Window-gefiltert (md_pv): Einspeise-Erlös, Netzbezugskosten und die
    # per-Monat-EV-/BKW-Ersparnis zählen nur Monate mit aktiver PV — wie die
    # Energiebilanz oben und der Amortisations-Pfad in aussichten.
    for m in md_pv:
        m_tarife = await _tarif_fuer_monat(m)
        m_allgemein = m_tarife.get("allgemein")
        m_preis_cent = m_allgemein.netzbezug_arbeitspreis_cent_kwh if m_allgemein else NETZBEZUG_DEFAULT_CENT
        m_grundpreis = (m_allgemein.grundpreis_euro_monat or 0) if m_allgemein else 0
        m_einspeis_cent = m_allgemein.einspeiseverguetung_cent_kwh if m_allgemein else EINSPEISEVERGUETUNG_DEFAULT_CENT
        eff_preis = resolve_netzbezug_preis_cent(m, m_preis_cent)
        kwh = m.netzbezug_kwh or 0
        netzbezug_kosten += berechne_netzbezug_kosten(kwh, eff_preis, m_grundpreis)

        m_key = (m.jahr, m.monat)
        m_pv = pv_erzeugung_inv_by_ym.get(m_key, 0.0) if use_inv_pv else (m.pv_erzeugung_kwh or 0)
        m_neg = await get_neg_preis_einspeisung_monat(db, anlage_id, m.jahr, m.monat)
        finanz_zeilen.append(FinanzMonatsZeile(
            einspeisung_kwh=m.einspeisung_kwh or 0,
            netzbezug_kwh=kwh,
            pv_erzeugung_kwh=m_pv,
            speicher_ladung_kwh=speicher_ladung_by_ym.get(m_key, 0.0),
            speicher_entladung_kwh=speicher_entladung_by_ym.get(m_key, 0.0),
            v2h_entladung_kwh=v2h_by_ym.get(m_key, 0.0),
            bkw_eigenverbrauch_kwh=bkw_eigenverbrauch_by_ym.get(m_key, 0.0),
            netzbezug_preis_cent=eff_preis,
            einspeiseverguetung_cent=m_einspeis_cent,
            neg_preis_kwh=m_neg,
        ))

    # §51 EEG: nicht vergüteter Erlös + zugehörige kWh kommen aus dem Aggregat;
    # `hat_neg_preis_daten` bleibt False, wenn KEIN Monat Tages-Aggregate hat,
    # und signalisiert dem Frontend „keine Strompreis-Mitschrift gepflegt".
    _finanz = berechne_finanz_aggregat(finanz_zeilen)
    einspeise_erloes = _finanz.einspeise_erloes_euro
    # #326: per-Monat summiert (Σ EV_m × flexpreis_m) statt Gesamt-EV × Ø-Preis —
    # deckungsgleich mit Auswertungen→Finanzen.
    ev_ersparnis = _finanz.ev_ersparnis_euro
    nicht_vergueteter_erloes_sum = _finanz.nicht_vergueteter_erloes_euro
    nicht_verguetete_kwh_sum = _finanz.nicht_verguetete_kwh
    hat_neg_preis_daten = _finanz.hat_neg_preis_daten
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

    # #326: BKW-Ersparnis ebenfalls per-Monat (Σ BKW-EV_m × flexpreis_m).
    bkw_ersparnis = _finanz.bkw_ersparnis_euro
    sonstige_netto = sonstige_ertraege_gesamt - sonstige_ausgaben_gesamt
    # #326 (rilmor-mhrs): Die manuell gepflegten „Sonstige Erträge & Ausgaben"
    # gehören in den ANGEZEIGTEN Netto-Ertrag — exakt wie Auswertungen→Finanzen
    # (Einspeiseerlös + EV-Ersparnis + Sonstige-Erträge − Sonstige-Ausgaben).
    # Bisher floss sonstige_netto nur in kumulative_ersparnis/ROI ein, nicht in
    # die Netto-Ertrag-Kachel → das Cockpit zeigte eine andere Summe als die
    # Auswertungen. Aufschlagen NACH dem USt-Abzug (USt betrifft nur den
    # Eigenverbrauch, nicht die Finanzpositionen).
    netto_ertrag += sonstige_netto

    # CO2-Bilanz
    co2_pv = eigenverbrauch * CO2_FAKTOR_STROM_KG_KWH
    co2_wp = (wp_waerme / WP_WIRKUNGSGRAD_GAS_DEFAULT * CO2_FAKTOR_GAS_KG_KWH) - (wp_strom * CO2_FAKTOR_STROM_KG_KWH) if wp_waerme > 0 else 0
    co2_emob = (benzin_verbrauch * CO2_FAKTOR_BENZIN_KG_LITER) - (emob_netz_ladung * CO2_FAKTOR_STROM_KG_KWH) if emob_km > 0 else 0
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
    # sonstige_netto steckt bereits in netto_ertrag (#326) — hier NICHT erneut
    # addieren, sonst Doppelzählung im ROI.
    kumulative_ersparnis = netto_ertrag + wp_ersparnis + emob_ersparnis + bkw_ersparnis - betriebskosten_zeitraum
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
        emob_verbrauch_100km=round(emob_eff.wert, 1) if emob_eff.wert is not None else None,
        emob_verbrauch_quelle=emob_eff.quelle,
        hat_emobilitaet=hat_emobilitaet,
        bkw_erzeugung_kwh=round(bkw_erzeugung, 1),
        bkw_eigenverbrauch_kwh=round(bkw_eigenverbrauch, 1),
        hat_balkonkraftwerk=hat_balkonkraftwerk,
        sonstiges_erzeugung_kwh=round(sonstiges_erzeugung, 1),
        sonstiges_verbrauch_kwh=round(sonstiges_verbrauch, 1),
        hat_sonstiges=hat_sonstiges,
        einspeise_erloes_euro=round(einspeise_erloes, 2),
        einspeise_neg_preis_kwh=(
            round(nicht_verguetete_kwh_sum, 1) if hat_neg_preis_daten else None
        ),
        nicht_vergueteter_erloes_euro=(
            round(nicht_vergueteter_erloes_sum, 2) if hat_neg_preis_daten else None
        ),
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
