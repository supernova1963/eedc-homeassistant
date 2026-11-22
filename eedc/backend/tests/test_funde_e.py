"""Fund-Päckchen E (22.11.2026) — Repo-Tests.

**E1 (N-818): Lückentag der Gerätegruppen wie in der Bilanz.** Hat ein Gerätekanal über einen abgeschlossenen Tag hinweg keine
Zeile (Spanne länger als der Tag), fiel seine Gruppe (E-Mobilität, Sonstiges, Wärmepumpe) an diesem Tag auf den Bestand
(``kanal/geraete_leser.waehle_gruppe`` streng ``voll``), während die Bilanz den Lückentag aus dem Kanal zählt
(``bilanz_leser._gedeckt``, «Lückentag wie HA»). An der Naht Bestandstag ↔ Kanal-Tag zählte die Stunde 23–24 Uhr in keinem
bzw. in beiden Tagen — gemessen an der Produktiv-Kopie (Wallbox März 2025 184,65 statt 188,12 kWh = HA). Seit E1 wählen die
Tages-Leser der Gerätegruppen mit derselben Regel am selben Ort (``bilanz_leser._gedeckt``, ``lueckentag=True``): der Tag in der
Lücke trägt 0, die Menge der Lücke steht in der ersten Stunde danach, wie in Home Assistant.

Welt: ``test_sensorwechsel_wegb_loeschen_proben`` (HA-Attrappe, stehende Uhr, echte Stundenläufe); die Lücke entsteht, indem die
HA-Attrappe die Zeilen eines Zeitraums nicht führt (wie ``test_funde_d::test_rd1_zaehlerluecke_mitten_in_der_quelle_wie_bisher``).

Schwesterdateien: test_funde_d.py (Zählerlücke mitten in der Quelle an der Bilanz), test_funde_c.py,
test_kanal_lesen.py (Abdeckungsregel der Lese-Schicht), test_sensorwechsel_wegb_loeschen_proben.py (Welt).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

import backend.tests.test_sensorwechsel_wegb_loeschen_proben as P
from backend.tests.test_sensorwechsel_wegb_loeschen_proben import stehende_uhr  # noqa: F401 — Fixture

OKT = (2026, 10)
NOV = (2026, 11)


def _tagesbeginn(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time())


def _wb_rate(e: int) -> float:
    """Wallbox 1,32 kWh/h; in der Stunde 23–24 Uhr je Tag verschieden (2,0 … 3,5) — eine Naht mit fehlender oder doppelter
    Stunde verschiebt dann den Monat (bei gleicher Rate höben sich beide auf)."""
    t = datetime.fromtimestamp(e)
    return 2.0 + 0.5 * (t.day % 4) if t.hour == 23 else 1.32


def _ha_luecke(w, eid: str, von: datetime, bis: datetime) -> None:
    """Die HA-Attrappe führt für ``eid`` keine Zeile mit Beginn in ``[von, bis]`` (die Menge steht in der Zeile danach)."""
    echt = w.ha_bis

    def ha_bis(b: int) -> None:
        echt(b)
        with w.svc._engine.begin() as c:
            c.execute(text("delete from statistics where metadata_id = :m and start_ts between :a and :b"),
                      {"m": w.mids[eid], "a": P.ep(von), "b": P.ep(bis)})
    w.ha_bis = ha_bis


async def _welt_wb(db, monkeypatch, luecke: tuple[datetime, datetime] | None, *, bis: datetime = datetime(2026, 11, 2, 3)):
    v = P.ep(P.START) - 5 * P.STUNDE
    serien = {P.ALT: (v, lambda _e: 0.6), P.PVC: (v, lambda _e: 2.0), P.WB: (v, _wb_rate)}
    w = await P.mach_welt(db, monkeypatch, serien, {"pv": P.ALT, "pvk": P.PVC, "wb": P.WB}, mqtt=False)
    if luecke is not None:
        _ha_luecke(w, P.WB, *luecke)
    await P.betrieb_bis(w, P.START, bis)
    P.UHR.stelle(bis + timedelta(minutes=20))
    return w


def _ha_tag(w, eid: str, d: date):
    """HAs Kalendertag (Σ ``change`` der Zeilen mit Beginn im Tag); ein Tag ohne Zeile mitten in einer laufenden Statistik
    zeigt in HA 0 (keine Änderung) — ``ha_summe`` nennt dort ``None``."""
    wert = w.ha_summe(eid, _tagesbeginn(d), _tagesbeginn(d + timedelta(days=1)))
    return 0.0 if wert is None else wert


def _ha_monat(w, eid: str, jm: tuple[int, int]):
    von = datetime(jm[0], jm[1], 1)
    return w.ha_summe(eid, von, datetime(jm[0] + (jm[1] == 12), jm[1] % 12 + 1, 1))


def _weltrand_wb(w) -> float:
    """Weltrand (benannte Grenze, ``_pruefe_soll``): am 26.10. beginnt der abgeleitete Kanal «PV-Anteil der Heimladung» ohne
    Vorstand — die E-Mob-Gruppe liest den Tag aus dem Bestand, die Stunde 26.10. 23–24 Uhr fehlt der Monatssicht."""
    return w.ha_summe(P.WB, datetime(2026, 10, 26, 23), datetime(2026, 10, 27))


async def _pruefe_wb_wie_ha(w, tage: list[date], monate: list[tuple[int, int]]) -> dict:
    bild = {}
    for jm in monate:
        s = await P.sichten(w, "wb", tage, jm)
        bild[jm] = s
        ha = _ha_monat(w, P.WB, jm)
        sicht = P.r3(ha - _weltrand_wb(w)) if jm == OKT else ha
        assert (s["monatssicht"], s["aus_ha_laden"]) == (sicht, ha), (jm, s, ha)
        for d in tage:
            if (d.year, d.month) == jm:
                assert s["tage"][d] == _ha_tag(w, P.WB, d), (d, s["tage"][d], _ha_tag(w, P.WB, d))
    return bild


# ── E1: Lückentag der Gerätegruppen ─────────────────────────────────────────────────────────────────────────────────


async def test_e1_lueckentag_wallbox_mitten_im_monat_tag_und_monat_wie_ha(db, monkeypatch, stehende_uhr):
    """HA führt für die Wallbox vom 28.10. 06:00 bis 30.10. 05:00 keine Zeile: der 29.10. liegt ganz in der Lücke. Tage und
    Monat = HA-Kalendertag bzw. -monat; der Tag in der Lücke trägt 0, die Menge der Lücke steht am 30.10."""
    w = await _welt_wb(db, monkeypatch, (datetime(2026, 10, 28, 6), datetime(2026, 10, 30, 5)))
    tage = [date(2026, 10, 27) + timedelta(days=i) for i in range(6)]
    bild = await _pruefe_wb_wie_ha(w, tage, [OKT])
    assert bild[OKT]["tage"][date(2026, 10, 29)] == 0.0
    assert await P.kanal_deckung(w, tage[0], tage[-1]) == []


async def test_e1_lueckentag_am_monatsrand(db, monkeypatch, stehende_uhr):
    """Lücke vom 30.10. 20:00 bis 01.11. 03:00: der 31.10. liegt ganz in der Lücke, die Menge steht am 01.11. — Oktober und
    November je = HA-Kalendermonat."""
    w = await _welt_wb(db, monkeypatch, (datetime(2026, 10, 30, 20), datetime(2026, 11, 1, 3)),
                       bis=datetime(2026, 11, 3, 3))
    tage = [date(2026, 10, 29) + timedelta(days=i) for i in range(5)]
    await _pruefe_wb_wie_ha(w, tage, [OKT, NOV])


async def test_e1_luecke_ueber_mehrere_tage(db, monkeypatch, stehende_uhr):
    """Lücke vom 28.10. 06:00 bis 31.10. 05:00: zwei ganze Tage in der Lücke (29./30.10. je 0), die Menge am 31.10."""
    w = await _welt_wb(db, monkeypatch, (datetime(2026, 10, 28, 6), datetime(2026, 10, 31, 5)))
    tage = [date(2026, 10, 27) + timedelta(days=i) for i in range(6)]
    bild = await _pruefe_wb_wie_ha(w, tage, [OKT])
    assert [bild[OKT]["tage"][date(2026, 10, d)] for d in (29, 30)] == [0.0, 0.0]


async def test_e1_gegenprobe_bilanz_und_geraet_ohne_luecke_unveraendert(db, monkeypatch, stehende_uhr):
    """Die Bilanz (PV) zeigt mit und ohne Lücke an der Wallbox dieselben Tage; eine Wallbox ohne Lücke zeigt je Tag HA."""
    tage = [date(2026, 10, 27) + timedelta(days=i) for i in range(6)]
    w = await _welt_wb(db, monkeypatch, (datetime(2026, 10, 28, 6), datetime(2026, 10, 30, 5)))
    assert (await P.sichten(w, "pv", tage, OKT))["tage"] == {d: 14.4 for d in tage}
    assert (await P.sichten(w, "pvk", tage, OKT))["tage"] == {d: 48.0 for d in tage}


async def test_e1_geraet_ohne_luecke_unveraendert(db, monkeypatch, stehende_uhr):
    """Gegenprobe: ohne Lücke zeigt die Wallbox je Tag und im Monat HA (wie vor E1)."""
    tage = [date(2026, 10, 27) + timedelta(days=i) for i in range(6)]
    w = await _welt_wb(db, monkeypatch, None)
    await _pruefe_wb_wie_ha(w, tage, [OKT])
    assert (await P.sichten(w, "pv", tage, OKT))["tage"] == {d: 14.4 for d in tage}


WPS, WPH = "sensor.wp_strom", "sensor.wp_waerme"


async def test_e1_lueckentag_waermepumpe_tag_wie_ha_auch_ohne_zeile(db, monkeypatch, stehende_uhr):
    """Wärmepumpe (Strom 0,8, Wärme 2,4 kWh/h), HA führt den Strom vom 28.10. 06:00 bis 30.10. 05:00 nicht: die WP-Gruppe
    kommt an allen Tagen aus den Kanälen; der Tag in der Lücke zeigt 0 (Σ Stunden ohne Zeile, wie die Bilanz), nicht «—»."""
    import json

    from sqlalchemy.orm.attributes import flag_modified

    from backend.models.investition import Investition
    from backend.services.energie_profil.kanal_stunden import kanal_gruppen_der_tage, komponenten_der_tage
    from backend.services.kanal import merken

    v = P.ep(P.START) - 5 * P.STUNDE
    serien = {P.ALT: (v, lambda _e: 0.6), P.PVC: (v, lambda _e: 2.0), WPS: (v, lambda _e: 0.8), WPH: (v, lambda _e: 2.4)}
    w = await P.mach_welt(db, monkeypatch, serien, {"pv": P.ALT, "pvk": P.PVC}, mqtt=False)
    db.add(Investition(id=4, anlage_id=w.a.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1)))
    a = await P.anlage(w)
    m = json.loads(json.dumps(a.sensor_mapping))
    m["investitionen"]["4"] = {"felder": {"stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": WPS},
                                          "heizenergie_kwh": {"strategie": "sensor", "sensor_id": WPH}}}
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    P.frisch(w)
    _ha_luecke(w, WPS, datetime(2026, 10, 28, 6), datetime(2026, 10, 30, 5))
    bis = datetime(2026, 11, 2, 3)
    await P.betrieb_bis(w, P.START, bis)
    P.UHR.stelle(bis + timedelta(minutes=20))
    tage = [date(2026, 10, d) for d in range(27, 32)]
    P.frisch(w)
    merken.invalidiere(w.a.id)
    komp = await komponenten_der_tage(w.db, w.a.id, tage[0], tage[-1])
    gruppen = await kanal_gruppen_der_tage(w.db, w.a.id, tage[0], tage[-1])
    await w.db.commit()
    assert all("wp" in gruppen[d] for d in tage), gruppen
    assert {d: P.r3(komp[d]["waermepumpe_4"]) for d in tage} == {d: _ha_tag(w, WPS, d) for d in tage}
    assert P.r3(komp[date(2026, 10, 29)]["waermepumpe_4"]) == 0.0


async def test_e1_mqtt_wallbox_mit_luecke_zaehlt_wie_die_quelle(db, monkeypatch, stehende_uhr):
    """MQTT-Wallbox (eigene Summe aus den Rohständen, 1,32 kWh/h ab 26.10. 19:00), keine Rohstände vom 28.10. 06:00 bis 30.10.
    05:59. Gemessen am HEAD ``819a6fc92``: 28.–30.10. «—» (E-Mob-Gruppe Bestand, der Bestand kennt das MQTT-Feld an diesen Tagen
    nicht). Seit E1 derselbe Weg wie an HA: der Tag in der Lücke 0, die Menge der Lücke im ersten Stand danach — nichts
    erfunden, nichts verworfen (Σ der drei Tage = Zuwachs der Rohstände 28.10. 00:00 … 31.10. 00:00)."""
    import json

    from sqlalchemy.orm.attributes import flag_modified

    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot

    beginn, luecke = datetime(2026, 10, 26, 19), (datetime(2026, 10, 28, 6), datetime(2026, 10, 30, 5, 59))

    def stand(t: datetime) -> float:
        return round(500.0 + 1.32 * (t - beginn).total_seconds() / 3600, 6)

    v = P.ep(P.START) - 5 * P.STUNDE
    w = await P.mach_welt(db, monkeypatch, {P.ALT: (v, lambda _e: 0.6), P.PVC: (v, lambda _e: 2.0)},
                          {"pv": P.ALT, "pvk": P.PVC}, mqtt=False)
    a = await P.anlage(w)
    m = json.loads(json.dumps(a.sensor_mapping))
    m["quellen"] = {"inv_energy_2_ladung_kwh": {"quelle": "mqtt_inbound_standard"}}
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    P.frisch(w)
    echt = P.lauf_05

    async def lauf(w_, h):
        for mi in (-45, -30, -15, 0):
            t = h + timedelta(minutes=mi)
            if t >= beginn and not luecke[0] <= t <= luecke[1]:
                w_.db.add(MqttEnergySnapshot(anlage_id=w_.a.id, timestamp=t, energy_key="inv/2/ladung_kwh",
                                             value_kwh=stand(t)))
        await w_.db.commit()
        await echt(w_, h)
    monkeypatch.setattr(P, "lauf_05", lauf)
    bis = datetime(2026, 11, 2, 3)
    await P.betrieb_bis(w, P.START, bis)
    P.UHR.stelle(bis + timedelta(minutes=20))
    tage = [date(2026, 10, d) for d in range(28, 32)]
    s = await P.sichten(w, "wb", tage, OKT)
    assert [s["tage"][d] for d in tage] == [7.92, 0.0, 87.12, 31.68], s["tage"]
    zuwachs = stand(datetime(2026, 10, 31)) - stand(datetime(2026, 10, 28))
    assert sum(s["tage"][d] for d in tage[:3]) == pytest.approx(zuwachs, abs=1e-6)


# ── E2 (N-815): Drift-Vergleich am Kalendertag ──────────────────────────────────────────────────────────────────────
#
# Welt der Messung B-M2 (``golden-master/funde-b-2026-11-22/test_mess_m2.py``): Wärmepumpe (Strom 2,5 kWh/h, Wärme 7,5),
# Wallbox (1,32), zwei PV-Felder; alle Statistiken beginnen um 19:00 des ersten Welttags. Gemessen am HEAD ``819a6fc92``:
# «WP: 3 Tag(e) weichen … ab (2026-10-27: 67,5 → 60,0)» — der erste Tag der Statistik und die beiden Tage um die Nachtstunde
# 27.10. 23–24 Uhr (10,0 kWh); Tag und HA-Kalendertag sind gleich, der Vergleichswert las [Vortag 23:00, 23:00).


def _wp_zuordnen(w, db):
    import json

    from sqlalchemy.orm.attributes import flag_modified

    from backend.models.investition import Investition

    async def _los():
        db.add(Investition(id=4, anlage_id=w.a.id, typ="waermepumpe", bezeichnung="WP", anschaffungsdatum=date(2024, 1, 1)))
        a = await P.anlage(w)
        m = json.loads(json.dumps(a.sensor_mapping))
        m["investitionen"]["4"]["felder"]["heizenergie_kwh"] = {"strategie": "sensor", "sensor_id": WPH}
        a.sensor_mapping = m
        flag_modified(a, "sensor_mapping")
        await db.commit()
        P.frisch(w)
    return _los()


async def _welt_wp(db, monkeypatch, wp_fn, *, start: datetime = datetime(2026, 10, 26, 19), von: datetime = P.START,
                   bis: datetime = datetime(2026, 10, 30, 3), wb_fn=lambda _e: 1.32, luecke_wp=None):
    monkeypatch.setitem(P.FELDER, "wp", ("4", "stromverbrauch_kwh", "inv:4:stromverbrauch_kwh", "waermepumpe_4"))
    v = P.ep(start)
    serien = {P.ALT: (v, lambda _e: 0.6), P.PVC: (v, lambda _e: 2.0), P.WB: (v, wb_fn), WPS: (v, wp_fn),
              WPH: (v, lambda _e: 7.5)}
    w = await P.mach_welt(db, monkeypatch, serien, {"pv": P.ALT, "pvk": P.PVC, "wb": P.WB, "wp": WPS}, mqtt=False)
    await _wp_zuordnen(w, db)
    if luecke_wp is not None:
        _ha_luecke(w, WPS, *luecke_wp)
    await P.betrieb_bis(w, von, bis)
    P.UHR.stelle(bis + timedelta(minutes=20))
    return w


def _nacht(*stunden: datetime, wert: float = 10.0, sonst: float = 2.5):
    nacht = {P.ep(s) for s in stunden}
    return lambda e: wert if e in nacht else sonst


async def _drift_komponente(w) -> list[str]:
    from backend.services.kanal import merken

    merken.invalidiere(w.a.id)
    return (await P.befunde(w)).get("drift_komponente", [])


async def _spiegel_plus(w, key: str, ab: datetime, plus: float) -> None:
    """Der Spiegel trägt ab ``ab`` eine Summe, die HA nicht führt (N-790 «Spiegel veraltet nach ‹Summe anpassen›»)."""
    from backend.services.kanal import merken

    await w.db.execute(text("update kanal_statistik set sum = sum + :p where start_ts >= :t and kanal_id = "
                            "(select id from kanal where key = :k and anlage_id = :a)"),
                       {"p": plus, "t": P.ep(ab), "k": key, "a": w.a.id})
    await w.db.commit()
    merken.invalidiere(w.a.id)


async def test_e2_nachtlauf_und_erster_tag_der_statistik_kein_befund(db, monkeypatch, stehende_uhr):
    """Nachtlauf (27.10. 23–24 Uhr 10,0 kWh) und erster Tag der Statistik (26.10. ab 19:00): eedc zeigt je Tag HAs
    Kalendertag, der Vergleich nimmt denselben — kein Befund (am HEAD drei Tage)."""
    w = await _welt_wp(db, monkeypatch, _nacht(datetime(2026, 10, 27, 23)))
    tage = [date(2026, 10, d) for d in (26, 27, 28, 29)]
    s = await P.sichten(w, "wp", tage, OKT)
    assert {d: s["tage"][d] for d in tage} == {d: _ha_tag(w, WPS, d) for d in tage}
    assert (s["tage"][date(2026, 10, 27)], s["tage"][date(2026, 10, 28)]) == (67.5, 60.0)
    assert await _drift_komponente(w) == []


async def test_e2_echter_fehler_am_kanal_tag_bleibt_befund_mit_handgriff(db, monkeypatch, stehende_uhr):
    """N-790: der Spiegel der Wärmepumpe trägt am 28.10. ab 12:00 10 kWh mehr als HA — der Kanal-Tag zeigt 70,0, HAs
    Kalendertag 60,0: Befund für genau diesen Tag, mit «Aus Home Assistant neu übernehmen»."""
    w = await _welt_wp(db, monkeypatch, _nacht(datetime(2026, 10, 27, 23)))
    await _spiegel_plus(w, "inv:4:stromverbrauch_kwh", datetime(2026, 10, 28, 12), 10.0)
    (zeile,) = await _drift_komponente(w)
    assert zeile.startswith("WP: 1 Tag(e)") and "2026-10-28: 70,0 → 60,0 kWh" in zeile, zeile
    assert "„Aus Home Assistant neu übernehmen“" in zeile


async def test_e2_bestandstag_und_gemischter_tag(db, monkeypatch, stehende_uhr):
    """Der Spiegel des WP-Stroms endet am 27.10. um 12:00 (Quelle endet ⇒ die WP-Gruppe liest 27.–29.10. aus dem Bestand:
    beide Seiten im Fenster wie bisher), die E-Mobilität an denselben Tagen aus den Kanälen mit einem Nachtlauf der Wallbox
    (27.10. 23–24 Uhr 10,0 kWh): die Wallbox vergleicht am Kalendertag (kein Befund), die Wärmepumpe im Fenster — eine
    falsche Tageszeile am 28.10. bleibt Befund."""
    w = await _welt_wp(db, monkeypatch, lambda _e: 2.5, wb_fn=_nacht(datetime(2026, 10, 27, 23), sonst=1.32))
    await db.execute(text("delete from kanal_statistik where start_ts >= :t and kanal_id = "
                          "(select id from kanal where key = 'inv:4:stromverbrauch_kwh')"),
                     {"t": P.ep(datetime(2026, 10, 27, 12))})
    await db.commit()
    for d in (26, 27, 28, 29):
        await P.aggregiere(w, datetime(2026, 10, 30, 3, 20), date(2026, 10, d))
    from backend.services.energie_profil.kanal_stunden import kanal_gruppen_der_tage
    from backend.services.kanal import merken

    merken.invalidiere(w.a.id)
    gruppen = await kanal_gruppen_der_tage(db, w.a.id, date(2026, 10, 27), date(2026, 10, 29))
    await db.commit()
    assert all("emob" in gruppen[d] and "wp" not in gruppen[d] for d in gruppen), gruppen
    assert await _drift_komponente(w) == []
    await db.execute(text("update tages_zusammenfassung set komponenten_kwh = json_set(komponenten_kwh, "
                          "'$.waermepumpe_4', 30.0) where datum = '2026-10-28'"))
    await db.commit()
    (zeile,) = await _drift_komponente(w)
    assert zeile.startswith("WP: 1 Tag(e)") and "2026-10-28: 30,0 → 60,0 kWh" in zeile, zeile


async def test_e2_randstunde_fehlt_in_ha_kein_vergleich(db, monkeypatch, stehende_uhr):
    """HA führt die Zeile 27.10. 23:00 der Wärmepumpe nicht (ihre Menge steht in der Zeile 28.10. 00:00): für den 27. und den
    28.10. ist eine Randstunde nicht bekannt — dort wird nicht verglichen (kein Ersatzwert). Derselbe Spiegel-Fehler am 28.
    bleibt deshalb still, am 29. ist er Befund."""
    w = await _welt_wp(db, monkeypatch, lambda _e: 2.5,
                       luecke_wp=(datetime(2026, 10, 27, 23), datetime(2026, 10, 27, 23)))
    await _spiegel_plus(w, "inv:4:stromverbrauch_kwh", datetime(2026, 10, 28, 12), 10.0)
    await _spiegel_plus(w, "inv:4:stromverbrauch_kwh", datetime(2026, 10, 29, 12), 10.0)
    (zeile,) = await _drift_komponente(w)
    assert zeile.startswith("WP: 1 Tag(e)") and "2026-10-29: 70,0 → 60,0 kWh" in zeile, zeile


async def test_e2_letzter_tag_gestern_mit_einem_read_von_heute(db, monkeypatch, stehende_uhr):
    """Nachtlauf am letzten geprüften Tag (29.10. 23–24 Uhr, heute 30.10.): seine Randstunde liegt im Read von heute — EIN
    zusätzlicher Read je Lauf, kein Befund."""
    import backend.services.snapshot.lts_aggregator as lts
    from backend.services.daten_checker import DatenChecker
    from backend.services.kanal import merken

    w = await _welt_wp(db, monkeypatch, _nacht(datetime(2026, 10, 29, 23)))
    echt = lts.get_komponenten_tageskwh_lts
    gelesen: list[date] = []

    async def _gezaehlt(anlage, invs_by_id, datum, **kw):
        gelesen.append(datum)
        return await echt(anlage, invs_by_id, datum, **kw)
    monkeypatch.setattr(lts, "get_komponenten_tageskwh_lts", _gezaehlt)
    P.frisch(w)
    merken.invalidiere(w.a.id)
    erg = await DatenChecker(db)._check_datenquelle_drift(await P.anlage(w))
    await db.rollback()
    assert [e.code for e in erg if e.code != "drift_ok" and "WP" in e.meldung] == []
    assert gelesen.count(date(2026, 10, 30)) == 1 and len(gelesen) == len(set(gelesen)), gelesen


async def test_e2_kanal_tag_vor_einer_luecke_der_tageszeilen_liest_den_folgetag_einmal(db, monkeypatch, stehende_uhr):
    """Entscheid Master H-E2 (a): der 29.10. hat keine Tageszeile (die Schleife liest ihn nicht) — für den Kanal-Tag 28.10.
    liest die Prüfung den 29.10. einmal nach; ein echter Spiegel-Fehler am 28.10. bleibt Befund (N-790/N-791). Reads: je
    Tageszeile einer (26.–28.10.) und der Folgetag 29.10. genau einmal; heute (30.10.) nicht — gestern ist keine Tageszeile."""
    import backend.services.snapshot.lts_aggregator as lts
    from backend.services.daten_checker import DatenChecker
    from backend.services.kanal import merken

    w = await _welt_wp(db, monkeypatch, _nacht(datetime(2026, 10, 27, 23)))
    await _spiegel_plus(w, "inv:4:stromverbrauch_kwh", datetime(2026, 10, 28, 12), 10.0)
    await db.execute(text("delete from tages_zusammenfassung where datum = '2026-10-29'"))
    await db.commit()
    echt = lts.get_komponenten_tageskwh_lts
    gelesen: list[date] = []

    async def _gezaehlt(anlage, invs_by_id, datum, **kw):
        gelesen.append(datum)
        return await echt(anlage, invs_by_id, datum, **kw)
    monkeypatch.setattr(lts, "get_komponenten_tageskwh_lts", _gezaehlt)
    P.frisch(w)
    merken.invalidiere(w.a.id)
    erg = await DatenChecker(db)._check_datenquelle_drift(await P.anlage(w))
    await db.rollback()
    (zeile,) = [e.meldung for e in erg if "weichen von HA-Statistics ab" in e.meldung]
    assert zeile.startswith("WP: 1 Tag(e)") and "2026-10-28: 70,0 → 60,0 kWh" in zeile, zeile
    assert sorted(gelesen) == [date(2026, 10, d) for d in (26, 27, 28, 29)], gelesen


@pytest.mark.parametrize("fall", ["herbst_25h", "fruehjahr_23h"])
async def test_e2_zeitumstellung(db, monkeypatch, stehende_uhr, fall):
    """Umstellungstag mit 25 bzw. 23 Stunden (Europe/Berlin 25.10.2026 / 29.03.2026) und ein Nachtlauf am Vortag: Tag =
    HAs Kalendertag, kein Befund. In anderen Zeitzonen ist es ein gewöhnlicher Tag — dieselben Aussagen gelten."""
    tag = date(2026, 10, 25) if fall == "herbst_25h" else date(2026, 3, 29)
    vortag = tag - timedelta(days=1)
    w = await _welt_wp(db, monkeypatch, _nacht(datetime.combine(vortag, datetime.min.time()).replace(hour=23)),
                       start=datetime.combine(vortag - timedelta(days=1), datetime.min.time()).replace(hour=19),
                       von=datetime.combine(vortag, datetime.min.time()),
                       bis=datetime.combine(tag + timedelta(days=2), datetime.min.time()).replace(hour=3))
    tage = [vortag, tag, tag + timedelta(days=1)]
    s = await P.sichten(w, "wp", tage, (tag.year, tag.month))
    assert {d: s["tage"][d] for d in tage} == {d: _ha_tag(w, WPS, d) for d in tage}
    stunden = (P.ep(_tagesbeginn(tag + timedelta(days=1))) - P.ep(_tagesbeginn(tag))) // P.STUNDE   # Berlin: 25 bzw. 23
    assert s["tage"][tag] == round(2.5 * stunden, 3)
    assert await _drift_komponente(w) == []
