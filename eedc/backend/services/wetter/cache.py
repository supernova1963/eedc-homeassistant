"""
L1/L2 Cache für Wetter-API-Antworten.

L1: In-Memory Dict (schnell, verliert Daten bei Neustart)
L2: SQLite-Tabelle api_cache (überlebt Neustarts)

Startup: warmup_l1_from_l2() lädt L2 → L1
Cleanup: cleanup_l2_cache() löscht abgelaufene L2-Einträge (täglich 04:00)
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# Flag: True sobald Event-Loop läuft (für fire-and-forget L2-Persist)
_loop_running = False

# ── In-Memory-Cache für Open-Meteo API-Antworten ──
# Reduziert API-Aufrufe: Forecast 60 Min, Archiv 24h Cache-TTL.
# Random-Jitter (1-30s) vor API-Calls verhindert Lastspitzen bei Open-Meteo.
_cache: dict[str, tuple[float, any]] = {}  # key → (expires_at, data)
FORECAST_CACHE_TTL = 3600       # 60 Minuten
ARCHIVE_CACHE_TTL = 86400       # 24 Stunden
JITTER_MAX_SECONDS = 30         # Max. zufällige Verzögerung vor API-Call


def _cache_get(key: str) -> Optional[any]:
    """Liefert gecachtes Ergebnis oder None wenn abgelaufen/nicht vorhanden."""
    entry = _cache.get(key)
    if entry and entry[0] > time.monotonic():
        return entry[1]
    return None


def _cache_set(key: str, data: any, ttl: int) -> None:
    """Speichert Ergebnis mit TTL im L1-Cache und persistiert in L2 (SQLite)."""
    _cache[key] = (time.monotonic() + ttl, data)
    # L2-Persist fire-and-forget (nur wenn Event-Loop läuft)
    if _loop_running:
        try:
            asyncio.get_event_loop().create_task(_persist_to_l2(key, data, ttl))
        except RuntimeError:
            pass  # Kein Event-Loop → Skip


async def _persist_to_l2(key: str, data: any, ttl: int) -> None:
    """Persistiert einen Cache-Eintrag in SQLite (L2)."""
    try:
        from backend.core.database import get_session
        from backend.models.api_cache import ApiCache
        from sqlalchemy import select

        now = datetime.utcnow()
        expires = now + timedelta(seconds=ttl)

        async with get_session() as db:
            result = await db.execute(
                select(ApiCache).where(ApiCache.cache_key == key)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.data = data
                existing.ttl_seconds = ttl
                existing.created_at = now
                existing.expires_at = expires
            else:
                db.add(ApiCache(
                    cache_key=key,
                    data=data,
                    ttl_seconds=ttl,
                    created_at=now,
                    expires_at=expires,
                ))
    except Exception as e:
        logger.debug(f"L2-Cache persist fehlgeschlagen für {key}: {e}")


async def warmup_l1_from_l2() -> int:
    """
    Lädt gültige L2-Cache-Einträge (SQLite) in den RAM-Cache (L1).

    Wird beim Server-Start aufgerufen, damit der erste Seitenaufruf
    sofort aus dem Cache bedient werden kann.

    Returns:
        Anzahl geladener Einträge
    """
    try:
        from backend.core.database import get_session
        from backend.models.api_cache import ApiCache
        from sqlalchemy import select

        now = datetime.utcnow()
        count = 0

        async with get_session() as db:
            result = await db.execute(
                select(ApiCache).where(ApiCache.expires_at > now)
            )
            entries = result.scalars().all()

            for entry in entries:
                remaining_seconds = (entry.expires_at - now).total_seconds()
                if remaining_seconds > 0:
                    _cache[entry.cache_key] = (
                        time.monotonic() + remaining_seconds,
                        entry.data,
                    )
                    count += 1

            # Abgelaufene Einträge gleich mitlöschen (Cleanup-Fallback)
            from sqlalchemy import delete
            cleaned = await db.execute(
                delete(ApiCache).where(ApiCache.expires_at <= now)
            )
            if cleaned.rowcount > 0:
                logger.info(f"Cache-Warmup: {cleaned.rowcount} abgelaufene L2-Einträge bereinigt")

        if count > 0:
            logger.info(f"Cache-Warmup: {count} Einträge aus L2 geladen")
        return count

    except Exception as e:
        logger.warning(f"Cache-Warmup aus L2 fehlgeschlagen: {e}")
        return 0


async def cleanup_l2_cache() -> int:
    """
    Löscht abgelaufene L2-Cache-Einträge aus SQLite.

    Returns:
        Anzahl gelöschter Einträge
    """
    try:
        from backend.core.database import get_session
        from backend.models.api_cache import ApiCache
        from sqlalchemy import delete

        now = datetime.utcnow()

        async with get_session() as db:
            result = await db.execute(
                delete(ApiCache).where(ApiCache.expires_at <= now)
            )
            count = result.rowcount
            if count > 0:
                logger.info(f"L2-Cache Cleanup: {count} abgelaufene Einträge gelöscht")
            return count

    except Exception as e:
        logger.warning(f"L2-Cache Cleanup fehlgeschlagen: {e}")
        return 0
