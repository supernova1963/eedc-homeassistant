"""
Wetter-Provider-Orchestrator: Multi-Provider-Routing mit Fallback-Kette.

Strategie bei "auto":
1. Deutschland → Bright Sky (DWD-Daten, höhere Qualität)
2. Sonst → Open-Meteo
3. Fallback: PVGIS TMY → Statische Defaults
"""

import logging
from datetime import date
from typing import Optional

from backend.core.config import settings
from backend.services.wetter.open_meteo import fetch_open_meteo_archive
from backend.services.wetter.pvgis import fetch_pvgis_tmy_monat, get_pvgis_tmy_defaults
from backend.services.wetter.models import WetterProvider

logger = logging.getLogger(__name__)


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

    Returns:
        dict mit globalstrahlung_kwh_m2, sonnenstunden, datenquelle, standort
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


async def get_wetterdaten_multi(
    latitude: float,
    longitude: float,
    jahr: int,
    monat: int,
    provider: WetterProvider = "auto"
) -> dict:
    """
    Holt Wetterdaten mit konfigurierbarer Quellenauswahl.

    Strategie bei "auto":
    1. Deutschland → Bright Sky (DWD-Daten, höhere Qualität)
    2. Sonst → Open-Meteo
    3. Fallback: PVGIS TMY → Statische Defaults

    Returns:
        dict mit globalstrahlung_kwh_m2, sonnenstunden, datenquelle,
        standort, provider_info
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

    # Provider-Reihenfolge bestimmen
    if provider == "auto":
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

    # Fallback: PVGIS TMY
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

    # Letzter Fallback: Statische Defaults
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
