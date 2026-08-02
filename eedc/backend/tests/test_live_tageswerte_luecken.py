"""Regression: Live-Tageswerte behandeln eine Sensor-Lücke nach EINER Regel.

Hintergrund (Rainer-PN 89905 / Konzept `docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md`):
`_calc_tages_ev_hv` wandte auf vier Sensoren **drei** verschiedene Regeln an —
PV/Einspeisung fehlt → beide Werte weg, Batterie fehlt → still 0, Netzbezug
fehlt → `bezug or 0` und damit ein Hausverbrauch, der ohne jede Kennzeichnung zu
niedrig ausgeliefert wurde.

Regel nach §3: ein Wert wird geliefert, wenn **seine eigenen** Summanden da sind;
sonst `None`. Eine **gemessene 0** ist dabei ein Wert und keine Lücke
(`is not None`, nie `if val`).

Achtung beim Lesen der Fixtures: `get_tages_kwh`/`_compute_deltas` legen einen
Key nur an, wenn ein Wert existiert (s. `test_mqtt_compute_deltas_pv_aggregation`
::test_kein_pv_kein_pv_key). Eine Lücke ist hier also ein **fehlender Key**.
"""

from backend.services.live_power_service import LivePowerService

calc = LivePowerService._calc_tages_ev_hv


def test_vollstaendig_beide_werte():
    """Alle Summanden da → beide Werte stehen."""
    ev, hv = calc({
        "pv": 20.0, "einspeisung": 8.0, "netzbezug": 5.0,
        "batterie_1_ladung": 4.0, "batterie_1_entladung": 3.0,
    })
    # Direkt = 20 − 8 − 4 = 8 · EV = 8 + 3 = 11 · HV = 11 + 5 = 16
    assert ev == 11.0
    assert hv == 16.0


def test_netzbezug_fehlt_eigenverbrauch_bleibt():
    """Der Eigenverbrauch braucht den Netzbezug nicht — er bleibt stehen."""
    ev, hv = calc({"pv": 20.0, "einspeisung": 8.0})
    assert ev == 12.0


def test_netzbezug_fehlt_hausverbrauch_wird_unterdrueckt():
    """Kern des Fundes: `bezug or 0` lieferte den Hausverbrauch still zu niedrig.

    Vor dem Fix stand hier 12.0 (nämlich Eigenverbrauch + 0) — ein Wert, der wie
    ein gemessener aussah und um den gesamten Netzbezug zu niedrig war.
    """
    ev, hv = calc({"pv": 20.0, "einspeisung": 8.0})
    assert ev == 12.0
    assert hv is None


def test_pv_fehlt_eigenverbrauch_weg():
    """Ohne PV ist die Differenz nicht bestimmbar — Eigenverbrauch schweigt."""
    ev, hv = calc({"einspeisung": 8.0, "netzbezug": 5.0})
    assert ev is None
    assert hv is None


def test_einspeisung_fehlt_eigenverbrauch_weg():
    """Symmetrisch zur PV-Lücke — auch die Einspeisung ist ein Summand."""
    ev, hv = calc({"pv": 20.0, "netzbezug": 5.0})
    assert ev is None
    assert hv is None


def test_gemessene_null_beim_netzbezug_bleibt_null():
    """Gegenrichtung: 0 kWh Netzbezug ist eine Aussage, kein fehlender Wert."""
    ev, hv = calc({"pv": 20.0, "einspeisung": 8.0, "netzbezug": 0.0})
    assert ev == 12.0
    assert hv == 12.0


def test_gemessene_null_bei_der_batterie_bleibt_null():
    """Eine Batterie, die heute nichts tat, verfälscht nichts.

    `and v` filterte die 0 vorher aus der Summe — für die Summe folgenlos, aber
    es war die 0-Werte-Falle aus CLAUDE.md in genau der Form, die anderswo schon
    Werte gekostet hat.
    """
    ev, hv = calc({
        "pv": 20.0, "einspeisung": 8.0, "netzbezug": 5.0,
        "batterie_1_ladung": 0.0, "batterie_1_entladung": 0.0,
    })
    assert ev == 12.0
    assert hv == 17.0


def test_eigenverbrauch_null_und_netzbezug_da():
    """Nachts: keine PV-Nutzung, aber der Hausverbrauch ist voll bekannt."""
    ev, hv = calc({"pv": 0.0, "einspeisung": 0.0, "netzbezug": 7.0})
    assert ev == 0.0
    assert hv == 7.0


def test_leere_werte_liefern_nichts():
    """Ohne jeden Sensor gibt es nichts zu behaupten."""
    assert calc({}) == (None, None)
