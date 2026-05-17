"""
Wallbox- + E-Auto-Dashboard: Pool-Fallback bei evcc-Portal-Import (#262).

junky84 hat evcc-CSV importiert → Ladedaten landen architektonisch in der
Wallbox-Investition (data_import.py:453), nicht in der E-Auto-Investition.
Vor dem Fix zeigte:
  - Wallbox-Dashboard: "keine Ladedaten" (las nur E-Auto-Aggregate)
  - E-Auto-Dashboard: alle Ladung-Felder 0 (las nur eigene Monatsdaten)

Fix:
  - Wallbox-Dashboard: Pool-Max über E-Auto + Wallbox pro Feld
  - E-Auto-Dashboard: Wallbox-Pool wird km-anteilig auf die E-Autos verteilt,
    wenn die Wallbox mehr Heim-Ladung hat als alle E-Autos zusammen.

Self-contained:

    eedc/backend/venv/bin/python -m pytest \
        eedc/backend/tests/test_dashboards_evcc_pool_fallback.py
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from backend.core.database import Base  # noqa: E402
from backend.models import (  # noqa: E402, F401
    Anlage, Investition, InvestitionMonatsdaten,
)


@asynccontextmanager
async def _session_ctx():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


async def _seed_anlage(db: AsyncSession) -> int:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    return anlage.id


async def _add_inv(db, anlage_id, typ, bezeichnung):
    inv = Investition(
        anlage_id=anlage_id, typ=typ, bezeichnung=bezeichnung,
        anschaffungsdatum=date(2024, 1, 1),
    )
    db.add(inv)
    await db.flush()
    return inv


async def _add_imd(db, inv_id, jahr, monat, daten):
    db.add(InvestitionMonatsdaten(
        investition_id=inv_id, jahr=jahr, monat=monat,
        verbrauch_daten=daten,
    ))


@pytest.mark.asyncio
async def test_wallbox_dashboard_evcc_setup_zeigt_ladedaten():
    """junky84-Setup: Ladedaten nur in Wallbox-Inv, E-Auto hat nur km.
    Vorher: Wallbox-Dashboard zeigte 0. Jetzt: Pool-Max greift."""
    from backend.api.routes.investitionen import get_wallbox_dashboard

    async with _session_ctx() as db:
        anlage_id = await _seed_anlage(db)
        wb = await _add_inv(db, anlage_id, "wallbox", "Warp3")
        ea = await _add_inv(db, anlage_id, "e-auto", "Cupra Born")

        # Wallbox bekommt Ladedaten (evcc-Import-Style)
        await _add_imd(db, wb.id, 2026, 4, {
            "ladung_kwh": 250, "ladung_pv_kwh": 120, "ladung_netz_kwh": 130,
            "ladevorgaenge": 18,
        })
        # E-Auto bekommt nur km
        await _add_imd(db, ea.id, 2026, 4, {"km_gefahren": 1244})
        await db.commit()

        result = await get_wallbox_dashboard(anlage_id=anlage_id, strompreis_cent=30.0, db=db)
        assert len(result) == 1
        z = result[0].zusammenfassung
        # gesamt_heim_ladung sollte 250 kWh sein (aus Wallbox-Daten, vorher 0)
        assert z["gesamt_heim_ladung_kwh"] == 250.0, (
            f"Erwartet 250 kWh, war {z['gesamt_heim_ladung_kwh']}"
        )
        assert z["ladung_pv_kwh"] == 120.0
        assert z["ladung_netz_kwh"] == 130.0


@pytest.mark.asyncio
async def test_eauto_dashboard_evcc_setup_zeigt_ladedaten_anteilig():
    """junky84-Setup: Ladedaten in Wallbox, 1 E-Auto. Wallbox-Pool wird
    komplett auf das eine E-Auto verteilt (Anteil km/km_total = 1.0)."""
    from backend.api.routes.investitionen import get_eauto_dashboard

    async with _session_ctx() as db:
        anlage_id = await _seed_anlage(db)
        wb = await _add_inv(db, anlage_id, "wallbox", "Warp3")
        ea = await _add_inv(db, anlage_id, "e-auto", "Cupra Born")

        await _add_imd(db, wb.id, 2026, 4, {
            "ladung_kwh": 250, "ladung_pv_kwh": 120, "ladung_netz_kwh": 130,
        })
        await _add_imd(db, ea.id, 2026, 4, {"km_gefahren": 1244})
        await db.commit()

        result = await get_eauto_dashboard(anlage_id=anlage_id, strompreis_cent=30.0, benzinpreis_euro=1.65, db=db)
        assert len(result) == 1
        z = result[0].zusammenfassung
        assert z["ladung_pv_kwh"] == 120.0, f"PV-Anteil 120, war {z['ladung_pv_kwh']}"
        assert z["ladung_netz_kwh"] == 130.0
        assert z["ladung_heim_kwh"] == 250.0
        assert z["gesamt_km"] == 1244


@pytest.mark.asyncio
async def test_eauto_dashboard_premium_setup_unveraendert():
    """Premium-Setup: E-Auto hat eigene Ladedaten, mehr als Wallbox.
    Pool-Fallback greift NICHT, E-Auto-eigene Werte bleiben."""
    from backend.api.routes.investitionen import get_eauto_dashboard

    async with _session_ctx() as db:
        anlage_id = await _seed_anlage(db)
        wb = await _add_inv(db, anlage_id, "wallbox", "Warp3")
        ea = await _add_inv(db, anlage_id, "e-auto", "Cupra Born")

        # Wallbox-Sicht: 200 kWh
        await _add_imd(db, wb.id, 2026, 4, {
            "ladung_kwh": 200, "ladung_pv_kwh": 100, "ladung_netz_kwh": 100,
        })
        # E-Auto-Sicht: 250 kWh (mehr) — Premium-Setup, getrennt gepflegt
        await _add_imd(db, ea.id, 2026, 4, {
            "ladung_kwh": 250, "ladung_pv_kwh": 150, "ladung_netz_kwh": 100,
            "km_gefahren": 1244,
        })
        await db.commit()

        result = await get_eauto_dashboard(anlage_id=anlage_id, strompreis_cent=30.0, benzinpreis_euro=1.65, db=db)
        z = result[0].zusammenfassung
        # E-Auto-Werte bleiben (eauto_pool_summe > wb_pool_summe → use_wb_pool=False)
        assert z["ladung_pv_kwh"] == 150.0
        assert z["ladung_netz_kwh"] == 100.0


@pytest.mark.asyncio
async def test_eauto_dashboard_multi_eauto_km_anteilig():
    """2 E-Autos, Wallbox-Pool, km-anteilige Verteilung."""
    from backend.api.routes.investitionen import get_eauto_dashboard

    async with _session_ctx() as db:
        anlage_id = await _seed_anlage(db)
        wb = await _add_inv(db, anlage_id, "wallbox", "Warp3")
        ea1 = await _add_inv(db, anlage_id, "e-auto", "Auto A")
        ea2 = await _add_inv(db, anlage_id, "e-auto", "Auto B")

        # Wallbox: 300 kWh PV + 200 kWh Netz = 500 kWh
        await _add_imd(db, wb.id, 2026, 4, {
            "ladung_kwh": 500, "ladung_pv_kwh": 300, "ladung_netz_kwh": 200,
        })
        # Auto A: 600 km, Auto B: 400 km → 60/40 Aufteilung
        await _add_imd(db, ea1.id, 2026, 4, {"km_gefahren": 600})
        await _add_imd(db, ea2.id, 2026, 4, {"km_gefahren": 400})
        await db.commit()

        result = await get_eauto_dashboard(anlage_id=anlage_id, strompreis_cent=30.0, benzinpreis_euro=1.65, db=db)
        by_name = {r.investition.bezeichnung: r.zusammenfassung for r in result}

        # Auto A (60% km): PV 180, Netz 120
        assert abs(by_name["Auto A"]["ladung_pv_kwh"] - 180.0) < 0.1
        assert abs(by_name["Auto A"]["ladung_netz_kwh"] - 120.0) < 0.1
        # Auto B (40% km): PV 120, Netz 80
        assert abs(by_name["Auto B"]["ladung_pv_kwh"] - 120.0) < 0.1
        assert abs(by_name["Auto B"]["ladung_netz_kwh"] - 80.0) < 0.1
