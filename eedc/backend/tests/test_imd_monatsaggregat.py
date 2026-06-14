"""Unit-Tests für den per-Zeilen-Resolver `imd_typ_beitrag` (Block 1).

Sichert die Per-Typ-Feld-Auswahl + kanonischen Resolver ab — wenn jemand später
z. B. den WP-Wärme-Fallback ändert oder ein Feld dem falschen Typ zuordnet,
schlägt der Test sofort an. Kontrakt-Test, DB-frei.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.core.berechnungen import ImdTypBeitrag, imd_typ_beitrag


def _inv(typ, parameter=None):
    return SimpleNamespace(typ=typ, parameter=parameter or {})


def test_unbekannter_typ_leer():
    b = imd_typ_beitrag(_inv("wechselrichter"), {"pv_erzeugung_kwh": 100})
    assert b == ImdTypBeitrag(typ="wechselrichter")


def test_none_data():
    b = imd_typ_beitrag(_inv("speicher"), None)
    assert b.speicher_ladung == 0.0 and b.speicher_entladung == 0.0


def test_pv_modul():
    b = imd_typ_beitrag(_inv("pv-module"), {"pv_erzeugung_kwh": 1000})
    assert b.pv_erzeugung == 1000.0
    assert b.bkw_erzeugung == 0.0  # PV-Modul speist NICHT bkw_erzeugung


def test_pv_modul_legacy_fallback():
    # get_pv_erzeugung_kwh NUR für BKW; pv-module liest direkt pv_erzeugung_kwh
    b = imd_typ_beitrag(_inv("pv-module"), {"erzeugung_kwh": 500})
    assert b.pv_erzeugung == 0.0  # kein Legacy-Fallback für pv-module (IST-Stand)


def test_bkw_alle_felder():
    b = imd_typ_beitrag(_inv("balkonkraftwerk"), {
        "erzeugung_kwh": 120,  # Legacy-Fallback via get_pv_erzeugung_kwh
        "eigenverbrauch_kwh": 90,
        "speicher_ladung_kwh": 30, "speicher_entladung_kwh": 25,
    })
    assert b.bkw_erzeugung == 120.0
    assert b.bkw_eigenverbrauch == 90.0
    assert b.bkw_speicher_ladung == 30.0
    assert b.bkw_speicher_entladung == 25.0


def test_speicher_mit_arbitrage():
    b = imd_typ_beitrag(_inv("speicher"), {
        "ladung_kwh": 500, "entladung_kwh": 450,
        "ladung_netz_kwh": 120, "speicher_ladepreis_cent": 25,
    })
    assert b.speicher_ladung == 500.0
    assert b.speicher_entladung == 450.0
    assert b.speicher_arbitrage == 120.0
    assert b.speicher_ladepreis_cent == 25.0


def test_wp_getrennte_strommessung():
    b = imd_typ_beitrag(
        _inv("waermepumpe", {"getrennte_strommessung": True}),
        {"heizenergie_kwh": 800, "warmwasser_kwh": 200,
         "strom_heizen_kwh": 250, "strom_warmwasser_kwh": 80},
    )
    assert b.wp_strom == 330.0  # split: 250 + 80
    assert b.wp_heizung == 800.0
    assert b.wp_warmwasser == 200.0
    assert b.wp_waerme == 1000.0  # heizung + warmwasser
    assert b.wp_strom_heizen == 250.0
    assert b.wp_strom_warmwasser == 80.0
    assert b.wp_hat_split is True


def test_wp_ohne_split_gesamtsensor():
    b = imd_typ_beitrag(_inv("waermepumpe"), {
        "stromverbrauch_kwh": 400, "heizenergie_kwh": 900, "warmwasser_kwh": 250,
    })
    assert b.wp_strom == 400.0
    assert b.wp_hat_split is False
    assert b.wp_waerme == 1150.0


def test_wp_waerme_kwh_hat_vorrang():
    # D1: waerme_kwh überschreibt die heizung+warmwasser-Summe
    b = imd_typ_beitrag(_inv("waermepumpe"), {
        "waerme_kwh": 1234, "heizenergie_kwh": 800, "warmwasser_kwh": 200,
    })
    assert b.wp_waerme == 1234.0


def test_wp_heizung_legacy_fallback_d1():
    # D1-Kern: Legacy heizung_kwh wird kanonisch berücksichtigt
    b = imd_typ_beitrag(_inv("waermepumpe"), {"heizung_kwh": 700, "warmwasser_kwh": 100})
    assert b.wp_heizung == 700.0
    assert b.wp_waerme == 800.0


def test_eauto():
    b = imd_typ_beitrag(_inv("e-auto"), {
        "km_gefahren": 1500, "verbrauch_kwh": 300, "v2h_entladung_kwh": 50,
        "ladung_pv_kwh": 200, "ladung_netz_kwh": 100,
    })
    assert b.eauto_km == 1500.0
    assert b.eauto_verbrauch == 300.0
    assert b.eauto_v2h == 50.0
    assert b.eauto_ladung_kanonisch == 300.0  # ladung_kwh fehlt → verbrauch_kwh-Legacy
    assert b.eauto_ladung_pv_netz == 300.0    # 200 + 100


def test_wallbox():
    b = imd_typ_beitrag(_inv("wallbox"), {"ladung_kwh": 400, "ladung_pv_kwh": 250})
    assert b.wallbox_ladung == 400.0
    assert b.wallbox_ladung_pv == 250.0


@pytest.mark.parametrize("kategorie,erw_erz,erw_verb", [
    ("erzeuger", 300.0, 0.0),
    ("verbraucher", 0.0, 200.0),
    ("", 300.0, 200.0),  # leer → beide (Site-3-Verhalten)
])
def test_sonstiges_kategorien(kategorie, erw_erz, erw_verb):
    b = imd_typ_beitrag(
        _inv("sonstiges", {"kategorie": kategorie}),
        {"erzeugung_kwh": 300, "verbrauch_sonstig_kwh": 200},
    )
    assert b.sonstiges_erzeugung == erw_erz
    assert b.sonstiges_verbrauch == erw_verb
