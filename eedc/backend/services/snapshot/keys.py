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

from backend.core.field_definitions import (
    SONSTIGES_KATEGORIE_UNGEPFLEGT,
    SONSTIGES_VERBRAUCH_FELDER,
    basis_feld_key,
    ist_stand_feld,
    kumulative_zaehler_felder_je_typ,
)


# Felder die kumulative kWh-Zählerstände enthalten, pro Investitionstyp.
# Wird von _build_counter_map konsumiert.
#
# ⚑ **Seit 2026-08-16 (N-259) ABGELEITET statt gepflegt.** Bis dahin stand hier
# eine zweite Liste derselben Feldnamen, die in `core/field_definitions.py`
# ohnehin als Registry existieren — und die beiden waren auseinandergelaufen:
# Ein *Sonstiges*-Verbraucher heißt in der Registry `verbrauch_sonstig_kwh`
# (so schreibt es die Zuordnungsfläche ins `sensor_mapping`, so baut
# `mqtt_topic_registry` das Topic), diese Liste kannte `verbrauch_kwh`. Damit
# verwarf `_mqtt_key_to_sensor_key` weiter unten ein Topic, das eedc **selbst
# publiziert**, und der Heizstab eines Melders existierte auf Stunden- und
# Tagesebene nicht — während der Monat ankam, weil
# `get_sonstiges_verbrauch_kwh` beide Namen liest.
#
# Die Ausnahmen (welches kWh-Feld bewusst NICHT gesnapshottet wird) stehen
# jetzt begründet neben der Registry, nicht als Auslassung in einer Aufzählung:
# `field_definitions._SNAPSHOT_AUSNAHMEN`. Gewächtert in
# `test_snapshot_felder_sot_konformitaet.py` — dort fällt auf, was hier früher
# nur fehlte.
KUMULATIVE_ZAEHLER_FELDER: dict[str, tuple[str, ...]] = kumulative_zaehler_felder_je_typ()

# Reine Counter (Anzahl-/Stunden-Zählwerte ohne kWh-Semantik, Issue #136).
# Werden vom Snapshot-Job mit erfasst (gleiches Schema, gleiche Tabelle), aber
# NICHT in die Energie-Bilanz von get_hourly_kwh_by_category einbezogen.
# Aggregation als Tages-Differenz erfolgt separat in aggregate_day.
#
# `wp_betriebsstunden` ist analog zu `wp_starts_anzahl` (#238 detLAN, Forum 5/5).
# Float-Counter — total_increasing in Stunden. Verhältnis Starts/Betriebsstunde
# bzw. Ø Laufzeit pro Start ist der eigentliche Diagnose-Wert (10 Starts auf
# 23 h sind ein Performance-Indikator, 10 Starts auf 4 h sind in Ordnung).
#
# `sonstiges/zaehlerstand` ist seit #377 dabei — der Zählerstand eines Gas-,
# Wasser- oder Ölzählers. Er gehört genau hierher und **nicht** zu
# `KUMULATIVE_ZAEHLER_FELDER`: Diese Liste ist die für Werte ohne
# kWh-Semantik, die trotzdem mitgeschrieben werden. Die Energie-Liste darüber
# ist abgeleitet und filtert auf `einheit_klasse == "energie"` — ein
# einheitenloses Feld fällt dort strukturell heraus, und genau das ist
# gewollt: so kann ein Gasverbrauch nie in die Strombilanz laufen.
KUMULATIVE_COUNTER_FELDER: dict[str, tuple[str, ...]] = {
    "waermepumpe": ("wp_starts_anzahl", "wp_betriebsstunden"),
    "sonstiges": ("zaehlerstand",),
}

# Counter-Felder, deren Tages-/Stunden-Delta GEBROCHEN ist (Stunden statt
# Zählwerte). Diese dürfen NICHT int-gerundet werden — sonst gehen Teil-
# Laufzeiten verloren und Tages- vs. Stunden-Aggregation driften auseinander
# (Forum-Befund Martin 2026-05-11 zur Counter-Drift). Starts bleiben ganzzahlig.
# Eine Quelle der Wahrheit für daily- + hourly-Aggregator (#238).
#
# `zaehlerstand` (#377) steht hier aus demselben Grund: Ein Gaszähler zeigt
# `312,4`, ein Wasserzähler `1.284,637`. Ohne diesen Eintrag rundeten die
# Counter-Pfade ganzzahlig, aus 312,4 würde 312 — und die Differenz über einen
# Monat verlöre bis zu zwei ganze Einheiten an den Rändern. Bei einem
# Anzahl-Zähler (Starts) ist die Rundung richtig, hier ist sie ein Messfehler.
FLOAT_COUNTER_FELDER: frozenset[str] = frozenset({"wp_betriebsstunden", "zaehlerstand"})

# Basis-Zähler mit Snapshot-Gegenstück.
#
# `pv_gesamt` ist seit 2026-08-07 dabei (Stufe 1 zu F-7, Forum kaba-kakao
# T89667 #109). Vorher versorgte der Anlagen-Zählerstand ausschließlich den
# **Monat** (`basis["pv_gesamt"]` → `Monatsdaten.pv_erzeugung_kwh`, Eingang von
# `resolve_pv_je_modul`, ADR-002/P7); die Tages- und Stundenebene entstand nur
# aus Zählern **je Erzeuger**. Wer eine Anlage mit EINEM Summenzähler und
# mehreren Ausrichtungen betreibt, hatte damit gar keine Tages-PV — und die
# Tagesbilanz rechnete daraus einen negativen Eigenverbrauch (F-7).
#
# Der naheliegende Ausweg „alles als EINE Investition erfassen" ist verboten:
# `services/pv_orientation.py` gruppiert je Investition nach (Neigung, Azimut)
# und nennt die Folge im Docstring wörtlich — ein systematisch falscher
# Tagesgang für den gesamten Prognose-Kanon inkl. HA-Prognose-Sensoren und
# PVGIS-SOLL. Deshalb bekommt das Aggregat einen eigenen Zählerpfad, statt die
# Anlagenstruktur zu verbiegen.
#
# **Alles-oder-nichts, kein Split:** der Beitrag entsteht nur, wenn KEIN
# Erzeuger einen eigenen `pv_erzeugung_kwh`-Zähler trägt — Regel und
# Begründung in `komponenten_beitraege.pv_je_investition_belegt`. Eine
# kWp-Verteilung auf Tagesebene ist ausdrücklich nicht vorgesehen (Entscheid
# Gernot 2026-08-07, festgehalten in `docs/BERECHNUNGEN.md`).
BASIS_ZAEHLER_FELDER: tuple[str, ...] = ("einspeisung", "netzbezug", "pv_gesamt")


# MQTT-Energy-Topic-Keys → sensor_snapshots.sensor_key Mapping.
# Das MQTT-Inbound nutzt flachere Keys (z.B. "inv/14/pv_erzeugung_kwh"),
# SensorSnapshot nutzt Doppelpunkt-Schema für Konsistenz mit HA-Pfad.
_MQTT_BASIS_KEYS: dict[str, str] = {
    "einspeisung_kwh": "basis:einspeisung",
    "netzbezug_kwh": "basis:netzbezug",
    "pv_gesamt_kwh": "basis:pv_gesamt",
}

# Umkehrung von `_MQTT_BASIS_KEYS` — abgeleitet statt zweitgeschrieben, damit
# ein neuer Basis-Zähler nicht in genau einer Richtung fehlt.
_BASIS_SENSOR_KEYS: dict[str, str] = {v: k for k, v in _MQTT_BASIS_KEYS.items()}


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
            if basis_feld_key(feld) in alle_felder:
                return f"inv:{inv_id}:{feld}"
    return None


def _sensor_key_to_mqtt_key(sensor_key: str) -> Optional[str]:
    """Umkehrung von _mqtt_key_to_sensor_key."""
    if sensor_key in _BASIS_SENSOR_KEYS:
        return _BASIS_SENSOR_KEYS[sensor_key]
    if sensor_key.startswith("inv:"):
        parts = sensor_key.split(":", 2)
        if len(parts) == 3:
            _, inv_id, feld = parts
            return f"inv/{inv_id}/{feld}"
    return None


def ist_stand_sensor_key(sensor_key: str) -> bool:
    """Trägt dieser Snapshot-Key einen **Stand** statt einer Menge? (F-58)

    Die Frage entscheidet, welche Spalte der HA-Statistik gelesen wird —
    `state` für einen Stand, `sum` für eine Menge. Sie wird **am Feld**
    beantwortet (`field_definitions.STAND_FELDER`); hier steht nur die
    Zerlegung des Keys, damit der Schreibpfad sie nicht selbst nachbaut.

    Keys sind `basis:<feld>` oder `inv:<id>:<feld>` — in beiden Fällen ist das
    Feld der letzte Abschnitt.
    """
    if not sensor_key:
        return False
    return ist_stand_feld(sensor_key.rpartition(":")[2])


def _is_kumulativ_feld(feld_name: str) -> bool:
    """Prüft ob ein Feld-Name ein kumulativer Zähler ist (Energie oder Counter).

    ⚠ **Mit Basis-Key-Auflösung** (#263): Die Betriebsart-Zähler einer
    Split-Klimaanlage gibt es je Innengerät
    (`betriebsart_strom_kuehlen_kwh-3`). Die Listen oben führen sie — wie jede
    Namens-Whitelist — nur unter ihrem Basis-Namen. Ohne die Auflösung wäre ein
    je-Innengerät-Zähler zuordenbar und würde **nie gesnapshottet**: still, ohne
    Fehlermeldung, mit einer Tages- und Stundenebene, die es nicht gibt.
    """
    alle = (
        {f for felder in KUMULATIVE_ZAEHLER_FELDER.values() for f in felder}
        | {f for felder in KUMULATIVE_COUNTER_FELDER.values() for f in felder}
    )
    return basis_feld_key(feld_name) in alle


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
    Snapshot-Counterpart (Preis-Felder, Live-Felder) liefern None und werden
    ignoriert.

    ⚠ **`basis_energy_pv_gesamt_kwh` gehörte bis 2026-08-07 zu diesen Feldern**
    und liefert seither `basis:pv_gesamt` — der Anlagen-Zählerstand hat mit
    Stufe 1 zu F-7 ein Snapshot-Gegenstück bekommen (Begründung an
    `BASIS_ZAEHLER_FELDER`). Wer den alten Satz sucht: er stand hier, in
    `datenquellen_mapping_sync.BASIS_ENERGY_FELD` und in
    `tests/test_datenquellen_resolver_c2b.py`.
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


def feld_hat_zaehler(
    config: Optional[dict],
    sensor_key: str,
    quellen_energy: dict[str, tuple[Optional[str], Optional[str]]],
    mqtt_keys: Optional[set[str]] = None,
) -> bool:
    """Trägt dieses Feld einen kumulativen Zähler — egal über welchen Weg?

    **Die eine Antwort für alle Frager** (N-328/N-328b, #396 gruaGit): Der
    Daten-Checker, der Tages-Aggregator, der Stunden-Aggregator, der
    Live-Counter-Read und die Reload-Vorschau haben dieselbe Frage bis zum
    26.08. jeweils selbst beantwortet — und alle fünf mit derselben zu engen
    Annahme `strategie == "sensor"`, also „nur ein HA-Sensor ist ein Zähler".

    **Die Regel, in zwei Tatsachen und einer Absage:**

    1. Dem Feld ist ein **HA-Sensor** zugeordnet (klassische `felder`-Struktur)
       → Zähler.
    2. Für seinen `sensor_key` sind **MQTT-Zählerstände angekommen** → Zähler.
    3. Die Quelle ist ausdrücklich ``"keine"`` → **kein** Zähler, egal was
       sonst vorliegt. Eine Absage des Anwenders schlägt jede Evidenz (§2d).

    ⛔ **Warum NICHT „ein `quellen`-Eintrag genügt".** Das war der erste
    Entwurf, und er hätte den Checker auf **jeder Bestandsanlage** verstummen
    lassen: `migrations/migrate_datenquellen_materialisieren.py:99` stempelt
    beim einmaligen Start-Lauf ``{"quelle": "mqtt_inbound_standard"}`` auf
    **jedes** Feld ohne HA-Sensor und ohne Gateway-Zeile — konservativ und
    bewusst (Entscheid 2026-07-15), aber eben ohne MQTT je zu prüfen. Gemessen
    am 27.08. an einer frisch angelegten Anlage, die nie MQTT gesehen hat:
    31 Felder, 31-mal ``mqtt_inbound_standard``, darunter genau das Feld des
    Melders. *Ein Stempel und eine Wahl sehen im Store bitgleich aus — deshalb
    entscheidet hier der Messwert, nicht der Eintrag.*

    ⭐ Damit folgt das Lesen derselben Unterscheidung, die das **Schreiben**
    längst trifft: `datenquellen_resolver.resolve_effektive_quelle` schreibt
    Inbound nur bei tatsächlichem Wert fest, stummes Inbound gar nicht.

    **Gateway braucht keinen Sonderfall:** Der Gateway-Dienst re-publiziert auf
    dasselbe Inbound-Topic, der Wert landet im selben Cache und damit in
    `mqtt_keys`. Ein *stummes* Gateway-Mapping soll melden — so steht es
    wörtlich in `datenquellen_resolver.erwartet_inbound_topic`.

    Args:
        config: Der `felder[feld]`- bzw. `basis[feld]`-Eintrag des klassischen
            `sensor_mapping` — oder None, wenn es keinen gibt (der Regelfall
            auf einer reinen MQTT-Anlage, s. `datenquellen_mapping_sync`).
        sensor_key: `basis:<feld>` bzw. `inv:<id>:<feld>`.
        quellen_energy: `extract_quellen_energy(anlage)`.
        mqtt_keys: sensor_keys mit MQTT-Zählerständen
            (`reader.mqtt_zaehler_keys`). None/leer ⇒ nur Weg 1 kann greifen.

    Returns:
        True, wenn das Feld einen kumulativen Zähler trägt.
    """
    quelle = (quellen_energy.get(sensor_key) or (None, None))[0]
    if quelle == QUELLE_KEINE_ENERGY:
        return False
    if (
        isinstance(config, dict)
        and config.get("strategie") == "sensor"
        and config.get("sensor_id")
    ):
        return True
    return bool(mqtt_keys) and sensor_key in mqtt_keys


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
        if feld == "pv_gesamt":
            # Der Anlagen-Zählerstand trägt dieselbe Größe wie die Summe der
            # Erzeuger-Zähler und gehört deshalb in dieselbe Kategorie. Dass
            # beide nie gleichzeitig gezählt werden, entscheidet NICHT diese
            # Funktion, sondern die Feld-Auswahl davor (`basis_beitraege` /
            # `mqtt_hourly_eintraege`) — seit #298 ist `_categorize_counter`
            # kein Whitelist-Gatekeeper mehr, sondern nur noch die Abbildung
            # Feld → Kategorie.
            return "pv"
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
        kategorie = (
            parameter.get("kategorie", SONSTIGES_KATEGORIE_UNGEPFLEGT)
            if isinstance(parameter, dict)
            else SONSTIGES_KATEGORIE_UNGEPFLEGT
        )
        # `verbrauch_sonstig_kwh` ist der kanonische Registry-Name (N-259),
        # `verbrauch_kwh` der Legacy-Zwilling — dieselbe Präzedenz wie in
        # `get_sonstiges_verbrauch_kwh`. Bis 16.08.2026 stand hier NUR der
        # Legacy-Name, und damit fiel jeder Sonstiges-Verbraucher aus der
        # Stunden-Kategorisierung: das Feld, das die Zuordnungsfläche
        # tatsächlich schreibt, traf keinen einzigen Zweig.
        verbrauch_felder = SONSTIGES_VERBRAUCH_FELDER
        if feld == "erzeugung_kwh" or (feld in verbrauch_felder and kategorie == "erzeuger"):
            return "erzeugung_sonstiges"
        if feld in verbrauch_felder:
            return "verbrauch_sonstiges"
    return None
