"""
Live Power Service - Sammelt aktuelle Leistungswerte aus verfügbaren Quellen.

Phase 1: Liest Live-Sensoren aus HA via live_sensors Mapping.
Phase 2: MQTT-Inbound-Cache als zusätzliche Quelle.
Phase 4: Connector read_current_power() als Fallback.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import HA_INTEGRATION_AVAILABLE
from backend.models.anlage import Anlage
from backend.models.investition import Investition


# Mapping von live_sensors Keys auf Komponenten-Metadaten
_KOMPONENTEN_CONFIG = {
    "pv": {
        "key": "pv",
        "label": "PV-Anlage",
        "icon": "sun",
        "sensor_key": "pv_leistung_w",
        "seite": "erzeugung",
    },
    "netz": {
        "key": "netz",
        "label": "Stromnetz",
        "icon": "zap",
        "sensor_einspeisung": "einspeisung_w",
        "sensor_bezug": "netzbezug_w",
        "bidirektional": True,
    },
    "batterie": {
        "key": "batterie",
        "label": "Speicher",
        "icon": "battery",
        "sensor_key": "batterie_w",
        "soc_key": "batterie_soc",
        "bidirektional": True,
        "investition_typ": "speicher",
    },
    "eauto": {
        "key": "eauto",
        "label": "E-Auto",
        "icon": "car",
        "sensor_key": "eauto_w",
        "soc_key": "eauto_soc",
        "seite": "verbrauch",
        "investition_typ": "e-auto",
    },
    "waermepumpe": {
        "key": "waermepumpe",
        "label": "Wärmepumpe",
        "icon": "flame",
        "sensor_key": "waermepumpe_w",
        "seite": "verbrauch",
        "investition_typ": "waermepumpe",
    },
    "sonstige": {
        "key": "sonstige",
        "label": "Sonstige",
        "icon": "wrench",
        "sensor_key": "sonstige_w",
        "seite": "verbrauch",
        "investition_typ": "sonstiges",
    },
}


class LivePowerService:
    """Sammelt aktuelle Leistungswerte aus verfügbaren Quellen."""

    async def get_live_data(self, anlage: Anlage, db: AsyncSession) -> dict:
        """
        Holt Live-Daten für eine Anlage.

        Returns:
            dict mit Komponenten, Gauges, Summen und Metadaten.
        """
        live_sensors = (anlage.sensor_mapping or {}).get("live_sensors", {})

        # Sensor-Werte lesen (HA-Modus)
        sensor_values: dict[str, Optional[float]] = {}
        if live_sensors and HA_INTEGRATION_AVAILABLE:
            from backend.services.ha_state_service import get_ha_state_service
            ha_service = get_ha_state_service()

            for key, entity_id in live_sensors.items():
                if entity_id:
                    sensor_values[key] = await ha_service.get_sensor_state(entity_id)

        # Investition-Typen für diese Anlage laden
        result = await db.execute(
            select(Investition.typ).where(Investition.anlage_id == anlage.id)
        )
        investition_typen = set(row[0] for row in result.all())

        # Komponenten aufbauen
        komponenten = []
        summe_erzeugung = 0.0
        summe_verbrauch = 0.0

        # PV — immer anzeigen wenn Sensor vorhanden
        pv_w = sensor_values.get("pv_leistung_w")
        if pv_w is not None:
            pv_kw = pv_w / 1000
            komponenten.append({
                "key": "pv",
                "label": "PV-Anlage",
                "icon": "sun",
                "erzeugung_kw": round(pv_kw, 2),
                "verbrauch_kw": None,
            })
            summe_erzeugung += pv_kw

        # Netz — bidirektional
        einspeisung_w = sensor_values.get("einspeisung_w")
        netzbezug_w = sensor_values.get("netzbezug_w")
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

        # Batterie — bidirektional (negativ = Entladung, positiv = Ladung)
        batterie_w = sensor_values.get("batterie_w")
        if batterie_w is not None and "speicher" in investition_typen:
            batt_kw = abs(batterie_w) / 1000
            ist_ladung = batterie_w > 0
            komponenten.append({
                "key": "batterie",
                "label": "Speicher",
                "icon": "battery",
                "erzeugung_kw": round(batt_kw, 2) if not ist_ladung else None,
                "verbrauch_kw": round(batt_kw, 2) if ist_ladung else None,
            })
            if ist_ladung:
                summe_verbrauch += batt_kw
            else:
                summe_erzeugung += batt_kw

        # E-Auto
        eauto_w = sensor_values.get("eauto_w")
        if eauto_w is not None and ("e-auto" in investition_typen or "wallbox" in investition_typen):
            eauto_kw = eauto_w / 1000
            komponenten.append({
                "key": "eauto",
                "label": "E-Auto",
                "icon": "car",
                "erzeugung_kw": None,
                "verbrauch_kw": round(eauto_kw, 2),
            })
            summe_verbrauch += eauto_kw

        # Wärmepumpe
        wp_w = sensor_values.get("waermepumpe_w")
        if wp_w is not None and "waermepumpe" in investition_typen:
            wp_kw = wp_w / 1000
            komponenten.append({
                "key": "waermepumpe",
                "label": "Wärmepumpe",
                "icon": "flame",
                "erzeugung_kw": None,
                "verbrauch_kw": round(wp_kw, 2),
            })
            summe_verbrauch += wp_kw

        # Sonstige
        sonstige_w = sensor_values.get("sonstige_w")
        if sonstige_w is not None:
            sonstige_kw = sonstige_w / 1000
            komponenten.append({
                "key": "sonstige",
                "label": "Sonstige",
                "icon": "wrench",
                "erzeugung_kw": None,
                "verbrauch_kw": round(sonstige_kw, 2),
            })
            summe_verbrauch += sonstige_kw

        # Haushalt (berechnet: Gesamtverbrauch - bekannte Verbraucher)
        if pv_w is not None and (einspeisung_w is not None or netzbezug_w is not None):
            bekannte_verbraucher = sum(
                k.get("verbrauch_kw") or 0
                for k in komponenten
                if k["key"] not in ("pv", "netz")
            )
            haushalt_kw = summe_erzeugung - summe_verbrauch - bekannte_verbraucher
            if haushalt_kw < 0:
                haushalt_kw = 0
            # Eigentlich: Haushalt = Erzeugung - Einspeisung - bekannte Verbraucher
            # Einfacher: Gesamtverbrauch = PV + Bezug - Einspeisung, Haushalt = Gesamtverbrauch - bekannte
            gesamt_erzeugung_kw = (pv_w or 0) / 1000 + (netzbezug_w or 0) / 1000
            gesamt_abgang_kw = (einspeisung_w or 0) / 1000
            gesamt_verbrauch_kw = gesamt_erzeugung_kw - gesamt_abgang_kw
            haushalt_kw = max(0, gesamt_verbrauch_kw - bekannte_verbraucher)

            komponenten.append({
                "key": "haushalt",
                "label": "Haushalt",
                "icon": "home",
                "erzeugung_kw": None,
                "verbrauch_kw": round(haushalt_kw, 2),
            })
            summe_verbrauch += haushalt_kw

        # Gauges aufbauen
        gauges = []

        # Netz-Gauge (Einspeisung vs. Bezug)
        if einspeisung_w is not None or netzbezug_w is not None:
            netto_w = (netzbezug_w or 0) - (einspeisung_w or 0)
            max_val = max(abs(einspeisung_w or 0), abs(netzbezug_w or 0), 1)
            gauges.append({
                "key": "netz",
                "label": "Netz",
                "wert": round(netto_w, 0),
                "min_wert": -max_val,
                "max_wert": max_val,
                "einheit": "W",
            })

        # Batterie SoC
        batterie_soc = sensor_values.get("batterie_soc")
        if batterie_soc is not None and "speicher" in investition_typen:
            gauges.append({
                "key": "batterie_soc",
                "label": "Speicher",
                "wert": round(batterie_soc, 0),
                "min_wert": 0,
                "max_wert": 100,
                "einheit": "%",
            })

        # E-Auto SoC
        eauto_soc = sensor_values.get("eauto_soc")
        if eauto_soc is not None:
            gauges.append({
                "key": "eauto_soc",
                "label": "E-Auto",
                "wert": round(eauto_soc, 0),
                "min_wert": 0,
                "max_wert": 100,
                "einheit": "%",
            })

        # Autarkie-Gauge
        if pv_w is not None and (einspeisung_w is not None or netzbezug_w is not None):
            gesamt_erzeugung_kw = (pv_w or 0) / 1000 + (netzbezug_w or 0) / 1000
            eigenverbrauch_kw = (pv_w or 0) / 1000 - (einspeisung_w or 0) / 1000
            gesamt_verbrauch_kw = eigenverbrauch_kw + (netzbezug_w or 0) / 1000
            autarkie = (eigenverbrauch_kw / gesamt_verbrauch_kw * 100) if gesamt_verbrauch_kw > 0 else 0
            gauges.append({
                "key": "autarkie",
                "label": "Autarkie",
                "wert": round(min(autarkie, 100), 0),
                "min_wert": 0,
                "max_wert": 100,
                "einheit": "%",
            })

        return {
            "anlage_id": anlage.id,
            "anlage_name": anlage.anlagenname,
            "zeitpunkt": datetime.now().isoformat(),
            "verfuegbar": len(komponenten) > 0,
            "komponenten": komponenten,
            "summe_erzeugung_kw": round(summe_erzeugung, 2),
            "summe_verbrauch_kw": round(summe_verbrauch, 2),
            "gauges": gauges,
            "heute_pv_kwh": None,
            "heute_einspeisung_kwh": None,
            "heute_netzbezug_kwh": None,
            "heute_eigenverbrauch_kwh": None,
        }


# Singleton
_live_power_service: Optional[LivePowerService] = None


def get_live_power_service() -> LivePowerService:
    """Gibt die Singleton-Instanz zurück."""
    global _live_power_service
    if _live_power_service is None:
        _live_power_service = LivePowerService()
    return _live_power_service
