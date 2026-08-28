"""
MQTT Client für Home Assistant Integration.

Ermöglicht das Publizieren von eedc-Sensoren über MQTT Auto-Discovery.
Home Assistant erkennt die Sensoren automatisch und erstellt native Entitäten.

MQTT Discovery Format:
- Config Topic: homeassistant/sensor/{unique_id}/config
- State Topic: eedc/{anlage_id}/{sensor_key}
- Attributes Topic: eedc/{anlage_id}/{sensor_key}/attributes
"""

import json
import asyncio
import logging
from typing import Optional, Any
from dataclasses import dataclass

try:
    import aiomqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

from backend.core.config import APP_VERSION
from backend.services.ha_sensors_export import (
    SensorDefinition,
    SensorValue,
    runde_export_payload,
    runde_exportwert,
)

logger = logging.getLogger(__name__)


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
            logger.warning("[MQTT] Verbindungsfehler: %s: %s", type(e).__name__, e)
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
        # ── EIN Geraet je Anlage — der Geraetename wandert in den Sensornamen ──
        #
        # ⛔ **Hier stand bis zum 28.08.2026 `device_id = f"eedc_inv_{id}"`, und
        # das hat zwei Melder in 24 Stunden gekostet.** Mit v4.0.30 erreichten
        # die geraetebezogenen Sensoren erstmals MQTT — und legten dabei je
        # Investition ein EIGENES HA-Geraet an. Bei rapahl entstanden acht
        # eedc-Geraete, **sechs davon mit genau einer Entitaet**; bei Knallfrosch
        # sechs neue auf einmal (T89667 #236).
        #
        # ⭐ **Der Satz, der die Entscheidung getragen hat** (rapahl, PN 27.08.):
        # *„Bisher gab es ein uebergeordnetes Geraet mit den darunterliegenden
        # Entitaeten. Der Anlagenname wurde Teil des Sensornamens. Eine
        # einheitliche Struktur waere mir am liebsten."* — Dazu der Punkt, der
        # ein Aufraeumen in HA ausschliesst: *„Die kann man zwar bereinigen,
        # aber in der Registry bleiben die drin."*
        #
        # **Entscheid Gernot (28.08.):** Alle eedc-Sensoren gehoeren unter die
        # **Anlage**, „da die Benutzer sonst ein zusaetzliches Geraet zu dem
        # Geraet der Integration bekommen".
        #
        # ⭐ **Warum das keine Entitaet und keine Historie kostet:** `unique_id`
        # und `state_topic` haengen an der **Investition**, nicht am Geraet —
        # beide bleiben Zeichen fuer Zeichen gleich. HA erkennt dieselbe Entitaet
        # wieder und haengt sie lediglich unter ein anderes Geraet um;
        # Langzeitstatistik, Automationen und `entity_id` bleiben unberuehrt.
        # Das war die Bedingung, unter der die Umstellung ueberhaupt vertretbar
        # ist (die Alternative — Werte als Attribute — scheiterte genau daran:
        # Attribute kennen keine Langzeitstatistik).
        #
        # ⚠ **Der sichtbare Name aendert sich NICHT.** HA setzt ihn aus
        # Geraetename + Sensorname zusammen; heute „eedc - Smart #1" + „Gefahrene
        # km", kuenftig „eedc - <Anlage>" + „Smart #1 Gefahrene km". Beides ergibt
        # denselben Text — die Gruppierung aendert sich, die Beschriftung nicht.
        #
        # ⚠ **Was zurueckbleibt:** Die alten `eedc_inv_*`-Geraete verlieren ihre
        # Entitaeten und stehen dann leer da. Ein leeres Discovery-Payload wuerde
        # hier nicht helfen — das Config-Topic haengt an der `unique_id`, es zu
        # leeren loeschte die ENTITAET samt Historie. Home Assistant entfernt
        # entitaetenlose MQTT-Geraete beim naechsten Neustart bzw. Reload der
        # Integration; andernfalls sind sie einmalig von Hand loeschbar.
        device_id = f"eedc_anlage_{anlage_id}"
        device_name = f"eedc - {anlage_name}"
        if investition_id:
            unique_id = f"eedc_{anlage_id}_{investition_id}_{sensor.key}"
            state_topic = f"{self.config.state_prefix}/anlage/{anlage_id}/investition/{investition_id}/{sensor.key}"
            # Der Geraetename traegt jetzt der Sensor — sonst hiessen die
            # Kennzahlen zweier Waermepumpen unter derselben Anlage gleich.
            # `investition_name` kann fehlen (Altaufrufe); dann bleibt es beim
            # nackten Sensornamen statt bei einem „None"-Praefix.
            sensor_name = f"{investition_name} {sensor.name}" if investition_name else sensor.name
        else:
            unique_id = f"eedc_{anlage_id}_{sensor.key}"
            state_topic = f"{self.config.state_prefix}/anlage/{anlage_id}/{sensor.key}"
            sensor_name = sensor.name

        payload = {
            "name": sensor_name,
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
        if sensor.entity_category:
            payload["entity_category"] = sensor.entity_category

        # Device-Info für Gruppierung in HA
        payload["device"] = {
            "identifiers": [device_id],
            "name": device_name,
            "manufacturer": "eedc",
            "model": "PV-Auswertung",
            "sw_version": APP_VERSION,
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

        # Bewusst KEIN try/except: Fehler (z. B. Broker nicht erreichbar/Auth)
        # propagieren an publish_all_sensors, das sie mit Grund einsammelt/loggt.
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

        # Bewusst KEIN try/except: Fehler propagieren an publish_all_sensors.
        async with aiomqtt.Client(
            hostname=self.config.host,
            port=self.config.port,
            username=self.config.username,
            password=self.config.password,
        ) as client:
            # Wert publizieren — Rundung je Größenart aus dem SoT neben den
            # Sensor-Definitionen (PN 89905/2): kWh ganzzahlig, Geld auf Cent,
            # Prozent auf eine Stelle. Vorher trug JEDE Größe dieselben zwei
            # Nachkommastellen.
            value = sensor_value.value
            if value is None:
                value = "unknown"
            else:
                value = runde_exportwert(value, sensor.unit)

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
            logger.warning("[MQTT] Fehler beim Entfernen von %s: %s: %s", sensor.key, type(e).__name__, e)
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
        errors: list[str] = []

        for sv in sensor_values:
            try:
                # Discovery Config + Wert publizieren
                await self.publish_sensor_discovery(
                    sv.definition, anlage_id, anlage_name,
                    investition_id, investition_name
                )
                await self.publish_sensor_value(
                    sv, anlage_id, investition_id
                )
                success += 1
            except Exception as e:
                failed += 1
                msg = f"{sv.definition.key}: {type(e).__name__}: {e}"
                logger.warning("[MQTT] Publizieren fehlgeschlagen — %s", msg)
                if len(errors) < 3:  # Stichprobe für den Aufrufer (Log/Activity)
                    errors.append(msg)

        return {
            "total": len(sensor_values),
            "success": success,
            "failed": failed,
            "errors": errors,
        }

    async def publish_monatsdaten(
        self,
        anlage_id: int,
        jahr: int,
        monat: int,
        daten: dict,
        einheiten: Optional[dict[str, str]] = None,
    ) -> bool:
        """
        Publiziert finale Monatsdaten auf MQTT (retained).

        Ermöglicht HA-Automationen basierend auf Monatsdaten.

        Der zweite Payload desselben Clients — und damit derselben Regel
        unterworfen wie `publish_sensor` (N-54): gerundet wird hier, an der
        Serialisierungsgrenze, nicht beim Erzeuger. Struktur, Feldnamen und
        Topic bleiben unverändert; daran hängen fremde HA-Automationen.

        Args:
            anlage_id: ID der Anlage
            jahr: Jahr
            monat: Monat
            daten: Monatsdaten als Dict
            einheiten: Größenart je Feld (der Payload trägt keine mit) —
                ohne Eintrag greift die dimensionslose Vorgabe

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
                    json.dumps(runde_export_payload(daten, einheiten)),
                    retain=True
                )
                return True
        except Exception as e:
            logger.warning("[MQTT] Fehler beim Publizieren von Monatsdaten %s/%s: %s: %s", jahr, monat, type(e).__name__, e)
            return False
