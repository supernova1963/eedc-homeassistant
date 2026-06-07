"""
HA MQTT Sync Service.

Single Source of Truth für den MQTT-Outbound-Pfad (eedc-Ergebnisse → Home
Assistant). Bündelt die Broker-Konfigurations-Auflösung und das Publizieren der
Anlage-Sensoren, das zuvor in `scheduler.mqtt_auto_publish_job` und der
manuellen `/ha/export/mqtt/publish`-Route dupliziert war (#655).
"""

import os
from typing import Optional, Any

from backend.services.mqtt_client import MQTTClient, MQTTConfig


def resolve_mqtt_config(
    host: Optional[str] = None,
    port: Optional[int] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> MQTTConfig:
    """Löst die MQTT-Broker-Konfiguration konsistent auf.

    Pro Feld: expliziter Override → Umgebungsvariable → kanonischer Default.

    Wichtig (#655): Ein leeres Config-Objekt aus dem Frontend (alle Felder None)
    fällt damit auf die ENV-Werte zurück. Vorher zog die manuelle Publish-Route
    den Pydantic-Default `core-mosquitto` und zielte so auf einen anderen Broker
    als der ENV-basierte Auto-Publish — ein Broker-Mismatch, der „erfolgreich
    publiziert, aber in HA nichts sichtbar" verursachte.
    """
    return MQTTConfig(
        host=host or os.environ.get("MQTT_HOST", "core-mosquitto"),
        port=port or int(os.environ.get("MQTT_PORT", "1883")),
        username=username if username is not None else (os.environ.get("MQTT_USER") or None),
        password=password if password is not None else (os.environ.get("MQTT_PASSWORD") or None),
    )


def _get_mqtt_config_from_env() -> MQTTConfig:
    """Lädt MQTT-Konfiguration aus Umgebungsvariablen."""
    return resolve_mqtt_config()


async def publish_anlage_sensors(
    db,
    anlage,
    mqtt_config: Optional[MQTTConfig] = None,
) -> dict:
    """Berechnet + publiziert alle HA-Export-Sensoren einer Anlage via MQTT Discovery.

    Der eine Outbound-Pfad für Auto-Publish (Scheduler) UND die manuelle Route.
    Beide meldeten zuvor „erfolg=True, 0 Sensoren" über den nicht existenten Key
    `published` — hier liefern wir die realen `success`/`failed`-Zahlen, damit
    Logs/Activity die Wahrheit zeigen.

    Returns:
        dict mit:
          available: bool   — aiomqtt verfügbar
          no_data: bool     — keine Sensoren (keine Monatsdaten)
          total/success/failed: int
          errors: list[str] — Stichprobe der Fehlergründe (für aussagekräftige Logs)
    """
    # Lazy-Import: calculate_anlage_sensors liegt im Route-Modul; ein Top-Level-
    # Import erzeugte einen Zyklus (die Route importiert diesen Service).
    from backend.api.routes.ha_export import calculate_anlage_sensors

    client = MQTTClient(mqtt_config or _get_mqtt_config_from_env())
    if not client.is_available:
        return {"available": False, "no_data": False, "total": 0, "success": 0, "failed": 0, "errors": []}

    sensor_values = await calculate_anlage_sensors(db, anlage)
    if not sensor_values:
        return {"available": True, "no_data": True, "total": 0, "success": 0, "failed": 0, "errors": []}

    result = await client.publish_all_sensors(sensor_values, anlage.id, anlage.anlagenname)
    return {
        "available": True,
        "no_data": False,
        "total": result.get("total", len(sensor_values)),
        "success": result.get("success", 0),
        "failed": result.get("failed", 0),
        "errors": result.get("errors", []),
    }


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
