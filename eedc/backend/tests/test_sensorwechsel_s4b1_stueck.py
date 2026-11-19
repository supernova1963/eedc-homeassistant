"""Sensorwechsel mit Grund, Sitzung 4b-1 «Stück» (Bauplan «Zu §14» Nr. 93–98, Messblatt ``opus-berichte/SENSORWECHSEL-S4B0-…``).

Proben mit den Zahlen des Messblatts als Soll (Saat des Befunds ``zaehler_versatz``: Wallbox «Ladung PV», wahrer Zähler 100 +
0,5 kWh je Stunde = 12,0 kWh je Tag, Stück um 80 kWh versetzt vom 10.06. 01:00 bis zum Rückgang 14.06. 19:00):

* **füllbar** (HA erreichbar, beide Rand-Stände = HAs Rohsumme): «Grund nachtragen → Korrektur» am Befund verwirft das Stück,
  B-0 füllt aus der Quelle ⇒ 12,0 an jedem Tag, 9.–16.06. 84,0, Monat 336,0; der Befund ist weg.
* **nicht füllbar** (ohne Home Assistant, HAs Summe verschoben): Lücken-Zeile; seit U1 ohne Höhenwechsel wie jede Zählerlücke ⇒
  10.06. 0,5 · 11.–13.06. kein Wert · 14.06. 59,5 · 9.–16.06. 84,0 · Monat 336,0; mit Höhenwechsel (andere Quelle davor,
  Fortsetzung dazwischen) Nähte ⇒ 14.06. 2,0, 9.–16.06. 26,5 (statt 6 012,0 am Tag des Rückgangs).
* **Nr. 91 a** — die gewöhnliche Korrektur ohne Füllen (Wechsel A → C ohne Home Assistant, «Falsch seit» am Sprung): 14.06.
  2,0 statt 6 012,0; rückwirkend für eine schon eingetragene MQTT-Korrektur ohne neue Zeile.
* **Nr. 91 d** — in einer Überlappung gilt die jüngste Korrektur (``zeitpunkt.quelle_am``).
* **Nr. 97** — ``kanal/korrektur._spaetere_richtige`` nimmt die Quelle an ``ab − 1 h`` mit.
* **H-4 (Nr. 96, Nr. 91 c)** — an einem früheren Wechsel A → X → A geht «Korrektur» über das Stück, auch mit einem späteren
  Wechsel oder Zählertausch; A → X → C bleibt gesperrt.
* **Nr. 91 e** — ``ab_ts = ab`` zählt nicht zum Intervall; der Nachbau wird an der Stunde vor ``ab_ts`` geprüft.
* **Routen am Befund**: kein frei wählbares Stück (404), nur «Korrektur» (422), die Prüfung schreibt nichts, Vorschau = Lauf.

Keine Probe liest die Uhr; die Zeitpunkte liegen im Juni (die Suite fährt auch in ``Pacific/Auckland`` und ``UTC``).
Schwesterdateien: test_daten_checker_zaehler_versatz.py (Befund), test_sensorwechsel_s4k_proben.py, test_sensorwechsel_s4_nachtrag.py.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import func, select

from backend.models import activity_log, mqtt_gateway_mapping  # noqa: F401 — Tabellen der Routen (Teil-Schema der Fixture)
from backend.models.investition import Investition
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.zuordnung_wechsel import ZuordnungWechsel
from backend.services.zuordnung_wechsel import zeitpunkt as zw
from backend.tests import test_daten_checker_zaehler_versatz as v
from backend.tests.test_daten_checker_zaehler_versatz import ha, ohne_ha  # noqa: F401 — Fixtures

SPRUNG = v.T0 + timedelta(hours=v.SPRUNG_H)        # 10.06. 01:00
RUECK = v.T0 + timedelta(hours=v.RUECK_H)          # 14.06. 19:00
TAGE = (9, 10, 11, 12, 13, 14, 15)
QA = {"art": "ha", "entity_id": v.SENSOR}


@pytest.fixture
def eingerichtet(monkeypatch):
    """Home Assistant gilt als eingerichtet (der Dienst nimmt dann den Dienst des Prozesses: die Attrappe ``ha``)."""
    import backend.services.zuordnung_wechsel.korrektur as kr

    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: True)


async def _tagesansicht(db, a, wid) -> dict[int, float | None]:
    """«Ladung PV» der Tagesansicht (Reihe — die Saat hat keinen Kanal) je Tag 9.–15.06."""
    from backend.models.anlage import Anlage
    from backend.services.kanal import merken
    from backend.services.snapshot.aggregator import get_tagesdetail_kwh

    zw.vergiss(db)
    merken.invalidiere(a.id)
    a_ = (await db.execute(select(Anlage).where(Anlage.id == a.id))).scalar_one()
    invs = {str(wid): await db.get(Investition, wid)}
    out = {}
    for d in TAGE:
        w = (await get_tagesdetail_kwh(db, a_, invs, date(2026, 6, d), tageszeile_rueckwaerts=True)).werte.get(
            "emob_ladung_pv_kwh")
        out[d] = None if w is None else round(w, 2)
    return out


async def _mengen(db, aid, key) -> tuple[float | None, float | None]:
    from backend.services.snapshot import reader

    zw.vergiss(db)
    return (await reader.delta(db, aid, key, v.SENSOR, datetime(2026, 6, 9), datetime(2026, 6, 16)),
            await reader.delta(db, aid, key, v.SENSOR, datetime(2026, 6, 1), datetime(2026, 6, 29)))


def _body(key, grund="korrektur", sprung="2026-06-10T01:00", rueck="2026-06-14T19:00"):
    from backend.api.routes import sensorwechsel as sw

    return sw.StueckRequest(sensor_key=key, sprung=sprung, rueckgang=rueck, grund=grund)


async def _stueck(db, aid, key, **kw):
    from backend.api.routes import sensorwechsel as sw
    from backend.services.zuordnung_wechsel import korrektur_lauf

    r = await sw.stueck_korrigieren(aid, _body(key, **kw), db)
    for t in list(korrektur_lauf._AUFGABEN.values()):
        await t
    return r


async def _abgelehnt(coro) -> HTTPException:
    with pytest.raises(HTTPException) as e:
        await coro
    return e.value


# ═══ füllbar: Stück aus der Reihe ersetzt ════════════════════════════════════════════════════════════════════════════

async def test_fuellbar_vorschau_gleich_lauf_und_zwoelf_an_jedem_tag(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    from backend.api.routes import sensorwechsel as sw

    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, spiegel=False)
    aid, wid = a.id, wb.id
    assert (await _tagesansicht(db, a, wid))[10] == 92.0
    (e,) = await v._pruefe(db, a)
    assert (e.werte["lage"], e.werte["sprung"], e.werte["rueckgang"]) == ("fuellbar", "2026-06-10T01:00", "2026-06-14T19:00")
    vor = await db.scalar(select(func.count()).select_from(SensorSnapshot))
    p = await sw.pruefe_stueck(aid, _body(key), db)
    assert await db.scalar(select(func.count()).select_from(SensorSnapshot)) == vor          # die Prüfung schreibt nichts
    assert (p["gruende"], p["korrektur_nicht"], p["stueck"]) == (
        ["korrektur"], None, {"sprung": "2026-06-10T01:00:00", "rueckgang": "2026-06-14T19:00:00"})
    assert p["wechsel_satz"] == ("Vom 10.06.2026 01:00 bis 14.06.2026 19:00 Uhr liegen die gespeicherten Zählerstände dieses "
                                 "Felds um 80,5 kWh neben denen davor und danach; davor und danach gilt sensor.pv_ladung.")
    k = p["korrektur"]
    assert (k["zaehlerstaende"], k["luecke"], k["mit_home_assistant"]) == (114, None, True)
    r = await _stueck(db, aid, key)
    assert r["korrektur"][0]["zaehlerstaende_geloescht"] == k["zaehlerstaende"] == 114
    (zeile,) = (await db.execute(select(ZuordnungWechsel))).scalars().all()
    assert (zeile.grund, zeile.falsch_seit_ts, zeile.ab_ts, zeile.vorher, zeile.nachher) == ("korrektur", SPRUNG, RUECK, QA, QA)
    assert await _tagesansicht(db, a, wid) == {d: 12.0 for d in TAGE}
    assert await _mengen(db, aid, key) == (pytest.approx(84.0), pytest.approx(336.0))
    assert await v._pruefe(db, a) == []
    # nicht noch einmal: die Erkennung findet das Stück nicht mehr
    assert (await _abgelehnt(sw.pruefe_stueck(aid, _body(key), db))).status_code == 404


# ═══ nicht füllbar: Lücke — Nähte nur bei Höhenwechsel (U1) ═════════════════════════════════════════════════════════════════════════════

LUECKE = {9: 12.0, 10: 0.5, 11: None, 12: None, 13: None, 14: 2.0, 15: 12.0}


#: «Wie jede Zählerlücke» (Entscheid Gernot 19.11.2026, Bauplan «Zu §14» Nr. 119/120): dieselbe Quelle auf derselben Höhe davor
#: und danach, nichts füllt — die Menge der leeren Zeit steht am Tag, an dem sie endet (seit U1 in jeder Lage).
ZAEHLERLUECKE = {9: 12.0, 10: 0.5, 11: None, 12: None, 13: None, 14: 59.5, 15: 12.0}


@pytest.fixture
def verschoben(monkeypatch, eingerichtet):  # noqa: F811
    """Home Assistant erreichbar, seine Summe 1 906,5 kWh über der Reihe («Stände passen nicht»): die Korrektur über das Stück
    füllt nicht — seit U1 (H-K2-1 Option A) bekommt die Zeit eine Lücken-Zeile (kein Heilen), und da davor und danach dieselbe
    Quelle gilt, rechnen die Leser über sie wie über jede Zählerlücke."""
    return v._ha_verschoben(monkeypatch, 1906.5)


async def test_ohne_home_assistant_wie_jede_zaehlerluecke(db, ohne_ha, monkeypatch):  # noqa: F811
    """Nr. 119/120: ohne Home Assistant, davor und danach dieselbe Quelle — keine Lücken-Zeile, keine Naht; die Tagesansicht
    rechnet über die leere Zeit wie über jede Zählerlücke (14.06. 59,5), Bereich und Monat wie ohne Korrektur (84,0 / 336,0)."""
    from backend.api.routes import sensorwechsel as sw
    from backend.services.zuordnung_wechsel import korrektur as kr

    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, spiegel=False)
    aid, wid = a.id, wb.id
    (e,) = await v._pruefe(db, a)
    assert e.werte["lage"] == "ohne_home_assistant"
    p = await sw.pruefe_stueck(aid, _body(key), db)
    k = p["korrektur"]
    assert k["luecke"] == {"von": "2026-06-10T01:00:00", "bis": "2026-06-14T19:00:00",
                           "tage_ohne_wert": ["2026-06-11", "2026-06-12", "2026-06-13"],
                           "tage_teilwert": ["2026-06-10"], "wie_zaehlerluecke": True, "tag_der_menge": "2026-06-14"}
    assert kr.SATZ_ZAEHLERLUECKE.format(von="10.06.2026 01:00", bis="14.06.2026 19:00") in k["saetze"]
    assert ("Wo die Tagesansicht den Wert aus den gespeicherten Zählerständen bildet, zeigt sie vom 11.06.2026 bis 13.06.2026 "
            "keinen Wert und am 10.06.2026 nur den Teil außerhalb dieser Zeit und am 14.06.2026 die Menge seit dem letzten "
            "Zählerstand davor.") in k["saetze"]
    await _stueck(db, aid, key)
    stueck, luecke = (await db.execute(select(ZuordnungWechsel).order_by(ZuordnungWechsel.id))).scalars().all()
    assert stueck.nachher == QA
    # U1 (H-K2-1 Option A): die Lücken-Zeile steht in jeder Lage (hier nicht heilen, nicht füllen) — ihre Ränder sind keine Nähte
    assert (zw.ist_luecken_zeile(luecke), luecke.falsch_seit_ts, luecke.ab_ts) == (True, SPRUNG, RUECK)
    zw.vergiss(db)
    assert await zw.fortsetzungs_naehte(db, aid, key) == []
    assert await _tagesansicht(db, a, wid) == ZAEHLERLUECKE
    assert await _mengen(db, aid, key) == (pytest.approx(84.0), pytest.approx(336.0))
    assert await v._pruefe(db, a) == []


async def test_ohne_home_assistant_andere_quelle_davor_bleibt_luecke(db, ohne_ha, monkeypatch):  # noqa: F811
    """Gegenlage zu Nr. 119/120: gilt am letzten Stand davor eine andere Quelle (verzeichneter Wechsel C → A am Sprung), ist die
    Zählerhöhe eine andere — die Lücke bleibt (Lücken-Zeile, Nähte, 14.06. 2,0)."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, spiegel=False)
    aid, wid = a.id, wb.id
    await _wechsel(db, aid, key, SPRUNG, {"art": "ha", "entity_id": "sensor.c"}, QA)      # davor galt sensor.c
    await db.commit()
    au = kr.Auftrag(anlage_id=aid, sensor_key=key, falsch_seit=SPRUNG, ab=RUECK, vorher=QA, nachher=QA, stueck=True)
    la = await kr.lage(db, au, ha_svc=None)
    assert la.luecke == (SPRUNG, RUECK) and not la.zaehlerluecke
    await kr.fuehre_aus(db, au, ha_svc=None, jetzt=datetime(2026, 7, 1, 12))
    await db.commit()
    zw.vergiss(db)
    assert await zw.fortsetzungs_naehte(db, aid, key) == [SPRUNG, RUECK]
    assert await _tagesansicht(db, a, wid) == LUECKE


async def test_ohne_home_assistant_fortsetzung_dazwischen_bleibt_luecke(db, ohne_ha, monkeypatch):  # noqa: F811
    """Gegenlage zu Nr. 119/120: eine Fortsetzung zwischen dem letzten Stand davor und dem ersten danach — andere Zählerhöhe,
    die Lücke bleibt (Vorschau und Leser). U1: die Fortsetzung liegt vor dem Intervall (die Reihe hat vor dem Sprung eine
    Lücke von fünf Stunden) — eine Fortsetzung **im** Intervall hebt die Korrektur auf (Bauplan §13 Nr. 67), danach ist sie
    kein Höhenwechsel mehr (Gegenprobe unten)."""
    from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG
    from backend.services.zuordnung_wechsel import korrektur as kr

    v._kanal_tage(monkeypatch, {})
    loch = range(v.SPRUNG_H - 5, v.SPRUNG_H)
    a, wb, key = await v._anlage(db, staende=[x for i, x in enumerate(v._reihe()) if i not in loch], spiegel=False)
    aid = a.id
    for zeit in (SPRUNG - timedelta(hours=3), SPRUNG + timedelta(hours=30)):
        db.add(ZuordnungWechsel(anlage_id=aid, sensor_key=key, erklaert_ts=zeit, ab_ts=zeit, vorher=QA, nachher=QA,
                                grund=GRUND_FORTSETZUNG, herkunft="wechsel"))
    await db.commit()
    au = kr.Auftrag(anlage_id=aid, sensor_key=key, falsch_seit=SPRUNG, ab=RUECK, vorher=QA, nachher=QA, stueck=True)
    la = await kr.lage(db, au, ha_svc=None)
    assert la.luecke == (SPRUNG, RUECK) and not la.zaehlerluecke
    await kr.fuehre_aus(db, au, ha_svc=None, jetzt=datetime(2026, 7, 1, 12))
    await db.commit()
    zw.vergiss(db)
    assert await zw.fortsetzungs_naehte(db, aid, key) == [SPRUNG - timedelta(hours=3), SPRUNG, RUECK]


TAUSCH = SPRUNG + timedelta(hours=30)


@pytest.mark.parametrize("sprengsatz", [False, True])
@pytest.mark.parametrize("fall", ["gleiche_hoehe", "echter_tausch", "fremde_quelle"])
async def test_u1k_zaehlertausch_im_intervall_bleibt_ein_hoehenwechsel(db, ohne_ha, monkeypatch, fall, sprengsatz):  # noqa: F811
    """Korrekturrunde U1-K (c) (ii), Bauplan Nr. 141 (ändert U-3): ein eingetragener Zählertausch derselben Quelle (A → A) im
    verworfenen Intervall ist ein Höhenwechsel, **auch wenn die Korrektur ihn aufgehoben hat** — die Lücke hat Nähte:
    0,5 · — · — · — · 2,0. Mit echtem Höhenunterschied (der neue Zähler 4 000 höher) nie 4 059,5. Eine Fortsetzung nur einer
    anderen Quelle (X → X) zählt nicht: wie jede Zählerlücke, 59,5. Sprengsatz: aufgehobene Fortsetzungen zählen nicht (U1) ⇒
    59,5 bzw. 4 059,5."""
    from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG
    from backend.services.zuordnung_wechsel import korrektur as kr

    v._kanal_tage(monkeypatch, {})
    if sprengsatz:
        echt = zw._zaehlertausch_dazwischen
        monkeypatch.setattr(zw, "_zaehlertausch_dazwischen",
                            lambda w, q, vor, nach: echt([x for x in w or () if x.aufgehoben_durch is None], q, vor, nach))
    plus = 4000.0 if fall == "echter_tausch" else 0.0
    reihe = [(z, wert + (plus if z >= TAUSCH else 0.0)) for z, wert in v._reihe()]
    a, wb, key = await v._anlage(db, staende=reihe, spiegel=False)
    aid, wid = a.id, wb.id
    q = {"art": "ha", "entity_id": "sensor.x"} if fall == "fremde_quelle" else QA
    if fall == "fremde_quelle":            # verzeichnet A → X am Sprung; «Zähler getauscht» trug ein, während X galt
        db.add(ZuordnungWechsel(anlage_id=aid, sensor_key=key, erklaert_ts=SPRUNG, ab_ts=SPRUNG, vorher=QA, nachher=q,
                                grund=None, herkunft="altbestand"))
    db.add(ZuordnungWechsel(anlage_id=aid, sensor_key=key, erklaert_ts=TAUSCH, ab_ts=TAUSCH, vorher=q, nachher=q,
                            grund=GRUND_FORTSETZUNG, herkunft="wechsel"))
    await db.commit()
    au = kr.Auftrag(anlage_id=aid, sensor_key=key, falsch_seit=SPRUNG, ab=RUECK, vorher=QA, nachher=QA, stueck=True)
    la = await kr.lage(db, au, ha_svc=None)
    await kr.fuehre_aus(db, au, ha_svc=None, jetzt=datetime(2026, 7, 1, 12))
    await db.commit()
    zw.vergiss(db)
    sicht = await _tagesansicht(db, a, wid)
    if fall == "fremde_quelle" or sprengsatz:
        assert la.zaehlerluecke
        assert sicht == {**ZAEHLERLUECKE, 14: 59.5 + plus}
        return
    assert la.luecke == (SPRUNG, RUECK) and not la.zaehlerluecke          # Vorschau = Lauf
    assert await zw.fortsetzungs_naehte(db, aid, key) == [SPRUNG, RUECK]           # der Tausch selbst ist aufgehoben
    assert sicht == LUECKE and 4059.5 not in sicht.values()


async def test_ha_summe_verschoben_wie_zaehlerluecke_und_kein_heilen_im_stueck(db, monkeypatch, eingerichtet):
    """U1 Punkt 1, Probe P3 (H-K2-1 Option A): HAs Summe liegt 1 906,5 über der Reihe — B-0 füllte das Stück mit einem anderen
    Niveau (Messblatt b: 10.06. 1 918,5). Im Stück gilt die Lücken-Zeile (Quelle unbekannt ⇒ kein Stand geheilt), ihre Ränder
    sind keine Nähte (davor und danach dieselbe Quelle): 14.06. 59,5, Bereich 84,0, Monat 336,0 — nie 1 918,5."""
    v._ha_verschoben(monkeypatch, 1906.5)
    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, spiegel=False)
    aid, wid = a.id, wb.id
    (e,) = await v._pruefe(db, a)
    assert e.werte["lage"] == "staende_passen_nicht"
    from backend.api.routes import sensorwechsel as sw
    from backend.services.zuordnung_wechsel import korrektur as kr

    k = (await sw.pruefe_stueck(aid, _body(key), db))["korrektur"]
    assert kr.SATZ_KEIN_TAG not in k["saetze"]             # mit einer Lücke kommt der Wert nicht aus dem richtigen Sensor
    assert kr.SATZ_ZAEHLERLUECKE.format(von="10.06.2026 01:00", bis="14.06.2026 19:00") in k["saetze"]
    assert (k["luecke"]["wie_zaehlerluecke"], k["luecke"]["tag_der_menge"]) == (True, "2026-06-14")
    await _stueck(db, aid, key)
    zw.vergiss(db)
    assert await zw.fortsetzungs_naehte(db, aid, key) == []
    assert await _tagesansicht(db, a, wid) == ZAEHLERLUECKE
    assert await _bereich(db, a, wid) == {**ZAEHLERLUECKE, 10: None}       # der Bereichs-Leser zählt den Teil davor nicht
    assert await _mengen(db, aid, key) == (pytest.approx(84.0), pytest.approx(336.0))
    assert await db.scalar(select(func.count()).select_from(SensorSnapshot).where(
        SensorSnapshot.zeitpunkt >= SPRUNG, SensorSnapshot.zeitpunkt < RUECK)) == 0      # kein Stand im Stück geheilt
    assert zw.quelle_am((await zw.lade_wechsel(db, aid)).get(key), datetime(2026, 6, 12, 12)) is zw.UNBEKANNT
    assert zw.quelle_am((await zw.lade_wechsel(db, aid)).get(key), datetime(2026, 6, 9, 12)) == QA


# ═══ Nr. 91 a: gewöhnliche Korrektur ohne Füllen ═════════════════════════════════════════════════════════════════════

async def test_nr91a_korrektur_am_wechsel_ohne_ha_zeigt_die_luecke(db, ohne_ha, monkeypatch):  # noqa: F811
    """Echter Wechsel A → C am «Rückgang» (1 000 → 7 000), «Grund nachtragen → Korrektur» mit «Falsch seit» am Sprung: am
    HEAD 14.06. 6 012,0 (danach 6 059,5), jetzt die Lücke."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    v._kanal_tage(monkeypatch, {})
    reihe = [(v.T0 + timedelta(hours=h), (7000.0 if h >= v.RUECK_H else 1000.0) + 0.5 * h) for h in range(29 * 24)]
    a, wb, key = await v._anlage(db, staende=reihe, spiegel=False)
    aid, wid = a.id, wb.id
    assert (await _tagesansicht(db, a, wid))[14] == 6012.0
    QC = {"art": "ha", "entity_id": "sensor.c"}
    await kr.fuehre_aus(db, kr.Auftrag(anlage_id=aid, sensor_key=key, falsch_seit=SPRUNG, ab=RUECK, vorher=QA, nachher=QC),
                        ha_svc=None, jetzt=datetime(2026, 7, 1, 12))
    await db.commit()
    assert await _tagesansicht(db, a, wid) == LUECKE


async def test_nr91a_ha_ohne_geschichte_des_richtigen_sensors_ist_eine_luecke(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    """Mit Home Assistant, aber ohne Geschichte des richtigen Sensors (``sensor.c`` kennt HA nicht): das ganze Intervall ist
    eine Lücke (eine Zeile mit ``nachher`` leer), statt 6 012,0 am Tag des Wechsels."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    v._kanal_tage(monkeypatch, {})
    # vor dem Wechsel die Stände von SENSOR (= HAs Summe, ``v._ha``), danach C (7 000 + …)
    reihe = [(v.T0 + timedelta(hours=h), (7000.0 if h >= v.RUECK_H else 100.0) + 0.5 * h) for h in range(29 * 24)]
    a, wb, key = await v._anlage(db, staende=reihe, spiegel=False)
    aid, wid = a.id, wb.id
    QC = {"art": "ha", "entity_id": "sensor.c"}
    au = kr.Auftrag(anlage_id=aid, sensor_key=key, falsch_seit=SPRUNG, ab=RUECK, vorher=QA, nachher=QC)
    assert (await kr.lage(db, au, ha_svc=ha)).luecke == (SPRUNG, RUECK)
    await kr.fuehre_aus(db, au, ha_svc=ha, jetzt=datetime(2026, 7, 1, 12))
    await db.commit()
    assert await _tagesansicht(db, a, wid) == LUECKE
    # führt HA den richtigen Sensor (hier: SENSOR seit jeher) auf der Höhe der Stände, gibt es keine Lücke
    au2 = kr.Auftrag(anlage_id=aid, sensor_key=key, falsch_seit=datetime(2026, 6, 5), ab=datetime(2026, 6, 6), vorher=QA, nachher=QA)
    assert (await kr.lage(db, au2, ha_svc=ha)).luecke is None
    # U1-K (d): die Stände um 20.06. sind die von C (7 000 + …), HA führt SENSOR auf 100 + … — füllen nur auf geprüfter Höhe
    au3 = kr.Auftrag(anlage_id=aid, sensor_key=key, falsch_seit=datetime(2026, 6, 20), ab=datetime(2026, 6, 21), vorher=QA, nachher=QA)
    assert (await kr.lage(db, au3, ha_svc=ha)).luecke == (datetime(2026, 6, 20), datetime(2026, 6, 21))


async def test_nr91a_rueckwirkend_eine_mqtt_korrektur_ohne_neue_zeile(db, monkeypatch):
    """Eine schon eingetragene Korrektur mit MQTT-Quelle (keine Geschichte): ihre Ränder sind Nähte — aus der Zeile, ohne
    Migration (Bauplan Nr. 96)."""
    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, spiegel=False)
    aid, wid = a.id, wb.id
    await db.execute(SensorSnapshot.__table__.delete().where(
        SensorSnapshot.zeitpunkt >= SPRUNG, SensorSnapshot.zeitpunkt < RUECK))
    db.add(ZuordnungWechsel(anlage_id=aid, sensor_key=key, erklaert_ts=RUECK, ab_ts=RUECK, vorher=QA,
                            nachher={"art": "mqtt", "mqtt_key": "x"}, grund="korrektur", falsch_seit_ts=SPRUNG,
                            herkunft="nachtrag"))
    await db.commit()
    assert await _tagesansicht(db, a, wid) == LUECKE


def test_ist_luecke():
    w = zw.Wechsel("k", RUECK, QA, QA, "korrektur", SPRUNG)
    assert not zw.ist_luecke(w)
    assert zw.ist_luecke(zw.Wechsel("k", RUECK, QA, None, "korrektur", SPRUNG))
    assert zw.ist_luecke(zw.Wechsel("k", RUECK, QA, {"art": "mqtt"}, "korrektur", SPRUNG))
    assert not zw.ist_luecke(zw.Wechsel("k", RUECK, QA, None, "korrektur", SPRUNG, aufgehoben_durch=3))
    assert not zw.ist_luecke(zw.Wechsel("k", RUECK, QA, None, None, SPRUNG))
    assert zw.naehte_der_fortsetzung([zw.Wechsel("k", RUECK, QA, None, "korrektur", SPRUNG),
                                      zw.Wechsel("k", RUECK, QA, QA, "fortsetzung")]) == [SPRUNG, RUECK]


def test_nr105_luecken_zeile_zaehlt_vor_ihr_nicht_als_wechsel():
    """Nr. 105 (F7): vor einer Lücken-Zeile gilt die Quelle des nächsten echten Wechsels — nicht das ``vorher`` der
    Lücken-Zeile (dort steht die verworfene Quelle); in ihrem Intervall gilt sie (unbekannt)."""
    QX, QC = {"art": "ha", "entity_id": "sensor.x"}, {"art": "ha", "entity_id": "sensor.c"}
    echt = zw.Wechsel("k", datetime(2026, 6, 20), QA, QC, None, id=1)
    luecke = zw.Wechsel("k", RUECK, QX, None, "korrektur", SPRUNG, id=2)
    assert zw.ist_luecken_zeile(luecke) and not zw.ist_luecken_zeile(echt)
    assert zw.quelle_am([echt, luecke], datetime(2026, 6, 5)) == QA
    assert zw.quelle_am([echt, luecke], datetime(2026, 6, 12)) is zw.UNBEKANNT


# ═══ Nr. 91 d: die jüngste Korrektur gewinnt ═════════════════════════════════════════════════════════════════════════

def test_nr91d_in_der_ueberlappung_gilt_die_juengste_korrektur():
    QY = {"art": "ha", "entity_id": "sensor.y"}
    alt = zw.Wechsel("k", datetime(2026, 6, 13), None, QY, "korrektur", datetime(2026, 6, 12), id=1)
    neu = zw.Wechsel("k", RUECK, None, QA, "korrektur", SPRUNG, id=2)
    for liste in ([alt, neu], [neu, alt]):
        assert zw.quelle_am(liste, datetime(2026, 6, 12, 12)) == QA
    assert zw.quelle_am([alt], datetime(2026, 6, 12, 12)) == QY


# ═══ Nr. 97: Kanal-Grenze ab − 1 h ═══════════════════════════════════════════════════════════════════════════════════

def test_nr97_spaetere_richtige_nimmt_die_quelle_eine_stunde_vor_ab_mit():
    from backend.models.kanal import FAMILIE_SPIEGEL
    from backend.services.kanal.korrektur import _spaetere_richtige

    ab = int(RUECK.timestamp())
    q = lambda t, sid: SimpleNamespace(gueltig_ab=t, familie=FAMILIE_SPIEGEL, statistic_id=sid, verworfen_ts=None)  # noqa: E731
    a_vor, c = q(ab - 3600, "sensor.a"), q(ab + 5 * 86400, "sensor.c")
    assert _spaetere_richtige([q(ab - 2 * 3600, "sensor.a"), a_vor, c], ab, "sensor.a") == [a_vor]
    assert _spaetere_richtige([q(ab - 2 * 3600, "sensor.a"), c], ab, "sensor.a") == []


# ═══ H-4 (Nr. 96, Nr. 91 c): früherer Wechsel über das Stück ═════════════════════════════════════════════════════════

async def _wechsel(db, aid, key, ab, vorher, nachher):
    db.add(ZuordnungWechsel(anlage_id=aid, sensor_key=key, erklaert_ts=ab, ab_ts=ab, vorher=vorher, nachher=nachher,
                            grund=None, herkunft="altbestand"))


async def _lagen(db, aid) -> list[tuple]:
    """Je Zeile: angebotene Gründe, Stück ``(Sprung, Rückgang, Quelle)`` und der Sperrsatz."""
    from backend.models.anlage import Anlage
    from backend.services.zuordnung_wechsel import nachtrag

    a = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    zw.vergiss(db)
    out = []
    for row in (await db.execute(select(ZuordnungWechsel).order_by(ZuordnungWechsel.id))).scalars().all():
        la = await nachtrag.lage(db, a, row.id)
        out.append((la.gruende, la.stueck, la.korrektur_nicht))
    return out


async def test_h4_nur_am_rueckkehr_wechsel_ueber_die_zeit_davor(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    """Bauplan «Zu §14» Nr. 101 (F2): A → X → A → C — am ersten Wechsel (A → X) keine Korrektur über das Stück (der Grund-Text
    meinte dort das Gegenteil), am Rückkehr-Wechsel (X → A) das Stück **vor** ihm, ``[A → X, X → A)``, richtig A; «Falsch seit»
    zählt dort nicht."""
    from backend.api.routes import sensorwechsel as sw
    from backend.services.zuordnung_wechsel import korrektur_lauf, nachtrag

    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, spiegel=False)
    aid, wid = a.id, wb.id
    QX = {"art": "ha", "entity_id": "sensor.x"}
    await _wechsel(db, aid, key, SPRUNG, QA, QX)
    await _wechsel(db, aid, key, RUECK, QX, QA)
    await _wechsel(db, aid, key, datetime(2026, 6, 20, 10), QA, {"art": "ha", "entity_id": "sensor.c"})
    await db.commit()
    (g1, s1, n1), (g2, s2, n2), _r3 = await _lagen(db, aid)
    assert (g1, s1, n1) == (["fortsetzung"], None, nachtrag.SATZ_KORREKTUR_NUR_JUENGSTER)
    assert (g2, s2, n2) == (["fortsetzung", "korrektur"], (SPRUNG, RUECK, QA), None)
    r1, r2, _ = [r.id for r in (await db.execute(select(ZuordnungWechsel).order_by(ZuordnungWechsel.id))).scalars().all()]
    e = await _abgelehnt(sw.grund_nachtragen(aid, r1, sw.GrundNachtragRequest(grund="korrektur", falsch_seit=SPRUNG), db))
    assert (e.status_code, e.detail) == (422, nachtrag.SATZ_KORREKTUR_NUR_JUENGSTER)
    await sw.grund_nachtragen(aid, r2, sw.GrundNachtragRequest(grund="korrektur", falsch_seit=datetime(2026, 6, 1)), db)
    for t in list(korrektur_lauf._AUFGABEN.values()):
        await t
    korr = (await db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.grund == "korrektur"))).scalars().all()
    assert [(k.falsch_seit_ts, k.ab_ts, k.nachher) for k in korr] == [(SPRUNG, RUECK, QA)]
    assert await _tagesansicht(db, a, wid) == {d: 12.0 for d in TAGE}


async def test_h4_a_x_a_x_jede_zeile_die_zeit_vor_ihr(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    """Nachmessung 4b-1 F2 (``test_p9_h4_a_x_a_x``): A → X → A → X. Am HEAD der Runde bot der Wechsel X → A die Zeit **nach**
    ihm mit X an. Jetzt: A → X nichts; X → A das Stück davor mit A; A → X (zurück zu X) das Stück davor mit X."""
    from backend.services.zuordnung_wechsel import nachtrag

    v._kanal_tage(monkeypatch, {})
    a, _wb, key = await v._anlage(db, spiegel=False)
    aid = a.id
    QX = {"art": "ha", "entity_id": "sensor.x"}
    t3 = datetime(2026, 6, 20, 10)
    await _wechsel(db, aid, key, SPRUNG, QA, QX)
    await _wechsel(db, aid, key, RUECK, QX, QA)
    await _wechsel(db, aid, key, t3, QA, QX)
    await db.commit()
    assert await _lagen(db, aid) == [
        (["fortsetzung"], None, nachtrag.SATZ_KORREKTUR_NUR_JUENGSTER),
        (["fortsetzung", "korrektur"], (SPRUNG, RUECK, QA), None),
        (["fortsetzung", "korrektur"], (RUECK, t3, QX), None),
    ]


@pytest.mark.parametrize("spiegel", [False, True])
async def test_h4_a_x_a_mit_spaeterem_zaehlertausch_heilt(db, ha, eingerichtet, monkeypatch, spiegel):  # noqa: F811
    """Nr. 103 (F4): A → X → A, danach «Zähler getauscht» (A → A). Der Zählertausch zählt nicht als späterer Wechsel — der
    Rückkehr-Wechsel ist der jüngste, die gewöhnliche Korrektur mit «Falsch seit» ist frei (Vorgabe: der Wechsel davor). Sie
    heilt Reihe und Kanal: 12,0 an jedem Tag (Stellung Reihe ohne Spiegel, echt mit Spiegel), Bereich 84,0."""
    from backend.api.routes import sensorwechsel as sw
    from backend.services.zuordnung_wechsel import korrektur_lauf

    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, spiegel=spiegel)
    aid, wid = a.id, wb.id
    QX = {"art": "ha", "entity_id": "sensor.x"}
    await _wechsel(db, aid, key, SPRUNG, QA, QX)
    await _wechsel(db, aid, key, RUECK, QX, QA)
    db.add(ZuordnungWechsel(anlage_id=aid, sensor_key=key, erklaert_ts=datetime(2026, 6, 20, 10), ab_ts=datetime(2026, 6, 20, 10),
                            vorher=QA, nachher=QA, grund="fortsetzung", herkunft="wechsel"))
    await db.commit()
    (g1, _s1, _n1), (g2, s2, n2), (g3, _s3, _n3) = await _lagen(db, aid)
    assert (g2, s2, n2, g3) == (["fortsetzung", "korrektur"], None, None, [])
    r2 = (await db.execute(select(ZuordnungWechsel).order_by(ZuordnungWechsel.id))).scalars().all()[1]
    await sw.grund_nachtragen(aid, r2.id, sw.GrundNachtragRequest(grund="korrektur", falsch_seit=SPRUNG), db)
    for t in list(korrektur_lauf._AUFGABEN.values()):
        await t
    assert await _tagesansicht(db, a, wid) == {d: 12.0 for d in TAGE}
    assert (await _mengen(db, aid, key))[0] == pytest.approx(84.0)


async def test_nr103_spaetere_korrektur_und_luecke_zaehlen_nicht(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    """Nr. 103 (Nachmessung F4 b, ``test_p3``): ein älterer offener Wechsel, danach eine Korrektur über ein Stück am Befund —
    der Wechsel bleibt der jüngste Quellenwechsel, «Korrektur» bleibt angeboten."""
    v._kanal_tage(monkeypatch, {})
    a, _wb, key = await v._anlage(db, spiegel=False)
    aid = a.id
    await _wechsel(db, aid, key, datetime(2026, 6, 5, 10), {"art": "ha", "entity_id": "sensor.ganz_alt"}, QA)
    await db.commit()
    ((gruende, _s, nicht),) = await _lagen(db, aid)
    assert (gruende, nicht) == (["fortsetzung", "korrektur"], None)
    await _stueck(db, aid, key)
    (gruende, _s, nicht), _stueck_zeile = await _lagen(db, aid)
    assert (gruende, nicht) == (["fortsetzung", "korrektur"], None)


async def test_h4_verschiedene_quellen_bleibt_gesperrt(db, ha, monkeypatch):  # noqa: F811
    from backend.models.anlage import Anlage
    from backend.services.zuordnung_wechsel import nachtrag

    a, wb, key = await v._anlage(db, spiegel=False)
    aid = a.id
    QX, QC = {"art": "ha", "entity_id": "sensor.x"}, {"art": "ha", "entity_id": "sensor.c"}
    await _wechsel(db, aid, key, SPRUNG, QA, QX)
    await _wechsel(db, aid, key, RUECK, QX, QC)
    await _wechsel(db, aid, key, datetime(2026, 6, 20, 10), QC, {"art": "ha", "entity_id": "sensor.d"})
    await db.commit()
    a = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    r1, r2, _ = (await db.execute(select(ZuordnungWechsel).order_by(ZuordnungWechsel.id))).scalars().all()
    for row in (r1, r2):
        la = await nachtrag.lage(db, a, row.id)
        assert la.stueck is None and la.korrektur_nicht == nachtrag.SATZ_KORREKTUR_NUR_JUENGSTER


# ═══ Routen am Befund ═════════════════════════════════════════════════════════════════════════════════════════════════

async def test_route_kein_frei_waehlbares_stueck_und_nur_korrektur(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    from backend.api.routes import sensorwechsel as sw
    from backend.services.zuordnung_wechsel import stueck as st

    a, _wb, key = await v._anlage(db, spiegel=False)
    aid = a.id
    e = await _abgelehnt(sw.pruefe_stueck(aid, _body(key, rueck="2026-06-14T18:00"), db))
    assert (e.status_code, e.detail) == (404, st.SATZ_NICHT_GEMELDET)
    # ein Feld, das der Befund nicht prüft (Ladung gesamt der Wallbox), hat kein Stück
    e = await _abgelehnt(sw.pruefe_stueck(aid, _body(key.replace("ladung_pv_kwh", "ladung_kwh")), db))
    assert e.status_code == 404
    e = await _abgelehnt(sw.stueck_korrigieren(aid, _body(key, grund="fortsetzung"), db))
    assert (e.status_code, e.detail) == (422, "Für einen versetzten Abschnitt lässt sich nur «Bisherige Werte verwerfen» eintragen.")
    e = await _abgelehnt(sw.stueck_korrigieren(aid, _body(key, grund=None), db))
    assert (e.status_code, e.detail) == (422, "Wähle, ob die bisherigen Werte bleiben oder verworfen werden.")
    assert (await _abgelehnt(sw.pruefe_stueck(aid, _body(key, grund="weiss_nicht"), db))).status_code == 400
    assert await db.scalar(select(func.count()).select_from(ZuordnungWechsel)) == 0


async def test_route_verschiedene_quellen_an_den_raendern_gesperrt(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    """Der Kanal trägt nach dem Abschnitt eine andere Entität als davor (A → X → C ohne verzeichneten Wechsel): keine Korrektur,
    Lage ``verschiedene_quellen``."""
    from backend.api.routes import sensorwechsel as sw
    from backend.models.kanal import FAMILIE_SPIEGEL, Kanal, KanalQuelle
    from backend.services.zuordnung_wechsel import stueck as st

    v._kanal_tage(monkeypatch, {})
    a, _wb, key = await v._anlage(db)
    aid = a.id
    k = (await db.execute(select(Kanal).where(Kanal.key == key))).scalar_one()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int(datetime(2026, 6, 12).timestamp()), familie=FAMILIE_SPIEGEL,
                       statistic_id="sensor.anders", offset=0.0))
    await db.commit()
    (e,) = await v._pruefe(db, a)
    assert e.werte["lage"] == "verschiedene_quellen"
    p = await sw.pruefe_stueck(aid, _body(key), db)
    assert (p["gruende"], p["korrektur_nicht"]) == (
        [], st.SATZ_VERSCHIEDENE_QUELLEN.format(vorher=v.SENSOR, nachher="sensor.anders"))
    assert (await _abgelehnt(sw.stueck_korrigieren(aid, _body(key), db))).status_code == 422


async def test_route_ha_eingerichtet_nicht_erreichbar_startet_nicht(db, ohne_ha, eingerichtet, monkeypatch):  # noqa: F811
    from backend.api.routes import sensorwechsel as sw

    a, _wb, key = await v._anlage(db, spiegel=False)
    aid = a.id
    e = await _abgelehnt(sw.stueck_korrigieren(aid, _body(key), db))
    assert e.status_code == 422 and "nicht erreichbar" in e.detail
    p = await sw.pruefe_stueck(aid, _body(key), db)
    assert p["korrektur"]["startbar"] is False


async def test_route_offener_lauf_sperrt(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    from backend.api.routes import sensorwechsel as sw
    from backend.services.zuordnung_wechsel import korrektur_lauf, nachtrag

    a, _wb, key = await v._anlage(db, spiegel=False)

    async def offen(_db, _aid, _key):
        return "lauf1"
    monkeypatch.setattr(korrektur_lauf, "offener_lauf", offen)
    aid = a.id
    p = await sw.pruefe_stueck(aid, _body(key), db)
    assert (p["gruende"], p["korrektur_nicht"], p["korrektur"]) == ([], nachtrag.SATZ_LAUF_OFFEN, None)
    e = await _abgelehnt(sw.stueck_korrigieren(aid, _body(key), db))
    assert (e.status_code, e.detail) == (422, nachtrag.SATZ_LAUF_OFFEN)


# ═══ Nr. 91 e ════════════════════════════════════════════════════════════════════════════════════════════════════════

def test_nr91e_ab_ts_gleich_ab_zaehlt_nicht_zum_intervall():
    from backend.services.zuordnung_wechsel.korrektur import Auftrag, _im_intervall

    au = Auftrag(anlage_id=1, sensor_key="k", falsch_seit=SPRUNG, ab=RUECK, vorher=QA, nachher={"art": "ha", "entity_id": "b"})
    zeile = lambda ab: SimpleNamespace(ab_ts=ab, vorher=QA, nachher={"art": "ha", "entity_id": "x"})  # noqa: E731
    assert not _im_intervall(au, zeile(RUECK))
    assert _im_intervall(au, zeile(RUECK - timedelta(hours=1)))
    assert not _im_intervall(au, zeile(SPRUNG))                       # Rand mit anderem ``vorher`` bleibt


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


# ═══ Nr. 102 (F3): «—» statt 0,0, Rand nicht über die Lücke, Lücke auf den Rest gekürzt ═════════════════════════════

@pytest.mark.parametrize("sprung_h,rueck_h,soll,ohne,teil", [
    # Rückgang genau am Fensterende (14.06. 23:00): der 14.06. hat keinen Wert (am Arbeitsstand vorher 0,0)
    (v.SPRUNG_H, 13 * 24 + 23, {9: 12.0, 10: 0.5, 11: None, 12: None, 13: None, 14: None, 15: 12.0},
     ["2026-06-11", "2026-06-12", "2026-06-13", "2026-06-14"], ["2026-06-10"]),
    # Rückgang mit der Zeile 15.06. 00:00: der 15.06. trägt nur seinen Teil ab 00:00
    (v.SPRUNG_H, 14 * 24, {9: 12.0, 10: 0.5, 11: None, 12: None, 13: None, 14: None, 15: 11.5},
     ["2026-06-11", "2026-06-12", "2026-06-13", "2026-06-14"], ["2026-06-10", "2026-06-15"]),
    # Sprung mit der Zeile 10.06. 00:00 (letzter Stand davor 09.06. 23:00 = Fensterbeginn): der 10.06. hat keinen Wert
    (9 * 24, v.RUECK_H, {9: 12.0, 10: None, 11: None, 12: None, 13: None, 14: 2.0, 15: 12.0},
     ["2026-06-10", "2026-06-11", "2026-06-12", "2026-06-13"], ["2026-06-14"]),
    # ein Tag: 10.06. 00:00 … 23:00 — zwischen den beiden Ständen nur die Lücke (am Arbeitsstand vorher 0,0)
    (9 * 24, 9 * 24 + 23, {9: 12.0, 10: None, 11: 12.0, 12: 12.0, 13: 12.0, 14: 12.0, 15: 12.0}, ["2026-06-10"], []),
])
async def test_nr102_rand_am_tagesfenster_kein_wert_statt_null(db, ohne_ha, monkeypatch, sprung_h, rueck_h, soll, ohne, teil):  # noqa: F811
    """Nachmessung 4b-1 F3 a (``test_p15_rand_am_tagesfenster``): an einer Lücke **mit Höhenwechsel** zeigt die Tagesansicht
    «—», wenn im Fenster außerhalb der Lücke nichts messbar ist, sonst den Teilwert; die Vorschau nennt dieselben Tage (S7).
    Seit 4b-1-K2 auch der Bereichs-Leser (Nr. 112, ``_bereich``). Seit U1 entsteht die Lücke mit Nähten nur bei einem
    Höhenwechsel — hier eine andere Quelle vor dem Sprung (``_luecke_mit_hoehenwechsel``)."""
    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, staende=v._reihe(sprung=sprung_h, rueck=rueck_h), spiegel=False)
    aid, wid = a.id, wb.id
    la = await _luecke_mit_hoehenwechsel(db, aid, key, v.T0 + timedelta(hours=sprung_h), v.T0 + timedelta(hours=rueck_h))
    assert ([d.isoformat() for d in la.luecke_tage], [d.isoformat() for d in la.luecke_rand]) == (ohne, teil)
    assert await _tagesansicht(db, a, wid) == soll
    assert await _bereich(db, a, wid) == soll


async def _luecke_mit_hoehenwechsel(db, aid, key, sprung, rueck):
    """Eine Lücke mit Höhenwechsel: vor dem Sprung galt laut einem verzeichneten Wechsel ``sensor.c`` (eine andere Zählerhöhe),
    die Korrektur über ``[sprung, rueck)`` mit richtig A, ohne Home Assistant — Lücken-Zeile, Nähte an beiden Rändern."""
    from backend.services.zuordnung_wechsel import korrektur as kr

    await _wechsel(db, aid, key, sprung, {"art": "ha", "entity_id": "sensor.c"}, QA)
    await db.commit()
    au = kr.Auftrag(anlage_id=aid, sensor_key=key, falsch_seit=sprung, ab=rueck, vorher=QA, nachher=QA, stueck=True)
    la = await kr.lage(db, au, ha_svc=None)
    assert la.luecke == (sprung, rueck) and not la.zaehlerluecke
    await kr.fuehre_aus(db, au, ha_svc=None, jetzt=datetime(2026, 7, 1, 12))
    await db.commit()
    zw.vergiss(db)
    assert await zw.fortsetzungs_naehte(db, aid, key) == [sprung, rueck]
    return la


async def _bereich(db, a, wid) -> dict[int, float | None]:
    """«Ladung PV» über den Bereichs-Leser (``lade_tageswerte_je_feld``, Tagesfenster rückwärts) je Tag 9.–15.06."""
    from backend.models.anlage import Anlage
    from backend.services.snapshot.aggregator import TAGESDETAIL_AUSGABE
    from backend.services.snapshot.bereichs_leser import lade_tageswerte_je_feld

    zw.vergiss(db)
    a_ = (await db.execute(select(Anlage).where(Anlage.id == a.id))).scalar_one()
    tage = [date(2026, 6, d) for d in TAGE]
    je = await lade_tageswerte_je_feld(db, a_, {str(wid): await db.get(Investition, wid)}, tage[0], tage[-1],
                                       {("wallbox", "ladung_pv_kwh"): TAGESDETAIL_AUSGABE[("wallbox", "ladung_pv_kwh")]},
                                       rueckwaerts_tage=frozenset(tage), kanal_zuerst=True)
    return {d.day: (round(je[d]["emob_ladung_pv_kwh"], 2) if d in je and "emob_ladung_pv_kwh" in je[d] else None) for d in tage}


@pytest.mark.parametrize("sprengsatz", [False, True])
async def test_nr102_rand_hinter_der_luecke_setzt_keine_marke_ab(db, ohne_ha, monkeypatch, sprengsatz):  # noqa: F811
    """Der Tag, an dem die Lücke endet (14.06., 2,0 = 19:00 … 23:00): der linke Rand rückt nicht über die Lücke auf den
    letzten Stand davor (10.06. 00:00), sondern beginnt an ihrem Ende. **U1 Punkt 5 (F5, Bauplan Nr. 136 (3)):** die Marke
    «ab 19:00» entfällt (wie vor Nr. 102 (i)) — sie stand an der Wärmepumpen-Kachel auch für die Lücke eines anderen Geräts;
    der Wert bleibt 2,0. Der Tag, an dem sie beginnt, behält «bis 00:00» (wie am HEAD). Sprengsatz: die Marke aus dem Rand."""
    import backend.services.snapshot.aggregator as agg
    from backend.services.snapshot.aggregator import get_tagesdetail_kwh

    if sprengsatz:
        echt = agg.TagesRandMenge

        def mit_marke(**kw):
            return echt(**{**kw, "ab_tagesbeginn": kw["seit"] <= kw["bis"] - timedelta(hours=24)})
        monkeypatch.setattr(agg, "TagesRandMenge", mit_marke)
    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, spiegel=False)
    aid, wid = a.id, wb.id
    await _luecke_mit_hoehenwechsel(db, aid, key, SPRUNG, RUECK)
    invs = {str(wid): await db.get(Investition, wid)}
    t14 = await get_tagesdetail_kwh(db, a, invs, date(2026, 6, 14), tageszeile_rueckwaerts=True)
    t10 = await get_tagesdetail_kwh(db, a, invs, date(2026, 6, 10), tageszeile_rueckwaerts=True)
    assert round(t14.werte["emob_ladung_pv_kwh"], 2) == 2.0
    assert (t14.abdeckung_von is None) is (not sprengsatz)
    assert (round(t10.werte["emob_ladung_pv_kwh"], 2), t10.abdeckung_bis) == (0.5, datetime(2026, 6, 10))


async def test_nr102_korrektur_kuerzt_eine_aeltere_luecke_auf_den_rest(db, monkeypatch, request):
    """Nachmessung 4b-1 F3 b (``test_p10_luecke_teilweise_ueberdeckt``): erst ein Stück ohne Home Assistant (Lücke 10.06. 01:00
    … 14.06. 19:00), später mit Home Assistant eine füllbare Korrektur ab 12.06. 00:00 — die alte Lücke wird auf den Rest
    10.06. 01:00 … 12.06. 00:00 gekürzt; die gefüllten Tage zeigen 12,0 (am Arbeitsstand vorher 0,0), der Rest bleibt Lücke."""
    import backend.services.ha_statistics_service as hss
    from backend.services.zuordnung_wechsel import korrektur as kr

    request.getfixturevalue("verschoben")
    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db, spiegel=False)
    aid, wid = a.id, wb.id
    await _stueck(db, aid, key)
    request.getfixturevalue("ha")
    au = kr.Auftrag(anlage_id=aid, sensor_key=key, falsch_seit=datetime(2026, 6, 12), ab=datetime(2026, 6, 20), vorher=QA,
                    nachher=QA)
    erg = await kr.fuehre_aus(db, au, ha_svc=hss._ha_statistics_service, jetzt=datetime(2026, 7, 1, 12))
    await db.commit()
    s = await kr.nach_dem_commit(erg, ha_svc=hss._ha_statistics_service, starten=False)
    from backend.core.database import get_session
    from backend.services.zuordnung_wechsel import korrektur_lauf
    monkeypatch.setattr(kr, "ha_eingerichtet", lambda: True)
    await korrektur_lauf.tage_neu_bilden(kr.sitzungen_wie(db, get_session), s["lauf"])   # 4b-1-K2 Nr. 111: Stände speichern
    zw.vergiss(db)
    luecken = [(w.falsch_seit_ts, w.ab_ts) for w in (await db.execute(select(ZuordnungWechsel).where(
        ZuordnungWechsel.aufgehoben_durch.is_(None)))).scalars().all() if zw.ist_luecken_zeile(w)]
    assert luecken == [(SPRUNG, datetime(2026, 6, 12))]
    # U1: der Rest ist eine Lücke ohne Höhenwechsel (davor A, danach die neu gelesenen Stände von A auf derselben Höhe) —
    # keine Nähte; die Menge des Rests steht am 12.06. (vom letzten Stand davor, 10.06. 00:00, bis 12.06. 23:00: 71 h × 0,5).
    assert await zw.fortsetzungs_naehte(db, aid, key) == []
    assert await _tagesansicht(db, a, wid) == {9: 12.0, 10: 0.5, 11: None, 12: 35.5, 13: 12.0, 14: 12.0, 15: 12.0}


def test_nr102_rest_der_luecke():
    from backend.services.zuordnung_wechsel.korrektur import _rest_der_luecke

    t = lambda d: datetime(2026, 6, d)  # noqa: E731
    assert _rest_der_luecke(t(10), t(15), t(12), t(20)) == [(t(10), t(12))]
    assert _rest_der_luecke(t(10), t(15), t(8), t(12)) == [(t(12), t(15))]
    assert _rest_der_luecke(t(10), t(15), t(11), t(12)) == [(t(10), t(11)), (t(12), t(15))]
    assert _rest_der_luecke(t(10), t(15), t(9), t(16)) == []


# ═══ Nr. 104 (F5/F6): Warnung nur, wo der Handgriff wirkt ═════════════════════════════════════════════════════════════

async def test_nr104_ha_eingerichtet_nicht_erreichbar_ist_eine_auskunft(db, ohne_ha, eingerichtet, monkeypatch):  # noqa: F811
    """Home Assistant eingerichtet, gerade nicht erreichbar: die Korrektur startet nicht (422) — der Befund ist eine Auskunft
    ohne Knopf mit wahrem Satz (Nachmessung F5, S4), nicht «Grund nachtragen … bleibt ohne Wert»."""
    from backend.services.daten_checker.datenquelle.versatz import GRUND_HA_NICHT_ERREICHBAR

    v._kanal_tage(monkeypatch, {})
    a, _wb, _key = await v._anlage(db, spiegel=False)
    (e,) = await v._pruefe(db, a)
    assert (e.schwere, e.klasse, e.knopf, e.ziel, e.werte["lage"]) == ("info", "auskunft", "Was gilt", None, GRUND_HA_NICHT_ERREICHBAR)
    assert e.details.endswith("Home Assistant ist gerade nicht erreichbar — ob eedc die Zählerstände dieses Abschnitts neu "
                              "holen kann, lässt sich jetzt nicht prüfen, und eine Korrektur startet erst, wenn eedc die "
                              "Langzeitstatistik wieder lesen kann. Dann steht hier der Knopf „Grund nachtragen“.")


async def test_nr104_abruf_wirft_der_daten_checker_antwortet(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    """Nachmessung «Bestand» (``test_nm4b1_proben4``): wirft der Abruf aus Home Assistant, warf die Prüfung — jetzt Lage
    «nicht erreichbar»; liefert er ``None``, passen die Stände zu keiner Summe (wie vorher)."""
    v._kanal_tage(monkeypatch, {})
    a, _wb, _key = await v._anlage(db, spiegel=False)

    def wirft(*_a, **_k):
        raise RuntimeError("Recorder antwortet nicht")
    monkeypatch.setattr(ha, "get_value_at", wirft)
    assert [(e.schwere, e.werte["lage"]) for e in await v._pruefe(db, a)] == [("info", "ha_nicht_erreichbar")]
    monkeypatch.setattr(ha, "get_value_at", lambda *_a, **_k: None)
    assert [(e.schwere, e.werte["lage"]) for e in await v._pruefe(db, a)] == [("warning", "staende_passen_nicht")]


async def test_nr104_ohne_fund_kein_abruf(db, ha, monkeypatch):  # noqa: F811
    """Home Assistant wird nur für einen gefundenen Abschnitt gefragt — für die OK-Zeile kein Abruf."""
    v._kanal_tage(monkeypatch, {})
    a, *_ = await v._anlage(db, staende=v._reihe(sprung=None), spiegel=False)
    abrufe = []
    echt = ha.get_value_at
    monkeypatch.setattr(ha, "get_value_at", lambda *x, **k: abrufe.append(x) or echt(*x, **k))
    (ok,) = await v._P(db)._check_zaehler_versatz(a, jetzt=v.JETZT)
    assert (ok.schwere, abrufe) == ("ok", [])
    b, *_ = await v._anlage(db, spiegel=False)
    await v._pruefe(db, b)
    assert len(abrufe) >= 2


async def test_nr104_verschiedene_quellen_auskunft_und_kopfsatz_mit_beiden(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    """Nachmessung F6/S5: bei verschiedenen Quellen ist der Befund eine Auskunft ohne Knopf (der Dialog könnte nur sperren),
    und der Kopfsatz der Prüf-Route nennt beide Quellen statt «davor und danach gilt sensor.pv_ladung»."""
    from backend.api.routes import sensorwechsel as sw
    from backend.models.kanal import FAMILIE_SPIEGEL, Kanal, KanalQuelle

    v._kanal_tage(monkeypatch, {})
    a, _wb, key = await v._anlage(db)
    k = (await db.execute(select(Kanal).where(Kanal.key == key))).scalar_one()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=int(datetime(2026, 6, 12).timestamp()), familie=FAMILIE_SPIEGEL,
                       statistic_id="sensor.anders", offset=0.0))
    await db.commit()
    (e,) = await v._pruefe(db, a)
    assert (e.schwere, e.klasse, e.ziel, e.werte["lage"]) == ("info", "auskunft", None, "verschiedene_quellen")
    p = await sw.pruefe_stueck(a.id, _body(key), db)
    assert p["wechsel_satz"] == ("Vom 10.06.2026 01:00 bis 14.06.2026 19:00 Uhr liegen die gespeicherten Zählerstände dieses "
                                 "Felds um 80,5 kWh neben denen davor und danach; davor gilt sensor.pv_ladung, danach "
                                 "sensor.anders.")


# ═══ Nr. 105 (F7): Lücken-Zeilen sind keine Quellenwechsel ════════════════════════════════════════════════════════════

async def test_nr105_luecken_zeile_ist_kein_wechsel(db, ohne_ha, monkeypatch):  # noqa: F811
    """Nachmessung F7 a/c (``test_p2``): nach einer Korrektur ohne Füllen am Wechsel X → A liefert ``letzte_quelle_mit_werten``
    die richtige Quelle A (vorher die verworfene X aus der Lücken-Zeile); die Routen kennen die Nummer der Lücken-Zeile nicht
    (404); ``quelle_am`` vor dem Intervall bleibt X (die Lücken-Zeile zählt nicht als Wechsel)."""
    from backend.api.routes import sensorwechsel as sw
    from backend.services.zuordnung_wechsel import abfrage

    v._kanal_tage(monkeypatch, {})
    reihe = [(v.T0 + timedelta(hours=h), (7000.0 if h >= v.RUECK_H else 1000.0) + 0.5 * h) for h in range(29 * 24)]
    a, _wb, key = await v._anlage(db, staende=reihe, spiegel=False)
    aid = a.id
    QX = {"art": "ha", "entity_id": "sensor.x"}
    await _wechsel(db, aid, key, RUECK, QX, QA)
    await db.commit()
    w_id = (await db.execute(select(ZuordnungWechsel.id))).scalar_one()
    await sw.grund_nachtragen(aid, w_id, sw.GrundNachtragRequest(grund="korrektur", falsch_seit=SPRUNG), db)
    zeilen = (await db.execute(select(ZuordnungWechsel).order_by(ZuordnungWechsel.id))).scalars().all()
    luecke = [w for w in zeilen if zw.ist_luecken_zeile(w)]
    assert len(luecke) == 1 and luecke[0].vorher == QX
    luecke_id = luecke[0].id
    zw.vergiss(db)
    assert await abfrage.letzte_quelle_mit_werten(db, aid, key, {"art": "keine"}) == QA
    assert zw.quelle_am((await zw.lade_wechsel(db, aid)).get(key), datetime(2026, 6, 5)) == QX
    for route in (sw.pruefe_grund_nachtragen, sw.grund_nachtragen):
        e = await _abgelehnt(route(aid, luecke_id, sw.GrundNachtragRequest(grund="korrektur", falsch_seit=SPRUNG), db))
        assert e.status_code == 404


# ═══ Nr. 106: solange das Füllen aussteht, gilt das Stück als Lücke ═══════════════════════════════════════════════════

async def test_nr106_fuellen_offen_luecke_danach_zwoelf(db, ha, eingerichtet, monkeypatch):  # noqa: F811
    """Füllbares Stück; Home Assistant ist nach dem Eintragen nicht erreichbar, das Füllen scheitert und bleibt offen — die
    Tagesansicht zeigt die Lücke (nicht 59,5 am 14.06.); nach dem Nachholen mit Home Assistant 12,0 an jedem Tag."""
    import backend.services.ha_statistics_service as hss
    import backend.services.kanal.korrektur as kk
    from backend.services.zuordnung_wechsel import korrektur_lauf
    from backend.tests.pv_achse_matrix import _ha_aus

    from backend.models.kanal import FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik

    v._kanal_tage(monkeypatch, {})
    a, wb, key = await v._anlage(db)
    aid, wid = a.id, wb.id
    # Im Stück führte auch der Kanal den fremden Sensor (wie die Reihe): die Korrektur verwirft ihn dort und füllt aus HA.
    k = (await db.execute(select(Kanal).where(Kanal.key == key))).scalar_one()
    s_ts, r_ts = int(SPRUNG.timestamp()) - 3600, int(RUECK.timestamp()) - 3600
    db.add_all([KanalQuelle(kanal_id=k.id, gueltig_ab=s_ts, familie=FAMILIE_SPIEGEL, statistic_id="sensor.x", offset=0.0),
                KanalQuelle(kanal_id=k.id, gueltig_ab=r_ts, familie=FAMILIE_SPIEGEL, statistic_id=v.SENSOR, offset=0.0)])
    for z in (await db.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id, KanalStatistik.start_ts >= s_ts,
                                                             KanalStatistik.start_ts < r_ts))).scalars().all():
        z.sum += v.VERSATZ
    await db.commit()
    echt_fuellen, svc = kk.fuelle_kanal, hss._ha_statistics_service

    async def scheitert(*_a, **_k):
        raise ConnectionError("Home Assistant nicht erreichbar")
    monkeypatch.setattr(kk, "fuelle_kanal", scheitert)
    r = await _stueck(db, aid, key)
    lauf = r["korrektur"][0]["lauf"]
    assert await korrektur_lauf.offener_lauf(db, aid, key) == lauf
    monkeypatch.setattr(hss, "_ha_statistics_service", _ha_aus())
    sicht = await _tagesansicht_reihe(db, a, wid, monkeypatch)
    assert sicht == LUECKE
    monkeypatch.setattr(hss, "_ha_statistics_service", svc)
    monkeypatch.setattr(kk, "fuelle_kanal", echt_fuellen)
    from backend.services.zuordnung_wechsel.korrektur import sitzungen_wie
    from backend.core.database import get_session

    await korrektur_lauf.tage_neu_bilden(sitzungen_wie(db, get_session), lauf)
    assert await korrektur_lauf.offener_lauf(db, aid, key) is None
    assert await _tagesansicht_reihe(db, a, wid, monkeypatch) == {d: 12.0 for d in TAGE}


async def _tagesansicht_reihe(db, a, wid, monkeypatch) -> dict[int, float | None]:
    """Die Tagesansicht in Stellung Reihe, auch wenn das Feld einen Kanal hat (der Kanal gestellt leer)."""
    import backend.services.kanal.feld_leser as fl

    async def kein_kanal(*_a, **_k):
        return {}
    monkeypatch.setattr(fl, "kanal_feldzeitraeume", kein_kanal)
    return await _tagesansicht(db, a, wid)
