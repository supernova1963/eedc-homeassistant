"""Erfassungs-Stillstand an einem Kanal-Tag (N-799, Bauplan Fassung 3, E-2/E-3/E-8): die Fenster-Lesestelle
``services/kanal/stillstand.py`` und die Marke an den Mischzeilen (``energie_profil/stillstand_marke.py``) — über beide
Lesewege: den Einzeltag ``/stunden`` (``kanal_stunden.stunden_des_tages``) und den Bereich (``stunden_der_kanal_tage`` /
``stunden_der_tage``, die Lesestelle aller Stundenleser).

Datenstand: Achsen-Form M07 (Bilanz, Sonstiges, WP aus Kanälen, HA; 01.06.–03.07.2026, Uhr der Matrix gestellt). Die
Matrix schreibt Zähler in Zehntel-kWh — genau die Lage der Grob-Sperre; ``_fein`` macht die Bilanz-Zähler fein (Δ × 1,00731,
eine 0 bleibt 0). Ein Stillstand entsteht wie in HA: die Zeilen der Stunden ``[beginn, beginn + k)`` tragen den Stand
davor, die Nachtragsstunde ihren eigenen (die Menge der k + 1 Stunden). Jede Sperre und der Speicher-Verwurf haben ihren
Sprengsatz (ohne sie würde die Probe rot). Zeitpunkte in Ortszeit der Prozesszone im Juni/Juli, fern jeder Umstellung
(die Suite fährt auch in ``Pacific/Auckland`` und ``UTC``); die Umstellungstage prüft die Layer-Probe.

Schwesterdateien: test_n799_stillstand_layer.py (die Regel rein), test_kanal_stunden_sichten.py (die Mischzeilen),
test_s5_merken.py (die Speicher je Prozess), test_kanal_lesen.py (die Lese-Schicht).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from backend.core.berechnungen import spannen as sp
from backend.services.energie_profil.kanal_stunden import stunden_der_kanal_tage, stunden_der_tage
from backend.services.kanal import bilanz_leser, lesen, merken, stillstand
from backend.tests import kanal_bilanz_gleichheit as kg

BILANZ = ("basis:einspeisung", "basis:netzbezug", "basis:pv_gesamt", "inv:1:pv_erzeugung_kwh")
WP = "inv:3:stromverbrauch_kwh"
ACHSEN = frozenset({"pv", "einspeisung", "netzbezug"})


@pytest.fixture(autouse=True)
def uhr(monkeypatch):
    """Die Uhr der Leser steht auf der Uhr der Matrix (``kg.JETZT_TS``, 03.07.2026 abends); Speicher leer."""
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)
    merken.leeren()
    yield
    merken.leeren()


def _ts(d: datetime) -> int:
    return int(d.timestamp())


async def _kid(ds, key: str) -> int:
    return (await ds.db.execute(text("SELECT id FROM kanal WHERE anlage_id = :a AND key = :k"),
                                {"a": ds.aid, "k": key})).scalar_one()


async def _fein(ds) -> None:
    for key in BILANZ:
        await ds.db.execute(text("UPDATE kanal_statistik SET sum = sum * 1.00731 WHERE kanal_id = :k"),
                            {"k": await _kid(ds, key)})
    await ds.db.commit()


async def _einfrieren(ds, beginn: datetime, k: int, keys=BILANZ) -> None:
    """HA nach einem Ausfall: die Stunden ``[beginn, beginn + k)`` tragen den Stand der Stunde davor."""
    a = _ts(beginn)
    for key in keys:
        kid = await _kid(ds, key)
        await ds.db.execute(text(
            "UPDATE kanal_statistik SET sum = (SELECT s2.sum FROM kanal_statistik s2 WHERE s2.kanal_id = :kid "
            "AND s2.start_ts = :vor) WHERE kanal_id = :kid AND start_ts >= :a AND start_ts < :b"),
            {"kid": kid, "vor": a - 3600, "a": a, "b": a + k * 3600})
    await ds.db.commit()
    merken.invalidiere(ds.aid, von=beginn.date() - timedelta(days=1))


async def _stunden(ds, tag: date) -> dict[int, object]:
    """``/stunden`` des Tages (Einzeltag-Leseweg)."""
    from backend.api.routes.energie_profil.serien import zeilen_der_stunden_sicht

    return {z.stunde: z for z in (await zeilen_der_stunden_sicht(ds.db, ds.aid, tag))[1]}


async def _bereich(ds, von: date, bis: date) -> dict[date, dict[int, object]]:
    """Die Mischzeilen des Bereichs (``stunden_der_kanal_tage``, Leseweg der Sichten)."""
    tage = [von + timedelta(days=i) for i in range((bis - von).days + 1)]
    return {d: {z.stunde: z for z in zs} for d, zs in (await stunden_der_kanal_tage(ds.db, ds.aid, tage, {})).items()}


def _marken(zeilen: dict[int, object]) -> dict[int, dict]:
    return {h: dict(z.spannen) for h, z in zeilen.items() if z.spannen}


# ── die Lese-Schicht ─────────────────────────────────────────────────────────────────────────────────────────────────

async def test_deltas_stapel_gleich_stunden_stapel():
    """``lesen.deltas_stapel`` liefert dieselben (start_ts, change, spanne) wie ``stunden_stapel`` — auch über den Stand
    vor dem Bereich und eine Lücke."""
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await ds.db.execute(text("DELETE FROM kanal_statistik WHERE kanal_id = :k AND start_ts IN (:a, :b)"),
                            {"k": await _kid(ds, "basis:netzbezug"), "a": _ts(datetime(2026, 6, 5, 3)),
                             "b": _ts(datetime(2026, 6, 5, 4))})
        kanaele = [k for k in (await lesen.kanaele_laden(ds.db, ds.aid, (*BILANZ, WP))).values()]
        von, bis = _ts(datetime(2026, 6, 3)), _ts(datetime(2026, 6, 9))
        schlank = await lesen.deltas_stapel(ds.db, kanaele, von, bis)
        voll = await lesen.stunden_stapel(ds.db, kanaele, von, bis)
    assert set(schlank) == set(voll) and len(schlank) == 5
    for key, st in voll.items():
        assert schlank[key] == [(w.start_ts, w.change, w.spanne) for w in st.werte]
    assert any(sp_ == 3 * 3600 for _t, _d, sp_ in schlank["basis:netzbezug"])


# ── Fenster und Marke ────────────────────────────────────────────────────────────────────────────────────────────────

async def test_ohne_stillstand_keine_marke():
    """Kopie ohne Stillstand: kein Fenster, keine Marke (auch mit den groben Matrix-Zählern)."""
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        assert await stillstand.fenster_im_bereich(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1], mit_gesperrten=True) == []
        await _fein(ds)
        merken.leeren()
        assert await stillstand.fenster_im_bereich(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1], mit_gesperrten=True) == []
        bereich = await _bereich(ds, kg.TAGE[0], kg.TAGE[-1])
    assert all(not _marken(z) for z in bereich.values())


async def test_stillstand_am_tag_beide_lesewege():
    tag = date(2026, 6, 10)
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        vorher = await _stunden(ds, tag)
        await _einfrieren(ds, datetime(2026, 6, 10, 10), 3)
        (f,) = await stillstand.fenster_im_bereich(ds.db, ds.aid, tag, tag)
        einzel = await _stunden(ds, tag)
        bereich = (await _bereich(ds, tag - timedelta(days=2), tag + timedelta(days=2)))[tag]
        lesestelle = {z.stunde: z for z in await stunden_der_tage(ds.db, ds.aid, tag, tag)}
    assert (f.k, f.n, f.nachtrag_ts) == (3, 4, _ts(datetime(2026, 6, 10, 13)))
    # E-2: die WP stand im Fenster (ihr Zähler hat an dem Tag kein Δ) ⇒ sie erbt; Sonstiges lief weiter ⇒ nicht.
    assert f.achsen == ACHSEN | {"waermepumpe"}
    erwartet = {h: {a: 0 for a in f.achsen} for h in (10, 11, 12)} | {13: {a: 4 for a in f.achsen}}
    for zeilen in (einzel, bereich, lesestelle):
        assert _marken(zeilen) == erwartet
        assert all(zeilen[h].ueberschuss_kw is None and zeilen[h].defizit_kw is None for h in range(10, 14))
        assert zeilen[9].ueberschuss_kw is not None
        assert sp.zeile_gebuendelt(zeilen[11], "pv") and sp.zeile_gebuendelt(zeilen[13], "netzbezug")
    # die Menge bleibt, wo HA sie hinschreibt: jede Tagessumme gleich
    for feld in ("pv_kw", "einspeisung_kw", "netzbezug_kw"):
        assert sum(getattr(z, feld) or 0 for z in einzel.values()) == pytest.approx(
            sum(getattr(z, feld) or 0 for z in vorher.values()), abs=0.005)       # je Stunde auf 3 Stellen gerundet
    assert einzel[13].pv_kw == pytest.approx(4 * vorher[13].pv_kw, abs=0.005)


async def test_lauf_ueber_mitternacht_einzeltag_gleich_bereich_und_tagesvergleich():
    """Fenster 10.06. 22:00 … 11.06. 11:00 (k = 13): beide Tage tragen Nullzeilen, die Nachtragszeile n = 14 steht am
    11.06. — Einzeltag ≡ Bereich. Der Tagesvergleich lässt beide Tage aus (E-8: Kandidat 11.06.); Sprengsatz: ohne den
    Kandidaten bleiben sie drin."""
    from backend.services.energie_profil.vergleichstage import tage_ohne_tagesvergleich

    d1, d2 = date(2026, 6, 10), date(2026, 6, 11)
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        await _einfrieren(ds, datetime(2026, 6, 10, 22), 13)
        einzel = {d: await _stunden(ds, d) for d in (d1, d2)}
        bereich = await _bereich(ds, d1 - timedelta(days=3), d2 + timedelta(days=3))
        aus = await tage_ohne_tagesvergleich(ds.db, ds.aid, "pv", von=d1 - timedelta(days=3), bis=d2 + timedelta(days=3))
        merken.leeren()
        with pytest.MonkeyPatch.context() as mp:
            async def _keine(*_a, **_k):
                return {}
            mp.setattr(stillstand, "erster_tag_der_fenster_ueber_mitternacht", _keine)
            ohne = await tage_ohne_tagesvergleich(ds.db, ds.aid, "pv", von=d1 - timedelta(days=3),
                                                  bis=d2 + timedelta(days=3))
    for d in (d1, d2):
        assert _marken(einzel[d]) == _marken(bereich[d])
    assert set(_marken(einzel[d1])) == {22, 23}
    assert set(_marken(einzel[d2])) == set(range(12)) and einzel[d2][11].spannen["pv"] == 14
    assert {d1, d2} <= aus
    assert not {d1, d2} & ohne


async def test_drei_tage_lauf_mittlere_tage_ganz_null():
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        await _einfrieren(ds, datetime(2026, 6, 13, 10), 72)
        mitte = date(2026, 6, 14)
        einzel = await _stunden(ds, mitte)
        bereich = await _bereich(ds, date(2026, 6, 12), date(2026, 6, 17))
        (f,) = await stillstand.fenster_im_bereich(ds.db, ds.aid, mitte, mitte)
    assert f.k == 72
    for zeilen in (einzel, bereich[mitte], bereich[date(2026, 6, 15)]):
        assert len(zeilen) == 24 and all(set(z.spannen.values()) == {0} for z in zeilen.values())
    assert bereich[date(2026, 6, 16)][10].spannen["pv"] == 73


async def test_treffer_gleich_kaltlauf_nach_dem_nachtrag():
    """Ein warmer Prozess (Monate gemerkt) sieht nach dem Schreiben des Stillstands dasselbe wie ein kalter — das
    Schreiben verwirft die Monate (``merken.invalidiere`` wie ``schreiber``). Sprengsatz: ohne das Verwerfen bliebe der
    warme Prozess beim alten Stand."""
    tag = date(2026, 6, 20)
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        assert await stillstand.fenster_im_bereich(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1]) == []
        await _einfrieren(ds, datetime(2026, 6, 20, 10), 3)
        warm = await stillstand.fenster_im_bereich(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1])
        warm_tag = _marken(await _stunden(ds, tag))
        merken.leeren()
        kalt = await stillstand.fenster_im_bereich(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1])
        assert len(stillstand.FENSTER) > 0
        merken.leeren()
        assert _marken(await _stunden(ds, tag)) == warm_tag
        # Generation (Investition/Kanal geändert, ohne Tag): ebenso verworfen
        merken.invalidiere(ds.aid)
        assert await stillstand.fenster_im_bereich(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1]) == kalt
        # Sprengsatz
        await _fein(ds)                    # andere Zahlen, aber KEIN Verwerfen
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(stillstand.FENSTER, "entferne", lambda *_a: None)
            await _einfrieren(ds, datetime(2026, 6, 24, 10), 2)
            veraltet = await stillstand.fenster_im_bereich(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1])
        merken.leeren()
        frisch = await stillstand.fenster_im_bereich(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1])
    assert warm == kalt and len(kalt) == 1 and set(warm_tag) == {10, 11, 12, 13}
    assert veraltet != frisch and len(frisch) == 2


async def test_laufender_tag():
    """03.07. (Uhr der Matrix 04.07. 00:30 — der Tag ist noch nicht abgeschlossen, letzte Zeile 23:00): ein Stillstand
    mit Nachtrag am laufenden Tag trägt die Marke; ein Stillstand, der noch andauert (kein Nachtrag), keine."""
    tag = date(2026, 7, 3)
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        await _einfrieren(ds, datetime(2026, 7, 3, 10), 3)
        mit = _marken(await _stunden(ds, tag))
        letzte = (await ds.db.execute(text("SELECT MAX(start_ts) FROM kanal_statistik WHERE kanal_id = :k"),
                                      {"k": await _kid(ds, "basis:netzbezug")})).scalar_one()
        assert datetime.fromtimestamp(letzte) == datetime(2026, 7, 3, 23)
        assert not merken.abgeschlossen(tag, kg.JETZT_TS)
        await _einfrieren(ds, datetime(2026, 7, 3, 20), 4)          # 20 … 23 Uhr, die letzte Zeile steht noch
        andauernd = _marken(await _stunden(ds, tag))
    assert set(mit) == {10, 11, 12, 13}
    assert andauernd == mit


async def test_luecke_und_stillstand_am_selben_tag():
    """Lücke (Netzbezug 05:00/06:00 ohne Zeile ⇒ 07:00 n = 3) und Stillstand 10:00 … 13:00 am 22.06.: die Lücke bleibt
    ein Lücken-Bündel (nur Netzbezug, n = 3), der Stillstand bekommt seine Marke."""
    tag = date(2026, 6, 22)
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        await ds.db.execute(text("DELETE FROM kanal_statistik WHERE kanal_id = :k AND start_ts IN (:a, :b)"),
                            {"k": await _kid(ds, "basis:netzbezug"), "a": _ts(datetime(2026, 6, 22, 5)),
                             "b": _ts(datetime(2026, 6, 22, 6))})
        await _einfrieren(ds, datetime(2026, 6, 22, 10), 3)
        einzel = await _stunden(ds, tag)
        bereich = (await _bereich(ds, tag, tag))[tag]
    for zeilen in (einzel, bereich):
        m = _marken(zeilen)
        assert m[7] == {"netzbezug": 3}
        assert set(m) == {7, 10, 11, 12, 13} and m[13]["pv"] == 4


async def test_grob_sperre_mit_sprengsatz(monkeypatch):
    """Die Matrix-Zähler (Zehntel-kWh) sind grob: der Stillstand wird erkannt, aber nicht markiert. Sprengsatz: ohne die
    Grob-Sperre trägt der Tag die Marke."""
    tag = date(2026, 6, 10)
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _einfrieren(ds, datetime(2026, 6, 10, 10), 3)
        (f,) = await stillstand.fenster_im_bereich(ds.db, ds.aid, tag, tag, mit_gesperrten=True)
        ohne = _marken(await _stunden(ds, tag))
        monkeypatch.setattr(sp, "GROB_MIN_POSITIVE", 10 ** 9)
        merken.leeren()
        mit = _marken(await _stunden(ds, tag))
    assert f.sperre == sp.SPERRE_GROB and not ohne
    assert set(mit) == {10, 11, 12, 13}


async def test_haeufigkeits_sperre_mit_sprengsatz(monkeypatch):
    """Tägliches Einfrieren an 20 Tagen (09.06. … 28.06., je 10–13 Uhr): die ersten fünf Tage tragen die Marke, die
    übrigen nicht (die Sperre blickt nur zurück). Sprengsatz: ohne die Häufigkeits-Sperre trägt jeder Tag sie."""
    tage = [date(2026, 6, 9) + timedelta(days=i) for i in range(20)]
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        for d in tage:
            await _einfrieren(ds, datetime(d.year, d.month, d.day, 10), 3)
        alle = await stillstand.fenster_im_bereich(ds.db, ds.aid, tage[0], tage[-1], mit_gesperrten=True)
        ohne = await _bereich(ds, tage[0], tage[-1])
        monkeypatch.setattr(sp, "HAEUFIG_MAX_FENSTER", 10 ** 9)
        merken.leeren()
        mit = await _bereich(ds, tage[0], tage[-1])
    assert len(alle) == 20 and [f.sperre for f in alle] == [None] * 5 + [sp.SPERRE_HAEUFIG] * 15
    assert all(set(_marken(ohne[d])) == {10, 11, 12, 13} for d in tage[:5])
    assert all(not _marken(ohne[d]) for d in tage[5:])
    assert all(set(_marken(mit[d])) == {10, 11, 12, 13} for d in tage)


async def test_speicher_ohne_zaehler_mit_sprengsatz(monkeypatch):
    """Ein aktiver Speicher ohne Ladung/Entladung-Zähler: keine Erkennung (Vorbedingung E-1). Sprengsatz: ohne die
    Bedingung träfe der Stillstand."""
    from backend.models.investition import Investition

    tag = date(2026, 6, 10)
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        ds.db.add(Investition(anlage_id=ds.aid, typ="speicher", bezeichnung="Speicher ohne Zähler",
                              anschaffungsdatum=date(2026, 1, 1), aktiv=True, parameter={"kapazitaet_kwh": 10}))
        await ds.db.commit()
        await _einfrieren(ds, datetime(2026, 6, 10, 10), 3)
        assert await stillstand.fenster_im_bereich(ds.db, ds.aid, tag, tag, mit_gesperrten=True) == []
        monkeypatch.setattr(stillstand, "_speicher_aktiv", lambda _invs: (lambda _ts: False))
        merken.leeren()
        assert len(await stillstand.fenster_im_bereich(ds.db, ds.aid, tag, tag)) == 1


async def test_pausierender_zaehler_bereich_kalt_gleich_einzeltag_gleich_warm():
    """Nachmessung F2: pausiert ein Bilanz-Zähler (``inv:1:pv_erzeugung_kwh`` ab 12.06. ohne Zeile), hing das Fenster an
    der Abfragereihenfolge. «erfasst» blickt jetzt nur zurück (eine Zeile in den 30 Tagen vor dem Laufbeginn): der
    Stillstand am 10.06. ist ein Fenster, der am 20.06. keines (der pausierende Zähler ist noch erfasst und hat keine
    Zeile) — gleich ob der Bereich kalt, nach dem Einzeltag oder warm gefragt wird."""
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        await ds.db.execute(text("DELETE FROM kanal_statistik WHERE kanal_id = :k AND start_ts >= :a"),
                            {"k": await _kid(ds, "inv:1:pv_erzeugung_kwh"), "a": _ts(datetime(2026, 6, 12))})
        await ds.db.commit()
        await _einfrieren(ds, datetime(2026, 6, 10, 10), 3)
        await _einfrieren(ds, datetime(2026, 6, 20, 10), 3, keys=BILANZ[:3])
        merken.leeren()
        bereich_kalt = await stillstand.fenster_im_bereich(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1], mit_gesperrten=True)
        merken.leeren()
        einzel = [await stillstand.fenster_im_bereich(ds.db, ds.aid, d, d, mit_gesperrten=True)
                  for d in (date(2026, 6, 20), date(2026, 6, 10))]
        bereich_warm = await stillstand.fenster_im_bereich(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1], mit_gesperrten=True)
    assert [datetime.fromtimestamp(f.von_ts) for f in bereich_kalt] == [datetime(2026, 6, 10, 10)]
    assert bereich_warm == bereich_kalt
    assert einzel == [[], bereich_kalt]
