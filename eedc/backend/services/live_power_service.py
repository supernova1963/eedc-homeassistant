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


# Icon-Zuordnung pro Investitionstyp
_TYP_ICON = {
    "pv-module": "sun",
    "balkonkraftwerk": "sun",
    "speicher": "battery",
    "e-auto": "car",
    "wallbox": "car",
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

# Kategorien für Tagesverlauf-Aggregation
_TAGESVERLAUF_KATEGORIE = {
    "pv-module": "pv",
    "balkonkraftwerk": "pv",
    "speicher": "batterie",
    "e-auto": "eauto",
    "wallbox": "eauto",
    "waermepumpe": "waermepumpe",
    "sonstiges": "sonstige",
}


class LivePowerService:
    """Sammelt aktuelle Leistungswerte aus verfügbaren Quellen."""

    def _extract_live_config(self, anlage: Anlage) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
        """
        Extrahiert Live-Sensor-Konfiguration aus sensor_mapping.

        Returns:
            (basis_live, inv_live_map)
            basis_live: {einspeisung_w: entity_id, netzbezug_w: entity_id}
            inv_live_map: {inv_id: {leistung_w: entity_id, soc: entity_id}}
        """
        mapping = anlage.sensor_mapping or {}

        # Neue Struktur: basis.live + investitionen[id].live
        basis_live: dict[str, str] = {}
        inv_live_map: dict[str, dict[str, str]] = {}

        basis = mapping.get("basis", {})
        if isinstance(basis.get("live"), dict):
            basis_live = {k: v for k, v in basis["live"].items() if v}

        for inv_id, inv_data in mapping.get("investitionen", {}).items():
            if isinstance(inv_data, dict) and isinstance(inv_data.get("live"), dict):
                live = {k: v for k, v in inv_data["live"].items() if v}
                if live:
                    inv_live_map[inv_id] = live

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

        return basis_live, inv_live_map

    def _collect_values(
        self, anlage: Anlage,
        basis_live: dict[str, str],
        inv_live_map: dict[str, dict[str, str]],
        sensor_values: dict[str, Optional[float]],
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

        # 1. HA-Sensor-Werte (Prio 2)
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
        if mqtt_svc and mqtt_svc.cache.has_data(anlage.id):
            mqtt_basis = mqtt_svc.cache.get_live_basis(anlage.id)
            basis_values.update(mqtt_basis)

            mqtt_inv = mqtt_svc.cache.get_all_live_inv(anlage.id)
            for inv_id, values in mqtt_inv.items():
                if inv_id not in inv_values:
                    inv_values[inv_id] = {}
                inv_values[inv_id].update(values)

        return basis_values, inv_values

    async def get_live_data(self, anlage: Anlage, db: AsyncSession) -> dict:
        """
        Holt Live-Daten für eine Anlage.

        Quellen: MQTT-Inbound (Prio 1), HA State Service (Prio 2).
        Returns:
            dict mit Komponenten, Gauges, Summen und Metadaten.
        """
        basis_live, inv_live_map = self._extract_live_config(anlage)

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
                sensor_values[entity_id] = await ha_service.get_sensor_state(entity_id)

        # Werte aus HA + MQTT zusammenführen
        basis_values, inv_values = self._collect_values(
            anlage, basis_live, inv_live_map, sensor_values
        )

        # Komponenten aufbauen
        komponenten = []
        summe_erzeugung = 0.0
        summe_verbrauch = 0.0
        gauges = []
        pv_total_w = 0.0


        # Per-Investition Komponenten
        for inv_id, values in inv_values.items():
            inv = investitionen.get(inv_id)
            if not inv or inv.typ in _SKIP_TYPEN:
                continue

            val_w = values.get("leistung_w")
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
                    "erzeugung_kw": round(kw, 2),
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
                    "erzeugung_kw": round(kw, 2) if not ist_ladung else None,
                    "verbrauch_kw": round(kw, 2) if ist_ladung else None,
                })
                if ist_ladung:
                    summe_verbrauch += kw
                else:
                    summe_erzeugung += kw

            else:
                # Verbraucher (E-Auto ohne V2H, WP, Wallbox, Sonstige)
                kw = val_w / 1000
                komponenten.append({
                    "key": f"{_TAGESVERLAUF_KATEGORIE.get(typ, typ)}_{inv_id}",
                    "label": inv.bezeichnung,
                    "icon": _TYP_ICON.get(typ, "wrench"),
                    "erzeugung_kw": None,
                    "verbrauch_kw": round(kw, 2),
                })
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
                "erzeugung_kw": round(bezug_kw, 2) if bezug_kw > 0 else None,
                "verbrauch_kw": round(einsp_kw, 2) if einsp_kw > 0 else None,
            })
            if bezug_kw > 0:
                summe_erzeugung += bezug_kw
            if einsp_kw > 0:
                summe_verbrauch += einsp_kw

        # Haushalt = Residual aus allen Komponenten
        # Quellen: PV, Batterie-Entladung, V2H-Entladung, Netzbezug
        # Senken: Einspeisung, Batterie-Ladung, EV-Ladung, WP, Wallbox, Sonstige
        gesamt_quellen = sum(k.get("erzeugung_kw") or 0 for k in komponenten)
        gesamt_senken = sum(k.get("verbrauch_kw") or 0 for k in komponenten)
        if gesamt_quellen > 0 and (einspeisung_w is not None or netzbezug_w is not None):
            haushalt_kw = max(0, gesamt_quellen - gesamt_senken)

            komponenten.append({
                "key": "haushalt",
                "label": "Haushalt",
                "icon": "home",
                "erzeugung_kw": None,
                "verbrauch_kw": round(haushalt_kw, 2),
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

        # Autarkie + Eigenverbrauchsquote
        if pv_total_w > 0 and (einspeisung_w is not None or netzbezug_w is not None):
            pv_kw = pv_total_w / 1000
            eigenverbrauch_kw = pv_kw - (einspeisung_w or 0) / 1000
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

        # Tages-kWh berechnen
        heute_kwh = await self._safe_get_tages_kwh(anlage, db, 0)
        gestern_kwh = await self._safe_get_tages_kwh(anlage, db, 1)

        heute_pv = heute_kwh.get("pv")
        heute_einsp = heute_kwh.get("einspeisung")
        heute_bezug = heute_kwh.get("netzbezug")
        heute_ev = round(heute_pv - heute_einsp, 1) if heute_pv is not None and heute_einsp is not None else None

        gestern_pv = gestern_kwh.get("pv")
        gestern_einsp = gestern_kwh.get("einspeisung")
        gestern_bezug = gestern_kwh.get("netzbezug")
        gestern_ev = round(gestern_pv - gestern_einsp, 1) if gestern_pv is not None and gestern_einsp is not None else None

        return {
            "anlage_id": anlage.id,
            "anlage_name": anlage.anlagenname,
            "zeitpunkt": datetime.now().isoformat(),
            "verfuegbar": len(komponenten) > 0,
            "komponenten": komponenten,
            "summe_erzeugung_kw": round(summe_erzeugung, 2),
            "summe_verbrauch_kw": round(summe_verbrauch, 2),
            "gauges": gauges,
            "heute_pv_kwh": heute_pv,
            "heute_einspeisung_kwh": heute_einsp,
            "heute_netzbezug_kwh": heute_bezug,
            "heute_eigenverbrauch_kwh": heute_ev,
            "gestern_pv_kwh": gestern_pv,
            "gestern_einspeisung_kwh": gestern_einsp,
            "gestern_netzbezug_kwh": gestern_bezug,
            "gestern_eigenverbrauch_kwh": gestern_ev,
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
            "gauges": [],
            "heute_pv_kwh": None,
            "heute_einspeisung_kwh": None,
            "heute_netzbezug_kwh": None,
            "heute_eigenverbrauch_kwh": None,
            "gestern_pv_kwh": None,
            "gestern_einspeisung_kwh": None,
            "gestern_netzbezug_kwh": None,
            "gestern_eigenverbrauch_kwh": None,
        }

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

    async def _get_tages_kwh(
        self, anlage: Anlage, db: AsyncSession, tage_zurueck: int = 0
    ) -> dict[str, Optional[float]]:
        """
        Berechnet Tages-kWh aus HA-History (Leistungssensoren → Energie via Trapezregel).

        Aggregiert per-Investition Sensoren in Kategorien (pv, einspeisung, netzbezug).
        """
        from backend.services.ha_state_service import get_ha_state_service

        basis_live, inv_live_map = self._extract_live_config(anlage)

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

        # Basis: Einspeisung + Netzbezug
        if basis_live.get("einspeisung_w"):
            category_entities["einspeisung"].append(basis_live["einspeisung_w"])
        if basis_live.get("netzbezug_w"):
            category_entities["netzbezug"].append(basis_live["netzbezug_w"])

        # PV-Investitionen
        for inv_id, live in inv_live_map.items():
            typ = inv_types.get(inv_id)
            if typ in _ERZEUGER_TYPEN and live.get("leistung_w"):
                category_entities["pv"].append(live["leistung_w"])

        # Alle Entity-IDs sammeln
        all_ids = [eid for eids in category_entities.values() for eid in eids]
        if not all_ids:
            return {}

        ha_service = get_ha_state_service()
        now = datetime.now()
        tag = now - timedelta(days=tage_zurueck)
        start = tag.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1) if tage_zurueck > 0 else now

        history = await ha_service.get_sensor_history(all_ids, start, end)

        result: dict[str, Optional[float]] = {}
        for category, entity_ids in category_entities.items():
            total_kwh = 0.0
            has_data = False

            for entity_id in entity_ids:
                if entity_id not in history:
                    continue
                points = history[entity_id]
                if len(points) < 2:
                    continue

                # Trapezregel: ∫P(t)dt ≈ Σ (P_i + P_{i+1})/2 × Δt
                energy_wh = 0.0
                for i in range(len(points) - 1):
                    t1, p1 = points[i]
                    t2, p2 = points[i + 1]
                    dt_hours = (t2 - t1).total_seconds() / 3600
                    if 0 < dt_hours < 2:  # Max 2h Lücke
                        energy_wh += (p1 + p2) / 2 * dt_hours

                total_kwh += energy_wh / 1000  # Wh → kWh
                has_data = True

            if has_data:
                result[category] = round(total_kwh, 1)

        return result

    async def get_tagesverlauf(self, anlage: Anlage, db: AsyncSession) -> list[dict]:
        """
        Holt stündlich aggregierte Leistungsdaten für heute.

        Aggregiert per-Investition Sensoren in Kategorien für den Chart.
        """
        basis_live, inv_live_map = self._extract_live_config(anlage)

        if not basis_live and not inv_live_map:
            return []

        if not HA_INTEGRATION_AVAILABLE:
            return []

        # Investitionstypen laden
        inv_result = await db.execute(
            select(Investition.id, Investition.typ).where(
                Investition.anlage_id == anlage.id, Investition.aktiv == True
            )
        )
        inv_types = {str(row[0]): row[1] for row in inv_result.all()}

        from backend.services.ha_state_service import get_ha_state_service
        ha_service = get_ha_state_service()

        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # Entity-IDs nach Tagesverlauf-Kategorie gruppieren
        category_entities: dict[str, list[str]] = {}

        # Basis: Einspeisung + Netzbezug
        if basis_live.get("einspeisung_w"):
            category_entities.setdefault("einspeisung", []).append(basis_live["einspeisung_w"])
        if basis_live.get("netzbezug_w"):
            category_entities.setdefault("netzbezug", []).append(basis_live["netzbezug_w"])

        # Investitionen nach Kategorie
        for inv_id, live in inv_live_map.items():
            typ = inv_types.get(inv_id)
            if not typ or not live.get("leistung_w"):
                continue
            kategorie = _TAGESVERLAUF_KATEGORIE.get(typ)
            if kategorie:
                category_entities.setdefault(kategorie, []).append(live["leistung_w"])

        all_ids = [eid for eids in category_entities.values() for eid in eids]
        if not all_ids:
            return []

        history = await ha_service.get_sensor_history(all_ids, start, now)

        # Stündliche Mittelwerte berechnen (aggregiert pro Kategorie)
        stunden: list[dict] = []
        for h in range(24):
            h_start = start + timedelta(hours=h)
            h_end = h_start + timedelta(hours=1)
            if h_start > now:
                break

            punkt: dict = {"zeit": f"{h:02d}:00"}

            for kategorie, entity_ids in category_entities.items():
                # Alle Entity-IDs dieser Kategorie summieren
                kategorie_sum = 0.0
                has_data = False

                for entity_id in entity_ids:
                    points = history.get(entity_id, [])
                    h_points = [p[1] for p in points if h_start <= p[0] < h_end]
                    if h_points:
                        avg_w = sum(h_points) / len(h_points)
                        kategorie_sum += avg_w / 1000  # W → kW
                        has_data = True

                if has_data:
                    punkt[kategorie] = round(kategorie_sum, 2)

            # Haushalt berechnen wenn PV + Netz vorhanden
            pv = punkt.get("pv", 0)
            bezug = punkt.get("netzbezug", 0)
            einsp = punkt.get("einspeisung", 0)
            batt = punkt.get("batterie", 0)
            eauto = punkt.get("eauto", 0)
            wp = punkt.get("waermepumpe", 0)

            gesamt_erzeugung = pv + bezug
            gesamt_abgang = einsp + eauto + wp
            if batt > 0:  # Ladung
                gesamt_abgang += batt
            else:  # Entladung
                gesamt_erzeugung += abs(batt)

            haushalt = max(0, gesamt_erzeugung - gesamt_abgang)
            if "pv" in punkt:
                punkt["haushalt"] = round(haushalt, 2)
                punkt["verbrauch_gesamt"] = round(
                    eauto + wp + haushalt + (batt if batt > 0 else 0), 2
                )

            stunden.append(punkt)

        return stunden


# Singleton
_live_power_service: Optional[LivePowerService] = None


def get_live_power_service() -> LivePowerService:
    """Gibt die Singleton-Instanz zurück."""
    global _live_power_service
    if _live_power_service is None:
        _live_power_service = LivePowerService()
    return _live_power_service
