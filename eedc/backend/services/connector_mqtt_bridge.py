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

from backend.services.connectors.base import LiveSnapshot, MeterSnapshot
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
    inv_id: int | None  # Live-Pfad: Investition-ID (Legacy, derzeit ungenutzt)
    connector_id: str
    host: str
    username: str
    password: str
    # Energie-Pfad: pro Mess-Kategorie die zugeordnete Investition.
    # {"pv": inv_id, "speicher": inv_id, "wallbox": inv_id} — Grid (Einspeisung/
    # Netzbezug) bleibt immer anlagenweit, daher hier nicht enthalten.
    field_inv_map: dict[str, int] = field(default_factory=dict)


class ConnectorMqttBridge:
    """Pollt konfigurierte Connectors und publisht Werte auf MQTT-Inbound-Topics."""

    def __init__(
        self,
        mqtt_host: str,
        mqtt_port: int,
        mqtt_username: Optional[str] = None,
        mqtt_password: Optional[str] = None,
        live_interval_s: int = 10,
        energy_interval_s: int = 300,
    ):
        self._mqtt_host = mqtt_host
        self._mqtt_port = mqtt_port
        self._mqtt_username = mqtt_username
        self._mqtt_password = mqtt_password
        self._live_interval = live_interval_s
        self._energy_interval = energy_interval_s
        self._targets: list[ConnectorTarget] = []
        self._task: Optional[asyncio.Task] = None
        self._energy_task: Optional[asyncio.Task] = None
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
        # Zwei unabhängige Schleifen: schnelle Live-Watt (10s) und langsame
        # Energie-Zählerstände (5min). Getrennte MQTT-Clients, damit ein
        # Verbindungsabriss der einen die andere nicht blockiert.
        self._task = asyncio.create_task(
            self._connection_loop(
                "eedc-connector-bridge", self._live_interval, self._poll_all
            )
        )
        self._energy_task = asyncio.create_task(
            self._connection_loop(
                "eedc-connector-bridge-energy", self._energy_interval, self._poll_all_energy
            )
        )
        logger.info(
            "Connector-Bridge: gestartet (%d Targets, Live %ds / Energie %ds)",
            len(self._targets), self._live_interval, self._energy_interval,
        )
        await log_activity(
            kategorie="mqtt",
            aktion="Connector-Bridge gestartet",
            erfolg=True,
            details=f"{len(self._targets)} Targets, Live {self._live_interval}s / Energie {self._energy_interval}s",
        )
        return True

    async def stop(self) -> None:
        """Stoppt die Bridge."""
        self._running = False
        for attr in ("_task", "_energy_task"):
            task = getattr(self, attr)
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                setattr(self, attr, None)
        logger.info("Connector-Bridge: gestoppt")

    async def _connection_loop(self, identifier: str, interval: int, poll) -> None:
        """Generische Poll-Schleife mit eigener MQTT-Verbindung.

        `poll` ist eine async-Methode, die einen verbundenen Client erhält
        (`_poll_all` für Live-Watt, `_poll_all_energy` für kWh-Zählerstände).
        """
        while self._running:
            try:
                async with aiomqtt.Client(
                    hostname=self._mqtt_host,
                    port=self._mqtt_port,
                    username=self._mqtt_username,
                    password=self._mqtt_password,
                    identifier=identifier,
                ) as client:
                    while self._running:
                        await poll(client)
                        await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.warning("Connector-Bridge (%s): Fehler (%s), Retry in 30s...",
                                   identifier, e)
                    await log_activity(
                        kategorie="mqtt",
                        aktion="Connector-Bridge Verbindungsfehler",
                        erfolg=False,
                        details=f"{identifier}: {type(e).__name__}: {e}",
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

    async def _poll_all_energy(self, client: "aiomqtt.Client") -> None:
        """Pollt alle Targets nach Zählerständen (kWh) und publisht sie."""
        for target in self._targets:
            if not self._running:
                break
            try:
                connector = get_connector(target.connector_id)
                meters = await connector.read_meters(
                    target.host, target.username, target.password
                )
                if meters:
                    await self._publish_energy(client, target, meters)
                    self._stats.polls += 1
            except Exception as e:
                self._stats.fehler += 1
                logger.debug("Connector-Bridge (energy): Fehler bei %s/%s: %s",
                             target.connector_id, target.host, e)

    async def _publish_energy(
        self,
        client: "aiomqtt.Client",
        target: ConnectorTarget,
        meters: MeterSnapshot,
    ) -> None:
        """Publisht MeterSnapshot-Zählerstände auf EEDC-Energy-Inbound-Topics.

        Per-Investition (`energy/inv/{inv_id}/{feld}`) ist der Pflicht-Pfad —
        nur so summiert die Aggregation pro Gerät statt über die fixe
        kWp-Verteilung. `pv_gesamt_kwh` wird ausschließlich als Fallback
        publisht, wenn KEINE PV-Investition zugeordnet ist (sonst zwingt es
        die Aggregation in die kWp-Verteilungs-Falle).

        Grid (Einspeisung/Netzbezug) ist anlagenweit und geht immer auf die
        Basis-Topics. Nur non-None-Felder werden publisht.
        """
        prefix = f"eedc/{target.anlage_id}/energy"
        m = target.field_inv_map or {}

        async def pub(topic: str, value: float) -> None:
            await client.publish(topic, str(round(value, 3)))
            self._stats.publishes += 1

        # PV-Erzeugung → zugeordnete PV-Investition, sonst Fallback pv_gesamt_kwh
        if meters.pv_erzeugung_kwh is not None:
            pv_inv = m.get("pv")
            if pv_inv:
                await pub(f"{prefix}/inv/{pv_inv}/pv_erzeugung_kwh", meters.pv_erzeugung_kwh)
            else:
                await pub(f"{prefix}/pv_gesamt_kwh", meters.pv_erzeugung_kwh)

        # Speicher → Ladung/Entladung auf die zugeordnete Speicher-Investition.
        # Ohne Zuordnung gibt es kein anlagenweites Basis-Topic → verworfen.
        spe_inv = m.get("speicher")
        if spe_inv:
            if meters.batterie_ladung_kwh is not None:
                await pub(f"{prefix}/inv/{spe_inv}/ladung_kwh", meters.batterie_ladung_kwh)
            if meters.batterie_entladung_kwh is not None:
                await pub(f"{prefix}/inv/{spe_inv}/entladung_kwh", meters.batterie_entladung_kwh)

        # Wallbox → Ladung auf die zugeordnete Wallbox-Investition.
        wb_inv = m.get("wallbox")
        if wb_inv and meters.wallbox_ladung_kwh is not None:
            await pub(f"{prefix}/inv/{wb_inv}/ladung_kwh", meters.wallbox_ladung_kwh)

        # Grid: immer anlagenweite Basis-Topics
        if meters.einspeisung_kwh is not None:
            await pub(f"{prefix}/einspeisung_kwh", meters.einspeisung_kwh)
        if meters.netzbezug_kwh is not None:
            await pub(f"{prefix}/netzbezug_kwh", meters.netzbezug_kwh)

    def get_status(self) -> dict:
        """Status + Statistiken."""
        return {
            "aktiv": self._running,
            "targets": len(self._targets),
            "intervall_s": self._live_interval,
            "energie_intervall_s": self._energy_interval,
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


async def build_targets_from_db(session) -> list[ConnectorTarget]:
    """Baut die ConnectorTarget-Liste aus allen Anlagen mit Connector-Config.

    Gemeinsame Quelle für Boot (`main.py`) und Hot-Reload nach Mapping-Änderung
    (`connector.py`). Decodiert das Passwort und übernimmt die per-Kategorie-
    Investitions-Zuordnung (`field_inv_map`) aus der `connector_config`.
    """
    from sqlalchemy import select
    from backend.models.anlage import Anlage

    result = await session.execute(select(Anlage))
    targets: list[ConnectorTarget] = []
    for anlage in result.scalars().all():
        cfg = anlage.connector_config
        if not cfg or not cfg.get("connector_id") or not cfg.get("host"):
            continue
        # Nur valide int-Werte übernehmen (UI darf null = "keine Zuordnung" senden)
        raw_map = cfg.get("field_inv_map") or {}
        field_inv_map = {
            kat: int(inv_id)
            for kat, inv_id in raw_map.items()
            if inv_id is not None
        }
        targets.append(
            ConnectorTarget(
                anlage_id=anlage.id,
                inv_id=None,
                connector_id=cfg["connector_id"],
                host=cfg["host"],
                username=cfg.get("username", ""),
                password=_decode_password(cfg.get("password", "")),
                field_inv_map=field_inv_map,
            )
        )
    return targets


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
