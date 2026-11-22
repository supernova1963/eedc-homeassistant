"""Sensorwechsel mit Grund, Sitzung 4 «Nachtrag» — der Rest nach Weg B (Sitzung B2).

«Grund nachtragen» an einem verzeichneten Wechsel, der Befund «Zuordnung geändert, Grund fehlt» und die Überführung der
Alt-Vermerke ``historie_hinweis`` sind entfernt (Entscheid Gernot 21.11.2026); ihre Proben sind mit ihnen gegangen. Geblieben:

* **Kanal:** ``kanal/naht.nachtrag_fortsetzung`` (der Weg von «Zähler getauscht») verwirft nur die abhängigen abgeleiteten
  Kanäle (§10 Nr. 34); im Stände-Nachbau teilt eine Fortsetzung den Lauf (``nachfuellen._laeufe``).
* **Rücksprung** an einer Fortsetzungs-Naht ist keiner (``reader.finde_zaehler_ruecksprunge``).

Die Helfer ``A``, ``B``, ``KEINE``, ``T``, ``_mit_b``, ``_wechsel``, ``_abgelehnt`` nutzen die Schwesterdateien.

Schwesterdateien: test_sensorwechsel_s3b_abfrage.py (Abfrage, Einstieg), test_sensorwechsel_s2_naht.py (Naht und Nachtrag bei
MQTT).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import and_, select

from backend.models.activity_log import ActivityLog
from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.tests.test_sensorwechsel_s1_verzeichnen import NETZ, NETZ_KEY, _anlage, _zeilen

A = {"art": "ha", "entity_id": "sensor.a"}
B = {"art": "ha", "entity_id": "sensor.b"}
KEINE = {"art": "keine"}
T = datetime(2026, 9, 10, 10, 47, 42)
AB = datetime(2026, 9, 10, 11)


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())


async def _mit_b(db, *, werte=(NETZ_KEY,)):
    """Anlage, heute auf ``sensor.b``; eigene Werte am 1.9. (vor dem Wechsel) und danach."""
    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.b"}}}, werte=werte)
    for t, w in ((datetime(2026, 9, 5, 12), 20.0), (datetime(2026, 9, 12, 12), 900.0)):
        db.add(SensorSnapshot(anlage_id=a.id, sensor_key=NETZ_KEY, zeitpunkt=t, wert_kwh=w, quelle="ha_statistics"))
    await db.flush()
    return a


async def _wechsel(db, aid, vorher=A, nachher=B, *, erklaert=T, grund=None, herkunft="altbestand", key=NETZ_KEY):
    row = ZuordnungWechsel(anlage_id=aid, sensor_key=key, erklaert_ts=erklaert, ab_ts=erklaert.replace(minute=0, second=0)
                           + (timedelta(hours=1) if erklaert.minute or erklaert.second else timedelta()), vorher=vorher,
                           nachher=nachher, grund=grund, herkunft=herkunft)
    db.add(row)
    await db.flush()
    return row


async def _abgelehnt(coro) -> HTTPException:
    with pytest.raises(HTTPException) as e:
        await coro
    return e.value


# ═══ Kanal: Mitschrift, Nachbau-Abschnitt, abhängige abgeleitete Kanäle ═════════════════════════════════════════════════

async def _mitschrift(db, aid, key, werte, *, t0, statistic_id="netzbezug_kwh"):
    k = Kanal(anlage_id=aid, key=key, einheit="kWh", art="sum")
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=_ts(t0), familie="mitschrift", statistic_id=statistic_id, offset=0.0))
    for i, w in enumerate(werte):
        db.add(KanalStatistik(kanal_id=k.id, start_ts=_ts(t0 + timedelta(hours=i)), sum=w, state=w, familie="mitschrift"))
    await db.flush()
    return k


def test_nachbau_teilt_an_einer_fortsetzung():
    """Der Stände-Nachbau (``_laeufe``) beginnt an einer verzeichneten Fortsetzung einen neuen Lauf; mit den Versätzen von
    hinten (``_offsets_rueckwaerts``) setzt er am Kanalwert des vorigen an — die Naht zählt nicht als Zuwachs."""
    from types import SimpleNamespace

    from backend.services.kanal.nachfuellen import _laeufe, _offsets_rueckwaerts

    t0 = datetime(2025, 3, 1, 0)
    staende = [(t0 + timedelta(hours=i), w, "ha") for i, w in enumerate((10.0, 11.0, 512.0, 513.0))]
    ziel = SimpleNamespace(kennung=lambda h: h)
    assert [len(x.staende) for x in _laeufe(staende, ziel)] == [4]
    naht = t0 + timedelta(hours=3)                                  # Stand 512 (Ende der Stunde 02:00) ist der erste neue
    laeufe = _laeufe(staende, ziel, [naht])
    assert [[w for _t, w in x.staende] for x in laeufe] == [[10.0, 11.0], [512.0, 513.0]]
    for x in laeufe:
        x.zeilen = [{"sum": w, "state": w} for _t, w in x.staende]
    _offsets_rueckwaerts(laeufe, "sum", None)
    assert laeufe[0].zeilen[-1]["sum"] + laeufe[0].offset == pytest.approx(laeufe[1].zeilen[0]["sum"] + laeufe[1].offset)


async def test_nachtrag_verwirft_nur_abhaengige_abgeleitete(db):
    """§10 Nr. 34: der Nachtrag an einem Speicher-Feld (aus ihm rechnet kein abgeleiteter Kanal) lässt PV-Anteil und Kosten
    stehen; am Netzbezug verwirft er beide (ab der Stunde)."""
    from backend.models.investition import Investition
    from backend.services.kanal.abgeleitet import abgeleitet_key
    from backend.services.kanal.naht import nachtrag_fortsetzung

    a = await _anlage(db, werte=())
    aid = a.id
    db.add(Investition(id=7, anlage_id=aid, typ="speicher", bezeichnung="Akku", anschaffungsdatum=datetime(2024, 1, 1).date()))
    await db.flush()
    t0 = datetime(2026, 11, 10, 8)
    abg = {}
    for key in (abgeleitet_key(2), "abgeleitet:basis:kosten_netzbezug"):
        k = Kanal(anlage_id=aid, key=key, einheit="kWh", art="sum")
        db.add(k)
        await db.flush()
        db.add_all([KanalStatistik(kanal_id=k.id, start_ts=_ts(t0 + timedelta(hours=i)), sum=float(i), familie="abgeleitet")
                    for i in range(4)])
        abg[key] = k.id
    speicher = await _mitschrift(db, aid, "inv:7:ladung_kwh", (1.0, 2.0, 500.0, 501.0), t0=t0, statistic_id="inv/7/ladung_kwh")
    netz = await _mitschrift(db, aid, NETZ_KEY, (1.0, 2.0, 500.0, 501.0), t0=t0)
    await db.commit()

    async def zeilen():
        return {key: len((await db.execute(select(KanalStatistik.start_ts).where(KanalStatistik.kanal_id == kid))).all())
                for key, kid in abg.items()}

    await nachtrag_fortsetzung(db, speicher.id, _ts(t0 + timedelta(hours=2)))
    assert await zeilen() == {abgeleitet_key(2): 4, "abgeleitet:basis:kosten_netzbezug": 4}
    await nachtrag_fortsetzung(db, netz.id, _ts(t0 + timedelta(hours=2)))
    assert await zeilen() == {abgeleitet_key(2): 2, "abgeleitet:basis:kosten_netzbezug": 2}


# ═══ Rücksprung an einer Fortsetzungs-Naht ═══════════════════════════════════════════════════════════════════════════

async def test_ruecksprung_an_einer_fortsetzung_ist_keiner(db):
    from backend.services.snapshot.reader import finde_zaehler_ruecksprunge

    a = await _anlage(db, werte=())
    aid = a.id
    t0 = datetime(2026, 11, 1, 0)
    for i, w in enumerate((1050.0, 1051.0, 525.0, 526.0)):                     # anderer Publisher, Niveau tiefer
        db.add(SensorSnapshot(anlage_id=aid, sensor_key=NETZ_KEY, zeitpunkt=t0 + timedelta(hours=i), wert_kwh=w, quelle="mqtt_inbound"))
    await db.commit()
    von, bis = t0 - timedelta(hours=1), t0 + timedelta(days=1)
    assert len(await finde_zaehler_ruecksprunge(db, aid, NETZ_KEY, von, bis)) == 1
    assert await finde_zaehler_ruecksprunge(db, aid, NETZ_KEY, von, bis, naehte=(t0 + timedelta(hours=2),)) == []
    assert len(await finde_zaehler_ruecksprunge(db, aid, NETZ_KEY, von, bis, naehte=(t0 + timedelta(hours=3),))) == 1


async def test_befund_ruecksprung_schweigt_an_einer_verzeichneten_fortsetzung(db):
    from backend.services.daten_checker import DatenChecker

    a = await _anlage(db, werte=())
    aid = a.id
    jetzt = datetime(2026, 11, 2, 12)
    t0 = datetime(2026, 11, 1, 0)
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot

    for i, w in enumerate((1050.0, 1051.0, 525.0, 526.0)):
        db.add(SensorSnapshot(anlage_id=aid, sensor_key=NETZ_KEY, zeitpunkt=t0 + timedelta(hours=i), wert_kwh=w, quelle="mqtt_inbound"))
        db.add(MqttEnergySnapshot(anlage_id=aid, timestamp=t0 + timedelta(hours=i), energy_key="netzbezug_kwh", value_kwh=w))
    await db.commit()
    assert [e.code for e in await DatenChecker(db)._check_zaehler_ruecksprung(a, jetzt=jetzt)] == ["zaehler_ruecksprung"]
    await _wechsel(db, aid, {"art": "mqtt"}, {"art": "mqtt"}, erklaert=t0 + timedelta(hours=1, minutes=30),
                   grund="fortsetzung", herkunft="wechsel")
    await db.commit()
    from backend.services.zuordnung_wechsel.zeitpunkt import vergiss
    vergiss(db)
    assert await DatenChecker(db)._check_zaehler_ruecksprung(a, jetzt=jetzt) == []
