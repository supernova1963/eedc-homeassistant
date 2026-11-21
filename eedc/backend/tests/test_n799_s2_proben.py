"""N-799 Sitzung 2, F7 (Nachmessung S1): «Proben, die halten» — je Proben-Punkt ein Fall, der unter dem genannten Mutanten
rot wird (Sprengsatz in der Probe selbst, wo er ohne Quelltext-Änderung geht).

* Toleranz des Stillstands (``spannen._EPS``): ein Zähler mit winzigem Δ steht nicht.
* Marke nicht an Bestandszeilen (E-9): ``stillstand_marke.markiere`` lässt eine Zeile ohne Bilanz aus den Kanälen liegen.
* Bereichsfilter der Lesestelle: ``fenster_im_bereich`` nennt nur Fenster, die den Bereich berühren.
* Generation: eine Änderung an Anlage/Investition/Kanal/Quelle (``merken.invalidiere`` ohne Tag) verwirft die Fenster.
* Offset in ``deltas_stapel``: ``sum + offset`` der geltenden Quelle — wie ``stunden_stapel``.
* Direktstellen «n ≠ 1»: ``emob_ladebloecke_speicher._stunde`` nimmt eine Nullzeile (n = 0) aus der Paarung. Die übrigen
  fünf sind gegen «zurück auf > 1» **äquivalent** (benannt, nicht prüfbar): Korrekturprofil-Aggregator und -Route lassen
  eine Zeile mit PV unter der Mess-Schwelle vorher aus (eine Nullzeile trägt PV 0), ``repair.py`` summiert die PV
  gebündelter Zeilen (eine Nullzeile trägt 0 bei), ``aggregator.verrechne_stunde`` liest Bestandszeilen und
  ``ladeanteil_der_kanal_stunden`` Adapter-Zeilen — beide tragen nie n = 0 (E-9 bzw. Marke nur an Mischzeilen).

Schwesterdateien: test_n799_stillstand_layer.py, test_n799_stillstand_lesestelle.py, test_n799_s2_leser.py.
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from backend.core.berechnungen import spannen as sp
from backend.core.berechnungen.spannen import StillstandFenster, ZaehlerReihe, stillstand_fenster
from backend.services.kanal import bilanz_leser, lesen, merken, stillstand
from backend.tests import kanal_bilanz_gleichheit as kg
from backend.tests.test_n799_stillstand_lesestelle import _einfrieren, _fein, _kid

H = 3600


@pytest.fixture(autouse=True)
def uhr(monkeypatch):
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)
    merken.leeren()
    yield
    merken.leeren()


def _reihe(rolle, deltas, t0):
    return ZaehlerReihe(rolle, tuple((t0 + h * H, d, None if h == 0 else H) for h, d in enumerate(deltas)))


def test_toleranz_ein_winziges_delta_steht_nicht(monkeypatch):
    t0 = 1_700_000_000 // H * H
    lauf = [0.5] * 30 + [0.0, 0.0, 0.0] + [2.0] + [0.5] * 5
    zuckt = [0.5] * 30 + [0.001, 0.001, 0.001] + [2.0] + [0.5] * 5
    basis = {"n": _reihe("netzbezug", lauf, t0), "p": _reihe("pv", lauf, t0)}
    assert len(stillstand_fenster(basis)) == 1
    mit = {**basis, "e": _reihe("einspeisung", zuckt, t0)}
    assert stillstand_fenster(mit) == []                     # Einspeisung läuft (1 Wh je Stunde): kein Stillstand
    monkeypatch.setattr(sp, "_EPS", 0.01)                    # Sprengsatz: grobe Toleranz ⇒ «steht»
    assert len(stillstand_fenster(mit)) == 1


def test_marke_nicht_an_bestandszeilen():
    from backend.services.energie_profil.stillstand_marke import markiere

    tag = date(2026, 6, 20)
    f = StillstandFenster(int(datetime(2026, 6, 20, 10).timestamp()), int(datetime(2026, 6, 20, 13).timestamp()), 3,
                          frozenset({"pv", "netzbezug"}))
    bestand = [SimpleNamespace(datum=tag, stunde=h, spannen=None, pv_kw=1.0) for h in range(9, 15)]
    markiere(tag, bestand, [f])
    assert all(z.spannen is None for z in bestand)


async def test_bereichsfilter_und_generation():
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        await _einfrieren(ds, datetime(2026, 6, 10, 10), 3)
        await _einfrieren(ds, datetime(2026, 6, 25, 10), 3)
        alle = await stillstand.fenster_im_bereich(ds.db, ds.aid, date(2026, 6, 1), date(2026, 6, 30))
        nur_erstes = await stillstand.fenster_im_bereich(ds.db, ds.aid, date(2026, 6, 9), date(2026, 6, 11))
        assert len(alle) == 2 and [f.nachtrag_ts for f in nur_erstes] == [alle[0].nachtrag_ts]
        # Generation: Zeilen ändern OHNE Tages-Invalidierung, dann nur die Generation der Anlage ⇒ frisch gelesen.
        kid = await _kid(ds, "basis:netzbezug")
        await ds.db.execute(text("UPDATE kanal_statistik SET sum = sum + 0.37 WHERE kanal_id = :k AND start_ts >= :t"),
                            {"k": kid, "t": int(datetime(2026, 6, 25, 11).timestamp())})
        await ds.db.commit()
        warm = await stillstand.fenster_im_bereich(ds.db, ds.aid, date(2026, 6, 1), date(2026, 6, 30))
        assert len(warm) == 2                                 # gemerkt: noch der alte Stand
        merken.invalidiere(ds.aid)                            # Generation (Anlage/Investition/Kanal/Quelle geändert)
        frisch = await stillstand.fenster_im_bereich(ds.db, ds.aid, date(2026, 6, 1), date(2026, 6, 30))
    assert len(frisch) == 1                                   # der Netzbezug lief im zweiten Fenster ⇒ kein Stillstand


async def test_offset_der_quelle_in_deltas_stapel():
    """``deltas_stapel`` liest ``sum + offset`` der geltenden Quelle wie ``stunden_stapel`` (Sensortausch). Sprengsatz:
    ohne Offset fehlte der Sprung an der Quellgrenze."""
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        kid = await _kid(ds, "basis:netzbezug")
        grenze = int(datetime(2026, 6, 15, 12).timestamp())
        await ds.db.execute(text(
            "INSERT INTO kanal_quelle (kanal_id, gueltig_ab, familie, statistic_id, \"offset\") "
            "VALUES (:k, :g, 'spiegel', 'sensor.neu', 100.0)"), {"k": kid, "g": grenze})
        await ds.db.commit()
        merken.invalidiere(ds.aid)
        kanaele = [k for k in (await lesen.kanaele_laden(ds.db, ds.aid, ("basis:netzbezug",))).values()]
        von, bis = int(datetime(2026, 6, 14).timestamp()), int(datetime(2026, 6, 17).timestamp())
        schlank = await lesen.deltas_stapel(ds.db, kanaele, von, bis)
        voll = await lesen.stunden_stapel(ds.db, kanaele, von, bis)
        orig = lesen._deltas
        with pytest.MonkeyPatch.context() as mp:              # Sprengsatz: Offset nicht gelesen
            mp.setattr(lesen, "_deltas", lambda z, _o, v, *b: orig(z, None, v, *b))
            ohne = await lesen.deltas_stapel(ds.db, kanaele, von, bis)
    assert schlank["basis:netzbezug"] == [(w.start_ts, w.change, w.spanne) for w in voll["basis:netzbezug"].werte]
    assert {ts: d for ts, d, _s in schlank["basis:netzbezug"]}[grenze] > 99.0
    assert {ts: d for ts, d, _s in ohne["basis:netzbezug"]}[grenze] < 99.0


def test_direktstelle_ladeblock_nimmt_nullzeile_aus():
    from backend.services.emob_ladebloecke_speicher import _stunde

    beginn = datetime(2026, 6, 20, 12)
    null = _stunde(beginn, ladung=0.0, netzbezug=0.0, einspeisung=0.0, batterie_spalte=0.0,
                   spannen={"wallbox": 0, "pv": 0, "netzbezug": 0})
    normal = _stunde(beginn, ladung=2.0, netzbezug=0.0, einspeisung=3.0, batterie_spalte=0.0, spannen=None)
    assert null.pv_anteil is None and null.speicher_anteil is None
    assert normal.pv_anteil is not None
    # Gegenprobe der alten Lesart «> 1» (Sprengsatz am Helfer): n = 0 wäre keine gebündelte Zeile
    assert sp.spanne({"pv": 0}, "pv") == 1 and sp.spannen_gebuendelt({"pv": 0}, "pv")

