"""
Daten-Checker: `_check_emob_doppelzaehlung_tage` (N-186) — gespeicherte Tage,
an denen Wallbox UND E-Auto dieselbe Ladung tragen, bekommen den
Bereichs-Reparatur-Knopf; Krümel und Einseitiges bleiben still.

Trigger: Prüfbericht Daten-Checker 2026-08-22 (B8, Test-Lücke) — der Check war
seit seinem Bau ungetestet, D5 schließt die Lücke. Mock-DB-Muster nach
`test_batterie_vorzeichen_historie_check.py`.

Self-contained:

    eedc/backend/venv/bin/python -m pytest eedc/backend/tests/test_daten_checker_emob_doppelzaehlung_tage.py
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.services.daten_checker import (
    CheckKategorie,
    DatenChecker,
)

_KAT = CheckKategorie.EMOB_DOPPELZAEHLUNG_TAGE.value


def _tz(datum: date, **komponenten):
    return SimpleNamespace(anlage_id=1, datum=datum, komponenten_kwh=komponenten)


def _anlage(mit_eauto: bool = True, mit_wallbox: bool = True):
    invs = []
    if mit_wallbox:
        invs.append(SimpleNamespace(id=3, typ="wallbox", bezeichnung="WB"))
    if mit_eauto:
        invs.append(SimpleNamespace(id=4, typ="e-auto", bezeichnung="EA"))
    return SimpleNamespace(id=1, investitionen=invs)


async def _run(tz_rows, anlage):
    db = MagicMock()

    async def _execute(stmt):
        result = MagicMock()
        scalars = MagicMock()
        scalars.all = MagicMock(return_value=tz_rows)
        result.scalars = MagicMock(return_value=scalars)
        return result

    db.execute = _execute
    return await DatenChecker(db)._check_emob_doppelzaehlung_tage(anlage)


@pytest.mark.asyncio
async def test_doppelt_getragene_tage_warnen_mit_bereichs_knopf():
    """Beide Seiten ≥1 kWh an zwei Tagen → WARNING + reaggregate_range."""
    d1, d2 = date.today() - timedelta(days=5), date.today() - timedelta(days=3)
    rows = [
        _tz(d1, wallbox_3=-12.0, eauto_4=-12.0),  # Butterfly: Senken negativ
        _tz(d2, wallbox_3=-8.0, eauto_4=-6.5),
    ]
    result = await _run(rows, _anlage())
    warn = [e for e in result if e.kategorie == _KAT and e.schwere == "warning"]
    assert warn, f"WARNING erwartet, bekam: {[(e.kategorie, e.schwere) for e in result]}"
    assert warn[0].action_kind == "reaggregate_range"
    assert warn[0].action_params["von"] == d1.isoformat()
    assert warn[0].action_params["bis"] == d2.isoformat()
    assert "2 Tag" in warn[0].meldung


@pytest.mark.asyncio
async def test_kruemel_unter_schwelle_bleiben_still():
    """Standby-Krümel (< 1 kWh auf einer Seite) sind kein Doppelzähl-Befund."""
    rows = [_tz(date.today() - timedelta(days=2), wallbox_3=-9.0, eauto_4=-0.4)]
    result = await _run(rows, _anlage())
    assert [e.schwere for e in result if e.kategorie == _KAT] == ["ok"]


@pytest.mark.asyncio
async def test_nur_eine_seite_traegt_ist_ok():
    """F-14-Sollzustand: nur die Wallbox trägt die Ladung → OK-Zeile."""
    rows = [_tz(date.today() - timedelta(days=2), wallbox_3=-11.0)]
    result = await _run(rows, _anlage())
    assert [e.schwere for e in result if e.kategorie == _KAT] == ["ok"]


@pytest.mark.asyncio
async def test_ohne_paar_keine_kategorie():
    """Ohne E-Auto/Wallbox-Paar erscheint die Kategorie gar nicht (leer)."""
    rows = [_tz(date.today() - timedelta(days=2), wallbox_3=-11.0)]
    result = await _run(rows, _anlage(mit_eauto=False))
    assert result == []


@pytest.mark.asyncio
async def test_span_ueber_max_begrenzt_bereich_und_nennt_rest():
    """Befunde über > REAGGREGATE_RANGE_MAX_DAYS: Knopf aufs jüngste Fenster,
    ältere Tage werden als Rest genannt."""
    from backend.services.repair_orchestrator import REAGGREGATE_RANGE_MAX_DAYS

    alt = date.today() - timedelta(days=REAGGREGATE_RANGE_MAX_DAYS + 20)
    neu = date.today() - timedelta(days=1)
    rows = [
        _tz(alt, wallbox_3=-5.0, eauto_4=-5.0),
        _tz(neu, wallbox_3=-7.0, eauto_4=-7.0),
    ]
    result = await _run(rows, _anlage())
    warn = [e for e in result if e.kategorie == _KAT][0]
    erwartet_von = max(alt, neu - timedelta(days=REAGGREGATE_RANGE_MAX_DAYS - 1))
    assert warn.action_params["von"] == erwartet_von.isoformat()
    assert "außerhalb des" in warn.details
