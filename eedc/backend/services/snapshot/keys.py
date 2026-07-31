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
    # Balkonkraftwerk: NUR die Erzeugung. Die BKW-eigenen Felder
    # `speicher_ladung_kwh`/`speicher_entladung_kwh` standen hier kurzzeitig
    # (Paket D, 2026-07-31) — zurückgenommen am selben Tag, weil der Kanon für
    # einen BKW-Akku die **eigene Speicher-Investition mit Parent
    # Balkonkraftwerk** ist (Weg A). Die trägt Live-Leistung, SoC und
    # Energiefluss-Knoten und läuft über den Eintrag `"speicher"` unten; ein
    # zweiter Zählerpfad für dasselbe Gerät wäre die Doppelerfassung, die der
    # Rückbau gerade beseitigt. `eigenverbrauch_kwh` steht ebenfalls nicht hier:
    # optionale Verfeinerung aus manueller Pflege/Import, kein Zähler
    # (Begründung im Modul-Docstring von `core/berechnungen/bkw_finanz.py`).
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

# Reine Counter (Anzahl-/Stunden-Zählwerte ohne kWh-Semantik, Issue #136).
# Werden vom Snapshot-Job mit erfasst (gleiches Schema, gleiche Tabelle), aber
# NICHT in die Energie-Bilanz von get_hourly_kwh_by_category einbezogen.
# Aggregation als Tages-Differenz erfolgt separat in aggregate_day.
#
# `wp_betriebsstunden` ist analog zu `wp_starts_anzahl` (#238 detLAN, Forum 5/5).
# Float-Counter — total_increasing in Stunden. Verhältnis Starts/Betriebsstunde
# bzw. Ø Laufzeit pro Start ist der eigentliche Diagnose-Wert (10 Starts auf
# 23 h sind ein Performance-Indikator, 10 Starts auf 4 h sind in Ordnung).
KUMULATIVE_COUNTER_FELDER: dict[str, tuple[str, ...]] = {
    "waermepumpe": ("wp_starts_anzahl", "wp_betriebsstunden"),
}

# Counter-Felder, deren Tages-/Stunden-Delta GEBROCHEN ist (Stunden statt
# Zählwerte). Diese dürfen NICHT int-gerundet werden — sonst gehen Teil-
# Laufzeiten verloren und Tages- vs. Stunden-Aggregation driften auseinander
# (Forum-Befund Martin 2026-05-11 zur Counter-Drift). Starts bleiben ganzzahlig.
# Eine Quelle der Wahrheit für daily- + hourly-Aggregator (#238).
FLOAT_COUNTER_FELDER: frozenset[str] = frozenset({"wp_betriebsstunden"})

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


# ─── Datenquellen-V4 C2b: feld-zentrische Quellen-Zuordnung (Energie-Pfad) ───
#
# Read-Through-Resolver für den kWh-/Snapshot-Pfad, analog zum Live-W-Resolver
# (`live_sensor_config.extract_quellen_live`, C2a). Eine explizite `quellen`-
# Zuordnung eines ENERGIE-Feldes gilt; ohne Eintrag bleibt das heutige,
# modus-basierte Verhalten UNVERÄNDERT (Regressionsschutz, keine erzwungene
# Migration, keine stille MQTT↔HA-Prioritäts-Umkehr). SoT-Konzept §2b1/§2d.

QUELLE_HA_ENERGY = ("ha_app", "ha_connector")
QUELLE_MQTT_ENERGY = ("mqtt_inbound_standard", "mqtt_gateway")
QUELLE_KEINE_ENERGY = "keine"


def _energy_field_id_to_sensor_key(field_id: str) -> Optional[str]:
    """`quellen`-Feld-ID (`basis_energy_*`/`inv_energy_{id}_{feld}`) → sensor_key.

    Nutzt die bestehende Key-Übersetzungs-SoT `_mqtt_key_to_sensor_key`, damit
    kein zweites Mapping driftet: `basis_energy_einspeisung_kwh` → (mqtt
    `einspeisung_kwh`) → `basis:einspeisung`; `inv_energy_2_pv_erzeugung_kwh` →
    (mqtt `inv/2/pv_erzeugung_kwh`) → `inv:2:pv_erzeugung_kwh`. Felder ohne
    Snapshot-Counterpart (z. B. `basis_energy_pv_gesamt_kwh` — PV läuft pro
    Investition) liefern None und werden ignoriert.
    """
    if field_id.startswith("basis_energy_"):
        return _mqtt_key_to_sensor_key(field_id[len("basis_energy_"):])
    if field_id.startswith("inv_energy_"):
        rest = field_id[len("inv_energy_"):]
        inv_id, sep, feld = rest.partition("_")
        if sep and inv_id.isdigit() and feld:
            return _mqtt_key_to_sensor_key(f"inv/{inv_id}/{feld}")
    return None


def extract_quellen_energy(anlage) -> dict[str, tuple[Optional[str], Optional[str]]]:
    """Explizite Datenquellen-Zuordnungen (`quellen`-Map) der ENERGIE-Felder (C2b).

    Read-Through-Resolver-Eingabe: NUR Energie-Felder mit ausdrücklichem
    `quellen`-Eintrag; Live-Felder (`basis_live_*`/`inv_live_*`) gehören zu C2a
    und werden hier ignoriert.

    Returns:
        {sensor_key: (quelle, entity_id|None)} — z. B.
        {"basis:einspeisung": ("ha_connector", "sensor.zaehler"),
         "inv:2:pv_erzeugung_kwh": ("mqtt_inbound_standard", None),
         "inv:5:ladung_kwh": ("keine", None)}
    """
    mapping = anlage.sensor_mapping or {}
    quellen = mapping.get("quellen") if isinstance(mapping, dict) else None
    out: dict[str, tuple[Optional[str], Optional[str]]] = {}
    if not isinstance(quellen, dict):
        return out
    for field_id, entry in quellen.items():
        if not isinstance(field_id, str) or not isinstance(entry, dict):
            continue
        sk = _energy_field_id_to_sensor_key(field_id)
        if sk is None:
            continue
        out[sk] = (entry.get("quelle"), entry.get("entity_id"))
    return out


def resolve_energy_snapshot_eid(
    quellen_energy: dict[str, tuple[Optional[str], Optional[str]]],
    sensor_key: str,
    raw_eid: Optional[str],
) -> tuple[Optional[str], bool]:
    """Read-Through für den SNAPSHOT-Pfad (Writer + `get_snapshot`).

    Returns `(effektive_entity_id, behalten)`:
      - kein `quellen`-Eintrag → `(raw_eid, True)` (heutiges Verhalten, bitgleich)
      - HA-Quelle → `(entity_id, True)` (Self-Heal/Write gegen zugeordnete Entity)
      - MQTT-Quelle → `(None, True)` (kein HA-Read; MQTT-Fallback via sensor_key)
      - keine → `(None, False)` (kein Wert, strikt kein Fallback)
    """
    if sensor_key not in quellen_energy:
        return raw_eid, True
    quelle, entity = quellen_energy[sensor_key]
    if quelle in QUELLE_HA_ENERGY:
        return entity, True
    if quelle in QUELLE_MQTT_ENERGY:
        return None, True
    return None, False  # keine


def resolve_energy_ha_eid(
    quellen_energy: dict[str, tuple[Optional[str], Optional[str]]],
    sensor_key: str,
    raw_eid: Optional[str],
) -> tuple[Optional[str], bool]:
    """Read-Through für reine HA-Pfade ohne MQTT-Fallback (LTS-direkt, Preview).

    Returns `(effektive_entity_id, behalten)`:
      - kein `quellen`-Eintrag → `(raw_eid, True)` (heutiges Verhalten)
      - HA-Quelle → `(entity_id, True)`
      - MQTT- oder keine-Quelle → `(None, False)` (HA-Pfad liest das Feld nicht;
        der Wert kommt aus dem MQTT-/Snapshot-Pfad bzw. gar nicht)
    """
    if sensor_key not in quellen_energy:
        return raw_eid, True
    quelle, entity = quellen_energy[sensor_key]
    if quelle in QUELLE_HA_ENERGY:
        return entity, True
    return None, False  # mqtt oder keine → HA-Pfad überspringt


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
