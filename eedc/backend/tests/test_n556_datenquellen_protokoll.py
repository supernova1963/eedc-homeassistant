"""N-556 — Die Datenquellen-Fläche protokolliert jede Zuordnung.

Die Alt-Route `/api/sensor-mapping` schrieb bis N-241 (`f8484dd0`, 13.08.2026)
beim Speichern und Löschen eine Zeile `kategorie="sensor_mapping"`. Die Fläche
`api/routes/datenquellen.py`, die sie ablöste, schrieb auf `sensor_mapping` und
protokollierte nichts — die Protokolle-Seite bot den Filter weiter an, er blieb leer.

Geprüft wird die **Wirkung** an den Schreibwegen der Fläche:

* Zuordnen, Wegschalten, Vorzeichen umkehren, Energie-Vorschläge übernehmen
  erzeugen je **eine** Zeile mit Anlage, Feld und alt → neu;
* die Zeile liegt in der **Sitzung des Aufrufers** (N-532) — ein Rollback nimmt
  sie mit;
* die Materialisierung im Lesepfad (`GET /felder`, B8-2) bleibt **still**: sie
  schreibt fest, was ohnehin gilt, und ist keine Handlung des Anwenders.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import select

from backend.api.routes import datenquellen as dq
from backend.api.routes.datenquellen import (
    EnergyUebernahmeRequest,
    InvertSetRequest,
    QuelleSetRequest,
    get_datenquellen_felder,
    set_feld_invert,
    set_feld_quelle,
    uebernehme_energy_vorschlaege,
)
from backend.models.activity_log import ActivityLog
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.tests import factories


async def _anlage(db, sensor_mapping: dict | None = None) -> Anlage:
    a = Anlage(anlagenname="Protokoll", leistung_kwp=10.0, sensor_mapping=sensor_mapping or {})
    db.add(a)
    await db.flush()
    db.add(Investition(
        anlage_id=a.id, typ="pv-module", bezeichnung="Süd",
        anschaffungsdatum=date(2020, 1, 1), leistung_kwp=10.0,
    ))
    await db.flush()
    return a


async def _zeilen(db, anlage_id: int) -> list[ActivityLog]:
    return list((await db.execute(
        select(ActivityLog).where(
            ActivityLog.kategorie == "sensor_mapping", ActivityLog.anlage_id == anlage_id,
        ).order_by(ActivityLog.id)
    )).scalars().all())


async def test_zuordnen_protokolliert_feld_und_alt_neu(db):
    a = await _anlage(db)
    await set_feld_quelle(
        a.id, "basis_energy_netzbezug_kwh",
        QuelleSetRequest(quelle="ha_connector", entity_id="sensor.netz"), db,
    )
    zeilen = await _zeilen(db, a.id)
    assert len(zeilen) == 1
    z = zeilen[0]
    assert z.aktion == "Datenquelle zugeordnet"
    assert z.details.startswith("Protokoll · ")
    assert "Standard (MQTT-Inbound) → HA-Sensor sensor.netz" in z.details
    assert z.details_json["field_id"] == "basis_energy_netzbezug_kwh"


async def test_wegschalten_protokolliert(db):
    a = await _anlage(db)
    await set_feld_quelle(
        a.id, "basis_energy_netzbezug_kwh",
        QuelleSetRequest(quelle="ha_connector", entity_id="sensor.netz"), db,
    )
    await set_feld_quelle(
        a.id, "basis_energy_netzbezug_kwh", QuelleSetRequest(quelle="keine"), db,
    )
    zeilen = await _zeilen(db, a.id)
    assert [z.aktion for z in zeilen] == ["Datenquelle zugeordnet", "Datenquelle entfernt"]
    assert zeilen[1].details.endswith("HA-Sensor sensor.netz → keine Quelle")


async def test_invertieren_protokolliert(db):
    a = await _anlage(db)
    await set_feld_invert(a.id, "inv_live_1_leistung_w", InvertSetRequest(invertieren=True), db)
    zeilen = await _zeilen(db, a.id)
    assert len(zeilen) == 1
    assert zeilen[0].aktion == "Vorzeichen umgekehrt"
    assert zeilen[0].details.endswith("normal → umgekehrt")


async def test_uebernehmen_protokolliert_eine_zeile_je_uebernahme(db, monkeypatch):
    a = await _anlage(db)

    async def fake_resolve(_db):
        return ("http://ha/api", "token", "ha_app")
    monkeypatch.setattr(dq, "_resolve_ha", fake_resolve)

    await uebernehme_energy_vorschlaege(a.id, EnergyUebernahmeRequest(
        basis={"einspeisung": "sensor.einsp", "netzbezug": "sensor.netz"},
    ), db)
    zeilen = await _zeilen(db, a.id)
    assert len(zeilen) == 1
    assert zeilen[0].aktion == "Energie-Dashboard-Vorschläge übernommen (2)"
    assert "→ HA-Sensor sensor.einsp" in zeilen[0].details
    assert "→ HA-Sensor sensor.netz" in zeilen[0].details


async def test_leere_uebernahme_ohne_zeile(db, monkeypatch):
    a = await _anlage(db)

    async def fake_resolve(_db):
        return ("http://ha/api", "token", "ha_app")
    monkeypatch.setattr(dq, "_resolve_ha", fake_resolve)
    await uebernehme_energy_vorschlaege(a.id, EnergyUebernahmeRequest(), db)
    assert await _zeilen(db, a.id) == []


async def test_materialisierung_im_lesepfad_bleibt_still(db):
    """B8-2 schreibt beim `GET /felder` fest, was ohnehin gilt — keine Handlung, keine Zeile."""
    a = await factories.anlage_mit_pv(db, {
        "investitionen": {
            "1": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}}},
        },
    })
    await get_datenquellen_felder(a.id, db)
    assert (a.sensor_mapping or {}).get("quellen"), "Vorbedingung: die Materialisierung hat geschrieben"
    assert await _zeilen(db, a.id) == []


async def test_protokollzeile_liegt_in_der_sitzung_des_aufrufers(db, monkeypatch):
    """N-532: ohne `db=` öffnete `log_activity` eine eigene Verbindung. In der Sitzung
    des Aufrufers ist die Zeile vor dem Commit schon sichtbar und geht mit ihm."""
    a = await _anlage(db)
    gesehen: list[int] = []
    echt_commit = db.commit

    async def commit_mit_blick():
        gesehen.append(len(await _zeilen(db, a.id)))
        await echt_commit()
    monkeypatch.setattr(db, "commit", commit_mit_blick)
    await set_feld_quelle(
        a.id, "basis_energy_netzbezug_kwh",
        QuelleSetRequest(quelle="ha_connector", entity_id="sensor.netz"), db,
    )
    assert gesehen and gesehen[0] == 1
