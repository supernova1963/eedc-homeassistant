"""
Live Sensor Konfiguration - Konstanten und Mapping-Extraktion für Live-Daten.

Ausgelagert aus live_power_service.py (Schritt 1 des Refactorings).
Enthält nur reine Daten und Logik ohne I/O.
"""

import logging
from backend.models.anlage import Anlage

logger = logging.getLogger(__name__)


# Einheiten-Konvertierung: HA gibt State in suggested_unit zurück (z.B. kW statt W).
# Wir normalisieren alles zu W, damit die Berechnung einheitlich ist.
UNIT_TO_W: dict[str, float] = {
    "W": 1.0,
    "kW": 1000.0,
    "MW": 1_000_000.0,
}


def normalize_to_w(value: float, unit: str) -> float:
    """Konvertiert einen Leistungswert in W basierend auf der HA-Einheit.

    SoC (%) und unbekannte Einheiten werden unverändert durchgereicht.
    """
    factor = UNIT_TO_W.get(unit)
    if factor is not None:
        return value * factor
    return value


# Icon-Zuordnung pro Investitionstyp
TYP_ICON = {
    "pv-module": "sun",
    "balkonkraftwerk": "sun",
    "speicher": "battery",
    "e-auto": "car",
    "wallbox": "plug",
    "waermepumpe": "flame",
    "sonstiges": "wrench",
    "wechselrichter": "zap",
}

# Investitionstypen die als Erzeuger zählen
ERZEUGER_TYPEN = {"pv-module", "balkonkraftwerk"}

# Bidirektionale Typen (positiv = Ladung/Verbrauch, negativ = Entladung/Erzeugung)
BIDIREKTIONAL_TYPEN = {"speicher"}

# Typen die SoC-Gauges bekommen
SOC_TYPEN = {"speicher", "e-auto"}

# Typen die im Live-Dashboard übersprungen werden (Durchleiter, keine eigene Messgröße)
SKIP_TYPEN = {"wechselrichter"}

# Kategorien für Tagesverlauf-Aggregation (Legacy, wird noch für Live-Komponenten-Keys genutzt)
TAGESVERLAUF_KATEGORIE = {
    "pv-module": "pv",
    "balkonkraftwerk": "pv",
    "speicher": "batterie",
    "e-auto": "eauto",
    "wallbox": "eauto",
    "waermepumpe": "waermepumpe",
    "sonstiges": "sonstige",
}

# Tagesverlauf: Kategorie + Seite (quelle/senke) + Farbe pro Investitionstyp
TV_SERIE_CONFIG: dict[str, dict] = {
    "pv-module":       {"kategorie": "pv",          "seite": "quelle", "farbe": "#eab308", "bidirektional": False},
    "balkonkraftwerk": {"kategorie": "pv",          "seite": "quelle", "farbe": "#eab308", "bidirektional": False},
    "speicher":        {"kategorie": "batterie",    "seite": "quelle", "farbe": "#3b82f6", "bidirektional": True},
    "wallbox":         {"kategorie": "wallbox",     "seite": "senke",  "farbe": "#a855f7", "bidirektional": False},
    "e-auto":          {"kategorie": "eauto",       "seite": "senke",  "farbe": "#a855f7", "bidirektional": False},
    "waermepumpe":     {"kategorie": "waermepumpe", "seite": "senke",  "farbe": "#f97316", "bidirektional": False},
    "sonstiges":       {"kategorie": "sonstige",    "seite": "senke",  "farbe": "#64748b", "bidirektional": False},
}

# Separate Key-Prefixe für Live-Komponenten (Energiefluss)
LIVE_KEY_PREFIX = {
    "wallbox": "wallbox",
}


def extract_live_config(anlage: Anlage) -> tuple[
    dict[str, str], dict[str, dict[str, str]],
    dict[str, bool], dict[str, dict[str, bool]],
]:
    """
    Extrahiert Live-Sensor-Konfiguration aus sensor_mapping.

    Returns:
        (basis_live, inv_live_map, basis_invert, inv_invert_map)
        basis_live: {einspeisung_w: entity_id, netzbezug_w: entity_id}
        inv_live_map: {inv_id: {leistung_w: entity_id, soc: entity_id}}
        basis_invert: {einspeisung_w: True}  — Vorzeichen invertieren
        inv_invert_map: {inv_id: {leistung_w: True}}
    """
    mapping = anlage.sensor_mapping or {}

    basis_live: dict[str, str] = {}
    inv_live_map: dict[str, dict[str, str]] = {}
    basis_invert: dict[str, bool] = {}
    inv_invert_map: dict[str, dict[str, bool]] = {}

    basis = mapping.get("basis", {})
    if isinstance(basis.get("live"), dict):
        basis_live = {k: v for k, v in basis["live"].items() if v}
    if isinstance(basis.get("live_invert"), dict):
        basis_invert = {k: v for k, v in basis["live_invert"].items() if v}

    for inv_id, inv_data in mapping.get("investitionen", {}).items():
        if isinstance(inv_data, dict) and isinstance(inv_data.get("live"), dict):
            live = {k: v for k, v in inv_data["live"].items() if v}
            if live:
                inv_live_map[inv_id] = live
        if isinstance(inv_data, dict) and isinstance(inv_data.get("live_invert"), dict):
            invert = {k: v for k, v in inv_data["live_invert"].items() if v}
            if invert:
                inv_invert_map[inv_id] = invert

    # Fallback: altes live_sensors-Dict (Migration)
    if not basis_live and not inv_live_map:
        legacy = mapping.get("live_sensors", {})
        if legacy:
            if legacy.get("einspeisung_w"):
                basis_live["einspeisung_w"] = legacy["einspeisung_w"]
            if legacy.get("netzbezug_w"):
                basis_live["netzbezug_w"] = legacy["netzbezug_w"]
            if any(k not in ("einspeisung_w", "netzbezug_w") for k in legacy):
                logger.info(
                    "Anlage %s nutzt noch legacy live_sensors — "
                    "bitte Sensor-Zuordnung im Wizard aktualisieren",
                    anlage.id,
                )

    return basis_live, inv_live_map, basis_invert, inv_invert_map
