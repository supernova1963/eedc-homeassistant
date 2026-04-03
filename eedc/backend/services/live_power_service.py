"""
Live Power Service - Sammelt aktuelle Leistungswerte aus verfügbaren Quellen.

Datenquellen-Priorität:
  1. MQTT-Inbound Cache (universell, jedes Smarthome)
  2. HA State Service (HA Add-on, sensor_mapping)

MQTT-Inbound überschreibt HA-Werte wo vorhanden.

Sensor-Mapping Struktur (für HA-Modus):
  basis.live: {einspeisung_w: entity_id, netzbezug_w: entity_id}
  investitionen[id].live: {leistung_w: entity_id, soc: entity_id}

MQTT Topic-Struktur (mit sprechenden Namen):
  eedc/{id}_{name}/live/einspeisung_w
  eedc/{id}_{name}/live/netzbezug_w
  eedc/{id}_{name}/live/inv/{id}_{name}/leistung_w
  eedc/{id}_{name}/live/inv/{id}_{name}/soc
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import HA_INTEGRATION_AVAILABLE
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.live_sensor_config import (
    normalize_to_w,
    extract_live_config,
)
from backend.services.live_history_service import safe_get_tages_kwh


class LivePowerService:
    """Sammelt aktuelle Leistungswerte aus verfügbaren Quellen."""

    def __init__(self):
        from backend.services.live_kwh_cache import LiveKwhCache
        self._kwh_cache = LiveKwhCache()

    def _collect_values(
        self, anlage: Anlage,
        basis_live: dict[str, str],
        inv_live_map: dict[str, dict[str, str]],
        sensor_values: dict[str, Optional[float]],
        basis_invert: dict[str, bool] | None = None,
        inv_invert_map: dict[str, dict[str, bool]] | None = None,
    ) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
        """
        Sammelt Werte aus HA-Sensoren und MQTT-Inbound (MQTT überschreibt HA).

        Returns:
            (basis_values, inv_values)
            basis_values: {"einspeisung_w": float, "netzbezug_w": float}
            inv_values: {inv_id: {"leistung_w": float, "soc": float}}
        """
        basis_values: dict[str, float] = {}
        inv_values: dict[str, dict[str, float]] = {}
        _basis_invert = basis_invert or {}
        _inv_invert = inv_invert_map or {}

        # 1. HA-Sensor-Werte (Prio 2)
        for key, entity_id in basis_live.items():
            val = sensor_values.get(entity_id)
            if val is not None:
                if _basis_invert.get(key):
                    val = -val
                basis_values[key] = val

        for inv_id, live in inv_live_map.items():
            for key, entity_id in live.items():
                val = sensor_values.get(entity_id)
                if val is not None:
                    if _inv_invert.get(inv_id, {}).get(key):
                        val = -val
                    if inv_id not in inv_values:
                        inv_values[inv_id] = {}
                    inv_values[inv_id][key] = val

        # 2. MQTT-Inbound-Werte (Prio 1 — überschreibt HA)
        from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
        mqtt_svc = get_mqtt_inbound_service()
        if mqtt_svc and mqtt_svc.cache.has_data(anlage.id):
            mqtt_basis = mqtt_svc.cache.get_live_basis(anlage.id)
            basis_values.update(mqtt_basis)

            mqtt_inv = mqtt_svc.cache.get_all_live_inv(anlage.id)
            for inv_id, values in mqtt_inv.items():
                if inv_id not in inv_values:
                    inv_values[inv_id] = {}
                inv_values[inv_id].update(values)

        # 3. Kombinierten Netz-Sensor auflösen (positiv=Bezug, negativ=Einspeisung)
        netz_kombi = basis_values.pop("netz_kombi_w", None)
        if netz_kombi is not None and "einspeisung_w" not in basis_values and "netzbezug_w" not in basis_values:
            if netz_kombi >= 0:
                basis_values["netzbezug_w"] = netz_kombi
                basis_values["einspeisung_w"] = 0.0
            else:
                basis_values["einspeisung_w"] = abs(netz_kombi)
                basis_values["netzbezug_w"] = 0.0

        return basis_values, inv_values

    async def get_live_data(self, anlage: Anlage, db: AsyncSession) -> dict:
        """
        Holt Live-Daten für eine Anlage.

        Quellen: MQTT-Inbound (Prio 1), HA State Service (Prio 2).
        Returns:
            dict mit Komponenten, Gauges, Summen und Metadaten.
        """
        basis_live, inv_live_map, basis_invert, inv_invert_map = extract_live_config(anlage)

        # Prüfe ob MQTT-Daten vorliegen (auch ohne sensor_mapping)
        from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
        mqtt_svc = get_mqtt_inbound_service()
        has_mqtt = mqtt_svc and mqtt_svc.cache.has_data(anlage.id)

        if not basis_live and not inv_live_map and not has_mqtt:
            return self._empty_response(anlage)

        # Investitionen aus DB laden
        result = await db.execute(
            select(Investition).where(
                Investition.anlage_id == anlage.id,
                Investition.aktiv == True,
            )
        )
        investitionen = {str(inv.id): inv for inv in result.scalars().all()}

        # HA-Sensor-Werte abrufen
        all_entity_ids: set[str] = set()
        for eid in basis_live.values():
            if eid:
                all_entity_ids.add(eid)
        for live in inv_live_map.values():
            for eid in live.values():
                if eid:
                    all_entity_ids.add(eid)

        sensor_values: dict[str, Optional[float]] = {}
        if all_entity_ids and HA_INTEGRATION_AVAILABLE:
            from backend.services.ha_state_service import get_ha_state_service
            ha_service = get_ha_state_service()
            # Batch-Abruf: 1 HTTP-Call statt N einzelne
            batch_result = await ha_service.get_sensor_states_batch(list(all_entity_ids))
            for entity_id in all_entity_ids:
                state = batch_result.get(entity_id)
                if state is not None:
                    value, unit = state
                    # Automatische Einheiten-Konvertierung zu W
                    # HA gibt den State in suggested_unit zurück (z.B. kW statt W)
                    sensor_values[entity_id] = normalize_to_w(value, unit)
                else:
                    sensor_values[entity_id] = None

        # Werte aus HA + MQTT zusammenführen
        basis_values, inv_values = self._collect_values(
            anlage, basis_live, inv_live_map, sensor_values,
            basis_invert, inv_invert_map,
        )

        # Komponenten + Gauges aufbauen
        from backend.services.live_komponenten_builder import build_komponenten
        build_result = build_komponenten(
            anlage, basis_values, inv_values, investitionen, inv_live_map,
        )
        komponenten = build_result["komponenten"]
        gauges = build_result["gauges"]
        pv_total_w = build_result["pv_total_w"]
        warmwasser_temperatur_c = build_result["warmwasser_temperatur_c"]


        # Tages-kWh berechnen (inv_types durchreichen um DB-Queries zu sparen)
        inv_types = {str(inv.id): inv.typ for inv in investitionen.values()}
        heute_kwh = await safe_get_tages_kwh(anlage, db, 0, self._kwh_cache, inv_types=inv_types)
        gestern_kwh = await safe_get_tages_kwh(anlage, db, 1, self._kwh_cache, inv_types=inv_types)

        heute_pv = heute_kwh.get("pv")
        heute_einsp = heute_kwh.get("einspeisung")
        heute_bezug = heute_kwh.get("netzbezug")
        heute_ev, heute_hv = self._calc_tages_ev_hv(heute_kwh)

        gestern_pv = gestern_kwh.get("pv")
        gestern_einsp = gestern_kwh.get("einspeisung")
        gestern_bezug = gestern_kwh.get("netzbezug")
        gestern_ev, gestern_hv = self._calc_tages_ev_hv(gestern_kwh)

        # Per-Komponente Heute-kWh für Tooltips im Energiefluss
        heute_pro_komp: dict[str, float] = {}
        for key, val in heute_kwh.items():
            if key in ("pv", "einspeisung", "netzbezug"):
                continue  # Aggregat-Kategorien überspringen
            if val is not None:
                heute_pro_komp[key] = val
        # Netz: Bezug + Einspeisung separat
        if heute_bezug is not None:
            heute_pro_komp["netz_bezug"] = heute_bezug
        if heute_einsp is not None:
            heute_pro_komp["netz_einspeisung"] = heute_einsp
        # Haushalt = Eigenverbrauch + Netzbezug (abzüglich Batterie)
        if heute_hv is not None:
            heute_pro_komp["haushalt"] = heute_hv

        return {
            "anlage_id": anlage.id,
            "anlage_name": anlage.anlagenname,
            "zeitpunkt": datetime.now().isoformat(),
            "verfuegbar": len(komponenten) > 0,
            "komponenten": komponenten,
            "summe_erzeugung_kw": build_result["summe_erzeugung_kw"],
            "summe_verbrauch_kw": build_result["summe_verbrauch_kw"],
            "summe_pv_kw": round(pv_total_w / 1000, 3),
            "gauges": gauges,
            "heute_pv_kwh": heute_pv,
            "heute_einspeisung_kwh": heute_einsp,
            "heute_netzbezug_kwh": heute_bezug,
            "heute_eigenverbrauch_kwh": heute_ev,
            "gestern_pv_kwh": gestern_pv,
            "gestern_einspeisung_kwh": gestern_einsp,
            "gestern_netzbezug_kwh": gestern_bezug,
            "gestern_eigenverbrauch_kwh": gestern_ev,
            "heute_kwh_pro_komponente": heute_pro_komp or None,
            "warmwasser_temperatur_c": warmwasser_temperatur_c,
        }

    def _empty_response(self, anlage: Anlage) -> dict:
        """Leere Antwort wenn keine Live-Sensoren konfiguriert."""
        return {
            "anlage_id": anlage.id,
            "anlage_name": anlage.anlagenname,
            "zeitpunkt": datetime.now().isoformat(),
            "verfuegbar": False,
            "komponenten": [],
            "summe_erzeugung_kw": 0,
            "summe_verbrauch_kw": 0,
            "summe_pv_kw": 0,
            "gauges": [],
            "heute_pv_kwh": None,
            "heute_einspeisung_kwh": None,
            "heute_netzbezug_kwh": None,
            "heute_eigenverbrauch_kwh": None,
            "gestern_pv_kwh": None,
            "gestern_einspeisung_kwh": None,
            "gestern_netzbezug_kwh": None,
            "gestern_eigenverbrauch_kwh": None,
            "heute_kwh_pro_komponente": None,
            "warmwasser_temperatur_c": None,
        }

    @staticmethod
    def _calc_tages_ev_hv(
        kwh: dict[str, Optional[float]],
    ) -> tuple[Optional[float], Optional[float]]:
        """Berechnet Eigenverbrauch und Hausverbrauch aus Tages-kWh inkl. Batterie.

        Returns:
            (eigenverbrauch, hausverbrauch) — jeweils Optional[float]
        """
        pv = kwh.get("pv")
        einsp = kwh.get("einspeisung")
        bezug = kwh.get("netzbezug")
        if pv is None or einsp is None:
            return None, None

        # Batterie-Ladung/-Entladung summieren (Keys: batterie_X_ladung, batterie_X_entladung)
        bat_ladung = sum(v for k, v in kwh.items() if k.endswith("_ladung") and v)
        bat_entladung = sum(v for k, v in kwh.items() if k.endswith("_entladung") and v)

        direktverbrauch = max(0, pv - einsp - bat_ladung)
        eigenverbrauch = round(direktverbrauch + bat_entladung, 1)
        hausverbrauch = round(eigenverbrauch + (bezug or 0), 1) if bezug is not None or eigenverbrauch > 0 else None
        return eigenverbrauch, hausverbrauch

    async def get_tagesverlauf(
        self, anlage: Anlage, db: AsyncSession, tage_zurueck: int = 0,
    ) -> dict:
        """Delegiert an live_tagesverlauf_service."""
        from backend.services.live_tagesverlauf_service import (
            get_tagesverlauf as _get_tv,
        )
        return await _get_tv(anlage, db, tage_zurueck)


    # ── Individuelles Verbrauchsprofil (delegiert an live_verbrauchsprofil_service) ──

    async def get_verbrauchsprofil(
        self, anlage: Anlage, db: AsyncSession
    ) -> Optional[dict]:
        """Delegiert an live_verbrauchsprofil_service."""
        from backend.services.live_verbrauchsprofil_service import (
            get_verbrauchsprofil as _get_vp,
        )
        return await _get_vp(anlage, db, self._kwh_cache)


# Singleton
_live_power_service: Optional[LivePowerService] = None


def get_live_power_service() -> LivePowerService:
    """Gibt die Singleton-Instanz zurück."""
    global _live_power_service
    if _live_power_service is None:
        _live_power_service = LivePowerService()
    return _live_power_service
