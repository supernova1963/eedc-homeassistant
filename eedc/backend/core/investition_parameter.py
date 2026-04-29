"""
Single Source of Truth für die Schlüssel im `parameter`-JSON-Feld
jeder Investition.

Hintergrund: das `parameter`-Feld auf einer Investition ist ein unstrukturiertes
JSON. Über mehrere Iterationen sind Schlüsselnamen zwischen Form, Wizard und
Backend-Lese-Code gedriftet — siehe Inventur in
`docs/drafts/INVENTUR-INVESTITIONS-PARAMETER.md`.

Dieses Modul macht die Keys statisch typisiert + auffindbar:
  - `PARAM_<TYP>` exportiert die kanonischen Schlüsselnamen pro Investitions-Typ
  - `PARAM_<TYP>_DEFAULTS` exportiert die Default-Werte (gemeinsam für Frontend
    und Backend, damit Default-Drift wie #7 in der Inventur nicht entsteht)

Das Frontend-Pendant lebt unter
  eedc/frontend/src/lib/investitionParameter.ts

Verwendung im Backend:

    from core.investition_parameter import PARAM_SPEICHER, PARAM_SPEICHER_DEFAULTS

    kapazitaet = inv.parameter.get(PARAM_SPEICHER["KAPAZITAET_KWH"], 0)
    arbitrage = inv.parameter.get(
        PARAM_SPEICHER["ARBITRAGE_FAEHIG"],
        PARAM_SPEICHER_DEFAULTS["arbitrage_faehig"],
    )
"""

from typing import Final


# ============================================================================
# E-Auto
# ============================================================================

PARAM_E_AUTO: Final[dict[str, str]] = {
    "BATTERIE_KAPAZITAET_KWH": "batteriekapazitaet_kwh",
    "VERBRAUCH_KWH_100KM": "verbrauch_kwh_100km",
    "JAHRESFAHRLEISTUNG_KM": "jahresfahrleistung_km",
    "PV_LADEANTEIL_PROZENT": "pv_ladeanteil_prozent",
    "VERGLEICH_VERBRAUCH_L_100KM": "vergleich_verbrauch_l_100km",
    "BENZINPREIS_EURO": "benzinpreis_euro",
    "V2H_FAEHIG": "v2h_faehig",
    "V2H_ENTLADELEISTUNG_KW": "v2h_entladeleistung_kw",
    "V2H_ENTLADE_PREIS_CENT": "v2h_entlade_preis_cent",
    "V2H_ENTLADUNG_KWH_JAHR": "v2h_entladung_kwh_jahr",
    "IST_DIENSTLICH": "ist_dienstlich",
    "ALTERNATIV_KOSTEN_EURO": "alternativ_kosten_euro",
}

PARAM_E_AUTO_DEFAULTS: Final[dict[str, object]] = {
    "verbrauch_kwh_100km": 18,
    "jahresfahrleistung_km": 15000,
    "pv_ladeanteil_prozent": 60,
    "vergleich_verbrauch_l_100km": 7.5,
    "benzinpreis_euro": 1.65,
    "v2h_faehig": False,
    "ist_dienstlich": False,
}


# ============================================================================
# Speicher
# ============================================================================

PARAM_SPEICHER: Final[dict[str, str]] = {
    "KAPAZITAET_KWH": "kapazitaet_kwh",
    "NUTZBARE_KAPAZITAET_KWH": "nutzbare_kapazitaet_kwh",
    "MAX_LADELEISTUNG_KW": "max_ladeleistung_kw",
    "MAX_ENTLADELEISTUNG_KW": "max_entladeleistung_kw",
    "WIRKUNGSGRAD_PROZENT": "wirkungsgrad_prozent",
    "ARBITRAGE_FAEHIG": "arbitrage_faehig",
    "LADE_DURCHSCHNITTSPREIS_CENT": "lade_durchschnittspreis_cent",
    "ENTLADE_VERMIEDENER_PREIS_CENT": "entlade_vermiedener_preis_cent",
}

PARAM_SPEICHER_DEFAULTS: Final[dict[str, object]] = {
    "wirkungsgrad_prozent": 95,
    "arbitrage_faehig": False,
    "lade_durchschnittspreis_cent": 12,
    "entlade_vermiedener_preis_cent": 35,
}


# ============================================================================
# Wärmepumpe
# ============================================================================

PARAM_WAERMEPUMPE: Final[dict[str, str]] = {
    "LEISTUNG_KW": "leistung_kw",
    "WP_ART": "wp_art",
    "EFFIZIENZ_MODUS": "effizienz_modus",
    "JAZ": "jaz",
    "SCOP_HEIZUNG": "scop_heizung",
    "SCOP_WARMWASSER": "scop_warmwasser",
    "VORLAUFTEMPERATUR": "vorlauftemperatur",
    "COP_HEIZUNG": "cop_heizung",
    "COP_WARMWASSER": "cop_warmwasser",
    "GETRENNTE_STROMMESSUNG": "getrennte_strommessung",
    "HEIZWAERMEBEDARF_KWH": "heizwaermebedarf_kwh",
    "WARMWASSERBEDARF_KWH": "warmwasserbedarf_kwh",
    "WAERMEBEDARF_KWH": "waermebedarf_kwh",
    "PV_ANTEIL_PROZENT": "pv_anteil_prozent",
    "ALTER_ENERGIETRAEGER": "alter_energietraeger",
    "ALTER_PREIS_CENT_KWH": "alter_preis_cent_kwh",
    "ALTERNATIV_ZUSATZKOSTEN_JAHR": "alternativ_zusatzkosten_jahr",
    "ALTERNATIV_KOSTEN_EURO": "alternativ_kosten_euro",
    "SG_READY": "sg_ready",
}

PARAM_WAERMEPUMPE_DEFAULTS: Final[dict[str, object]] = {
    "wp_art": "luft_wasser",
    "effizienz_modus": "gesamt_jaz",
    "jaz": 3.5,
    "scop_heizung": 4.5,
    "scop_warmwasser": 3.2,
    "vorlauftemperatur": "35",
    "cop_heizung": 3.9,
    "cop_warmwasser": 3.0,
    "getrennte_strommessung": False,
    "heizwaermebedarf_kwh": 12000,
    "warmwasserbedarf_kwh": 3000,
    "pv_anteil_prozent": 30,
    "alter_energietraeger": "gas",
    # Inventur Bug #7: aussichten.py + ha_export.py:241 hatten 10.0,
    # alle anderen 12.0. Vereinheitlicht auf 12.0 — typischer Gas-Endkundenpreis.
    "alter_preis_cent_kwh": 12,
    "alternativ_zusatzkosten_jahr": 0,
    "sg_ready": False,
}


# ============================================================================
# Wallbox
# ============================================================================

PARAM_WALLBOX: Final[dict[str, str]] = {
    "MAX_LADELEISTUNG_KW": "max_ladeleistung_kw",
    "BIDIREKTIONAL": "bidirektional",
    "PV_OPTIMIERT": "pv_optimiert",
    "IST_DIENSTLICH": "ist_dienstlich",
}

PARAM_WALLBOX_DEFAULTS: Final[dict[str, object]] = {
    "max_ladeleistung_kw": 11,
    "bidirektional": False,
    "pv_optimiert": True,
    "ist_dienstlich": False,
}


# ============================================================================
# Wechselrichter
# ============================================================================

PARAM_WECHSELRICHTER: Final[dict[str, str]] = {
    "MAX_LEISTUNG_KW": "max_leistung_kw",
    "WIRKUNGSGRAD_PROZENT": "wirkungsgrad_prozent",
    "HYBRID": "hybrid",
}

PARAM_WECHSELRICHTER_DEFAULTS: Final[dict[str, object]] = {
    "wirkungsgrad_prozent": 97,
    "hybrid": False,
}


# ============================================================================
# PV-Module
# ============================================================================

PARAM_PV_MODULE: Final[dict[str, str]] = {
    "ANZAHL_MODULE": "anzahl_module",
    "MODUL_LEISTUNG_WP": "modul_leistung_wp",
    "MODUL_TYP": "modul_typ",
    "AUSRICHTUNG_GRAD": "ausrichtung_grad",
}


# ============================================================================
# Balkonkraftwerk
# ============================================================================

PARAM_BALKONKRAFTWERK: Final[dict[str, str]] = {
    "LEISTUNG_WP": "leistung_wp",
    "ANZAHL": "anzahl",
    "AUSRICHTUNG": "ausrichtung",
    "NEIGUNG_GRAD": "neigung_grad",
    "HAT_SPEICHER": "hat_speicher",
    "SPEICHER_KAPAZITAET_WH": "speicher_kapazitaet_wh",
}

PARAM_BALKONKRAFTWERK_DEFAULTS: Final[dict[str, object]] = {
    "anzahl": 2,
    "ausrichtung": "Süd",
    "neigung_grad": 30,
    "hat_speicher": False,
}


# ============================================================================
# Sonstiges
# ============================================================================

PARAM_SONSTIGES: Final[dict[str, str]] = {
    "KATEGORIE": "kategorie",
    "BESCHREIBUNG": "beschreibung",
}

PARAM_SONSTIGES_DEFAULTS: Final[dict[str, object]] = {
    "kategorie": "erzeuger",
}


# ============================================================================
# Legacy-Keys (deprecated, aber Migrations-Code muss sie weiter erkennen)
# ============================================================================

# In v3.25.0 entstandene Migration: Diese alten Keys werden in der
# DB-Migration auf die neuen Schlüssel umgeschrieben. Sie dürfen nirgends
# mehr aktiv gelesen oder geschrieben werden — die Liste hier dient nur
# als Bezugsanker für die einmalige Migration.
LEGACY_PARAM_KEYS: Final[dict[str, str]] = {
    # E-Auto
    "km_jahr": "jahresfahrleistung_km",
    "pv_anteil_prozent": "pv_ladeanteil_prozent",  # nur in E-Auto-Kontext, nicht WP
    "benzin_verbrauch_liter_100km": "vergleich_verbrauch_l_100km",
    "nutzt_v2h": "v2h_faehig",
    # Speicher
    "nutzt_arbitrage": "arbitrage_faehig",
    # Wallbox
    "leistung_kw": "max_ladeleistung_kw",  # nur in Wallbox-Kontext, nicht WP
    # Wechselrichter
    "leistung_ac_kw": "max_leistung_kw",  # nur im toten Schema
}
