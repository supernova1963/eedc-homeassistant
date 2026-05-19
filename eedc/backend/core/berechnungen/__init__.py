"""Berechnungs-Layer — Single Source of Truth für alle Aggregat-Berechnungen.

Dieser Layer bündelt Berechnungs-Funktionen, die historisch über die
Codebase verteilt waren (Drift-Quelle, siehe BKW-Doppelzählung 2026-05-19,
Rainer-PN). Jede Whitelist, jeder Σ-Helper, jede Invariante für die zentralen
Aggregat-Tabellen (TagesEnergieProfil, TagesZusammenfassung, InvestitionMonatsdaten)
gehört hierher — NICHT in Domain-Module wie daten_checker.py, prognosen.py
oder Routes.

Regel (siehe `docs/ADR-001-BERECHNUNGS-LAYER.md`):
- Jede neue Aggregat-Berechnung MUSS in `core/berechnungen/` definiert werden.
- Jeder bestehende Code, der eine Aggregat-Berechnung dupliziert und aus
  anderem Grund angefasst wird, MUSS bei der Gelegenheit auf den Layer migrieren.
- Der Pytest-Konformitäts-Test `test_berechnungs_layer_konformitaet.py` blockiert
  PRs, die Whitelist-/Prefix-Definitionen außerhalb dieses Layers neu einführen.

Submodule:
- `energie` — kWh-Aggregate aus komponenten_kwh, TagesEnergieProfil
- `invarianten` — Konsistenz-Asserts (Σ Hourly == Daily, Σ pv == komponenten_pv etc.)

Geplant (step-by-step, wenn Konsumenten angefasst werden):
- `counter` — Counter-Aggregate (WP-Starts, Vollzyklen)
- `peaks` — Peak-Werte (peak_pv/bezug/einspeisung)
- `kennzahlen` — Eigenverbrauch, Autarkie, spez. Tagesertrag (Migration aus calculations.py)
"""

from backend.core.berechnungen.energie import (
    PV_KOMPONENTEN_PREFIXE,
    summe_pv_bkw_kwh,
)
from backend.core.berechnungen.invarianten import (
    assert_tep_tz_konsistent,
    pruefe_tep_tz_konsistenz,
)

__all__ = [
    "PV_KOMPONENTEN_PREFIXE",
    "summe_pv_bkw_kwh",
    "assert_tep_tz_konsistent",
    "pruefe_tep_tz_konsistenz",
]
