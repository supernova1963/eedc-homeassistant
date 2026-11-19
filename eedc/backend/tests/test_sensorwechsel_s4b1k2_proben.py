"""Sensorwechsel mit Grund, Korrekturrunde 4b-1-K2 (Bauplan «Zu §14» Nr. 109–121, Nachmessung ``SENSORWECHSEL-S4B1-K-NACHMESSUNG``).

Saat des Befunds ``zaehler_versatz`` (``test_daten_checker_zaehler_versatz``): wahrer Zähler 100 + 0,5 kWh je Stunde = 12,0 kWh
je Tag, Stück um 80 kWh versetzt vom 10.06. 01:00 bis zum Rückgang 14.06. 19:00.

* **Nr. 111 (F2)** — nach einer füllbaren Korrektur stehen die Zählerstände wieder fest in eedc: der Lauf liest sie aus Home
  Assistant neu und speichert sie (``korrektur.fuelle_staende``); Home Assistant danach weg ⇒ weiter 12,0, der Tagesabschluss
  speichert 12,0. Home Assistant während des Laufs weg ⇒ der Auftrag bleibt offen, Lücke (0,5 · — · — · — · 2,0), kein
  Schreiber speichert 59,5; nach dem Nachholen 12,0 und die Stände gespeichert.
* **Nr. 113 (F4)** — eine füllbare Korrektur, die eine ältere MQTT-Korrektur-Zeile teilweise überdeckt, kürzt deren Lücke auf
  den Rest; die Vorschau nennt es.
* **U1** — «HA erreichbar, führt nichts» beendet den Lauf mit einer Lücken-Zeile (Regel der Zählerlücke), «HA führt erst
  später» lässt nur die Zeit davor leer.
* **Nr. 116** — E-K6 (Abruf-Fehler von Home Assistant in der Prüf-Route ⇒ nicht startbar, kein 500), N3 (Meldung «vom … bis …»
  = Tage des ersten und letzten versetzten Stands), N4 (eine aufgehobene Korrektur-Zeile mit offenem Lauf sperrt nicht).

Keine Probe liest die Uhr; die Zeitpunkte liegen im Juni (die Suite fährt auch in ``Pacific/Auckland`` und ``UTC``).
Schwesterdateien: test_sensorwechsel_s4b1_stueck.py (Stück, Lücke, Nr. 112 und Nr. 119/120), test_daten_checker_zaehler_versatz.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import func, select

from backend.models import activity_log, mqtt_gateway_mapping  # noqa: F401 — Tabellen der Routen (Teil-Schema der Fixture)
from backend.models.investition import Investition
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw
from backend.tests import test_daten_checker_zaehler_versatz as v
from backend.tests.test_daten_checker_zaehler_versatz import ha  # noqa: F401 — Fixture
from backend.tests.test_sensorwechsel_s4b1_stueck import (  # noqa: F401 — Fixture
    LUECKE, QA, RUECK, SPRUNG, TAGE, _body, _stueck, eingerichtet,
)

ZWOELF = {d: 12.0 for d in TAGE}
KURVE = {"serien": [], "punkte": [{"zeit": f"{h:02d}:00", "werte": {}} for h in range(24)]}
AUSGABE = {"wallbox": ("ladung_pv_kwh", "emob_ladung_pv_kwh"), "waermepumpe": ("stromverbrauch_kwh", "wp_strom_gesamt_kwh")}


async def _anlage(db, typ: str):
    """Die Saat an einem Gerät ``typ`` ohne Kanal (Reihe)."""
    from backend.models.anlage import Anlage

    feld = AUSGABE[typ][0]
    a = Anlage(anlagenname="K2", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    inv = Investition(anlage_id=a.id, typ=typ, bezeichnung="Gerät", anschaffungsdatum=date(2025, 1, 1))
    db.add(inv)
    await db.flush()
    a.sensor_mapping = {"investitionen": {str(inv.id): {"felder": {feld: {"strategie": "sensor", "sensor_id": v.SENSOR}}}}}
    key = f"inv:{inv.id}:{feld}"
    db.add_all([SensorSnapshot(anlage_id=a.id, sensor_key=key, zeitpunkt=t, wert_kwh=w, quelle="ha_statistics")
                for t, w in v._reihe()])
    await db.commit()
    return a, inv, key


async def _sicht(db, a, inv, typ: str) -> dict[int, float | None]:
    """Die Tagesansicht (``get_tagesdetail_kwh``, Bestandsfenster rückwärts) je Tag 9.–15.06."""
    from backend.models.anlage import Anlage
    from backend.services.kanal import merken
    from backend.services.snapshot.aggregator import get_tagesdetail_kwh

    zw.vergiss(db)
    merken.invalidiere(a.id)
    a_ = (await db.execute(select(Anlage).where(Anlage.id == a.id))).scalar_one()
    invs = {str(inv.id): await db.get(Investition, inv.id)}
    out = {}
    for d in TAGE:
        w = (await get_tagesdetail_kwh(db, a_, invs, date(2026, 6, d), tageszeile_rueckwaerts=True)).werte.get(AUSGABE[typ][1])
        out[d] = None if w is None else round(w, 2)
    return out


async def _bereich(db, a, inv, typ: str) -> dict[int, float | None]:
    from backend.models.anlage import Anlage
    from backend.services.snapshot.aggregator import TAGESDETAIL_AUSGABE
    from backend.services.snapshot.bereichs_leser import lade_tageswerte_je_feld

    zw.vergiss(db)
    feld, aus = AUSGABE[typ]
    a_ = (await db.execute(select(Anlage).where(Anlage.id == a.id))).scalar_one()
    tage = [date(2026, 6, d) for d in TAGE]
    je = await lade_tageswerte_je_feld(db, a_, {str(inv.id): await db.get(Investition, inv.id)}, tage[0], tage[-1],
                                       {(typ, feld): TAGESDETAIL_AUSGABE[(typ, feld)]}, rueckwaerts_tage=frozenset(tage),
                                       kanal_zuerst=True)
    return {d.day: (round(je[d][aus], 2) if d in je and aus in je[d] else None) for d in tage}


async def _staende_im_stueck(db, key) -> int:
    return int((await db.execute(select(func.count()).select_from(SensorSnapshot).where(
        SensorSnapshot.sensor_key == key, SensorSnapshot.zeitpunkt >= SPRUNG, SensorSnapshot.zeitpunkt < RUECK))).scalar_one())


async def _tagesabschluss(db, aid, tag: date):
    """``aggregate_day`` wie der Scheduler (Leistungskurve gestellt); Rückgabe ``komponenten_kwh`` der Tageszeile."""
    from backend.models.anlage import Anlage
    from backend.models.tages_energie_profil import TagesZusammenfassung
    from backend.services.energie_profil.aggregator import aggregate_day
    from backend.services.energie_profil.source import Source

    zw.vergiss(db)
    a_ = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    await aggregate_day(a_, tag, db, source=Source.SCHEDULER, prefetched_tagesverlauf=KURVE)
    await db.commit()
    tz = (await db.execute(select(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == aid,
                                                               TagesZusammenfassung.datum == tag))).scalar_one_or_none()
    return None if tz is None else tz.komponenten_kwh


def _ha_weg(monkeypatch):
    import backend.services.ha_statistics_service as hss
    from backend.tests.pv_achse_matrix import _ha_aus

    monkeypatch.setattr(hss, "_ha_statistics_service", _ha_aus())


# ═══ Nr. 111 (F2): nach einer füllbaren Korrektur stehen die Stände fest in eedc ═══════════════════════════════════════

@pytest.mark.parametrize("typ", ["wallbox", "waermepumpe"])
async def test_nr111_fuellbar_staende_gespeichert_ha_danach_weg(db, ha, eingerichtet, monkeypatch, typ):  # noqa: F811
    """Mit Home Assistant 12,0 an jedem Tag **und** die 114 Stände des Stücks gespeichert (Vorschau = Lauf: die Zeit
    ``staende_neu``); Home Assistant danach weg ⇒ Tagesansicht und Bereichs-Leser weiter 12,0, der Tagesabschluss des End-Tags
    speichert 12,0 (vorher 59,5)."""
    from backend.api.routes import sensorwechsel as sw
    from backend.services.zuordnung_wechsel import korrektur_lauf

    v._kanal_tage(monkeypatch, {})
    a, inv, key = await _anlage(db, typ)
    aid = a.id
    k = (await sw.pruefe_stueck(aid, _body(key), db))["korrektur"]
    assert k["staende_neu"] == {"von": SPRUNG.isoformat(), "bis": RUECK.isoformat()}
    r = await _stueck(db, aid, key)
    assert await _staende_im_stueck(db, key) == 114
    z = await korrektur_lauf.stand(db, r["korrektur"][0]["lauf"])
    assert (z["status"], z["fuellen"]["erledigt"], z["fuellen"]["staende_neu"], z["fuellen"]["staende"]["von"]) == (
        "fertig", True, 114, k["staende_neu"]["von"])
    assert await _sicht(db, a, inv, typ) == ZWOELF
    _ha_weg(monkeypatch)
    assert await _sicht(db, a, inv, typ) == ZWOELF
    assert await _bereich(db, a, inv, typ) == ZWOELF
    if typ == "waermepumpe":
        assert await _tagesabschluss(db, aid, date(2026, 6, 14)) == {f"waermepumpe_{inv.id}": 12.0}


async def test_nr111_ha_waehrend_des_laufs_weg_luecke_dann_nachholen(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    """Home Assistant fällt nach dem Eintragen aus (der Abruf wirft): der Auftrag «Stände speichern» bleibt offen, das Stück
    gilt als Lücke (Nr. 106) — Tagesansicht 0,5 · — · — · — · 2,0, Bereichs-Leser ebenso, der Tagesabschluss des End-Tags
    speichert 2,0, nicht 59,5. Nach dem Nachholen (der Lauf, Home Assistant wieder da) 12,0 an jedem Tag, die Stände
    gespeichert, der Lauf fertig."""
    from backend.core.database import get_session
    from backend.services.zuordnung_wechsel import korrektur_lauf
    from backend.services.zuordnung_wechsel.korrektur import sitzungen_wie

    v._kanal_tage(monkeypatch, {})
    a, inv, key = await _anlage(db, "waermepumpe")
    aid = a.id
    echt = ha.get_value_at
    gelesen = {"n": 0}

    def faellt_aus(*args, **kw):          # die Prüfung (vier Abrufe) gelingt, dann ist Home Assistant weg
        gelesen["n"] += 1
        if gelesen["n"] > 4:
            raise ConnectionError("Home Assistant nicht erreichbar")
        return echt(*args, **kw)
    monkeypatch.setattr(ha, "get_value_at", faellt_aus)
    r = await _stueck(db, aid, key)
    lauf = r["korrektur"][0]["lauf"]
    assert await korrektur_lauf.offener_lauf(db, aid, key) == lauf
    assert await _staende_im_stueck(db, key) == 0
    _ha_weg(monkeypatch)
    soll = {**LUECKE}
    assert await _sicht(db, a, inv, "waermepumpe") == soll
    assert await _bereich(db, a, inv, "waermepumpe") == soll
    assert await _tagesabschluss(db, aid, date(2026, 6, 14)) == {f"waermepumpe_{inv.id}": 2.0}
    monkeypatch.setattr(ha, "get_value_at", echt)
    import backend.services.ha_statistics_service as hss
    monkeypatch.setattr(hss, "_ha_statistics_service", ha)
    await korrektur_lauf.tage_neu_bilden(sitzungen_wie(db, get_session), lauf)
    assert await korrektur_lauf.offener_lauf(db, aid, key) is None
    assert await _staende_im_stueck(db, key) == 114
    assert await _sicht(db, a, inv, "waermepumpe") == ZWOELF


async def test_nr111_ha_still_nicht_erreichbar_wirft(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    """Ist Home Assistant während des Speicherns nicht erreichbar (``is_available`` falsch, kein Fehler), schreibt der Schreiber
    nichts — ``fuelle_staende`` wirft, damit der Auftrag offen bleibt (sonst endete die Sperre ohne gespeicherte Stände)."""
    from backend.core.database import get_session
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.tests.pv_achse_matrix import _ha_aus

    a, inv, key = await _anlage(db, "wallbox")
    auftrag = {"key": key, "von": SPRUNG.isoformat(), "bis": RUECK.isoformat()}
    with pytest.raises(kr.KorrekturNichtStartbar):
        await kr.fuelle_staende(kr.sitzungen_wie(db, get_session), a.id, auftrag, ha_svc=_ha_aus())


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_u1_ha_erreichbar_fuehrt_nichts_lauf_endet_wie_zaehlerluecke(db, ha, eingerichtet, monkeypatch, sprengsatz):  # noqa: F811
    """U1 Punkt 2 (ändert E-K2-3): Home Assistant ist erreichbar, führt für die Zeit des Stücks aber nichts (die Statistik ist
    zwischen Eintragen und Lauf weg) — der Lauf endet (``fertig``), die Zeit bekommt eine Lücken-Zeile (kein Heilen), und da
    davor und danach dieselbe Quelle gilt, rechnen Tagesansicht, Bereichs-Leser und Tagesabschluss wie über jede Zählerlücke:
    14.06. 59,5 (Probe P1, Lage «Lauf offen, HA liefert nichts»). Sprengsatz: wie bis 4b-1-K2 — ``fuelle_staende`` wirft, der
    Lauf bleibt offen, die Zeit gesperrt (0,5 · — · 2,0)."""
    from backend.core.database import get_session
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel import korrektur_lauf

    if sprengsatz:
        echt = kr._luecke_nach_dem_lesen

        async def wirft(*a, **k):
            raise LookupError("Home Assistant hat für diese Zeit keine Zählerstände geliefert")
        monkeypatch.setattr(kr, "_luecke_nach_dem_lesen", wirft)
        assert echt is not None
    v._kanal_tage(monkeypatch, {})
    a, inv, key = await _anlage(db, "waermepumpe")
    aid = a.id
    monkeypatch.setattr(korrektur_lauf, "starten", lambda *a, **k: None)
    r = await _stueck(db, aid, key)
    lauf = r["korrektur"][0]["lauf"]
    monkeypatch.setattr(ha, "get_value_at", lambda *_a, **_k: None)        # HA erreichbar, führt für die Zeit nichts
    await korrektur_lauf.tage_neu_bilden(kr.sitzungen_wie(db, get_session), lauf)
    z = await korrektur_lauf.stand(db, lauf)
    zeilen = (await db.execute(select(ZuordnungWechsel).order_by(ZuordnungWechsel.id))).scalars().all()
    if sprengsatz:
        assert z["status"] == "laeuft" and await _sicht(db, a, inv, "waermepumpe") == LUECKE
        return
    assert (z["status"], z["fuellen"]["erledigt"], z["fuellen"]["staende_neu"]) == ("fertig", True, 0)
    assert [(zw.ist_luecken_zeile(w), w.falsch_seit_ts, w.ab_ts, w.lauf) for w in zeilen] == [
        (False, SPRUNG, RUECK, lauf), (True, SPRUNG, RUECK, lauf)]
    _ha_weg(monkeypatch)
    soll = {9: 12.0, 10: 0.5, 11: None, 12: None, 13: None, 14: 59.5, 15: 12.0}
    assert await _sicht(db, a, inv, "waermepumpe") == soll
    assert await _bereich(db, a, inv, "waermepumpe") == {**soll, 10: None}
    assert await _tagesabschluss(db, aid, date(2026, 6, 14)) == {f"waermepumpe_{inv.id}": 59.5}


async def test_u1_ha_fuehrt_erst_spaeter_nur_die_zeit_davor_bleibt_leer(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    """U1 Punkt 2/3 im Lauf: führt Home Assistant im Stück erst ab 12.06. 00:00 Stände, speichert der Lauf sie ab dort und die
    Lücken-Zeile deckt nur [10.06. 01:00, 12.06. 00:00) — 13. und 14.06. je 12,0, nie 0,0."""
    from backend.core.database import get_session
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel import korrektur_lauf

    v._kanal_tage(monkeypatch, {})
    a, inv, key = await _anlage(db, "waermepumpe")
    monkeypatch.setattr(korrektur_lauf, "starten", lambda *a, **k: None)
    r = await _stueck(db, a.id, key)
    lauf = r["korrektur"][0]["lauf"]
    echt = ha.get_value_at
    ab = datetime(2026, 6, 12)
    monkeypatch.setattr(ha, "get_value_at", lambda sid, z, *x, **k: echt(sid, z, *x, **k) if z >= ab else None)
    await korrektur_lauf.tage_neu_bilden(kr.sitzungen_wie(db, get_session), lauf)
    luecken = [(w.falsch_seit_ts, w.ab_ts) for w in (await db.execute(select(ZuordnungWechsel))).scalars().all()
               if zw.ist_luecken_zeile(w)]
    assert luecken == [(SPRUNG, ab)]
    _ha_weg(monkeypatch)
    sicht = await _sicht(db, a, inv, "waermepumpe")
    assert (sicht[13], sicht[14], sicht[15]) == (12.0, 12.0, 12.0)
    assert sicht[12] == 35.5            # dieselbe Quelle davor und danach: die Menge seit 10.06. 00:00 steht am 12.06.


# ═══ Nr. 113 (F4): eine ältere MQTT-Korrektur-Zeile wird auf den Rest gekürzt ═════════════════════════════════════════

async def test_nr113_mqtt_korrektur_teilweise_ueberdeckt_wird_gekuerzt(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    """Eine MQTT-Korrektur [10.06. 01:00, 14.06. 19:00) (selbst eine Lücke), später eine füllbare Korrektur [12.06., 20.06.) mit
    Home Assistant: die MQTT-Zeile wird aufgehoben, ihr Rest [10.06. 01:00, 12.06.) steht als Lücken-Zeile; die Vorschau nennt
    es (kein «Kein Tag muss neu gebildet werden» allein); Tagesansicht 13.06. 12,0 · 14.06. 12,0 (vorher «—»). Korrekturrunde
    U1-K (c) (i), Bauplan Nr. 141: für den Rest ist MQTT als richtig erklärt (die MQTT-Korrektur), davor und danach gilt A — kein
    Zuwachs von A über eine Zeit, für die A als falsch erklärt ist: der Rest ist eine Lücke mit Höhenwechsel, Naht an seinen
    Rändern, 12.06. 11,5 (wie bis 4b-1-K2; in U1 35,5)."""
    from backend.services.zuordnung_wechsel import korrektur as kr
    from backend.services.zuordnung_wechsel.abfrage import vorschau_des_auftrags

    v._kanal_tage(monkeypatch, {})
    a, inv, key = await _anlage(db, "wallbox")
    aid = a.id
    mq = {"art": "mqtt", "mqtt_key": f"inv/{inv.id}/ladung_pv_kwh"}
    await db.execute(SensorSnapshot.__table__.delete().where(SensorSnapshot.zeitpunkt >= SPRUNG, SensorSnapshot.zeitpunkt < RUECK))
    db.add(ZuordnungWechsel(anlage_id=aid, sensor_key=key, erklaert_ts=RUECK, ab_ts=RUECK, vorher=QA, nachher=mq,
                            grund="korrektur", falsch_seit_ts=SPRUNG, herkunft="nachtrag"))
    await db.commit()
    assert await _sicht(db, a, inv, "wallbox") == LUECKE
    au = kr.Auftrag(anlage_id=aid, sensor_key=key, falsch_seit=datetime(2026, 6, 12), ab=datetime(2026, 6, 20), vorher=QA,
                    nachher=QA)
    p = await vorschau_des_auftrags(db, au)
    assert p["luecken_gekuerzt"] == [{"von": SPRUNG.isoformat(), "bis": RUECK.isoformat(),
                                      "rest": [{"von": SPRUNG.isoformat(), "bis": "2026-06-12T00:00:00"}]}]
    assert kr.SATZ_LUECKE_GEKUERZT.format(
        von="10.06.2026 01:00", bis="14.06.2026 19:00",
        rest=kr.SATZ_LUECKE_REST.format(teile="die Zeit vom 10.06.2026 01:00 bis 12.06.2026 00:00 Uhr")) in p["saetze"]
    erg = await kr.fuehre_aus(db, au, ha_svc=ha, jetzt=datetime(2026, 7, 1, 12))
    await db.commit()
    s = await kr.nach_dem_commit(erg, ha_svc=ha, starten=False)
    assert s["staende_offen"]
    from backend.core.database import get_session
    from backend.services.zuordnung_wechsel import korrektur_lauf
    await korrektur_lauf.tage_neu_bilden(kr.sitzungen_wie(db, get_session), s["lauf"])     # der Lauf speichert die Stände
    zeilen = (await db.execute(select(ZuordnungWechsel).order_by(ZuordnungWechsel.id))).scalars().all()
    assert zeilen[0].aufgehoben_durch == erg["summary"]["wechsel_id"]
    assert [(w.falsch_seit_ts, w.ab_ts) for w in zeilen if w.aufgehoben_durch is None and zw.ist_luecke(w)] == [
        (SPRUNG, datetime(2026, 6, 12))]
    assert await _sicht(db, a, inv, "wallbox") == {9: 12.0, 10: 0.5, 11: None, 12: 11.5, 13: 12.0, 14: 12.0, 15: 12.0}
    zw.vergiss(db)
    assert await zw.fortsetzungs_naehte(db, aid, key) == [SPRUNG, datetime(2026, 6, 12)]


# ═══ Nr. 116: E-K6, N3, N4 ═════════════════════════════════════════════════════════════════════════════════════════════

async def test_ek6_abruf_fehler_in_der_pruef_route_ist_nicht_startbar(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    """Wirft ein Abruf aus Home Assistant in der Prüfung des Stücks, antwortet die Prüf-Route wie bei «nicht erreichbar»
    (nicht startbar, der bestehende Satz) — kein 500; die Route des Eintrags lehnt mit 422 ab, nichts wird geschrieben."""
    from fastapi import HTTPException

    from backend.api.routes import sensorwechsel as sw
    from backend.services.zuordnung_wechsel import korrektur as kr

    v._kanal_tage(monkeypatch, {})
    a, inv, key = await _anlage(db, "wallbox")

    def wirft(*_a, **_k):
        raise ConnectionError("Verbindung abgebrochen")
    monkeypatch.setattr(ha, "get_value_at", wirft)
    p = (await sw.pruefe_stueck(a.id, _body(key), db))["korrektur"]
    assert (p["startbar"], p["saetze"]) == (False, [kr.SATZ_NICHT_ERREICHBAR])
    vor = await db.scalar(select(func.count()).select_from(SensorSnapshot))
    with pytest.raises(HTTPException) as e:
        await sw.stueck_korrigieren(a.id, _body(key), db)
    assert (e.value.status_code, e.value.detail) == (422, kr.SATZ_NICHT_ERREICHBAR)
    assert await db.scalar(select(func.count()).select_from(SensorSnapshot)) == vor
    assert (await db.execute(select(func.count()).select_from(ZuordnungWechsel))).scalar_one() == 0


async def test_n3_meldung_nennt_die_tage_des_ersten_und_letzten_versetzten_stands(db, ha, monkeypatch):  # noqa: F811
    """E-K3/S11: Sprung mit der Zeile 10.06. 00:00, Rückgang mit der Zeile 15.06. 00:00 — die Meldung nennt «vom 10.06.2026 bis
    14.06.2026» (die versetzten Stände), nicht den Kalendertag der Schritte (09.06. bzw. 15.06.)."""
    v._kanal_tage(monkeypatch, {})
    a, *_ = await v._anlage(db, staende=v._reihe(sprung=9 * 24, rueck=14 * 24), spiegel=False)
    (e,) = await v._pruefe(db, a)
    assert "Zählerstände vom 10.06.2026 bis 14.06.2026 um" in e.meldung


def test_n4_aufgehobene_korrektur_zeile_mit_offenem_lauf_sperrt_nicht():
    """Nr. 106: die Sperre folgt dem offenen Lauf — aber nur für eine geltende Korrektur-Zeile; eine aufgehobene sperrt nicht."""
    gilt = zw.Wechsel("k", RUECK, QA, QA, "korrektur", SPRUNG, None, None, 7, "L1")
    aufgehoben = zw.Wechsel("k", RUECK, QA, QA, "korrektur", SPRUNG, 9, None, 7, "L1")
    assert zw.gesperrte_stuecke([gilt], frozenset({"L1"})) == [(SPRUNG, RUECK)]
    assert zw.gesperrte_stuecke([aufgehoben], frozenset({"L1"})) == []
    assert zw.gesperrte_stuecke([gilt], frozenset()) == []


def test_zaehler_naht_luecken_regel():
    """Die eine Lücken-Regel (``core/berechnungen/zaehler_naht``, Nr. 112): Anker vor einem Stück ⇒ dessen Ende; Fensterende im
    Stück; keine Messung ohne zwei Stände in einem Abschnitt."""
    from backend.core.berechnungen.zaehler_naht import ende_der_luecke_davor, endet_in_luecke, traegt_messung

    t = lambda h: datetime(2026, 6, 10) + timedelta(hours=h)  # noqa: E731
    st = [(t(1), t(20))]
    assert ende_der_luecke_davor(t(0), t(23), st) == t(20)
    assert ende_der_luecke_davor(t(21), t(23), st) is None
    assert ende_der_luecke_davor(None, t(23), st) is None
    assert endet_in_luecke(t(5), st) and endet_in_luecke(t(1), st) and not endet_in_luecke(t(20), st)
    assert not traegt_messung([(t(0), 1.0), (t(23), 2.0)], [t(1), t(20)])
    assert traegt_messung([(t(0), 1.0), (t(22), 2.0), (t(23), 2.5)], [t(1), t(20)])


async def test_s4_luecken_tag_hat_eigenen_grund(db, monkeypatch, eingerichtet):  # noqa: F811
    """S4: am «—» eines Lücken-Tags steht der eigene Grund («eine Korrektur hat die Zählerstände dieser Zeit verworfen»), nicht
    «Tageswerte entstehen ab der Zuordnung …»; ein Tag ohne Stände außerhalb einer Lücke behält den bisherigen Grund."""
    from backend.core.tageswert_grund import GRUND_KEINE_ZAEHLERSTAENDE, GRUND_LUECKE_VERWORFEN, tageswert_grund_text
    from backend.services.snapshot.aggregator import get_tagesdetail_kwh

    v._ha_verschoben(monkeypatch, 1906.5)
    v._kanal_tage(monkeypatch, {})
    a, inv, key = await _anlage(db, "wallbox")
    await db.execute(SensorSnapshot.__table__.delete().where(SensorSnapshot.zeitpunkt >= datetime(2026, 6, 22),
                                                            SensorSnapshot.zeitpunkt < datetime(2026, 6, 24)))
    await db.commit()
    await _stueck(db, a.id, key)
    _ha_weg(monkeypatch)                     # sonst heilte «Zuordnung zum Zeitpunkt» den 23.06. aus Home Assistant
    zw.vergiss(db)
    invs = {str(inv.id): await db.get(Investition, inv.id)}
    t12 = await get_tagesdetail_kwh(db, a, invs, date(2026, 6, 12), tageszeile_rueckwaerts=True)
    t23 = await get_tagesdetail_kwh(db, a, invs, date(2026, 6, 23), tageszeile_rueckwaerts=True)
    assert t12.grund_je_feld["emob_ladung_pv_kwh"] == GRUND_LUECKE_VERWORFEN
    assert t23.grund_je_feld["emob_ladung_pv_kwh"] == GRUND_KEINE_ZAEHLERSTAENDE
    assert "eine Korrektur hat die Zählerstände dieser Zeit verworfen" in tageswert_grund_text(GRUND_LUECKE_VERWORFEN)


def test_nr111_fortschritt_staende_im_lauf_sind_kein_ausstehendes_fuellen():
    """Speichert der Hintergrund-Lauf nur noch die Stände (Kanal-Teil nach dem Commit gelaufen), sagt die Fläche «Korrektur
    läuft …» — nicht «Das Füllen aus Home Assistant steht noch aus …»; das steht erst nach einem gescheiterten Versuch."""
    from backend.services.zuordnung_wechsel.korrektur_lauf import FUELLEN_PRAEFIX, fuellen_offen

    laeuft = {"fuellen": {"erledigt": False, "kanal_erledigt": True}, "fehler": []}
    assert fuellen_offen(laeuft) is False
    assert fuellen_offen({**laeuft, "fehler": [{"tag": None, "grund": FUELLEN_PRAEFIX + "ConnectionError: weg"}]}) is True
    assert fuellen_offen({"fuellen": {"erledigt": False}, "fehler": []}) is True
    assert fuellen_offen({"fuellen": {"erledigt": True, "kanal_erledigt": True}, "fehler": []}) is False
    assert fuellen_offen({"fuellen": None}) is False
