"""Kalender-Anker der Amortisations-Kurve (Radiocarbonat, Forum v4.0.0).

Der ROI-Verlauf modelliert ab „Jahr 0" = Investitionszeitpunkt; die Sicht zeigte
deshalb nur eine Dauer („12,3 Jahre"), nie ein Datum. `basis_jahr` (frühestes
Anschaffungsjahr) macht die X-Achse kalendrisch beschriftbar,
`gesamt_amortisation_jahr` ist das daraus abgeleitete Break-Even-Jahr.

Bei mehreren Investitionen mit verschiedenen Anschaffungsdaten ist das früheste
Jahr der Anker — dieselbe Näherung, die die Kurve mit ihrer konstanten
Jahres-Einsparung ohnehin macht.
"""

from __future__ import annotations

import math
from datetime import date

from backend.api.routes.investitionen.crud import get_roi_dashboard
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten


async def _seed(db, *, daten: list[date | None]) -> int:
    """Anlage mit je einem PV-Modul pro übergebenem Anschaffungsdatum."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2026, monat=5,
                       netzbezug_kwh=100.0, einspeisung_kwh=300.0))
    for i, d in enumerate(daten):
        pv = Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=f"Dach-{i}",
            leistung_kwp=10.0, anschaffungsdatum=d,
            anschaffungskosten_gesamt=10000.0,
        )
        db.add(pv)
        await db.flush()
        db.add(InvestitionMonatsdaten(
            investition_id=pv.id, jahr=2026, monat=5,
            verbrauch_daten={"pv_erzeugung_kwh": 800.0},
        ))
    await db.flush()
    return anlage.id


async def _roi(db, anlage_id: int):
    return await get_roi_dashboard(
        anlage_id=anlage_id, strompreis_cent=30.0, einspeiseverguetung_cent=8.0,
        benzinpreis_euro=None, jahr=None, db=db,
    )


async def test_basis_jahr_ist_das_frueheste_anschaffungsjahr(db):
    anlage_id = await _seed(db, daten=[date(2024, 6, 1), date(2021, 3, 15), date(2026, 1, 9)])
    await db.commit()

    result = await _roi(db, anlage_id)

    assert result.basis_jahr == 2021


async def test_amortisationsjahr_ist_basis_plus_dauer(db):
    anlage_id = await _seed(db, daten=[date(2023, 4, 1)])
    await db.commit()

    result = await _roi(db, anlage_id)

    assert result.gesamt_amortisation_jahre is not None
    # Aufgerundet: im angebrochenen Jahr ist die Kostendeckung noch nicht erreicht.
    assert result.gesamt_amortisation_jahr == 2023 + math.ceil(result.gesamt_amortisation_jahre)


async def test_ohne_anschaffungsdatum_bleibt_der_anker_offen(db):
    """Ohne gepflegtes Datum kein erfundenes Jahr — die Achse bleibt Index-basiert."""
    anlage_id = await _seed(db, daten=[None])
    await db.commit()

    result = await _roi(db, anlage_id)

    assert result.basis_jahr is None
    assert result.gesamt_amortisation_jahr is None
    # Die Dauer selbst bleibt davon unberührt.
    assert result.gesamt_amortisation_jahre is not None
