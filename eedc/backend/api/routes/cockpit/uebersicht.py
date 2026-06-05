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
from backend.models.pvgis_prognose import PVGISPrognose
from backend.api.routes.strompreise import lade_tarife_fuer_anlage, resolve_netzbezug_preis_cent
from backend.core.berechnungen import eauto_effizienz_100km, einspeise_erloes_euro
from backend.core.calculations import (
    CO2_FAKTOR_STROM_KG_KWH, CO2_FAKTOR_GAS_KG_KWH,
    CO2_FAKTOR_BENZIN_KG_LITER, berechne_ust_eigenverbrauch,
)
from backend.utils.sonstige_positionen import berechne_sonstige_summen
from backend.core.investition_parameter import PARAM_E_AUTO, PARAM_WAERMEPUMPE, ist_dienstlich
from backend.core.field_definitions import (
    get_emob_pv_netz_kwh,
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
    # #260: km pro (jahr, monat) für die per-Monat-korrekte Benzinpreis-
    # Gewichtung (EU-OB-Monatspreis aus Monatsdaten statt statischem Param).
    eauto_km_pro_monat: dict[tuple[int, int], float] = {}
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
            if ist_dienstlich(inv):
                # #262: SoT-Helper liefert (pv, netz) inkl. Fallback für
                # evcc-Imports ohne expliziten `ladung_netz_kwh`-Key.
                pv_kwh, netz_kwh = get_emob_pv_netz_kwh(data)
                dienstlich_ladekosten_euro += (
                    netz_kwh * wallbox_preis_cent +
                    pv_kwh * einspeise_verguetung_cent
                ) / 100
            elif inv.typ == "e-auto":
                eauto_imd_data.append(data)
                km_monat = data.get("km_gefahren", 0) or 0
                eauto_km += km_monat
                eauto_verbrauch += data.get("verbrauch_kwh", 0) or 0
                if km_monat:
                    eauto_km_pro_monat[(imd.jahr, imd.monat)] = (
                        eauto_km_pro_monat.get((imd.jahr, imd.monat), 0.0) + km_monat
                    )
            else:  # wallbox (nicht-dienstlich)
                wb_imd_data.append(data)

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
        for md in monatsdaten_list:
            if (md.pv_erzeugung_kwh or 0) > 0:
                covered_months.add((md.jahr, md.monat))

    monthly_weight: dict[int, float] = {}
    if covered_months and anlagenleistung_kwp > 0:
        pvgis_res = await db.execute(
            select(PVGISPrognose)
            .where(PVGISPrognose.anlage_id == anlage_id, PVGISPrognose.ist_aktiv == True)
            .order_by(PVGISPrognose.abgerufen_am.desc())
            .limit(1)
        )
        pvgis = pvgis_res.scalar_one_or_none()
        if pvgis and pvgis.monatswerte:
            for entry in pvgis.monatswerte:
                try:
                    m = int(entry.get("monat"))
                    e = float(entry.get("e_m") or 0.0)
                except (TypeError, ValueError):
                    continue
                if 1 <= m <= 12 and e > 0:
                    monthly_weight[m] = e
        if not monthly_weight:
            # Typische 52°N-Verteilung in % des Jahresertrags
            monthly_weight = {
                1: 2.5, 2: 4.5, 3: 8.0, 4: 11.5, 5: 13.0, 6: 13.5,
                7: 13.5, 8: 12.0, 9: 9.0, 10: 6.5, 11: 3.5, 12: 2.5,
            }

    # Nenner pro Monat mit der TATSÄCHLICH AKTIVEN PV-Leistung gewichten.
    # Bug-Symptom "alle Jahre = ~300 kWh/kWp": Anlagen, die über die Jahre
    # erweitert wurden, hatten den heutigen kWp-Stand × Jahresanzahl als
    # Nenner. Frühere Jahre mit kleinerer Anlage wurden so künstlich
    # niedrig gerechnet. Per-Monat-Lookup via ist_aktiv_im_monat liefert
    # die historisch korrekte Leistung pro Datenpunkt.
    def _kwp_aktiv_im_monat(jahr: int, monat: int) -> float:
        kwp = 0.0
        for inv in investitionen:
            if inv.typ not in ("pv-module", "balkonkraftwerk"):
                continue
            if not inv.ist_aktiv_im_monat(jahr, monat):
                continue
            if inv.typ == "pv-module" and inv.leistung_kwp:
                kwp += inv.leistung_kwp
            elif inv.typ == "balkonkraftwerk":
                if inv.leistung_kwp:
                    kwp += inv.leistung_kwp
                else:
                    params = inv.parameter or {}
                    bkw_anzahl = params.get("anzahl", 1) or 1
                    kwp += (params.get("leistung_wp", 0) or 0) * bkw_anzahl / 1000
        return kwp

    weight_sum_year = sum(monthly_weight.values())
    denom_kwp_jahre = 0.0  # Summe kWp·Jahres-Äquivalente
    if covered_months and weight_sum_year > 0:
        for (j, m) in covered_months:
            w = monthly_weight.get(m, 0.0) / weight_sum_year
            kwp_m = _kwp_aktiv_im_monat(j, m)
            if kwp_m <= 0:
                # Fallback wenn Investitionen ohne Anschaffungsdatum existieren
                # oder Setup nur Anlagen-Zähler nutzt.
                kwp_m = anlagenleistung_kwp
            denom_kwp_jahre += kwp_m * w

    if denom_kwp_jahre > 0 and pv_erzeugung > 0:
        spez_ertrag = pv_erzeugung / denom_kwp_jahre
    elif anlagenleistung_kwp > 0:
        spez_ertrag = pv_erzeugung / anlagenleistung_kwp if pv_erzeugung > 0 else None
    else:
        spez_ertrag = None

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

    gew_preis_sum = 0.0
    gew_kwh_sum = 0.0
    netzbezug_kosten = 0.0
    einspeise_erloes_sum = 0.0
    # §51 EEG: nicht vergüteter Erlös + zugehörige kWh, monatlich aus dem
    # Tages-Aggregat `TagesZusammenfassung.einspeisung_neg_preis_kwh`
    # gespeist. Wenn KEIN Monat Tages-Aggregate hat, bleibt es `None` und
    # signalisiert dem Frontend „keine Strompreis-Mitschrift gepflegt".
    nicht_vergueteter_erloes_sum = 0.0
    nicht_verguetete_kwh_sum = 0.0
    hat_neg_preis_daten = False

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

        m_neg = await get_neg_preis_einspeisung_monat(db, anlage_id, m.jahr, m.monat)
        if m_neg is not None:
            hat_neg_preis_daten = True
        m_erloes = einspeise_erloes_euro(
            einspeisung_kwh=m.einspeisung_kwh or 0,
            neg_preis_kwh=m_neg,
            verguetung_ct_kwh=m_einspeis_cent,
        )
        einspeise_erloes_sum += m_erloes.erloes_euro
        nicht_vergueteter_erloes_sum += m_erloes.nicht_vergueteter_erloes_euro
        nicht_verguetete_kwh_sum += m_erloes.nicht_verguetete_kwh

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
