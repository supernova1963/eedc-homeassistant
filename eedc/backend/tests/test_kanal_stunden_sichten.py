"""Die Stunden-Sichten an einem Kanal-Tag (HA-Bauform S3, Etappe E-S3-2; Bauplan §3 «Umhängen», §4 S3-R1/R5/R6).

``/stunden``, ``tage-werte`` (die stundengepaarten Größen) und ``monat`` (Heatmap, Profil, Spitzen) lesen an einem Tag
mit Kanal-Gruppe die **Mischzeilen** aus ``services/energie_profil/kanal_stunden.py``: die Mengen der Gruppen mit Wahl
``kanal`` aus dem Kanal-Stundentag (``kanal/stunden_adapter.py``, HAs ``change`` je Stunde), SoC, Wetter, Zählwerke und
``komponenten`` (der Leistungspfad, H-1 A) aus der Stundenzeile; ``spannen`` je Achse gemischt in der Form der Spalte.

Geprüft an der Achsen-Form M07 (Bilanz, Sonstiges, WP aus Kanälen, HA), Tag 15.06.2026, Uhr der Matrix gestellt
(keine Probe liest die Uhr): die Route trägt je Stunde die Adapter-Werte (Gegenprobe: eine verfälschte Stundenzeile
ändert die Kanal-Felder NICHT, wohl aber den Ladestand); ein Tag ohne Stundenzeile bekommt die Mengen, die übrigen Felder
bleiben leer; ``tage-werte`` rechnet Direktverbrauch/Überschuss/Defizit/WP-Strom aus den Adapter-Zeilen über
``bilanz_aus_stundenrows``; ``monat`` zeigt in der Heatmap die Adapter-Werte; der Lade-Kontext (zweiter Aufruf liest
nichts, die Bilanz-Randstände kommen aus ``kanal_tage`` derselben Anfrage). Ohne Kanal-Tag bleibt jede Liste dieselbe.

**S4 E-S4-1 (S4-R-3b):** die Stunde eines Kanal-Tags ist ihr Beginn; die Mischzeile paart nach Bahnen — Backward-Bahnen
aus der Bestandszeile ``(D, h+1)`` (Stunde 23: Slot 0 des Folgetags), Forward-Bahnen (SoC, Preise) zeilengleich — und
trägt ``raster = "beginn"``; ``/stunden`` liefert das Raster je Zeile.

Schwesterdateien: test_kanal_stunden_gleichheit.py, test_kanal_stunden_summe.py, test_n553_stunden_serie_eine_uhr.py.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, event, update

from backend.core.berechnungen import bilanz_aus_stundenrows
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.energie_profil.kanal_stunden import (
    Mischzeile,
    mische_spannen,
    mische_stunden,
    stunden_der_kanal_tage,
    stundenzeilen_mit_kanaelen,
)
from backend.services.kanal import bilanz_leser, lesen, merken
from backend.services.kanal.lade_kontext import lese_anfrage
from backend.services.kanal.stunden_adapter import stunden_aus_kanaelen
from backend.services.kanal.stunden_leser import kanal_stundentag
from backend.tests import kanal_bilanz_gleichheit as kg

TAG = date(2026, 6, 15)
_FELDER = ("pv_kw", "verbrauch_kw", "einspeisung_kw", "netzbezug_kw", "batterie_kw", "ueberschuss_kw", "defizit_kw",
           "waermepumpe_kw")


@pytest.fixture
def uhr(monkeypatch):
    """Die Uhr der Leser steht auf der Uhr der Matrix (``kg.JETZT_TS``)."""
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)


# ── rein ────────────────────────────────────────────────────────────────────


def test_mischzeile_kanal_felder_aus_dem_adapter_alles_uebrige_aus_der_stundenzeile():
    """S4-R-3b: die Mischzeile der Stunde ``[3, 4)`` nimmt die Backward-Bahnen (``komponenten``, Wetter, ``*_kw``) aus der
    Bestandszeile ``(D, 4)`` und die Forward-Bahnen (SoC, Preise) aus ``(D, 3)``; sie trägt ``raster = "beginn"``."""
    rueck = SimpleNamespace(datum=TAG, stunde=4, pv_kw=9.0, soc_prozent=11.0, komponenten={"pv_6": 1.0},
                            temperatur_c=7.0, spannen=None)
    vor = SimpleNamespace(datum=TAG, stunde=3, pv_kw=8.0, soc_prozent=55.0, strompreis_cent=31.0,
                          komponenten={"pv_6": 9.9}, temperatur_c=1.0, spannen=None)
    m = Mischzeile(TAG, 3, {"pv_kw": 1.5}, rueck, None, vor)
    assert (m.pv_kw, m.soc_prozent, m.strompreis_cent, m.komponenten, m.temperatur_c, m.raster) == (
        1.5, 55.0, 31.0, {"pv_6": 1.0}, 7.0, "beginn")
    ohne = Mischzeile(TAG, 3, {"pv_kw": 1.5}, None, None)
    assert (ohne.pv_kw, ohne.soc_prozent, ohne.komponenten) == (1.5, None, None)


def test_mische_stunden_paart_nach_bahnen_und_stunde_23_aus_dem_folgetag():
    """Zeilen des Tages UND des Folgetags: Stunde ``h`` ← Bestandszeile ``(D, h+1)``, Stunde 23 ← ``(D+1, 0)``; der
    Ladestand zeilengleich aus ``(D, h)``; ``spannen`` der Nicht-Kanal-Achsen aus der herangezogenen Bestandszeile."""
    zeilen = [SimpleNamespace(datum=TAG, stunde=h, temperatur_c=float(h), soc_prozent=100.0 + h,
                              spannen={"waermepumpe": 2} if h == 4 else None) for h in range(24)]
    zeilen.append(SimpleNamespace(datum=TAG + timedelta(days=1), stunde=0, temperatur_c=-1.0, soc_prozent=0.0,
                                  spannen=None))
    k = [SimpleNamespace(stunde=h, pv_kw=1.0, komponenten=None, spannen=None) for h in range(24)]
    ks = SimpleNamespace(zeilen=k, felder=frozenset({"pv_kw", "komponenten", "spannen"}))
    ms = mische_stunden(TAG, zeilen, SimpleNamespace(gruppen={"bilanz": None}), ks)
    assert [m.stunde for m in ms] == list(range(24))
    assert [m.temperatur_c for m in ms] == [float(h + 1) for h in range(23)] + [-1.0]
    assert [m.soc_prozent for m in ms] == [100.0 + h for h in range(24)]
    assert ms[3].spannen == {"waermepumpe": 2} and ms[4].spannen is None
    assert all(m.raster == "beginn" for m in ms)


def test_spannen_je_achse_gemischt_in_der_form_der_spalte():
    zeile = SimpleNamespace(spannen={"pv": 2, "waermepumpe": 3})
    bilanz = frozenset({"pv", "einspeisung", "netzbezug", "batterie"})
    assert mische_spannen(zeile, {"pv": 4, "waermepumpe": 9}, bilanz) == {"waermepumpe": 3, "pv": 4}
    assert mische_spannen(zeile, None, bilanz) == {"waermepumpe": 3}
    assert mische_spannen(SimpleNamespace(spannen=None), None, bilanz) is None


def test_stunde_ohne_zeile_und_ohne_kanalwert_ist_keine_zeile():
    k = [SimpleNamespace(stunde=h, pv_kw=(None if h == 5 else 1.0), komponenten=None, spannen=None) for h in range(24)]
    ks = SimpleNamespace(zeilen=k, felder=frozenset({"pv_kw", "komponenten", "spannen"}))
    tag = SimpleNamespace(gruppen={"bilanz": None})
    stunden = [m.stunde for m in mische_stunden(TAG, [], tag, ks)]
    assert stunden == [h for h in range(24) if h != 5]
    # Die Stunde 5 entsteht, sobald eine der beiden Stundenzeilen da ist: die Bestandszeile (D, 6) oder die Zeile (D, 5).
    for zeile in (SimpleNamespace(datum=TAG, stunde=6, pv_kw=7.0, spannen=None),
                  SimpleNamespace(datum=TAG, stunde=5, pv_kw=7.0, spannen=None)):
        mit_zeile = mische_stunden(TAG, [zeile], tag, ks)
        assert [m.stunde for m in mit_zeile] == list(range(24)) and mit_zeile[5].pv_kw is None


def test_ohne_kanal_tag_bleibt_die_liste_dieselbe():
    zeilen = [SimpleNamespace(datum=TAG, stunde=h) for h in range(24)]
    assert stundenzeilen_mit_kanaelen(zeilen, {}) == zeilen


# ── an einem Datenstand ─────────────────────────────────────────────────────


async def _adapter(ds):
    return stunden_aus_kanaelen(await kanal_stundentag(ds.db, ds.aid, TAG, jetzt=kg.JETZT_TS))


async def test_stunden_route_traegt_die_kanal_stunden_und_den_ladestand_der_zeile(uhr):
    from backend.api.routes.energie_profil.views import get_stundenwerte

    async with kg.datenstand("achsen", "M07", "HA") as ds:
        ks = await _adapter(ds)
        assert {"pv_kw", "waermepumpe_kw"} <= ks.felder
        # Gegenprobe: eine verfälschte Stundenzeile ändert die Kanal-Felder nicht, wohl aber den Ladestand der Zeile.
        await ds.db.execute(update(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum == TAG,
        ).values(pv_kw=TagesEnergieProfil.pv_kw + 1.0, waermepumpe_kw=99.0, soc_prozent=42.0))
        await ds.db.commit()
        antwort = await get_stundenwerte(anlage_id=ds.aid, datum=TAG, db=ds.db)
        komp = {z.stunde: z.komponenten for z in (await ds.db.execute(
            TagesEnergieProfil.__table__.select().where(TagesEnergieProfil.anlage_id == ds.aid,
                                                        TagesEnergieProfil.datum == TAG))).all()}
        folge0 = (await ds.db.execute(TagesEnergieProfil.__table__.select().where(
            TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum == TAG + timedelta(days=1),
            TagesEnergieProfil.stunde == 0))).one()
    assert [s.stunde for s in antwort.stunden] == list(range(24))
    for s, k in zip(antwort.stunden, ks.zeilen):
        for f in _FELDER:
            assert getattr(s, f) == getattr(k, f), (s.stunde, f)
        # Leistungspfad aus der Bestandszeile der Stunde (H-1 A; S4-R-3b: Stunde h ← Zeile h+1, Stunde 23 ← Folgetag 0)
        assert s.komponenten == (komp[s.stunde + 1] if s.stunde < 23 else folge0.komponenten), s.stunde
        assert s.spannen is None or all(isinstance(n, int) and n > 1 for n in s.spannen.values())
        assert s.raster == "beginn"
    assert all(s.soc_prozent == 42.0 for s in antwort.stunden)    # S4-R-3b: Beginn-Raster ⇒ Ladestand zeilengleich


async def test_tag_ohne_stundenzeile_bekommt_die_mengen_aus_den_kanaelen(uhr):
    from backend.api.routes.energie_profil.views import get_stundenwerte

    async with kg.datenstand("achsen", "M07", "HA") as ds:
        ks = await _adapter(ds)
        await ds.db.execute(delete(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum == TAG))
        await ds.db.commit()
        antwort = await get_stundenwerte(anlage_id=ds.aid, datum=TAG, db=ds.db)
        folge0 = (await ds.db.execute(TagesEnergieProfil.__table__.select().where(
            TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum == TAG + timedelta(days=1),
            TagesEnergieProfil.stunde == 0))).one()
    assert [s.pv_kw for s in antwort.stunden] == [k.pv_kw for k in ks.zeilen]
    assert all(s.soc_prozent is None for s in antwort.stunden)
    assert all(s.komponenten is None and s.temperatur_c is None for s in antwort.stunden[:23])
    # Die Stunde 23 trägt ihre Backward-Bahnen aus Slot 0 des Folgetags (S4-R-3b) — der ist nicht gelöscht.
    assert (antwort.stunden[23].komponenten, antwort.stunden[23].temperatur_c) == (folge0.komponenten,
                                                                                  folge0.temperatur_c)


async def test_tage_werte_stundengepaarte_groessen_aus_den_kanal_stunden(uhr):
    from backend.api.routes.energie_profil.tage import get_tage_werte

    async with kg.datenstand("achsen", "M07", "HA") as ds:
        ks = await _adapter(ds)
        await ds.db.execute(update(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum == TAG,
        ).values(pv_kw=TagesEnergieProfil.pv_kw + 1.0, waermepumpe_kw=99.0))
        await ds.db.commit()
        zeile = {z.datum: z for z in await get_tage_werte(ds.aid, TAG, TAG, ds.db)}[TAG]
    soll = bilanz_aus_stundenrows(ks.zeilen)
    assert zeile.stunden_verfuegbar is not None
    assert zeile.direktverbrauch == pytest.approx(round(soll.direktverbrauch_kwh, 3))
    assert zeile.ueberschuss_kwh == pytest.approx(round(soll.ueberschuss_kwh, 3))
    assert zeile.defizit_kwh == pytest.approx(round(soll.defizit_kwh, 3))
    assert zeile.wp_strom == pytest.approx(round(soll.wp_strom_kwh, 3))


async def test_monat_heatmap_und_spitzen_aus_den_kanal_stunden(uhr):
    from backend.api.routes.energie_profil.views import get_monatsauswertung

    async with kg.datenstand("achsen", "M07", "HA") as ds:
        ks = await _adapter(ds)
        await ds.db.execute(update(TagesEnergieProfil).where(
            TagesEnergieProfil.anlage_id == ds.aid, TagesEnergieProfil.datum == TAG,
        ).values(pv_kw=TagesEnergieProfil.pv_kw + 1.0))
        await ds.db.commit()
        m = await get_monatsauswertung(ds.aid, TAG.year, TAG.month, 10, ds.db)
    zellen = {z.stunde: z for z in m.heatmap if z.tag == TAG.day}
    assert sorted(zellen) == list(range(24))
    for k in ks.zeilen:
        assert zellen[k.stunde].pv_kw == (round(k.pv_kw, 3) if k.pv_kw is not None else None), k.stunde


class _Zaehler:
    """Zählt die Anweisungen über die Verbindung der Sitzung; ``rand`` die von ``lesen._randstaende``."""

    _RAND = "FROM k CROSS JOIN g"

    def __init__(self, db):
        self.n = self.rand = 0
        self._engine = db.bind.sync_engine

    def _hook(self, _conn, _cur, statement, *_a, **_k):
        self.n += 1
        self.rand += self._RAND in statement

    def __enter__(self):
        event.listen(self._engine, "before_cursor_execute", self._hook)
        return self

    def __exit__(self, *_a):
        event.remove(self._engine, "before_cursor_execute", self._hook)


assert _Zaehler._RAND in lesen._RAND_SQL


async def test_lade_kontext_zweiter_aufruf_liest_nichts_und_bilanz_raender_aus_kanal_tage(uhr):
    """Wie ``tage-werte``: erst ``kanal_tage`` über den Zeitraum, dann die Stunden der Kanal-Tage über den Bereichs-Leser
    (Nachbau E-S3-2, §10c L-1). Die Bilanz-Tageswahl liest ihre Randstände aus dem Kontext (EINE Randstand-Anweisung
    weniger als ohne ``kanal_tage`` davor — eine je Bereich, nicht je Tag); der zweite Aufruf derselben Anfrage liest
    nichts."""
    tage = [TAG + timedelta(days=i) for i in range(3)]
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        with lese_anfrage():
            with _Zaehler(ds.db) as ohne:
                await stunden_der_kanal_tage(ds.db, ds.aid, tage, {})
        # Der Speicher je Prozess (HA-Bauform S5 E-S5-1c, ``kanal/merken.py``) hielte die Tage über die Anfrage hinaus —
        # diese Probe zählt den Lade-Kontext EINER Anfrage, also kalt.
        merken.leeren()
        with lese_anfrage():
            kanal = await bilanz_leser.kanal_tage(ds.db, ds.aid, tage[0], tage[-1])
            with _Zaehler(ds.db) as mit:
                erst = await stunden_der_kanal_tage(ds.db, ds.aid, kanal, {})
            with _Zaehler(ds.db) as zweit:
                wieder = await stunden_der_kanal_tage(ds.db, ds.aid, kanal, {})
    assert sorted(kanal) == tage and sorted(erst) == tage
    assert mit.rand == ohne.rand - 1, (ohne.rand, mit.rand)
    assert zweit.n == 0
    assert all([(m.stunde, m.pv_kw) for m in erst[t]] == [(m.stunde, m.pv_kw) for m in wieder[t]] for t in tage)
