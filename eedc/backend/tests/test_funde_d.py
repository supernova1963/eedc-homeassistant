"""Fund-Päckchen D (22.11.2026) — Repo-Tests.

**R-D1 (N-816), wie Home Assistant:** vor dem Beginn seiner Quelle trägt ein neu zugeordnetes Feld nichts, die übrigen Felder
zählen weiter. Gemessen am HEAD ``f512e9c52`` und am Stand v4.3.1 (``golden-master/funde-d-2026-11-22/test_mess_d1_n816.py``,
dieselbe Welt): ein PV-Modul, dessen HA-Statistik am 02.11. 08:00 beginnt und das am 04.11. 10:20 zugeordnet wird, nahm den Tagen
27.10.–01.11. (v4.3.1: bis 02.11.) die Kanal-Deckung — Tageswert Erzeugung «—» statt 62,4, Monatssicht des unberührten PV-Felds
Oktober «—» statt 75,0; unmittelbar nach der Zuordnung bis zum nächsten Stundenlauf an allen Tagen «—». Die Regel steht an einer
Stelle (``kanal/bilanz_adapter.BewusstLeer``, am Bedarf jeder Gruppenwahl): die Quelle beginnt erst bei oder nach dem Ende des
Zeitraums (erste Zeile = Beginn der HA-Statistik bzw. erster MQTT-Stand) oder das Feld hat noch keinen Kanal ⇒ nicht benötigt.

Welt: ``test_sensorwechsel_wegb_loeschen_proben`` (HA-Attrappe, stehende Uhr, echte Stundenläufe).

Schwesterdateien: test_kanal_verworfen_bewusst_leer.py (dieselbe Regel für «verworfen»), test_sensorwechsel_wegb_loeschen_proben.py
(Welt, «löschen»), test_funde_c.py, test_kanal_lesen.py (Abdeckungsregel der Lese-Schicht).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

import backend.tests.test_sensorwechsel_wegb_loeschen_proben as P
from backend.tests.test_sensorwechsel_wegb_loeschen_proben import stehende_uhr  # noqa: F401 — Fixture

NEU_PV = "sensor.pv_neu"
FID_5 = "inv_energy_5_pv_erzeugung_kwh"
TAGE = [date(2026, 10, 27) + timedelta(days=i) for i in range(8)]       # 27.10. … 03.11.


async def _welt_junges_pv_modul(db, monkeypatch, *, beginn: datetime = datetime(2026, 11, 2, 8)):
    """PV Feld (0,6), PV-Kontrolle (2,0), Wallbox (1,32) über HA ab 26.10. 19:00; PV-Modul 5 (2 kWp) ohne Zuordnung; HA führt
    ``sensor.pv_neu`` (2,5 kWh/h) ab ``beginn``. Betrieb bis zum 04.11. 10:00 (Oktober abgeschlossen)."""
    from backend.models.investition import Investition

    v = P.ep(P.START) - 5 * P.STUNDE
    serien = {P.ALT: (v, lambda _e: 0.6), P.PVC: (v, lambda _e: 2.0), P.WB: (v, lambda _e: 1.32),
              NEU_PV: (P.ep(beginn), lambda _e: 2.5)}
    w = await P.mach_welt(db, monkeypatch, serien, {"pv": P.ALT, "pvk": P.PVC, "wb": P.WB}, mqtt=False)
    db.add(Investition(id=5, anlage_id=w.a.id, typ="pv-module", bezeichnung="PV neu", leistung_kwp=2.0,
                       anschaffungsdatum=date(2024, 1, 1)))
    await db.commit()
    await P._bis_zum_wechsel(w, P.T0)
    return w


async def _zuordnen(w) -> None:
    from backend.api.routes.datenquellen import QuelleSetRequest, set_feld_quelle

    P.UHR.stelle(P.T0)
    P.frisch(w)
    await set_feld_quelle(w.a.id, FID_5, QuelleSetRequest(quelle="ha_app", entity_id=NEU_PV), w.db)
    await P.laeufe()
    P.frisch(w)
    P.UHR.stelle(P.T0)


async def _tage(w) -> dict:
    """Je Tag (Erzeugung, PV-Modul 5) über die Routen (``baue_tage_werte`` bzw. ``/tage``)."""
    from backend.api.routes.energie_profil.tage import get_tages_zusammenfassungen
    from backend.services.energie_profil.tage_werte import baue_tage_werte
    from backend.services.kanal import merken

    merken.invalidiere(w.a.id)
    P.frisch(w)
    erz = {x.datum: P.r3(x.erzeugung) for x in await baue_tage_werte(w.db, await P.anlage(w), TAGE[0], TAGE[-1])}
    tz = {t.datum: P.r3((t.komponenten_kwh or {}).get("pv_5")) for t in
          await get_tages_zusammenfassungen(w.a.id, TAGE[0], TAGE[-1], w.db)}
    await w.db.commit()
    return {d: (erz.get(d), tz.get(d)) for d in TAGE}


async def test_rd1_junger_sensor_die_tage_davor_behalten_deckung_und_zahlen(db, monkeypatch, stehende_uhr):
    """Vor dem Beginn seiner Statistik trägt das neue PV-Modul nichts (Tag ohne Wert), die übrigen Felder zählen weiter — auch
    unmittelbar nach der Zuordnung, vor dem ersten Stundenlauf; ab seinem Beginn zählt es (02.11. ab 08:00 wie HA)."""
    w = await _welt_junges_pv_modul(db, monkeypatch)
    vorher = await _tage(w)
    assert all(vorher[d] == (62.4, None) for d in TAGE), vorher
    await _zuordnen(w)
    # unmittelbar nach der Zuordnung (noch kein Kanal für das neue Feld): nichts fehlt an den übrigen Feldern
    assert await P.kanal_deckung(w, TAGE[0], TAGE[-1]) == []
    assert await _tage(w) == vorher
    assert (await P.sichten(w, "pv", TAGE[:5], (2026, 10)))["monatssicht"] == 75.0
    await P._nach_dem_wechsel(w, P.T0)
    assert await P.kanal_deckung(w, TAGE[0], TAGE[-1]) == []
    nach = await _tage(w)
    assert {d: nach[d] for d in TAGE[:6]} == {d: (62.4, None) for d in TAGE[:6]}            # 27.10. … 01.11.: ohne Wert
    assert (nach[date(2026, 11, 2)], nach[date(2026, 11, 3)]) == ((102.4, 40.0), (122.4, 60.0))
    assert nach[date(2026, 11, 2)][1] == w.ha_summe(NEU_PV, datetime(2026, 11, 2), datetime(2026, 11, 3))
    s = await P.sichten(w, "pv", TAGE[:5], (2026, 10))
    assert s["monatssicht"] == 75.0 and all(s["tage"][d] == 14.4 for d in TAGE[:5])
    assert "tage_ohne_kanal_deckung" not in await P.befunde(w)


async def test_rd1_im_zweifel_gilt_die_regel_nicht_und_der_befund_spricht(db, monkeypatch, stehende_uhr):
    """Ist die erste Zeile nicht als Beginn der HA-Statistik bestätigt (Marke des Nachfüllens mit Grund), gilt die Regel nicht:
    die Tage davor bleiben ohne Kanal-Deckung, und der Befund ``tage_ohne_kanal_deckung`` nennt sie (wie vor R-D1)."""
    w = await _welt_junges_pv_modul(db, monkeypatch)
    await _zuordnen(w)
    await P._nach_dem_wechsel(w, P.T0)
    await w.db.execute(text("update kanal_nachfuellung set ergebnis = json_set(ergebnis, '$.grund', 'probe') where kanal_id = "
                            "(select id from kanal where key = 'inv:5:pv_erzeugung_kwh')"))
    await w.db.commit()
    # 27.10. … 01.11. und der Tag des Beginns (02.11.: auch die Regel «Anfangsstand 0» braucht den bestätigten Beginn)
    assert await P.kanal_deckung(w, TAGE[0], TAGE[-1]) == TAGE[:7]
    assert "tage_ohne_kanal_deckung" in await P.befunde(w)


async def test_rd1_zaehlerluecke_mitten_in_der_quelle_wie_bisher(db, monkeypatch, stehende_uhr):
    """Gegenprobe: HA führt für die PV-Kontrolle am 29.10. keine Zeile (Lücke mitten in einer laufenden Quelle). Das bleibt eine
    Zählerlücke wie HA: der Tag ist gedeckt und trägt 0, die Menge steht in der ersten Stunde danach (30.10. 00:00)."""
    v = P.ep(P.START) - 5 * P.STUNDE
    w = await P.mach_welt(db, monkeypatch, {P.ALT: (v, lambda _e: 0.6), P.PVC: (v, lambda _e: 2.0)},
                          {"pv": P.ALT, "pvk": P.PVC}, mqtt=False)
    echt = w.ha_bis
    luecke = (P.ep(datetime(2026, 10, 29)), P.ep(datetime(2026, 10, 29, 23)))

    def ha_bis(bis: int) -> None:
        echt(bis)
        with w.svc._engine.begin() as c:
            c.execute(text("delete from statistics where metadata_id = :m and start_ts between :a and :b"),
                      {"m": w.mids[P.PVC], "a": luecke[0], "b": luecke[1]})
    w.ha_bis = ha_bis
    await P.betrieb_bis(w, P.START, datetime(2026, 10, 31, 3))
    P.UHR.stelle(datetime(2026, 10, 31, 3, 20))
    tage = [date(2026, 10, 28), date(2026, 10, 29), date(2026, 10, 30)]
    assert await P.kanal_deckung(w, tage[0], tage[-1]) == []
    s = await P.sichten(w, "pvk", tage, (2026, 10))
    assert [s["tage"][d] for d in tage] == [48.0, 0.0, 96.0]
    assert (await P.sichten(w, "pv", tage, (2026, 10)))["tage"] == {d: 14.4 for d in tage}


def test_rd1_regel_rein():
    """Die Regel als reine Funktion: vor dem Beginn (``beginn ≥ bis``) und «noch kein Kanal» (nur in einer Anlage mit
    Kanälen) ⇒ nicht benötigt; ab dem Beginn und bei unbestätigtem Beginn benötigt; «vor Beginn» ist kein bewusstes Leer."""
    from types import SimpleNamespace

    from backend.services.kanal.bilanz_adapter import BewusstLeer

    v, n = 1000, 2000
    leer = BewusstLeer({"x": (2500, ((500, 2500, True), (2500, None, False)))},
                       beginn={"a": 2000, "b": 1500}, mit_zeile=frozenset({"a", "b", "c", "x"}))
    assert leer.leer("a", v, n) and leer.vor_beginn("a", v, n)           # Quelle beginnt am Ende des Zeitraums
    assert not leer.leer("b", v, n)                                       # Beginn im Zeitraum (Rand-Tag: lesen.py)
    assert not leer.leer("c", v, n)                                       # Zeilen, Beginn nicht bestätigt
    assert leer.leer("neu", v, n)                                         # noch kein Kanal, Anlage mit Kanälen
    assert not BewusstLeer().leer("neu", v, n)                            # Anlage ohne Kanäle: wie bisher
    e = [SimpleNamespace(schluessel=k) for k in ("a", "x")]
    assert [x.schluessel for x in leer.ohne(e, v, n)] == []
    assert not leer.alle_verworfen(e, v, n) and leer.alle_verworfen(e[1:], v, n)


async def test_rd1_mqtt_anlage_feld_mit_spaeterem_ersten_stand(db, monkeypatch, stehende_uhr):
    """Reine MQTT-Anlage: Netzbezug ab 26.10. 19:00, Einspeisung sendet erst ab 30.10. 12:00. Vor dem ersten Stand der
    Einspeisung trägt sie nichts; der Netzbezug zählt an diesen Tagen aus dem Kanal (27.–29.10. je 21,6)."""
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot

    w = await P.mach_welt(db, monkeypatch, {}, {}, mqtt=True, live=False)
    einsp_ab = datetime(2026, 10, 30, 12)
    h = P.START
    while h <= datetime(2026, 10, 31, 3):
        for m in (-45, -30, -15, 0):
            t = h + timedelta(minutes=m)
            if t >= einsp_ab:
                w.db.add(MqttEnergySnapshot(anlage_id=w.a.id, timestamp=t, energy_key="einspeisung_kwh",
                                            value_kwh=round(500.0 + 0.5 * (t - einsp_ab).total_seconds() / 3600, 6)))
        await w.db.commit()
        await P.lauf_05(w, h)
        if h.hour in (0, 2):
            await P.aggregiere(w, h + timedelta(minutes=15), h.date() - timedelta(days=1))
        h += timedelta(hours=1)
    P.UHR.stelle(datetime(2026, 10, 31, 3, 20))
    tage = [date(2026, 10, 27), date(2026, 10, 28), date(2026, 10, 29)]
    assert await P.kanal_deckung(w, tage[0], tage[-1]) == []
    assert await P.netz_tage(w, tage) == {d: 21.6 for d in tage}


async def test_zaehler_getauscht_zieht_die_abgeleiteten_kanaele_sofort_nach(db, monkeypatch, stehende_uhr):
    """Nachbar von N-814 (gemessen am HEAD ``f512e9c52``, ``golden-master/funde-d-2026-11-22/test_mess_d5_nachbarn.py``):
    «Zähler getauscht (gleiche Quelle)» am MQTT-Netzbezug trägt die Fortsetzung nach und verwirft dabei den PV-Anteil der
    Heimladung ab der Stunde des Tauschs — bis zum nächsten Stundenlauf zeigte die Wallbox am 28.10. «—» und im Oktober 36,96
    statt 72,6. Jetzt zieht die Route die abgeleiteten Kanäle sofort nach (``konsistenz.abgeleitete_nachziehen``)."""
    from backend.api.routes.sensorwechsel import ZaehlerGetauschtRequest, zaehler_getauscht

    t = datetime(2026, 10, 28, 12, 20)
    v = P.ep(P.START) - 5 * P.STUNDE
    w = await P.mach_welt(db, monkeypatch, {P.ALT: (v, lambda _e: 0.6), P.PVC: (v, lambda _e: 2.0), P.WB: (v, lambda _e: 1.32)},
                          {"pv": P.ALT, "pvk": P.PVC, "wb": P.WB}, mqtt=True, mqtt_neu=t)
    ende = datetime(2026, 10, 29, 3)
    await P.betrieb_bis(w, P.START, ende)
    P.UHR.stelle(ende + timedelta(minutes=20))
    tage = [date(2026, 10, 27), date(2026, 10, 28)]
    vorher = await P.sichten(w, "wb", tage, (2026, 10))
    monkeypatch.setattr("backend.core.database.get_session", w.sitzungen)   # das Nachziehen öffnet eine eigene Sitzung
    r = await zaehler_getauscht(w.a.id, P.NETZ_FID, ZaehlerGetauschtRequest(getauscht_am=t), w.db)
    assert r["eingetragen"]
    P.frisch(w)
    nachher = await P.sichten(w, "wb", tage, (2026, 10))
    assert nachher["tage"] == vorher["tage"] == {tage[0]: 31.68, tage[1]: 31.68}
    assert nachher["monatssicht"] == vorher["monatssicht"] == 72.6


# ── R-D2 (N-813): jedes Feld aus seiner Quelle ──────────────────────────────


async def test_rd2_netzbezug_ha_dann_mqtt_bleiben_tage_und_monat_aus_dem_kanal(db, monkeypatch, stehende_uhr):
    """Lage A5 (gemessen am HEAD ``f512e9c52`` und im Päckchen C, ``test_mess_c1.py``): PV-Kontrolle über HA, Netzbezug HA → MQTT
    «bisherige Werte bleiben» am 28.10. 12:20. Vorher: Tageswerte Netzbezug an allen Tagen «—», Monat 0,0, aktueller Monat leer —
    der Kanal führte 4,5/21,6/20,925/21,6. Jetzt liest eedc das MQTT-Feld aus seiner Quelle: Tageswerte = Kanal, Monat 71,33."""
    from sqlalchemy.orm.attributes import flag_modified

    from backend.api.routes.aktueller_monat import get_aktueller_monat
    from backend.api.routes.energie_profil.monat import get_monatsauswertung
    from backend.models.anlage import Anlage
    from backend.services.kanal import merken
    from backend.services.kanal.nachfuellen import nachfuellen_anlage
    from backend.tests.test_sensorwechsel_wegb_k_proben import _wechsel
    from sqlalchemy import select

    netz = "sensor.netz"
    v = P.ep(P.START) - 5 * P.STUNDE
    w = await P.mach_welt(db, monkeypatch, {netz: (v, lambda _e: 0.9), P.PVC: (v, lambda _e: 2.0)}, {"pvk": P.PVC},
                          mqtt=False, mqtt_neu=datetime(2026, 10, 28, 12, 20))
    async with w.sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == w.a.id))).scalar_one()
        m = dict(a.sensor_mapping)
        m["basis"] = {**(m.get("basis") or {}), "netzbezug": {"strategie": "sensor", "sensor_id": netz}}
        a.sensor_mapping = m
        flag_modified(a, "sensor_mapping")
    P.frisch(w)
    t = datetime(2026, 10, 28, 12, 20)
    await P.betrieb_bis(w, P.START, t.replace(minute=0))
    P.UHR.stelle(t - timedelta(minutes=2))
    w.mit_mqtt = True
    await _wechsel(w, t, "fortsetzung", fid=P.NETZ_FID, quelle="mqtt_gateway", quell_topic="neu/zaehler/netz")
    ende = datetime(2026, 10, 30, 3)
    await P.betrieb_bis(w, t.replace(minute=0) + timedelta(hours=1), ende)
    await nachfuellen_anlage(w.sitzungen, w.a.id, jetzt=P._FDT.now(), ha_svc=w.svc, nur_vorhandene=True)
    P.frisch(w)
    P.UHR.stelle(ende + timedelta(minutes=20))
    tage = [date(2026, 10, 26) + timedelta(days=i) for i in range(4)]
    assert await P.netz_tage(w, tage) == dict(zip(tage, (4.5, 21.6, 20.925, 21.6)))
    assert await P.kanal_deckung(w, tage[0], tage[-1]) == []
    merken.invalidiere(w.a.id)
    P.frisch(w)
    assert (await get_monatsauswertung(w.a.id, 2026, 10, 10, w.db)).netzbezug_kwh == 71.33
    await w.db.commit()
    merken.invalidiere(w.a.id)
    P.frisch(w)
    assert (await get_aktueller_monat(w.a.id, 2026, 10, w.db)).netzbezug_kwh == 71.33


async def test_rd2_mqtt_wallbox_an_einer_ha_anlage_zeigt_an_kanal_tagen_ihre_zahl(db, monkeypatch, stehende_uhr):
    """S4 «Mischform» (gemessen am Stand v4.3.1 und am HEAD, ``test_mess_d2_s4.py``/``test_mess_c1.py``): PV über HA, Ladung der
    Wallbox über MQTT — die Wallbox stand an allen Tagen «—», der Monat ohne sie. Jetzt an den Kanal-Tagen ihre Zahl (MQTT
    0,9 kWh/h ⇒ 21,6). Am Rand der Welt (26./27.10.) beginnt ihr abgeleiteter Kanal (PV-Anteil) erst mit einem Vorstand
    (benannte Grenze «Weltrand», ``abgeleitet.py`` H-2) — dort bleibt sie «—»; die PV-Felder sind unberührt."""
    monkeypatch.setattr(P, "NETZ_MK", "inv/2/ladung_kwh")
    monkeypatch.setattr(P, "NETZ_FID", "inv_energy_2_ladung_kwh")
    v = P.ep(P.START) - 5 * P.STUNDE
    w = await P.mach_welt(db, monkeypatch, {P.ALT: (v, lambda _e: 0.6), P.PVC: (v, lambda _e: 2.0)},
                          {"pv": P.ALT, "pvk": P.PVC}, mqtt=True)
    ende = datetime(2026, 10, 30, 3)
    await P.betrieb_bis(w, P.START, ende)
    P.UHR.stelle(ende + timedelta(minutes=20))
    tage = [date(2026, 10, 28), date(2026, 10, 29)]
    wb = await P.sichten(w, "wb", tage, (2026, 10))
    assert wb["tage"] == {d: 21.6 for d in tage}
    pvk = await P.sichten(w, "pvk", tage, (2026, 10))
    assert pvk["tage"] == {d: 48.0 for d in tage} and pvk["monatssicht"] == 160.0


async def test_rd2_feld_in_beiden_quellen_zaehlt_einmal(db, monkeypatch, stehende_uhr):
    """Ein Feld, das einen HA-Sensor hat UND MQTT-Stände bekommt (Netzbezug), steht einmal in der Auswahl: ein Schlüssel, ein
    Kanal — der Tag zählt 21,6 (HA 0,9 kWh/h), nicht doppelt; die reine HA-Auswahl bleibt (kein Feld allein über MQTT)."""
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from backend.models.anlage import Anlage
    from backend.models.investition import Investition
    from backend.services.kanal.bilanz_adapter import zaehler_eintraege

    netz = "sensor.netz"
    v = P.ep(P.START) - 5 * P.STUNDE
    w = await P.mach_welt(db, monkeypatch, {netz: (v, lambda _e: 0.9), P.PVC: (v, lambda _e: 2.0)}, {"pvk": P.PVC},
                          mqtt=False)
    async with w.sitzungen() as s:
        a = (await s.execute(select(Anlage).where(Anlage.id == w.a.id))).scalar_one()
        m = dict(a.sensor_mapping)
        m["basis"] = {**(m.get("basis") or {}), "netzbezug": {"strategie": "sensor", "sensor_id": netz}}
        a.sensor_mapping = m
        flag_modified(a, "sensor_mapping")
    P.frisch(w)
    w.mit_mqtt = True                                   # dieselben 0,9 kWh/h kommen zusätzlich als MQTT-Stände an
    await P.betrieb_bis(w, P.START, datetime(2026, 10, 29, 3))
    P.UHR.stelle(datetime(2026, 10, 29, 3, 20))
    tage = [date(2026, 10, 27), date(2026, 10, 28)]
    assert await P.netz_tage(w, tage) == {d: 21.6 for d in tage}
    a = await P.anlage(w)
    invs = {str(i.id): i for i in (await w.db.execute(select(Investition).where(Investition.anlage_id == a.id))).scalars()}
    keys = [e.schluessel for e in await zaehler_eintraege(w.db, a, invs, tage[0])]
    assert keys.count("basis:netzbezug") == 1
