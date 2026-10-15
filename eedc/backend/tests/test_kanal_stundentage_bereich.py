"""Bereichs-Leser des Kanal-Stundentags (HA-Bauform S3, Nachbau E-S3-2; Bauplan §10c L-1).

``stunden_leser.kanal_stundentage(von, bis)`` liefert je Tag **dasselbe** wie ``kanal_stundentag(tag)`` — dieselben
Pläne je Tag (Tageswahl der Tages-Leser), aber je Gruppe EIN ``stunden_stapel`` über den ganzen Bereich und EIN
``reihe_stapel`` für die Tageswahl der Geräte und der WP; je Tag ein Ausschnitt (``ausschnitt``). Geprüft:

* **bitgleich je Tag** an jeder Form beider Abnahme-Matrizen, ``HA`` und ``MQTT``, alle Tage 01.06.–03.07.;
* **Abfrage-Budget ∝ Gruppen, nicht ∝ Tage** (3 und 20 Tage lesen gleich viele Anweisungen);
* **der Schwanz einer Lücke über das Bereichsende** (rein): bestimmbar aus der nächsten Zeile im Bereich, aus
  ``endet_vor_bis`` oder einer größten Spanne über allen inneren — sonst ``None`` und der Tag liest selbst; an einem
  Datenstand mit genau dieser Lage bleibt der Bereich bitgleich (Gegenprobe: der Rückfall wird gezählt).

* **nur die gefragten Gruppen** (L-1b → A: `tage-werte`/`monat` fragen Bilanz und WP) — gleich und mit einer
  Stunden-Anweisung je gefragter Gruppe.

Schwesterdateien: test_kanal_stunden_gleichheit.py, test_kanal_stunden_summe.py, test_kanal_stunden_sichten.py.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import delete, event, select

from backend.models.kanal import Kanal, KanalStatistik
from backend.services.kanal import lesen
from backend.services.kanal import stunden_leser as sl
from backend.services.kanal.fenster import tagesfenster
from backend.services.kanal.lade_kontext import lese_anfrage
from backend.services.kanal.lesen import GRUND_ENDET_VOR_BIS, Stunden, Stundenwert
from backend.tests import achsen_matrix as am
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests import pv_achse_matrix as mx

_FORMEN = [("achsen", f) for f in am.MATRIX_FORMEN] + [("pv", f) for f in mx.MATRIX_FORMEN]
_FAELLE = [(m, f, art) for art in ("HA", "MQTT") for m, f in _FORMEN]
H = 3600


def _ungleich(einzeln: dict, bereich: dict) -> list:
    return [(d, [x for x in ("wahlen", "gruppen", "bilanz") if getattr(t, x) != getattr(bereich[d], x)])
            for d, t in einzeln.items() if t != bereich[d]]


@pytest.mark.parametrize("matrix,fid,art", _FAELLE, ids=[f"{a}-{m}-{f}" for m, f, a in _FAELLE])
async def test_bereich_gleich_dem_tages_leser_je_tag(matrix, fid, art):
    async with kg.datenstand(matrix, fid, art) as ds:
        bereich = await sl.kanal_stundentage(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[-1], jetzt=kg.JETZT_TS)
        einzeln = {d: await sl.kanal_stundentag(ds.db, ds.aid, d, jetzt=kg.JETZT_TS) for d in kg.TAGE}
    assert list(bereich) == list(kg.TAGE)
    assert not _ungleich(einzeln, bereich)


class _Zaehler:
    _STUNDEN = "FROM r LEFT JOIN kanal_statistik s ON s.kanal_id = r.kid"

    def __init__(self, db):
        self.n = self.stunden = 0
        self._engine = db.bind.sync_engine

    def _hook(self, _c, _cur, statement, *_a, **_k):
        self.n += 1
        self.stunden += self._STUNDEN in statement

    def __enter__(self):
        event.listen(self._engine, "before_cursor_execute", self._hook)
        return self

    def __exit__(self, *_a):
        event.remove(self._engine, "before_cursor_execute", self._hook)


assert _Zaehler._STUNDEN in lesen._STUNDEN_SQL


async def test_abfrage_budget_je_gruppe_nicht_je_tag():
    """M07 (Bilanz, Sonstiges, WP aus Kanälen), im Lade-Kontext einer Anfrage wie jede GET-Route: drei
    Stunden-Anweisungen für 3 und für 20 Tage, und gleich viele Anweisungen insgesamt — der Tages-Leser liest je Tag und
    Gruppe."""
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        with lese_anfrage(), _Zaehler(ds.db) as kurz:
            await sl.kanal_stundentage(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[2], jetzt=kg.JETZT_TS)
        with lese_anfrage(), _Zaehler(ds.db) as lang:
            await sl.kanal_stundentage(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[19], jetzt=kg.JETZT_TS)
        with lese_anfrage(), _Zaehler(ds.db) as tageweise:
            for d in kg.TAGE[:20]:
                await sl.kanal_stundentag(ds.db, ds.aid, d, jetzt=kg.JETZT_TS)
    assert (kurz.stunden, lang.stunden) == (3, 3)
    assert kurz.n == lang.n
    assert tageweise.stunden == 60 and tageweise.n > 3 * lang.n


# ── Der Ausschnitt (rein) ───────────────────────────────────────────────────


def _st(zeilen: list[int], *, vor: int | None, gedeckt_von, groesste, grund=None) -> Stunden:
    """Ein Bereichs-Ergebnis mit Zeilen zu den Zeitpunkten ``zeilen`` (Zuwachs 1 je Zeile)."""
    werte, vorher = [], vor
    for ts in zeilen:
        werte.append(Stundenwert(ts, 1.0 if vorher is not None else None, 0.0, "spiegel",
                                 ts - vorher if vorher is not None else None))
        vorher = ts
    return Stunden(key="k", art="sum", einheit="kWh", von=0, bis=0, werte=werte, gedeckt_von=gedeckt_von,
                   gedeckt_bis=None, groesste_spanne=groesste, voll=grund is None, grund=grund, laufend=False)


def test_ausschnitt_lueckenschwanz_aus_der_naechsten_zeile_im_bereich():
    # Tag [0, 24h): Zeilen bis 10h, die nächste erst 30h (im Bereich) ⇒ Schwanz 20h.
    zeilen = [h * H for h in range(0, 11)] + [30 * H, 31 * H]
    st = _st(zeilen, vor=-H, gedeckt_von=0, groesste=20 * H)
    a = sl.ausschnitt(st, [w.start_ts for w in st.werte], 0, 24 * H)
    assert (a.gedeckt_von, a.gedeckt_bis, a.groesste_spanne, len(a.werte)) == (0, 11 * H, 20 * H, 11)


def test_ausschnitt_schwanz_hinter_dem_bereich():
    zeilen = [h * H for h in range(0, 11)]
    ts = zeilen
    # endet_vor_bis: es gibt keine Zeile dahinter ⇒ kein Schwanz.
    a = sl.ausschnitt(_st(zeilen, vor=-H, gedeckt_von=0, groesste=H, grund=GRUND_ENDET_VOR_BIS), ts, 0, 24 * H)
    assert a.groesste_spanne == H
    # größte Spanne über allen inneren ⇒ sie ist der Schwanz.
    a = sl.ausschnitt(_st(zeilen, vor=-H, gedeckt_von=0, groesste=50 * H), ts, 0, 24 * H)
    assert a.groesste_spanne == 50 * H
    # sonst nicht bestimmbar ⇒ None (der Tag liest selbst).
    innen = [0, 5 * H] + [h * H for h in range(6, 11)]
    assert sl.ausschnitt(_st(innen, vor=-H, gedeckt_von=0, groesste=5 * H), innen, 0, 24 * H) is None


def test_ausschnitt_vor_aus_dem_bereich_und_tag_ohne_zeile():
    zeilen = [h * H for h in range(0, 24)]
    st = _st(zeilen, vor=-3 * H, gedeckt_von=-2 * H, groesste=3 * H)
    a = sl.ausschnitt(st, zeilen, 0, 24 * H)
    assert (a.gedeckt_von, a.gedeckt_bis) == (-2 * H, 24 * H)
    leer = sl.ausschnitt(_st([], vor=None, gedeckt_von=None, groesste=None, grund="keine_zeile"), [], 0, 24 * H)
    assert (leer.werte, leer.gedeckt_von, leer.gedeckt_bis, leer.groesste_spanne) == ([], None, None, None)


async def test_luecke_ueber_das_bereichsende_bleibt_bitgleich(monkeypatch):
    """M01 HA: der Netzbezug-Kanal schweigt 40 h ab 10.06. 12:00 (innere Lücke) und 30 h ab 20.06. 10:00 (über das
    Bereichsende 20.06.; beide länger als ein Tag ⇒ Lückentag wie HA, die Tage bleiben Kanal-Tage). Der Schwanz (31 h) ist
    kürzer als die innere Spanne (41 h) ⇒ nicht aus dem Bereich bestimmbar ⇒ der 20.06. liest selbst (gezählt), und der
    Bereich ist trotzdem bitgleich."""
    async with kg.datenstand("achsen", "M01", "HA") as ds:
        kid = (await ds.db.execute(select(Kanal.id).where(Kanal.anlage_id == ds.aid,
                                                          Kanal.key == "basis:netzbezug"))).scalar_one()
        for a, b in ((date(2026, 6, 10), 13), (date(2026, 6, 20), 11)):
            von = tagesfenster(a)[0] + b * H
            await ds.db.execute(delete(KanalStatistik).where(
                KanalStatistik.kanal_id == kid, KanalStatistik.start_ts >= von,
                KanalStatistik.start_ts < von + (40 * H if a.day == 10 else 30 * H)))
        await ds.db.commit()
        echt = sl._lies_stunden
        rueckfall = []

        async def _zaehle(db, aid, keys, datum, jetzt):
            rueckfall.append(datum)
            return await echt(db, aid, keys, datum, jetzt)

        bis = date(2026, 6, 20)
        tage = [d for d in kg.TAGE if d <= bis]
        einzeln = {d: await sl.kanal_stundentag(ds.db, ds.aid, d, jetzt=kg.JETZT_TS) for d in tage}
        monkeypatch.setattr(sl, "_lies_stunden", _zaehle)
        bereich = await sl.kanal_stundentage(ds.db, ds.aid, tage[0], bis, jetzt=kg.JETZT_TS)
    assert rueckfall == [bis]
    assert not _ungleich(einzeln, bereich)


async def test_nur_gefragte_gruppen_gleich_und_budget_je_gefragter_gruppe():
    """L-1b → A: ``tage-werte``/``monat`` fragen nur Bilanz und WP. Je Tag dasselbe wie der Tages-Leser, eingeschränkt
    auf die gefragten Gruppen; M07 liest dann zwei Stunden-Anweisungen statt drei (die Geräte-Gruppe fällt weg)."""
    gefragt = ("bilanz", "wp")
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        with lese_anfrage(), _Zaehler(ds.db) as z:
            bereich = await sl.kanal_stundentage(ds.db, ds.aid, kg.TAGE[0], kg.TAGE[19], jetzt=kg.JETZT_TS,
                                                 gruppen=gefragt)
        einzeln = {d: sl._nur(await sl.kanal_stundentag(ds.db, ds.aid, d, jetzt=kg.JETZT_TS), frozenset(gefragt))
                   for d in kg.TAGE[:20]}
    assert z.stunden == 2
    assert all(set(t.gruppen) <= set(gefragt) and set(t.wahlen) == set(gefragt) for t in bereich.values())
    assert not _ungleich(einzeln, bereich)
