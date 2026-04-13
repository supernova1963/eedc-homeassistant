"""
Aktueller Monat API Route.

Kombiniert Daten aus HA-Sensoren, HA-Statistics, Connectors und gespeicherten
Monatsdaten zu einer Echtzeit-Übersicht des laufenden Monats.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.deps import get_db
from backend.core.config import HA_INTEGRATION_AVAILABLE
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.models.pvgis_prognose import PVGISPrognose, PVGISMonatsprognose
from backend.api.routes.strompreise import lade_tarife_fuer_anlage, resolve_netzbezug_preis_cent
from backend.api.routes.connector import _calc_month_delta

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
    gesamtverbrauch_kwh: Optional[float] = None

    # Quoten (%)
    autarkie_prozent: Optional[float] = None
    eigenverbrauch_quote_prozent: Optional[float] = None

    # Komponenten — Speicher
    speicher_ladung_kwh: Optional[float] = None
    speicher_entladung_kwh: Optional[float] = None
    speicher_ladung_netz_kwh: Optional[float] = None   # Arbitrage-Ladung vom Netz
    speicher_wirkungsgrad_prozent: Optional[float] = None  # Entladung / Ladung * 100
    speicher_vollzyklen: Optional[float] = None        # Ladung / Kapazität
    speicher_kapazitaet_kwh: Optional[float] = None    # Aus Investition.parameter
    hat_speicher: bool = False

    # Komponenten — Wärmepumpe
    wp_strom_kwh: Optional[float] = None
    wp_waerme_kwh: Optional[float] = None
    wp_heizung_kwh: Optional[float] = None
    wp_warmwasser_kwh: Optional[float] = None
    hat_waermepumpe: bool = False

    # Komponenten — E-Mobilität
    emob_ladung_kwh: Optional[float] = None
    emob_km: Optional[float] = None
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
    hat_sonstiges: bool = False

    # Finanzen (Euro)
    einspeise_erloes_euro: Optional[float] = None
    netzbezug_kosten_euro: Optional[float] = None
    ev_ersparnis_euro: Optional[float] = None
    netto_ertrag_euro: Optional[float] = None
    wp_ersparnis_euro: Optional[float] = None
    emob_ersparnis_euro: Optional[float] = None
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
        emob_ladung_total = 0.0
        emob_km_total = 0.0
        emob_pv_ladung_total = 0.0
        bkw_erzeugung_total = 0.0
        bkw_eigenverbrauch_total = 0.0

        for imd in imd_result.scalars().all():
            inv = inv_by_id.get(imd.investition_id)
            if not inv:
                continue
            data = imd.verbrauch_daten or {}

            if inv.typ == "pv-module":
                pv_erzeugung_total += data.get("pv_erzeugung_kwh", 0) or 0
            elif inv.typ == "speicher":
                speicher_ladung_total += data.get("ladung_kwh", 0) or 0
                speicher_entladung_total += data.get("entladung_kwh", 0) or 0
            elif inv.typ == "waermepumpe":
                wp_strom_total += (
                    data.get("stromverbrauch_kwh", 0) or
                    (data.get("strom_heizen_kwh", 0) or 0) +
                    (data.get("strom_warmwasser_kwh", 0) or 0) or
                    data.get("strom_kwh", 0) or
                    data.get("verbrauch_kwh", 0) or 0
                )
                wp_waerme_total += (
                    data.get("waerme_kwh", 0) or
                    (data.get("heizenergie_kwh", 0) or data.get("heizung_kwh", 0)) +
                    (data.get("warmwasser_kwh", 0) or 0)
                )
            elif inv.typ in ("e-auto", "wallbox"):
                if not (inv.parameter or {}).get("ist_dienstlich", False):
                    emob_ladung_total += (
                        data.get("ladung_kwh", 0) or
                        data.get("verbrauch_kwh", 0) or 0
                    )
                    emob_km_total += data.get("km_gefahren", 0) or 0
                    emob_pv_ladung_total += data.get("ladung_pv_kwh", 0) or 0
            elif inv.typ == "balkonkraftwerk":
                bkw_kwh = (
                    data.get("pv_erzeugung_kwh", 0) or
                    data.get("erzeugung_kwh", 0) or 0
                )
                bkw_erzeugung_total += bkw_kwh
                # BKW ist PV-Erzeugung → fließt in Gesamt-PV ein
                pv_erzeugung_total += bkw_kwh
                bkw_eigenverbrauch_total += data.get("eigenverbrauch_kwh", 0) or bkw_kwh

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
        if emob_pv_ladung_total > 0:
            resolved["emob_pv_ladung_kwh"] = (emob_pv_ladung_total, quelle)
        if bkw_erzeugung_total > 0:
            resolved["bkw_erzeugung_kwh"] = (bkw_erzeugung_total, quelle)
        if bkw_eigenverbrauch_total > 0:
            resolved["bkw_eigenverbrauch_kwh"] = (bkw_eigenverbrauch_total, quelle)

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
    emob_inv_ids = [i.id for i in investitionen if i.typ in ("e-auto", "wallbox") and not (i.parameter or {}).get("ist_dienstlich", False)]
    all_inv_ids = pv_inv_ids + bat_inv_ids + wp_inv_ids + emob_inv_ids

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
        emob_ladung_vj = 0.0
        emob_km_vj = 0.0

        for imd in imd_result.scalars().all():
            data = imd.verbrauch_daten or {}
            if imd.investition_id in pv_inv_ids:
                pv_vj += data.get("pv_erzeugung_kwh", 0) or data.get("erzeugung_kwh", 0) or 0
            elif imd.investition_id in bat_inv_ids:
                bat_ladung_vj += data.get("ladung_kwh", 0) or 0
                bat_entladung_vj += data.get("entladung_kwh", 0) or 0
            elif imd.investition_id in wp_inv_ids:
                wp_strom_vj += (
                    data.get("stromverbrauch_kwh", 0) or
                    (data.get("strom_heizen_kwh", 0) or 0) + (data.get("strom_warmwasser_kwh", 0) or 0) or 0
                )
                wp_waerme_vj += (
                    (data.get("heizenergie_kwh", 0) or 0) + (data.get("warmwasser_kwh", 0) or 0)
                )
            elif imd.investition_id in emob_inv_ids:
                emob_ladung_vj += data.get("ladung_kwh", 0) or data.get("verbrauch_kwh", 0) or 0
                emob_km_vj += data.get("km_gefahren", 0) or 0

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
    direktverbrauch = max(0, pv - einsp - bat_ladung) if pv > 0 else 0
    ev = direktverbrauch + bat_entladung
    gv = ev + netz
    result["eigenverbrauch_kwh"] = round(ev, 1)
    result["autarkie_prozent"] = round(ev / gv * 100, 1) if gv > 0 else None

    # Finanzen mit historisch korrektem Tarif berechnen
    try:
        stichtag_vj = date_type(vj, monat, 1)
        tarife_vj = await lade_tarife_fuer_anlage(db, anlage_id, target_date=stichtag_vj)
        tarif_vj = tarife_vj.get("allgemein")
        if tarif_vj:
            netz_preis = tarif_vj.netzbezug_arbeitspreis_cent_kwh or 30.0
            einsp_preis = tarif_vj.einspeiseverguetung_cent_kwh or 8.2
            grundpreis = tarif_vj.grundpreis_euro_monat or 0
            # Flexibler Tarif überschreibt wenn vorhanden
            if result.get("netzbezug_durchschnittspreis_cent"):
                netz_preis = result["netzbezug_durchschnittspreis_cent"]
            if einsp > 0:
                result["einspeise_erloes_euro"] = round(einsp * einsp_preis / 100, 2)
            if netz > 0:
                result["netzbezug_kosten_euro"] = round(netz * netz_preis / 100 + grundpreis, 2)
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
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    now = datetime.now()
    if jahr is None:
        jahr = now.year
    if monat is None:
        monat = now.month
    ist_aktueller_monat = (jahr == now.year and monat == now.month)
    investitionen = [i for i in anlage.investitionen if i.aktiv]

    # ── Daten sammeln (niedrigste Konfidenz zuerst, höchste überschreibt) ──
    resolved: dict[str, tuple[float, DatenquelleInfo]] = {}

    saved = await _collect_saved_data(anlage_id, jahr, monat, investitionen, db)
    resolved.update(saved)

    connector = await _collect_connector_data(anlage, jahr, monat)
    resolved.update(connector)

    mqtt_energy = await _collect_mqtt_inbound_data(anlage, investitionen) if ist_aktueller_monat else {}
    resolved.update(mqtt_energy)

    ha_stats = await _collect_ha_statistics_data(anlage, jahr, monat)
    if ist_aktueller_monat:
        # Laufender Monat: HA-Stats sind die frischeste Quelle und sollen die
        # gespeicherten Werte überschreiben (Vorschau aus Live-Sensoren).
        resolved.update(ha_stats)
    else:
        # Vergangener Monat: gespeicherte Monatsdaten + InvestitionMonatsdaten
        # sind authoritativ (Monatsabschluss). HA-Stats nur als Fallback für
        # Felder, die noch nicht vorhanden sind — kein Override mehr, sonst
        # können sich Werte rückwirkend ändern (Sensor-Renames, Recorder-Drift)
        # und Monatsbericht weicht von Auswertung→Tabelle ab (#118).
        for k, v in ha_stats.items():
            resolved.setdefault(k, v)

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
        "e-auto": {"ladung_kwh": "emob_ladung_kwh", "verbrauch_kwh": "emob_ladung_kwh", "km_gefahren": "emob_km"},
        "wallbox": {"ladung_kwh": "emob_ladung_kwh"},
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

    for inv in investitionen:
        agg_map = typ_aggregation.get(inv.typ, {})
        for inv_suffix, top_level_feld in agg_map.items():
            _aggregate(top_level_feld, f"inv_{inv.id}_{inv_suffix}")

    # ── Werte extrahieren ──
    def get_val(feld: str) -> Optional[float]:
        entry = resolved.get(feld)
        return round(entry[0], 2) if entry else None

    pv = get_val("pv_erzeugung_kwh")
    einspeisung = get_val("einspeisung_kwh")
    netzbezug = get_val("netzbezug_kwh")
    speicher_ladung = get_val("speicher_ladung_kwh")
    speicher_entladung = get_val("speicher_entladung_kwh")

    # ── Berechnete Werte ──
    eigenverbrauch = None
    gesamtverbrauch = None
    autarkie = None
    ev_quote = None

    if pv is not None and einspeisung is not None:
        ladung = speicher_ladung or 0
        entladung = speicher_entladung or 0
        direktverbrauch = max(0, pv - einspeisung - ladung)
        eigenverbrauch = round(direktverbrauch + entladung, 2)

        if netzbezug is not None:
            gesamtverbrauch = round(eigenverbrauch + netzbezug, 2)
            if gesamtverbrauch > 0:
                autarkie = round(eigenverbrauch / gesamtverbrauch * 100, 1)

        if pv > 0:
            ev_quote = round(min(eigenverbrauch / pv * 100, 100), 1)

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
        netzbezug_preis_cent = allgemein_tarif.netzbezug_arbeitspreis_cent_kwh if allgemein_tarif.netzbezug_arbeitspreis_cent_kwh is not None else 30.0
        einspeise_cent = allgemein_tarif.einspeiseverguetung_cent_kwh if allgemein_tarif.einspeiseverguetung_cent_kwh is not None else 8.2
        # Flexibler Durchschnittspreis überschreibt Netzbezugspreis für Finanzberechnung
        # (wird nach dem Monatsdaten-Laden gesetzt, hier Platzhalter für spätere Überschreibung)

        if einspeisung is not None:
            einspeise_erloes = round(einspeisung * einspeise_cent / 100, 2)
        if netzbezug is not None:
            grundpreis = allgemein_tarif.grundpreis_euro_monat or 0
            netzbezug_kosten = round(netzbezug * netzbezug_preis_cent / 100 + grundpreis, 2)
        if eigenverbrauch is not None:
            ev_ersparnis = round(eigenverbrauch * netzbezug_preis_cent / 100, 2)

        if einspeise_erloes is not None and ev_ersparnis is not None:
            netto_ertrag = round(einspeise_erloes + ev_ersparnis, 2)

    # ── Komponenten-Ersparnis ──
    wp_ersparnis = None
    emob_ersparnis = None

    wp_waerme = get_val("wp_waerme_kwh")
    wp_strom = get_val("wp_strom_kwh")
    if wp_waerme is not None and wp_strom is not None and allgemein_tarif:
        wp_tarif = tarife.get("waermepumpe")
        wp_preis_cent = (
            wp_tarif.netzbezug_arbeitspreis_cent_kwh
            if wp_tarif and wp_tarif.netzbezug_arbeitspreis_cent_kwh is not None
            else netzbezug_preis_cent
        )
        GAS_PREIS_CENT = 10.0
        wp_ersparnis = round(
            (wp_waerme / 0.9 * GAS_PREIS_CENT - wp_strom * wp_preis_cent) / 100, 2
        )

    emob_ladung = get_val("emob_ladung_kwh")
    emob_km = get_val("emob_km")
    emob_pv_ladung = get_val("emob_pv_ladung_kwh") or 0.0
    if emob_km is not None and emob_km > 0 and allgemein_tarif:
        wallbox_tarif = tarife.get("wallbox")
        wallbox_preis_cent = (
            wallbox_tarif.netzbezug_arbeitspreis_cent_kwh
            if wallbox_tarif and wallbox_tarif.netzbezug_arbeitspreis_cent_kwh is not None
            else netzbezug_preis_cent
        )
        benzin_kosten = emob_km * 7 / 100 * 1.80
        strom_kosten = ((emob_ladung or 0) - emob_pv_ladung) * wallbox_preis_cent / 100
        emob_ersparnis = round(benzin_kosten - strom_kosten, 2)

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

    # ── Gesamtnettoertrag = Erlöse + Einsparungen − Kosten ──
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
    # Speicher: Kapazität, Arbitrage-Ladung, Wirkungsgrad, Vollzyklen
    speicher_ladung_netz = None
    speicher_wirkungsgrad = None
    speicher_vollzyklen = None
    speicher_kapazitaet = None

    speicher_invs = [i for i in investitionen if i.typ == "speicher"]
    if speicher_invs:
        # Kapazität aus parameter
        kap_sum = sum((i.parameter or {}).get("kapazitaet_kwh", 0) or 0 for i in speicher_invs)
        if kap_sum > 0:
            speicher_kapazitaet = round(kap_sum, 1)

        # Arbitrage-Ladung aus gespeicherten Daten
        sp_ids = [i.id for i in speicher_invs]
        sp_imd = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(sp_ids),
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            )
        )
        ladung_netz_total = 0.0
        for imd in sp_imd.scalars().all():
            data = imd.verbrauch_daten or {}
            ladung_netz_total += data.get("ladung_netz_kwh", 0) or 0
        if ladung_netz_total > 0:
            speicher_ladung_netz = round(ladung_netz_total, 2)

        # Wirkungsgrad und Vollzyklen
        sl = speicher_ladung or 0
        se = speicher_entladung or 0
        if sl > 0 and se > 0:
            speicher_wirkungsgrad = round(se / sl * 100, 1)
        if sl > 0 and speicher_kapazitaet and speicher_kapazitaet > 0:
            speicher_vollzyklen = round(sl / speicher_kapazitaet, 2)

    # WP: Heizung/Warmwasser-Split
    wp_heizung = None
    wp_warmwasser = None
    wp_invs = [i for i in investitionen if i.typ == "waermepumpe"]
    if wp_invs:
        wp_ids = [i.id for i in wp_invs]
        wp_imd = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(wp_ids),
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            )
        )
        h_total = 0.0
        ww_total = 0.0
        for imd in wp_imd.scalars().all():
            data = imd.verbrauch_daten or {}
            h_total += data.get("heizenergie_kwh", 0) or data.get("heizung_kwh", 0) or 0
            ww_total += data.get("warmwasser_kwh", 0) or 0
        if h_total > 0:
            wp_heizung = round(h_total, 2)
        if ww_total > 0:
            wp_warmwasser = round(ww_total, 2)

    # E-Mobilität: PV/Netz/Extern-Split + V2H
    emob_pv = get_val("emob_pv_ladung_kwh")
    emob_ladung_netz = None
    emob_ladung_extern = None
    emob_v2h = None

    emob_invs = [i for i in investitionen if i.typ in ("e-auto", "wallbox") and not (i.parameter or {}).get("ist_dienstlich", False)]
    if emob_invs:
        emob_ids = [i.id for i in emob_invs]
        emob_imd = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(emob_ids),
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            )
        )
        netz_total = 0.0
        extern_total = 0.0
        v2h_total = 0.0
        for imd in emob_imd.scalars().all():
            data = imd.verbrauch_daten or {}
            netz_total += data.get("ladung_netz_kwh", 0) or 0
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
        bkw_ids = [i.id for i in bkw_invs]
        bkw_imd = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(bkw_ids),
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            )
        )
        ev_total = 0.0
        for imd in bkw_imd.scalars().all():
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
    if sonstiges_invs:
        sonstiges_ids = [i.id for i in sonstiges_invs]
        sonstiges_imd = await db.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(sonstiges_ids),
                InvestitionMonatsdaten.jahr == jahr,
                InvestitionMonatsdaten.monat == monat,
            )
        )
        se_total = 0.0
        sev_total = 0.0
        sei_total = 0.0
        sv_total = 0.0
        sbpv_total = 0.0
        sbnetz_total = 0.0
        for imd in sonstiges_imd.scalars().all():
            data = imd.verbrauch_daten or {}
            se_total   += data.get("erzeugung_kwh", 0) or 0
            sev_total  += data.get("eigenverbrauch_kwh", 0) or 0
            sei_total  += data.get("einspeisung_kwh", 0) or 0
            sv_total   += data.get("verbrauch_sonstig_kwh", 0) or 0
            sbpv_total += data.get("bezug_pv_kwh", 0) or 0
            sbnetz_total += data.get("bezug_netz_kwh", 0) or 0
        if se_total > 0:   sonstiges_erzeugung    = round(se_total, 2)
        if sev_total > 0:  sonstiges_eigenverbrauch = round(sev_total, 2)
        if sei_total > 0:  sonstiges_einspeisung  = round(sei_total, 2)
        if sv_total > 0:   sonstiges_verbrauch    = round(sv_total, 2)
        if sbpv_total > 0: sonstiges_bezug_pv     = round(sbpv_total, 2)
        if sbnetz_total > 0: sonstiges_bezug_netz = round(sbnetz_total, 2)

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
    hat_speicher = any(i.typ == "speicher" for i in investitionen)
    hat_waermepumpe = any(i.typ == "waermepumpe" for i in investitionen)
    hat_emobilitaet = any(
        i.typ in ("e-auto", "wallbox") and not (i.parameter or {}).get("ist_dienstlich", False)
        for i in investitionen
    )
    hat_balkonkraftwerk = any(i.typ == "balkonkraftwerk" for i in investitionen)
    hat_sonstiges = any(i.typ == "sonstiges" for i in investitionen)

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

    # ── Per-Investition Finanzdetails (T-Konto) ──
    investitionen_financials: list[InvestitionFinancialDetail] = []
    if investitionen and allgemein_tarif:
        netz_p = netzbezug_preis_cent or 30.0
        if netzbezug_durchschnittspreis:
            netz_p = netzbezug_durchschnittspreis
        einsp_p = einspeise_cent or 8.2
        wp_tarif_obj = tarife.get("waermepumpe")
        wp_p = (wp_tarif_obj.netzbezug_arbeitspreis_cent_kwh
                if wp_tarif_obj and wp_tarif_obj.netzbezug_arbeitspreis_cent_kwh is not None
                else netz_p)
        wb_tarif_obj = tarife.get("wallbox")
        wb_p = (wb_tarif_obj.netzbezug_arbeitspreis_cent_kwh
                if wb_tarif_obj and wb_tarif_obj.netzbezug_arbeitspreis_cent_kwh is not None
                else netz_p)
        GAS_PREIS_CENT = 10.0

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

        for inv in investitionen:
            if not inv.aktiv:
                continue
            data = imd_by_inv.get(inv.id, {})
            bk_monat = round((inv.betriebskosten_jahr or 0) / 12, 2)
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
                waerme = (data.get("heizenergie_kwh", 0) or data.get("heizung_kwh", 0) or 0)
                ww = data.get("warmwasser_kwh", 0) or 0
                strom = data.get("stromverbrauch_kwh")
                waerme_total = (waerme or 0) + (ww or 0)
                if waerme_total > 0 and strom is not None:
                    inv_ersparnis = round(
                        (waerme_total / 0.9 * GAS_PREIS_CENT - strom * wp_p) / 100, 2
                    )
                    inv_label = "Ersparnis vs. Gas"
                    inv_formel = "(Wärme ÷ 0,9 × Gaspreis) − Strom × WP-Strompreis"
                    inv_berechnung = f"{waerme_total:.1f} kWh / 0,9 × 10 ct − {strom:.1f} kWh × {wp_p:.2f} ct"

            elif inv.typ in ("e-auto", "wallbox") and not (inv.parameter or {}).get("ist_dienstlich", False):
                km = data.get("km_gefahren")
                ladung = data.get("ladung_kwh") or data.get("verbrauch_kwh")
                ladung_netz = data.get("ladung_netz_kwh")
                ladung_pv = data.get("ladung_pv_kwh")
                if km and km > 0:
                    benzin_kosten = km * 7 / 100 * 1.80
                    netz_kwh = ladung_netz if ladung_netz is not None else ((ladung or 0) - (ladung_pv or 0))
                    strom_kosten = max(0, netz_kwh) * wb_p / 100
                    inv_ersparnis = round(benzin_kosten - strom_kosten, 2)
                    inv_label = "Ersparnis vs. Verbrenner"
                    inv_formel = "(km × 7 L/100km × 1,80 €/L) − Netzladung × Strompreis"
                    inv_berechnung = f"{km:.0f} km × 7/100 × 1,80 €"
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

            if bk_monat > 0 or inv_ersparnis is not None or inv_erloes is not None:
                investitionen_financials.append(InvestitionFinancialDetail(
                    investition_id=inv.id,
                    bezeichnung=inv.bezeichnung,
                    typ=inv.typ,
                    betriebskosten_monat_euro=bk_monat,
                    erloes_euro=inv_erloes,
                    ersparnis_euro=inv_ersparnis,
                    ersparnis_label=inv_label,
                    formel=inv_formel,
                    berechnung=inv_berechnung,
                ))

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
        gesamtverbrauch_kwh=gesamtverbrauch,
        autarkie_prozent=autarkie,
        eigenverbrauch_quote_prozent=ev_quote,
        # Komponenten — Speicher
        speicher_ladung_kwh=speicher_ladung,
        speicher_entladung_kwh=speicher_entladung,
        speicher_ladung_netz_kwh=speicher_ladung_netz,
        speicher_wirkungsgrad_prozent=speicher_wirkungsgrad,
        speicher_vollzyklen=speicher_vollzyklen,
        speicher_kapazitaet_kwh=speicher_kapazitaet,
        hat_speicher=hat_speicher,
        # Komponenten — WP
        wp_strom_kwh=get_val("wp_strom_kwh"),
        wp_waerme_kwh=get_val("wp_waerme_kwh"),
        wp_heizung_kwh=wp_heizung,
        wp_warmwasser_kwh=wp_warmwasser,
        hat_waermepumpe=hat_waermepumpe,
        # Komponenten — E-Mobilität
        emob_ladung_kwh=get_val("emob_ladung_kwh"),
        emob_km=get_val("emob_km"),
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
        hat_sonstiges=hat_sonstiges,
        # Finanzen
        einspeise_erloes_euro=einspeise_erloes,
        netzbezug_kosten_euro=netzbezug_kosten,
        ev_ersparnis_euro=ev_ersparnis,
        netto_ertrag_euro=netto_ertrag,
        wp_ersparnis_euro=wp_ersparnis,
        emob_ersparnis_euro=emob_ersparnis,
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
        # Quellen
        feld_quellen=feld_quellen,
    )
