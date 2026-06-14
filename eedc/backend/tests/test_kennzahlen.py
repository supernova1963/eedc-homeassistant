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
