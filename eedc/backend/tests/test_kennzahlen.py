"""Block 3 — Helper-Unit-Tests für Autarkie / Eigenverbrauchsquote / spez. Ertrag."""

from __future__ import annotations

import pytest

from backend.core.berechnungen import (
    autarkie_prozent,
    eigenverbrauchsquote_prozent,
    spezifischer_ertrag_kwh_kwp,
)


def test_autarkie_normal():
    assert autarkie_prozent(600, 1000) == pytest.approx(60.0)


def test_autarkie_kein_verbrauch():
    assert autarkie_prozent(0, 0) == 0.0
    assert autarkie_prozent(500, 0) == 0.0


def test_ev_quote_normal():
    assert eigenverbrauchsquote_prozent(300, 1000) == pytest.approx(30.0)


def test_ev_quote_cap_bei_100():
    # Drift kann >100 % ergeben → gecappt (Maintainer-Entscheid)
    assert eigenverbrauchsquote_prozent(1200, 1000) == 100.0


def test_ev_quote_keine_erzeugung():
    assert eigenverbrauchsquote_prozent(500, 0) == 0.0


def test_spez_ertrag_normal():
    assert spezifischer_ertrag_kwh_kwp(8500, 10) == pytest.approx(850.0)


def test_spez_ertrag_keine_leistung_none():
    assert spezifischer_ertrag_kwh_kwp(8500, 0) is None
    assert spezifischer_ertrag_kwh_kwp(8500, None) is None


def test_spez_ertrag_keine_erzeugung_none():
    """N-355: eine Division braucht BEIDE Operanden.

    Bis dahin deckte die Regel nur den Nenner ab, und `aktueller_monat.py`
    reichte `pv or 0` herein — ein Monat ohne gemessene PV-Zahl bekam damit
    `0,0 kWh/kWp`, eine Zahl, die wie eine Messung aussieht.
    """
    assert spezifischer_ertrag_kwh_kwp(None, 10) is None


def test_spez_ertrag_gemessene_null_bleibt_null():
    """Die Gegenrichtung, und sie ist der Punkt der ganzen Unterscheidung.

    Ohne diese Probe wäre der Fix auch dann grün, wenn er **jede** Null
    unterdrückt. Ein Monat, in dem die Anlage nachweislich nichts geliefert hat
    (gemessene 0 kWh), hat einen spezifischen Ertrag von 0 — das ist ein
    Ergebnis, keine Lücke.
    """
    assert spezifischer_ertrag_kwh_kwp(0.0, 10) == 0.0
