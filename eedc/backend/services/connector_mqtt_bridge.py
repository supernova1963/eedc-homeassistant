"""
Connector → MQTT Bridge.

Pollt konfigurierte Device-Connectors und publisht deren Live-Werte
auf EEDC-Inbound-Topics. Dadurch fließen Connector-Daten automatisch
durch die bestehende MQTT-Inbound-Pipeline ins Live-Dashboard,
den Energiefluss und den Tagesverlauf.

Läuft als periodischer Task (Standard: alle 10s für Live, alle 5min für Energy).
"""

import asyncio
import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from backend.services.connectors.base import LiveSnapshot
from backend.services.connectors.registry import get_connector
from backend.services.activity_service import log_activity

logger = logging.getLogger(__name__)

try:
    import aiomqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False


def _decode_password(encoded: str) -> str:
    """Base64-Decoding für Passwort (gleich wie in connector.py)."""
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded.encode()).decode()
    except Exception:
        return encoded


@dataclass
class BridgeStats:
    """Laufzeit-Statistiken."""
    polls: int = 0
    publishes: int = 0
    fehler: int = 0
    gestartet_um: datetime | None = None


@dataclass
class ConnectorTarget:
    """Ein konfigurierter Connector mit Ziel-Informationen."""
    anlage_id: int
    inv_id: int | None  # Investition-ID (wenn zugeordnet)
    connector_id: str
    host: str
    username: str
    password: str


class ConnectorMqttBridge:
    """Pollt konfigurierte Connectors und publisht Werte auf MQTT-Inbound-Topics."""

    def __init__(
        self,
        mqtt_host: str,
        mqtt_port: int,
        mqtt_username: Optional[str] = None,
        mqtt_password: Optional[str] = None,
        live_interval_s: int = 10,
    ):
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port
        self._mqtt_username = mqtt_username
        self._mqtt_password = mqtt_password
        self._live_interval = live_interval_s
        self._targets: list[ConnectorTarget] = []
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._stats = BridgeStats()

    def load_targets(self, targets: list[ConnectorTarget]) -> None:
        """Setzt die Liste der zu pollenden Connector-Targets."""
        self._targets = targets
        logger.info("Connector-Bridge: %d Targets geladen", len(targets))

    async def start(self) -> bool:
        """Startet die Bridge als Background-Task."""
        if not MQTT_AVAILABLE:
            logger.warning("Connector-Bridge: aiomqtt nicht installiert")
            return False

        if not self._targets:
            logger.info("Connector-Bridge: Keine Targets, nicht gestartet")
            return False

        if self._running:
            return True

        self._running = True
        self._stats = BridgeStats(gestartet_um=datetime.now(timezone.utc))
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Connector-Bridge: gestartet (%d Targets, %ds Intervall)",
                     len(self._targets), self._live_interval)
        await log_activity(
            kategorie="mqtt",
            aktion="Connector-Bridge gestartet",
            erfolg=True,
            details=f"{len(self._targets)} Targets, {self._live_interval}s Intervall",
        )
        return True

    async def stop(self) -> None:
        """Stoppt die Bridge."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("Connector-Bridge: gestoppt")

    async def _poll_loop(self) -> None:
        """Periodische Poll-Schleife."""
        while self._running:
            try:
                async with aiomqtt.Client(
                    hostname=self._mqtt_host,
                    port=self._mqtt_port,
                    username=self._mqtt_username,
                    password=self._mqtt_password,
                    identifier="eedc-connector-bridge",
                ) as client:
                    while self._running:
                        await self._poll_all(client)
                        await asyncio.sleep(self._live_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.warning("Connector-Bridge: Fehler (%s), Retry in 30s...", e)
                    await log_activity(
                        kategorie="mqtt",
                        aktion="Connector-Bridge Verbindungsfehler",
                        erfolg=False,
                        details=f"{type(e).__name__}: {e}",
                    )
                    await asyncio.sleep(30)

    async def _poll_all(self, client: "aiomqtt.Client") -> None:
        """Pollt alle Targets und publisht die Ergebnisse."""
        for target in self._targets:
            if not self._running:
                break
            try:
                connector = get_connector(target.connector_id)
                live = await connector.read_live(
                    target.host, target.username, target.password
                )
                if live:
                    await self._publish_live(client, target, live)
                    self._stats.polls += 1
            except Exception as e:
                self._stats.fehler += 1
                logger.debug("Connector-Bridge: Fehler bei %s/%s: %s",
                             target.connector_id, target.host, e)

    async def _publish_live(
        self,
        client: "aiomqtt.Client",
        target: ConnectorTarget,
        live: LiveSnapshot,
    ) -> None:
        """Publisht LiveSnapshot-Werte auf EEDC-Inbound-Topics."""
        prefix = f"eedc/{target.anlage_id}"

        if target.inv_id:
            # Investitions-spezifische Topics
            inv_prefix = f"{prefix}/live/inv/{target.inv_id}"
            if live.leistung_w is not None:
                await client.publish(f"{inv_prefix}/leistung_w", str(round(live.leistung_w, 1)))
                self._stats.publishes += 1
            if live.soc is not None:
                await client.publish(f"{inv_prefix}/soc", str(round(live.soc, 1)))
                self._stats.publishes += 1
        else:
            # Basis-Topics (Smart Meter, System-Level)
            if live.leistung_w is not None:
                await client.publish(f"{prefix}/live/pv_gesamt_w", str(round(live.leistung_w, 1)))
                self._stats.publishes += 1
            if live.einspeisung_w is not None:
                await client.publish(f"{prefix}/live/einspeisung_w", str(round(live.einspeisung_w, 1)))
                self._stats.publishes += 1
            if live.netzbezug_w is not None:
                await client.publish(f"{prefix}/live/netzbezug_w", str(round(live.netzbezug_w, 1)))
                self._stats.publishes += 1
            if live.batterie_ladung_w is not None:
                await client.publish(f"{prefix}/live/batterie_ladung_w", str(round(live.batterie_ladung_w, 1)))
                self._stats.publishes += 1
            if live.batterie_entladung_w is not None:
                await client.publish(f"{prefix}/live/batterie_entladung_w", str(round(live.batterie_entladung_w, 1)))
                self._stats.publishes += 1

    def get_status(self) -> dict:
        """Status + Statistiken."""
        return {
            "aktiv": self._running,
            "targets": len(self._targets),
            "intervall_s": self._live_interval,
            "polls": self._stats.polls,
            "publishes": self._stats.publishes,
            "fehler": self._stats.fehler,
            "gestartet_um": self._stats.gestartet_um.isoformat() if self._stats.gestartet_um else None,
        }

    async def reload(self, targets: list[ConnectorTarget]) -> bool:
        """Hot-Reload: Targets neu laden, Service neu starten."""
        was_running = self._running
        if was_running:
            await self.stop()
        self.load_targets(targets)
        if was_running or self._targets:
            return await self.start()
        return False


# ─── Singleton ───────────────────────────────────────────────────────

_bridge: Optional[ConnectorMqttBridge] = None


def get_connector_mqtt_bridge() -> Optional[ConnectorMqttBridge]:
    return _bridge


def init_connector_mqtt_bridge(
    mqtt_host: str, mqtt_port: int,
    mqtt_username: Optional[str] = None,
    mqtt_password: Optional[str] = None,
) -> ConnectorMqttBridge:
    global _bridge
    _bridge = ConnectorMqttBridge(mqtt_host, mqtt_port, mqtt_username, mqtt_password)
    return _bridge
