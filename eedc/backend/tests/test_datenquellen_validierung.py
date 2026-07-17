"""
Datenquellen-V4 §2i — Zuordnungs-Validierung (config-basiert, diagnostisch).

Regel-Tabellen für die vier Prüfungen: Einheit (#200), state_class,
Aggregat-Redundanz (C, Engine-Vorrang), HA-Doppelmapping (#314).
"""

from backend.services.datenquellen_validierung import (
    einheit_problem,
    state_class_problem,
    finde_redundante_aggregate,
    finde_doppelmappings,
)


# ─── Einheit (Leistung↔Energie, #200) ────────────────────────────────────

def test_einheit_mismatch():
    # Energie-Sensor in Leistungs-Feld → ERROR
    assert einheit_problem("W", "kWh")["schwere"] == "error"
    # Leistungs-Sensor in Energie-Feld → WARNING
    assert einheit_problem("kWh", "W")["schwere"] == "warning"


def test_einheit_ok_und_egal():
    assert einheit_problem("W", "kW") is None      # beide Leistung (kW→W normalisiert)
    assert einheit_problem("kWh", "kWh") is None    # gleich
    assert einheit_problem("%", "°C") is None        # keine Leistung/Energie → egal
    assert einheit_problem("W", None) is None        # Sensor-Einheit unbekannt
    assert einheit_problem(None, "kWh") is None       # Feld-Einheit unbekannt


# ─── state_class (HA-Energie-Feld ohne Langzeit-Statistik) ────────────────

def test_state_class_fehlt_nur_energie():
    assert state_class_problem("kWh", None)["schwere"] == "warning"
    assert state_class_problem("kWh", "")["schwere"] == "warning"
    assert state_class_problem("kWh", "total_increasing") is None
    # Live-W braucht kein state_class (liest state direkt)
    assert state_class_problem("W", None) is None
    assert state_class_problem("%", None) is None


# ─── Aggregat-Redundanz (C, Engine-Vorrang) ──────────────────────────────

def _f(id, feld, typ, belegt):
    return {"id": id, "feld": feld, "typ": typ, "belegt": belegt}


def test_pv_gesamt_redundant_wenn_einzeln_belegt():
    felder = [
        _f("basis_energy_pv_gesamt_kwh", "pv_gesamt_kwh", "basis", True),
        _f("basis_live_pv_gesamt_w", "pv_gesamt_w", "basis", True),
        _f("inv_energy_2_pv_erzeugung_kwh", "pv_erzeugung_kwh", "pv-module", True),
    ]
    red = finde_redundante_aggregate(felder)
    assert "basis_energy_pv_gesamt_kwh" in red
    assert "basis_live_pv_gesamt_w" in red
    assert red["basis_energy_pv_gesamt_kwh"]["grund"] == "pv_aggregat"
    assert "inv_energy_2_pv_erzeugung_kwh" in red["basis_energy_pv_gesamt_kwh"]["wirksame_felder"]
    # Die Komponente selbst ist nicht redundant
    assert "inv_energy_2_pv_erzeugung_kwh" not in red


def test_pv_gesamt_allein_nicht_redundant():
    felder = [
        _f("basis_energy_pv_gesamt_kwh", "pv_gesamt_kwh", "basis", True),
        _f("inv_energy_2_pv_erzeugung_kwh", "pv_erzeugung_kwh", "pv-module", False),  # keine
    ]
    assert finde_redundante_aggregate(felder) == {}


def test_netz_kombi_redundant_wenn_split_belegt():
    felder = [
        _f("basis_live_netz_kombi_w", "netz_kombi_w", "basis", True),
        _f("basis_live_einspeisung_w", "einspeisung_w", "basis", True),
        _f("basis_live_netzbezug_w", "netzbezug_w", "basis", False),
    ]
    red = finde_redundante_aggregate(felder)
    assert red["basis_live_netz_kombi_w"]["grund"] == "netz_kombi"  # schon 1 Split reicht


def test_batterie_leistung_kein_pv_aggregat_konflikt():
    """`leistung_w` einer Batterie ist KEINE PV-Komponente → kein Fehlalarm."""
    felder = [
        _f("basis_live_pv_gesamt_w", "pv_gesamt_w", "basis", True),
        _f("inv_live_3_leistung_w", "leistung_w", "batteriespeicher", True),
    ]
    assert finde_redundante_aggregate(felder) == {}


# ─── Doppelmapping (#314) ─────────────────────────────────────────────────

def test_doppelmapping_gleiche_entity():
    z = {
        "inv_energy_1_verbrauch_kwh": "sensor.wallbox",
        "inv_energy_2_verbrauch_kwh": "sensor.wallbox",   # dieselbe
        "basis_energy_einspeisung_kwh": "sensor.einsp",
    }
    d = finde_doppelmappings(z)
    assert "inv_energy_1_verbrauch_kwh" in d and "inv_energy_2_verbrauch_kwh" in d
    assert d["inv_energy_1_verbrauch_kwh"]["entity_id"] == "sensor.wallbox"
    assert "inv_energy_2_verbrauch_kwh" in d["inv_energy_1_verbrauch_kwh"]["andere_felder"]
    assert "basis_energy_einspeisung_kwh" not in d   # eindeutig


def test_doppelmapping_leer_bei_eindeutig():
    assert finde_doppelmappings({"a": "sensor.x", "b": "sensor.y"}) == {}
