"""HA-Abgleich des Diagnose-Pakets v4 — lesend, je Spiegel-Abschnitt wie der Nachtlauf (Konzept Q2, Bauplan §3.7, G4, K9).

Fixtures ``ha``/``datei`` und Datenstand wie ``test_kanal_nachfuellen.py`` (HA-Recorder-Schema in-memory, Datei-Datenbank mit
eigener Sitzung je Block); der Spiegel entsteht über ``nachfuellen_spiegel``. Keine Probe liest die Uhr.

Schwesterdateien: test_diagnose_paket.py, test_diagnose_paket_auszug.py, test_kanal_konsistenz.py.
"""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta

from sqlalchemy import select, text, update

from backend.models.anlage import Anlage
from backend.models.kanal import FAMILIE_SPIEGEL, Kanal, KanalQuelle
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401 — Tabelle im Schema der Datei
from backend.services.diagnose_paket import ha_abgleich as hab
from backend.services.kanal import konsistenz
from backend.services.kanal.nachfuellen import nachfuellen_spiegel
from backend.tests.test_kanal_nachfuellen import JETZT, ZEIT, _ts, datei, ha  # noqa: F401 — Fixtures

_EINSP_MID = 1          # sensor.einsp ist der erste Sensor der Fixture `ha`


def _verschiebe(svc, mid: int, ab_ts: int, um: float) -> None:
    with svc._engine.begin() as conn:
        conn.execute(text("UPDATE statistics SET sum = sum + :um WHERE metadata_id = :m AND start_ts >= :t"),
                     {"um": um, "m": mid, "t": ab_ts})


async def _gespiegelt(ha, datei):  # noqa: F811
    svc, _ = ha
    sitzungen, pfad, aid, _gid = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    return svc, sitzungen, pfad, aid


def _je_key(erg: dict) -> dict:
    return {a["kanal_key"]: a for a in erg["abschnitte"]}


def _statistik(pfad: str) -> list:
    con = sqlite3.connect(pfad)
    try:
        return con.execute("SELECT * FROM kanal_statistik ORDER BY kanal_id, start_ts").fetchall()
    finally:
        con.close()


async def test_g4_spiegel_gleich_ha(ha, datei):  # noqa: F811
    svc, sitzungen, _p, aid = await _gespiegelt(ha, datei)
    erg = await hab.ha_abgleich(sitzungen, aid, ha_svc=svc)
    assert (erg["verfuegbar"], erg["grund"], erg["status"]) == (True, None, "ok")
    assert len(erg["abschnitte"]) == 3
    for a in erg["abschnitte"]:
        assert a["gleich"] is True and a["erste_abweichung"] is None and a["ha_zeilen"] == [], a["kanal_key"]
        assert a["zeilen_spiegel"] > 0 and a["dauer_ms"] is not None


async def test_g4_versatz_ab_t_hoechstens_744(ha, datei):  # noqa: F811
    svc, sitzungen, _p, aid = await _gespiegelt(ha, datei)
    t = _ts(ZEIT + timedelta(days=3, hours=5))
    _verschiebe(svc, _EINSP_MID, t, -480.0)
    a = _je_key(await hab.ha_abgleich(sitzungen, aid, ha_svc=svc))["basis:einspeisung"]
    assert a["gleich"] is False and a["erste_abweichung"] == t
    # Fenster 744 Stunden ab t; darin fehlen die 48 Stunden der Fixture-Lücke ohne HA-Zeile. Die Fixture schreitet in
    # naiven Ortsstunden: liegt im Fenster ein Wechsel auf Winterzeit (Pacific/Auckland, 5.4.2026), fehlt ihr dort eine
    # weitere Stunde — die Erwartung zählt deshalb die HA-Zeilen der Fixture im Fenster (CI Auckland, v4.3.1).
    erwartet = sum(1 for ts in ha[1]["sensor.einsp"] if t <= ts < t + hab.HA_ZEILEN_MAX * 3600)
    assert hab.HA_ZEILEN_MAX == 744 and erwartet in (744 - 48, 744 - 49)
    assert len(a["ha_zeilen"]) == erwartet
    assert int(a["ha_zeilen"][0]["start_ts"]) == t
    assert int(a["ha_zeilen"][-1]["start_ts"]) == t + 743 * 3600


class _HaWeg:
    is_available = False


async def test_g4_ha_weg_verfuegbar_false_paket_vollstaendig(ha, datei, tmp_path, monkeypatch):  # noqa: F811
    import json
    import zipfile

    from backend.services.diagnose_paket import ablage, paket

    _svc, sitzungen, pfad, aid = await _gespiegelt(ha, datei)
    erg = await hab.ha_abgleich(sitzungen, aid, ha_svc=_HaWeg())
    assert (erg["verfuegbar"], erg["grund"], erg["abschnitte"]) == (False, "ha_nicht_erreichbar", [])
    from backend.services.diagnose_paket.register import MIGRATIONS_DDL

    con = sqlite3.connect(pfad)
    con.execute(MIGRATIONS_DDL)
    con.commit()
    con.close()
    monkeypatch.setattr(ablage, "VERZEICHNIS", tmp_path / "ablage")
    felder = await paket.bereitstellen(aid, db_pfad=pfad, sitzungen=sitzungen, ha_svc=_HaWeg(),
                                       jetzt=datetime(2026, 5, 20, 12, 0))
    with zipfile.ZipFile(ablage._EINTRAEGE[aid].pfad) as zf:
        inhalt = json.loads(zf.read("inhalt.json"))
        lage = json.loads(zf.read("lage.json"))
    assert inhalt["vollstaendig"] is True and inhalt["lage"]["ha_abgleich"] == "ok"
    assert lage["ha_abgleich"]["verfuegbar"] is False
    assert {t: s for t, s in inhalt["tabellen"].items() if s["status"] != "ok"} == {}
    assert felder["inhalt"]["stundenwerte"] > 0


async def test_g4_zweimal_kanal_statistik_bitgleich(ha, datei):  # noqa: F811
    svc, sitzungen, pfad, aid = await _gespiegelt(ha, datei)
    _verschiebe(svc, _EINSP_MID, _ts(ZEIT + timedelta(days=10)), -480.0)
    vorher = _statistik(pfad)
    for _ in range(2):
        erg = await hab.ha_abgleich(sitzungen, aid, ha_svc=svc)
        assert _je_key(erg)["basis:einspeisung"]["gleich"] is False
        assert _statistik(pfad) == vorher


async def test_g4_zeitgrenze_teilergebnis(ha, datei, monkeypatch):  # noqa: F811
    svc, sitzungen, _p, aid = await _gespiegelt(ha, datei)
    echt = konsistenz.pruefe_abschnitt_lesend
    aufrufe = []

    async def _langsam(*a, **k):
        aufrufe.append(1)
        if len(aufrufe) == 2:
            await asyncio.sleep(5)
        return await echt(*a, **k)

    monkeypatch.setattr(konsistenz, "pruefe_abschnitt_lesend", _langsam)
    erg = await hab.ha_abgleich(sitzungen, aid, ha_svc=svc, zeitgrenze_s=1.0)
    assert erg["status"] == "zeitgrenze" and erg["zeitgrenze_s"] == 1.0
    gruende = [a["grund"] for a in erg["abschnitte"]]
    assert gruende == [None, "zeitgrenze", "nicht_geprueft"]
    assert erg["abschnitte"][0]["gleich"] is True


async def _quelle_setzen(sitzungen, aid: int, key: str, statistic_id: str) -> None:
    async with sitzungen() as s:
        kid = (await s.execute(select(Kanal.id).where(Kanal.anlage_id == aid, Kanal.key == key))).scalar_one()
        await s.execute(update(KanalQuelle).where(KanalQuelle.kanal_id == kid).values(statistic_id=statistic_id))


async def test_g4_grund_ha_kennt_sensor_nicht(ha, datei):  # noqa: F811
    svc, sitzungen, _p, aid = await _gespiegelt(ha, datei)
    await _quelle_setzen(sitzungen, aid, "basis:einspeisung", "sensor.gibt_es_nicht")
    a = _je_key(await hab.ha_abgleich(sitzungen, aid, ha_svc=svc))["basis:einspeisung"]
    assert (a["grund"], a["gleich"], a["entity"]) == ("ha_kennt_sensor_nicht", None, "sensor.gibt_es_nicht")


async def test_g4_grund_ha_ohne_zeilen(ha, datei):  # noqa: F811
    svc, sitzungen, _p, aid = await _gespiegelt(ha, datei)
    with svc._engine.begin() as conn:
        conn.execute(text("DELETE FROM statistics WHERE metadata_id = :m"), {"m": _EINSP_MID})
    a = _je_key(await hab.ha_abgleich(sitzungen, aid, ha_svc=svc))["basis:einspeisung"]
    assert (a["grund"], a["zeilen_ha"]) == ("ha_ohne_zeilen", 0)


async def test_g4_grund_ha_historie_gekuerzt(ha, datei):  # noqa: F811
    svc, sitzungen, _p, aid = await _gespiegelt(ha, datei)
    erste = _ts(ZEIT + timedelta(days=5))
    with svc._engine.begin() as conn:
        conn.execute(text("DELETE FROM statistics WHERE metadata_id = :m AND start_ts < :t"), {"m": _EINSP_MID, "t": erste})
    a = _je_key(await hab.ha_abgleich(sitzungen, aid, ha_svc=svc))["basis:einspeisung"]
    assert a["gekuerzt"]["ha_erste_ts"] == erste and a["gekuerzt"]["behalten"] > 0
    assert a["grund"] is None and a["gleich"] is True


async def test_g4_kein_spiegel(ha, datei):  # noqa: F811
    svc, _ = ha
    sitzungen, _p, _aid, _g = datei
    async with sitzungen() as s:
        neu = Anlage(anlagenname="Ohne Spiegel", leistung_kwp=5.0)
        s.add(neu)
        await s.flush()
        nid = neu.id
    erg = await hab.ha_abgleich(sitzungen, nid, ha_svc=svc)
    assert (erg["verfuegbar"], erg["grund"], erg["abschnitte"]) == (None, "kein_spiegel", [])


async def test_g4_zwei_abschnitte_je_eigene_entity(ha, datei):  # noqa: F811
    svc, sitzungen, _p, aid = await _gespiegelt(ha, datei)
    naht = _ts(ZEIT + timedelta(days=20))
    async with sitzungen() as s:
        kid = (await s.execute(select(Kanal.id).where(Kanal.anlage_id == aid, Kanal.key == "basis:einspeisung"))).scalar_one()
        s.add(KanalQuelle(kanal_id=kid, gueltig_ab=naht, familie=FAMILIE_SPIEGEL, statistic_id="sensor.netz_wh", offset=0.0))
    erg = await hab.ha_abgleich(sitzungen, aid, ha_svc=svc)
    teile = [a for a in erg["abschnitte"] if a["kanal_key"] == "basis:einspeisung"]
    assert [(a["entity"], a["von"], a["bis"]) for a in teile] == [("sensor.einsp", _ts(ZEIT), naht),
                                                                  ("sensor.netz_wh", naht, None)]
    assert teile[0]["gleich"] is True
