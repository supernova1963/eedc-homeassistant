"""
Snapshot-Diagnose (E3 aus KONZEPT-ENERGIEPROFIL-3C.md).

Read-Helper auf der `quelle`-Spalte von `sensor_snapshots` für die
Datenverwaltung-Seite und Support-Anfragen — beantwortet Fragen wie
„Welcher Anteil meiner letzten 30 Tage kam aus HA-Native vs. MQTT-
Fallback?".

Kein Schreib-Pfad; reine SELECT-Aggregation.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.sensor_snapshot import SensorSnapshot


async def get_snapshot_source_distribution(
    db: AsyncSession,
    anlage_id: int,
    von: date,
    bis: date,
) -> dict[str, int]:
    """
    Liefert die Anzahl Snapshots pro `quelle` für eine Anlage im Zeitraum [von, bis).

    Args:
        db: Async Session
        anlage_id: Anlagen-ID
        von: Start (inklusiv, Tagesgrenze 00:00)
        bis: Ende (exklusiv, Tagesgrenze 00:00)

    Returns:
        {quelle: count}, z.B. {"ha_statistics": 720, "mqtt_inbound": 14, "unknown": 3}.
        Quellen ohne Treffer im Zeitraum sind nicht enthalten.
    """
    von_dt = datetime.combine(von, datetime.min.time())
    bis_dt = datetime.combine(bis, datetime.min.time())

    result = await db.execute(
        select(SensorSnapshot.quelle, func.count(SensorSnapshot.id))
        .where(
            and_(
                SensorSnapshot.anlage_id == anlage_id,
                SensorSnapshot.zeitpunkt >= von_dt,
                SensorSnapshot.zeitpunkt < bis_dt,
            )
        )
        .group_by(SensorSnapshot.quelle)
    )
    return {quelle: count for quelle, count in result.all()}


async def get_snapshot_source_distribution_recent(
    db: AsyncSession,
    anlage_id: int,
    days: int = 30,
) -> dict[str, int]:
    """Convenience-Wrapper: Verteilung der letzten `days` Tage bis heute (exklusiv)."""
    heute = date.today()
    return await get_snapshot_source_distribution(
        db, anlage_id, heute - timedelta(days=days), heute,
    )
