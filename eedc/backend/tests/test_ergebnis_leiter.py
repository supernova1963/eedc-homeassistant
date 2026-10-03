"""Ergebnis-Leiter im Layer (``core/berechnungen/ergebnis.py``) — Einheitsproben ohne Datenbank.

Paket „Ergebnisgrößen Monat/Jahr in den Layer" (03.10.2026). Die Proben gegen echte Einstiege (Monatsroute,
Jahresroute, Übersicht, PDF, HA-Export) stehen in ``test_ergebnis_symmetrie_monat_jahr.py`` und
``test_ergebnis_monat_probe.py``; hier stehen die Regeln selbst.
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen.ergebnis import (
    ErgebnisEingang,
    berechne_ergebnis,
    falte_posten,
    falte_zeitraum,
    jahr_vergleich_aus,
    mittel_jahre,
    quote_paarweise,
    soll_erfuellung,
    ust_anteil_euro,
    ust_satz_euro_je_kwh,
)
from backend.core.berechnungen.ust_eigenverbrauch import UstJahresanteil, berechne_ust_eigenverbrauch


# ── Die Leiter ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_drei_stufen_mit_allen_posten():
    e = ErgebnisEingang(
        einspeise_erloes=32.0, ev_ersparnis=180.0, bkw_rest_ersparnis=4.5, erzeuger_erloes=3.0,
        sonstige_netto=-10.0, ust_anteil=5.7, wp_ersparnis=40.0, emob_ersparnis=25.0,
        stromkosten=53.48, betriebskosten=10.0,
    )
    leiter = berechne_ergebnis(e)
    assert leiter.netto_ertrag == pytest.approx(32 + 180 + 4.5 + 3 - 10 - 5.7)
    assert leiter.vor_betriebskosten == pytest.approx(leiter.netto_ertrag + 40 + 25 - 53.48)
    assert leiter.ergebnis == pytest.approx(leiter.vor_betriebskosten - 10)
    # Herleitung: jeder Summand einzeln, Stromrechnung und Betriebskosten mit Vorzeichen −.
    namen = [w.name for w in leiter.herleitung["ergebnis"].eingesetzte_werte]
    assert namen == ["Einspeise-Erlös", "Eigenverbrauchs-Ersparnis", "BKW-Ersparnis", "Erlös eigener Satz",
                     "Sonstige Positionen", "USt auf Eigenverbrauch", "WP-Ersparnis", "E-Mobilität-Ersparnis",
                     "Stromrechnung", "Betriebskosten"]
    assert sum(w.betrag for w in leiter.herleitung["ergebnis"].eingesetzte_werte) == pytest.approx(leiter.ergebnis)
    assert leiter.herleitung["ergebnis"].formel.startswith("Einspeise-Erlös + Eigenverbrauchs-Ersparnis")
    assert " − Stromrechnung − Betriebskosten" in leiter.herleitung["ergebnis"].formel


def test_optionale_posten_nur_wenn_ungleich_null():
    """N-600-Zuschnitt (Gernot 02.10.): WP/E-Mob/BKW/Erzeuger/USt/Sonstiges erscheinen nur, wenn ≠ 0."""
    leiter = berechne_ergebnis(ErgebnisEingang(
        einspeise_erloes=19.54, ev_ersparnis=283.85, wp_ersparnis=0.0, emob_ersparnis=None,
        stromkosten=53.48, betriebskosten=0.0,
    ))
    namen = [w.name for w in leiter.herleitung["ergebnis"].eingesetzte_werte]
    assert namen == ["Einspeise-Erlös", "Eigenverbrauchs-Ersparnis", "Stromrechnung", "Betriebskosten"]
    # Der Melderfall #398 (Blockmove): 19,54 + 283,85 − 53,48 − 0,00 = 249,91.
    assert round(leiter.ergebnis, 2) == 249.91
    assert round(leiter.netto_ertrag, 2) == 303.39


@pytest.mark.parametrize("fehlt,stufen_none", [
    ("einspeise_erloes", ("netto_ertrag", "vor_betriebskosten", "ergebnis")),
    ("ev_ersparnis", ("netto_ertrag", "vor_betriebskosten", "ergebnis")),
    ("stromkosten", ("vor_betriebskosten", "ergebnis")),
])
def test_pflichtposten_fehlt_stufe_ist_none(fehlt, stufen_none):
    """Monatsregel (§3.3): eine Stufe ist None, wenn einer ihrer Pflichtposten fehlt — keine 0."""
    werte = dict(einspeise_erloes=10.0, ev_ersparnis=20.0, stromkosten=5.0, betriebskosten=1.0)
    werte[fehlt] = None
    leiter = berechne_ergebnis(ErgebnisEingang(**werte))
    for stufe in ("netto_ertrag", "vor_betriebskosten", "ergebnis"):
        if stufe in stufen_none:
            assert getattr(leiter, stufe) is None
        else:
            assert getattr(leiter, stufe) is not None
    assert leiter.fehlende_posten, "der fehlende Pflichtposten wird genannt (P4)"


def test_betriebskosten_duerfen_fehlen():
    leiter = berechne_ergebnis(ErgebnisEingang(einspeise_erloes=10.0, ev_ersparnis=20.0, stromkosten=5.0))
    assert leiter.ergebnis == pytest.approx(25.0)


def test_optionaler_posten_einer_vorhandenen_komponente_wird_genannt():
    leiter = berechne_ergebnis(ErgebnisEingang(
        einspeise_erloes=10.0, ev_ersparnis=20.0, stromkosten=5.0, wp_ersparnis=None,
        komponenten_vorhanden=frozenset({"waermepumpe"}),
    ))
    assert leiter.ergebnis == pytest.approx(25.0)
    assert "WP-Ersparnis" in leiter.fehlende_posten


def test_layer_rundet_nicht():
    """G8: ein rundender Layer wäre höchstens zu einer Seite bitgleich."""
    leiter = berechne_ergebnis(ErgebnisEingang(einspeise_erloes=0.1, ev_ersparnis=0.2, stromkosten=0.0))
    assert leiter.netto_ertrag == 0.1 + 0.2  # 0.30000000000000004 — ungerundet


# ── USt-Satz (E1) ────────────────────────────────────────────────────────────────────────────────────────────────

def test_summe_der_monatsanteile_ist_der_jahreswert():
    """N-130: Σ ungerundeter Monatsanteile == berechne_ust_eigenverbrauch des Jahres (keine zweite Formel)."""
    ev_monate = [120.0, 180.0, 260.0, 300.0, 310.0, 330.0, 320.0, 300.0, 250.0, 190.0, 130.0, 100.0]
    anteil = UstJahresanteil(jahr=2025, eigenverbrauch_kwh=sum(ev_monate), pv_kwh=9800.0, monate=12)
    kw = dict(bemessungsgrundlage_euro=17600.0, betriebskosten_jahr_euro=720.0, ust_satz_prozent=19.0)
    satz = ust_satz_euro_je_kwh(anteil, **kw)
    jahr = berechne_ust_eigenverbrauch([anteil], **kw)
    assert sum(ust_anteil_euro(ev, satz) for ev in ev_monate) == pytest.approx(jahr, rel=1e-12)
    assert jahr > 0


def test_satz_eines_jahres_ohne_pv_ist_null():
    anteil = UstJahresanteil(jahr=2025, eigenverbrauch_kwh=0.0, pv_kwh=0.0, monate=3)
    assert ust_satz_euro_je_kwh(anteil, bemessungsgrundlage_euro=10000, betriebskosten_jahr_euro=100,
                                ust_satz_prozent=19) == 0.0


# ── SOLL-Erfüllung (N-69, N-356) ──────────────────────────────────────────────────────────────────────────────────

def test_soll_erfuellung_augustzahl_winterborn():
    """Umgezogen aus ``lib/sollErfuellung.test.ts`` (03.10.2026) — dieselben Zahlen (Winterborn, 04.08.2026)."""
    s = soll_erfuellung(264.75, 179.1, 4, 31, 1387.9)
    assert round(s.prozent) == 148  # gekürzt — nicht 19 %
    assert round(s.monat_prozent) == 19  # Fortschritt gegen den ganzen Monat
    assert s.fenster_text == "anteilig · 4 von 31 Tagen"
    zukunft = soll_erfuellung(0.0, 0.0, 0, 30, None)
    assert zukunft.prozent is None and zukunft.monat_prozent is None
    jahr = soll_erfuellung(9715.02, 8107.8, 216, 243)
    assert round(jahr.prozent) == 120 and jahr.fenster_text == "anteilig · 216 von 243 Tagen"


def test_soll_erfuellung_wortlaut_wie_client():
    s = soll_erfuellung(412.0, 450.0, 4, 31, 1387.9)
    assert s.prozent == pytest.approx(412 / 450 * 100)
    assert s.monat_prozent == pytest.approx(412 / 1387.9 * 100)
    assert s.fenster_text == "anteilig · 4 von 31 Tagen"
    voll = soll_erfuellung(412.0, 450.0, 31, 31, 450.0)
    assert voll.fenster_text is None
    assert soll_erfuellung(412.0, 0.0, 0, 31).prozent is None  # SOLL 0 hat keine Quote
    assert soll_erfuellung(None, 450.0, 31, 31).prozent is None


# ── Zeitraum (N-584, G2) ─────────────────────────────────────────────────────────────────────────────────────────

def _monat(m, **kw):
    basis = dict(monat=m, einspeise_erloes_euro=10.0, ev_ersparnis_euro=20.0, netzbezug_kosten_euro=5.0)
    basis.update(kw)
    return basis


def test_n584_quote_paarweise_statt_198_prozent():
    """Der Melderfall #421: acht Monate mit EV 559 und Gesamtverbrauch 559 (Volleinspeiser-Muster, EV = GV),
    der laufende September mit EV 549 und OHNE Gesamtverbrauch. Σ je Feld ⇒ 1 108 ÷ 559 = 198 %."""
    monate = [dict(monat=m, eigenverbrauch_kwh=559 / 8, gesamtverbrauch_kwh=559 / 8) for m in range(1, 9)]
    monate.append(dict(monat=9, eigenverbrauch_kwh=549.0, gesamtverbrauch_kwh=None))
    q = quote_paarweise(monate, "eigenverbrauch_kwh", "gesamtverbrauch_kwh")
    assert q.wert == pytest.approx(100.0)
    assert q.zaehler == pytest.approx(559.0) and q.nenner == pytest.approx(559.0)
    assert q.fenster_text == "aus 8 von 9 Monaten"
    j = falte_zeitraum(monate, 2026)
    assert j["autarkie_prozent"] == pytest.approx(100.0)
    assert j["autarkie_zaehler_kwh"] == pytest.approx(559.0)
    assert j["autarkie_fenster"] == "aus 8 von 9 Monaten"
    assert j["eigenverbrauch_kwh"] == pytest.approx(1108.0), "die Summe selbst bleibt die Summe aller Monate"


def test_g2_jahr_ohne_stromrechnung_eines_monats_hat_kein_ergebnis():
    monate = [_monat(m) for m in range(1, 9)] + [_monat(9, netzbezug_kosten_euro=None)]
    j = falte_zeitraum(monate, 2026)
    assert j["netto_ertrag_euro"] == pytest.approx(9 * 30.0), "Stufe 1 hängt nicht an der Stromrechnung"
    assert j["ergebnis_vor_betriebskosten_euro"] is None
    assert j["ergebnis_euro"] is None
    assert "Stromrechnung (Sep 2026)" in j["fehlende_posten"]


def test_jahr_ergebnis_ist_summe_der_monatsergebnisse():
    monate = [_monat(m, betriebskosten_anteilig_euro=1.0, sonstige_netto_euro=0.5, wp_ersparnis_euro=2.0)
              for m in range(1, 13)]
    j = falte_zeitraum(monate, 2025)
    einzeln = [berechne_ergebnis(ErgebnisEingang(
        einspeise_erloes=10.0, ev_ersparnis=20.0, stromkosten=5.0, betriebskosten=1.0, sonstige_netto=0.5,
        wp_ersparnis=2.0)).ergebnis for _ in range(12)]
    assert j["ergebnis_euro"] == pytest.approx(sum(einzeln))
    e = falte_posten(monate, 2025)
    assert e.stromkosten == pytest.approx(60.0)


def test_vergleichsjahre_paarweise():
    zeilen = [dict(jahr=2024, monat=m, eigenverbrauch_kwh=100.0, gesamtverbrauch_kwh=200.0) for m in range(1, 7)]
    zeilen.append(dict(jahr=2024, monat=7, eigenverbrauch_kwh=500.0, gesamtverbrauch_kwh=None))
    vj = jahr_vergleich_aus(zeilen, 2024)
    assert vj["autarkie"] == pytest.approx(50.0)
    assert vj["monate"] == list(range(1, 8))
    assert vj["autarkie_zaehler"] == pytest.approx(600.0) and vj["autarkie_nenner"] == pytest.approx(1200.0)
    # Zweites Jahr 300 ÷ 300 = 100 %. Mittel der Prozente wäre (50 + 100) / 2 = 75 %; die Quote der gemittelten
    # paarweisen Mengen ist (600 + 300) / 2 ÷ (1200 + 300) / 2 = 60 % — gewichtet nach Verbrauch, wie jede Quote.
    oe = mittel_jahre([vj, dict(vj, jahr=2023, autarkie_zaehler=300.0, autarkie_nenner=300.0)], None)
    assert oe["autarkie"] == pytest.approx(60.0)
    assert oe["count"] == 2
