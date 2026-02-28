"""
Open-Meteo Solar Forecast Service

Bietet direkte PV-Ertragsprognosen basierend auf:
- Global Tilted Irradiance (GTI) - Strahlung auf geneigter Fläche
- Anlagenleistung, Neigung, Ausrichtung
- Temperaturkorrektur

Vorteile gegenüber Standard Open-Meteo:
- GTI-Berechnung integriert (tilt/azimuth Parameter)
- Optimiert für PV-Anwendungen
- Bis 16 Tage Prognose

API-Dokumentation: https://open-meteo.com/en/docs
"""

import logging
from datetime import date, datetime
from typing import Optional, List
from dataclasses import dataclass

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

# Konstanten
OPEN_METEO_FORECAST_URL = settings.open_meteo_solar_api_url
MJ_TO_KWH = 1 / 3.6  # 1 MJ = 0.2778 kWh
SECONDS_TO_HOURS = 1 / 3600

# Systemverluste und Korrekturfaktoren
DEFAULT_SYSTEM_LOSSES = 0.14  # 14% (Kabel, Wechselrichter, etc.)
TEMP_COEFFICIENT = 0.004  # -0.4%/°C über 25°C (typisch für Silizium)
SNOW_LOSS_FACTOR = 0.1  # 10% Verlust bei Schnee


@dataclass
class PVStringConfig:
    """Konfiguration eines PV-Strings."""
    name: str
    kwp: float
    neigung: int  # 0-90°
    ausrichtung: int  # -180 bis 180° (0=Süd, -90=Ost, 90=West, 180=Nord)


@dataclass
class SolarPrognoseTag:
    """Prognose für einen Tag."""
    datum: str
    pv_ertrag_kwh: float
    gti_kwh_m2: float  # Global Tilted Irradiance
    ghi_kwh_m2: float  # Global Horizontal Irradiance (zum Vergleich)
    sonnenstunden: float
    temperatur_max_c: Optional[float]
    temperatur_min_c: Optional[float]
    bewoelkung_prozent: Optional[int]
    niederschlag_mm: Optional[float]
    schnee_cm: Optional[float]


@dataclass
class SolarPrognoseResponse:
    """Vollständige Solar-Prognose."""
    anlage_id: Optional[int]
    kwp_gesamt: float
    neigung: int
    ausrichtung: int
    system_losses_prozent: float
    prognose_zeitraum: dict
    summe_kwh: float
    durchschnitt_kwh_tag: float
    tageswerte: List[SolarPrognoseTag]
    string_prognosen: Optional[List[dict]]  # Pro String, falls mehrere
    datenquelle: str
    abgerufen_am: str


def azimuth_to_openmeteo(ausrichtung_grad: int) -> int:
    """
    Konvertiert Ausrichtung in Open-Meteo Format.

    EEDC/PVGIS:  0=Süd, -90=Ost, 90=West, 180/-180=Nord
    Open-Meteo:  0=Süd, -90=Ost, 90=West, 180=Nord

    Gleiche Konvention - keine Umrechnung nötig!
    """
    return ausrichtung_grad


async def fetch_gti_forecast(
    latitude: float,
    longitude: float,
    neigung: int = 35,
    ausrichtung: int = 0,
    days: int = 7,
    timeout: float = 30.0
) -> Optional[dict]:
    """
    Ruft GTI-Prognose (Global Tilted Irradiance) von Open-Meteo ab.

    GTI = Strahlung auf geneigter Fläche, optimiert für PV-Module.

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        neigung: Modulneigung in Grad (0=horizontal, 90=vertikal)
        ausrichtung: Azimut in Grad (0=Süd, -90=Ost, 90=West)
        days: Anzahl Vorhersagetage (max 16)
        timeout: Timeout in Sekunden

    Returns:
        dict mit stündlichen GTI-Werten und Wetterdaten oder None
    """
    if not settings.open_meteo_solar_enabled:
        logger.debug("Open-Meteo Solar ist deaktiviert")
        return None

    days = min(days, 16)  # API-Maximum

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join([
            "global_tilted_irradiance",
            "shortwave_radiation",  # GHI zum Vergleich
            "direct_radiation",
            "diffuse_radiation",
            "temperature_2m",
            "cloud_cover",
            "precipitation",
            "snowfall",
            "sunshine_duration",
        ]),
        "daily": ",".join([
            "shortwave_radiation_sum",
            "sunshine_duration",
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "snowfall_sum",
        ]),
        "tilt": neigung,
        "azimuth": azimuth_to_openmeteo(ausrichtung),
        "timezone": "Europe/Berlin",
        "forecast_days": days,
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(OPEN_METEO_FORECAST_URL, params=params)
            response.raise_for_status()
            data = response.json()

            logger.info(
                f"Open-Meteo Solar: {days} Tage @ ({latitude}, {longitude}), "
                f"Neigung={neigung}°, Azimut={ausrichtung}°"
            )

            return data

    except httpx.TimeoutException:
        logger.error("Open-Meteo Solar: Timeout")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"Open-Meteo Solar: HTTP-Fehler {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Open-Meteo Solar: Fehler: {e}")
        return None


def berechne_pv_ertrag(
    gti_wh_m2: float,
    kwp: float,
    temperatur_c: Optional[float] = None,
    system_losses: float = DEFAULT_SYSTEM_LOSSES,
    schnee_cm: Optional[float] = None
) -> float:
    """
    Berechnet PV-Ertrag aus GTI.

    Formel:
    Ertrag = GTI [kWh/m²] × kWp × (1 - Systemverluste) × Temperaturkorrektur × Schneekorrektur

    Die Formel basiert darauf, dass 1 kWp unter STC (1000 W/m² Einstrahlung)
    1 kW Leistung produziert. Bei GTI in kWh/m² pro Stunde:
    Ertrag [kWh] = GTI [kWh/m²] × kWp

    Args:
        gti_wh_m2: Global Tilted Irradiance in Wh/m² (stündlich = W/m² für 1h)
        kwp: Anlagenleistung in kWp
        temperatur_c: Lufttemperatur in °C
        system_losses: Systemverluste (0-1)
        schnee_cm: Schneehöhe für Schnee-Verlustabschätzung

    Returns:
        Ertrag in kWh
    """
    if gti_wh_m2 <= 0 or kwp <= 0:
        return 0.0

    # GTI von Wh/m² in kWh/m² umrechnen
    # WICHTIG: Stündliche Werte sind in W/m², was für 1 Stunde = Wh/m² entspricht
    gti_kwh_m2 = gti_wh_m2 / 1000.0

    # Basis-Ertrag: GTI [kWh/m²] × kWp × (1 - Verluste)
    # Bei STC (1 kWh/m² = 1000 Wh/m²) produziert 1 kWp genau 1 kWh
    ertrag = gti_kwh_m2 * kwp * (1 - system_losses)

    # Temperaturkorrektur (Module werden ~25-30°C wärmer als Luft bei voller Sonne)
    if temperatur_c is not None:
        # Modultemperatur schätzen: Lufttemp + Aufheizung durch Einstrahlung
        # Bei niedriger Einstrahlung weniger Aufheizung
        aufheizung = min(25, gti_wh_m2 / 40)  # ~25°C bei 1000 W/m²
        modul_temp = temperatur_c + aufheizung
        if modul_temp > 25:
            temp_verlust = (modul_temp - 25) * TEMP_COEFFICIENT
            ertrag *= (1 - temp_verlust)

    # Schneeverlust (vereinfacht)
    if schnee_cm is not None and schnee_cm > 0:
        # Bei leichtem Schnee rutscht er ab, bei viel Schnee bedeckt er die Module
        if schnee_cm > 5:
            ertrag *= (1 - SNOW_LOSS_FACTOR)

    return max(0, ertrag)


async def get_solar_prognose(
    latitude: float,
    longitude: float,
    kwp: float,
    neigung: int = 35,
    ausrichtung: int = 0,
    days: int = 7,
    system_losses: float = DEFAULT_SYSTEM_LOSSES,
) -> Optional[SolarPrognoseResponse]:
    """
    Berechnet PV-Ertragsprognose basierend auf GTI.

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        kwp: Anlagenleistung in kWp
        neigung: Modulneigung (0-90°)
        ausrichtung: Azimut (0=Süd)
        days: Anzahl Vorhersagetage
        system_losses: Systemverluste (0-1)

    Returns:
        SolarPrognoseResponse mit Tageswerten oder None
    """
    data = await fetch_gti_forecast(
        latitude, longitude, neigung, ausrichtung, days
    )

    if not data:
        return None

    hourly = data.get("hourly", {})
    daily = data.get("daily", {})

    # Stündliche GTI-Werte
    timestamps = hourly.get("time", [])
    gti_values = hourly.get("global_tilted_irradiance", [])
    ghi_values = hourly.get("shortwave_radiation", [])
    temp_values = hourly.get("temperature_2m", [])
    snow_values = hourly.get("snowfall", [])

    # Nach Tagen gruppieren und Ertrag berechnen
    daily_data = {}
    cloud_values = hourly.get("cloud_cover", [])

    for i, timestamp in enumerate(timestamps):
        tag = timestamp[:10]

        if tag not in daily_data:
            daily_data[tag] = {
                "gti_sum_wh": 0,
                "ghi_sum_wh": 0,
                "ertrag_sum_kwh": 0,
                "temp_max": None,
                "snow_sum": 0,
                "cloud_values": [],  # Für Durchschnittsberechnung
            }

        day = daily_data[tag]

        # GTI summieren (Werte sind W/m², für 1h = Wh/m²)
        gti = gti_values[i] if i < len(gti_values) else 0
        ghi = ghi_values[i] if i < len(ghi_values) else 0
        temp = temp_values[i] if i < len(temp_values) else None
        snow = snow_values[i] if i < len(snow_values) else 0

        if gti is not None:
            day["gti_sum_wh"] += gti

        if ghi is not None:
            day["ghi_sum_wh"] += ghi

        if snow is not None:
            day["snow_sum"] += snow

        # Bewölkung sammeln für Tagesdurchschnitt
        cloud = cloud_values[i] if i < len(cloud_values) else None
        if cloud is not None:
            day["cloud_values"].append(cloud)

        # Stündlichen Ertrag berechnen
        if gti is not None and gti > 0:
            stunden_ertrag = berechne_pv_ertrag(
                gti_wh_m2=gti,
                kwp=kwp,
                temperatur_c=temp,
                system_losses=system_losses,
                schnee_cm=snow
            )
            day["ertrag_sum_kwh"] += stunden_ertrag

        # Temperatur-Maximum
        if temp is not None:
            if day["temp_max"] is None or temp > day["temp_max"]:
                day["temp_max"] = temp

    # Tageswerte aus daily-Daten ergänzen
    daily_dates = daily.get("time", [])
    daily_temp_max = daily.get("temperature_2m_max", [])
    daily_temp_min = daily.get("temperature_2m_min", [])
    daily_sunshine = daily.get("sunshine_duration", [])
    daily_precip = daily.get("precipitation_sum", [])
    daily_snow = daily.get("snowfall_sum", [])
    daily_radiation = daily.get("shortwave_radiation_sum", [])

    tageswerte = []
    summe_kwh = 0.0

    for i, datum in enumerate(daily_dates):
        day = daily_data.get(datum, {})

        gti_kwh = day.get("gti_sum_wh", 0) / 1000
        ghi_kwh = day.get("ghi_sum_wh", 0) / 1000
        ertrag = day.get("ertrag_sum_kwh", 0)

        # Falls stündliche Berechnung fehlgeschlagen, aus Tagessumme schätzen
        if ertrag == 0 and i < len(daily_radiation):
            rad_mj = daily_radiation[i] or 0
            ghi_kwh = rad_mj * MJ_TO_KWH
            # Grobe GTI-Schätzung aus GHI (abhängig von Neigung)
            gti_kwh = ghi_kwh * 1.1  # ~10% mehr durch optimale Neigung
            ertrag = gti_kwh * kwp * (1 - system_losses)

        sonnenstunden = 0
        if i < len(daily_sunshine) and daily_sunshine[i] is not None:
            sonnenstunden = daily_sunshine[i] * SECONDS_TO_HOURS

        tageswerte.append(SolarPrognoseTag(
            datum=datum,
            pv_ertrag_kwh=round(ertrag, 2),
            gti_kwh_m2=round(gti_kwh, 2),
            ghi_kwh_m2=round(ghi_kwh, 2),
            sonnenstunden=round(sonnenstunden, 1),
            temperatur_max_c=daily_temp_max[i] if i < len(daily_temp_max) else None,
            temperatur_min_c=daily_temp_min[i] if i < len(daily_temp_min) else None,
            bewoelkung_prozent=(
                round(sum(day.get("cloud_values", [])) / len(day["cloud_values"]))
                if day.get("cloud_values") else None
            ),
            niederschlag_mm=daily_precip[i] if i < len(daily_precip) else None,
            schnee_cm=daily_snow[i] if i < len(daily_snow) else None,
        ))

        summe_kwh += ertrag

    if not tageswerte:
        return None

    return SolarPrognoseResponse(
        anlage_id=None,  # Wird vom Aufrufer gesetzt
        kwp_gesamt=kwp,
        neigung=neigung,
        ausrichtung=ausrichtung,
        system_losses_prozent=round(system_losses * 100, 1),
        prognose_zeitraum={
            "von": tageswerte[0].datum,
            "bis": tageswerte[-1].datum,
        },
        summe_kwh=round(summe_kwh, 1),
        durchschnitt_kwh_tag=round(summe_kwh / len(tageswerte), 2),
        tageswerte=tageswerte,
        string_prognosen=None,
        datenquelle="open-meteo-solar-gti",
        abgerufen_am=datetime.now().isoformat(),
    )


async def get_multi_string_prognose(
    latitude: float,
    longitude: float,
    strings: List[PVStringConfig],
    days: int = 7,
    system_losses: float = DEFAULT_SYSTEM_LOSSES,
) -> Optional[dict]:
    """
    Berechnet Prognose für mehrere Strings mit unterschiedlicher Ausrichtung.

    Nützlich für Anlagen mit Ost/West-Ausrichtung oder mehreren Dachflächen.

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        strings: Liste von PVStringConfig
        days: Anzahl Vorhersagetage
        system_losses: Systemverluste

    Returns:
        dict mit Gesamt- und String-Prognosen oder None
    """
    if not strings:
        return None

    string_prognosen = []
    gesamt_kwh = 0.0
    gesamt_kwp = 0.0

    for string in strings:
        prognose = await get_solar_prognose(
            latitude=latitude,
            longitude=longitude,
            kwp=string.kwp,
            neigung=string.neigung,
            ausrichtung=string.ausrichtung,
            days=days,
            system_losses=system_losses,
        )

        if prognose:
            string_prognosen.append({
                "name": string.name,
                "kwp": string.kwp,
                "neigung": string.neigung,
                "ausrichtung": string.ausrichtung,
                "summe_kwh": prognose.summe_kwh,
                "durchschnitt_kwh_tag": prognose.durchschnitt_kwh_tag,
                "tageswerte": [
                    {
                        "datum": t.datum,
                        "pv_ertrag_kwh": t.pv_ertrag_kwh,
                        "gti_kwh_m2": t.gti_kwh_m2,
                    }
                    for t in prognose.tageswerte
                ],
            })
            gesamt_kwh += prognose.summe_kwh
            gesamt_kwp += string.kwp

    if not string_prognosen:
        return None

    # Durchschnitts-Neigung und -Ausrichtung (gewichtet nach kWp)
    avg_neigung = sum(s.neigung * s.kwp for s in strings) / gesamt_kwp
    avg_ausrichtung = sum(s.ausrichtung * s.kwp for s in strings) / gesamt_kwp

    return {
        "kwp_gesamt": gesamt_kwp,
        "neigung_durchschnitt": round(avg_neigung),
        "ausrichtung_durchschnitt": round(avg_ausrichtung),
        "summe_kwh": round(gesamt_kwh, 1),
        "durchschnitt_kwh_tag": round(gesamt_kwh / days, 2),
        "string_prognosen": string_prognosen,
        "datenquelle": "open-meteo-solar-gti",
        "abgerufen_am": datetime.now().isoformat(),
    }
