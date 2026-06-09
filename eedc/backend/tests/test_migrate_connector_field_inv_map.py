"""Migration `_migrate_connector_field_inv_map_backfill` — Fall B (#300).

Vor v3.39.0 angelegte `connector_config` hat keine `field_inv_map`. Der
automatische Energy-Poll (`e4471ca2`) publisht PV dann nur aufs Fallback-Topic
`pv_gesamt_kwh` und Speicher/Wallbox gar nicht. Die Migration leitet die
`field_inv_map` eindeutig aus den Investitionen ab (gleiche Typ-Regeln wie der
`/connectors/mapping`-Endpoint). [[project_connector_mqtt_energie]].
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from backend.core.database import _migrate_connector_field_inv_map_backfill  # noqa: E402


def _seed_db(connector_config: dict | None, investitionen: list[tuple] | None = None):
    """In-Memory SQLite mit anlagen + investitionen (nur relevante Spalten).

    `investitionen`: Liste von (typ, aktiv) für anlage_id=1.
    """
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE anlagen ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, connector_config TEXT)"
        ))
        conn.execute(text(
            "CREATE TABLE investitionen ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, anlage_id INTEGER, "
            "typ TEXT, aktiv INTEGER)"
        ))
        conn.execute(
            text("INSERT INTO anlagen (id, connector_config) VALUES (1, :c)"),
            {"c": json.dumps(connector_config) if connector_config is not None else None},
        )
        for typ, aktiv in (investitionen or []):
            conn.execute(
                text("INSERT INTO investitionen (anlage_id, typ, aktiv) "
                     "VALUES (1, :t, :a)"),
                {"t": typ, "a": aktiv},
            )
    return engine


def _config(engine, anlage_id=1) -> dict | None:
    with engine.begin() as conn:
        raw = conn.execute(
            text("SELECT connector_config FROM anlagen WHERE id = :id"),
            {"id": anlage_id},
        ).scalar_one()
    return json.loads(raw) if raw else None


_LEGACY_CFG = {"connector_id": "fronius_solar_api", "host": "10.0.0.5",
               "username": "User", "password": "x"}


def test_eindeutige_zuordnung_wird_abgeleitet():
    engine = _seed_db(_LEGACY_CFG, [("pv-module", 1), ("speicher", 1), ("wallbox", 1)])
    inv_ids = _inv_ids(engine)
    with engine.begin() as conn:
        _migrate_connector_field_inv_map_backfill(conn)
    m = _config(engine)["field_inv_map"]
    assert m == {"pv": inv_ids["pv-module"],
                 "speicher": inv_ids["speicher"],
                 "wallbox": inv_ids["wallbox"]}


def test_balkonkraftwerk_zaehlt_als_pv():
    engine = _seed_db(_LEGACY_CFG, [("balkonkraftwerk", 1)])
    inv_ids = _inv_ids(engine)
    with engine.begin() as conn:
        _migrate_connector_field_inv_map_backfill(conn)
    assert _config(engine)["field_inv_map"] == {"pv": inv_ids["balkonkraftwerk"]}


def test_mehrdeutige_kategorie_bleibt_offen():
    """Zwei PV-Investitionen → PV-Kategorie nicht automatisch zugeordnet."""
    engine = _seed_db(_LEGACY_CFG, [("pv-module", 1), ("pv-module", 1), ("speicher", 1)])
    inv_ids_speicher = None
    with engine.begin() as conn:
        inv_ids_speicher = conn.execute(text(
            "SELECT id FROM investitionen WHERE typ='speicher'")).scalar_one()
        _migrate_connector_field_inv_map_backfill(conn)
    m = _config(engine)["field_inv_map"]
    assert "pv" not in m                       # mehrdeutig → offen
    assert m == {"speicher": inv_ids_speicher}  # Speicher eindeutig → gesetzt


def test_inaktive_investition_zaehlt_nicht():
    """aktiv=False = wie gelöscht → nicht für Ableitung herangezogen."""
    engine = _seed_db(_LEGACY_CFG, [("pv-module", 0), ("pv-module", 1)])
    inv_aktiv = None
    with engine.begin() as conn:
        inv_aktiv = conn.execute(text(
            "SELECT id FROM investitionen WHERE aktiv=1")).scalar_one()
        _migrate_connector_field_inv_map_backfill(conn)
    # Nur die aktive PV-Investition → eindeutig
    assert _config(engine)["field_inv_map"] == {"pv": inv_aktiv}


def test_bestehende_map_unangetastet():
    cfg = {**_LEGACY_CFG, "field_inv_map": {"pv": 99}}
    engine = _seed_db(cfg, [("pv-module", 1), ("speicher", 1)])
    with engine.begin() as conn:
        _migrate_connector_field_inv_map_backfill(conn)
    assert _config(engine)["field_inv_map"] == {"pv": 99}  # No-Op


def test_kein_connector_kein_eingriff():
    """connector_config ohne connector_id/host → übersprungen."""
    engine = _seed_db({"foo": "bar"}, [("pv-module", 1)])
    with engine.begin() as conn:
        _migrate_connector_field_inv_map_backfill(conn)
    assert "field_inv_map" not in _config(engine)


def test_keine_passende_investition_bleibt_absent():
    """Connector da, aber keine ableitbare Investition → Feld bleibt absent
    (späterer Boot kann erneut versuchen)."""
    engine = _seed_db(_LEGACY_CFG, [])
    with engine.begin() as conn:
        _migrate_connector_field_inv_map_backfill(conn)
    assert "field_inv_map" not in _config(engine)


def test_null_config_kein_fehler():
    engine = _seed_db(None)
    with engine.begin() as conn:
        _migrate_connector_field_inv_map_backfill(conn)
    assert _config(engine) is None


def test_idempotent():
    engine = _seed_db(_LEGACY_CFG, [("pv-module", 1)])
    inv_ids = _inv_ids(engine)
    with engine.begin() as conn:
        _migrate_connector_field_inv_map_backfill(conn)
        _migrate_connector_field_inv_map_backfill(conn)
    assert _config(engine)["field_inv_map"] == {"pv": inv_ids["pv-module"]}


def _inv_ids(engine) -> dict[str, int]:
    """typ → id für anlage_id=1 (für Tests mit eindeutigen Typen)."""
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT typ, id FROM investitionen WHERE anlage_id=1")).fetchall()
    return {typ: i for typ, i in rows}
