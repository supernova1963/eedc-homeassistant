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
from backend.utils.investition_filter import aktiv_jetzt
from backend.services.live_sensor_config import (
    normalize_to_w,
    extract_live_config,
    extract_quellen_live,
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
        quellen_basis: dict[str, tuple] | None = None,
        quellen_inv: dict[str, dict[str, tuple]] | None = None,
    ) -> tuple[dict[str, float], dict[str, dict[str, float]]]:
        """
        Sammelt Werte aus HA-Sensoren und MQTT-Inbound (MQTT überschreibt HA).

        `quellen_basis`/`quellen_inv` (C2a): explizite Datenquellen-Zuordnungen —
        für Felder mit Eintrag gilt GENAU die zugeordnete Quelle (kein Merge/
        Fallback); Felder ohne Eintrag bleiben dem heutigen Merge überlassen
        (Read-Through, Regressionsschutz).

        Returns:
            (basis_values, inv_values)
            basis_values: {"einspeisung_w": float, "netzbezug_w": float}
            inv_values: {inv_id: {"leistung_w": float, "soc": float}}
        """
        basis_values: dict[str, float] = {}
        inv_values: dict[str, dict[str, float]] = {}
        _basis_invert = basis_invert or {}
        _inv_invert = inv_invert_map or {}

        # 1. HA-Sensor-Werte (Prio 2). Invert wird NICHT hier angewendet, sondern
        # EINMAL am final aufgelösten Wert (Schritt 2.6) — quellen-unabhängig.
        for key, entity_id in basis_live.items():
            val = sensor_values.get(entity_id)
            if val is not None:
                basis_values[key] = val

        for inv_id, live in inv_live_map.items():
            for key, entity_id in live.items():
                val = sensor_values.get(entity_id)
                if val is not None:
                    if inv_id not in inv_values:
                        inv_values[inv_id] = {}
                    inv_values[inv_id][key] = val

        # 2. MQTT-Inbound-Werte (Prio 1 — überschreibt HA)
        from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
        mqtt_svc = get_mqtt_inbound_service()
        mqtt_basis: dict[str, float] = {}
        mqtt_inv: dict[str, dict[str, float]] = {}
        if mqtt_svc and mqtt_svc.cache.has_data(anlage.id):
            mqtt_basis = mqtt_svc.cache.get_live_basis(anlage.id)
            basis_values.update(mqtt_basis)

            mqtt_inv = mqtt_svc.cache.get_all_live_inv(anlage.id)
            for inv_id, values in mqtt_inv.items():
                if inv_id not in inv_values:
                    inv_values[inv_id] = {}
                inv_values[inv_id].update(values)

        # 2.5 Explizite Datenquellen-Zuordnungen anwenden (C2a): pro zugeordnetem
        # Feld GENAU die gewählte Quelle, ohne Merge/Fallback. Nur Felder mit
        # Eintrag werden angefasst → Anlagen ohne neue Zuordnung bleiben identisch.
        self._apply_quellen_overrides(basis_values, quellen_basis, sensor_values, mqtt_basis)
        for inv_id, keys in (quellen_inv or {}).items():
            d = inv_values.get(inv_id) or {}
            self._apply_quellen_overrides(d, keys, sensor_values, mqtt_inv.get(inv_id) or {})
            if d:
                inv_values[inv_id] = d
            else:
                inv_values.pop(inv_id, None)

        # 2.6 Vereinheitlichter Invert (Datenquellen-V4-SoT): Vorzeichen-Flip EINMAL
        # am final aufgelösten Wert — quellen-unabhängig, egal ob der Wert aus HA,
        # MQTT-Inbound oder MQTT-Gateway stammt (Gateway invertiert NICHT mehr im
        # Republish-Transform). `_basis_invert`/`_inv_invert` kommen aus
        # `extract_live_config` = Union(Store `sensor_mapping.invertieren`,
        # Legacy `live_invert`). VOR dem netz_kombi-Split (Schritt 3), damit ein
        # invertierter Kombi-Netzsensor mit korrektem Vorzeichen gesplittet wird.
        for key in _basis_invert:
            if basis_values.get(key) is not None:
                basis_values[key] = -basis_values[key]
        for inv_id, keys in _inv_invert.items():
            d = inv_values.get(inv_id)
            if not d:
                continue
            for key in keys:
                if d.get(key) is not None:
                    d[key] = -d[key]

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

    @staticmethod
    def _resolve_quelle_value(quelle, entity_id, sensor_values, mqtt_val):
        """Wert der EINEN zugeordneten Quelle (C2a) — kein Fallback auf andere Quellen.

        HA (ha_app/ha_connector): der (W-normalisierte) HA-State der Entity.
        MQTT-Inbound/-Gateway: der Inbound-Cache-Wert (Gateway fließt nach dem
        ziel_key-Fix ebenfalls durch den Inbound-Cache). „keine": None (Feld leer).

        Vorzeichen-Invert ist NICHT hier — er ist quellen-unabhängig im
        vereinheitlichten `sensor_mapping.invertieren`-Store und wird als finaler
        Pass in `_collect_values` (Schritt 2.6) angewendet.
        """
        if quelle in ("ha_app", "ha_connector"):
            return sensor_values.get(entity_id) if entity_id else None
        if quelle in ("mqtt_inbound_standard", "mqtt_gateway"):
            return mqtt_val
        return None  # "keine" oder unbekannt → kein Wert

    def _apply_quellen_overrides(self, values, overrides, sensor_values, mqtt_values):
        """Setzt/entfernt je zugeordnetem Feld den Wert der gewählten Quelle (in-place).

        Invert bleibt hier außen vor — er wird quellen-unabhängig im finalen Pass
        (`_collect_values` Schritt 2.6) auf den Endwert angewendet.
        """
        if not overrides:
            return
        for key, tup in overrides.items():
            quelle, entity_id = tup[0], tup[1]
            val = self._resolve_quelle_value(
                quelle, entity_id, sensor_values, mqtt_values.get(key)
            )
            if val is None:
                values.pop(key, None)
            else:
                values[key] = val

    async def _fetch_ha_states(self, db: AsyncSession, entity_ids: set) -> dict:
        """W-normalisierte States einer Entity-Menge über die aktive HA-Verbindung.

        Nutzt den zentralen `resolve_ha_connection` (Supervisor ODER Remote-HA)
        und holt **genau** die gebrauchten Entities über `fetch_selected_states`
        — nicht mehr den Voll-Dump `/api/states`. Dieselbe Begründung wie im
        Supervisor-Pfad (`ha_state_service`): der Dump kostet auf einer
        gewachsenen Instanz Megabytes, und beide Pfade hängen am 5-s-Poll des
        Live-Cockpits. Einen von beiden zu heilen wäre kein Fix gewesen.

        Nur für explizit zugeordnete quellen-HA-Entities (C2a); der alte
        sensor_mapping-Pfad bleibt Supervisor-gebunden.
        """
        if not entity_ids:
            return {}
        from backend.services.ha_connection import resolve_ha_connection
        from backend.services.ha_state_service import fetch_selected_states
        api_url, token, _ = await resolve_ha_connection(db)
        if not api_url or not token:
            return {}
        roh = await fetch_selected_states(api_url, token, list(entity_ids))
        out: dict = {}
        for eid, st in roh.items():
            if not st:
                continue
            attrs = st.get("attributes", {}) or {}
            unit = attrs.get("unit_of_measurement", "")
            try:
                out[eid] = normalize_to_w(float(st.get("state")), unit)
            except (ValueError, TypeError):
                out[eid] = None
        return out

    async def get_live_data(self, anlage: Anlage, db: AsyncSession) -> dict:
        """
        Holt Live-Daten für eine Anlage.

        Quellen: MQTT-Inbound (Prio 1), HA State Service (Prio 2).
        Returns:
            dict mit Komponenten, Gauges, Summen und Metadaten.
        """
        basis_live, inv_live_map, basis_invert, inv_invert_map = extract_live_config(anlage)
        # C2a: explizite Datenquellen-Zuordnungen der Live-Felder (Read-Through).
        quellen_basis, quellen_inv, quellen_ha = extract_quellen_live(anlage)

        # Prüfe ob MQTT-Daten vorliegen (auch ohne sensor_mapping)
        from backend.services.mqtt_inbound_service import get_mqtt_inbound_service
        mqtt_svc = get_mqtt_inbound_service()
        has_mqtt = mqtt_svc and mqtt_svc.cache.has_data(anlage.id)

        if (not basis_live and not inv_live_map and not has_mqtt
                and not quellen_basis and not quellen_inv):
            return self._empty_response(anlage)

        # Investitionen aus DB laden
        result = await db.execute(
            select(Investition).where(
                Investition.anlage_id == anlage.id,
                aktiv_jetzt(),
            )
        )
        investitionen = {str(inv.id): inv for inv in result.scalars().all()}

        # HA-Sensor-Werte abrufen (alte sensor_mapping-Entities + explizit
        # zugeordnete quellen-HA-Entities).
        all_entity_ids: set[str] = set(quellen_ha)
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

        # C2a: explizit zugeordnete HA-Entities auch OHNE Supervisor lesen
        # (Remote-HA per LL-Token) — additiv, das Supervisor-Gate für den alten
        # sensor_mapping-Pfad bleibt unberührt (Remote dafür = P3).
        if quellen_ha and not HA_INTEGRATION_AVAILABLE:
            remote = await self._fetch_ha_states(db, quellen_ha)
            for entity_id, val in remote.items():
                if val is not None:
                    sensor_values[entity_id] = val

        # Werte aus HA + MQTT zusammenführen (+ explizite quellen-Overrides, C2a)
        basis_values, inv_values = self._collect_values(
            anlage, basis_live, inv_live_map, sensor_values,
            basis_invert, inv_invert_map,
            quellen_basis, quellen_inv,
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
            # #263 — reine Anzeige je Innengerät, ohne Auswertung. `None` statt
            # leerer Liste, wo nichts ankommt: die Fläche zeigt den Block dann
            # gar nicht, statt leere Zeilen zu stellen.
            "innengeraete": build_result.get("innengeraete") or None,
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
            "innengeraete": None,
        }

    @staticmethod
    def _calc_tages_ev_hv(
        kwh: dict[str, Optional[float]],
    ) -> tuple[Optional[float], Optional[float]]:
        """Berechnet Eigenverbrauch und Hausverbrauch aus Tages-kWh inkl. Batterie.

        **Eine Regel für beide Werte** (KONZEPT-UNVOLLSTAENDIGE-WERTE §3): jeder
        Wert wird genau dann geliefert, wenn **seine eigenen** Summanden vorliegen.
        Beide sind Differenzen bzw. bauen auf einer auf — ihre Fehlerrichtung hängt
        davon ab, *welcher* Summand fehlt, also wird eine Lücke unterdrückt und
        nicht als 0 eingesetzt. Die Leitfrage ist nie „ist irgendein Sensor
        ausgefallen", sondern „braucht *dieser* Wert den fehlenden Sensor".

        Vorher galten hier drei verschiedene Regeln nebeneinander: PV/Einspeisung
        → beide Werte weg, Batterie-Lücke → still 0, Netzbezug-Lücke → `bezug or 0`
        und damit ein Hausverbrauch, der ohne Kennzeichnung zu niedrig war.

        Returns:
            (eigenverbrauch, hausverbrauch) — jeweils Optional[float]
        """
        pv = kwh.get("pv")
        einsp = kwh.get("einspeisung")
        bezug = kwh.get("netzbezug")

        # Batterie-Ladung/-Entladung summieren (Keys: batterie_X_ladung, batterie_X_entladung).
        # `is not None` statt `and v`: eine gemessene 0 ist eine Aussage, keine Lücke.
        bat_ladung = sum(
            v for k, v in kwh.items() if k.endswith("_ladung") and v is not None
        )
        bat_entladung = sum(
            v for k, v in kwh.items() if k.endswith("_entladung") and v is not None
        )

        # Eigenverbrauch = (PV − Einspeisung − Ladung) + Entladung.
        eigenverbrauch: Optional[float] = None
        if pv is not None and einsp is not None:
            direktverbrauch = max(0, pv - einsp - bat_ladung)
            eigenverbrauch = round(direktverbrauch + bat_entladung, 1)

        # Hausverbrauch = Eigenverbrauch + Netzbezug — beide Summanden nötig.
        hausverbrauch: Optional[float] = None
        if eigenverbrauch is not None and bezug is not None:
            hausverbrauch = round(eigenverbrauch + bezug, 1)

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
