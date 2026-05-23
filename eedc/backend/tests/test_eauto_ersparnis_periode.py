"""Periode-Ersparnis mit per-Monat-Benzinpreis (#260, NongJoWo).

`berechne_eauto_ersparnis_periode` rechnet:
    benzin_kosten = Σ (km_monat × verbrauch_l_100km × preis_monat)
mit Preis-Fallback-Kette: Lookup → params.benzinpreis_euro → Default 1,65.

Vor v3.32.1 nutzte das E-Auto-Dashboard `berechne_eauto_ersparnis` einmal
auf der Gesamtsumme aller km mit einem festen Default (1,65 €) — die
Cockpit-Übersicht rechnete per Monat mit dem dynamischen EU-Oil-Bulletin-
Preis. NongJoWo sah 2696 € vs. 2375 € für dieselbe Anlage.
"""

from __future__ import annotations

import pytest

from backend.services.eauto_wirtschaftlichkeit import (
    berechne_eauto_ersparnis_periode,
)


def test_einzelner_monat_nutzt_lookup_preis():
    # 1000 km × 7,5 L/100km × 1,80 €/L = 135 € Benzin
    erg = berechne_eauto_ersparnis_periode(
        km_pro_monat=[(2026, 3, 1000.0)],
        ladung_netz_kwh_gesamt=100.0,
        ladung_extern_euro_gesamt=0.0,
        wallbox_strompreis_cent=30.0,
        eauto_parameter={"vergleich_verbrauch_l_100km": 7.5},
        monats_benzinpreis_lookup={(2026, 3): 1.80},
    )
    assert erg.benzin_kosten_euro == pytest.approx(135.0)
    # Strom: 100 × 30 / 100 = 30 €
    assert erg.strom_kosten_euro == pytest.approx(30.0)
    assert erg.ersparnis_euro == pytest.approx(105.0)
    assert erg.verwendeter_benzinpreis_euro == pytest.approx(1.80)


def test_drei_monate_unterschiedliche_preise():
    """Drift-Fix-Szenario: pro Monat anderer EU-OB-Preis."""
    erg = berechne_eauto_ersparnis_periode(
        km_pro_monat=[
            (2026, 1, 1000.0),  # 1000 × 7,5 × 1,70 = 127,5
            (2026, 2, 1500.0),  # 1500 × 7,5 × 1,80 = 202,5
            (2026, 3, 2000.0),  # 2000 × 7,5 × 1,90 = 285,0
        ],
        ladung_netz_kwh_gesamt=0.0,
        ladung_extern_euro_gesamt=0.0,
        wallbox_strompreis_cent=0.0,
        eauto_parameter={"vergleich_verbrauch_l_100km": 7.5},
        monats_benzinpreis_lookup={
            (2026, 1): 1.70, (2026, 2): 1.80, (2026, 3): 1.90,
        },
    )
    assert erg.benzin_kosten_euro == pytest.approx(127.5 + 202.5 + 285.0)
    # km-gewichteter Durchschnitt: (1000×1.7 + 1500×1.8 + 2000×1.9) / 4500
    erwartet_avg = (1000 * 1.70 + 1500 * 1.80 + 2000 * 1.90) / 4500
    assert erg.verwendeter_benzinpreis_euro == pytest.approx(erwartet_avg)


def test_monat_ohne_lookup_eintrag_faellt_auf_param_zurueck():
    # Februar im Lookup, Januar nicht → Januar nutzt params (2,00 €).
    erg = berechne_eauto_ersparnis_periode(
        km_pro_monat=[(2026, 1, 1000.0), (2026, 2, 1000.0)],
        ladung_netz_kwh_gesamt=0.0,
        ladung_extern_euro_gesamt=0.0,
        wallbox_strompreis_cent=0.0,
        eauto_parameter={
            "vergleich_verbrauch_l_100km": 7.5,
            "benzinpreis_euro": 2.00,
        },
        monats_benzinpreis_lookup={(2026, 2): 1.80},
    )
    # Januar: 1000 × 7,5 × 2,00 = 150 €
    # Februar: 1000 × 7,5 × 1,80 = 135 €
    assert erg.benzin_kosten_euro == pytest.approx(150.0 + 135.0)


def test_lookup_eintrag_mit_none_faellt_zurueck():
    # Anwender hat den Monat noch nicht erfasst → kraftstoffpreis_euro=None.
    erg = berechne_eauto_ersparnis_periode(
        km_pro_monat=[(2026, 1, 1000.0)],
        ladung_netz_kwh_gesamt=0.0,
        ladung_extern_euro_gesamt=0.0,
        wallbox_strompreis_cent=0.0,
        eauto_parameter={
            "vergleich_verbrauch_l_100km": 7.5,
            "benzinpreis_euro": 1.95,
        },
        monats_benzinpreis_lookup={(2026, 1): None},
    )
    # Fallback auf 1,95 € → 1000 × 7,5 × 1,95 / 100 = 146,25 €
    assert erg.benzin_kosten_euro == pytest.approx(146.25)
    assert erg.verwendeter_benzinpreis_euro == pytest.approx(1.95)


def test_ohne_lookup_und_ohne_params_nimmt_kanon_default():
    # Default-Verbrauch 7,5 L/100 km, Default-Preis 1,65 €/L.
    erg = berechne_eauto_ersparnis_periode(
        km_pro_monat=[(2026, 1, 1000.0)],
        ladung_netz_kwh_gesamt=0.0,
        ladung_extern_euro_gesamt=0.0,
        wallbox_strompreis_cent=0.0,
    )
    # 1000 × 7,5 × 1,65 / 100 = 123,75 €
    assert erg.benzin_kosten_euro == pytest.approx(123.75)


def test_keine_km_im_zeitraum_liefert_null_ergebnis():
    erg = berechne_eauto_ersparnis_periode(
        km_pro_monat=[],
        ladung_netz_kwh_gesamt=50.0,  # wird ignoriert wenn km=0
        ladung_extern_euro_gesamt=10.0,
        wallbox_strompreis_cent=30.0,
        eauto_parameter={"vergleich_verbrauch_l_100km": 7.5},
    )
    assert erg.ersparnis_euro == 0.0
    assert erg.benzin_kosten_euro == 0.0
    assert erg.strom_kosten_euro == 0.0


def test_monate_mit_km_0_oder_negativ_werden_uebersprungen():
    # Nur Februar trägt bei (Januar km=0, März km=None).
    erg = berechne_eauto_ersparnis_periode(
        km_pro_monat=[
            (2026, 1, 0.0),
            (2026, 2, 1000.0),
            (2026, 3, None),  # type: ignore[list-item]
        ],
        ladung_netz_kwh_gesamt=0.0,
        ladung_extern_euro_gesamt=0.0,
        wallbox_strompreis_cent=0.0,
        eauto_parameter={"vergleich_verbrauch_l_100km": 7.5},
        monats_benzinpreis_lookup={(2026, 2): 1.80},
    )
    assert erg.benzin_kosten_euro == pytest.approx(135.0)


def test_nongjowo_szenario_cockpit_vs_dashboard_konsistenz():
    """Drift-Fix-Szenario aus #260: Cockpit nutzt Monatspreise (~1,80),
    Dashboard nutzte zuvor Default 1,65 — Drift sichtbar.

    Hier: bei konsistenter Anwendung des Monats-Lookups (1,80) muss das
    Periode-Helper-Ergebnis dem ehemaligen Cockpit-Wert entsprechen.
    """
    # 30.534 km × 7 L/100km × 1,80 €/L = 3847,28 €
    erg = berechne_eauto_ersparnis_periode(
        km_pro_monat=[(2026, m, 30534.0 / 12) for m in range(1, 13)],
        ladung_netz_kwh_gesamt=4000.0,
        ladung_extern_euro_gesamt=0.0,
        wallbox_strompreis_cent=30.0,
        eauto_parameter={
            "vergleich_verbrauch_l_100km": 7.0,
            "benzinpreis_euro": 1.65,  # alter Param-Default
        },
        monats_benzinpreis_lookup={(2026, m): 1.80 for m in range(1, 13)},
    )
    # benzin_kosten = 30534/100 × 7 × 1.80 = 3847,284
    assert erg.benzin_kosten_euro == pytest.approx(3847.284, abs=0.01)
    # Strom = 4000 × 30/100 = 1200 €
    assert erg.strom_kosten_euro == pytest.approx(1200.0)
    # Ersparnis = 3847,28 − 1200 = 2647,28 € (statt der ~2375 € mit Default 1,65)
    assert erg.ersparnis_euro == pytest.approx(2647.284, abs=0.01)
    # Verwendeter Preis = 1,80 (gewichteter Schnitt aller Monate)
    assert erg.verwendeter_benzinpreis_euro == pytest.approx(1.80)
