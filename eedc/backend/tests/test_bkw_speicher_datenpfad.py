"""
Paket D (Nebenfunde-Runde, 2026-07-31) — der Datenpfad des BKW-Akkus.

Ausgangslage, gemessen: `INVESTITION_FELDER["balkonkraftwerk"]` bot vier
kWh-Felder an, aber nur `pv_erzeugung_kwh` lief durch den Zähler-Pfad
(Snapshot/HA-Sensor + MQTT). Ein BKW **mit Akku** (Zendure, Anker SOLIX) konnte
seine Lade-/Entladezähler zwar zuordnen — der Monatswert kam über die
HA-Langzeitstatistik auch an —, aber Tages-, Stunden- und Live-Werte blieben
leer. `eigenverbrauch_kwh` war schlimmer als still: die MQTT-Map schickte es auf
denselben Ziel-Key wie die Erzeugung.

Dieses Modul pinnt beide Hälften des Entscheids:

* **`eigenverbrauch_kwh`** bleibt zuordenbar (der HA-Monatswert funktioniert),
  verliert aber seinen falschen MQTT-Ziel-Key.
* **`speicher_ladung_kwh`/`speicher_entladung_kwh`** werden voll angeschlossen —
  Zähler-Whitelist, MQTT-Map, Energiefluss-Kategorie **und** Komponenten-Bilanz.

Die Falle, gegen die hier vor allem geprüft wird, ist der geteilte Ziel-Key:
`bkw_{id}` steht in `PV_KOMPONENTEN_PREFIXE` und wird als *Erzeugung* summiert.
Landete die Speicher-Hälfte dort, zählte eine Entladung als PV-Erzeugung und
eine Ladung kürzte still die BKW-Erzeugung — die Klasse des BKW-Bugs vom
2026-05-19 (Rainer-PN). Deshalb `batterie_{id}` als zweiter Ziel-Key.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.core.berechnungen.energie import (
    summe_batterie_netto_kwh,
    summe_bkw_kwh,
    summe_pv_bkw_kwh,
)
from backend.services.mqtt_energy_history_service import _compute_deltas
from backend.services.snapshot.keys import (
    KUMULATIVE_ZAEHLER_FELDER,
    _categorize_counter,
    _is_kumulativ_feld,
    _mqtt_key_to_sensor_key,
)
from backend.services.snapshot.komponenten_beitraege import (
    investition_beitraege,
    investition_hourly_eintraege,
)


BKW_ID = 7
SPEICHER_ID = 9


def _bkw(inv_id=BKW_ID, hat_speicher=True):
    return SimpleNamespace(
        id=inv_id,
        typ="balkonkraftwerk",
        parameter={"hat_speicher": hat_speicher},
        parent_investition_id=None,
    )


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def _bkw_mapping_voll() -> dict:
    return {"felder": {
        "pv_erzeugung_kwh": _sensor("sensor.bkw_ertrag"),
        "speicher_ladung_kwh": _sensor("sensor.bkw_akku_geladen"),
        "speicher_entladung_kwh": _sensor("sensor.bkw_akku_entladen"),
    }}


# ─── 1. Zähler-Whitelist ────────────────────────────────────────────────────

def test_bkw_speicherfelder_sind_kumulative_zaehler():
    """Ohne das schreibt der Snapshot-Writer den zugeordneten Sensor nicht —
    `_build_counter_map` filtert namensbasiert über `_is_kumulativ_feld`."""
    assert KUMULATIVE_ZAEHLER_FELDER["balkonkraftwerk"] == (
        "pv_erzeugung_kwh", "speicher_ladung_kwh", "speicher_entladung_kwh",
    )
    assert _is_kumulativ_feld("speicher_ladung_kwh")
    assert _is_kumulativ_feld("speicher_entladung_kwh")


def test_bkw_eigenverbrauch_bleibt_ohne_zaehler_pfad():
    """Bewusst KEIN Zähler: das Feld ist die manuell/per Import gepflegte
    Verfeinerung (SoT-Begründung in `core/berechnungen/bkw_finanz.py`)."""
    assert "eigenverbrauch_kwh" not in KUMULATIVE_ZAEHLER_FELDER["balkonkraftwerk"]
    assert not _is_kumulativ_feld("eigenverbrauch_kwh")


def test_bkw_speicher_topic_wird_zu_sensor_key():
    assert _mqtt_key_to_sensor_key(f"inv/{BKW_ID}/speicher_ladung_kwh") == \
        f"inv:{BKW_ID}:speicher_ladung_kwh"
    assert _mqtt_key_to_sensor_key(f"inv/{BKW_ID}/speicher_entladung_kwh") == \
        f"inv:{BKW_ID}:speicher_entladung_kwh"
    assert _mqtt_key_to_sensor_key(f"inv/{BKW_ID}/eigenverbrauch_kwh") is None


# ─── 2. Energiefluss-Kategorie ──────────────────────────────────────────────

def test_bkw_speicher_ist_batterie_kategorie():
    """Energetisch ist ein BKW-Akku eine Batterie hinter dem Hauszähler —
    dieselbe Kategorie wie beim Typ `speicher`."""
    p = {"hat_speicher": True}
    assert _categorize_counter("speicher_ladung_kwh", "balkonkraftwerk", p) == "ladung_batterie"
    assert _categorize_counter("speicher_entladung_kwh", "balkonkraftwerk", p) == "entladung_batterie"
    # Die Erzeugung bleibt unberührt PV.
    assert _categorize_counter("pv_erzeugung_kwh", "balkonkraftwerk", p) == "pv"


def test_bkw_eigenverbrauch_bekommt_keine_kategorie():
    assert _categorize_counter("eigenverbrauch_kwh", "balkonkraftwerk", {}) is None


# ─── 3. Komponenten-Bilanz: der geteilte Ziel-Key ───────────────────────────

def test_bkw_speicher_liegt_nicht_auf_dem_erzeugungs_key():
    """Der Kern des Pakets. `bkw_{id}` wird als Erzeugung summiert — die
    Speicher-Hälfte muss auf einen eigenen Key."""
    beitraege = investition_beitraege(_bkw(), _bkw_mapping_voll())
    nach_feld = {b.feld: b for b in beitraege}

    assert nach_feld["pv_erzeugung_kwh"].target_key == f"bkw_{BKW_ID}"
    assert nach_feld["speicher_ladung_kwh"].target_key == f"batterie_{BKW_ID}"
    assert nach_feld["speicher_entladung_kwh"].target_key == f"batterie_{BKW_ID}"
    # Vorzeichen-Konvention identisch zum Typ `speicher`.
    assert nach_feld["speicher_ladung_kwh"].vorzeichen == -1
    assert nach_feld["speicher_entladung_kwh"].vorzeichen == +1


def test_bkw_speicher_faelscht_die_pv_summe_nicht():
    """Gegenprobe an den Σ-Helpern: die Erzeugungs-Summe sieht ausschließlich
    die Erzeugung, die Batterie-Summe ausschließlich den Akku."""
    komponenten_kwh = {
        f"bkw_{BKW_ID}": 10.0,        # Erzeugung
        f"batterie_{BKW_ID}": +2.0,   # netto: 6 entladen − 4 geladen
    }
    assert summe_bkw_kwh(komponenten_kwh) == 10.0
    assert summe_pv_bkw_kwh(komponenten_kwh) == 10.0
    assert summe_batterie_netto_kwh(komponenten_kwh) == 2.0


def test_bkw_akku_kollidiert_nicht_mit_echtem_speicher():
    """Beide tragen den `batterie_`-Präfix, aber die Investitions-ID trennt sie."""
    bkw = investition_beitraege(_bkw(), _bkw_mapping_voll())
    speicher = investition_beitraege(
        SimpleNamespace(id=SPEICHER_ID, typ="speicher", parameter={},
                        parent_investition_id=None),
        {"felder": {"ladung_kwh": _sensor("sensor.a"), "entladung_kwh": _sensor("sensor.b")}},
    )
    bkw_batterie_keys = {b.target_key for b in bkw if b.target_key.startswith("batterie_")}
    speicher_keys = {b.target_key for b in speicher}
    assert bkw_batterie_keys == {f"batterie_{BKW_ID}"}
    assert speicher_keys == {f"batterie_{SPEICHER_ID}"}
    assert not (bkw_batterie_keys & speicher_keys)


def test_bkw_ohne_zugeordnete_speicher_sensoren_unveraendert():
    """Regressions-Schutz: ein BKW ohne Akku-Sensoren verhält sich wie zuvor."""
    beitraege = investition_beitraege(
        _bkw(hat_speicher=False),
        {"felder": {"pv_erzeugung_kwh": _sensor("sensor.bkw")}},
    )
    assert [(b.feld, b.target_key, b.vorzeichen) for b in beitraege] == [
        ("pv_erzeugung_kwh", f"bkw_{BKW_ID}", +1),
    ]


# ─── 4. Stunden-Pfad: dieselbe Auswahl, passende Kategorie ──────────────────

def test_hourly_eintraege_spiegeln_den_tagespfad():
    """K3-Eigenschaft (Issue #298): der Stunden-Pfad ist eine treue Projektion
    des Tages-SoT — gleiche Feldmenge, jedes Feld mit gültiger Kategorie."""
    tages_felder = {b.feld for b in investition_beitraege(_bkw(), _bkw_mapping_voll())}
    hourly = investition_hourly_eintraege(_bkw(), _bkw_mapping_voll())
    assert {e.feld for e in hourly} == tages_felder
    assert {e.feld: e.kategorie for e in hourly} == {
        "pv_erzeugung_kwh": "pv",
        "speicher_ladung_kwh": "ladung_batterie",
        "speicher_entladung_kwh": "entladung_batterie",
    }


# ─── 5. MQTT-Pfad ──────────────────────────────────────────────────────────

def test_mqtt_bkw_speicher_landet_auf_batterie_keys():
    start = {
        f"inv/{BKW_ID}/speicher_ladung_kwh": 100.0,
        f"inv/{BKW_ID}/speicher_entladung_kwh": 80.0,
    }
    end = {
        f"inv/{BKW_ID}/speicher_ladung_kwh": 104.0,
        f"inv/{BKW_ID}/speicher_entladung_kwh": 83.5,
    }
    deltas = _compute_deltas(end, start, {str(BKW_ID): "balkonkraftwerk"})
    assert deltas[f"batterie_{BKW_ID}_ladung"] == 4.0
    assert deltas[f"batterie_{BKW_ID}_entladung"] == 3.5


def test_mqtt_eigenverbrauch_ueberschreibt_die_erzeugung_nicht():
    """Der gemessene Datenfehler: beide Topics zeigten auf `pv`, der zweite
    gewann. Aus 10 kWh Erzeugung wurden 4 kWh in der „Heute"-Kachel."""
    start = {
        f"inv/{BKW_ID}/pv_erzeugung_kwh": 100.0,
        f"inv/{BKW_ID}/eigenverbrauch_kwh": 40.0,
    }
    end = {
        f"inv/{BKW_ID}/pv_erzeugung_kwh": 110.0,
        f"inv/{BKW_ID}/eigenverbrauch_kwh": 44.0,
    }
    deltas = _compute_deltas(end, start, {str(BKW_ID): "balkonkraftwerk"})
    assert deltas[f"pv_{BKW_ID}"] == 10.0
    assert deltas["pv"] == 10.0
    # Der Eigenverbrauch fällt unverändert durch und wird von niemandem
    # als Erzeugung aufgesammelt.
    assert deltas[f"inv/{BKW_ID}/eigenverbrauch_kwh"] == 4.0
