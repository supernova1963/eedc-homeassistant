"""
Snapshot-Fallback (MQTT-Live-Pfad).

Schreibt für eine anstehende volle Stunde Live-Snapshots aus MQTT-Topic-
Werten — Standalone-/Docker-Modus, wenn HA-Integration nicht verfügbar ist.
Der Add-on-Modus überlässt die laufende Stunde dem regulären :05-Hourly-Job
aus `writer.snapshot_anlage()` (`sum`-basiert, exakt — gegen prä-#184-State-
Spike-Falle).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot

from backend.services.snapshot.keys import _mqtt_key_to_sensor_key
from backend.services.snapshot.source import SnapshotSource
from backend.services.snapshot.writer import _upsert_snapshot

logger = logging.getLogger(__name__)


async def live_snapshot_if_missing(
    db: AsyncSession,
    anlage,
    zeitpunkt: datetime,
) -> int:
    """
    Schreibt für eine anstehende volle Stunde einen Live-Snapshot pro
    MQTT-Counter, aber nur wenn dort noch kein Eintrag existiert.

    Hintergrund: Der reguläre `snapshot_anlage` läuft erst :05 nach voller
    Stunde. Im Standalone-/Docker-Modus mit MQTT publishen die Geräte ihre
    kumulativen kWh-Werte kontinuierlich; ein Live-Snapshot kurz vor voller
    Stunde liefert einen guten Annäherungswert für die laufende Stunde.

    HA-Counter-Pfad (Add-on-Modus) wurde in v3.25.18 entfernt:
    `ha_state_svc.get_sensor_state()` liefert das Sensor-`state`, nicht das
    Statistics-`sum`. Bei Tagesreset-Zählern (utility_meter daily cycle) sind
    die zwei verschiedene Skalen — `state`=Tagesenergie, `sum`=Lifetime-
    bereinigt. Wurde der :05-Hourly-Job nach so einem Live-Schreiben
    übersprungen (HA/Add-on-Restart, Job-Crash), blieb der `state`-Wert
    persistent in der Snapshot-Tabelle und produzierte beim nächsten
    Aggregat einen Lifetime-grossen Stunden-Spike (Issue #184, Befund Rainer
    1.5.2026). Die laufende Stunde wartet im Add-on-Modus jetzt bis :05 der
    Folgestunde — wie vor #146 — und der reguläre `snapshot_anlage`-Job
    schreibt aus HA-Statistics den exakten `sum`-Wert.

    MQTT hat keinen `state`/`sum`-Split: Topics liefern direkt kumulative
    Lifetime-Werte. Der MQTT-Pfad bleibt unverändert.

    Args:
        db: Async Session
        anlage: Anlage-Objekt
        zeitpunkt: Anstehende volle Stunde (typisch: now+1h auf :00 gerundet)

    Returns:
        Anzahl geschriebener Live-Snapshots (MQTT-Counter).
    """
    count = 0

    # MQTT-gespeiste Zähler (Standalone-Modus): jüngsten Snapshot der
    # letzten ~10 Min als Live-Wert verwenden. Bei MQTT ist der Topic-Wert
    # die kumulative Lifetime-Energie (kein state/sum-Split wie bei HA).
    cutoff = zeitpunkt - timedelta(minutes=10)
    mqtt_keys_result = await db.execute(
        select(MqttEnergySnapshot.energy_key).where(
            and_(
                MqttEnergySnapshot.anlage_id == anlage.id,
                MqttEnergySnapshot.timestamp >= cutoff,
            )
        ).distinct()
    )
    for (mqtt_key,) in mqtt_keys_result.all():
        sensor_key = _mqtt_key_to_sensor_key(mqtt_key)
        if not sensor_key:
            continue
        existing = await db.execute(
            select(SensorSnapshot.id).where(
                and_(
                    SensorSnapshot.anlage_id == anlage.id,
                    SensorSnapshot.sensor_key == sensor_key,
                    SensorSnapshot.zeitpunkt == zeitpunkt,
                )
            )
        )
        if existing.scalar_one_or_none() is not None:
            continue
        # Jüngsten MQTT-Wert nehmen (innerhalb des cutoff-Fensters)
        recent = await db.execute(
            select(MqttEnergySnapshot.value_kwh).where(
                and_(
                    MqttEnergySnapshot.anlage_id == anlage.id,
                    MqttEnergySnapshot.energy_key == mqtt_key,
                    MqttEnergySnapshot.timestamp >= cutoff,
                )
            ).order_by(MqttEnergySnapshot.timestamp.desc()).limit(1)
        )
        wert = recent.scalar_one_or_none()
        if wert is None:
            continue
        await _upsert_snapshot(
            db, anlage.id, sensor_key, zeitpunkt, wert,
            quelle=SnapshotSource.MQTT_LIVE,
        )
        count += 1

    return count
