"""
PVGIS (Photovoltaic Geographical Information System) Client.

Liefert TMY (Typical Meteorological Year) Daten als Fallback
für aktuelle/zukünftige Monate wenn keine Archivdaten verfügbar.
"""

import asyncio
import logging
import random
from typing import Optional

import httpx

from backend.core.config import settings
from backend.services.wetter.cache import (
    _cache_get, _cache_set,
    ARCHIVE_CACHE_TTL, JITTER_MAX_SECONDS,
)

logger = logging.getLogger(__name__)

# PVGIS TMY Durchschnittswerte für verschiedene Breitengrade (Fallback)
# Basierend auf typischen Werten für Mitteleuropa (45-55°N)
PVGIS_TMY_DEFAULTS = {
    # Monat: (globalstrahlung_kwh_m2, sonnenstunden)
    1: (28, 55),
    2: (50, 85),
    3: (95, 145),
    4: (130, 195),
    5: (160, 235),
    6: (170, 260),
    7: (175, 275),
    8: (150, 250),
    9: (110, 180),
    10: (65, 120),
    11: (32, 55),
    12: (22, 40),
}


async def fetch_pvgis_tmy_monat(
    latitude: float,
    longitude: float,
    monat: int,
    timeout: float = 30.0
) -> Optional[dict]:
    """
    Ruft PVGIS TMY (Typical Meteorological Year) Daten für einen Monat ab.

    TMY-Daten sind langjährige Durchschnittswerte und eignen sich für:
    - Aktuelle Monate (noch nicht abgeschlossen)
    - Zukünftige Monate (Prognose)
    - Als Fallback wenn Open-Meteo nicht verfügbar

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        monat: Monat (1-12)
        timeout: Timeout in Sekunden

    Returns:
        dict mit globalstrahlung_kwh_m2 und sonnenstunden oder None bei Fehler
    """
    # Cache prüfen (TMY-Daten sind statistisch → 24h TTL)
    cache_key = f"pvgis_tmy:{latitude:.2f}:{longitude:.2f}:{monat}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug(f"PVGIS TMY: Cache-Hit für Monat {monat}")
        return cached

    # PVGIS TMY Endpoint
    url = f"{settings.pvgis_api_url}/tmy"
    params = {
        "lat": latitude,
        "lon": longitude,
        "outputformat": "json",
    }

    # Random-Jitter vor API-Call
    await asyncio.sleep(random.uniform(1, JITTER_MAX_SECONDS))

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            # TMY liefert stündliche Daten für ein typisches Jahr
            # Wir müssen die Stundenwerte für den Monat aggregieren
            hourly_data = data.get("outputs", {}).get("tmy_hourly", [])

            if not hourly_data:
                logger.warning(f"PVGIS TMY: Keine Daten für Monat {monat}")
                return None

            # Filtern nach Monat und aggregieren
            month_radiation = 0.0
            month_sunshine_hours = 0.0

            for hour in hourly_data:
                # Format: "20050101:0010" (YYYYMMDD:HHMM)
                time_str = hour.get("time", "")
                if len(time_str) >= 6:
                    hour_month = int(time_str[4:6])
                    if hour_month == monat:
                        # G(h) = Horizontal Global Irradiance (W/m²)
                        ghi = hour.get("G(h)", 0)
                        if ghi and ghi > 0:
                            # W/m² für 1 Stunde → Wh/m² → kWh/m² (÷1000)
                            month_radiation += ghi / 1000

                            # Sonnenstunde zählen wenn Strahlung > 120 W/m²
                            # (WMO Definition: Sonnenschein wenn Direktstrahlung > 120 W/m²)
                            if ghi > 120:
                                month_sunshine_hours += 1

            globalstrahlung_kwh = round(month_radiation, 1)
            sonnenstunden = round(month_sunshine_hours, 0)

            logger.info(
                f"PVGIS TMY: Monat {monat} @ ({latitude}, {longitude}) - "
                f"Globalstrahlung: {globalstrahlung_kwh} kWh/m², "
                f"Sonnenstunden: {sonnenstunden}h"
            )

            result = {
                "globalstrahlung_kwh_m2": globalstrahlung_kwh,
                "sonnenstunden": sonnenstunden,
            }
            _cache_set(cache_key, result, ARCHIVE_CACHE_TTL)
            return result

    except httpx.TimeoutException:
        logger.error(f"PVGIS TMY: Timeout für Monat {monat}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"PVGIS TMY: HTTP-Fehler {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"PVGIS TMY: Fehler für Monat {monat}: {type(e).__name__}: {e}")
        return None


def get_pvgis_tmy_defaults(monat: int, latitude: float = 48.0) -> dict:
    """
    Gibt statische TMY-Durchschnittswerte zurück (Fallback).

    Verwendet vordefinierte Werte für Mitteleuropa.
    Werte werden leicht angepasst basierend auf Breitengrad.

    Args:
        monat: Monat (1-12)
        latitude: Breitengrad (für leichte Anpassung)

    Returns:
        dict mit globalstrahlung_kwh_m2 und sonnenstunden
    """
    base_values = PVGIS_TMY_DEFAULTS.get(monat, (100, 150))

    # Leichte Anpassung nach Breitengrad
    # Südlichere Standorte: mehr Strahlung
    # Nördlichere Standorte: weniger Strahlung
    lat_factor = 1.0 + (48.0 - latitude) * 0.01  # ±1% pro Grad

    return {
        "globalstrahlung_kwh_m2": round(base_values[0] * lat_factor, 1),
        "sonnenstunden": round(base_values[1] * lat_factor, 0),
    }
