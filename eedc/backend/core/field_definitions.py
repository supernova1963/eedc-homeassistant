"""
Kanonische Felddefinitionen für Monatsdaten-Eingabe und Import.

Single Source of Truth für alle Eingabe- und Import-Kanäle:
- MonatsabschlussWizard (liest via API)
- MonatsdatenForm (Frontend, direkte Eingabe)
- CSV-Import/Export (personalisiertes Template)
- Custom-Import-Wizard (Spalten-Mapping)
- Portal-Import / Cloud-Import

Kanonische Feldnamen = Backend-Namen (der Wizard war bereits korrekt).
Alle anderen Kanäle wurden auf diese Namen ausgerichtet.

Namens-History:
  speicher_ladung_netz_kwh → ladung_netz_kwh   (Speicher Arbitrage-Netzladung)
  entladung_v2h_kwh        → v2h_entladung_kwh  (E-Auto V2H)

Feld-Attribute:
  feld          — kanonischer Backend-Feldname in verbrauch_daten
  label         — Anzeigename (Wizard, Dropdown)
  einheit       — Einheit für Anzeige (kWh, km, €, ct/kWh, "")
  bedingung     — optionale Bedingung (Parameter-Key), z.B. "arbitrage_faehig"
  csv_suffix    — Spalten-Suffix in der personalisierten CSV, z.B. "Ladung_kWh"
                  Konvention: {SanitizedBezeichnung}_{csv_suffix}
  csv_suffix_alt— alternativer (Legacy-)Suffix für Rückwärtskompatibilität
  aggregiert_in — Summen-Key für Monatsdaten-Aggregat:
                  "pv_sum", "batterie_ladung_sum", "batterie_entladung_sum"
  typ           — Datentyp für Import-Parsing: "float" (default) | "int"
  placeholder   — optionaler Platzhalter für Eingabefeld
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
#
# Import-Attribute (csv_suffix, aggregiert_in, typ) werden von
# _import_investition_monatsdaten_v09() und _build_investition_felder()
# automatisch ausgewertet — keine hardcodierten Typ-Checks mehr nötig.
# =============================================================================

INVESTITION_FELDER: dict = {
    "pv-module": [
        {
            "feld": "pv_erzeugung_kwh", "label": "PV-Erzeugung", "einheit": "kWh",
            "csv_suffix": "kWh",
            "aggregiert_in": "pv_erzeugung_sum",
        },
    ],

    "wechselrichter": [
        {
            "feld": "pv_erzeugung_kwh", "label": "PV-Erzeugung", "einheit": "kWh",
            "csv_suffix": "kWh",
            "aggregiert_in": "pv_erzeugung_sum",
        },
    ],

    "speicher": [
        {
            "feld": "ladung_kwh", "label": "Ladung", "einheit": "kWh",
            "csv_suffix": "Ladung_kWh",
            "aggregiert_in": "batterie_ladung_sum",
        },
        {
            "feld": "entladung_kwh", "label": "Entladung", "einheit": "kWh",
            "csv_suffix": "Entladung_kWh",
            "aggregiert_in": "batterie_entladung_sum",
        },
        # Konditionell — nur wenn arbitrage_faehig=true:
        {
            "feld": "ladung_netz_kwh", "label": "Netzladung", "einheit": "kWh",
            "bedingung": "arbitrage_faehig",
            "csv_suffix": "Netzladung_kWh",
        },
        {
            "feld": "speicher_ladepreis_cent", "label": "Ø Ladepreis", "einheit": "ct/kWh",
            "bedingung": "arbitrage_faehig",
            "csv_suffix": "Ladepreis_Cent",
        },
    ],

    "waermepumpe": [
        # Default-Modus (getrennte_strommessung=false):
        {
            "feld": "stromverbrauch_kwh", "label": "Stromverbrauch", "einheit": "kWh",
            "bedingung": "!getrennte_strommessung",
            "csv_suffix": "Strom_kWh",
        },
        # Getrennte-Strommessung-Modus (getrennte_strommessung=true):
        {
            "feld": "strom_heizen_kwh", "label": "Strom Heizen", "einheit": "kWh",
            "bedingung": "getrennte_strommessung",
            "csv_suffix": "Strom_Heizen_kWh",
        },
        {
            "feld": "strom_warmwasser_kwh", "label": "Strom Warmwasser", "einheit": "kWh",
            "bedingung": "getrennte_strommessung",
            "csv_suffix": "Strom_Warmwasser_kWh",
        },
        # Immer vorhanden:
        {
            "feld": "heizenergie_kwh", "label": "Heizenergie", "einheit": "kWh",
            "csv_suffix": "Heizung_kWh",
        },
        {
            "feld": "warmwasser_kwh", "label": "Warmwasser", "einheit": "kWh",
            "csv_suffix": "Warmwasser_kWh",
        },
    ],

    "e-auto": [
        {
            "feld": "km_gefahren", "label": "km gefahren", "einheit": "km",
            "placeholder": "z.B. 1200",
            "csv_suffix": "km",
        },
        {
            "feld": "verbrauch_kwh", "label": "Verbrauch", "einheit": "kWh",
            "placeholder": "z.B. 216",
            "csv_suffix": "Verbrauch_kWh",
        },
        {
            "feld": "ladung_pv_kwh", "label": "Heim: PV", "einheit": "kWh",
            "placeholder": "z.B. 130",
            "csv_suffix": "Ladung_PV_kWh",
        },
        {
            "feld": "ladung_netz_kwh", "label": "Heim: Netz", "einheit": "kWh",
            "placeholder": "z.B. 50",
            "csv_suffix": "Ladung_Netz_kWh",
        },
        {
            "feld": "ladung_extern_kwh", "label": "Extern", "einheit": "kWh",
            "placeholder": "z.B. 36",
            "csv_suffix": "Ladung_Extern_kWh",
        },
        {
            "feld": "ladung_extern_euro", "label": "Extern Kosten", "einheit": "€",
            "placeholder": "z.B. 18.00",
            "csv_suffix": "Ladung_Extern_Euro",
        },
        # Konditionell — nur wenn v2h_faehig=true oder nutzt_v2h=true:
        {
            "feld": "v2h_entladung_kwh", "label": "V2H Entladung", "einheit": "kWh",
            "bedingung": "v2h_faehig",
            "placeholder": "z.B. 25",
            "csv_suffix": "V2H_kWh",
        },
    ],

    "wallbox": [
        {
            "feld": "ladung_kwh", "label": "Ladung gesamt", "einheit": "kWh",
            "placeholder": "z.B. 200",
            "csv_suffix": "Ladung_kWh",
        },
        {
            "feld": "ladung_pv_kwh", "label": "Ladung PV", "einheit": "kWh",
            "placeholder": "z.B. 80",
            "csv_suffix": "Ladung_PV_kWh",
        },
        {
            "feld": "ladevorgaenge", "label": "Ladevorgänge", "einheit": "",
            "placeholder": "z.B. 12",
            "csv_suffix": "Ladevorgaenge",
            "typ": "int",
        },
    ],

    "balkonkraftwerk": [
        {
            "feld": "pv_erzeugung_kwh", "label": "Erzeugung", "einheit": "kWh",
            "csv_suffix": "Erzeugung_kWh",
            "csv_suffix_alt": "kWh",  # Rückwärtskompatibilität
            "aggregiert_in": "pv_erzeugung_sum",
        },
        {
            "feld": "eigenverbrauch_kwh", "label": "Eigenverbrauch", "einheit": "kWh",
            "csv_suffix": "Eigenverbrauch_kWh",
        },
        # Konditionell — nur wenn hat_speicher=true:
        {
            "feld": "speicher_ladung_kwh", "label": "Speicher Ladung", "einheit": "kWh",
            "bedingung": "hat_speicher",
            "csv_suffix": "Speicher_Ladung_kWh",
            "aggregiert_in": "batterie_ladung_sum",
        },
        {
            "feld": "speicher_entladung_kwh", "label": "Speicher Entladung", "einheit": "kWh",
            "bedingung": "hat_speicher",
            "csv_suffix": "Speicher_Entladung_kWh",
            "aggregiert_in": "batterie_entladung_sum",
        },
    ],

    # Sonstiges: Felder hängen von der Kategorie ab (via get_felder_fuer_sonstiges)
    "sonstiges": {
        "erzeuger": [
            {
                "feld": "erzeugung_kwh", "label": "Erzeugung", "einheit": "kWh",
                "csv_suffix": "Erzeugung_kWh",
                "aggregiert_in": "pv_erzeugung_sum",
            },
            {
                "feld": "eigenverbrauch_kwh", "label": "Eigenverbrauch", "einheit": "kWh",
                "csv_suffix": "Eigenverbrauch_kWh",
            },
            {
                "feld": "einspeisung_kwh", "label": "Einspeisung", "einheit": "kWh",
                "csv_suffix": "Einspeisung_kWh",
            },
        ],
        "verbraucher": [
            {
                "feld": "verbrauch_sonstig_kwh", "label": "Verbrauch", "einheit": "kWh",
                "csv_suffix": "Verbrauch_kWh",
            },
            {
                "feld": "bezug_pv_kwh", "label": "davon PV", "einheit": "kWh",
                "csv_suffix": "Bezug_PV_kWh",
            },
            {
                "feld": "bezug_netz_kwh", "label": "davon Netz", "einheit": "kWh",
                "csv_suffix": "Bezug_Netz_kWh",
            },
        ],
        "speicher": [
            # Hinweis: cockpit/komponenten.py liest erzeugung_kwh/verbrauch_sonstig_kwh
            # für Sonstiges-Speicher — diese Feldnamen sind bindend.
            {
                "feld": "erzeugung_kwh", "label": "Erzeugung/Entladung", "einheit": "kWh",
                "csv_suffix": "Erzeugung_kWh",
                "aggregiert_in": "batterie_entladung_sum",
            },
            {
                "feld": "verbrauch_sonstig_kwh", "label": "Verbrauch/Ladung", "einheit": "kWh",
                "csv_suffix": "Verbrauch_kWh",
                "aggregiert_in": "batterie_ladung_sum",
            },
        ],
    },
}

# Alte Feldnamen → neue kanonische Namen (für Lese-Kompatibilität mit alten DB-Einträgen)
LEGACY_FELDNAMEN: dict[str, str] = {
    "speicher_ladung_netz_kwh": "ladung_netz_kwh",   # Speicher Arbitrage
    "entladung_v2h_kwh":        "v2h_entladung_kwh", # E-Auto V2H
}

# Summen-Keys die _import_investition_monatsdaten_v09 zurückgibt
IMPORT_SUMMEN_KEYS = ("pv_erzeugung_sum", "batterie_ladung_sum", "batterie_entladung_sum")


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


def get_alle_felder_fuer_investition(typ: str, parameter: Optional[dict] = None) -> list[dict]:
    """
    Gibt ALLE Felder für einen Investitionstyp zurück — ohne Bedingungsfilter.

    Für Import-Kontext: alle Felder anbieten, unabhängig von aktuellen Parametern.
    Der Import soll nie Daten stillschweigend ignorieren.

    Für Sonstiges wird die Kategorie aus `parameter` gelesen (Default: "erzeuger").

    Args:
        typ: Investitionstyp
        parameter: Investitions-Parameter-Dict (nur für Sonstiges-Kategorie benötigt)

    Returns:
        Liste aller Feld-Dicts (inkl. konditioneller Felder)
    """
    alle_felder = INVESTITION_FELDER.get(typ, [])

    if isinstance(alle_felder, dict):
        # Sonstiges — Kategorie-abhängig
        params = parameter or {}
        kategorie = params.get("kategorie", "erzeuger")
        return list(get_felder_fuer_sonstiges(kategorie))

    return list(alle_felder)


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
