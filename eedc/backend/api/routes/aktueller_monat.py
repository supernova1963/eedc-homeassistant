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

    # Komponenten
    speicher_ladung_kwh: Optional[float] = None
    speicher_entladung_kwh: Optional[float] = None
    hat_speicher: bool = False
    wp_strom_kwh: Optional[float] = None
    wp_waerme_kwh: Optional[float] = None
    hat_waermepumpe: bool = False
    emob_ladung_kwh: Optional[float] = None
    emob_km: Optional[float] = None
    hat_emobilitaet: bool = False
    bkw_erzeugung_kwh: Optional[float] = None
    hat_balkonkraftwerk: bool = False

    # Finanzen (Euro)
    einspeise_erloes_euro: Optional[float] = None
    netzbezug_kosten_euro: Optional[float] = None
    ev_ersparnis_euro: Optional[float] = None
    netto_ertrag_euro: Optional[float] = None

    # Vergleiche
    vorjahr: Optional[dict] = None
    soll_pv_kwh: Optional[float] = None

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
        bkw_erzeugung_total = 0.0

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
            elif inv.typ == "balkonkraftwerk":
                bkw_kwh = (
                    data.get("pv_erzeugung_kwh", 0) or
                    data.get("erzeugung_kwh", 0) or 0
                )
                bkw_erzeugung_total += bkw_kwh
                # BKW ist PV-Erzeugung → fließt in Gesamt-PV ein
                pv_erzeugung_total += bkw_kwh

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
        if bkw_erzeugung_total > 0:
            resolved["bkw_erzeugung_kwh"] = (bkw_erzeugung_total, quelle)

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
    """Lädt Vorjahres-Monatsdaten für Vergleich."""
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
    }

    # PV-Erzeugung + Batterie aus InvestitionMonatsdaten
    pv_inv_ids = [i.id for i in investitionen if i.typ in ("pv-module", "balkonkraftwerk")]
    bat_inv_ids = [i.id for i in investitionen if i.typ == "speicher"]
    all_inv_ids = pv_inv_ids + bat_inv_ids
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
        for imd in imd_result.scalars().all():
            data = imd.verbrauch_daten or {}
            if imd.investition_id in pv_inv_ids:
                pv_vj += data.get("pv_erzeugung_kwh", 0) or data.get("erzeugung_kwh", 0) or 0
            elif imd.investition_id in bat_inv_ids:
                bat_ladung_vj += data.get("ladung_kwh", 0) or 0
                bat_entladung_vj += data.get("entladung_kwh", 0) or 0
        if pv_vj > 0:
            result["pv_erzeugung_kwh"] = round(pv_vj, 1)
        if bat_ladung_vj > 0:
            result["speicher_ladung_kwh"] = round(bat_ladung_vj, 1)
        if bat_entladung_vj > 0:
            result["speicher_entladung_kwh"] = round(bat_entladung_vj, 1)

    # Berechnete Werte (mit Batterie-Korrektur)
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
    db: AsyncSession = Depends(get_db),
):
    """
    Übersicht des aktuellen Monats mit Daten aus allen verfügbaren Quellen.

    Datenquellen-Priorität (höchste überschreibt niedrigere):
    1. Gespeicherte Monatsdaten (85%) — DB
    2. Connector (90%) — Geräte-Snapshot-Delta
    3. MQTT-Inbound (91%) — Energy-Topics aus Smarthome
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
    jahr = now.year
    monat = now.month
    investitionen = [i for i in anlage.investitionen if i.aktiv]

    # ── Daten sammeln (niedrigste Konfidenz zuerst, höchste überschreibt) ──
    resolved: dict[str, tuple[float, DatenquelleInfo]] = {}

    saved = await _collect_saved_data(anlage_id, jahr, monat, investitionen, db)
    resolved.update(saved)

    connector = await _collect_connector_data(anlage, jahr, monat)
    resolved.update(connector)

    mqtt_energy = await _collect_mqtt_inbound_data(anlage, investitionen)
    resolved.update(mqtt_energy)

    ha_stats = await _collect_ha_statistics_data(anlage, jahr, monat)
    resolved.update(ha_stats)

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

    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein_tarif = tarife.get("allgemein")
    if allgemein_tarif:
        netzbezug_preis_cent = allgemein_tarif.netzbezug_arbeitspreis_cent_kwh if allgemein_tarif.netzbezug_arbeitspreis_cent_kwh is not None else 30.0
        einspeise_cent = allgemein_tarif.einspeiseverguetung_cent_kwh if allgemein_tarif.einspeiseverguetung_cent_kwh is not None else 8.2

        if einspeisung is not None:
            einspeise_erloes = round(einspeisung * einspeise_cent / 100, 2)
        if netzbezug is not None:
            grundpreis = allgemein_tarif.grundpreis_euro_monat or 0
            netzbezug_kosten = round(netzbezug * netzbezug_preis_cent / 100 + grundpreis, 2)
        if eigenverbrauch is not None:
            ev_ersparnis = round(eigenverbrauch * netzbezug_preis_cent / 100, 2)

        if einspeise_erloes is not None and ev_ersparnis is not None:
            netto_ertrag = round(einspeise_erloes + ev_ersparnis, 2)

    # ── Komponenten-Flags ──
    hat_speicher = any(i.typ == "speicher" for i in investitionen)
    hat_waermepumpe = any(i.typ == "waermepumpe" for i in investitionen)
    hat_emobilitaet = any(
        i.typ in ("e-auto", "wallbox") and not (i.parameter or {}).get("ist_dienstlich", False)
        for i in investitionen
    )
    hat_balkonkraftwerk = any(i.typ == "balkonkraftwerk" for i in investitionen)

    # ── Vergleichsdaten ──
    vorjahr = await _load_vorjahr(anlage_id, investitionen, jahr, monat, db)
    soll_pv = await _load_soll_pv(anlage_id, monat, db)

    # ── Quellen-Übersicht ──
    quellen = {
        "ha_statistics": bool(ha_stats),
        "mqtt_inbound": bool(mqtt_energy),
        "connector": bool(connector),
        "gespeichert": bool(saved),
    }

    # ── Feld-Quellen extrahieren ──
    feld_quellen = {
        feld: info
        for feld, (_, info) in resolved.items()
        if not feld.startswith("inv_")  # Investitions-Detail-Felder ausblenden
    }

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
        # Komponenten
        speicher_ladung_kwh=speicher_ladung,
        speicher_entladung_kwh=speicher_entladung,
        hat_speicher=hat_speicher,
        wp_strom_kwh=get_val("wp_strom_kwh"),
        wp_waerme_kwh=get_val("wp_waerme_kwh"),
        hat_waermepumpe=hat_waermepumpe,
        emob_ladung_kwh=get_val("emob_ladung_kwh"),
        emob_km=get_val("emob_km"),
        hat_emobilitaet=hat_emobilitaet,
        bkw_erzeugung_kwh=get_val("bkw_erzeugung_kwh"),
        hat_balkonkraftwerk=hat_balkonkraftwerk,
        # Finanzen
        einspeise_erloes_euro=einspeise_erloes,
        netzbezug_kosten_euro=netzbezug_kosten,
        ev_ersparnis_euro=ev_ersparnis,
        netto_ertrag_euro=netto_ertrag,
        # Vergleiche
        vorjahr=vorjahr,
        soll_pv_kwh=soll_pv,
        # Quellen
        feld_quellen=feld_quellen,
    )
