"""Unit-Tests für die Konsistenz-Invarianten des Berechnungs-Layers.

Aktuell: Speicher-Ladung-Konsistenz (#281) — `ladung_netz_kwh` ⊆ `ladung_kwh`.
Der implizite PV-Anteil `ladung_kwh − ladung_netz_kwh` darf nie negativ werden.
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen import (
    assert_speicher_ladung_konsistent,
    pruefe_speicher_ladung_konsistenz,
)


def test_netz_unter_gesamt_ist_konsistent():
    bericht = pruefe_speicher_ladung_konsistenz(ladung_kwh=100.0, ladung_netz_kwh=30.0)
    assert bericht.konsistent
    assert bericht.erwartet == 100.0
    assert bericht.tatsaechlich == 30.0
    assert bericht.details == ""


def test_netz_gleich_gesamt_ist_konsistent():
    bericht = pruefe_speicher_ladung_konsistenz(ladung_kwh=80.0, ladung_netz_kwh=80.0)
    assert bericht.konsistent


def test_reiner_pv_speicher_ohne_netz_ist_konsistent():
    bericht = pruefe_speicher_ladung_konsistenz(ladung_kwh=120.0, ladung_netz_kwh=0.0)
    assert bericht.konsistent


def test_beide_none_ist_konsistent():
    # None → 0.0: 0 ≤ 0 ist gültig (Monat ohne erfasste Ladung).
    bericht = pruefe_speicher_ladung_konsistenz(ladung_kwh=None, ladung_netz_kwh=None)
    assert bericht.konsistent


def test_kleine_ueberschreitung_innerhalb_toleranz():
    # Rundungs-Rauschen: netz minimal über gesamt, innerhalb Default-Toleranz 0.1.
    bericht = pruefe_speicher_ladung_konsistenz(ladung_kwh=50.0, ladung_netz_kwh=50.05)
    assert bericht.konsistent


def test_netz_ueber_gesamt_ist_inkonsistent():
    bericht = pruefe_speicher_ladung_konsistenz(ladung_kwh=100.0, ladung_netz_kwh=120.0)
    assert not bericht.konsistent
    assert bericht.details  # nicht-leere Diagnose
    assert "#281" in bericht.details


def test_netz_gesetzt_aber_gesamt_fehlt_ist_inkonsistent():
    # Netz-Wert ohne Gesamt-Wert: gesamt=None→0, netz=50 > 0 → Verstoß.
    bericht = pruefe_speicher_ladung_konsistenz(ladung_kwh=None, ladung_netz_kwh=50.0)
    assert not bericht.konsistent


def test_assert_wirft_bei_verstoss():
    with pytest.raises(AssertionError):
        assert_speicher_ladung_konsistent(ladung_kwh=10.0, ladung_netz_kwh=99.0)


def test_assert_schweigt_bei_konsistenz():
    # Kein Fehler bei gültigen Werten.
    assert_speicher_ladung_konsistent(ladung_kwh=100.0, ladung_netz_kwh=40.0)
