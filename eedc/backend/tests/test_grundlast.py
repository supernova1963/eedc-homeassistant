"""Tests für `core/berechnungen/grundlast.py` (R12-1, Nacht-Sockel) — die FORMEL.

Hier steht ausschließlich der Layer: Median, Hochrechnung, Anteil, die beiden
Nicht-Fälle. Wer die Größe **einsammelt**, wird woanders geprüft.

Schwesterdatei: `test_grundlast_spalte_je_nacht.py` — dort das Sourcing des
Tages-Pfads (Nachtstunden-Filter, Spalte der Tagestabelle). Die Trennung ist
Absicht: dieselbe Formel bedient inzwischen vier Zeiträume (Live, Tag, Monat,
Jahr), und ein Fehler sitzt praktisch immer im Filter, nicht im Median.
"""

from __future__ import annotations

from backend.core.berechnungen import berechne_grundlast


def test_median_ungerade():
    # Median von [0.3, 0.4, 0.5] = 0.4
    k = berechne_grundlast(
        nacht_verbrauch_kw=[0.5, 0.3, 0.4], gesamtverbrauch_kwh=None, tage=30,
    )
    assert k.grundlast_kw == 0.4
    # 0.4 kW × 24 h × 30 Tage = 288 kWh
    assert k.grundlast_kwh == 288.0
    assert k.grundlast_anteil_prozent is None  # ohne Gesamtverbrauch kein Anteil


def test_median_gerade_und_anteil():
    # Median von [0.2, 0.4] = 0.3 → 0.3 × 24 × 10 = 72 kWh
    k = berechne_grundlast(
        nacht_verbrauch_kw=[0.4, 0.2], gesamtverbrauch_kwh=360.0, tage=10,
    )
    assert k.grundlast_kw == 0.3
    assert k.grundlast_kwh == 72.0
    assert k.grundlast_anteil_prozent == 20.0  # 72 / 360 × 100


def test_median_robust_gegen_ausreisser():
    # Eine Ausreißer-Nacht (5.0) verschiebt den Median NICHT (≠ Mittelwert).
    k = berechne_grundlast(
        nacht_verbrauch_kw=[0.3, 0.3, 0.3, 5.0], gesamtverbrauch_kwh=None, tage=1,
    )
    assert k.grundlast_kw == 0.3


def test_leere_liste_keine_grundlast():
    # Keine Stundendaten → alles None (Aufrufer fällt auf PVGIS zurück).
    k = berechne_grundlast(nacht_verbrauch_kw=[], gesamtverbrauch_kwh=400.0, tage=30)
    assert k.grundlast_kw is None
    assert k.grundlast_kwh is None
    assert k.grundlast_anteil_prozent is None


def test_tage_null_keine_grundlast():
    k = berechne_grundlast(nacht_verbrauch_kw=[0.4], gesamtverbrauch_kwh=100.0, tage=0)
    assert k.grundlast_kw is None
