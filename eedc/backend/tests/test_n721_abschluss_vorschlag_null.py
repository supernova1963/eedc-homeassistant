"""N-721 — Monatsabschluss-Vorschlag: eine von HA oder MQTT gemessene 0 wird vorgeschlagen (0 ist ein Wert).

**Der Fund.** Der HA-Weg des Vorschlags (`api/routes/monatsabschluss/views.py`) übernahm einen HA-Monatswert nur bei
`> 0` — Basis-Felder (`baue_basis_feld`) und Investitions-Felder (`_ergaenze_investitions_vorschlaege`, Ausnahme seit
N-555 nur die Heimlade-Mengen). Der MQTT-Weg verwarf schon eine Ebene tiefer: `mqtt_energy_history_service.py::
mqtt_monats_mengen` gab eine Menge nur bei `> 0` zurück, die N-555-Ausnahme «Heimlade-0 wird vorgeschlagen» war damit
auf dem MQTT-Weg toter Code (der N-555-Test ersetzt `mqtt_monats_deltas` durch eine Attrappe und sah es nicht).

Gemessen am HEAD `7fb9b026` (Dezember 2025, Vormonat mit Einspeisung 55, Speicher 45/40, WP-Heizenergie 900; HA
liefert für alle vier eine 0):

* kein HA-Vorschlag; der beste Vorschlag (höchste Konfidenz, den das Formular vorbelegt) ist «vormonat» mit 80:
  Einspeisung 55, Ladung 45, Entladung 40, Heizenergie 900 — Abzeichen «geschätzt» statt der gemessenen 0;
* MQTT, Stand am Monatsanfang = Stand am Monatsende: `mqtt_monats_deltas` ⇒ `{}`, kein Vorschlag.

Soll: die gemessene 0 ist der Vorschlag (HA Konfidenz 92, MQTT 91, Wortlaut «0 — kein Zuwachs»). **Ausnahme bleibt**
die PV-Erzeugung und der PV-Anteil der Ladung (`pv_erzeugung_kwh`, `ladung_pv_kwh`): eine eingefrorene Integration
ergäbe dort ebenfalls 0 und verdrängte die Verteilung bzw. sperrte die Ableitung des PV-Anteils (N-555 Regel 4).

Schwesterdateien: test_n555_fahrverbrauch_bleibt_fahrverbrauch.py (Regel 4, Heimladung), test_396_mqtt_stand_zaehler_reihe.py
(MQTT-Monatsmengen aus der Standreihe), test_n707_import_pv_null_ist_messwert.py (dieselbe Regel am Import).
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy.orm.attributes import flag_modified

from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.migrations.migrate_datenquellen_materialisieren import materialisiere_datenquellen
from backend.services.mqtt_energy_history_service import mqtt_monats_deltas
from backend.services.snapshot.keys import extract_quellen_energy
from backend.services.snapshot.writer import snapshot_anlage
from backend.tests import factories

JAHR, MONAT = 2025, 12


def _sensor(eid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": eid}


def _vorschlaege_basis(resp, feld: str) -> list[dict]:
    for f in resp.basis_felder:
        if f.feld == feld:
            return [v if isinstance(v, dict) else v.model_dump() for v in f.vorschlaege]
    return []


def _vorschlaege_inv(resp, inv_id: int, feld: str) -> list[dict]:
    for inv in resp.investitionen:
        if inv.id != inv_id:
            continue
        for f in inv.felder:
            if f.feld == feld:
                return [v if isinstance(v, dict) else v.model_dump() for v in f.vorschlaege]
    return []


def _bester(vorschlaege: list[dict]):
    """Wie der Client vorbelegt (`erfassungZustand.ts::besterVorschlag`): die höchste Konfidenz, bei Gleichstand der erste."""
    if not vorschlaege:
        return None
    best = vorschlaege[0]
    for v in vorschlaege:
        if v["konfidenz"] > best["konfidenz"]:
            best = v
    return best


async def _anlage(db):
    a = await factories.anlage(db, anlagenname="Abschluss", sensor_mapping={"basis": {}, "investitionen": {}})
    sp = await factories.investition(db, a.id, "speicher", bezeichnung="Akku", parameter={"kapazitaet_kwh": 10.0})
    wp = await factories.investition(db, a.id, "waermepumpe", bezeichnung="WP")
    pv = await factories.investition(db, a.id, "pv-module", bezeichnung="Dach", leistung_kwp=10.0)
    a.sensor_mapping = {
        "basis": {"einspeisung": _sensor("sensor.einsp")},
        "investitionen": {
            str(sp.id): {"felder": {"ladung_kwh": _sensor("sensor.sp_lad"), "entladung_kwh": _sensor("sensor.sp_ent")}},
            str(wp.id): {"felder": {"heizenergie_kwh": _sensor("sensor.wp_heiz")}},
            str(pv.id): {"felder": {"pv_erzeugung_kwh": _sensor("sensor.pv")}},
        },
    }
    flag_modified(a, "sensor_mapping")
    # Der Vormonat — Quelle des «vormonat»-Vorschlags (Konfidenz 80).
    await factories.monatsdaten(db, a.id, JAHR, MONAT - 1, einspeisung_kwh=55.0, netzbezug_kwh=200.0)
    await factories.imd(db, sp.id, JAHR, MONAT - 1, {"ladung_kwh": 45.0, "entladung_kwh": 40.0})
    await factories.imd(db, wp.id, JAHR, MONAT - 1, {"heizenergie_kwh": 900.0, "stromverbrauch_kwh": 300.0})
    await factories.imd(db, pv.id, JAHR, MONAT - 1, {"pv_erzeugung_kwh": 400.0})
    await db.commit()
    return a, sp, wp, pv


@pytest.mark.asyncio
async def test_ha_null_ist_der_vorschlag_statt_des_vormonats(db, monkeypatch):
    from backend.api.routes.monatsabschluss import views

    a, sp, wp, _pv = await _anlage(db)

    async def _ha(*_a, **_k):
        return {"sensor.einsp": 0.0, "sensor.sp_lad": 0.0, "sensor.sp_ent": 0.0, "sensor.wp_heiz": 0.0, "sensor.pv": 0.0}

    monkeypatch.setattr(views, "lade_ha_statistik_werte", _ha)
    resp = await views.get_monatsabschluss(a.id, JAHR, MONAT, db=db)

    for name, vorschlaege in (
        ("Einspeisung", _vorschlaege_basis(resp, "einspeisung_kwh")),
        ("Speicher-Ladung", _vorschlaege_inv(resp, sp.id, "ladung_kwh")),
        ("Speicher-Entladung", _vorschlaege_inv(resp, sp.id, "entladung_kwh")),
        ("WP-Heizenergie", _vorschlaege_inv(resp, wp.id, "heizenergie_kwh")),
    ):
        best = _bester(vorschlaege)
        assert best is not None, name
        assert (best["quelle"], best["wert"]) == ("ha_statistics", 0.0), (name, vorschlaege)
        assert best["beschreibung"] == views.NULL_VORSCHLAG_BESCHREIBUNG, name


@pytest.mark.asyncio
async def test_ha_null_bei_pv_bleibt_ohne_vorschlag(db, monkeypatch):
    """Gegenprobe: eine HA-0 an der PV-Erzeugung verdrängt nichts (eingefrorene Integration, N-555 Regel 4)."""
    from backend.api.routes.monatsabschluss import views

    a, _sp, _wp, pv = await _anlage(db)

    async def _ha(*_a, **_k):
        return {"sensor.pv": 0.0}

    monkeypatch.setattr(views, "lade_ha_statistik_werte", _ha)
    resp = await views.get_monatsabschluss(a.id, JAHR, MONAT, db=db)
    assert not [v for v in _vorschlaege_inv(resp, pv.id, "pv_erzeugung_kwh") if v["quelle"] == "ha_statistics"]


@pytest.mark.asyncio
async def test_ha_wert_ueber_null_unveraendert(db, monkeypatch):
    from backend.api.routes.monatsabschluss import views

    a, sp, _wp, _pv = await _anlage(db)

    async def _ha(*_a, **_k):
        return {"sensor.einsp": 61.24, "sensor.sp_ent": 38.0}

    monkeypatch.setattr(views, "lade_ha_statistik_werte", _ha)
    resp = await views.get_monatsabschluss(a.id, JAHR, MONAT, db=db)
    best = _bester(_vorschlaege_basis(resp, "einspeisung_kwh"))
    assert (best["quelle"], best["wert"], best["beschreibung"]) == ("ha_statistics", 61.2, "Aus HA-Statistik (Recorder-DB)")
    best = _bester(_vorschlaege_inv(resp, sp.id, "entladung_kwh"))
    assert (best["quelle"], best["wert"]) == ("ha_statistics", 38.0)


# ── MQTT: der echte Weg über die Standreihe (keine Attrappe für `mqtt_monats_deltas`) ──────────────────────────────

MQ_JAHR, MQ_MONAT = 2026, 6


async def _mqtt_anlage(db, staende: dict[str, tuple[float, float]]):
    anlage = await factories.anlage(db, anlagenname="Standalone")
    wb = await factories.investition(db, anlage.id, "wallbox", bezeichnung="go-e Charger")
    await db.commit()
    await materialisiere_datenquellen(db)
    await db.commit()
    await db.refresh(anlage)
    von, bis = datetime(MQ_JAHR, MQ_MONAT, 1), datetime(MQ_JAHR, MQ_MONAT + 1, 1)
    keys = {k.format(wb=wb.id): v for k, v in staende.items()}
    for key, (start, ende) in keys.items():
        for ts, wert in ((von, start), (bis, ende)):
            db.add(MqttEnergySnapshot(anlage_id=anlage.id, timestamp=ts, energy_key=key, value_kwh=wert))
    await db.commit()
    for ts in (von, bis):
        await snapshot_anlage(db, anlage, zeitpunkt=ts)
    await db.commit()
    return anlage, wb, list(keys)


@pytest.mark.asyncio
async def test_mqtt_monatsmenge_null_mit_beiden_raendern_ist_ein_wert(db):
    anlage, wb, keys = await _mqtt_anlage(db, {
        "inv/{wb}/ladung_kwh": (500.0, 500.0), "einspeisung_kwh": (300.0, 300.0),
    })
    mengen = await mqtt_monats_deltas(db, anlage.id, MQ_JAHR, MQ_MONAT, keys,
                                      quellen_energy=extract_quellen_energy(anlage))
    assert mengen == {f"inv/{wb.id}/ladung_kwh": 0.0, "einspeisung_kwh": 0.0}


@pytest.mark.asyncio
async def test_mqtt_null_wird_im_abschluss_vorgeschlagen(db, monkeypatch):
    """Die N-555-Ausnahme (Heimlade-0) wirkt auf dem MQTT-Weg — und die Einspeisung-0 ebenso."""
    from backend.api.routes.monatsabschluss import views

    anlage, wb, keys = await _mqtt_anlage(db, {
        "inv/{wb}/ladung_kwh": (500.0, 500.0), "einspeisung_kwh": (300.0, 300.0),
    })
    cache = SimpleNamespace(get_energy_data=lambda _aid: {k: 1.0 for k in keys})
    monkeypatch.setattr(views, "get_mqtt_inbound_service", lambda: SimpleNamespace(cache=cache))

    async def _ha(*_a, **_k):
        return {}

    monkeypatch.setattr(views, "lade_ha_statistik_werte", _ha)
    resp = await views.get_monatsabschluss(anlage.id, MQ_JAHR, MQ_MONAT, db=db)

    mq = [v for v in _vorschlaege_inv(resp, wb.id, "ladung_kwh") if v["quelle"] == "mqtt_inbound"]
    assert [(v["wert"], v["beschreibung"]) for v in mq] == [(0.0, "0 — kein Zuwachs")]
    mq = [v for v in _vorschlaege_basis(resp, "einspeisung_kwh") if v["quelle"] == "mqtt_inbound"]
    assert [v["wert"] for v in mq] == [0.0]


@pytest.mark.asyncio
async def test_mqtt_ohne_rand_bleibt_ohne_menge(db):
    """Gegenprobe: fehlt ein Rand, heißt Abwesenheit weiter «keine Aussage»."""
    anlage, wb, keys = await _mqtt_anlage(db, {"inv/{wb}/ladung_kwh": (500.0, 500.0)})
    # Zweiter Key nur mit Stand am Monatsende.
    db.add(MqttEnergySnapshot(anlage_id=anlage.id, timestamp=datetime(MQ_JAHR, MQ_MONAT + 1, 1),
                              energy_key="einspeisung_kwh", value_kwh=300.0))
    await db.commit()
    mengen = await mqtt_monats_deltas(db, anlage.id, MQ_JAHR, MQ_MONAT, [*keys, "einspeisung_kwh"],
                                      quellen_energy=extract_quellen_energy(anlage))
    assert "einspeisung_kwh" not in mengen
