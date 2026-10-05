"""Proben der Lese-Schicht (HA-Bauform E3, Auftrag Punkte 1, 2, 7) — ``services/kanal/lesen.py``.

Kunst-Kanäle im Schema des Produkts (In-Memory-SQLite der ``db``-Fixture), Zeiten absolut (UTC-Stunden ab
``T0``) — die Schicht kennt keine Zone; die Fenster-Helfer haben ihre Zonen-Proben in ``test_kanal_lesen_fenster.py``.
Keine Probe liest die Uhr: ``jetzt`` ist überall gesetzt.

Je Probe der Fall des Auftrags: Δ gegen Handrechnung · Naht zweier Quellen · ``stand`` über eine Quellgrenze
(Minimalfall der E1-Nachmessung 1002,4 → 2,7 · 3,0) · Kanal beginnt mitten im Zeitraum · Lücke im Zeitraum ·
dünne Punkte (Tag ohne Wert) · laufender Zeitraum mit Schreibverzug · ``mittel`` · Abfrage-Budget.
Die Sprengsätze stehen im Bericht E3.

Schwesterdateien: test_kanal_lesen_fenster.py, test_kanal_quellenwahl.py, test_kanal_lesen_waechter.py,
test_kanal_symmetrie.py (Fenster-Helfer == Bestand über ``aggregate_day``).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy import event, insert

from backend.models.anlage import Anlage
from backend.models.kanal import (
    ART_MEAN,
    ART_STAND,
    ART_SUM,
    FAMILIE_MITSCHRIFT,
    FAMILIE_SPIEGEL,
    Kanal,
    KanalQuelle,
    KanalStatistik,
)
from backend.services.kanal.lesen import (
    GRUND_BEGINNT_NACH_VON,
    GRUND_ENDET_VOR_BIS,
    GRUND_FEINER_ALS_SPANNE,
    GRUND_KEINE_ZEILE,
    SCHREIBVERZUG_S,
    mittel,
    mittel_stapel,
    reihe,
    reihe_stapel,
    soll_ende,
    stunden,
    stunden_stapel,
    zeitraum,
    zeitraum_stapel,
)

H = 3600
T0 = 1_767_571_200            # 2026-01-05 00:00 UTC
JETZT = 4_102_444_800         # 2100-01-01 — alle Zeiträume abgeschlossen, wo nicht anders gesetzt


def h(n: int) -> int:
    return T0 + n * H


async def _anlage(db) -> int:
    a = Anlage(anlagenname="Lese-Probe", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    return a.id


async def _kanal(db, aid: int, key: str, art: str, zeilen, *, einheit: str = "kWh", quellen=None,
                 familie: str = FAMILIE_SPIEGEL) -> Kanal:
    """``zeilen``: ``[(start_ts, wert)]`` — bei ``mean`` ``(start_ts, mean, min, max)``. ``quellen``:
    ``[(gueltig_ab, offset)]`` (Standard: eine Quelle ab der ersten Zeile, ``offset`` 0)."""
    k = Kanal(anlage_id=aid, key=key, art=art, einheit=einheit)
    db.add(k)
    await db.flush()
    for i, (ab, off) in enumerate(quellen or [(zeilen[0][0] if zeilen else T0, 0.0)]):
        db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=ab, familie=familie, statistic_id=f"sensor.q{i}", offset=off))
    reihen = []
    for z in zeilen:
        if art == ART_MEAN:
            reihen.append({"kanal_id": k.id, "start_ts": z[0], "sum": None, "state": None, "mean": z[1],
                           "min": z[2], "max": z[3], "familie": familie})
        else:
            reihen.append({"kanal_id": k.id, "start_ts": z[0], "sum": z[1] if art == ART_SUM else None,
                           "state": z[1], "mean": None, "min": None, "max": None, "familie": familie})
    if reihen:
        await db.execute(insert(KanalStatistik), reihen)
    await db.flush()
    return k


# ── Δ gegen Handrechnung ────────────────────────────────────────────────────


async def test_delta_ist_stand_vor_bis_minus_stand_vor_von_handrechnung(db):
    aid = await _anlage(db)
    werte = [10.0, 11.5, 13.0, 13.0, 16.25, 17.0, 20.5, 21.0, 22.75, 23.0]
    k = await _kanal(db, aid, "basis:einspeisung", ART_SUM, [(h(i), w) for i, w in enumerate(werte)])
    z = await zeitraum(db, k, h(2), h(6), jetzt=JETZT)
    # Stand vor h(2) = Zeile h(1) (Ende 02:00) = 11,5 · Stand vor h(6) = Zeile h(5) = 17,0 ⇒ 5,5
    assert z.delta == pytest.approx(17.0 - 11.5)
    assert (z.voll, z.grund, z.laufend, z.teil_delta) == (True, None, False, None)
    assert (z.gedeckt_von, z.gedeckt_bis, z.rand_spanne) == (h(2), h(6), H)
    assert (z.wert_von, z.wert_bis) == (11.5, 17.0)
    # Σ HA-change der Zeilen h(2)…h(5) = 1,5 + 0 + 3,25 + 0,75
    st = await stunden(db, k, h(2), h(6), jetzt=JETZT)
    assert [w.change for w in st.werte] == pytest.approx([1.5, 0.0, 3.25, 0.75])
    assert sum(w.change for w in st.werte) == pytest.approx(z.delta)
    # reihe = zeitraum je Intervall, Σ der Intervalle = Δ über alles
    r = await reihe(db, k, [h(2), h(4), h(6)], jetzt=JETZT)
    assert [x.delta for x in r] == pytest.approx([1.5, 4.0])


async def test_mittelwert_kanal_hat_kein_delta_und_grenzen_werden_geprueft(db):
    aid = await _anlage(db)
    m = await _kanal(db, aid, "basis:netzbezug_w", ART_MEAN, [(h(0), 1.0, 0.5, 1.5)], einheit="W")
    with pytest.raises(ValueError):
        await zeitraum(db, m, h(0), h(1), jetzt=JETZT)
    k = await _kanal(db, aid, "basis:einspeisung", ART_SUM, [(h(0), 1.0)])
    with pytest.raises(ValueError):
        await reihe(db, k, [h(3), h(1)], jetzt=JETZT)
    with pytest.raises(ValueError):
        await mittel(db, k, h(0), h(1), jetzt=JETZT)


# ── Naht zweier Quellen (offset) ────────────────────────────────────────────


async def test_naht_zweier_quellen_offset_im_zeitraum(db):
    """Sensortausch bei h(6): alte Summe 100…105, neue Rohsumme beginnt bei 2,0; ``offset`` 104,0 (Stand der alten
    Quelle zur letzten Stunde minus Anker des neuen Sensors, wie ``schreiber._neue_spiegel_quelle``)."""
    aid = await _anlage(db)
    alt = [(h(i), 100.0 + i) for i in range(6)]
    neu = [(h(6), 2.0), (h(7), 3.5), (h(8), 4.0), (h(9), 6.0)]
    k = await _kanal(db, aid, "basis:netzbezug", ART_SUM, alt + neu, quellen=[(h(0), 0.0), (h(6), 104.0)])
    z = await zeitraum(db, k, h(3), h(9), jetzt=JETZT)
    # Stand vor h(3) = 102,0 (alt) · Stand vor h(9) = 4,0 + 104,0 = 108,0 ⇒ 6,0
    assert z.delta == pytest.approx(108.0 - 102.0)
    assert (z.wert_von, z.wert_bis) == pytest.approx((102.0, 108.0))
    st = await stunden(db, k, h(5), h(8), jetzt=JETZT)
    assert [w.change for w in st.werte] == pytest.approx([1.0, 1.0, 1.5])   # über die Naht stetig
    assert [w.familie for w in st.werte] == [FAMILIE_SPIEGEL] * 3


async def test_stand_ueber_eine_quellgrenze_minimalfall_e1_nachmessung(db):
    """Gaszähler 1002,4 m³ → neuer Zähler (2,7 · 3,0), Versatz 1000,0. Der Stand ist ``state`` roh (die Zahl auf dem
    Zähler, F-58); ``offset`` überbrückt nur die Differenz über die Quellgrenze (Bauplan §3a, Nachtrag 06.10.)."""
    aid = await _anlage(db)
    k = await _kanal(db, aid, "inv:7:zaehlerstand", ART_STAND, [(h(5), 1002.4), (h(6), 2.7), (h(7), 3.0)],
                     einheit="m³", quellen=[(h(5), 0.0), (h(6), 1000.0)])
    z = await zeitraum(db, k, h(6), h(8), jetzt=JETZT)
    assert z.delta == pytest.approx(0.6)                      # (3,0 + 1000) − (1002,4 + 0)
    assert (z.wert_von, z.wert_bis) == pytest.approx((1002.4, 3.0))   # roh — 1003,0 stünde auf keinem Zähler
    st = await stunden(db, k, h(6), h(8), jetzt=JETZT)
    assert [w.change for w in st.werte] == pytest.approx([0.3, 0.3])
    assert [w.wert for w in st.werte] == pytest.approx([2.7, 3.0])


# ── Abdeckung (a): Kanal beginnt mitten im Zeitraum ─────────────────────────


async def test_kanal_beginnt_mitten_im_zeitraum_nicht_gedeckt_kein_stiller_teilwert(db):
    aid = await _anlage(db)
    k = await _kanal(db, aid, "basis:einspeisung", ART_SUM, [(h(i), 0.5 * (i - 9)) for i in range(10, 20)])
    z = await zeitraum(db, k, h(0), h(20), jetzt=JETZT)
    assert (z.voll, z.grund, z.delta) == (False, GRUND_BEGINNT_NACH_VON, None)
    # Teilsumme mit Marke: zwischen dem ersten (Ende h(10)) und dem letzten Stand (Ende h(20)).
    assert z.teil_delta == pytest.approx(5.0 - 0.5)
    assert (z.gedeckt_von, z.gedeckt_bis) == (h(11), h(20))
    # Die erste Zeile genau AM Anfang deckt auch nicht: ein Stand VOR `von` fehlt (HA nennt dort still 0-basiert).
    assert (await zeitraum(db, k, h(10), h(20), jetzt=JETZT)).grund == GRUND_BEGINNT_NACH_VON
    assert (await zeitraum(db, k, h(11), h(20), jetzt=JETZT)).voll
    assert (await zeitraum(db, k, h(0), h(5), jetzt=JETZT)).grund == GRUND_KEINE_ZEILE
    st = await stunden(db, k, h(0), h(20), jetzt=JETZT)
    assert (st.voll, st.grund, st.werte[0].change) == (False, GRUND_BEGINNT_NACH_VON, None)


async def test_kanal_endet_vor_bis_nicht_gedeckt(db):
    aid = await _anlage(db)
    k = await _kanal(db, aid, "basis:einspeisung", ART_SUM, [(h(i), float(i)) for i in range(0, 10)])
    z = await zeitraum(db, k, h(5), h(20), jetzt=JETZT)
    assert (z.voll, z.grund, z.teil_delta, z.gedeckt_bis) == (False, GRUND_ENDET_VOR_BIS, 9.0 - 4.0, h(10))
    assert (await zeitraum(db, k, h(5), h(10), jetzt=JETZT)).voll     # letzte Zeile = letzte Stunde vor `bis`


# ── Lücke im Zeitraum, Menge in der Folgestunde ─────────────────────────────


async def test_luecke_im_zeitraum_gedeckt_spanne_gemeldet_menge_in_folgestunde(db):
    """HA hat h(5)…h(7) nicht geschrieben (Ausfall); der Zähler lief weiter — Zeile h(8) trägt vier Stunden. Die Lücke
    liegt im Inneren: ``zeitraum`` meldet nur die Spannen über die Ränder (lückenlos), die Lücke nennt ``stunden``
    (Entscheid Master L1, Option A)."""
    aid = await _anlage(db)
    zeilen = [(h(i), float(i)) for i in range(-2, 24) if i not in (5, 6, 7)]
    k = await _kanal(db, aid, "basis:einspeisung", ART_SUM, zeilen)
    z = await zeitraum(db, k, h(0), h(24), jetzt=JETZT)
    assert (z.voll, z.delta, z.rand_spanne) == (True, pytest.approx(24.0), H)
    st = await stunden(db, k, h(0), h(24), jetzt=JETZT)
    assert [w.start_ts for w in st.werte if w.start_ts in (h(4), h(5), h(6), h(7), h(8))] == [h(4), h(8)]
    folge = next(w for w in st.werte if w.start_ts == h(8))
    assert (folge.change, folge.spanne) == (pytest.approx(4.0), 4 * H)
    assert st.groesste_spanne == 4 * H
    # Ein Zeitraum NUR um die Lücke ist feiner als die Spanne, in die er fällt ⇒ kein Wert.
    eng = await zeitraum(db, k, h(5), h(7), jetzt=JETZT)
    assert (eng.voll, eng.grund, eng.delta) == (False, GRUND_FEINER_ALS_SPANNE, None)


async def test_luecke_ueber_den_rand_menge_im_naechsten_zeitraum_wie_ha(db):
    """Ausfall h(22)…h(25) über die Grenze h(24): wie HA steht die Menge in der Folgestunde (h(26), nächster
    Zeitraum). Beide Tage sind gedeckt (die Spanne ist kürzer als ein Tag) und nennen sie."""
    aid = await _anlage(db)
    zeilen = [(h(i), float(i)) for i in range(-2, 50) if i not in (22, 23, 24, 25)]
    k = await _kanal(db, aid, "basis:einspeisung", ART_SUM, zeilen)
    r = await reihe(db, k, [h(0), h(24), h(48)], jetzt=JETZT)
    assert [x.voll for x in r] == [True, True]
    assert [x.delta for x in r] == pytest.approx([21.0 - (-1.0), 47.0 - 21.0])
    assert [x.rand_spanne for x in r] == [5 * H, 5 * H]
    assert r[0].gedeckt_bis == h(22) and r[1].gedeckt_von == h(22)


# ── dünne Punkte: Monat richtig, Tag kein Wert ──────────────────────────────


async def test_duenne_punkte_monats_delta_richtig_tages_delta_kein_wert(db):
    """Ein Punkt je Monat (Ablesung/Import), genau auf der Monatsgrenze: der Monat hat seinen Δ, ein Tag darin
    ist feiner als die Spanne, in die er fällt — kein Wert, auch nicht der Tag, an dessen Ende der Punkt liegt."""
    aid = await _anlage(db)
    grenzen = [T0 + d * 86400 for d in (0, 31, 59, 90)]           # vier Monatspunkte (Stand gilt am Grenz-Zeitpunkt)
    k = await _kanal(db, aid, "basis:netzbezug", ART_SUM,
                     [(g - H, w) for g, w in zip(grenzen, (1000.0, 1310.0, 1590.0, 1900.0))])
    r = await reihe(db, k, grenzen, jetzt=JETZT)
    assert [x.delta for x in r] == pytest.approx([310.0, 280.0, 310.0])
    assert all(x.voll for x in r)
    for von in (grenzen[1] + 9 * 86400, grenzen[2] - 86400):
        tag = await zeitraum(db, k, von, von + 86400, jetzt=JETZT)
        assert (tag.voll, tag.grund, tag.delta) == (False, GRUND_FEINER_ALS_SPANNE, None), von
        assert tag.rand_spanne == 28 * 86400


# ── laufender Zeitraum mit Schreibverzug ────────────────────────────────────


async def test_laufender_zeitraum_mit_schreibverzug_bleibt_kanal(db):
    """Der :05-Lauf schreibt die Zeile, die zur vollen Stunde H endet, um H:05. Um H:03 ist sie noch nicht da —
    der laufende Tag bleibt trotzdem gedeckt (die Quelle wechselte sonst jede Stunde für einige Minuten). Auch EIN
    verpasster Lauf ist toleriert; zwei in Folge nicht."""
    aid = await _anlage(db)
    tag_von, tag_bis = h(0), h(24)
    hh = h(14)                                             # volle Stunde H = 14:00
    k = await _kanal(db, aid, "basis:einspeisung", ART_SUM, [(h(i), float(i)) for i in range(-3, 13)])
    # Zeilen bis start_ts h(12) ⇒ letzter Stand gilt um 13:00; die Zeile „bis 14:00" kommt um 14:05.
    z = await zeitraum(db, k, tag_von, tag_bis, jetzt=hh + 3 * 60)
    assert (z.voll, z.laufend, z.delta, z.gedeckt_bis) == (True, True, pytest.approx(13.0), h(13))
    # Ein verpasster Lauf (der 13:05-Lauf hat die Zeile „bis 13:00" nicht bekommen, der letzte Stand gilt um
    # 12:00; der 14:05-Lauf holt sie nach): um 14:03 noch gedeckt.
    k2 = await _kanal(db, aid, "basis:netzbezug", ART_SUM, [(h(i), float(i)) for i in range(-3, 12)])
    assert (await zeitraum(db, k2, tag_von, tag_bis, jetzt=hh + 3 * 60)).voll
    # Zwei verpasste Läufe (um 15:15 fehlen die Stände 14:00 und 15:00, der letzte gilt um 13:00): nicht gedeckt.
    z2 = await zeitraum(db, k, tag_von, tag_bis, jetzt=hh + H + 15 * 60)
    assert (z2.voll, z2.grund) == (False, GRUND_ENDET_VOR_BIS)
    assert soll_ende(hh + 3 * 60) == h(12) and soll_ende(hh + 10 * 60) == h(13) and SCHREIBVERZUG_S == 4200
    # Der abgeschlossene Tag braucht dagegen die Zeile der letzten Stunde.
    assert (await zeitraum(db, k, tag_von, h(14), jetzt=JETZT)).grund == GRUND_ENDET_VOR_BIS


async def test_laufender_zeitraum_meldet_die_spanne_am_soll_ende(db):
    """HA fiel 10:00–12:00 aus und schreibt wieder (Zeile 12:00, vom 13:05-Lauf geschrieben); um 13:10 liegt das
    Soll-Ende (12:00) in dieser Lücke — sie ist der Rand des laufenden Zeitraums und wird gemeldet. Gedeckt bleibt er."""
    aid = await _anlage(db)
    k = await _kanal(db, aid, "basis:einspeisung", ART_SUM, [(h(i), float(i)) for i in range(-3, 13) if i not in (10, 11)])
    z = await zeitraum(db, k, h(0), h(24), jetzt=h(13) + 10 * 60)
    assert (z.voll, z.laufend, z.rand_spanne, z.delta) == (True, True, 3 * H, pytest.approx(13.0))
    z_spaeter = await zeitraum(db, k, h(0), h(24), jetzt=h(14) + 10 * 60)   # Soll-Ende 13:00 = Stand ⇒ lückenlos
    assert z_spaeter.rand_spanne == H


async def test_zeitraum_ganz_in_einer_luecke_am_soll_ende_nennt_keinen_wert(db):
    """Minimalfall der Nachmessung E3 (2c): Zeilen h3 und h5, h4 fehlt; Zeitraum [h4, h5) beginnt genau am Soll-Ende
    (jetzt = h6 + 8 min ⇒ Soll-Ende h4). Er liegt ganz in der Lücke — kein Wert, zu jedem Zeitpunkt; vorher nannte er
    von h6:05 bis h6:10 still Δ 0."""
    aid = await _anlage(db)
    k = await _kanal(db, aid, "basis:einspeisung", ART_SUM, [(h(3), 3.0), (h(5), 5.0)])
    for jetzt in (h(6) + 8 * 60, h(6) + 10 * 60, JETZT):
        z = await zeitraum(db, k, h(4), h(5), jetzt=jetzt)
        assert (z.voll, z.grund, z.delta, z.rand_spanne) == (False, GRUND_FEINER_ALS_SPANNE, None, 2 * H), jetzt


async def test_laufender_zeitraum_ohne_faellige_stunde(db):
    """Um 00:02 hat der neue Tag noch keine fällige Stunde: Δ 0, gedeckt (nichts fehlt, was da sein müsste)."""
    aid = await _anlage(db)
    k = await _kanal(db, aid, "basis:einspeisung", ART_SUM, [(h(i), float(i)) for i in range(-5, -1)])
    z = await zeitraum(db, k, h(0), h(24), jetzt=h(0) + 120)
    assert (z.voll, z.laufend, z.delta) == (True, True, 0.0)


# ── mittel ──────────────────────────────────────────────────────────────────


async def test_mittel_wie_ha_in_der_einheit_des_kanals(db):
    aid = await _anlage(db)
    zeilen = [(h(i), m, m - 1.0, m + 2.0) for i, m in enumerate((10.0, 20.0, 30.0, 40.0, 50.0, 60.0))]
    k = await _kanal(db, aid, "basis:aussentemperatur_c", ART_MEAN, zeilen, einheit="°C")
    m = await mittel(db, k, h(1), h(5), jetzt=JETZT)
    # Stunden h(1)…h(4): Mittel der Mittel 35, Minimum der Minima 19, Maximum der Maxima 52
    assert (m.mean, m.min, m.max, m.einheit, m.stunden) == (35.0, 19.0, 52.0, "°C", 4)
    assert (m.voll, m.rand_spanne, m.gedeckt_von, m.gedeckt_bis) == (True, H, h(1), h(5))
    teil = await mittel(db, k, h(-3), h(3), jetzt=JETZT)
    assert (teil.voll, teil.grund, teil.mean, teil.teil_mean) == (False, GRUND_BEGINNT_NACH_VON, None, 20.0)


async def test_mittel_mit_luecke_meldet_spanne_und_mittelt_die_gemessenen_stunden(db):
    aid = await _anlage(db)
    zeilen = [(h(i), float(i), float(i), float(i)) for i in range(0, 24) if i not in (10, 11)]
    k = await _kanal(db, aid, "inv:2:soc", ART_MEAN, zeilen, einheit="%")
    m = (await mittel_stapel(db, [k], h(0), h(24), jetzt=JETZT))[k.key]
    gemessen = [float(i) for i in range(24) if i not in (10, 11)]
    # die Lücke liegt innen: Ränder lückenlos (3600); erkennbar ist sie an 22 statt 24 gemessenen Stunden
    assert (m.voll, m.stunden, m.rand_spanne) == (True, 22, H)
    assert m.mean == pytest.approx(sum(gemessen) / len(gemessen))
    assert (m.min, m.max) == (0.0, 23.0)
    # gleich NACH der Lücke: die erste Stunde des Zeitraums ist gemessen — die fehlenden Stunden davor berühren ihn nicht
    danach = await mittel(db, k, h(12), h(14), jetzt=JETZT)
    assert (danach.voll, danach.mean, danach.rand_spanne) == (True, 12.5, H)
    loch = await mittel(db, k, h(10), h(12), jetzt=JETZT)
    assert (loch.voll, loch.grund, loch.stunden) == (False, GRUND_FEINER_ALS_SPANNE, 0)


# ── Stapel = einzeln ────────────────────────────────────────────────────────


async def test_stapel_liefert_dasselbe_wie_einzeln(db):
    aid = await _anlage(db)
    a = await _kanal(db, aid, "basis:einspeisung", ART_SUM, [(h(i), 2.0 * i) for i in range(0, 30)])
    b = await _kanal(db, aid, "basis:netzbezug", ART_SUM, [(h(i), 3.0 * i) for i in range(5, 30) if i != 17],
                     familie=FAMILIE_MITSCHRIFT)
    c = await _kanal(db, aid, "inv:3:zaehlerstand", ART_STAND, [(h(i), 1000.0 + i) for i in range(0, 30)],
                     einheit="m³")
    grenzen = [h(1), h(6), h(12), h(20), h(29)]
    stapel = await reihe_stapel(db, [a, b, c], grenzen, jetzt=JETZT)
    for k in (a, b, c):
        assert stapel[k.key] == await reihe(db, k, grenzen, jetzt=JETZT), k.key
    zs = await zeitraum_stapel(db, [a, b, c], h(6), h(20), jetzt=JETZT)
    assert zs[b.key].rand_spanne == H and zs[c.key].delta == pytest.approx(14.0)
    ss = await stunden_stapel(db, [a, b, c], h(6), h(20), jetzt=JETZT)
    for k in (a, b, c):
        assert ss[k.key] == await stunden(db, k, h(6), h(20), jetzt=JETZT)
    assert {w.familie for w in ss[b.key].werte} == {FAMILIE_MITSCHRIFT}


# ── Abfrage-Budget ──────────────────────────────────────────────────────────


class _Zaehler:
    """Zählt die SQL-Anweisungen, die über die Verbindung der Sitzung gehen."""

    def __init__(self, db):
        self.n = 0
        self._engine = db.bind.sync_engine

    def _hook(self, *_a, **_k):
        self.n += 1

    def __enter__(self):
        self.n = 0
        event.listen(self._engine, "before_cursor_execute", self._hook)
        return self

    def __exit__(self, *_a):
        event.remove(self._engine, "before_cursor_execute", self._hook)


async def test_abfrage_budget_haengt_nicht_an_der_laenge_und_nicht_an_der_kanalzahl(db):
    """Jeder Stapel-Aufruf ist EINE Anweisung — ``zeitraum`` über einen Tag, einen Monat, zwölf Jahre; ``reihe`` über
    2, 13, 145 Grenzen; Stapel über 1 und 3 Kanäle. Die Daten tragen Lücken."""
    aid = await _anlage(db)
    n = 12 * 365 * 24
    zeilen = [(h(i), 0.5 * i) for i in range(-1, n) if i % 1000 not in (1, 2, 3)]
    a = await _kanal(db, aid, "basis:einspeisung", ART_SUM, zeilen)
    b = await _kanal(db, aid, "basis:netzbezug", ART_SUM, zeilen[::7])
    c = await _kanal(db, aid, "inv:3:zaehlerstand", ART_STAND, zeilen[::24], einheit="m³")
    m = await _kanal(db, aid, "basis:aussentemperatur_c", ART_MEAN, [(t, w, w, w) for t, w in zeilen[::3]],
                     einheit="°C")

    async def zaehle(coro) -> int:
        with _Zaehler(db) as z:
            await coro
        return z.n

    tag, monat, alles = (h(0), h(24)), (h(0), h(31 * 24)), (h(0), h(n - 1))
    zr = {name: await zaehle(zeitraum(db, a, *w, jetzt=JETZT)) for name, w in
          (("tag", tag), ("monat", monat), ("zwoelf_jahre", alles))}
    assert zr == {"tag": 1, "monat": 1, "zwoelf_jahre": 1}, zr
    assert await zaehle(zeitraum_stapel(db, [a, b, c], *alles, jetzt=JETZT)) == 1
    rg = {g: await zaehle(reihe_stapel(db, [a, b, c], [h(i * (n // g)) for i in range(g)], jetzt=JETZT))
          for g in (2, 13, 145)}
    assert rg == {2: 1, 13: 1, 145: 1}, rg
    st = {name: await zaehle(stunden(db, a, *w, jetzt=JETZT)) for name, w in (("tag", tag), ("monat", monat))}
    assert st == {"tag": 1, "monat": 1}, st
    assert await zaehle(stunden_stapel(db, [a, b, c], *tag, jetzt=JETZT)) == 1
    mt = {name: await zaehle(mittel(db, m, *w, jetzt=JETZT)) for name, w in (("tag", tag), ("zwoelf_jahre", alles))}
    assert mt == {"tag": 1, "zwoelf_jahre": 1}, mt
    # und die Zahlen stimmen trotz Lücken: Δ über alles = letzter Stand − Stand vor h(0)
    z = await zeitraum(db, a, *alles, jetzt=JETZT)
    assert z.voll and z.delta == pytest.approx(0.5 * (n - 2) - 0.5 * (-1)) and z.rand_spanne == H


async def test_zeitraum_und_reihe_lesen_nur_randstaende_keine_zeile_dazwischen(db):
    """Die Zahl der GELESENEN Zeilen hängt nicht von der Länge ab (Entscheid Master L1) — zweifach geprüft, ohne Uhr:

    * der Abfrageplan der Randstände kennt kein ``SCAN`` auf ``kanal_statistik``/``kanal_quelle``, nur ``SEARCH``
      über den Index (``json_each`` ist die Eingabeliste, kein Tabellen-Scan);
    * die Zahl der SQLite-VM-Schritte (``set_progress_handler`` mit Schritt 1 — ein deterministischer Zähler,
      keine Zeitmessung) ist für einen Tag und für zwölf Jahre gleich (Spielraum 1,5×; ein Lauf über die Zeilen
      dazwischen bräuchte das Tausendfache)."""
    from sqlalchemy import text

    from backend.services.kanal import lesen

    aid = await _anlage(db)
    n = 12 * 365 * 24
    a = await _kanal(db, aid, "basis:einspeisung", ART_SUM, [(h(i), 0.5 * i) for i in range(-1, n)])
    plan = [r[-1] for r in (await db.execute(text("EXPLAIN QUERY PLAN " + lesen._RAND_SQL), {
        "kanaele": f"[[{a.id}, \"sum\"]]", "grenzen": f"[{h(0)}, {h(24)}]"})).all()]
    gescannt = [z for z in plan if z.startswith("SCAN") and "json_each" not in z]
    assert not gescannt, plan
    assert any("SEARCH" in z and "kanal_statistik" in z for z in plan), plan

    roh = (await (await db.connection()).get_raw_connection()).driver_connection
    schritte = [0]

    def _zaehle():
        schritte[0] += 1
        return 0

    async def vm(coro) -> int:
        schritte[0] = 0
        await roh.set_progress_handler(_zaehle, 1)
        try:
            await coro
        finally:
            await roh.set_progress_handler(None, 1)
        return schritte[0]

    tag = await vm(zeitraum(db, a, h(0), h(24), jetzt=JETZT))
    jahre = await vm(zeitraum(db, a, h(0), h(n - 1), jetzt=JETZT))
    reihe_kurz = await vm(reihe(db, a, [h(0), h(24), h(48)], jetzt=JETZT))
    reihe_lang = await vm(reihe(db, a, [h(0), h(n // 2), h(n - 1)], jetzt=JETZT))
    assert 0 < tag and jahre <= 1.5 * tag, (tag, jahre)
    assert 0 < reihe_kurz and reihe_lang <= 1.5 * reihe_kurz, (reihe_kurz, reihe_lang)
    assert n > 1000 * 1.5    # ein Scan der 105 120 Zeilen läge weit über dem Spielraum


def test_t0_ist_eine_volle_utc_stunde():
    assert T0 % H == 0 and datetime.fromtimestamp(T0, timezone.utc).hour == 0
