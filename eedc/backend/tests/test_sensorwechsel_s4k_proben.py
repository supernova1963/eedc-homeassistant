"""Sensorwechsel mit Grund, Korrekturrunde 4-K (Bauplan §13 Nr. 66–73; Nachmessung Sitzung 4, F1 … F8, H-2) — der Rest nach
Weg B.

* **F3** (Nr. 68): Nachtrag und Einstieg treffen im Nachbau-Abschnitt aus HA-Ständen bei einem Wechsel zur vollen Stunde
  dieselbe Stunde wie ``nachfuellen._laeufe``; im Stundenlauf der Mitschrift bleibt es die Stunde des Zeitpunkts; an der Grenze
  Nachbau → Stundenlauf trifft die Naht die Stunde vor ``ab_ts`` (Nr. 91 e, bis Sitzung B3a in den Stück-Proben).

Die Proben zu F1 (Nachtrag), F2/F8 und Nr. 84 (Korrektur), F4 (MQTT-Vorschau im Nachtrag), H-2 (a) (``zaehler_versatz``) und
Nr. 73 (Korrektur im Nachtrag) sind mit «Grund nachtragen» (Weg B, Sitzung B2) bzw. der Korrektur und dem Befund (Sitzung B3a)
entfernt.

Schwesterdateien: test_sensorwechsel_s4_nachtrag.py (Sitzung 4), test_kanal_eigene_summe_nachfuellen.py (Stände-Nachbau).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import and_, select

from backend.models.investition import Investition
from backend.models.kanal import Kanal, KanalStatistik
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw
from backend.tests.test_sensorwechsel_s1_verzeichnen import NETZ, NETZ_KEY, _anlage, _quelle, _zeilen
from backend.tests.test_sensorwechsel_s4_nachtrag import (
    A, B, T, _mit_b, _wechsel,
)


# ═══ F3 — volle Stunde im Nachbau-Abschnitt ══════════════════════════════════════════════════════════════════════════

FOLGE = {0: 100.0, 1: 101.0, 2: 102.0, 3: 2103.0, 4: 2104.0, 5: 2105.0}    # der Stand zur Stunde 03:00 ist der erste neue


@pytest.fixture
async def datei():
    from backend.tests import test_kanal_eigene_summe_nachfuellen as e

    async for x in e.datei.__wrapped__():
        yield x


async def _nachbau(datei, *, quelle: str, mapping: dict, name: str = "x"):
    from backend.services.kanal.nachfuellen import nachfuellen_eigene_summe
    from backend.tests import test_kanal_eigene_summe_nachfuellen as e

    sitzungen, aid = await datei(name, mapping=mapping)
    await e._staende(sitzungen, aid, NETZ_KEY, FOLGE, quelle=quelle)
    await nachfuellen_eigene_summe(sitzungen, aid, jetzt=e.JETZT)

    async def zuw():
        _k, zeilen, quellen = await e._kanal(sitzungen, aid, NETZ_KEY)
        return {datetime.fromtimestamp(t).strftime("%H:%M"): round(w, 3) for t, w in e._zuwaechse(zeilen, quellen).items()}
    return sitzungen, aid, zuw


async def test_f3_fortsetzung_zur_vollen_stunde_teilt_den_nachbau(datei):
    """Nachbau aus HA-Ständen (Kennung ``sensor_snapshots:…``): ohne Wechsel zählt die Zeile 02:00 den Sprung (2 001); mit einer
    verzeichneten Fortsetzung genau um 03:00:00 — der Stand 03:00 ist neu, er steht in der Zeile 02:00 — teilt der
    Stände-Nachbau dort (``_laeufe``): die Zeile 02:00 zählt 0, die Stunde 03:00 zählt 1,0. (Bis Weg B prüfte die Probe auch
    «Fortsetzung nachtragen» gegen diesen Schnitt; der Nachtrag ist in Sitzung B2 entfernt.)"""
    from backend.services.kanal.nachfuellen import nachfuellen_eigene_summe
    from backend.tests import test_kanal_eigene_summe_nachfuellen as e

    _sitzungen, _aid, zuw = await _nachbau(datei, quelle="ha_statistics",
                                           mapping={"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.b"}},
                                                    "investitionen": {}})
    assert (await zuw())["02:00"] == 2001.0
    wechsel = e.T0 + timedelta(hours=3)
    s2, aid2 = await datei("teilt", mapping={"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.b"}},
                                             "investitionen": {}})
    async with s2() as s:
        s.add(ZuordnungWechsel(anlage_id=aid2, sensor_key=NETZ_KEY, erklaert_ts=wechsel, ab_ts=wechsel, vorher=A, nachher=B,
                               grund="fortsetzung", herkunft="wechsel"))
    await e._staende(s2, aid2, NETZ_KEY, FOLGE, quelle="ha_statistics")
    await nachfuellen_eigene_summe(s2, aid2, jetzt=e.JETZT)
    _k, zeilen, quellen = await e._kanal(s2, aid2, NETZ_KEY)
    geteilt = {datetime.fromtimestamp(t).strftime("%H:%M"): round(w, 3) for t, w in e._zuwaechse(zeilen, quellen).items()}
    assert (geteilt["02:00"], geteilt["03:00"]) == (0.0, 1.0)


async def test_f3_einstieg_zur_vollen_stunde_nennt_den_zuwachs_der_stunde_die_null_zaehlt(datei):
    """Einstieg «Zähler getauscht» um 03:00 im Nachbau-Abschnitt aus HA-Ständen: Vorschau nennt die Stunde 02:00 mit dem
    Zuwachs, den sie bisher zählt (2 001); nach dem Eintrag zählt genau sie 0."""
    from backend.api.routes import sensorwechsel as sw
    from backend.tests import test_kanal_eigene_summe_nachfuellen as e

    sitzungen, aid, zuw = await _nachbau(datei, quelle="ha_statistics",
                                         mapping={"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.b"}},
                                                  "investitionen": {}})
    req = sw.ZaehlerGetauschtRequest(getauscht_am=e.T0 + timedelta(hours=3))
    async with sitzungen() as s:
        p = await sw.pruefe_zaehler_getauscht(aid, NETZ, req, s)
    assert p["weg"] == "fortsetzung"
    assert "Die Stunde ab 10.06.2026 02:00 Uhr ist schon gespeichert" in p["saetze"][1]
    assert p["saetze"][2] == "Bisher zählt sie 2.001,00 kWh."
    from backend.services.zuordnung_wechsel.zaehler_getauscht import lage as zg_lage
    assert len(p["saetze"]) == 3                                         # U3 a (G3): ohne festen Tageswert kein Satz dazu
    async with sitzungen() as s:
        from backend.models.anlage import Anlage
        an = await s.get(Anlage, aid)
        am_tag = await zg_lage(s, an, NETZ_KEY, e.T0 + timedelta(hours=3), heute=e.T0.date())
        danach = await zg_lage(s, an, NETZ_KEY, e.T0 + timedelta(hours=3), heute=e.T0.date() + timedelta(days=1))
    assert (am_tag.vor_heute, danach.vor_heute) == (False, True)       # am laufenden Tag kein Zusatz
    async with sitzungen() as s:
        await sw.zaehler_getauscht(aid, NETZ, req, s)
    nach = await zuw()
    assert (nach["02:00"], nach["03:00"]) == (0.0, 1.0)


async def test_f3_mitschrift_des_stundenlaufs_bleibt_bei_der_stunde_des_zeitpunkts(db):
    """Außerhalb des Nachbau-Abschnitts (Stundenlauf der Mitschrift: ein Rohstand gehört zur Stunde, in der er eintraf) trägt
    bei einem Publisher-Wechsel genau um 02:00:00 die Zeile 02:00 den Sprung (gemessen ohne Wechsel-Zeile: Δ 2 002), und mit
    verzeichneter Fortsetzung beginnt dort die neue Periode (Δ 1,0 ab ihrem ersten Stand). ``naht_stunde`` nennt diese Stunde
    — unverändert gegenüber Sitzung 4 (die Stunde, in der der Zeitpunkt liegt)."""
    from backend.services.zuordnung_wechsel.zaehler_getauscht import naht_stunde
    from backend.tests import test_sensorwechsel_s2_naht as n

    folge = {0: [(0, 1000.0), (30, 1001.0)], 1: [(0, 1002.0), (45, 1003.0)], 2: [(0, 3004.0), (30, 3005.0)],
             3: [(0, 3006.0)], 4: [(0, 3007.0)]}
    a = await n._mqtt_anlage(db)
    await n._mqtt_staende(db, a.id, folge)
    await n._mqtt_lauf(db, a, [1, 2, 3, 4, 5])
    k = await n._kanal_der_anlage(db, a)
    assert await n._kanal_delta(db, a, 2, 3) == pytest.approx(2002.0)          # ohne Wechsel-Zeile: die Zeile 02:00
    assert await naht_stunde(db, k, n.T0 + timedelta(hours=2)) == n._h(2)
    await db.execute(KanalStatistik.__table__.delete().where(KanalStatistik.kanal_id == k.id))
    from backend.models.kanal import KanalQuelle
    await db.execute(KanalQuelle.__table__.delete().where(KanalQuelle.kanal_id == k.id))
    await n._mqtt_wechsel(db, a.id, n.T0 + timedelta(hours=2))
    await db.commit()
    zw.vergiss(db)
    await n._mqtt_lauf(db, a, [1, 2, 3, 4, 5])
    assert await n._kanal_delta(db, a, 2, 3) == pytest.approx(1.0)            # die neue Periode ab 3 004
    assert await n._kanal_delta(db, a, 1, 4) == pytest.approx(2.0 + 1.0 + 1.0)       # 1 001 → 1 003, dann 1 und 1
    assert await naht_stunde(db, k, n.T0 + timedelta(hours=2)) == n._h(2)


async def test_nr91e_nachbau_wird_an_der_stunde_vor_ab_ts_geprueft(monkeypatch):
    """Der Wechsel genau zur vollen Stunde Z an der Grenze Nachbau → Stundenlauf: die Stunde vor ``ab_ts`` (Z − 1 h) liegt im
    Nachbau-Abschnitt aus HA-Ständen, die Stunde Z im Stundenlauf — die Naht trifft Z − 1 h (geprüft wird vor ``ab_ts``)."""
    import backend.services.kanal.angaben as angaben
    from backend.services.kanal.nachfuellen import STAENDE_HA_PRAEFIX
    from backend.services.zuordnung_wechsel.zaehler_getauscht import naht_stunde

    z = datetime(2026, 6, 10, 3)
    zt = int(z.timestamp())

    async def quelle(_db, _kid, ts):
        return SimpleNamespace(statistic_id=f"{STAENDE_HA_PRAEFIX}x" if ts < zt else None, familie="mitschrift")
    monkeypatch.setattr(angaben, "quelle_zur_stunde", quelle)
    assert await naht_stunde(None, SimpleNamespace(id=1), z) == zt - 3600
    assert await naht_stunde(None, SimpleNamespace(id=1), z + timedelta(minutes=30)) == zt
