"""Migration `_migrate_sensor_mapping_strategien_clear` — Datenchecker-Achse A1.

Schreibt Dead-Strategie-Werte (`kwp_verteilung`/`ev_quote`/`cop_berechnung`/
`manuell`) im `anlagen.sensor_mapping`-JSON auf `keine` um. Hard-Precondition
vor der `StrategieTyp`-Enum-Reduktion (Pydantic-validiert). Idempotent.
[[project_datenchecker_konsistenz]].
"""

from __future__ import annotations

import json

from sqlalchemy import create_engine, text

from backend.core.database import _migrate_sensor_mapping_strategien_clear
from backend.api.routes.sensor_mapping import StrategieTyp


def _seed_db(mapping: dict | None):
    """In-Memory SQLite mit anlagen-Tabelle (nur sensor_mapping relevant)."""
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE anlagen ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, sensor_mapping TEXT)"
        ))
        conn.execute(
            text("INSERT INTO anlagen (id, sensor_mapping) VALUES (1, :m)"),
            {"m": json.dumps(mapping) if mapping is not None else None},
        )
    return engine


def _mapping(engine, anlage_id=1) -> dict | None:
    with engine.begin() as conn:
        raw = conn.execute(
            text("SELECT sensor_mapping FROM anlagen WHERE id = :id"),
            {"id": anlage_id},
        ).scalar_one()
    return json.loads(raw) if raw else None


_VOLL = {
    "basis": {
        "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einspeisung"},
        "netzbezug": {"strategie": "manuell"},
        "pv_gesamt": {"strategie": "keine"},
        "live": {"einspeisung_w": "sensor.live"},  # String-Map → übersprungen
    },
    "investitionen": {
        "10": {
            "felder": {
                "pv_erzeugung_kwh": {"strategie": "kwp_verteilung",
                                     "parameter": {"anteil": 0.4}},
                "heizenergie_kwh": {"strategie": "cop_berechnung",
                                    "parameter": {"cop": 3.5}},
                "ladung_netz_kwh": {"strategie": "ev_quote", "parameter": {}},
                "ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.ladung"},
            },
            "live": {"leistung_w": "sensor.leistung"},
        }
    },
    "updated_at": "2026-06-07T00:00:00",
}


def test_dead_strategien_werden_keine():
    engine = _seed_db(_VOLL)
    with engine.begin() as conn:
        _migrate_sensor_mapping_strategien_clear(conn)
    m = _mapping(engine)
    # Alle vier Dead-Werte → keine
    assert m["basis"]["netzbezug"]["strategie"] == "keine"          # manuell
    felder = m["investitionen"]["10"]["felder"]
    assert felder["pv_erzeugung_kwh"]["strategie"] == "keine"       # kwp_verteilung
    assert felder["heizenergie_kwh"]["strategie"] == "keine"        # cop_berechnung
    assert felder["ladung_netz_kwh"]["strategie"] == "keine"        # ev_quote


def test_sensor_und_keine_bleiben():
    engine = _seed_db(_VOLL)
    with engine.begin() as conn:
        _migrate_sensor_mapping_strategien_clear(conn)
    m = _mapping(engine)
    assert m["basis"]["einspeisung"]["strategie"] == "sensor"
    assert m["basis"]["einspeisung"]["sensor_id"] == "sensor.einspeisung"
    assert m["basis"]["pv_gesamt"]["strategie"] == "keine"
    assert m["investitionen"]["10"]["felder"]["ladung_kwh"]["strategie"] == "sensor"


def test_live_und_struktur_unangetastet():
    engine = _seed_db(_VOLL)
    with engine.begin() as conn:
        _migrate_sensor_mapping_strategien_clear(conn)
    m = _mapping(engine)
    assert m["basis"]["live"] == {"einspeisung_w": "sensor.live"}
    assert m["investitionen"]["10"]["live"] == {"leistung_w": "sensor.leistung"}
    assert m["updated_at"] == "2026-06-07T00:00:00"


def test_migrierte_werte_sind_enum_konform():
    """Nach Migration darf das reduzierte StrategieTyp-Enum jeden Wert parsen."""
    engine = _seed_db(_VOLL)
    with engine.begin() as conn:
        _migrate_sensor_mapping_strategien_clear(conn)
    m = _mapping(engine)
    werte = [m["basis"]["netzbezug"]["strategie"]]
    werte += [f["strategie"] for f in m["investitionen"]["10"]["felder"].values()]
    for w in werte:
        StrategieTyp(w)  # wirft ValueError bei Dead-Wert


def test_idempotent():
    engine = _seed_db(_VOLL)
    with engine.begin() as conn:
        _migrate_sensor_mapping_strategien_clear(conn)
        _migrate_sensor_mapping_strategien_clear(conn)
    m = _mapping(engine)
    assert m["investitionen"]["10"]["felder"]["pv_erzeugung_kwh"]["strategie"] == "keine"


def test_null_mapping_kein_fehler():
    engine = _seed_db(None)
    with engine.begin() as conn:
        _migrate_sensor_mapping_strategien_clear(conn)
    assert _mapping(engine) is None


def test_enum_hat_nur_zwei_werte():
    assert {s.value for s in StrategieTyp} == {"sensor", "keine"}
