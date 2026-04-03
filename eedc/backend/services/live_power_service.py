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
from backend.services.live_sensor_config import (
    normalize_to_w,
    TYP_ICON,
    ERZEUGER_TYPEN,
    BIDIREKTIONAL_TYPEN,
    SOC_TYPEN,
    SKIP_TYPEN,
    TAGESVERLAUF_KATEGORIE,
    TV_SERIE_CONFIG,
    LIVE_KEY_PREFIX,
    extract_live_config,
)
from backend.services.live_history_service import (
    get_history_normalized,
    apply_invert_to_history,
    trapez_kwh,
    safe_get_tages_kwh,
)


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

        # Komponenten aufbauen
        komponenten = []
        summe_erzeugung = 0.0
        summe_verbrauch = 0.0
        gauges = []
        pv_total_w = 0.0


        # Wallbox-Keys sammeln für E-Auto → Wallbox Zuordnung
        wallbox_keys: list[str] = []

        # Entity-IDs tracken um Duplikate zu erkennen (z.B. gleicher Sensor bei Wallbox + E-Auto)
        used_leistung_eids: dict[str, str] = {}  # entity_id → inv_id (erster Nutzer)
        for inv_id, live in inv_live_map.items():
            eid = live.get("leistung_w")
            if eid and eid not in used_leistung_eids:
                used_leistung_eids[eid] = inv_id

        # Per-Investition Komponenten
        for inv_id, values in inv_values.items():
            inv = investitionen.get(inv_id)
            if not inv or inv.typ in SKIP_TYPEN:
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
                # Kein Leistungswert → trotzdem SoC-Gauge prüfen (weiter unten)
                typ = inv.typ if inv else None
                if typ in SOC_TYPEN:
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
                continue

            typ = inv.typ

            # Duplikat-Sensor-Erkennung: Wenn ein E-Auto denselben Leistungs-Sensor
            # wie eine Wallbox nutzt, Leistung überspringen (Wallbox zeigt sie bereits).
            # SoC wird weiter unten trotzdem erfasst.
            leistung_eid = inv_live_map.get(inv_id, {}).get("leistung_w")
            if typ == "e-auto" and leistung_eid:
                first_user = used_leistung_eids.get(leistung_eid)
                if first_user and first_user != inv_id:
                    first_inv = investitionen.get(first_user)
                    if first_inv and first_inv.typ == "wallbox":
                        logger.debug(
                            f"E-Auto {inv.bezeichnung}: gleicher Sensor wie Wallbox "
                            f"{first_inv.bezeichnung} — Leistung übersprungen"
                        )
                        val_w = None

            if val_w is None:
                # Duplikat erkannt oder kein Wert → nur SoC-Gauge
                if typ in SOC_TYPEN:
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
                continue

            # E-Auto mit V2H ist bidirektional (negativ = Entladung ins Haus)
            ist_v2h = (typ == "e-auto"
                       and isinstance(inv.parameter, dict)
                       and inv.parameter.get("nutzt_v2h"))
            ist_bidirektional = typ in BIDIREKTIONAL_TYPEN or ist_v2h

            if typ in ERZEUGER_TYPEN:
                # PV / BKW — nur Erzeugung
                kw = val_w / 1000
                komponenten.append({
                    "key": f"pv_{inv_id}",
                    "label": inv.bezeichnung,
                    "icon": TYP_ICON.get(typ, "sun"),
                    "erzeugung_kw": round(kw, 3),
                    "verbrauch_kw": None,
                })
                summe_erzeugung += kw
                pv_total_w += val_w

            elif ist_bidirektional:
                # Speicher / E-Auto mit V2H — bidirektional (positiv = Ladung, negativ = Entladung)
                kw = abs(val_w) / 1000
                ist_ladung = val_w > 0
                kategorie = TAGESVERLAUF_KATEGORIE.get(typ, "batterie")
                komponenten.append({
                    "key": f"{kategorie}_{inv_id}",
                    "label": inv.bezeichnung,
                    "icon": TYP_ICON.get(typ, "battery"),
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
                prefix = LIVE_KEY_PREFIX.get(typ, TAGESVERLAUF_KATEGORIE.get(typ, typ))
                komp_key = f"{prefix}_{inv_id}"
                komponenten.append({
                    "key": komp_key,
                    "label": inv.bezeichnung,
                    "icon": wp_icon or TYP_ICON.get(typ, "wrench"),
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
            if typ in SOC_TYPEN:
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
        basis_live, inv_live_map, basis_invert, inv_invert_map = extract_live_config(anlage)

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
            if typ in SKIP_TYPEN:
                continue

            has_leistung = live.get("leistung_w")

            # WP mit getrennter Strommessung → zwei Serien statt einer
            if not has_leistung and typ == "waermepumpe":
                heiz_eid = live.get("leistung_heizen_w")
                ww_eid = live.get("leistung_warmwasser_w")
                config = TV_SERIE_CONFIG.get("waermepumpe")
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

            config = TV_SERIE_CONFIG.get(typ)
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

        history, _ = await get_history_normalized(all_ids, start, end)

        # Vorzeichen-Invertierung auf History anwenden (#58)
        apply_invert_to_history(
            history, basis_live, basis_invert, inv_live_map, inv_invert_map
        )

        # 10-Minuten-Mittelwerte berechnen
        punkte: list[dict] = []
        for m in range(144):
            h_start = start + timedelta(minutes=m * 10)
            h_end = h_start + timedelta(minutes=10)
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

            punkte.append({"zeit": f"{h_start.hour:02d}:{h_start.minute:02d}", "werte": werte})

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
