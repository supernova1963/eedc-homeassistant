"""
MQTT Live History Service.

Periodische Snapshots der MQTT Live-Leistungsdaten (W) in SQLite,
um den Tagesverlauf-Chart im Standalone-MQTT-Modus zu ermöglichen.

Snapshots: alle 5 Minuten via Scheduler.
Retention: 15 Tage.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.database import get_session
from backend.models.anlage import Anlage
from backend.models.mqtt_live_snapshot import MqttLiveSnapshot
from backend.services.mqtt_inbound_service import get_mqtt_inbound_service

logger = logging.getLogger(__name__)

# Basis-Keys die als Live-Leistungswerte (W) interpretiert werden
_BASIS_POWER_KEYS = {
    "einspeisung_w",
    "netzbezug_w",
    "pv_gesamt_w",
    "netz_kombi_w",
}

# Investment-Keys die als Live-Leistungswerte (W) interpretiert werden
_INV_POWER_KEYS = {
    "leistung_w",
    "leistung_heizen_w",
    "leistung_warmwasser_w",
}


async def snapshot_live_cache() -> int:
    """
    Snapshots aktuelle MQTT Live-W-Werte in die DB.

    Returns:
        Anzahl geschriebener Snapshot-Einträge.
    """
    mqtt_svc = get_mqtt_inbound_service()
    if not mqtt_svc:
        return 0

    all_live = mqtt_svc.cache.get_all_live_raw()
    if not all_live:
        return 0

    # Gültige Anlage-IDs aus DB holen (verhindert FK-Fehler)
    async with get_session() as session:
        result = await session.execute(select(Anlage.id))
        valid_ids = {row[0] for row in result.all()}

    now = datetime.now()
    count = 0
    rows = []

    for anlage_id, cache in all_live.items():
        if anlage_id not in valid_ids:
            logger.debug("MQTT Live Snapshot: anlage_id=%d unbekannt, übersprungen", anlage_id)
            continue

        # Basis-Werte
        for key, (value, _ts) in cache.get("basis", {}).items():
            if key in _BASIS_POWER_KEYS:
                rows.append(MqttLiveSnapshot(
                    anlage_id=anlage_id,
                    timestamp=now,
                    component_key=f"basis:{key}",
                    value_w=value,
                ))

        # Investitions-Werte
        for inv_id, inv_data in cache.get("inv", {}).items():
            for key, (value, _ts) in inv_data.items():
                if key in _INV_POWER_KEYS:
                    rows.append(MqttLiveSnapshot(
                        anlage_id=anlage_id,
                        timestamp=now,
                        component_key=f"inv:{inv_id}:{key}",
                        value_w=value,
                    ))

    if not rows:
        return 0

    async with get_session() as session:
        session.add_all(rows)
        await session.commit()
        count = len(rows)

    logger.debug("MQTT Live Snapshot: %d Einträge geschrieben", count)
    return count


async def cleanup_old_snapshots(retention_days: int = 15) -> int:
    """
    Löscht Snapshots älter als retention_days.

    Returns:
        Anzahl gelöschter Einträge.
    """
    cutoff = datetime.now() - timedelta(days=retention_days)

    async with get_session() as session:
        result = await session.execute(
            delete(MqttLiveSnapshot).where(MqttLiveSnapshot.timestamp < cutoff)
        )
        await session.commit()
        deleted = result.rowcount

    if deleted > 0:
        logger.info("MQTT Live Cleanup: %d alte Snapshots gelöscht", deleted)
    return deleted


async def get_snapshots_for_range(
    anlage_id: int, start: datetime, end: datetime, db: AsyncSession
) -> list[MqttLiveSnapshot]:
    """
    Lädt alle Power-Snapshots für einen Zeitraum.

    Args:
        start: Startzeit (inklusiv)
        end: Endzeit (exklusiv)

    Returns:
        Liste aller MqttLiveSnapshot-Einträge im Zeitraum.
    """
    result = await db.execute(
        select(MqttLiveSnapshot)
        .where(
            MqttLiveSnapshot.anlage_id == anlage_id,
            MqttLiveSnapshot.timestamp >= start,
            MqttLiveSnapshot.timestamp < end,
        )
        .order_by(MqttLiveSnapshot.timestamp)
    )
    return list(result.scalars().all())
