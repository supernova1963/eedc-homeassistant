"""
Investitionen-Dashboards — API Routes.

Pro-Investitionstyp-Dashboards (E-Auto, Wärmepumpe, Speicher, Wallbox,
Balkonkraftwerk, Sonstiges) plus die Investition-Monatsdaten-Abfrage.
2026-05-20 aus investitionen.py ausgelagert; der gemeinsame Router wird
in investitionen/__init__.py aggregiert.
"""

from typing import Optional, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from dataclasses import asdict
from datetime import date
import logging

from backend.api.deps import get_db
from backend.models.investition import Investition, InvestitionTyp, InvestitionMonatsdaten
from backend.utils.investition_filter import aktiv_im_monat
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_netzbezug_preis_cent,
    resolve_strompreis_for_komponente,
)
from backend.utils.sonstige_positionen import berechne_sonstige_summen
from backend.core.investition_parameter import (
    PARAM_SPEICHER,
    PARAM_SPEICHER_DEFAULTS,
    PARAM_WALLBOX,
    PARAM_WALLBOX_DEFAULTS,
)
from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis
from backend.services.eauto_wirtschaftlichkeit import (
    aggregiere_emob_ladung,
    attribute_emob_pool_by_km,
    berechne_eauto_ersparnis,
    berechne_eauto_ersparnis_periode,
    compute_emob_pool_attribution,
)
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    EXTERNE_LADUNG_DEFAULT_EURO_KWH,
)
from backend.services.speicher_wirtschaftlichkeit import (
    aggregiere_speicher_ist,
    berechne_effektiver_ladepreis,
    berechne_ist_wirkungsgrad,
    berechne_v2h_ersparnis,
    ist_eta_degradation_alarm,
)
from backend.core.calculations import (
    CO2_FAKTOR_BENZIN_KG_LITER,
    CO2_FAKTOR_GAS_KG_KWH,
    CO2_FAKTOR_STROM_KG_KWH,
)
from backend.core.field_definitions import get_emob_pv_netz_kwh
from backend.core.berechnungen import (
    gleitende_effizienz,
    pruefe_speicher_durchsatz_konsistenz,
    speicher_effizienz_prozent,
)
from backend.api.routes.investitionen.crud import InvestitionResponse

logger = logging.getLogger(__name__)

router = APIRouter()


class InvestitionMonatsdatenResponse(BaseModel):
    """Monatsdaten für eine Investition."""
    id: int
    investition_id: int
    jahr: int
    monat: int
    verbrauch_daten: dict[str, Any]
    einsparung_monat_euro: Optional[float]
    co2_einsparung_kg: Optional[float]

    class Config:
        from_attributes = True


class EAutoDashboardResponse(BaseModel):
    """E-Auto Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


class WaermepumpeDashboardResponse(BaseModel):
    """Wärmepumpe Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


class SpeicherDashboardResponse(BaseModel):
    """Speicher Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]
    # Gleitende 12-Monats-Effizienz (carry-over-immun) — ersetzt die naive
    # Pro-Monats-Effizienz, die durch den SoC-Übertrag >100 % zappeln konnte.
    effizienz_verlauf: list[dict[str, Any]] = []


class WallboxDashboardResponse(BaseModel):
    """Wallbox Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


class BalkonkraftwerkDashboardResponse(BaseModel):
    """Balkonkraftwerk Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


class SonstigesDashboardResponse(BaseModel):
    """Sonstiges Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


@router.get("/dashboard/e-auto/{anlage_id}", response_model=list[EAutoDashboardResponse])
async def get_eauto_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(None, description="Override: Strompreis (auto aus Wallbox-Tarif wenn leer)"),
    db: AsyncSession = Depends(get_db),
):
    """
    E-Auto Dashboard für eine Anlage.

    Zeigt alle E-Autos mit Monatsdaten, km-Statistik, PV-Anteil, Ersparnis.
    """
    # Wallbox-Tarif laden (E-Auto lädt über Wallbox)
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    wallbox_tarif = tarife.get("wallbox")
    allgemein_tarif = tarife.get("allgemein")
    strompreis_cent = strompreis_cent or resolve_strompreis_for_komponente(tarife, "wallbox")
    # Einspeisevergütung für V2H-Spread-Berechnung (Drift-Audit D)
    einspeise_verg_cent = (allgemein_tarif.einspeiseverguetung_cent_kwh
                           if allgemein_tarif and allgemein_tarif.einspeiseverguetung_cent_kwh is not None
                           else EINSPEISEVERGUETUNG_DEFAULT_CENT)

    # E-Autos laden — Issue #123: Dashboard ist historische Übersicht,
    # stillgelegte E-Autos bleiben mit ihrer Historie sichtbar.
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.E_AUTO.value)
    )
    eautos = inv_result.scalars().all()

    if not eautos:
        return []

    # Batch-Query: E-Auto-Monatsdaten + Wallbox-Monatsdaten auf einmal laden
    # (#262 junky84: evcc-Portal-Import schreibt Ladedaten in die Wallbox-
    # Investition; ohne diesen Pool sähe das E-Auto-Dashboard nichts).
    eauto_ids = [e.id for e in eautos]
    wallbox_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.WALLBOX.value)
    )
    wallboxen = wallbox_result.scalars().all()
    wallbox_ids = [w.id for w in wallboxen]

    all_md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(eauto_ids + wallbox_ids))
        .order_by(InvestitionMonatsdaten.investition_id, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    all_monatsdaten = all_md_result.scalars().all()
    md_by_inv: dict[int, list] = {}
    for md in all_monatsdaten:
        md_by_inv.setdefault(md.investition_id, []).append(md)

    # Wallbox-Heimladung als Wahrheit, wenn größer als Σ E-Auto-Heimladung
    # (typisches evcc-Portal-Import-Setup). Km-Anteile pro E-Auto unten.
    pool_attr = compute_emob_pool_attribution(
        eauto_imd_data=[
            (md.verbrauch_daten or {})
            for e in eautos for md in md_by_inv.get(e.id, [])
            if e.ist_aktiv_im_monat(md.jahr, md.monat)
        ],
        wallbox_imd_data=[
            (md.verbrauch_daten or {})
            for w in wallboxen for md in md_by_inv.get(w.id, [])
            if w.ist_aktiv_im_monat(md.jahr, md.monat)
        ],
    )

    # #260 (NongJoWo): Benzinpreis pro Monat aus Anlage.monatsdaten (EU
    # Weekly Oil Bulletin, seit v3.17.0) — vorher zog dieses Dashboard nur
    # einen statischen Default 1.65 €/L und driftete damit gegen die
    # Cockpit-Übersicht, die seit v3.17.0 monatlich rechnet.
    anlage_md_result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    benzinpreis_lookup: dict[tuple[int, int], Optional[float]] = {
        (md.jahr, md.monat): md.kraftstoffpreis_euro
        for md in anlage_md_result.scalars().all()
    }

    dashboards = []
    for eauto in eautos:
        # Issue #153 / #155 / #236: SoT-Filter inkl. stilllegungsdatum
        monatsdaten = [
            md for md in md_by_inv.get(eauto.id, [])
            if eauto.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        # Zusammenfassung berechnen
        gesamt_km = 0
        gesamt_verbrauch = 0
        gesamt_pv_ladung = 0
        gesamt_netz_ladung = 0
        gesamt_extern_ladung = 0
        gesamt_extern_kosten = 0
        gesamt_v2h = 0
        # #260: km pro Monat sammeln, damit berechne_eauto_ersparnis_periode
        # mit dem jeweils gültigen Monats-Benzinpreis rechnen kann.
        km_pro_monat: list[tuple[int, int, float]] = []

        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            km_this = d.get('km_gefahren', 0) or 0
            gesamt_km += km_this
            if km_this > 0:
                km_pro_monat.append((md.jahr, md.monat, km_this))
            gesamt_verbrauch += d.get('verbrauch_kwh', 0)
            # #262: PV/Netz via SoT-Helper (evcc-Import schreibt nur Total + PV).
            pv, netz = get_emob_pv_netz_kwh(d)
            gesamt_pv_ladung += pv
            gesamt_netz_ladung += netz
            gesamt_extern_ladung += d.get('ladung_extern_kwh', 0)
            gesamt_extern_kosten += d.get('ladung_extern_euro', 0)
            gesamt_v2h += d.get('v2h_entladung_kwh', 0)

        # Wallbox-Pool-Fallback (#262 junky84): wenn die Wallbox-Investition
        # mehr Heim-Ladung enthält als alle E-Autos zusammen, sind die Daten
        # offenbar via evcc-Portal-Import in die Wallbox geflossen. Anteilig
        # nach gefahrenen km auf die E-Autos verteilen.
        share = attribute_emob_pool_by_km(pool_attr, gesamt_km)
        if pool_attr.use_wb_pool and share.netz_kwh + share.pv_kwh > 0:
            gesamt_pv_ladung = share.pv_kwh
            gesamt_netz_ladung = share.netz_kwh
            gesamt_extern_ladung = share.extern_kwh
            gesamt_extern_kosten = share.extern_euro

        # Heim-Ladung (Wallbox) = PV + Netz
        gesamt_heim_ladung = gesamt_pv_ladung + gesamt_netz_ladung
        # Gesamt-Ladung = Heim + Extern
        gesamt_ladung = gesamt_heim_ladung + gesamt_extern_ladung
        # PV-Anteil nur auf Heim-Ladung bezogen
        pv_anteil_heim = (gesamt_pv_ladung / gesamt_heim_ladung * 100) if gesamt_heim_ladung > 0 else 0
        # PV-Anteil auf Gesamt-Ladung
        pv_anteil_gesamt = (gesamt_pv_ladung / gesamt_ladung * 100) if gesamt_ladung > 0 else 0

        # E-Auto-Ersparnis über die Periode mit per-Monat-Benzinpreis
        # (#260, NongJoWo): Σ km_monat × verbrauch × preis_monat aus dem
        # benzinpreis_lookup, statt einmaliger Multiplikation mit Default.
        params = eauto.parameter or {}
        eauto_result = berechne_eauto_ersparnis_periode(
            km_pro_monat=km_pro_monat,
            ladung_netz_kwh_gesamt=gesamt_netz_ladung,
            ladung_extern_euro_gesamt=gesamt_extern_kosten,
            wallbox_strompreis_cent=strompreis_cent,
            eauto_parameter=params,
            monats_benzinpreis_lookup=benzinpreis_lookup,
        )
        benzin_kosten = eauto_result.benzin_kosten_euro
        heim_netz_kosten = gesamt_netz_ladung * strompreis_cent / 100
        strom_kosten_gesamt = eauto_result.strom_kosten_euro
        ersparnis_vs_benzin = eauto_result.ersparnis_euro
        benzin_verbrauch_100km = eauto_result.verwendeter_verbrauch_l_100km

        # V2H Ersparnis (Rückspeisung ins Haus, Drift-Audit D: Spread-Modell).
        # User kann `v2h_entlade_preis_cent` als expliziten Override pflegen;
        # ohne Override: Spread (Bezug − Einspeise) — die V2H-Energie hätte
        # alternativ eingespeist werden können.
        v2h_preis_override = params.get('v2h_entlade_preis_cent')
        if v2h_preis_override is not None:
            v2h_ersparnis = gesamt_v2h * v2h_preis_override / 100
        else:
            v2h_ersparnis = berechne_v2h_ersparnis(
                v2h_entladung_kwh=gesamt_v2h,
                bezug_preis_cent=strompreis_cent,
                einspeise_verg_cent=einspeise_verg_cent,
            ).ersparnis_euro

        # Wallbox-Ersparnis: Was hätte externe Ladung gekostet?
        # Durchschnittlicher externer Preis (wenn vorhanden) oder kanon. Default.
        extern_preis_kwh = (
            gesamt_extern_kosten / gesamt_extern_ladung
            if gesamt_extern_ladung > 0
            else EXTERNE_LADUNG_DEFAULT_EURO_KWH
        )
        heim_ladung_als_extern = gesamt_heim_ladung * extern_preis_kwh
        heim_kosten_tatsaechlich = heim_netz_kosten  # PV ist kostenlos
        wallbox_ersparnis = heim_ladung_als_extern - heim_kosten_tatsaechlich

        # CO2 Ersparnis: Benzin vs. Strommix
        benzin_co2 = (gesamt_km / 100) * benzin_verbrauch_100km * CO2_FAKTOR_BENZIN_KG_LITER
        strom_co2 = gesamt_verbrauch * CO2_FAKTOR_STROM_KG_KWH
        co2_ersparnis = benzin_co2 - strom_co2

        zusammenfassung = {
            'gesamt_km': round(gesamt_km, 0),
            'gesamt_verbrauch_kwh': round(gesamt_verbrauch, 1),
            'durchschnitt_verbrauch_kwh_100km': round(gesamt_verbrauch / gesamt_km * 100, 1) if gesamt_km > 0 else 0,
            # Ladung aufgeschlüsselt
            'gesamt_ladung_kwh': round(gesamt_ladung, 1),
            'ladung_heim_kwh': round(gesamt_heim_ladung, 1),
            'ladung_pv_kwh': round(gesamt_pv_ladung, 1),
            'ladung_netz_kwh': round(gesamt_netz_ladung, 1),
            'ladung_extern_kwh': round(gesamt_extern_ladung, 1),
            'ladung_extern_euro': round(gesamt_extern_kosten, 2),
            # PV-Anteile
            'pv_anteil_heim_prozent': round(pv_anteil_heim, 1),
            'pv_anteil_gesamt_prozent': round(pv_anteil_gesamt, 1),
            # V2H
            'v2h_entladung_kwh': round(gesamt_v2h, 1),
            'v2h_ersparnis_euro': round(v2h_ersparnis, 2),
            # Kosten-Vergleich
            'benzin_kosten_alternativ_euro': round(benzin_kosten, 2),
            'strom_kosten_heim_euro': round(heim_netz_kosten, 2),
            'strom_kosten_extern_euro': round(gesamt_extern_kosten, 2),
            'strom_kosten_gesamt_euro': round(strom_kosten_gesamt, 2),
            'ersparnis_vs_benzin_euro': round(ersparnis_vs_benzin, 2),
            # Wallbox-Ersparnis (durch Heimladen statt extern)
            'wallbox_ersparnis_euro': round(wallbox_ersparnis, 2),
            # Gesamt-Ersparnis
            'gesamt_ersparnis_euro': round(ersparnis_vs_benzin + v2h_ersparnis, 2),
            'co2_ersparnis_kg': round(co2_ersparnis, 1),
            'anzahl_monate': len(monatsdaten),
        }

        dashboards.append(EAutoDashboardResponse(
            investition=eauto,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


@router.get("/dashboard/waermepumpe/{anlage_id}", response_model=list[WaermepumpeDashboardResponse])
async def get_waermepumpe_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(None, description="Override: Strompreis (auto aus WP-Tarif wenn leer)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Wärmepumpe Dashboard für eine Anlage.

    Zeigt alle Wärmepumpen mit COP, Heizkosten, Ersparnis vs. alte Heizung.
    """
    # WP-Tarif laden
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    wp_tarif = tarife.get("waermepumpe")
    allgemein_tarif = tarife.get("allgemein")
    strompreis_cent = strompreis_cent or resolve_strompreis_for_komponente(tarife, "waermepumpe")

    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.WAERMEPUMPE.value)
    )
    waermepumpen = inv_result.scalars().all()

    if not waermepumpen:
        return []

    # Anlage einmal laden — get_counter_lifetime braucht sensor_mapping.
    anlage_result = await db.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = anlage_result.scalar_one_or_none()
    if anlage is None:
        return []

    from backend.services.sensor_snapshot_service import get_counter_lifetime

    # Batch-Query: Alle Monatsdaten für alle Wärmepumpen auf einmal laden
    wp_ids = [w.id for w in waermepumpen]
    all_md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(wp_ids))
        .order_by(InvestitionMonatsdaten.investition_id, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    all_monatsdaten = all_md_result.scalars().all()
    md_by_inv: dict[int, list] = {}
    for md in all_monatsdaten:
        md_by_inv.setdefault(md.investition_id, []).append(md)

    # Counter-Tagesinkremente (Starts + Betriebsstunden, Issue #169 / #238):
    # Quelle TagesZusammenfassung.komponenten_starts mit
    # {"wp_starts_anzahl": {"<inv_id>": <int>},
    #  "wp_betriebsstunden": {"<inv_id>": <float>}}.
    # Wird hier für Max/Tag-KPI + Σ-Betriebsstunden-Aggregat gebraucht.
    # Σ Lebensdauer-Starts kommt direkt aus dem Hersteller-Sensor
    # (`get_counter_lifetime`), Σ-Betriebsstunden ebenfalls direkt aus dem
    # Sensor — beide sind kumulative Counter, der Sensor ist die Wahrheit.
    tz_result = await db.execute(
        select(TagesZusammenfassung.komponenten_starts)
        .where(TagesZusammenfassung.anlage_id == anlage_id)
        .where(TagesZusammenfassung.komponenten_starts.is_not(None))
    )
    starts_by_inv: dict[int, list[int]] = {wid: [] for wid in wp_ids}
    stunden_by_inv: dict[int, list[float]] = {wid: [] for wid in wp_ids}
    for (komp_starts,) in tz_result.all():
        wp_map = (komp_starts or {}).get("wp_starts_anzahl") or {}
        for inv_id_str, count in wp_map.items():
            try:
                inv_id = int(inv_id_str)
            except (TypeError, ValueError):
                continue
            if inv_id in starts_by_inv and isinstance(count, (int, float)) and count > 0:
                starts_by_inv[inv_id].append(int(count))
        stunden_map = (komp_starts or {}).get("wp_betriebsstunden") or {}
        for inv_id_str, hours in stunden_map.items():
            try:
                inv_id = int(inv_id_str)
            except (TypeError, ValueError):
                continue
            if inv_id in stunden_by_inv and isinstance(hours, (int, float)) and hours > 0:
                stunden_by_inv[inv_id].append(float(hours))

    dashboards = []
    for wp in waermepumpen:
        # Issue #153 / #236: SoT-Filter inkl. stilllegungsdatum
        monatsdaten = [
            md for md in md_by_inv.get(wp.id, [])
            if wp.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        gesamt_strom = 0
        gesamt_strom_heizen = 0
        gesamt_strom_warmwasser = 0
        gesamt_heizung = 0
        gesamt_warmwasser = 0
        hat_getrennte_strom = False

        gesamt_heizung_getrennt = 0.0  # Heizung nur für Monate mit getrennter Strommessung
        gesamt_warmwasser_getrennt = 0.0  # Warmwasser nur für Monate mit getrennter Strommessung
        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            gesamt_strom += d.get('stromverbrauch_kwh', 0)
            gesamt_heizung += d.get('heizenergie_kwh', 0)
            gesamt_warmwasser += d.get('warmwasser_kwh', 0)
            if 'strom_heizen_kwh' in d:
                hat_getrennte_strom = True
                gesamt_strom_heizen += d.get('strom_heizen_kwh', 0)
                gesamt_strom_warmwasser += d.get('strom_warmwasser_kwh', 0)
                gesamt_heizung_getrennt += d.get('heizenergie_kwh', 0)
                gesamt_warmwasser_getrennt += d.get('warmwasser_kwh', 0)

        gesamt_waerme = gesamt_heizung + gesamt_warmwasser
        durchschnitt_cop = gesamt_waerme / gesamt_strom if gesamt_strom > 0 else 0

        # Drift-Audit Domäne A1 / Issue #178: vorher las dieser Endpoint
        # `gas_kwh_preis_cent` (toter Key, Form schreibt `alter_preis_cent_kwh`)
        # und ignorierte den Wirkungsgrad-Faktor → Ergebnis +16€ Drift.
        # TODO: monatlicher Gaspreis-Override (analog `aussichten.py`-Loop)
        # könnte ergänzt werden, ist aber für Lebenszeit-Aggregat weniger relevant.
        wp_result = berechne_wp_ersparnis(
            wp_waerme_kwh=gesamt_waerme,
            wp_strom_kwh=gesamt_strom,
            wp_strompreis_cent=strompreis_cent,
            wp_parameter=wp.parameter,
        )
        wp_kosten = wp_result.wp_kosten_euro
        alte_heizung_kosten = wp_result.alte_heizung_kosten_euro
        ersparnis = wp_result.ersparnis_euro

        # CO2: Gas vs. Strommix (kanon. 0.201 / 0.38 kg/kWh)
        gas_co2 = gesamt_waerme * CO2_FAKTOR_GAS_KG_KWH
        strom_co2 = gesamt_strom * CO2_FAKTOR_STROM_KG_KWH
        co2_ersparnis = gas_co2 - strom_co2

        # Kompressor-Starts: Σ Lebensdauer kommt direkt aus dem Hersteller-
        # Sensor (Hersteller zählt seit Werks-Inbetriebnahme, das ist die
        # Wahrheit). Drift zwischen Hersteller-Counter und EEDC-Tagesinkrementen
        # wird im Daten-Checker sichtbar gemacht, nicht im Read-Pfad versteckt.
        # Max/Tag bleibt aus EEDC-Tagesinkrementen (echte Höchst-Tagessumme).
        wp_starts_list = starts_by_inv.get(wp.id, [])
        starts_lifetime = await get_counter_lifetime(
            db, anlage, wp, 'wp_starts_anzahl'
        )
        kompressor_starts_gesamt = (
            int(round(starts_lifetime)) if starts_lifetime is not None else None
        )
        kompressor_starts_max_tag = max(wp_starts_list) if wp_starts_list else None

        # Betriebsstunden (#238 detLAN): Σ Lebensdauer + Max/Tag analog zu den
        # Starts. KPI „Ø Laufzeit pro Start" und „Starts pro Betriebsstunde"
        # nur sichtbar wenn beide Werte für denselben Lebensdauer-Stand vorhanden
        # sind — ansonsten wären sie Krücken, weil Starts- und Stunden-Sensor
        # zu unterschiedlichen Zeitpunkten in Betrieb genommen worden sein
        # können.
        wp_stunden_list = stunden_by_inv.get(wp.id, [])
        betriebsstunden_gesamt = await get_counter_lifetime(
            db, anlage, wp, 'wp_betriebsstunden'
        )
        betriebsstunden_max_tag = (
            round(max(wp_stunden_list), 1) if wp_stunden_list else None
        )
        oe_laufzeit_pro_start_h: Optional[float] = None
        starts_pro_betriebsstunde: Optional[float] = None
        if (
            betriebsstunden_gesamt is not None
            and kompressor_starts_gesamt is not None
            and kompressor_starts_gesamt > 0
            and betriebsstunden_gesamt > 0
        ):
            oe_laufzeit_pro_start_h = round(
                betriebsstunden_gesamt / kompressor_starts_gesamt, 2
            )
            starts_pro_betriebsstunde = round(
                kompressor_starts_gesamt / betriebsstunden_gesamt, 3
            )

        zusammenfassung = {
            'gesamt_stromverbrauch_kwh': round(gesamt_strom, 1),
            'gesamt_heizenergie_kwh': round(gesamt_heizung, 1),
            'gesamt_warmwasser_kwh': round(gesamt_warmwasser, 1),
            'gesamt_waerme_kwh': round(gesamt_waerme, 1),
            'durchschnitt_cop': round(durchschnitt_cop, 2),
            'wp_kosten_euro': round(wp_kosten, 2),
            'alte_heizung_kosten_euro': round(alte_heizung_kosten, 2),
            'ersparnis_euro': round(ersparnis, 2),
            'co2_ersparnis_kg': round(co2_ersparnis, 1),
            'anzahl_monate': len(monatsdaten),
            'kompressor_starts_gesamt': kompressor_starts_gesamt,
            'kompressor_starts_max_tag': kompressor_starts_max_tag,
            'betriebsstunden_gesamt': (
                round(betriebsstunden_gesamt, 1)
                if betriebsstunden_gesamt is not None else None
            ),
            'betriebsstunden_max_tag': betriebsstunden_max_tag,
            'oe_laufzeit_pro_start_h': oe_laufzeit_pro_start_h,
            'starts_pro_betriebsstunde': starts_pro_betriebsstunde,
        }

        # Getrennte COP-Werte wenn separate Strommessung vorhanden
        if hat_getrennte_strom:
            zusammenfassung['gesamt_strom_heizen_kwh'] = round(gesamt_strom_heizen, 1)
            zusammenfassung['gesamt_strom_warmwasser_kwh'] = round(gesamt_strom_warmwasser, 1)
            zusammenfassung['gesamt_heizung_getrennt_kwh'] = round(gesamt_heizung_getrennt, 1)
            zusammenfassung['gesamt_warmwasser_getrennt_kwh'] = round(gesamt_warmwasser_getrennt, 1)
            zusammenfassung['cop_heizen'] = round(
                gesamt_heizung_getrennt / gesamt_strom_heizen, 2
            ) if gesamt_strom_heizen > 0 else 0
            zusammenfassung['cop_warmwasser'] = round(
                gesamt_warmwasser_getrennt / gesamt_strom_warmwasser, 2
            ) if gesamt_strom_warmwasser > 0 else 0

        dashboards.append(WaermepumpeDashboardResponse(
            investition=wp,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


@router.get("/dashboard/speicher/{anlage_id}", response_model=list[SpeicherDashboardResponse])
async def get_speicher_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(None),
    einspeiseverguetung_cent: Optional[float] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    """
    Speicher Dashboard für eine Anlage.

    Zeigt alle Speicher mit Zyklen, Effizienz, Eigenverbrauchserhöhung.
    Drift-Audit E: Tarife aus DB statt 30/8-Defaults aus Query-Param.
    """
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.SPEICHER.value)
    )
    speicher_list = inv_result.scalars().all()

    if not speicher_list:
        return []

    # Tarife aus DB laden (falls Query-Params nicht explizit übergeben)
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein_tarif = tarife.get("allgemein")
    if strompreis_cent is None:
        strompreis_cent = resolve_strompreis_for_komponente(tarife, "allgemein")
    if einspeiseverguetung_cent is None:
        einspeiseverguetung_cent = (
            allgemein_tarif.einspeiseverguetung_cent_kwh
            if allgemein_tarif and allgemein_tarif.einspeiseverguetung_cent_kwh is not None
            else EINSPEISEVERGUETUNG_DEFAULT_CENT
        )

    # Monatsdaten für Durchschnittspreis-Fallback laden
    anlage_md_result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    anlage_md_dict = {
        (m.jahr, m.monat): m for m in anlage_md_result.scalars().all()
    }

    # Gewichteter Ø-Netzbezugspreis für Spread-Berechnung
    gew_preis_sum = sum(
        resolve_netzbezug_preis_cent(m, strompreis_cent) * (m.netzbezug_kwh or 0)
        for m in anlage_md_dict.values()
    )
    gew_kwh_sum = sum(m.netzbezug_kwh or 0 for m in anlage_md_dict.values())
    eff_strompreis_cent = gew_preis_sum / gew_kwh_sum if gew_kwh_sum > 0 else strompreis_cent

    # Batch-Query: Alle Monatsdaten für alle Speicher auf einmal laden
    speicher_ids = [s.id for s in speicher_list]
    all_md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(speicher_ids))
        .order_by(InvestitionMonatsdaten.investition_id, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    all_monatsdaten = all_md_result.scalars().all()
    md_by_inv: dict[int, list] = {}
    for md in all_monatsdaten:
        md_by_inv.setdefault(md.investition_id, []).append(md)

    # Etappe C (#264): TEP-basierter effektiver Ladepreis — anlageweit, einmal.
    # Periode = älteste Speicher-Installation bis heute (oder neueste
    # Stilllegung, wenn alle Speicher stillgelegt sind). Try/except-gekapselt:
    # das Dashboard darf nie an einem Helper sterben (analog aussichten.py).
    installs = [s.anschaffungsdatum for s in speicher_list if s.anschaffungsdatum]
    stilllegungen = [s.stilllegungsdatum for s in speicher_list if s.stilllegungsdatum]
    periode_von = min(installs) if installs else None
    periode_bis = (
        max(stilllegungen)
        if stilllegungen and len(stilllegungen) == len(speicher_list)
        else date.today()
    )
    eff_ladepreis = None
    if periode_von is not None:
        try:
            eff_ladepreis = await berechne_effektiver_ladepreis(
                db, anlage_id=anlage_id, von=periode_von, bis=periode_bis,
            )
        except Exception as e:
            logger.warning(
                f"Speicher-Dashboard Anlage {anlage_id}: effektiver Ladepreis "
                f"fehlgeschlagen: {type(e).__name__}: {e}"
            )

    dashboards = []
    for speicher in speicher_list:
        # Issue #153 / #155 / #236: SoT-Filter inkl. stilllegungsdatum
        monatsdaten = [
            md for md in md_by_inv.get(speicher.id, [])
            if speicher.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        gesamt_ladung = 0
        gesamt_entladung = 0
        gesamt_arbitrage_kwh = 0
        arbitrage_preis_sum = 0
        arbitrage_count = 0

        monats_reihe: list[tuple[int, int, float, float]] = []
        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            md_ladung = d.get('ladung_kwh', 0) or 0
            md_entladung = d.get('entladung_kwh', 0) or 0
            gesamt_ladung += md_ladung
            gesamt_entladung += md_entladung
            monats_reihe.append((md.jahr, md.monat, md_ladung, md_entladung))
            # Arbitrage (Netzladung zu günstigen Zeiten)
            netzladung = d.get('speicher_ladung_netz_kwh', 0) or 0
            if netzladung > 0:
                gesamt_arbitrage_kwh += netzladung
                preis = d.get('speicher_ladepreis_cent', 0) or 0
                # Fallback: Monatsdaten Ø-Preis für dynamische Tarife
                if preis <= 0:
                    anlage_md = anlage_md_dict.get((md.jahr, md.monat))
                    if anlage_md and anlage_md.netzbezug_durchschnittspreis_cent:
                        preis = anlage_md.netzbezug_durchschnittspreis_cent
                if preis > 0:
                    arbitrage_preis_sum += preis * netzladung
                    arbitrage_count += netzladung

        # Effizienz — Σentladung/Σladung über die gesamte Historie. Über ein
        # langes Fenster mittelt sich der SoC-Übertrag aus (siehe
        # core/berechnungen/speicher.py); pro Monat wäre der Wert verzerrt.
        effizienz = speicher_effizienz_prozent(gesamt_ladung, gesamt_entladung) or 0
        verlauf = gleitende_effizienz(monats_reihe)
        durchsatz = pruefe_speicher_durchsatz_konsistenz(gesamt_ladung, gesamt_entladung)
        if not durchsatz.konsistent:
            logger.warning(
                f"Speicher-Dashboard Anlage {anlage_id}, Speicher {speicher.id}: "
                f"{durchsatz}"
            )

        # Zyklen (basierend auf Kapazität)
        params = speicher.parameter or {}
        kapazitaet = params.get(PARAM_SPEICHER["KAPAZITAET_KWH"], 10)
        arbitrage_faehig = params.get(PARAM_SPEICHER["ARBITRAGE_FAEHIG"], PARAM_SPEICHER_DEFAULTS["arbitrage_faehig"])
        vollzyklen = gesamt_ladung / kapazitaet if kapazitaet > 0 else 0

        # Etappe C (#264): SoC-korrigierter η-IST pro Speicher.
        # aggregiere_speicher_ist als SoT-Helper statt Parallel-Summe.
        eta_ist = None
        if monatsdaten and periode_von is not None:
            try:
                ist_agg = aggregiere_speicher_ist(
                    [md.verbrauch_daten or {} for md in monatsdaten]
                )
                if ist_agg.jahres_faktor > 0:
                    nutzbar = params.get(
                        PARAM_SPEICHER["NUTZBARE_KAPAZITAET_KWH"],
                        params.get(PARAM_SPEICHER["KAPAZITAET_KWH"], 0),
                    ) or 0
                    eta_ist = await berechne_ist_wirkungsgrad(
                        db, anlage_id=anlage_id, von=periode_von, bis=periode_bis,
                        ladung_kwh=ist_agg.ladung_kwh_jahr / ist_agg.jahres_faktor,
                        entladung_kwh=ist_agg.entladung_kwh_jahr / ist_agg.jahres_faktor,
                        nutzbare_kapazitaet_kwh=float(nutzbar),
                        fenster_monate=ist_agg.anzahl_monate,
                    )
            except Exception as e:
                logger.warning(
                    f"Speicher-Dashboard Anlage {anlage_id}, Speicher {speicher.id}: "
                    f"η-IST fehlgeschlagen: {type(e).__name__}: {e}"
                )

        # Ersparnis: Entladung ersetzt Netzbezug (Spread zwischen Netzbezug und Einspeisung)
        spread = eff_strompreis_cent - einspeiseverguetung_cent
        ersparnis = gesamt_entladung * spread / 100

        # Arbitrage-Gewinn: (Strompreis - Ladepreis) * Netzladung
        arbitrage_avg_preis = (arbitrage_preis_sum / arbitrage_count) if arbitrage_count > 0 else 0
        arbitrage_gewinn = gesamt_arbitrage_kwh * (eff_strompreis_cent - arbitrage_avg_preis) / 100 if gesamt_arbitrage_kwh > 0 else 0

        zusammenfassung = {
            'gesamt_ladung_kwh': round(gesamt_ladung, 1),
            'gesamt_entladung_kwh': round(gesamt_entladung, 1),
            'effizienz_prozent': round(effizienz, 1),
            'vollzyklen': round(vollzyklen, 1),
            'zyklen_pro_monat': round(vollzyklen / len(monatsdaten), 1) if monatsdaten else 0,
            'kapazitaet_kwh': kapazitaet,
            'ersparnis_euro': round(ersparnis, 2),
            'anzahl_monate': len(monatsdaten),
            # Arbitrage-Daten
            'arbitrage_faehig': arbitrage_faehig,
            'arbitrage_kwh': round(gesamt_arbitrage_kwh, 1),
            'arbitrage_avg_preis_cent': round(arbitrage_avg_preis, 1) if arbitrage_avg_preis > 0 else None,
            'arbitrage_gewinn_euro': round(arbitrage_gewinn, 2),
            # Invariante: Σentladung ≤ Σladung — kumulativ unmöglich zu verletzen.
            'durchsatz_inkonsistent': not durchsatz.konsistent,
        }

        # Etappe C (#264): TEP-basierte KPIs fürs UI — effektiver Ladepreis
        # mit Quellen-Transparenz (C1/C4), SoC-korrigierter η-IST + Degradations-
        # Alarm (C3). Felder sind optional; das Frontend fällt sonst auf die
        # bestehenden Werte (arbitrage_avg_preis_cent, effizienz_prozent) zurück.
        if eff_ladepreis is not None:
            zusammenfassung['effektiver_ladepreis_cent'] = (
                round(eff_ladepreis.effektiver_ladepreis_cent, 2)
                if eff_ladepreis.effektiver_ladepreis_cent is not None else None
            )
            zusammenfassung['effektiver_ladepreis_quelle'] = eff_ladepreis.quelle
            if eff_ladepreis.quelle == "datenbasis-zu-duenn":
                zusammenfassung['ladepreis_abdeckung_prozent'] = round(
                    eff_ladepreis.abdeckung_prozent, 0
                )
        if eta_ist is not None:
            wirkungsgrad_param = params.get(
                PARAM_SPEICHER["WIRKUNGSGRAD_PROZENT"],
                PARAM_SPEICHER_DEFAULTS["wirkungsgrad_prozent"],
            )
            zusammenfassung['ist_wirkungsgrad_prozent'] = (
                round(eta_ist.wirkungsgrad_prozent, 1)
                if eta_ist.wirkungsgrad_prozent is not None else None
            )
            zusammenfassung['wirkungsgrad_quelle'] = eta_ist.quelle
            zusammenfassung['param_wirkungsgrad_prozent'] = round(wirkungsgrad_param, 1)
            if eta_ist.wirkungsgrad_prozent is not None:
                zusammenfassung['eta_degradation_alarm'] = ist_eta_degradation_alarm(
                    ist_wirkungsgrad_prozent=eta_ist.wirkungsgrad_prozent,
                    param_wirkungsgrad_prozent=wirkungsgrad_param,
                )

        dashboards.append(SpeicherDashboardResponse(
            investition=speicher,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
            effizienz_verlauf=[asdict(m) for m in verlauf],
        ))

    return dashboards


@router.get("/monatsdaten/{anlage_id}/{jahr}/{monat}", response_model=list[InvestitionMonatsdatenResponse])
async def get_investition_monatsdaten_by_month(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt alle InvestitionMonatsdaten für eine Anlage und einen bestimmten Monat zurück.

    Dies wird vom MonatsdatenForm benötigt, um beim Bearbeiten eines Monats
    die vorhandenen Investitionsdaten (E-Auto km, Speicher Ladung, etc.) zu laden.

    Args:
        anlage_id: ID der Anlage
        jahr: Jahr
        monat: Monat (1-12)

    Returns:
        list[InvestitionMonatsdatenResponse]: Liste der InvestitionMonatsdaten
    """
    # Issue #123: MonatsdatenForm-Editor — zeige Investitionen, die in dem
    # bearbeiteten Monat aktiv waren (auch inzwischen stillgelegte).
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(aktiv_im_monat(jahr, monat))
    )
    investitionen = inv_result.scalars().all()

    # Batch-Query: Alle InvestitionMonatsdaten für diesen Monat auf einmal laden
    inv_ids = [inv.id for inv in investitionen]
    if not inv_ids:
        return []

    md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(inv_ids))
        .where(InvestitionMonatsdaten.jahr == jahr)
        .where(InvestitionMonatsdaten.monat == monat)
    )
    return md_result.scalars().all()


@router.get("/dashboard/wallbox/{anlage_id}", response_model=list[WallboxDashboardResponse])
async def get_wallbox_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(None, description="Override: Strompreis (auto aus Wallbox-Tarif wenn leer)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Wallbox Dashboard für eine Anlage.

    Zeigt Wallboxen mit Heimladung (aus E-Auto-Daten) und Ersparnis vs. externe Ladung.
    Die Wallbox-Daten kommen primär aus den E-Auto-Monatsdaten (ladung_pv_kwh + ladung_netz_kwh).
    """
    # Wallbox-Tarif laden
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    wallbox_tarif = tarife.get("wallbox")
    allgemein_tarif = tarife.get("allgemein")
    strompreis_cent = strompreis_cent or resolve_strompreis_for_komponente(tarife, "wallbox")

    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.WALLBOX.value)
    )
    wallboxen = inv_result.scalars().all()

    if not wallboxen:
        return []

    # E-Auto Monatsdaten für die Anlage laden (für Heimladung-Berechnung)
    eauto_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.E_AUTO.value)
    )
    eautos = eauto_result.scalars().all()

    # Batch-Query: Alle Monatsdaten für E-Autos + Wallboxen auf einmal laden
    eauto_ids = [e.id for e in eautos]
    wallbox_ids = [w.id for w in wallboxen]
    all_inv_ids = eauto_ids + wallbox_ids

    all_md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(all_inv_ids))
        .order_by(InvestitionMonatsdaten.investition_id, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    all_monatsdaten = all_md_result.scalars().all()
    md_by_inv: dict[int, list] = {}
    for md in all_monatsdaten:
        md_by_inv.setdefault(md.investition_id, []).append(md)

    # E-Auto- und Wallbox-IMD getrennt sammeln, dann via SoT-Helper zu EINER
    # konsistenten Heimladungs-Trias poolen (#262 junky84): evcc-Portal-Import
    # schreibt die Ladedaten in die Wallbox-Investition (data_import.py:453),
    # das Premium-Setup (separate E-Auto-Sensoren) aus E-Auto-Sicht. Früher
    # feldweises `max()` über pv/netz getrennt — das konnte pv aus der einen
    # und netz aus der anderen Quelle nehmen → PV-Anteil > 100 %. Jetzt
    # gewinnt die Quelle mit der größeren Heimladung die komplette Trias,
    # identisch zu Cockpit-Übersicht, Komponenten und EAutoDashboard.
    monate_set = set()

    # Issue #153 / #155: Daten vor Anschaffungsdatum ignorieren
    inv_by_id = {e.id: e for e in eautos}
    inv_by_id.update({w.id: w for w in wallboxen})

    def _nicht_aktiv_im_monat(inv_id: int, jahr: int, monat: int) -> bool:
        """#236: nicht-aktive Monate (vor anschaffungs- / nach stilllegungsdatum) überspringen."""
        inv = inv_by_id.get(inv_id)
        if not inv:
            return False
        return not inv.ist_aktiv_im_monat(jahr, monat)

    eauto_id_set = set(eauto_ids)
    wallbox_id_set = set(wallbox_ids)
    eauto_imd_data: list[dict] = []
    wb_imd_data: list[dict] = []
    for inv_id, md_list in md_by_inv.items():
        for md in md_list:
            if _nicht_aktiv_im_monat(inv_id, md.jahr, md.monat):
                continue
            d = md.verbrauch_daten or {}
            if inv_id in eauto_id_set:
                eauto_imd_data.append(d)
            elif inv_id in wallbox_id_set:
                wb_imd_data.append(d)
            monate_set.add((md.jahr, md.monat))

    emob_pool = aggregiere_emob_ladung(
        eauto_imd_data=eauto_imd_data,
        wallbox_imd_data=wb_imd_data,
    )
    gesamt_heim_pv = emob_pool.pv_kwh
    gesamt_heim_netz = emob_pool.netz_kwh
    gesamt_extern_kwh = emob_pool.extern_kwh
    gesamt_extern_euro = emob_pool.extern_euro
    gesamt_ladevorgaenge = emob_pool.ladevorgaenge
    gesamt_heim_ladung = emob_pool.ladung_kwh
    anzahl_monate = len(monate_set)

    # PV-Anteil der Heimladung
    pv_anteil = (gesamt_heim_pv / gesamt_heim_ladung * 100) if gesamt_heim_ladung > 0 else 0

    # Kosten Heimladung (nur Netzstrom, PV ist "kostenlos")
    heim_kosten = gesamt_heim_netz * strompreis_cent / 100

    # Was hätte externe Ladung gekostet?
    # Durchschnittspreis extern (wenn vorhanden) oder Annahme 50 ct/kWh
    extern_preis_kwh = (gesamt_extern_euro / gesamt_extern_kwh) if gesamt_extern_kwh > 0 else 0.50
    heim_als_extern_kosten = gesamt_heim_ladung * extern_preis_kwh

    # Ersparnis durch Heimladen (Wallbox-ROI)
    ersparnis_vs_extern = heim_als_extern_kosten - heim_kosten

    dashboards = []
    for wallbox in wallboxen:
        # Wallbox-eigene Monatsdaten aus Batch-Ergebnis
        # Issue #153 / #155 / #236: SoT-Filter inkl. stilllegungsdatum
        monatsdaten = [
            md for md in md_by_inv.get(wallbox.id, [])
            if wallbox.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        params = wallbox.parameter or {}
        # Bug #6 v3.25.0: vorher 'leistung_kw' (toter Schema-Key), Form/Wizard schreiben
        # 'max_ladeleistung_kw' → Dashboard zeigte immer 11 kW Default unabhängig vom User-Setup.
        leistung_kw = params.get(PARAM_WALLBOX["MAX_LADELEISTUNG_KW"], PARAM_WALLBOX_DEFAULTS["max_ladeleistung_kw"])

        zusammenfassung = {
            # Heimladung (aus E-Auto-Daten)
            'gesamt_heim_ladung_kwh': round(gesamt_heim_ladung, 1),
            'ladung_pv_kwh': round(gesamt_heim_pv, 1),
            'ladung_netz_kwh': round(gesamt_heim_netz, 1),
            'pv_anteil_prozent': round(pv_anteil, 1),
            # Externe Ladung zum Vergleich
            'extern_ladung_kwh': round(gesamt_extern_kwh, 1),
            'extern_kosten_euro': round(gesamt_extern_euro, 2),
            'extern_preis_kwh_euro': round(extern_preis_kwh, 2),
            # Kostenvergleich
            'heim_kosten_euro': round(heim_kosten, 2),
            'heim_als_extern_kosten_euro': round(heim_als_extern_kosten, 2),
            'ersparnis_vs_extern_euro': round(ersparnis_vs_extern, 2),
            # Wallbox-Info
            'leistung_kw': leistung_kw,
            'gesamt_ladevorgaenge': int(gesamt_ladevorgaenge),
            'ladevorgaenge_pro_monat': round(gesamt_ladevorgaenge / anzahl_monate, 1) if anzahl_monate > 0 else 0,
            'anzahl_monate': anzahl_monate,
        }

        dashboards.append(WallboxDashboardResponse(
            investition=wallbox,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


@router.get("/dashboard/balkonkraftwerk/{anlage_id}", response_model=list[BalkonkraftwerkDashboardResponse])
async def get_balkonkraftwerk_dashboard(
    anlage_id: int,
    strompreis_cent: float = Query(30.0),
    einspeiseverguetung_cent: float = Query(8.0),
    db: AsyncSession = Depends(get_db)
):
    """
    Balkonkraftwerk Dashboard für eine Anlage.

    Zeigt Balkonkraftwerke mit Erzeugung, Eigenverbrauch, Ersparnis.
    """
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.BALKONKRAFTWERK.value)
    )
    balkonkraftwerke = inv_result.scalars().all()

    if not balkonkraftwerke:
        return []

    # Batch-Query: Alle Monatsdaten für alle BKW auf einmal laden
    bkw_ids = [b.id for b in balkonkraftwerke]
    all_md_result = await db.execute(
        select(InvestitionMonatsdaten)
        .where(InvestitionMonatsdaten.investition_id.in_(bkw_ids))
        .order_by(InvestitionMonatsdaten.investition_id, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
    )
    all_monatsdaten = all_md_result.scalars().all()
    md_by_inv: dict[int, list] = {}
    for md in all_monatsdaten:
        md_by_inv.setdefault(md.investition_id, []).append(md)

    dashboards = []
    for bkw in balkonkraftwerke:
        # Issue #153 / #155 / #236: SoT-Filter inkl. stilllegungsdatum
        monatsdaten = [
            md for md in md_by_inv.get(bkw.id, [])
            if bkw.ist_aktiv_im_monat(md.jahr, md.monat)
        ]

        gesamt_erzeugung = 0
        gesamt_eigenverbrauch = 0
        gesamt_einspeisung = 0
        gesamt_speicher_ladung = 0
        gesamt_speicher_entladung = 0

        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            # Akzeptiere beide Feldnamen für Rückwärtskompatibilität
            gesamt_erzeugung += d.get('pv_erzeugung_kwh', 0) or d.get('erzeugung_kwh', 0) or 0
            gesamt_eigenverbrauch += d.get('eigenverbrauch_kwh', 0) or 0
            gesamt_einspeisung += d.get('einspeisung_kwh', 0) or 0
            gesamt_speicher_ladung += d.get('speicher_ladung_kwh', 0) or 0
            gesamt_speicher_entladung += d.get('speicher_entladung_kwh', 0) or 0

        # Parameter
        params = bkw.parameter or {}
        leistung_wp = params.get('leistung_wp', 0)
        anzahl = params.get('anzahl', 2)
        hat_speicher = params.get('hat_speicher', False)
        speicher_kapazitaet = params.get('speicher_kapazitaet_wh', 0)

        # Berechnungen
        gesamt_leistung_wp = leistung_wp * anzahl if leistung_wp else (bkw.leistung_kwp or 0) * 1000

        # Einspeisung berechnen falls nicht explizit erfasst
        # Einspeisung = Erzeugung - Eigenverbrauch (unvergütet ins Netz)
        if gesamt_einspeisung == 0 and gesamt_erzeugung > 0 and gesamt_eigenverbrauch > 0:
            gesamt_einspeisung = max(0, gesamt_erzeugung - gesamt_eigenverbrauch)

        # Eigenverbrauchsquote
        eigenverbrauch_quote = min(gesamt_eigenverbrauch / gesamt_erzeugung * 100, 100) if gesamt_erzeugung > 0 else 0

        # Speicher-Effizienz
        speicher_effizienz = (gesamt_speicher_entladung / gesamt_speicher_ladung * 100) if gesamt_speicher_ladung > 0 else 0

        # Ersparnis: Eigenverbrauch spart Netzbezug
        ersparnis_eigenverbrauch = gesamt_eigenverbrauch * strompreis_cent / 100
        # Einspeisung bei BKW ist i.d.R. unvergütet (keine Einspeisevergütung ohne Anmeldung)
        # Wird nur als Info angezeigt, nicht als Erlös
        erloes_einspeisung = 0  # BKW-Einspeisung ist unvergütet
        gesamt_ersparnis = ersparnis_eigenverbrauch

        # CO2-Einsparung für Eigenverbrauch
        co2_ersparnis = gesamt_eigenverbrauch * CO2_FAKTOR_STROM_KG_KWH

        # Spezifischer Ertrag (kWh pro kWp)
        spezifischer_ertrag = (gesamt_erzeugung / (gesamt_leistung_wp / 1000)) if gesamt_leistung_wp > 0 else 0

        zusammenfassung = {
            'gesamt_erzeugung_kwh': round(gesamt_erzeugung, 1),
            'gesamt_eigenverbrauch_kwh': round(gesamt_eigenverbrauch, 1),
            'gesamt_einspeisung_kwh': round(gesamt_einspeisung, 1),  # Berechnet: unvergütet ins Netz
            'eigenverbrauch_quote_prozent': round(eigenverbrauch_quote, 1),
            'spezifischer_ertrag_kwh_kwp': round(spezifischer_ertrag, 0),
            # Leistung
            'leistung_wp': gesamt_leistung_wp,
            'anzahl_module': anzahl,
            # Speicher (falls vorhanden)
            'hat_speicher': hat_speicher,
            'speicher_kapazitaet_wh': speicher_kapazitaet,
            'speicher_ladung_kwh': round(gesamt_speicher_ladung, 1) if hat_speicher else 0,
            'speicher_entladung_kwh': round(gesamt_speicher_entladung, 1) if hat_speicher else 0,
            'speicher_effizienz_prozent': round(speicher_effizienz, 1) if hat_speicher else 0,
            # Finanzen
            'ersparnis_eigenverbrauch_euro': round(ersparnis_eigenverbrauch, 2),
            'erloes_einspeisung_euro': round(erloes_einspeisung, 2),  # 0 bei BKW (unvergütet)
            'gesamt_ersparnis_euro': round(gesamt_ersparnis, 2),
            # CO2
            'co2_ersparnis_kg': round(co2_ersparnis, 1),
            'anzahl_monate': len(monatsdaten),
        }

        dashboards.append(BalkonkraftwerkDashboardResponse(
            investition=bkw,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


@router.get("/dashboard/sonstiges/{anlage_id}", response_model=list[SonstigesDashboardResponse])
async def get_sonstiges_dashboard(
    anlage_id: int,
    strompreis_cent: float = Query(30.0),
    einspeiseverguetung_cent: float = Query(8.0),
    db: AsyncSession = Depends(get_db)
):
    """
    Sonstiges Dashboard für eine Anlage.

    Zeigt sonstige Investitionen (Mini-BHKW, Pelletofen, etc.) mit kategorie-abhängigen Daten.
    """
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.SONSTIGES.value)
    )
    sonstige = inv_result.scalars().all()

    if not sonstige:
        return []

    dashboards = []
    for inv in sonstige:
        md_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id == inv.id)
            .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
        )
        monatsdaten = md_result.scalars().all()

        params = inv.parameter or {}
        kategorie = params.get('kategorie', 'erzeuger')
        beschreibung = params.get('beschreibung', '')

        # Aggregation basierend auf Kategorie
        gesamt_erzeugung = 0
        gesamt_eigenverbrauch = 0
        gesamt_einspeisung = 0
        gesamt_verbrauch = 0
        gesamt_bezug_pv = 0
        gesamt_bezug_netz = 0
        gesamt_ladung = 0
        gesamt_entladung = 0
        gesamt_sonstige_ertraege = 0
        gesamt_sonstige_ausgaben = 0

        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            summen = berechne_sonstige_summen(d)
            gesamt_sonstige_ertraege += summen["ertraege_euro"]
            gesamt_sonstige_ausgaben += summen["ausgaben_euro"]

            if kategorie == 'erzeuger':
                gesamt_erzeugung += d.get('erzeugung_kwh', 0)
                gesamt_eigenverbrauch += d.get('eigenverbrauch_kwh', 0)
                gesamt_einspeisung += d.get('einspeisung_kwh', 0)
            elif kategorie == 'verbraucher':
                gesamt_verbrauch += d.get('verbrauch_kwh', 0)
                gesamt_bezug_pv += d.get('bezug_pv_kwh', 0)
                gesamt_bezug_netz += d.get('bezug_netz_kwh', 0)
            elif kategorie == 'speicher':
                gesamt_ladung += d.get('ladung_kwh', 0)
                gesamt_entladung += d.get('entladung_kwh', 0)

        gesamt_sonstige_netto = gesamt_sonstige_ertraege - gesamt_sonstige_ausgaben

        # Berechnungen je nach Kategorie
        if kategorie == 'erzeuger':
            eigenverbrauch_quote = min(gesamt_eigenverbrauch / gesamt_erzeugung * 100, 100) if gesamt_erzeugung > 0 else 0
            ersparnis_eigenverbrauch = gesamt_eigenverbrauch * strompreis_cent / 100
            erloes_einspeisung = gesamt_einspeisung * einspeiseverguetung_cent / 100
            gesamt_ersparnis = ersparnis_eigenverbrauch + erloes_einspeisung + gesamt_sonstige_netto
            co2_ersparnis = gesamt_eigenverbrauch * CO2_FAKTOR_STROM_KG_KWH

            zusammenfassung = {
                'kategorie': kategorie,
                'beschreibung': beschreibung,
                'gesamt_erzeugung_kwh': round(gesamt_erzeugung, 1),
                'gesamt_eigenverbrauch_kwh': round(gesamt_eigenverbrauch, 1),
                'gesamt_einspeisung_kwh': round(gesamt_einspeisung, 1),
                'eigenverbrauch_quote_prozent': round(eigenverbrauch_quote, 1),
                'ersparnis_eigenverbrauch_euro': round(ersparnis_eigenverbrauch, 2),
                'erloes_einspeisung_euro': round(erloes_einspeisung, 2),
                'gesamt_ersparnis_euro': round(gesamt_ersparnis, 2),
                'co2_ersparnis_kg': round(co2_ersparnis, 1),
                'sonderkosten_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_ertraege_euro': round(gesamt_sonstige_ertraege, 2),
                'sonstige_ausgaben_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_netto_euro': round(gesamt_sonstige_netto, 2),
                'anzahl_monate': len(monatsdaten),
            }

        elif kategorie == 'verbraucher':
            pv_anteil = (gesamt_bezug_pv / gesamt_verbrauch * 100) if gesamt_verbrauch > 0 else 0
            kosten_netz = gesamt_bezug_netz * strompreis_cent / 100
            # Ersparnis: PV-Strom statt Netzstrom + sonstige Erträge/Ausgaben
            ersparnis_pv = gesamt_bezug_pv * strompreis_cent / 100 + gesamt_sonstige_netto

            zusammenfassung = {
                'kategorie': kategorie,
                'beschreibung': beschreibung,
                'gesamt_verbrauch_kwh': round(gesamt_verbrauch, 1),
                'bezug_pv_kwh': round(gesamt_bezug_pv, 1),
                'bezug_netz_kwh': round(gesamt_bezug_netz, 1),
                'pv_anteil_prozent': round(pv_anteil, 1),
                'kosten_netz_euro': round(kosten_netz, 2),
                'ersparnis_pv_euro': round(ersparnis_pv, 2),
                'sonderkosten_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_ertraege_euro': round(gesamt_sonstige_ertraege, 2),
                'sonstige_ausgaben_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_netto_euro': round(gesamt_sonstige_netto, 2),
                'anzahl_monate': len(monatsdaten),
            }

        else:  # speicher
            effizienz = (gesamt_entladung / gesamt_ladung * 100) if gesamt_ladung > 0 else 0
            # Ersparnis: Spread zwischen Netzbezug und Einspeisung
            spread = strompreis_cent - einspeiseverguetung_cent
            ersparnis = gesamt_entladung * spread / 100 + gesamt_sonstige_netto

            zusammenfassung = {
                'kategorie': kategorie,
                'beschreibung': beschreibung,
                'gesamt_ladung_kwh': round(gesamt_ladung, 1),
                'gesamt_entladung_kwh': round(gesamt_entladung, 1),
                'effizienz_prozent': round(effizienz, 1),
                'ersparnis_euro': round(ersparnis, 2),
                'sonderkosten_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_ertraege_euro': round(gesamt_sonstige_ertraege, 2),
                'sonstige_ausgaben_euro': round(gesamt_sonstige_ausgaben, 2),
                'sonstige_netto_euro': round(gesamt_sonstige_netto, 2),
                'anzahl_monate': len(monatsdaten),
            }

        dashboards.append(SonstigesDashboardResponse(
            investition=inv,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards
