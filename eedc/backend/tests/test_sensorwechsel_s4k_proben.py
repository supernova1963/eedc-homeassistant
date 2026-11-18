"""Sensorwechsel mit Grund, Korrekturrunde 4-K (Bauplan §13 Nr. 66–73; Nachmessung Sitzung 4, F1 … F8, H-2).

* **F1** (Nr. 66): «Keine» und zurück zur selben Quelle in derselben Stunde ist kein Befund «Grund fehlt» — die Abfrage zum
  Zeitpunkt eines verzeichneten Wechsels zählt die Zeilen mit gleichem ``ab_ts`` und kleinerer Nummer mit
  (``abfrage.letzte_quelle_mit_werten(vor=, vor_id=)``).
* **F2/F8** (Nr. 67): die Korrektur hebt die Wechsel-Zeilen ihres Intervalls auf (``korrektur._im_intervall``): Zeilen im
  Intervall, die Rand-Zeile bei «falsch seit», wenn ihr ``vorher`` die richtige Quelle ist; Korrektur-Zeilen bleiben. Ein
  Dienst für Dialog, Nachtrag und Werkbank.
* **F3** (Nr. 68): Nachtrag und Einstieg treffen im Nachbau-Abschnitt aus HA-Ständen bei einem Wechsel zur vollen Stunde
  dieselbe Stunde wie ``nachfuellen._laeufe``; im Stundenlauf der Mitschrift bleibt es die Stunde des Zeitpunkts.
* **F4** (Nr. 69): im Nachtrag sagt die MQTT-Vorschau «bis zum Wechsel».
* **H-2 (a)** (Nr. 71): ein Rand an einer Fortsetzungs-Naht ist für ``zaehler_versatz`` ohne Wirkung.
* **Offener Lauf** (Nr. 73): eine Korrektur im Nachtrag startet nicht bei offenem Korrektur-Lauf des Felds.

Schwesterdateien: test_sensorwechsel_s4_nachtrag.py (Sitzung 4), test_sensorwechsel_s3_korrektur.py (Dienst),
test_daten_checker_zaehler_versatz.py (Befund und Saat ``_anlage``), test_kanal_eigene_summe_nachfuellen.py (Stände-Nachbau).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import and_, select

from backend.models.investition import Investition
from backend.models.kanal import Kanal, KanalStatistik
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw
from backend.tests import test_daten_checker_zaehler_versatz as v
from backend.tests.test_daten_checker_zaehler_versatz import ha  # noqa: F401 — Fixture
from backend.tests.test_sensorwechsel_s1_verzeichnen import NETZ, NETZ_KEY, _anlage, _quelle, _zeilen
from backend.tests.test_sensorwechsel_s4_nachtrag import (
    A, B, KEINE, T, _abgelehnt, _befunde, _mit_b, _nachtragen, _pruefen, _wechsel,
)

X = {"art": "ha", "entity_id": "sensor.fremd"}
HEUTE = {"art": "ha", "entity_id": v.SENSOR}
T1 = v.T0 + timedelta(hours=v.SPRUNG_H) - timedelta(minutes=13)        # 10.06. 00:47 → ab 01:00
T2 = v.T0 + timedelta(hours=v.RUECK_H) - timedelta(minutes=40)         # 14.06. 18:20 → ab 19:00
AB1 = v.T0 + timedelta(hours=v.SPRUNG_H)


# ═══ F1 — «Keine» und zurück in derselben Stunde ═════════════════════════════════════════════════════════════════════

async def test_f1_keine_und_zurueck_in_derselben_stunde_ist_kein_befund(db):
    """Über die echte Feld-Route: A → «Keine» (ohne Frage) und sofort zurück zu A (B-2 fragt nicht). Beide Zeilen tragen
    dasselbe ``ab_ts``; der Befund fragt dieselbe Regel zum Zeitpunkt — die Zeile davor zählt mit (Nachmessung F1)."""
    from backend.services.zuordnung_wechsel.abfrage import haette_gefragt

    a = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.a"}}})
    aid = a.id
    await db.commit()
    await _quelle(db, aid, quelle="keine")
    await _quelle(db, aid, quelle="ha_app", entity_id="sensor.a")
    zw.vergiss(db)
    hin, zurueck = await _zeilen(db, aid)
    assert hin.ab_ts == zurueck.ab_ts and (hin.nachher, zurueck.vorher) == (KEINE, KEINE)
    assert not await haette_gefragt(db, aid, zurueck)
    await db.refresh(a)
    assert await _befunde(db, a) == []


async def test_f1_reihenfolge_in_derselben_stunde(db):
    """A → «Keine» → B in derselben Stunde fragt weiter (B ist nicht die letzte Quelle mit Werten); die spätere Zeile zählt
    für die frühere nicht mit (Reihenfolge ``ab_ts``, dann Nummer)."""
    from backend.services.zuordnung_wechsel.abfrage import haette_gefragt

    a = await _mit_b(db)
    aid = a.id
    erst = await _wechsel(db, aid, A, KEINE, erklaert=T)
    dann = await _wechsel(db, aid, KEINE, B, erklaert=T + timedelta(minutes=5))
    await db.commit()
    zw.vergiss(db)
    assert await haette_gefragt(db, aid, dann)
    assert not await haette_gefragt(db, aid, erst)             # → «Keine» fragt nie


# ═══ F2/F8 — die Korrektur hebt die Wechsel-Zeilen ihres Intervalls auf ═══════════════════════════════════════════════

async def _a_x_a(db, monkeypatch, *, ersten_fortsetzen: bool = False):
    """A → X → A an der Saat des Befunds ``zaehler_versatz`` (Reihe um 80 kWh versetzt vom 10.06. 01:00 bis 14.06. 19:00),
    beide Wechsel ohne Grund; HA führt A durchgehend; der eigene Spiegel fehlt über beide Rand-Tage (die Tagesansicht liest
    dort die Reihe, Nachmessung H1)."""
    import backend.services.energie_profil.kanal_stunden as ks
    from backend.services.zuordnung_wechsel import korrektur as kr

    async def keine_gruppe(*_a):
        return frozenset()
    monkeypatch.setattr(ks, "kanal_schluessel_des_tages", keine_gruppe)
    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: True)
    a, wb, key = await v._anlage(db)
    kid = (await db.execute(select(Kanal.id).where(Kanal.key == key))).scalar_one()
    for von, bis in ((datetime(2026, 6, 8, 22), datetime(2026, 6, 10, 6)), (datetime(2026, 6, 14, 19), datetime(2026, 6, 16, 0))):
        await db.execute(KanalStatistik.__table__.delete().where(and_(
            KanalStatistik.kanal_id == kid, KanalStatistik.start_ts >= int(von.timestamp()),
            KanalStatistik.start_ts < int(bis.timestamp()))))
    r1 = await _wechsel(db, a.id, HEUTE, X, erklaert=T1, key=key)
    r2 = await _wechsel(db, a.id, X, HEUTE, erklaert=T2, key=key)
    await db.commit()
    id1, id2 = r1.id, r2.id
    if ersten_fortsetzen:
        await _nachtragen(db, a.id, id1, grund="fortsetzung")
        zw.vergiss(db)
    return a, wb.id, key, id1, id2


async def _tagesansicht(db, a, wid) -> dict[int, float | None]:
    from backend.services.kanal import merken
    from backend.services.snapshot.aggregator import get_tagesdetail_kwh

    zw.vergiss(db)
    merken.invalidiere(a.id)
    a_ = (await db.execute(select(type(a)).where(type(a).id == a.id))).scalar_one()
    invs = {str(wid): await db.get(Investition, wid)}
    out = {}
    for d in (9, 10, 11, 13, 14, 15):
        w = (await get_tagesdetail_kwh(db, a_, invs, date(2026, 6, d), tageszeile_rueckwaerts=True)).werte.get("emob_ladung_pv_kwh")
        out[d] = None if w is None else round(w, 2)
    return out


async def _korrektur_am_zweiten(db, aid, id2):
    from backend.services.zuordnung_wechsel import korrektur_lauf as kl

    fs = datetime.fromisoformat((await _pruefen(db, aid, id2))["vorgabe_falsch_seit"])
    assert fs == AB1                                                # Vorgabe = Beginn von X = ab_ts des ersten Wechsels
    await _nachtragen(db, aid, id2, grund="korrektur", falsch_seit=fs)
    for t in list(kl._AUFGABEN.values()):
        await t
    zw.vergiss(db)


async def test_f2a_korrektur_am_zweiten_wechsel_erledigt_den_ersten(db, ha, monkeypatch):  # noqa: F811
    """Nachmessung F2: «Korrektur» am zweiten Wechsel mit der Vorgabe — der erste Wechsel (Rand «falsch seit», ``vorher`` =
    die richtige Quelle) ist danach aufgehoben, kein Befund «Grund fehlt» bleibt, die Tagesansicht ist an allen Tagen richtig."""
    a, wid, key, id1, id2 = await _a_x_a(db, monkeypatch)
    assert await _tagesansicht(db, a, wid) == {9: 12.0, 10: 92.0, 11: 12.0, 13: 12.0, 14: None, 15: 12.0}
    assert len(await _befunde(db, a)) == 2
    await _korrektur_am_zweiten(db, a.id, id2)
    r1, r2, korr = await _zeilen(db, a.id)
    assert (r1.aufgehoben_durch, r2.aufgehoben_durch, korr.grund, korr.falsch_seit_ts) == (korr.id, korr.id, "korrektur", AB1)
    assert await _befunde(db, a) == []
    assert await v._pruefe(db, a) == []
    assert await _tagesansicht(db, a, wid) == {9: 12.0, 10: 12.0, 11: 12.0, 13: 12.0, 14: 12.0, 15: 12.0}
    aid = a.id
    assert (await _abgelehnt(_nachtragen(db, aid, id1, grund="fortsetzung"))).status_code == 422
    # B-0 danach: im Intervall immer die richtige Quelle (nie die verworfene X) …
    wl = (await zw.lade_wechsel(db, aid))[key]
    for z in (AB1, datetime(2026, 6, 12, 7), T2 - timedelta(minutes=1)):
        assert zw.quelle_am(wl, z) == HEUTE
    # … und davor die Quelle, die ohne die Korrektur dort galt (A), nicht das ``vorher`` X der Korrektur-Zeile («Zu §13» Nr. 84)
    assert zw.quelle_am(wl, AB1 - timedelta(hours=2)) == HEUTE


async def test_f2b_erst_fortsetzung_am_ersten_dann_korrektur_am_zweiten(db, ha, monkeypatch):  # noqa: F811
    """Dieselbe Lage, der Anwender trägt erst am ersten Wechsel «Fortsetzung» ein: die Korrektur am zweiten hebt auch diese
    Fortsetzung auf — keine Naht bleibt in Daten, die danach durchgehend aus einem Sensor stammen."""
    a, wid, key, _id1, id2 = await _a_x_a(db, monkeypatch, ersten_fortsetzen=True)
    assert await zw.fortsetzungs_naehte(db, a.id, key) == [AB1]
    await _korrektur_am_zweiten(db, a.id, id2)
    assert await zw.fortsetzungs_naehte(db, a.id, key) == []
    assert all(r.aufgehoben_durch is not None for r in (await _zeilen(db, a.id)) if r.grund != "korrektur")
    assert await _befunde(db, a) == []
    assert await _tagesansicht(db, a, wid) == {9: 12.0, 10: 12.0, 11: 12.0, 13: 12.0, 14: 12.0, 15: 12.0}


async def test_f8_werkbank_ueber_eine_fortsetzung_mit_anderer_quelle(db):
    """Nachmessung F8: A → B (Fortsetzung nachgetragen), später B → C; der Dienst in der Werkbank-Form (von Beginn an bis zum
    Beginn von C, richtig = C) lässt keine Fortsetzungs-Naht im Intervall stehen."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    C = {"art": "ha", "entity_id": "sensor.c"}
    a = await _mit_b(db)
    aid = a.id
    a.sensor_mapping = {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.c"}}}
    r1 = await _wechsel(db, aid, A, B)
    await _wechsel(db, aid, B, C, erklaert=T + timedelta(days=5), grund="fortsetzung", herkunft="wechsel")
    await db.commit()
    await _nachtragen(db, aid, r1.id, grund="fortsetzung")
    zw.vergiss(db)
    assert len(await zw.fortsetzungs_naehte(db, aid, NETZ_KEY)) == 2
    ab = (T + timedelta(days=5)).replace(minute=0, second=0)
    auftrag = kr.Auftrag(anlage_id=aid, sensor_key=NETZ_KEY, falsch_seit=None, ab=ab, vorher=None, nachher=C)
    vorschau_ab = await kr.wirksames_ab(db, auftrag, None)
    erg = await kr.fuehre_aus(db, auftrag, ha_svc=None, jetzt=datetime(2026, 11, 18, 8))
    await db.commit()
    zw.vergiss(db)
    assert await zw.fortsetzungs_naehte(db, aid, NETZ_KEY) == []
    alt, b_c, fort, korr = await _zeilen(db, aid)
    assert korr.grund == "korrektur" and korr.ab_ts == vorschau_ab == ab + timedelta(hours=1)   # §10 Nr. 36 unverändert
    assert (alt.aufgehoben_durch, b_c.aufgehoben_durch, fort.aufgehoben_durch) == (fort.id, korr.id, korr.id)
    assert erg["summary"]["wechsel_id"] == korr.id


async def test_nr67_rand_mit_anderem_vorher_bleibt_eine_zeile_davor_wird_aufgehoben(db):
    """Die Regel am Dienst: falsch in ``[F, ab)``, richtig = B. Am Rand F bleibt eine Zeile, deren ``vorher`` nicht B ist (dort
    wechselt weiter etwas); eine Zeile im Intervall wird aufgehoben, auch mit «Fortsetzung»; Korrektur-Zeilen bleiben; eine
    Zeile vor F bleibt."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    a = await _mit_b(db)
    aid = a.id
    F = datetime(2026, 9, 3, 10)
    vor_f = await _wechsel(db, aid, {"art": "ha", "entity_id": "sensor.z"}, A, erklaert=datetime(2026, 9, 2, 9, 30))
    rand = await _wechsel(db, aid, A, X, erklaert=F)                                  # vorher A ≠ richtig B ⇒ bleibt
    innen = await _wechsel(db, aid, X, A, erklaert=datetime(2026, 9, 6, 8, 10), grund="fortsetzung")
    alt_korr = ZuordnungWechsel(anlage_id=aid, sensor_key=NETZ_KEY, erklaert_ts=datetime(2026, 9, 7, 9), ab_ts=datetime(2026, 9, 7, 9),
                                vorher=A, nachher=X, grund="korrektur", falsch_seit_ts=datetime(2026, 9, 6, 20), herkunft="wechsel")
    db.add(alt_korr)
    await db.commit()
    auftrag = kr.Auftrag(anlage_id=aid, sensor_key=NETZ_KEY, falsch_seit=F, ab=datetime(2026, 9, 10, 11), vorher=A, nachher=B)
    await kr.fuehre_aus(db, auftrag, ha_svc=None, jetzt=datetime(2026, 11, 18, 8))
    await db.commit()
    for r in (vor_f, rand, innen, alt_korr):
        await db.refresh(r)
    neu = (await _zeilen(db, aid))[-1]
    assert (vor_f.aufgehoben_durch, rand.aufgehoben_durch, innen.aufgehoben_durch, alt_korr.aufgehoben_durch) == (
        None, None, neu.id, None)
    # Rand mit vorher = richtige Quelle ⇒ aufgehoben
    b2 = await _anlage(db, {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.b"}}})
    rand2 = await _wechsel(db, b2.id, B, X, erklaert=F)
    await db.commit()
    await kr.fuehre_aus(db, kr.Auftrag(anlage_id=b2.id, sensor_key=NETZ_KEY, falsch_seit=F, ab=datetime(2026, 9, 10, 11),
                                       vorher=X, nachher=B), ha_svc=None, jetzt=datetime(2026, 11, 18, 8))
    await db.commit()
    await db.refresh(rand2)
    assert rand2.aufgehoben_durch == (await _zeilen(db, b2.id))[-1].id


async def test_nr71_falsch_seit_vor_dem_aelteren_wechsel_erledigt_ihn_mit(db):
    """Zwei gemeldete Wechsel desselben Felds (A → X, X → B), Korrektur am jüngeren mit «Falsch seit» **vor** dem älteren: der
    ältere liegt im Intervall und ist danach aufgehoben, gleich welches ``vorher`` er trägt (Lösungsweg, Bauplan §13 Nr. 71)."""
    a = await _mit_b(db)
    aid = a.id
    alt = await _wechsel(db, aid, A, X, erklaert=datetime(2026, 9, 6, 8, 10))
    jung = await _wechsel(db, aid, X, B)
    await db.commit()
    assert len(await _befunde(db, a)) == 2
    await _nachtragen(db, aid, jung.id, grund="korrektur", falsch_seit=datetime(2026, 9, 3))
    zw.vergiss(db)
    await db.refresh(alt)
    assert alt.aufgehoben_durch is not None
    assert await _befunde(db, a) == []


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


async def test_f3_nachtrag_zur_vollen_stunde_trifft_die_stunde_des_nachbaus(datei):
    """Nachbau aus HA-Ständen (Kennung ``sensor_snapshots:…``): der Wechsel genau um 03:00:00 — der Stand 03:00 ist neu, er
    steht in der Zeile 02:00. «Fortsetzung nachtragen» nullt die Zeile 02:00 (wie ``_laeufe``), die Stunde 03:00 zählt 1,0."""
    from backend.tests import test_kanal_eigene_summe_nachfuellen as e

    sitzungen, aid, zuw = await _nachbau(datei, quelle="ha_statistics",
                                         mapping={"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.b"}},
                                                  "investitionen": {}})
    assert (await zuw())["02:00"] == 2001.0
    wechsel = e.T0 + timedelta(hours=3)
    async with sitzungen() as s:
        s.add(ZuordnungWechsel(anlage_id=aid, sensor_key=NETZ_KEY, erklaert_ts=wechsel, ab_ts=wechsel, vorher=A, nachher=B,
                               grund=None, herkunft="altbestand"))
    async with sitzungen() as s:
        (row,) = await _zeilen(s, aid)
        await _nachtragen(s, aid, row.id, grund="fortsetzung")
    nach = await zuw()
    assert (nach["02:00"], nach["03:00"]) == (0.0, 1.0)
    # derselbe Schnitt, den der Stände-Nachbau bei schon verzeichneter Fortsetzung macht
    s2, aid2 = await datei("teilt", mapping={"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.b"}},
                                             "investitionen": {}})
    async with s2() as s:
        s.add(ZuordnungWechsel(anlage_id=aid2, sensor_key=NETZ_KEY, erklaert_ts=wechsel, ab_ts=wechsel, vorher=A, nachher=B,
                               grund="fortsetzung", herkunft="nachtrag"))
    from backend.services.kanal.nachfuellen import nachfuellen_eigene_summe
    await e._staende(s2, aid2, NETZ_KEY, FOLGE, quelle="ha_statistics")
    await nachfuellen_eigene_summe(s2, aid2, jetzt=e.JETZT)
    _k, zeilen, quellen = await e._kanal(s2, aid2, NETZ_KEY)
    geteilt = {datetime.fromtimestamp(t).strftime("%H:%M"): round(w, 3) for t, w in e._zuwaechse(zeilen, quellen).items()}
    assert geteilt == nach


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
    from backend.services.zuordnung_wechsel.zaehler_getauscht import SATZ_TAG_FEST, lage as zg_lage
    assert p["saetze"][3] == SATZ_TAG_FEST                               # «Zu §13» Nr. 87: Tausch vor dem laufenden Tag
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


# ═══ F4 — MQTT-Vorschau im Nachtrag ══════════════════════════════════════════════════════════════════════════════════

async def test_f4_mqtt_vorschau_im_nachtrag_sagt_bis_zum_wechsel(db):
    from backend.services.zuordnung_wechsel.korrektur import SATZ_KANAL_MQTT, SATZ_KANAL_MQTT_NACHTRAG
    from backend.services.zuordnung_wechsel.quelle import standard_quelle

    a = await _mit_b(db)
    aid = a.id
    a.sensor_mapping = {"basis": {}}
    row = await _wechsel(db, aid, A, standard_quelle(NETZ_KEY))
    await db.commit()
    p = await _pruefen(db, aid, row.id, grund="korrektur", falsch_seit=datetime(2026, 9, 3))
    assert SATZ_KANAL_MQTT_NACHTRAG in p["korrektur"]["saetze"]
    assert SATZ_KANAL_MQTT not in p["korrektur"]["saetze"]
    assert "bis zum Wechsel" in SATZ_KANAL_MQTT_NACHTRAG and "bis jetzt" in SATZ_KANAL_MQTT


# ═══ H-2 (a) — Rand an einer Fortsetzungs-Naht ohne Wirkung ═══════════════════════════════════════════════════════════

async def test_h2_rand_an_einer_fortsetzung_hat_keine_wirkung(db, monkeypatch):
    """A → X → A ohne Grund: beide Befunde stehen (Wirkung und Ursache). «Fortsetzung» am Sprung: der Rand 10.06. rechnet
    richtig (11,5), der Rand 14.06. weiter falsch ⇒ ``zaehler_versatz`` bleibt; «Fortsetzung» an beiden Rändern ⇒ die
    Tagesansicht rechnet an beiden Rändern 11,5, ``zaehler_versatz`` meldet nichts mehr (OK-Zeile)."""
    import backend.services.energie_profil.kanal_stunden as ks
    import backend.services.ha_statistics_service as hss
    from backend.services.daten_checker import DatenChecker
    from backend.services.daten_checker.kategorien import CheckSeverity
    from backend.tests.pv_achse_matrix import _ha_aus

    async def keine_gruppe(*_a):
        return frozenset()
    monkeypatch.setattr(ks, "kanal_schluessel_des_tages", keine_gruppe)
    monkeypatch.setattr(hss, "_ha_statistics_service", _ha_aus())
    a, wb, key = await v._anlage(db)
    kid = (await db.execute(select(Kanal.id).where(Kanal.key == key))).scalar_one()
    for von, bis in ((datetime(2026, 6, 8, 22), datetime(2026, 6, 10, 6)), (datetime(2026, 6, 14, 19), datetime(2026, 6, 16, 0))):
        await db.execute(KanalStatistik.__table__.delete().where(and_(
            KanalStatistik.kanal_id == kid, KanalStatistik.start_ts >= int(von.timestamp()),
            KanalStatistik.start_ts < int(bis.timestamp()))))
    r1 = await _wechsel(db, a.id, HEUTE, X, erklaert=T1, key=key)
    r2 = await _wechsel(db, a.id, X, HEUTE, erklaert=T2, key=key)
    await db.commit()
    id1, id2 = r1.id, r2.id
    assert [e.code for e in await v._pruefe(db, a)] == ["zaehler_versatz"]
    await _nachtragen(db, a.id, id1, grund="fortsetzung")
    t = await _tagesansicht(db, a, wb.id)
    assert (t[10], t[14]) == (11.5, None)
    assert [e.code for e in await v._pruefe(db, a)] == ["zaehler_versatz"]
    await _nachtragen(db, a.id, id2, grund="fortsetzung")
    t = await _tagesansicht(db, a, wb.id)
    assert (t[10], t[14]) == (11.5, 11.5)
    assert await v._pruefe(db, a) == []
    (ok,) = await DatenChecker(db)._check_zaehler_versatz(a, jetzt=v.JETZT)
    assert (ok.schwere, ok.werte) == (CheckSeverity.OK, {"funde": 0})
    assert await _befunde(db, a) == []


# ═══ Nr. 73 — offener Korrektur-Lauf ═════════════════════════════════════════════════════════════════════════════════

async def test_nr73_offener_lauf_sperrt_die_korrektur_im_nachtrag(db):
    from backend.services.zuordnung_wechsel import korrektur_lauf as kl
    from backend.services.zuordnung_wechsel.nachtrag import SATZ_LAUF_OFFEN

    a = await _mit_b(db)
    aid = a.id
    row = await _wechsel(db, aid)
    await db.commit()
    rid = row.id
    assert (await _pruefen(db, aid, rid))["gruende"] == ["fortsetzung", "korrektur"]
    await kl.anlegen(db, "offen0000001", aid, NETZ_KEY, [], fuellen={"erledigt": False, "kanal_id": None, "key": NETZ_KEY})
    await db.commit()
    p = await _pruefen(db, aid, rid)
    assert (p["gruende"], p["korrektur_nicht"]) == (["fortsetzung"], SATZ_LAUF_OFFEN)
    e = await _abgelehnt(_nachtragen(db, aid, rid, grund="korrektur", falsch_seit=datetime(2026, 9, 3)))
    assert (e.status_code, e.detail) == (422, SATZ_LAUF_OFFEN)
    assert len(await _zeilen(db, aid)) == 1
    # Fortsetzung → Korrektur bei offenem Lauf: derselbe Satz (nicht «kein Grund nachzutragen»)
    await _nachtragen(db, aid, rid, grund="fortsetzung")
    fort = (await _zeilen(db, aid))[-1]
    e = await _abgelehnt(_nachtragen(db, aid, fort.id, grund="korrektur", falsch_seit=datetime(2026, 9, 3)))
    assert (e.status_code, e.detail) == (422, SATZ_LAUF_OFFEN)


# ═══ «Zu §13» Nr. 84 — vor «falsch seit» gilt, was ohne die Korrektur galt ═════════════════════════════════════════════

def test_nr84_vor_falsch_seit_zaehlen_die_aufgehobenen_zeilen():
    """Rein an ``quelle_am``: A → X → A, Korrektur am zweiten Wechsel (falsch seit = erster Wechsel) hebt beide Zeilen auf —
    vor dem ersten Wechsel A, im Intervall A, danach heute. Ohne die Regel wäre es vor dem ersten Wechsel X."""
    t1, t2, f = datetime(2026, 6, 10, 1), datetime(2026, 6, 14, 19), datetime(2026, 6, 10, 1)
    r1 = zw.Wechsel(NETZ_KEY, t1, A, X, aufgehoben_durch=3, id=1)
    r2 = zw.Wechsel(NETZ_KEY, t2, X, A, aufgehoben_durch=3, id=2)
    korr = zw.Wechsel(NETZ_KEY, t2, X, A, grund="korrektur", falsch_seit_ts=f, id=3)
    wl = [r1, r2, korr]
    assert zw.quelle_am(wl, t1 - timedelta(hours=5)) == A
    assert zw.quelle_am(wl, datetime(2026, 6, 12)) == A
    assert zw.quelle_am(wl, t2 + timedelta(hours=1)) is zw.HEUTE
    assert zw.quelle_am([korr], t1 - timedelta(hours=5)) == X           # ohne die aufgehobenen Zeilen: vorher der Korrektur


def test_nr84_einfache_korrektur_davor_weiter_vorher():
    """Korrektur A → B mit «falsch seit» nach dem Beginn, ohne frühere Zeile: davor weiter ``vorher`` A, im Intervall B; eine
    von ihr aufgehobene Zeile ohne Grund für denselben Wechsel ändert davor nichts."""
    f, ab = datetime(2026, 9, 3), datetime(2026, 9, 10, 11)
    korr = zw.Wechsel(NETZ_KEY, ab, A, B, grund="korrektur", falsch_seit_ts=f, id=2)
    alt = zw.Wechsel(NETZ_KEY, ab, A, B, aufgehoben_durch=2, id=1)
    for wl in ([korr], [alt, korr]):
        assert zw.quelle_am(wl, f - timedelta(hours=1)) == A
        assert zw.quelle_am(wl, f + timedelta(days=1)) == B
        assert zw.quelle_am(wl, ab) is zw.HEUTE

