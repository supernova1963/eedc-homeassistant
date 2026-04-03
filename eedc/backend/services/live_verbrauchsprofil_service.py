"""
Verbrauchsprofil-Service — stündliches Verbrauchsprofil aus HA-History oder MQTT.

Ausgelagert aus live_power_service.py (Schritt 4 des Refactorings).
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
    ERZEUGER_TYPEN,
    extract_live_config,
)
from backend.services.live_history_service import (
    get_history_normalized,
    apply_invert_to_history,
)

logger = logging.getLogger(__name__)


async def get_verbrauchsprofil(
    anlage: Anlage, db: AsyncSession, kwh_cache,
) -> Optional[dict]:
    """
    Berechnet ein individuelles stündliches Verbrauchsprofil aus den letzten 14 Tagen,
    getrennt nach Werktag (Mo-Fr) und Wochenende (Sa-So).

    Datenquellen (Priorität):
      1. HA-History (Leistungs-Sensoren → Stundenmittel in kW)
      2. MQTT Energy Snapshots (kumulative kWh → stündliche Deltas)

    Verbrauch pro Stunde = PV + Netzbezug - Einspeisung

    Returns:
        {
            "werktag": {0: kW, 1: kW, ..., 23: kW},
            "wochenende": {0: kW, 1: kW, ..., 23: kW},
            "tage_werktag": int,
            "tage_wochenende": int,
            "quelle": "ha" | "mqtt",
        }
        oder None wenn keine History verfügbar.
    """
    # Cache prüfen (unterscheidet "nicht gecacht" von "gecacht als keine Daten")
    cache = kwh_cache.get_profil(anlage.id)
    if cache is not None:
        if cache is kwh_cache.PROFIL_UNAVAILABLE:
            logger.info("Verbrauchsprofil Anlage %s: Cache-Hit (keine Daten)", anlage.id)
            return None
        logger.info(
            "Verbrauchsprofil Anlage %s: Cache-Hit (ok, quelle=%s)",
            anlage.id, cache.get("quelle"),
        )
        return cache

    # 1. Versuche HA-History
    result = await _profil_from_ha(anlage, db)
    logger.info(
        "Verbrauchsprofil Anlage %s: HA=%s",
        anlage.id,
        "None" if result is None else f"ok(quelle={result.get('quelle')},wt={result.get('tage_werktag')})",
    )

    # 2. Fallback: MQTT Energy Snapshots
    if result is None:
        result = await _profil_from_mqtt(anlage.id)
        logger.info(
            "Verbrauchsprofil Anlage %s: MQTT=%s",
            anlage.id,
            "None" if result is None else f"ok(wt={result.get('tage_werktag')},we={result.get('tage_wochenende')})",
        )

    # IMMER cachen — auch None, damit der teure Timeout sich nicht wiederholt
    kwh_cache.set_profil(anlage.id, result)

    return result


async def _profil_from_ha(
    anlage: Anlage, db: AsyncSession
) -> Optional[dict]:
    """Verbrauchsprofil aus HA-History (Leistungs-Sensoren, kW-Mittelwerte)."""
    if not HA_INTEGRATION_AVAILABLE:
        return None

    basis_live, inv_live_map, basis_invert, inv_invert_map = extract_live_config(anlage)

    einsp_eid = basis_live.get("einspeisung_w")
    bezug_eid = basis_live.get("netzbezug_w")
    kombi_eid = basis_live.get("netz_kombi_w")
    # Kombinierter Sensor als Fallback
    if not einsp_eid and not bezug_eid and kombi_eid:
        pass  # Kombi-Sensor wird unten behandelt
    elif not einsp_eid and not bezug_eid:
        return None

    # PV-Entity-IDs
    inv_result = await db.execute(
        select(Investition.id, Investition.typ).where(
            Investition.anlage_id == anlage.id, Investition.aktiv == True
        )
    )
    inv_types = {str(row[0]): row[1] for row in inv_result.all()}

    pv_eids: list[str] = []
    wp_eids: list[str] = []
    for inv_id, live in inv_live_map.items():
        typ = inv_types.get(inv_id)
        if typ in ERZEUGER_TYPEN and live.get("leistung_w"):
            pv_eids.append(live["leistung_w"])
        elif typ == "waermepumpe" and live.get("leistung_w"):
            wp_eids.append(live["leistung_w"])

    # PV Gesamt aus Basis als Fallback
    if not pv_eids and basis_live.get("pv_gesamt_w"):
        pv_eids.append(basis_live["pv_gesamt_w"])

    temp_eid = basis_live.get("aussentemperatur_c")

    now = datetime.now()
    start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)

    all_ids = list(set(filter(None, [einsp_eid, bezug_eid, kombi_eid] + pv_eids + wp_eids + ([temp_eid] if temp_eid else []))))
    history, _ = await get_history_normalized(all_ids, start, now)

    # Vorzeichen-Invertierung auf History anwenden (#58)
    apply_invert_to_history(
        history, basis_live, basis_invert, inv_live_map, inv_invert_map
    )

    if not history:
        return None

    werktag_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    wochenende_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    wp_werktag_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    wp_wochenende_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    werktage_set: set[str] = set()
    wochenende_set: set[str] = set()
    temp_werte: list[float] = []

    for day_offset in range(7):
        tag = start + timedelta(days=day_offset)
        tag_str = tag.strftime("%Y-%m-%d")
        ist_wochenende = tag.weekday() >= 5

        for h in range(24):
            h_start = tag.replace(hour=h, minute=0, second=0)
            h_end = h_start + timedelta(hours=1)
            if h_end > now:
                break

            pv_kw = 0.0
            for eid in pv_eids:
                pts = history.get(eid, [])
                h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
                if h_pts:
                    pv_kw += sum(h_pts) / len(h_pts) / 1000

            bezug_kw = 0.0
            einsp_kw = 0.0
            if kombi_eid and not bezug_eid and not einsp_eid:
                pts = history.get(kombi_eid, [])
                h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
                if h_pts:
                    avg_w = sum(h_pts) / len(h_pts)
                    if avg_w >= 0:
                        bezug_kw = avg_w / 1000
                    else:
                        einsp_kw = abs(avg_w) / 1000
            else:
                if bezug_eid:
                    pts = history.get(bezug_eid, [])
                    h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
                    if h_pts:
                        bezug_kw = sum(h_pts) / len(h_pts) / 1000

                if einsp_eid:
                    pts = history.get(einsp_eid, [])
                    h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
                    if h_pts:
                        einsp_kw = sum(h_pts) / len(h_pts) / 1000

            verbrauch_kw = max(0, pv_kw + bezug_kw - einsp_kw)

            wp_kw = 0.0
            for eid in wp_eids:
                pts = history.get(eid, [])
                h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
                if h_pts:
                    wp_kw += abs(sum(h_pts) / len(h_pts)) / 1000

            if temp_eid:
                pts = history.get(temp_eid, [])
                h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
                if h_pts:
                    temp_werte.append(sum(h_pts) / len(h_pts))

            if ist_wochenende:
                wochenende_sums[h].append(verbrauch_kw)
                wp_wochenende_sums[h].append(wp_kw)
                wochenende_set.add(tag_str)
            else:
                werktag_sums[h].append(verbrauch_kw)
                wp_werktag_sums[h].append(wp_kw)
                werktage_set.add(tag_str)

    referenz_temp_c = round(sum(temp_werte) / len(temp_werte), 1) if temp_werte else None

    return _build_profil_result(
        werktag_sums, wochenende_sums, werktage_set, wochenende_set, "ha",
        wp_werktag_sums=wp_werktag_sums if wp_eids else None,
        wp_wochenende_sums=wp_wochenende_sums if wp_eids else None,
        referenz_temp_c=referenz_temp_c,
    )


async def _profil_from_mqtt(anlage_id: int) -> Optional[dict]:
    """
    Verbrauchsprofil aus MQTT Energy Snapshots (kumulative kWh → stündliche Deltas).

    Die Snapshots enthalten kumulative Monatswerte (pv_gesamt_kwh, einspeisung_kwh,
    netzbezug_kwh) alle 5 Minuten. Für jede Stunde berechnen wir das Delta und
    daraus den durchschnittlichen Verbrauch in kW (= kWh/h).
    """
    from backend.core.database import get_session
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot

    now = datetime.now()
    start = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)

    # Alle Snapshots der letzten 7 Tage laden
    async with get_session() as session:
        result = await session.execute(
            select(
                MqttEnergySnapshot.timestamp,
                MqttEnergySnapshot.energy_key,
                MqttEnergySnapshot.value_kwh,
            ).where(
                MqttEnergySnapshot.anlage_id == anlage_id,
                MqttEnergySnapshot.timestamp >= start,
            ).order_by(MqttEnergySnapshot.timestamp)
        )
        rows = result.all()

    if not rows:
        return None

    # Snapshots nach Zeitpunkt gruppieren: {timestamp: {key: value}}
    snapshots: dict[datetime, dict[str, float]] = {}
    for ts, key, val in rows:
        if ts not in snapshots:
            snapshots[ts] = {}
        snapshots[ts][key] = val

    sorted_times = sorted(snapshots.keys())
    if len(sorted_times) < 2:
        return None

    # Relevante Keys
    pv_key = "pv_gesamt_kwh"
    einsp_key = "einspeisung_kwh"
    bezug_key = "netzbezug_kwh"

    werktag_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    wochenende_sums: dict[int, list[float]] = {h: [] for h in range(24)}
    werktage_set: set[str] = set()
    wochenende_set: set[str] = set()

    for day_offset in range(7):
        tag = start + timedelta(days=day_offset)
        tag_str = tag.strftime("%Y-%m-%d")
        ist_wochenende = tag.weekday() >= 5

        for h in range(24):
            h_start = tag.replace(hour=h, minute=0, second=0)
            h_end = h_start + timedelta(hours=1)
            if h_end > now:
                break

            # Snapshots in dieser Stunde finden
            hour_snaps = [
                snapshots[t] for t in sorted_times
                if h_start <= t < h_end
            ]
            if len(hour_snaps) < 2:
                continue

            # Delta: letzter - erster Snapshot der Stunde
            first = hour_snaps[0]
            last = hour_snaps[-1]

            def delta(key: str, _first=first, _last=last) -> float:
                v_end = _last.get(key)
                v_start = _first.get(key)
                if v_end is None or v_start is None:
                    return 0.0
                d = v_end - v_start
                return max(0, d)  # Negative Deltas = Counter-Reset → ignorieren

            pv_kwh = delta(pv_key)
            bezug_kwh = delta(bezug_key)
            einsp_kwh = delta(einsp_key)

            # Verbrauch in kWh für diese Stunde, ≈ kW (da 1h Intervall)
            verbrauch_kw = max(0, pv_kwh + bezug_kwh - einsp_kwh)

            if ist_wochenende:
                wochenende_sums[h].append(verbrauch_kw)
                wochenende_set.add(tag_str)
            else:
                werktag_sums[h].append(verbrauch_kw)
                werktage_set.add(tag_str)

    return _build_profil_result(
        werktag_sums, wochenende_sums, werktage_set, wochenende_set, "mqtt"
    )


def _build_profil_result(
    werktag_sums: dict[int, list[float]],
    wochenende_sums: dict[int, list[float]],
    werktage_set: set[str],
    wochenende_set: set[str],
    quelle: str,
    wp_werktag_sums: Optional[dict[int, list[float]]] = None,
    wp_wochenende_sums: Optional[dict[int, list[float]]] = None,
    referenz_temp_c: Optional[float] = None,
) -> Optional[dict]:
    """Baut das Profil-Ergebnis aus den gesammelten Stundenwerten."""
    tage_wt = len(werktage_set)
    tage_we = len(wochenende_set)

    if tage_wt < 2 and tage_we < 2:
        return None

    def avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 3) if values else 0.0

    # Nur Stunden mit echten Daten aufnehmen (keine 0.0 für fehlende History)
    def build_profil(sums: dict[int, list[float]]) -> dict[int, float]:
        return {h: avg(sums[h]) for h in range(24) if sums[h]}

    result: dict = {
        "werktag": build_profil(werktag_sums) if tage_wt >= 2 else None,
        "wochenende": build_profil(wochenende_sums) if tage_we >= 2 else None,
        "tage_werktag": tage_wt,
        "tage_wochenende": tage_we,
        "quelle": quelle,
    }

    if wp_werktag_sums is not None:
        result["wp_werktag"] = build_profil(wp_werktag_sums) if tage_wt >= 2 else None
        result["wp_wochenende"] = build_profil(wp_wochenende_sums) if tage_we >= 2 else None

    if referenz_temp_c is not None:
        result["referenz_temp_c"] = referenz_temp_c

    return result
