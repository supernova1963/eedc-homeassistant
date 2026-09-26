"""P20 — E7 (Zählerlücken wie HA, Vorlage Fassung 7 §5): der Daten-Checker nennt
die Bestandstage ohne Regelmarke und bietet den bestehenden Reparaturweg an.

Tage mit ``TagesZusammenfassung.verworfen`` NULL wurden vor dem Umbau gerechnet
und bleiben bei N-92 (E6), bis sie neu aggregiert werden. Begrenzt auf Tage mit
Stundenzeilen; eine Zeile je Anlage; alle mit Marke ⇒ still.

Schwesterdateien: test_zaehlerluecken_tagesregel.py (R9: der Aggregator schreibt
die Marke immer), test_batterie_vorzeichen_historie_check.py (dieselbe Bauform
„Bestand + Bereichs-Reparatur", Präzedenz v3.45.6).
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.models import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.daten_checker import CheckKategorie, DatenChecker

TAG = date(2026, 5, 10)


async def _anlage(db, tage: dict[date, object], ohne_stunden: tuple = ()):
    a = Anlage(anlagenname="E7", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    for d, marke in tage.items():
        db.add(TagesZusammenfassung(anlage_id=a.id, datum=d, verworfen=marke))
        if d not in ohne_stunden:
            db.add(TagesEnergieProfil(anlage_id=a.id, datum=d, stunde=12, pv_kw=1.0))
    await db.commit()
    return a


def _quelle(vorhanden=True):
    from types import SimpleNamespace
    return patch(
        "backend.services.energie_profil.aggregations_quelle.ermittle_aggregations_quelle",
        new=AsyncMock(return_value=SimpleNamespace(vorhanden=vorhanden)),
    )


@pytest.mark.asyncio
async def test_p20_drei_tage_ohne_marke_eine_zeile_mit_zahl_und_reparaturweg(db):
    tage = {TAG + timedelta(days=i): None for i in range(3)}
    tage[TAG + timedelta(days=3)] = {}                              # mit Marke
    tage[TAG + timedelta(days=4)] = None                            # ohne Stunden ⇒ zählt nicht
    a = await _anlage(db, tage, ohne_stunden=(TAG + timedelta(days=4),))
    with _quelle():
        erg = await DatenChecker(db)._check_bestandstage_ohne_regelmarke(a)
    assert len(erg) == 1
    e = erg[0]
    assert e.kategorie == CheckKategorie.ENERGIEPROFIL_ABDECKUNG
    assert e.meldung.startswith("3 Tag(e) sind vor dem Umbau gerechnet")
    assert e.action_kind == "reaggregate_range"
    assert e.action_params == {"anlage_id": a.id, "von": "2026-05-10", "bis": "2026-05-12"}


@pytest.mark.asyncio
async def test_p20_alle_mit_marke_bleibt_still(db):
    a = await _anlage(db, {TAG: {}, TAG + timedelta(days=1): {"pv": 3.0}})
    with _quelle():
        assert await DatenChecker(db)._check_bestandstage_ohne_regelmarke(a) == []


@pytest.mark.asyncio
async def test_p20_mehr_als_31_tage_knopf_auf_das_juengste_fenster(db):
    tage = {TAG + timedelta(days=i): None for i in range(40)}
    a = await _anlage(db, tage)
    with _quelle():
        e = (await DatenChecker(db)._check_bestandstage_ohne_regelmarke(a))[0]
    assert e.meldung.startswith("40 Tag(e)")
    neuester = TAG + timedelta(days=39)
    assert e.action_params["bis"] == neuester.isoformat()
    assert e.action_params["von"] == (neuester - timedelta(days=30)).isoformat()
    assert "9 ältere(r) Tag(e)" in e.details


@pytest.mark.asyncio
async def test_p20_ohne_datenquelle_kein_knopf(db):
    a = await _anlage(db, {TAG: None})
    with _quelle(vorhanden=False):
        e = (await DatenChecker(db)._check_bestandstage_ohne_regelmarke(a))[0]
    assert e.action_kind is None


def test_p20_pruefung_ist_im_lauf_eingehaengt():
    """Die Zeile erreicht den Anwender nur, wenn `check_anlage` sie ruft."""
    import inspect
    src = inspect.getsource(DatenChecker.check_anlage)
    assert "self._check_bestandstage_ohne_regelmarke(anlage)" in src
