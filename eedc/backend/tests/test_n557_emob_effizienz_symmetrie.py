"""N-557: `core/berechnungen/emob.py::eauto_effizienz_zeitraum` == `lib/emobEffizienz.ts`.

*Cockpit → Jahr* baut das Jahr im Client aus zwölf Monatsantworten und hat keine
Backend-Zahl für die Jahres-kWh/100 km. Die Regel (Konzept Heimladung/Fahrverbrauch,
Regel 10: Σ Monatswerte ÷ Σ km, „gemessen" nur, wenn jeder Monat mit km gemessen ist)
braucht dort eine zweite **Heimat**; damit keine zweite **Definition** daraus wird,
stehen die Fixtures wortgleich in `frontend/src/lib/emobEffizienz.test.ts`.
Gleiches Muster wie `test_speicher_wirkungsgrad_symmetrie.py`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.core.berechnungen import (
    EffizienzWert,
    eauto_effizienz_100km,
    eauto_effizienz_zeitraum,
)

#: ([[basis_kwh, km, quelle], …], erwartet_wert, erwartete_quelle) — wortgleich im TS-Test.
FIXTURES = [
    ([[300.0, 1500.0, "ladung"], [270.0, 1500.0, "gemessen"]], 19.0, "ladung"),
    ([[270.0, 1500.0, "gemessen"], [180.0, 1000.0, "gemessen"]], 18.0, "gemessen"),
    ([[270.0, 1500.0, "gemessen"], [None, 500.0, "keine"]], 18.0, "ladung"),
    ([[270.0, 1500.0, "gemessen"], [None, 0.0, "keine"]], 18.0, "gemessen"),
    ([[None, 0.0, "keine"]], None, "keine"),
    ([], None, "keine"),
]

_FRONTEND = Path(__file__).resolve().parents[2] / "frontend/src/lib"
FRONTEND_TEST = _FRONTEND / "emobEffizienz.test.ts"


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


def test_die_fixtures_stehen_wortgleich_im_client_test():
    """Der Beleg, dass „gespiegelt" nicht nur behauptet ist."""
    assert FRONTEND_TEST.exists(), "Spiegel-Test fehlt"
    ts = FRONTEND_TEST.read_text(encoding="utf-8")
    block = re.search(r"const FIXTURES[^=]*=\s*(\[[\s\S]*?\n\])", ts)
    assert block, "FIXTURES-Block im Client-Test nicht gefunden"
    roh = re.sub(r"//[^\n]*", "", block.group(1))
    roh = roh.replace("undefined", "null").replace("'", '"')
    roh = re.sub(r",(\s*[\]\}])", r"\1", roh)
    ts_fixtures = [(m, w, q) for m, w, q in json.loads(roh)]
    assert ts_fixtures == [(m, w, q) for m, w, q in FIXTURES], (
        "Die Fixtures beider Seiten sind auseinandergelaufen."
    )
