"""
MQTT Client für Home Assistant Integration.

Ermöglicht das Publizieren von EEDC-Sensoren über MQTT Auto-Discovery.
Home Assistant erkennt die Sensoren automatisch und erstellt native Entitäten.

MQTT Discovery Format:
- Config Topic: homeassistant/sensor/{unique_id}/config
- State Topic: eedc/{anlage_id}/{sensor_key}
- Attributes Topic: eedc/{anlage_id}/{sensor_key}/attributes

Monatswechsel-Sensoren (mwd_*):
- number.eedc_{anlage}_mwd_{feld}_start - Speichert Zählerstand Monatsanfang
- sensor.eedc_{anlage}_mwd_{feld}_monat - Berechnet aktuellen Monatswert via value_template
"""

import json
import asyncio
from typing import Optional, Any
from dataclasses import dataclass

try:
    import aiomqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

from backend.services.ha_sensors_export import SensorDefinition, SensorValue


@dataclass
class MQTTConfig:
    """MQTT-Broker Konfiguration."""
    host: str = "core-mosquitto"  # HA Mosquitto Add-on
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    discovery_prefix: str = "homeassistant"
    state_prefix: str = "eedc"


class MQTTClient:
    """
    Async MQTT Client für Home Assistant Discovery.

    Verwendet aiomqtt für asynchrone Kommunikation.
    Fallback auf synchronen Modus wenn aiomqtt nicht verfügbar.
    """

    def __init__(self, config: Optional[MQTTConfig] = None):
        self.config = config or MQTTConfig()
        self._client: Optional[Any] = None
        self._connected = False

    @property
    def is_available(self) -> bool:
        """Prüft ob MQTT-Bibliothek verfügbar ist."""
        return MQTT_AVAILABLE

    async def connect(self) -> bool:
        """
        Verbindet zum MQTT-Broker.

        Returns:
            True wenn erfolgreich verbunden
        """
        if not MQTT_AVAILABLE:
            return False

        try:
            # aiomqtt verwendet Context Manager, daher keine persistente Verbindung
            # Stattdessen testen wir die Verbindung
            async with aiomqtt.Client(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            ) as client:
                self._connected = True
                return True
        except Exception as e:
            print(f"[MQTT] Verbindungsfehler: {e}")
            self._connected = False
            return False

    async def test_connection(self) -> dict:
        """
        Testet die MQTT-Verbindung.

        Returns:
            Dict mit Status und Details
        """
        if not MQTT_AVAILABLE:
            return {
                "connected": False,
                "error": "aiomqtt Bibliothek nicht installiert",
                "hint": "pip install aiomqtt"
            }

        try:
            async with aiomqtt.Client(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            ) as client:
                return {
                    "connected": True,
                    "broker": f"{self.config.host}:{self.config.port}",
                    "message": "MQTT-Verbindung erfolgreich"
                }
        except Exception as e:
            return {
                "connected": False,
                "broker": f"{self.config.host}:{self.config.port}",
                "error": str(e)
            }

    def _build_discovery_payload(
        self,
        sensor: SensorDefinition,
        anlage_id: int,
        anlage_name: str,
        investition_id: Optional[int] = None,
        investition_name: Optional[str] = None,
    ) -> dict:
        """
        Baut das MQTT Discovery Payload für einen Sensor.

        Args:
            sensor: Sensor-Definition
            anlage_id: ID der Anlage
            anlage_name: Name der Anlage
            investition_id: Optional - ID der Investition
            investition_name: Optional - Name der Investition

        Returns:
            Dict für MQTT Discovery Config
        """
        # Unique ID erstellen
        if investition_id:
            unique_id = f"eedc_{anlage_id}_{investition_id}_{sensor.key}"
            state_topic = f"{self.config.state_prefix}/anlage/{anlage_id}/investition/{investition_id}/{sensor.key}"
            device_id = f"eedc_inv_{investition_id}"
            device_name = f"EEDC - {investition_name}"
        else:
            unique_id = f"eedc_{anlage_id}_{sensor.key}"
            state_topic = f"{self.config.state_prefix}/anlage/{anlage_id}/{sensor.key}"
            device_id = f"eedc_anlage_{anlage_id}"
            device_name = f"EEDC - {anlage_name}"

        payload = {
            "name": sensor.name,
            "unique_id": unique_id,
            "state_topic": state_topic,
            "icon": sensor.icon,
            "json_attributes_topic": f"{state_topic}/attributes",
        }

        # Optionale Felder
        if sensor.unit:
            payload["unit_of_measurement"] = sensor.unit
        if sensor.device_class:
            payload["device_class"] = sensor.device_class
        if sensor.state_class:
            payload["state_class"] = sensor.state_class

        # Device-Info für Gruppierung in HA
        payload["device"] = {
            "identifiers": [device_id],
            "name": device_name,
            "manufacturer": "EEDC",
            "model": "PV-Auswertung",
            "sw_version": "0.9.2",
        }

        return payload

    def _get_config_topic(
        self,
        sensor: SensorDefinition,
        anlage_id: int,
        investition_id: Optional[int] = None,
    ) -> str:
        """Generiert das Discovery Config Topic."""
        if investition_id:
            unique_id = f"eedc_{anlage_id}_{investition_id}_{sensor.key}"
        else:
            unique_id = f"eedc_{anlage_id}_{sensor.key}"

        return f"{self.config.discovery_prefix}/sensor/{unique_id}/config"

    async def publish_sensor_discovery(
        self,
        sensor: SensorDefinition,
        anlage_id: int,
        anlage_name: str,
        investition_id: Optional[int] = None,
        investition_name: Optional[str] = None,
    ) -> bool:
        """
        Publiziert die Discovery-Konfiguration für einen Sensor.

        Args:
            sensor: Sensor-Definition
            anlage_id: ID der Anlage
            anlage_name: Name der Anlage
            investition_id: Optional - ID der Investition
            investition_name: Optional - Name der Investition

        Returns:
            True wenn erfolgreich
        """
        if not MQTT_AVAILABLE:
            return False

        config_topic = self._get_config_topic(sensor, anlage_id, investition_id)
        payload = self._build_discovery_payload(
            sensor, anlage_id, anlage_name, investition_id, investition_name
        )

        try:
            async with aiomqtt.Client(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            ) as client:
                await client.publish(
                    config_topic,
                    json.dumps(payload),
                    retain=True
                )
                return True
        except Exception as e:
            print(f"[MQTT] Fehler beim Publizieren von {sensor.key}: {e}")
            return False

    async def publish_sensor_value(
        self,
        sensor_value: SensorValue,
        anlage_id: int,
        investition_id: Optional[int] = None,
    ) -> bool:
        """
        Publiziert den aktuellen Wert eines Sensors.

        Args:
            sensor_value: Sensor mit aktuellem Wert
            anlage_id: ID der Anlage
            investition_id: Optional - ID der Investition

        Returns:
            True wenn erfolgreich
        """
        if not MQTT_AVAILABLE:
            return False

        sensor = sensor_value.definition

        # Topics bestimmen
        if investition_id:
            state_topic = f"{self.config.state_prefix}/anlage/{anlage_id}/investition/{investition_id}/{sensor.key}"
        else:
            state_topic = f"{self.config.state_prefix}/anlage/{anlage_id}/{sensor.key}"

        attributes_topic = f"{state_topic}/attributes"

        # Attribute zusammenstellen
        attributes = {
            "formel": sensor.formel,
            "kategorie": sensor.category.value,
            "einheit": sensor.unit,
        }
        if sensor_value.berechnung:
            attributes["berechnung"] = sensor_value.berechnung
        attributes.update(sensor_value.zusatz_attribute)

        try:
            async with aiomqtt.Client(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            ) as client:
                # Wert publizieren
                value = sensor_value.value
                if value is None:
                    value = "unknown"
                elif isinstance(value, float):
                    value = round(value, 2)

                await client.publish(
                    state_topic,
                    str(value),
                    retain=True
                )

                # Attribute publizieren
                await client.publish(
                    attributes_topic,
                    json.dumps(attributes),
                    retain=True
                )

                return True
        except Exception as e:
            print(f"[MQTT] Fehler beim Publizieren von {sensor.key}: {e}")
            return False

    async def remove_sensor(
        self,
        sensor: SensorDefinition,
        anlage_id: int,
        investition_id: Optional[int] = None,
    ) -> bool:
        """
        Entfernt einen Sensor aus HA Discovery.

        Durch Publizieren einer leeren Nachricht auf das Config-Topic
        wird der Sensor aus HA entfernt.

        Args:
            sensor: Sensor-Definition
            anlage_id: ID der Anlage
            investition_id: Optional - ID der Investition

        Returns:
            True wenn erfolgreich
        """
        if not MQTT_AVAILABLE:
            return False

        config_topic = self._get_config_topic(sensor, anlage_id, investition_id)

        try:
            async with aiomqtt.Client(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            ) as client:
                # Leere Nachricht = Sensor entfernen
                await client.publish(config_topic, "", retain=True)
                return True
        except Exception as e:
            print(f"[MQTT] Fehler beim Entfernen von {sensor.key}: {e}")
            return False

    async def publish_all_sensors(
        self,
        sensor_values: list[SensorValue],
        anlage_id: int,
        anlage_name: str,
        investition_id: Optional[int] = None,
        investition_name: Optional[str] = None,
    ) -> dict:
        """
        Publiziert alle Sensoren (Discovery + Werte).

        Args:
            sensor_values: Liste der Sensor-Werte
            anlage_id: ID der Anlage
            anlage_name: Name der Anlage
            investition_id: Optional - ID der Investition
            investition_name: Optional - Name der Investition

        Returns:
            Dict mit Statistiken
        """
        success = 0
        failed = 0

        for sv in sensor_values:
            # Discovery Config publizieren
            disc_ok = await self.publish_sensor_discovery(
                sv.definition, anlage_id, anlage_name,
                investition_id, investition_name
            )

            # Wert publizieren
            value_ok = await self.publish_sensor_value(
                sv, anlage_id, investition_id
            )

            if disc_ok and value_ok:
                success += 1
            else:
                failed += 1

        return {
            "total": len(sensor_values),
            "success": success,
            "failed": failed
        }

    # =========================================================================
    # Monatswechsel-Sensoren (mwd_*)
    # =========================================================================

    def _build_device_info(self, anlage_id: int, anlage_name: str) -> dict:
        """Baut die Device-Info für MQTT Discovery (konsistent mit bestehenden Sensoren)."""
        return {
            "identifiers": [f"eedc_anlage_{anlage_id}"],
            "name": f"EEDC - {anlage_name}",
            "manufacturer": "EEDC",
            "model": "PV-Auswertung",
            "sw_version": "1.0.0",
        }

    async def publish_number_discovery(
        self,
        key: str,
        name: str,
        anlage_id: int,
        anlage_name: str,
        unit: str = "kWh",
        min_value: float = 0,
        max_value: float = 9999999,
        icon: str = "mdi:counter",
    ) -> bool:
        """
        Erstellt eine number Entity via MQTT Discovery.

        Diese Entities speichern Zählerstände vom Monatsanfang (retained).

        Args:
            key: Sensor-Key z.B. "mwd_einspeisung_start"
            name: Display-Name z.B. "EEDC Einspeisung Monatsanfang"
            anlage_id: ID der Anlage
            anlage_name: Name der Anlage
            unit: Einheit (default: kWh)
            min_value: Minimalwert (default: 0)
            max_value: Maximalwert (default: 9999999)
            icon: MDI Icon (default: mdi:counter)

        Returns:
            True wenn erfolgreich
        """
        if not MQTT_AVAILABLE:
            return False

        unique_id = f"eedc_{anlage_id}_{key}"
        state_topic = f"{self.config.state_prefix}/anlage/{anlage_id}/{key}/state"
        command_topic = f"{self.config.state_prefix}/anlage/{anlage_id}/{key}/set"
        config_topic = f"{self.config.discovery_prefix}/number/{unique_id}/config"

        payload = {
            "name": name,
            "unique_id": unique_id,
            "state_topic": state_topic,
            "command_topic": command_topic,
            "min": min_value,
            "max": max_value,
            "step": 0.01,
            "unit_of_measurement": unit,
            "device_class": "energy",
            "icon": icon,
            "retain": True,
            "device": self._build_device_info(anlage_id, anlage_name),
        }

        try:
            async with aiomqtt.Client(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            ) as client:
                await client.publish(
                    config_topic,
                    json.dumps(payload),
                    retain=True
                )
                return True
        except Exception as e:
            print(f"[MQTT] Fehler beim Erstellen von number {key}: {e}")
            return False

    async def publish_calculated_sensor(
        self,
        key: str,
        name: str,
        anlage_id: int,
        anlage_name: str,
        source_sensor: str,
        start_number_key: str,
        unit: str = "kWh",
        icon: str = "mdi:chart-line",
        device_class: str = "energy",
        state_class: str = "total",
    ) -> bool:
        """
        Erstellt einen Sensor mit value_template via MQTT Discovery.

        Dieser Sensor berechnet den Monatswert automatisch:
        aktueller_zählerstand - startwert_monatsanfang

        Args:
            key: Sensor-Key z.B. "mwd_einspeisung_monat"
            name: Display-Name z.B. "EEDC Einspeisung Monat"
            anlage_id: ID der Anlage
            anlage_name: Name der Anlage
            source_sensor: HA-Sensor für aktuellen Wert z.B. "sensor.stromzaehler_total"
            start_number_key: Key der number Entity z.B. "mwd_einspeisung_start"
            unit: Einheit (default: kWh)
            icon: MDI Icon (default: mdi:chart-line)
            device_class: Device Class (default: energy)
            state_class: State Class (default: total)

        Returns:
            True wenn erfolgreich
        """
        if not MQTT_AVAILABLE:
            return False

        unique_id = f"eedc_{anlage_id}_{key}"
        state_topic = f"{self.config.state_prefix}/anlage/{anlage_id}/{key}/state"
        config_topic = f"{self.config.discovery_prefix}/sensor/{unique_id}/config"

        # Number Entity ID für value_template
        number_entity_id = f"number.eedc_{anlage_id}_{start_number_key}"

        # value_template berechnet: aktueller_wert - startwert
        value_template = (
            f"{{{{ (states('{source_sensor}') | float(0) - "
            f"states('{number_entity_id}') | float(0)) | round(1) }}}}"
        )

        payload = {
            "name": name,
            "unique_id": unique_id,
            "state_topic": state_topic,
            "value_template": value_template,
            "unit_of_measurement": unit,
            "device_class": device_class,
            "state_class": state_class,
            "icon": icon,
            "device": self._build_device_info(anlage_id, anlage_name),
        }

        try:
            async with aiomqtt.Client(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            ) as client:
                await client.publish(
                    config_topic,
                    json.dumps(payload),
                    retain=True
                )
                return True
        except Exception as e:
            print(f"[MQTT] Fehler beim Erstellen von sensor {key}: {e}")
            return False

    async def update_month_start_value(
        self,
        anlage_id: int,
        key: str,
        wert: float,
    ) -> bool:
        """
        Publiziert neuen Startwert für Monatswechsel (retained).

        Wird am 1. des Monats aufgerufen, um den neuen Startwert zu setzen.

        Args:
            anlage_id: ID der Anlage
            key: Sensor-Key z.B. "mwd_einspeisung_start"
            wert: Zählerstand vom Monatsanfang

        Returns:
            True wenn erfolgreich
        """
        if not MQTT_AVAILABLE:
            return False

        state_topic = f"{self.config.state_prefix}/anlage/{anlage_id}/{key}/state"

        try:
            async with aiomqtt.Client(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            ) as client:
                await client.publish(
                    state_topic,
                    str(round(wert, 2)),
                    retain=True
                )
                return True
        except Exception as e:
            print(f"[MQTT] Fehler beim Aktualisieren von {key}: {e}")
            return False

    async def publish_monatsdaten(
        self,
        anlage_id: int,
        jahr: int,
        monat: int,
        daten: dict,
    ) -> bool:
        """
        Publiziert finale Monatsdaten auf MQTT (retained).

        Ermöglicht HA-Automationen basierend auf Monatsdaten.

        Args:
            anlage_id: ID der Anlage
            jahr: Jahr
            monat: Monat
            daten: Monatsdaten als Dict

        Returns:
            True wenn erfolgreich
        """
        if not MQTT_AVAILABLE:
            return False

        topic = f"{self.config.state_prefix}/anlage/{anlage_id}/monatsdaten/{jahr}/{monat:02d}"

        try:
            async with aiomqtt.Client(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            ) as client:
                await client.publish(
                    topic,
                    json.dumps(daten),
                    retain=True
                )
                return True
        except Exception as e:
            print(f"[MQTT] Fehler beim Publizieren von Monatsdaten {jahr}/{monat}: {e}")
            return False

    async def remove_mwd_sensors(
        self,
        anlage_id: int,
        keys: list[str],
    ) -> dict:
        """
        Entfernt Monatswechsel-Sensoren aus HA Discovery.

        Args:
            anlage_id: ID der Anlage
            keys: Liste der Sensor-Keys (ohne Präfix)

        Returns:
            Dict mit Statistiken
        """
        if not MQTT_AVAILABLE:
            return {"success": 0, "failed": len(keys)}

        success = 0
        failed = 0

        try:
            async with aiomqtt.Client(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            ) as client:
                for key in keys:
                    try:
                        # Number Entity entfernen
                        start_key = f"mwd_{key}_start"
                        number_config = f"{self.config.discovery_prefix}/number/eedc_{anlage_id}_{start_key}/config"
                        await client.publish(number_config, "", retain=True)

                        # Sensor Entity entfernen
                        monat_key = f"mwd_{key}_monat"
                        sensor_config = f"{self.config.discovery_prefix}/sensor/eedc_{anlage_id}_{monat_key}/config"
                        await client.publish(sensor_config, "", retain=True)

                        success += 1
                    except Exception as e:
                        print(f"[MQTT] Fehler beim Entfernen von {key}: {e}")
                        failed += 1

            return {"success": success, "failed": failed}
        except Exception as e:
            print(f"[MQTT] Verbindungsfehler beim Entfernen: {e}")
            return {"success": 0, "failed": len(keys)}
