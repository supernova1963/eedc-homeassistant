"""
MQTT Inbound Service — Empfängt Live-Leistungsdaten via MQTT.

Universelle Datenbrücke: Jedes Smarthome-System (HA, ioBroker, FHEM, openHAB,
Node-RED) kann Live-Werte auf EEDC-Topics publishen.

Topic-Struktur (mit sprechenden Namen):
  eedc/{id}_{anlagename}/live/einspeisung_w
  eedc/{id}_{anlagename}/live/netzbezug_w
  eedc/{id}_{anlagename}/live/strompreis_ct          (dynamischer Strompreis, ct/kWh)
  eedc/{id}_{anlagename}/live/inv/{id}_{name}/leistung_w
  eedc/{id}_{anlagename}/live/inv/{id}_{name}/soc

  eedc/{id}_{anlagename}/energy/einspeisung_kwh
  eedc/{id}_{anlagename}/energy/inv/{id}_{name}/{key}

  Beispiel: eedc/1_Meine_PV_Anlage/live/inv/3_BYD_HVS/leistung_w
  Die numerische ID am Anfang jedes Segments ist die DB-ID, der Name ist optional.
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

from backend.services.activity_service import log_activity

logger = logging.getLogger(__name__)

try:
    import aiomqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False


# Topic-Pattern: eedc/{id}_{name}/live/{key} oder eedc/{id}_{name}/live/inv/{id}_{name}/{key}
# Die ID ist numerisch, der _name-Teil ist optional (für Lesbarkeit)
_TOPIC_RE = re.compile(
    r"^eedc/(\d+)(?:_[^/]*)?/(live|energy)/"
    r"(?:inv/(\d+)(?:_[^/]*)*/)?(.+)$"
)


class MqttInboundCache:
    """
    In-Memory-Cache für empfangene MQTT-Werte.

    Struktur:
      _live[anlage_id]["basis"][key] = (wert, timestamp)
      _live[anlage_id]["inv"][inv_id][key] = (wert, timestamp)
      _energy[anlage_id][key] = (wert, timestamp)
    """

    def __init__(self):
        self._live: dict[int, dict] = {}
        self._energy: dict[int, dict[str, tuple[float, datetime]]] = {}
        self._message_count = 0
        self._last_message_at: Optional[datetime] = None

    def on_message(self, topic: str, payload: str) -> None:
        """Verarbeitet eine eingehende MQTT-Nachricht."""
        m = _TOPIC_RE.match(topic)
        if not m:
            return

        anlage_id = int(m.group(1))
        category = m.group(2)  # "live" oder "energy"
        inv_id = m.group(3)    # None oder Investition-ID
        key = m.group(4)

        try:
            wert = float(payload)
        except (ValueError, TypeError):
            logger.debug("MQTT-Inbound: ungültiger Payload '%s' auf %s", payload, topic)
            return

        now = datetime.now()
        self._message_count += 1
        self._last_message_at = now

        if category == "live":
            if anlage_id not in self._live:
                self._live[anlage_id] = {"basis": {}, "inv": {}}
            cache = self._live[anlage_id]

            if inv_id:
                if inv_id not in cache["inv"]:
                    cache["inv"][inv_id] = {}
                cache["inv"][inv_id][key] = (wert, now)
            else:
                cache["basis"][key] = (wert, now)

        elif category == "energy":
            if anlage_id not in self._energy:
                self._energy[anlage_id] = {}
            self._energy[anlage_id][f"inv/{inv_id}/{key}" if inv_id else key] = (wert, now)

    def get_live_basis(self, anlage_id: int) -> dict[str, float]:
        """Gibt Basis-Live-Werte zurück (einspeisung_w, netzbezug_w)."""
        cache = self._live.get(anlage_id, {})
        basis = cache.get("basis", {})
        return {k: v[0] for k, v in basis.items()}

    def get_live_inv(self, anlage_id: int, inv_id: str) -> dict[str, float]:
        """Gibt Live-Werte für eine Investition zurück (leistung_w, soc)."""
        cache = self._live.get(anlage_id, {})
        inv_data = cache.get("inv", {}).get(inv_id, {})
        return {k: v[0] for k, v in inv_data.items()}

    def get_all_live_inv(self, anlage_id: int) -> dict[str, dict[str, float]]:
        """Gibt Live-Werte für alle Investitionen zurück."""
        cache = self._live.get(anlage_id, {})
        inv_data = cache.get("inv", {})
        return {
            inv_id: {k: v[0] for k, v in values.items()}
            for inv_id, values in inv_data.items()
        }

    def get_energy_data(self, anlage_id: int) -> dict[str, float]:
        """Gibt Energy-Werte zurück (einspeisung_kwh, netzbezug_kwh, inv/...)."""
        cache = self._energy.get(anlage_id, {})
        return {k: v[0] for k, v in cache.items()}

    def get_all_energy_raw(self) -> dict[int, dict[str, tuple[float, datetime]]]:
        """Gibt alle Energy-Daten mit Timestamps zurück (für History-Snapshots)."""
        return self._energy

    def get_all_live_raw(self) -> dict[int, dict]:
        """Gibt alle Live-Daten zurück (für Power-Snapshots).

        Struktur: {anlage_id: {"basis": {key: (val, ts)}, "inv": {inv_id: {key: (val, ts)}}}}
        """
        return self._live

    def has_data(self, anlage_id: int) -> bool:
        """Prüft ob MQTT-Daten für eine Anlage vorliegen."""
        cache = self._live.get(anlage_id, {})
        return bool(cache.get("basis") or cache.get("inv"))

    def clear_cache(self, anlage_id: Optional[int] = None) -> int:
        """Löscht Cache-Daten. Gibt Anzahl gelöschter Einträge zurück."""
        if anlage_id is not None:
            count = 0
            if anlage_id in self._live:
                live = self._live.pop(anlage_id)
                count += len(live.get("basis", {}))
                count += sum(len(v) for v in live.get("inv", {}).values())
            if anlage_id in self._energy:
                count += len(self._energy.pop(anlage_id))
            return count
        # Alle löschen
        count = 0
        for data in self._live.values():
            count += len(data.get("basis", {}))
            count += sum(len(v) for v in data.get("inv", {}).values())
        for data in self._energy.values():
            count += len(data)
        self._live.clear()
        self._energy.clear()
        self._message_count = 0
        self._last_message_at = None
        return count

    def get_status(self) -> dict:
        """Gibt Status-Informationen zurück."""
        anlagen_mit_daten = [
            aid for aid, data in self._live.items()
            if data.get("basis") or data.get("inv")
        ]
        return {
            "verfuegbar": MQTT_AVAILABLE,
            "empfangene_nachrichten": self._message_count,
            "letzte_nachricht": self._last_message_at.isoformat() if self._last_message_at else None,
            "anlagen_mit_daten": anlagen_mit_daten,
        }


class MqttInboundService:
    """
    Managed den MQTT-Subscriber für Inbound-Daten.

    Startet einen Background-Task der auf eedc/+/live/# und eedc/+/energy/#
    subscribt und den Cache befüllt.
    """

    def __init__(self, host: str, port: int,
                 username: Optional[str] = None,
                 password: Optional[str] = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.cache = MqttInboundCache()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self) -> bool:
        """Startet den MQTT-Subscriber als Background-Task."""
        if not MQTT_AVAILABLE:
            logger.warning("MQTT-Inbound: aiomqtt nicht installiert")
            return False

        if self._running:
            return True

        self._running = True
        self._task = asyncio.create_task(self._subscribe_loop())
        logger.info("MQTT-Inbound: Subscriber gestartet (%s:%d)", self.host, self.port)
        await log_activity(
            kategorie="mqtt",
            aktion="MQTT-Inbound gestartet",
            erfolg=True,
            details=f"Broker: {self.host}:{self.port}",
        )
        return True

    async def stop(self) -> None:
        """Stoppt den MQTT-Subscriber."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("MQTT-Inbound: Subscriber gestoppt")

    async def _subscribe_loop(self) -> None:
        """Subscribe-Loop mit Auto-Reconnect."""
        while self._running:
            try:
                async with aiomqtt.Client(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                ) as client:
                    await client.subscribe("eedc/+/live/#")
                    await client.subscribe("eedc/+/energy/#")
                    logger.info("MQTT-Inbound: Subscribed auf eedc/+/live/# und eedc/+/energy/#")

                    async for message in client.messages:
                        if not self._running:
                            break
                        topic = str(message.topic)
                        payload = message.payload.decode("utf-8", errors="replace") if isinstance(message.payload, bytes) else str(message.payload)
                        self.cache.on_message(topic, payload)

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.warning("MQTT-Inbound: Verbindung verloren (%s), Reconnect in 10s...", e)
                    await log_activity(
                        kategorie="mqtt",
                        aktion="MQTT-Inbound Verbindung verloren",
                        erfolg=False,
                        details=f"{type(e).__name__}: {e}",
                    )
                    await asyncio.sleep(10)

    def get_status(self) -> dict:
        """Gibt den Status des Services + Cache zurück."""
        status = self.cache.get_status()
        status["subscriber_aktiv"] = self._running
        status["broker"] = f"{self.host}:{self.port}"
        return status


# Singleton
_mqtt_inbound_service: Optional[MqttInboundService] = None


def get_mqtt_inbound_service() -> Optional[MqttInboundService]:
    """Gibt die Singleton-Instanz zurück (None wenn nicht initialisiert)."""
    return _mqtt_inbound_service


def init_mqtt_inbound_service(
    host: str, port: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> MqttInboundService:
    """Erstellt und speichert die Singleton-Instanz."""
    global _mqtt_inbound_service
    _mqtt_inbound_service = MqttInboundService(host, port, username, password)
    return _mqtt_inbound_service
