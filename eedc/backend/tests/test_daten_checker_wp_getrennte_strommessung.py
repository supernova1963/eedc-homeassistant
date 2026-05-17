"""
Daten-Checker: WP mit `getrennte_strommessung=True` darf NICHT als
unvollständig gemeldet werden, wenn `strom_heizen_kwh` und
`strom_warmwasser_kwh` korrekt im Sensor-Mapping sitzen.

Trigger: dietmar1968 Forum-PN 2026-05-17 (Premium-Setup mit Stiebel-
Boiler-Sensoren, vier Energie-Slots vollständig gemappt — Checker
meldete trotzdem "kWh-Zähler fehlt", weil er hartcodiert nach dem
Legacy-Feld `stromverbrauch_kwh` suchte).

Self-contained:

    eedc/backend/venv/bin/python -m pytest eedc/backend/tests/test_daten_checker_wp_getrennte_strommessung.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.models import Anlage, Investition  # noqa: E402
from backend.services.daten_checker import (  # noqa: E402
    CheckKategorie,
    CheckSeverity,
    DatenChecker,
)


def _make_anlage(*, getrennte_strommessung: bool, vollstaendig: bool) -> Anlage:
    """Anlage + WP-Investition + Sensor-Mapping konstruieren."""
    anlage = Anlage(id=1, anlagenname="Test", leistung_kwp=10.0)
    inv = Investition(
        id=42,
        anlage_id=1,
        typ="waermepumpe",
        bezeichnung="Test-WP",
        aktiv=True,
        parameter={"getrennte_strommessung": getrennte_strommessung},
    )
    anlage.investitionen = [inv]

    if getrennte_strommessung:
        felder = {
            "strom_heizen_kwh": {"strategie": "sensor", "sensor_id": "sensor.wp_heizen"},
            "strom_warmwasser_kwh": {"strategie": "sensor", "sensor_id": "sensor.wp_ww"},
        }
        if not vollstaendig:
            felder.pop("strom_warmwasser_kwh")
    else:
        felder = {}
        if vollstaendig:
            felder["stromverbrauch_kwh"] = {
                "strategie": "sensor", "sensor_id": "sensor.wp_total",
            }

    # Basis-Zähler ebenfalls mappen, damit der Basis-Check nicht querschlägt
    anlage.sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einspeisung"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.netzbezug"},
        },
        "investitionen": {str(inv.id): {"felder": felder}},
    }
    return anlage


def test_getrennte_strommessung_vollstaendig_ist_ok():
    """Premium-Setup (dietmar1968): beide Splitsensoren gemappt → OK."""
    anlage = _make_anlage(getrennte_strommessung=True, vollstaendig=True)
    svc = DatenChecker(db=None)  # _check_energieprofil_abdeckung ist sync ohne DB-Zugriff
    ergebnisse = svc._check_energieprofil_abdeckung(anlage)
    # Es darf KEIN Warning auftauchen, dass kWh-Zähler-Abdeckung fehlt
    warnings = [e for e in ergebnisse if e.schwere == CheckSeverity.WARNING]
    assert not warnings, (
        f"Bei getrennte_strommessung=True + beiden Splitsensoren gemappt darf "
        f"kein WARNING kommen. Gefunden: {[w.meldung for w in warnings]}"
    )
    # Stattdessen: OK-Meldung "Alle ... Komponenten haben kWh-Zähler gemappt"
    oks = [e for e in ergebnisse if e.schwere == CheckSeverity.OK]
    assert oks, "OK-Meldung erwartet, keine gefunden"


def test_getrennte_strommessung_unvollstaendig_meldet_fehlend():
    """Wenn nur ein Splitsensor da ist (z.B. nur strom_heizen_kwh), warnen."""
    anlage = _make_anlage(getrennte_strommessung=True, vollstaendig=False)
    svc = DatenChecker(db=None)
    ergebnisse = svc._check_energieprofil_abdeckung(anlage)
    warnings = [e for e in ergebnisse if e.schwere == CheckSeverity.WARNING]
    assert warnings, "Warning erwartet bei unvollständigen Splitsensoren"
    assert "strom_warmwasser_kwh" in warnings[0].details, (
        f"Fehlender Slot soll im Detail-Text genannt sein. Got: {warnings[0].details}"
    )


def test_legacy_pfad_unveraendert():
    """getrennte_strommessung=False + stromverbrauch_kwh gemappt → OK (unverändertes Verhalten)."""
    anlage = _make_anlage(getrennte_strommessung=False, vollstaendig=True)
    svc = DatenChecker(db=None)
    ergebnisse = svc._check_energieprofil_abdeckung(anlage)
    warnings = [e for e in ergebnisse if e.schwere == CheckSeverity.WARNING]
    assert not warnings, f"Legacy-Pfad: kein WARNING erwartet. Got: {[w.meldung for w in warnings]}"


def test_legacy_pfad_ohne_mapping_warnt():
    """getrennte_strommessung=False + kein stromverbrauch_kwh → WARNING."""
    anlage = _make_anlage(getrennte_strommessung=False, vollstaendig=False)
    svc = DatenChecker(db=None)
    ergebnisse = svc._check_energieprofil_abdeckung(anlage)
    warnings = [e for e in ergebnisse if e.schwere == CheckSeverity.WARNING]
    assert warnings, "Warning erwartet wenn weder Split- noch Gesamt-Sensor"
    assert "stromverbrauch_kwh" in warnings[0].details
