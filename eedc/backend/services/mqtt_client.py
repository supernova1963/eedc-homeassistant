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
        unique_id = self._get_unique_id(sensor, anlage_id, investition_id)
        state_topic = self._get_state_topic(sensor, anlage_id, investition_id)
        if investition_id:
            # Der Geraetename traegt jetzt der Sensor — sonst hiessen die
            # Kennzahlen zweier Waermepumpen unter derselben Anlage gleich.
            # `investition_name` kann fehlen (Altaufrufe); dann bleibt es beim
            # nackten Sensornamen statt bei einem „None"-Praefix.
            sensor_name = f"{investition_name} {sensor.name}" if investition_name else sensor.name
        else:
            sensor_name = sensor.name

        payload = {
            "name": sensor_name,
            "unique_id": unique_id,
            "state_topic": state_topic,
            "icon": sensor.icon,
            "json_attributes_topic": f"{state_topic}/attributes",
        }

        # ── Optionale Felder, je Komponententyp (S2, 21.09.2026) ────────────
        #
        # ⚠ **Ein `binary_sensor` traegt weder `unit_of_measurement` noch
        # `state_class`.** HA kennt fuer ihn keine Einheit und keine
        # Langzeitstatistik ueber Zahlen — er kennt zwei Zustaende. Beides
        # mitzuschicken erzeugt in HA dieselbe Sorte Protokollzeile wie F-63
        # ("impossible considering device class") und kostet die Entitaet ihre
        # Statistik. Deshalb steht die Weiche HIER, an der einen Stelle, die
        # den Payload baut — nicht als Disziplin an 60 Definitionen.
        if sensor.komponente == "binary_sensor":
            # `payload_on`/`payload_off` sind HAs Default ("ON"/"OFF"), stehen
            # aber ausdruecklich da: `publish_sensor_value` schreibt genau
            # diese beiden Woerter, und ein stiller Default-Wechsel in HA
            # wuerde sonst erst beim Anwender auffallen.
            payload["payload_on"] = "ON"
            payload["payload_off"] = "OFF"
            # ── Verfuegbarkeit — die P4-Haelfte des Typs (B2b, 21.09.2026) ──
            #
            # ⛔ **Ein `binary_sensor` hat keinen Leerwert, also braucht er
            # einen Verfuegbarkeits-Kanal.** Wo ein `sensor` ohne Eingang
            # `"None"` meldet und in HA „unbekannt" zeigt (X-3), hat HA fuer
            # den `binary_sensor` nur zwei Nutzlasten — ein dritter Wert waere
            # „No matching payload found for entity". Ohne diesen Kanal bliebe
            # deshalb der **letzte** Zustand retained stehen, und eine
            # Automation bekaeme ihn als Wahrheit geliefert: faellt der
            # Preisabruf aus, stuende `eedc_guenstige_stunde` womoeglich
            # dauerhaft auf `ON` und liesse das Auto zur teuersten Stunde laden.
            # **ADR-002/P4 verlangt, dass ein fehlender Eingang sichtbar ist** —
            # in HA heisst das „nicht verfuegbar", nicht „zuletzt ON".
            #
            # ⚠ **Das vierte Topic gehoert zur Ruecknahme.** Es liegt wie die
            # anderen drei mit `retain=True` auf dem Broker; `alle_topics`
            # fuehrt es deshalb mit (sonst bliebe nach „Sensoren entfernen" ein
            # `offline` liegen — die #400-Klasse).
            payload["availability_topic"] = f"{state_topic}/availability"
            payload["payload_available"] = "online"
            payload["payload_not_available"] = "offline"
        else:
            if sensor.unit:
                payload["unit_of_measurement"] = sensor.unit
            if sensor.state_class:
                payload["state_class"] = sensor.state_class
        if sensor.device_class:
            payload["device_class"] = sensor.device_class
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

    # ── Die drei Topics eines Sensors — EINE Wahrheit ────────────────────────
    #
    # ⛔ **Warum das Helfer sind und keine Inline-Ausdrücke (#400, 28.08.):** Bis
    # hierher baute jede Stelle ihr Topic selbst — `_build_discovery_payload` und
    # `publish_sensor_value` je einmal den `state_topic`, `_get_config_topic` die
    # `unique_id` ein zweites Mal. `remove_sensor` musste dieselbe Bildung ein
    # drittes Mal treffen. **Weicht der Entfernen-Pfad auch nur in einem Zeichen
    # ab, räumt er ein Topic, das niemand geschrieben hat — und lässt das
    # geschriebene liegen, ohne dass irgendetwas rot wird.** Ein Publisher und
    # ein Remover, die ihre Adressen getrennt bilden, sind dieselbe Klasse wie
    # zwei Wahrheiten über denselben Broker (#655).

    def _get_unique_id(
        self,
        sensor: SensorDefinition,
        anlage_id: int,
        investition_id: Optional[int] = None,
    ) -> str:
        """Die `unique_id`, an der HA die Entität wiedererkennt."""
        if investition_id:
            return f"eedc_{anlage_id}_{investition_id}_{sensor.key}"
        return f"eedc_{anlage_id}_{sensor.key}"

    def _get_config_topic(
        self,
        sensor: SensorDefinition,
        anlage_id: int,
        investition_id: Optional[int] = None,
    ) -> str:
        """Generiert das Discovery Config Topic — je Komponententyp.

        ⚠ **Der Typ steht an der Definition, nicht hier** (S2): bis zum
        21.09.2026 war `sensor` an dieser Stelle fest verdrahtet und damit die
        einzige Stelle im Baum, die `discovery_prefix` benutzte. Ein zweiter
        Typ haette sonst eine zweite Topic-Bildung gebraucht — und genau
        getrennte Adressbildungen sind die Klasse hinter #400 (der Entferner
        traf ein Topic, das niemand geschrieben hatte).
        """
        unique_id = self._get_unique_id(sensor, anlage_id, investition_id)
        return f"{self.config.discovery_prefix}/{sensor.komponente}/{unique_id}/config"

    def _get_state_topic(
        self,
        sensor: SensorDefinition,
        anlage_id: int,
        investition_id: Optional[int] = None,
    ) -> str:
        """Generiert das Werte-Topic."""
        if investition_id:
            return (
                f"{self.config.state_prefix}/anlage/{anlage_id}"
                f"/investition/{investition_id}/{sensor.key}"
            )
        return f"{self.config.state_prefix}/anlage/{anlage_id}/{sensor.key}"

    def alle_topics(
        self,
        sensor: SensorDefinition,
        anlage_id: int,
        investition_id: Optional[int] = None,
    ) -> list[str]:
        """**Alle** Topics, die dieser Sensor auf dem Broker belegt.

        Config, Wert und Attribute — alle drei werden mit ``retain=True``
        publiziert und bleiben deshalb ohne aktives Zurücknehmen dauerhaft auf
        dem Broker liegen. Wer entfernt, entfernt diese Liste; wer sie kürzt,
        lässt Reste stehen, die eedc als entfernt meldet.

        ⭐ **Je Komponententyp verschieden, und zwar von selbst** (S2): das
        Config-Topic kommt aus ``_get_config_topic`` und traegt damit
        ``sensor.komponente``. Wer den Typ einer Definition aendert, aendert
        Publish **und** Ruecknahme in einem Zug — eine zweite Liste, die
        nachgepflegt werden muesste, gibt es nicht.

        ⭐ **Ein `binary_sensor` belegt VIER Topics** (B2b, 21.09.2026): dazu
        kommt ``{state_topic}/availability``, ebenfalls retained (s.
        ``_build_discovery_payload``). Die Abwahl eines einzelnen Sensors und
        „Sensoren entfernen" raeumen es damit mit; die **bestandsgetriebene**
        Haelfte (``verwaiste_topics``) faende es ohnehin, weil es unter
        ``{state_prefix}/anlage/{id}/`` liegt — aber sie laeuft nur beim
        vollstaendigen Entfernen, die Abwahl nicht.
        """
        state_topic = self._get_state_topic(sensor, anlage_id, investition_id)
        topics = [
            self._get_config_topic(sensor, anlage_id, investition_id),
            state_topic,
            f"{state_topic}/attributes",
        ]
        if sensor.komponente == "binary_sensor":
            topics.append(f"{state_topic}/availability")
        return topics

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

        ⭐ **Zwei Formen, je Komponententyp** (S2/B2b, 21.09.2026):

        * ``sensor`` — der Wert, gerundet nach dem Kanon; ohne Wert der
          HA-Leerwert ``"None"`` (X-3), die Entitaet zeigt „unbekannt".
        * ``binary_sensor`` — ``ON``/``OFF`` auf dem State-Topic **und**
          ``online``/``offline`` auf ``{state_topic}/availability``. Ohne Wert
          wird **kein** State-Topic publiziert und die Entitaet **wird in HA
          nicht verfuegbar** — sie behaelt nicht ihren letzten Zustand (das war
          die Lage bis B2b und ist die Luecke, die ADR-002/P4 hier schliesst:
          ein veralteter Zustand ist fuer eine Automation eine falsche
          Wahrheit, kein fehlender Wert).

        Args:
            sensor_value: Sensor mit aktuellem Wert
            anlage_id: ID der Anlage
            investition_id: Optional - ID der Investition

        Returns:
            True wenn ein Zustand publiziert wurde. ``False`` heisst bei einem
            ``binary_sensor`` ohne Wert **nicht** „Fehler": ``offline`` ist
            dann geschrieben, ein Zustand bewusst nicht.
        """
        if not MQTT_AVAILABLE:
            return False

        sensor = sensor_value.definition

        # Topics bestimmen — dieselben Helfer, die auch `remove_sensor` benutzt.
        state_topic = self._get_state_topic(sensor, anlage_id, investition_id)
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

            # ── Zweiter Komponententyp: ON/OFF statt einer Zahl (S2) ────────
            #
            # ⚠ **Ein `binary_sensor` kennt in HA keinen Leerwert.** Wo ein
            # Sensor `"None"` bekommt und damit „unbekannt" zeigt (X-3, s. u.),
            # hat HA fuer den `binary_sensor` nur zwei Nutzlasten — alles andere
            # quittiert es mit „No matching payload found for entity". Deshalb
            # wird das State-Topic in dieser Lage **gar nicht** publiziert.
            #
            # ⭐ **Stattdessen wird die Entitaet in HA *nicht verfuegbar*
            # gemeldet** (B2b, 21.09.2026). Ohne diesen Kanal behielte das
            # retained State-Topic, was zuletzt galt — und eine Automation
            # bekaeme einen **veralteten Zustand als Wahrheit** geliefert: ein
            # ausgefallener Preisabruf liesse `eedc_guenstige_stunde` dauerhaft
            # auf `ON` stehen. ADR-002/P4 verlangt, dass ein fehlender Eingang
            # sichtbar ist; fuer einen `binary_sensor` ist „nicht verfuegbar"
            # die einzige Form, die HA dafuer kennt.
            #
            # ⚠ **Reihenfolge: erst `online`, dann der Zustand.** Umgekehrt
            # saehe HA fuer einen Augenblick einen Zustand an einer Entitaet,
            # die es noch fuer nicht verfuegbar haelt, und verwuerfe ihn.
            if sensor.komponente == "binary_sensor":
                verfuegbarkeits_topic = f"{state_topic}/availability"
                if value is None:
                    await client.publish(
                        verfuegbarkeits_topic, "offline", retain=True
                    )
                    return False
                await client.publish(
                    verfuegbarkeits_topic, "online", retain=True
                )
                await client.publish(
                    state_topic, "ON" if bool(value) else "OFF", retain=True
                )
                await client.publish(
                    attributes_topic, json.dumps(attributes), retain=True
                )
                return True

            if value is None:
                # B5/X-3 (05.09.2026): der Leerwert eines MQTT-Sensors ist in
                # Home Assistant der String ``"None"`` (``PAYLOAD_NONE`` in
                # ``homeassistant/components/mqtt/const.py``; ``mqtt/sensor.py``
                # setzt darauf ``native_value = None`` → Zustand „unbekannt").
                # ⛔ Hier stand ``"unknown"`` — für einen Sensor mit Einheit
                # oder ``state_class`` ist das in HA ein Fehler („has the
                # non-numeric value"), kein Leerwert. Der Pfad war nie
                # erreichbar: kein Produzent lieferte ``None``; seit X-3 tun es
                # gesperrte Kennzahlen und der Sync-Job für verschwundene
                # Sensoren.
                value = "None"
            else:
                value = runde_exportwert(value, sensor.unit, sensor.category)

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
        """Nimmt **alle** Topics eines Sensors vom Broker zurueck.

        Drei bei einem ``sensor`` (Config · Wert · Attribute), **vier** bei
        einem ``binary_sensor`` (dazu ``availability``) — die Liste kommt aus
        ``alle_topics`` und wird hier nicht zweitgebildet.

        Eine leere Nachricht auf ein retained Topic loescht die festgehaltene
        Nachricht. Auf dem Config-Topic entfernt HA damit die Entitaet; auf dem
        Werte- und Attribut-Topic verschwindet der zuletzt gehaltene Wert.

        ⛔ **Warum alle und nicht nur die Discovery (#400, Entscheid Gernot
        28.08.):** Alle werden mit ``retain=True`` publiziert
        (``publish_sensor_discovery`` · ``publish_sensor_value``). Bis hierher
        nahm das Entfernen nur das Config-Topic zurueck — die beiden anderen
        blieben mit ihrem letzten Wert dauerhaft auf dem Broker liegen, sichtbar
        in jedem MQTT-Client. Der Bestaetigen-Dialog sagt dem Anwender, dass
        seine Daten aus HA **und MQTT** verloren sind; blieben zwei Drittel der
        Nachrichten liegen, waere genau dieser Satz falsch. *Der Umfang des
        Aufraeumens folgt der Zusage, die wir dem Anwender machen.*

        ⚠ **Was eedc dabei NICHT anfasst: Home Assistant.** Kein Registry-Zugriff,
        keine Statistik-Loeschung. Was HA nach dem Entfernen der Entitaet an
        Langzeitstatistik behaelt, entscheidet HA. Der Dialog warnt bewusst nach
        der sicheren Seite — lieber zu viel Verlust angekuendigt als zu wenig.

        Args:
            sensor: Sensor-Definition
            anlage_id: ID der Anlage
            investition_id: Optional - ID der Investition

        Returns:
            True wenn **alle** Topics zurueckgenommen wurden
        """
        if not MQTT_AVAILABLE:
            return False

        topics = self.alle_topics(sensor, anlage_id, investition_id)

        try:
            async with aiomqtt.Client(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            ) as client:
                for topic in topics:
                    # Leere Nachricht auf ein retained Topic = Nachricht loeschen
                    await client.publish(topic, "", retain=True)
                return True
        except Exception as e:
            logger.warning("[MQTT] Fehler beim Entfernen von %s: %s: %s", sensor.key, type(e).__name__, e)
            return False

    async def verwaiste_topics(
        self,
        anlage_id: int,
        bekannte: set[str],
        sammelzeit_s: float = 1.5,
    ) -> list[str]:
        """Retained Topics **dieser Anlage**, die der heutige Export nicht kennt.

        ⭐ **Warum bestandsgetrieben und nicht definitionsgetrieben** (Entscheid
        Gernot 21.09.2026). Bis hierher raeumte „Sensoren entfernen" genau die
        Topics, die die **heutigen** Definitionen bilden. Was eedc frueher
        einmal publiziert hat, blieb damit fuer immer liegen — und es gibt
        solche Bestaende: die MWD-Startwerte als
        ``homeassistant/number/eedc_{anlage_id}_mwd_{feld}_start/config``
        (v1.1.0-beta.1, 17.02.2026; ersetzt am 13.03.2026 mit ``77c6e211``).
        In Gernots Produktion stehen davon bis heute **19** Entitaeten, alle
        ``unknown``. *Eine Liste, die nur die Gegenwart kennt, kann die
        Vergangenheit nicht aufraeumen — und sagt nie, dass sie es nicht tut.*

        ⛔ **Nur eigene Topics, und das ist die Grenze.** Zurueckgegeben —
        und damit spaeter geraeumt — wird ausschliesslich, was unter
        ``{state_prefix}/anlage/{anlage_id}/`` liegt oder dessen ``unique_id``
        mit ``eedc_{anlage_id}_`` beginnt. Ein fremdes retained Topic bleibt
        unberuehrt, auch das einer anderen eedc-Anlage. Dass das so bleibt,
        haelt ``test_s2_zweiter_komponententyp.py`` mit zwei Kontroll-Topics
        fest.

        ⚠ **Gelesen wird trotzdem mehr, und das laesst sich nicht vermeiden.**
        MQTT kennt keinen Praefix-Platzhalter: ``+`` steht fuer eine **ganze**
        Ebene, ``eedc_{anlage_id}_+`` ist deshalb kein gueltiger Filter und
        trifft nichts (am 21.09.2026 beim ersten Lauf der Probe genau so
        aufgefallen). Das Discovery-Abo lautet daher
        ``{discovery_prefix}/+/+/config`` und die Auswahl faellt **hier** im
        Code. Der Unterschied ist wichtig genug, um ihn zu benennen: eedc
        *sieht* waehrend der 1,5 s die Config-Topics anderer Integrationen —
        es merkt sich keines und fasst keines an.

        ⚠ **Retained-Sammeln braucht Zeit, nicht ein Signal.** Der Broker
        liefert die festgehaltenen Nachrichten direkt nach dem Abonnieren aus,
        sagt aber nicht, wann er fertig ist — dieselbe Lage wie im Inbound
        (``mqtt_inbound_service.py``). Deshalb ein Zeitfenster; es ist eine
        Wette auf einen langsamen Broker und bewusst grosszuegig. Was in
        dieser Zeit nicht kommt, bleibt liegen und wird beim naechsten
        Entfernen gefunden — ein zu kurzes Fenster kostet also nichts
        Unwiederbringliches.

        Args:
            anlage_id: nur Topics mit diesem Praefix werden betrachtet.
            bekannte: die Topics, die der heutige Export ohnehin zuruecknimmt.
            sammelzeit_s: Fenster, in dem retained Nachrichten eintreffen.

        Returns:
            Topics ausserhalb ``bekannte`` — leer, wenn aiomqtt fehlt oder der
            Broker nicht erreichbar ist (eine Ruecknahme, die am Broker
            scheitert, meldet das ueber ``remove_sensors``).
        """
        if not MQTT_AVAILABLE:
            return []

        gefunden: set[str] = set()
        alle_config = f"{self.config.discovery_prefix}/+/+/config"
        eigen_state = f"{self.config.state_prefix}/anlage/{anlage_id}/#"
        #: Das Praefix, an dem eedc seine eigenen Entitaeten erkennt — dieselbe
        #: Bildung wie `_get_unique_id`, damit Fund und Erzeugung nicht
        #: auseinanderlaufen koennen (#400-Klasse).
        eigen_praefix = f"/eedc_{anlage_id}_"
        state_praefix = f"{self.config.state_prefix}/anlage/{anlage_id}/"
        #: ⛔ **Die finalen Monatsdaten sind keine Sensor-Nachrichten und bleiben
        #: liegen** (`publish_final_month_data`, retained, ein Topic je Monat).
        #: Gemessen 21.09.2026 im HAOS-Lab: die erste Fassung der Bestandsaufnahme
        #: nahm `eedc/anlage/1/monatsdaten/2026/07` als „verwaist" mit — der Knopf
        #: heisst „Sensoren entfernen", und ein Monatsabschluss publiziert seine
        #: Nachricht nur einmal; ein Konsument in HA haette sie bis zum naechsten
        #: Abschluss verloren, ohne dass der Dialog das angekuendigt hat.
        monatsdaten_praefix = f"{state_praefix}monatsdaten/"
        try:
            async with aiomqtt.Client(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            ) as client:
                await client.subscribe(alle_config)
                await client.subscribe(eigen_state)

                async def _sammeln():
                    async for message in client.messages:
                        # Ein leeres Payload IST die Loeschung — ein Topic, das
                        # nur noch als Tombstone kommt, ist nichts zum Raeumen.
                        roh = message.payload
                        if roh is None or len(roh) == 0:
                            continue
                        topic = str(message.topic)
                        if not (topic.startswith(state_praefix)
                                or eigen_praefix in topic):
                            continue        # fremd — gesehen, nicht gemerkt
                        if topic.startswith(monatsdaten_praefix):
                            continue        # eigene Daten, kein Sensor — bleibt
                        gefunden.add(topic)

                try:
                    await asyncio.wait_for(_sammeln(), timeout=sammelzeit_s)
                except asyncio.TimeoutError:
                    pass
        except Exception as e:
            logger.warning(
                "[MQTT] Bestandsaufnahme fuer Anlage %s fehlgeschlagen: %s: %s",
                anlage_id, type(e).__name__, e,
            )
            return []

        return sorted(gefunden - set(bekannte))

    async def remove_sensors(
        self,
        eintraege: list[tuple[SensorDefinition, int, Optional[int]]],
        *,
        anlage_id_bestand: Optional[int] = None,
    ) -> dict:
        """Nimmt viele Sensoren ueber **eine** Verbindung zurueck.

        ``eintraege`` sind Tripel ``(sensor, anlage_id, investition_id)``.

        ⛔ **Warum sammelnd und nicht ``remove_sensor`` in einer Schleife:** Jeder
        Einzelaufruf oeffnet seine eigene Broker-Verbindung. Beim vollstaendigen
        Entfernen einer Anlage mit fuenf Komponenten sind das ueber dreihundert
        Verbindungsaufbauten fuer gut tausend Topics — der Knopf haette minutenlang
        gedreht. Hier ist es **eine** Verbindung.

        ``anlage_id_bestand`` (S2, 21.09.2026) schaltet die **bestandsgetriebene**
        Haelfte dazu: vor dem Raeumen fragt ``verwaiste_topics`` den Broker, was
        unter dem Praefix dieser Anlage sonst noch liegt, und nimmt es mit
        zurueck. Die Antwort weist es getrennt aus (``altlast_topics``) — wer
        aufraeumt, soll sehen, dass da etwas war.

        Returns:
            dict mit ``sensoren`` (zurueckgenommene Sensoren), ``topics`` und
            ``altlast_topics`` (die Liste der gefundenen Altlast-Topics)
        """
        if not MQTT_AVAILABLE or not eintraege:
            return {"sensoren": 0, "topics": 0, "altlast_topics": [], "fehler": None}

        topics: list[str] = []
        for sensor, anlage_id, investition_id in eintraege:
            topics.extend(self.alle_topics(sensor, anlage_id, investition_id))

        altlast: list[str] = []
        if anlage_id_bestand is not None:
            altlast = await self.verwaiste_topics(anlage_id_bestand, set(topics))

        try:
            async with aiomqtt.Client(
                hostname=self.config.host,
                port=self.config.port,
                username=self.config.username,
                password=self.config.password,
            ) as client:
                for topic in topics + altlast:
                    await client.publish(topic, "", retain=True)
            return {"sensoren": len(eintraege), "topics": len(topics) + len(altlast),
                    "altlast_topics": altlast, "fehler": None}
        except Exception as e:
            fehler = f"{type(e).__name__}: {e}"
            logger.warning("[MQTT] Sammel-Entfernen fehlgeschlagen — %s", fehler)
            return {"sensoren": 0, "topics": 0, "altlast_topics": [], "fehler": fehler}

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
