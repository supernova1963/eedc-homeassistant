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
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import HA_INTEGRATION_AVAILABLE
from backend.models.anlage import Anlage
from backend.models.investition import Investition


# Einheiten-Konvertierung: HA gibt State in suggested_unit zurück (z.B. kW statt W).
# Wir normalisieren alles zu W, damit die Berechnung einheitlich ist.
_UNIT_TO_W: dict[str, float] = {
    "W": 1.0,
    "kW": 1000.0,
    "MW": 1_000_000.0,
}


def _normalize_to_w(value: float, unit: str) -> float:
    """Konvertiert einen Leistungswert in W basierend auf der HA-Einheit.

    SoC (%) und unbekannte Einheiten werden unverändert durchgereicht.
    """
    factor = _UNIT_TO_W.get(unit)
    if factor is not None:
        return value * factor
    # Nicht-Leistungseinheiten (%, °C, etc.) unverändert lassen
    return value


# Icon-Zuordnung pro Investitionstyp
_TYP_ICON = {
    "pv-module": "sun",
    "balkonkraftwerk": "sun",
    "speicher": "battery",
    "e-auto": "car",
    "wallbox": "plug",
    "waermepumpe": "flame",
    "sonstiges": "wrench",
    "wechselrichter": "zap",
}

# Investitionstypen die als Erzeuger zählen
_ERZEUGER_TYPEN = {"pv-module", "balkonkraftwerk"}

# Bidirektionale Typen (positiv = Ladung/Verbrauch, negativ = Entladung/Erzeugung)
_BIDIREKTIONAL_TYPEN = {"speicher"}

# Typen die SoC-Gauges bekommen
_SOC_TYPEN = {"speicher", "e-auto"}

# Typen die im Live-Dashboard übersprungen werden (Durchleiter, keine eigene Messgröße)
_SKIP_TYPEN = {"wechselrichter"}

# Kategorien für Tagesverlauf-Aggregation (Legacy, wird noch für Live-Komponenten-Keys genutzt)
_TAGESVERLAUF_KATEGORIE = {
    "pv-module": "pv",
    "balkonkraftwerk": "pv",
    "speicher": "batterie",
    "e-auto": "eauto",
    "wallbox": "eauto",
    "waermepumpe": "waermepumpe",
    "sonstiges": "sonstige",
}

# Tagesverlauf: Kategorie + Seite (quelle/senke) + Farbe pro Investitionstyp
_TV_SERIE_CONFIG: dict[str, dict] = {
    "pv-module":       {"kategorie": "pv",          "seite": "quelle", "farbe": "#eab308", "bidirektional": False},
    "balkonkraftwerk": {"kategorie": "pv",          "seite": "quelle", "farbe": "#eab308", "bidirektional": False},
    "speicher":        {"kategorie": "batterie",    "seite": "quelle", "farbe": "#3b82f6", "bidirektional": True},
    "wallbox":         {"kategorie": "wallbox",     "seite": "senke",  "farbe": "#a855f7", "bidirektional": False},
    "e-auto":          {"kategorie": "eauto",       "seite": "senke",  "farbe": "#a855f7", "bidirektional": False},
    "waermepumpe":     {"kategorie": "waermepumpe", "seite": "senke",  "farbe": "#f97316", "bidirektional": False},
    "sonstiges":       {"kategorie": "sonstige",    "seite": "senke",  "farbe": "#64748b", "bidirektional": False},
}

# Separate Key-Prefixe für Live-Komponenten (Energiefluss)
_LIVE_KEY_PREFIX = {
    "wallbox": "wallbox",
}


class LivePowerService:
    """Sammelt aktuelle Leistungswerte aus verfügbaren Quellen."""

    @staticmethod
    async def _get_history_normalized(
        entity_ids: list[str], start: datetime, end: datetime,
    ) -> dict[str, list[tuple[datetime, float]]]:
        """Holt Sensor-History und normalisiert kW→W anhand der Einheit.

        HA gibt History-Werte in der suggested_unit zurück (z.B. kW statt W).
        Wir fragen die Einheit pro Entity einmal ab und skalieren alle Punkte.
        """
        from backend.services.ha_state_service import get_ha_state_service
        ha_service = get_ha_state_service()

        # Einheiten + History parallel-ish abfragen
        units = await ha_service.get_sensor_units(entity_ids)
        history = await ha_service.get_sensor_history(entity_ids, start, end)

        # History-Werte normalisieren
        for eid, points in history.items():
            factor = _UNIT_TO_W.get(units.get(eid, ""), None)
            if factor is not None and factor != 1.0:
                history[eid] = [(ts, val * factor) for ts, val in points]

        return history

    def _extract_live_config(self, anlage: Anlage) -> tuple[
        dict[str, str], dict[str, dict[str, str]],
        dict[str, bool], dict[str, dict[str, bool]],
    ]:
        """
        Extrahiert Live-Sensor-Konfiguration aus sensor_mapping.

        Returns:
            (basis_live, inv_live_map, basis_invert, inv_invert_map)
            basis_live: {einspeisung_w: entity_id, netzbezug_w: entity_id}
            inv_live_map: {inv_id: {leistung_w: entity_id, soc: entity_id}}
            basis_invert: {einspeisung_w: True}  — Vorzeichen invertieren
            inv_invert_map: {inv_id: {leistung_w: True}}
        """
        mapping = anlage.sensor_mapping or {}

        # Neue Struktur: basis.live + investitionen[id].live
        basis_live: dict[str, str] = {}
        inv_live_map: dict[str, dict[str, str]] = {}
        basis_invert: dict[str, bool] = {}
        inv_invert_map: dict[str, dict[str, bool]] = {}

        basis = mapping.get("basis", {})
        if isinstance(basis.get("live"), dict):
            basis_live = {k: v for k, v in basis["live"].items() if v}
        if isinstance(basis.get("live_invert"), dict):
            basis_invert = {k: v for k, v in basis["live_invert"].items() if v}

        for inv_id, inv_data in mapping.get("investitionen", {}).items():
            if isinstance(inv_data, dict) and isinstance(inv_data.get("live"), dict):
                live = {k: v for k, v in inv_data["live"].items() if v}
                if live:
                    inv_live_map[inv_id] = live
            if isinstance(inv_data, dict) and isinstance(inv_data.get("live_invert"), dict):
                invert = {k: v for k, v in inv_data["live_invert"].items() if v}
                if invert:
                    inv_invert_map[inv_id] = invert

        # Fallback: altes live_sensors-Dict (Migration)
        if not basis_live and not inv_live_map:
            legacy = mapping.get("live_sensors", {})
            if legacy:
                if legacy.get("einspeisung_w"):
                    basis_live["einspeisung_w"] = legacy["einspeisung_w"]
                if legacy.get("netzbezug_w"):
                    basis_live["netzbezug_w"] = legacy["netzbezug_w"]
                # Legacy kann nicht per-Investition aufgelöst werden,
                # aber wir loggen es als Hinweis
                if any(k not in ("einspeisung_w", "netzbezug_w") for k in legacy):
                    logger.info(
                        "Anlage %s nutzt noch legacy live_sensors — "
                        "bitte Sensor-Zuordnung im Wizard aktualisieren",
                        anlage.id,
                    )

        return basis_live, inv_live_map, basis_invert, inv_invert_map

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
        basis_live, inv_live_map, basis_invert, inv_invert_map = self._extract_live_config(anlage)

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
            for entity_id in all_entity_ids:
                result = await ha_service.get_sensor_state_with_unit(entity_id)
                if result is not None:
                    value, unit = result
                    # Automatische Einheiten-Konvertierung zu W
                    # HA gibt den State in suggested_unit zurück (z.B. kW statt W)
                    sensor_values[entity_id] = _normalize_to_w(value, unit)
                else:
                    sensor_values[entity_id] = None

        # Werte aus HA + MQTT zusammenführen
        basis_values, inv_values = self._collect_values(
            anlage, basis_live, inv_live_map, sensor_values,
            basis_invert, inv_invert_map,
        )

        # Komponenten aufbauen
        komponenten = []
        summe_erzeugung = 0.0
        summe_verbrauch = 0.0
        gauges = []
        pv_total_w = 0.0


        # Wallbox-Keys sammeln für E-Auto → Wallbox Zuordnung
        wallbox_keys: list[str] = []

        # Per-Investition Komponenten
        for inv_id, values in inv_values.items():
            inv = investitionen.get(inv_id)
            if not inv or inv.typ in _SKIP_TYPEN:
                continue

            val_w = values.get("leistung_w")

            # Wärmepumpe: getrennte Leistungswerte summieren + Icon je Betriebsmodus
            wp_icon = None
            if inv.typ == "waermepumpe":
                heizen_w = values.get("leistung_heizen_w")
                ww_w = values.get("leistung_warmwasser_w")
                if heizen_w is not None or ww_w is not None:
                    # Getrennte Werte vorhanden: Summe als Leistung (falls kein leistung_w)
                    if val_w is None:
                        val_w = (heizen_w or 0) + (ww_w or 0)
                    # Icon nach dominantem Betriebsmodus (höherer Wert gewinnt)
                    h = heizen_w or 0
                    w = ww_w or 0
                    if h > 0 or w > 0:
                        wp_icon = "heater" if h >= w else "droplets"

            if val_w is None:
                continue

            typ = inv.typ

            # E-Auto mit V2H ist bidirektional (negativ = Entladung ins Haus)
            ist_v2h = (typ == "e-auto"
                       and isinstance(inv.parameter, dict)
                       and inv.parameter.get("nutzt_v2h"))
            ist_bidirektional = typ in _BIDIREKTIONAL_TYPEN or ist_v2h

            if typ in _ERZEUGER_TYPEN:
                # PV / BKW — nur Erzeugung
                kw = val_w / 1000
                komponenten.append({
                    "key": f"pv_{inv_id}",
                    "label": inv.bezeichnung,
                    "icon": _TYP_ICON.get(typ, "sun"),
                    "erzeugung_kw": round(kw, 3),
                    "verbrauch_kw": None,
                })
                summe_erzeugung += kw
                pv_total_w += val_w

            elif ist_bidirektional:
                # Speicher / E-Auto mit V2H — bidirektional (positiv = Ladung, negativ = Entladung)
                kw = abs(val_w) / 1000
                ist_ladung = val_w > 0
                kategorie = _TAGESVERLAUF_KATEGORIE.get(typ, "batterie")
                komponenten.append({
                    "key": f"{kategorie}_{inv_id}",
                    "label": inv.bezeichnung,
                    "icon": _TYP_ICON.get(typ, "battery"),
                    "erzeugung_kw": round(kw, 3) if not ist_ladung else None,
                    "verbrauch_kw": round(kw, 3) if ist_ladung else None,
                })
                if ist_ladung:
                    summe_verbrauch += kw
                else:
                    summe_erzeugung += kw

            else:
                # Verbraucher (E-Auto ohne V2H, WP, Wallbox, Sonstige)
                kw = abs(val_w) / 1000
                prefix = _LIVE_KEY_PREFIX.get(typ, _TAGESVERLAUF_KATEGORIE.get(typ, typ))
                komp_key = f"{prefix}_{inv_id}"
                komponenten.append({
                    "key": komp_key,
                    "label": inv.bezeichnung,
                    "icon": wp_icon or _TYP_ICON.get(typ, "wrench"),
                    "erzeugung_kw": None,
                    "verbrauch_kw": round(kw, 3),
                })
                if typ == "wallbox":
                    wallbox_keys.append(komp_key)
                # E-Auto ohne V2H: NICHT in summe_verbrauch zählen
                # (Wallbox erfasst die gleiche Ladeleistung bereits)
                if typ != "e-auto":
                    summe_verbrauch += kw

            # SoC-Gauge pro Investition
            if typ in _SOC_TYPEN:
                soc_val = values.get("soc")
                if soc_val is not None:
                    gauges.append({
                        "key": f"soc_{inv_id}",
                        "label": inv.bezeichnung,
                        "wert": round(soc_val, 0),
                        "min_wert": 0,
                        "max_wert": 100,
                        "einheit": "%",
                    })

        # E-Auto → Wallbox Zuordnung (parent_key setzen)
        if wallbox_keys:
            wb_idx = 0
            for komp in komponenten:
                if komp["key"].startswith("eauto_"):
                    komp["parent_key"] = wallbox_keys[wb_idx % len(wallbox_keys)]
                    wb_idx += 1

        # PV Gesamt aus Basis (wenn kein individueller PV-Sensor vorhanden)
        has_individual_pv = any(k.key.startswith("pv_") if hasattr(k, 'key') else k.get("key", "").startswith("pv_") for k in komponenten)
        pv_gesamt_w_val = basis_values.get("pv_gesamt_w")
        if pv_gesamt_w_val is not None and not has_individual_pv:
            kw = pv_gesamt_w_val / 1000
            gesamt_kwp = anlage.leistung_kwp or 0
            komponenten.append({
                "key": "pv_gesamt",
                "label": f"PV Gesamt{f' {gesamt_kwp} kWp' if gesamt_kwp else ''}",
                "icon": "sun",
                "erzeugung_kw": round(kw, 3),
                "verbrauch_kw": None,
            })
            summe_erzeugung += kw
            pv_total_w += pv_gesamt_w_val

        # Netz-Komponente (aus Basis-Werten)
        einspeisung_w = basis_values.get("einspeisung_w")
        netzbezug_w = basis_values.get("netzbezug_w")

        if einspeisung_w is not None or netzbezug_w is not None:
            einsp_kw = (einspeisung_w or 0) / 1000
            bezug_kw = (netzbezug_w or 0) / 1000
            komponenten.append({
                "key": "netz",
                "label": "Stromnetz",
                "icon": "zap",
                "erzeugung_kw": round(bezug_kw, 3) if bezug_kw > 0 else None,
                "verbrauch_kw": round(einsp_kw, 3) if einsp_kw > 0 else None,
            })
            if bezug_kw > 0:
                summe_erzeugung += bezug_kw
            if einsp_kw > 0:
                summe_verbrauch += einsp_kw

        # Haushalt = Residual aus allen Komponenten
        # Quellen: PV, Batterie-Entladung, V2H-Entladung, Netzbezug
        # Senken: Einspeisung, Batterie-Ladung, EV-Ladung, WP, Wallbox, Sonstige
        # Kind-Komponenten (parent_key) ausschließen: Parent misst bereits die gleiche Energie
        gesamt_quellen = sum(k.get("erzeugung_kw") or 0 for k in komponenten)
        gesamt_senken = sum(
            k.get("verbrauch_kw") or 0 for k in komponenten
            if not k.get("parent_key")
        )
        if gesamt_quellen > 0 and (einspeisung_w is not None or netzbezug_w is not None):
            haushalt_kw = max(0, gesamt_quellen - gesamt_senken)

            komponenten.append({
                "key": "haushalt",
                "label": "Haushalt",
                "icon": "home",
                "erzeugung_kw": None,
                "verbrauch_kw": round(haushalt_kw, 3),
            })
            summe_verbrauch += haushalt_kw

        # Netz-Gauge
        if einspeisung_w is not None or netzbezug_w is not None:
            netto_w = (netzbezug_w or 0) - (einspeisung_w or 0)
            max_val = max(abs(einspeisung_w or 0), abs(netzbezug_w or 0), 1)
            gauges.insert(0, {
                "key": "netz",
                "label": "Netz",
                "wert": round(netto_w, 0),
                "min_wert": -max_val,
                "max_wert": max_val,
                "einheit": "W",
            })

        # PV-Leistung in % von kWp
        kwp = anlage.leistung_kwp
        if pv_total_w > 0 and kwp and kwp > 0:
            pv_pct = pv_total_w / 1000 / kwp * 100
            gauges.append({
                "key": "pv_leistung",
                "label": "PV-Leistung",
                "wert": round(min(pv_pct, 120), 0),
                "min_wert": 0,
                "max_wert": 120,
                "einheit": "% kWp",
            })

        # Autarkie + Eigenverbrauchsquote (mit Batterie-Korrektur)
        if pv_total_w > 0 and (einspeisung_w is not None or netzbezug_w is not None):
            pv_kw = pv_total_w / 1000
            # Batterie-Leistung aus Komponenten extrahieren
            bat_ladung_kw = sum(
                k.get("verbrauch_kw") or 0 for k in komponenten
                if k["key"].startswith("batterie_") or k["key"].startswith("v2h_")
            )
            bat_entladung_kw = sum(
                k.get("erzeugung_kw") or 0 for k in komponenten
                if k["key"].startswith("batterie_") or k["key"].startswith("v2h_")
            )
            direktverbrauch_kw = max(0, pv_kw - (einspeisung_w or 0) / 1000 - bat_ladung_kw)
            eigenverbrauch_kw = direktverbrauch_kw + bat_entladung_kw
            gesamt_verbrauch_kw = eigenverbrauch_kw + (netzbezug_w or 0) / 1000

            if gesamt_verbrauch_kw > 0:
                autarkie = eigenverbrauch_kw / gesamt_verbrauch_kw * 100
                gauges.append({
                    "key": "autarkie",
                    "label": "Autarkie",
                    "wert": round(min(autarkie, 100), 0),
                    "min_wert": 0,
                    "max_wert": 100,
                    "einheit": "%",
                })

            if pv_kw > 0:
                ev_quote = eigenverbrauch_kw / pv_kw * 100
                gauges.append({
                    "key": "eigenverbrauch",
                    "label": "Eigenverbr.",
                    "wert": round(min(ev_quote, 100), 0),
                    "min_wert": 0,
                    "max_wert": 100,
                    "einheit": "%",
                })

        # Warmwasser-Temperatur aus Wärmepumpen-Investitionen
        warmwasser_temperatur_c = None
        for inv_id, values in inv_values.items():
            inv = investitionen.get(inv_id)
            if inv and inv.typ == "waermepumpe":
                ww_temp = values.get("warmwasser_temperatur_c")
                if ww_temp is not None:
                    warmwasser_temperatur_c = round(ww_temp, 1)
                    break

        # Tages-kWh berechnen
        heute_kwh = await self._safe_get_tages_kwh(anlage, db, 0)
        gestern_kwh = await self._safe_get_tages_kwh(anlage, db, 1)

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
            "summe_erzeugung_kw": round(summe_erzeugung, 3),
            "summe_verbrauch_kw": round(summe_verbrauch, 3),
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

    async def _safe_get_tages_kwh(
        self, anlage: Anlage, db: AsyncSession, tage_zurueck: int
    ) -> dict[str, Optional[float]]:
        """Wrapper mit Fehlerbehandlung für _get_tages_kwh (HA + MQTT Fallback)."""
        # 1. Versuche HA-History (Trapezregel)
        if HA_INTEGRATION_AVAILABLE:
            try:
                result = await self._get_tages_kwh(anlage, db, tage_zurueck)
                if result:
                    return result
            except Exception as e:
                label = "Heute" if tage_zurueck == 0 else "Gestern"
                logger.warning(f"Fehler bei {label}-kWh Berechnung (HA): {e}")

        # 2. Fallback: MQTT Energy Snapshots
        try:
            from backend.services.mqtt_energy_history_service import get_tages_kwh
            result = await get_tages_kwh(anlage.id, tage_zurueck)
            if result:
                return result
        except Exception as e:
            label = "Heute" if tage_zurueck == 0 else "Gestern"
            logger.debug(f"MQTT Energy History nicht verfügbar für {label}: {e}")

        return {}

    @staticmethod
    def _trapez_kwh(points: list) -> Optional[float]:
        """Berechnet kWh aus Leistungs-History via Trapezregel."""
        if len(points) < 2:
            return None
        energy_wh = 0.0
        for i in range(len(points) - 1):
            t1, p1 = points[i]
            t2, p2 = points[i + 1]
            dt_hours = (t2 - t1).total_seconds() / 3600
            if 0 < dt_hours < 2:  # Max 2h Lücke
                energy_wh += (p1 + p2) / 2 * dt_hours
        return energy_wh / 1000  # Wh → kWh

    async def _get_tages_kwh(
        self, anlage: Anlage, db: AsyncSession, tage_zurueck: int = 0
    ) -> dict[str, Optional[float]]:
        """
        Berechnet Tages-kWh aus HA-History (Leistungssensoren → Energie via Trapezregel).

        Aggregiert in Kategorien (pv, einspeisung, netzbezug) UND per-Komponente
        (z.B. pv_3, wallbox_6, batterie_2) für Tooltips im Energiefluss.
        """
        basis_live, inv_live_map, _, _ = self._extract_live_config(anlage)

        # Investitionstypen laden
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
            # Kombinierter Sensor: wird separat behandelt (Vorzeichen-Split)
            category_entities["netz_kombi"] = [netz_kombi_eid]
        else:
            netz_kombi_eid = None
            if basis_live.get("einspeisung_w"):
                category_entities["einspeisung"].append(basis_live["einspeisung_w"])
            if basis_live.get("netzbezug_w"):
                category_entities["netzbezug"].append(basis_live["netzbezug_w"])

        # Alle Investitionen mit leistung_w Sensor (oder getrennte WP-Sensoren)
        for inv_id, live in inv_live_map.items():
            typ = inv_types.get(inv_id)
            if not typ or typ in _SKIP_TYPEN:
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

            if not entity_id:
                continue

            if typ in _ERZEUGER_TYPEN:
                category_entities["pv"].append(entity_id)
                component_entities[f"pv_{inv_id}"] = entity_id
            else:
                prefix = _LIVE_KEY_PREFIX.get(typ, _TAGESVERLAUF_KATEGORIE.get(typ, typ))
                component_entities[f"{prefix}_{inv_id}"] = entity_id

        # PV Gesamt aus Basis als Fallback (wenn kein individueller PV-Sensor)
        if not category_entities["pv"] and basis_live.get("pv_gesamt_w"):
            pv_gesamt_eid = basis_live["pv_gesamt_w"]
            category_entities["pv"].append(pv_gesamt_eid)
            component_entities["pv_gesamt"] = pv_gesamt_eid

        # Alle Entity-IDs sammeln (dedupliziert)
        all_ids = list(set(
            [eid for eids in category_entities.values() for eid in eids]
            + list(component_entities.values())
        ))
        if not all_ids:
            return {}

        now = datetime.now()
        tag = now - timedelta(days=tage_zurueck)
        start = tag.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1) if tage_zurueck > 0 else now

        history = await self._get_history_normalized(all_ids, start, end)

        result: dict[str, Optional[float]] = {}

        # Aggregierte Kategorien (pv, einspeisung, netzbezug)
        for category, entity_ids in category_entities.items():
            if category == "netz_kombi":
                # Kombinierter Netz-Sensor: Points nach Vorzeichen splitten
                for entity_id in entity_ids:
                    if entity_id not in history:
                        continue
                    pts = history[entity_id]
                    bezug_pts = [(t, max(p, 0)) for t, p in pts]
                    einsp_pts = [(t, abs(min(p, 0))) for t, p in pts]
                    bezug_kwh = self._trapez_kwh(bezug_pts)
                    einsp_kwh = self._trapez_kwh(einsp_pts)
                    if bezug_kwh is not None:
                        result["netzbezug"] = round(bezug_kwh, 1)
                    if einsp_kwh is not None:
                        result["einspeisung"] = round(einsp_kwh, 1)
                continue

            total_kwh = 0.0
            has_data = False
            for entity_id in entity_ids:
                if entity_id not in history:
                    continue
                kwh = self._trapez_kwh(history[entity_id])
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

            # Batterie: Ladung/Entladung getrennt berechnen (positiv=Ladung, negativ=Entladung)
            if comp_key.startswith("batterie_"):
                ladung_pts = [(t, max(p, 0)) for t, p in pts]
                entladung_pts = [(t, abs(min(p, 0))) for t, p in pts]
                ladung_kwh = self._trapez_kwh(ladung_pts)
                entladung_kwh = self._trapez_kwh(entladung_pts)
                if ladung_kwh is not None:
                    result[f"{comp_key}_ladung"] = round(ladung_kwh, 1)
                if entladung_kwh is not None:
                    result[f"{comp_key}_entladung"] = round(entladung_kwh, 1)

            kwh = self._trapez_kwh(pts)
            if kwh is not None:
                result[comp_key] = round(abs(kwh), 1)

        return result

    async def get_tagesverlauf(
        self, anlage: Anlage, db: AsyncSession, tage_zurueck: int = 0,
    ) -> dict:
        """
        Holt stündlich aggregierte Leistungsdaten für einen Tag.

        Args:
            tage_zurueck: 0=heute, 1=gestern, etc.

        Returns:
            dict mit "serien" (Beschreibung der Kurven) und "punkte" (Stundenwerte).
            Butterfly-Chart: Quellen positiv, Senken negativ.
            Bidirektionale Serien (Speicher, Netz) wechseln je nach Richtung.
        """
        basis_live, inv_live_map, _, _ = self._extract_live_config(anlage)

        if not basis_live and not inv_live_map:
            return {"serien": [], "punkte": []}

        if not HA_INTEGRATION_AVAILABLE:
            return {"serien": [], "punkte": []}

        # Investitionen aus DB laden (brauchen Bezeichnung + Typ + parent_id)
        inv_result = await db.execute(
            select(Investition).where(
                Investition.anlage_id == anlage.id,
                Investition.aktiv == True,
            )
        )
        investitionen = {str(inv.id): inv for inv in inv_result.scalars().all()}

        now = datetime.now()
        if tage_zurueck > 0:
            tag = now - timedelta(days=tage_zurueck)
            start = tag.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1)
        else:
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now

        # Serien aufbauen + Entity-IDs sammeln
        serien: list[dict] = []
        # Mapping: serie_key → list[entity_id] (für Multi-Sensor-Aggregation)
        serie_entities: dict[str, list[str]] = {}

        # Investitionen → Serien
        for inv_id, live in inv_live_map.items():
            inv = investitionen.get(inv_id)
            if not inv:
                continue
            typ = inv.typ
            if typ in _SKIP_TYPEN:
                continue

            has_leistung = live.get("leistung_w")

            # WP mit getrennter Strommessung → zwei Serien statt einer
            if not has_leistung and typ == "waermepumpe":
                heiz_eid = live.get("leistung_heizen_w")
                ww_eid = live.get("leistung_warmwasser_w")
                config = _TV_SERIE_CONFIG.get("waermepumpe")
                if config and (heiz_eid or ww_eid):
                    if heiz_eid:
                        key_h = f"waermepumpe_{inv_id}_heizen"
                        serien.append({
                            "key": key_h,
                            "label": f"{inv.bezeichnung} Heizen",
                            "kategorie": config["kategorie"],
                            "farbe": config["farbe"],
                            "seite": config["seite"],
                            "bidirektional": config["bidirektional"],
                        })
                        serie_entities[key_h] = [heiz_eid]
                    if ww_eid:
                        key_w = f"waermepumpe_{inv_id}_warmwasser"
                        serien.append({
                            "key": key_w,
                            "label": f"{inv.bezeichnung} Warmwasser",
                            "kategorie": config["kategorie"],
                            "farbe": "#f59e0b",  # Amber für Warmwasser
                            "seite": config["seite"],
                            "bidirektional": config["bidirektional"],
                        })
                        serie_entities[key_w] = [ww_eid]
                continue

            if not has_leistung:
                continue

            # E-Auto mit Parent (Wallbox) überspringen — Wallbox misst bereits
            if typ == "e-auto" and inv.parent_investition_id is not None:
                continue

            config = _TV_SERIE_CONFIG.get(typ)
            if not config:
                continue

            # Sonstiges: Seite aus parameter.kategorie ableiten
            seite = config["seite"]
            bidirektional = config["bidirektional"]
            if typ == "sonstiges" and isinstance(inv.parameter, dict):
                kat = inv.parameter.get("kategorie", "verbraucher")
                if kat == "erzeuger":
                    seite = "quelle"
                elif kat == "speicher":
                    bidirektional = True

            serie_key = f"{config['kategorie']}_{inv_id}"
            serien.append({
                "key": serie_key,
                "label": inv.bezeichnung,
                "kategorie": config["kategorie"],
                "farbe": config["farbe"],
                "seite": seite,
                "bidirektional": bidirektional,
            })
            serie_entities[serie_key] = [live["leistung_w"]]

        # PV Gesamt aus Basis als Fallback (wenn kein individueller PV-Sensor)
        has_individual_pv = any(s["kategorie"] == "pv" for s in serien)
        if not has_individual_pv and basis_live.get("pv_gesamt_w"):
            gesamt_kwp = anlage.leistung_kwp or 0
            serien.append({
                "key": "pv_gesamt",
                "label": f"PV Gesamt{f' {gesamt_kwp} kWp' if gesamt_kwp else ''}",
                "kategorie": "pv",
                "farbe": "#eab308",
                "seite": "quelle",
                "bidirektional": False,
            })
            serie_entities["pv_gesamt"] = [basis_live["pv_gesamt_w"]]

        # Netz (Einspeisung + Netzbezug als eine bidirektionale Serie)
        has_netz = False
        netz_kombi_eid = basis_live.get("netz_kombi_w")
        netz_einspeisung_eid = basis_live.get("einspeisung_w")
        netz_bezug_eid = basis_live.get("netzbezug_w")
        # Kombinierter Sensor hat Vorrang wenn keine getrennten Sensoren
        if netz_kombi_eid and not netz_einspeisung_eid and not netz_bezug_eid:
            has_netz = True
            serien.append({
                "key": "netz",
                "label": "Stromnetz",
                "kategorie": "netz",
                "farbe": "#ef4444",
                "seite": "quelle",
                "bidirektional": True,
            })
        elif netz_einspeisung_eid or netz_bezug_eid:
            netz_kombi_eid = None  # Getrennte Sensoren → kein Kombi
            has_netz = True
            serien.append({
                "key": "netz",
                "label": "Stromnetz",
                "kategorie": "netz",
                "farbe": "#ef4444",
                "seite": "quelle",
                "bidirektional": True,
            })

        # Alle Entity-IDs für History-Abfrage sammeln
        all_ids = list(set(
            eid for eids in serie_entities.values() for eid in eids
        ))
        if netz_kombi_eid:
            all_ids.append(netz_kombi_eid)
        if netz_einspeisung_eid:
            all_ids.append(netz_einspeisung_eid)
        if netz_bezug_eid:
            all_ids.append(netz_bezug_eid)
        all_ids = list(set(all_ids))

        if not all_ids:
            return {"serien": [], "punkte": []}

        history = await self._get_history_normalized(all_ids, start, end)

        # Stündliche Mittelwerte berechnen
        punkte: list[dict] = []
        for h in range(24):
            h_start = start + timedelta(hours=h)
            h_end = h_start + timedelta(hours=1)
            if h_start > end:
                break

            werte: dict[str, float] = {}
            raw_values: dict[str, float] = {}  # Ungerundet für Haushalt-Berechnung

            # Investitions-Serien
            for serie in serien:
                skey = serie["key"]
                if skey == "netz":
                    continue  # Netz separat behandeln

                entity_ids = serie_entities.get(skey, [])
                serie_sum = 0.0
                has_data = False

                for entity_id in entity_ids:
                    points = history.get(entity_id, [])
                    h_points = [p[1] for p in points if h_start <= p[0] < h_end]
                    if h_points:
                        avg_w = sum(h_points) / len(h_points)
                        serie_sum += avg_w / 1000  # W → kW
                        has_data = True

                if has_data:
                    if serie["bidirektional"]:
                        # Sensor-Konvention: positiv=Ladung, negativ=Entladung
                        # Butterfly-Konvention: positiv=Quelle(Entladung), negativ=Senke(Ladung)
                        # → Vorzeichen umkehren
                        raw_val = -serie_sum
                    elif serie["seite"] == "senke":
                        # Senken als negative Werte
                        raw_val = -abs(serie_sum)
                    else:
                        # Quellen als positive Werte
                        raw_val = abs(serie_sum)
                    raw_values[skey] = raw_val
                    werte[skey] = round(raw_val, 2)

            # Netz: Bezug (positiv/Quelle) - Einspeisung (negativ/Senke)
            if has_netz:
                bezug_kw = 0.0
                einsp_kw = 0.0

                if netz_kombi_eid:
                    # Kombinierter Sensor: positiv=Bezug, negativ=Einspeisung
                    pts = history.get(netz_kombi_eid, [])
                    h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
                    if h_pts:
                        avg_w = sum(h_pts) / len(h_pts)
                        if avg_w >= 0:
                            bezug_kw = avg_w / 1000
                        else:
                            einsp_kw = abs(avg_w) / 1000
                else:
                    if netz_bezug_eid:
                        pts = history.get(netz_bezug_eid, [])
                        h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
                        if h_pts:
                            bezug_kw = sum(h_pts) / len(h_pts) / 1000

                    if netz_einspeisung_eid:
                        pts = history.get(netz_einspeisung_eid, [])
                        h_pts = [p[1] for p in pts if h_start <= p[0] < h_end]
                        if h_pts:
                            einsp_kw = sum(h_pts) / len(h_pts) / 1000

                netto = bezug_kw - einsp_kw  # positiv=Bezug, negativ=Einspeisung
                if abs(netto) > 0.001:
                    raw_values["netz"] = netto
                    werte["netz"] = round(netto, 2)

            # Haushalt aus ungerundeten Rohwerten berechnen (vermeidet akkumulierte Rundungsfehler)
            quellen_sum = sum(v for v in raw_values.values() if v > 0)
            senken_sum = sum(v for v in raw_values.values() if v < 0)
            haushalt = quellen_sum + senken_sum
            if quellen_sum > 0 and haushalt > 0:
                werte["haushalt"] = round(-haushalt, 2)  # Haushalt ist Senke → negativ

            punkte.append({"zeit": f"{h:02d}:00", "werte": werte})

        # Haushalt-Serie hinzufügen wenn Daten vorhanden
        if any("haushalt" in p["werte"] for p in punkte):
            serien.append({
                "key": "haushalt",
                "label": "Haushalt",
                "kategorie": "haushalt",
                "farbe": "#10b981",
                "seite": "senke",
                "bidirektional": False,
            })

        return {"serien": serien, "punkte": punkte}


    # ── Individuelles Verbrauchsprofil ──────────────────────────────────────

    async def get_verbrauchsprofil(
        self, anlage: Anlage, db: AsyncSession
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
        # Cache prüfen
        cache = self._get_profil_cache(anlage.id)
        if cache is not None:
            return cache

        # 1. Versuche HA-History
        result = await self._profil_from_ha(anlage, db)

        # 2. Fallback: MQTT Energy Snapshots
        if result is None:
            result = await self._profil_from_mqtt(anlage.id)

        if result is not None:
            self._set_profil_cache(anlage.id, result)

        return result

    async def _profil_from_ha(
        self, anlage: Anlage, db: AsyncSession
    ) -> Optional[dict]:
        """Verbrauchsprofil aus HA-History (Leistungs-Sensoren, kW-Mittelwerte)."""
        if not HA_INTEGRATION_AVAILABLE:
            return None

        basis_live, inv_live_map, _, _ = self._extract_live_config(anlage)

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
        for inv_id, live in inv_live_map.items():
            typ = inv_types.get(inv_id)
            if typ in _ERZEUGER_TYPEN and live.get("leistung_w"):
                pv_eids.append(live["leistung_w"])

        # PV Gesamt aus Basis als Fallback
        if not pv_eids and basis_live.get("pv_gesamt_w"):
            pv_eids.append(basis_live["pv_gesamt_w"])

        now = datetime.now()
        start = (now - timedelta(days=14)).replace(hour=0, minute=0, second=0, microsecond=0)

        all_ids = list(set(filter(None, [einsp_eid, bezug_eid, kombi_eid] + pv_eids)))
        history = await self._get_history_normalized(all_ids, start, now)

        if not history:
            return None

        werktag_sums: dict[int, list[float]] = {h: [] for h in range(24)}
        wochenende_sums: dict[int, list[float]] = {h: [] for h in range(24)}
        werktage_set: set[str] = set()
        wochenende_set: set[str] = set()

        for day_offset in range(14):
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

                if ist_wochenende:
                    wochenende_sums[h].append(verbrauch_kw)
                    wochenende_set.add(tag_str)
                else:
                    werktag_sums[h].append(verbrauch_kw)
                    werktage_set.add(tag_str)

        return self._build_profil_result(
            werktag_sums, wochenende_sums, werktage_set, wochenende_set, "ha"
        )

    async def _profil_from_mqtt(self, anlage_id: int) -> Optional[dict]:
        """
        Verbrauchsprofil aus MQTT Energy Snapshots (kumulative kWh → stündliche Deltas).

        Die Snapshots enthalten kumulative Monatswerte (pv_gesamt_kwh, einspeisung_kwh,
        netzbezug_kwh) alle 5 Minuten. Für jede Stunde berechnen wir das Delta und
        daraus den durchschnittlichen Verbrauch in kW (= kWh/h).
        """
        from backend.core.database import get_session
        from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot

        now = datetime.now()
        start = (now - timedelta(days=14)).replace(hour=0, minute=0, second=0, microsecond=0)

        # Alle Snapshots der letzten 14 Tage laden
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

        for day_offset in range(14):
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

                def delta(key: str) -> float:
                    v_end = last.get(key)
                    v_start = first.get(key)
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

        return self._build_profil_result(
            werktag_sums, wochenende_sums, werktage_set, wochenende_set, "mqtt"
        )

    @staticmethod
    def _build_profil_result(
        werktag_sums: dict[int, list[float]],
        wochenende_sums: dict[int, list[float]],
        werktage_set: set[str],
        wochenende_set: set[str],
        quelle: str,
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

        return {
            "werktag": build_profil(werktag_sums) if tage_wt >= 2 else None,
            "wochenende": build_profil(wochenende_sums) if tage_we >= 2 else None,
            "tage_werktag": tage_wt,
            "tage_wochenende": tage_we,
            "quelle": quelle,
        }

    # ── Profil-Cache (1x täglich) ────────────────────────────────────────

    _profil_cache: dict[int, tuple[str, dict]] = {}  # {anlage_id: (datum_str, profil)}

    def _get_profil_cache(self, anlage_id: int) -> Optional[dict]:
        """Gibt gecachtes Profil zurück wenn es von heute ist."""
        if anlage_id not in self._profil_cache:
            return None
        datum, profil = self._profil_cache[anlage_id]
        if datum == datetime.now().strftime("%Y-%m-%d"):
            return profil
        return None

    def _set_profil_cache(self, anlage_id: int, profil: dict) -> None:
        """Speichert Profil mit heutigem Datum."""
        self._profil_cache[anlage_id] = (datetime.now().strftime("%Y-%m-%d"), profil)


# Singleton
_live_power_service: Optional[LivePowerService] = None


def get_live_power_service() -> LivePowerService:
    """Gibt die Singleton-Instanz zurück."""
    global _live_power_service
    if _live_power_service is None:
        _live_power_service = LivePowerService()
    return _live_power_service
