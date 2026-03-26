"""
MQTT Gateway Service — Topic-Translator für EEDC.

Subscribt auf konfigurierte Quell-Topics, transformiert Payloads
und re-publisht auf EEDC-Inbound-Topics (eedc/{id}/live/...).
Der bestehende MqttInboundService empfängt diese dann automatisch.

Läuft als Background-Task parallel zum MqttInboundService,
nutzt denselben Broker (gleiche Credentials).
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from backend.services.activity_service import log_activity

logger = logging.getLogger(__name__)

try:
    import aiomqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False


# ─── Payload Transformation ──────────────────────────────────────────

def transform_payload(
    payload: str,
    payload_typ: str,
    json_pfad: str | None,
    array_index: int | None,
    faktor: float,
    offset: float,
    invertieren: bool,
) -> float | None:
    """Transformiert einen MQTT-Payload in einen Float-Wert.

    Pipeline: Rohwert → JSON-Extraktion → × Faktor → + Offset → × (-1 wenn invertieren)
    """
    try:
        if payload_typ == "plain":
            raw = float(payload.strip())

        elif payload_typ == "json":
            data = json.loads(payload)
            if not json_pfad:
                return None
            for key in json_pfad.split("."):
                if isinstance(data, list):
                    data = data[int(key)]
                else:
                    data = data[key]
            raw = float(data)

        elif payload_typ == "json_array":
            data = json.loads(payload)
            if array_index is None:
                return None
            raw = float(data[array_index])

        else:
            return None

        result = raw * faktor + offset
        if invertieren:
            result = -result
        return result

    except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None


# ─── Mapping Dataclass (leichtgewichtig, aus DB geladen) ─────────────

@dataclass
class GatewayMapping:
    """Ein einzelnes Topic-Mapping (aus DB geladen)."""
    id: int
    anlage_id: int
    quell_topic: str
    ziel_key: str
    payload_typ: str = "plain"
    json_pfad: str | None = None
    array_index: int | None = None
    faktor: float = 1.0
    offset: float = 0.0
    invertieren: bool = False


@dataclass
class GatewayStats:
    """Laufzeit-Statistiken des Gateway."""
    empfangen: int = 0
    weitergeleitet: int = 0
    transform_fehler: int = 0
    gestartet_um: datetime | None = None


# ─── Service ─────────────────────────────────────────────────────────

class MqttGatewayService:
    """
    Subscribt auf konfigurierte Quell-Topics, transformiert Payloads
    und publisht auf EEDC-Inbound-Topics.
    """

    def __init__(self, host: str, port: int,
                 username: Optional[str] = None,
                 password: Optional[str] = None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self._mappings: dict[str, list[GatewayMapping]] = {}  # topic → [mappings]
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._stats = GatewayStats()

    def load_mappings(self, mappings: list[GatewayMapping]) -> None:
        """Gruppiert Mappings nach Quell-Topic für schnellen Lookup."""
        self._mappings.clear()
        for m in mappings:
            self._mappings.setdefault(m.quell_topic, []).append(m)
        logger.info("MQTT-Gateway: %d Mappings geladen (%d Topics)",
                     sum(len(v) for v in self._mappings.values()),
                     len(self._mappings))

    async def start(self) -> bool:
        """Startet den Gateway als Background-Task."""
        if not MQTT_AVAILABLE:
            logger.warning("MQTT-Gateway: aiomqtt nicht installiert")
            return False

        if not self._mappings:
            logger.info("MQTT-Gateway: Keine aktiven Mappings, nicht gestartet")
            return False

        if self._running:
            return True

        self._running = True
        self._stats = GatewayStats(gestartet_um=datetime.utcnow())
        self._task = asyncio.create_task(self._subscribe_loop())
        logger.info("MQTT-Gateway: gestartet (%s:%d, %d Topics)",
                     self.host, self.port, len(self._mappings))
        await log_activity(
            kategorie="mqtt",
            aktion="MQTT-Gateway gestartet",
            erfolg=True,
            details=f"Broker: {self.host}:{self.port}, {len(self._mappings)} Topics",
        )
        return True

    async def stop(self) -> None:
        """Stoppt den Gateway."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("MQTT-Gateway: gestoppt")

    async def _subscribe_loop(self) -> None:
        """Subscribe-Loop mit Auto-Reconnect."""
        while self._running:
            try:
                async with aiomqtt.Client(
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    identifier="eedc-gateway",
                ) as client:
                    # Subscribe auf alle konfigurierten Quell-Topics
                    for topic in self._mappings:
                        await client.subscribe(topic)

                    logger.info("MQTT-Gateway: %d Topics subscribed", len(self._mappings))

                    async for message in client.messages:
                        if not self._running:
                            break
                        await self._handle_message(client, message)

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.warning("MQTT-Gateway: Verbindung verloren (%s), Reconnect in 10s...", e)
                    await log_activity(
                        kategorie="mqtt",
                        aktion="MQTT-Gateway Verbindung verloren",
                        erfolg=False,
                        details=f"{type(e).__name__}: {e}",
                    )
                    await asyncio.sleep(10)

    async def _handle_message(self, client: "aiomqtt.Client", message) -> None:
        """Transformiert und re-publisht eine Nachricht."""
        topic = str(message.topic)
        payload = message.payload.decode("utf-8", errors="replace") if isinstance(message.payload, bytes) else str(message.payload)

        mappings = self._mappings.get(topic, [])
        if not mappings:
            return

        self._stats.empfangen += 1

        for mapping in mappings:
            wert = transform_payload(
                payload,
                mapping.payload_typ,
                mapping.json_pfad,
                mapping.array_index,
                mapping.faktor,
                mapping.offset,
                mapping.invertieren,
            )
            if wert is None:
                self._stats.transform_fehler += 1
                continue

            ziel_topic = f"eedc/{mapping.anlage_id}/{mapping.ziel_key}"
            await client.publish(ziel_topic, str(round(wert, 2)))
            self._stats.weitergeleitet += 1

    def get_status(self) -> dict:
        """Status + Statistiken."""
        return {
            "aktiv": self._running,
            "broker": f"{self.host}:{self.port}" if self._running else None,
            "topics_subscribed": len(self._mappings),
            "mappings_gesamt": sum(len(v) for v in self._mappings.values()),
            "empfangen": self._stats.empfangen,
            "weitergeleitet": self._stats.weitergeleitet,
            "transform_fehler": self._stats.transform_fehler,
            "gestartet_um": self._stats.gestartet_um.isoformat() if self._stats.gestartet_um else None,
        }

    async def reload(self, mappings: list[GatewayMapping]) -> bool:
        """Hot-Reload: Mappings neu laden, Service neu starten."""
        was_running = self._running
        if was_running:
            await self.stop()
        self.load_mappings(mappings)
        if was_running or self._mappings:
            return await self.start()
        return False


# ─── Singleton ───────────────────────────────────────────────────────

_mqtt_gateway_service: Optional[MqttGatewayService] = None


def get_mqtt_gateway_service() -> Optional[MqttGatewayService]:
    """Gibt die Singleton-Instanz zurück (None wenn nicht initialisiert)."""
    return _mqtt_gateway_service


def init_mqtt_gateway_service(
    host: str, port: int,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> MqttGatewayService:
    """Erstellt und speichert die Singleton-Instanz."""
    global _mqtt_gateway_service
    _mqtt_gateway_service = MqttGatewayService(host, port, username, password)
    return _mqtt_gateway_service
