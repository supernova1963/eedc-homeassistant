"""
C2b — Read-Through-Resolver für den kWh-/Snapshot-Pfad (Datenquellen-V4).

Sichert die Kern-Invariante ab: Energie-Felder OHNE explizite `quellen`-
Zuordnung bleiben dem heutigen, modus-basierten Verhalten überlassen
(Regressionsschutz, bitgleich); Felder MIT Zuordnung lesen/schreiben genau die
eine gewählte Quelle (kein Merge, kein Fallback — §2d).

Deckt die vier berührten Pfade ab:
  W  — Writer `_build_counter_map`
  R1 — `get_snapshot` (Snapshot-Aggregator-Funnel)
  R2 — LTS-direkt (`resolve_energy_ha_eid`)
  R4 — Reaggregator-Preview (`resolve_energy_ha_eid`)
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.snapshot.keys import (
    _energy_field_id_to_sensor_key,
    extract_quellen_energy,
    resolve_energy_ha_eid,
    resolve_energy_snapshot_eid,
)
from backend.services.snapshot.reader import get_snapshot
from backend.services.snapshot.writer import _build_counter_map


def _anlage(sensor_mapping: dict):
    a = MagicMock()
    a.id = 1
    a.sensor_mapping = sensor_mapping
    return a


# ─── Key-Übersetzung (feld_id → sensor_key via bestehende SoT) ───────────

def test_field_id_to_sensor_key_translation():
    assert _energy_field_id_to_sensor_key("basis_energy_einspeisung_kwh") == "basis:einspeisung"
    assert _energy_field_id_to_sensor_key("basis_energy_netzbezug_kwh") == "basis:netzbezug"
    # PV-gesamt HAT seit Stufe 1 zu F-7 (2026-08-07) einen Snapshot-Counterpart.
    # Bis dahin stand hier `is None` — mit der Folge, dass eine Anlage mit EINEM
    # Summenzähler und mehreren Ausrichtungen gar keine Tages-PV bekam (Forum
    # kaba-kakao, T89667 #109). Ob der Zähler dann auch WIRKT, entscheidet die
    # Alles-oder-nichts-Regel in `komponenten_beitraege.basis_beitraege` —
    # nicht diese Übersetzung.
    assert _energy_field_id_to_sensor_key("basis_energy_pv_gesamt_kwh") == "basis:pv_gesamt"
    assert _energy_field_id_to_sensor_key("inv_energy_2_pv_erzeugung_kwh") == "inv:2:pv_erzeugung_kwh"
    assert _energy_field_id_to_sensor_key("inv_energy_5_ladung_kwh") == "inv:5:ladung_kwh"
    # Reine Counter (WP-Starts) sind ebenfalls kumulativ → übersetzt:
    assert _energy_field_id_to_sensor_key("inv_energy_7_wp_starts_anzahl") == "inv:7:wp_starts_anzahl"
    # Live-Felder gehören zu C2a → ignoriert:
    assert _energy_field_id_to_sensor_key("basis_live_netzbezug_w") is None
    assert _energy_field_id_to_sensor_key("inv_live_2_leistung_w") is None


# ─── extract_quellen_energy ──────────────────────────────────────────────

def test_extract_quellen_energy_parst_energie_ignoriert_live():
    a = _anlage({"quellen": {
        "basis_energy_einspeisung_kwh": {"quelle": "ha_connector", "entity_id": "sensor.z"},
        "inv_energy_2_pv_erzeugung_kwh": {"quelle": "mqtt_inbound_standard"},
        "inv_energy_5_ladung_kwh": {"quelle": "keine"},
        # Live-Feld → C2a, hier raus:
        "basis_live_netzbezug_w": {"quelle": "ha_app", "entity_id": "sensor.w"},
        # PV-gesamt hat seit Stufe 1 zu F-7 einen Counterpart → bleibt drin:
        "basis_energy_pv_gesamt_kwh": {"quelle": "ha_app", "entity_id": "sensor.pv"},
    }})
    qe = extract_quellen_energy(a)
    assert qe == {
        "basis:pv_gesamt": ("ha_app", "sensor.pv"),
        "basis:einspeisung": ("ha_connector", "sensor.z"),
        "inv:2:pv_erzeugung_kwh": ("mqtt_inbound_standard", None),
        "inv:5:ladung_kwh": ("keine", None),
    }


def test_extract_quellen_energy_leer_ohne_map():
    assert extract_quellen_energy(_anlage({})) == {}
    assert extract_quellen_energy(_anlage({"basis": {}})) == {}
    assert extract_quellen_energy(_anlage(None)) == {}


# ─── Entscheidungstabellen ───────────────────────────────────────────────

def test_resolve_energy_snapshot_eid():
    qe = {
        "basis:einspeisung": ("ha_connector", "sensor.z"),
        "inv:2:pv_erzeugung_kwh": ("mqtt_inbound_standard", None),
        "inv:5:ladung_kwh": ("keine", None),
    }
    # HA → Entity-Swap, behalten
    assert resolve_energy_snapshot_eid(qe, "basis:einspeisung", "sensor.alt") == ("sensor.z", True)
    # MQTT → kein HA-Read (None), aber behalten (MQTT-Fallback via sensor_key)
    assert resolve_energy_snapshot_eid(qe, "inv:2:pv_erzeugung_kwh", "sensor.alt") == (None, True)
    # keine → kein Wert
    assert resolve_energy_snapshot_eid(qe, "inv:5:ladung_kwh", "sensor.alt") == (None, False)
    # kein Eintrag → heutiges Verhalten (bitgleich)
    assert resolve_energy_snapshot_eid(qe, "inv:9:ladung_kwh", "sensor.alt") == ("sensor.alt", True)


def test_resolve_energy_ha_eid():
    qe = {
        "basis:einspeisung": ("ha_app", "sensor.z"),
        "inv:2:pv_erzeugung_kwh": ("mqtt_gateway", None),
        "inv:5:ladung_kwh": ("keine", None),
    }
    # HA → Entity-Swap, behalten
    assert resolve_energy_ha_eid(qe, "basis:einspeisung", "sensor.alt") == ("sensor.z", True)
    # MQTT → HA-Pfad überspringt (kein HA-Read für ein MQTT-Feld)
    assert resolve_energy_ha_eid(qe, "inv:2:pv_erzeugung_kwh", "sensor.alt") == (None, False)
    # keine → überspringt
    assert resolve_energy_ha_eid(qe, "inv:5:ladung_kwh", "sensor.alt") == (None, False)
    # kein Eintrag → unverändert
    assert resolve_energy_ha_eid(qe, "inv:9:ladung_kwh", "sensor.alt") == ("sensor.alt", True)


# ─── W: _build_counter_map (Writer) ──────────────────────────────────────

_SENSOR_MAPPING_BASE = {
    "basis": {
        "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einsp"},
        "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.bezug"},
    },
    "investitionen": {
        "2": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}}},
        "5": {"felder": {"ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.lad"}}},
    },
}


def test_build_counter_map_symmetrie_ohne_quellen():
    """Ohne `quellen` ist die counter_map bitgleich zur sensor_mapping-Basis."""
    ohne = _build_counter_map(_anlage(_SENSOR_MAPPING_BASE))
    mit_leer = _build_counter_map(_anlage({**_SENSOR_MAPPING_BASE, "quellen": {}}))
    assert ohne == mit_leer == {
        "basis:einspeisung": "sensor.einsp",
        "basis:netzbezug": "sensor.bezug",
        "inv:2:pv_erzeugung_kwh": "sensor.pv",
        "inv:5:ladung_kwh": "sensor.lad",
    }


def test_build_counter_map_ha_swap():
    """HA-Zuordnung → die zugeordnete Entity ersetzt die sensor_mapping-Entity."""
    cm = _build_counter_map(_anlage({**_SENSOR_MAPPING_BASE, "quellen": {
        "basis_energy_einspeisung_kwh": {"quelle": "ha_connector", "entity_id": "sensor.NEU"},
    }}))
    assert cm["basis:einspeisung"] == "sensor.NEU"
    # Rest unverändert
    assert cm["basis:netzbezug"] == "sensor.bezug"


def test_build_counter_map_ha_add_when_absent():
    """HA-Zuordnung für ein Feld OHNE sensor_mapping-Eintrag → ergänzt (neue Fläche)."""
    mapping = {"basis": {}, "investitionen": {}, "quellen": {
        "inv_energy_3_pv_erzeugung_kwh": {"quelle": "ha_app", "entity_id": "sensor.neu_pv"},
    }}
    cm = _build_counter_map(_anlage(mapping))
    assert cm == {"inv:3:pv_erzeugung_kwh": "sensor.neu_pv"}


def test_build_counter_map_mqtt_und_keine_drop():
    """MQTT- und keine-Zuordnung → aus der HA-Schreib-Map entfernt."""
    cm = _build_counter_map(_anlage({**_SENSOR_MAPPING_BASE, "quellen": {
        "inv_energy_2_pv_erzeugung_kwh": {"quelle": "mqtt_inbound_standard"},
        "inv_energy_5_ladung_kwh": {"quelle": "keine"},
    }}))
    assert "inv:2:pv_erzeugung_kwh" not in cm
    assert "inv:5:ladung_kwh" not in cm
    # Nicht-zugeordnete Basis-Felder bleiben
    assert cm["basis:einspeisung"] == "sensor.einsp"


def test_build_counter_map_ha_ohne_entity_droppt():
    """HA-Zuordnung ohne entity_id (Fehlkonfiguration) → Feld raus, kein Alt-Sensor."""
    cm = _build_counter_map(_anlage({**_SENSOR_MAPPING_BASE, "quellen": {
        "basis_energy_einspeisung_kwh": {"quelle": "ha_app"},
    }}))
    assert "basis:einspeisung" not in cm


# ─── R1: get_snapshot (DB-gestützt) ──────────────────────────────────────

async def _insert_snap(db, sensor_key, ts, wert, quelle="ha_statistics"):
    db.add(SensorSnapshot(anlage_id=1, sensor_key=sensor_key,
                          zeitpunkt=ts, wert_kwh=wert, quelle=quelle))
    await db.flush()


@pytest.mark.asyncio
async def test_get_snapshot_symmetrie_none(db):
    """quellen_energy=None → DB-Wert wird unverändert geliefert (heutiges Verhalten)."""
    ts = datetime(2026, 6, 1, 12, 0, 0)
    await _insert_snap(db, "basis:einspeisung", ts, 42.0)
    wert = await get_snapshot(db, 1, "basis:einspeisung", "sensor.egal", ts)
    assert wert == 42.0
    # Leere Map → identisch
    wert2 = await get_snapshot(db, 1, "basis:einspeisung", "sensor.egal", ts, quellen_energy={})
    assert wert2 == 42.0


@pytest.mark.asyncio
async def test_get_snapshot_keine_kurzschluss(db):
    """`keine`-Zuordnung → None, auch wenn ein DB-Altbestand existiert (§2d)."""
    ts = datetime(2026, 6, 1, 12, 0, 0)
    await _insert_snap(db, "inv:5:ladung_kwh", ts, 99.0)
    qe = {"inv:5:ladung_kwh": ("keine", None)}
    wert = await get_snapshot(db, 1, "inv:5:ladung_kwh", "sensor.alt", ts, quellen_energy=qe)
    assert wert is None


@pytest.mark.asyncio
async def test_get_snapshot_ha_swap_self_heal(db):
    """HA-Zuordnung → Self-Heal liest die ZUGEORDNETE Entity (nicht die alte)."""
    ts = datetime(2026, 6, 1, 12, 0, 0)
    # Kein DB-Snapshot → Self-Heal-Pfad. Mock HA so, dass nur die neue Entity liefert.
    ha_svc = MagicMock()
    ha_svc.is_available = True
    ha_svc.get_value_at = MagicMock(
        # `**_` deckt `als_stand` (F-58) ab: Der Leser bekommt seither die Frage
        # mit, ob ein **Stand** oder eine **Menge** geholt wird. Die Attrappe
        # spiegelt die Signatur des echten Lesers — sonst prüft sie eine
        # Aufrufform, die es nicht mehr gibt.
        side_effect=lambda eid, zp, tol, **_: 123.0 if eid == "sensor.NEU" else None
    )
    qe = {"basis:einspeisung": ("ha_connector", "sensor.NEU")}
    with patch("backend.services.snapshot.reader.get_ha_statistics_service",
               return_value=ha_svc):
        wert = await get_snapshot(db, 1, "basis:einspeisung", "sensor.ALT", ts,
                                  quellen_energy=qe)
    assert wert == 123.0
    # `als_stand=False` gehört zur Aussage: `basis:einspeisung` ist eine
    # **Menge** und bleibt es (F-58) — sonst füllte der Self-Heal-Pfad die
    # Lücke mit der falschen Größe.
    ha_svc.get_value_at.assert_called_with("sensor.NEU", ts, 10, als_stand=False)


@pytest.mark.asyncio
async def test_get_snapshot_mqtt_kein_ha_read(db):
    """MQTT-Zuordnung → HA-Self-Heal deaktiviert (sensor_id=None), MQTT-Fallback greift."""
    ts = datetime(2026, 6, 1, 12, 0, 0)
    ha_svc = MagicMock()
    ha_svc.is_available = True
    ha_svc.get_value_at = MagicMock(return_value=777.0)  # dürfte NIE gerufen werden
    qe = {"inv:2:pv_erzeugung_kwh": ("mqtt_inbound_standard", None)}
    with patch("backend.services.snapshot.reader.get_ha_statistics_service",
               return_value=ha_svc):
        wert = await get_snapshot(db, 1, "inv:2:pv_erzeugung_kwh", "sensor.ALT", ts,
                                  quellen_energy=qe)
    # Kein DB-Snapshot, kein MQTT-Snapshot → None; HA wurde NICHT als Quelle genutzt.
    assert wert is None
    ha_svc.get_value_at.assert_not_called()


# ─── R3: get_tages_kwh (Live-Heute/Gestern, kWh-Sensor-Zweig) ────────────

@pytest.mark.asyncio
async def test_get_tages_kwh_honoriert_energie_quelle(monkeypatch):
    """Die kWh-Sensoren in get_tages_kwh SIND die Energie-Quellen-Sensoren →
    HA-Override tauscht die angefragte Entity, `keine` lässt den kWh-Sensor weg."""
    from backend.services import live_history_service as L

    captured: dict = {}

    async def fake_hist(entity_ids, start, end):
        captured["ids"] = set(entity_ids)
        return ({}, {})

    monkeypatch.setattr(L, "get_history_normalized", fake_hist)

    a = MagicMock()
    a.id = 1
    a.sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einsp_alt"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.bezug"},
        },
        "investitionen": {},
        "quellen": {
            "basis_energy_einspeisung_kwh": {"quelle": "ha_connector",
                                             "entity_id": "sensor.einsp_NEU"},
            "basis_energy_netzbezug_kwh": {"quelle": "keine"},
        },
    }
    await L.get_tages_kwh(a, db=MagicMock(), tage_zurueck=1, inv_types={})

    # HA-Override: die zugeordnete Entity wird angefragt, nicht die sensor_mapping-Entity
    assert "sensor.einsp_NEU" in captured["ids"]
    assert "sensor.einsp_alt" not in captured["ids"]
    # keine: der netzbezug-kWh-Sensor wird NICHT angefragt
    assert "sensor.bezug" not in captured["ids"]
