"""Die Preisachse der E-Mob-Ersparnis (F-18 · N-181, ADR-002/P8).

Bis 2026-08-08 lösten vier Sichten denselben Netzbezugspreis auf vier Arten
auf — Cockpit → Jahr und beide HA-Export-Pfade mit dem **heute** gültigen
Tarif, der Komponenten-Hub mit einem mengengewichteten Monats-Ø, die
Aussichten mit dem echten Monatspreis. An einer Anlage mit Tarifwechsel wies
das Cockpit deshalb eine andere E-Auto-Ersparnis aus als der Hub, ohne dass
sich eine einzige kWh unterschied.

Diese Datei prüft den neuen SoT `aufgeloester_strompreis_cent` und seine
Einbettung in `berechne_eauto_ersparnis_periode`. Die **Symmetrie über die
Sichten** liegt in `test_emob_preisachse_sichten_symmetrie.py`.
"""

from __future__ import annotations

import pytest

from backend.services.eauto_wirtschaftlichkeit import (
    aufgeloester_strompreis_cent,
    berechne_eauto_ersparnis_periode,
)


# ---------------------------------------------------------------------------
# aufgeloester_strompreis_cent — der Kern
# ---------------------------------------------------------------------------

def test_ohne_lookup_bleibt_der_skalar_unveraendert():
    """Bestandsaufrufer bewegen keine Zahl — das ist die Migrationszusage."""
    assert aufgeloester_strompreis_cent(
        wallbox_strompreis_cent=31.5,
        monats_strompreis_lookup=None,
        gewichte=[(2026, 3, 100.0)],
    ) == pytest.approx(31.5)


def test_ohne_gewichte_bleibt_der_skalar_unveraendert():
    assert aufgeloester_strompreis_cent(
        wallbox_strompreis_cent=31.5,
        monats_strompreis_lookup={(2026, 3): 20.0},
        gewichte=None,
    ) == pytest.approx(31.5)


def test_tarifwechsel_wird_mengengewichtet():
    """Der Fall aus F-18: 20 ct in der ersten, 40 ct in der zweiten Hälfte.

    400 kWh × 20 + 400 kWh × 40 ⇒ Ø 30 ct. Mit dem *heutigen* Tarif (40) wären
    es 40 — genau die 80-€-Drift des Fundes bei 800 kWh.
    """
    preis = aufgeloester_strompreis_cent(
        wallbox_strompreis_cent=40.0,
        monats_strompreis_lookup={(2026, 1): 20.0, (2026, 7): 40.0},
        gewichte=[(2026, 1, 400.0), (2026, 7, 400.0)],
    )
    assert preis == pytest.approx(30.0)


def test_gewichtung_ist_mengen_nicht_monatsgewichtet():
    """Ein Monat mit 10 kWh darf einen mit 990 kWh nicht gleich stark ziehen."""
    preis = aufgeloester_strompreis_cent(
        wallbox_strompreis_cent=0.0,
        monats_strompreis_lookup={(2026, 1): 10.0, (2026, 2): 100.0},
        gewichte=[(2026, 1, 990.0), (2026, 2, 10.0)],
    )
    # Mengengewichtet: (990×10 + 10×100) / 1000 = 10,9 — nicht 55 (Monats-Ø).
    assert preis == pytest.approx(10.9)


def test_monat_ohne_lookup_eintrag_faellt_auf_den_skalar():
    preis = aufgeloester_strompreis_cent(
        wallbox_strompreis_cent=30.0,
        monats_strompreis_lookup={(2026, 1): 10.0},  # Februar fehlt
        gewichte=[(2026, 1, 100.0), (2026, 2, 100.0)],
    )
    assert preis == pytest.approx(20.0)


def test_none_im_lookup_zaehlt_wie_ein_fehlender_monat():
    """`None` ist „kein Tarif für diesen Monat", nicht „0 ct"."""
    preis = aufgeloester_strompreis_cent(
        wallbox_strompreis_cent=30.0,
        monats_strompreis_lookup={(2026, 1): 10.0, (2026, 2): None},
        gewichte=[(2026, 1, 100.0), (2026, 2, 100.0)],
    )
    assert preis == pytest.approx(20.0)


def test_nicht_positive_mengen_werden_uebersprungen():
    """Ein Monat ohne Ladung darf seinen Tarif nicht in den Ø tragen."""
    preis = aufgeloester_strompreis_cent(
        wallbox_strompreis_cent=99.0,
        monats_strompreis_lookup={(2026, 1): 10.0, (2026, 2): 40.0},
        gewichte=[(2026, 1, 100.0), (2026, 2, 0.0)],
    )
    assert preis == pytest.approx(10.0)


def test_nur_nullmengen_fallen_auf_den_skalar():
    preis = aufgeloester_strompreis_cent(
        wallbox_strompreis_cent=31.5,
        monats_strompreis_lookup={(2026, 1): 10.0},
        gewichte=[(2026, 1, 0.0)],
    )
    assert preis == pytest.approx(31.5)


# ---------------------------------------------------------------------------
# Einbettung in die Periodenrechnung
# ---------------------------------------------------------------------------

def test_periode_ohne_neue_parameter_rechnet_wie_vorher():
    """Die Rückwärtskompatibilität ist die Bedingung für das Umhängen."""
    erg = berechne_eauto_ersparnis_periode(
        km_pro_monat=[(2026, 3, 1000.0)],
        ladung_netz_kwh_gesamt=100.0,
        ladung_extern_euro_gesamt=0.0,
        wallbox_strompreis_cent=30.0,
        eauto_parameter={"vergleich_verbrauch_l_100km": 7.5},
        monats_benzinpreis_lookup={(2026, 3): 1.80},
    )
    assert erg.strom_kosten_euro == pytest.approx(30.0)
    assert erg.verwendeter_strompreis_cent == pytest.approx(30.0)


def test_periode_nutzt_die_netzmengen_als_gewicht():
    """Netzladung je Monat vorhanden ⇒ danach gewichten, nicht nach km.

    Die km liegen hier bewusst **gegenläufig** zur Netzladung: würde die
    Funktion nach km gewichten, käme 35 statt 25 ct heraus.
    """
    erg = berechne_eauto_ersparnis_periode(
        km_pro_monat=[(2026, 1, 100.0), (2026, 7, 900.0)],
        ladung_netz_kwh_gesamt=1000.0,
        ladung_extern_euro_gesamt=0.0,
        wallbox_strompreis_cent=40.0,
        eauto_parameter={"vergleich_verbrauch_l_100km": 7.5},
        monats_strompreis_lookup={(2026, 1): 20.0, (2026, 7): 40.0},
        netz_pro_monat=[(2026, 1, 750.0), (2026, 7, 250.0)],
    )
    # (750×20 + 250×40) / 1000 = 25 ct
    assert erg.verwendeter_strompreis_cent == pytest.approx(25.0)
    assert erg.strom_kosten_euro == pytest.approx(1000.0 * 0.25)


def test_periode_faellt_ohne_netzaufteilung_auf_die_km_gewichte():
    """Der Wallbox-Pool-Fall (#262): es GIBT keine Netzladung je Monat.

    `attribute_emob_pool_by_km` verteilt einen Gesamtwert nach km — also ist
    km der Schlüssel, nach dem auch der Preis gemittelt werden muss.
    """
    erg = berechne_eauto_ersparnis_periode(
        km_pro_monat=[(2026, 1, 750.0), (2026, 7, 250.0)],
        ladung_netz_kwh_gesamt=1000.0,
        ladung_extern_euro_gesamt=0.0,
        wallbox_strompreis_cent=40.0,
        eauto_parameter={"vergleich_verbrauch_l_100km": 7.5},
        monats_strompreis_lookup={(2026, 1): 20.0, (2026, 7): 40.0},
        netz_pro_monat=None,
    )
    assert erg.verwendeter_strompreis_cent == pytest.approx(25.0)


def test_externe_ladung_bleibt_vom_strompreis_unberuehrt():
    """`ladung_extern_euro` ist eine ECHTE Rechnung, kein bepreiste Menge."""
    erg = berechne_eauto_ersparnis_periode(
        km_pro_monat=[(2026, 1, 1000.0)],
        ladung_netz_kwh_gesamt=0.0,
        ladung_extern_euro_gesamt=77.0,
        wallbox_strompreis_cent=40.0,
        eauto_parameter={"vergleich_verbrauch_l_100km": 7.5},
        monats_strompreis_lookup={(2026, 1): 20.0},
        netz_pro_monat=[(2026, 1, 100.0)],
    )
    assert erg.strom_kosten_euro == pytest.approx(77.0)


def test_km_pro_monat_darf_ein_generator_sein():
    """Der Aufrufer übergibt oft einen Generator — er wird zweimal gebraucht.

    Vor der Listifizierung im Rumpf wäre er nach der Preis-Mittelung leer und
    die Benzinkosten still 0 gewesen.
    """
    erg = berechne_eauto_ersparnis_periode(
        km_pro_monat=((2026, m, 100.0) for m in (1, 2)),
        ladung_netz_kwh_gesamt=100.0,
        ladung_extern_euro_gesamt=0.0,
        wallbox_strompreis_cent=30.0,
        eauto_parameter={"vergleich_verbrauch_l_100km": 7.5},
        monats_benzinpreis_lookup={(2026, 1): 2.0, (2026, 2): 2.0},
        monats_strompreis_lookup={(2026, 1): 20.0, (2026, 2): 20.0},
    )
    assert erg.benzin_kosten_euro == pytest.approx(200 / 100 * 7.5 * 2.0)
    assert erg.verwendeter_strompreis_cent == pytest.approx(20.0)


def test_ohne_km_traegt_das_ergebnis_trotzdem_den_preis():
    """Frühausstieg bei 0 km — die Diagnostik darf nicht still 0 melden."""
    erg = berechne_eauto_ersparnis_periode(
        km_pro_monat=[],
        ladung_netz_kwh_gesamt=0.0,
        ladung_extern_euro_gesamt=0.0,
        wallbox_strompreis_cent=31.5,
        monats_strompreis_lookup={(2026, 1): 20.0},
        netz_pro_monat=[(2026, 1, 10.0)],
    )
    assert erg.verwendeter_strompreis_cent == pytest.approx(20.0)
