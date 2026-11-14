"""Backup-Export (*Einstellungen → Backup*, «Backup als JSON herunterladen»): die Zugangsdaten der Cloud-Import-Quellen
gehören nicht in die Datei (14.11.2026, Fund-Päckchen «Beobachtungen»).

``_sanitize_connector_config`` entfernte nur ``password`` oberster Ebene; ``connector_config["cloud_import"][i]
["credentials"]`` (Viessmann ``username``/``password``, Fronius ``access_key_id``/``access_key_value``, EcoFlow
``access_key``/``secret_key``) standen im Klartext im Export, obwohl der Import ``connector_config`` gar nicht übernimmt.
Der Solcast-Schlüssel in ``sensor_mapping.solcast_config`` bleibt bewusst (der Import übernimmt ihn, Zweck Umzug).

Schwesterdateien: test_import_sensor_mapping_remap_353.py (Export → Import der Zuordnung), test_export_rundung_rest_mqtt_gleich.py.
"""
from __future__ import annotations

import json

import pytest

from backend.api.routes.import_export.json_operations import _export_anlage_full_impl, _sanitize_connector_config
from backend.models.anlage import Anlage


def _config() -> dict:
    return {
        "host": "192.168.1.5",
        "password": "geraet-geheim",
        "meter_snapshots": {"2026-11-01": 123.4},
        "cloud_import": [
            {"provider_id": "viessmann_gridbox", "credentials": {"username": "a@b.de", "password": "vi-geheim"},
             "ziel_investition_id": None, "bezeichnung": "Gridbox", "schluessel": "viessmann_gridbox:anlage"},
            {"provider_id": "fronius_solarweb",
             "credentials": {"access_key_id": "FKI", "access_key_value": "fr-geheim"},
             "ziel_investition_id": 3, "bezeichnung": None, "schluessel": "fronius_solarweb:3"},
        ],
    }


def test_credentials_je_quelle_entfernt_rest_bleibt():
    s = _sanitize_connector_config(_config())
    assert "password" not in s
    assert all("credentials" not in q for q in s["cloud_import"])
    assert [q["provider_id"] for q in s["cloud_import"]] == ["viessmann_gridbox", "fronius_solarweb"]
    assert s["cloud_import"][1]["ziel_investition_id"] == 3 and s["cloud_import"][0]["bezeichnung"] == "Gridbox"
    assert s["host"] == "192.168.1.5" and s["meter_snapshots"] == {"2026-11-01": 123.4}
    assert "geheim" not in json.dumps(s)


def test_altform_ein_objekt_und_original_unveraendert():
    roh = {"cloud_import": {"provider_id": "ecoflow_powerocean", "credentials": {"access_key": "K", "secret_key": "S"}}}
    s = _sanitize_connector_config(roh)
    assert s == {"cloud_import": {"provider_id": "ecoflow_powerocean"}}
    assert roh["cloud_import"]["credentials"] == {"access_key": "K", "secret_key": "S"}, "die Anlage selbst bleibt"
    original = _config()
    _sanitize_connector_config(original)
    assert original["cloud_import"][0]["credentials"]["password"] == "vi-geheim"
    assert _sanitize_connector_config(None) is None and _sanitize_connector_config({}) is None


@pytest.mark.asyncio
async def test_export_route_traegt_keine_zugangsdaten(db):
    anlage = Anlage(anlagenname="Export", leistung_kwp=9.9, standort_land="DE", connector_config=_config(),
                    sensor_mapping={"solcast_config": {"api_key": "sc-schluessel", "resource_ids": ["r1"]}})
    db.add(anlage)
    await db.commit()
    export = json.loads((await _export_anlage_full_impl(anlage.id, db)).body)
    text = json.dumps(export)
    assert "geheim" not in text
    assert export["anlage"]["connector_config"]["cloud_import"][0]["provider_id"] == "viessmann_gridbox"
    # bewusst: der Solcast-Schlüssel bleibt für den Umzug (der Import übernimmt ihn)
    assert export["anlage"]["sensor_mapping"]["solcast_config"]["api_key"] == "sc-schluessel"
