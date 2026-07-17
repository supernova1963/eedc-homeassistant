"""
C2a — Read-Through-Resolver für die Live-W-Pipeline (Datenquellen-V4).

Sichert die Kern-Invariante ab: Felder OHNE explizite `quellen`-Zuordnung bleiben
dem heutigen Merge überlassen (Regressionsschutz für MQTT-only-Anlagen); Felder MIT
Zuordnung lesen genau die eine gewählte Quelle (kein Merge/Fallback).
"""

from backend.models.anlage import Anlage
from backend.services.live_sensor_config import extract_quellen_live
from backend.services.live_power_service import LivePowerService


def _anlage(quellen: dict) -> Anlage:
    a = Anlage()
    a.id = 1
    a.anlagenname = "Test"
    a.sensor_mapping = {"quellen": quellen}
    return a


def test_extract_quellen_live_parst_basis_und_inv_ignoriert_energy():
    a = _anlage({
        "basis_live_einspeisung_w": {"quelle": "ha_connector", "entity_id": "sensor.e"},
        "basis_live_netzbezug_w": {"quelle": "keine"},
        "inv_live_2_soc": {"quelle": "ha_app", "entity_id": "sensor.soc"},
        "inv_live_2_leistung_w": {"quelle": "mqtt_inbound_standard"},
        # Energie-Felder gehören zu C2b → hier ignoriert:
        "basis_energy_einspeisung_kwh": {"quelle": "ha_connector", "entity_id": "sensor.x"},
    })
    basis_ov, inv_ov, ha = extract_quellen_live(a)

    assert basis_ov["einspeisung_w"] == ("ha_connector", "sensor.e", False)
    assert basis_ov["netzbezug_w"] == ("keine", None, False)
    assert inv_ov["2"]["soc"] == ("ha_app", "sensor.soc", False)
    assert inv_ov["2"]["leistung_w"] == ("mqtt_inbound_standard", None, False)
    # Nur HA-Zuordnungen MIT entity_id werden gelesen; Energie-Feld ist raus.
    assert ha == {"sensor.e", "sensor.soc"}
    assert "einspeisung_kwh" not in basis_ov


def test_extract_quellen_live_leer_ohne_map():
    a = Anlage()
    a.sensor_mapping = {}
    assert extract_quellen_live(a) == ({}, {}, set())


def test_resolve_quelle_value():
    r = LivePowerService._resolve_quelle_value
    sv = {"sensor.e": 42.0}
    assert r("ha_connector", "sensor.e", sv, None) == 42.0
    assert r("ha_app", "sensor.fehlt", sv, None) is None   # HA ohne Wert → None
    assert r("mqtt_inbound_standard", None, sv, 7.0) == 7.0
    assert r("mqtt_gateway", None, sv, 3.0) == 3.0          # Gateway fließt über Inbound
    assert r("keine", None, sv, 9.0) is None                # kein Fallback


def test_collect_values_leere_quellen_identisch_zum_merge():
    """Read-Through: ohne Zuordnung ist das Ergebnis bitgleich zum heutigen Merge."""
    svc = LivePowerService()
    a = _anlage({})
    basis_live = {"einspeisung_w": "sensor.old"}
    sensor_values = {"sensor.old": 100.0}

    b_ohne, i_ohne = svc._collect_values(a, basis_live, {}, sensor_values, {}, {})
    b_mit, i_mit = svc._collect_values(a, basis_live, {}, sensor_values, {}, {}, None, None)

    assert b_ohne == b_mit == {"einspeisung_w": 100.0}
    assert i_ohne == i_mit == {}


def test_collect_values_ha_override_ersetzt_merge():
    svc = LivePowerService()
    a = _anlage({})
    basis_live = {"einspeisung_w": "sensor.old"}
    sensor_values = {"sensor.old": 100.0, "sensor.neu": 250.0}

    b, _ = svc._collect_values(
        a, basis_live, {}, sensor_values, {}, {},
        quellen_basis={"einspeisung_w": ("ha_connector", "sensor.neu")},
    )
    assert b["einspeisung_w"] == 250.0


def test_collect_values_keine_entfernt_feld():
    svc = LivePowerService()
    a = _anlage({})
    basis_live = {"einspeisung_w": "sensor.old"}
    sensor_values = {"sensor.old": 100.0}

    b, _ = svc._collect_values(
        a, basis_live, {}, sensor_values, {}, {},
        quellen_basis={"einspeisung_w": ("keine", None)},
    )
    assert "einspeisung_w" not in b


def test_collect_values_inv_override():
    svc = LivePowerService()
    a = _anlage({})
    inv_live_map = {"2": {"leistung_w": "sensor.old"}}
    sensor_values = {"sensor.old": 500.0, "sensor.neu": 800.0}

    b, inv = svc._collect_values(
        a, {}, inv_live_map, sensor_values, {}, {},
        quellen_inv={"2": {"leistung_w": ("ha_app", "sensor.neu")}},
    )
    assert inv["2"]["leistung_w"] == 800.0
