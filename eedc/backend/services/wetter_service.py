"""
Wetter-Service für automatische Globalstrahlung und Sonnenstunden.

Unterstützte Datenquellen (Provider):
- "auto": Automatische Auswahl (Bright Sky für DE, Open-Meteo sonst)
- "open-meteo": Open-Meteo Archive API (weltweit)
- "brightsky": Bright Sky API (DWD-Daten für Deutschland)
- "open-meteo-solar": Open-Meteo mit GTI (für PV-Prognosen)

Fallback-Kette:
1. Gewählter Provider
2. Alternative Provider
3. PVGIS TMY (langjährige Durchschnittswerte)
4. Statische Defaults

Konvertierungen:
- Open-Meteo: shortwave_radiation_sum (MJ/m²) → kWh/m² (÷ 3.6)
- Open-Meteo: sunshine_duration (Sekunden) → Stunden (÷ 3600)
- Bright Sky: solar (bereits kWh/m²), sunshine (Minuten → Stunden)
"""

import logging
from datetime import date, datetime
from calendar import monthrange
from typing import Optional, Literal

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

# Typ für Provider-Auswahl
WetterProvider = Literal["auto", "open-meteo", "brightsky", "open-meteo-solar"]

# Konstanten
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
MJ_TO_KWH = 1 / 3.6  # 1 MJ = 0.2778 kWh
SECONDS_TO_HOURS = 1 / 3600

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

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date,
        "end_date": end_date,
        "daily": "shortwave_radiation_sum,sunshine_duration",
        "timezone": "Europe/Berlin",
    }

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

            return {
                "globalstrahlung_kwh_m2": globalstrahlung_kwh,
                "sonnenstunden": sonnenstunden,
                "tage_mit_daten": len([v for v in radiation_values if v is not None]),
                "tage_gesamt": last_day,
            }

    except httpx.TimeoutException:
        logger.error(f"Open-Meteo: Timeout für {monat}/{jahr}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"Open-Meteo: HTTP-Fehler {e.response.status_code} für {monat}/{jahr}")
        return None
    except Exception as e:
        logger.error(f"Open-Meteo: Fehler für {monat}/{jahr}: {e}")
        return None


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
    # PVGIS TMY Endpoint
    url = f"{settings.pvgis_api_url}/tmy"
    params = {
        "lat": latitude,
        "lon": longitude,
        "outputformat": "json",
    }

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
                        # G(i) = Globalstrahlung auf geneigter Ebene (W/m²)
                        # Für horizontale Strahlung: Gb(n) + Gd(h) verwenden
                        ghi = hour.get("G(h)", 0)  # Horizontal Global Irradiance
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

            return {
                "globalstrahlung_kwh_m2": globalstrahlung_kwh,
                "sonnenstunden": sonnenstunden,
            }

    except httpx.TimeoutException:
        logger.error(f"PVGIS TMY: Timeout für Monat {monat}")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"PVGIS TMY: HTTP-Fehler {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"PVGIS TMY: Fehler für Monat {monat}: {e}")
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


async def get_wetterdaten(
    latitude: float,
    longitude: float,
    jahr: int,
    monat: int
) -> dict:
    """
    Hauptfunktion: Holt Wetterdaten mit automatischer Quellenauswahl.

    Strategie:
    1. Vergangene Monate → Open-Meteo Archive (echte historische Daten)
    2. Aktueller/Zukünftiger Monat → PVGIS TMY (Durchschnittswerte)
    3. Fallback bei Fehlern → Statische Defaults

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        jahr: Jahr
        monat: Monat (1-12)

    Returns:
        dict mit:
            - globalstrahlung_kwh_m2
            - sonnenstunden
            - datenquelle: "open-meteo" | "pvgis-tmy" | "defaults"
            - standort: {latitude, longitude}
    """
    today = date.today()
    request_date = date(jahr, monat, 1)

    result = {
        "jahr": jahr,
        "monat": monat,
        "standort": {
            "latitude": latitude,
            "longitude": longitude,
        },
    }

    # Strategie 1: Vergangene Monate → Open-Meteo
    if request_date < date(today.year, today.month, 1):
        logger.debug(f"Wetterdaten: Versuche Open-Meteo für {monat}/{jahr}")
        data = await fetch_open_meteo_archive(latitude, longitude, jahr, monat)

        if data:
            result.update({
                "globalstrahlung_kwh_m2": data["globalstrahlung_kwh_m2"],
                "sonnenstunden": data["sonnenstunden"],
                "datenquelle": "open-meteo",
                "abdeckung_prozent": round(data["tage_mit_daten"] / data["tage_gesamt"] * 100, 0),
            })
            return result

    # Strategie 2: PVGIS TMY (für aktuelle/zukünftige oder als Fallback)
    logger.debug(f"Wetterdaten: Versuche PVGIS TMY für Monat {monat}")
    data = await fetch_pvgis_tmy_monat(latitude, longitude, monat)

    if data:
        result.update({
            "globalstrahlung_kwh_m2": data["globalstrahlung_kwh_m2"],
            "sonnenstunden": data["sonnenstunden"],
            "datenquelle": "pvgis-tmy",
        })
        return result

    # Strategie 3: Statische Defaults als letzter Fallback
    logger.warning(f"Wetterdaten: Verwende Defaults für {monat}/{jahr}")
    defaults = get_pvgis_tmy_defaults(monat, latitude)
    result.update({
        "globalstrahlung_kwh_m2": defaults["globalstrahlung_kwh_m2"],
        "sonnenstunden": defaults["sonnenstunden"],
        "datenquelle": "defaults",
        "hinweis": "Durchschnittswerte für Mitteleuropa",
    })

    return result


async def fetch_open_meteo_forecast(
    latitude: float,
    longitude: float,
    days: int = 16,
    timeout: float = 30.0
) -> Optional[dict]:
    """
    Ruft Wettervorhersage von Open-Meteo Forecast API ab (bis 16 Tage).

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        days: Anzahl Tage (max 16)
        timeout: Timeout in Sekunden

    Returns:
        dict mit täglichen Vorhersagedaten oder None bei Fehler:
        {
            "tage": [
                {
                    "datum": "2026-02-13",
                    "globalstrahlung_kwh_m2": 2.1,
                    "sonnenstunden": 5.2,
                    "temperatur_max_c": 8.5,
                    "temperatur_min_c": 2.1,
                    "niederschlag_mm": 0.0,
                    "bewoelkung_prozent": 45,
                    "wetter_code": 2
                },
                ...
            ],
            "abgerufen_am": "2026-02-13T10:30:00",
            "standort": {"latitude": 48.0, "longitude": 11.5}
        }
    """
    days = min(days, 16)  # Open-Meteo Maximum

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
            )

            return {
                "tage": tage,
                "abgerufen_am": datetime.now().isoformat(),
                "standort": {
                    "latitude": latitude,
                    "longitude": longitude,
                },
            }

    except httpx.TimeoutException:
        logger.error("Open-Meteo Forecast: Timeout")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"Open-Meteo Forecast: HTTP-Fehler {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Open-Meteo Forecast: Fehler: {e}")
        return None


def wetter_code_zu_symbol(code: Optional[int]) -> str:
    """
    Konvertiert WMO Weather Code zu einfachem Symbol-String.

    WMO Weather Codes: https://open-meteo.com/en/docs
    """
    if code is None:
        return "unknown"

    if code == 0:
        return "sunny"
    elif code in (1, 2, 3):
        return "partly_cloudy"
    elif code in (45, 48):
        return "foggy"
    elif code in (51, 53, 55, 56, 57):
        return "drizzle"
    elif code in (61, 63, 65, 66, 67):
        return "rainy"
    elif code in (71, 73, 75, 77):
        return "snowy"
    elif code in (80, 81, 82):
        return "showers"
    elif code in (85, 86):
        return "snow_showers"
    elif code in (95, 96, 99):
        return "thunderstorm"
    else:
        return "cloudy"


# =============================================================================
# Multi-Provider Wetterdaten-Abruf
# =============================================================================

async def get_wetterdaten_multi(
    latitude: float,
    longitude: float,
    jahr: int,
    monat: int,
    provider: WetterProvider = "auto"
) -> dict:
    """
    Hauptfunktion: Holt Wetterdaten mit konfigurierbarer Quellenauswahl.

    Strategie bei "auto":
    1. Deutschland → Bright Sky (DWD-Daten, höhere Qualität)
    2. Sonst → Open-Meteo
    3. Fallback bei Fehlern → PVGIS TMY → Statische Defaults

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        jahr: Jahr
        monat: Monat (1-12)
        provider: Gewünschter Provider ("auto", "open-meteo", "brightsky")

    Returns:
        dict mit:
            - globalstrahlung_kwh_m2
            - sonnenstunden
            - datenquelle: "open-meteo" | "brightsky" | "pvgis-tmy" | "defaults"
            - standort: {latitude, longitude}
            - provider_info: Details zur verwendeten Quelle
    """
    from backend.services.brightsky_service import (
        fetch_brightsky_month,
        is_in_germany
    )

    today = date.today()
    request_date = date(jahr, monat, 1)

    result = {
        "jahr": jahr,
        "monat": monat,
        "standort": {
            "latitude": latitude,
            "longitude": longitude,
        },
        "provider_versucht": [],
    }

    # Provider-Auswahl
    if provider == "auto":
        # Deutschland → Bright Sky bevorzugen
        if is_in_germany(latitude, longitude) and settings.brightsky_enabled:
            provider_order = ["brightsky", "open-meteo"]
        else:
            provider_order = ["open-meteo", "brightsky"]
    elif provider == "brightsky":
        provider_order = ["brightsky", "open-meteo"]
    else:
        provider_order = ["open-meteo", "brightsky"]

    # Vergangene Monate: Versuche Provider der Reihe nach
    if request_date < date(today.year, today.month, 1):
        for prov in provider_order:
            result["provider_versucht"].append(prov)

            if prov == "brightsky" and settings.brightsky_enabled:
                logger.debug(f"Wetterdaten: Versuche Bright Sky für {monat}/{jahr}")
                data = await fetch_brightsky_month(latitude, longitude, jahr, monat)

                if data:
                    result.update({
                        "globalstrahlung_kwh_m2": data["globalstrahlung_kwh_m2"],
                        "sonnenstunden": data["sonnenstunden"],
                        "datenquelle": "brightsky",
                        "abdeckung_prozent": round(
                            data["tage_mit_daten"] / data["tage_gesamt"] * 100, 0
                        ),
                        "provider_info": {
                            "name": "Bright Sky (DWD)",
                            "tage_mit_daten": data["tage_mit_daten"],
                            "tage_gesamt": data["tage_gesamt"],
                            "temperatur_c": data.get("durchschnitts_temperatur_c"),
                        },
                    })
                    return result

            elif prov == "open-meteo":
                logger.debug(f"Wetterdaten: Versuche Open-Meteo für {monat}/{jahr}")
                data = await fetch_open_meteo_archive(latitude, longitude, jahr, monat)

                if data:
                    result.update({
                        "globalstrahlung_kwh_m2": data["globalstrahlung_kwh_m2"],
                        "sonnenstunden": data["sonnenstunden"],
                        "datenquelle": "open-meteo",
                        "abdeckung_prozent": round(
                            data["tage_mit_daten"] / data["tage_gesamt"] * 100, 0
                        ),
                        "provider_info": {
                            "name": "Open-Meteo Archive",
                            "tage_mit_daten": data["tage_mit_daten"],
                            "tage_gesamt": data["tage_gesamt"],
                        },
                    })
                    return result

    # Strategie 2: PVGIS TMY (für aktuelle/zukünftige oder als Fallback)
    logger.debug(f"Wetterdaten: Versuche PVGIS TMY für Monat {monat}")
    result["provider_versucht"].append("pvgis-tmy")
    data = await fetch_pvgis_tmy_monat(latitude, longitude, monat)

    if data:
        result.update({
            "globalstrahlung_kwh_m2": data["globalstrahlung_kwh_m2"],
            "sonnenstunden": data["sonnenstunden"],
            "datenquelle": "pvgis-tmy",
            "provider_info": {
                "name": "PVGIS Typical Meteorological Year",
                "hinweis": "Langjährige Durchschnittswerte",
            },
        })
        return result

    # Strategie 3: Statische Defaults als letzter Fallback
    logger.warning(f"Wetterdaten: Verwende Defaults für {monat}/{jahr}")
    result["provider_versucht"].append("defaults")
    defaults = get_pvgis_tmy_defaults(monat, latitude)
    result.update({
        "globalstrahlung_kwh_m2": defaults["globalstrahlung_kwh_m2"],
        "sonnenstunden": defaults["sonnenstunden"],
        "datenquelle": "defaults",
        "hinweis": "Durchschnittswerte für Mitteleuropa",
        "provider_info": {
            "name": "Statische Defaults",
            "hinweis": "Durchschnittswerte für Mitteleuropa",
        },
    })

    return result


def get_available_providers(latitude: float, longitude: float) -> list:
    """
    Gibt Liste der verfügbaren Provider für einen Standort zurück.

    Args:
        latitude: Breitengrad
        longitude: Längengrad

    Returns:
        Liste von Provider-Dicts mit name, id, empfohlen, verfuegbar
    """
    from backend.services.brightsky_service import is_in_germany

    in_germany = is_in_germany(latitude, longitude)

    providers = [
        {
            "id": "auto",
            "name": "Automatisch",
            "beschreibung": "Beste Quelle automatisch wählen",
            "empfohlen": True,
            "verfuegbar": True,
        },
        {
            "id": "open-meteo",
            "name": "Open-Meteo",
            "beschreibung": "Weltweit verfügbar, 16-Tage Prognose",
            "empfohlen": not in_germany,
            "verfuegbar": True,
        },
        {
            "id": "brightsky",
            "name": "Bright Sky (DWD)",
            "beschreibung": "Höchste Qualität für Deutschland",
            "empfohlen": in_germany,
            "verfuegbar": in_germany and settings.brightsky_enabled,
            "hinweis": None if in_germany else "Nur für Standorte in Deutschland",
        },
        {
            "id": "open-meteo-solar",
            "name": "Open-Meteo Solar",
            "beschreibung": "GTI-Berechnung für geneigte PV-Module",
            "empfohlen": False,
            "verfuegbar": settings.open_meteo_solar_enabled,
        },
    ]

    return providers


async def get_provider_comparison(
    latitude: float,
    longitude: float,
    jahr: int,
    monat: int
) -> dict:
    """
    Vergleicht Wetterdaten verschiedener Provider für denselben Monat.

    Nützlich für:
    - Transparenz/Debug
    - Qualitätskontrolle
    - Benutzer-Entscheidung

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        jahr: Jahr
        monat: Monat

    Returns:
        dict mit Daten aller verfügbaren Provider
    """
    from backend.services.brightsky_service import (
        fetch_brightsky_month,
        is_in_germany
    )

    results = {
        "jahr": jahr,
        "monat": monat,
        "standort": {"latitude": latitude, "longitude": longitude},
        "provider": {},
    }

    # Open-Meteo
    try:
        data = await fetch_open_meteo_archive(latitude, longitude, jahr, monat)
        if data:
            results["provider"]["open-meteo"] = {
                "verfuegbar": True,
                "globalstrahlung_kwh_m2": data["globalstrahlung_kwh_m2"],
                "sonnenstunden": data["sonnenstunden"],
                "abdeckung_prozent": round(
                    data["tage_mit_daten"] / data["tage_gesamt"] * 100, 0
                ),
            }
        else:
            results["provider"]["open-meteo"] = {"verfuegbar": False}
    except Exception as e:
        results["provider"]["open-meteo"] = {"verfuegbar": False, "fehler": str(e)}

    # Bright Sky (nur für Deutschland)
    if is_in_germany(latitude, longitude) and settings.brightsky_enabled:
        try:
            data = await fetch_brightsky_month(latitude, longitude, jahr, monat)
            if data:
                results["provider"]["brightsky"] = {
                    "verfuegbar": True,
                    "globalstrahlung_kwh_m2": data["globalstrahlung_kwh_m2"],
                    "sonnenstunden": data["sonnenstunden"],
                    "abdeckung_prozent": round(
                        data["tage_mit_daten"] / data["tage_gesamt"] * 100, 0
                    ),
                    "temperatur_c": data.get("durchschnitts_temperatur_c"),
                }
            else:
                results["provider"]["brightsky"] = {"verfuegbar": False}
        except Exception as e:
            results["provider"]["brightsky"] = {"verfuegbar": False, "fehler": str(e)}
    else:
        results["provider"]["brightsky"] = {
            "verfuegbar": False,
            "hinweis": "Nur für Standorte in Deutschland",
        }

    # PVGIS TMY (immer verfügbar)
    try:
        data = await fetch_pvgis_tmy_monat(latitude, longitude, monat)
        if data:
            results["provider"]["pvgis-tmy"] = {
                "verfuegbar": True,
                "globalstrahlung_kwh_m2": data["globalstrahlung_kwh_m2"],
                "sonnenstunden": data["sonnenstunden"],
                "hinweis": "Langjährige Durchschnittswerte",
            }
        else:
            # Fallback auf statische Defaults
            defaults = get_pvgis_tmy_defaults(monat, latitude)
            results["provider"]["pvgis-tmy"] = {
                "verfuegbar": True,
                "globalstrahlung_kwh_m2": defaults["globalstrahlung_kwh_m2"],
                "sonnenstunden": defaults["sonnenstunden"],
                "hinweis": "Statische Durchschnittswerte",
            }
    except Exception as e:
        results["provider"]["pvgis-tmy"] = {"verfuegbar": False, "fehler": str(e)}

    # Abweichungen berechnen
    providers_with_data = [
        (name, p) for name, p in results["provider"].items()
        if p.get("verfuegbar") and "globalstrahlung_kwh_m2" in p
    ]

    if len(providers_with_data) >= 2:
        values = [p["globalstrahlung_kwh_m2"] for _, p in providers_with_data]
        avg = sum(values) / len(values)
        results["vergleich"] = {
            "durchschnitt_kwh_m2": round(avg, 1),
            "abweichung_max_prozent": round(
                (max(values) - min(values)) / avg * 100, 1
            ) if avg > 0 else 0,
        }

    return results
