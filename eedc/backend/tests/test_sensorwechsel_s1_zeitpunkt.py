"""Sensorwechsel mit Grund, Sitzung 1 — B-0 «Zuordnung zum Zeitpunkt» (Bauplan Fassung 2 §2 B-0, §7 Nr. 1–4).

**Regel:** für einen Zeitstempel ``z`` gilt ``vorher`` des frühesten verzeichneten Wechsels mit ``ab_ts > z``, sonst die heutige
Zuordnung; **kein Schreiber setzt für z den Stand einer anderen Quelle**, und gelöscht wird bei ``force_resnap`` nur eine
Stunden-Zeile derselben Quelle wie am Zeitpunkt — nie eine Fünf-Minuten-Zeile, die älter ist, als HAs Kurzzeitstatistik reicht.

Geprüft am echten Schreiber gegen einen In-Memory-Recorder (``ha_lts_helfer``): «Tag neu aggregieren» (``resnap_anlage_range``)
für einen Tag vor dem Wechsel · neue Entität ohne Geschichte · Heilen eines fehlenden Randes (``get_snapshot``, der Weg von
``tag-detail``) an ``ladung_pv_kwh`` · Wechsel, dann Neustart (Startup-Recovery) · Wechsel 10:47:42 ⇒ Zeile 11:00 neu,
Fünf-Minuten-Zeile 10:50 alt · der LTS-Tag (``lts_tagestabelle``) liest je Slot die Entität zum Stand · der Live-Rückfall.
Jede Probe hat einen **Sprengsatz**: ``lade_wechsel`` liefert nichts (= «der Resolver liefert die heutige Entität»), dann wird
die Probe rot — gezeigt durch die Gegenprobe im selben Test.

Schwesterdateien: test_sensorwechsel_s1_verzeichnen.py (Tabelle, wirksame Quelle, Verzeichnen je Schreibweg, Überführung,
Räumen), test_zaehlerluecken_lts_tabelle.py (LTS-Tag), test_n656_snapshot_rollback_je_anlage.py (Startup-Recovery),
test_datenquellen_resolver_c2b.py (Writer-Read-Through).
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw
from backend.services.zuordnung_wechsel.zeitpunkt import HEUTE, UNBEKANNT, Wechsel, ab_ts_aus, quelle_am
from backend.tests import ha_lts_helfer

A = {"art": "ha", "entity_id": "sensor.a"}
B = {"art": "ha", "entity_id": "sensor.b"}
ERKLAERT = datetime(2026, 10, 18, 10, 47, 42)
T = datetime(2026, 10, 18, 11, 0)
D = date(2026, 9, 20)
KEY = "inv:2:ladung_kwh"


# ═══ Reine Regel ════════════════════════════════════════════════════════════════════════════════════════════════════

def test_ab_ts_erste_volle_stunde_ab_der_erklaerung():
    assert ab_ts_aus(ERKLAERT) == T
    assert ab_ts_aus(datetime(2026, 10, 18, 11, 0, 0)) == T
    assert ab_ts_aus(datetime(2026, 10, 18, 23, 0, 1)) == datetime(2026, 10, 19, 0, 0)


def test_quelle_am_regel():
    w = [Wechsel(KEY, T, A, B)]
    assert quelle_am(None, T) is HEUTE
    assert quelle_am(w, T - timedelta(seconds=1)) == A          # ein Stand vor ab_ts gehört zur alten Quelle
    assert quelle_am(w, T) is HEUTE                              # ab ab_ts die heutige
    # A → «keine» → B: der früheste Wechsel nach z entscheidet
    t2 = T + timedelta(days=3)
    kette = [Wechsel(KEY, t2, {"art": "keine"}, B), Wechsel(KEY, T, A, {"art": "keine"})]
    assert quelle_am(kette, T - timedelta(hours=1)) == A
    assert quelle_am(kette, T + timedelta(hours=1)) == {"art": "keine"}
    assert quelle_am(kette, t2) is HEUTE
    # vorher leer = unbekannt
    assert quelle_am([Wechsel(KEY, T, None, B)], datetime(2026, 1, 1)) is UNBEKANNT
    # eine aufgehobene Zeile zählt nicht
    assert quelle_am([Wechsel(KEY, T, A, B, aufgehoben_durch=7)], datetime(2026, 1, 1)) is HEUTE


# ═══ Umgebung: Recorder, Anlage, Wechsel ═══════════════════════════════════════════════════════════════════════════════

def _stand_a(t: datetime) -> float:
    return round(1500.0 + (t - datetime(2026, 9, 1)).total_seconds() / 3600 * 0.1, 3)


def _stand_b(t: datetime) -> float:
    return round(_stand_a(t) + 2114.714, 3)


def _recorder(staende: dict, kurz: dict | None = None):
    """``staende``: {entity: {zeitpunkt: stand}} (Stand AN zeitpunkt ⇒ HA-Zeile start_ts = zeitpunkt − 1 h)."""
    svc = ha_lts_helfer.mach_service(thread_sicher=True)
    for eid in set(staende) | set(kurz or {}):
        mid = ha_lts_helfer.sensor(svc, eid, "kWh", has_sum=True)
        for t, w in (staende.get(eid) or {}).items():
            ha_lts_helfer.zeile(svc, mid, t - timedelta(hours=1), state=w, sum_wert=w)
        for t, w in ((kurz or {}).get(eid) or {}).items():
            ha_lts_helfer.zeile(svc, mid, t - timedelta(minutes=5), state=w, sum_wert=w, tabelle="statistics_short_term")
    return svc


def _stunden(von: datetime, bis: datetime) -> list[datetime]:
    out, t = [], von
    while t <= bis:
        out.append(t)
        t += timedelta(hours=1)
    return out


async def _anlage(db, key_feld: str = "ladung_kwh", entity: str = "sensor.b") -> Anlage:
    a = Anlage(anlagenname="Sensorwechsel", leistung_kwp=10.0, sensor_mapping={
        "investitionen": {"2": {"felder": {key_feld: {"strategie": "sensor", "sensor_id": entity}}}},
        "quellen": {f"inv_energy_2_{key_feld}": {"quelle": "ha_app", "entity_id": entity}},
    })
    db.add(a)
    await db.flush()
    db.add(Investition(id=2, anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 11, 1)))
    await db.flush()
    return a


async def _wechsel(db, anlage_id: int, key: str = KEY, vorher=A, nachher=B, erklaert: datetime = ERKLAERT):
    db.add(ZuordnungWechsel(anlage_id=anlage_id, sensor_key=key, erklaert_ts=erklaert, ab_ts=ab_ts_aus(erklaert),
                            vorher=vorher, nachher=nachher, herkunft="wechsel"))
    await db.flush()
    zw.vergiss(db)


async def _reihe(db, anlage_id: int, key: str = KEY) -> dict[datetime, float]:
    return {z: w for z, w in (await db.execute(select(SensorSnapshot.zeitpunkt, SensorSnapshot.wert_kwh).where(
        SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == key).order_by(SensorSnapshot.zeitpunkt))).all()}


def _sprengsatz(monkeypatch):
    """«Der Resolver liefert die heutige Entität»: keine verzeichneten Wechsel."""
    async def nichts(db, anlage_id):
        return {}
    monkeypatch.setattr(zw, "lade_wechsel", nichts)


def _ha(svc):
    return patch.multiple("backend.services.snapshot.writer", get_ha_statistics_service=lambda: svc)


# ═══ «Tag neu aggregieren» für einen Tag vor dem Wechsel ══════════════════════════════════════════════════════════════

TAG0 = datetime.combine(D, datetime.min.time())
FENSTER = _stunden(TAG0 - timedelta(hours=1), TAG0 + timedelta(days=1))          # 26 volle Stunden wie in Sitzung 0
FUENF = [TAG0 + timedelta(hours=10, minutes=m) for m in range(5, 60, 5)]           # 11 Fünf-Minuten-Zeilen


async def _resnap_lage(db, *, b_geschichte: bool, kurz_a: dict | None = None):
    from backend.services.snapshot.reaggregator import resnap_anlage_range

    a = await _anlage(db)
    for t in FENSTER + FUENF:
        db.add(SensorSnapshot(anlage_id=a.id, sensor_key=KEY, zeitpunkt=t, wert_kwh=_stand_a(t), quelle="ha_statistics"))
    await _wechsel(db, a.id)
    staende = {"sensor.a": {t: _stand_a(t) for t in _stunden(TAG0 - timedelta(hours=3), TAG0 + timedelta(days=1, hours=3))}}
    if b_geschichte:
        staende["sensor.b"] = {t: _stand_b(t) for t in staende["sensor.a"]}
    svc = _recorder(staende, kurz={"sensor.a": kurz_a} if kurz_a else None)
    with _ha(svc):
        await resnap_anlage_range(db, a, von=TAG0 - timedelta(hours=1), bis=TAG0 + timedelta(days=1, hours=1),
                                  include_5min=True)
    return await _reihe(db, a.id)


async def test_b0_tag_neu_aggregieren_vor_dem_wechsel_bleibt_aus_a(db, monkeypatch):
    reihe = await _resnap_lage(db, b_geschichte=True)
    assert [reihe[t] for t in FENSTER] == [_stand_a(t) for t in FENSTER]           # nicht 26 × +2 114,714
    assert all(t in reihe for t in FUENF)                                          # Fünf-Minuten-Zeilen bleiben


async def test_b0_sprengsatz_heutige_entitaet_ueberschreibt(db, monkeypatch):
    _sprengsatz(monkeypatch)
    reihe = await _resnap_lage(db, b_geschichte=True)
    assert [reihe[t] for t in FENSTER] == [_stand_b(t) for t in FENSTER]           # die Probe oben wäre rot


async def test_b0_neue_entitaet_ohne_geschichte_loescht_keinen_stand(db):
    reihe = await _resnap_lage(db, b_geschichte=False)
    assert len([t for t in reihe if t.minute == 0]) == len(FENSTER) == 26
    assert [reihe[t] for t in FENSTER] == [_stand_a(t) for t in FENSTER]
    assert len([t for t in reihe if t.minute]) == len(FUENF)


async def test_b0_sprengsatz_ohne_geschichte_loescht_26_stunden(db, monkeypatch):
    _sprengsatz(monkeypatch)
    reihe = await _resnap_lage(db, b_geschichte=False)
    assert [t for t in reihe if t.minute == 0] == []                                # Sitzung 0, Fall (3): 26 gelöscht


G1 = 1906.5   # Produktiv (Nachmessung §4): die Reihe derselben Entität steht 250 Tage um 1 906,5 kWh unter HAs heutiger Summe


def _alt_stand(t: datetime) -> float:
    return round(_stand_a(t) - G1, 3)


async def _nur_fuellen_lage(db, *, vorher=A):
    """Bauplan §8 Nr. 16: vorhandene Zeilen vor dem Wechsel stehen auf einem anderen HA-Summenstand derselben Entität
    (Klasse G-1); HA liefert für A dort einen anderen Wert (``_stand_a``) oder nichts (``luecke``); einige Stunden- und
    Fünf-Minuten-Zeilen fehlen (``fehlt``)."""
    from backend.services.snapshot.reaggregator import resnap_anlage_range

    a = await _anlage(db)
    fehlt = set(FENSTER[3:6]) | set(FUENF[2:4])
    luecke = set(FENSTER[10:14]) | {FUENF[6]}
    for t in FENSTER + FUENF:
        if t not in fehlt:
            db.add(SensorSnapshot(anlage_id=a.id, sensor_key=KEY, zeitpunkt=t, wert_kwh=_alt_stand(t), quelle="ha_statistics"))
    await _wechsel(db, a.id, vorher=vorher)
    stunden = _stunden(TAG0 - timedelta(hours=3), TAG0 + timedelta(days=1, hours=3))
    svc = _recorder({"sensor.a": {t: _stand_a(t) for t in stunden if t not in luecke},
                     "sensor.b": {t: _stand_b(t) for t in stunden}},
                    kurz={"sensor.a": {t: _stand_a(t) for t in FUENF if t not in luecke},
                          "sensor.b": {t: _stand_b(t) for t in FUENF}})
    with _ha(svc):
        await resnap_anlage_range(db, a, von=FENSTER[0], bis=FENSTER[-1] + timedelta(hours=1), include_5min=True)
    return await _reihe(db, a.id), fehlt, luecke


async def test_b0_vor_dem_wechsel_nur_fuellen(db):
    """Vorhandene Zeile bleibt bitgleich (HA liefert anderen Wert / nichts), keine gelöscht; fehlende kommt aus A."""
    reihe, fehlt, luecke = await _nur_fuellen_lage(db)
    vorhanden = [t for t in FENSTER + FUENF if t not in fehlt]
    assert [reihe.get(t) for t in vorhanden] == [_alt_stand(t) for t in vorhanden]     # 0 überschrieben, 0 gelöscht
    assert all(reihe[t] == _alt_stand(t) for t in luecke)                               # HA ohne Wert: bleibt
    assert {t: reihe.get(t) for t in fehlt} == {t: _stand_a(t) for t in fehlt}          # gefüllt aus der früheren Entität


async def test_b0_sprengsatz_nur_fuellen_heutige_entitaet_ueberschreibt(db, monkeypatch):
    _sprengsatz(monkeypatch)
    reihe, fehlt, luecke = await _nur_fuellen_lage(db)
    assert all(reihe[t] == _stand_b(t) for t in FENSTER)                               # die Probe oben wäre rot
    assert {t: reihe[t] for t in fehlt} == {t: _stand_b(t) for t in fehlt}


async def test_b0_sprengsatz_ueberschreiben_aus_der_damaligen_quelle(db, monkeypatch):
    """Sprengsatz zu §8 Nr. 16 (Option b, wie Sitzung 1 gebaut): schreibt der Lauf vor dem Wechsel aus A über vorhandene
    Zeilen, verschiebt er sie um G1 — die Probe ``test_b0_vor_dem_wechsel_nur_fuellen`` wäre rot."""
    from backend.services.snapshot import writer

    async def nie_vorhanden(*_a, **_k):
        return False
    monkeypatch.setattr(writer, "_snapshot_vorhanden", nie_vorhanden)
    reihe, fehlt, luecke = await _nur_fuellen_lage(db)
    assert all(reihe[t] == _stand_a(t) for t in FENSTER if t not in luecke)            # +1 906,5 an jeder Stunde


@pytest.mark.parametrize("vorher", [None, {"art": "keine"}], ids=["unbekannt", "keine"])
async def test_b0_unbekannte_oder_keine_quelle_fuellt_nicht(db, vorher):
    """Quelle unbekannt bzw. «keine» am Zeitpunkt: der Writer fragt HA nicht, füllt nichts, ändert und löscht nichts —
    Gegenprobe im selben Lauf: ab ``ab_ts`` (die zwei Stunden des Folgetags nach dem Wechsel gibt es hier nicht) schreibt er
    wie heute; dafür liegt der Wechsel in diesem Test MITTEN im Fenster."""
    from backend.services.snapshot.reaggregator import resnap_anlage_range

    a = await _anlage(db)
    fehlt = set(FENSTER[3:6])
    for t in FENSTER:
        if t not in fehlt:
            db.add(SensorSnapshot(anlage_id=a.id, sensor_key=KEY, zeitpunkt=t, wert_kwh=_alt_stand(t), quelle="ha_statistics"))
    await _wechsel(db, a.id, vorher=vorher, erklaert=TAG0 + timedelta(hours=11, minutes=30))     # ab_ts 12:00
    ab = TAG0 + timedelta(hours=12)
    svc = _recorder({"sensor.a": {t: _stand_a(t) for t in FENSTER}, "sensor.b": {t: _stand_b(t) for t in FENSTER}})
    with _ha(svc):
        await resnap_anlage_range(db, a, von=FENSTER[0], bis=FENSTER[-1] + timedelta(hours=1), include_5min=False)
    reihe = await _reihe(db, a.id)
    vor = [t for t in FENSTER if t < ab]
    assert {t: reihe.get(t) for t in vor} == {t: (None if t in fehlt else _alt_stand(t)) for t in vor}
    assert all(reihe[t] == _stand_b(t) for t in FENSTER if t >= ab)                    # Gegenprobe: heutige Quelle


async def test_fuenf_minuten_zeile_nur_geloescht_wo_ha_kurzzeit_reicht(db, monkeypatch):
    """Gegenprobe zu §7 Nr. 3 (ohne Wechsel, heutige Quelle): führt HA in der Stunde Kurzzeit-Zeilen der Quelle (alle außer
    10:30), wird die Zeile ohne HA-Wert gelöscht (#184-Spike-Regel bleibt), die übrigen neu geschrieben; ohne Kurzzeit-Zeilen
    bleiben alle Fünf-Minuten-Zeilen (Sitzung 0: 2 860 gelöscht)."""
    _sprengsatz(monkeypatch)    # kein Wechsel: es gilt die heutige Quelle B
    kurz = {t: _stand_b(t) + 0.0001 for t in FUENF if t.minute != 30}
    from backend.services.snapshot.reaggregator import resnap_anlage_range

    a = await _anlage(db)
    for t in FUENF:
        db.add(SensorSnapshot(anlage_id=a.id, sensor_key=KEY, zeitpunkt=t, wert_kwh=_stand_a(t), quelle="ha_statistics"))
    await db.flush()
    with _ha(_recorder({}, kurz={"sensor.b": kurz})):
        await resnap_anlage_range(db, a, von=TAG0 + timedelta(hours=10), bis=TAG0 + timedelta(hours=11))
    reihe = await _reihe(db, a.id)
    assert TAG0 + timedelta(hours=10, minutes=30) not in reihe
    assert reihe[TAG0 + timedelta(hours=10, minutes=5)] == round(_stand_b(TAG0 + timedelta(hours=10, minutes=5)) + 0.0001, 3)
    with _ha(_recorder({})):
        await resnap_anlage_range(db, a, von=TAG0 + timedelta(hours=10), bis=TAG0 + timedelta(hours=11))
    assert len([t for t in await _reihe(db, a.id) if t.minute]) == len(FUENF) - 1


# ═══ Heilen eines fehlenden Randes (Self-Healing, Weg von `tag-detail`) an `ladung_pv_kwh` ═══════════════════════════════

async def _heil_lage(db, vorher=A):
    from backend.services.snapshot.keys import extract_quellen_energy
    from backend.services.snapshot.reader import get_snapshot

    key = "inv:2:ladung_pv_kwh"
    a = await _anlage(db, key_feld="ladung_pv_kwh")
    await _wechsel(db, a.id, key=key, vorher=vorher)
    z = datetime(2026, 9, 21, 0, 0)
    svc = _recorder({"sensor.a": {z: 120.5}, "sensor.b": {z: 3615.024}})
    with patch("backend.services.snapshot.reader.get_ha_statistics_service", lambda: svc):
        wert = await get_snapshot(db, a.id, key, "sensor.b", z, quellen_energy=extract_quellen_energy(a))
    return wert, await _reihe(db, a.id, key)


async def test_b0_heilen_vor_dem_wechsel_liest_die_alte_entitaet(db):
    wert, reihe = await _heil_lage(db)
    assert wert == 120.5 and list(reihe.values()) == [120.5]                        # keine Zeile auf B-Niveau


async def test_b0_sprengsatz_heilen_mit_der_heutigen_entitaet(db, monkeypatch):
    _sprengsatz(monkeypatch)
    wert, reihe = await _heil_lage(db)
    assert wert == 3615.024 and list(reihe.values()) == [3615.024]                  # Sitzung 0, M-B (2)


async def test_b0_heilen_mit_unbekannter_quelle_schreibt_nichts(db):
    wert, reihe = await _heil_lage(db, vorher=None)
    assert wert is None and reihe == {}


# ═══ Wechsel 10:47:42 ⇒ Zeile 11:00 neu, Fünf-Minuten-Zeile 10:50 alt ═════════════════════════════════════════════════

async def test_b1_wechsel_1047_stunde_1100_neu_fuenf_minuten_1050_alt(db):
    from backend.services.snapshot.writer import snapshot_anlage, snapshot_anlage_5min

    a = await _anlage(db)
    await _wechsel(db, a.id)
    t1050 = datetime(2026, 10, 18, 10, 50)
    svc = _recorder({"sensor.a": {T: _stand_a(T)}, "sensor.b": {T: _stand_b(T)}},
                    kurz={"sensor.a": {t1050: _stand_a(t1050)}, "sensor.b": {t1050: _stand_b(t1050)}})
    with _ha(svc):
        await snapshot_anlage(db, a, zeitpunkt=T)
        await snapshot_anlage_5min(db, a, zeitpunkt=t1050)
    reihe = await _reihe(db, a.id)
    assert reihe == {t1050: _stand_a(t1050), T: _stand_b(T)}


# ═══ Wechsel, dann Neustart (Startup-Recovery, §7 Nr. 1) ════════════════════════════════════════════════════════════════

class _FesteUhr(datetime):
    JETZT = datetime(2026, 10, 18, 12, 30)

    @classmethod
    def now(cls, tz=None):
        return cls.JETZT


@pytest.fixture
async def datei_db():
    from backend.tests import pv_achse_matrix as mx

    verz = tempfile.mkdtemp(prefix="eedc-sw1-")
    engine, s = await mx._neue_db(f"{verz}/x.db")
    await s.close()
    macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def sitzungen():
        async with macher() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise
    try:
        yield sitzungen
    finally:
        await engine.dispose()
        shutil.rmtree(verz, ignore_errors=True)


async def _neustart_lage(sitzungen, monkeypatch) -> dict[datetime, float]:
    import backend.core.database as dbmod
    import backend.services.energie_profil_service as eps
    from backend.core.config import settings as app_settings
    from backend.services import scheduler

    stunden = _stunden(datetime(2026, 10, 18, 6), datetime(2026, 10, 18, 12))      # die 7 Stunden der Recovery
    async with sitzungen() as s:
        a = await _anlage(s)
        aid = a.id
        for t in stunden:   # was der Stundenlauf geschrieben hatte: vor 11:00 A, ab 11:00 B
            s.add(SensorSnapshot(anlage_id=aid, sensor_key=KEY, zeitpunkt=t,
                                 wert_kwh=_stand_a(t) if t < T else _stand_b(t), quelle="ha_statistics"))
        await _wechsel(s, aid)
    svc = _recorder({"sensor.a": {t: _stand_a(t) for t in stunden}, "sensor.b": {t: _stand_b(t) for t in stunden}})

    async def null(*_a, **_k):
        return 0
    monkeypatch.setattr(dbmod, "get_session", sitzungen)
    monkeypatch.setattr(eps, "aggregate_today_all", null)
    monkeypatch.setattr(scheduler, "datetime", _FesteUhr)
    monkeypatch.setattr(app_settings, "live_snapshot_5min_enabled", False)
    with _ha(svc):
        await scheduler.sensor_snapshot_startup_recovery()
    async with sitzungen() as s:
        return await _reihe(s, aid)


async def test_b0_wechsel_dann_neustart_die_stunden_vor_dem_wechsel_bleiben_aus_a(datei_db, monkeypatch):
    reihe = await _neustart_lage(datei_db, monkeypatch)
    assert {t: w for t, w in reihe.items() if t < T} == {t: _stand_a(t) for t in reihe if t < T}
    assert len([t for t in reihe if t < T]) == 5 and reihe[T] == _stand_b(T)


async def test_b0_sprengsatz_neustart_ueberschreibt_mit_b(datei_db, monkeypatch):
    _sprengsatz(monkeypatch)
    reihe = await _neustart_lage(datei_db, monkeypatch)
    assert all(w == _stand_b(t) for t, w in reihe.items())                        # 06:00–10:00 auf B-Niveau


# ═══ LTS-Tag (`lts_tagestabelle` über `aggregate_day`): je Slot die Entität zum Stand ═══════════════════════════════════

def _lts_reihe(rate: float, start: float):
    from backend.tests.test_zaehlerluecken_lts_tabelle import _reihe as lts_reihe
    return lts_reihe(datetime(2026, 9, 18, 12), datetime(2026, 9, 22, 22), start, rate)


async def _lts(db, *, ab: datetime, vorher=A):
    from backend.services.snapshot import lts_aggregator
    from backend.tests.test_zaehlerluecken_lts_tabelle import _svc_sql

    a = Anlage(anlagenname="LTS", leistung_kwp=10.0, sensor_mapping={
        "basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.b"}}, "investitionen": {}})
    db.add(a)
    await db.flush()
    await _wechsel(db, a.id, key="basis:netzbezug", vorher=vorher, erklaert=ab)
    svc = _svc_sql({"sensor.a": _lts_reihe(0.5, 800.0), "sensor.b": _lts_reihe(1.0, 5000.0)})
    with patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=svc):
        return await lts_aggregator.lts_tagestabelle(
            SimpleNamespace(id=a.id, anlagenname="LTS", leistung_kwp=10.0, sensor_mapping=a.sensor_mapping), {}, D,
            **await lts_aggregator.wechsel_kwargs(db, a.id))


async def test_b0_lts_tag_vor_dem_wechsel_liest_a(db):
    tab = await _lts(db, ab=ERKLAERT)
    assert tab.komponenten_kwh["netzbezug"] == 12.0                                # 24 × 0,5 (A), nicht 24 × 1,0


async def test_b0_sprengsatz_lts_tag_liest_b(db, monkeypatch):
    _sprengsatz(monkeypatch)
    tab = await _lts(db, ab=ERKLAERT)
    assert tab.komponenten_kwh["netzbezug"] == 24.0


async def test_b0_lts_naht_im_tag_je_slot_eine_entitaet_kein_sprung(db):
    tab = await _lts(db, ab=datetime(2026, 9, 20, 11, 30))                         # ab_ts 12:00
    assert [tab.stunden[h]["netzbezug"] for h in (11, 12, 13)] == [0.5, 1.0, 1.0]  # Slot 12 = B(12) − B(11)
    assert tab.komponenten_kwh["netzbezug"] == 12 * 0.5 + 12 * 1.0


async def test_b0_lts_fruehere_quelle_ausserhalb_ha_faellt_auf_den_snapshot_pfad(db):
    assert await _lts(db, ab=ERKLAERT, vorher={"art": "mqtt", "mqtt_key": "netzbezug_kwh", "topic": None}) is None
    zw.vergiss(db)
    assert await _lts(db, ab=ERKLAERT, vorher=None) is None


# ═══ Live-Rückfall (`live_snapshot_if_missing`, Startup-Recovery der laufenden Stunde) ════════════════════════════════════

async def test_b0_live_rueckfall_schreibt_keinen_mqtt_wert_vor_dem_wechsel(db):
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.services.snapshot.fallback import live_snapshot_if_missing

    a = await _anlage(db)
    stunde = datetime(2026, 10, 18, 10)
    db.add(MqttEnergySnapshot(anlage_id=a.id, energy_key="inv/2/ladung_kwh", timestamp=stunde + timedelta(minutes=55),
                              value_kwh=99.0))
    await _wechsel(db, a.id, vorher=A, nachher={"art": "mqtt", "mqtt_key": "inv/2/ladung_kwh", "topic": None},
                   erklaert=datetime(2026, 10, 18, 10, 20))
    assert await live_snapshot_if_missing(db, a, zeitpunkt=stunde) == 0               # um 10:00 galt A (HA)
    assert await live_snapshot_if_missing(db, a, zeitpunkt=stunde + timedelta(hours=1)) == 1
    assert (await db.execute(select(func.count()).select_from(SensorSnapshot))).scalar_one() == 1


# ═══ Korrekturrunde 17.11. (Bauplan §8 Nr. 19–20, Nachmessung §2): weitere Proben, je mit Gegenprobe im selben Test ═══════


@pytest.mark.parametrize("vorher", [{"art": "mqtt", "mqtt_key": "inv/2/ladung_kwh", "topic": None}, {"art": "keine"}, None],
                         ids=["mqtt", "keine", "unbekannt"])
def test_schreib_map_fruehere_quelle_ausserhalb_ha_faellt_heraus(vorher):
    from backend.services.snapshot.writer import _build_counter_map

    anlage = SimpleNamespace(sensor_mapping={
        "investitionen": {"2": {"felder": {"ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.b"}}}},
        "quellen": {"inv_energy_2_ladung_kwh": {"quelle": "ha_app", "entity_id": "sensor.b"}}})
    wechsel = {KEY: [Wechsel(KEY, T, vorher, B)]}
    assert KEY not in _build_counter_map(anlage, set(), zeitpunkt=T - timedelta(hours=1), wechsel=wechsel)
    assert _build_counter_map(anlage, set(), zeitpunkt=T, wechsel=wechsel)[KEY] == "sensor.b"       # Gegenprobe


def test_schreib_map_stillgelegtes_geraet_bleibt_draussen():
    """Eine Stilllegung ist ein Geräte-Ende: die frühere Entität holt den Schlüssel nicht zurück (``anwenden.py``)."""
    from backend.services.snapshot.writer import _build_counter_map

    anlage = SimpleNamespace(sensor_mapping={
        "investitionen": {"2": {"felder": {"ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.b"}}}}})
    wechsel = {KEY: [Wechsel(KEY, T, A, B)]}
    vor = T - timedelta(hours=1)
    assert KEY not in _build_counter_map(anlage, {"2"}, zeitpunkt=vor, wechsel=wechsel)
    assert _build_counter_map(anlage, set(), zeitpunkt=vor, wechsel=wechsel)[KEY] == "sensor.a"     # Gegenprobe


async def _mqtt_zeile(db, anlage_id: int, key: str, t: datetime, wert: float):
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot

    db.add(MqttEnergySnapshot(anlage_id=anlage_id, energy_key=key, timestamp=t, value_kwh=wert))
    await db.flush()


async def test_b0_mqtt_schritt_frueher_ha_schreibt_keinen_mqtt_wert(db):
    """Heute MQTT (Standard-Inbound), früher A (HA, ohne Wert): vor dem Wechsel schreibt der MQTT-Schritt nichts."""
    from backend.services.snapshot.writer import snapshot_anlage

    a = Anlage(anlagenname="MQTT heute", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    db.add(Investition(id=2, anlage_id=a.id, typ="wallbox", bezeichnung="WB", anschaffungsdatum=date(2024, 11, 1)))
    vor, nach = T - timedelta(hours=2), T + timedelta(hours=1)
    for t in (vor, nach):
        await _mqtt_zeile(db, a.id, "inv/2/ladung_kwh", t, 77.0)
    await _wechsel(db, a.id, vorher=A, nachher={"art": "mqtt", "mqtt_key": "inv/2/ladung_kwh", "topic": None})
    with _ha(_recorder({"sensor.a": {}})):
        assert await snapshot_anlage(db, a, zeitpunkt=vor) == 0
        assert await snapshot_anlage(db, a, zeitpunkt=nach) == 1                     # Gegenprobe: ab ab_ts MQTT
    assert await _reihe(db, a.id) == {nach: 77.0}


async def test_b0_mqtt_schritt_frueher_mqtt_fuellt_trotz_heutiger_ha_zuordnung(db):
    """Heute HA (B), früher MQTT: vor dem Wechsel füllt der MQTT-Schritt die fehlende Zeile; danach nicht (C2b)."""
    from backend.services.snapshot.writer import snapshot_anlage

    a = await _anlage(db)
    vor, nach = T - timedelta(hours=2), T + timedelta(hours=1)
    for t in (vor, nach):
        await _mqtt_zeile(db, a.id, "inv/2/ladung_kwh", t, 55.0)
    await _wechsel(db, a.id, vorher={"art": "mqtt", "mqtt_key": "inv/2/ladung_kwh", "topic": None}, nachher=B)
    with _ha(_recorder({"sensor.b": {}})):
        assert await snapshot_anlage(db, a, zeitpunkt=vor) == 1
        assert await snapshot_anlage(db, a, zeitpunkt=nach) == 0                     # Gegenprobe: heute HA, kein MQTT
    assert await _reihe(db, a.id) == {vor: 55.0}


async def test_b0_heilen_vor_dem_wechsel_ohne_mqtt_rueckfall(db):
    """Galt um z die HA-Entität A und führt HA dort nichts, heilt der Leser NICHT aus MQTT; ab ``ab_ts`` (heute) wie bisher."""
    from backend.services.snapshot.keys import extract_quellen_energy
    from backend.services.snapshot.reader import get_snapshot

    key = "inv:2:ladung_pv_kwh"
    a = await _anlage(db, key_feld="ladung_pv_kwh")
    await _wechsel(db, a.id, key=key)
    vor, nach = datetime(2026, 9, 21, 0, 0), T + timedelta(hours=1)
    for t in (vor, nach):
        await _mqtt_zeile(db, a.id, "inv/2/ladung_pv_kwh", t, 42.0)
    svc = _recorder({"sensor.a": {}, "sensor.b": {}})
    with patch("backend.services.snapshot.reader.get_ha_statistics_service", lambda: svc):
        q = extract_quellen_energy(a)
        assert await get_snapshot(db, a.id, key, "sensor.b", vor, quellen_energy=q) is None
        assert await get_snapshot(db, a.id, key, "sensor.b", nach, quellen_energy=q) == 42.0       # Gegenprobe
    assert await _reihe(db, a.id, key) == {nach: 42.0}


async def test_b0_lts_fruehere_entitaet_fehlt_in_ha(db):
    assert await _lts(db, ab=ERKLAERT, vorher={"art": "ha", "entity_id": "sensor.c"}) is None      # Snapshot-Pfad
    zw.vergiss(db)
    assert (await _lts(db, ab=ERKLAERT)).komponenten_kwh["netzbezug"] == 12.0                      # Gegenprobe: A da


async def test_aggregate_day_reicht_die_wechsel_an_den_lts_tag(db, monkeypatch):
    """``energie_profil/aggregator.lade_zaehler_und_counter`` gibt ``lts_tagestabelle`` die Wechsel der Anlage mit — ohne
    Wechsel ruft er wörtlich wie vorher (kein Argument)."""
    from backend.services.energie_profil.aggregator import lade_zaehler_und_counter
    from backend.services.snapshot import lts_aggregator

    aufrufe: list[dict] = []

    async def spion(*_a, **kw):
        aufrufe.append(kw)
        return None
    monkeypatch.setattr(lts_aggregator, "lts_tagestabelle", spion)
    a = await _anlage(db)
    await lade_zaehler_und_counter(a, D, db)
    await _wechsel(db, a.id)
    await lade_zaehler_und_counter(a, D, db)
    assert "wechsel" not in aufrufe[0]                                              # Gegenprobe: ohne Wechsel
    assert [w.ab_ts for w in aufrufe[1]["wechsel"][KEY]] == [T]


async def _vorschau_lage(db):
    from backend.services.snapshot.reaggregator import get_reaggregate_preview

    a = await _anlage(db)
    inv = (await db.execute(select(Investition).where(Investition.id == 2))).scalar_one()
    fehlt = {FENSTER[4]}
    for t in FENSTER:
        if t not in fehlt:
            db.add(SensorSnapshot(anlage_id=a.id, sensor_key=KEY, zeitpunkt=t, wert_kwh=_alt_stand(t), quelle="ha_statistics"))
    await _wechsel(db, a.id)
    stunden = _stunden(TAG0 - timedelta(hours=3), TAG0 + timedelta(days=1, hours=3))
    svc = _recorder({"sensor.a": {t: _stand_a(t) for t in stunden}, "sensor.b": {t: _stand_b(t) for t in stunden}})
    with patch("backend.services.snapshot.reaggregator.get_ha_statistics_service", lambda: svc), \
            patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", lambda: svc):
        v = await get_reaggregate_preview(db, a, {"2": inv}, D)
    return {b["zeitpunkt"]: (b["alt_kwh"], b["neu_kwh"]) for b in v["boundaries"] if b["sensor_key"] == KEY}, fehlt


async def test_vorschau_zeigt_was_der_lauf_schreibt(db):
    """§8 Nr. 19: vor dem Wechsel «neu» = vorhandene Zeile; eine fehlende kommt aus A (wie der Lauf, Probe oben)."""
    grenzen, fehlt = await _vorschau_lage(db)
    assert len(grenzen) == 25
    assert all(neu == alt for t, (alt, neu) in grenzen.items() if t not in fehlt)
    assert {t: grenzen[t] for t in fehlt} == {t: (None, _stand_a(t)) for t in fehlt}


async def test_sprengsatz_vorschau_mit_der_heutigen_entitaet(db, monkeypatch):
    _sprengsatz(monkeypatch)
    grenzen, _fehlt = await _vorschau_lage(db)
    assert all(neu == _stand_b(t) for t, (_alt, neu) in grenzen.items())                # Nachmessung §7: 3 615,024 …


async def test_kurzzeit_probe_einmal_je_entitaet_und_stunde(db, monkeypatch):
    """§8 Nr. 20: «Tag neu aggregieren» fragt die Kurzzeit-Reichweite je Entität und Stunde einmal (nicht je Slot) —
    Gegenprobe: ohne Merkliste des Laufs elfmal."""
    _sprengsatz(monkeypatch)
    from backend.services.snapshot.reaggregator import resnap_anlage_range
    from backend.services.snapshot.writer import snapshot_anlage_5min

    a = await _anlage(db)
    svc = _recorder({"sensor.b": {}})
    proben: list = []
    echt = svc.get_value_at

    def zaehle(eid, zp, toleranz_minuten=120, short_term=False, als_stand=False):
        if short_term and als_stand:
            proben.append((eid, zp))
        return echt(eid, zp, toleranz_minuten, short_term, als_stand)
    monkeypatch.setattr(svc, "get_value_at", zaehle)
    with _ha(svc):
        await resnap_anlage_range(db, a, von=TAG0 + timedelta(hours=10), bis=TAG0 + timedelta(hours=11))
        assert len(proben) == 1
        proben.clear()
        for zp in FUENF:
            await snapshot_anlage_5min(db, a, zeitpunkt=zp, force=True, force_resnap=True)
    assert len(proben) == len(FUENF) == 11
