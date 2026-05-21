"""Akzeptanztest: aggregate_day rettet die Day-Ahead-Prognose-Felder.

Bug (2026-05-21, bei der Lernfaktor-Untersuchung gefunden): `aggregate_day`
macht ein Delete-and-Recreate der TagesZusammenfassung-Zeile und rettet dabei
nur ausgewählte Prognose-Felder. `pv_prognose_stundenprofil` und
`solcast_prognose_stundenprofil` fehlten in der Rettungsliste — dadurch wurde
der vom Wetter-Endpoint (`_speichere_prognose`) geschriebene Day-Ahead-
Snapshot bei jeder nächtlichen IST-Aggregation gelöscht. Folge: der
Korrekturprofil-Bin-Aggregator (`_lade_tagesprognose`, liest `datum < heute`)
fand nie ein Stundenprofil — die Heatmap blieb dauerhaft bei 0 Bins
(Anlage 1: 26 Tage, 0 Bins, auch bei 730-Tage-Lookback).

Fix: `_PROGNOSE_FELDER_RETTEN` enthält jetzt alle 7 Prognose-Felder, die
`_speichere_prognose` schreibt.
"""

from __future__ import annotations

from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.energie_profil.aggregator import _PROGNOSE_FELDER_RETTEN


def test_stundenprofile_in_rettungsliste():
    """Die beiden Day-Ahead-Stundenprofile müssen gerettet werden —
    ihr Fehlen war der Bug."""
    assert "pv_prognose_stundenprofil" in _PROGNOSE_FELDER_RETTEN
    assert "solcast_prognose_stundenprofil" in _PROGNOSE_FELDER_RETTEN


def test_rettungsliste_deckt_alle_prognose_felder():
    """Die Rettungsliste muss alle Felder spiegeln, die der Wetter-Endpoint
    (`_speichere_prognose`) in TagesZusammenfassung schreibt — sonst gehen
    sie beim Delete-and-Recreate still verloren."""
    vom_wetter_endpoint_geschrieben = {
        "pv_prognose_kwh",
        "sfml_prognose_kwh",
        "solcast_prognose_kwh",
        "solcast_p10_kwh",
        "solcast_p90_kwh",
        "pv_prognose_stundenprofil",
        "solcast_prognose_stundenprofil",
    }
    fehlend = vom_wetter_endpoint_geschrieben - set(_PROGNOSE_FELDER_RETTEN)
    assert not fehlend, (
        f"Nicht in der Rettungsliste — geht beim Reaggregieren verloren: {fehlend}"
    )


def test_rettungsfelder_sind_echte_spalten():
    """Jedes Rettungs-Feld muss eine echte TagesZusammenfassung-Spalte sein —
    fängt Tippfehler und spätere Spalten-Umbenennungen ab."""
    spalten = set(TagesZusammenfassung.__table__.columns.keys())
    unbekannt = [f for f in _PROGNOSE_FELDER_RETTEN if f not in spalten]
    assert not unbekannt, f"Keine TagesZusammenfassung-Spalten: {unbekannt}"
