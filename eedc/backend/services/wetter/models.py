"""
Wettermodell-Konfiguration und Konstanten.

Zentrale Definition der verfügbaren Wettermodelle,
Anzeigenamen und Typ-Definitionen.
"""

from typing import Literal

# Typ für Provider-Auswahl (Monatsarchiv)
WetterProvider = Literal["auto", "open-meteo", "brightsky", "open-meteo-solar"]

# Wettermodell-Konfiguration: Key → (Open-Meteo model name, max Prognosetage)
# Wird für Solar-Prognose, Kurzfrist-Aussichten und Live-Wetter verwendet.
#
# Seamless-Modelle kaskadieren intern bei Open-Meteo automatisch:
#   icon_seamless:        ICON-D2 (2 Tage) → ICON-EU (5 Tage) → ICON-Global (7.5 Tage)
#   meteoswiss_seamless:  CH-Modelle kombiniert (5 Tage), danach Code-Fallback auf best_match
#   ecmwf_seamless:       Alle ECMWF-Modelle kombiniert (15 Tage)
WETTER_MODELLE = {
    "auto":                 (None,                    16),  # best_match, kein models-Parameter
    # Seamless (empfohlen — interne Kaskade bei Open-Meteo)
    "icon_seamless":        ("icon_seamless",          7),  # DE/EU: D2→EU→Global
    "meteoswiss_seamless":  ("meteoswiss_seamless",    5),  # Alpenraum, danach Fallback
    "ecmwf_seamless":       ("ecmwf_seamless",        15),  # Global, 15 Tage
    # Einzelmodelle (für fortgeschrittene Nutzer / Vergleich)
    "meteoswiss_icon_ch2":  ("meteoswiss_icon_ch2",   5),  # Alpenraum, 2.1 km
    "icon_d2":              ("icon_d2",               2),  # Deutschland, 2.2 km
    "icon_eu":              ("icon_eu",               5),  # Europa, 7 km
    "ecmwf_ifs04":          ("ecmwf_ifs04",          10),  # Global, 9 km
}

# Anzeigenamen für Datenquellen (UI + API-Responses)
MODELL_ANZEIGE = {
    "auto":                 "Open-Meteo (best_match)",
    # Seamless
    "icon_seamless":        "DWD ICON Seamless (D2→EU→Global)",
    "meteoswiss_seamless":  "MeteoSwiss Seamless",
    "ecmwf_seamless":       "ECMWF Seamless",
    # Einzelmodelle
    "meteoswiss_icon_ch2":  "MeteoSwiss ICON-CH2 (2.1 km)",
    "icon_d2":              "DWD ICON-D2 (2.2 km)",
    "icon_eu":              "DWD ICON-EU (7 km)",
    "ecmwf_ifs04":          "ECMWF IFS (9 km)",
    "best_match":           "Open-Meteo (best_match)",
}
