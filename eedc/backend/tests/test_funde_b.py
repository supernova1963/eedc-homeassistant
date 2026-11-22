"""Fund-Päckchen B «Betrieb, Daten-Checker, Kleines» (22.11.2026) — die Belege der gebauten Punkte.

* **B2** «Zählerstand springt» nennt auch eine HA-Statistik, die mit einem großen Stand statt bei 0 beginnt (etwa importiert):
  HA und eedc zählen den ganzen Stand als Menge der ersten Stunde (Anfangsstand 0, ``kanal/lesen._ha_beginn_sql``). Bis hierher
  meldete das an der Wallbox und der Wärmepumpe kein Befund, an PV nur ``drift_tag`` (gemessen: Wallbox 5 004,66 kWh am ersten
  Tag ohne Befund). eedc ändert die Zahl nicht; der Befund sagt, was die Quelle führt, und den Weg dort.
* **B3** ``wp_strom_fehlt_monate`` nennt auch den Monat mit gemessen 0 kWh Strom bei Wärme > 0 (seit Päckchen A ohne Ersparnis).

B1 (Job-Kollision 03:05) belegt ``test_scheduler_job_registrierung.py::TestKeineZweiJobsInDerselbenMinute``.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm.attributes import flag_modified

import backend.tests.test_sensorwechsel_wegb_loeschen_proben as P
from backend.core.berechnungen.zaehlerstand_sprung import BEGINN, beginn_ueber_grenze, grenze_unmoeglich
from backend.services.daten_checker.datenquelle.standsprung import finde
from backend.tests.test_sensorwechsel_wegb_loeschen_proben import stehende_uhr  # noqa: F401

# ── B2: Layer und reine Erkennung ─────────────────────────────────────────────────────────────────────────────────────

T1 = 1_793_000_000


def test_b2_beginn_ueber_der_grenze_ist_ein_fund_von_0_auf_den_stand():
    sp = beginn_ueber_grenze((T1, 5000.7, 5000.7), grenze_unmoeglich(15.0))
    assert (sp.start_ts, sp.art, sp.menge, sp.stand_vorher, sp.stand_nachher, sp.mass) == (T1, BEGINN, 5000.7, 0.0, 5000.7, 0.0)


@pytest.mark.parametrize("zeile,grenze", [
    ((T1, 0.6, 0.6), 100.0),          # gewöhnliche erste Stunde
    ((T1, 100.0, 100.0), 100.0),      # genau auf der Grenze
    ((T1, 5000.7, 5000.7), None),     # ohne Grenze (Stand-Zähler in m³/l/km)
    ((T1, 5000.7, None), 100.0),      # ohne Summe
])
def test_b2_kein_fund_unter_der_grenze_ohne_grenze_ohne_summe(zeile, grenze):
    assert beginn_ueber_grenze(zeile, grenze) is None


def _zeilen(key: str, art: str, einheit: str, z: list[tuple]) -> list[tuple]:
    return [(1, key, art, einheit, z[0][0], "sensor.x", ts, st, su) for ts, st, su in z]


def test_b2_finde_nur_wenn_eedc_die_erste_zeile_ab_0_zaehlt():
    z = [(T1 + i * 3600, 5000.7 + 1.32 * i, 5000.7 + 1.32 * i) for i in range(30)]
    mit = finde(_zeilen("inv:2:ladung_kwh", "sum", "kWh", z), 15.0, {"inv:2:ladung_kwh": T1})
    assert [(f.key, f.sprung.art, f.sprung.menge) for f in mit] == [("inv:2:ladung_kwh", BEGINN, 5000.7)]
    # Ohne Marke «Beginn der HA-Statistik» (der Spiegel beginnt nach HAs Geschichte, die erste Zeile zählt nirgends): still.
    assert finde(_zeilen("inv:2:ladung_kwh", "sum", "kWh", z), 15.0, {}) == []
    assert finde(_zeilen("inv:2:ladung_kwh", "sum", "kWh", z), 15.0, {"inv:2:ladung_kwh": T1 + 3600}) == []
    # Stand-Zähler: eedc zählt Δ state, die erste Zeile nie als Menge.
    assert finde(_zeilen("inv:9:zaehlerstand", "stand", "m³", z), 15.0, {"inv:9:zaehlerstand": T1}) == []


# ── B2: Welt (Erst-Zuordnung einer importierten Statistik, Sichten und Daten-Checker) ─────────────────────────────────

WPS, WPH = "sensor.wp_strom", "sensor.wp_heiz"


async def _welt_import(db, monkeypatch, an: str | None):
    from backend.models.investition import Investition

    v = P.ep(P.START) - 5 * P.STUNDE
    monkeypatch.setitem(P.FELDER, "wp", ("4", "stromverbrauch_kwh", "inv:4:stromverbrauch_kwh", "waermepumpe_4"))

    def fn(gross, normal, feld):
        return (lambda e: gross if e == v else normal) if an == feld else (lambda _e: normal)
    serien = {P.ALT: (v, fn(1000.4, 0.6, "pv")), P.PVC: (v, lambda _e: 2.0), P.WB: (v, fn(5000.7, 1.32, "wb")),
              WPS: (v, fn(3000.5, 2.5, "wp")), WPH: (v, lambda _e: 7.5)}
    w = await P.mach_welt(db, monkeypatch, serien, {"pv": P.ALT, "pvk": P.PVC, "wb": P.WB, "wp": WPS}, mqtt=False)
    db.add(Investition(id=4, anlage_id=w.a.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1)))
    a = await P.anlage(w)
    m = json.loads(json.dumps(a.sensor_mapping))
    m["investitionen"]["4"]["felder"]["heizenergie_kwh"] = {"strategie": "sensor", "sensor_id": WPH}
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    P.frisch(w)
    ende = datetime(2026, 10, 29, 3)
    await P.betrieb_bis(w, P.START, ende)
    P.UHR.stelle(ende + timedelta(minutes=20))
    return w, v


async def _springt(w):
    from backend.services.daten_checker import DatenChecker

    P.frisch(w)
    res = await DatenChecker(w.db).check_anlage(w.a.id)
    out = [e for e in res.ergebnisse if e.code == "ha_zaehlerstand_springt"]
    await w.db.rollback()
    P.frisch(w)
    return out


@pytest.mark.parametrize("feld,eid,menge,name", [
    ("wb", P.WB, 5000.7, "WB · Ladung gesamt (sensor.wb) am 26.10.2026, Stunde ab 19:00: +5.000,7 kWh (Stand 0,0 → 5.000,7"),
    ("pv", P.ALT, 1000.4, "PV Feld · PV-Erzeugung (sensor.alt) am 26.10.2026, Stunde ab 19:00: +1.000,4 kWh (Stand 0,0 → 1.000,4"),
    ("wp", WPS, 3000.5, "WP · Stromverbrauch (sensor.wp_strom) am 26.10.2026, Stunde ab 19:00: +3.000,5 kWh (Stand 0,0 → 3.000,5"),
])
async def test_b2_importierte_statistik_nennt_der_befund_an_jeder_feldart(db, monkeypatch, stehende_uhr, feld, eid, menge, name):  # noqa: F811
    """Tag und Monat zählen den Stand wie HA (unverändert, Quellentreue); der Befund nennt Feld, Sensor, Stunde, Menge, den
    Satz zum Beginn und den Weg in HA. Am HEAD ``be1d4e935``: kein Befund an Wallbox und Wärmepumpe, an PV nur ``drift_tag``."""
    from backend.tests.werkzeug_befund import befund_op, befund_params

    w, _v = await _welt_import(db, monkeypatch, feld)
    s = await P.sichten(w, feld, [P.WELTBEGINN], (2026, 10))
    ha_tag = w.ha_summe(eid, datetime(2026, 10, 26), datetime(2026, 10, 27))
    assert s["tage"][P.WELTBEGINN] > menge and ha_tag > menge      # die Zahl bleibt, was HA führt
    (e,) = await _springt(w)
    assert name + ", die Statistik beginnt mit diesem Stand statt bei 0)" in e.details
    assert "Beginnt die Statistik eines Sensors in Home Assistant mit einem großen Stand statt bei 0" in e.details
    assert "„Summe anpassen“" in e.details
    assert (befund_op(e), befund_params(e)) == ("spiegel_abgleich_tag", {"datum": "2026-10-26"})
    assert e.werte["funde"][0]["art"] == BEGINN and e.werte["funde"][0]["menge"] == menge


async def test_b2_gewoehnlicher_beginn_ohne_befund(db, monkeypatch, stehende_uhr):  # noqa: F811
    w, _v = await _welt_import(db, monkeypatch, None)
    assert await _springt(w) == []


@pytest.mark.parametrize("feld,eid,gross,klein", [("pv", P.ALT, 1000.4, 0.6), ("wb", P.WB, 5000.7, 1.32), ("wp", WPS, 3000.5, 2.5)])
async def test_b2_nach_summe_anpassen_in_ha_und_uebernahme_ist_der_befund_weg(db, monkeypatch, stehende_uhr,  # noqa: F811
                                                                               feld, eid, gross, klein):
    """Der Lösungsweg: in HA «Summe anpassen» an der ersten Stunde (Neuer Wert = die echte Menge), danach der Knopf
    «Aus Home Assistant neu übernehmen» (``plan`` → ``execute``) ⇒ kein Befund; «Aus HA laden» zeigt HAs berichtigte Zahl,
    an PV und Wärmepumpe auch Tag und Monatssicht."""
    from backend.services.repair_orchestrator import RepairOperationRequest, RepairOperationType, execute, plan
    from backend.tests.werkzeug_befund import befund_op, befund_params

    w, v = await _welt_import(db, monkeypatch, feld)
    monkeypatch.setattr("backend.core.database.get_session", w.sitzungen)   # der Abgleich öffnet eigene Sitzungen

    async def _ohne_boerse(*_a, **_k):
        return None              # der Tag-Lauf fragt die Börse; kein Netz in Proben
    monkeypatch.setattr("backend.services.strompreis_markt_service.fetch_marktpreise", _ohne_boerse)
    (e,) = await _springt(w)
    with w.svc._engine.begin() as c:                      # HA: «Summe anpassen» verschiebt die Summe ab der Stunde
        c.execute(text("UPDATE statistics SET sum = sum - :d WHERE metadata_id = :m AND start_ts >= :t"),
                  {"d": gross - klein, "m": w.mids[eid], "t": v})
    p = await plan(RepairOperationRequest(anlage_id=w.a.id, operation=RepairOperationType(befund_op(e)),
                                          params=befund_params(e)), w.db)
    r = await execute(p.plan_id, w.db)
    assert r.operation_summary.get("fehlgeschlagen", 0) == 0, r.operation_summary
    assert await _springt(w) == []
    s = await P.sichten(w, feld, [P.WELTBEGINN], (2026, 10))
    ha_tag = w.ha_summe(eid, datetime(2026, 10, 26), datetime(2026, 10, 27))
    ha_okt = w.ha_summe(eid, datetime(2026, 10, 1), datetime(2026, 11, 1))
    assert s["aus_ha_laden"] == ha_okt and ha_okt < 200.0
    if feld != "wb":
        assert (s["tage"][P.WELTBEGINN], s["monatssicht"]) == (ha_tag, ha_okt), s
    # Wallbox: Tag und Monatssicht folgen der Übernahme NICHT (Tag 5 004,66, Monat 5 004,66 gegen HA 6,6/73,92) — dieselbe
    # Lage wie bei einem Sprung mitten in der Reihe am HEAD (Bericht Funde B, offener Punkt «Übernahme an der Wallbox»);
    # hier bewusst nicht festgeschrieben.


# ── B3: «Strom gemessen 0 bei Wärme > 0» ──────────────────────────────────────────────────────────────────────────────

WP_GESAMT = {"wp_art": "luft_wasser"}
WP_GETRENNT = {"wp_art": "luft_wasser", "getrennte_strommessung": True}


async def _wp_strom_befund(db, parameter: dict, monate: dict[int, dict]):
    from backend.tests.test_n443_f5_ein_stromfeld_fehlt import _wp_befunde

    return [e for e in await _wp_befunde(db, parameter=parameter, monate=monate) if e.code == "wp_strom_fehlt_monate"]


async def test_b3_strom_0_bei_waerme_nennt_der_befund(db):
    """Knopf «Monat öffnen» springt in den ersten genannten Monat. Am HEAD ``be1d4e935`` kein Befund (nur ``is None``); der Monat trägt seit Päckchen A keine Ersparnis."""
    from backend.tests.werkzeug_befund import befund_link

    (e,) = await _wp_strom_befund(db, WP_GESAMT, {
        1: {"stromverbrauch_kwh": 300.0, "heizenergie_kwh": 1000.0},
        2: {"stromverbrauch_kwh": 0.0, "heizenergie_kwh": 400.0},
    })
    assert e.meldung == "WP: Stromverbrauch fehlt oder ist 0 kWh bei erfasster Wärme in 1 Monat(en)"
    assert e.details == "0 kWh Strom bei erfasster Wärme: 02/2025"
    assert befund_link(e).startswith("/einstellungen/daten?erfassen=2025-02&")


async def test_b3_fehlt_und_null_in_einer_zeile_wortlaut_ohne_null_wie_bisher(db):
    beide = await _wp_strom_befund(db, WP_GESAMT, {
        1: {"heizenergie_kwh": 1000.0},
        2: {"stromverbrauch_kwh": 0.0, "heizenergie_kwh": 400.0},
        3: {"stromverbrauch_kwh": 300.0, "heizenergie_kwh": 1000.0},
    })
    assert [(e.meldung, e.details) for e in beide] == [(
        "WP: Stromverbrauch fehlt oder ist 0 kWh bei erfasster Wärme in 2 Monat(en)",
        "01/2025; 0 kWh Strom bei erfasster Wärme: 02/2025")]
    (nur_fehlt,) = await _wp_strom_befund(db, WP_GESAMT, {
        1: {"heizenergie_kwh": 1000.0}, 2: {"stromverbrauch_kwh": 300.0, "heizenergie_kwh": 1000.0}})
    assert (nur_fehlt.meldung, nur_fehlt.details) == ("WP: Stromverbrauch fehlt in 1 Monat(en)", "01/2025")


@pytest.mark.parametrize("parameter,zeile", [
    (WP_GESAMT, {"stromverbrauch_kwh": 0.0, "heizenergie_kwh": 0.0}),                 # 0/0: kein Betrieb (N-806)
    (WP_GESAMT, {"stromverbrauch_kwh": 15.0, "heizenergie_kwh": 0.0}),                # Standby (N-670)
    (WP_GESAMT, {"stromverbrauch_kwh": 0.0, "strom_heizen_kwh": 250.0,                # getrennte Messung aus, Teilfelder
                 "heizenergie_kwh": 1000.0}),                                         # gepflegt: anderer Befund
    (WP_GETRENNT, {"strom_heizen_kwh": 250.0, "strom_warmwasser_kwh": 0.0,            # eine Seite 0, Strom > 0
                   "heizenergie_kwh": 1000.0, "warmwasser_kwh": 0.0}),
])
async def test_b3_ausgenommen(db, parameter, zeile):
    assert await _wp_strom_befund(db, parameter, {1: zeile}) == []


async def test_b3_getrennte_messung_beide_seiten_0_bei_waerme(db):
    (e,) = await _wp_strom_befund(db, WP_GETRENNT, {
        1: {"strom_heizen_kwh": 0.0, "strom_warmwasser_kwh": 0.0, "heizenergie_kwh": 800.0, "warmwasser_kwh": 100.0}})
    assert e.meldung == "WP: Strom Heizen/Warmwasser fehlt oder ist 0 kWh bei erfasster Wärme in 1 Monat(en)"


# ── H4/H5: Kasten «Was noch möglich wäre» im Tag ohne wirkungslosen Handgriff ─────────────────────────────────────────

def test_h5_kasten_ohne_handgriff_behaelt_grund_und_groesse():
    from backend.core.berechnungen.waermepumpe_kennzahl import GRUND_ZEITRAUM
    from backend.services.waerme_klima_block import was_noch_moeglich

    mit = was_noch_moeglich([("Arbeitszahl", GRUND_ZEITRAUM)])
    ohne = was_noch_moeglich([("Arbeitszahl", GRUND_ZEITRAUM)], ohne_handgriff=frozenset({GRUND_ZEITRAUM}))
    assert [(z.grund, z.handgriff) for z in mit] == [(GRUND_ZEITRAUM, "Lücken im Monatsabschluss schließen")]
    assert [(z.grund, z.groesse, z.handgriff, z.link) for z in ohne] == [(GRUND_ZEITRAUM, "Arbeitszahl", None, None)]


async def test_h4_tag_vor_der_ersten_zeile_eines_geloeschten_wp_stromfelds_ohne_werkbank_handgriff(  # noqa: F811
        db, monkeypatch, stehende_uhr):
    """Welt der Nachmessung Weg B (``loeschen-wp_jung``): WP-Strom ab 04.11. 08:00 neu, «löschen» am 04.11. 10:20. Am 03.11.
    trägt die Arbeitszahl «für diesen Tag keine Zählerstände»; am HEAD ``be1d4e935`` mit dem Handgriff «Den Tag in der
    Reparatur-Werkbank nachrechnen» — die Werkbank hat dort nichts. Der 04.11. (erste Zeile) bleibt unberührt."""
    from backend.api.routes.energie_profil.tag import get_tag_detail
    from backend.models.investition import Investition
    from backend.services.kanal import merken

    v = P.ep(P.START) - 5 * P.STUNDE
    e_neu = datetime(2026, 11, 4, 8)
    monkeypatch.setitem(P.FELDER, "wp", ("4", "stromverbrauch_kwh", "inv:4:stromverbrauch_kwh", "waermepumpe_4"))
    serien = {P.ALT: (v, lambda _e: 0.6), P.PVC: (v, lambda _e: 2.0), P.WB: (v, lambda _e: 1.32),
              P.NEU: (P.ep(e_neu), lambda _e: 0.4), WPS: (v, lambda _e: 0.8), WPH: (v, lambda _e: 2.4)}
    w = await P.mach_welt(db, monkeypatch, serien, {"pv": P.ALT, "pvk": P.PVC, "wb": P.WB}, mqtt=True)
    db.add(Investition(id=4, anlage_id=w.a.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1)))
    a = await P.anlage(w)
    m = json.loads(json.dumps(a.sensor_mapping))
    m["investitionen"]["4"] = {"felder": {"stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": WPS},
                                          "heizenergie_kwh": {"strategie": "sensor", "sensor_id": WPH}}}
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    P.frisch(w)
    await P._bis_zum_wechsel(w, P.T0)
    await P.loeschen(w, P.T0, "inv_energy_4_stromverbrauch_kwh", quelle="ha_app", entity_id=P.NEU)
    await P._nach_dem_wechsel(w, P.T0)

    async def kasten(d):
        P.frisch(w)
        merken.invalidiere(w.a.id)
        td = await get_tag_detail(anlage_id=w.a.id, datum=d, db=w.db)
        await w.db.commit()
        return {z.grund: z.handgriff for z in td.wp_moeglich or []}

    vor = await kasten(date(2026, 11, 3))
    assert "für diesen Tag keine Zählerstände" in vor and vor["für diesen Tag keine Zählerstände"] is None
    assert vor["Strom nicht getrennt je Funktion gemessen"] == "Getrennte Strommessung einschalten und beide Zähler zuordnen"
    assert "für diesen Tag keine Zählerstände" not in await kasten(date(2026, 11, 4))


async def test_h5_tag_route_nennt_den_zeitraum_grund_ohne_monatsabschluss_handgriff(db):
    """Bestandstag der A1-Probe (Strom ab 08:00, Wärme ab 00:00): die Arbeitszahl trägt «Zähler messen verschiedene Zeiträume».
    Am HEAD ``be1d4e935`` stand im Kasten dazu «Lücken im Monatsabschluss schließen» — im Tag gibt es keinen Monatsabschluss;
    Handbuch Wärme & Klima §4: im Tag nichts zu tun."""
    from backend.core.berechnungen.waermepumpe_kennzahl import GRUND_ZEITRAUM
    from backend.tests.test_funde_a_anzeige import _bestand_tag

    r = await _bestand_tag(db, strom_ab=8, waerme_ab=0)
    zeilen = [(z.grund, z.handgriff, z.link) for z in r.wp_moeglich or [] if z.grund.endswith(GRUND_ZEITRAUM)]
    assert zeilen and all(h is None and link is None for _g, h, link in zeilen), r.wp_moeglich


# ── H1: Werkbank-Vorschau «Werte vor dem Sensorbeginn verwerfen» mit Einzahl ─────────────────────────────────────────

def test_h1_werkbank_vorschau_einzahl_und_mehrzahl():
    """Lab-Durchlauf 2b W11: «1 Tage …» (v4.3.1-Wortlaut). Am HEAD ``be1d4e935``: «Danach haben 1 Tage …», «1 Tag(e) …»."""
    from types import SimpleNamespace

    from backend.services.verwerfen_vor_quellbeginn import _saetze_danach

    d1, d2 = date(2026, 11, 3), date(2026, 11, 4)

    def lage(ohne, nur, mit):
        return SimpleNamespace(lesart1_ohne_werte=lambda: ohne, nur_kanal=nur, lesart1_mit_bestand=lambda: mit)

    eins = " ".join(_saetze_danach(lage([d1], {d1: 1}, [d1])))
    assert "Danach hat 1 Tag (03.11.2026) keinen Wert" in eins
    assert "An 1 Tag (03.11.2026), die nur" in eins
    assert "1 Tag verliert seine Kanalzeilen (03.11.2026), sein Bestand bleibt" in eins
    zwei = " ".join(_saetze_danach(lage([d1, d2], {d1: 1, d2: 1}, [d1, d2])))
    assert "Danach haben 2 Tage (" in zwei and "An 2 Tagen (" in zwei and "2 Tage verlieren ihre Kanalzeilen (" in zwei
    assert "Tag(e)" not in eins + zwei and "1 Tage" not in eins


# ── H2: «Zählerstand springt zwischendurch zurück» — der Satz trägt auch einen einzelnen Rückgang ───────────────────────

async def test_h2_ruecksprung_satz_nennt_auch_den_einzelnen_rueckgang():
    """Nachmessung Weg B (Saat ``mqtt_stueck_ohne``: MQTT-Stand zwei Tage um 2 000 höher, danach zurück): der Satz sagte nur
    «typisch für ein Feld, das „heute“ … meint». Am HEAD ``be1d4e935`` fehlt der Satz zum einzelnen Rückgang."""
    from backend.tests.test_s4_r7_tagesreset_zaehler import _rueckspruenge, datenstand

    async with datenstand("beide") as (sitzungen, aid, _keys):
        (b,) = await _rueckspruenge(sitzungen, aid)
    assert "fällt er immer wieder zurück, typisch für ein Feld, das „heute“ oder „diesen Monat“ meint" in b.details
    assert "fällt er einmal, kann auch ein neuer Zähler begonnen oder die Quelle eine Zeit lang einen anderen Stand" in b.details
    assert "am Feld mit „Zähler getauscht (gleiche Quelle)“ ein" in b.details
    assert b.details.split("Lösung: ")[1].startswith("Schicke den fortlaufenden Stand statt des Tageswerts.")
