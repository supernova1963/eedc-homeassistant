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

import logging
from datetime import date, datetime, timedelta
from calendar import monthrange
from typing import Optional, List

import httpx

from backend.core.config import settings

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

    params = {
        "lat": latitude,
        "lon": longitude,
        "date": date_str,
    }

    if last_date_str:
        params["last_date"] = last_date_str

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

            return {
                "weather": weather,
                "sources": sources,
            }

    except httpx.TimeoutException:
        logger.error(f"Bright Sky: Timeout für {date_str}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"Bright Sky: HTTP-Fehler {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Bright Sky: Fehler: {e}")
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


async def fetch_brightsky_forecast(
    latitude: float,
    longitude: float,
    days: int = 10,
    timeout: float = 30.0
) -> Optional[dict]:
    """
    Ruft Wettervorhersage (MOSMIX) von Bright Sky ab.

    Hinweis: MOSMIX enthält KEINE direkte Globalstrahlung, nur:
    - sunshine (prognostizierte Sonnenscheindauer)
    - cloud_cover (Bewölkung)

    Für Strahlungsprognosen besser Open-Meteo verwenden!

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        days: Anzahl Tage (max ~10 bei MOSMIX)
        timeout: Timeout in Sekunden

    Returns:
        dict mit täglichen Vorhersagedaten oder None
    """
    today = date.today()
    end_date = today + timedelta(days=days)

    data = await fetch_brightsky_weather(
        latitude, longitude,
        today.isoformat(),
        end_date.isoformat(),
        timeout
    )

    if not data or not data.get("weather"):
        return None

    # Nach Tagen gruppieren
    daily_data = {}
    for hour in data["weather"]:
        timestamp = hour.get("timestamp", "")
        if not timestamp:
            continue

        tag = timestamp[:10]
        if tag not in daily_data:
            daily_data[tag] = {
                "sunshine_minutes": 0,
                "temp_max": None,
                "temp_min": None,
                "precipitation": 0,
                "cloud_cover_sum": 0,
                "cloud_cover_count": 0,
                "conditions": [],
            }

        day = daily_data[tag]

        # Sonnenschein aggregieren
        sunshine = hour.get("sunshine")
        if sunshine is not None:
            day["sunshine_minutes"] += sunshine

        # Temperatur min/max
        temp = hour.get("temperature")
        if temp is not None:
            if day["temp_max"] is None or temp > day["temp_max"]:
                day["temp_max"] = temp
            if day["temp_min"] is None or temp < day["temp_min"]:
                day["temp_min"] = temp

        # Niederschlag summieren
        precip = hour.get("precipitation")
        if precip is not None:
            day["precipitation"] += precip

        # Bewölkung für Durchschnitt
        cloud = hour.get("cloud_cover")
        if cloud is not None:
            day["cloud_cover_sum"] += cloud
            day["cloud_cover_count"] += 1

        # Wetterzustand
        condition = hour.get("condition")
        if condition and condition not in day["conditions"]:
            day["conditions"].append(condition)

    # In Tagesliste umwandeln
    tage = []
    for datum in sorted(daily_data.keys()):
        day = daily_data[datum]
        avg_cloud = (
            day["cloud_cover_sum"] / day["cloud_cover_count"]
            if day["cloud_cover_count"] > 0 else None
        )

        # Hauptwetterzustand bestimmen
        condition = "dry"
        if "thunderstorm" in day["conditions"]:
            condition = "thunderstorm"
        elif "rain" in day["conditions"]:
            condition = "rain"
        elif "snow" in day["conditions"]:
            condition = "snow"
        elif "fog" in day["conditions"]:
            condition = "fog"

        tage.append({
            "datum": datum,
            "sonnenstunden": round(day["sunshine_minutes"] / 60, 1),
            "temperatur_max_c": day["temp_max"],
            "temperatur_min_c": day["temp_min"],
            "niederschlag_mm": round(day["precipitation"], 1),
            "bewoelkung_prozent": round(avg_cloud) if avg_cloud else None,
            "wetter_zustand": condition,
            # Keine Globalstrahlung in MOSMIX!
            "globalstrahlung_kwh_m2": None,
        })

    return {
        "tage": tage,
        "abgerufen_am": datetime.now().isoformat(),
        "standort": {"latitude": latitude, "longitude": longitude},
        "datenquelle": "brightsky-mosmix",
        "hinweis": "MOSMIX enthält keine Globalstrahlungs-Prognose",
    }


async def get_brightsky_sources(
    latitude: float,
    longitude: float,
    timeout: float = 15.0
) -> Optional[List[dict]]:
    """
    Gibt verfügbare DWD-Stationen in der Nähe zurück.

    Nützlich für:
    - Anzeige der Datenquelle
    - Debug/Transparenz
    """
    params = {
        "lat": latitude,
        "lon": longitude,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(BRIGHTSKY_SOURCES_URL, params=params)
            response.raise_for_status()
            data = response.json()
            return data.get("sources", [])

    except Exception as e:
        logger.error(f"Bright Sky Sources: Fehler: {e}")
        return None
