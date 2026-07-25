"""Tests für den Speicher-Berechnungs-Layer (`core/berechnungen/speicher.py`)
und die kumulative Durchsatz-Invariante.

Hintergrund (Rainer-PN 2026-05-22): Die naive Pro-Monats-Effizienz
`entladung/ladung` konnte >100 % zeigen, weil ein Akku ein Bestand ist und
der SoC einen Übertrag über die Monatsgrenze trägt. Ein einzelner Monat darf
mehr ent- als laden — die Summe über die ganze Historie nicht.
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen import (
    assert_speicher_durchsatz_konsistent,
    berechne_netzladung_kosten,
    gleitende_effizienz,
    pruefe_speicher_durchsatz_konsistenz,
    speicher_effizienz_prozent,
)


# ─── speicher_effizienz_prozent ─────────────────────────────────────────────


def test_effizienz_basis():
    assert speicher_effizienz_prozent(100.0, 90.0) == pytest.approx(90.0)


def test_effizienz_ohne_ladung_ist_none():
    assert speicher_effizienz_prozent(0.0, 0.0) is None
    assert speicher_effizienz_prozent(0.0, 5.0) is None


def test_effizienz_ueber_100_wird_nicht_geklemmt():
    """Über ein kurzes Fenster mit SoC-Drawdown ist entladung > ladung möglich
    — die Funktion klemmt das NICHT (Diagnose statt stillem Cap). Gegen den
    >100 %-Effekt hilft `gleitende_effizienz`, nicht ein versteckter Cap."""
    assert speicher_effizienz_prozent(100.0, 107.0) == pytest.approx(107.0)


# ─── gleitende_effizienz ────────────────────────────────────────────────────


def test_gleitende_effizienz_leer():
    assert gleitende_effizienz([]) == []


def test_gleitende_effizienz_kumulativ_bei_kurzer_historie():
    """Unter Fensterbreite: kumulativ ab Start, `fenster_monate` zählt mit."""
    reihe = [
        (2026, 1, 100.0, 95.0),
        (2026, 2, 100.0, 95.0),
        (2026, 3, 100.0, 95.0),
    ]
    verlauf = gleitende_effizienz(reihe, fenster=12)
    assert len(verlauf) == 3
    assert verlauf[0].fenster_monate == 1
    assert verlauf[2].fenster_monate == 3
    assert verlauf[2].effizienz_prozent == pytest.approx(95.0)
    assert verlauf[2].jahr == 2026 and verlauf[2].monat == 3


def test_gleitende_effizienz_fenster_begrenzt():
    """Bei mehr Monaten als `fenster` zählt nur das gleitende Fenster."""
    reihe = [(2025, (i % 12) + 1, 100.0, 90.0) for i in range(14)]
    verlauf = gleitende_effizienz(reihe, fenster=12)
    assert verlauf[-1].fenster_monate == 12
    assert verlauf[-1].effizienz_prozent == pytest.approx(90.0)


def test_gleitende_effizienz_glaettet_carryover():
    """Ein einzelner Monat mit entladung > ladung treibt die gleitende Reihe
    NICHT über 100 %, solange die kumulative Summe konsistent ist."""
    reihe = [
        (2026, 1, 200.0, 50.0),   # SoC steigt: viel geladen, wenig entladen
        (2026, 2, 50.0, 180.0),   # SoC fällt: Monat 2 naiv 360 % — unmöglich
    ]
    naiv = speicher_effizienz_prozent(50.0, 180.0)
    assert naiv is not None and naiv > 100
    verlauf = gleitende_effizienz(reihe, fenster=12)
    # Gleitend (kumulativ): 230 / 250 = 92 % — plausibel, ≤ 100.
    assert verlauf[1].effizienz_prozent == pytest.approx(92.0)
    assert verlauf[1].effizienz_prozent <= 100


# ─── Durchsatz-Invariante ───────────────────────────────────────────────────


def test_durchsatz_konsistent():
    assert pruefe_speicher_durchsatz_konsistenz(1000.0, 900.0).konsistent


def test_durchsatz_inkonsistent_kumulativ():
    bericht = pruefe_speicher_durchsatz_konsistenz(900.0, 1000.0)
    assert not bericht.konsistent
    assert "übersteigt" in bericht.details


def test_durchsatz_toleranz():
    """Rundungs-Toleranz: knapp drüber gilt noch als konsistent."""
    assert pruefe_speicher_durchsatz_konsistenz(1000.0, 1000.05).konsistent


def test_durchsatz_none_als_null():
    assert pruefe_speicher_durchsatz_konsistenz(None, None).konsistent


def test_durchsatz_assert_wirft_bei_verstoss():
    with pytest.raises(AssertionError):
        assert_speicher_durchsatz_konsistent(900.0, 1000.0)


# ─── berechne_netzladung_kosten (R15-1 Kostenkachel) ─────────────────────────


def test_netzladung_kosten_tep_hat_vorrang():
    r = berechne_netzladung_kosten(
        112.0, eff_ladepreis_cent=22.4, imd_preis_cent=25.0, netzbezug_preis_cent=30.0,
    )
    assert r is not None
    assert r.quelle == "tep"
    assert r.preis_cent == 22.4
    assert r.kosten_euro == pytest.approx(25.09, abs=0.01)


def test_netzladung_kosten_imd_fallback():
    r = berechne_netzladung_kosten(31.6, imd_preis_cent=22.0, netzbezug_preis_cent=30.0)
    assert r is not None
    assert r.quelle == "imd"
    assert r.kosten_euro == pytest.approx(6.95, abs=0.01)


def test_netzladung_kosten_bezugspreis_fallback():
    r = berechne_netzladung_kosten(40.0, netzbezug_preis_cent=29.21)
    assert r is not None
    assert r.quelle == "bezugspreis"
    assert r.kosten_euro == pytest.approx(11.68, abs=0.01)


def test_netzladung_kosten_ohne_speicher_none():
    """Kein Speicher / keine Daten → None (Kachel bleibt aus)."""
    assert berechne_netzladung_kosten(None, netzbezug_preis_cent=30.0) is None


def test_netzladung_kosten_null_kwh_ist_eine_aussage():
    """0 kWh Netzladung → 0,00 € statt None (Rainer-PN 2026-07-25).

    „Diesen Monat nichts aus dem Netz geladen" ist eine Information; früher fiel
    die Kachel weg und der Nutzer musste anderswo nachsehen, ob wirklich nichts
    lief. Ein Ladepreis existiert dabei nicht → `preis_cent is None` („—").
    """
    r = berechne_netzladung_kosten(0.0, netzbezug_preis_cent=30.0)
    assert r is not None
    assert r.kosten_euro == 0.0
    assert r.preis_cent is None
    assert r.quelle == "keine"


def test_netzladung_kosten_ohne_preis_none():
    assert berechne_netzladung_kosten(50.0) is None
