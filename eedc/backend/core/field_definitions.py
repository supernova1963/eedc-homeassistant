"""
Kanonische Felddefinitionen für Monatsdaten-Eingabe.

Single Source of Truth für alle Eingabekanäle:
- MonatsabschlussWizard (liest via API)
- MonatsdatenForm (Frontend, direkte Eingabe)
- CSV-Import/Export (personalisiertes Template)

Kanonische Feldnamen = Backend-Namen (der Wizard war bereits korrekt).
Alle anderen Kanäle wurden auf diese Namen ausgerichtet.

Namens-History:
  speicher_ladung_netz_kwh → ladung_netz_kwh   (Speicher Arbitrage-Netzladung)
  entladung_v2h_kwh        → v2h_entladung_kwh  (E-Auto V2H)
"""

from typing import Optional


# =============================================================================
# Basis-Felder (Monatsdaten — Zählerwerte)
# =============================================================================

BASIS_FELDER = [
    {"feld": "einspeisung_kwh",        "label": "Einspeisung",     "einheit": "kWh",    "mapping_key": "einspeisung"},
    {"feld": "netzbezug_kwh",          "label": "Netzbezug",       "einheit": "kWh",    "mapping_key": "netzbezug"},
    {"feld": "globalstrahlung_kwh_m2", "label": "Globalstrahlung", "einheit": "kWh/m²", "mapping_key": "globalstrahlung"},
    {"feld": "sonnenstunden",          "label": "Sonnenstunden",   "einheit": "h",      "mapping_key": "sonnenstunden"},
    {"feld": "durchschnittstemperatur","label": "Ø Temperatur",    "einheit": "°C",     "mapping_key": "temperatur"},
]

# =============================================================================
# Optionale Felder (manuelle Eingabe, keine HA-Quelle)
# =============================================================================

OPTIONALE_FELDER = [
    {"feld": "sonderkosten_euro",                 "label": "Sonderkosten",  "einheit": "€",       "typ": "number"},
    {"feld": "sonderkosten_beschreibung",          "label": "Beschreibung",  "einheit": "",        "typ": "text"},
    {"feld": "notizen",                            "label": "Notizen",       "einheit": "",        "typ": "text"},
    # Nur bei dynamischem Tarif (wird in get_monatsabschluss() konditionell ergänzt):
    # {"feld": "netzbezug_durchschnittspreis_cent", "label": "Ø Strompreis", "einheit": "ct/kWh"}
]

# =============================================================================
# Investitions-Felder nach Typ
#
# Bedingungsfelder werden über get_felder_fuer_investition() aufgelöst.
# "bedingung" ist ein informativer String für Dokumentation/Debugging.
# =============================================================================

INVESTITION_FELDER: dict = {
    "pv-module": [
        {"feld": "pv_erzeugung_kwh", "label": "PV-Erzeugung", "einheit": "kWh"},
    ],

    "wechselrichter": [
        {"feld": "pv_erzeugung_kwh", "label": "PV-Erzeugung", "einheit": "kWh"},
    ],

    "speicher": [
        {"feld": "ladung_kwh",     "label": "Ladung",     "einheit": "kWh"},
        {"feld": "entladung_kwh",  "label": "Entladung",  "einheit": "kWh"},
        # Konditionell — nur wenn arbitrage_faehig=true:
        {"feld": "ladung_netz_kwh",      "label": "Netzladung",   "einheit": "kWh",    "bedingung": "arbitrage_faehig"},
        {"feld": "speicher_ladepreis_cent", "label": "Ø Ladepreis", "einheit": "ct/kWh", "bedingung": "arbitrage_faehig"},
    ],

    "waermepumpe": [
        # Default-Modus (getrennte_strommessung=false):
        {"feld": "stromverbrauch_kwh",  "label": "Stromverbrauch",   "einheit": "kWh", "bedingung": "!getrennte_strommessung"},
        # Getrennte-Strommessung-Modus (getrennte_strommessung=true):
        {"feld": "strom_heizen_kwh",    "label": "Strom Heizen",     "einheit": "kWh", "bedingung": "getrennte_strommessung"},
        {"feld": "strom_warmwasser_kwh","label": "Strom Warmwasser", "einheit": "kWh", "bedingung": "getrennte_strommessung"},
        # Immer vorhanden:
        {"feld": "heizenergie_kwh",     "label": "Heizenergie",      "einheit": "kWh"},
        {"feld": "warmwasser_kwh",      "label": "Warmwasser",       "einheit": "kWh"},
    ],

    "e-auto": [
        {"feld": "km_gefahren",       "label": "km gefahren",    "einheit": "km",  "placeholder": "z.B. 1200"},
        {"feld": "verbrauch_kwh",     "label": "Verbrauch",      "einheit": "kWh", "placeholder": "z.B. 216"},
        {"feld": "ladung_pv_kwh",     "label": "Heim: PV",       "einheit": "kWh", "placeholder": "z.B. 130"},
        {"feld": "ladung_netz_kwh",   "label": "Heim: Netz",     "einheit": "kWh", "placeholder": "z.B. 50"},
        {"feld": "ladung_extern_kwh", "label": "Extern",         "einheit": "kWh", "placeholder": "z.B. 36"},
        {"feld": "ladung_extern_euro","label": "Extern Kosten",  "einheit": "€",   "placeholder": "z.B. 18.00"},
        # Konditionell — nur wenn v2h_faehig=true oder nutzt_v2h=true:
        {"feld": "v2h_entladung_kwh", "label": "V2H Entladung",  "einheit": "kWh", "bedingung": "v2h_faehig", "placeholder": "z.B. 25"},
    ],

    "wallbox": [
        {"feld": "ladung_kwh",    "label": "Ladung gesamt", "einheit": "kWh", "placeholder": "z.B. 200"},
        {"feld": "ladung_pv_kwh", "label": "Ladung PV",     "einheit": "kWh", "placeholder": "z.B. 80"},
        {"feld": "ladevorgaenge", "label": "Ladevorgänge",  "einheit": "",    "placeholder": "z.B. 12"},
    ],

    "balkonkraftwerk": [
        {"feld": "pv_erzeugung_kwh",   "label": "Erzeugung",      "einheit": "kWh"},
        {"feld": "eigenverbrauch_kwh", "label": "Eigenverbrauch", "einheit": "kWh"},
        # Konditionell — nur wenn hat_speicher=true:
        {"feld": "speicher_ladung_kwh",    "label": "Speicher Ladung",    "einheit": "kWh", "bedingung": "hat_speicher"},
        {"feld": "speicher_entladung_kwh", "label": "Speicher Entladung", "einheit": "kWh", "bedingung": "hat_speicher"},
    ],

    # Sonstiges: Felder hängen von der Kategorie ab (via get_felder_fuer_sonstiges)
    "sonstiges": {
        "erzeuger": [
            {"feld": "erzeugung_kwh",     "label": "Erzeugung",     "einheit": "kWh"},
            {"feld": "eigenverbrauch_kwh","label": "Eigenverbrauch","einheit": "kWh"},
            {"feld": "einspeisung_kwh",   "label": "Einspeisung",   "einheit": "kWh"},
        ],
        "verbraucher": [
            {"feld": "verbrauch_sonstig_kwh","label": "Verbrauch",  "einheit": "kWh"},
            {"feld": "bezug_pv_kwh",         "label": "davon PV",   "einheit": "kWh"},
            {"feld": "bezug_netz_kwh",        "label": "davon Netz", "einheit": "kWh"},
        ],
        "speicher": [
            {"feld": "erzeugung_kwh",        "label": "Erzeugung/Entladung", "einheit": "kWh"},
            {"feld": "verbrauch_sonstig_kwh","label": "Verbrauch/Ladung",    "einheit": "kWh"},
        ],
    },
}

# Alte Feldnamen → neue kanonische Namen (für Lese-Kompatibilität mit alten DB-Einträgen)
LEGACY_FELDNAMEN: dict[str, str] = {
    "speicher_ladung_netz_kwh": "ladung_netz_kwh",   # Speicher Arbitrage
    "entladung_v2h_kwh":        "v2h_entladung_kwh", # E-Auto V2H
}


# =============================================================================
# Hilfsfunktionen
# =============================================================================

def get_felder_fuer_investition(typ: str, parameter: Optional[dict]) -> list[dict]:
    """
    Gibt die relevanten Felder für eine Investition zurück (Bedingungen aufgelöst).

    Filtert konditionelle Felder basierend auf Investitions-Parametern heraus.
    Für Typ "sonstiges" bitte get_felder_fuer_sonstiges() verwenden.

    Args:
        typ: Investitionstyp (z.B. "speicher", "e-auto")
        parameter: Investitions-Parameter-Dict (inv.parameter)

    Returns:
        Liste von Feld-Dicts ohne "bedingung"-Key (bereits aufgelöst)
    """
    params = parameter or {}
    alle_felder = INVESTITION_FELDER.get(typ, [])

    if isinstance(alle_felder, dict):
        # Sonstiges — Kategorie-abhängig
        kategorie = params.get("kategorie", "erzeuger")
        return get_felder_fuer_sonstiges(kategorie)

    result = []
    getrennte_strommessung = bool(params.get("getrennte_strommessung"))
    arbitrage_faehig = bool(params.get("arbitrage_faehig"))
    v2h_faehig = bool(params.get("v2h_faehig") or params.get("nutzt_v2h"))
    hat_speicher = bool(params.get("hat_speicher"))

    for feld in alle_felder:
        bedingung = feld.get("bedingung")
        if bedingung is None:
            result.append({k: v for k, v in feld.items() if k != "bedingung"})
        elif bedingung == "getrennte_strommessung" and getrennte_strommessung:
            result.append({k: v for k, v in feld.items() if k != "bedingung"})
        elif bedingung == "!getrennte_strommessung" and not getrennte_strommessung:
            result.append({k: v for k, v in feld.items() if k != "bedingung"})
        elif bedingung == "arbitrage_faehig" and arbitrage_faehig:
            result.append({k: v for k, v in feld.items() if k != "bedingung"})
        elif bedingung == "v2h_faehig" and v2h_faehig:
            result.append({k: v for k, v in feld.items() if k != "bedingung"})
        elif bedingung == "hat_speicher" and hat_speicher:
            result.append({k: v for k, v in feld.items() if k != "bedingung"})

    return result


def get_felder_fuer_sonstiges(kategorie: str) -> list[dict]:
    """
    Gibt Felder für eine Sonstiges-Investition nach Kategorie zurück.

    Args:
        kategorie: "erzeuger", "verbraucher" oder "speicher"

    Returns:
        Liste von Feld-Dicts
    """
    sonstiges = INVESTITION_FELDER.get("sonstiges", {})
    return sonstiges.get(kategorie, sonstiges.get("erzeuger", []))


def resolve_legacy_key(key: str) -> str:
    """
    Gibt den kanonischen Feldnamen für einen ggf. veralteten Key zurück.

    Für Rückwärtskompatibilität beim Lesen alter DB-Einträge.
    """
    return LEGACY_FELDNAMEN.get(key, key)
