"""
Datenquellen P2 (D2, #343) — Wizard-Übernahme der Energy-Vorschläge +
Remote-Prefs-Parsing.

Deckt: (1) `uebernehme_energy_vorschlaege` schreibt NUR registry-gültige
Feld-IDs in `sensor_mapping.quellen` (HA-Transport der aktiven Verbindung),
(2) `_suggestions_aus_prefs` parst das WS-`energy/get_prefs`-Result (dieselbe
Form wie der `data`-Teil der core.energy-Datei — gemeinsames Parsing).
"""

from datetime import date

import pytest
from sqlalchemy import select

from backend.api.routes import datenquellen as dq
from backend.api.routes.datenquellen import (
    EnergyUebernahmeRequest,
    uebernehme_energy_vorschlaege,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services.ha_energy_service import _suggestions_aus_prefs


async def _anlage_mit_wallbox(db):
    anlage = Anlage(anlagenname="P2", leistung_kwp=10.0, standort_plz="80331")
    db.add(anlage)
    await db.flush()
    wb = Investition(
        anlage_id=anlage.id, typ="wallbox", bezeichnung="Wallbox",
        anschaffungsdatum=date(2024, 1, 1),
    )
    db.add(wb)
    await db.flush()
    return anlage, wb


async def test_uebernahme_schreibt_nur_gueltige_feld_ids(db, monkeypatch):
    anlage, wb = await _anlage_mit_wallbox(db)

    async def fake_resolve(_db):
        return ("http://ha/api", "token", "ha_app")
    monkeypatch.setattr(dq, "_resolve_ha", fake_resolve)

    body = EnergyUebernahmeRequest(
        basis={"einspeisung": "sensor.einsp", "netzbezug": "sensor.netz", "unbekannt": "sensor.x"},
        investitionen={
            str(wb.id): {"ladung_kwh": "sensor.wb_energy", "quatsch_kwh": "sensor.y"},
            "999": {"ladung_kwh": "sensor.fremd"},  # fremde/nicht existente Investition
        },
    )
    result = await uebernehme_energy_vorschlaege(anlage.id, body, db)

    assert result["gespeichert"] is True
    felder = set(result["felder"])
    assert felder == {
        "basis_energy_einspeisung_kwh",
        "basis_energy_netzbezug_kwh",
        f"inv_energy_{wb.id}_ladung_kwh",
    }

    frisch = (await db.execute(select(Anlage).where(Anlage.id == anlage.id))).scalar_one()
    quellen = (frisch.sensor_mapping or {}).get("quellen") or {}
    assert quellen["basis_energy_einspeisung_kwh"] == {"quelle": "ha_app", "entity_id": "sensor.einsp"}
    assert quellen[f"inv_energy_{wb.id}_ladung_kwh"] == {"quelle": "ha_app", "entity_id": "sensor.wb_energy"}
    assert "basis_energy_unbekannt" not in str(quellen)


async def test_uebernahme_ohne_ha_verbindung_400(db, monkeypatch):
    anlage, _ = await _anlage_mit_wallbox(db)

    async def fake_resolve(_db):
        return (None, None, None)
    monkeypatch.setattr(dq, "_resolve_ha", fake_resolve)

    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        await uebernehme_energy_vorschlaege(
            anlage.id, EnergyUebernahmeRequest(basis={"einspeisung": "sensor.x"}), db
        )
    assert e.value.status_code == 400


def test_suggestions_aus_prefs_parst_ws_result():
    prefs = {
        "energy_sources": [
            {"type": "grid",
             "flow_from": [{"stat_energy_from": "sensor.netzbezug"}],
             "flow_to": [{"stat_energy_to": "sensor.einspeisung"}]},
            {"type": "solar", "stat_energy_from": "sensor.pv"},
            {"type": "battery", "stat_energy_to": "sensor.bat_in", "stat_energy_from": "sensor.bat_out"},
        ],
        "device_consumption": [
            {"stat_consumption": "sensor.wallbox_energy", "name": "Wallbox Garage"},
        ],
    }
    s = _suggestions_aus_prefs(prefs)
    assert s.available is True
    assert {(e.feld, e.entity_id) for e in s.energy_sources} == {
        ("netzbezug", "sensor.netzbezug"),
        ("einspeisung", "sensor.einspeisung"),
        ("pv_gesamt", "sensor.pv"),
    }
    assert s.battery is not None and s.battery.ladung_entity == "sensor.bat_in"
    assert s.device_consumption[0].suggested_inv_typ == "wallbox"
