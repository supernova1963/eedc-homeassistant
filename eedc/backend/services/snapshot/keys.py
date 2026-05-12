"""
Snapshot-Key-Schema und Konstanten.

Hält die zentralen Listen kumulativer Zähler-Felder pro Investitionstyp,
das `sensor_key`-Schema (`basis:<feld>` / `inv:<id>:<feld>`), die Mapping-
Funktionen zwischen MQTT-Topic-Keys und SensorSnapshot-Keys, sowie die
Kategorie-Zuordnung für Energiefluss-Aggregation.

Reine Konstanten + reine Funktionen — keine I/O, keine DB-Abhängigkeit.
"""

from __future__ import annotations

from typing import Optional


# Felder die kumulative kWh-Zählerstände enthalten, pro Investitionstyp.
# Wird von _build_counter_map konsumiert.
KUMULATIVE_ZAEHLER_FELDER: dict[str, tuple[str, ...]] = {
    "pv-module": ("pv_erzeugung_kwh",),
    "balkonkraftwerk": ("pv_erzeugung_kwh",),
    "speicher": ("ladung_kwh", "entladung_kwh", "ladung_netz_kwh"),
    "waermepumpe": (
        "stromverbrauch_kwh",
        "strom_heizen_kwh",
        "strom_warmwasser_kwh",
        "heizenergie_kwh",
        "warmwasser_kwh",
    ),
    "wallbox": ("ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh"),
    "e-auto": ("ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh", "verbrauch_kwh"),
    "sonstiges": ("verbrauch_kwh", "erzeugung_kwh"),
}

# Reine Counter (Anzahl-Zählwerte ohne kWh-Semantik, Issue #136).
# Werden vom Snapshot-Job mit erfasst (gleiches Schema, gleiche Tabelle), aber
# NICHT in die Energie-Bilanz von get_hourly_kwh_by_category einbezogen.
# Aggregation als Tages-Differenz erfolgt separat in aggregate_day.
KUMULATIVE_COUNTER_FELDER: dict[str, tuple[str, ...]] = {
    "waermepumpe": ("wp_starts_anzahl",),
}

BASIS_ZAEHLER_FELDER: tuple[str, ...] = ("einspeisung", "netzbezug")


# MQTT-Energy-Topic-Keys → sensor_snapshots.sensor_key Mapping.
# Das MQTT-Inbound nutzt flachere Keys (z.B. "inv/14/pv_erzeugung_kwh"),
# SensorSnapshot nutzt Doppelpunkt-Schema für Konsistenz mit HA-Pfad.
_MQTT_BASIS_KEYS: dict[str, str] = {
    "einspeisung_kwh": "basis:einspeisung",
    "netzbezug_kwh": "basis:netzbezug",
}


def _mqtt_key_to_sensor_key(mqtt_key: str) -> Optional[str]:
    """
    Konvertiert MQTT-Energy-Topic-Key ins SensorSnapshot.sensor_key-Schema.

    Gibt None zurück für Keys die keine kumulative kWh-Energie sind
    (ladevorgaenge, km_gefahren, speicher_ladepreis_cent etc.).
    """
    if mqtt_key in _MQTT_BASIS_KEYS:
        return _MQTT_BASIS_KEYS[mqtt_key]
    if mqtt_key.startswith("inv/"):
        parts = mqtt_key.split("/", 2)
        if len(parts) == 3:
            _, inv_id, feld = parts
            # Kumulative Energie-Felder + reine Counter (keine km_gefahren, Preise, etc.)
            alle_felder = (
                {f for felder in KUMULATIVE_ZAEHLER_FELDER.values() for f in felder}
                | {f for felder in KUMULATIVE_COUNTER_FELDER.values() for f in felder}
            )
            if feld in alle_felder:
                return f"inv:{inv_id}:{feld}"
    return None


def _sensor_key_to_mqtt_key(sensor_key: str) -> Optional[str]:
    """Umkehrung von _mqtt_key_to_sensor_key."""
    if sensor_key == "basis:einspeisung":
        return "einspeisung_kwh"
    if sensor_key == "basis:netzbezug":
        return "netzbezug_kwh"
    if sensor_key.startswith("inv:"):
        parts = sensor_key.split(":", 2)
        if len(parts) == 3:
            _, inv_id, feld = parts
            return f"inv/{inv_id}/{feld}"
    return None


def _is_kumulativ_feld(feld_name: str) -> bool:
    """Prüft ob ein Feld-Name ein kumulativer Zähler ist (Energie oder Counter)."""
    alle = (
        {f for felder in KUMULATIVE_ZAEHLER_FELDER.values() for f in felder}
        | {f for felder in KUMULATIVE_COUNTER_FELDER.values() for f in felder}
    )
    return feld_name in alle


def _categorize_counter(
    feld: str,
    inv_typ: Optional[str],
    parameter: Optional[dict],
) -> Optional[str]:
    """
    Ordnet ein gemapptes Zähler-Feld einer Energiefluss-Kategorie zu.

    Rückgabewerte werden in aggregate_day für die Summenbildung pro
    Stunde genutzt:
        "pv", "einspeisung", "netzbezug",
        "ladung_batterie", "entladung_batterie",
        "ladung_wallbox", "verbrauch_wp",
        "verbrauch_eauto",
        "erzeugung_sonstiges", "verbrauch_sonstiges"
    """
    if inv_typ is None:  # basis
        if feld == "einspeisung":
            return "einspeisung"
        if feld == "netzbezug":
            return "netzbezug"
        return None

    if inv_typ in ("pv-module", "balkonkraftwerk") and feld == "pv_erzeugung_kwh":
        return "pv"
    if inv_typ == "speicher":
        if feld == "ladung_kwh":
            return "ladung_batterie"
        if feld == "entladung_kwh":
            return "entladung_batterie"
    if inv_typ == "waermepumpe":
        # Wenn die Anlage Strom-Heizen/-Warmwasser getrennt erfasst (#191),
        # sind die beiden Einzel-Sensoren die elektrische Wahrheit; das alte
        # `stromverbrauch_kwh`-Feld wird ignoriert (analog zu get_wp_strom_kwh
        # in field_definitions.py). Andernfalls zählt der Gesamt-Strom-Sensor.
        getrennte = bool((parameter or {}).get("getrennte_strommessung"))
        if getrennte:
            if feld in ("strom_heizen_kwh", "strom_warmwasser_kwh"):
                return "verbrauch_wp"
        else:
            if feld == "stromverbrauch_kwh":
                return "verbrauch_wp"
    if inv_typ == "wallbox" and feld == "ladung_kwh":
        return "ladung_wallbox"
    if inv_typ == "e-auto" and feld in ("verbrauch_kwh", "ladung_kwh"):
        return "verbrauch_eauto"
    if inv_typ == "sonstiges":
        kategorie = (parameter or {}).get("kategorie", "verbraucher") if isinstance(parameter, dict) else "verbraucher"
        if feld == "erzeugung_kwh" or (feld == "verbrauch_kwh" and kategorie == "erzeuger"):
            return "erzeugung_sonstiges"
        if feld == "verbrauch_kwh":
            return "verbrauch_sonstiges"
    return None
