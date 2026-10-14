"""RF-23 Fall-Probe: die Zweige der Reaggregate-Vorschau, die keine bestehende Testdatei erreicht.

Gemessen am HEAD `766f4ab8` (Spur über 115 Testdateien): 15 Aufrufe in 13 Tests, aber **kein** Test erreicht
das Counter-Tagesdelta (`KUMULATIVE_COUNTER_FELDER`, Befund Bug B MartyBr 07.05.) und **keiner** hängt einen
MQTT-Zähler an die Grenzen-Tabelle (#317). Diese Fälle halten beide Teile fest — Werte, Reihenfolge, Grenzen.

* F1 Counter über HA: zwei Wärmepumpen, je Feld über beide summiert; ein Rückwärts-Stand zählt nicht (alt und
  neu), ein fehlender HA-Stand ebenso nicht.
* F2 Counter nur über MQTT (N-328b): „alt" aus den gespeicherten Ständen (der zeitlich nähere Stand im ± 5-min-
  Fenster gewinnt), „neu" bleibt leer (C2b: HA-only).
* F3 MQTT-Zähler an der Grenzen-Tabelle (#317): ein Basis-Zähler mit HA-Sensor wird von seinem MQTT-Zwilling
  nicht verdoppelt; die MQTT-Zähler kommen sortiert und ohne HA-Entity dazu.
* F4 kaputte Zuordnung: eine Investitions-Zuordnung, die kein Dict ist, und ein Gerät ohne Objekt fallen still
  heraus.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend.models.anlage import Anlage
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.snapshot.reaggregator import get_reaggregate_preview

DATUM = date(2026, 5, 22)
TAG0 = datetime.combine(DATUM, datetime.min.time())
TAG_ENDE = TAG0 + timedelta(days=1)


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def _inv(inv_id: int, typ: str):
    return SimpleNamespace(
        id=inv_id, anlage_id=0, typ=typ, parameter={}, parent_investition_id=None,
        anschaffungsdatum=None, stilllegungsdatum=None, aktiv=True,
    )


class _FakeHA:
    def __init__(self, verfuegbar: bool, werte: dict | None = None):
        self.is_available = verfuegbar
        self._werte = werte or {}
        self.aufrufe: list[tuple] = []

    def get_value_at(self, entity_id, zp, toleranz_minuten=None, als_stand=None):
        self.aufrufe.append((entity_id, zp, toleranz_minuten, als_stand))
        return self._werte.get((entity_id, zp))


async def _anlage(db, sensor_mapping: dict) -> Anlage:
    a = Anlage(anlagenname="RF23", leistung_kwp=10.0, standort_plz="10115", standort_land="DE",
               wechselrichter_hersteller="generic", sensor_mapping=sensor_mapping)
    db.add(a)
    await db.flush()
    return a


def _stand(db, anlage_id: int, sk: str, zp: datetime, wert: float) -> None:
    db.add(SensorSnapshot(anlage_id=anlage_id, sensor_key=sk, zeitpunkt=zp, wert_kwh=wert, quelle="test"))


async def _vorschau(db, anlage, invs, ha, mqtt_weit: bool = False):
    p_ha = patch("backend.services.snapshot.reaggregator.get_ha_statistics_service", return_value=ha)
    p_lts = patch("backend.services.snapshot.lts_aggregator.lts_tagestabelle", AsyncMock(return_value=None))
    p_mqtt = patch("backend.services.snapshot.reaggregator.MQTT_AKTIV_TAGE", 100000 if mqtt_weit else 7)
    with p_ha, p_lts, p_mqtt:
        return await get_reaggregate_preview(db, anlage, invs, DATUM)


async def test_f1_counter_ueber_ha_je_feld_summiert(db):
    sm = {"investitionen": {
        "1": {"felder": {"wp_starts_anzahl": _sensor("sensor.wp1_starts"),
                         "wp_betriebsstunden": _sensor("sensor.wp1_h")}},
        "2": {"felder": {"wp_starts_anzahl": _sensor("sensor.wp2_starts"),
                         "wp_betriebsstunden": _sensor("sensor.wp2_h")}},
    }}
    a = await _anlage(db, sm)
    for sk, start, ende in (("inv:1:wp_starts_anzahl", 100, 112), ("inv:2:wp_starts_anzahl", 50, 55),
                            ("inv:1:wp_betriebsstunden", 10.0, 14.6), ("inv:2:wp_betriebsstunden", 20.0, 19.0)):
        _stand(db, a.id, sk, TAG0, start)
        _stand(db, a.id, sk, TAG_ENDE, ende)
    await db.flush()
    ha = _FakeHA(True, {
        ("sensor.wp1_starts", TAG0): 100.0, ("sensor.wp1_starts", TAG_ENDE): 113.0,
        ("sensor.wp2_starts", TAG0): 50.0,                       # Ende fehlt ⇒ zählt nicht
        ("sensor.wp1_h", TAG0): 10.0, ("sensor.wp1_h", TAG_ENDE): 12.4,
        ("sensor.wp2_h", TAG0): 30.0, ("sensor.wp2_h", TAG_ENDE): 29.0,   # rückwärts ⇒ zählt nicht
    })
    invs = {"1": _inv(1, "waermepumpe"), "2": _inv(2, "waermepumpe")}
    prev = await _vorschau(db, a, invs, ha)

    assert prev["counter_tagesdelta"] == [
        {"feld": "wp_betriebsstunden", "alt": 5, "neu": 2},
        {"feld": "wp_starts_anzahl", "alt": 17, "neu": 13},
    ]
    assert prev["ha_verfuegbar"] is True
    # Je Gerät und Feld erst Start, dann Ende — in der Reihenfolge der Geräte und der Feldliste.
    assert [(e, z) for e, z, *_ in ha.aufrufe] == [
        ("sensor.wp1_starts", TAG0), ("sensor.wp1_starts", TAG_ENDE),
        ("sensor.wp1_h", TAG0), ("sensor.wp1_h", TAG_ENDE),
        ("sensor.wp2_starts", TAG0), ("sensor.wp2_starts", TAG_ENDE),
        ("sensor.wp2_h", TAG0), ("sensor.wp2_h", TAG_ENDE),
    ]
    assert {t for _, _, t, _ in ha.aufrufe} == {10}


async def test_f2_counter_nur_ueber_mqtt_alt_ja_neu_nein(db):
    a = await _anlage(db, {"investitionen": {"3": {"felder": {}}}})
    db.add(MqttEnergySnapshot(anlage_id=a.id, timestamp=TAG0, energy_key="inv/3/wp_starts_anzahl", value_kwh=7.0))
    _stand(db, a.id, "inv:3:wp_starts_anzahl", TAG0, 7.0)
    _stand(db, a.id, "inv:3:wp_starts_anzahl", TAG0 + timedelta(minutes=4), 8.0)      # der nähere Stand gewinnt
    _stand(db, a.id, "inv:3:wp_starts_anzahl", TAG_ENDE + timedelta(minutes=4), 9.4)   # Toleranz ± 5 min
    await db.flush()
    ha = _FakeHA(True)
    prev = await _vorschau(db, a, {"3": _inv(3, "waermepumpe")}, ha, mqtt_weit=True)

    assert prev["counter_tagesdelta"] == [{"feld": "wp_starts_anzahl", "alt": 2, "neu": None}]
    assert ha.aufrufe == []


async def test_f3_mqtt_zaehler_an_der_grenzen_tabelle(db):
    a = await _anlage(db, {"basis": {"netzbezug": _sensor("sensor.netz")}})
    for key in ("netzbezug_kwh", "einspeisung_kwh", "pv_gesamt_kwh"):
        db.add(MqttEnergySnapshot(anlage_id=a.id, timestamp=TAG0, energy_key=key, value_kwh=1.0))
    _stand(db, a.id, "basis:einspeisung", TAG0 + timedelta(hours=3), 4.5)
    await db.flush()
    prev = await _vorschau(db, a, {}, _FakeHA(False), mqtt_weit=True)

    keys = []
    for b in prev["boundaries"]:
        if not keys or keys[-1][0] != b["sensor_key"]:
            keys.append((b["sensor_key"], b["kategorie"]))
    assert [k for k, _ in keys] == ["basis:netzbezug", "basis:einspeisung", "basis:pv_gesamt"]
    assert len(prev["boundaries"]) == 3 * 25
    assert all(b["neu_kwh"] is None for b in prev["boundaries"])
    treffer = [b for b in prev["boundaries"] if b["alt_kwh"] is not None]
    assert [(b["sensor_key"], b["zeitpunkt"], b["alt_kwh"]) for b in treffer] == [
        ("basis:einspeisung", TAG0 + timedelta(hours=3), 4.5),
    ]


async def test_f4_kaputte_zuordnung_faellt_still_heraus(db):
    sm = {"investitionen": {
        "5": "kaputt",
        "6": {"felder": {"wp_starts_anzahl": _sensor("sensor.wp6_starts")}},
    }}
    a = await _anlage(db, sm)
    _stand(db, a.id, "inv:6:wp_starts_anzahl", TAG0, 1.0)
    _stand(db, a.id, "inv:6:wp_starts_anzahl", TAG_ENDE, 4.0)
    await db.flush()
    invs = {"5": _inv(5, "waermepumpe"), "6": _inv(6, "waermepumpe"), "7": None}
    prev = await _vorschau(db, a, invs, _FakeHA(False))

    assert prev["boundaries"] == []
    assert prev["counter_tagesdelta"] == [{"feld": "wp_starts_anzahl", "alt": 3, "neu": None}]


async def test_f5_zaehlerstand_liest_die_stand_spalte(db):
    """F-58: der Zählerstand eines Sonstiges-Zählers ist ein Stand — HA liefert ihn aus `state`, nicht aus `sum`."""
    a = await _anlage(db, {"investitionen": {"8": {"felder": {"zaehlerstand": _sensor("sensor.gas")}}}})
    ha = _FakeHA(True, {("sensor.gas", TAG0): 1000.0, ("sensor.gas", TAG_ENDE): 1003.6})
    prev = await _vorschau(db, a, {"8": _inv(8, "sonstiges")}, ha)

    assert prev["counter_tagesdelta"] == [{"feld": "zaehlerstand", "alt": None, "neu": 4}]
    assert [(e, s) for e, _, _, s in ha.aufrufe] == [("sensor.gas", True), ("sensor.gas", True)]


async def test_f6_wallbox_traegt_die_ladung_nicht_das_e_auto(db):
    """N-555 (Konzept Regel 6): trägt eine Wallbox einen Ladezähler, zeigt die Vorschau die Ladung des Autos
    nicht ein zweites Mal — dieselbe Auswahl wie der Stunden-Aggregator."""
    sm = {"investitionen": {
        "1": {"felder": {"ladung_kwh": _sensor("sensor.wb_ladung")}},
        "2": {"felder": {"ladung_kwh": _sensor("sensor.auto_ladung")}},
    }}
    a = await _anlage(db, sm)
    prev = await _vorschau(db, a, {"1": _inv(1, "wallbox"), "2": _inv(2, "e-auto")}, _FakeHA(False))

    assert sorted({b["sensor_key"] for b in prev["boundaries"]}) == ["inv:1:ladung_kwh"]
