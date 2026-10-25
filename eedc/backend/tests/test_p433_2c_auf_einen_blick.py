"""P-433-2c «Auf einen Blick nach Mockup» — die zwei Backend-Zugaben der Karte im Hub-Überblick Wärmepumpe.

* **C-1:** ``WpGeraetZeile.jaz_zaehler_kwh/jaz_nenner_kwh`` — Zähler und Nenner, aus denen der Layer ``jaz`` gebildet
  hat (ungerundet, nur mit Zahl). Eine Rechenstelle (``waerme_klima_block.geraete_zeilen``) ⇒ Tag, Monat und Jahr.
* **C-2:** ``WpGeraetZeile.betrieb_stunden`` — Stunden je Betriebsart des Tages aus der Betriebsart-Mitschrift
  (Layer ``core/berechnungen/betriebsstunden.py``, Tagesleser ``kanal_stunden.wp_betriebsart_anteile_je_stunde``,
  Phase ``tag._mit_betrieb_stunden``); nur am Tag, Monat ``None``.

Fixtures aus ``test_p433_3_s3_tagessicht.py`` (Wärme-Anlage im Backward-Raster, Kanal-Zeilen) und
``test_p433_3_s2_heizstab_zusatzheizung.py``/``test_r2_je_funktion.py`` (Monat).
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from backend.core.berechnungen.betriebsstunden import BETRIEBSARTEN_MIT_STUNDEN, stunden_je_betriebsart
from backend.core.betriebsmodus import AUS, BETRIEBSMODUS_KANON, HEIZEN, KUEHLEN, UNBESTIMMT, WARMWASSER
from backend.models.kanal import ART_MEAN
from backend.services.kanal.katalog import modus_kanal_key
from backend.tests.test_p433_3_s3_tagessicht import DATUM, T0, _anlage_waerme, _kanal, _ts

H = 3600


# ═══ C-2 Layer ═══════════════════════════════════════════════════════════════

def test_layer_summe_und_rundung():
    anteile = {h: {HEIZEN: 1.0, WARMWASSER: 0.0, AUS: 0.0} for h in range(9)}
    anteile[9] = {HEIZEN: 0.4, WARMWASSER: 0.6, AUS: 0.0}
    anteile[10] = {HEIZEN: 0.0, WARMWASSER: 1.0, AUS: 0.0}
    anteile[11] = {HEIZEN: 0.0, WARMWASSER: 0.0, AUS: 1.0}
    assert stunden_je_betriebsart(anteile) == {HEIZEN: 9.4, WARMWASSER: 1.6}


def test_layer_filter_nur_betriebsarten_in_lese_reihenfolge():
    """``aus``/``unbestimmt`` sind kein Betrieb; die Reihenfolge ist die der Karte, nicht die der Eingabe."""
    r = stunden_je_betriebsart({0: {UNBESTIMMT: 1.0, KUEHLEN: 0.25, AUS: 0.5, "lueften": 0.25, HEIZEN: 0.0}})
    assert list(r) == [HEIZEN, KUEHLEN, "lueften"]
    assert r == {HEIZEN: 0.0, KUEHLEN: 0.2, "lueften": 0.2}
    assert set(BETRIEBSARTEN_MIT_STUNDEN) == set(BETRIEBSMODUS_KANON) - {AUS, UNBESTIMMT}


def test_layer_leer_ist_none_gemessene_null_bleibt():
    assert stunden_je_betriebsart({}) is None
    assert stunden_je_betriebsart({0: {AUS: 1.0}, 1: {UNBESTIMMT: 1.0}}) is None, "nur aus/unbestimmt ⇒ keine Zeile"
    assert stunden_je_betriebsart({0: {HEIZEN: 0.0, AUS: 1.0}}) == {HEIZEN: 0.0}, "gemessen nicht geheizt ⇒ 0, nicht None"


def test_layer_herbst_doppelstunde_zaehlt_beide_zeilen():
    """Die Schlüssel sind je Stunde eindeutig (``start_ts``) — zwei reale Stunden auf derselben Wanduhr zählen beide."""
    ts = 1_793_000_000
    assert stunden_je_betriebsart({ts: {HEIZEN: 1.0}, ts + H: {HEIZEN: 1.0}}) == {HEIZEN: 2.0}


# ═══ C-2 Leser und Route ═════════════════════════════════════════════════════

def _anteile_bestandstag() -> dict[int, dict[str, float]]:
    """Mitschrift im Beginn-Raster ``[H, H+1)`` von Vortag 23:00 bis D 23:00 (eine Zeile mehr als der Bestandstag):
    Zeile Vortag 23:00 (= Slot 0) heizt, 00:00–07:00 heizen, 08:00 0,4 Heizen + 0,6 Warmwasser, 09:00 Warmwasser,
    sonst aus — und die Zeile D 23:00 (Slot 0 des Folgetags) heizt, darf hier aber nicht zählen."""
    von = _ts(T0)
    out: dict[int, dict[str, float]] = {}
    for h in range(-1, 24):
        if h <= 7:
            a = {HEIZEN: 1.0}
        elif h == 8:
            a = {HEIZEN: 0.4, WARMWASSER: 0.6}
        elif h == 9:
            a = {WARMWASSER: 1.0}
        elif h == 23:
            a = {HEIZEN: 1.0}
        else:
            a = {AUS: 1.0}
        out[von + h * H] = a
    return out


async def _mitschrift(db, anlage_id: int, inv_id: int, anteile: dict[int, dict[str, float]]) -> None:
    """Je Kanon-Modus ein Mittelwert-Kanal mit einer Zeile je Stunde (0 = gemessen nicht in diesem Modus), wie
    ``schreiber.schreibe_betriebsart_mitschrift``."""
    for modus in BETRIEBSMODUS_KANON:
        zeilen = [(ts, je.get(modus, 0.0), None, None) for ts, je in sorted(anteile.items())]
        await _kanal(db, anlage_id, modus_kanal_key(inv_id, modus), ART_MEAN, zeilen, einheit="Anteil")
    await db.commit()


async def _tag(db, anlage_id):
    from backend.api.routes.energie_profil.views import get_tag_detail

    return await get_tag_detail(anlage_id, DATUM, db)


@pytest.mark.asyncio
async def test_tag_detail_betrieb_stunden_aus_der_mitschrift(db):
    """Bestandstag (Ende-Raster): Slot 0 = Zeile Vortag 23:00 (heizt) + 00:00–07:00 + 0,4 ⇒ Heizen 9,4 h; Warmwasser
    0,6 + 1 ⇒ 1,6 h. Die Zeile D 23:00 gehört dem Folgetag. Das zweite Gerät hat keine Mitschrift ⇒ ``None``."""
    a, (wp1, wp2) = await _anlage_waerme(db, [{"heizenergie_kwh": {6: 8.0, 18: 4.0}},
                                              {"heizenergie_kwh": {7: 3.0}}])
    await _mitschrift(db, a.id, wp1.id, _anteile_bestandstag())
    t = await _tag(db, a.id)
    je = {z.investition_id: z for z in t.wp_geraete}
    assert je[wp1.id].betrieb_stunden == {HEIZEN: 9.4, WARMWASSER: 1.6, KUEHLEN: 0.0, "entfeuchten": 0.0,
                                          "lueften": 0.0}
    assert list(je[wp1.id].betrieb_stunden)[:2] == [HEIZEN, WARMWASSER]
    assert je[wp2.id].betrieb_stunden is None


@pytest.mark.asyncio
async def test_kanal_tag_beginn_raster_ohne_vortagszeile(db, monkeypatch):
    """An einem WP-Kanal-Tag liegt der Tag auf ``[D 00:00, D+1 00:00)``: die Zeile Vortag 23:00 zählt nicht, die Zeile
    D 23:00 schon ⇒ Heizen wieder 9,4 h (8 + 1 + 0,4), aus anderen Zeilen."""
    from types import SimpleNamespace

    from backend.services.energie_profil import kanal_stunden
    from backend.services.kanal.stunden_leser import GRUPPE_WP

    a, (wp,) = await _anlage_waerme(db, [{"heizenergie_kwh": {6: 8.0}}])
    await _mitschrift(db, a.id, wp.id, _anteile_bestandstag())

    async def _wp_kanal_tag(_db, _aid, _datum, **_k):
        return SimpleNamespace(gruppen={GRUPPE_WP: object()})

    monkeypatch.setattr(kanal_stunden, "kanal_stundentag", _wp_kanal_tag)
    anteile = await kanal_stunden.wp_betriebsart_anteile_je_stunde(db, a, {str(wp.id): wp}, DATUM)
    zeilen = anteile[str(wp.id)]
    assert min(zeilen) == _ts(T0) and max(zeilen) == _ts(T0 + timedelta(hours=23))
    assert stunden_je_betriebsart(zeilen)[HEIZEN] == 9.4


@pytest.mark.asyncio
async def test_ohne_mitschrift_kein_feld_und_stillgelegt_fehlt(db):
    a, (wp,) = await _anlage_waerme(db, [{"heizenergie_kwh": {6: 8.0}}])
    t = await _tag(db, a.id)
    assert [z.betrieb_stunden for z in t.wp_geraete] == [None]
    from backend.services.energie_profil.kanal_stunden import wp_betriebsart_anteile_je_stunde

    await _mitschrift(db, a.id, wp.id, _anteile_bestandstag())
    wp.stilllegungsdatum = DATUM - timedelta(days=1)
    await db.commit()
    assert await wp_betriebsart_anteile_je_stunde(db, a, {str(wp.id): wp}, DATUM) == {}


# ═══ C-1 Zähler und Nenner je Gerät ══════════════════════════════════════════

@pytest.mark.asyncio
async def test_tag_zaehler_durch_nenner_ist_jaz_je_geraet(db):
    """Muster S3 ``test_tag_detail_zaehler_und_nenner_je_funktion``: je Gerät Zähler ÷ Nenner = ``jaz`` (2 Stellen);
    ein Gerät ohne Wärme hat keine Zahl ⇒ beide ``None``."""
    a, (wp1, wp2) = await _anlage_waerme(db, [{"heizenergie_kwh": {6: 8.0, 18: 4.0}}, {}])
    t = await _tag(db, a.id)
    je = {z.investition_id: z for z in t.wp_geraete}
    z1 = je[wp1.id]
    assert z1.jaz is not None
    assert z1.jaz_zaehler_kwh == pytest.approx(12.0)
    assert round(z1.jaz_zaehler_kwh / z1.jaz_nenner_kwh, 2) == z1.jaz
    z2 = je[wp2.id]
    assert z2.jaz is None and z2.jaz_zaehler_kwh is None and z2.jaz_nenner_kwh is None


@pytest.mark.asyncio
async def test_monat_zaehler_nenner_aus_derselben_rechenstelle_und_keine_betriebsstunden(db):
    """Der Monat liefert dieselbe Zeile: Zähler/Nenner zur Zahl, ``betrieb_stunden`` immer ``None`` (nur der Tag)."""
    from backend.tests.test_p433_3_s2_heizstab_zusatzheizung import MONAT_OHNE, _lage
    from backend.tests.test_r2_je_funktion import _monat

    a, _inv = await _lage(db, dict(MONAT_OHNE), name="P433-2c Monat")
    m = await _monat(db, a.id)
    assert m.wp_geraete, "die Lage trägt eine Gerätezeile"
    mit_zahl = [z for z in m.wp_geraete if z.jaz is not None]
    assert mit_zahl, "die Lage trägt eine Arbeitszahl"
    for z in m.wp_geraete:
        assert z.betrieb_stunden is None
        if z.jaz is None:
            assert z.jaz_zaehler_kwh is None and z.jaz_nenner_kwh is None
        else:
            assert round(z.jaz_zaehler_kwh / z.jaz_nenner_kwh, 2) == z.jaz
