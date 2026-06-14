"""Unit-Tests für den Alternativkosten-Berechnungs-Layer
(`core/berechnungen/alternativkosten.py`).

Reine Funktionen, DB-/Service-frei — getestet mit leichten Stand-ins
(``SimpleNamespace`` liefert ``.id``/``.parameter``). Die End-to-End-
Charakterisierung über `calculate_anlage_sensors` liegt in
`test_ha_export_alternativkosten.py`.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.core.berechnungen import (
    berechne_bkw_alternativkosten_ersparnis,
    berechne_wp_alternativkosten_ersparnis,
    gas_kosten_altanlage,
)


def _wp(id_: int, parameter=None):
    return SimpleNamespace(id=id_, parameter=parameter or {})


def _wp_imd(inv_id: int, jahr=2025):
    return {
        (inv_id, jahr, m): {
            "heizenergie_kwh": 200.0,
            "warmwasser_kwh": 50.0,
            "stromverbrauch_kwh": 80.0,
        }
        for m in range(1, 13)
    }


def test_wp_gas_default():
    """Gas-WP (Default 0,90 / 12 ct / PV-Anteil 50 %), kein Monats-Gaspreis:
    pro Monat 250/0,90×12/100 − 80×0,5×0,30 = 33,3333 − 12 = 21,3333 → 256 €/J."""
    out = berechne_wp_alternativkosten_ersparnis(
        [_wp(1)], _wp_imd(1), {}, 30.0,
    )
    assert abs(out - 256.0) < 1e-6


def test_wp_oel_und_monats_gaspreis_schlaegt_default():
    """Öl (0,85) + Monats-Gaspreis 15 ct überstimmt den Parameter-Default:
    250/0,85×15/100 − 12 = 44,1176 − 12 = 32,1176 → ×12 = 385,41 €/J."""
    gaspreis = {(2025, m): 15.0 for m in range(1, 13)}
    out = berechne_wp_alternativkosten_ersparnis(
        [_wp(1, {"alter_energietraeger": "oel"})], _wp_imd(1), gaspreis, 30.0,
    )
    assert abs(out - 385.41) < 0.01


def test_wp_per_wp_parameter_kein_last_write_wins():
    """Zwei WPs (Gas + Öl) müssen je eigenen Wirkungsgrad nutzen — die Summe
    ist Gas-Beitrag (256) + Öl-Beitrag (Default-Gaspreis 12 ct):
    Öl: 250/0,85×12/100 − 12 = 35,2941 − 12 = 23,2941 → ×12 = 279,53 €.
    Σ = 256 + 279,53 = 535,53 €. Bei last-write-wins (beide Öl) wäre es 559,06 €."""
    imd = {**_wp_imd(1), **_wp_imd(2)}
    out = berechne_wp_alternativkosten_ersparnis(
        [_wp(1), _wp(2, {"alter_energietraeger": "oel"})], imd, {}, 30.0,
    )
    assert abs(out - (256.0 + 279.53)) < 0.05


def test_wp_zusatzkosten_anteilig_pro_erfasstem_monat():
    """Fixe Zusatzkosten/Jahr werden anteilig pro erfasstem Monat addiert.
    Mit 6 erfassten Monaten und 120 €/J Zusatzkosten: 120 × 6/12 = 60 € obendrauf.
    WP-Ersparnis pro Monat (Gas) = 21,3333 € → 6 Monate = 128 € + 60 = 188 €."""
    imd = {
        (1, 2025, m): {
            "heizenergie_kwh": 200.0, "warmwasser_kwh": 50.0,
            "stromverbrauch_kwh": 80.0,
        }
        for m in range(1, 7)
    }
    out = berechne_wp_alternativkosten_ersparnis(
        [_wp(1, {"alternativ_zusatzkosten_jahr": 120.0})], imd, {}, 30.0,
    )
    assert abs(out - (128.0 + 60.0)) < 0.01


def test_wp_leer():
    assert berechne_wp_alternativkosten_ersparnis([], {}, {}, 30.0) == 0.0


def test_bkw_eigenverbrauch_zum_netzpreis():
    """12 × 40 kWh × 30 ct/100 = 144 €."""
    imd = {(2, 2025, m): {"eigenverbrauch_kwh": 40.0} for m in range(1, 13)}
    out = berechne_bkw_alternativkosten_ersparnis(
        [SimpleNamespace(id=2)], imd, 30.0,
    )
    assert abs(out - 144.0) < 1e-6


def test_bkw_ignoriert_fremde_inv_ids():
    """Nur IMD der BKW-Investition zählen — andere Komponenten bleiben außen vor."""
    imd = {
        (2, 2025, 1): {"eigenverbrauch_kwh": 40.0},
        (99, 2025, 1): {"eigenverbrauch_kwh": 1000.0},  # fremde Investition
    }
    out = berechne_bkw_alternativkosten_ersparnis(
        [SimpleNamespace(id=2)], imd, 30.0,
    )
    assert abs(out - (40.0 * 0.30)) < 1e-6


def test_bkw_leer():
    assert berechne_bkw_alternativkosten_ersparnis([], {}, 30.0) == 0.0


# ============================================================================
# gas_kosten_altanlage — Fragment-Helper (SoT der „bisherige fossile Heizung"-
# Energiekosten). Konsolidiert die zuvor 4× duplizierte Inline-Formel.
# ============================================================================


def test_gas_kosten_altanlage_grundfall():
    """(1000 / 0,90) * 10 / 100 = 111,111 €."""
    assert gas_kosten_altanlage(1000.0, 0.90, 10.0) == (1000.0 / 0.90) * 10.0 / 100


def test_gas_kosten_altanlage_oel_wirkungsgrad():
    """Niedrigerer Öl-Wirkungsgrad → höhere hypothetische Kosten."""
    gas = gas_kosten_altanlage(1000.0, 0.90, 10.0)
    oel = gas_kosten_altanlage(1000.0, 0.85, 10.0)
    assert oel > gas


def test_gas_kosten_altanlage_null_waerme():
    assert gas_kosten_altanlage(0.0, 0.90, 10.0) == 0.0


def test_gas_kosten_altanlage_byte_identisch_zur_inline_formel():
    """Verhaltens-Garantie für die Migration: identisch zur bisherigen
    Inline-Berechnung `(waerme / wirkungsgrad) * gaspreis / 100` (gleiche
    Operations-Reihenfolge → keine Float-Abweichung)."""
    for waerme, wg, preis in [(800.0, 0.9, 12.0), (1234.5, 0.85, 9.3), (300.0, 0.9, 0.0)]:
        assert gas_kosten_altanlage(waerme, wg, preis) == (waerme / wg) * preis / 100
