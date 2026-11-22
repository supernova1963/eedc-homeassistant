"""Sensorwechsel Weg B, Korrekturrunde WEGB-K (Bauplan Nr. 186; Nachmessung A1/A2) — die Lese-Regel «Anfangsstand 0 am Beginn
einer HA-Statistik» richtig abgegrenzt (``kanal/lesen._ha_beginn_sql``, Marke ``kanal_nachfuellung`` mit ``ergebnis.beginn``).

**Teil 1 — Lagen-Tabelle an der Lese-Schicht** (Kunst-Kanäle, die erste Zeile trägt einen laufenden ``sum`` von 1 000 wie ein
echter Zähler): gilt die Regel an der ersten Zeile des Kanals, zählt die erste Stunde ab 0 (wie Home Assistant); gilt sie nicht,
fehlt die erste Stunde (wie v4.3.1). Grundsatz: im Zweifel gilt sie nicht — nie ein Zählerstand als Menge. Drei Leser
(``zeitraum``, ``stunden``, ``deltas_stapel``) sehen dieselbe Bedingung. Die Lage «keine Marke» hält zugleich den Sprengsatz
der Nachmessung fest («erste Zeile immer ab 0, auch ohne Marke» — die Abnahme-Matrix sieht ihn seit der Saat ab ``sum`` 0
nicht mehr).

**Teil 2 — Proben über die Sichten** (Welt von ``test_sensorwechsel_wegb_loeschen_proben.py``: HA-Attrappe, stehende Uhr, echter
Stundenlauf mit Nachfüllen; alle HA-Statistiken beginnen am 26.10. um 19:00): R1 A → B → A («bleiben») und danach die Werkbank —
die erste Zeile der jüngsten A-Quelle ist kein Beginn; R2 «bleiben» — der Tag des Statistikbeginns der bisherigen Quelle zeigt
vor und nach dem Wechsel dasselbe wie Home Assistant; dazu «löschen» → «bleiben», «bleiben» HA → MQTT, Quelle «Keine» und zurück
und eine in Home Assistant umbenannte Entity.

Schwesterdateien: test_sensorwechsel_wegb_loeschen_proben.py (Welt, Sichten), test_kanal_lesen.py (Regel an der Lese-Schicht),
test_sensorwechsel_wegb_werkbank_nach_bleiben.py (Werkbank).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import insert, select, text

from backend.models.anlage import Anlage
from backend.models.kanal import (
    ART_SUM,
    FAMILIE_MITSCHRIFT,
    FAMILIE_SPIEGEL,
    Kanal,
    KanalNachfuellung,
    KanalQuelle,
    KanalStatistik,
)
from backend.services.kanal.lesen import GRUND_BEGINNT_NACH_VON, deltas_stapel, stunden, zeitraum
from backend.tests import test_sensorwechsel_wegb_loeschen_proben as P
from backend.tests.test_sensorwechsel_wegb_loeschen_proben import stehende_uhr  # noqa: F401 — Fixture

H = 3600
T0 = 1_767_571_200            # 2026-01-05 00:00 UTC
JETZT = 4_102_444_800         # alle Zeiträume abgeschlossen
S0 = 1000.0                   # laufender ``sum`` der ersten Zeile (ein Zählerstand, keine Menge)


def h(n: int) -> int:
    return T0 + n * H


# ── Teil 1: Lagen-Tabelle ─────────────────────────────────────────────────────────────────────────────────────────────

#: Lage → (Quellen ``[(Stunde, statistic_id, verworfen, familie)]``, erste Zeile (Stunde), Marke ``(statistic_id, ergebnis)``
#: oder ``None``, gilt die Regel an der ersten Zeile?)
_V = 1                        # «verworfen am» (Werkbank bzw. Platzhalter von «löschen»)
LAGEN = {
    #: eine Quelle, das Nachfüllen fand vor ihr nichts (Marke ohne Grund) — der Beginn der Statistik
    "eine_quelle_marke_ohne_grund": ([(0, "sensor.a", None, FAMILIE_SPIEGEL)], 0, ("sensor.a", {"zeilen": 3}), True),
    #: keine Marke (HA nicht gefragt) — der Sprengsatz «erste Zeile immer ab 0» der Nachmessung
    "keine_marke": ([(0, "sensor.a", None, FAMILIE_SPIEGEL)], 0, None, False),
    #: das Nachfüllen nennt einen Grund für die Entity selbst
    "marke_mit_grund": ([(0, "sensor.a", None, FAMILIE_SPIEGEL)], 0,
                        ("sensor.a", {"zeilen": 0, "grund": "ha_kennt_sensor_nicht"}), False),
    #: A1 — A → B → A («bleiben»), danach Werkbank vor der jüngsten A-Quelle: die Marke zeigt wieder auf A ohne Grund, aber
    #: die erste Zeile gehört zu einer späteren Quelle derselben Entity
    "aba_werkbank": ([(-40, "sensor.a", _V, FAMILIE_SPIEGEL), (-20, "sensor.b", _V, FAMILIE_SPIEGEL),
                      (0, "sensor.a", None, FAMILIE_SPIEGEL)], 0, ("sensor.a", {"zeilen": 0}), False),
    #: Werkbank an der ersten Quelle (A → B «bleiben», verworfen ab einer Stunde mitten in A): die erste Zeile gehört zu A
    "werkbank_erste_quelle": ([(-10, "sensor.a", _V, FAMILIE_SPIEGEL), (20, "sensor.b", None, FAMILIE_SPIEGEL)], 0,
                              ("sensor.b", {"zeilen": 0, "grund": "vorgeschichte_andere_quelle", "beginn": "sensor.a"}),
                              False),
    #: A2 — A → B «bleiben»: die Marke zeigt auf B mit Grund und trägt den Beginn von A weiter
    "bleiben_beginn_weiter": ([(0, "sensor.a", None, FAMILIE_SPIEGEL), (20, "sensor.b", None, FAMILIE_SPIEGEL)], 0,
                              ("sensor.b", {"zeilen": 0, "grund": "vorgeschichte_andere_quelle", "beginn": "sensor.a"}),
                              True),
    #: Bestand: dieselbe Lage mit einer Marke, die ein früherer Stand schon überschrieben hat (ohne ``beginn``) — wie v4.3.1
    "bleiben_bestand_ohne_beginn": ([(0, "sensor.a", None, FAMILIE_SPIEGEL), (20, "sensor.b", None, FAMILIE_SPIEGEL)], 0,
                                    ("sensor.b", {"zeilen": 0, "grund": "vorgeschichte_andere_quelle"}), False),
    #: «löschen»: ein Platzhalter ohne Entity vor der Quelle des neuen Sensors, dessen Geschichte nachgefüllt ist
    "loeschen": ([(-1, None, _V, FAMILIE_SPIEGEL), (0, "sensor.b", None, FAMILIE_SPIEGEL)], 0, ("sensor.b", {"zeilen": 5}), True),
    #: «löschen» → «bleiben»: der Beginn von B überlebt den Wechsel auf C
    "loeschen_dann_bleiben": ([(-1, None, _V, FAMILIE_SPIEGEL), (0, "sensor.b", None, FAMILIE_SPIEGEL),
                               (20, "sensor.c", None, FAMILIE_SPIEGEL)], 0,
                              ("sensor.c", {"zeilen": 0, "grund": "vorgeschichte_andere_quelle", "beginn": "sensor.b"}), True),
    #: weitergetragener Beginn einer Quelle, die die Werkbank inzwischen verworfen hat
    "beginn_verworfen": ([(0, "sensor.a", _V, FAMILIE_SPIEGEL), (20, "sensor.b", None, FAMILIE_SPIEGEL)], 0,
                         ("sensor.b", {"zeilen": 0, "grund": "vorgeschichte_andere_quelle", "beginn": "sensor.a"}), False),
    #: MQTT → HA «bleiben»: die erste Zeile ist eine eigene Summe (Mitschrift), kein Beginn einer HA-Statistik — seit Fund-
    #: Päckchen D (R-D1) der erste MQTT-Stand: er ist der Anfangsstand (``MQTT``, kein Anfangsstand 0)
    "mqtt_dann_ha": ([(0, "netzbezug_kwh", None, FAMILIE_MITSCHRIFT), (20, "sensor.a", None, FAMILIE_SPIEGEL)], 0,
                     ("sensor.a", {"zeilen": 0, "grund": "vorgeschichte_andere_quelle"}), "MQTT"),
    #: HA → MQTT «bleiben»: die Marke der eigenen Summe trägt den Beginn der HA-Statistik weiter
    "ha_dann_mqtt": ([(0, "sensor.a", None, FAMILIE_SPIEGEL), (20, "netzbezug_kwh", None, FAMILIE_MITSCHRIFT)], 0,
                     ("netzbezug_kwh", {"zeilen": 0, "grund": "vorgeschichte_andere_quelle", "beginn": "sensor.a"}), True),
}


async def _lage_kanal(db, lage: str) -> Kanal:
    quellen, erste, marke, _gilt = LAGEN[lage]
    a = Anlage(anlagenname="WEGB-K", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    k = Kanal(anlage_id=a.id, key="basis:einspeisung", art=ART_SUM, einheit="kWh")
    db.add(k)
    await db.flush()
    for ab, sid, verworfen, familie in quellen:
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=h(ab), familie=familie, statistic_id=sid, offset=0.0,
                           verworfen_ts=JETZT if verworfen else None))
    await db.execute(insert(KanalStatistik), [
        {"kanal_id": k.id, "start_ts": h(erste + i), "sum": S0 + 0.5 * i, "state": S0 + 0.5 * i, "mean": None, "min": None,
         "max": None, "familie": FAMILIE_SPIEGEL} for i in range(40)])
    if marke is not None:
        db.add(KanalNachfuellung(kanal_id=k.id, statistic_id=marke[0], abgeschlossen_ts=JETZT, ergebnis=marke[1]))
    await db.flush()
    return k


@pytest.mark.parametrize("lage", sorted(LAGEN))
async def test_lagen_der_regel_an_der_ersten_zeile(db, lage):
    """Gilt die Regel: die erste Stunde zählt ab 0 (``sum`` der ersten Zeile = 1 000), der Tag ist gedeckt. Gilt sie nicht: die
    erste Stunde hat keinen Zuwachs, der Zeitraum beginnt nach ``von`` (wie v4.3.1). Drei Leser, eine Bedingung."""
    gilt = LAGEN[lage][3]
    k = await _lage_kanal(db, lage)
    z = await zeitraum(db, k, h(0), h(3), jetzt=JETZT)
    st = await stunden(db, k, h(0), h(3), jetzt=JETZT)
    de = (await deltas_stapel(db, [k], h(0), h(3)))[k.key]
    if gilt == "MQTT":
        # Fund-Päckchen D (R-D1): bis dahin wie «gilt nicht» (beginnt nach von); jetzt ist der Zeitraum gedeckt, gezählt ab dem
        # ersten Stand — die erste Stunde trägt keinen Zuwachs (kein Stand davor, kein Anfangsstand 0)
        assert (z.voll, z.grund, z.delta, z.teil_delta) == (True, None, pytest.approx(1.0), None), lage
        assert st.voll and st.werte[0].change is None and de[0][1] is None, lage
    elif gilt:
        assert (z.voll, z.delta) == (True, pytest.approx(S0 + 1.0)), lage
        assert st.werte[0].change == pytest.approx(S0) and de[0][1] == pytest.approx(S0), lage
    else:
        assert (z.voll, z.grund, z.delta, z.teil_delta) == (False, GRUND_BEGINNT_NACH_VON, None, pytest.approx(1.0)), lage
        assert st.werte[0].change is None and de[0][1] is None, lage
    # die Stunden danach zählen in jeder Lage gleich (Zuwachs 0,5)
    assert [w.change for w in st.werte[1:]] == pytest.approx([0.5, 0.5])


# ── Teil 2: Proben über die Sichten ───────────────────────────────────────────────────────────────────────────────────

FID = "inv_energy_1_pv_erzeugung_kwh"
KEY = P.FELDER["pv"][2]
#: Die HA-Statistiken der Welt beginnen am 26.10. um 19:00 (fünf Stunden vor ``P.START``).
BEGINN = P.WELTBEGINN
OKT = (2026, 10)


async def _welt(db, monkeypatch, *, neu_ab: datetime | None = None, c_ab: datetime | None = None):
    v = P.ep(P.START) - 5 * P.STUNDE
    serien = {P.ALT: (v, lambda _e: 0.6), P.NEU: (v if neu_ab is None else P.ep(neu_ab), lambda _e: 0.4),
              P.PVC: (v, lambda _e: 2.0), P.WB: (v, lambda _e: 1.32)}
    if c_ab is not None:
        serien[P.C] = (P.ep(c_ab), lambda _e: 0.3)
    return await P.mach_welt(db, monkeypatch, serien, {"pv": P.ALT, "pvk": P.PVC, "wb": P.WB}, mqtt=True)


async def _wechsel(w, t: datetime, grund: str, *, fid: str = FID, **ziel):
    from backend.api.routes.datenquellen import QuelleSetRequest, set_feld_quelle

    P.UHR.stelle(t)
    w.ha_bis(P.ep(t.replace(minute=0)) - P.STUNDE)
    r = await set_feld_quelle(w.a.id, fid, QuelleSetRequest(**ziel, grund=grund), w.db)
    await P.laeufe()
    P.frisch(w)
    return r


async def _erster_tag(w, feld: str = "pv") -> dict:
    """Der Tag des Statistikbeginns (26.10.) und der Oktober eines Felds über die Sichten, dazu die Kanal-Deckung."""
    s = await P.sichten(w, feld, [BEGINN], OKT)
    return {"tag": s["tage"][BEGINN], "monat": (s["monatssicht"], s["aus_ha_laden"], s["vorschlag"])}


def _ha(w, eid: str, von: datetime, bis: datetime):
    return w.ha_summe(eid, von, bis)


def _tag(d: date) -> tuple[datetime, datetime]:
    return datetime.combine(d, datetime.min.time()), datetime.combine(d + timedelta(days=1), datetime.min.time())


async def _drift_und_deckung(w, von: date, bis: date) -> tuple[list[str], list[date]]:
    b = await P.befunde(w)
    return sorted(x[:10] for x in b.get("drift_tag", [])), await P.kanal_deckung(w, von, bis)


async def test_r2_bleiben_der_erste_tag_der_bisherigen_statistik_bleibt_wie_ha(db, monkeypatch, stehende_uhr):
    """R2 (Nachmessung A2): «Bisherige Werte bleiben» an einem HA-Feld überschreibt die Nachfüll-Marke des Kanals — der Beginn
    der Statistik des bisherigen Sensors gilt weiter (``ergebnis.beginn``). Der 26.10. (Statistikbeginn 19:00) zeigt vor und
    nach dem Wechsel dasselbe wie Home Assistant: PV Feld 3,0 (5 × 0,6), Kontroll-PV 10,0; der Oktober in drei Sichten gleich;
    kein Tag ohne Kanal-Deckung; der Daten-Checker nennt vorher und nachher dieselben Tage (der 26.10. selbst ist die benannte
    Grenze der Drift-Prüfung am ersten Tag einer Statistik, Lösungsweg ``drift_tag``)."""
    w = await _welt(db, monkeypatch, neu_ab=datetime(2026, 10, 28, 8))
    t = datetime(2026, 10, 28, 12, 20)
    await P.betrieb_bis(w, P.START, t.replace(minute=0))
    P.UHR.stelle(t - timedelta(minutes=2))
    vor = {f: await _erster_tag(w, f) for f in ("pv", "pvk")}
    vor_befunde = await _drift_und_deckung(w, P.START.date(), date(2026, 10, 27))
    await _wechsel(w, t, "fortsetzung", quelle="ha_app", entity_id=P.NEU)
    ende = datetime(2026, 10, 30, 3)
    await P.betrieb_bis(w, t.replace(minute=0) + timedelta(hours=1), ende)
    P.UHR.stelle(ende + timedelta(minutes=20))
    nach = {f: await _erster_tag(w, f) for f in ("pv", "pvk")}
    assert {f: x["tag"] for f, x in nach.items()} == {f: x["tag"] for f, x in vor.items()}
    assert (nach["pv"]["tag"], nach["pvk"]["tag"]) == (_ha(w, P.ALT, *_tag(BEGINN)), _ha(w, P.PVC, *_tag(BEGINN))) == (3.0, 10.0)
    # der laufende Oktober in drei Sichten gleich (Monatssicht, «Aus HA laden», Vorschlag), vor wie nach dem Wechsel
    assert all(len(set(x["monat"])) == 1 for z in (vor, nach) for x in z.values()), (vor, nach)
    marke = (await w.db.execute(text("select m.ergebnis from kanal_nachfuellung m join kanal k on k.id = m.kanal_id "
                                     "where k.key = :k"), {"k": KEY})).scalar_one()
    assert '"beginn": "sensor.alt"' in marke
    drift, ohne = await _drift_und_deckung(w, BEGINN, date(2026, 10, 29))
    assert ohne == [] and drift == vor_befunde[0]


async def test_r2_loeschen_dann_bleiben_der_beginn_des_geloeschten_feldes_bleibt(db, monkeypatch, stehende_uhr):
    """«löschen» auf B (HA führt B seit dem 27.10. 08:00), danach «bleiben» auf C: der 27.10. bleibt Kanal-Tag der Anlage, das
    Feld zeigt dort Home Assistant für B ab 08:00 (16 × 0,4 = 6,4), die Kontroll-PV ihren ganzen Tag; der Oktober aller
    Felder bleibt; die Auskunft nach «löschen» behält ihren Satz (Home Assistant führt den neuen Sensor seit …)."""
    w = await _welt(db, monkeypatch, neu_ab=datetime(2026, 10, 27, 8), c_ab=datetime(2026, 10, 29, 9))
    t1, t2 = datetime(2026, 10, 28, 10, 20), datetime(2026, 10, 29, 14, 20)
    await P.betrieb_bis(w, P.START, t1.replace(minute=0))
    await _wechsel(w, t1, "loeschen", quelle="ha_app", entity_id=P.NEU)
    await P.betrieb_bis(w, t1.replace(minute=0) + timedelta(hours=1), t2.replace(minute=0))
    P.UHR.stelle(t2 - timedelta(minutes=2))
    tag = date(2026, 10, 27)
    vor = {f: (await P.sichten(w, f, [tag], OKT)) for f in ("pv", "pvk")}
    await _wechsel(w, t2, "fortsetzung", quelle="ha_app", entity_id=P.C)
    ende = datetime(2026, 10, 31, 3)
    await P.betrieb_bis(w, t2.replace(minute=0) + timedelta(hours=1), ende)
    P.UHR.stelle(ende + timedelta(minutes=20))
    nach = {f: (await P.sichten(w, f, [tag], OKT)) for f in ("pv", "pvk")}
    assert nach["pv"]["tage"][tag] == vor["pv"]["tage"][tag] == _ha(w, P.NEU, *_tag(tag)) == 6.4
    assert nach["pvk"]["tage"][tag] == vor["pvk"]["tage"][tag] == _ha(w, P.PVC, *_tag(tag)) == 48.0
    assert await P.kanal_deckung(w, P.START.date(), date(2026, 10, 30)) == []
    b = await P.befunde(w)
    assert "tage_ohne_kanal_deckung" not in b
    assert "Home Assistant führt den neuen Sensor seit dem 27.10.2026 08:00 Uhr" in b["daten_vor_aenderung_geloescht"][0]


async def test_r1_aba_und_werkbank_die_erste_zeile_der_juengsten_quelle_ist_kein_beginn(db, monkeypatch, stehende_uhr):
    """R1 (Nachmessung A1): A → B → A («bleiben», «bleiben»), danach die Werkbank «Werte vor dem Sensorbeginn verwerfen» mit
    ihrer Vorgabe-Zeit (Beginn der jüngsten Quelle). Die erste Zeile danach gehört zur jüngsten A-Quelle — ihr ``sum`` ist der
    laufende Stand von A, keine Menge. Soll wie v4.3.1: die erste Stunde und der Tag «—», «Aus HA laden» = Home Assistant für A
    über den ganzen Monat; nie der Stand als Menge."""
    from backend.models.kanal import Kanal as _K

    w = await _welt(db, monkeypatch)
    t1, t2 = datetime(2026, 10, 28, 12, 20), datetime(2026, 10, 30, 12, 20)
    await P.betrieb_bis(w, P.START, t1.replace(minute=0))
    await _wechsel(w, t1, "fortsetzung", quelle="ha_app", entity_id=P.NEU)
    await P.betrieb_bis(w, t1.replace(minute=0) + timedelta(hours=1), t2.replace(minute=0))
    await _wechsel(w, t2, "fortsetzung", quelle="ha_app", entity_id=P.ALT)
    ende = datetime(2026, 10, 31, 3)
    await P.betrieb_bis(w, t2.replace(minute=0) + timedelta(hours=1), ende)
    P.UHR.stelle(ende + timedelta(minutes=20))
    P.frisch(w)
    k = (await w.db.execute(select(_K).where(_K.anlage_id == w.a.id, _K.key == KEY))).scalar_one()
    t = (await w.db.execute(text("select max(gueltig_ab) from kanal_quelle where kanal_id = :k"), {"k": k.id})).scalar_one()
    assert datetime.fromtimestamp(t) == t2.replace(minute=0)
    from backend.tests.test_werkbank_verwerfen_kommt_nicht_zurueck import _verwerfen

    await _verwerfen(w.sitzungen, w.a.id, KEY, t)
    P.frisch(w)
    st = await stunden(w.db, k, t, t + 3 * H)
    assert [w_.change for w_ in st.werte] == [None, pytest.approx(0.6), pytest.approx(0.6)]
    s = await P.sichten(w, "pv", [t2.date()], OKT)
    assert s["tage"][t2.date()] is None
    assert s["aus_ha_laden"] == _ha(w, P.ALT, datetime(2026, 10, 1), datetime(2026, 11, 1))
    # Monatssicht: Σ der Tage mit Wert — der 30.10. «—», der 31.10. bis 03:00 (3 × 0,6 = 1,8); wie v4.3.1 (Nachmessung R1:
    # 16,2 = 14,4 + 1,8). Der laufende Stand von A (über 60 kWh) erscheint nirgends.
    assert s["monatssicht"] == pytest.approx(1.8)


async def test_aba_ohne_werkbank_der_beginn_von_a_gilt(db, monkeypatch, stehende_uhr):
    """A → B → A ohne Werkbank: die erste Zeile des Kanals ist die erste der Statistik von A (erste Quelle, Marke wieder A ohne
    Grund) — der 26.10. zeigt Home Assistant (3,0), die Stunde der Rückkehr zählt über die Quellgrenze wie gebaut."""
    w = await _welt(db, monkeypatch)
    t1, t2 = datetime(2026, 10, 27, 12, 20), datetime(2026, 10, 28, 12, 20)
    await P.betrieb_bis(w, P.START, t1.replace(minute=0))
    await _wechsel(w, t1, "fortsetzung", quelle="ha_app", entity_id=P.NEU)
    await P.betrieb_bis(w, t1.replace(minute=0) + timedelta(hours=1), t2.replace(minute=0))
    await _wechsel(w, t2, "fortsetzung", quelle="ha_app", entity_id=P.ALT)
    ende = datetime(2026, 10, 29, 3)
    await P.betrieb_bis(w, t2.replace(minute=0) + timedelta(hours=1), ende)
    P.UHR.stelle(ende + timedelta(minutes=20))
    assert (await _erster_tag(w))["tag"] == _ha(w, P.ALT, *_tag(BEGINN)) == 3.0
    assert await P.kanal_deckung(w, P.START.date(), date(2026, 10, 28)) == []


async def test_ha_dann_mqtt_bleiben_der_beginn_der_ha_statistik_bleibt(db, monkeypatch, stehende_uhr):
    """HA → MQTT «bleiben» (das Feld Netzbezug wechselt von einem HA-Sensor auf das Gateway): die Marke der eigenen Summe trägt
    den Beginn der HA-Statistik weiter — der 26.10. zeigt vor und nach dem Wechsel Home Assistant (5 × 0,9 = 4,5)."""
    from backend.services.kanal import merken

    netz = "sensor.netz"
    v = P.ep(P.START) - 5 * P.STUNDE
    w = await P.mach_welt(db, monkeypatch, {netz: (v, lambda _e: 0.9), P.PVC: (v, lambda _e: 2.0)}, {"pvk": P.PVC},
                          mqtt=False, mqtt_neu=datetime(2026, 10, 28, 12, 20))
    async with w.sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == w.a.id))).scalar_one()
        m = dict(a.sensor_mapping)
        m["basis"] = {**(m.get("basis") or {}), "netzbezug": {"strategie": "sensor", "sensor_id": netz}}
        a.sensor_mapping = m
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(a, "sensor_mapping")
    P.frisch(w)

    async def netz_tag() -> float | None:
        """Der Kanal-Tag des Felds (die Tageswerte der Oberfläche nennen MQTT-Netzbezug neben HA-Feldern nicht — Kandidat
        ohne ID, v4.3.1 gleich; gemessen wird deshalb der Kanal, den die Regel betrifft)."""
        merken.invalidiere(w.a.id)
        P.frisch(w)
        k = (await w.db.execute(select(Kanal).where(Kanal.anlage_id == w.a.id, Kanal.key == P.NETZ_KEY))).scalar_one()
        return P.r3((await zeitraum(w.db, k, *(P.ep(x) for x in _tag(BEGINN)))).delta)

    t = datetime(2026, 10, 28, 12, 20)
    await P.betrieb_bis(w, P.START, t.replace(minute=0))
    P.UHR.stelle(t - timedelta(minutes=2))
    vor = await netz_tag()
    assert vor == _ha(w, netz, *_tag(BEGINN)) == 4.5
    w.mit_mqtt = True
    await _wechsel(w, t, "fortsetzung", fid=P.NETZ_FID, quelle="mqtt_gateway", quell_topic="neu/zaehler/netz")
    ende = datetime(2026, 10, 30, 3)
    await P.betrieb_bis(w, t.replace(minute=0) + timedelta(hours=1), ende)
    P.UHR.stelle(ende + timedelta(minutes=20))
    # der Anstoß nach dem Stundenlauf füllt wie der Scheduler beide Familien (``nachfuellen_anlage``): die eigene Summe des
    # MQTT-Felds setzt ihre Marke — sie trägt den Beginn der HA-Statistik weiter
    from backend.services.kanal.nachfuellen import nachfuellen_anlage

    await nachfuellen_anlage(w.sitzungen, w.a.id, jetzt=P._FDT.now(), ha_svc=w.svc, nur_vorhandene=True)
    P.frisch(w)
    marke = (await w.db.execute(text("select m.statistic_id, m.ergebnis from kanal_nachfuellung m join kanal k on "
                                     "k.id = m.kanal_id where k.key = :k"), {"k": P.NETZ_KEY})).one()
    assert marke[0] == P.NETZ_MK and '"beginn": "sensor.netz"' in marke[1]
    assert await netz_tag() == vor


async def test_quelle_keine_und_zurueck_der_beginn_bleibt(db, monkeypatch, stehende_uhr):
    """Quelle «Keine» und wieder derselbe Sensor: der Kanal behält seine Quelle und Marke (keine neue Quelle für dieselbe
    Entity), der 26.10. zeigt Home Assistant (3,0)."""
    w = await _welt(db, monkeypatch)
    t1, t2 = datetime(2026, 10, 27, 12, 20), datetime(2026, 10, 27, 18, 20)
    await P.betrieb_bis(w, P.START, t1.replace(minute=0))
    await _wechsel(w, t1, "fortsetzung", quelle="keine")
    await P.betrieb_bis(w, t1.replace(minute=0) + timedelta(hours=1), t2.replace(minute=0))
    await _wechsel(w, t2, "fortsetzung", quelle="ha_app", entity_id=P.ALT)
    ende = datetime(2026, 10, 29, 3)
    await P.betrieb_bis(w, t2.replace(minute=0) + timedelta(hours=1), ende)
    P.UHR.stelle(ende + timedelta(minutes=20))
    assert (await _erster_tag(w))["tag"] == _ha(w, P.ALT, *_tag(BEGINN)) == 3.0


async def test_entity_in_ha_umbenannt_bleiben_der_beginn_bleibt(db, monkeypatch, stehende_uhr):
    """Die Entity wird in Home Assistant umbenannt (dieselbe Statistik, neue ``statistic_id``), das Feld mit «bleiben» auf den
    neuen Namen gestellt: der 26.10. zeigt vor und nach der Umstellung Home Assistant (3,0)."""
    w = await _welt(db, monkeypatch)
    t = datetime(2026, 10, 28, 12, 20)
    await P.betrieb_bis(w, P.START, t.replace(minute=0))
    P.UHR.stelle(t - timedelta(minutes=2))
    vor = await _erster_tag(w)
    with w.svc._engine.begin() as c:
        c.execute(text("UPDATE statistics_meta SET statistic_id = 'sensor.alt_umbenannt' WHERE statistic_id = :e"),
                  {"e": P.ALT})
    w.svc._meta_cache.clear()
    await _wechsel(w, t, "fortsetzung", quelle="ha_app", entity_id="sensor.alt_umbenannt")
    ende = datetime(2026, 10, 30, 3)
    await P.betrieb_bis(w, t.replace(minute=0) + timedelta(hours=1), ende)
    P.UHR.stelle(ende + timedelta(minutes=20))
    nach = await _erster_tag(w)
    assert nach["tag"] == vor["tag"] == 3.0


# ── Teil 3: WebSocket — eine Statistik, die über 1 024 Tage ruhte, ist kein Beginn (Nachmessung B2) ──────────────────────

class _ZaehlWS:
    """WebSocket-Attrappe: ``statistics_during_period`` über Stundenzeilen; ``month``/``day`` liefern je Periode mit Daten eine
    Zeile am Periodenbeginn (wie HA). Zählt die Befehle."""

    def __init__(self, zeilen: dict):
        self._z, self.ws_url, self.n = zeilen, "ws://x", 0

    def metadaten(self, erneuern: bool = False):
        from backend.services.ha_statistics_ws import WsSensorMeta

        return {s: WsSensorMeta("kWh", True, False) for s in self._z}

    def statistiken(self, sensor_ids, von, bis, period="hour", types=None):
        self.n += 1
        out = {}
        for s in sensor_ids:
            rows = [z for z in self._z.get(s, []) if von.timestamp() <= z["start_ts"] < bis.timestamp()]
            if period != "hour":
                je = {}
                for z in rows:
                    d = datetime.fromtimestamp(z["start_ts"])
                    k = (d.replace(day=1, hour=0) if period == "month" else d.replace(hour=0)).timestamp()
                    je[k] = {**z, "start_ts": k}
                rows = list(je.values())
            out[s] = [dict(z) for z in rows]
        return out

    def erreichbar(self):
        return True

    def schliessen(self):
        pass


def _ws_dienst(zeilen: dict):
    from backend.services.ha_statistics_service import HAStatisticsService

    svc = HAStatisticsService()
    svc._initialized, svc._engine = True, None
    svc._ws_client = _ZaehlWS(zeilen)
    return svc


def _reihe(start: datetime, n: int, basis: float) -> list[dict]:
    t0 = P.ep(start)
    return [{"start_ts": float(t0 + i * H), "sum": round(basis + 0.5 * (i + 1), 6), "state": 1.0, "mean": None, "min": None,
             "max": None} for i in range(n)]


def test_ws_luecke_ueber_1024_tage_zaehlt_den_stand_nicht_als_menge():
    """Zeilen im Oktober 2023, dann erst wieder ab 10.11.2026 12:00 (laufender ``sum`` 3 020,5 …): Monat und Tag zählen gegen die
    letzte Zeile von 2023 (3 012,0) wie Home Assistant — nicht ab 0 (vorher 3 056,0 bzw. 3 025,5). Eine Statistik, die im Monat
    wirklich beginnt, zählt weiter ab 0. Mehrkosten nur dort, wo die Fenster-Leiter nichts findet: mit Geschichte keine Anfrage
    mehr (Monatsabruf mit 10 Sensoren 20, Tag 1)."""
    g = {"sensor.g": _reihe(datetime(2023, 10, 1), 24, 3000.0) + _reihe(datetime(2026, 11, 10, 12), 72, 3020.0)}
    svc = _ws_dienst(g)
    monat = next(round(x.differenz, 3) for x in svc.get_monatswerte(["sensor.g"], 2026, 11).sensoren)
    slots = svc.get_hourly_slots_for_day(["sensor.g"], date(2026, 11, 10))["sensor.g"].slots
    assert (monat, round(sum(s.delta for s in slots.values()), 3)) == (44.0, 13.5)
    neu = _ws_dienst({"sensor.n": _reihe(datetime(2026, 11, 10, 12), 72, 0.0)})
    assert next(round(x.differenz, 3) for x in neu.get_monatswerte(["sensor.n"], 2026, 11).sensoren) == 36.0
    lang = {f"sensor.s{i}": _reihe(datetime(2026, 1, 1), 24 * 330, 0.0) for i in range(10)}
    svc = _ws_dienst(lang)
    svc.get_monatswerte(list(lang), 2026, 11)
    n_monat, svc._ws_client.n = svc._ws_client.n, 0
    svc.get_hourly_slots_for_day(list(lang), date(2026, 11, 10))
    assert (n_monat, svc._ws_client.n) == (20, 1)


# ── Teil 4: MQTT ohne Plausibilitätsdeckel in der Eigenen Summe (K7, Entscheid Gernot 22.11.2026) ──────────────────────

#: Welt F7 der Nachmessung: 10 kWp, MQTT-Rohstände alle 5 Minuten, 0,6 kWh/h ab 5 000, Sprung +2 000 am 18.06.2026 10:23.
_F7_ST, _F7_EN, _F7_SPRUNG = datetime(2026, 6, 15), datetime(2026, 6, 20, 3), datetime(2026, 6, 18, 10, 23)


def _f7_stand(t: datetime) -> float:
    return round(5000.0 + 0.6 * (t.timestamp() - _F7_ST.timestamp()) / 3600 + (2000.0 if t >= _F7_SPRUNG else 0.0), 6)


@pytest.mark.parametrize("lage", ["pv", "einspeisung"])
async def test_k7_mqtt_sprung_an_pv_und_einspeisung_zaehlt_und_der_befund_nennt_ihn(db, lage):
    """Ein Sprung des Zählerstands an einem MQTT-Feld PV bzw. Einspeisung zählt am Kanal-Tag als Menge (Tag 2 014,4 in Kanal und
    Tagesansicht) — bis K7 verwarf der Deckel die ganze Stunde (13,8, kein Befund). «Zählerstand springt (MQTT)» nennt die Stunde
    mit dem Knopf «Zähler getauscht»; nach dem Eintrag zählt der Tag 14,35, der Befund ist weg — wie am Netzbezug."""
    from backend.api.routes.sensorwechsel import ZaehlerGetauschtRequest, zaehler_getauscht
    from backend.models.investition import Investition
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.services.daten_checker import DatenChecker
    from backend.services.kanal.schreiber import schreibe_kanaele_im_stundenlauf
    from backend.services.snapshot.writer import snapshot_anlage
    from backend.tests import factories
    from backend.tests.test_sensorwechsel_u3b_proben import _anlage_frisch, _laeufe, _tagesabschluss, zw

    mk, key, fid, komp = {"pv": ("inv/1/pv_erzeugung_kwh", "inv:1:pv_erzeugung_kwh", "inv_energy_1_pv_erzeugung_kwh", "pv_1"),
                          "einspeisung": ("einspeisung_kwh", "basis:einspeisung", "basis_energy_einspeisung_kwh",
                                          "einspeisung")}[lage]
    a = await factories.anlage(db, anlagenname="F7", leistung_kwp=10.0, sensor_mapping={"basis": {}, "investitionen": {}})
    db.add(Investition(id=1, anlage_id=a.id, typ="pv-module", bezeichnung="PV MQTT", leistung_kwp=10.0,
                       anschaffungsdatum=date(2024, 1, 1)))
    await db.commit()
    aid, t = a.id, _F7_ST
    while t <= _F7_EN:
        db.add(MqttEnergySnapshot(anlage_id=aid, timestamp=t, energy_key=mk, value_kwh=_f7_stand(t)))
        await db.commit()
        if t.minute == 5 and t > _F7_ST + timedelta(hours=1):
            h_ = t.replace(minute=0)
            an = await _anlage_frisch(db, aid)
            await snapshot_anlage(db, an, zeitpunkt=h_)
            await db.commit()
            await schreibe_kanaele_im_stundenlauf(db, an, h_)
            await db.commit()
            if h_.hour == 0 and h_.date() > _F7_ST.date():
                await _tagesabschluss(db, aid, h_.date() - timedelta(days=1))
            db.expunge_all()
            zw.vergiss(db)
        t = datetime.fromtimestamp(t.timestamp() + 300)
    tag = _F7_SPRUNG.date()

    async def bild():
        from backend.api.routes.energie_profil.tage import get_tages_zusammenfassungen

        zw.vergiss(db)
        k = (await db.execute(select(Kanal).where(Kanal.anlage_id == aid, Kanal.key == key))).scalar_one()
        kanal_tag = (await zeitraum(db, k, *(P.ep(x) for x in _tag(tag)))).delta
        tz = {x.datum: x for x in await get_tages_zusammenfassungen(aid, tag, tag, db)}
        res = await DatenChecker(db).check_anlage(aid)
        sprung = [(e.meldung, e.knopf) for e in res.ergebnisse if e.code == "mqtt_zaehlerstand_springt"]
        await db.rollback()
        return round(kanal_tag, 3), round((tz[tag].komponenten_kwh or {})[komp], 3), sprung

    kanal_tag, tagesansicht, sprung = await bild()
    assert (kanal_tag, tagesansicht) == (2014.4, 2014.4)
    assert len(sprung) == 1 and sprung[0][1] == "Zähler getauscht" and "18.06.2026 um 10:25 Uhr" in sprung[0][0]
    await zaehler_getauscht(aid, fid, ZaehlerGetauschtRequest(getauscht_am=_F7_SPRUNG), db)
    await _laeufe()
    db.expunge_all()
    await _tagesabschluss(db, aid, tag)
    db.expunge_all()
    assert await bild() == (14.35, 14.35, [])
