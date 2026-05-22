"""Unit-Tests für die Konsistenz-Invarianten des Berechnungs-Layers.

Speicher-Ladung-Konsistenz (#281) — `ladung_netz_kwh` ⊆ `ladung_kwh`.
Der implizite PV-Anteil `ladung_kwh − ladung_netz_kwh` darf nie negativ werden.

Zwei Varianten:
- `pruefe_speicher_ladung_konsistenz` — strikt, für in sich geschlossene Werte.
- `pruefe_speicher_netzladung_kumulativ` — kumulativ über die Historie; pro
  Monat ist ein kleiner Überhang durch Zähler-Schnappschüsse an der Monats-
  grenze legitim (rapahl-PN 2026-05-22).
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen import (
    assert_speicher_ladung_konsistent,
    assert_speicher_netzladung_kumulativ,
    pruefe_speicher_ladung_konsistenz,
    pruefe_speicher_netzladung_kumulativ,
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


# --- Kumulative Netzladung-Konsistenz (rapahl-PN 2026-05-22) -----------------

def test_kumulativ_netz_unter_gesamt_konsistent():
    bericht = pruefe_speicher_netzladung_kumulativ(
        ladung_kwh_gesamt=10000.0, ladung_netz_kwh_gesamt=4000.0
    )
    assert bericht.konsistent
    assert bericht.details == ""


def test_kumulativ_netz_gleich_gesamt_konsistent():
    bericht = pruefe_speicher_netzladung_kumulativ(
        ladung_kwh_gesamt=8000.0, ladung_netz_kwh_gesamt=8000.0
    )
    assert bericht.konsistent


def test_kumulativ_carry_over_an_monatsgrenze_konsistent():
    # rapahl-Fall: ein Ladevorgang über die Dez/Jan-Grenze lässt die
    # kumulierte Netzladung minimal über der Gesamtladung liegen, weil der
    # Nachbarmonat am Rand des Datenfensters den Überhang noch nicht
    # ausgeglichen hat. Innerhalb der relativen Toleranz → konsistent.
    bericht = pruefe_speicher_netzladung_kumulativ(
        ladung_kwh_gesamt=10000.0, ladung_netz_kwh_gesamt=10001.0
    )
    assert bericht.konsistent


def test_kumulativ_echter_erfassungsfehler_inkonsistent():
    # `ladung_kwh` als reine PV-Ladung gepflegt: die kumulierte Netzladung
    # übersteigt die Gesamtladung systematisch und weit über die Toleranz.
    bericht = pruefe_speicher_netzladung_kumulativ(
        ladung_kwh_gesamt=6000.0, ladung_netz_kwh_gesamt=9000.0
    )
    assert not bericht.konsistent
    assert "#281" in bericht.details


def test_kumulativ_beide_none_konsistent():
    bericht = pruefe_speicher_netzladung_kumulativ(
        ladung_kwh_gesamt=None, ladung_netz_kwh_gesamt=None
    )
    assert bericht.konsistent


def test_assert_kumulativ_wirft_bei_verstoss():
    with pytest.raises(AssertionError):
        assert_speicher_netzladung_kumulativ(
            ladung_kwh_gesamt=1000.0, ladung_netz_kwh_gesamt=5000.0
        )


def test_assert_kumulativ_schweigt_bei_konsistenz():
    assert_speicher_netzladung_kumulativ(
        ladung_kwh_gesamt=10000.0, ladung_netz_kwh_gesamt=3000.0
    )
