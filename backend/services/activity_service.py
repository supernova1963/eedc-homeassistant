"""
Activity Log Service.

Stellt log_activity() zum Schreiben und get_activities() zum Abfragen bereit.
Enthält Auto-Cleanup für alte Einträge.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, delete, func, desc
from backend.core.database import get_session
from backend.models.activity_log import ActivityLog

logger = logging.getLogger(__name__)

MAX_ENTRIES = 1000
CLEANUP_INTERVAL_DAYS = 90


async def log_activity(
    kategorie: str,
    aktion: str,
    erfolg: bool = True,
    details: Optional[str] = None,
    details_json: Optional[dict] = None,
    anlage_id: Optional[int] = None,
):
    """
    Aktivität im persistenten Protokoll speichern.

    Nutzt eigene Session, kann von überall aufgerufen werden.
    Crasht nie den aufrufenden Code.
    """
    try:
        async with get_session() as session:
            entry = ActivityLog(
                kategorie=kategorie,
                aktion=aktion,
                erfolg=erfolg,
                details=details,
                details_json=details_json,
                anlage_id=anlage_id,
            )
            session.add(entry)
    except Exception as e:
        logger.warning(f"Aktivitätsprotokoll konnte nicht geschrieben werden: {e}")


async def get_activities(
    kategorie: Optional[str] = None,
    erfolg: Optional[bool] = None,
    anlage_id: Optional[int] = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """
    Activity Log mit Filtern abfragen.

    Returns:
        dict mit "items" Liste und "total" Anzahl
    """
    async with get_session() as session:
        query = select(ActivityLog).order_by(desc(ActivityLog.timestamp))
        count_query = select(func.count()).select_from(ActivityLog)

        if kategorie:
            query = query.where(ActivityLog.kategorie == kategorie)
            count_query = count_query.where(ActivityLog.kategorie == kategorie)
        if erfolg is not None:
            query = query.where(ActivityLog.erfolg == erfolg)
            count_query = count_query.where(ActivityLog.erfolg == erfolg)
        if anlage_id is not None:
            query = query.where(ActivityLog.anlage_id == anlage_id)
            count_query = count_query.where(ActivityLog.anlage_id == anlage_id)

        total_result = await session.execute(count_query)
        total = total_result.scalar() or 0

        query = query.offset(offset).limit(limit)
        result = await session.execute(query)
        items = [entry.to_dict() for entry in result.scalars().all()]

        return {"items": items, "total": total}


async def cleanup_old_activities():
    """Alte Activity-Log-Einträge bereinigen (>90 Tage oder >1000 Stück)."""
    async with get_session() as session:
        cutoff = datetime.utcnow() - timedelta(days=CLEANUP_INTERVAL_DAYS)
        await session.execute(
            delete(ActivityLog).where(ActivityLog.timestamp < cutoff)
        )

        count_result = await session.execute(
            select(func.count()).select_from(ActivityLog)
        )
        total = count_result.scalar() or 0

        if total > MAX_ENTRIES:
            threshold_result = await session.execute(
                select(ActivityLog.id)
                .order_by(desc(ActivityLog.timestamp))
                .offset(MAX_ENTRIES)
                .limit(1)
            )
            threshold_id = threshold_result.scalar()
            if threshold_id:
                await session.execute(
                    delete(ActivityLog).where(ActivityLog.id <= threshold_id)
                )
