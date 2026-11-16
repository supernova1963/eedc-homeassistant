"""N-799 Sitzung 2 «Leser» (Bauplan Fassung 3, E-4/E-5/E-7, §6 F3/F5/F11/F12, Tagesvergleich): die Tagesbilanz rechnet eine
gebündelte Zeile als **Fenster-Rechnung** aus den Zähler-Mengen und trägt ein Kennzeichen mit drei Zuständen; die Leser
reichen es durch.

Layer (``core/berechnungen/tagesbilanz.py``): Überschuss_w = min(PV_w, Einspeisung_w + Ladung_w) · Direkt_w = PV_w −
Überschuss_w · Defizit_w = Verbrauch_w − Direkt_w; unter der Schwelle 0,1 kWh gepaart wie bisher; Begrenzung ⇒
Mindest-Netzladung; ungleiche n oder saldierte Batterie ⇒ «nicht rechenbar»; Nullzeilen (n = 0) tragen nichts bei.
Jede neue Bedingung hat ihren Sprengsatz (ohne sie würde die Probe rot) — außer «Nullzeile trägt nichts bei»: eine
Nullzeile trägt PV 0 und Verbrauch 0, ihre Paarung als Stunde ist 0 (äquivalenter Mutant, benannt). Korrekturrunde S2:
K1 (nur PV gebündelt, PV-Schwelle bei ungleichen n) und K2 (None an `tage-werte` und Lesestelle, Wert-Soll am Kanal-Tag
mit Speicher, Schwelle auf dem Verbrauch, Netzladung im Potenzial, Netzbezugs-Spitze, `mische_bilanz`).

DB (Achsen-Form M07, Kanal-Tag; Bestandszeilen für Monat/Ladepreis): ``tage-werte`` mit Kennzeichen und Satz, die
Lesestelle ``ueberschuss_defizit_der_tage``, F3 Einzeltag ≡ Bereich bei einem Stillstand über 7 Tage über die Monatsgrenze,
Tagesvergleich über alle berührten Tage, F5 Ladepreis-Grund, E-7 Heatmap und Monatszähler, Ziel ``befund=``.

Zeitpunkte in Ortszeit der Prozesszone im Juni/Juli (fern jeder Umstellung; die Suite fährt auch ``Pacific/Auckland`` und
``UTC``); die Umstellungstage prüft ``test_n799_stillstand_layer.py::test_umstellungstag_*`` (F11).

Schwesterdateien: test_n799_stillstand_layer.py (die Regel des Fensters), test_n799_stillstand_lesestelle.py (Lesestelle und
Marke), test_tagesbilanz*.py (die Tagesbilanz), test_zaehlerluecken_leser.py (die Leser gebündelter Zeilen).
"""

from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from backend.core.berechnungen import tagesbilanz as tb
from backend.core.berechnungen.spannen import ZaehlerReihe, stillstand_fenster
from backend.core.berechnungen.tagesbilanz import (
    PAARUNG_FENSTER, PAARUNG_NICHT_RECHENBAR, PAARUNG_VOLL, bilanz_aus_stundenrows, monatsbilanz_aus_tagen,
)

H = 3600


def _z(stunde, pv, v, e, n, batt=None, spannen=None, ladung=None, entladung=None, **kw):
    return SimpleNamespace(stunde=stunde, raster="beginn", pv_kw=pv, verbrauch_kw=v, einspeisung_kw=e, netzbezug_kw=n,
                           batterie_kw=batt, waermepumpe_kw=None, spannen=spannen, speicher_ladung_kw=ladung,
                           speicher_entladung_kw=entladung, **kw)


ALLE12 = {"pv": 12, "einspeisung": 12, "netzbezug": 12, "batterie": 12}
NULL = {"pv": 0, "einspeisung": 0, "netzbezug": 0, "batterie": 0}


def _tag_12_11():
    """Der 12.11.2026 (Produktiv, Stunde 17 trägt 12 Stunden) in Kurzform: eine normale Stunde, eine Nullzeile, die
    Nachtragszeile mit getrennter Ladung/Entladung."""
    return [_z(5, 0.0, 0.5, 0.0, 0.5, 0.0),
            _z(10, 0.0, 0.0, 0.0, 0.0, -0.0, NULL, 0.0, 0.0),
            _z(17, 25.936, 30.127, 8.264, 17.695, -5.24, ALLE12, 11.776, 6.536)]


# ── Layer ────────────────────────────────────────────────────────────────────────────────────────────────────────────

def test_fenster_rechnung_der_nachtragszeile():
    b = bilanz_aus_stundenrows(_tag_12_11())
    assert b.stundenpaarung == PAARUNG_FENSTER and b.mindest_netzladung_kwh is None
    assert b.ueberschuss_kwh == pytest.approx(8.264 + 11.776)
    assert b.direktverbrauch_kwh == pytest.approx(25.936 - 20.04)
    assert b.defizit_kwh == pytest.approx(0.5 + 30.127 - (25.936 - 20.04))
    # PV = Direkt + Überschuss in jeder Zeile
    assert b.direktverbrauch_kwh + b.ueberschuss_kwh == pytest.approx(b.erzeugung_kwh)
    assert b.paarung_zeilen == ((17, 12, "beginn", "fenster"),)
    # Sprengsatz: ohne Marke wäre es die Paarung als eine Stunde (Überschuss 0)
    ohne = bilanz_aus_stundenrows([_z(r.stunde, r.pv_kw, r.verbrauch_kw, r.einspeisung_kw, r.netzbezug_kw, r.batterie_kw)
                                   for r in _tag_12_11()])
    assert ohne.stundenpaarung == PAARUNG_VOLL and ohne.ueberschuss_kwh == 0.0


def test_schwelle_0_1_kwh_paart_wie_bisher(monkeypatch):
    nacht = [_z(2, 0.05, 6.0, 0.0, 6.0, None, {"pv": 5, "einspeisung": 5, "netzbezug": 5})]
    b = bilanz_aus_stundenrows(nacht)
    assert b.stundenpaarung == PAARUNG_VOLL and b.defizit_kwh == pytest.approx(5.95)
    monkeypatch.setattr(tb, "FENSTER_SCHWELLE_KWH", 0.0)          # Sprengsatz: ohne Schwelle Fenster-Rechnung
    assert bilanz_aus_stundenrows(nacht).stundenpaarung == PAARUNG_FENSTER


def test_begrenzung_mit_mindest_netzladung():
    z = _z(13, 33.0, 10.0, 28.0, 35.0, -30.0, {"pv": 4, "einspeisung": 4, "netzbezug": 4, "batterie": 4}, 30.0, 0.0)
    b = bilanz_aus_stundenrows([z])
    assert b.ueberschuss_kwh == pytest.approx(33.0)                # auf die PV begrenzt
    assert b.direktverbrauch_kwh == pytest.approx(0.0)
    assert b.defizit_kwh == pytest.approx(10.0)
    assert b.mindest_netzladung_kwh == pytest.approx(28.0 + 30.0 - 33.0)
    # Sprengsatz: ohne Begrenzung (Überschuss = Einspeisung + Ladung) läge der Überschuss über der PV
    assert b.ueberschuss_kwh < 28.0 + 30.0


def test_ungleiche_n_nicht_rechenbar():
    z = _z(9, 4.433, None, 0.054, 4.266, -4.161, {"einspeisung": 9, "netzbezug": 9}, 4.2, 0.04)
    b = bilanz_aus_stundenrows([_z(8, 1.0, 2.0, 0.0, 1.0, 0.0), z])
    assert b.stundenpaarung == PAARUNG_NICHT_RECHENBAR
    assert b.paarung_zeilen == ((9, 9, "beginn", "ungleich"),)
    # gleiche n auf denselben Achsen (Sprengsatz der Bedingung): kein «nicht rechenbar» aus dieser Zeile
    gleich = _z(9, 4.433, 4.0, 0.054, 4.266, -4.161, {"pv": 9, "einspeisung": 9, "netzbezug": 9, "batterie": 9}, 4.2, 0.04)
    assert bilanz_aus_stundenrows([gleich]).stundenpaarung == PAARUNG_FENSTER


def test_k1_nur_pv_gebuendelt_bleibt_wie_bisher():
    """K1 (Korrekturrunde S2): ein Wechselrichter, der nachts keine Zeilen schreibt — die erste Zeile am Morgen trägt
    PV über n Stunden, Einspeisung und Netzbezug n = 1. Kein Erfassungs-Ausfall: kein Kennzeichen, die Zeile wie am HEAD
    (ohne gebildeten Verbrauch nicht gepaart), auch mit PV über der Schwelle. Sprengsatz der Bedingung «nur PV»: dieselbe
    Zeile mit gebündelter Einspeisung ist nicht rechenbar."""
    morgen = _z(6, 0.015, None, 0.0, 0.4, 0.0, {"pv": 10})
    tags = _z(7, 2.5, None, 1.0, 0.0, 0.0, {"pv": 10})
    for z in (morgen, tags):
        b = bilanz_aus_stundenrows([_z(5, 0.0, 0.5, 0.0, 0.5, 0.0), z, _z(12, 5.0, 2.0, 3.0, 0.0, 0.0)])
        assert b.stundenpaarung == PAARUNG_VOLL and b.paarung_zeilen == ()
        assert b.ueberschuss_kwh == pytest.approx(3.0) and b.defizit_kwh == pytest.approx(0.5)
    einsp = _z(7, 2.5, None, 1.0, 0.0, 0.0, {"pv": 10, "einspeisung": 10})
    assert bilanz_aus_stundenrows([einsp]).stundenpaarung == PAARUNG_NICHT_RECHENBAR


def test_k1_andere_achse_gebuendelt_nur_mit_pv_ueber_der_schwelle(monkeypatch):
    """K1: Netzbezug/Einspeisung gebündelt, PV n = 1 — «nicht rechenbar» nur mit PV über 0,1 kWh (6.11.2025: 4,43 kWh;
    17.5.2026: 0,38 kWh); nachts (PV ≤ 0,1) wie am HEAD, ohne Kennzeichen. Sprengsatz: Schwelle 0 ⇒ nicht rechenbar."""
    nacht = _z(3, 0.05, None, 0.0, 2.4, 0.0, {"einspeisung": 4, "netzbezug": 4})
    tag_6_11 = _z(9, 4.433, None, 0.054, 4.266, -4.161, {"einspeisung": 9, "netzbezug": 9}, 4.2, 0.04)
    tag_17_5 = _z(6, 0.381, None, 0.008, 7.259, 0.105, {"einspeisung": 11, "netzbezug": 11}, 0.0, 0.105)
    assert bilanz_aus_stundenrows([nacht]).stundenpaarung == PAARUNG_VOLL
    assert bilanz_aus_stundenrows([tag_6_11]).stundenpaarung == PAARUNG_NICHT_RECHENBAR
    assert bilanz_aus_stundenrows([tag_17_5]).stundenpaarung == PAARUNG_NICHT_RECHENBAR
    monkeypatch.setattr(tb, "FENSTER_SCHWELLE_KWH", 0.0)
    assert bilanz_aus_stundenrows([nacht]).stundenpaarung == PAARUNG_NICHT_RECHENBAR


def test_schwelle_auf_dem_verbrauch(monkeypatch):
    """E-4: auch ein Verbrauch ≤ 0,1 kWh paart wie bisher (K2 c). Sprengsatz: Schwelle 0 ⇒ Fenster-Rechnung."""
    z = _z(13, 3.0, 0.05, 2.95, 0.0, None, {"pv": 5, "einspeisung": 5, "netzbezug": 5})
    b = bilanz_aus_stundenrows([z])
    assert b.stundenpaarung == PAARUNG_VOLL and b.ueberschuss_kwh == pytest.approx(2.95)
    monkeypatch.setattr(tb, "FENSTER_SCHWELLE_KWH", 0.0)
    assert bilanz_aus_stundenrows([z]).stundenpaarung == PAARUNG_FENSTER


def test_mische_bilanz_reicht_kennzeichen_und_mindest_durch():
    """K2 f: `mische_bilanz` trägt Kennzeichen, Mindest-Netzladung und Zeilen der Stunden-Bilanz in die Kanal-Bilanz."""
    from backend.services.kanal.bilanz_leser import mische_bilanz

    kanal = bilanz_aus_stundenrows([_z(12, 5.0, 2.0, 3.0, 0.0, None)])
    z = _z(13, 33.0, 10.0, 28.0, 35.0, -30.0, {"pv": 4, "einspeisung": 4, "netzbezug": 4, "batterie": 4}, 30.0, 0.0)
    stunden = bilanz_aus_stundenrows([z])
    m = mische_bilanz(kanal, stunden)
    assert m.stundenpaarung == PAARUNG_FENSTER
    assert m.mindest_netzladung_kwh == pytest.approx(25.0) and m.paarung_zeilen == stunden.paarung_zeilen
    assert m.ueberschuss_kwh == pytest.approx(33.0) and m.erzeugung_kwh == kanal.erzeugung_kwh


def test_potenzial_und_netzbezug_spitze_lassen_gebuendelte_zeile_aus():
    """K2 d/e: Speicher-Potenzial zählt die Netzladung einer gebündelten Zeile nicht (die Ladung schon); die Attribute der
    Netzbezugs-Spitze lassen sie aus. Sprengsatz: dieselben Zeilen ohne Spannen zählen bzw. stehen darin."""
    from backend.api.routes.ha_export.anlage_steuerung import netzbezug_stundenmittel
    from backend.services.speicher_potential_service import ladung_und_netzladung

    normal = SimpleNamespace(batterie_kw=-1.0, netzbezug_kw=1.0, spannen=None)
    buendel = SimpleNamespace(batterie_kw=-5.0, netzbezug_kw=17.0, spannen=ALLE12)
    null = SimpleNamespace(batterie_kw=-0.0, netzbezug_kw=0.0, spannen=NULL)
    assert ladung_und_netzladung([normal, buendel, null]) == (6.0, 1.0)
    assert ladung_und_netzladung([normal, SimpleNamespace(**{**vars(buendel), "spannen": None})]) == (6.0, 6.0)
    assert [w for _z_, w in netzbezug_stundenmittel([normal, buendel, null])] == [1.0]
    assert [w for _z_, w in netzbezug_stundenmittel([normal, SimpleNamespace(**{**vars(buendel), "spannen": None})])] \
        == [1.0, 17.0]


def test_saldierte_batterie_nicht_rechenbar_ohne_speicher_fenster():
    sp = {"pv": 4, "einspeisung": 4, "netzbezug": 4, "batterie": 4}
    saldiert = _z(13, 20.0, 12.0, 6.0, 1.0, -3.0, sp)                # Bestandszeile: nur batterie_kw
    b = bilanz_aus_stundenrows([saldiert])
    assert b.stundenpaarung == PAARUNG_NICHT_RECHENBAR and b.paarung_zeilen[0][3] == "saldiert"
    from backend.services.energie_profil.stundenpaarung import GRUND_SALDIERT, grund_satz
    assert grund_satz(date(2026, 6, 20), b) == GRUND_SALDIERT.format(zeitraum="von 10 bis 14 Uhr")
    ohne_speicher = _z(13, 20.0, 12.0, 8.0, 0.0, None, {"pv": 4, "einspeisung": 4, "netzbezug": 4})
    b = bilanz_aus_stundenrows([ohne_speicher])
    assert b.stundenpaarung == PAARUNG_FENSTER and b.ueberschuss_kwh == pytest.approx(8.0)


def test_nullzeilen_tragen_nichts_bei():
    rows = [_z(h, 0.0, 0.0, 0.0, 0.0, -0.0, NULL, 0.0, 0.0) for h in range(6, 17)]
    b = bilanz_aus_stundenrows(rows)
    assert (b.ueberschuss_kwh, b.defizit_kwh, b.direktverbrauch_kwh) == (0.0, 0.0, 0.0)
    assert b.stundenpaarung == PAARUNG_VOLL                        # eine Nullzeile allein kennzeichnet nichts


def test_drei_zustaende_nicht_rechenbar_gewinnt():
    fenster = _tag_12_11()
    nicht = _z(9, 4.4, None, 0.05, 4.2, -4.1, {"einspeisung": 9, "netzbezug": 9}, 4.2, 0.04)
    assert bilanz_aus_stundenrows(fenster).stundenpaarung == PAARUNG_FENSTER
    assert bilanz_aus_stundenrows([nicht, *fenster]).stundenpaarung == PAARUNG_NICHT_RECHENBAR
    assert bilanz_aus_stundenrows([*fenster, nicht]).stundenpaarung == PAARUNG_NICHT_RECHENBAR


def test_ohne_spannen_bitgleich():
    rows = [_z(h, float(h % 7), 1.0 + h / 10, max(0.0, h % 7 - 1.0), 0.2, None) for h in range(24)]
    b = bilanz_aus_stundenrows(rows)
    u = d = dv = 0.0
    for r in rows:
        x = r.pv_kw - r.verbrauch_kw
        if x > 0:
            u += x
        else:
            d += -x
        dv += min(r.pv_kw, r.verbrauch_kw)
    assert (b.ueberschuss_kwh, b.defizit_kwh, b.direktverbrauch_kwh) == (u, d, dv)
    assert b.stundenpaarung == PAARUNG_VOLL and b.paarung_zeilen == ()


def test_monatsbilanz_zaehlt_und_laesst_nicht_rechenbare_aus():
    voll = bilanz_aus_stundenrows([_z(12, 5.0, 2.0, 3.0, 0.0, None)])
    fenster = bilanz_aus_stundenrows(_tag_12_11())
    nicht = bilanz_aus_stundenrows([_z(8, 1.0, 2.0, 0.0, 1.0, 0.0),
                                    _z(9, 4.4, None, 0.05, 4.2, -4.1, {"einspeisung": 9, "netzbezug": 9}, 4.2, 0.04)])
    m = monatsbilanz_aus_tagen([voll, fenster, nicht])
    assert (m.tage_mit_fenster_rechnung, m.tage_ohne_stundenpaarung) == (1, 1)
    assert m.ueberschuss_kwh == pytest.approx(voll.ueberschuss_kwh + fenster.ueberschuss_kwh)
    assert m.defizit_kwh == pytest.approx(voll.defizit_kwh + fenster.defizit_kwh)
    assert m.direktverbrauch_kwh == pytest.approx(voll.direktverbrauch_kwh + fenster.direktverbrauch_kwh)
    assert nicht.defizit_kwh > 0                                    # Sprengsatz: der Tag hätte etwas beigetragen


def test_neuer_zaehler_im_lauf_bleibt_ausser_betracht():
    """F12 (benannt): ein Zähler, dessen erste Zeile im Lauf liegt, ist für den Lauf nicht erfasst — das Fenster der
    übrigen Zähler steht unverändert."""
    t0 = 1_700_000_000 // H * H

    def reihe(rolle, beginn=0):
        return ZaehlerReihe(rolle, tuple(
            (t0 + h * H, 0.0 if 40 <= h < 43 else (2.0 if h == 43 else 0.5), None if h == beginn else H)
            for h in range(beginn, 60)))

    base = {"n": reihe("netzbezug"), "p": reihe("pv"), "e": reihe("einspeisung")}
    (f,) = stillstand_fenster(base)
    for b in (41, 42, 43):
        assert stillstand_fenster({**base, "neu": reihe("pv", b)}) == [f]


# ── Grund-Satz (Uhrzeiten, keine Energie) ────────────────────────────────────────────────────────────────────────────

def test_grund_satz_und_zeitraum():
    from backend.services.energie_profil.stundenpaarung import felder_der_tageszeile, zeitraum_text

    tag = date(2026, 6, 20)
    b = bilanz_aus_stundenrows([_z(17, 25.9, 30.1, 8.3, 17.7, -5.2, ALLE12, 11.8, 6.5)])
    f = felder_der_tageszeile(tag, b)
    assert f["stundenpaarung"] == PAARUNG_FENSTER
    assert f["stundenpaarung_grund"].startswith("Für die Stunden von 6 bis 18 Uhr gab es keine Stundenwerte")
    assert zeitraum_text(tag, datetime(2026, 6, 16, 10), datetime(2026, 6, 20, 19)) == "vom 16.6. 10 Uhr bis 20.6. 19 Uhr"
    assert zeitraum_text(tag, datetime(2026, 6, 20, 22), datetime(2026, 6, 21, 0)) == "von 22 bis 24 Uhr"
    # «nicht rechenbar» mit zwei Zählern verschiedener Spanne (Saat L5): ein Zeitraum, nicht zwei überlappende
    nicht = bilanz_aus_stundenrows([_z(13, 4.0, None, 1.0, 2.0, None, {"pv": 3, "einspeisung": 4, "netzbezug": 4}),
                                    _z(12, 3.0, None, 1.0, 2.0, None, {"pv": 2, "einspeisung": 3, "netzbezug": 3})])
    g = felder_der_tageszeile(tag, nicht)["stundenpaarung_grund"]
    assert nicht.stundenpaarung == PAARUNG_NICHT_RECHENBAR and g.startswith("Für die Stunden von 10 bis 14 Uhr haben nur einzelne Zähler Stundenwerte geliefert")
    voll = felder_der_tageszeile(tag, bilanz_aus_stundenrows([_z(12, 5.0, 2.0, 3.0, 0.0, None)]))
    assert voll == {"stundenpaarung": None, "stundenpaarung_grund": None, "mindest_netzladung_kwh": None}


def test_ziel_befund():
    from backend.services.daten_checker import ziele
    from backend.services.daten_checker.kategorien import link_aus_ziel

    assert link_aus_ziel(ziele.ziel_befund("zaehler_versatz")) == "/einstellungen/daten?block=datenchecker&befund=zaehler_versatz"
    with pytest.raises(ValueError):
        ziele.ziel_befund("gibt_es_nicht")


# ── DB: Kanal-Tag (M07) ──────────────────────────────────────────────────────────────────────────────────────────────

from backend.services.kanal import bilanz_leser, merken, stillstand  # noqa: E402
from backend.tests import kanal_bilanz_gleichheit as kg  # noqa: E402
from backend.tests.test_n799_stillstand_lesestelle import _bereich, _einfrieren, _fein, _kid, _marken, _stunden  # noqa: E402
from sqlalchemy import text  # noqa: E402


@pytest.fixture
def uhr(monkeypatch):
    monkeypatch.setattr(bilanz_leser, "uhr", lambda: kg.JETZT_TS)
    merken.leeren()
    yield
    merken.leeren()


async def _anlage(ds):
    from sqlalchemy import select

    from backend.models.anlage import Anlage

    return (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()


async def test_tage_werte_fenster_rechnung_am_kanal_tag(uhr):
    from backend.services.energie_profil.kanal_stunden import ueberschuss_defizit_der_tage
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    tag = date(2026, 6, 20)
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        vorher = {z.datum: z for z in await baue_tage_werte(ds.db, await _anlage(ds), tag, tag)}[tag]
        await _einfrieren(ds, datetime(2026, 6, 20, 10), 3)
        merken.leeren()
        t = {z.datum: z for z in await baue_tage_werte(ds.db, await _anlage(ds), tag, tag)}[tag]
        ud = (await ueberschuss_defizit_der_tage(ds.db, ds.aid, tag, tag))[tag]
    assert vorher.stundenpaarung is None and vorher.stundenpaarung_grund is None
    assert t.stundenpaarung == PAARUNG_FENSTER
    assert t.stundenpaarung_grund.startswith("Für die Stunden von 10 bis 14 Uhr")
    assert t.direktverbrauch + t.ueberschuss_kwh == pytest.approx(t.erzeugung, abs=0.01)
    assert (t.erzeugung, t.einspeisung, t.netzbezug) == (vorher.erzeugung, vorher.einspeisung, vorher.netzbezug)
    assert ud[0] == pytest.approx(t.ueberschuss_kwh, abs=1e-3) and ud[1] == pytest.approx(t.defizit_kwh, abs=1e-3)


async def test_f3_einzeltag_gleich_bereich_ueber_die_monatsgrenze(uhr, monkeypatch):
    """F3: ein Stillstand von 13 Tagen (20.06. 10 Uhr bis 03.07. 10 Uhr) — der Einzeltag 22.06. trägt dieselben
    Nullzeilen wie der Bereich. Sprengsatz: mit dem alten Nachlauf (7 Tage) fehlen sie am Einzeltag."""
    tag = date(2026, 6, 22)
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        await _einfrieren(ds, datetime(2026, 6, 20, 10), 13 * 24)
        einzel = _marken(await _stunden(ds, tag))
        bereich = _marken((await _bereich(ds, date(2026, 6, 19), date(2026, 7, 3)))[tag])
        merken.leeren()
        monkeypatch.setattr(stillstand, "NACHLAUF_TAGE", 7)
        alt = _marken(await _stunden(ds, tag))
    assert einzel == bereich and len(einzel) == 24 and all(set(m.values()) == {0} for m in einzel.values())
    assert alt == {}


async def test_tagesvergleich_alle_beruehrten_tage(uhr):
    from backend.services.energie_profil.vergleichstage import tage_ohne_tagesvergleich

    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        await _einfrieren(ds, datetime(2026, 6, 13, 10), 72)
        aus = await tage_ohne_tagesvergleich(ds.db, ds.aid, "pv", von=date(2026, 6, 10), bis=date(2026, 6, 20))
        merken.leeren()
        echt = stillstand.erster_tag_der_fenster_ueber_mitternacht
        with pytest.MonkeyPatch.context() as mp:      # Sprengsatz: nur der Nachtragstag (wie S1) ⇒ 13./14.06. fehlen
            async def _nur_nachtrag(db, aid, von, bis):
                return {d: d for d in await echt(db, aid, von, bis)}
            mp.setattr(stillstand, "erster_tag_der_fenster_ueber_mitternacht", _nur_nachtrag)
            alt = await tage_ohne_tagesvergleich(ds.db, ds.aid, "pv", von=date(2026, 6, 10), bis=date(2026, 6, 20))
    assert {date(2026, 6, 13), date(2026, 6, 14), date(2026, 6, 15), date(2026, 6, 16)} <= aus
    assert not {date(2026, 6, 13), date(2026, 6, 14)} <= alt


# ── DB: Bestandszeilen (Monat, Ladepreis) ────────────────────────────────────────────────────────────────────────────

JETZT = datetime(2026, 9, 26)


def _tep(aid, d, h, **kw):
    from backend.models.tages_energie_profil import TagesEnergieProfil

    kw.setdefault("source_provenance", {})
    return TagesEnergieProfil(anlage_id=aid, datum=d, stunde=h, **kw)


async def _bestand(db):
    from backend.models.anlage import Anlage

    a = Anlage(anlagenname="Leser S2", leistung_kwp=10.0)
    db.add(a)
    await db.flush()
    return a


async def test_monat_heatmap_und_zaehler(db):
    from backend.api.routes.energie_profil.views import get_monatsauswertung

    a = await _bestand(db)
    d1, d2 = date(2026, 5, 10), date(2026, 5, 11)
    db.add(_tep(a.id, d1, 12, pv_kw=8.0, einspeisung_kw=6.0, netzbezug_kw=0.0, verbrauch_kw=2.0))
    db.add(_tep(a.id, d1, 13, pv_kw=40.0, einspeisung_kw=35.0, netzbezug_kw=0.0, verbrauch_kw=5.0,
                spannen={"pv": 4, "einspeisung": 4, "netzbezug": 4}))
    db.add(_tep(a.id, d2, 12, pv_kw=8.0, einspeisung_kw=6.0, netzbezug_kw=0.0, verbrauch_kw=2.0))
    db.add(_tep(a.id, d2, 13, pv_kw=9.0, einspeisung_kw=7.0, netzbezug_kw=1.0, verbrauch_kw=None,
                spannen={"einspeisung": 3, "netzbezug": 3}))
    await db.commit()
    m = await get_monatsauswertung(a.id, jahr=2026, monat=5, top_n=10, db=db)
    assert (m.tage_mit_fenster_rechnung, m.tage_ohne_stundenpaarung) == (1, 1)
    assert m.ueberschuss_kwh == pytest.approx(6.0 + 35.0)            # d1: 6 + Fenster 35; d2 nicht in der Summe
    assert {(c.tag, c.stunde) for c in m.heatmap} == {(10, 11), (11, 11)}   # die gebündelten Zeilen fallen aus
    assert m.pv_kwh == pytest.approx(65.0)                            # Energie bleibt in der Summe


async def test_f5_ladepreis_erfassungsluecke_statt_keine_netzladung(db):
    from backend.services.speicher_wirtschaftlichkeit import berechne_effektiver_ladepreis

    a = await _bestand(db)
    d = date(2026, 5, 10)
    db.add(_tep(a.id, d, 10, batterie_kw=1.0, netzbezug_kw=0.0))          # Entladung, keine Netzladung
    db.add(_tep(a.id, d, 18, batterie_kw=-5.0, netzbezug_kw=17.0, spannen={"batterie": 12, "netzbezug": 12}))
    await db.commit()
    r = await berechne_effektiver_ladepreis(db, anlage_id=a.id, von=d, bis=d)
    assert r.quelle == "erfassungsluecke" and r.effektiver_ladepreis_cent is None
    # Sprengsatz: ohne die gebündelte Zeile ist es «keine Netzladung»
    from sqlalchemy import text

    await db.execute(text("DELETE FROM tages_energie_profil WHERE anlage_id = :a AND stunde = 18"), {"a": a.id})
    await db.commit()
    assert (await berechne_effektiver_ladepreis(db, anlage_id=a.id, von=d, bis=d)).quelle == "keine-netzladung"


def test_sizing_und_potential_lassen_gebuendelte_mengen_aus():
    from backend.services.speicher_sizing_service import _als_sizing_stunde

    z = SimpleNamespace(datum=date(2026, 5, 10), stunde=17, pv_kw=25.9, verbrauch_kw=30.1, soc_prozent=50.0,
                        batterie_kw=-5.2, einspeisung_kw=8.3, netzbezug_kw=17.7, spannen=ALLE12,
                        created_at=JETZT)
    s = _als_sizing_stunde(z)
    assert (s.pv_kwh, s.verbrauch_kwh, s.einspeisung_kwh, s.batterie_kwh, s.netzbezug_kwh) == (None,) * 5
    z.spannen = None
    s = _als_sizing_stunde(z)
    assert (s.pv_kwh, s.verbrauch_kwh, s.einspeisung_kwh) == (25.9, 30.1, 8.3)



# ── K2 (Korrekturrunde S2): Proben mit Wert-Soll am Kanal-Tag ────────────────────────────────────────────────────────

async def _alle_mengen_kanaele(ds) -> dict[str, int]:
    return {k: i for i, k in (await ds.db.execute(text(
        "SELECT id, key FROM kanal WHERE anlage_id = :a AND art = 'sum'"), {"a": ds.aid})).all()}


async def _delta(ds, kid: int, von_ts: int, bis_ts: int) -> float:
    """Δ des Zählers über ``[von_ts, bis_ts]`` (Stand der Stunde vor ``von_ts`` bis Stand der Stunde ``bis_ts``)."""
    q = "SELECT sum FROM kanal_statistik WHERE kanal_id = :k AND start_ts = :t"
    a = (await ds.db.execute(text(q), {"k": kid, "t": von_ts - H})).scalar_one()
    b = (await ds.db.execute(text(q), {"k": kid, "t": bis_ts})).scalar_one()
    return b - a


async def test_k2_nicht_rechenbar_liefert_none_an_tage_werte_und_lesestelle(uhr):
    """K2 a: Netzbezug und Einspeisung ohne Zeilen 10–12 Uhr, PV läuft — die Zeile 13 Uhr trägt Netz/Einspeisung n = 4,
    PV n = 1 und PV über der Schwelle ⇒ «nicht rechenbar»: `tage-werte` zeigt die drei Spalten leer mit Kennzeichen, die
    Lesestelle `ueberschuss_defizit_der_tage` liefert `(None, None)` (Rollup, `/tage`, HA-Sensor)."""
    from backend.services.energie_profil.kanal_stunden import ueberschuss_defizit_der_tage
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    tag = date(2026, 6, 20)
    async with kg.datenstand("achsen", "M07", "HA") as ds:
        await _fein(ds)
        for key in ("basis:netzbezug", "basis:einspeisung"):
            await ds.db.execute(text("DELETE FROM kanal_statistik WHERE kanal_id = :k AND start_ts >= :a AND start_ts < :b"),
                                {"k": await _kid(ds, key), "a": int(datetime(2026, 6, 20, 10).timestamp()),
                                 "b": int(datetime(2026, 6, 20, 13).timestamp())})
        await ds.db.commit()
        merken.invalidiere(ds.aid)
        t = {z.datum: z for z in await baue_tage_werte(ds.db, await _anlage(ds), tag, tag)}[tag]
        ud = (await ueberschuss_defizit_der_tage(ds.db, ds.aid, tag, tag))[tag]
    assert t.stundenpaarung == PAARUNG_NICHT_RECHENBAR
    assert (t.direktverbrauch, t.ueberschuss_kwh, t.defizit_kwh) == (None, None, None)
    assert t.erzeugung is not None and t.netzbezug is not None                # die Mengen bleiben
    assert ud == (None, None)


async def test_k2_kanal_tag_mit_speicher_fenster_mit_wert_soll(uhr):
    """K2 b: Kanal-Tag mit zwei Speichern (M04, Ladung 10–16 Uhr; M02 friert in jeder Nacht ein und sperrt die Häufigkeit), Stillstand 10–12 Uhr aller Zähler, Nachtrag 13 Uhr. Die
    Nachtragszeile trägt Ladung und Entladung **getrennt aus den Zählern** (Δ über das Fenster, hier unabhängig per SQL
    gelesen), und der Überschuss des Tages ist Σ max(0, PV − V) der übrigen Stunden + min(PV_w, Einspeisung_w + Ladung_w)
    — ein Wert-Soll, keine Identität. Rot, wenn der Adapter Ladung und Entladung vertauscht oder nicht durchreicht."""
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    tag = date(2026, 6, 20)
    async with kg.datenstand("achsen", "M04", "HA") as ds:
        kanaele = {k: i for k, i in (await _alle_mengen_kanaele(ds)).items() if not k.startswith("abgeleitet:")}
        for kid in kanaele.values():
            await ds.db.execute(text("UPDATE kanal_statistik SET sum = sum * 1.00731 WHERE kanal_id = :k"), {"k": kid})
        await ds.db.commit()
        await _einfrieren(ds, datetime(2026, 6, 20, 10), 3, keys=tuple(kanaele))
        merken.leeren()
        zeilen = (await _bereich(ds, tag, tag))[tag]
        t = {z.datum: z for z in await baue_tage_werte(ds.db, await _anlage(ds), tag, tag)}[tag]
        von, nachtrag = int(datetime(2026, 6, 20, 10).timestamp()), int(datetime(2026, 6, 20, 13).timestamp())
        lad = sum([await _delta(ds, i, von, nachtrag) for k, i in kanaele.items() if k.endswith(":ladung_kwh")
                   and k.startswith("inv:")])
        ent = sum([await _delta(ds, i, von, nachtrag) for k, i in kanaele.items() if k.endswith(":entladung_kwh")])
    z13 = zeilen[13]
    assert z13.spannen["batterie"] == 4 and lad > 1.0
    assert z13.speicher_ladung_kw == pytest.approx(lad, abs=2e-3)
    assert z13.speicher_entladung_kw == pytest.approx(ent, abs=2e-3)
    uebrige = sum(max(0.0, z.pv_kw - z.verbrauch_kw) for h, z in zeilen.items()
                  if h != 13 and z.pv_kw is not None and z.verbrauch_kw is not None and z.spannen is None)
    soll = uebrige + min(z13.pv_kw, z13.einspeisung_kw + lad)
    assert t.stundenpaarung == PAARUNG_FENSTER
    assert t.ueberschuss_kwh == pytest.approx(soll, abs=5e-3)
