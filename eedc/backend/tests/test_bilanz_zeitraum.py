"""Weg 2 im Layer (HA-Bauform E4a-2, Bauplan §6b): ``pv_verteilung.loese_pv_zeitraum_auf`` (W2-R1/R2/R3/R5) und
``bilanz_zeitraum.komponiere_bilanz_zeitraum`` — reine Funktionen, Zahlen aus den Minimalfällen der Probe-Rechnung
(``plans/ha-bauform-werkzeug/probe-weg2/minimalfaelle.py``) und den Matrix-Formen.

Jede Regel hat hier eine Probe, die rot wird, wenn die Regel fällt (Sprengsätze im Bericht E4a-2)."""

from __future__ import annotations

import pytest

from backend.core.berechnungen.bilanz_zeitraum import KWP_ANTEIL, Eingang, komponiere_bilanz_zeitraum
from backend.core.berechnungen.pv_verteilung import PvTraeger, loese_pv_zeitraum_auf

SUED, WEST, BKW, K1, K2 = 1, 2, 3, 4, 5


def _t(i, typ, kwp, parent=None):
    return PvTraeger(i, typ, kwp, parent)


STRINGS_BKW = [_t(SUED, "pv-module", 6.0), _t(WEST, "pv-module", 4.0), _t(BKW, "balkonkraftwerk", 0.8)]
MIT_KINDERN = STRINGS_BKW + [_t(K1, "pv-module", 0.3, BKW), _t(K2, "pv-module", 0.5, BKW)]


def _r(d):
    return {k: round(v, 6) for k, v in d.items()}


def test_r1_gemessen_traegt_sein_delta_und_wird_nicht_skaliert():
    """Begrenzung (Minimalfall 2, Form V): Süd misst 12,6 > Anlagenzähler 12,096 — Süd bleibt 12,6, West bekommt 0."""
    traeger = [_t(SUED, "pv-module", 6.0), _t(WEST, "pv-module", 4.0)]
    r = loese_pv_zeitraum_auf(traeger=traeger, eigen={SUED: 12.6}, anlagenzaehler_kwh=12.096)
    assert _r(r.werte) == {SUED: 12.6, WEST: 0.0}
    assert r.verteilt == frozenset({WEST})
    # R3 (Wortlaut nach H2): die PV-Summe ist Σ Geräte; der Anlagenzähler füllt nur. Die Differenz wird als
    # Wandlungsverluste geführt (N-588, nicht bewertet).
    assert r.bilanz_kwh == pytest.approx(12.6)
    assert r.geraete_kwh == pytest.approx(12.6)
    assert r.wandlungsverluste_kwh == pytest.approx(0.504)


def test_r2_rest_nach_kwp_auf_die_luecken():
    """Lücken-Tag (Minimalfall 3): Anlage 21, Süd 12 und West 6 gemessen, BKW ohne — BKW 3,0 mit Marke."""
    r = loese_pv_zeitraum_auf(traeger=STRINGS_BKW, eigen={SUED: 12.0, WEST: 6.0}, anlagenzaehler_kwh=21.0)
    assert _r(r.werte) == {SUED: 12.0, WEST: 6.0, BKW: 3.0}
    assert r.verteilt == frozenset({BKW})
    assert r.bilanz_kwh == 21.0 and r.wandlungsverluste_kwh == 0.0


def test_r2_kinder_sind_die_luecke_ihres_bkw():
    """F09a: BKW-Zähler 3,0, Kinder ohne Zähler (0,3/0,5 kWp) — die Kinder teilen 3,0 nach kWp (Marke), das BKW
    trägt keinen Eintrag; der Anlagenzähler füllt die Strings (21 − 3 = 18 nach 6 : 4)."""
    r = loese_pv_zeitraum_auf(traeger=MIT_KINDERN, eigen={BKW: 3.0}, anlagenzaehler_kwh=21.0)
    assert _r(r.werte) == {SUED: 10.8, WEST: 7.2, K1: 1.125, K2: 1.875}
    assert r.verteilt == frozenset({SUED, WEST, K1, K2})
    assert BKW not in r.werte


def test_r2_bkw_rest_geht_nicht_an_das_bkw_sondern_in_den_anlagenrest():
    """Minimalfall 1: BKW 3,0 mit zwei gemessenen Kindern (1,2 + 1,2) — die Kinder messen weniger als ihr BKW; der
    Rest 0,6 hat keinen Empfänger unter dem BKW und landet über den Anlagenzähler bei West (6,6). Ohne
    Anlagenzähler fällt er weg."""
    eigen = {SUED: 12.0, BKW: 3.0, K1: 1.2, K2: 1.2}
    r = loese_pv_zeitraum_auf(traeger=MIT_KINDERN, eigen=eigen, anlagenzaehler_kwh=21.0)
    assert _r(r.werte) == {SUED: 12.0, WEST: 6.6, K1: 1.2, K2: 1.2}
    o = loese_pv_zeitraum_auf(traeger=MIT_KINDERN, eigen=eigen, anlagenzaehler_kwh=None)
    assert _r(o.werte) == {SUED: 12.0, K1: 1.2, K2: 1.2}
    assert o.fehlt == frozenset({WEST}) and o.bilanz_kwh == pytest.approx(14.4) and o.wandlungsverluste_kwh is None


def test_r2_selbst_tragendes_bkw_ohne_wert_bekommt_seinen_anteil_n621():
    r = loese_pv_zeitraum_auf(traeger=STRINGS_BKW, eigen={SUED: 12.0}, anlagenzaehler_kwh=21.0)
    assert _r(r.werte) == {SUED: 12.0, WEST: 9.0 * 4 / 4.8, BKW: round(9.0 * 0.8 / 4.8, 6)}


def test_r2_selbst_tragendes_bkw_mit_wert_ist_ein_gemessenes_geraet_n611():
    """Süd 12 und BKW 3 gemessen, West ohne, Anlagenzähler 21 — West bekommt 21 − 12 − 3 = 6, nicht 9."""
    r = loese_pv_zeitraum_auf(traeger=STRINGS_BKW, eigen={SUED: 12.0, BKW: 3.0}, anlagenzaehler_kwh=21.0)
    assert _r(r.werte) == {SUED: 12.0, WEST: 6.0, BKW: 3.0}
    assert r.geraete_kwh == pytest.approx(21.0)


def test_r5_untergrenze_einmal_je_zeitraum():
    """Zwei Tage (Süd 12,6 bei 12,096 und Süd 12,6 bei 17,28) gegen den Monat: am Tag klemmt der Rest des ersten
    auf 0 — Σ Tage West 4,68, Monat West 4,176 (der Monat klemmt einmal über die Summe). Die Bilanz-PV ist in
    beiden Fällen Σ Geräte — sie folgt der Aufteilung (Σ Tage 30,48 gegen Monat 29,376)."""
    traeger = [_t(SUED, "pv-module", 6.0), _t(WEST, "pv-module", 4.0)]
    t1 = loese_pv_zeitraum_auf(traeger=traeger, eigen={SUED: 12.6}, anlagenzaehler_kwh=12.096)
    t2 = loese_pv_zeitraum_auf(traeger=traeger, eigen={SUED: 12.6}, anlagenzaehler_kwh=17.28)
    m = loese_pv_zeitraum_auf(traeger=traeger, eigen={SUED: 25.2}, anlagenzaehler_kwh=29.376)
    assert t1.werte[WEST] + t2.werte[WEST] == pytest.approx(4.68)
    assert m.werte[WEST] == pytest.approx(4.176)
    assert t1.bilanz_kwh + t2.bilanz_kwh == pytest.approx(12.6 + 17.28)
    assert m.bilanz_kwh == pytest.approx(29.376)


def test_r3_ohne_anlagenzaehler_ist_die_bilanz_die_summe_der_geraete():
    traeger = [_t(SUED, "pv-module", 6.0), _t(WEST, "pv-module", 4.0)]
    r = loese_pv_zeitraum_auf(traeger=traeger, eigen={SUED: 12.0, WEST: 6.0}, anlagenzaehler_kwh=None)
    assert r.bilanz_kwh == pytest.approx(18.0) and r.wandlungsverluste_kwh is None


def test_r3_ohne_pv_traeger_ist_der_zaehler_die_summe():
    r = loese_pv_zeitraum_auf(traeger=[], eigen={}, anlagenzaehler_kwh=5.0)
    assert r.werte == {} and r.bilanz_kwh == 5.0


def test_marke_ist_die_der_provenienz():
    from backend.services.provenance import ABGELEITET_KWP_ANTEIL
    from backend.services.snapshot.komponenten_beitraege import _TYP_KEY_PREFIX

    assert KWP_ANTEIL == ABGELEITET_KWP_ANTEIL
    from backend.core.berechnungen.bilanz_zeitraum import PV_SCHLUESSEL_PRAEFIX
    assert all(_TYP_KEY_PREFIX.get(t) == p for t, p in PV_SCHLUESSEL_PRAEFIX.items())


def test_komposition_bilanz_mit_speicher_und_anlagenzaehler():
    """F13a-artig mit Speicher: Strings 12 + 6 + BKW 3 = 21 gegen Anlagenzähler 19,8 (alle gemessen); Einspeisung 6,
    Netzbezug 7,2, Ladung 3, Entladung 2. Bilanz-PV = Σ Geräte 21 (R3); EV = PV − Einspeisung − Ladung + Entladung;
    die 1,2 über dem Anlagenzähler sind geführte Wandlungsverluste."""
    eingaenge = [
        Eingang("pv", "pv_gesamt", 1, 19.8),
        Eingang("pv", f"pv_{SUED}", 1, 12.0, SUED), Eingang("pv", f"pv_{WEST}", 1, 6.0, WEST),
        Eingang("pv", f"bkw_{BKW}", 1, 3.0, BKW),
        Eingang("einspeisung", "einspeisung", 1, 6.0), Eingang("netzbezug", "netzbezug", 1, 7.2),
        Eingang("ladung_batterie", "batterie_9", -1, 3.0), Eingang("entladung_batterie", "batterie_9", 1, 2.0),
    ]
    k = komponiere_bilanz_zeitraum(eingaenge, STRINGS_BKW)
    assert _r(k.komponenten) == {f"pv_{SUED}": 12.0, f"pv_{WEST}": 6.0, f"bkw_{BKW}": 3.0, "einspeisung": 6.0,
                                 "netzbezug": 7.2, "batterie_9": -1.0}
    assert k.marken == {}
    b = k.bilanz
    assert b.erzeugung_kwh == pytest.approx(21.0)
    assert b.speicher_ladung_kwh == pytest.approx(3.0) and b.speicher_entladung_kwh == pytest.approx(2.0)
    assert b.eigenverbrauch_kwh == pytest.approx(21.0 - 6.0 - 3.0 + 2.0)
    assert b.gesamtverbrauch_kwh == pytest.approx(21.0 - 6.0 + 7.2 - 3.0 + 2.0)
    assert k.pv.wandlungsverluste_kwh == pytest.approx(1.2)


def test_komposition_ohne_wert_ist_keine_aussage():
    assert komponiere_bilanz_zeitraum([Eingang("einspeisung", "einspeisung", 1, None)], []) is None
