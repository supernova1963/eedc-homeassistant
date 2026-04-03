"""
Live History Service - HA-History-Abfragen, Trapez-Integration, Tages-kWh.

Ausgelagert aus live_power_service.py (Schritt 3 des Refactorings).
Enthält:
  - get_history_normalized: History holen + kW→W normalisieren
  - apply_invert_to_history: Vorzeichen-Invertierung auf History
  - trapez_kwh: Energie aus Leistungsverlauf (Trapezregel)
  - get_tages_kwh: Tages-kWh aus HA-History (Kategorien + Komponenten)
  - safe_get_tages_kwh: Wrapper mit Cache + MQTT-Fallback
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import HA_INTEGRATION_AVAILABLE
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.live_sensor_config import (
    UNIT_TO_W,
    ERZEUGER_TYPEN,
    SKIP_TYPEN,
    LIVE_KEY_PREFIX,
    TAGESVERLAUF_KATEGORIE,
    extract_live_config,
)

logger = logging.getLogger(__name__)


# ── Hilfsfunktionen (ehemals Closures in _get_tages_kwh) ─────────────

# Einheiten für Energie-Sensoren
_KWH_UNITS = {"kWh", "Wh", "MWh"}
_KWH_SCALE = {"kWh": 1.0, "Wh": 0.001, "MWh": 1000.0}

# Monatsabschluss-Sensoren: typ → (sensor_field, comp_key_prefix)
_MONATSABSCHLUSS_KWH: dict[str, tuple[str, str]] = {
    "waermepumpe": ("stromverbrauch_kwh", "waermepumpe"),
    "wallbox":     ("ladung_kwh",          "wallbox"),
}


def _feld_eid(conf: object) -> Optional[str]:
    """Extrahiert entity_id aus FeldMapping-Dict {strategie, sensor_id}."""
    if isinstance(conf, dict) and conf.get("strategie") == "sensor":
        return conf.get("sensor_id") or None
    return None


def _is_energy_sensor(eid: str, sensor_units: dict[str, str]) -> bool:
    """Prüft ob ein Sensor ein Energie-Sensor ist (kWh/Wh/MWh)."""
    return sensor_units.get(eid, "") in _KWH_UNITS


def _energy_delta(
    eid: str,
    history: dict[str, list[tuple[datetime, float]]],
    sensor_units: dict[str, str],
) -> Optional[float]:
    """Tages-kWh aus kumulativem Energie-Sensor via Delta (min → letzter Wert)."""
    pts = history.get(eid)
    if not pts:
        return None
    scale = _KWH_SCALE.get(sensor_units.get(eid, "kWh"), 1.0)
    val_start = min(p[1] for p in pts) * scale
    val_end = pts[-1][1] * scale
    return max(0.0, val_end - val_start)


# ── Öffentliche Funktionen ────────────────────────────────────────────

async def get_history_normalized(
    entity_ids: list[str], start: datetime, end: datetime,
) -> tuple[dict[str, list[tuple[datetime, float]]], dict[str, str]]:
    """Holt Sensor-History und normalisiert kW→W anhand der Einheit.

    Returns:
        (history, units) — history mit normalisierten W-Werten,
        units dict für nachgelagerte Einheit-Erkennung (z.B. kWh-Sensoren).
    """
    from backend.services.ha_state_service import get_ha_state_service
    ha_service = get_ha_state_service()

    units = await ha_service.get_sensor_units(entity_ids)
    history = await ha_service.get_sensor_history(entity_ids, start, end)

    for eid, points in history.items():
        factor = UNIT_TO_W.get(units.get(eid, ""), None)
        if factor is not None and factor != 1.0:
            history[eid] = [(ts, val * factor) for ts, val in points]

    return history, units


def apply_invert_to_history(
    history: dict[str, list[tuple[datetime, float]]],
    basis_live: dict[str, str],
    basis_invert: dict[str, bool],
    inv_live_map: dict[str, dict[str, str]] | None = None,
    inv_invert_map: dict[str, dict[str, bool]] | None = None,
) -> None:
    """Invertiert History-Werte für Sensoren mit Vorzeichen-Invertierung.

    Mutiert das history-Dict in-place (negiert Werte invertierter Sensoren).
    """
    invert_eids: set[str] = set()
    for key, should_invert in basis_invert.items():
        if should_invert and key in basis_live:
            invert_eids.add(basis_live[key])

    if inv_live_map and inv_invert_map:
        for inv_id, invert_flags in inv_invert_map.items():
            live = inv_live_map.get(inv_id, {})
            for key, should_invert in invert_flags.items():
                if should_invert and key in live:
                    invert_eids.add(live[key])

    for eid in invert_eids:
        if eid in history:
            history[eid] = [(ts, -val) for ts, val in history[eid]]


def trapez_kwh(points: list) -> Optional[float]:
    """Berechnet kWh aus Leistungs-History via Trapezregel."""
    if not points:
        return None
    if len(points) < 2:
        return 0.0
    energy_wh = 0.0
    for i in range(len(points) - 1):
        t1, p1 = points[i]
        t2, p2 = points[i + 1]
        dt_hours = (t2 - t1).total_seconds() / 3600
        if 0 < dt_hours < 2:  # Max 2h Lücke
            energy_wh += (p1 + p2) / 2 * dt_hours
    return energy_wh / 1000  # Wh → kWh


async def get_tages_kwh(
    anlage: Anlage, db: AsyncSession, tage_zurueck: int = 0,
    inv_types: dict[str, str] | None = None,
) -> dict[str, Optional[float]]:
    """
    Berechnet Tages-kWh aus HA-History (Leistungssensoren → Energie via Trapezregel).

    Aggregiert in Kategorien (pv, einspeisung, netzbezug) UND per-Komponente
    (z.B. pv_3, wallbox_6, batterie_2) für Tooltips im Energiefluss.
    """
    basis_live, inv_live_map, basis_invert, inv_invert_map = extract_live_config(anlage)

    # Investitionstypen: durchgereicht oder aus DB laden
    if inv_types is None:
        inv_result = await db.execute(
            select(Investition.id, Investition.typ).where(
                Investition.anlage_id == anlage.id, Investition.aktiv == True
            )
        )
        inv_types = {str(row[0]): row[1] for row in inv_result.all()}

    # Entity-IDs nach Kategorie gruppieren
    category_entities: dict[str, list[str]] = {
        "pv": [],
        "einspeisung": [],
        "netzbezug": [],
    }

    # Per-Komponente Entity-IDs {component_key: entity_id}
    component_entities: dict[str, str] = {}

    # Basis: Einspeisung + Netzbezug (oder kombinierter Netz-Sensor)
    netz_kombi_eid = basis_live.get("netz_kombi_w")
    if netz_kombi_eid and not basis_live.get("einspeisung_w") and not basis_live.get("netzbezug_w"):
        category_entities["netz_kombi"] = [netz_kombi_eid]
    else:
        netz_kombi_eid = None
        if basis_live.get("einspeisung_w"):
            category_entities["einspeisung"].append(basis_live["einspeisung_w"])
        if basis_live.get("netzbezug_w"):
            category_entities["netzbezug"].append(basis_live["netzbezug_w"])

    # kWh-Sensoren aus Monatsabschluss-Mapping für exakte Tageswerte (#64)
    mapping_full = anlage.sensor_mapping or {}
    basis_map = mapping_full.get("basis", {})
    basis_kwh_sensors: dict[str, str] = {}
    if (eid := _feld_eid(basis_map.get("einspeisung", {}))):
        basis_kwh_sensors["einspeisung"] = eid
    if (eid := _feld_eid(basis_map.get("netzbezug", {}))):
        basis_kwh_sensors["netzbezug"] = eid

    separate_battery_sensors: dict[str, dict[str, Optional[str]]] = {}
    separate_kwh_sensors: dict[str, str] = {}
    mapping_investitionen = mapping_full.get("investitionen", {})
    for inv_id, inv_data in mapping_investitionen.items():
        typ = inv_types.get(inv_id) if inv_types else None
        if not isinstance(inv_data, dict):
            continue
        inv_live = inv_data.get("live", {}) or {}
        inv_felder = inv_data.get("felder", {}) or {}

        if typ == "speicher":
            ladung_eid = inv_live.get("ladung_kwh") or None
            entladung_eid = inv_live.get("entladung_kwh") or None
            if not ladung_eid:
                ladung_eid = _feld_eid(inv_felder.get("ladung_kwh", {}))
            if not entladung_eid:
                entladung_eid = _feld_eid(inv_felder.get("entladung_kwh", {}))
            if ladung_eid or entladung_eid:
                separate_battery_sensors[inv_id] = {
                    "ladung": ladung_eid,
                    "entladung": entladung_eid,
                }
        elif typ in ERZEUGER_TYPEN:
            pv_eid = _feld_eid(inv_felder.get("pv_erzeugung_kwh", {}))
            if pv_eid:
                separate_kwh_sensors[f"pv_{inv_id}"] = pv_eid
        elif typ in _MONATSABSCHLUSS_KWH:
            sensor_field, prefix = _MONATSABSCHLUSS_KWH[typ]
            kwh_eid = _feld_eid(inv_felder.get(sensor_field, {}))
            if kwh_eid:
                separate_kwh_sensors[f"{prefix}_{inv_id}"] = kwh_eid

    # Alle Investitionen mit leistung_w Sensor (oder getrennte WP-Sensoren)
    for inv_id, live in inv_live_map.items():
        typ = inv_types.get(inv_id)
        if not typ or typ in SKIP_TYPEN:
            continue

        entity_id = live.get("leistung_w")

        # WP: getrennte Leistungssensoren → beide als Komponenten
        if not entity_id and typ == "waermepumpe":
            heiz_eid = live.get("leistung_heizen_w")
            ww_eid = live.get("leistung_warmwasser_w")
            if heiz_eid:
                component_entities[f"waermepumpe_{inv_id}_heizen"] = heiz_eid
            if ww_eid:
                component_entities[f"waermepumpe_{inv_id}_warmwasser"] = ww_eid
            continue

        # Speicher ohne leistung_w aber mit separaten kWh-Sensoren
        if not entity_id and typ == "speicher":
            sep = separate_battery_sensors.get(inv_id, {})
            entity_id = sep.get("ladung") or None

        if not entity_id:
            continue

        if typ in ERZEUGER_TYPEN:
            category_entities["pv"].append(entity_id)
            component_entities[f"pv_{inv_id}"] = entity_id
        else:
            prefix = LIVE_KEY_PREFIX.get(typ, TAGESVERLAUF_KATEGORIE.get(typ, typ))
            component_entities[f"{prefix}_{inv_id}"] = entity_id

    # PV Gesamt aus Basis als Fallback
    if not category_entities["pv"] and basis_live.get("pv_gesamt_w"):
        pv_gesamt_eid = basis_live["pv_gesamt_w"]
        category_entities["pv"].append(pv_gesamt_eid)
        component_entities["pv_gesamt"] = pv_gesamt_eid

    # Alle Entity-IDs sammeln (dedupliziert)
    all_ids = list(set(
        [eid for eids in category_entities.values() for eid in eids]
        + list(component_entities.values())
        + [eid for sep in separate_battery_sensors.values()
           for eid in sep.values() if eid]
        + list(separate_kwh_sensors.values())
        + list(basis_kwh_sensors.values())
    ))
    if not all_ids:
        return {}

    now = datetime.now()
    tag = now - timedelta(days=tage_zurueck)
    start = tag.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1) if tage_zurueck > 0 else now

    history, sensor_units = await get_history_normalized(all_ids, start, end)

    # Vorzeichen-Invertierung auf History anwenden (#58)
    apply_invert_to_history(
        history, basis_live, basis_invert, inv_live_map, inv_invert_map
    )

    result: dict[str, Optional[float]] = {}

    # Aggregierte Kategorien (pv, einspeisung, netzbezug)
    for category, entity_ids in category_entities.items():
        if category == "netz_kombi":
            for entity_id in entity_ids:
                if entity_id not in history:
                    continue
                pts = history[entity_id]
                bezug_pts = [(t, max(p, 0)) for t, p in pts]
                einsp_pts = [(t, abs(min(p, 0))) for t, p in pts]
                bezug_kwh = trapez_kwh(bezug_pts)
                einsp_kwh = trapez_kwh(einsp_pts)
                if bezug_kwh is not None:
                    result["netzbezug"] = round(bezug_kwh, 1)
                if einsp_kwh is not None:
                    result["einspeisung"] = round(einsp_kwh, 1)
            continue

        # Priorität 1: kumulierter kWh-Sensor
        if category in basis_kwh_sensors:
            kwh_eid = basis_kwh_sensors[category]
            if kwh_eid in history:
                kwh = _energy_delta(kwh_eid, history, sensor_units)
                if kwh is not None:
                    result[category] = round(kwh, 1)
                    continue
        elif category == "pv":
            pv_total = 0.0
            pv_has_kwh = False
            for comp_key, kwh_eid in separate_kwh_sensors.items():
                if comp_key.startswith("pv_") and kwh_eid in history:
                    kwh = _energy_delta(kwh_eid, history, sensor_units)
                    if kwh is not None:
                        pv_total += kwh
                        pv_has_kwh = True
            if pv_has_kwh:
                result["pv"] = round(pv_total, 1)
                continue

        # Fallback: W-Sensoren + Trapezregel
        total_kwh = 0.0
        has_data = False
        for entity_id in entity_ids:
            if entity_id not in history:
                continue
            if _is_energy_sensor(entity_id, sensor_units):
                kwh = _energy_delta(entity_id, history, sensor_units)
            else:
                kwh = trapez_kwh(history[entity_id])
            if kwh is not None:
                total_kwh += kwh
                has_data = True
        if has_data:
            result[category] = round(total_kwh, 1)

    # Per-Komponente kWh (für Tooltips)
    for comp_key, entity_id in component_entities.items():
        if entity_id not in history:
            continue
        pts = history[entity_id]

        # Batterie: Ladung/Entladung getrennt berechnen
        if comp_key.startswith("batterie_"):
            inv_id = comp_key[len("batterie_"):]
            sep = separate_battery_sensors.get(inv_id, {})
            ladung_eid = sep.get("ladung")
            entladung_eid = sep.get("entladung")

            if ladung_eid and ladung_eid in history:
                ladung_kwh = _energy_delta(ladung_eid, history, sensor_units)
            elif _is_energy_sensor(entity_id, sensor_units):
                ladung_kwh = _energy_delta(entity_id, history, sensor_units)
            else:
                ladung_pts = [(t, max(p, 0)) for t, p in pts]
                ladung_kwh = trapez_kwh(ladung_pts)

            if entladung_eid and entladung_eid in history:
                entladung_kwh = _energy_delta(entladung_eid, history, sensor_units)
            elif not _is_energy_sensor(entity_id, sensor_units):
                entladung_pts = [(t, abs(min(p, 0))) for t, p in pts]
                entladung_kwh = trapez_kwh(entladung_pts)
            else:
                entladung_kwh = None

            if ladung_kwh is not None:
                result[f"{comp_key}_ladung"] = round(ladung_kwh, 1)
            if entladung_kwh is not None:
                result[f"{comp_key}_entladung"] = round(entladung_kwh, 1)

            # Gesamtaktivität
            if ladung_eid or entladung_eid:
                total = (ladung_kwh or 0) + (entladung_kwh or 0)
                if total > 0:
                    result[comp_key] = round(total, 1)
            elif _is_energy_sensor(entity_id, sensor_units):
                kwh = _energy_delta(entity_id, history, sensor_units)
                if kwh is not None:
                    result[comp_key] = round(abs(kwh), 1)
            else:
                kwh = trapez_kwh(pts)
                if kwh is not None:
                    result[comp_key] = round(abs(kwh), 1)
        else:
            # WP/Wallbox: kWh-Sensor aus Monatsabschluss bevorzugen (#64 Follow-up)
            sep_eid = separate_kwh_sensors.get(comp_key)
            if sep_eid and sep_eid in history:
                kwh = _energy_delta(sep_eid, history, sensor_units)
            elif _is_energy_sensor(entity_id, sensor_units):
                kwh = _energy_delta(entity_id, history, sensor_units)
            else:
                kwh = trapez_kwh(pts)
            if kwh is not None:
                result[comp_key] = round(abs(kwh), 1)

    return result


async def safe_get_tages_kwh(
    anlage: Anlage, db: AsyncSession, tage_zurueck: int,
    kwh_cache,
    inv_types: dict[str, str] | None = None,
) -> dict[str, Optional[float]]:
    """Wrapper mit Fehlerbehandlung für get_tages_kwh (HA + MQTT Fallback).

    Heute-kWh: 60s TTL-Cache (verhindert HA-History-Flood bei jedem Live-Refresh).
    Gestern-kWh: Tages-Cache (ändert sich nach Mitternacht nicht mehr).
    """
    # Cache prüfen
    if tage_zurueck == 0:
        cached = kwh_cache.get_heute(anlage.id)
        if cached is not None:
            return cached
    elif tage_zurueck >= 1:
        cached = kwh_cache.get_gestern(anlage.id)
        if cached is not None:
            return cached

    # 1. Versuche HA-History (Trapezregel)
    if HA_INTEGRATION_AVAILABLE:
        try:
            result = await get_tages_kwh(anlage, db, tage_zurueck, inv_types=inv_types)
            if result:
                if tage_zurueck == 0:
                    kwh_cache.set_heute(anlage.id, result)
                else:
                    kwh_cache.set_gestern(anlage.id, result)
                return result
        except Exception as e:
            label = "Heute" if tage_zurueck == 0 else "Gestern"
            logger.warning(f"Fehler bei {label}-kWh Berechnung (HA): {type(e).__name__}: {e}")

    # 2. Fallback: MQTT Energy Snapshots
    try:
        from backend.services.mqtt_energy_history_service import get_tages_kwh as mqtt_get_tages_kwh
        result = await mqtt_get_tages_kwh(anlage.id, tage_zurueck, inv_types=inv_types)
        if result:
            if tage_zurueck == 0:
                kwh_cache.set_heute(anlage.id, result)
            else:
                kwh_cache.set_gestern(anlage.id, result)
            return result
    except Exception as e:
        label = "Heute" if tage_zurueck == 0 else "Gestern"
        logger.debug(f"MQTT Energy History nicht verfügbar für {label}: {e}")

    return {}
