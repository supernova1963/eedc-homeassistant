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
- `einspeise_erloes` — §51-bereinigte Einspeise-Erlös-Berechnung
- `invarianten` — Konsistenz-Asserts (Σ Hourly == Daily, Σ pv == komponenten_pv etc.)
- `speicher` — Speicher-Effizienz (gleitend, carry-over-immun)

Geplant (step-by-step, wenn Konsumenten angefasst werden):
- `counter` — Counter-Aggregate (WP-Starts, Vollzyklen)
- `peaks` — Peak-Werte (peak_pv/bezug/einspeisung)
- `kennzahlen` — Eigenverbrauch, Autarkie, spez. Tagesertrag (Migration aus calculations.py)
"""

from backend.core.berechnungen.einspeise_erloes import (
    EinspeiseErloes,
    einspeise_erloes_euro,
)
from backend.core.berechnungen.emob import (
    QUELLE_GEMESSEN,
    QUELLE_KEINE,
    QUELLE_LADUNG,
    EffizienzWert,
    eauto_effizienz_100km,
)
from backend.core.berechnungen.energie import (
    BATTERIE_KOMPONENTEN_PREFIXE,
    PV_KOMPONENTEN_PREFIXE,
    WAERMEPUMPE_KOMPONENTEN_PREFIXE,
    WALLBOX_KOMPONENTEN_PREFIXE,
    summe_batterie_netto_kwh,
    summe_pv_bkw_kwh,
    summe_waermepumpe_kwh,
    summe_wallbox_eauto_kwh,
    wert_basis_kwh,
)
from backend.core.berechnungen.invarianten import (
    assert_speicher_durchsatz_konsistent,
    assert_speicher_ladung_konsistent,
    assert_speicher_netzladung_kumulativ,
    assert_tep_komponenten_intern_konsistent,
    assert_tep_tz_komponenten_konsistent,
    assert_tep_tz_konsistent,
    pruefe_speicher_durchsatz_konsistenz,
    pruefe_speicher_ladung_konsistenz,
    pruefe_speicher_netzladung_kumulativ,
    pruefe_tep_komponenten_intern_konsistenz,
    pruefe_tep_tz_komponenten_konsistenz,
    pruefe_tep_tz_konsistenz,
)
from backend.core.berechnungen.speicher import (
    EFFIZIENZ_FENSTER_MONATE,
    MonatsEffizienz,
    gleitende_effizienz,
    speicher_effizienz_prozent,
)
from backend.core.berechnungen.verbrauch import (
    VerbrauchsKennzahlen,
    berechne_verbrauchs_kennzahlen,
)

__all__ = [
    "EinspeiseErloes",
    "einspeise_erloes_euro",
    "QUELLE_GEMESSEN",
    "QUELLE_LADUNG",
    "QUELLE_KEINE",
    "EffizienzWert",
    "eauto_effizienz_100km",
    "PV_KOMPONENTEN_PREFIXE",
    "WAERMEPUMPE_KOMPONENTEN_PREFIXE",
    "WALLBOX_KOMPONENTEN_PREFIXE",
    "BATTERIE_KOMPONENTEN_PREFIXE",
    "summe_pv_bkw_kwh",
    "summe_waermepumpe_kwh",
    "summe_wallbox_eauto_kwh",
    "summe_batterie_netto_kwh",
    "wert_basis_kwh",
    "assert_tep_tz_konsistent",
    "pruefe_tep_tz_konsistenz",
    "assert_tep_tz_komponenten_konsistent",
    "pruefe_tep_tz_komponenten_konsistenz",
    "assert_tep_komponenten_intern_konsistent",
    "pruefe_tep_komponenten_intern_konsistenz",
    "assert_speicher_ladung_konsistent",
    "pruefe_speicher_ladung_konsistenz",
    "assert_speicher_netzladung_kumulativ",
    "pruefe_speicher_netzladung_kumulativ",
    "assert_speicher_durchsatz_konsistent",
    "pruefe_speicher_durchsatz_konsistenz",
    "EFFIZIENZ_FENSTER_MONATE",
    "MonatsEffizienz",
    "gleitende_effizienz",
    "speicher_effizienz_prozent",
    "VerbrauchsKennzahlen",
    "berechne_verbrauchs_kennzahlen",
]
