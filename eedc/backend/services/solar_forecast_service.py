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

import asyncio
import logging
import random
from datetime import date, datetime
from math import radians, sin, cos
from typing import Optional, List

from backend.services.wetter_service import wetter_code_zu_symbol, _cache_get, _cache_set, FORECAST_CACHE_TTL, JITTER_MAX_SECONDS


def _plausibles_wetter_symbol(
    symbol: str,
    bewoelkung_pct: Optional[float],
    niederschlag_mm: Optional[float],
) -> str:
    """
    Korrigiert das WMO-basierte Wetter-Symbol anhand der tatsächlichen Bewölkung.

    Manche Modelle (z.B. MeteoSwiss) liefern weather_code inkonsistent zur
    gemessenen Bewölkung. Diese Funktion plausibilisiert das Symbol.
    """
    # Niederschlag hat Vorrang — Symbol nicht überschreiben
    if niederschlag_mm is not None and niederschlag_mm > 0.5:
        return symbol

    if bewoelkung_pct is None:
        return symbol

    # Bewölkung < 20% → sonnig, auch wenn WMO-Code cloudy sagt
    if bewoelkung_pct < 20 and symbol in ("cloudy", "partly_cloudy"):
        return "sunny"
    # Bewölkung < 40% → höchstens partly_cloudy
    if bewoelkung_pct < 40 and symbol == "cloudy":
        return "mostly_sunny"
    # Bewölkung > 80% → mindestens cloudy
    if bewoelkung_pct > 80 and symbol in ("sunny", "mostly_sunny"):
        return "cloudy"

    return symbol
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

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

# Timezone für Solar-Noon-Berechnung
_BERLIN_TZ = ZoneInfo("Europe/Berlin")

# Wettermodell-Konfiguration: Key → (Open-Meteo model name, max Prognosetage)
WETTER_MODELLE = {
    "auto": (None, 16),                        # best_match, kein models-Parameter
    "meteoswiss_icon_ch2": ("meteoswiss_icon_ch2", 5),  # Alpenraum, 2.1 km
    "icon_d2": ("icon_d2", 2),                  # Deutschland, 2.2 km
    "icon_eu": ("icon_eu", 7),                  # Europa, 7 km
    "ecmwf_ifs04": ("ecmwf_ifs04", 10),         # Global, 9 km
}

# Anzeigenamen für Datenquellen
MODELL_ANZEIGE = {
    "auto": "Open-Meteo (best_match)",
    "meteoswiss_icon_ch2": "MeteoSwiss ICON-CH2 (2.1 km)",
    "icon_d2": "DWD ICON-D2 (2.2 km)",
    "icon_eu": "DWD ICON-EU (7 km)",
    "ecmwf_ifs04": "ECMWF IFS (9 km)",
    "best_match": "Open-Meteo (best_match)",
}


def _solar_noon_hour(datum: str, longitude: float) -> float:
    """
    Berechnet Solar Noon in lokaler Stunde (Europe/Berlin).

    Nutzt die Equation of Time (Spencer, 1971) — genau auf ~2 Minuten.

    Args:
        datum: Datum als ISO-String (YYYY-MM-DD)
        longitude: Längengrad des Standorts

    Returns:
        Solar Noon als float (z.B. 12.4 = 12:24)
    """
    d = date.fromisoformat(datum)
    # CET (+1) oder CEST (+2)?
    tz_offset = datetime(d.year, d.month, d.day, 12, tzinfo=_BERLIN_TZ).utcoffset()
    tz_hours = tz_offset.total_seconds() / 3600 if tz_offset else 1.0

    # Equation of Time (Spencer, 1971)
    day_of_year = d.timetuple().tm_yday
    B = radians(360 / 365 * (day_of_year - 81))
    EoT_minutes = 9.87 * sin(2 * B) - 7.53 * cos(B) - 1.5 * sin(B)

    # Solar Noon = 12:00 UTC - EoT + Längengradkorrektur, dann in lokale Zeit
    # Referenzmeridian = tz_hours * 15° (CET=15°, CEST=30°)
    timezone_meridian = tz_hours * 15
    solar_noon = 12.0 - EoT_minutes / 60 + (timezone_meridian - longitude) / 15

    return solar_noon


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
    wetter_symbol: str = "unknown"
    pv_ertrag_morgens_kwh: Optional[float] = None   # vor 12:00
    pv_ertrag_nachmittags_kwh: Optional[float] = None  # ab 12:00
    datenquelle: str = "best_match"  # Welches Wettermodell die Daten lieferte


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
    timeout: float = 30.0,
    model: Optional[str] = None,
    skip_jitter: bool = False,
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

    # Cache prüfen (GTI-Forecast → 60 Min TTL)
    model_key = model or "auto"
    cache_key = f"gti:{latitude:.2f}:{longitude:.2f}:{neigung}:{ausrichtung}:{days}:{model_key}"
    cached = _cache_get(cache_key)
    if cached is not None:
        logger.debug(f"Open-Meteo Solar: Cache-Hit ({days} Tage, {model_key})")
        return cached

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
            "weather_code",
        ]),
        "tilt": neigung,
        "azimuth": azimuth_to_openmeteo(ausrichtung),
        "timezone": "Europe/Berlin",
        "forecast_days": days,
    }

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

            model_info = f", Modell={model}" if model else ""
            logger.info(
                f"Open-Meteo Solar: {days} Tage @ ({latitude}, {longitude}), "
                f"Neigung={neigung}°, Azimut={ausrichtung}°{model_info}"
            )

            _cache_set(cache_key, data, FORECAST_CACHE_TTL)
            return data

    except httpx.TimeoutException:
        logger.error("Open-Meteo Solar: Timeout")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"Open-Meteo Solar: HTTP-Fehler {e.response.status_code}")
        return None
    except Exception as e:
        logger.error(f"Open-Meteo Solar: Fehler: {type(e).__name__}: {e}")
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
    wetter_modell: str = "auto",
    skip_jitter: bool = False,
) -> Optional[SolarPrognoseResponse]:
    """
    Berechnet PV-Ertragsprognose basierend auf GTI.

    Bei wetter_modell != "auto" wird eine Kaskade verwendet:
    bevorzugtes Modell (begrenzte Tage) + best_match Fallback für den Rest.

    Args:
        latitude: Breitengrad
        longitude: Längengrad
        kwp: Anlagenleistung in kWp
        neigung: Modulneigung (0-90°)
        ausrichtung: Azimut (0=Süd)
        days: Anzahl Vorhersagetage
        system_losses: Systemverluste (0-1)
        wetter_modell: Wettermodell-Key aus WETTER_MODELLE

    Returns:
        SolarPrognoseResponse mit Tageswerten oder None
    """
    model_name, max_days = WETTER_MODELLE.get(wetter_modell, (None, 16))

    if wetter_modell == "auto" or days <= max_days:
        # Einfacher Fall: ein Call reicht
        data = await fetch_gti_forecast(
            latitude, longitude, neigung, ausrichtung, days,
            model=model_name, skip_jitter=skip_jitter,
        )
        if not data:
            return None
        datenquelle_tag = wetter_modell if wetter_modell != "auto" else "best_match"
        return _build_prognose(data, kwp, neigung, ausrichtung, days, system_losses,
                               longitude, datenquelle_tag=datenquelle_tag)

    # Kaskade: bevorzugtes Modell + best_match Fallback (parallel)
    primary_coro = fetch_gti_forecast(
        latitude, longitude, neigung, ausrichtung, max_days,
        model=model_name, skip_jitter=skip_jitter,
    )
    fallback_coro = fetch_gti_forecast(
        latitude, longitude, neigung, ausrichtung, days,
        model=None, skip_jitter=skip_jitter,
    )
    primary_data, fallback_data = await asyncio.gather(primary_coro, fallback_coro)

    if not primary_data and not fallback_data:
        return None

    if not primary_data:
        # Bevorzugtes Modell hat keine Daten → nur Fallback
        logger.warning(f"Wettermodell {wetter_modell} lieferte keine Daten, nutze best_match")
        return _build_prognose(fallback_data, kwp, neigung, ausrichtung, days,
                               system_losses, longitude, datenquelle_tag="best_match")

    if not fallback_data:
        # Nur bevorzugtes Modell verfügbar
        return _build_prognose(primary_data, kwp, neigung, ausrichtung, max_days,
                               system_losses, longitude, datenquelle_tag=wetter_modell)

    # Beide verfügbar → zusammenführen
    # Primary-Tage bestimmen
    primary_dates = set(primary_data.get("daily", {}).get("time", []))

    # Primary verarbeiten
    primary_prognose = _build_prognose(
        primary_data, kwp, neigung, ausrichtung, max_days,
        system_losses, longitude, datenquelle_tag=wetter_modell
    )
    # Fallback verarbeiten
    fallback_prognose = _build_prognose(
        fallback_data, kwp, neigung, ausrichtung, days,
        system_losses, longitude, datenquelle_tag="best_match"
    )

    if not primary_prognose:
        return fallback_prognose
    if not fallback_prognose:
        return primary_prognose

    # Tage mergen: Primary hat Vorrang, Fallback füllt auf
    merged_tage = list(primary_prognose.tageswerte)
    for tag in fallback_prognose.tageswerte:
        if tag.datum not in primary_dates:
            merged_tage.append(tag)

    # Nach Datum sortieren
    merged_tage.sort(key=lambda t: t.datum)

    summe_kwh = sum(t.pv_ertrag_kwh for t in merged_tage)
    quellen = list(dict.fromkeys(t.datenquelle for t in merged_tage))
    datenquelle_str = " + ".join(
        MODELL_ANZEIGE.get(q, q) for q in quellen
    )

    return SolarPrognoseResponse(
        anlage_id=None,
        kwp_gesamt=kwp,
        neigung=neigung,
        ausrichtung=ausrichtung,
        system_losses_prozent=round(system_losses * 100, 1),
        prognose_zeitraum={
            "von": merged_tage[0].datum,
            "bis": merged_tage[-1].datum,
        },
        summe_kwh=round(summe_kwh, 1),
        durchschnitt_kwh_tag=round(summe_kwh / len(merged_tage), 2),
        tageswerte=merged_tage,
        string_prognosen=None,
        datenquelle=datenquelle_str,
        abgerufen_am=datetime.now().isoformat(),
    )


def _build_prognose(
    data: dict,
    kwp: float,
    neigung: int,
    ausrichtung: int,
    days: int,
    system_losses: float,
    longitude: float,
    datenquelle_tag: str = "best_match",
) -> Optional[SolarPrognoseResponse]:
    """Baut SolarPrognoseResponse aus Open-Meteo API-Daten."""
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
    solar_noon_cache: dict[str, float] = {}  # Tag → Solar Noon (Stunde als float)

    for i, timestamp in enumerate(timestamps):
        tag = timestamp[:10]

        if tag not in daily_data:
            daily_data[tag] = {
                "gti_sum_wh": 0,
                "ghi_sum_wh": 0,
                "ertrag_sum_kwh": 0,
                "ertrag_morgens_kwh": 0,
                "ertrag_nachmittags_kwh": 0,
                "temp_max": None,
                "snow_sum": 0,
                "cloud_values": [],  # Für Durchschnittsberechnung
            }
            # Solar Noon für diesen Tag berechnen
            solar_noon_cache[tag] = _solar_noon_hour(tag, longitude)

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
            # Vor-/Nachmittag-Split an Solar Noon (proportional)
            stunde = int(timestamp[11:13]) if len(timestamp) >= 13 else 12
            noon = solar_noon_cache.get(tag, 12.4)
            noon_hour = int(noon)
            if stunde < noon_hour:
                day["ertrag_morgens_kwh"] += stunden_ertrag
            elif stunde > noon_hour:
                day["ertrag_nachmittags_kwh"] += stunden_ertrag
            else:
                # Stunde enthält Solar Noon — proportional aufteilen
                frac_vm = noon - noon_hour  # z.B. 0.4 bei 12:24
                day["ertrag_morgens_kwh"] += stunden_ertrag * frac_vm
                day["ertrag_nachmittags_kwh"] += stunden_ertrag * (1 - frac_vm)

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
    daily_weather_code = daily.get("weather_code", [])
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

        ertrag_morgens = day.get("ertrag_morgens_kwh", 0)
        ertrag_nachmittags = day.get("ertrag_nachmittags_kwh", 0)

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
            wetter_symbol=_plausibles_wetter_symbol(
                wetter_code_zu_symbol(daily_weather_code[i] if i < len(daily_weather_code) else None),
                round(sum(day.get("cloud_values", [])) / len(day["cloud_values"])) if day.get("cloud_values") else None,
                daily_precip[i] if i < len(daily_precip) else None,
            ),
            pv_ertrag_morgens_kwh=round(ertrag_morgens, 2) if ertrag_morgens > 0 else None,
            pv_ertrag_nachmittags_kwh=round(ertrag_nachmittags, 2) if ertrag_nachmittags > 0 else None,
            datenquelle=datenquelle_tag,
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
        datenquelle=MODELL_ANZEIGE.get(datenquelle_tag, datenquelle_tag),
        abgerufen_am=datetime.now().isoformat(),
    )


async def get_multi_string_prognose(
    latitude: float,
    longitude: float,
    strings: List[PVStringConfig],
    days: int = 7,
    system_losses: float = DEFAULT_SYSTEM_LOSSES,
    wetter_modell: str = "auto",
    skip_jitter: bool = False,
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
        wetter_modell: Wettermodell-Key aus WETTER_MODELLE

    Returns:
        dict mit Gesamt- und String-Prognosen oder None
    """
    if not strings:
        return None

    # Alle Strings parallel abfragen (statt sequentiell mit je 1-30s Jitter)
    coros = [
        get_solar_prognose(
            latitude=latitude,
            longitude=longitude,
            kwp=string.kwp,
            neigung=string.neigung,
            ausrichtung=string.ausrichtung,
            days=days,
            system_losses=system_losses,
            wetter_modell=wetter_modell,
            skip_jitter=skip_jitter,
        )
        for string in strings
    ]
    results = await asyncio.gather(*coros)

    string_prognosen = []
    gesamt_kwh = 0.0
    gesamt_kwp = 0.0

    for string, prognose in zip(strings, results):
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
                        "sonnenstunden": t.sonnenstunden,
                        "temperatur_max_c": t.temperatur_max_c,
                        "temperatur_min_c": t.temperatur_min_c,
                        "bewoelkung_prozent": t.bewoelkung_prozent,
                        "niederschlag_mm": t.niederschlag_mm,
                        "schnee_cm": t.schnee_cm,
                        "wetter_symbol": t.wetter_symbol,
                        "pv_ertrag_morgens_kwh": t.pv_ertrag_morgens_kwh,
                        "pv_ertrag_nachmittags_kwh": t.pv_ertrag_nachmittags_kwh,
                        "datenquelle": t.datenquelle,
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

    # Datenquelle aus erstem String ableiten (gleicher Standort)
    first_tage = string_prognosen[0]["tageswerte"]
    quellen = list(dict.fromkeys(t["datenquelle"] for t in first_tage))
    datenquelle_str = " + ".join(MODELL_ANZEIGE.get(q, q) for q in quellen)

    return {
        "kwp_gesamt": gesamt_kwp,
        "neigung_durchschnitt": round(avg_neigung),
        "ausrichtung_durchschnitt": round(avg_ausrichtung),
        "summe_kwh": round(gesamt_kwh, 1),
        "durchschnitt_kwh_tag": round(gesamt_kwh / days, 2),
        "string_prognosen": string_prognosen,
        "datenquelle": datenquelle_str,
        "abgerufen_am": datetime.now().isoformat(),
    }
