"""B1 — der EINE Fenster-Rechner (`core/berechnungen/fenster.py`), an Handrechnungen geprüft.

Jede Probe rechnet ihr Ergebnis **vor** und vergleicht dann; eine Probe, die
nur „irgendetwas Plausibles" prüft, hält keine Formeländerung auf.

⚠ **Nirgends `== 24`.** Am Ende der Sommerzeit hat ein Tag 23 oder 25 Stunden
(F-6); die Proben benutzen 24 Slots als bequeme Länge, prüfen aber keine.
"""

import pytest

from backend.core.berechnungen.fenster import (
    arbitrage_vorschlag,
    bestes_fenster,
    kosten_profil,
    ueberschuss_bloecke,
    verteile_auf_guenstigste,
)


def _reihe(werte: dict, n: int = 24, default=0.0) -> list:
    """Eine n-Slot-Reihe aus den paar Stunden, die eine Probe wirklich setzt."""
    return [werte.get(h, default) for h in range(n)]


# ── kosten_profil ───────────────────────────────────────────────────────────

def test_kosten_profil_ohne_ueberschuss_ist_der_slot_preis():
    preis = _reihe({0: 30.0, 1: 20.0, 2: 10.0})
    out = kosten_profil(preis, _reihe({}), 1.0)
    assert out[0] == 30.0 and out[1] == 20.0 and out[2] == 10.0


def test_ueberschuss_senkt_die_kosten_auf_null():
    """3 kWh Überschuss und 1 kWh Bedarf ⇒ der Anteil ist gekappt, nicht > 1."""
    preis = _reihe({12: 25.0})
    out = kosten_profil(preis, _reihe({12: 3.0}), 1.0)
    assert out[12] == 0.0


def test_teilweiser_ueberschuss_ergibt_den_mischpreis():
    """1 kWh Überschuss bei 4 kWh Bedarf ⇒ 25 % gratis ⇒ 30 × 0,75 = 22,5."""
    preis = _reihe({9: 30.0})
    out = kosten_profil(preis, _reihe({9: 1.0}), _reihe({9: 4.0}))
    assert out[9] == pytest.approx(22.5)


def test_fehlender_preis_bleibt_none():
    preis = _reihe({0: 10.0})
    preis[5] = None
    out = kosten_profil(preis, _reihe({5: 99.0}), 1.0)
    assert out[5] is None, "ohne Preis gibt es keine Kosten — auch nicht 0 (ADR-002/P4)"


# ── bestes_fenster ──────────────────────────────────────────────────────────

def test_bestes_fenster_findet_den_billigsten_block():
    """Handrechnung: 2-h-Mittel bei 13 = (5+5)/2 = 5, überall sonst ≥ 10."""
    kosten = _reihe({h: 20.0 for h in range(24)})
    kosten[13] = 5.0
    kosten[14] = 5.0
    f = bestes_fenster(kosten, dauer_h=2, ab_h=0)
    assert (f.ab, f.bis) == (13, 15)
    assert f.kosten_cent_kwh == pytest.approx(5.0)
    assert f.delta_vs_jetzt == pytest.approx(5.0 - 20.0)


def test_ab_h_schneidet_die_vergangenheit_weg():
    kosten = _reihe({h: 20.0 for h in range(24)})
    kosten[2] = kosten[3] = 1.0
    kosten[18] = kosten[19] = 4.0
    f = bestes_fenster(kosten, dauer_h=2, ab_h=10)
    assert (f.ab, f.bis) == (18, 20), "das billigere Fenster liegt vor `ab_h`"


def test_frist_schneidet_das_fenster_ab():
    """Die Frist gilt für den **letzten Slot im** Fenster, nicht für seinen Beginn."""
    kosten = _reihe({h: 20.0 for h in range(24)})
    kosten[16] = kosten[17] = 1.0
    kosten[9] = kosten[10] = 9.0
    assert bestes_fenster(kosten, 2, 0, frist_h=17).ab == 16
    # Frist 16: der Block 16–17 ragt über die Frist hinaus und fällt weg
    assert bestes_fenster(kosten, 2, 0, frist_h=16).ab == 9


def test_luecke_in_der_mitte_verhindert_das_fenster_darueber():
    """Ein `None` mitten im billigen Bereich macht den Block unbenutzbar."""
    kosten = _reihe({h: 20.0 for h in range(24)})
    kosten[11] = 1.0
    kosten[12] = None
    kosten[13] = 1.0
    kosten[20] = kosten[21] = 8.0
    f = bestes_fenster(kosten, dauer_h=2, ab_h=0)
    assert (f.ab, f.bis) == (20, 22)


def test_kein_fenster_wenn_zu_wenig_slots_mit_preis_bleiben():
    kosten = [None] * 24
    kosten[23] = 5.0
    assert bestes_fenster(kosten, dauer_h=2, ab_h=0) is None


def test_gleichstand_geht_an_das_fruehere_fenster():
    kosten = _reihe({h: 20.0 for h in range(24)})
    kosten[4] = kosten[5] = kosten[15] = kosten[16] = 3.0
    assert bestes_fenster(kosten, 2, 0).ab == 4


def test_delta_fehlt_wenn_jetzt_keinen_preis_traegt():
    kosten = _reihe({h: 20.0 for h in range(24)})
    kosten[0] = None
    kosten[7] = kosten[8] = 2.0
    f = bestes_fenster(kosten, 2, ab_h=0)
    assert f.ab == 7 and f.delta_vs_jetzt is None


def test_eigenschaft_kein_n_fenster_ist_billiger():
    """Eigenschaftsprobe: das gemeldete Fenster ist **das** Minimum.

    Sie prüft die Aussage der Funktion, nicht ein Beispiel — genau das, was
    eine Handrechnung allein nicht leistet.
    """
    import random

    rng = random.Random(4711)
    for _ in range(200):
        n = rng.randint(6, 30)
        kosten = [None if rng.random() < 0.15 else round(rng.uniform(-5, 60), 2)
                  for _ in range(n)]
        dauer = rng.randint(1, 4)
        f = bestes_fenster(kosten, dauer, ab_h=0)
        alle = [
            sum(kosten[a:a + dauer]) / dauer
            for a in range(0, n - dauer + 1)
            if all(k is not None for k in kosten[a:a + dauer])
        ]
        if not alle:
            assert f is None
        else:
            assert f is not None
            assert f.kosten_cent_kwh == pytest.approx(min(alle), abs=1e-3)


# ── ueberschuss_bloecke ─────────────────────────────────────────────────────

def test_ein_zusammenhaengender_block():
    pv = _reihe({10: 3.0, 11: 5.0, 12: 4.0})
    verbrauch = _reihe({h: 1.0 for h in range(24)})
    bloecke = ueberschuss_bloecke(pv, verbrauch)
    assert len(bloecke) == 1
    b = bloecke[0]
    assert (b.ab, b.bis, b.stunden) == (10, 13, 3)
    assert b.min_kw == pytest.approx(2.0)          # 3−1
    assert b.summe_kwh == pytest.approx(2.0 + 4.0 + 3.0)


def test_zwei_bloecke_mit_einer_luecke():
    pv = _reihe({9: 2.0, 10: 2.0, 11: 0.5, 12: 3.0})
    verbrauch = _reihe({h: 1.0 for h in range(24)})
    bloecke = ueberschuss_bloecke(pv, verbrauch)
    assert [(b.ab, b.bis) for b in bloecke] == [(9, 11), (12, 13)]


def test_kein_ueberschuss_gibt_keine_bloecke():
    assert ueberschuss_bloecke(_reihe({}), _reihe({h: 1.0 for h in range(24)})) == []


def test_block_am_ende_der_reihe_wird_geschlossen():
    pv = _reihe({22: 2.0, 23: 2.0})
    verbrauch = _reihe({h: 1.0 for h in range(24)})
    assert [(b.ab, b.bis) for b in ueberschuss_bloecke(pv, verbrauch)] == [(22, 24)]


# ── verteile_auf_guenstigste (P7) ───────────────────────────────────────────

def test_verteilung_schiebt_die_menge_in_die_billigen_stunden():
    """Handrechnung: 3 Stunden × 2 kWh; Preise 30/30/10 innerhalb der Heizzeit.

    Alt: 2×30 + 2×30 + 2×10 = 140 ct. Das Stundenmaximum ist 2 kWh, also
    passen in die billigste Stunde 2 kWh, dann in die nächstbillige usw. —
    die 6 kWh belegen 10, 30, 30 ⇒ 140. Erst eine echte Spreizung bewegt
    etwas; deshalb die zweite Probe darunter.
    """
    kosten = _reihe({6: 30.0, 7: 30.0, 8: 10.0})
    menge = _reihe({6: 2.0, 7: 2.0, 8: 2.0})
    v = verteile_auf_guenstigste(kosten, menge, [6, 7, 8])
    assert v.kosten_alt_cent == pytest.approx(140.0)
    assert v.kosten_neu_cent == pytest.approx(140.0)
    assert v.ersparnis_cent == pytest.approx(0.0)


def test_verteilung_spart_wenn_das_profil_spitzen_hat():
    """Profil 4/1/1 kWh bei Preisen 30/30/10 ⇒ alt 4×30+1×30+1×10 = 160.

    Neu: 6 kWh in die billigsten Stunden, je höchstens 4 (das
    Stundenmaximum): 4 × 10 + 2 × 30 = 100 ⇒ 60 ct Ersparnis.
    """
    kosten = _reihe({6: 30.0, 7: 30.0, 8: 10.0})
    menge = _reihe({6: 4.0, 7: 1.0, 8: 1.0})
    v = verteile_auf_guenstigste(kosten, menge, [6, 7, 8])
    assert v.kosten_alt_cent == pytest.approx(160.0)
    assert v.kosten_neu_cent == pytest.approx(100.0)
    assert v.ersparnis_cent == pytest.approx(60.0)
    assert v.stunden == (6, 8)


def test_verteilung_ohne_benutzbare_stunde_ist_none():
    kosten = [None] * 24
    assert verteile_auf_guenstigste(kosten, _reihe({}), [6, 7]) is None


def test_verteilung_ignoriert_stunden_ausserhalb_der_erlaubten_menge():
    """Eine billige Stunde außerhalb der Heizzeit zieht die Menge nicht an sich."""
    kosten = _reihe({6: 30.0, 7: 30.0, 3: 1.0})
    menge = _reihe({6: 2.0, 7: 2.0})
    v = verteile_auf_guenstigste(kosten, menge, [6, 7])
    assert 3 not in v.stunden


# ── arbitrage_vorschlag (P3) ────────────────────────────────────────────────

def test_arbitrage_laedt_billig_und_ersetzt_teures_defizit():
    """Handrechnung: laden bei 10 ct mit η = 90 % ⇒ 11,11 ct je nutzbare kWh;
    ersetzt 3 kWh Defizit bei 40 ct ⇒ 3 × (40 − 11,11) = 86,7 ct."""
    kosten = _reihe({h: 25.0 for h in range(24)})
    kosten[3] = 10.0
    kosten[18] = 40.0
    guenstig = _reihe({3: True}, default=False)
    defizit = _reihe({18: 3.0})
    a = arbitrage_vorschlag(kosten, defizit, frei_kwh=5.0,
                            wirkungsgrad_prozent=90.0, guenstig=guenstig)
    assert a.menge_kwh == pytest.approx(3.0)
    assert a.lade_stunden == (3,)
    assert a.ersparnis_cent == pytest.approx(3 * (40.0 - 10.0 / 0.9), abs=0.15)


def test_arbitrage_kappt_an_der_freien_kapazitaet():
    kosten = _reihe({h: 25.0 for h in range(24)})
    kosten[3] = 5.0
    kosten[18] = 50.0
    a = arbitrage_vorschlag(kosten, _reihe({18: 9.0}), frei_kwh=2.0,
                            wirkungsgrad_prozent=95.0,
                            guenstig=_reihe({3: True}, default=False))
    assert a.menge_kwh == pytest.approx(2.0)


def test_arbitrage_ohne_gewinn_ist_none():
    """Spanne kleiner als der Wirkungsgradverlust ⇒ kein Vorschlag, keine 0."""
    kosten = _reihe({h: 25.0 for h in range(24)})
    kosten[3] = 24.0
    kosten[18] = 25.0
    a = arbitrage_vorschlag(kosten, _reihe({18: 5.0}), frei_kwh=5.0,
                            wirkungsgrad_prozent=80.0,
                            guenstig=_reihe({3: True}, default=False))
    assert a is None


def test_arbitrage_ohne_platz_ist_none():
    kosten = _reihe({3: 1.0, 18: 50.0})
    assert arbitrage_vorschlag(kosten, _reihe({18: 5.0}), 0.0, 90.0,
                               _reihe({3: True}, default=False)) is None


def test_arbitrage_laedt_nicht_nach_dem_bedarf():
    """Die günstige Stunde liegt NACH dem Defizit ⇒ sie hilft ihm nicht."""
    kosten = _reihe({h: 25.0 for h in range(24)})
    kosten[20] = 1.0
    kosten[8] = 50.0
    a = arbitrage_vorschlag(kosten, _reihe({8: 4.0}), 5.0, 90.0,
                            _reihe({20: True}, default=False))
    assert a is None
