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
- `counter` — Counter-Aggregate (WP-Starts/Betriebsstunden): Stunden-Σ aus
  Tages-Boundary-Diff ableiten + Pflicht-Invariante (Variante 2-light)
- `invarianten` — Konsistenz-Asserts (Σ Hourly == Daily, Σ pv == komponenten_pv etc.)
- `speicher` — Speicher-Effizienz (gleitend, carry-over-immun)
- `spez_ertrag` — spezifischer Ertrag annualisiert (saisonal gewichtet,
  per-Monat-aktives kWp) — Cockpit-Kachel == HA-Export-Sensor
- `prognose_korrektur` — Kaskaden-Faktoren auf Prognose-Stundenprofil,
  Tageswert = Σ Export-Slots (Invariante HA-Export #150 / Prognosen-Vergleich)

Geplant (step-by-step, wenn Konsumenten angefasst werden):
- `peaks` — Peak-Werte (peak_pv/bezug/einspeisung)
- `kennzahlen` — Eigenverbrauch, Autarkie, spez. Tagesertrag (Migration aus calculations.py)
"""

from backend.core.berechnungen.co2_amortisation import (
    QUELLE_DEFAULT,
    QUELLE_FEHLT,
    QUELLE_KEIN_DEFAULT,
    QUELLE_OVERRIDE,
    GraueLastBericht,
    GraueLastPosten,
    graue_last_einzeln,
    summe_graue_last,
)
from backend.core.berechnungen.counter import (
    CounterKonsistenzBericht,
    assert_counter_konsistent,
    pruefe_counter_konsistent,
    verteile_counter_auf_stunden,
)
from backend.core.berechnungen.einspeise_erloes import (
    EinspeiseErloes,
    einspeise_erloes_euro,
)
from backend.core.berechnungen.finanz_aggregat import (
    FinanzAggregat,
    FinanzMonatsZeile,
    berechne_finanz_aggregat,
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
from backend.core.berechnungen.pv_verteilung import (
    QUELLE_FEHLT as PV_QUELLE_FEHLT,
    QUELLE_GEMESSEN as PV_QUELLE_GEMESSEN,
    QUELLE_VERTEILT as PV_QUELLE_VERTEILT,
    STATUS_FEHLT as PV_STATUS_FEHLT,
    STATUS_OK as PV_STATUS_OK,
    STATUS_TEIL_LUECKE as PV_STATUS_TEIL_LUECKE,
    STATUS_VERTEILT as PV_STATUS_VERTEILT,
    PvModul,
    PvModulWert,
    gesamt_pv_kwh,
    klassifiziere_pv_monat,
    resolve_pv_je_modul,
    verteile_basis_kwh_nach_kwp,
)
from backend.core.berechnungen.preis_rang import (
    GUENSTIG_SCHWELLE_FAKTOR,
    GUENSTIG_TOP_N,
    PEAK_AUSSCHLUSS_N,
    RANG_TEUER,
    PreisRangErgebnis,
    berechne_preis_rang,
    guenstig_schwelle,
)
from backend.core.berechnungen.prognose_korrektur import (
    KorrigiertesTagesprofil,
    korrigiere_tagesprofil,
)
from backend.core.berechnungen.spez_ertrag import (
    MONATSGEWICHTE_52N,
    PV_ERZEUGER_TYPEN,
    berechne_spez_ertrag_annualisiert,
    kwp_aktiv_im_monat,
    monatsgewichte_aus_pvgis,
)
from backend.core.berechnungen.speicher import (
    EFFIZIENZ_FENSTER_MONATE,
    MonatsEffizienz,
    gleitende_effizienz,
    speicher_effizienz_prozent,
)
from backend.core.berechnungen.speicher_simulation import (
    SpeicherSimErgebnis,
    StundenBilanz,
    simuliere_speicher_tag,
)
from backend.core.berechnungen.verbrauch import (
    VerbrauchsKennzahlen,
    berechne_verbrauchs_kennzahlen,
)

__all__ = [
    "QUELLE_OVERRIDE",
    "QUELLE_DEFAULT",
    "QUELLE_FEHLT",
    "QUELLE_KEIN_DEFAULT",
    "GraueLastBericht",
    "GraueLastPosten",
    "graue_last_einzeln",
    "summe_graue_last",
    "CounterKonsistenzBericht",
    "assert_counter_konsistent",
    "pruefe_counter_konsistent",
    "verteile_counter_auf_stunden",
    "EinspeiseErloes",
    "einspeise_erloes_euro",
    "FinanzAggregat",
    "FinanzMonatsZeile",
    "berechne_finanz_aggregat",
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
    "GUENSTIG_SCHWELLE_FAKTOR",
    "GUENSTIG_TOP_N",
    "PEAK_AUSSCHLUSS_N",
    "RANG_TEUER",
    "PreisRangErgebnis",
    "berechne_preis_rang",
    "guenstig_schwelle",
    "KorrigiertesTagesprofil",
    "korrigiere_tagesprofil",
    "MONATSGEWICHTE_52N",
    "PV_ERZEUGER_TYPEN",
    "berechne_spez_ertrag_annualisiert",
    "kwp_aktiv_im_monat",
    "monatsgewichte_aus_pvgis",
    "SpeicherSimErgebnis",
    "StundenBilanz",
    "simuliere_speicher_tag",
    "EFFIZIENZ_FENSTER_MONATE",
    "MonatsEffizienz",
    "gleitende_effizienz",
    "speicher_effizienz_prozent",
    "VerbrauchsKennzahlen",
    "berechne_verbrauchs_kennzahlen",
    "PV_QUELLE_GEMESSEN",
    "PV_QUELLE_VERTEILT",
    "PV_QUELLE_FEHLT",
    "PV_STATUS_OK",
    "PV_STATUS_VERTEILT",
    "PV_STATUS_TEIL_LUECKE",
    "PV_STATUS_FEHLT",
    "PvModul",
    "PvModulWert",
    "verteile_basis_kwh_nach_kwp",
    "resolve_pv_je_modul",
    "gesamt_pv_kwh",
    "klassifiziere_pv_monat",
]
