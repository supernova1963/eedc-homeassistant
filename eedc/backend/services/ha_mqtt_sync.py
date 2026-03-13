"""
HA MQTT Sync Service.

Publiziert EEDC-Ergebnisse (KPIs, Monatsdaten) nach Home Assistant via MQTT.
"""

import os
from typing import Optional, Any

from backend.services.mqtt_client import MQTTClient, MQTTConfig


def _get_mqtt_config_from_env() -> MQTTConfig:
    """Lädt MQTT-Konfiguration aus Umgebungsvariablen."""
    return MQTTConfig(
        host=os.environ.get("MQTT_HOST", "core-mosquitto"),
        port=int(os.environ.get("MQTT_PORT", "1883")),
        username=os.environ.get("MQTT_USER") or None,
        password=os.environ.get("MQTT_PASSWORD") or None,
    )


class HAMqttSyncService:
    """Publiziert EEDC-Ergebnisse nach HA via MQTT."""

    def __init__(self, mqtt_client: Optional[MQTTClient] = None):
        if mqtt_client:
            self.mqtt = mqtt_client
        else:
            config = _get_mqtt_config_from_env()
            self.mqtt = MQTTClient(config)

    async def publish_final_month_data(
        self,
        anlage_id: int,
        jahr: int,
        monat: int,
        daten: dict[str, Any],
    ) -> bool:
        """
        Publiziert finale Monatsdaten auf MQTT (retained).

        Args:
            anlage_id: ID der Anlage
            jahr: Jahr
            monat: Monat
            daten: Monatsdaten

        Returns:
            True wenn erfolgreich
        """
        return await self.mqtt.publish_monatsdaten(
            anlage_id=anlage_id,
            jahr=jahr,
            monat=monat,
            daten=daten,
        )


# Singleton-Instanz
_ha_mqtt_sync_service: Optional[HAMqttSyncService] = None


def get_ha_mqtt_sync_service() -> HAMqttSyncService:
    """Gibt die Singleton-Instanz des Services zurück."""
    global _ha_mqtt_sync_service
    if _ha_mqtt_sync_service is None:
        _ha_mqtt_sync_service = HAMqttSyncService()
    return _ha_mqtt_sync_service
