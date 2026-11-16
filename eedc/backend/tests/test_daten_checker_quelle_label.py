"""Herkunft im Daten-Checker als Anwender-Wort (Päckchen «Kleineres» 16.11.2026, N3).

`kategorien._quelle_label` ließ die Herkünfte, die eedc selbst schreibt (`auto:*`, `legacy:unknown`), roh durch; der Befund
`datenquelle_aggregate_aeltere_quelle` setzte die Rohquelle sogar ohne Label ein («… aus 'auto:monatsabschluss'
geschrieben»). Die Wörter folgen der Oberfläche («HA-Spiegel» für die Tageszeile aus dem gespiegelten HA-Zähler).

Schwesterdateien: test_daten_checker_ohne_tageswerte.py (Befund «Aggregate aus älterer Quelle»), test_daten_checker_ziele.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.core.source_priority import SOURCE_LABELS
from backend.services.daten_checker.kategorien import _quelle_label


@pytest.mark.parametrize("roh, wort", [
    ("auto:monatsabschluss", "Monatsabschluss"),
    ("auto:kanal_tag", "HA-Spiegel"),
    ("auto:preserve_restore", "Wiederherstellung"),
    ("auto:demo_data", "Demo-Daten"),
    ("legacy:unknown", "Altbestand"),
    ("manual:form", "manuell"),
    ("external:ha_statistics:hourly", "HA-Statistik"),
    ("repair", "Reparatur"),
    ("", ""),
])
def test_quelle_label_anwender_wort(roh, wort):
    assert _quelle_label(roh) == wort


def test_jede_auto_herkunft_des_vokabulars_hat_ein_wort():
    """Kommt eine neue `auto:`-Herkunft ins Vokabular, braucht sie hier ein Wort — sonst stünde sie roh im Befund."""
    roh = sorted(s for s in SOURCE_LABELS if s.startswith(("auto:", "legacy:")) and _quelle_label(s) == s)
    assert roh == [], roh


def test_aeltere_quelle_setzt_das_wort_ein():
    """Der Befund «Aggregate aus älterer Quelle» nennt die Herkunft über `_quelle_label`, nicht roh."""
    pfad = Path(__file__).resolve().parents[1] / "services" / "daten_checker" / "datenquelle" / "quellen.py"
    quelltext = pfad.read_text(encoding="utf-8")
    baum = ast.parse(quelltext)
    formate = [ast.unparse(n) for n in ast.walk(baum) if isinstance(n, ast.JoinedStr) and "geschrieben" in ast.unparse(n)]
    assert formate and all("_quelle_label(letzte_source" in f for f in formate), formate
