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
    A, B, T, _mit_b, _wechsel,
)

X = {"art": "ha", "entity_id": "sensor.fremd"}
HEUTE = {"art": "ha", "entity_id": v.SENSOR}
T1 = v.T0 + timedelta(hours=v.SPRUNG_H) - timedelta(minutes=13)        # 10.06. 00:47 → ab 01:00
T2 = v.T0 + timedelta(hours=v.RUECK_H) - timedelta(minutes=40)         # 14.06. 18:20 → ab 19:00
AB1 = v.T0 + timedelta(hours=v.SPRUNG_H)


# ═══ F2/F8 — die Korrektur hebt die Wechsel-Zeilen ihres Intervalls auf ═══════════════════════════════════════════════


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


async def test_f8_werkbank_ueber_eine_fortsetzung_mit_anderer_quelle(db):
    """Nachmessung F8: A → B (Fortsetzung), später B → C; der Dienst in der Werkbank-Form (von Beginn an bis zum Beginn von C,
    richtig = C) lässt keine Fortsetzungs-Naht im Intervall stehen. Seit Weg B (Sitzung B2, «Grund nachtragen» entfernt) ist
    die Fortsetzung A → B gleich verzeichnet statt nachgetragen."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    C = {"art": "ha", "entity_id": "sensor.c"}
    a = await _mit_b(db)
    aid = a.id
    a.sensor_mapping = {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.c"}}}
    await _wechsel(db, aid, A, B, grund="fortsetzung", herkunft="wechsel")
    await _wechsel(db, aid, B, C, erklaert=T + timedelta(days=5), grund="fortsetzung", herkunft="wechsel")
    await db.commit()
    zw.vergiss(db)
    assert len(await zw.fortsetzungs_naehte(db, aid, NETZ_KEY)) == 2
    ab = (T + timedelta(days=5)).replace(minute=0, second=0)
    auftrag = kr.Auftrag(anlage_id=aid, sensor_key=NETZ_KEY, falsch_seit=None, ab=ab, vorher=None, nachher=C)
    vorschau_ab = await kr.wirksames_ab(db, auftrag, None)
    erg = await kr.fuehre_aus(db, auftrag, ha_svc=None, jetzt=datetime(2026, 11, 18, 8))
    await db.commit()
    zw.vergiss(db)
    fort, b_c, korr, luecke = await _zeilen(db, aid)
    # Keine Fortsetzungs-Naht bleibt im Intervall; ohne Home Assistant füllt nichts — seit 4b-1 (Bauplan «Zu §14» Nr. 95 (1))
    # sind die Ränder der Lücke die einzigen Nähte.
    assert luecke.nachher is None and luecke.ab_ts == korr.ab_ts
    assert await zw.fortsetzungs_naehte(db, aid, NETZ_KEY) == [luecke.falsch_seit_ts, luecke.ab_ts]
    assert korr.grund == "korrektur" and korr.ab_ts == vorschau_ab == ab + timedelta(hours=1)   # §10 Nr. 36 unverändert
    assert (b_c.aufgehoben_durch, fort.aufgehoben_durch) == (korr.id, korr.id)
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
    neu = [z for z in await _zeilen(db, aid) if z.grund == "korrektur" and z.nachher == B][-1]
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
    assert rand2.aufgehoben_durch == [z for z in await _zeilen(db, b2.id) if z.grund == "korrektur" and z.nachher == B][-1].id


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


# ═══ H-2 (a) — Rand an einer Fortsetzungs-Naht ohne Wirkung ═══════════════════════════════════════════════════════════

async def _fortsetzung(db, wid: int) -> None:
    """Die Zeile ``wid`` trägt den Grund «Fortsetzung» (wie ein Wechsel, nach dem der Dialog mit «bleiben» beantwortet wurde)."""
    row = await db.get(ZuordnungWechsel, wid)
    row.grund = "fortsetzung"
    await db.commit()
    zw.vergiss(db)


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
    await _fortsetzung(db, id1)
    t = await _tagesansicht(db, a, wb.id)
    assert (t[10], t[14]) == (11.5, None)
    assert [e.code for e in await v._pruefe(db, a)] == ["zaehler_versatz"]
    await _fortsetzung(db, id2)
    t = await _tagesansicht(db, a, wb.id)
    assert (t[10], t[14]) == (11.5, 11.5)
    assert await v._pruefe(db, a) == []
    (ok,) = await DatenChecker(db)._check_zaehler_versatz(a, jetzt=v.JETZT)
    assert (ok.schwere, ok.werte) == (CheckSeverity.OK, {"funde": 0})



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

