"""`core/berechnungen/stundenbilanz.py` — der SoT der stündlichen Bilanz.

Die Formel ``verbrauch = PV + Netzbezug − Einspeisung − Batterie-Netto`` stand
bis zum 29.08.2026 **zweimal wortgleich** im Baum (`snapshot/aggregator.py` und
`snapshot/lts_aggregator.py`). Sie hat jetzt eine Stelle; diese Proben halten
fest, dass die Auslagerung **verhaltensneutral** war.

⛔ **Was hier bewusst NICHT geprüft wird:** dass ein fehlender Batterie-Beitrag
die Stunde unbekannt macht. Er zählt weiterhin als 0 — das ist der offene Punkt
N-346 (Melder OB73-gif, #395) und gehört als *Differenz mit fehlendem
Subtrahenden* in die Konzept-Entscheidung zu N-95/N-94, gemeinsam für alle drei
Fundstellen. Eine Unterdrückung allein an dieser Stelle wäre schädlich: Die
Erwartung „hat die Anlage einen Speicher?" kippt am Anschaffungsdatum, also
mitten im Monat, und ``tagesbilanz`` setzt ``verbrauch_erfasst`` schon bei der
ersten Stunde mit Wert — aus einem durchgehend zu niedrigen Monat würde ein
noch niedrigerer, als vollständig ausgewiesener. Das hält
``test_teilunterdrueckung_waere_schlimmer`` fest, damit die Falle nicht erneut
gestellt wird.

Schwesterdateien: ``test_lts_aggregator_konsistenz.py`` (derselbe Aggregator,
Σ-Symmetrie) und ``test_grundlast.py`` (die Kennzahl, die auf diesen Stundenwert
aufsetzt).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.core.berechnungen.stundenbilanz import (
    berechne_batterie_netto_kwh,
    stunden_verbrauch_kwh,
)
from backend.core.berechnungen.tagesbilanz import bilanz_aus_stundenrows


def test_bilanz_mit_entladung():
    """Nachtstunde: Netzbezug 0,01 + Entladung 0,33 → 0,34 kWh Hausverbrauch."""
    assert stunden_verbrauch_kwh(
        pv_kwh=0.0, netzbezug_kwh=0.01, einspeisung_kwh=0.0,
        batterie_netto_kwh=-0.33,
    ) == pytest.approx(0.34)


def test_fehlende_batterie_zaehlt_als_null_das_ist_der_bestand():
    """⚠ Kein Wächter: der fehlende Subtrahend wird zur 0 (offener Punkt N-346).

    Die Probe hält den **Ist-Zustand** fest, nicht seine Richtigkeit — damit eine
    spätere Änderung sichtbar wird, statt sich einzuschleichen.
    """
    assert stunden_verbrauch_kwh(
        pv_kwh=0.0, netzbezug_kwh=0.01, einspeisung_kwh=0.0,
        batterie_netto_kwh=None,
    ) == pytest.approx(0.01)


@pytest.mark.parametrize("fehlt", ["pv_kwh", "netzbezug_kwh", "einspeisung_kwh"])
def test_ohne_eine_der_drei_basisgroessen_keine_zahl(fehlt):
    werte = dict(pv_kwh=1.0, netzbezug_kwh=1.0, einspeisung_kwh=1.0,
                 batterie_netto_kwh=0.0)
    werte[fehlt] = None
    assert stunden_verbrauch_kwh(**werte) is None


def test_negative_bilanz_bleibt_auf_null_geklemmt():
    assert stunden_verbrauch_kwh(
        pv_kwh=1.0, netzbezug_kwh=0.0, einspeisung_kwh=2.0,
        batterie_netto_kwh=0.0,
    ) == 0.0


def test_netto_ist_ladung_minus_entladung():
    assert berechne_batterie_netto_kwh(ladung_kwh=0.5, entladung_kwh=0.1) == pytest.approx(0.4)
    assert berechne_batterie_netto_kwh(ladung_kwh=None, entladung_kwh=0.4) == pytest.approx(-0.4)
    assert berechne_batterie_netto_kwh(ladung_kwh=None, entladung_kwh=None) is None


def test_teilunterdrueckung_waere_schlimmer():
    """⛔ Warum die Unterdrückung NICHT allein an dieser Stelle gebaut wird.

    ``tagesbilanz`` setzt seinen Träger ``verbrauch_erfasst`` bereits bei der
    ersten Stunde mit Wert. Ein teilweise unterdrückter Zeitraum liefert deshalb
    eine **zu kleine Summe, die sich als vollständig ausgibt** — schlechter als
    eine durchgehend zu niedrige. Gemessen, nicht behauptet.
    """
    def _row(verbrauch):
        return SimpleNamespace(
            pv_kw=0.0, verbrauch_kw=verbrauch, einspeisung_kw=0.0,
            netzbezug_kw=1.0, batterie_kw=None, waermepumpe_kw=None,
        )

    bilanz = bilanz_aus_stundenrows([_row(1.0)] * 12 + [_row(None)] * 12)
    assert bilanz.gesamtverbrauch_kwh == pytest.approx(12.0)   # wahr wären 24
    assert bilanz.verbrauch_erfasst is True                    # und niemand sagt es
