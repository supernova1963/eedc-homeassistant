"""Sensorwechsel mit Grund, Sitzung 4 «Nachtrag» (Bauplan B-7, §10 Nr. 34, §12 Nr. 61–64; Konzept S-6, S-10 a/c/d).

* **Befund «Zuordnung geändert, Grund fehlt»** (``daten_checker/datenquelle/grund_fehlt.py``): nur für verzeichnete Wechsel
  ohne Grund, nach denen die Abfrage gefragt hätte (``abfrage.haette_gefragt`` — die eine Prüf-Funktion), Handgriff
  «Grund nachtragen» als Sprung in die Datenquellen mit ``nachtrag=<id>``.
* **Grund nachtragen** (``zuordnung_wechsel/nachtrag.py``, Routen ``…/zuordnung-wechsel/{id}/grund[/pruefen]``): Fortsetzung als
  Zeile ``herkunft = nachtrag`` (die alte wird aufgehoben, ``erklaert_ts`` bleibt der Wechsel), im Kanal der Nachtrag der
  Mitschrift; Korrektur über den Dienst (Vorschau = Lauf), nur am jüngsten Wechsel mit heutiger Quelle; Fortsetzung → Korrektur
  ja, Korrektur → nichts.
* **Überführung der Alt-Vermerke** ``historie_hinweis`` (``ueberfuehrung.ueberfuehre_vermerke``): je Feld der jüngste
  Protokoll-Eintrag, nur was die Abfrage gefragt hätte, keine Doppelzeile; danach kein Vermerk; zweimal = einmal.
* **Kanal:** der Nachtrag verwirft nur die abhängigen abgeleiteten Kanäle (§10 Nr. 34); im Stände-Nachbau teilt eine
  Fortsetzung den Lauf (``nachfuellen._laeufe``), ein Nachtrag im Nachbau-Abschnitt (HA-Stände wörtlich, Familie Mitschrift)
  erreicht die Kanal-Sicht (§12 Nr. 61).
* **Rücksprung** an einer Fortsetzungs-Naht ist keiner (``reader.finde_zaehler_ruecksprunge``).
* **Probe heilbare Lage** des Befunds ``zaehler_versatz`` nach «Kanal vor Reihe»: wirkt noch, wo der eigene Kanal am Rand-Tag
  eine Lücke hat.

Die Sprengsätze (bewusst falsche Bausteine, gegen die je Probe rot gemessen) stehen im Bericht der Sitzung
(``opus-berichte/SENSORWECHSEL-S4-2026-11-18.md``).

Schwesterdateien: test_sensorwechsel_s3b_abfrage.py (Abfrage, Einstieg), test_sensorwechsel_s3_korrektur.py (Dienst der
Korrektur), test_sensorwechsel_s2_naht.py (Naht und Nachtrag bei MQTT), test_daten_checker_zaehler_versatz.py.
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
from backend.tests.test_daten_checker_zaehler_versatz import JETZT, _pruefe as _versatz_pruefe, ha  # noqa: F401 — Fixture
from backend.tests.test_daten_checker_zaehler_versatz import _anlage as _versatz_anlage
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


async def _befunde(db, a):
    from backend.services.daten_checker import DatenChecker

    return await DatenChecker(db)._check_zuordnung_grund_fehlt(a)


async def _pruefen(db, aid, wid, **kw):
    from backend.api.routes.sensorwechsel import GrundNachtragRequest, pruefe_grund_nachtragen

    return await pruefe_grund_nachtragen(aid, wid, GrundNachtragRequest(**kw), db)


async def _nachtragen(db, aid, wid, **kw):
    from backend.api.routes.sensorwechsel import GrundNachtragRequest, grund_nachtragen

    return await grund_nachtragen(aid, wid, GrundNachtragRequest(**kw), db)


async def _abgelehnt(coro) -> HTTPException:
    with pytest.raises(HTTPException) as e:
        await coro
    return e.value


# ═══ Wann der Befund kommt (über die Abfrage, B-2) ══════════════════════════════════════════════════════════════════════

async def test_haette_gefragt_wie_die_abfrage(db):
    from backend.services.zuordnung_wechsel.abfrage import haette_gefragt

    a = await _mit_b(db)
    aid = a.id
    assert await haette_gefragt(db, aid, await _wechsel(db, aid, A, B))                       # A → B, eigene Werte
    assert not await haette_gefragt(db, aid, await _wechsel(db, aid, A, KEINE, erklaert=T + timedelta(days=1)))  # → «Keine»
    assert not await haette_gefragt(db, aid, await _wechsel(db, aid, B, B, erklaert=T + timedelta(days=2)))      # getauscht
    ohne = await _wechsel(db, aid, A, B, erklaert=datetime(2026, 8, 1, 10, 5))                 # vor dem ersten Wert
    assert not await haette_gefragt(db, aid, ohne)


async def test_a_keine_a_nicht_a_keine_b_schon(db):
    from backend.services.zuordnung_wechsel.abfrage import haette_gefragt
    from backend.services.zuordnung_wechsel.zeitpunkt import vergiss

    a = await _mit_b(db)
    aid = a.id
    await _wechsel(db, aid, A, KEINE, erklaert=datetime(2026, 9, 6, 9, 30))
    zurueck = await _wechsel(db, aid, KEINE, A)
    vergiss(db)
    assert not await haette_gefragt(db, aid, zurueck)                   # A → «Keine» → A: die letzte Quelle mit Werten
    anders = await _wechsel(db, aid, KEINE, B, erklaert=T + timedelta(days=1))
    vergiss(db)
    assert await haette_gefragt(db, aid, anders)                        # A → «Keine» → B


async def test_befund_grund_fehlt_nur_fuer_gefragte_wechsel_ohne_grund(db):
    from backend.services.zuordnung_wechsel.zeitpunkt import vergiss

    a = await _mit_b(db)
    aid = a.id
    row = await _wechsel(db, aid)
    await _wechsel(db, aid, B, KEINE, erklaert=T + timedelta(days=1))            # → «Keine»: kein Befund
    await _wechsel(db, aid, A, B, erklaert=T + timedelta(days=2), grund="fortsetzung")
    weg = await _wechsel(db, aid, A, B, erklaert=T + timedelta(days=3))
    weg.aufgehoben_durch = row.id
    await db.commit()
    vergiss(db)
    (e,) = await _befunde(db, a)
    assert (e.code, e.kategorie, e.schwere, e.klasse, e.knopf) == (
        "zuordnung_grund_fehlt", "zuordnung_grund_fehlt", "warning", "sprung", "Grund nachtragen")
    assert (e.ziel.bereich, e.ziel.params) == ("datenquellen", {"feld": "netzbezug_kwh", "nachtrag": row.id})
    assert e.meldung == "Netzbezug: Zuordnung am 10.09.2026 geändert — Grund fehlt"
    assert "Am 10.09.2026 10:47 Uhr wechselte die Quelle dieses Felds von sensor.a zu sensor.b" in e.details
    assert e.werte == {"schluessel": NETZ_KEY, "wechsel_id": row.id, "herkunft": "altbestand", "wechsel": "2026-09-10T10:47"}


async def test_ohne_wechsel_keine_zeile(db):
    a = await _mit_b(db)
    assert await _befunde(db, a) == []


# ═══ Grund nachtragen: Prüfen ═══════════════════════════════════════════════════════════════════════════════════════════

async def test_pruefen_nennt_gruende_und_schreibt_nichts(db):
    from backend.tests.test_sensorwechsel_s3b_abfrage import _zaehlung

    a = await _mit_b(db)
    aid = a.id
    row = await _wechsel(db, aid)
    await db.commit()
    vorher = await _zaehlung(db)
    p = await _pruefen(db, aid, row.id)
    assert (p["gruende"], p["korrektur_nicht"], p["grund_erforderlich"], p["sensor_key"]) == (
        ["fortsetzung", "korrektur"], None, True, NETZ_KEY)
    assert p["wechsel_satz"] == "Am 10.09.2026 10:47 Uhr wechselte die Quelle von sensor.a zu sensor.b."
    assert (p["erster_wert"], p["vorgabe_falsch_seit"], p["feld_id"]) == ("2026-09-01T12:00:00", "2026-09-01T12:00:00", NETZ)
    k = await _pruefen(db, aid, row.id, grund="korrektur", falsch_seit=datetime(2026, 9, 3))
    assert k["korrektur"]["zaehlerstaende"] == 1 and k["korrektur"]["startbar"] is True    # der Stand vom 5.9.
    assert await _zaehlung(db) == vorher
    e = await _abgelehnt(_pruefen(db, aid, row.id, grund="korrektur", falsch_seit=AB))
    assert e.status_code == 422 and "vor dem Wechsel" in e.detail
    assert (await _abgelehnt(_pruefen(db, aid, 9999))).status_code == 404
    assert (await _abgelehnt(_pruefen(db, aid, row.id, grund="weiss_nicht"))).status_code == 400


async def test_vorgabe_falsch_seit_ist_der_beginn_der_quelle_vor_dem_wechsel(db):
    """Ohne früheren Wechsel: der Beginn des Kanal-Abschnitts, der vor der Stunde des Wechsels galt (nicht der jüngste —
    die neue Quelle trägt die Stunde des Wechsels selbst); mit einem früheren Wechsel, der die Quelle brachte, dessen ab_ts."""
    a = await _mit_b(db)
    aid = a.id
    k = Kanal(anlage_id=aid, key=NETZ_KEY, einheit="kWh", art="sum")
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=_ts(datetime(2026, 8, 20, 5)), familie="spiegel", statistic_id="sensor.a",
                       offset=0.0))
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=_ts(datetime(2026, 9, 10, 10)), familie="spiegel", statistic_id="sensor.b",
                       offset=-50.0))
    row = await _wechsel(db, aid)
    await db.commit()
    # die Quellzeile ist älter als jeder eigene Wert (erster Wert 1.9. 12:00) ⇒ die Stunde vor dem ersten Wert (E-6)
    assert (await _pruefen(db, aid, row.id))["vorgabe_falsch_seit"] == "2026-09-01T11:00:00"
    db.add(SensorSnapshot(anlage_id=aid, sensor_key=NETZ_KEY, zeitpunkt=datetime(2026, 8, 20, 6), wert_kwh=1.0,
                          quelle="ha_statistics"))
    await db.commit()
    assert (await _pruefen(db, aid, row.id))["vorgabe_falsch_seit"] == "2026-08-20T05:00:00"
    await _wechsel(db, aid, {"art": "ha", "entity_id": "sensor.z"}, A, erklaert=datetime(2026, 9, 4, 7, 30), grund="fortsetzung")
    await db.commit()
    from backend.services.zuordnung_wechsel.zeitpunkt import vergiss
    vergiss(db)
    assert (await _pruefen(db, aid, row.id))["vorgabe_falsch_seit"] == "2026-09-04T08:00:00"


async def test_korrektur_nur_am_juengsten_wechsel_mit_heutiger_quelle(db):
    a = await _mit_b(db)
    aid = a.id
    alt = await _wechsel(db, aid, A, B)
    await _wechsel(db, aid, B, {"art": "ha", "entity_id": "sensor.c"}, erklaert=T + timedelta(days=1))
    await db.commit()
    p = await _pruefen(db, aid, alt.id)
    assert p["gruende"] == ["fortsetzung"] and "jüngsten Wechsel" in p["korrektur_nicht"]
    # der jüngste Wechsel, aber seine neue Quelle (sensor.c) ist heute nicht zugeordnet (heute: sensor.b) ⇒ keine Korrektur
    (_a, juengster) = await _zeilen(db, aid)
    assert (await _pruefen(db, aid, juengster.id))["gruende"] == ["fortsetzung"]
    e = await _abgelehnt(_nachtragen(db, aid, alt.id, grund="korrektur", falsch_seit=datetime(2026, 9, 3)))
    assert e.status_code == 422 and "jüngsten Wechsel" in e.detail


# ═══ Grund nachtragen: Fortsetzung, Korrektur, Übergänge ════════════════════════════════════════════════════════════════

async def test_fortsetzung_nachtragen_hebt_auf_und_setzt_die_naht(db):
    from backend.services.zuordnung_wechsel.zeitpunkt import fortsetzungs_naehte, vergiss

    a = await _mit_b(db)
    aid = a.id
    row = await _wechsel(db, aid)
    await db.commit()
    r = await _nachtragen(db, aid, row.id, grund="fortsetzung")
    assert r["eingetragen"] is True and r["korrektur"] == []
    alt, neu = await _zeilen(db, aid)
    assert (alt.aufgehoben_durch, neu.grund, neu.herkunft) == (neu.id, "fortsetzung", "nachtrag")
    assert (neu.erklaert_ts, neu.ab_ts, neu.vorher, neu.nachher) == (T, AB, A, B)    # erklaert_ts = der Wechsel (E-1)
    vergiss(db)
    assert await fortsetzungs_naehte(db, aid, NETZ_KEY) == [AB]
    assert await _befunde(db, a) == []
    log = (await db.execute(select(ActivityLog).where(ActivityLog.aktion == "Grund nachgetragen"))).scalars().all()
    assert [x.details for x in log] == ["Wechsel · Netzbezug Zählerstand (kWh): Fortsetzung (Wechsel vom 10.09.2026 10:47)"]
    # die aufgehobene Zeile: nichts mehr nachzutragen; die neue: nur noch «Korrektur» (S-10 d)
    assert (await _pruefen(db, aid, alt.id))["gruende"] == []
    assert (await _pruefen(db, aid, neu.id))["gruende"] == ["korrektur"]
    e = await _abgelehnt(_nachtragen(db, aid, neu.id, grund="fortsetzung"))
    assert e.status_code == 422 and "nur zu «Korrektur»" in e.detail


async def test_korrektur_nachtragen_ohne_home_assistant_verwirft_im_intervall(db):
    """Ohne Home Assistant (Standalone): der Dienst verwirft die Zählerstände in ``[falsch_seit, Wechsel)``; davor und danach
    bleibt alles. Vorschau = Lauf; die Zeile ohne Grund wird von der Korrektur-Zeile aufgehoben."""
    a = await _mit_b(db)
    aid = a.id
    row = await _wechsel(db, aid)
    await db.commit()
    v = await _pruefen(db, aid, row.id, grund="korrektur", falsch_seit=datetime(2026, 9, 3))
    r = await _nachtragen(db, aid, row.id, grund="korrektur", falsch_seit=datetime(2026, 9, 3))
    assert r["korrektur"][0]["zaehlerstaende_geloescht"] == v["korrektur"]["zaehlerstaende"] == 1
    staende = sorted(t for (t,) in (await db.execute(select(SensorSnapshot.zeitpunkt).where(
        SensorSnapshot.anlage_id == aid, SensorSnapshot.sensor_key == NETZ_KEY))).all())
    assert staende == [datetime(2026, 9, 1, 12), datetime(2026, 9, 12, 12)]
    alt, korr = await _zeilen(db, aid)
    assert (alt.aufgehoben_durch, korr.grund, korr.falsch_seit_ts, korr.ab_ts, korr.herkunft) == (
        korr.id, "korrektur", datetime(2026, 9, 3), AB, "nachtrag")
    assert await _befunde(db, a) == []
    e = await _abgelehnt(_nachtragen(db, aid, korr.id, grund="fortsetzung"))
    assert e.status_code == 422 and e.detail == "Eine Korrektur lässt sich nicht mehr ändern."


async def test_fortsetzung_dann_korrektur(db):
    a = await _mit_b(db)
    aid = a.id
    row = await _wechsel(db, aid)
    await db.commit()
    await _nachtragen(db, aid, row.id, grund="fortsetzung")
    _alt, fort = await _zeilen(db, aid)
    await _nachtragen(db, aid, fort.id, grund="korrektur", falsch_seit=datetime(2026, 9, 3))
    _a, fort, korr = await _zeilen(db, aid)
    assert (fort.aufgehoben_durch, korr.grund) == (korr.id, "korrektur")


async def test_ohne_grund_und_korrektur_ohne_falsch_seit_abgelehnt(db):
    a = await _mit_b(db)
    aid = a.id
    rid = (await _wechsel(db, aid)).id
    await db.commit()
    assert (await _abgelehnt(_nachtragen(db, aid, rid))).status_code == 422
    e = await _abgelehnt(_nachtragen(db, aid, rid, grund="korrektur"))
    assert e.status_code == 422 and "falsch seit" in e.detail
    assert len(await _zeilen(db, aid)) == 1


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


async def test_fortsetzung_im_nachbau_abschnitt_erreicht_die_kanal_sicht(db):
    """§12 Nr. 61: ein Nachbau-Abschnitt (HA-Stände wörtlich, Familie Mitschrift, ``_rohstaende``) trägt den Sprung eines
    alten Wechsels; der nachgetragene Grund «Fortsetzung» setzt dort über ``kanal/naht.nachtrag_fortsetzung`` eine Quelle,
    die Stunde des Wechsels zählt in der Kanal-Sicht (``lesen.stunden``) keinen Zuwachs mehr."""
    from backend.services.kanal.lesen import stunden

    a = await _mit_b(db)
    aid = a.id
    t0 = datetime(2026, 9, 10, 8)
    k = await _mitschrift(db, aid, NETZ_KEY, (100.0, 101.0, 2101.5, 2102.5), t0=t0, statistic_id="ha")
    row = await _wechsel(db, aid, erklaert=datetime(2026, 9, 10, 10, 15))
    await db.commit()
    vorher = {w.start_ts: w.change for w in (await stunden(db, k, _ts(t0), _ts(t0) + 4 * 3600)).werte}
    assert vorher[_ts(t0 + timedelta(hours=2))] == pytest.approx(2000.5)
    await _nachtragen(db, aid, row.id, grund="fortsetzung")
    nachher = {w.start_ts: w.change for w in (await stunden(db, k, _ts(t0), _ts(t0) + 4 * 3600)).werte}
    assert nachher[_ts(t0 + timedelta(hours=2))] == pytest.approx(0.0)
    assert nachher[_ts(t0 + timedelta(hours=3))] == pytest.approx(1.0)
    q = (await db.execute(select(KanalQuelle).where(and_(
        KanalQuelle.kanal_id == k.id, KanalQuelle.gueltig_ab == _ts(t0 + timedelta(hours=2)))))).scalar_one()
    assert q.offset == pytest.approx(-2000.5)


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


# ═══ Überführung der Alt-Vermerke (S-10 c) ═════════════════════════════════════════════════════════════════════════════

async def _vermerk_lage(db, *, mit_zeile: bool):
    """Wie die Produktiv-Anlage: drei Vermerk-Felder — erste Zuordnung (keine Werte davor), zwei Einträge mit unverändertem
    Stand, ein echter Wechsel A → B."""
    a = await _mit_b(db)
    aid = a.id
    a.sensor_mapping = {**a.sensor_mapping, "historie_hinweis": {"felder": [
        {"id": "basis_energy_einspeisung_kwh", "label": "Einspeisung"}, {"id": "inv_energy_2_ladung_kwh", "label": "WB"},
        {"id": NETZ, "label": "Netzbezug"}], "seit": "2026-09-01T10:00:00+02:00"}}
    ein = {"quelle": "ha_app", "entity_id": "sensor.wb"}
    for t, fid, vorher, nachher in (
            (datetime(2026, 9, 1, 9), "basis_energy_einspeisung_kwh", {"quelle": "keine"}, {"quelle": "ha_app", "entity_id": "sensor.e"}),
            (datetime(2026, 9, 2, 9), "inv_energy_2_ladung_kwh", None, ein),
            (datetime(2026, 9, 2, 9, 1), "inv_energy_2_ladung_kwh", ein, ein),
            (T, NETZ, {"quelle": "ha_app", "entity_id": "sensor.a"}, {"quelle": "ha_app", "entity_id": "sensor.b"})):
        db.add(ActivityLog(timestamp=t, kategorie="sensor_mapping", aktion="Datenquelle zugeordnet", anlage_id=aid,
                           details_json={"field_id": fid, "vorher": vorher, "nachher": nachher}))
    if mit_zeile:
        await _wechsel(db, aid)
    await db.commit()
    return a


async def test_vermerke_eine_zeile_statt_drei_und_der_schluessel_verschwindet(db):
    from backend.services.zuordnung_wechsel.ueberfuehrung import ueberfuehre_vermerke

    a = await _vermerk_lage(db, mit_zeile=False)
    z = await ueberfuehre_vermerke(db)
    await db.commit()
    assert dict(z) == {"ohne_eigene_werte": 1, "wirksam_unveraendert": 1, "ueberfuehrt": 1, "vermerke_entfernt": 1}
    (w,) = await _zeilen(db, a.id)
    assert (w.sensor_key, w.vorher, w.nachher, w.grund, w.herkunft, w.erklaert_ts) == (NETZ_KEY, A, B, None, "altbestand", T)
    await db.refresh(a)
    assert "historie_hinweis" not in a.sensor_mapping and a.sensor_mapping["basis"]
    assert dict(await ueberfuehre_vermerke(db)) == {}                        # zweimal = einmal
    assert len(await _zeilen(db, a.id)) == 1
    assert [e.code for e in await _befunde(db, a)] == ["zuordnung_grund_fehlt"]


async def test_vermerke_keine_doppelzeile_zur_ueberfuehrung_aus_sitzung_1(db):
    from backend.services.zuordnung_wechsel.ueberfuehrung import ueberfuehre_vermerke

    a = await _vermerk_lage(db, mit_zeile=True)
    z = await ueberfuehre_vermerke(db)
    await db.commit()
    assert z["schon_ueberfuehrt"] == 1 and z["ueberfuehrt"] == 0
    assert len(await _zeilen(db, a.id)) == 1


async def test_vermerk_nach_keine_verfaellt(db):
    from backend.services.zuordnung_wechsel.ueberfuehrung import ueberfuehre_vermerke

    a = await _mit_b(db)
    aid = a.id
    a.sensor_mapping = {**a.sensor_mapping, "historie_hinweis": {"felder": [{"id": NETZ, "label": "N"}], "seit": "x"}}
    db.add(ActivityLog(timestamp=T, kategorie="sensor_mapping", aktion="x", anlage_id=aid,
                       details_json={"field_id": NETZ, "vorher": {"quelle": "ha_app", "entity_id": "sensor.a"},
                                     "nachher": {"quelle": "keine"}}))
    await db.commit()
    z = await ueberfuehre_vermerke(db)
    assert z["nicht_gefragt"] == 1 and await _zeilen(db, aid) == []


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


# ═══ Probe: heilbare Lage des Befunds zaehler_versatz nach «Kanal vor Reihe» (B-7) ══════════════════════════════════════

async def test_heilbare_lage_wirkt_nur_bei_einer_luecke_im_eigenen_kanal(db, ha, monkeypatch):  # noqa: F811
    """Mit der echten Feld-Auskunft (B-5): trägt der eigene Spiegel die Rand-Tage, schweigt der Befund (die Tagesansicht zeigt
    dort den Kanal) — auch mit einer einzelnen fehlenden Stunde (``voll`` ist eine Auflösungsregel). Reicht eine Lücke im
    Spiegel von mehr als einem Tag über den Rand des Tagesfensters (hier vom 14.06. 19:00 bis 16.06.), liest die
    Tagesansicht den Rand-Tag aus der Reihe — dann steht die heilbare Lage mit «Tage neu aufbauen» (sichtbare Wirkung)."""
    import backend.services.energie_profil.kanal_stunden as ks
    from backend.services.kanal import merken

    async def keine_gruppe(*_a):
        return frozenset()
    monkeypatch.setattr(ks, "kanal_schluessel_des_tages", keine_gruppe)
    a, _wb, key = await _versatz_anlage(db)
    assert await _versatz_pruefe(db, a) == []
    k = (await db.execute(select(Kanal).where(Kanal.key == key))).scalar_one()

    async def loesche(von: datetime, bis: datetime) -> None:
        await db.execute(KanalStatistik.__table__.delete().where(and_(
            KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= _ts(von), KanalStatistik.start_ts < _ts(bis))))
        await db.commit()
        merken.invalidiere(a.id)

    await loesche(datetime(2026, 6, 10, 12), datetime(2026, 6, 10, 13))
    assert await _versatz_pruefe(db, a) == []
    await loesche(datetime(2026, 6, 14, 19), datetime(2026, 6, 16, 0))
    (e,) = await _versatz_pruefe(db, a)
    assert (e.code, e.werte["lage"], e.knopf) == ("zaehler_versatz", "heilbar", "Tage neu aufbauen")
