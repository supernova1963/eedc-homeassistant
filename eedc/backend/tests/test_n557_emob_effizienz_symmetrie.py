"""N-557: `core/berechnungen/emob.py::eauto_effizienz_zeitraum` — die Zeitraum-Regel der E-Auto-Effizienz.

Die Regel (Konzept Heimladung/Fahrverbrauch, Regel 10): Σ Monatswerte ÷ Σ km, „gemessen" nur, wenn jeder Monat
mit km gemessen ist.

⚑ **Seit 03.10.2026 nur noch die Backend-Seite.** Bis dahin baute *Cockpit → Jahr* das Jahr im Client aus zwölf
Monatsantworten (`v4/JahrAggregat.tsx`) und brauchte die Regel ein zweites Mal (`lib/emobEffizienz.ts`); diese
Datei hielt die Fixtures beider Seiten wortgleich. Mit dem Paket „Ergebnisgrößen Monat/Jahr in den Layer" faltet die
Jahresroute im Backend (`core/berechnungen/ergebnis.py::falte_zeitraum` ruft `eauto_effizienz_zeitraum` selbst) —
der Client-Spiegel war ohne Laufzeit-Konsumenten und ist entfernt, der Wortgleichheits-Test mit ihm. Die
Jahres-Seite der Regel prüfen jetzt die portierten Proben in `test_ergebnis_jahr_portiert.py`.
"""

from __future__ import annotations

import pytest

from backend.core.berechnungen import (
    EffizienzWert,
    eauto_effizienz_100km,
    eauto_effizienz_zeitraum,
)

#: ([[basis_kwh, km, quelle], …], erwartet_wert, erwartete_quelle).
FIXTURES = [
    ([[300.0, 1500.0, "ladung"], [270.0, 1500.0, "gemessen"]], 19.0, "ladung"),
    ([[270.0, 1500.0, "gemessen"], [180.0, 1000.0, "gemessen"]], 18.0, "gemessen"),
    ([[270.0, 1500.0, "gemessen"], [None, 500.0, "keine"]], 18.0, "ladung"),
    ([[270.0, 1500.0, "gemessen"], [None, 0.0, "keine"]], 18.0, "gemessen"),
    ([[None, 0.0, "keine"]], None, "keine"),
    ([], None, "keine"),
]


def _monat(basis, km, quelle) -> EffizienzWert:
    wert = basis / km * 100 if basis is not None and km > 0 else None
    return EffizienzWert(wert, quelle, basis, km)


@pytest.mark.parametrize("monate,wert,quelle", FIXTURES)
def test_backend_haelt_die_fixtures(monate, wert, quelle):
    e = eauto_effizienz_zeitraum(_monat(*m) for m in monate)
    assert e.quelle == quelle
    if wert is None:
        assert e.wert is None
    else:
        assert e.wert == pytest.approx(wert)


def test_die_monatsregel_liefert_die_basis_die_der_zeitraum_summiert():
    """Der Monat trägt seine MENGE mit: gemessen ⇒ Fahrverbrauch, sonst Heim + Extern.

    Ohne `basis_kwh`/`km` am Monatswert könnte der Zeitraum nur Quoten mitteln —
    oder die Ladung neu teilen, genau der Fehler aus N-557.
    """
    gemessen = eauto_effizienz_100km(270.0, 999.0, 1500.0)
    assert (gemessen.basis_kwh, gemessen.km, gemessen.quelle) == (270.0, 1500.0, "gemessen")
    naeherung = eauto_effizienz_100km(0.0, 300.0, 1500.0)
    assert (naeherung.basis_kwh, naeherung.km, naeherung.quelle) == (300.0, 1500.0, "ladung")
    ohne = eauto_effizienz_100km(0.0, 0.0, 500.0)
    assert (ohne.basis_kwh, ohne.km, ohne.quelle) == (None, 500.0, "keine")
