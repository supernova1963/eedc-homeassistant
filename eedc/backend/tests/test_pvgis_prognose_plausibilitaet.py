"""
Unit-Tests für den Stale-/Oversize-Wächter der PVGIS-Prognose
(_pruefe_prognose_plausibilitaet).

Hintergrund (Sabrina #638): Eine PVGIS-Prognose, die für ~357 kWp gerechnet
und nach kWp-Korrektur auf 2,4 kWp nie neu abgerufen wurde, lieferte eine
SOLL-Jahresprognose von 357 MWh. Der Wächter erkennt die grobe kWp-Abweichung
und gibt einen Diagnose-Hinweis zurück — bewusst ohne die Werte still zu cappen
oder zu skalieren.
"""

from __future__ import annotations

from types import SimpleNamespace

from backend.api.routes.cockpit.pv_strings import _pruefe_prognose_plausibilitaet


def _prognose(gesamt_leistung_kwp=None, jahresertrag_kwh=0.0, spez=0.0):
    return SimpleNamespace(
        gesamt_leistung_kwp=gesamt_leistung_kwp,
        jahresertrag_kwh=jahresertrag_kwh,
        spezifischer_ertrag_kwh_kwp=spez,
    )


def test_stale_oversize_prognose_loest_hinweis_aus():
    """Prognose für 357 kWp, Anlage hat 2,4 kWp → Hinweis."""
    prognose = _prognose(gesamt_leistung_kwp=357.0)
    msg = _pruefe_prognose_plausibilitaet(prognose, gesamt_kwp=2.4)
    assert msg is not None
    assert "357" in msg
    assert "2.4" in msg


def test_passende_kwp_kein_hinweis():
    """Prognose und Anlage gleich groß → kein Hinweis."""
    prognose = _prognose(gesamt_leistung_kwp=12.3)
    assert _pruefe_prognose_plausibilitaet(prognose, gesamt_kwp=12.32) is None


def test_kleine_abweichung_innerhalb_toleranz():
    """±20 % gelten noch als plausibel (kein Nörgeln bei Rundung)."""
    prognose = _prognose(gesamt_leistung_kwp=10.0)
    assert _pruefe_prognose_plausibilitaet(prognose, gesamt_kwp=11.0) is None
    assert _pruefe_prognose_plausibilitaet(prognose, gesamt_kwp=9.0) is None


def test_zu_kleine_gespeicherte_prognose_loest_hinweis_aus():
    """Modul später vergrößert: Prognose 5 kWp, Anlage 12 kWp → Hinweis."""
    prognose = _prognose(gesamt_leistung_kwp=5.0)
    assert _pruefe_prognose_plausibilitaet(prognose, gesamt_kwp=12.0) is not None


def test_fallback_aus_jahresertrag_und_spez_ertrag():
    """Ältere Prognose ohne gesamt_leistung_kwp: kWp aus Ertrag/spez. Ertrag."""
    # 357000 kWh / 1000 kWh/kWp = 357 kWp implizit
    prognose = _prognose(gesamt_leistung_kwp=None, jahresertrag_kwh=357000.0, spez=1000.0)
    assert _pruefe_prognose_plausibilitaet(prognose, gesamt_kwp=2.4) is not None


def test_keine_prognose_kein_hinweis():
    assert _pruefe_prognose_plausibilitaet(None, gesamt_kwp=5.0) is None


def test_gesamt_kwp_null_kein_crash():
    prognose = _prognose(gesamt_leistung_kwp=10.0)
    assert _pruefe_prognose_plausibilitaet(prognose, gesamt_kwp=0.0) is None


def test_unbestimmbare_prognose_kwp_kein_hinweis():
    """Weder gespeicherte kWp noch ableitbar → kein Fehlalarm."""
    prognose = _prognose(gesamt_leistung_kwp=None, jahresertrag_kwh=0.0, spez=0.0)
    assert _pruefe_prognose_plausibilitaet(prognose, gesamt_kwp=2.4) is None
