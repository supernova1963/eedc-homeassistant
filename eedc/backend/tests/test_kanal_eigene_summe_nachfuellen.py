"""Proben Nachfüllen «Eigene Summe» aus den Stundenständen (HA-Bauform S3, Etappe E-S3-4, Auftrag Punkte 1, 3, 7).

Für jeden Zähler **ohne HA-Entity** (S3-R9) werden die stündlichen Zählerstände in ``sensor_snapshots`` vor der ersten
Kanal-Zeile zu Zeilen der Familie Mitschrift — über dieselbe Rechenstelle wie der Stundenlauf
(``schreiber._eigene_summe_zeilen``). Ein Stand zur vollen Stunde ``Z`` ist der Stand am Ende von ``[Z−1 h, Z)`` ⇒
Kanalzeile ``start_ts = Z − 3600``.

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
    """Nachmessung E-S3-4 (M-1): Schlüssel ohne Kanal (nur ``live_fallback``, Tagesstände) bekommen keine Marke und werden
    bei jedem Start neu geprüft — protokolliert wird nur, wenn Zeilen geschrieben wurden oder ein Kanal abbrach."""
    sitzungen, aid = await datei()
    await _staende(sitzungen, aid, "basis:netzbezug", {0: 5.0, 1: 6.0}, quelle="live_fallback")
    await _staende(sitzungen, aid, "basis:einspeisung", {i * 24: 100.0 + i for i in range(5)})
    for _ in range(3):
        erg = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT, ha_svc=mx._ha_aus())
        assert erg.eigene_summe.kanaele == 2 and erg.eigene_summe.zeilen == 0
    async with sitzungen() as s:
        assert (await s.execute(select(ActivityLog))).scalars().all() == []


# ── S3-R9: HA-Entity nie aus sensor_snapshots ───────────────────────────────


async def test_feld_mit_ha_entity_bekommt_nichts_aus_den_stundenstaenden(datei):
    """S3-R9: die Zuordnung entscheidet, nicht die Spalte ``quelle``. Netzbezug (HA-Sensor), PV-Gesamt (``quellen``:
    HA), Speicher-Ladung (``quellen``: keine) und ein stillgelegtes Gerät mit HA-Entity bleiben ohne Kanal — auch mit
    ``mqtt_inbound``-Ständen; die Einspeisung ohne Zuordnung wird gefüllt — auch aus ``ha_statistics``-Ständen."""
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
    await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    assert await _keys(sitzungen, aid) == {"basis:einspeisung"}


async def test_auswahl_wie_der_stundenlauf(datei):
    """Dieselbe Schlüsselmenge wie der Stundenlauf über die Rohstände (``schreiber._eigene_summe``) — gemischte
    Zuordnung: HA-Sensor, ``quellen`` keine, MQTT-Gerätezähler, Stand-Zähler, ein Schlüssel ohne Zählerreihe."""
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
    assert gefunden[0] == gefunden[1] == {"basis:pv_gesamt", "pv_erzeugung_kwh", "ladevorgaenge"}


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


async def test_erste_quelle_eines_anderen_schluessels_bleibt_unberuehrt(datei):
    """Die Vorgeschichte DERSELBEN Quelle (wie der Spiegel): beginnt der Kanal mit einer anderen Quelle, nichts."""
    sitzungen, aid = await datei()
    async with sitzungen() as s:
        k = Kanal(anlage_id=aid, key="basis:netzbezug", art="sum", einheit="kWh")
        s.add(k)
        await s.flush()
        s.add(KanalQuelle(kanal_id=k.id, gueltig_ab=_ts(T0 + timedelta(hours=5)), familie="spiegel",
                          statistic_id="sensor.alt", offset=0.0))
        s.add(KanalStatistik(kanal_id=k.id, start_ts=_ts(T0 + timedelta(hours=5)), sum=1.0, state=1.0,
                             familie="spiegel"))
    await _staende(sitzungen, aid, "basis:netzbezug", {h: 10.0 + h for h in range(5)})
    erg = await nachfuellen_eigene_summe(sitzungen, aid, jetzt=JETZT)
    _, zeilen, _ = await _kanal(sitzungen, aid, "basis:netzbezug")
    assert len(zeilen) == 1 and erg.uebersprungen["vorgeschichte_andere_quelle"] == 1 and erg.markiert == 1


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


async def test_tagesstand_reihe_wird_nicht_nachgefuellt_sondern_gezaehlt(datei):
    """Entscheid Master E-S3-4 (Option B): nur stündliche Reihen (Median der Abstände ≤ 3 600 s). Ein Stand je Tag um
    00:00 würde die Zeile 23:00 und träfe im 23-Uhr-Tagesfenster weder den Tag (Vortagsmenge) noch den Monat (31.05. statt
    30.06.) — die Reihe bleibt Lesart 1 (kein Kanal), gezählt als ``tagesstaende`` und in der Aktivität genannt. Eine
    stündliche Reihe mit einer langen inneren Lücke wird dagegen gefüllt (Menge in der Folgestunde)."""
    sitzungen, aid = await datei()
    await _staende(sitzungen, aid, "basis:netzbezug", {i * 24: 1000.0 + 10 * i for i in range(45)},
                   ab=T0 - timedelta(days=20))
    luecke = {h: 10.0 + h for h in range(6)} | {h: 10.0 + h for h in range(40, 46)}
    await _staende(sitzungen, aid, "basis:einspeisung", luecke)
    erg = await nachfuellen_anlage(sitzungen, aid, jetzt=JETZT + timedelta(days=30), ha_svc=mx._ha_aus())
    es = erg.eigene_summe
    assert es.uebersprungen["tagesstaende"] == 1 and es.gefuellt == 1 and es.zeilen == 12
    assert await _keys(sitzungen, aid) == {"basis:einspeisung"}
    _, einsp, quellen = await _kanal(sitzungen, aid, "basis:einspeisung")
    assert _zuwaechse(einsp, quellen)[_ts(T0 + timedelta(hours=40)) - _H] == pytest.approx(35.0)
    async with sitzungen() as s:
        details = [a.details for a in (await s.execute(select(ActivityLog))).scalars().all()
                   if a.aktion.endswith("abgeschlossen")]
    assert details and "1 Reihen mit Tagesständen — ab Kalendertag (S4)" in details[0], details


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
