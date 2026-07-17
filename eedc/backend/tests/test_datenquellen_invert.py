"""
Datenquellen-V4 — VEREINHEITLICHTES Invert-Modell.

Vorzeichen-Umkehr ist eine QUELLEN-UNABHÄNGIGE Wert-Eigenschaft im Store
`sensor_mapping.invertieren = {field_id: true}`, EINMAL am Read-Endwert angewendet:
- Live-Power: finaler Pass in `_collect_values` (nach dem Quellen-Override),
- History: `apply_invert_to_history` (tagesverlauf/verbrauchsprofil/history),
- Gateway invertiert NICHT mehr im Republish-Transform (kein Doppel-Invert).

`extract_live_config` ist der EINE Trichter: es unioniert den neuen Store mit dem
Legacy-`live_invert` und liefert `basis_invert`/`inv_invert_map` an alle Consumer.
"""

from datetime import date

import pytest
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
from backend.services.live_sensor_config import extract_live_config
from backend.services.live_power_service import LivePowerService
from backend.services.live_history_service import apply_invert_to_history
from backend.services.mqtt_gateway_service import transform_payload
from backend.services.migrations.migrate_invert_vereinheitlichen import (
    migrate_invert_vereinheitlichen,
)


def _anlage(sensor_mapping: dict) -> Anlage:
    a = Anlage()
    a.id = 1
    a.anlagenname = "Test"
    a.sensor_mapping = sensor_mapping
    return a


# ─── Trichter: extract_live_config liest den neuen Store (∪ Legacy) ───────

def test_extract_live_config_liest_invert_store():
    a = _anlage({
        "basis": {"live": {"einspeisung_w": "sensor.e"}},
        "investitionen": {"2": {"live": {"leistung_w": "sensor.p"}}},
        "invertieren": {
            "basis_live_einspeisung_w": True,
            "inv_live_2_leistung_w": True,
            "basis_live_netzbezug_w": False,   # falsy → ignoriert
        },
    })
    _bl, _il, basis_invert, inv_invert = extract_live_config(a)
    assert basis_invert.get("einspeisung_w") is True
    assert "netzbezug_w" not in basis_invert
    assert inv_invert.get("2", {}).get("leistung_w") is True


def test_extract_live_config_unioniert_legacy_live_invert():
    """Legacy basis.live_invert + neuer Store → beide greifen (idempotent)."""
    a = _anlage({
        "basis": {"live": {"einspeisung_w": "sensor.e"}, "live_invert": {"einspeisung_w": True}},
        "invertieren": {"basis_live_netzbezug_w": True},
    })
    _bl, _il, basis_invert, _inv = extract_live_config(a)
    assert basis_invert.get("einspeisung_w") is True   # aus Legacy
    assert basis_invert.get("netzbezug_w") is True     # aus Store


# ─── Live-Power: EINMALIGER finaler Invert-Pass, quellen-unabhängig ───────

def test_collect_values_invert_ha_merge():
    """HA-Merge-Wert wird durch den finalen Pass genau einmal invertiert."""
    svc = LivePowerService()
    a = _anlage({})
    b, _ = svc._collect_values(
        a, {"einspeisung_w": "sensor.e"}, {}, {"sensor.e": 100.0},
        basis_invert={"einspeisung_w": True}, inv_invert_map={},
    )
    assert b["einspeisung_w"] == -100.0


def test_collect_values_invert_quellen_override_ha():
    """Regression: der Quellen-Override verschluckt den Sign NICHT mehr (finaler Pass)."""
    svc = LivePowerService()
    a = _anlage({})
    b, _ = svc._collect_values(
        a, {"einspeisung_w": "sensor.old"}, {}, {"sensor.old": 100.0, "sensor.neu": 250.0},
        basis_invert={"einspeisung_w": True}, inv_invert_map={},
        quellen_basis={"einspeisung_w": ("ha_connector", "sensor.neu", False)},
    )
    assert b["einspeisung_w"] == -250.0   # Override-Wert, einmal invertiert


def test_apply_quellen_overrides_gateway_invertiert_nicht():
    """Kein Doppel-Invert: der Quellen-Override (auch Gateway) invertiert NIE selbst
    — das Vorzeichen kommt ausschließlich aus dem finalen Store-Pass."""
    svc = LivePowerService()
    d = {}
    svc._apply_quellen_overrides(
        d, {"netzbezug_w": ("mqtt_gateway", None, False)},
        sensor_values={}, mqtt_values={"netzbezug_w": 30.0},
    )
    assert d["netzbezug_w"] == 30.0
    # HA-Override ebenfalls roh (kein Invert am Override)
    d2 = {}
    svc._apply_quellen_overrides(
        d2, {"leistung_w": ("ha_app", "sensor.x", False)},
        sensor_values={"sensor.x": 55.0}, mqtt_values={},
    )
    assert d2["leistung_w"] == 55.0


def test_collect_values_ohne_invert_unveraendert():
    """Ohne Store bleibt alles bitgleich (Symmetrie / Regression)."""
    svc = LivePowerService()
    a = _anlage({})
    b, _ = svc._collect_values(
        a, {"einspeisung_w": "sensor.e"}, {}, {"sensor.e": 100.0},
        basis_invert={}, inv_invert_map={},
        quellen_basis={"einspeisung_w": ("ha_connector", "sensor.e", False)},
    )
    assert b["einspeisung_w"] == 100.0


def test_collect_values_invert_vor_netzkombi_split():
    """Invertierter Kombi-Netzsensor splittet mit korrektem Vorzeichen."""
    svc = LivePowerService()
    a = _anlage({})
    # Roh −200 (Einspeisung), invertiert → +200 → Bezug 200
    b, _ = svc._collect_values(
        a, {"netz_kombi_w": "sensor.netz"}, {}, {"sensor.netz": -200.0},
        basis_invert={"netz_kombi_w": True}, inv_invert_map={},
    )
    assert b["netzbezug_w"] == 200.0 and b["einspeisung_w"] == 0.0


# ─── History-Pfad: apply_invert_to_history nutzt denselben Store-Trichter ──

def test_apply_invert_to_history_via_store():
    a = _anlage({
        "basis": {"live": {"einspeisung_w": "sensor.e"}},
        "invertieren": {"basis_live_einspeisung_w": True},
    })
    basis_live, inv_live_map, basis_invert, inv_invert = extract_live_config(a)
    history = {"sensor.e": [(0, 10.0), (1, -5.0)]}
    apply_invert_to_history(history, basis_live, basis_invert, inv_live_map, inv_invert)
    assert history["sensor.e"] == [(0, -10.0), (1, 5.0)]


# ─── Gateway-Transform invertiert nicht mehr (Default False) ──────────────

def test_transform_payload_kein_invert_default():
    assert transform_payload("42", "plain", None, None, 1.0, 0.0) == 42.0
    # Alt-Signatur mit invertieren=True bleibt kompatibel (Alt-Wizard-Vorschau)
    assert transform_payload("42", "plain", None, None, 1.0, 0.0, True) == -42.0


# ─── Migration: Legacy + quellen + Gateway → EIN Store ────────────────────

async def _anlage_mit_pv(db, sensor_mapping: dict) -> Anlage:
    a = Anlage(anlagenname="Test", leistung_kwp=10.0, sensor_mapping=sensor_mapping)
    db.add(a)
    await db.flush()
    inv = Investition(
        anlage_id=a.id, typ="pv-module", bezeichnung="PV",
        anschaffungsdatum=date(2020, 1, 1),
    )
    db.add(inv)
    await db.flush()
    return a


@pytest.mark.asyncio
async def test_migration_faltet_alle_quellen_in_store(db):
    a = await _anlage_mit_pv(db, {
        "basis": {"live_invert": {"einspeisung_w": True}},
        "investitionen": {"1": {"live_invert": {"leistung_w": True}}},
        "quellen": {
            "basis_live_netzbezug_w": {"quelle": "ha_connector", "entity_id": "sensor.n", "invertieren": True},
        },
    })
    gw = MqttGatewayMapping(
        anlage_id=a.id, quell_topic="shellies/em/power",
        ziel_key="live/inv/1_PV/leistung_w", invertieren=True, aktiv=True,
    )
    db.add(gw)
    await db.flush()

    await migrate_invert_vereinheitlichen(db)
    store = a.sensor_mapping["invertieren"]

    # 1. Legacy live_invert (basis + inv) gefaltet
    assert store["basis_live_einspeisung_w"] is True
    assert store["inv_live_1_leistung_w"] is True
    # 2. quellen[].invertieren gefaltet + Sub-Flag entfernt
    assert store["basis_live_netzbezug_w"] is True
    assert "invertieren" not in a.sensor_mapping["quellen"]["basis_live_netzbezug_w"]
    # 3. Gateway-Invert gefaltet + Zeile invertiert nicht mehr
    assert gw.invertieren is False

    # Idempotent: zweiter Lauf ändert nichts
    store1 = dict(store)
    await migrate_invert_vereinheitlichen(db)
    assert a.sensor_mapping["invertieren"] == store1
