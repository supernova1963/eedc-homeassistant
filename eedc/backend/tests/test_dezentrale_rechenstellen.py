"""Wächter «Rechenstellen»: keine neue Formel außerhalb des Berechnungs-Layers (Päckchen Z3, 9.11.2026).

Schwesterdateien: `test_kognitive_komplexitaet.py` (dasselbe Baseline-Muster — eine Liste, die nur schrumpft, ein
verwaister Eintrag macht rot) · `test_berechnungs_layer_konformitaet.py` (Layer-Wächter je Größe) · Werkzeug
`werkzeug_rechenstellen.py` (Erhebung, Schlüssel, Baseline-Befehl).

**Was gilt (ADR-001 «eine Formel, ein Ort»; Erhebung und Einwertung 9.11.2026):** in Routen (`api/`) und Services
(`services/`) entsteht kein neuer Rechenausdruck der Gestalten Quote zweier Mengen (`E/E`), Differenz zweier Mengen
(`E-E`), Menge × Preis (`E*G`), Menge × Zahl-Literal (`E*L`), Preis ÷ Menge (`G/E`) und Differenz zweier Geldbeträge
(`G-G`) — außer als Einheitenumrechnung (× 100, ÷ 1000 …), Zähler (± 1) oder in einer Funktion, die den Layer
(`core/berechnungen/`) schon ruft. Der Bestand steht in `rechenstellen_baseline.txt` (Stand nach Päckchen Z1/Z2,
darin die bewusst gelassenen Stellen: Monats-Fakten, Verteilungen, Checker-/Import-Differenzen, Demo-Faktoren) und
**darf nur schrumpfen**: eine Stelle, die in den Layer zieht, verschwindet aus der Erhebung, und der Test bleibt rot,
bis sie aus der Baseline gestrichen ist — so sinkt die Zahl sichtbar im Commit.

**Wenn dieser Test rot wird:** Formel in den Layer (`core/berechnungen/`) oder — bewusst, mit Grund im Commit —
Baseline neu schreiben:

    cd eedc && backend/venv/bin/python -m backend.tests.werkzeug_rechenstellen --baseline
"""
from __future__ import annotations

from collections import Counter

import pytest

from backend.tests.werkzeug_rechenstellen import BASELINE, baseline_lesen, gefuehrte

BEFEHL = "python -m backend.tests.werkzeug_rechenstellen --baseline"


@pytest.fixture(scope="module")
def stellen():
    return gefuehrte()


def test_keine_neue_rechenstelle_ausserhalb_des_layers(stellen):
    baseline = baseline_lesen()
    aktuell = Counter(t.schluessel for t in stellen)
    neu_schluessel = aktuell - baseline
    neu = [t for t in stellen if neu_schluessel[t.schluessel] > 0]
    assert not neu, (
        f"{sum(neu_schluessel.values())} neue Rechenstelle(n) außerhalb des Layers:\n  "
        + "\n  ".join(f"{t.datei}:{t.zeile}  {t.gestalt}  {t.operanden[0]} {t.operator} {t.operanden[1]}" for t in neu)
        + f"\nFormel in den Layer (`core/berechnungen/`) oder bewusst in die Baseline: `{BEFEHL}`"
    )


def test_baseline_ist_aktuell(stellen):
    """Eine Stelle, die es nicht mehr gibt (in den Layer gezogen, gelöscht), steht nicht mehr in der Baseline."""
    verwaist = baseline_lesen() - Counter(t.schluessel for t in stellen)
    assert not verwaist, (
        f"{sum(verwaist.values())} Baseline-Eintrag/-Einträge ohne Rechenstelle — die Baseline schrumpft im Commit "
        f"(`{BEFEHL}`):\n  " + "\n  ".join(sorted(verwaist))
    )


def test_baseline_traegt_nur_gefuehrte_gestalten():
    """Die Baseline ist keine Ablage für alles — jede Zeile nennt eine der geführten Gestalten."""
    from backend.tests.werkzeug_rechenstellen import GESTALTEN

    fremd = [z for z in BASELINE.read_text(encoding="utf-8").splitlines()
             if z.strip() and not z.startswith("#") and z.rsplit("\t", 1)[-1] not in GESTALTEN]
    assert not fremd, "Baseline-Zeilen mit fremder Gestalt:\n  " + "\n  ".join(fremd)
