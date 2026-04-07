"""
Open-Meteo API Client: Archive (historisch) und Forecast (Vorhersage).

Archive: Vergangene Monate mit Globalstrahlung + Sonnenstunden.
Forecast: Bis 16 Tage mit optionaler Wettermodell-Auswahl.
"""

import asyncio
import logging
import random
from calendar import monthrange
from datetime import date, datetime
from typing import Optional

import httpx

from backend.services.wetter.cache import (
    _cache_get, _cache_set, _error_cache_check, _error_cache_set,
    FORECAST_CACHE_TTL, ARCHIVE_CACHE_TTL, JITTER_MAX_SECONDS,
    ERROR_TTL_RATE_LIMIT, ERROR_TTL_SERVER_ERROR, ERROR_TTL_NETWORK,
)
from backend.services.wetter.utils import MJ_TO_KWH, SECONDS_TO_HOURS

logger = logging.getLogger(__name__)

OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


async def fetch_open_meteo_archive(
    latitude: float,
    longitude: float,
    jahr: int,
    monat: int,
    timeout: float = 30.0
) -> Optional[dict]:
    """
    Ruft historische Wetterdaten von Open-Meteo Archive API ab.

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        jahr: Jahr
        monat: Monat (1-12)
        timeout: Timeout in Sekunden

    Returns:
        dict mit globalstrahlung_kwh_m2 und sonnenstunden oder None bei Fehler
    """
    # Datumsgrenzen für den Monat berechnen
    _, last_day = monthrange(jahr, monat)
    start_date = f"{jahr}-{monat:02d}-01"
    end_date = f"{jahr}-{monat:02d}-{last_day:02d}"

    # Prüfen ob Datum in der Vergangenheit liegt
    today = date.today()
    request_end = date(jahr, monat, last_day)

    if request_end >= today:
        logger.debug(f"Open-Meteo: Monat {monat}/{jahr} liegt nicht vollständig in Vergangenheit")
        return None

    # Cache prüfen (Archivdaten ändern sich nicht → 24h TTL)
    cache_key = f"archive:{latitude:.2f}:{longitude:.2f}:{jahr}:{monat}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug(f"Open-Meteo Archive: Cache-Hit für {monat}/{jahr}")
        return cached

    # Negative Cache: kürzlich fehlgeschlagen → API-Call überspringen
    if _error_cache_check(cache_key):
        logger.debug(f"Open-Meteo Archive: Negative-Cache-Hit für {monat}/{jahr}")
        return None

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "shortwave_radiation_sum,sunshine_duration",
        "timezone": "Europe/Berlin",
    }

    # Random-Jitter vor API-Call (verhindert Lastspitzen bei Open-Meteo)
    await asyncio.sleep(random.uniform(1, JITTER_MAX_SECONDS))

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(OPEN_METEO_ARCHIVE_URL, params=params)
            response.raise_for_status()
            data = response.json()

            daily = data.get("daily", {})
            radiation_values = daily.get("shortwave_radiation_sum", [])
            sunshine_values = daily.get("sunshine_duration", [])

            if not radiation_values or not sunshine_values:
                logger.warning(f"Open-Meteo: Keine Daten für {monat}/{jahr}")
                return None

            # Summe über alle Tage des Monats (None-Werte herausfiltern)
            radiation_sum = sum(v for v in radiation_values if v is not None)
            sunshine_sum = sum(v for v in sunshine_values if v is not None)

            # Konvertierung
            globalstrahlung_kwh = round(radiation_sum * MJ_TO_KWH, 1)
            sonnenstunden = round(sunshine_sum * SECONDS_TO_HOURS, 0)

            logger.info(
                f"Open-Meteo: {monat}/{jahr} @ ({latitude}, {longitude}) - "
                f"Globalstrahlung: {globalstrahlung_kwh} kWh/m², "
                f"Sonnenstunden: {sonnenstunden}h"
            )

            result = {
                "globalstrahlung_kwh_m2": globalstrahlung_kwh,
                "sonnenstunden": sonnenstunden,
                "tage_mit_daten": len([v for v in radiation_values if v is not None]),
                "tage_gesamt": last_day,
            }
            _cache_set(cache_key, result, ARCHIVE_CACHE_TTL)
            return result

    except httpx.TimeoutException:
        logger.error(f"Open-Meteo: Timeout für {monat}/{jahr}")
        _error_cache_set(cache_key, ERROR_TTL_NETWORK)
        return None
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        ttl = ERROR_TTL_RATE_LIMIT if status == 429 else ERROR_TTL_SERVER_ERROR
        logger.error(f"Open-Meteo: HTTP-Fehler {status} für {monat}/{jahr}")
        _error_cache_set(cache_key, ttl)
        return None
    except Exception as e:
        logger.error(f"Open-Meteo: Fehler für {monat}/{jahr}: {type(e).__name__}: {e}")
        _error_cache_set(cache_key, ERROR_TTL_NETWORK)
        return None


async def fetch_open_meteo_forecast(
    latitude: float,
    longitude: float,
    days: int = 16,
    timeout: float = 30.0,
    skip_jitter: bool = False,
    model: Optional[str] = None,
) -> Optional[dict]:
    """
    Ruft Wettervorhersage von Open-Meteo Forecast API ab (bis 16 Tage).

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        days: Anzahl Tage (max 16)
        timeout: Timeout in Sekunden
        skip_jitter: True bei Prefetch (kein Random-Delay)
        model: Open-Meteo Modellname (z.B. "icon_eu", "icon_d2").
               None = best_match (Open-Meteo Default).

    Returns:
        dict mit täglichen Vorhersagedaten oder None bei Fehler
    """
    days = min(days, 16)  # Open-Meteo Maximum

    # Cache prüfen (Forecast → 60 Min TTL, Key enthält Modell)
    model_key = model or "auto"
    cache_key = f"forecast:{latitude:.2f}:{longitude:.2f}:{days}:{model_key}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug(f"Open-Meteo Forecast: Cache-Hit ({days} Tage, {model_key})")
        return cached

    # Negative Cache: kürzlich fehlgeschlagen → API-Call überspringen
    if _error_cache_check(cache_key):
        logger.debug(f"Open-Meteo Forecast: Negative-Cache-Hit ({days} Tage, {model_key})")
        return None

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": ",".join([
            "shortwave_radiation_sum",
            "sunshine_duration",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "cloud_cover_mean",
            "weather_code"
        ]),
        "timezone": "Europe/Berlin",
        "forecast_days": days,
    }

    # Wettermodell ergänzen (None = best_match = Parameter weglassen)
    if model is not None:
        params["models"] = model

    # Random-Jitter vor API-Call (entfällt bei Prefetch)
    if not skip_jitter:
        await asyncio.sleep(random.uniform(1, JITTER_MAX_SECONDS))

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(OPEN_METEO_FORECAST_URL, params=params)
            response.raise_for_status()
            data = response.json()

            daily = data.get("daily", {})
            dates = daily.get("time", [])

            if not dates:
                logger.warning("Open-Meteo Forecast: Keine Daten erhalten")
                return None

            tage = []
            for i, datum in enumerate(dates):
                radiation = daily.get("shortwave_radiation_sum", [])[i]
                sunshine = daily.get("sunshine_duration", [])[i]

                tage.append({
                    "datum": datum,
                    "globalstrahlung_kwh_m2": round(radiation * MJ_TO_KWH, 2) if radiation is not None else None,
                    "sonnenstunden": round(sunshine * SECONDS_TO_HOURS, 1) if sunshine is not None else None,
                    "temperatur_max_c": daily.get("temperature_2m_max", [])[i],
                    "temperatur_min_c": daily.get("temperature_2m_min", [])[i],
                    "niederschlag_mm": daily.get("precipitation_sum", [])[i],
                    "bewoelkung_prozent": daily.get("cloud_cover_mean", [])[i],
                    "wetter_code": daily.get("weather_code", [])[i],
                })

            logger.info(
                f"Open-Meteo Forecast: {len(tage)} Tage @ ({latitude}, {longitude})"
                f" [Modell: {model_key}]"
            )

            result = {
                "tage": tage,
                "abgerufen_am": datetime.now().isoformat(),
                "standort": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
                "wetter_modell": model_key,
            }
            _cache_set(cache_key, result, FORECAST_CACHE_TTL)
            return result

    except httpx.TimeoutException:
        logger.error("Open-Meteo Forecast: Timeout")
        _error_cache_set(cache_key, ERROR_TTL_NETWORK)
        return None
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        ttl = ERROR_TTL_RATE_LIMIT if status == 429 else ERROR_TTL_SERVER_ERROR
        logger.error(f"Open-Meteo Forecast: HTTP-Fehler {status}")
        _error_cache_set(cache_key, ttl)
        return None
    except Exception as e:
        logger.error(f"Open-Meteo Forecast: Fehler: {type(e).__name__}: {e}")
        _error_cache_set(cache_key, ERROR_TTL_NETWORK)
        return None
