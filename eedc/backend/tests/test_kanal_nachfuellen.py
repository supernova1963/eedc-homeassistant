"""Proben Nachfüllen Spiegel, Neu-Laden und Auslöser (HA-Bauform E2, Auftrag Punkte 1 und 3).

Gegen die HA-Langzeitstatistik im echten Recorder-Schema (``ha_lts_helfer``) und eine Datei-Datenbank
(``pv_achse_matrix._neue_db``) — der Lauf öffnet je Block eine eigene Sitzung, und die Probe „kein
HA-Abruf in einer offenen Schreib-Transaktion" braucht eine zweite, echte Verbindung auf dieselbe Datei.

Die Zeit steht fest (``ZEIT``, ``JETZT``) — keine Probe liest die Uhr.

Schwesterdateien: test_kanal_spiegel.py, test_kanal_konsistenz.py, test_kanal_symmetrie.py, test_kanal_bestand_unberuehrt.py.
"""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import time as _zeit
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm.attributes import flag_modified

from backend.models.activity_log import ActivityLog
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import (
    FAMILIE_BESTAND,
    FAMILIE_MITSCHRIFT,
    FAMILIE_SPIEGEL,
    Kanal,
    KanalNachfuellung,
    KanalQuelle,
    KanalStatistik,
)
from backend.services.kanal.nachfuellen import (
    nachfuellen_anlage,
    nachfuellen_nach_dem_start,
    nachfuellen_spiegel,
    neu_spiegeln,
)
from backend.services.kanal.schreiber import schreibe_spiegel
from backend.tests import ha_lts_helfer
from backend.tests import pv_achse_matrix as mx

ZEIT = datetime(2026, 4, 1, 0)           # HA-Historie beginnt hier
TAGE = 40
JETZT = ZEIT + timedelta(days=TAGE, minutes=5)
LUECKE = range(24 * 10, 24 * 12)         # zwei Tage ohne HA-Zeile (über einen Block von 24 h hinaus)


def _ts(dt: datetime) -> int:
    return int(_zeit.mktime(dt.timetuple()))


def _s(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def _reihe(svc, sid, unit, *, start=500.0, rate=1.25, stand=False, has_sum=True, mean=False, luecke=()):
    mid = ha_lts_helfer.sensor(svc, sid, unit, has_sum=has_sum)
    wert, zeilen = start, {}
    for h in range(TAGE * 24):
        t = ZEIT + timedelta(hours=h)
        wert += rate
        if h in luecke:
            continue
        if mean:
            ha_lts_helfer.zeile(svc, mid, t, mean=wert, min_wert=wert - 1, max_wert=wert + 1)
            zeilen[_ts(t)] = {"mean": wert, "min": wert - 1, "max": wert + 1}
        elif stand:
            ha_lts_helfer.zeile(svc, mid, t, state=wert)
            zeilen[_ts(t)] = {"state": wert, "sum": None}
        else:
            ha_lts_helfer.zeile(svc, mid, t, state=wert - 300.0, sum_wert=wert)
            zeilen[_ts(t)] = {"state": wert - 300.0, "sum": wert}
    return zeilen


@pytest.fixture
def ha():
    svc = ha_lts_helfer.mach_service(thread_sicher=True)
    reihen = {
        "sensor.einsp": _reihe(svc, "sensor.einsp", "kWh", luecke=LUECKE),
        "sensor.netz_wh": _reihe(svc, "sensor.netz_wh", "Wh", start=800_000.0, rate=900.0),
        "sensor.gas": _reihe(svc, "sensor.gas", "m³", start=1000.0, rate=0.3, stand=True, has_sum=False),
        "sensor.preis": _reihe(svc, "sensor.preis", "ct/kWh", start=20.0, rate=0.001, mean=True, has_sum=False),
    }
    return svc, reihen


@pytest.fixture
async def datei():
    """``(sitzungen, pfad, anlage_id, gas_id)`` — Datei-DB, Anlage mit Basis-Zählern, Gaszähler, Preissensor."""
    verz = tempfile.mkdtemp(prefix="eedc-kanal-nachfuellen-")
    engine, db = await mx._neue_db(f"{verz}/x.db")
    await db.close()
    macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def sitzungen():
        async with macher() as s:
            yield s
            await s.commit()

    async with sitzungen() as s:
        a = Anlage(anlagenname="Nachfüllen", leistung_kwp=10.0)
        s.add(a)
        await s.flush()
        gas = Investition(anlage_id=a.id, typ="sonstiges", bezeichnung="Gas",
                          parameter={"kategorie": "zaehler", "zaehler_einheit": "m³"})
        s.add(gas)
        await s.flush()
        a.sensor_mapping = {
            "basis": {"einspeisung": _s("sensor.einsp"), "netzbezug": _s("sensor.netz_wh"),
                      "strompreis": _s("sensor.preis")},
            "investitionen": {str(gas.id): {"felder": {"zaehlerstand": _s("sensor.gas")}}},
        }
        flag_modified(a, "sensor_mapping")
        aid, gid = a.id, gas.id
    try:
        yield sitzungen, f"{verz}/x.db", aid, gid
    finally:
        await engine.dispose()
        shutil.rmtree(verz, ignore_errors=True)


async def _zeilen(sitzungen, aid: int, key: str) -> dict[int, KanalStatistik]:
    async with sitzungen() as s:
        k = (await s.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key == key))).scalar_one()
        return {r.start_ts: r for r in (await s.execute(
            select(KanalStatistik).where(KanalStatistik.kanal_id == k.id))).scalars().all()}


async def _quellen(sitzungen, aid: int, key: str) -> list[KanalQuelle]:
    async with sitzungen() as s:
        k = (await s.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key == key))).scalar_one()
        return list((await s.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id)
                                     .order_by(KanalQuelle.gueltig_ab))).scalars().all())


async def _stundenlauf(sitzungen, aid, svc, zeitpunkt):
    async with sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        return await schreibe_spiegel(s, a, zeitpunkt, ha_svc=svc)


def _bis_jetzt(reihe: dict) -> dict:
    grenze = _ts(JETZT.replace(minute=0) - timedelta(hours=1))
    return {ts: w for ts, w in reihe.items() if ts <= grenze}


async def test_nachfuellen_schreibt_die_ganze_historie_woertlich(ha, datei):
    """Der Stundenlauf hat nur die letzte Stunde; das Nachfüllen holt alles davor — ``sum``/``state``
    wörtlich (Wh → kWh wie der Stundenlauf), Stand roh, Mittelwert mit ``min``/``max``, HA-Lücke bleibt
    Lücke. Die erste Quelle gilt jetzt ab HAs erster Stunde, ``offset`` 0."""
    svc, reihen = ha
    sitzungen, _pfad, aid, gid = datei
    await _stundenlauf(sitzungen, aid, svc, JETZT.replace(minute=0))
    erg = await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc, block_stunden=24)
    assert erg.fehler == 0 and erg.kanaele == 4 and erg.gefuellt == 4
    assert erg.bloecke > 4 * 30, erg.bloecke                     # wirklich in Blöcken

    einsp = await _zeilen(sitzungen, aid, "basis:einspeisung")
    soll = _bis_jetzt(reihen["sensor.einsp"])
    assert set(einsp) == set(soll)
    assert all((einsp[t].sum, einsp[t].state, einsp[t].familie) == (w["sum"], w["state"], FAMILIE_SPIEGEL)
               for t, w in soll.items())
    assert not ({_ts(ZEIT + timedelta(hours=h)) for h in LUECKE} & set(einsp))
    netz = await _zeilen(sitzungen, aid, "basis:netzbezug")
    assert set(netz) == set(_bis_jetzt(reihen["sensor.netz_wh"]))
    assert all(netz[t].sum == pytest.approx(w["sum"] * 0.001, abs=1e-12)
               for t, w in _bis_jetzt(reihen["sensor.netz_wh"]).items())
    gas = await _zeilen(sitzungen, aid, f"inv:{gid}:zaehlerstand")
    assert all((gas[t].state, gas[t].sum) == (w["state"], None) for t, w in _bis_jetzt(reihen["sensor.gas"]).items())
    preis = await _zeilen(sitzungen, aid, "basis:strompreis")
    assert all((preis[t].mean, preis[t].min, preis[t].max) == (w["mean"], w["min"], w["max"])
               for t, w in _bis_jetzt(reihen["sensor.preis"]).items())
    for key in ("basis:einspeisung", "basis:netzbezug", f"inv:{gid}:zaehlerstand", "basis:strompreis"):
        q = await _quellen(sitzungen, aid, key)
        assert [(x.gueltig_ab, x.familie, x.offset) for x in q] == [(_ts(ZEIT), FAMILIE_SPIEGEL, 0.0)], key


async def test_nachfuellen_ohne_kanalzeile_fuellt_bis_zur_stunde_vor_jetzt(ha, datei):
    """Ohne Stundenlauf davor: der Kanal entsteht beim Nachfüllen, bis zur Stunde vor ``jetzt``; der
    Stundenlauf danach schreibt nichts doppelt."""
    svc, reihen = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    assert set(await _zeilen(sitzungen, aid, "basis:einspeisung")) == set(_bis_jetzt(reihen["sensor.einsp"]))
    assert await _stundenlauf(sitzungen, aid, svc, JETZT.replace(minute=0)) == 0


async def test_nachfuellen_ist_idempotent(ha, datei):
    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc, block_stunden=100)
    vorher = {k: (r.sum, r.state, r.mean) for k, r in (await _zeilen(sitzungen, aid, "basis:einspeisung")).items()}
    zweiter = await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc, block_stunden=100)
    assert (zweiter.zeilen, zweiter.bloecke, zweiter.gefuellt) == (0, 0, 0)
    nachher = {k: (r.sum, r.state, r.mean) for k, r in (await _zeilen(sitzungen, aid, "basis:einspeisung")).items()}
    assert nachher == vorher
    assert len(await _quellen(sitzungen, aid, "basis:einspeisung")) == 1


class _AbbruchNach:
    """HA-Dienst, der beim n-ten Block-Abruf scheitert (abgebrochener Lauf)."""

    def __init__(self, svc, n):
        self._svc, self._n, self.abrufe = svc, n, 0

    def __getattr__(self, name):
        return getattr(self._svc, name)

    def get_stundenzeilen_mehrere(self, *a, **k):
        self.abrufe += 1
        if self.abrufe == self._n:
            raise RuntimeError("Abbruch mitten im Nachfüllen")
        return self._svc.get_stundenzeilen_mehrere(*a, **k)


async def test_abgebrochener_lauf_setzt_fort_und_endet_gleich(ha, datei):
    svc, reihen = ha
    sitzungen, _pfad, aid, _ = datei
    kaputt = _AbbruchNach(svc, 5)
    erst = await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=kaputt, block_stunden=24)
    assert erst.fehler == 1
    teil = await _zeilen(sitzungen, aid, "basis:einspeisung")
    soll = _bis_jetzt(reihen["sensor.einsp"])
    assert 0 < len(teil) < len(soll)                              # Teilstand: die jüngsten Blöcke
    assert min(teil) > _ts(ZEIT)
    bis_je_abruf = []

    class _Bis:
        def __getattr__(self, name):
            return getattr(svc, name)

        def get_stundenzeilen_mehrere(self, je, ts_bis):
            bis_je_abruf.append(ts_bis)
            return svc.get_stundenzeilen_mehrere(je, ts_bis)

    zweit = await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=_Bis(), block_stunden=24)
    assert zweit.fehler == 0
    assert bis_je_abruf and max(bis_je_abruf) < min(teil)       # setzt fort — liest Vorhandenes nicht erneut
    voll = await _zeilen(sitzungen, aid, "basis:einspeisung")
    assert {t: (r.sum, r.state) for t, r in voll.items()} == {t: (w["sum"], w["state"]) for t, w in soll.items()}
    assert [(q.gueltig_ab, q.offset) for q in await _quellen(sitzungen, aid, "basis:einspeisung")] == [(_ts(ZEIT), 0.0)]


async def test_vorgeschichte_einer_anderen_quelle_wird_nicht_gefuellt(ha, datei):
    """Beginnt der Kanal mit einer Mitschrift (MQTT), gehört HAs Vorgeschichte nicht in diese Reihe."""
    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    t0 = _ts(ZEIT + timedelta(days=20))
    async with sitzungen() as s:
        k = Kanal(anlage_id=aid, key="basis:einspeisung", art="sum", einheit="kWh")
        s.add(k)
        await s.flush()
        s.add(KanalQuelle(kanal_id=k.id, gueltig_ab=t0, familie=FAMILIE_MITSCHRIFT,
                          statistic_id="basis/einspeisung", offset=0.0))
        s.add(KanalStatistik(kanal_id=k.id, start_ts=t0, sum=1.0, state=1.0, familie=FAMILIE_MITSCHRIFT))
    erg = await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    assert erg.uebersprungen["vorgeschichte_andere_quelle"] == 1
    assert list(await _zeilen(sitzungen, aid, "basis:einspeisung")) == [t0]


async def test_kein_ha_abruf_in_einer_offenen_schreib_transaktion(ha, datei):
    """Bei jedem HA-Abruf des Nachfüllens kann eine ZWEITE Verbindung sofort schreiben (``BEGIN IMMEDIATE``
    ohne Wartezeit) — das Nachfüllen hält dann keinen Schreib-Lock; der Stundenlauf wartet nie auf HA."""
    svc, _ = ha
    sitzungen, pfad, aid, _ = datei
    proben = []

    class _Pruefend:
        def __getattr__(self, name):
            return getattr(svc, name)

        def _frei(self):
            c = sqlite3.connect(pfad, timeout=0)
            try:
                c.execute("BEGIN IMMEDIATE")
                c.execute("ROLLBACK")
                proben.append(True)
            except sqlite3.OperationalError:
                proben.append(False)
            finally:
                c.close()

        def get_stundenzeilen_mehrere(self, *a, **k):
            self._frei()
            return svc.get_stundenzeilen_mehrere(*a, **k)

        def get_stundenzeile_bis(self, *a, **k):
            self._frei()
            return svc.get_stundenzeile_bis(*a, **k)

    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=_Pruefend(), block_stunden=48)
    assert len(proben) > 50 and all(proben), proben.count(False)


async def test_neu_laden_ersetzt_nur_spiegelzeilen(ha, datei):
    """HA ändert ``sum`` ab Stunde t; Neu-Laden ab t übernimmt das in die Spiegelzeilen. Eine
    Bestands- und eine Mitschriftzeile im selben Bereich (Stunden ohne Spiegelzeile) bleiben bitgleich,
    die Zeilen vor t ebenso."""
    svc, reihen = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    einsp = await _zeilen(sitzungen, aid, "basis:einspeisung")
    kid = next(iter(einsp.values())).kanal_id
    t = _ts(ZEIT + timedelta(days=30))
    t_b, t_m = _ts(ZEIT + timedelta(hours=24 * 10 + 3)), _ts(ZEIT + timedelta(hours=24 * 11 + 5))   # in der HA-Lücke
    async with sitzungen() as s:
        s.add(KanalStatistik(kanal_id=kid, start_ts=t_b, sum=7.0, state=7.0, familie=FAMILIE_BESTAND))
        s.add(KanalStatistik(kanal_id=kid, start_ts=t_m, sum=8.0, state=8.0, familie=FAMILIE_MITSCHRIFT))
    from sqlalchemy import text
    mid = 1  # sensor.einsp ist der erste Sensor der Fixture
    with svc._engine.begin() as conn:
        conn.execute(text("UPDATE statistics SET sum = sum - 480 WHERE metadata_id = :m AND start_ts >= :t"),
                     {"m": mid, "t": t})
        # dieselben zwei Stunden, die eedc als Bestand/Mitschrift führt, liefert HA jetzt auch
        conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, 1, 1)"),
                     {"m": mid, "t": t_b})
    n = await neu_spiegeln(sitzungen, kid, _ts(ZEIT + timedelta(days=5)), ha_svc=svc, block_stunden=24)
    assert n > 0
    nach = await _zeilen(sitzungen, aid, "basis:einspeisung")
    assert (nach[t_b].familie, nach[t_b].sum) == (FAMILIE_BESTAND, 7.0)
    assert (nach[t_m].familie, nach[t_m].sum) == (FAMILIE_MITSCHRIFT, 8.0)
    for ts, r in nach.items():
        if ts in (t_b, t_m):
            continue
        soll = reihen["sensor.einsp"][ts]["sum"] - (480.0 if ts >= t else 0.0)
        assert (r.sum, r.familie) == (soll, FAMILIE_SPIEGEL), ts
    assert set(nach) == set(einsp) | {t_b, t_m}


class _Abrufe:
    """HA-Dienst, der jede Abfrage mit ihrer Entity mitschreibt."""

    def __init__(self, svc):
        self._svc, self.abrufe = svc, []

    def __getattr__(self, name):
        return getattr(self._svc, name)

    def get_stundenzeile_bis(self, eid, *a, **k):
        self.abrufe.append(eid)
        return self._svc.get_stundenzeile_bis(eid, *a, **k)

    def get_stundenzeilen_mehrere(self, je, *a, **k):
        self.abrufe.extend(je)
        return self._svc.get_stundenzeilen_mehrere(je, *a, **k)


async def _marken(sitzungen) -> dict[int, tuple[str, dict]]:
    async with sitzungen() as s:
        return {m.kanal_id: (m.statistic_id, m.ergebnis) for m in (await s.execute(select(KanalNachfuellung))).scalars().all()}


async def test_marke_je_kanal_mit_fortschritt_und_ergebnis_im_protokoll(ha, datei):
    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    aus = type("Aus", (), {"is_available": False})()
    erg = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=aus)
    assert erg.uebersprungen == {"ha_nicht_erreichbar": 1} and await _marken(sitzungen) == {}   # ohne HA keine Marke
    erg = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    assert (erg.fehler, erg.kanaele, erg.markiert) == (0, 4, 4) and erg.zeilen > 0
    marken = await _marken(sitzungen)
    assert sorted(sid for sid, _e in marken.values()) == ["sensor.einsp", "sensor.gas", "sensor.netz_wh", "sensor.preis"]
    assert sum(e["zeilen"] for _sid, e in marken.values()) == erg.zeilen
    gezaehlt = _Abrufe(svc)
    dritt = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=gezaehlt)
    assert (dritt.kanaele, dritt.uebersprungen["schon_gefuellt"], gezaehlt.abrufe) == (0, 4, [])
    async with sitzungen() as s:
        log = [(x.aktion, x.erfolg, x.anlage_id) for x in (await s.execute(select(ActivityLog))).scalars().all()]
    assert log == [("Kanalstatistik: Nachfüllen aus HA begonnen", True, aid),
                   ("Kanalstatistik: Nachfüllen aus HA abgeschlossen", True, aid)]


async def test_abgebrochenes_nachfuellen_setzt_fuer_diesen_kanal_keine_marke(ha, datei):
    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    erg = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=_AbbruchNach(svc, 3), block_stunden=24)
    assert erg.fehler == 1 and erg.markiert == 3
    assert "sensor.einsp" not in {sid for sid, _e in (await _marken(sitzungen)).values()}
    async with sitzungen() as s:
        log = [(x.aktion, x.erfolg) for x in (await s.execute(select(ActivityLog))).scalars().all()]
    assert log[-1] == ("Kanalstatistik: Nachfüllen aus HA unvollständig", False)
    gezaehlt = _Abrufe(svc)
    zweit = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=gezaehlt, block_stunden=24)
    assert (zweit.fehler, zweit.kanaele) == (0, 1) and set(gezaehlt.abrufe) == {"sensor.einsp"}


async def test_spaeter_zugeordneter_sensor_bekommt_seine_vorgeschichte_ohne_neuabfrage_der_anderen(ha, datei):
    """Auftrag Master 06.10.: nach der ersten Füllung wird ein zweiter Zähler zugeordnet. Der Stundenlauf legt
    seinen Kanal an, der Anstoß danach holt seine ganze Historie — und fragt HA für KEINEN der schon
    gefüllten Kanäle (Abrufe je Entity gezählt)."""
    from backend.services.kanal.nachfuellen import nachfuellen_anstossen

    svc, reihen = ha
    sitzungen, _pfad, aid, gid = datei
    await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    neu = _reihe(svc, "sensor.ladung", "kWh", start=20.0, rate=0.5)
    async with sitzungen() as s:
        sp = Investition(anlage_id=aid, typ="speicher", bezeichnung="Akku")
        s.add(sp)
        await s.flush()
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        m = dict(a.sensor_mapping)
        m["investitionen"] = {**m["investitionen"], str(sp.id): {"felder": {"ladung_kwh": _s("sensor.ladung")}}}
        a.sensor_mapping = m
        flag_modified(a, "sensor_mapping")
        sp_id = sp.id
    await _stundenlauf(sitzungen, aid, svc, JETZT.replace(minute=0))      # legt den Kanal an: eine Zeile
    assert len(await _zeilen(sitzungen, aid, f"inv:{sp_id}:ladung_kwh")) == 1
    gezaehlt = _Abrufe(svc)
    aufgabe = nachfuellen_anstossen(sitzungen, jetzt=JETZT, ha_svc=gezaehlt)
    assert nachfuellen_anstossen(sitzungen, jetzt=JETZT, ha_svc=gezaehlt) is None    # läuft schon
    await aufgabe
    assert set(gezaehlt.abrufe) == {"sensor.ladung"}, gezaehlt.abrufe
    ladung = await _zeilen(sitzungen, aid, f"inv:{sp_id}:ladung_kwh")
    assert {t: r.sum for t, r in ladung.items()} == {t: w["sum"] for t, w in _bis_jetzt(neu).items()}
    assert "sensor.ladung" in {sid for sid, _e in (await _marken(sitzungen)).values()}
    gezaehlt.abrufe.clear()
    await nachfuellen_anstossen(sitzungen, jetzt=JETZT, ha_svc=gezaehlt)
    assert gezaehlt.abrufe == []                                           # jetzt hat auch er seine Marke


async def test_neue_quelle_eines_kanals_wird_geprueft_ohne_ha_abruf(ha, datei):
    """Sensortausch (neue ``kanal_quelle``): die Marke zeigt auf die alte Entity ⇒ der Kanal ist offen; seine
    Vorgeschichte gehört aber der alten Quelle (nichts zu füllen) — geprüft ohne HA-Abruf, Marke umgesetzt."""
    from backend.services.kanal.nachfuellen import nachfuellen_anstossen

    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT - timedelta(days=5), ha_svc=svc)
    _reihe(svc, "sensor.einsp_neu", "kWh", start=10.0, rate=2.0)
    async with sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        a.sensor_mapping = {**a.sensor_mapping, "basis": {**a.sensor_mapping["basis"], "einspeisung": _s("sensor.einsp_neu")}}
        flag_modified(a, "sensor_mapping")
    await _stundenlauf(sitzungen, aid, svc, JETZT.replace(minute=0))
    assert [q.statistic_id for q in await _quellen(sitzungen, aid, "basis:einspeisung")] == ["sensor.einsp", "sensor.einsp_neu"]
    gezaehlt = _Abrufe(svc)
    await nachfuellen_anstossen(sitzungen, jetzt=JETZT, ha_svc=gezaehlt)
    assert gezaehlt.abrufe == []
    marken = {sid: e for sid, e in (await _marken(sitzungen)).values()}
    assert marken["sensor.einsp_neu"] == {"zeilen": 0, "grund": "vorgeschichte_andere_quelle"}
    assert "sensor.einsp" not in marken


async def test_anstoss_fragt_sensoren_ohne_kanal_nicht_ab(ha, datei):
    """Ein zugeordneter Sensor, den HA nicht kennt (kein Kanal): der stündliche Anstoß fragt ihn nicht ab — nur
    der Startlauf prüft alle Zuordnungen."""
    from backend.services.kanal.nachfuellen import nachfuellen_anstossen

    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    async with sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        a.sensor_mapping = {**a.sensor_mapping, "basis": {**a.sensor_mapping["basis"], "pv_gesamt": _s("sensor.unbekannt")}}
        flag_modified(a, "sensor_mapping")
    gezaehlt = _Abrufe(svc)
    await nachfuellen_anstossen(sitzungen, jetzt=JETZT, ha_svc=gezaehlt)
    assert gezaehlt.abrufe == []
    start = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=gezaehlt)
    assert gezaehlt.abrufe == ["sensor.unbekannt"] and start.markiert == 0


async def test_sensor_ohne_statistik_startlauf_stundenlauf_anstoss_legt_keinen_kanal_an(ha, datei):
    """Lab-Durchlauf 4.1.3-rc1 (07.10.2026), Anlage 4 (Demo-Sensoren ohne HA-Statistik) — die Reihenfolge des
    Produkts: Startlauf → Stundenlauf → Anstoß. Bis dahin legte der Zähler-Spiegel (``schreiber._spiegel``) den
    Kanal an, BEVOR HA geliefert hatte; der Anstoß fand dann einen Kanal ohne Marke, fragte HA ein zweites Mal
    und protokollierte „Nachfüllen … begonnen / 0 von N gefüllt" ein zweites Mal — zurück blieben leere Kanäle
    ohne ``kanal_quelle``. Soll (wie ``_mean_spiegel`` und der Docstring von ``nachfuellen_spiegel``): ein Kanal
    entsteht erst, wenn HA für ihn liefert."""
    from backend.services.kanal.nachfuellen import nachfuellen_anstossen

    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    async with sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        a.sensor_mapping = {**a.sensor_mapping, "basis": {**a.sensor_mapping["basis"], "pv_gesamt": _s("sensor.unbekannt")}}
        flag_modified(a, "sensor_mapping")
    await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    async with sitzungen() as s:
        protokoll_vorher = len((await s.execute(select(ActivityLog))).scalars().all())
    await _stundenlauf(sitzungen, aid, svc, JETZT + timedelta(hours=1))
    async with sitzungen() as s:
        assert (await s.execute(select(Kanal).where(
            Kanal.anlage_id == aid, Kanal.key == "basis:pv_gesamt"))).scalar_one_or_none() is None
    gezaehlt = _Abrufe(svc)
    await nachfuellen_anstossen(sitzungen, jetzt=JETZT + timedelta(hours=1), ha_svc=gezaehlt)
    assert gezaehlt.abrufe == []
    async with sitzungen() as s:
        assert len((await s.execute(select(ActivityLog))).scalars().all()) == protokoll_vorher


async def test_startlauf_fuellt_jeden_kanal_ohne_marke(ha, datei, monkeypatch):
    """``nachfuellen_nach_dem_start`` (Hintergrund-Aufgabe aus ``main.py``) über die Sitzungen des Produkts."""
    import backend.core.database as dbmod
    import backend.services.ha_statistics_service as hss

    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    monkeypatch.setattr(dbmod, "get_session", sitzungen)
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    await nachfuellen_nach_dem_start(warte_s=0)
    assert len(await _marken(sitzungen)) == 4
    assert len(await _zeilen(sitzungen, aid, "basis:einspeisung")) > 900


async def test_stundenlauf_stoesst_das_nachfuellen_an(ha, datei, monkeypatch):
    """Der Einstieg im Produkt: ``scheduler.sensor_snapshot_job`` legt den Kanal des neu zugeordneten Zählers
    an und stößt danach (außerhalb seiner Sitzung) das Nachfüllen an — dessen Historie kommt. Uhr gestellt."""
    import backend.core.database as dbmod
    import backend.services.ha_statistics_service as hss
    from backend.services import scheduler
    from backend.services.kanal import nachfuellen as nf

    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    neu = _reihe(svc, "sensor.ladung", "kWh", start=20.0, rate=0.5)
    async with sitzungen() as s:
        sp = Investition(anlage_id=aid, typ="speicher", bezeichnung="Akku")
        s.add(sp)
        await s.flush()
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        a.sensor_mapping = {**a.sensor_mapping, "investitionen": {
            **a.sensor_mapping["investitionen"], str(sp.id): {"felder": {"ladung_kwh": _s("sensor.ladung")}}}}
        flag_modified(a, "sensor_mapping")
        sp_id = sp.id

    class _Uhr(datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D102
            return JETZT

    monkeypatch.setattr(dbmod, "get_session", sitzungen)
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    monkeypatch.setattr(scheduler, "datetime", _Uhr)
    monkeypatch.setattr(nf, "datetime", _Uhr)
    monkeypatch.setattr(nf, "_ANSTOSS", None)
    await scheduler.sensor_snapshot_job()
    assert nf._ANSTOSS is not None
    await nf._ANSTOSS
    ladung = await _zeilen(sitzungen, aid, f"inv:{sp_id}:ladung_kwh")
    assert {t: r.sum for t, r in ladung.items()} == {t: w["sum"] for t, w in _bis_jetzt(neu).items()}



class _StillWeg:
    """HA-Dienst, der nach ``n`` Abfragen still wegfällt (WebSocket: ``is_available`` falsch, die Leser liefern
    ``None``/``{}``). ``zurueck()`` holt ihn wieder."""

    def __init__(self, svc, n: int):
        self._svc, self._n, self.abrufe, self.da = svc, n, 0, True

    @property
    def is_available(self):
        return self.da

    def __getattr__(self, name):
        attr = getattr(self._svc, name)
        if not (callable(attr) and name.startswith("get_")):
            return attr

        def _abruf(*a, **k):
            self.abrufe += 1
            if self.abrufe >= self._n:
                self.da = False
            if not self.da:
                return {} if name == "get_stundenzeilen_mehrere" else None
            return attr(*a, **k)
        return _abruf


@pytest.mark.parametrize("n", [4, 5], ids=["entity_fehlt", "anker_none"])
async def test_ha_faellt_still_aus_keine_marke_der_naechste_lauf_setzt_fort(ha, datei, n):
    """Nachmessung E2 Punkt 4: HA fällt nach der n-ten Abfrage still aus — beim Block (``{}``, n = 4) bzw.
    beim Anker (``None``, n = 5). Der Kanal ist ein Fehler ohne Marke; mit HA zurück holt der nächste Lauf den Rest."""
    svc, reihen = ha
    sitzungen, _pfad, aid, _ = datei
    erg = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=_StillWeg(svc, n), block_stunden=24)
    assert erg.fehler >= 1
    marken = {sid for sid, _e in (await _marken(sitzungen)).values()}
    assert "sensor.einsp" not in marken
    teil = await _zeilen(sitzungen, aid, "basis:einspeisung")
    soll = _bis_jetzt(reihen["sensor.einsp"])
    assert len(teil) < len(soll)
    zweit = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=svc, block_stunden=24)
    assert zweit.fehler == 0
    assert set(await _zeilen(sitzungen, aid, "basis:einspeisung")) == set(soll)
    assert "sensor.einsp" in {sid for sid, _e in (await _marken(sitzungen)).values()}



async def test_neu_laden_loescht_nichts_unter_has_erster_zeile(ha, datei):
    """Nachmessung E2 Punkt 2b, unmittelbar am Neu-Laden: HA hält die Zeilen vor Tag 12 nicht mehr; ein
    Neu-Laden ab der ersten Stunde ersetzt erst ab HAs erster Zeile — darunter bleibt jede Spiegelzeile."""
    from sqlalchemy import text

    svc, _ = ha
    sitzungen, _pfad, aid, _ = datei
    await nachfuellen_spiegel(sitzungen, aid, jetzt=JETZT, ha_svc=svc)
    vorher = {t: (r.sum, r.state) for t, r in (await _zeilen(sitzungen, aid, "basis:einspeisung")).items()}
    kid = next(iter((await _zeilen(sitzungen, aid, "basis:einspeisung")).values())).kanal_id
    x = _ts(ZEIT + timedelta(days=12, hours=7))                 # mitten in einem 31-Tage-Block
    with svc._engine.begin() as conn:
        conn.execute(text("DELETE FROM statistics WHERE metadata_id = 1 AND start_ts < :t"), {"t": x})
    await neu_spiegeln(sitzungen, kid, _ts(ZEIT), ha_svc=svc)
    nachher = {t: (r.sum, r.state) for t, r in (await _zeilen(sitzungen, aid, "basis:einspeisung")).items()}
    assert nachher == vorher
