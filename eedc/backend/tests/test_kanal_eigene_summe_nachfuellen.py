"""Proben Nachfüllen aus den Stundenständen (HA-Bauform S3, Etappe E-S3-4; S4, Etappe E-S4-3 «Nachbau 2», S4-R-N2).

Für **jeden Zähler** (seit E-S4-3 auch mit HA-Entity) werden die stündlichen Zählerstände in ``sensor_snapshots`` vor der
ersten Kanal-Zeile und vor der ersten Quelle zu Zeilen der Familie Mitschrift — MQTT-Rohstände über dieselbe Rechenstelle
wie der Stundenlauf (``schreiber._eigene_summe_zeilen``), HAs Stände (``ha_statistics``) wörtlich. Ein Stand zur vollen
Stunde ``Z`` ist der Stand am Ende von ``[Z−1 h, Z)`` ⇒ Kanalzeile ``start_ts = Z − 3600``.

Gegen eine Datei-Datenbank (``pv_achse_matrix._neue_db``): das Nachfüllen öffnet je Block eine eigene Sitzung. Die
Referenz der Summenregel ist die Abschrift von HAs Schleife aus ``test_kanal_eigene_summe.py`` (nicht die
Produktfunktion). Keine Probe liest die Uhr.

Schwesterdateien: test_kanal_eigene_summe.py, test_kanal_nachfuellen.py, test_kanal_bestand_unberuehrt.py,
test_kanal_bilanz_gleichheit.py (Datenstand ``MQTT``; die Gleichheit des Nachfüllens dort:
test_kanal_eigene_summe_gleichheit.py).
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Optional
from unittest.mock import patch

import pytest
from sqlalchemy import insert, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models.activity_log import ActivityLog
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import FAMILIE_MITSCHRIFT, Kanal, KanalNachfuellung, KanalQuelle, KanalStatistik
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.kanal.nachfuellen import nachfuellen_anlage, nachfuellen_eigene_summe
from backend.services.kanal.schreiber import schreibe_eigene_summe
from backend.tests import pv_achse_matrix as mx
from backend.tests.test_kanal_eigene_summe import _ha_referenz

T0 = datetime(2026, 6, 10, 0)
JETZT = datetime(2026, 6, 20, 0, 30)
_H = 3600


def _ts(dt: datetime) -> int:
    return int(round(dt.timestamp()))


def _s(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


@pytest.fixture
async def datei():
    """``neue_db()`` → ``(sitzungen, anlage_id)``: je Aufruf eine frische Datei-DB mit einer Anlage (10 kWp, Zuordnung
    leer = reine MQTT-Anlage). Mehrere Aufrufe je Probe ergeben unabhängige Datenbanken (Vergleich zweier Läufe)."""
    verz = tempfile.mkdtemp(prefix="eedc-es-nachfuellen-")
    engines = []

    async def neue_db(name: str = "x", *, mapping: Optional[dict] = None):
        engine, db = await mx._neue_db(f"{verz}/{name}.db")
        await db.close()
        engines.append(engine)
        macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        @asynccontextmanager
        async def sitzungen():
            async with macher() as s:
                yield s
                await s.commit()

        async with sitzungen() as s:
            a = Anlage(anlagenname="ES", leistung_kwp=10.0,
                       sensor_mapping=mapping or {"basis": {}, "investitionen": {}})
            s.add(a)
            await s.flush()
            aid = a.id
        return sitzungen, aid

    yield neue_db
    for e in engines:
        await e.dispose()
    shutil.rmtree(verz, ignore_errors=True)


async def _staende(sitzungen, aid: int, key: str, folge: dict[int, float], *, quelle: str = "mqtt_inbound",
                   ab: datetime = T0) -> None:
    """``{Stunde: Stand}`` → ``sensor_snapshots`` zur vollen Stunde ``ab + Stunde``."""
    async with sitzungen() as s:
        await s.execute(insert(SensorSnapshot), [
            {"anlage_id": aid, "sensor_key": key, "zeitpunkt": ab + timedelta(hours=h), "wert_kwh": w, "quelle": quelle}
            for h, w in folge.items()])


async def _investition(sitzungen, aid: int, typ: str, **kw) -> int:
    async with sitzungen() as s:
        inv = Investition(anlage_id=aid, typ=typ, bezeichnung=typ, **kw)
        s.add(inv)
        await s.flush()
        return inv.id


async def _mapping(sitzungen, aid: int, mapping: dict) -> None:
    from sqlalchemy.orm.attributes import flag_modified

    async with sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        a.sensor_mapping = mapping
        flag_modified(a, "sensor_mapping")


async def _kanal(sitzungen, aid: int, key: str):
    """``(kanal, zeilen, quellen)`` — ``(None, [], [])`` ohne Kanal."""
    async with sitzungen() as s:
        k = (await s.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key == key))).scalar_one_or_none()
        if k is None:
            return None, [], []
        zeilen = (await s.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id)
                                  .order_by(KanalStatistik.start_ts))).scalars().all()
        quellen = (await s.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id)
                                   .order_by(KanalQuelle.gueltig_ab))).scalars().all()
        return k, list(zeilen), list(quellen)


async def _keys(sitzungen, aid: int) -> set[str]:
    async with sitzungen() as s:
        return set((await s.execute(select(Kanal.key).where(Kanal.anlage_id == aid))).scalars().all())


def _werte(zeilen, quellen) -> list[tuple[int, float]]:
    """``(start_ts, Kanalwert)`` je Zeile (``sum + offset`` der geltenden Quelle)."""
    out = []
    for z in zeilen:
        q = max((q for q in quellen if q.gueltig_ab <= z.start_ts), key=lambda q: q.gueltig_ab, default=None)
        out.append((z.start_ts, z.sum + (q.offset if q else 0.0)))
    return out


def _zuwaechse(zeilen, quellen) -> dict[int, float]:
    w = _werte(zeilen, quellen)
    return {b[0]: b[1] - a[1] for a, b in zip(w, w[1:])}


# ── Rechnung, Zuordnung der Stunde, Quelle ──────────────────────────────────


async def test_stundenstaende_werden_die_eigene_summe_nach_has_regel(datei):
    """Reset (< 90 %), Dip (90–100 %), negativer Stand: je Stunde ``(sum, state)`` wie HAs Schleife; ``start_ts`` =
    ``Z − 1 h``; eine Quelle (Mitschrift, MQTT-Kennung, ``offset`` 0) ab der ersten Stunde."""
    sitzungen, aid = await datei()
    folge = {0: 480.0, 1: 482.0, 2: 3.0, 3: 480.0, 4: 470.0, 5: -2.0, 6: 476.0}
    await _staende(sitzungen, aid, "basis:netzbezug", folge)
    erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    k, zeilen, quellen = await _kanal(sitzungen, aid, "basis:netzbezug")
    ref = _ha_referenz([[folge[h]] for h in range(7)])
    assert [(z.sum, z.state) for z in zeilen] == [r for r in ref if r is not None]
    assert [z.start_ts for z in zeilen] == [_ts(T0 + timedelta(hours=h)) - _H for h in range(7)]
    assert {z.familie for z in zeilen} == {FAMILIE_MITSCHRIFT} and k.art == "sum"
    assert [(q.gueltig_ab, q.familie, q.statistic_id, q.offset) for q in quellen] == [
        (zeilen[0].start_ts, FAMILIE_MITSCHRIFT, "netzbezug_kwh", 0.0)]
    assert (erg.kanaele, erg.gefuellt, erg.zeilen, erg.fehler) == (1, 1, 7, 0)


async def test_nur_bis_zur_stunde_vor_jetzt(datei):
    """Ohne Kanal-Zeile wird bis zur Stunde vor ``jetzt`` gefüllt — wie der Stundenlauf (der Stand zur vollen Stunde
    ``jetzt`` gehört zur eben abgeschlossenen Stunde, ein späterer nicht)."""
    sitzungen, aid = await datei()
    await _staende(sitzungen, aid, "basis:netzbezug", {h: 10.0 + h for h in range(6)})
    await nachfuellen_eigene_summe(sitzungen, aid, jetzt=T0 + timedelta(hours=3, minutes=10))
    _, zeilen, _ = await _kanal(sitzungen, aid, "basis:netzbezug")
    assert [z.start_ts for z in zeilen] == [_ts(T0 + timedelta(hours=h)) - _H for h in range(4)]


async def test_luecke_bleibt_luecke_die_menge_steht_in_der_folgestunde(datei):
    sitzungen, aid = await datei()
    await _staende(sitzungen, aid, "basis:netzbezug", {0: 10.0, 1: 11.0, 4: 17.0, 5: 18.0})
    await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    _, zeilen, quellen = await _kanal(sitzungen, aid, "basis:netzbezug")
    assert [z.start_ts for z in zeilen] == [_ts(T0 + timedelta(hours=h)) - _H for h in (0, 1, 4, 5)]
    assert list(_zuwaechse(zeilen, quellen).values()) == pytest.approx([1.0, 6.0, 1.0])


async def test_stand_feld_schreibt_den_stand_ohne_summe(datei):
    sitzungen, aid = await datei()
    wb = await _investition(sitzungen, aid, "wallbox")
    await _staende(sitzungen, aid, f"inv:{wb}:ladevorgaenge", {0: 7.0, 1: -1.0, 2: 9.0})
    await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    k, zeilen, _ = await _kanal(sitzungen, aid, f"inv:{wb}:ladevorgaenge")
    assert k.art == "stand"
    assert [(z.sum, z.state) for z in zeilen] == [(None, 7.0), (None, 9.0)]   # negativ ⇒ keine Zeile


# ── Marke, Idempotenz, Aktivität ────────────────────────────────────────────


async def test_zweiter_lauf_schreibt_nichts_marke_je_kanal(datei):
    sitzungen, aid = await datei()
    await _staende(sitzungen, aid, "basis:netzbezug", {h: 10.0 + h for h in range(5)})
    erst = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=mx._ha_aus())
    zweit = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=mx._ha_aus())
    assert (erst.eigene_summe.zeilen, erst.eigene_summe.markiert) == (5, 1)
    assert zweit.eigene_summe.zeilen == 0 and dict(zweit.eigene_summe.uebersprungen) == {"schon_gefuellt": 1}
    async with sitzungen() as s:
        marken = (await s.execute(select(KanalNachfuellung))).scalars().all()
        protokoll = [(a.aktion, a.erfolg) for a in (await s.execute(select(ActivityLog))).scalars().all()]
    assert [(m.statistic_id, m.ergebnis) for m in marken] == [("netzbezug_kwh", {"zeilen": 5})]
    assert protokoll == [("Kanalstatistik: Nachfüllen aus den Zählerständen abgeschlossen", True)]


async def test_start_ohne_neue_zeilen_schreibt_keine_aktivitaet(datei):
    """Nachmessung E-S3-4 (M-1): Schlüssel ohne Kanal (nur ``live_fallback``- bzw. ``unknown``-Stände) bekommen keine Marke
    und werden bei jedem Start neu geprüft — protokolliert wird nur, wenn Zeilen geschrieben wurden oder ein Kanal abbrach.
    (Bis E-S4-3 stand hier eine Tagesstand-Reihe; seit S4-R-3e wird sie gefüllt.)"""
    sitzungen, aid = await datei()
    await _staende(sitzungen, aid, "basis:netzbezug", {0: 5.0, 1: 6.0}, quelle="live_fallback")
    await _staende(sitzungen, aid, "basis:einspeisung", {i * 24: 100.0 + i for i in range(5)}, quelle="unknown")
    for _ in range(3):
        erg = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=mx._ha_aus())
        assert erg.eigene_summe.kanaele == 2 and erg.eigene_summe.zeilen == 0
    async with sitzungen() as s:
        assert (await s.execute(select(ActivityLog))).scalars().all() == []


# ── S4-R-N2: jeder Zähler, auch mit HA-Entity ───────────────────────────────


async def test_jeder_zaehler_auch_mit_ha_entity_wird_gefuellt(datei):
    """S4-R-N2 (S3-R9 berichtigt, Bauplan S3 §10f): Netzbezug (HA-Sensor), PV-Gesamt (``quellen``: HA) und ein
    stillgelegtes Gerät mit HA-Entity bekommen ihre Stände wie die Einspeisung ohne Zuordnung; nur die Speicher-Ladung mit
    ``quellen`` «keine» bleibt ohne Kanal. Die Herkunft der Stände entscheidet die Rechnung (``mqtt_inbound`` ⇒ HAs Regel,
    ``ha_statistics`` ⇒ wörtlich), nicht die Zuordnung."""
    sitzungen, aid = await datei()
    sp = await _investition(sitzungen, aid, "speicher")
    alt = await _investition(sitzungen, aid, "pv-module", leistung_kwp=2.0, stilllegungsdatum=date(2026, 1, 1))
    await _mapping(sitzungen, aid, {
        "basis": {"netzbezug": _s("sensor.netz")},
        "investitionen": {str(alt): {"felder": {"pv_erzeugung_kwh": _s("sensor.alt")}}},
        "quellen": {"basis_energy_pv_gesamt_kwh": {"quelle": "ha_app", "entity_id": "sensor.pv"},
                    f"inv_energy_{sp}_ladung_kwh": {"quelle": "keine"}},
    })
    for key in ("basis:netzbezug", "basis:pv_gesamt", f"inv:{sp}:ladung_kwh", f"inv:{alt}:pv_erzeugung_kwh"):
        await _staende(sitzungen, aid, key, {h: 10.0 + h for h in range(4)})
    await _staende(sitzungen, aid, "basis:einspeisung", {h: 10.0 + h for h in range(4)}, quelle="ha_statistics")
    erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    assert await _keys(sitzungen, aid) == {"basis:einspeisung", "basis:netzbezug", "basis:pv_gesamt",
                                           f"inv:{alt}:pv_erzeugung_kwh"}
    assert (erg.gefuellt, erg.zeilen) == (4, 16)
    _, netz, q_netz = await _kanal(sitzungen, aid, "basis:netzbezug")
    assert [z.sum for z in netz] == [0.0, 1.0, 2.0, 3.0] and [q.statistic_id for q in q_netz] == ["netzbezug_kwh"]
    _, einsp, q_einsp = await _kanal(sitzungen, aid, "basis:einspeisung")
    assert [(z.sum, z.state) for z in einsp] == [(10.0 + h, None) for h in range(4)]          # wörtlich, ohne state
    assert [(q.statistic_id, q.familie, q.offset) for q in q_einsp] == [
        ("sensor_snapshots:basis:einspeisung", FAMILIE_MITSCHRIFT, 0.0)]


async def test_auswahl_wie_der_stundenlauf(datei):
    """Die Schlüsselmenge des Stundenlaufs über die Rohstände (``schreiber._eigene_summe``) und dazu die Zähler mit
    HA-Entity (S4-R-N2; der Stundenlauf schreibt sie über den Spiegel) — gemischte Zuordnung: HA-Sensor, ``quellen``
    keine, MQTT-Gerätezähler, Stand-Zähler, ein Schlüssel ohne Zählerreihe."""
    mapping = {"basis": {"netzbezug": _s("sensor.netz")}, "investitionen": {},
               "quellen": {"basis_energy_einspeisung_kwh": {"quelle": "keine"}}}
    gefunden = []
    for name, weg in (("stundenlauf", "mqtt"), ("nachfuellen", "snap")):
        sitzungen, aid = await datei(name, mapping=mapping)
        pv = await _investition(sitzungen, aid, "pv-module", leistung_kwp=5.0)
        wb = await _investition(sitzungen, aid, "wallbox")
        keys = {"basis:netzbezug": "netzbezug_kwh", "basis:einspeisung": "einspeisung_kwh",
                "basis:pv_gesamt": "pv_gesamt_kwh", f"inv:{pv}:pv_erzeugung_kwh": f"inv/{pv}/pv_erzeugung_kwh",
                f"inv:{wb}:ladevorgaenge": f"inv/{wb}/ladevorgaenge", f"inv:{wb}:soc": f"inv/{wb}/soc"}
        if weg == "mqtt":
            async with sitzungen() as s:
                await s.execute(insert(MqttEnergySnapshot), [
                    {"anlage_id": aid, "energy_key": mk, "timestamp": T0 + timedelta(minutes=30), "value_kwh": 5.0}
                    for mk in keys.values()])
            async with sitzungen() as s:
                a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
                await schreibe_eigene_summe(s, a, T0 + timedelta(hours=1, minutes=5))
        else:
            for sk in keys:
                await _staende(sitzungen, aid, sk, {1: 5.0})
            await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
        gefunden.append({k.split(":", 2)[-1] if k.startswith("inv:") else k for k in await _keys(sitzungen, aid)})
    assert gefunden[0] == {"basis:pv_gesamt", "pv_erzeugung_kwh", "ladevorgaenge"}
    assert gefunden[1] == gefunden[0] | {"basis:netzbezug"}


# ── live_fallback, Deckel ───────────────────────────────────────────────────


async def test_live_fallback_ist_kein_rohstand_ausgeschlossen_und_gezaehlt(datei):
    sitzungen, aid = await datei()
    await _staende(sitzungen, aid, "basis:netzbezug", {0: 10.0, 1: 11.0, 3: 13.0})
    await _staende(sitzungen, aid, "basis:netzbezug", {2: 99.0}, quelle="live_fallback")
    await _staende(sitzungen, aid, "basis:einspeisung", {0: 5.0, 1: 6.0}, quelle="live_fallback")
    erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    _, zeilen, _ = await _kanal(sitzungen, aid, "basis:netzbezug")
    assert [z.state for z in zeilen] == [10.0, 11.0, 13.0]
    assert erg.live_fallback == 3 and erg.uebersprungen["keine_staende"] == 1
    assert await _keys(sitzungen, aid) == {"basis:netzbezug"}


async def test_unknown_ist_kein_rohstand_ausgeschlossen_und_gezaehlt(datei):
    """Nachmessung E-S3-4 (A-1): ``quelle = unknown`` (Herkunft unklassifiziert) wie ``live_fallback`` — keine Zeile,
    gezählt; ein Schlüssel nur mit ``unknown``-Ständen bekommt keinen Kanal."""
    sitzungen, aid = await datei()
    await _staende(sitzungen, aid, "basis:netzbezug", {0: 10.0, 1: 11.0, 3: 13.0})
    await _staende(sitzungen, aid, "basis:netzbezug", {2: 99.0}, quelle="unknown")
    await _staende(sitzungen, aid, "basis:einspeisung", {0: 5.0, 1: 6.0}, quelle="unknown")
    erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    _, zeilen, _ = await _kanal(sitzungen, aid, "basis:netzbezug")
    assert [z.state for z in zeilen] == [10.0, 11.0, 13.0]
    assert (erg.unknown, erg.live_fallback, erg.uebersprungen["keine_staende"]) == (3, 0, 1)
    assert await _keys(sitzungen, aid) == {"basis:netzbezug"}


async def test_deckel_bleibt_schreibfilter_und_wird_gezaehlt(datei):
    """10 kWp ⇒ Schwelle 15 kWh je Stunde: +250 kWh auf der PV-Achse wird verworfen (Stand läuft weiter, Summe nicht),
    der Netzbezug (ohne Deckel) trägt denselben Sprung. Gezählt: eine verworfene Stunde."""
    sitzungen, aid = await datei()
    pv = await _investition(sitzungen, aid, "pv-module", leistung_kwp=10.0)
    folge = {0: 100.0, 1: 104.0, 2: 354.0, 3: 358.0}
    await _staende(sitzungen, aid, f"inv:{pv}:pv_erzeugung_kwh", folge)
    await _staende(sitzungen, aid, "basis:netzbezug", folge)
    erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    _, pvz, _ = await _kanal(sitzungen, aid, f"inv:{pv}:pv_erzeugung_kwh")
    _, netz, _ = await _kanal(sitzungen, aid, "basis:netzbezug")
    assert [z.sum for z in pvz] == [0.0, 4.0, 4.0, 8.0] and [z.state for z in pvz] == list(folge.values())
    assert [z.sum for z in netz] == [0.0, 4.0, 254.0, 258.0]
    assert erg.deckel_verworfen == 1


# ── Naht an die erste Kanal-Zeile (der Stundenlauf war zuerst da) ───────────


@pytest.mark.parametrize("stand_naht,zuwachs_naht", [(21.0, 1.0), (1.5, 1.5)], ids=["stetig", "reset_an_der_naht"])
async def test_naht_an_den_stundenlauf(datei, stand_naht, zuwachs_naht):
    """Der Stundenlauf hat den Kanal ab Stunde 10 angelegt (Rohstände ab dort); das Nachfüllen setzt die Stunden
    davor an: die vorhandenen Zeilen und ihre Quelle bleiben (``offset`` unverändert), ``gueltig_ab`` sinkt auf die
    erste Stunde, und die Naht-Stunde trägt HAs Zuwachs (stetig: Stand − letzter Stand; Reset < 90 %: der neue Stand)."""
    sitzungen, aid = await datei()
    staende = {h: 10.0 + h for h in range(11)}
    staende[11] = stand_naht                      # Stand am Ende der Stunde 10 (Z = 11)
    await _staende(sitzungen, aid, "basis:netzbezug", staende)
    async with sitzungen() as s:
        await s.execute(insert(MqttEnergySnapshot), [
            {"anlage_id": aid, "energy_key": "netzbezug_kwh", "timestamp": T0 + timedelta(hours=h, minutes=59),
             "value_kwh": staende[h + 1] if h == 10 else staende[11] + (h - 10)} for h in range(10, 14)])
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        await schreibe_eigene_summe(s, a, T0 + timedelta(hours=11, minutes=5))
    async with sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        await schreibe_eigene_summe(s, a, T0 + timedelta(hours=14, minutes=5))
    _, vorher, q_vorher = await _kanal(sitzungen, aid, "basis:netzbezug")
    assert vorher[0].start_ts == _ts(T0 + timedelta(hours=10))
    await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    _, nachher, quellen = await _kanal(sitzungen, aid, "basis:netzbezug")
    assert [(z.start_ts, z.sum, z.state) for z in nachher[-len(vorher):]] == [
        (z.start_ts, z.sum, z.state) for z in vorher]
    assert len(quellen) == 1 and quellen[0].offset == q_vorher[0].offset
    assert quellen[0].gueltig_ab == nachher[0].start_ts == _ts(T0) - _H
    zuwachs = _zuwaechse(nachher, quellen)
    assert zuwachs[vorher[0].start_ts] == pytest.approx(zuwachs_naht)
    assert all(v == pytest.approx(1.0) for ts, v in zuwachs.items() if ts < vorher[0].start_ts)


async def _spiegel_ab(sitzungen, aid: int, key: str, ab_h: int, sums: list[float], *, offset: float = 0.0) -> None:
    """Ein Kanal, der mit dem Spiegel ``sensor.neu`` ab Stunde ``ab_h`` beginnt (``sum`` je Stunde, ``state`` = sum + 7)."""
    async with sitzungen() as s:
        k = Kanal(anlage_id=aid, key=key, art="sum", einheit="kWh")
        s.add(k)
        await s.flush()
        s.add(KanalQuelle(kanal_id=k.id, gueltig_ab=_ts(T0 + timedelta(hours=ab_h)), familie="spiegel",
                          statistic_id="sensor.neu", offset=offset))
        for i, v in enumerate(sums):
            s.add(KanalStatistik(kanal_id=k.id, start_ts=_ts(T0 + timedelta(hours=ab_h + i)), sum=v, state=v + 7.0,
                                 familie="spiegel"))


@pytest.mark.parametrize("quelle,kennung", [("mqtt_inbound", "netzbezug_kwh"),
                                            ("ha_statistics", "sensor_snapshots:basis:netzbezug")], ids=["mqtt", "ha"])
async def test_staende_vor_der_ersten_spiegel_zeile_eigene_quelle_naht_ohne_zuwachs(datei, quelle, kennung):
    """S4-R-N2: beginnt der Kanal mit dem Spiegel (HAs Statistik ab Stunde 5), füllen die Stände die Stunden DAVOR —
    eigene Mitschrift-Quelle (MQTT-Kennung bzw. ``sensor_snapshots:<key>``), Spiegel-Zeilen und -Quelle unberührt. Zwei
    Summen-Systeme haben keinen gemeinsamen Anker: die erste Spiegel-Stunde trägt keinen Zuwachs (wie ein Quellwechsel im
    Stundenlauf), der Kanalwert ist an der Naht stetig."""
    sitzungen, aid = await datei()
    await _spiegel_ab(sitzungen, aid, "basis:netzbezug", 5, [0.0, 2.0, 4.0], offset=100.0)
    await _staende(sitzungen, aid, "basis:netzbezug", {h: 10.0 + h for h in range(6)}, quelle=quelle)
    erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    _, zeilen, quellen = await _kanal(sitzungen, aid, "basis:netzbezug")
    erste_spiegel = _ts(T0 + timedelta(hours=5))
    assert [z.start_ts for z in zeilen] == [_ts(T0 + timedelta(hours=h)) - _H for h in range(6)] + [
        erste_spiegel + i * _H for i in (0, 1, 2)]                    # Stand Z=5 ⇒ Zeile 4; ab Zeile 5 der Spiegel
    assert [(z.sum, z.familie) for z in zeilen if z.start_ts >= erste_spiegel] == [
        (0.0, "spiegel"), (2.0, "spiegel"), (4.0, "spiegel")]
    assert [(q.familie, q.statistic_id) for q in quellen] == [("mitschrift", kennung), ("spiegel", "sensor.neu")]
    assert quellen[1].offset == 100.0 and quellen[0].gueltig_ab == zeilen[0].start_ts
    zuwachs = _zuwaechse(zeilen, quellen)
    assert all(v == pytest.approx(1.0) for ts, v in zuwachs.items() if ts < erste_spiegel)
    assert zuwachs[erste_spiegel] == pytest.approx(0.0) and zuwachs[erste_spiegel + _H] == pytest.approx(2.0)
    assert (erg.gefuellt, erg.zeilen, erg.markiert) == (1, 6, 1)


async def test_ha_staende_woertlich_ohne_reset_regel_und_herkunftswechsel(datei):
    """HAs Stände von damals (``ha_statistics``) sind HAs Summen: wörtlich — ein Rückgang bleibt ein Rückgang (keine
    90-%-Regel, kein Deckel). Wechselt die Herkunft (HA → MQTT), beginnt eine zweite Quelle; ihre erste Stunde trägt keinen
    Zuwachs (der neue Abschnitt setzt am Kanalwert des vorigen an), danach HAs Regel über die MQTT-Rohstände."""
    sitzungen, aid = await datei()
    pv = await _investition(sitzungen, aid, "pv-module", leistung_kwp=10.0)
    key = f"inv:{pv}:pv_erzeugung_kwh"
    await _staende(sitzungen, aid, key, {0: 500.0, 1: 504.0, 2: 3.0, 3: 900.0}, quelle="ha_statistics")
    await _staende(sitzungen, aid, key, {4: 50.0, 5: 52.0, 6: 1.0}, quelle="mqtt_inbound")
    erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    _, zeilen, quellen = await _kanal(sitzungen, aid, key)
    assert [(q.statistic_id, q.gueltig_ab) for q in quellen] == [
        (f"sensor_snapshots:{key}", zeilen[0].start_ts), (f"inv/{pv}/pv_erzeugung_kwh", zeilen[4].start_ts)]
    assert [z.sum for z in zeilen[:4]] == [500.0, 504.0, 3.0, 900.0]                  # wörtlich (−501, +897 ohne Deckel)
    w = _werte(zeilen, quellen)
    assert w[4][1] == pytest.approx(w[3][1])                                          # Quellgrenze ohne Zuwachs
    assert [b[1] - a[1] for a, b in zip(w[4:], w[5:])] == pytest.approx([2.0, 1.0])   # Reset < 90 % ⇒ der neue Stand
    assert erg.deckel_verworfen == 0 and (erg.gefuellt, erg.zeilen) == (1, 7)


# ── Blockweise, abgebrochen, fortgesetzt ────────────────────────────────────


async def test_abbruch_nach_einem_block_setzt_beim_naechsten_lauf_fort(datei):
    """Blöcke zu 3 Stunden, jüngster zuerst; der zweite Block scheitert ⇒ keine Marke, ein Fehler. Der nächste Lauf
    rechnet bis zur dann ersten Zeile neu — das Ergebnis ist Zeile für Zeile das eines ungestörten Laufs."""
    from backend.services.kanal import nachfuellen as nf

    folge = {h: 100.0 + 1.5 * h for h in range(10)}
    sitzungen, aid = await datei("gestoert")
    await _staende(sitzungen, aid, "basis:netzbezug", folge)
    echt, aufrufe = nf._einfuegen, []

    async def _zweiter_scheitert(db, zeilen):
        aufrufe.append(len(zeilen))
        if len(aufrufe) == 2:
            raise RuntimeError("Sprengsatz Block 2")
        return await echt(db, zeilen)

    with patch.object(nf, "_einfuegen", _zweiter_scheitert):
        erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT, block_stunden=3)
    assert erg.fehler == 1 and erg.markiert == 0
    _, teil, _ = await _kanal(sitzungen, aid, "basis:netzbezug")
    assert len(teil) == 3
    zweit = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT, block_stunden=3)
    assert zweit.fehler == 0 and zweit.markiert == 1 and zweit.zeilen == 7
    _, gestoert, q_gestoert = await _kanal(sitzungen, aid, "basis:netzbezug")

    sitzungen2, aid2 = await datei("ungestoert")
    await _staende(sitzungen2, aid2, "basis:netzbezug", folge)
    await nachfuellen_eigene_summe(sitzungen2, aid2, jetzt=JETZT, block_stunden=3)
    _, glatt, q_glatt = await _kanal(sitzungen2, aid2, "basis:netzbezug")
    assert [(ts, round(v, 9)) for ts, v in _werte(gestoert, q_gestoert)] == [
        (ts, round(v, 9)) for ts, v in _werte(glatt, q_glatt)]
    assert [z.state for z in gestoert] == [z.state for z in glatt]
    assert q_gestoert[0].gueltig_ab == q_glatt[0].gueltig_ab == gestoert[0].start_ts


# ── Ein Stand je Tag (mess3: Tagesgrenzen 00:00 aus der HA-Zeit) ────────────


async def test_tagesstand_reihe_wird_gefuellt_und_gezaehlt(datei):
    """S4-R-3e (E-S4-3): seit dem Kalendertag (R-3) liegt ein Stand um 00:00 als Zeile 23:00 genau auf der Tagesgrenze —
    die Reihe wird gefüllt wie jede andere (das Option-B-Kriterium ist entfallen); die Aktivität nennt sie («1 Reihen mit
    Tagesständen»). Eine stündliche Reihe mit einer langen inneren Lücke zählt nicht dazu (Menge in der Folgestunde).
    Tag und Stunden aus solchen Reihen: ``test_kanal_tagesstand_reihen.py``."""
    sitzungen, aid = await datei()
    await _staende(sitzungen, aid, "basis:netzbezug", {i * 24: 1000.0 + 10 * i for i in range(45)},
                   ab=T0 - timedelta(days=20))
    luecke = {h: 10.0 + h for h in range(6)} | {h: 10.0 + h for h in range(40, 46)}
    await _staende(sitzungen, aid, "basis:einspeisung", luecke)
    erg = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT + timedelta(days=30), ha_svc=mx._ha_aus())
    es = erg.eigene_summe
    assert (es.tagesstand_reihen, es.gefuellt, es.zeilen) == (1, 2, 12 + 45)
    assert await _keys(sitzungen, aid) == {"basis:einspeisung", "basis:netzbezug"}
    _, netz, q_netz = await _kanal(sitzungen, aid, "basis:netzbezug")
    assert {datetime.fromtimestamp(z.start_ts).hour for z in netz} == {23}
    assert set(_zuwaechse(netz, q_netz).values()) == {10.0}
    _, einsp, quellen = await _kanal(sitzungen, aid, "basis:einspeisung")
    assert _zuwaechse(einsp, quellen)[_ts(T0 + timedelta(hours=40)) - _H] == pytest.approx(35.0)
    async with sitzungen() as s:
        details = [a.details for a in (await s.execute(select(ActivityLog))).scalars().all()
                   if a.aktion.endswith("abgeschlossen")]
    assert details and details[0].endswith("; 1 Reihen mit Tagesständen"), details


# ── Auslöser: Anstoß aus dem Stundenlauf, Startlauf ─────────────────────────


async def test_anstoss_und_startlauf_nehmen_die_eigene_summe_mit(datei, monkeypatch):
    """Der Stundenlauf legt den Kanal der MQTT-Reihe an (erste Stunde 10), der Anstoß danach füllt die Stunden davor
    aus ``sensor_snapshots`` — ohne HA; ein zweiter Anstoß schreibt nichts und protokolliert nichts. Ein Schlüssel nur in
    der Vergangenheit (kein MQTT mehr, kein Kanal) bleibt dem Anstoß fern (nur vorhandene Kanäle) und kommt mit dem
    Startlauf (``nachfuellen_nach_dem_start``, Sitzungen des Produkts)."""
    import backend.core.database as dbmod
    import backend.services.ha_statistics_service as hss
    from backend.services.kanal.nachfuellen import nachfuellen_anstossen, nachfuellen_nach_dem_start

    sitzungen, aid = await datei()
    await _staende(sitzungen, aid, "basis:netzbezug", {h: 10.0 + h for h in range(11)})
    await _staende(sitzungen, aid, "basis:einspeisung", {h: 50.0 + h for h in range(5)})
    async with sitzungen() as s:
        await s.execute(insert(MqttEnergySnapshot), [
            {"anlage_id": aid, "energy_key": "netzbezug_kwh", "timestamp": T0 + timedelta(hours=10, minutes=59),
             "value_kwh": 21.0}])
        a = (await s.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        await schreibe_eigene_summe(s, a, T0 + timedelta(hours=11, minutes=5))
    aus = mx._ha_aus()
    await nachfuellen_anstossen(sitzungen, jetzt=JETZT, ha_svc=aus)
    _, zeilen, _ = await _kanal(sitzungen, aid, "basis:netzbezug")
    assert len(zeilen) == 12 and zeilen[0].start_ts == _ts(T0) - _H
    assert await _keys(sitzungen, aid) == {"basis:netzbezug"}
    async with sitzungen() as s:
        protokoll = len((await s.execute(select(ActivityLog))).scalars().all())
    await nachfuellen_anstossen(sitzungen, jetzt=JETZT, ha_svc=aus)
    async with sitzungen() as s:
        assert len((await s.execute(select(ActivityLog))).scalars().all()) == protokoll
    assert len((await _kanal(sitzungen, aid, "basis:netzbezug"))[1]) == 12

    monkeypatch.setattr(dbmod, "get_session", sitzungen)
    monkeypatch.setattr(hss, "_ha_statistics_service", aus)
    await nachfuellen_nach_dem_start(warte_s=0)
    _, einsp, _ = await _kanal(sitzungen, aid, "basis:einspeisung")
    assert [z.state for z in einsp] == [50.0 + h for h in range(5)]
