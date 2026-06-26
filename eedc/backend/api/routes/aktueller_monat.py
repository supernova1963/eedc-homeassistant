"""
Aktueller Monat API Route.

Kombiniert Daten aus HA-Sensoren, HA-Statistics, Connectors und gespeicherten
Monatsdaten zu einer Echtzeit-Übersicht des laufenden Monats.
"""

import asyncio
import logging
from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.core.config import HA_INTEGRATION_AVAILABLE
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose, PVGISMonatsprognose
from backend.api.routes.strompreise import lade_tarife_fuer_anlage, resolve_netzbezug_preis_cent
from backend.api.routes.connector import _calc_month_delta
from backend.core.berechnungen import (
    autarkie_prozent,
    berechne_netzbezug_kosten,
    eauto_effizienz_100km,
    eigenverbrauchsquote_prozent,
    einspeise_erloes_euro,
    erzeugung_hinter_zaehler_kwh,
    imd_typ_beitrag,
    merge_datenquellen,
    spezifischer_ertrag_kwh_kwp,
)
from backend.services.einspeise_erloes_service import get_neg_preis_einspeisung_monat
from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis
from backend.services.eauto_wirtschaftlichkeit import (
    attribute_emob_pool_by_km,
    berechne_eauto_ersparnis,
    compute_emob_pool_attribution,
    get_emob_heimladung_canonical,
    pick_emob_ref_parameter,
)
from backend.core.wirtschaftlichkeit_defaults import (
    EINSPEISEVERGUETUNG_DEFAULT_CENT,
    NETZBEZUG_DEFAULT_CENT,
)
from backend.core.field_definitions import (
    get_eauto_ladung_kwh,
    get_emob_pv_netz_kwh,
    get_pv_erzeugung_kwh,
    get_sonstiges_verbrauch_kwh,
    get_wp_heizenergie_kwh,
    get_wp_strom_kwh,
)
from backend.utils.sonstige_positionen import berechne_sonstige_summen, aggregiere_sonstige_je_monat
from backend.core.investition_parameter import ist_dienstlich

logger = logging.getLogger(__name__)

router = APIRouter()

MONAT_NAMEN = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


# =============================================================================
# Schemas
# =============================================================================

class DatenquelleInfo(BaseModel):
    """Quellenangabe für ein einzelnes Feld."""
    quelle: str          # "ha_sensor" | "local_connector" | "gespeichert"
    konfidenz: int       # 95, 90, 85
    zeitpunkt: Optional[str] = None


class InvestitionFinancialDetail(BaseModel):
    """Finanzielle Details einer einzelnen Investition für den T-Konto-View."""
    investition_id: int
    bezeichnung: str
    typ: str
    betriebskosten_monat_euro: float = 0.0
    erloes_euro: Optional[float] = None      # z.B. BKW-Einspeisung
    ersparnis_euro: Optional[float] = None   # Eigenverbrauch, WP, eMob, Speicher, ...
    ersparnis_label: str = ""                # "Eigenverbrauch-Ersparnis", "Ersparnis vs. Gas", ...
    formel: Optional[str] = None
    berechnung: Optional[str] = None
    # Sonstige Positionen (z.B. AG-Vergütung Dienstwagen, THG-Quote, Reparaturen).
    # Werden je Investition aggregiert; Detail-Zeilen rendert das Frontend.
    sonstige_ertraege_euro: float = 0.0
    sonstige_ausgaben_euro: float = 0.0


class SonstigesGeraet(BaseModel):
    """Ein einzelnes „Sonstiges"-Gerät mit seinen Energiewerten — für die Sonder-
    Darstellung im Cockpit: zwei Blöcke (Erzeuger/Verbraucher), darin pro Gerät
    eine eigene Werte-Zeile mit Bezeichnung."""
    bezeichnung: str
    kategorie: str  # "erzeuger" | "verbraucher"
    # Erzeuger
    erzeugung_kwh: Optional[float] = None
    eigenverbrauch_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    # Verbraucher
    verbrauch_kwh: Optional[float] = None
    bezug_pv_kwh: Optional[float] = None
    bezug_netz_kwh: Optional[float] = None


class AktuellerMonatResponse(BaseModel):
    """Aggregierte Übersicht des aktuellen Monats."""
    anlage_id: int
    anlage_name: str
    jahr: int
    monat: int
    monat_name: str
    aktualisiert_um: str

    # Verfügbare Quellen
    quellen: dict[str, bool]

    # Energie-Bilanz (kWh)
    pv_erzeugung_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    eigenverbrauch_kwh: Optional[float] = None
    direktverbrauch_kwh: Optional[float] = None  # PV direkt verbraucht (ohne Speicher): EV − Speicher-Entladung; günstigster Verbrauch (nur entgangene Einspeisung)
    gesamtverbrauch_kwh: Optional[float] = None

    # Quoten (%)
    autarkie_prozent: Optional[float] = None
    eigenverbrauch_quote_prozent: Optional[float] = None
    # Spezifischer Ertrag kWh/kWp — gleiche Basis wie der Community-Vergleich
    # (anlage.leistung_kwp), damit die Abweichung zum Community-Median stimmt.
    spez_ertrag: Optional[float] = None

    # Komponenten — Speicher
    speicher_ladung_kwh: Optional[float] = None
    speicher_entladung_kwh: Optional[float] = None
    speicher_ladung_netz_kwh: Optional[float] = None   # Arbitrage-Ladung vom Netz
    speicher_wirkungsgrad_prozent: Optional[float] = None  # Entladung / Ladung * 100
    speicher_vollzyklen: Optional[float] = None        # Ladung / Kapazität
    speicher_kapazitaet_kwh: Optional[float] = None    # Aus Investition.parameter
    # Etappe C (#264): SoC-Drift über die Monatsgrenze macht den Monats-η
    # unzuverlässig (Speicher Anfang voll → Ende leer ergibt naiv > 100 %).
    # Flag setzen, wenn |ΔSoC × Kapazität| > 10 % der Monats-Ladung; das
    # Frontend blendet dann den Monats-η aus und verweist auf den Jahreswert.
    speicher_soc_drift_signifikant: bool = False
    speicher_effektiver_ladepreis_cent: Optional[float] = None
    speicher_effektiver_ladepreis_quelle: Optional[str] = None  # dyn-tarif | boersenpreis
    hat_speicher: bool = False

    # Komponenten — Wärmepumpe
    wp_strom_kwh: Optional[float] = None
    wp_waerme_kwh: Optional[float] = None
    wp_heizung_kwh: Optional[float] = None
    wp_warmwasser_kwh: Optional[float] = None
    # #191: Strom-Aufteilung Heizung/Warmwasser. Nur gesetzt wenn mindestens
    # eine WP-Investition `getrennte_strommessung=true` hat. Sonst None →
    # Frontend zeigt nur den Gesamtstromverbrauch.
    wp_strom_heizen_kwh: Optional[float] = None
    wp_strom_warmwasser_kwh: Optional[float] = None
    # Issue #169: Kompressor-Starts. Quelle: TagesZusammenfassung.komponenten_starts
    # über die Tage des Monats, summiert über alle WP-Investitionen.
    wp_starts_max_tag: Optional[int] = None
    wp_starts_summe_monat: Optional[int] = None
    # Issue #238: Betriebsstunden analog zu den Starts (gleiche Counter-Architektur,
    # Feld `wp_betriebsstunden` in komponenten_starts). Stunden → float.
    wp_betriebsstunden_max_tag: Optional[float] = None
    wp_betriebsstunden_summe_monat: Optional[float] = None
    hat_waermepumpe: bool = False

    # Komponenten — E-Mobilität
    emob_ladung_kwh: Optional[float] = None
    emob_km: Optional[float] = None
    # Ø Verbrauch (kWh/100 km) zentral via core/berechnungen/emob.py (gemessen > Ladung).
    emob_verbrauch_100km: Optional[float] = None
    emob_verbrauch_quelle: str = "keine"
    emob_ladung_pv_kwh: Optional[float] = None       # PV-Anteil der Ladung
    emob_ladung_netz_kwh: Optional[float] = None     # Netz-Anteil
    emob_ladung_extern_kwh: Optional[float] = None   # Extern (Ladesäule o.ä.)
    emob_v2h_kwh: Optional[float] = None             # V2H-Rückspeisung
    hat_emobilitaet: bool = False

    # Komponenten — BKW
    bkw_erzeugung_kwh: Optional[float] = None
    bkw_eigenverbrauch_kwh: Optional[float] = None
    hat_balkonkraftwerk: bool = False

    # Komponenten — Sonstiges
    sonstiges_erzeugung_kwh: Optional[float] = None    # Erzeuger-Typ
    sonstiges_eigenverbrauch_kwh: Optional[float] = None
    sonstiges_einspeisung_kwh: Optional[float] = None
    sonstiges_verbrauch_kwh: Optional[float] = None    # Verbraucher-Typ
    sonstiges_bezug_pv_kwh: Optional[float] = None
    sonstiges_bezug_netz_kwh: Optional[float] = None
    # Pro-Gerät-Aufschlüsselung für die Sonder-Darstellung (2 Blöcke Erzeuger/
    # Verbraucher, darin je Gerät eine eigene Werte-Zeile mit Bezeichnung).
    sonstiges_geraete: list[SonstigesGeraet] = []
    hat_sonstiges: bool = False

    # Finanzen (Euro)
    einspeise_erloes_euro: Optional[float] = None
    netzbezug_kosten_euro: Optional[float] = None
    ev_ersparnis_euro: Optional[float] = None
    netto_ertrag_euro: Optional[float] = None
    wp_ersparnis_euro: Optional[float] = None
    emob_ersparnis_euro: Optional[float] = None
    # Sonstige Positionen aggregiert (z.B. AG-Vergütung Dienstwagen, THG-Quote,
    # Reparaturen). Detail-Zeilen pro Investition stehen in
    # investitionen_financials. Frontend addiert sonstige_netto auf
    # nettoNachAllem; gesamtnettoertrag enthält sie bewusst NICHT (Backward-Compat).
    sonstige_ertraege_euro: float = 0.0
    sonstige_ausgaben_euro: float = 0.0
    sonstige_netto_euro: float = 0.0
    gesamtnettoertrag_euro: Optional[float] = None  # Erlöse + Einsparungen − Kosten

    # Tarif-Info
    netzbezug_preis_cent: Optional[float] = None      # Verwendeter Tarif
    einspeise_preis_cent: Optional[float] = None
    netzbezug_durchschnittspreis_cent: Optional[float] = None  # Flexibler Tarif (Monatsdurchschnitt)

    # Vergleiche
    vorjahr: Optional[dict] = None
    soll_pv_kwh: Optional[float] = None

    # Betriebskosten (anteilig, Σ betriebskosten_jahr / 12 aller aktiven Investitionen)
    betriebskosten_anteilig_euro: Optional[float] = None

    # Per-Investition Finanzdetails (für T-Konto)
    investitionen_financials: list[InvestitionFinancialDetail] = []

    # Aktive Geräte je Typ im Monat (Namen) — macht in aggregierten Blöcken
    # kenntlich, woraus die Summe besteht (z. B. PV aus mehreren Strings + WR,
    # E-Mob aus Auto + Wallbox). Deckungsgleich mit der Aggregation (ist_aktiv_im_monat).
    komponenten_geraete: dict[str, list[str]] = {}

    # Quellenangabe pro Feld
    feld_quellen: dict[str, DatenquelleInfo] = {}


# =============================================================================
# Datensammlung
# =============================================================================

async def _collect_ha_statistics_data(anlage: Anlage, jahr: int, monat: int) -> dict[str, tuple[float, DatenquelleInfo]]:
    """Sammelt Daten aus der HA Recorder-Statistik-DB (Konfidenz 92%).

    Liest MAX(state) - MIN(state) pro Sensor aus der HA statistics-Tabelle.
    Funktioniert für total_increasing UND measurement Sensoren (Fallback).
    """
    if not HA_INTEGRATION_AVAILABLE:
        return {}

    from backend.services.ha_statistics_service import get_ha_statistics_service
    ha_stats = get_ha_statistics_service()
    if not ha_stats.is_available:
        return {}

    mapping = anlage.sensor_mapping or {}
    basis = mapping.get("basis", {})
    inv_mapping = mapping.get("investitionen", {})

    # Sensor-IDs sammeln und Rückmapping erstellen: sensor_id → feld_name
    sensor_to_feld: dict[str, str] = {}

    basis_feld_map = {
        "einspeisung": "einspeisung_kwh",
        "netzbezug": "netzbezug_kwh",
        "pv_gesamt": "pv_erzeugung_kwh",
    }
    for mapping_key, feld_name in basis_feld_map.items():
        feld_mapping = basis.get(mapping_key)
        if feld_mapping and feld_mapping.get("strategie") == "sensor" and feld_mapping.get("sensor_id"):
            sensor_to_feld[feld_mapping["sensor_id"]] = feld_name

    for inv_id_str, inv_data in inv_mapping.items():
        felder = inv_data.get("felder", {})
        for feld_key, feld_config in felder.items():
            if feld_config and feld_config.get("strategie") == "sensor" and feld_config.get("sensor_id"):
                sensor_to_feld[feld_config["sensor_id"]] = f"inv_{inv_id_str}_{feld_key}"

    if not sensor_to_feld:
        return {}

    # Synchronen SQLite-Zugriff in Thread auslagern
    try:
        sensor_ids = list(sensor_to_feld.keys())
        result = await asyncio.to_thread(ha_stats.get_monatswerte, sensor_ids, jahr, monat)
    except Exception:
        logger.warning("HA Statistics DB nicht erreichbar")
        return {}

    resolved: dict[str, tuple[float, DatenquelleInfo]] = {}
    now_str = datetime.now().isoformat()
    quelle = DatenquelleInfo(quelle="ha_statistics", konfidenz=92, zeitpunkt=now_str)

    for sensor_wert in result.sensoren:
        feld_name = sensor_to_feld.get(sensor_wert.sensor_id)
        if feld_name and sensor_wert.differenz is not None and sensor_wert.differenz > 0:
            resolved[feld_name] = (sensor_wert.differenz, quelle)

    return resolved


async def _collect_connector_data(anlage: Anlage, jahr: int, monat: int) -> dict[str, tuple[float, DatenquelleInfo]]:
    """Sammelt Daten aus Connector-Snapshots (Konfidenz 90%)."""
    config = anlage.connector_config
    if not config:
        return {}

    snapshots = config.get("meter_snapshots", {})
    if not snapshots:
        return {}

    delta = _calc_month_delta(snapshots, jahr, monat)
    if not delta:
        return {}

    resolved: dict[str, tuple[float, DatenquelleInfo]] = {}
    last_fetch = config.get("last_fetch")
    quelle = DatenquelleInfo(quelle="local_connector", konfidenz=90, zeitpunkt=last_fetch)

    feld_map = {
        "pv_erzeugung_kwh": "pv_erzeugung_kwh",
        "einspeisung_kwh": "einspeisung_kwh",
        "netzbezug_kwh": "netzbezug_kwh",
        "batterie_ladung_kwh": "speicher_ladung_kwh",
        "batterie_entladung_kwh": "speicher_entladung_kwh",
    }
    for delta_key, feld_name in feld_map.items():
        val = delta.get(delta_key)
        if val is not None:
            resolved[feld_name] = (val, quelle)

    return resolved


async def _collect_saved_data(
    anlage_id: int, jahr: int, monat: int,
    investitionen: list[Investition],
    db: AsyncSession,
) -> dict[str, tuple[float, DatenquelleInfo]]:
    """Sammelt bereits gespeicherte Monatsdaten (Konfidenz 85%)."""
    resolved: dict[str, tuple[float, DatenquelleInfo]] = {}
    quelle = DatenquelleInfo(quelle="gespeichert", konfidenz=85)

    # Monatsdaten (Basis)
    md_result = await db.execute(
        select(Monatsdaten).where(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == jahr,
            Monatsdaten.monat == monat,
        )
    )
    md = md_result.scalar_one_or_none()

    if md:
        quelle = DatenquelleInfo(
            quelle="gespeichert", konfidenz=85,
            zeitpunkt=md.updated_at.isoformat() if hasattr(md, 'updated_at') and md.updated_at else None,
        )
        for attr, feld in [
            ("einspeisung_kwh", "einspeisung_kwh"),
            ("netzbezug_kwh", "netzbezug_kwh"),
        ]:
            val = getattr(md, attr, None)
            if val is not None:
                resolved[feld] = (val, quelle)

    # InvestitionMonatsdaten
    inv_ids = [i.id for i in investitionen]
    if inv_ids:
        imd_result = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(inv_ids),
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            )
        )
        inv_by_id = {i.id: i for i in investitionen}
        pv_erzeugung_total = 0.0
        speicher_ladung_total = 0.0
        speicher_entladung_total = 0.0
        wp_strom_total = 0.0
        wp_waerme_total = 0.0
        # E-Mobilität: rohe IMD je Quelle (E-Auto / Wallbox) sammeln, danach
        # zentral via `get_emob_heimladung_canonical` zu EINER konsistenten Heim-
        # ladungs-Trias poolen. Beide Investitionstypen messen denselben
        # Stromfluss aus zwei Perspektiven (siehe docs/KONZEPT-WALLBOX-EAUTO.md)
        # — der Helper wählt die Quelle mit der größeren Heimladung komplett,
        # statt feldweisem max() (das pv aus der einen, netz aus der anderen
        # Quelle nehmen konnte → PV-Anteil > 100 %, #262). km kommt nur vom
        # E-Auto. Gleiche Logik wie Übersicht / Komponenten / EAutoDashboard.
        eauto_imd_data: list[dict] = []
        wb_imd_data: list[dict] = []
        eauto_km_total = 0.0
        eauto_verbrauch_total = 0.0  # gemessener Fahrverbrauch (Vorrang vor Ladung)
        bkw_erzeugung_total = 0.0
        bkw_eigenverbrauch_total = 0.0
        sonstiges_erzeugung_total = 0.0  # sonstige Erzeuger (BHKW) hinter dem Zähler

        for imd in imd_result.scalars().all():
            inv = inv_by_id.get(imd.investition_id)
            if not inv:
                continue
            # Issue #153 / #155 / #236: SoT-Filter inkl. stilllegungsdatum
            if not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
                continue
            data = imd.verbrauch_daten or {}
            # Per-Typ-Feld-Auflösung zentral ([[imd_typ_beitrag]], Block 1).
            b = imd_typ_beitrag(inv, data)

            if inv.typ == "pv-module":
                pv_erzeugung_total += b.pv_erzeugung
            elif inv.typ == "speicher":
                speicher_ladung_total += b.speicher_ladung
                speicher_entladung_total += b.speicher_entladung
            elif inv.typ == "waermepumpe":
                # #183: bei getrennter Strommessung Gesamt-Strom aus Einzel-
                # Sensoren (im Resolver). wp_waerme = waerme_kwh oder Heiz+WW.
                wp_strom_total += b.wp_strom
                wp_waerme_total += b.wp_waerme
            elif inv.typ == "e-auto":
                if not ist_dienstlich(inv):
                    eauto_imd_data.append(data)
                    eauto_km_total += b.eauto_km
                    eauto_verbrauch_total += b.eauto_verbrauch
            elif inv.typ == "wallbox":
                if not ist_dienstlich(inv):
                    wb_imd_data.append(data)
            elif inv.typ == "balkonkraftwerk":
                bkw_kwh = b.bkw_erzeugung
                bkw_erzeugung_total += bkw_kwh
                # BKW ist PV-Erzeugung → fließt in Gesamt-PV ein
                pv_erzeugung_total += bkw_kwh
                # D5 (Block 1, IST-Stand erhalten): eigenverbrauch fällt bei
                # fehlendem Messwert auf die volle Erzeugung zurück — Site-1-Quirk,
                # divergent zu Komponenten/Übersicht (siehe FELD-MATRIX D5).
                bkw_eigenverbrauch_total += b.bkw_eigenverbrauch or bkw_kwh
            elif inv.typ == "sonstiges":
                # Sonstiger Erzeuger (BHKW) speist hinter den Zähler → in die
                # Netzpunkt-Bilanz (Resolver kategorie-bewusst: nur erzeuger).
                sonstiges_erzeugung_total += b.sonstiges_erzeugung

        # E-Mobilitäts-Pool: EINE Quelle liefert die konsistente Heimladungs-
        # Trias (pv + netz == ladung). Früher feldweises max() — das nahm pv
        # aus der einen, netz aus der anderen Quelle und konnte PV-Anteil
        # > 100 % erzeugen (#262 junky84). Externe Lade-Kosten (#260) kommen
        # paarweise aus der Quelle mit den höheren Extern-Kosten.
        emob_pool = get_emob_heimladung_canonical(
            eauto_imd_data=eauto_imd_data,
            wallbox_imd_data=wb_imd_data,
        )
        emob_ladung_total = emob_pool.ladung_kwh
        emob_pv_ladung_total = emob_pool.pv_kwh
        emob_km_total = eauto_km_total
        emob_extern_euro_total = emob_pool.extern_euro

        if pv_erzeugung_total > 0:
            resolved["pv_erzeugung_kwh"] = (pv_erzeugung_total, quelle)
        if speicher_ladung_total > 0:
            resolved["speicher_ladung_kwh"] = (speicher_ladung_total, quelle)
        if speicher_entladung_total > 0:
            resolved["speicher_entladung_kwh"] = (speicher_entladung_total, quelle)
        if wp_strom_total > 0:
            resolved["wp_strom_kwh"] = (wp_strom_total, quelle)
        if wp_waerme_total > 0:
            resolved["wp_waerme_kwh"] = (wp_waerme_total, quelle)
        if emob_ladung_total > 0:
            resolved["emob_ladung_kwh"] = (emob_ladung_total, quelle)
        if emob_km_total > 0:
            resolved["emob_km"] = (emob_km_total, quelle)
        if eauto_verbrauch_total > 0:
            resolved["emob_verbrauch_kwh"] = (eauto_verbrauch_total, quelle)
        if emob_pv_ladung_total > 0:
            resolved["emob_pv_ladung_kwh"] = (emob_pv_ladung_total, quelle)
        if emob_extern_euro_total > 0:
            resolved["emob_ladung_extern_euro"] = (emob_extern_euro_total, quelle)
        if bkw_erzeugung_total > 0:
            resolved["bkw_erzeugung_kwh"] = (bkw_erzeugung_total, quelle)
        if bkw_eigenverbrauch_total > 0:
            resolved["bkw_eigenverbrauch_kwh"] = (bkw_eigenverbrauch_total, quelle)
        if sonstiges_erzeugung_total > 0:
            resolved["sonstiges_erzeugung_kwh"] = (sonstiges_erzeugung_total, quelle)

    return resolved


async def _collect_mqtt_inbound_data(anlage: Anlage, investitionen: list[Investition]) -> dict[str, tuple[float, DatenquelleInfo]]:
    """Sammelt Monatsdaten aus MQTT-Inbound Energy-Topics (Konfidenz 91%).

    Liest kumulierte Monatswerte aus dem MQTT-Cache.
    Topics: eedc/{id}/energy/einspeisung_kwh, .../inv/{inv_id}/ladung_kwh etc.
    """
    from backend.services.mqtt_inbound_service import get_mqtt_inbound_service

    svc = get_mqtt_inbound_service()
    if not svc:
        return {}

    energy = svc.cache.get_energy_data(anlage.id)
    if not energy:
        return {}

    resolved: dict[str, tuple[float, DatenquelleInfo]] = {}
    now_str = datetime.now().isoformat()
    quelle = DatenquelleInfo(quelle="mqtt_inbound", konfidenz=91, zeitpunkt=now_str)

    # Basis-Felder
    basis_map = {
        "pv_gesamt_kwh": "pv_erzeugung_kwh",
        "einspeisung_kwh": "einspeisung_kwh",
        "netzbezug_kwh": "netzbezug_kwh",
    }
    for mqtt_key, feld_name in basis_map.items():
        val = energy.get(mqtt_key)
        if val is not None and val > 0:
            resolved[feld_name] = (val, quelle)

    # Investitions-Felder: inv/{inv_id}/{key} → inv_{inv_id}_{key}
    # (passt zum Aggregations-Pattern in der Prioritätskette)
    inv_ids = {str(i.id) for i in investitionen}
    for mqtt_key, val in energy.items():
        if not mqtt_key.startswith("inv/") or val is None or val <= 0:
            continue
        parts = mqtt_key.split("/", 2)  # ["inv", "3", "ladung_kwh"]
        if len(parts) == 3 and parts[1] in inv_ids:
            resolved[f"inv_{parts[1]}_{parts[2]}"] = (val, quelle)

    return resolved


# =============================================================================
# Vergleichsdaten
# =============================================================================

async def _load_vorjahr(anlage_id: int, investitionen: list[Investition], jahr: int, monat: int, db: AsyncSession) -> Optional[dict]:
    """Lädt Vorjahres-Monatsdaten für Vergleich (Energie + Finanzen)."""
    from datetime import date as date_type
    vj = jahr - 1

    md_result = await db.execute(
        select(Monatsdaten).where(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == vj,
            Monatsdaten.monat == monat,
        )
    )
    md = md_result.scalar_one_or_none()
    if not md:
        return None

    result: dict = {
        "einspeisung_kwh": md.einspeisung_kwh,
        "netzbezug_kwh": md.netzbezug_kwh,
        "netzbezug_durchschnittspreis_cent": md.netzbezug_durchschnittspreis_cent,
    }

    # PV-Erzeugung + Batterie + WP + eMob aus InvestitionMonatsdaten
    pv_inv_ids = [i.id for i in investitionen if i.typ in ("pv-module", "balkonkraftwerk")]
    bat_inv_ids = [i.id for i in investitionen if i.typ == "speicher"]
    wp_inv_ids = [i.id for i in investitionen if i.typ == "waermepumpe"]
    # E-Auto und Wallbox separat halten — selbe Pool-Doppelzählungs-Falle wie
    # in `_collect_saved_data` (siehe dort). Max-pro-Feld statt Summe.
    eauto_inv_ids = [i.id for i in investitionen if i.typ == "e-auto" and not ist_dienstlich(i)]
    wb_inv_ids = [i.id for i in investitionen if i.typ == "wallbox" and not ist_dienstlich(i)]
    # Sonstige Erzeuger (BHKW) speisen hinter den Zähler → in die Netzpunkt-Bilanz
    # (Konzept Sonstiger Erzeuger); auch der VJ-Vergleich muss sie mitziehen,
    # sonst zeigt das YoY-Delta einen methodischen Scheinsprung.
    sonstiges_inv_ids = [i.id for i in investitionen if i.typ == "sonstiges"]
    all_inv_ids = pv_inv_ids + bat_inv_ids + wp_inv_ids + eauto_inv_ids + wb_inv_ids + sonstiges_inv_ids
    sonstiges_vj = 0.0

    if all_inv_ids:
        imd_result = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(all_inv_ids),
                InvestitionMonatsdaten.jahr == vj,
                InvestitionMonatsdaten.monat == monat,
            )
        )
        pv_vj = 0.0
        bat_ladung_vj = 0.0
        bat_entladung_vj = 0.0
        wp_strom_vj = 0.0
        wp_waerme_vj = 0.0
        eauto_ladung_vj = 0.0
        wb_ladung_vj = 0.0
        emob_km_vj = 0.0

        inv_by_id_vj = {i.id: i for i in investitionen}
        for imd in imd_result.scalars().all():
            inv = inv_by_id_vj.get(imd.investition_id)
            if not inv:
                continue
            data = imd.verbrauch_daten or {}
            # Per-Typ-Feld-Auflösung zentral ([[imd_typ_beitrag]], Block 1).
            b = imd_typ_beitrag(inv, data)
            if imd.investition_id in pv_inv_ids:
                # pv_inv_ids enthält PV-Module UND BKW. D6 (IST-Stand erhalten):
                # pv-module behält den erzeugung_kwh-Legacy-Fallback (divergent zum
                # aktuellen Monat); BKW kanonisch via Resolver.
                pv_vj += (
                    get_pv_erzeugung_kwh(data) if inv.typ == "pv-module"
                    else b.bkw_erzeugung
                )
            elif imd.investition_id in bat_inv_ids:
                bat_ladung_vj += b.speicher_ladung
                bat_entladung_vj += b.speicher_entladung
            elif imd.investition_id in wp_inv_ids:
                # D1 (Block 1): wp_waerme kanonisch (waerme_kwh-Vorrang +
                # heizung_kwh-Legacy) statt rohem Heiz+WW — angeglichen an den
                # aktuellen Monat derselben Route.
                wp_strom_vj += b.wp_strom
                wp_waerme_vj += b.wp_waerme
            elif imd.investition_id in eauto_inv_ids:
                eauto_ladung_vj += b.eauto_ladung_kanonisch
                emob_km_vj += b.eauto_km
            elif imd.investition_id in wb_inv_ids:
                wb_ladung_vj += b.wallbox_ladung
            elif inv.typ == "sonstiges":
                sonstiges_vj += b.sonstiges_erzeugung

        # Pool-Auswahl konsistent zu _collect_saved_data: pro Feld die größere
        # Quelle. WB liefert üblicherweise Loadpoint-Wahrheit, EAuto ist Vehicle-
        # Sicht; wenn nur eine gepflegt ist, gewinnt sie automatisch.
        emob_ladung_vj = max(eauto_ladung_vj, wb_ladung_vj)

        if pv_vj > 0:
            result["pv_erzeugung_kwh"] = round(pv_vj, 1)
        if bat_ladung_vj > 0:
            result["speicher_ladung_kwh"] = round(bat_ladung_vj, 1)
        if bat_entladung_vj > 0:
            result["speicher_entladung_kwh"] = round(bat_entladung_vj, 1)
        if wp_strom_vj > 0:
            result["wp_strom_kwh"] = round(wp_strom_vj, 1)
        if wp_waerme_vj > 0:
            result["wp_waerme_kwh"] = round(wp_waerme_vj, 1)
        if emob_ladung_vj > 0:
            result["emob_ladung_kwh"] = round(emob_ladung_vj, 1)
        if emob_km_vj > 0:
            result["emob_km"] = round(emob_km_vj, 1)

    # Berechnete Energie-Werte (mit Batterie-Korrektur)
    pv = result.get("pv_erzeugung_kwh", 0) or 0
    einsp = result.get("einspeisung_kwh", 0) or 0
    netz = result.get("netzbezug_kwh", 0) or 0
    bat_ladung = result.get("speicher_ladung_kwh", 0) or 0
    bat_entladung = result.get("speicher_entladung_kwh", 0) or 0
    # Netzpunkt-Bilanz inkl. sonstiger Erzeuger (BHKW); `pv` (result) bleibt rein.
    erzeugung_bilanz = erzeugung_hinter_zaehler_kwh(pv, sonstiges_vj)
    direktverbrauch = max(0, erzeugung_bilanz - einsp - bat_ladung) if erzeugung_bilanz > 0 else 0
    ev = direktverbrauch + bat_entladung
    gv = ev + netz
    result["eigenverbrauch_kwh"] = round(ev, 1)
    result["direktverbrauch_kwh"] = round(direktverbrauch, 1)
    result["gesamtverbrauch_kwh"] = round(gv, 1) if gv > 0 else None
    result["autarkie_prozent"] = round(ev / gv * 100, 1) if gv > 0 else None

    # Finanzen mit historisch korrektem Tarif berechnen
    try:
        stichtag_vj = date_type(vj, monat, 1)
        tarife_vj = await lade_tarife_fuer_anlage(db, anlage_id, target_date=stichtag_vj)
        tarif_vj = tarife_vj.get("allgemein")
        if tarif_vj:
            netz_preis = tarif_vj.netzbezug_arbeitspreis_cent_kwh or NETZBEZUG_DEFAULT_CENT
            einsp_preis = tarif_vj.einspeiseverguetung_cent_kwh or EINSPEISEVERGUETUNG_DEFAULT_CENT
            grundpreis = tarif_vj.grundpreis_euro_monat or 0
            # Flexibler Tarif überschreibt wenn vorhanden
            if result.get("netzbezug_durchschnittspreis_cent"):
                netz_preis = result["netzbezug_durchschnittspreis_cent"]
            if einsp > 0:
                # §51 EEG: Einspeisung in Negativpreis-Stunden ist seit
                # Solarpaket I unvergütet. Wenn das Tages-Aggregat fehlt
                # (Anwender ohne Strompreis-Sensor), greift die alte
                # Berechnung unverändert (None → kein Abzug).
                m_neg = await get_neg_preis_einspeisung_monat(db, anlage_id, vj, monat)
                m_erloes = einspeise_erloes_euro(
                    einspeisung_kwh=einsp,
                    neg_preis_kwh=m_neg,
                    verguetung_ct_kwh=einsp_preis,
                )
                result["einspeise_erloes_euro"] = round(m_erloes.erloes_euro, 2)
            if netz > 0:
                result["netzbezug_kosten_euro"] = round(
                    berechne_netzbezug_kosten(netz, netz_preis, grundpreis), 2
                )
            if ev > 0:
                result["ev_ersparnis_euro"] = round(ev * netz_preis / 100, 2)
            einspeise_e = result.get("einspeise_erloes_euro", 0) or 0
            ev_e = result.get("ev_ersparnis_euro", 0) or 0
            netz_k = result.get("netzbezug_kosten_euro", 0) or 0
            if einspeise_e or ev_e:
                result["gesamtnettoertrag_euro"] = round(einspeise_e + ev_e - netz_k, 2)
    except Exception:
        logger.warning("Vorjahr-Finanzen konnten nicht berechnet werden")

    return result


async def _load_soll_pv(anlage_id: int, monat: int, db: AsyncSession) -> Optional[float]:
    """Lädt PVGIS SOLL-Wert für den Monat."""
    result = await db.execute(
        select(PVGISMonatsprognose)
        .join(PVGISPrognose)
        .where(
            PVGISPrognose.anlage_id == anlage_id,
            PVGISPrognose.ist_aktiv == True,
            PVGISMonatsprognose.monat == monat,
        )
    )
    prognosen = result.scalars().all()
    if not prognosen:
        return None
    return round(sum(p.ertrag_kwh for p in prognosen), 1)


# =============================================================================
# Endpoint
# =============================================================================

def _baue_investition_financial(
    inv,
    data: dict,
    *,
    netz_p: float,
    einsp_p: float,
    wp_p: float,
    wb_p: float,
    monats_gaspreis: Optional[float],
    monats_benzinpreis: Optional[float],
    emob_pool_attr,
) -> Optional[InvestitionFinancialDetail]:
    """Baut das T-Konto-Detail (InvestitionFinancialDetail) EINER Investition.

    Extrahiert aus get_aktueller_monat (Spur A, Refactoring-Plan). Bewusst IM
    Route-Modul statt core/berechnungen: erzeugt deutsche Anzeige-Strings
    (label/formel/berechnung) und das Pydantic-Response-Modell — Präsentations-
    Finanzlogik, kein Aggregat-Σ. Verhaltensneutral 1:1 übernommen.

    Gibt None zurück, wenn die Investition inaktiv ist ODER keinerlei finanzielle
    Relevanz hat (Inclusion-Guard: weder Betriebskosten noch Ersparnis/Erlös/
    sonstige Positionen). Preis-/Pool-Kontext wird vom Aufrufer einmal aufgelöst
    und übergeben.
    """
    if not inv.aktiv:
        return None
    bk_monat = round((inv.betriebskosten_jahr or 0) / 12, 2)
    # Sonstige Erträge/Ausgaben (z.B. AG-Vergütung Dienstwagen, THG-Quote)
    # für JEDE Investition evaluieren — typ-unabhängig, auch wenn der
    # Wirtschaftlichkeits-Zweig unten übersprungen wird (z.B. ist_dienstlich).
    inv_sonstige = berechne_sonstige_summen(data)
    inv_sonstige_ertraege = round(inv_sonstige["ertraege_euro"], 2)
    inv_sonstige_ausgaben = round(inv_sonstige["ausgaben_euro"], 2)
    inv_erloes: Optional[float] = None
    inv_ersparnis: Optional[float] = None
    inv_label = ""
    inv_formel: Optional[str] = None
    inv_berechnung: Optional[str] = None

    if inv.typ == "balkonkraftwerk":
        ev_kwh = data.get("eigenverbrauch_kwh") or data.get("pv_erzeugung_kwh")
        einsp_kwh = data.get("einspeisung_kwh")
        if ev_kwh:
            inv_ersparnis = round(ev_kwh * netz_p / 100, 2)
            inv_label = "Eigenverbrauch-Ersparnis"
            inv_formel = "BKW-Eigenverbrauch × Netzbezugspreis"
            inv_berechnung = f"{ev_kwh:.1f} kWh × {netz_p:.2f} ct/kWh"
        if einsp_kwh and einsp_kwh > 0:
            inv_erloes = round(einsp_kwh * einsp_p / 100, 2)

    elif inv.typ == "speicher":
        entl_kwh = data.get("entladung_kwh")
        if entl_kwh and entl_kwh > 0:
            inv_ersparnis = round(entl_kwh * netz_p / 100, 2)
            inv_label = "Entladung-Ersparnis"
            inv_formel = "Speicher-Entladung × Netzbezugspreis"
            inv_berechnung = f"{entl_kwh:.1f} kWh × {netz_p:.2f} ct/kWh"

    elif inv.typ == "waermepumpe":
        waerme = get_wp_heizenergie_kwh(data)
        ww = data.get("warmwasser_kwh", 0) or 0
        strom = get_wp_strom_kwh(data, inv.parameter) or None
        waerme_total = (waerme or 0) + (ww or 0)
        if waerme_total > 0 and strom is not None:
            wp_result = berechne_wp_ersparnis(
                wp_waerme_kwh=waerme_total,
                wp_strom_kwh=strom,
                wp_strompreis_cent=wp_p,
                wp_parameter=inv.parameter,
                monats_gaspreis_cent=monats_gaspreis,
            )
            inv_ersparnis = round(wp_result.ersparnis_euro, 2)
            inv_label = "Ersparnis vs. Gas"
            inv_formel = "(Wärme ÷ Wirkungsgrad × Gaspreis) − Strom × WP-Strompreis"
            inv_berechnung = (
                f"{waerme_total:.1f} kWh / {wp_result.verwendeter_wirkungsgrad:.2f} "
                f"× {wp_result.verwendeter_gaspreis_cent:.1f} ct − "
                f"{strom:.1f} kWh × {wp_p:.2f} ct"
            )

    elif inv.typ in ("e-auto", "wallbox") and not ist_dienstlich(inv):
        km = data.get("km_gefahren")
        ladung = get_eauto_ladung_kwh(data) or None
        # #262: SoT-Helper konsolidiert den vorherigen Inline-Fallback
        # (netz = ladung_netz ?? total − pv) — gleiche Semantik, gleiche
        # Drift-Quelle wie in den anderen Read-Sites.
        ladung_pv, netz_kwh = get_emob_pv_netz_kwh(data, total_kwh=ladung or 0)
        ladung_pv = ladung_pv or None
        if km and km > 0:
            extern_euro = data.get("ladung_extern_euro", 0) or 0
            # Wallbox-Pool-Override für evcc-Setups (Ladedaten auf der
            # Wallbox-IMD, nur km am E-Auto). Selbes Pattern wie im
            # EAutoDashboard.
            if emob_pool_attr.use_wb_pool and inv.typ == "e-auto":
                share = attribute_emob_pool_by_km(emob_pool_attr, km)
                if share.netz_kwh + share.pv_kwh > 0:
                    netz_kwh = share.netz_kwh
                    ladung_pv = share.pv_kwh or None
                    extern_euro = share.extern_euro
            eauto_result = berechne_eauto_ersparnis(
                km_gefahren=km,
                ladung_netz_kwh=max(0, netz_kwh),
                ladung_extern_euro=extern_euro,
                wallbox_strompreis_cent=wb_p,
                eauto_parameter=inv.parameter,
                monats_benzinpreis_euro=monats_benzinpreis,
            )
            inv_ersparnis = round(eauto_result.ersparnis_euro, 2)
            inv_label = "Ersparnis vs. Verbrenner"
            inv_formel = "(km × Verbrauch × Benzinpreis) − Netzladung × Strompreis"
            inv_berechnung = (
                f"{km:.0f} km × {eauto_result.verwendeter_verbrauch_l_100km:.1f} L/100km × "
                f"{eauto_result.verwendeter_benzinpreis_euro:.2f} €"
            )
        elif inv.typ == "wallbox" and ladung_pv and ladung_pv > 0:
            inv_ersparnis = round(ladung_pv * wb_p / 100, 2)
            inv_label = "PV-Ladung-Ersparnis"
            inv_formel = "PV-Ladung × Netzbezugspreis"
            inv_berechnung = f"{ladung_pv:.1f} kWh × {wb_p:.2f} ct/kWh"

    elif inv.typ == "sonstiges":
        ev_kwh = data.get("eigenverbrauch_kwh")
        einsp_kwh = data.get("einspeisung_kwh")
        if ev_kwh and ev_kwh > 0:
            inv_ersparnis = round(ev_kwh * netz_p / 100, 2)
            inv_label = "Eigenverbrauch-Ersparnis"
            inv_formel = "Eigenverbrauch × Netzbezugspreis"
            inv_berechnung = f"{ev_kwh:.1f} kWh × {netz_p:.2f} ct/kWh"
        if einsp_kwh and einsp_kwh > 0:
            inv_erloes = round(einsp_kwh * einsp_p / 100, 2)

    if (
        bk_monat > 0
        or inv_ersparnis is not None
        or inv_erloes is not None
        or inv_sonstige_ertraege > 0
        or inv_sonstige_ausgaben > 0
    ):
        return InvestitionFinancialDetail(
            investition_id=inv.id,
            bezeichnung=inv.bezeichnung,
            typ=inv.typ,
            betriebskosten_monat_euro=bk_monat,
            erloes_euro=inv_erloes,
            ersparnis_euro=inv_ersparnis,
            ersparnis_label=inv_label,
            formel=inv_formel,
            berechnung=inv_berechnung,
            sonstige_ertraege_euro=inv_sonstige_ertraege,
            sonstige_ausgaben_euro=inv_sonstige_ausgaben,
        )
    return None


@router.get("/{anlage_id}", response_model=AktuellerMonatResponse)
async def get_aktueller_monat(
    anlage_id: int,
    jahr: Optional[int] = None,
    monat: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Übersicht eines Monats mit Daten aus allen verfügbaren Quellen.

    Datenquellen-Priorität (höchste überschreibt niedrigere):
    1. Gespeicherte Monatsdaten (85%) — DB
    2. Connector (90%) — Geräte-Snapshot-Delta
    3. MQTT-Inbound (91%) — Energy-Topics aus Smarthome (nur aktueller Monat)
    4. HA Statistics (92%) — Recorder-DB
    """
    # Anlage mit Investitionen laden
    result = await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    now = datetime.now()
    if jahr is None:
        jahr = now.year
    if monat is None:
        monat = now.month
    ist_aktueller_monat = (jahr == now.year and monat == now.month)
    investitionen = [i for i in anlage.investitionen if i.aktiv]

    # ── Daten sammeln (I/O) — Zusammenführung nach Präzedenz im SoT-Helper ──
    # Sammeln bleibt hier (DB/HA-Zugriff); die Merge-/Override-Regeln leben in
    # core/berechnungen/datenquellen.merge_datenquellen (ADR-001) — eine Stelle,
    # symmetrie-getestet, ohne Drift zwischen den Quellen-Zweigen.
    # MQTT wird für abgeschlossene Monate gar nicht erst gesammelt.
    saved = await _collect_saved_data(anlage_id, jahr, monat, investitionen, db)
    connector = await _collect_connector_data(anlage, jahr, monat)
    mqtt_energy = await _collect_mqtt_inbound_data(anlage, investitionen) if ist_aktueller_monat else {}
    ha_stats = await _collect_ha_statistics_data(anlage, jahr, monat)

    resolved: dict[str, tuple[float, DatenquelleInfo]] = merge_datenquellen(
        saved=saved,
        connector=connector,
        mqtt_energy=mqtt_energy,
        ha_stats=ha_stats,
        ist_aktueller_monat=ist_aktueller_monat,
    )

    # ── Investitions-Felder in Top-Level aggregieren (typabhängig) ──
    # Nur aggregieren wenn kein direkter Top-Level-Wert existiert (sonst Doppelzählung!)
    # Direkte Werte kommen z.B. aus gespeicherten Aggregaten oder MQTT pv_gesamt_kwh.
    typ_aggregation: dict[str, dict[str, str]] = {
        "pv-module": {"pv_erzeugung_kwh": "pv_erzeugung_kwh"},
        "speicher": {"ladung_kwh": "speicher_ladung_kwh", "entladung_kwh": "speicher_entladung_kwh"},
        "waermepumpe": {
            "stromverbrauch_kwh": "wp_strom_kwh",
            "strom_heizen_kwh": "wp_strom_kwh",
            "strom_warmwasser_kwh": "wp_strom_kwh",
            "heizenergie_kwh": "wp_waerme_kwh",
            "warmwasser_kwh": "wp_waerme_kwh",
        },
        # E-Auto und Wallbox NICHT hier — sie messen denselben Stromfluss aus
        # zwei Perspektiven (Vehicle vs. Loadpoint). Aufsummieren über beide
        # Typen würde Pool-Doppelzählung produzieren (Joachim/Gernot
        # 2026-05-02). Aggregation passiert unten als max-Pool nach dem
        # Standard-Loop, identisch zu `_collect_saved_data` (Commit 92d522a8)
        # und `cockpit/uebersicht.py`.
        "balkonkraftwerk": {"pv_erzeugung_kwh": "bkw_erzeugung_kwh"},
    }

    # Top-Level-Felder die bereits direkt von Collectoren gesetzt wurden
    # → nicht nochmal aus Einzel-Investitionen aufaddieren
    direct_fields = set(resolved.keys())

    def _aggregate(top_level_feld: str, inv_key: str) -> None:
        if inv_key not in resolved:
            return
        if top_level_feld in direct_fields:
            return  # Bereits direkt gesetzt → nicht doppelt zählen
        val = resolved[inv_key][0]
        quelle_info = resolved[inv_key][1]
        if top_level_feld not in resolved:
            resolved[top_level_feld] = (val, quelle_info)
        else:
            resolved[top_level_feld] = (resolved[top_level_feld][0] + val, quelle_info)

    # #239 detLAN-Folge: HA-Statistics-/MQTT-Sensoren liefern Werte auch in
    # Monaten vor Anschaffung der EEDC-Investition (Sensor existierte in HA
    # schon vorher). Vor-Anschaffungs-/Nach-Stilllegungs-Monate hier
    # rausfiltern, sonst tauchen WP-Werte (z.B. 145 kWh Strom für März bei
    # Anschaffungsdatum April) im Monatsbericht auf.
    for inv in investitionen:
        if not inv.ist_aktiv_im_monat(jahr, monat):
            continue
        agg_map = typ_aggregation.get(inv.typ, {})
        for inv_suffix, top_level_feld in agg_map.items():
            _aggregate(top_level_feld, f"inv_{inv.id}_{inv_suffix}")

    # ── E-Mobilität: max-Pool über E-Auto + Wallbox ──
    # Dienstliche Fahrzeuge früh herausfiltern (sie zählen separat in
    # `dienstlich_ladekosten`, nicht in der Haus-Energiebilanz). Pro Feld die
    # größere Quelle gewinnt; PV ≤ Gesamt erzwingen. Identische Logik wie in
    # `_collect_saved_data` (Commit 92d522a8) und `cockpit/uebersicht.py`.
    if "emob_ladung_kwh" not in direct_fields:
        eauto_ladung = 0.0
        eauto_km = 0.0
        eauto_extern_euro = 0.0
        wb_ladung = 0.0
        wb_extern_euro = 0.0
        emob_quelle: Optional[tuple] = None
        for inv in investitionen:
            if ist_dienstlich(inv):
                continue
            # #239 detLAN-Folge: HA-Statistics-Werte aus vor-Anschaffungs-
            # Monaten nicht in den Monatsbericht-Pool aggregieren.
            if not inv.ist_aktiv_im_monat(jahr, monat):
                continue
            if inv.typ == "e-auto":
                for suffix in ("ladung_kwh", "verbrauch_kwh"):
                    entry = resolved.get(f"inv_{inv.id}_{suffix}")
                    if entry:
                        eauto_ladung += entry[0]
                        emob_quelle = entry[1]
                        break
                km_entry = resolved.get(f"inv_{inv.id}_km_gefahren")
                if km_entry:
                    eauto_km += km_entry[0]
                    emob_quelle = km_entry[1]
                extern_entry = resolved.get(f"inv_{inv.id}_ladung_extern_euro")
                if extern_entry:
                    eauto_extern_euro += extern_entry[0]
            elif inv.typ == "wallbox":
                entry = resolved.get(f"inv_{inv.id}_ladung_kwh")
                if entry:
                    wb_ladung += entry[0]
                    emob_quelle = entry[1]
                extern_entry = resolved.get(f"inv_{inv.id}_ladung_extern_euro")
                if extern_entry:
                    wb_extern_euro += extern_entry[0]
        emob_ladung = max(eauto_ladung, wb_ladung)
        if emob_ladung > 0 and emob_quelle is not None:
            resolved["emob_ladung_kwh"] = (emob_ladung, emob_quelle)
        if "emob_km" not in direct_fields and eauto_km > 0 and emob_quelle is not None:
            resolved["emob_km"] = (eauto_km, emob_quelle)
        # #260: externe Lade-Kosten poolen wie ladung_kwh
        if "emob_ladung_extern_euro" not in direct_fields:
            emob_extern_euro = max(eauto_extern_euro, wb_extern_euro)
            if emob_extern_euro > 0 and emob_quelle is not None:
                resolved["emob_ladung_extern_euro"] = (emob_extern_euro, emob_quelle)

    # ── Werte extrahieren ──
    def get_val(feld: str) -> Optional[float]:
        entry = resolved.get(feld)
        return round(entry[0], 2) if entry else None

    pv = get_val("pv_erzeugung_kwh")
    einspeisung = get_val("einspeisung_kwh")
    netzbezug = get_val("netzbezug_kwh")
    speicher_ladung = get_val("speicher_ladung_kwh")
    speicher_entladung = get_val("speicher_entladung_kwh")

    # Sonstige Erzeuger (z. B. BHKW) speisen hinter den Hauszähler → ihre Erzeugung
    # gehört in die Netzpunkt-Bilanz, sonst drückt der gemessene Einspeise-Zähler
    # die PV-Bilanz still zu niedrig (Konzept Sonstiger Erzeuger 2026-06-22).
    # `pv` (Anzeige + PV-Kennzahlen) bleibt rein. Der Wert wird in
    # `_collect_saved_data` aktiv-/anschaffungsdatum-gefiltert aggregiert
    # ([[feedback_anschaffungsdatum_grenze]]).
    sonstiges_erz_bilanz = get_val("sonstiges_erzeugung_kwh") or 0
    erzeugung_bilanz = erzeugung_hinter_zaehler_kwh(pv, sonstiges_erz_bilanz)

    # ── Berechnete Werte ──
    eigenverbrauch = None
    direktverbrauch = None
    gesamtverbrauch = None
    autarkie = None
    ev_quote = None

    if (pv is not None or sonstiges_erz_bilanz > 0) and einspeisung is not None:
        ladung = speicher_ladung or 0
        entladung = speicher_entladung or 0
        direktverbrauch = round(max(0, erzeugung_bilanz - einspeisung - ladung), 2)
        eigenverbrauch = round(direktverbrauch + entladung, 2)

        if netzbezug is not None:
            gesamtverbrauch = round(eigenverbrauch + netzbezug, 2)
            if gesamtverbrauch > 0:
                autarkie = round(autarkie_prozent(eigenverbrauch, gesamtverbrauch), 1)

        if erzeugung_bilanz > 0:
            ev_quote = round(eigenverbrauchsquote_prozent(eigenverbrauch, erzeugung_bilanz), 1)

    # ── Finanzen ──
    einspeise_erloes = None
    netzbezug_kosten = None
    ev_ersparnis = None
    netto_ertrag = None
    netzbezug_preis_cent = None
    einspeise_cent = None

    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein_tarif = tarife.get("allgemein")
    if allgemein_tarif:
        netzbezug_preis_cent = allgemein_tarif.netzbezug_arbeitspreis_cent_kwh if allgemein_tarif.netzbezug_arbeitspreis_cent_kwh is not None else NETZBEZUG_DEFAULT_CENT
        einspeise_cent = allgemein_tarif.einspeiseverguetung_cent_kwh if allgemein_tarif.einspeiseverguetung_cent_kwh is not None else EINSPEISEVERGUETUNG_DEFAULT_CENT
        # Flexibler Durchschnittspreis überschreibt Netzbezugspreis für Finanzberechnung
        # (wird nach dem Monatsdaten-Laden gesetzt, hier Platzhalter für spätere Überschreibung)

        if einspeisung is not None:
            # §51 EEG: siehe `_load_vorjahr` für Begründung.
            m_neg = await get_neg_preis_einspeisung_monat(db, anlage_id, jahr, monat)
            m_erloes = einspeise_erloes_euro(
                einspeisung_kwh=einspeisung,
                neg_preis_kwh=m_neg,
                verguetung_ct_kwh=einspeise_cent,
            )
            einspeise_erloes = round(m_erloes.erloes_euro, 2)
        if netzbezug is not None:
            grundpreis = allgemein_tarif.grundpreis_euro_monat or 0
            netzbezug_kosten = round(
                berechne_netzbezug_kosten(netzbezug, netzbezug_preis_cent, grundpreis), 2
            )
        if eigenverbrauch is not None:
            ev_ersparnis = round(eigenverbrauch * netzbezug_preis_cent / 100, 2)

        if einspeise_erloes is not None and ev_ersparnis is not None:
            netto_ertrag = round(einspeise_erloes + ev_ersparnis, 2)

    # ── Komponenten-Ersparnis ──
    wp_ersparnis = None
    emob_ersparnis = None

    # Monats-Gaspreis (für WP-Ersparnis hier + Per-Investition-Block unten).
    # Drift-Audit Domäne A1 / Issue #178: ohne diesen Override fiel der Code
    # auf hartcodierte 10ct zurück.
    md_result = await db.execute(
        select(Monatsdaten).where(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == jahr,
            Monatsdaten.monat == monat,
        )
    )
    md_for_gas = md_result.scalar_one_or_none()
    monats_gaspreis = md_for_gas.gaspreis_cent_kwh if md_for_gas else None
    monats_benzinpreis = md_for_gas.kraftstoffpreis_euro if md_for_gas else None

    wp_waerme = get_val("wp_waerme_kwh")
    wp_strom = get_val("wp_strom_kwh")
    if wp_waerme is not None and wp_strom is not None and allgemein_tarif:
        wp_tarif = tarife.get("waermepumpe")
        wp_preis_cent = (
            wp_tarif.netzbezug_arbeitspreis_cent_kwh
            if wp_tarif and wp_tarif.netzbezug_arbeitspreis_cent_kwh is not None
            else netzbezug_preis_cent
        )
        wp_invs = [i for i in investitionen if i.typ == "waermepumpe"]
        wp_ref_parameter = wp_invs[0].parameter if wp_invs else None

        wp_ersparnis_result = berechne_wp_ersparnis(
            wp_waerme_kwh=wp_waerme,
            wp_strom_kwh=wp_strom,
            wp_strompreis_cent=wp_preis_cent,
            wp_parameter=wp_ref_parameter,
            monats_gaspreis_cent=monats_gaspreis,
        )
        wp_ersparnis = round(wp_ersparnis_result.ersparnis_euro, 2)

    emob_ladung = get_val("emob_ladung_kwh")
    emob_km = get_val("emob_km")
    emob_pv_ladung = get_val("emob_pv_ladung_kwh") or 0.0
    emob_extern_euro = get_val("emob_ladung_extern_euro") or 0.0
    if emob_km is not None and emob_km > 0 and allgemein_tarif:
        wallbox_tarif = tarife.get("wallbox")
        wallbox_preis_cent = (
            wallbox_tarif.netzbezug_arbeitspreis_cent_kwh
            if wallbox_tarif and wallbox_tarif.netzbezug_arbeitspreis_cent_kwh is not None
            else netzbezug_preis_cent
        )
        emob_result = berechne_eauto_ersparnis(
            km_gefahren=emob_km,
            ladung_netz_kwh=(emob_ladung or 0) - emob_pv_ladung,
            ladung_extern_euro=emob_extern_euro,
            wallbox_strompreis_cent=wallbox_preis_cent,
            eauto_parameter=pick_emob_ref_parameter(investitionen),
            monats_benzinpreis_euro=monats_benzinpreis,
        )
        emob_ersparnis = round(emob_result.ersparnis_euro, 2)

    # BKW-Ersparnis wird NICHT separat ausgewiesen — BKW-Erzeugung fließt in
    # pv_erzeugung_total und damit in eigenverbrauch ein → bereits in ev_ersparnis enthalten.

    # ── Betriebskosten anteilig ──
    betriebskosten_anteilig = None
    bk_summe = sum(
        (i.betriebskosten_jahr or 0) / 12
        for i in investitionen
        if (i.betriebskosten_jahr or 0) > 0
    )
    if bk_summe > 0:
        betriebskosten_anteilig = round(bk_summe, 2)

    # ── Sonstige Erträge / Ausgaben über alle Investitionen aggregieren ──
    # Pro Investition gehen Detail-Zeilen ins T-Konto (siehe
    # investitionen_financials weiter unten). Aggregate als eigenes Feld
    # exponiert, damit das Frontend Monatsergebnis-Korrekturen sauber rechnen
    # kann ohne `gesamtnettoertrag` zu verschieben (verhindert Drift mit
    # bestehender `sonderkosten`-Logik in MonatsabschlussView).
    sonstige_inv_imd_result = await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id.in_([i.id for i in investitionen]),
            InvestitionMonatsdaten.jahr == jahr,
            InvestitionMonatsdaten.monat == monat,
        )
    ) if investitionen else None
    # Sonstige Erträge/Ausgaben des Monats — zentraler SoT-Helper, identisch zur
    # Komponenten-Zeitreihe (Symmetrie: test_sonstige_readsite_symmetrie). Gleiche
    # Sichtbarkeitsregel wie überall: `investitionen` ist bereits aktiv-gefiltert
    # (aktiv=False = wie gelöscht), zusätzlich nur innerhalb der Laufzeit
    # Anschaffung→Stilllegung (detLAN [[feedback_anschaffungsdatum_grenze]],
    # #236/#308) — Finanzpositionen sind keine Ausnahme.
    _inv_by_id_s = {i.id: i for i in investitionen}
    _sonstige_rows = [
        imd for imd in (sonstige_inv_imd_result.scalars().all()
                        if sonstige_inv_imd_result is not None else [])
        if _inv_by_id_s[imd.investition_id].ist_aktiv_im_monat(imd.jahr, imd.monat)
    ]
    _sonstige_agg = aggregiere_sonstige_je_monat(_sonstige_rows).get((jahr, monat), {})
    sonstige_ertraege_total = round(_sonstige_agg.get("ertraege_euro", 0.0), 2)
    sonstige_ausgaben_total = round(_sonstige_agg.get("ausgaben_euro", 0.0), 2)
    sonstige_netto_total = round(sonstige_ertraege_total - sonstige_ausgaben_total, 2)

    # ── Gesamtnettoertrag = Erlöse + Einsparungen − Kosten ──
    # Sonstige Positionen werden NICHT eingerechnet — sie werden separat im
    # T-Konto gerendert und im Monatsergebnis (nettoNachAllem) addiert.
    gesamtnettoertrag = None
    if einspeise_erloes is not None and ev_ersparnis is not None and netzbezug_kosten is not None:
        gesamtnettoertrag = round(
            einspeise_erloes + ev_ersparnis
            + (wp_ersparnis or 0)
            + (emob_ersparnis or 0)
            - netzbezug_kosten,
            2,
        )

    # ── Komponenten-Detail aus gespeicherten InvestitionMonatsdaten ──
    # Batch-Query: Alle InvestitionMonatsdaten für diesen Monat auf einmal laden
    all_inv_ids = [i.id for i in investitionen]
    imd_by_inv: dict[int, list] = {}
    if all_inv_ids:
        all_imd_result = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(all_inv_ids),
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            )
        )
        for imd in all_imd_result.scalars().all():
            imd_by_inv.setdefault(imd.investition_id, []).append(imd)

    def get_imd_for_invs(invs: list) -> list:
        """Sammelt InvestitionMonatsdaten für eine Liste von Investitionen."""
        result = []
        for inv in invs:
            result.extend(imd_by_inv.get(inv.id, []))
        return result

    # Speicher: Kapazität, Arbitrage-Ladung, Wirkungsgrad, Vollzyklen
    speicher_ladung_netz = None
    speicher_wirkungsgrad = None
    speicher_vollzyklen = None
    speicher_kapazitaet = None

    speicher_invs = [i for i in investitionen if i.typ == "speicher"]
    speicher_soc_drift_flag = False
    speicher_eff_ladepreis = None
    speicher_eff_ladepreis_quelle = None
    if speicher_invs:
        # Kapazität aus parameter
        kap_sum = sum((i.parameter or {}).get("kapazitaet_kwh", 0) or 0 for i in speicher_invs)
        if kap_sum > 0:
            speicher_kapazitaet = round(kap_sum, 1)
        nutzbare_kapazitaet = sum(
            (i.parameter or {}).get("nutzbare_kapazitaet_kwh") or (i.parameter or {}).get("kapazitaet_kwh", 0) or 0
            for i in speicher_invs
        )

        # Arbitrage-Ladung aus gespeicherten Daten
        ladung_netz_total = 0.0
        for imd in get_imd_for_invs(speicher_invs):
            data = imd.verbrauch_daten or {}
            ladung_netz_total += data.get("ladung_netz_kwh", 0) or 0
        if ladung_netz_total > 0:
            speicher_ladung_netz = round(ladung_netz_total, 2)

        # Wirkungsgrad und Vollzyklen
        sl = speicher_ladung or 0
        se = speicher_entladung or 0

        # Etappe C2 (#264): SoC-Drift über den Monat erkennen, bevor der naive
        # Quotient ausgewiesen wird. Maintainer-Vorgabe: Schwelle
        # |soc_ende − soc_start| > 20 pp (≈ ein voller Lade-/Entladezyklus
        # über die Monatsgrenze hinaus), nicht relativ zur Ladung.
        if sl > 0:
            from calendar import monthrange
            from backend.core.berechnungen.speicher_wirtschaftlichkeit import (
                ist_soc_drift_signifikant,
            )
            from backend.services.speicher_wirtschaftlichkeit import (
                _lese_soc_am_periodenrand,
            )
            try:
                monat_start = date(jahr, monat, 1)
                monat_ende = date(jahr, monat, monthrange(jahr, monat)[1])
                soc_start = await _lese_soc_am_periodenrand(
                    db, anlage_id=anlage_id, datum=monat_start, richtung="erste",
                )
                soc_ende = await _lese_soc_am_periodenrand(
                    db, anlage_id=anlage_id, datum=monat_ende, richtung="letzte",
                )
                if soc_start is not None and soc_ende is not None:
                    speicher_soc_drift_flag = ist_soc_drift_signifikant(
                        soc_start_prozent=soc_start,
                        soc_ende_prozent=soc_ende,
                    )
            except Exception as e:  # noqa: BLE001
                # SoC-Lookup darf den Endpoint nicht killen — bei Fehler
                # bleibt das Drift-Flag False und der Monats-η wird angezeigt.
                logger.warning(
                    "aktueller_monat: SoC-Drift-Lookup fehlgeschlagen "
                    "(anlage=%s, %s/%s): %s", anlage_id, jahr, monat, e,
                )

        # Monats-η nur ausweisen, wenn SoC-Drift nicht signifikant ist
        if sl > 0 and se > 0 and not speicher_soc_drift_flag:
            speicher_wirkungsgrad = round(se / sl * 100, 1)
        if sl > 0 and speicher_kapazitaet and speicher_kapazitaet > 0:
            speicher_vollzyklen = round(sl / speicher_kapazitaet, 2)

        # Etappe C1+C4: stundengewichteter effektiver Netz-Ladepreis für den Monat.
        # Helper liefert immer ein Ergebnis (auch bei dünner Datenlage) — UI
        # entscheidet anhand der `quelle`, ob KPI anzeigen oder nur Param.
        if speicher_ladung_netz is not None and speicher_ladung_netz > 0:
            from calendar import monthrange as _monthrange
            from backend.services.speicher_wirtschaftlichkeit import (
                berechne_effektiver_ladepreis as _berechne_eff_ladepreis,
            )
            try:
                _ende = date(jahr, monat, _monthrange(jahr, monat)[1])
                eff = await _berechne_eff_ladepreis(
                    db, anlage_id=anlage_id, von=date(jahr, monat, 1), bis=_ende,
                )
                # Wert nur zurückgeben, wenn belastbar (dyn-tarif/boersenpreis)
                # ODER zumindest mit Diagnose (datenbasis-zu-duenn). Bei
                # `keine-netzladung`/`keine-tep-daten` bleibt das Feld None.
                if eff.effektiver_ladepreis_cent is not None:
                    speicher_eff_ladepreis = round(eff.effektiver_ladepreis_cent, 2)
                speicher_eff_ladepreis_quelle = eff.quelle
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "aktueller_monat: effektiver-Ladepreis-Lookup fehlgeschlagen "
                    "(anlage=%s, %s/%s): %s", anlage_id, jahr, monat, e,
                )

    # WP: Heizung/Warmwasser-Split (Wärme + bei getrennter Strommessung auch Strom, #191)
    wp_heizung = None
    wp_warmwasser = None
    wp_strom_heizen = None
    wp_strom_warmwasser = None
    wp_invs = [i for i in investitionen if i.typ == "waermepumpe"]
    if wp_invs:
        h_total = 0.0
        ww_total = 0.0
        sh_total = 0.0
        sww_total = 0.0
        any_getrennt = False
        for imd in get_imd_for_invs(wp_invs):
            data = imd.verbrauch_daten or {}
            inv = next((i for i in wp_invs if i.id == imd.investition_id), None)
            h_total += get_wp_heizenergie_kwh(data)
            ww_total += data.get("warmwasser_kwh", 0) or 0
            if inv and (inv.parameter or {}).get("getrennte_strommessung"):
                any_getrennt = True
                sh_total += data.get("strom_heizen_kwh", 0) or 0
                sww_total += data.get("strom_warmwasser_kwh", 0) or 0
        if h_total > 0:
            wp_heizung = round(h_total, 2)
        if ww_total > 0:
            wp_warmwasser = round(ww_total, 2)
        if any_getrennt:
            # Auch 0-Werte zurückgeben, damit Frontend "getrennt erfasst, aktuell 0"
            # vs. "gar nicht getrennt erfasst" unterscheiden kann.
            wp_strom_heizen = round(sh_total, 2)
            wp_strom_warmwasser = round(sww_total, 2)

    # E-Mobilität: PV/Netz/Extern-Split + V2H
    emob_pv = get_val("emob_pv_ladung_kwh")
    emob_ladung_netz = None
    emob_ladung_extern = None
    emob_v2h = None

    emob_invs = [i for i in investitionen if i.typ in ("e-auto", "wallbox") and not ist_dienstlich(i)]
    if emob_invs:
        netz_total = 0.0
        extern_total = 0.0
        v2h_total = 0.0
        for imd in get_imd_for_invs(emob_invs):
            data = imd.verbrauch_daten or {}
            # #262: Netz via SoT-Helper — bei evcc-Imports wird aus Total − PV
            # abgeleitet, wenn `ladung_netz_kwh` nicht als eigener Key existiert.
            _, netz = get_emob_pv_netz_kwh(data)
            netz_total += netz
            extern_total += data.get("ladung_extern_kwh", 0) or 0
            v2h_total += data.get("v2h_entladung_kwh", 0) or 0
        if netz_total > 0:
            emob_ladung_netz = round(netz_total, 2)
        if extern_total > 0:
            emob_ladung_extern = round(extern_total, 2)
        if v2h_total > 0:
            emob_v2h = round(v2h_total, 2)

    # BKW: Eigenverbrauch
    bkw_eigenverbrauch = None
    bkw_invs = [i for i in investitionen if i.typ == "balkonkraftwerk"]
    if bkw_invs:
        ev_total = 0.0
        for imd in get_imd_for_invs(bkw_invs):
            data = imd.verbrauch_daten or {}
            ev_total += data.get("eigenverbrauch_kwh", 0) or 0
        if ev_total > 0:
            bkw_eigenverbrauch = round(ev_total, 2)

    # Sonstiges: erzeuger + verbraucher aggregieren
    sonstiges_erzeugung = None
    sonstiges_eigenverbrauch = None
    sonstiges_einspeisung = None
    sonstiges_verbrauch = None
    sonstiges_bezug_pv = None
    sonstiges_bezug_netz = None

    sonstiges_invs = [i for i in investitionen if i.typ == "sonstiges"]
    sonstiges_geraete: list[SonstigesGeraet] = []
    if sonstiges_invs:
        se_total = 0.0
        sev_total = 0.0
        sei_total = 0.0
        sv_total = 0.0
        sbpv_total = 0.0
        sbnetz_total = 0.0
        # Pro-Gerät-Akkumulator (für die Sonder-Darstellung: Werte je Gerät).
        acc: dict[int, dict[str, float]] = {}
        for imd in get_imd_for_invs(sonstiges_invs):
            data = imd.verbrauch_daten or {}
            erz = data.get("erzeugung_kwh", 0) or 0
            eig = data.get("eigenverbrauch_kwh", 0) or 0
            ein = data.get("einspeisung_kwh", 0) or 0
            vrb = get_sonstiges_verbrauch_kwh(data)
            bpv = data.get("bezug_pv_kwh", 0) or 0
            bnz = data.get("bezug_netz_kwh", 0) or 0
            se_total += erz; sev_total += eig; sei_total += ein
            sv_total += vrb; sbpv_total += bpv; sbnetz_total += bnz
            g = acc.setdefault(imd.investition_id, {"erz": 0.0, "eig": 0.0, "ein": 0.0, "vrb": 0.0, "bpv": 0.0, "bnz": 0.0})
            g["erz"] += erz; g["eig"] += eig; g["ein"] += ein
            g["vrb"] += vrb; g["bpv"] += bpv; g["bnz"] += bnz
        if se_total > 0:   sonstiges_erzeugung    = round(se_total, 2)
        if sev_total > 0:  sonstiges_eigenverbrauch = round(sev_total, 2)
        if sei_total > 0:  sonstiges_einspeisung  = round(sei_total, 2)
        if sv_total > 0:   sonstiges_verbrauch    = round(sv_total, 2)
        if sbpv_total > 0: sonstiges_bezug_pv     = round(sbpv_total, 2)
        if sbnetz_total > 0: sonstiges_bezug_netz = round(sbnetz_total, 2)
        # Pro-Gerät-Liste in Investitions-Reihenfolge; Kategorie aus parameter.
        def _v(x: float) -> Optional[float]:
            return round(x, 2) if x > 0 else None
        for inv in sonstiges_invs:
            g = acc.get(inv.id)
            if not g:
                continue
            kat = (inv.parameter or {}).get("kategorie", "erzeuger")
            if kat == "verbraucher":
                if g["vrb"] > 0 or g["bpv"] > 0 or g["bnz"] > 0:
                    sonstiges_geraete.append(SonstigesGeraet(
                        bezeichnung=inv.bezeichnung, kategorie="verbraucher",
                        verbrauch_kwh=_v(g["vrb"]), bezug_pv_kwh=_v(g["bpv"]), bezug_netz_kwh=_v(g["bnz"]),
                    ))
            else:
                if g["erz"] > 0:
                    sonstiges_geraete.append(SonstigesGeraet(
                        bezeichnung=inv.bezeichnung, kategorie="erzeuger",
                        erzeugung_kwh=_v(g["erz"]), eigenverbrauch_kwh=_v(g["eig"]), einspeisung_kwh=_v(g["ein"]),
                    ))

    # Flexibler Tarif: Durchschnittspreis aus Monatsdaten lesen
    netzbezug_durchschnittspreis = None
    md_flex_result = await db.execute(
        select(Monatsdaten).where(
            Monatsdaten.anlage_id == anlage_id,
            Monatsdaten.jahr == jahr,
            Monatsdaten.monat == monat,
        )
    )
    md_flex = md_flex_result.scalar_one_or_none()
    if md_flex and md_flex.netzbezug_durchschnittspreis_cent is not None:
        netzbezug_durchschnittspreis = md_flex.netzbezug_durchschnittspreis_cent

    # ── Komponenten-Flags ──
    # #239 detLAN: pro Monat filtern, nicht pro Anlage. Sonst wird die
    # Sektion (z.B. Wärmepumpe) im Monatsbericht angezeigt, bevor die
    # Investition angeschafft wurde — alle Werte sind dann "—", was den
    # User irritiert ("Investition vor Anschaffung darstellen" #236 P2).
    hat_speicher = any(
        i.typ == "speicher" and i.ist_aktiv_im_monat(jahr, monat)
        for i in investitionen
    )
    hat_waermepumpe = any(
        i.typ == "waermepumpe" and i.ist_aktiv_im_monat(jahr, monat)
        for i in investitionen
    )

    # ── Issue #169/#238: WP-Counter pro Monat aus TagesZusammenfassung ──
    # Quelle: TagesZusammenfassung.komponenten_starts (JSON, Form
    # {"wp_starts_anzahl": {"<inv_id>": <int>}, "wp_betriebsstunden": {...}}). Pro
    # Tag des Monats werden die Werte aller WP-Investitionen summiert (= Tagessumme
    # der Anlage), daraus max(Tagessumme) und Σ(Tagessumme im Monat). Zeigt was EEDC
    # erfasst hat — Drift gegenüber dem Hersteller-Counter (Cockpit) wird im
    # Daten-Checker ausgewiesen, nicht hier verrechnet. Starts = int, Stunden = float.
    wp_starts_max_tag: Optional[int] = None
    wp_starts_summe_monat: Optional[int] = None
    wp_betriebsstunden_max_tag: Optional[float] = None
    wp_betriebsstunden_summe_monat: Optional[float] = None
    if hat_waermepumpe:
        from backend.models.tages_energie_profil import TagesZusammenfassung
        from sqlalchemy import extract
        wp_invs = [
            i for i in investitionen
            if i.typ == "waermepumpe" and i.ist_aktiv_im_monat(jahr, monat)
        ]
        wp_inv_id_strs = {str(i.id) for i in wp_invs}
        tz_result = await db.execute(
            select(TagesZusammenfassung.komponenten_starts)
            .where(TagesZusammenfassung.anlage_id == anlage_id)
            .where(extract("year", TagesZusammenfassung.datum) == jahr)
            .where(extract("month", TagesZusammenfassung.datum) == monat)
            .where(TagesZusammenfassung.komponenten_starts.is_not(None))
        )

        def _tagessumme(komp: dict | None, feld: str) -> float:
            """Summe eines Counter-Felds über alle aktiven WP-Investitionen an einem Tag."""
            feld_map = (komp or {}).get(feld) or {}
            tag_sum = 0.0
            for inv_id_str, wert in feld_map.items():
                if inv_id_str in wp_inv_id_strs and isinstance(wert, (int, float)) and wert > 0:
                    tag_sum += float(wert)
            return tag_sum

        starts_tagessummen: list[int] = []
        stunden_tagessummen: list[float] = []
        for (komp_starts,) in tz_result.all():
            s = _tagessumme(komp_starts, "wp_starts_anzahl")
            if s > 0:
                starts_tagessummen.append(int(s))
            h = _tagessumme(komp_starts, "wp_betriebsstunden")
            if h > 0:
                stunden_tagessummen.append(h)
        if starts_tagessummen:
            wp_starts_max_tag = max(starts_tagessummen)
            wp_starts_summe_monat = sum(starts_tagessummen)
        if stunden_tagessummen:
            wp_betriebsstunden_max_tag = round(max(stunden_tagessummen), 1)
            wp_betriebsstunden_summe_monat = round(sum(stunden_tagessummen), 1)


    hat_emobilitaet = any(
        i.typ in ("e-auto", "wallbox")
        and not ist_dienstlich(i)
        and i.ist_aktiv_im_monat(jahr, monat)
        for i in investitionen
    )
    hat_balkonkraftwerk = any(
        i.typ == "balkonkraftwerk" and i.ist_aktiv_im_monat(jahr, monat)
        for i in investitionen
    )
    hat_sonstiges = any(
        i.typ == "sonstiges" and i.ist_aktiv_im_monat(jahr, monat)
        for i in investitionen
    )

    # ── Vergleichsdaten ──
    vorjahr = await _load_vorjahr(anlage_id, investitionen, jahr, monat, db)
    soll_pv = await _load_soll_pv(anlage_id, monat, db)

    # ── Quellen-Übersicht ──
    quellen = {
        "ha_statistics": bool(ha_stats),
        "mqtt_inbound": bool(mqtt_energy) if ist_aktueller_monat else False,
        "connector": bool(connector),
        "gespeichert": bool(saved),
    }

    # ── Feld-Quellen extrahieren ──
    feld_quellen = {
        feld: info
        for feld, (_, info) in resolved.items()
        if not feld.startswith("inv_")  # Investitions-Detail-Felder ausblenden
    }

    # ── Aktive Geräte je Typ (Namen) für die „aggregiert aus …"-Hinweise ──
    komponenten_geraete: dict[str, list[str]] = {}
    for _inv in investitionen:
        if _inv.ist_aktiv_im_monat(jahr, monat):
            komponenten_geraete.setdefault(_inv.typ, []).append(_inv.bezeichnung)

    # ── Per-Investition Finanzdetails (T-Konto) ──
    investitionen_financials: list[InvestitionFinancialDetail] = []
    if investitionen and allgemein_tarif:
        netz_p = netzbezug_preis_cent or NETZBEZUG_DEFAULT_CENT
        if netzbezug_durchschnittspreis:
            netz_p = netzbezug_durchschnittspreis
        einsp_p = einspeise_cent or EINSPEISEVERGUETUNG_DEFAULT_CENT
        wp_tarif_obj = tarife.get("waermepumpe")
        wp_p = (wp_tarif_obj.netzbezug_arbeitspreis_cent_kwh
                if wp_tarif_obj and wp_tarif_obj.netzbezug_arbeitspreis_cent_kwh is not None
                else netz_p)
        wb_tarif_obj = tarife.get("wallbox")
        wb_p = (wb_tarif_obj.netzbezug_arbeitspreis_cent_kwh
                if wb_tarif_obj and wb_tarif_obj.netzbezug_arbeitspreis_cent_kwh is not None
                else netz_p)
        # WP-Ersparnis pro Investition siehe wp_wirtschaftlichkeit.berechne_wp_ersparnis()
        # — nicht mehr lokal mit hartcodiertem Gaspreis berechnet (Drift-Audit A1).
        # Der monatliche Gaspreis-Override wird oben (md_for_gas) bereits geladen.

        # Alle InvestitionMonatsdaten in einem Query laden
        all_ids = [i.id for i in investitionen]
        all_imd_result = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(all_ids),
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            )
        )
        imd_by_inv: dict[int, dict] = {}
        for imd in all_imd_result.scalars().all():
            imd_by_inv[imd.investition_id] = imd.verbrauch_daten or {}

        # Wallbox-Pool-Attribution für die E-Auto-Komponente: bei evcc-Setups
        # steht die Ladung auf der Wallbox-IMD, das E-Auto trägt nur km. Ohne
        # diese Attribution rechnet die Komponente mit netz=0 + extern=0 und
        # weicht vom Hauptwert (Pool-Tile) ab — Drift gleicher Sicht.
        eauto_imd_data: list[dict] = []
        wb_imd_data: list[dict] = []
        for i in investitionen:
            if (not i.aktiv
                or not i.ist_aktiv_im_monat(jahr, monat)
                or ist_dienstlich(i)
                or i.id not in imd_by_inv):
                continue
            if i.typ == "e-auto":
                eauto_imd_data.append(imd_by_inv[i.id])
            elif i.typ == "wallbox":
                wb_imd_data.append(imd_by_inv[i.id])
        emob_pool_attr = compute_emob_pool_attribution(
            eauto_imd_data=eauto_imd_data,
            wallbox_imd_data=wb_imd_data,
        )

        for inv in investitionen:
            detail = _baue_investition_financial(
                inv,
                imd_by_inv.get(inv.id, {}),
                netz_p=netz_p,
                einsp_p=einsp_p,
                wp_p=wp_p,
                wb_p=wb_p,
                monats_gaspreis=monats_gaspreis,
                monats_benzinpreis=monats_benzinpreis,
                emob_pool_attr=emob_pool_attr,
            )
            if detail is not None:
                investitionen_financials.append(detail)

    # Ø Verbrauch (kWh/100 km) via zentralem Helper aus den FINALEN (ggf. connector-
    # überschriebenen) Werten — gemessener Fahrverbrauch hat Vorrang vor Ladung.
    emob_eff = eauto_effizienz_100km(
        get_val("emob_verbrauch_kwh") or 0,
        get_val("emob_ladung_kwh") or 0,
        get_val("emob_km") or 0,
    )

    # Spez. Ertrag auf Community-Basis (anlage.leistung_kwp), für die Abweichung
    # zum Community-Median in der Cockpit/Monat-Summary.
    spez_ertrag = spezifischer_ertrag_kwh_kwp(pv or 0, anlage.leistung_kwp)

    return AktuellerMonatResponse(
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        jahr=jahr,
        monat=monat,
        monat_name=MONAT_NAMEN[monat],
        aktualisiert_um=now.isoformat(),
        quellen=quellen,
        # Energie
        pv_erzeugung_kwh=pv,
        einspeisung_kwh=einspeisung,
        netzbezug_kwh=netzbezug,
        eigenverbrauch_kwh=eigenverbrauch,
        direktverbrauch_kwh=direktverbrauch,
        gesamtverbrauch_kwh=gesamtverbrauch,
        autarkie_prozent=autarkie,
        eigenverbrauch_quote_prozent=ev_quote,
        spez_ertrag=round(spez_ertrag, 1) if spez_ertrag is not None else None,
        # Komponenten — Speicher
        speicher_ladung_kwh=speicher_ladung,
        speicher_entladung_kwh=speicher_entladung,
        speicher_ladung_netz_kwh=speicher_ladung_netz,
        speicher_wirkungsgrad_prozent=speicher_wirkungsgrad,
        speicher_vollzyklen=speicher_vollzyklen,
        speicher_kapazitaet_kwh=speicher_kapazitaet,
        speicher_soc_drift_signifikant=speicher_soc_drift_flag,
        speicher_effektiver_ladepreis_cent=speicher_eff_ladepreis,
        speicher_effektiver_ladepreis_quelle=speicher_eff_ladepreis_quelle,
        hat_speicher=hat_speicher,
        # Komponenten — WP
        wp_strom_kwh=get_val("wp_strom_kwh"),
        wp_waerme_kwh=get_val("wp_waerme_kwh"),
        wp_heizung_kwh=wp_heizung,
        wp_warmwasser_kwh=wp_warmwasser,
        wp_strom_heizen_kwh=wp_strom_heizen,
        wp_strom_warmwasser_kwh=wp_strom_warmwasser,
        wp_starts_max_tag=wp_starts_max_tag,
        wp_starts_summe_monat=wp_starts_summe_monat,
        wp_betriebsstunden_max_tag=wp_betriebsstunden_max_tag,
        wp_betriebsstunden_summe_monat=wp_betriebsstunden_summe_monat,
        hat_waermepumpe=hat_waermepumpe,
        # Komponenten — E-Mobilität
        emob_ladung_kwh=get_val("emob_ladung_kwh"),
        emob_km=get_val("emob_km"),
        emob_verbrauch_100km=round(emob_eff.wert, 1) if emob_eff.wert is not None else None,
        emob_verbrauch_quelle=emob_eff.quelle,
        emob_ladung_pv_kwh=emob_pv if emob_pv else None,
        emob_ladung_netz_kwh=emob_ladung_netz,
        emob_ladung_extern_kwh=emob_ladung_extern,
        emob_v2h_kwh=emob_v2h,
        hat_emobilitaet=hat_emobilitaet,
        # Komponenten — BKW
        bkw_erzeugung_kwh=get_val("bkw_erzeugung_kwh"),
        bkw_eigenverbrauch_kwh=bkw_eigenverbrauch,
        hat_balkonkraftwerk=hat_balkonkraftwerk,
        # Komponenten — Sonstiges
        sonstiges_erzeugung_kwh=sonstiges_erzeugung,
        sonstiges_eigenverbrauch_kwh=sonstiges_eigenverbrauch,
        sonstiges_einspeisung_kwh=sonstiges_einspeisung,
        sonstiges_verbrauch_kwh=sonstiges_verbrauch,
        sonstiges_bezug_pv_kwh=sonstiges_bezug_pv,
        sonstiges_bezug_netz_kwh=sonstiges_bezug_netz,
        sonstiges_geraete=sonstiges_geraete,
        hat_sonstiges=hat_sonstiges,
        # Finanzen
        einspeise_erloes_euro=einspeise_erloes,
        netzbezug_kosten_euro=netzbezug_kosten,
        ev_ersparnis_euro=ev_ersparnis,
        netto_ertrag_euro=netto_ertrag,
        wp_ersparnis_euro=wp_ersparnis,
        emob_ersparnis_euro=emob_ersparnis,
        sonstige_ertraege_euro=sonstige_ertraege_total,
        sonstige_ausgaben_euro=sonstige_ausgaben_total,
        sonstige_netto_euro=sonstige_netto_total,
        gesamtnettoertrag_euro=gesamtnettoertrag,
        betriebskosten_anteilig_euro=betriebskosten_anteilig,
        # Tarif-Info
        netzbezug_preis_cent=netzbezug_preis_cent if allgemein_tarif else None,
        einspeise_preis_cent=einspeise_cent if allgemein_tarif else None,
        netzbezug_durchschnittspreis_cent=netzbezug_durchschnittspreis,
        # Vergleiche
        vorjahr=vorjahr,
        soll_pv_kwh=soll_pv,
        # Per-Investition Finanzdetails
        investitionen_financials=investitionen_financials,
        komponenten_geraete=komponenten_geraete,
        # Quellen
        feld_quellen=feld_quellen,
    )
