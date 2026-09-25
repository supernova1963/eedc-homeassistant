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
    """Getrennte Strommessung **ohne** Gesamtzähler — die beiden Achsen tragen.

    ⛔ **Diese Probe hatte bis zum 14.09.2026 zusätzlich einen zugeordneten
    ``stromverbrauch_kwh`` („ignoriert bei split") und hielt fest, dass er
    **nicht** zählt.** Die Substanz, die sie sichert, ist die Doppelzählung:
    Gesamtzähler und Achsen laufen auf EINEN Ziel-Key, es darf immer nur eine
    Seite beitragen. Diese Substanz gilt unverändert — nur gewinnt seit WK-16d
    die andere Seite (K1), und dafür steht die Probe direkt darunter. Hier
    bleibt der Fall ohne Gesamtzähler: Die Achsen sind die einzige Messung.
    """
    inv = _inv(7, "waermepumpe", parameter={"getrennte_strommessung": True})
    sm = {"felder": {
        "strom_heizen_kwh": _sensor("sensor.wp_heiz_strom"),
        "strom_warmwasser_kwh": _sensor("sensor.wp_ww_strom"),
        "heizenergie_kwh": _sensor("sensor.wp_thermisch"),  # ignoriert
    }}
    b = investition_beitraege(inv, sm)
    felder = [x[0] for x in _fields_to_beitraege(b)]
    assert set(felder) == {"strom_heizen_kwh", "strom_warmwasser_kwh"}
    assert all(x[1] == "waermepumpe_7" for x in _fields_to_beitraege(b))


def test_wp_getrennte_strommessung_mit_gesamtzaehler_traegt_der_gesamtzaehler():
    """K1/WK-16d: Gesamtzähler zugeordnet ⇒ **er** trägt, die Achsen nicht.

    ⭐ **Die Doppelzählungs-Aussage der Probe darüber, mit getauschtem Sieger.**
    Beide Seiten laufen auf ``waermepumpe_7``; beide zu emittieren hieße, den
    Heiz- und Warmwasserstrom zweimal in die Tagesbilanz zu legen. Welche Seite
    gewinnt, entscheidet K1: die Gesamtmenge. Was sie **mehr** misst als die
    Achsen — Standby, Steuerung, Umwälzpumpen —, war vorher aus Tag, Monat,
    Kosten und CO₂ verschwunden.
    """
    inv = _inv(7, "waermepumpe", parameter={"getrennte_strommessung": True})
    sm = {"felder": {
        "strom_heizen_kwh": _sensor("sensor.wp_heiz_strom"),
        "strom_warmwasser_kwh": _sensor("sensor.wp_ww_strom"),
        "stromverbrauch_kwh": _sensor("sensor.wp_gesamt"),
    }}
    b = investition_beitraege(inv, sm)
    assert _fields_to_beitraege(b) == [
        ("stromverbrauch_kwh", "waermepumpe_7", +1, None),
    ]


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
    """Ladezähler UND Fahrverbrauch zugeordnet ⇒ genau EIN Beitrag: die Ladung.

    N-555 (Konzept Regel 6): gewählt wird nach der QUELLE, nicht mehr über eine
    Either-Or-Gruppe nach Tagesdaten. Die Substanz dieser Probe bleibt — das Auto
    zählt nur einmal, und die Ladung geht vor dem Fahrverbrauch —, nur die Form
    ist eine andere: der Fahrverbrauch wird gar nicht erst Kandidat, wenn ein
    Heimlade-Feld eine Quelle hat (bis 25.09.2026 sprang er ein, sobald der
    Ladezähler an einem Tag stumm war).
    """
    inv = _inv(1, "e-auto")
    sm = {"felder": {
        "ladung_kwh": _sensor("sensor.ea_lade"),
        "verbrauch_kwh": _sensor("sensor.ea_verbr"),
    }}
    b = investition_beitraege(inv, sm)
    assert [x.feld for x in b] == ["ladung_kwh"]
    assert all(x.target_key == "eauto_1" for x in b)


def test_eauto_verbrauch_nur_ohne_heimlade_quelle():
    """N-555: ohne jedes Heimlade-Feld mit Quelle ist der Fahrverbrauch die
    erlaubte Tages-/Stunden-Schätzung (Konzept Regel 6)."""
    inv = _inv(1, "e-auto")
    sm = {"felder": {"verbrauch_kwh": _sensor("sensor.ea_verbr")}}
    b = investition_beitraege(inv, sm)
    assert [x.feld for x in b] == ["verbrauch_kwh"]


def test_eauto_skip_wenn_parent_wallbox():
    inv = _inv(1, "e-auto", parent_investition_id=2)
    sm = {"felder": {"ladung_kwh": _sensor("sensor.ea")}}
    assert investition_beitraege(inv, sm) == []


def test_eauto_ladung_pv_netz_nicht_addiert():
    """Gesamt UND PV/Netz zugeordnet ⇒ die Ladung zählt EINMAL, nie Gesamt + Teile.

    N-555 (Konzept Regel 6; Fable-Runde 6, C3): „Heim: PV" + „Heim: Netz" SIND
    die Heimladung des Autos — mit Netz-Quelle gehen sie vor dem alten
    Gesamtwert (dieselbe Lesart wie der Monat, `get_emob_pv_netz_kwh`). Bis
    25.09.2026 wurden sie am Tag ignoriert; die Substanz dieser Probe — keine
    Doppelzählung von Gesamt und Teilen — bleibt.
    """
    inv = _inv(1, "e-auto")
    sm = {"felder": {
        "ladung_kwh": _sensor("sensor.ea"),
        "ladung_pv_kwh": _sensor("sensor.ea_pv"),
        "ladung_netz_kwh": _sensor("sensor.ea_netz"),
    }}
    b = investition_beitraege(inv, sm)
    felder = {x.feld for x in b}
    assert felder == {"ladung_pv_kwh", "ladung_netz_kwh"}
    assert "ladung_kwh" not in felder


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
