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

# ── Negative Cache (Error-TTL) ──
# Verhindert API-Hammering bei Open-Meteo-Ausfällen.
# Bei Fehler wird der Cache-Key kurzzeitig gesperrt.
_error_cache: dict[str, float] = {}  # key → expires_at (monotonic)

ERROR_TTL_RATE_LIMIT = 300      # 429 Too Many Requests: 5 Minuten
ERROR_TTL_SERVER_ERROR = 120    # 502/503 Bad Gateway: 2 Minuten
ERROR_TTL_NETWORK = 60          # Timeout/ConnectError: 1 Minute


# ── Snapshot-Horizont: EIN OpenMeteo-Abruf je (Standort, Modell) ─────────────
# Größter im Baum benötigter Horizont. `/solar-prognose?tage=` und
# `/aussichten/kurzfristig?tage=` erlauben beide bis 16, der Prefetch wärmt 16 —
# und 16 ist zugleich das OpenMeteo-Maximum (`forecast_days`).
SNAPSHOT_HORIZONT_TAGE = 16


def snapshot_days(model: Optional[str] = None) -> int:
    """Kanonisches ``days`` für Cache-Key UND ``forecast_days`` (Entscheidung E15).

    **Warum es diese Funktion gibt.** Die Cache-Keys beider OpenMeteo-Räume
    (``gti:lat:lon:neigung:ausrichtung:days:model`` in
    ``solar_forecast_service`` und ``forecast:lat:lon:days:model`` hier im
    Wetter-Client) enthalten ``days``. Verschiedene Sichten fragen verschiedene
    Horizonte — der Kanon 4, der Prefetch 7 und 14, ``/solar-prognose`` bis 16 —
    also lag für DENSELBEN Tag je Sicht ein anderer Snapshot im Cache. Zwei
    Seiten zeigten für „morgen" zwei Zahlen, ohne dass sich die Rechnung
    unterschied (N20/N33). Seit dieser Funktion bestimmt **nicht mehr der
    Aufrufer** den Cache-Key, sondern das Modell: ein ``days``-Wert je
    ``(lat, lon, model)``, alle Aufrufer treffen denselben Eintrag.

    **Warum EIN langer Abruf und nicht ein Cache ohne ``days`` (Variante b).**

    * Die Antwort ist ein **echtes Präfix**: der API-Parameter heißt
      ``forecast_days``; ``days=16`` liefert Tag 0..15 und enthält den
      ``days=4``-Abruf vollständig. Variante (b) — Key ohne ``days``, längstes
      Fenster bedient kürzere Anfragen — müsste genau diese Eigenschaft in einer
      eigenen Cache-Schicht nachbauen, die die API bereits mitbringt.
    * Kostentreiber ist der **Request, nicht der Tag**: die Payload sind wenige
      KB; teuer sind Rate-Limit (``ERROR_TTL_RATE_LIMIT``) und der Jitter von
      1–30 s vor jedem Nicht-Prefetch-Call.
    * (b) verlagert Komplexität an die falsche Stelle: der Cache hier ist
      ``key → (expires_at, data)`` plus L2-Persistenz in ``ApiCache`` plus
      Negative-Cache über DENSELBEN Key. (b) verlangte zusätzlich eine
      Fensterlänge je Eintrag, eine „reicht das Fenster?"-Logik, den Mitzug des
      Negative-Caches und die L2-Rekonstruktion — eine neue Invariante ohne
      Wächter. (a) dagegen ist wächterbar: genau ein ``days``-Wert je
      ``(lat, lon, model)``, Baseline 0.

    **Warum ``min`` und nicht pauschal 16 (Auflage E15-a).** ``WETTER_MODELLE``
    gibt je Modell ein Maximum (icon_d2 2 Tage, icon_eu 5, ecmwf_ifs04 10 …).
    Ein pauschales 16 verfehlte nicht nur den Cache — es änderte Zahlen. Am
    2026-07-28 gemessen: ``models=icon_d2&forecast_days=16`` liefert 16
    Tageseinträge, ab Tag 3 aber ``None``. Die Modell-Kaskade in
    ``solar_forecast_service.get_solar_prognose`` bildet
    ``primary_dates`` aus den Daten der Primär-Antwort und lässt den
    best_match-Fallback nur die FEHLENDEN Tage auffüllen. Mit 16 leeren
    Primär-Tagen hätte der Fallback keinen einzigen Tag mehr beigesteuert, und
    Tag 3–16 wären auf den 0-Ertrag der leeren Antwort gefallen statt auf
    best_match.

    Seit A30/N16 reicht der Prognose-Kanon ``Anlage.wetter_modell`` durch —
    die Grenze greift dort seither in echt, nicht mehr nur vorsorglich.

    ⚑ **Nachtrag 2026-08-18 (F-36): dieser Absatz beschrieb eine Schwäche, die
    er nur zur Hälfte beseitigt hat.** Die Begrenzung nimmt der Kaskade die
    **ganz leeren** Tage jenseits des Horizonts — den **angeschnittenen Tag am
    Rand** lässt sie stehen, denn der liegt ja im Fenster. Bei ``icon_d2`` (2
    Tage) ist das der zweite: Open-Meteo liefert für ihn einen Eintrag, aber
    nur die Stunden bis zum Ende des Modelllaufs. An Gernots Anlage gemessen
    (2026-08-18): letzter GTI-Wert ``19.08. 08:00``, danach ``None`` — der
    Folgetag stand mit **0,3 kWh** zwischen 12,4 und 62,6 kWh.
    Die eigentliche Ursache, die hier oben richtig benannt ist („bildet
    ``primary_dates`` aus den Daten der Primär-Antwort"), ist seither behoben:
    der Merge-Vorrang hängt an der **Abdeckung** statt an der Existenz, siehe
    ``solar_forecast_service._merge_nach_abdeckung``. **Diese Funktion bleibt
    trotzdem richtig** — sie spart den sinnlosen Abruf leerer Tage und hält den
    Cache-Kanon; sie ist nur nicht mehr das, was den Fehler verhindert.

    Args:
        model: OpenMeteo-**Modellname** wie im Cache-Key (``icon_d2``,
            ``ecmwf_seamless``, …). ``None`` = best_match/``auto``.
    """
    # Import lokal: `models` ist reine Konfiguration, aber ein Modul-Import auf
    # dieser Ebene machte den Cache von der Modell-Schicht abhängig.
    from backend.services.wetter.models import WETTER_MODELLE

    max_je_modell = {
        (name or "auto"): tage for name, tage in WETTER_MODELLE.values()
    }
    return min(
        SNAPSHOT_HORIZONT_TAGE,
        max_je_modell.get(model or "auto", SNAPSHOT_HORIZONT_TAGE),
    )


def _error_cache_check(key: str) -> bool:
    """True wenn dieser Key kürzlich einen Fehler hatte → API-Call überspringen."""
    expires = _error_cache.get(key)
    if expires and expires > time.monotonic():
        return True
    return False


def _error_cache_set(key: str, ttl: int) -> None:
    """Sperrt einen Cache-Key für ttl Sekunden nach einem API-Fehler."""
    _error_cache[key] = time.monotonic() + ttl
    logger.debug(f"Negative-Cache: {key} gesperrt für {ttl}s")


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
