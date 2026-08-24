"""
Bright Sky Service - DWD-Daten über REST-API

Bright Sky ist ein kostenloser REST-Wrapper um DWD Open Data.
Bietet einfachen Zugang zu:
- Historische Wetterdaten (inkl. Globalstrahlung, Sonnenscheindauer)
- MOSMIX Vorhersagen

Vorteile gegenüber direktem DWD-Zugang:
- JSON statt ZIP/CSV
- Automatische Koordinaten-Interpolation
- Keine Station-ID-Suche nötig
- Bereits konvertierte Einheiten (kWh/m²)

Dokumentation: https://brightsky.dev/docs/
"""

import asyncio
import logging
import random
from datetime import date, datetime, timedelta
from calendar import monthrange
from typing import Optional

import httpx

from backend.core.config import settings
from backend.services.wetter.cache import _cache_get, _cache_set, FORECAST_CACHE_TTL, ARCHIVE_CACHE_TTL, JITTER_MAX_SECONDS

logger = logging.getLogger(__name__)

# Konstanten
BRIGHTSKY_WEATHER_URL = f"{settings.brightsky_api_url}/weather"
BRIGHTSKY_SOURCES_URL = f"{settings.brightsky_api_url}/sources"

# Deutschland Bounding Box (ungefähr)
GERMANY_BOUNDS = {
    "lat_min": 47.27,
    "lat_max": 55.06,
    "lon_min": 5.87,
    "lon_max": 15.04,
}


def is_in_germany(latitude: float, longitude: float) -> bool:
    """
    Prüft ob Koordinaten innerhalb Deutschlands liegen.

    Verwendet eine einfache Bounding Box - für Grenzfälle nicht 100% genau,
    aber ausreichend für die Provider-Auswahl.
    """
    return (
        GERMANY_BOUNDS["lat_min"] <= latitude <= GERMANY_BOUNDS["lat_max"] and
        GERMANY_BOUNDS["lon_min"] <= longitude <= GERMANY_BOUNDS["lon_max"]
    )


async def fetch_brightsky_weather(
    latitude: float,
    longitude: float,
    date_str: str,
    last_date_str: Optional[str] = None,
    timeout: float = 30.0
) -> Optional[dict]:
    """
    Ruft Wetterdaten von Bright Sky ab.

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        date_str: Startdatum (YYYY-MM-DD)
        last_date_str: Enddatum (optional, für Zeitraum)
        timeout: Timeout in Sekunden

    Returns:
        dict mit weather-Array und sources oder None bei Fehler
    """
    if not settings.brightsky_enabled:
        logger.debug("Bright Sky ist deaktiviert")
        return None

    # Cache prüfen (historisch → 24h, Zukunft → 60 Min)
    end_key = last_date_str or date_str
    is_historical = end_key < date.today().isoformat()
    ttl = ARCHIVE_CACHE_TTL if is_historical else FORECAST_CACHE_TTL
    cache_key = f"brightsky:{latitude:.2f}:{longitude:.2f}:{date_str}:{end_key}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug(f"Bright Sky: Cache-Hit für {date_str}")
        return cached

    params = {
        "lat": latitude,
        "lon": longitude,
        "date": date_str,
    }

    if last_date_str:
        params["last_date"] = last_date_str

    # Random-Jitter vor API-Call
    await asyncio.sleep(random.uniform(1, JITTER_MAX_SECONDS))

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(BRIGHTSKY_WEATHER_URL, params=params)
            response.raise_for_status()
            data = response.json()

            weather = data.get("weather", [])
            sources = data.get("sources", [])

            logger.debug(
                f"Bright Sky: {len(weather)} Stunden Daten für "
                f"({latitude}, {longitude}) am {date_str}"
            )

            result = {
                "weather": weather,
                "sources": sources,
            }
            _cache_set(cache_key, result, ttl)
            return result

    except httpx.TimeoutException:
        logger.error(f"Bright Sky: Timeout für {date_str}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"Bright Sky: HTTP-Fehler {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Bright Sky: Fehler: {type(e).__name__}: {e}")
        return None


async def fetch_brightsky_month(
    latitude: float,
    longitude: float,
    jahr: int,
    monat: int,
    timeout: float = 60.0
) -> Optional[dict]:
    """
    Ruft Wetterdaten für einen kompletten Monat ab.

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        jahr: Jahr
        monat: Monat (1-12)
        timeout: Timeout in Sekunden

    Returns:
        dict mit:
            - globalstrahlung_kwh_m2
            - sonnenstunden
            - tage_mit_daten
            - tage_gesamt
            - durchschnitts_temperatur_c
        oder None bei Fehler
    """
    # Prüfen ob Monat in der Vergangenheit liegt
    today = date.today()
    _, last_day = monthrange(jahr, monat)
    month_end = date(jahr, monat, last_day)

    if month_end >= today:
        logger.debug(f"Bright Sky: Monat {monat}/{jahr} noch nicht abgeschlossen")
        # Für laufenden Monat: bis gestern abfragen
        if date(jahr, monat, 1) < today:
            month_end = today - timedelta(days=1)
            last_day = month_end.day
        else:
            return None

    date_str = f"{jahr}-{monat:02d}-01"
    last_date_str = f"{jahr}-{monat:02d}-{last_day:02d}"

    data = await fetch_brightsky_weather(
        latitude, longitude, date_str, last_date_str, timeout
    )

    if not data or not data.get("weather"):
        return None

    weather = data["weather"]

    # Aggregieren
    total_solar = 0.0
    total_sunshine = 0.0
    total_temp = 0.0
    temp_count = 0
    tage_mit_solar = set()

    for hour in weather:
        # solar ist bereits in kWh/m² (pro Stunde)
        solar = hour.get("solar")
        if solar is not None:
            total_solar += solar
            # Tag merken
            timestamp = hour.get("timestamp", "")
            if timestamp:
                tage_mit_solar.add(timestamp[:10])

        # sunshine ist in Minuten pro Stunde
        sunshine = hour.get("sunshine")
        if sunshine is not None:
            total_sunshine += sunshine

        # Temperatur für Durchschnitt
        temp = hour.get("temperature")
        if temp is not None:
            total_temp += temp
            temp_count += 1

    avg_temp = total_temp / temp_count if temp_count > 0 else None

    result = {
        "globalstrahlung_kwh_m2": round(total_solar, 1),
        "sonnenstunden": round(total_sunshine / 60, 1),  # Minuten → Stunden
        "tage_mit_daten": len(tage_mit_solar),
        "tage_gesamt": last_day,
        "durchschnitts_temperatur_c": round(avg_temp, 1) if avg_temp else None,
    }

    logger.info(
        f"Bright Sky: {monat}/{jahr} @ ({latitude}, {longitude}) - "
        f"Globalstrahlung: {result['globalstrahlung_kwh_m2']} kWh/m², "
        f"Sonnenstunden: {result['sonnenstunden']}h, "
        f"Daten für {result['tage_mit_daten']}/{result['tage_gesamt']} Tage"
    )

    return result
