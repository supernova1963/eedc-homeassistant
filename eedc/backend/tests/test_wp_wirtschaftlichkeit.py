"""Unit-Tests für `services/wp_wirtschaftlichkeit.berechne_wp_ersparnis`.

Bisher nur indirekt (T-Konto `is not None`) abgedeckt — dieser Wert-Pin
sichert die Migration der Altanlagen-Gaskosten-Formel auf den SoT-Helper
`gas_kosten_altanlage` ab (eine Arg-Vertauschung würde hier auffallen).
"""

from __future__ import annotations

from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis


def test_wp_ersparnis_gas_wert_gepinnt():
    """Gas (η 0,90), Wärme 1000, Strom 300 @ 30 ct, Gaspreis 10 ct.

    alte_heizung = (1000 / 0,90) * 10 / 100 = 111,111 €
    wp_kosten    = 300 * 30 / 100            =  90,000 €
    ersparnis    =                              21,111 €
    """
    r = berechne_wp_ersparnis(
        wp_waerme_kwh=1000.0,
        wp_strom_kwh=300.0,
        wp_strompreis_cent=30.0,
        wp_parameter={"alter_energietraeger": "gas"},
        monats_gaspreis_cent=10.0,
    )
    assert r.alte_heizung_kosten_euro == (1000.0 / 0.90) * 10.0 / 100
    assert r.wp_kosten_euro == 90.0
    assert r.ersparnis_euro == r.alte_heizung_kosten_euro - 90.0
    assert r.verwendeter_wirkungsgrad == 0.90
    assert r.verwendeter_gaspreis_cent == 10.0


def test_wp_ersparnis_oel_hoeherer_aufwand():
    """Öl-Wirkungsgrad (0,85) < Gas → höhere hypothetische Altkosten."""
    gas = berechne_wp_ersparnis(
        wp_waerme_kwh=1000.0, wp_strom_kwh=300.0, wp_strompreis_cent=30.0,
        wp_parameter={"alter_energietraeger": "gas"}, monats_gaspreis_cent=10.0,
    )
    oel = berechne_wp_ersparnis(
        wp_waerme_kwh=1000.0, wp_strom_kwh=300.0, wp_strompreis_cent=30.0,
        wp_parameter={"alter_energietraeger": "oel"}, monats_gaspreis_cent=10.0,
    )
    assert oel.alte_heizung_kosten_euro > gas.alte_heizung_kosten_euro


def test_wp_ersparnis_null_waerme():
    """Ohne Wärme: alles 0 (Frühausstieg)."""
    r = berechne_wp_ersparnis(
        wp_waerme_kwh=0.0, wp_strom_kwh=100.0, wp_strompreis_cent=30.0,
    )
    assert r.ersparnis_euro == 0.0
    assert r.alte_heizung_kosten_euro == 0.0
