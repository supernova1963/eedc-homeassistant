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

#: Länder, für die Bright Sky (DWD) **nicht** in Frage kommt. Bewusst als
#: Ausschluss- statt Einschlussliste: ein unbekanntes Land (``None``) darf die
#: bisherige Koordinaten-Heuristik nicht abschalten, sonst verlöre jede
#: deutsche Altanlage ohne gepflegtes Land ihre DWD-Quelle.
_OHNE_BRIGHTSKY = {"AT", "CH", "IT"}


def nutze_brightsky(latitude: float, longitude: float, land: Optional[str] = None) -> bool:
    """Darf Bright Sky (DWD) für diesen Standort verwendet werden? (#386)

    **Das gepflegte Land schlägt die Koordinaten.** Bis v4.0.20 entschied
    allein ``is_in_germany`` — eine Bounding-Box, also ein Rechteck. Sie
    schließt West-/Zentralösterreich und die Nordostschweiz mit ein: Salzburg,
    Innsbruck, Linz, Bregenz, Zürich und Basel liegen darin. Ein Anwender
    konnte „Österreich" einstellen und bekam trotzdem DWD — das Feld wurde an
    dieser Stelle nie gelesen (gemeldet von gruaGit, #386).

    Was Handbuch und Oberfläche seit jeher behaupten („Bright Sky nur für
    Deutschland"), setzt erst diese Funktion um. Bright Sky liefert
    DWD-**Stationsmessungen**; deren Netz endet an der Staatsgrenze, und für
    einen Standort ohne Station in Reichweite kommt keine Globalstrahlung
    zurück (siehe die Abdeckungsprüfung im Aufrufer).

    ``None`` bedeutet ausdrücklich „Land nicht bekannt", nicht „Deutschland" —
    dann bleibt es bei der Box.
    """
    from backend.services.brightsky_service import is_in_germany

    if land and land.strip().upper() in _OHNE_BRIGHTSKY:
        return False
    return is_in_germany(latitude, longitude)


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
    provider: WetterProvider = "auto",
    land: Optional[str] = None,
) -> dict:
    """
    Holt Wetterdaten mit konfigurierbarer Quellenauswahl.

    Strategie bei "auto":
    1. Deutschland → Bright Sky (DWD-Daten, höhere Qualität)
    2. Sonst → Open-Meteo
    3. Fallback: PVGIS TMY → Statische Defaults

    Args:
        land: Gepflegtes `Anlage.standort_land` (``DE``/``AT``/``CH``/``IT``).
            **Schlägt die Koordinaten-Heuristik** — siehe `nutze_brightsky`.
            ``None`` heißt „nicht bekannt", nicht „Deutschland".

    Returns:
        dict mit globalstrahlung_kwh_m2, sonnenstunden, datenquelle,
        standort, provider_info
    """
    from backend.services.brightsky_service import fetch_brightsky_month

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
        if nutze_brightsky(latitude, longitude, land) and settings.brightsky_enabled:
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

                # #386: Ein Monat OHNE einen einzigen Tag Strahlungsdaten ist
                # kein Ergebnis, sondern eine Lücke — und `if data:` allein
                # nahm ihn an, weil das dict nicht leer ist. Meldet die
                # nächstgelegene DWD-Station keine Strahlung (bei gruaGit:
                # Marktschellenberg, 49 km, `solar` durchgängig None), lieferte
                # Bright Sky {globalstrahlung 0.0, tage_mit_daten 0} — und
                # eedc bot dem Anwender **0,0 kWh/m²** an, statt Open-Meteo zu
                # fragen, das 206,5 gehabt hätte. Der zweite Provider stand
                # bereits in der Kette; er wurde nur nie erreicht.
                # Bewusst hier und nicht in `fetch_brightsky_month`: der
                # Provider-VERGLEICH unten will die 0 Tage sehen können.
                if data and data.get("tage_mit_daten", 0) <= 0:
                    logger.info(
                        "Bright Sky: %s/%s @ (%s, %s) ohne Strahlungstage — "
                        "weiter zum nächsten Provider",
                        monat, jahr, latitude, longitude,
                    )
                    data = None

                if data:
                    result.update({
                        "globalstrahlung_kwh_m2": data["globalstrahlung_kwh_m2"],
                        "sonnenstunden": data["sonnenstunden"],
                        "durchschnittstemperatur_c": data.get("durchschnitts_temperatur_c"),
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
                        "durchschnittstemperatur_c": data.get("durchschnitts_temperatur_c"),
                        "datenquelle": "open-meteo",
                        "abdeckung_prozent": round(
                            data["tage_mit_daten"] / data["tage_gesamt"] * 100, 0
                        ),
                        "provider_info": {
                            "name": "Open-Meteo Archive",
                            "tage_mit_daten": data["tage_mit_daten"],
                            "tage_gesamt": data["tage_gesamt"],
                            "temperatur_c": data.get("durchschnitts_temperatur_c"),
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


def get_available_providers(
    latitude: float, longitude: float, land: Optional[str] = None
) -> list:
    """
    Gibt Liste der verfügbaren Provider für einen Standort zurück.

    `land` wirkt hier genauso wie bei der Abruf-Automatik (#386) — sonst
    zeigte die Oberfläche „Bright Sky ✓ verfügbar" für einen Standort, den
    der Abruf gar nicht mehr an Bright Sky schickt.
    """
    in_germany = nutze_brightsky(latitude, longitude, land)

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
    monat: int,
    land: Optional[str] = None,
) -> dict:
    """
    Vergleicht Wetterdaten verschiedener Provider für denselben Monat.

    `land` wirkt wie bei der Automatik (#386): Wo eedc Bright Sky nicht mehr
    verwendet, darf der Vergleich es nicht als Quelle anbieten.
    """
    from backend.services.brightsky_service import fetch_brightsky_month

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
                "temperatur_c": data.get("durchschnitts_temperatur_c"),
            }
        else:
            results["provider"]["open-meteo"] = {"verfuegbar": False}
    except Exception as e:
        results["provider"]["open-meteo"] = {"verfuegbar": False, "fehler": str(e)}

    # Bright Sky (nur für Deutschland)
    if nutze_brightsky(latitude, longitude, land) and settings.brightsky_enabled:
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
