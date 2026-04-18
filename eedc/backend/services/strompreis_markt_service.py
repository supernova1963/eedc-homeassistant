"""
Strompreis-Markt-Service — Öffentliche EPEX Day-Ahead Preise via aWATTar API.

Liefert stündliche Börsenpreise (EPEX Spot DE/AT) für:
  1. Tagesverlauf-Overlay als Fallback (wenn kein eigener Sensor konfiguriert)
  2. Stündliche Mitschrift ins TagesEnergieProfil

Datenquelle: aWATTar API (frei, kein Auth nötig)
  - DE: https://api.awattar.de/v1/marketdata
  - AT: https://api.awattar.at/v1/marketdata

Einheit intern: ct/kWh (aWATTar liefert EUR/MWh → ÷ 10)
Cache: 2h TTL (Day-Ahead Preise ändern sich nur 1× täglich um 13:00 CET)
"""

import logging
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── API ──────────────────────────────────────────────────────────────────

AWATTAR_URLS = {
    "DE": "https://api.awattar.de/v1/marketdata",
    "AT": "https://api.awattar.at/v1/marketdata",
}

# ── Cache (einfacher In-Memory-Cache, reicht für Day-Ahead) ─────────────

_cache: dict[str, tuple[float, dict[int, float]]] = {}
CACHE_TTL = 7200  # 2 Stunden

# ── Negative Cache ──────────────────────────────────────────────────────

_error_cache: dict[str, float] = {}
ERROR_TTL_RATE_LIMIT = 300
ERROR_TTL_SERVER_ERROR = 120
ERROR_TTL_NETWORK = 60


def _cache_key(markt: str, datum: date) -> str:
    return f"awattar:{markt}:{datum.isoformat()}"


async def fetch_marktpreise(
    datum: date,
    markt: str = "DE",
    timeout: float = 15.0,
) -> Optional[dict[int, float]]:
    """
    Holt EPEX Day-Ahead Preise für einen Tag.

    Args:
        datum: Tag für den Preise geholt werden
        markt: "DE" oder "AT"
        timeout: HTTP-Timeout

    Returns:
        dict {stunde: preis_ct_kwh} (0-23) oder None bei Fehler.
        Preise sind Netto-Börsenpreise (ohne Steuern/Netzentgelte/Aufschläge).
    """
    key = _cache_key(markt, datum)

    # Cache prüfen
    cached = _cache.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]

    # Error-Cache prüfen
    err_expires = _error_cache.get(key)
    if err_expires and err_expires > time.monotonic():
        return None

    url = AWATTAR_URLS.get(markt)
    if not url:
        logger.warning("Strompreis-Markt: Unbekannter Markt '%s'", markt)
        return None

    # aWATTar erwartet Unix-Millisekunden
    start_dt = datetime(datum.year, datum.month, datum.day, tzinfo=timezone.utc)
    end_dt = start_dt + timedelta(days=1)
    params = {
        "start": str(int(start_dt.timestamp() * 1000)),
        "end": str(int(end_dt.timestamp() * 1000)),
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

    except httpx.TimeoutException:
        logger.warning("Strompreis-Markt: Timeout für %s %s", markt, datum)
        _error_cache[key] = time.monotonic() + ERROR_TTL_NETWORK
        return None
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        ttl = ERROR_TTL_RATE_LIMIT if status == 429 else ERROR_TTL_SERVER_ERROR
        logger.warning("Strompreis-Markt: HTTP %d für %s %s", status, markt, datum)
        _error_cache[key] = time.monotonic() + ttl
        return None
    except Exception as e:
        logger.warning("Strompreis-Markt: Fehler für %s %s: %s", markt, datum, e)
        _error_cache[key] = time.monotonic() + ERROR_TTL_NETWORK
        return None

    # Response parsen: [{start_timestamp, end_timestamp, marketprice, unit}]
    entries = data.get("data", [])
    if not entries:
        logger.debug("Strompreis-Markt: Keine Daten für %s %s", markt, datum)
        return None

    preise: dict[int, float] = {}
    for entry in entries:
        ts_ms = entry.get("start_timestamp")
        mp = entry.get("marketprice")  # EUR/MWh
        if ts_ms is None or mp is None:
            continue
        # Lokale Stunde (Europe/Berlin bzw. Vienna — beide CET/CEST)
        local_dt = datetime.fromtimestamp(ts_ms / 1000)
        stunde = local_dt.hour
        # EUR/MWh → ct/kWh (÷ 10)
        preise[stunde] = round(mp / 10, 2)

    if preise:
        _cache[key] = (time.monotonic() + CACHE_TTL, preise)
        logger.debug("Strompreis-Markt: %d Stunden für %s %s geladen", len(preise), markt, datum)

    return preise if preise else None


async def get_strompreis_stunden(
    anlage_land: Optional[str],
    datum: date,
) -> dict[int, float]:
    """
    Convenience-Wrapper: Holt Marktpreise passend zum Anlagen-Land.

    Args:
        anlage_land: ISO-Code des Landes (z.B. "DE", "AT") oder None → "DE"
        datum: Tag

    Returns:
        dict {stunde: ct_kwh} oder {} wenn nicht verfügbar
    """
    markt = "AT" if anlage_land and anlage_land.upper() in ("AT", "AUT") else "DE"
    result = await fetch_marktpreise(datum, markt=markt)
    return result or {}
