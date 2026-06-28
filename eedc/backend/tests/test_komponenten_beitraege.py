"""
Unit-Tests für den Per-Typ-Beitrags-Helper (v3.33.0, Issue #290).

Sichert die exakte Per-Typ-Auswahl ab — wenn jemand morgen den Helper
ändert und z. B. `ladung_netz_kwh` versehentlich für Wallbox aktiviert,
schlägt der Test sofort an.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.services.snapshot.komponenten_beitraege import (
    KomponentenBeitrag,
    basis_beitraege,
    investition_beitraege,
)


def _inv(inv_id, typ, parameter=None, parent_investition_id=None):
    return SimpleNamespace(
        id=inv_id,
        typ=typ,
        parameter=parameter or {},
        parent_investition_id=parent_investition_id,
    )


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def _fields_to_beitraege(beitraege):
    return [(b.feld, b.target_key, b.vorzeichen, b.fallback_gruppe) for b in beitraege]


# ─── Basis ─────────────────────────────────────────────────────────────────

def test_basis_einspeisung_und_netzbezug():
    sm = {"basis": {
        "einspeisung": _sensor("sensor.einsp"),
        "netzbezug": _sensor("sensor.bezug"),
    }}
    b = basis_beitraege(sm)
    assert _fields_to_beitraege(b) == [
        ("einspeisung", "einspeisung", +1, None),
        ("netzbezug", "netzbezug", +1, None),
    ]


def test_basis_ohne_sensor_id_uebersprungen():
    sm = {"basis": {
        "einspeisung": {"strategie": "sensor", "sensor_id": None},
        "netzbezug": {"strategie": "manuell"},
    }}
    assert basis_beitraege(sm) == []


def test_basis_leer():
    assert basis_beitraege({}) == []
    assert basis_beitraege({"basis": None}) == []


# ─── PV-Module / BKW ──────────────────────────────────────────────────────

def test_pv_module_nur_pv_erzeugung():
    inv = _inv(3, "pv-module")
    sm = {"felder": {
        "pv_erzeugung_kwh": _sensor("sensor.pv"),
        "ladung_kwh": _sensor("sensor.wtf"),  # darf NICHT durchschlagen
    }}
    b = investition_beitraege(inv, sm)
    assert _fields_to_beitraege(b) == [("pv_erzeugung_kwh", "pv_3", +1, None)]


def test_balkonkraftwerk_bkw_key():
    inv = _inv(11, "balkonkraftwerk")
    sm = {"felder": {"pv_erzeugung_kwh": _sensor("sensor.bkw")}}
    b = investition_beitraege(inv, sm)
    assert _fields_to_beitraege(b) == [("pv_erzeugung_kwh", "bkw_11", +1, None)]


# ─── Speicher ──────────────────────────────────────────────────────────────

def test_speicher_ladung_und_entladung():
    inv = _inv(5, "speicher")
    sm = {"felder": {
        "ladung_kwh": _sensor("sensor.lade"),
        "entladung_kwh": _sensor("sensor.entlade"),
    }}
    b = investition_beitraege(inv, sm)
    # Konvention: ENTLADUNG positiv (Quelle), LADUNG negativ (Senke) — identisch
    # zur batterie_kw-Spalte (SoT core.berechnungen.batterie_kw_spalte).
    assert _fields_to_beitraege(b) == [
        ("ladung_kwh", "batterie_5", -1, None),
        ("entladung_kwh", "batterie_5", +1, None),
    ]


def test_speicher_ladung_netz_kwh_nicht_addiert():
    """Arbitrage-Bug: ladung_netz_kwh ist Teilmenge von ladung_kwh."""
    inv = _inv(5, "speicher")
    sm = {"felder": {
        "ladung_kwh": _sensor("sensor.lade"),
        "entladung_kwh": _sensor("sensor.entlade"),
        "ladung_netz_kwh": _sensor("sensor.lade_netz"),
    }}
    b = investition_beitraege(inv, sm)
    felder = [x[0] for x in _fields_to_beitraege(b)]
    assert "ladung_netz_kwh" not in felder
    assert set(felder) == {"ladung_kwh", "entladung_kwh"}


# ─── Wärmepumpe ────────────────────────────────────────────────────────────

def test_wp_nur_stromverbrauch_wenn_kein_split():
    inv = _inv(7, "waermepumpe", parameter={"getrennte_strommessung": False})
    sm = {"felder": {
        "stromverbrauch_kwh": _sensor("sensor.wp_strom"),
        "heizenergie_kwh": _sensor("sensor.wp_heiz_thermisch"),  # darf NICHT
        "warmwasser_kwh": _sensor("sensor.wp_ww_thermisch"),  # darf NICHT
        "wp_starts_anzahl": _sensor("sensor.wp_starts"),  # Counter — NICHT in kWh
    }}
    b = investition_beitraege(inv, sm)
    assert _fields_to_beitraege(b) == [
        ("stromverbrauch_kwh", "waermepumpe_7", +1, None),
    ]


def test_wp_getrennte_strommessung():
    inv = _inv(7, "waermepumpe", parameter={"getrennte_strommessung": True})
    sm = {"felder": {
        "strom_heizen_kwh": _sensor("sensor.wp_heiz_strom"),
        "strom_warmwasser_kwh": _sensor("sensor.wp_ww_strom"),
        "stromverbrauch_kwh": _sensor("sensor.wp_gesamt"),  # ignoriert bei split
        "heizenergie_kwh": _sensor("sensor.wp_thermisch"),  # ignoriert
    }}
    b = investition_beitraege(inv, sm)
    felder = [x[0] for x in _fields_to_beitraege(b)]
    assert set(felder) == {"strom_heizen_kwh", "strom_warmwasser_kwh"}
    assert all(x[1] == "waermepumpe_7" for x in _fields_to_beitraege(b))


# ─── Wallbox ───────────────────────────────────────────────────────────────

def test_wallbox_nur_ladung_kwh():
    """Gernot-Bug: ladung_pv_kwh + ladung_netz_kwh sind Teilmengen."""
    inv = _inv(2, "wallbox")
    sm = {"felder": {
        "ladung_kwh": _sensor("sensor.wb"),
        "ladung_pv_kwh": _sensor("sensor.wb_pv"),
        "ladung_netz_kwh": _sensor("sensor.wb_netz"),
    }}
    b = investition_beitraege(inv, sm)
    assert _fields_to_beitraege(b) == [("ladung_kwh", "wallbox_2", +1, None)]


# ─── E-Auto ───────────────────────────────────────────────────────────────

def test_eauto_either_or_ladung_dann_verbrauch():
    inv = _inv(1, "e-auto")
    sm = {"felder": {
        "ladung_kwh": _sensor("sensor.ea_lade"),
        "verbrauch_kwh": _sensor("sensor.ea_verbr"),
    }}
    b = investition_beitraege(inv, sm)
    assert len(b) == 2
    assert b[0].feld == "ladung_kwh"
    assert b[1].feld == "verbrauch_kwh"
    # gleiche fallback_gruppe
    assert b[0].fallback_gruppe == b[1].fallback_gruppe
    assert b[0].fallback_gruppe is not None
    assert all(x.target_key == "eauto_1" for x in b)


def test_eauto_skip_wenn_parent_wallbox():
    inv = _inv(1, "e-auto", parent_investition_id=2)
    sm = {"felder": {"ladung_kwh": _sensor("sensor.ea")}}
    assert investition_beitraege(inv, sm) == []


def test_eauto_ladung_pv_netz_nicht_addiert():
    """Wenn jemand ladung_pv_kwh/ladung_netz_kwh mappt: ignorieren."""
    inv = _inv(1, "e-auto")
    sm = {"felder": {
        "ladung_kwh": _sensor("sensor.ea"),
        "ladung_pv_kwh": _sensor("sensor.ea_pv"),
        "ladung_netz_kwh": _sensor("sensor.ea_netz"),
    }}
    b = investition_beitraege(inv, sm)
    # Nur Either-Or für ladung_kwh + verbrauch_kwh — beide Split-Felder raus
    felder = {x.feld for x in b}
    assert felder == {"ladung_kwh"}  # verbrauch_kwh nicht gemappt


# ─── Sonstiges ─────────────────────────────────────────────────────────────

def test_sonstiges_verbraucher_nur_einmal_positiv():
    """Auch wenn beide gemappt, kommt nur ein +1-Wert raus."""
    inv = _inv(13, "sonstiges", parameter={"kategorie": "verbraucher"})
    sm = {"felder": {
        "verbrauch_kwh": _sensor("sensor.pool_verbr"),
        "erzeugung_kwh": _sensor("sensor.pool_erz"),  # darf nicht aufaddieren
    }}
    b = investition_beitraege(inv, sm)
    assert len(b) == 2
    assert b[0].feld == "verbrauch_kwh"  # primary für verbraucher
    assert b[1].feld == "erzeugung_kwh"  # secondary fallback
    assert b[0].vorzeichen == +1
    assert b[1].vorzeichen == +1
    assert b[0].fallback_gruppe == b[1].fallback_gruppe
    assert all(x.target_key == "sonstige_13" for x in b)


def test_sonstiges_erzeuger_primary_erzeugung():
    inv = _inv(14, "sonstiges", parameter={"kategorie": "erzeuger"})
    sm = {"felder": {
        "erzeugung_kwh": _sensor("sensor.x_erz"),
    }}
    b = investition_beitraege(inv, sm)
    assert b[0].feld == "erzeugung_kwh"
    assert b[0].vorzeichen == +1


def test_sonstiges_fallback_nur_secondary_gemappt():
    inv = _inv(13, "sonstiges", parameter={"kategorie": "verbraucher"})
    sm = {"felder": {
        "erzeugung_kwh": _sensor("sensor.x"),  # nur secondary
    }}
    b = investition_beitraege(inv, sm)
    # primary nicht gemappt, secondary fallback wird verwendet
    assert len(b) == 1
    assert b[0].feld == "erzeugung_kwh"


# ─── Unbekannte / Edge Cases ──────────────────────────────────────────────

def test_unbekannter_typ_leer():
    inv = _inv(99, "wechselrichter")
    sm = {"felder": {"foo_kwh": _sensor("sensor.foo")}}
    assert investition_beitraege(inv, sm) == []


def test_keine_felder_leer():
    inv = _inv(3, "pv-module")
    assert investition_beitraege(inv, {}) == []
    assert investition_beitraege(inv, None) == []


_TESTS = [
    test_basis_einspeisung_und_netzbezug,
    test_basis_ohne_sensor_id_uebersprungen,
    test_basis_leer,
    test_pv_module_nur_pv_erzeugung,
    test_balkonkraftwerk_bkw_key,
    test_speicher_ladung_und_entladung,
    test_speicher_ladung_netz_kwh_nicht_addiert,
    test_wp_nur_stromverbrauch_wenn_kein_split,
    test_wp_getrennte_strommessung,
    test_wallbox_nur_ladung_kwh,
    test_eauto_either_or_ladung_dann_verbrauch,
    test_eauto_skip_wenn_parent_wallbox,
    test_eauto_ladung_pv_netz_nicht_addiert,
    test_sonstiges_verbraucher_nur_einmal_positiv,
    test_sonstiges_erzeuger_primary_erzeugung,
    test_sonstiges_fallback_nur_secondary_gemappt,
    test_unbekannter_typ_leer,
    test_keine_felder_leer,
]
