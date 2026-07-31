"""Unit-Tests für `bkw_finanz_beitrag` — welcher BKW-Wert die Finanz-Zeile trägt.

Reine Funktion, DB-/Service-frei (ADR-001). Die End-zu-End-Wirkung über alle
vier Read-Sites liegt in `test_netto_ertrag_vier_wege_symmetrie.py`, die
Schreib-Seite bewacht `test_wurzelmuster_konformitaet.py::test_p9_*`.

Die Invariante (ADR-002/P9): ein Energiefluss trägt genau einmal zum
Finanz-Netto bei. Weil die BKW-Erzeugung in dieselbe Summe fließt, aus der der
Eigenverbrauch abgeleitet wird, ist der gemessene BKW-Eigenverbrauch **kein**
Zusatzposten — er ist der Ersatzträger für den Fall, dass keine Erzeugung
erfasst ist.
"""

from __future__ import annotations

from backend.core.berechnungen import bkw_finanz_beitrag


def test_erzeugung_erfasst_traegt_die_erzeugung():
    """Der Normalfall (`pv_erzeugung_kwh` ist BKW-Pflichtfeld): die Erzeugung
    geht in die PV-Summe, ein Rest-Term entsteht nicht."""
    out = bkw_finanz_beitrag(erzeugung_kwh=200.0, eigenverbrauch_kwh=0.0)

    assert out.erzeugung_kwh == 200.0
    assert out.rest_eigenverbrauch_kwh == 0.0


def test_beide_erfasst_traegt_trotzdem_nur_die_erzeugung():
    """Der Doppelzählungs-Fall. Ein gemessener Eigenverbrauch NEBEN der
    Erzeugung ist eine Aufschlüsselung derselben Energie, keine zweite
    Position — die Ableitung aus der PV-Summe deckt ihn bereits ab."""
    out = bkw_finanz_beitrag(erzeugung_kwh=200.0, eigenverbrauch_kwh=150.0)

    assert out.erzeugung_kwh == 200.0
    assert out.rest_eigenverbrauch_kwh == 0.0


def test_nur_eigenverbrauch_traegt_den_rest_term():
    """Datenlücke: ohne Erzeugung kennt die PV-Summe das BKW nicht, der
    gemessene Eigenverbrauch ist der einzige Träger seiner Ersparnis."""
    out = bkw_finanz_beitrag(erzeugung_kwh=0.0, eigenverbrauch_kwh=150.0)

    assert out.erzeugung_kwh == 0.0
    assert out.rest_eigenverbrauch_kwh == 150.0


def test_none_und_leer_sind_tolerant():
    """Fehlende Felder (`None`) wie 0 behandeln — IMD-JSONs sind lückenhaft."""
    out = bkw_finanz_beitrag(erzeugung_kwh=None, eigenverbrauch_kwh=None)

    assert out.erzeugung_kwh == 0.0
    assert out.rest_eigenverbrauch_kwh == 0.0


def test_negative_erzeugung_gilt_nicht_als_erfasst():
    """Ein negativer Zählerwert (Vorzeichen-/Reset-Artefakt) darf die Erfassung
    nicht vortäuschen — sonst verlöre die Anlage still ihren Rest-Term."""
    out = bkw_finanz_beitrag(erzeugung_kwh=-5.0, eigenverbrauch_kwh=150.0)

    assert out.erzeugung_kwh == 0.0
    assert out.rest_eigenverbrauch_kwh == 150.0
