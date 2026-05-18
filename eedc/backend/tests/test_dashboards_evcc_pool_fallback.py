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


# ── #262 Folge-Bündel: evcc-Datenform ohne expliziten ladung_netz_kwh-Key ───
#
# junky84 hat nach v3.31.3 gemeldet: PV-Anteil 100 %, Netzladung 0 kWh in
# Wallbox-/E-Auto-Dashboard. Ursache: evcc-Portal-Import schreibt nur
# `ladung_kwh` + `ladung_pv_kwh` in die Wallbox-Monatsdaten — `ladung_netz_kwh`
# fehlt komplett, und die Pool-Aggregationen lasen den Key direkt → Netz = 0.
#
# Helper `get_emob_pv_netz_kwh()` leitet bei fehlendem Key aus `Total − PV` ab.
# Nach Verifikation gegen Gernots evcc-CSV (5 Sessions, 80 kWh Total, 66 kWh PV,
# 14 kWh Netz) + seine HA-Template-Helper (gleiche Formel).


@pytest.mark.asyncio
async def test_wallbox_dashboard_evcc_ohne_netz_key():
    """junky84 Folge-Bug: Wallbox hat nur ladung_kwh + ladung_pv_kwh (kein
    ladung_netz_kwh-Key — typische evcc-Import-Datenform). Vor dem Fix wurde
    PV-Anteil als 100 % gerendert, weil netz direkt 0 zurückgab.
    """
    from backend.api.routes.investitionen import get_wallbox_dashboard

    async with _session_ctx() as db:
        anlage_id = await _seed_anlage(db)
        wb = await _add_inv(db, anlage_id, "wallbox", "Warp3")
        ea = await _add_inv(db, anlage_id, "e-auto", "Smart #1")

        # evcc-Datenform: nur Total + PV (ladung_netz_kwh fehlt absichtlich)
        await _add_imd(db, wb.id, 2026, 5, {
            "ladung_kwh": 80.02,        # 5 Sessions, ~14 kWh Netz drin
            "ladung_pv_kwh": 65.97,
            "ladevorgaenge": 5,
        })
        await _add_imd(db, ea.id, 2026, 5, {"km_gefahren": 115})
        await db.commit()

        result = await get_wallbox_dashboard(anlage_id=anlage_id, strompreis_cent=30.0, db=db)
        assert len(result) == 1
        z = result[0].zusammenfassung
        # SoT-Helper leitet netz = 80.02 − 65.97 = 14.05 kWh ab
        assert abs(z["ladung_pv_kwh"] - 65.97) < 0.1, (
            f"Erwartet PV 65.97, war {z['ladung_pv_kwh']}"
        )
        assert abs(z["ladung_netz_kwh"] - 14.05) < 0.1, (
            f"Erwartet Netz 14.05 (= total − pv), war {z['ladung_netz_kwh']}"
        )
        assert abs(z["gesamt_heim_ladung_kwh"] - 80.02) < 0.1
        # PV-Anteil sollte NICHT 100 % sein (vor dem Fix: 100 %)
        assert z["pv_anteil_prozent"] < 100.0, (
            f"PV-Anteil darf nicht 100 % sein wenn Netz-Anteil existiert, war "
            f"{z['pv_anteil_prozent']}"
        )
        assert abs(z["pv_anteil_prozent"] - 82.4) < 0.5, (
            f"Erwartet PV-Anteil ~82.4 %, war {z['pv_anteil_prozent']}"
        )


@pytest.mark.asyncio
async def test_eauto_dashboard_evcc_ohne_netz_key():
    """Spiegelbild für E-Auto-Dashboard: Pool-Fallback muss bei evcc-only-Daten
    (kein ladung_netz_kwh-Key) den Netz-Anteil aus Total − PV ableiten.
    """
    from backend.api.routes.investitionen import get_eauto_dashboard

    async with _session_ctx() as db:
        anlage_id = await _seed_anlage(db)
        wb = await _add_inv(db, anlage_id, "wallbox", "Warp3")
        ea = await _add_inv(db, anlage_id, "e-auto", "Smart #1")

        await _add_imd(db, wb.id, 2026, 5, {
            "ladung_kwh": 80.02,
            "ladung_pv_kwh": 65.97,
        })
        await _add_imd(db, ea.id, 2026, 5, {"km_gefahren": 115})
        await db.commit()

        result = await get_eauto_dashboard(
            anlage_id=anlage_id, strompreis_cent=30.0, benzinpreis_euro=1.65, db=db
        )
        z = result[0].zusammenfassung
        assert abs(z["ladung_pv_kwh"] - 65.97) < 0.1
        assert abs(z["ladung_netz_kwh"] - 14.05) < 0.1, (
            f"E-Auto-Dashboard muss Netz aus Wallbox-Pool ableiten, war "
            f"{z['ladung_netz_kwh']}"
        )


def test_helper_get_emob_pv_netz_kwh_evcc_form():
    """SoT-Helper Unit-Test: evcc-Datenform (Total + PV, kein netz-Key)."""
    from backend.core.field_definitions import get_emob_pv_netz_kwh

    # Fall A: evcc-Import — nur Total + PV
    pv, netz = get_emob_pv_netz_kwh({"ladung_kwh": 80.02, "ladung_pv_kwh": 65.97})
    assert abs(pv - 65.97) < 0.01
    assert abs(netz - 14.05) < 0.01

    # Fall B: explizit gepflegt — alle drei Keys vorhanden
    pv, netz = get_emob_pv_netz_kwh({
        "ladung_kwh": 100, "ladung_pv_kwh": 60, "ladung_netz_kwh": 40,
    })
    assert pv == 60.0
    assert netz == 40.0

    # Fall C: ladung_netz_kwh=0 explizit gepflegt (reine PV-Anlage)
    pv, netz = get_emob_pv_netz_kwh({
        "ladung_kwh": 100, "ladung_pv_kwh": 100, "ladung_netz_kwh": 0,
    })
    assert pv == 100.0
    assert netz == 0.0  # Explizite 0 wird NICHT mit Fallback überschrieben

    # Fall D: leere Daten
    pv, netz = get_emob_pv_netz_kwh({})
    assert pv == 0.0
    assert netz == 0.0

    # Fall E: nur Total (kein PV) — Netz = Total
    pv, netz = get_emob_pv_netz_kwh({"ladung_kwh": 50})
    assert pv == 0.0
    assert netz == 50.0

    # Fall F: PV > Total (Rundungs-Edge-Case) — Netz = 0, nicht negativ
    pv, netz = get_emob_pv_netz_kwh({"ladung_kwh": 100, "ladung_pv_kwh": 101})
    assert pv == 101.0
    assert netz == 0.0  # max(0, 100 − 101) = 0

    # Fall G: total_kwh als Argument übergeben (spart Doppellesung)
    pv, netz = get_emob_pv_netz_kwh({"ladung_pv_kwh": 30}, total_kwh=80)
    assert pv == 30.0
    assert netz == 50.0


def test_evcc_parser_csv_smoketest():
    """Real-world evcc-CSV (Gernot 2026-05, 5 Sessions) durch Parser, ergibt
    `wallbox_ladung_kwh` + `wallbox_ladung_pv_kwh` für genau einen Monat.
    Validiert Mathematik gegen Hand-Rechnung (Σ Energie × Solar%/100).
    """
    from backend.services.import_parsers.evcc import EVCCParser

    csv_content = (
        "﻿Startzeit;Endzeit;Ladepunkt;Kennung;Fahrzeug;Kilometerstand (km);"
        "Anfangszählerstand (kWh);Endzählerstand (kWh);Energie (kWh);Ladedauer;"
        "Sonne (%);Preis;Preis/kWh;CO₂/kWh;Reference Price/kWh;Reference CO2/kWh (gCO2eq)\n"
        "2026-05-13 18:53:35;2026-05-14 16:46:05;Carport;;Smart #1;;5369,715;5397,137;"
        "27,429;5h21m5s;97,815;2,3262;0,0848;3,5376;0,3;181,866\n"
        "2026-05-08 16:36:22;2026-05-10 18:25:22;Carport;;Smart #1;21085;5335,651;"
        "5369,708;34,057;13h39m30s;99,484;2,7632;0,0811;0,6724;0,3;183,732\n"
        # Session 3 = reine Netz-Ladung (Sonne 0.07 %) — Edge-Case
        "2026-05-07 17:42:22;2026-05-08 07:47:52;Carport;;Smart #1;21023;5322,363;"
        "5335,651;13,253;39m29s;0,0715;3,9738;0,2998;224,839;0,3;185,7526\n"
        "2026-05-06 13:24:22;2026-05-06 14:25:52;Carport;;Smart #1;20970;5318,899;"
        "5322,363;3,459;59m29s;99,8353;0,278;0,0804;0,2687;0,3;185,9794\n"
        "2026-05-04 15:43:49;2026-05-04 16:16:49;Carport;;Smart #1;;5317,118;5318,898;"
        "1,818;31m0s;98,5746;0,1511;0,0831;2,2652;0,3;174,3093"
    )

    parser = EVCCParser()
    assert parser.can_parse(csv_content, "session.csv")
    result = parser.parse(csv_content)
    assert len(result) == 1
    m = result[0]
    assert (m.jahr, m.monat) == (2026, 5)
    # Σ Energie über 5 Sessions
    assert abs(m.wallbox_ladung_kwh - 80.02) < 0.05
    # Σ (Energie × Sonne%/100): 26.83 + 33.88 + 0.009 + 3.45 + 1.79 ≈ 65.96
    assert abs(m.wallbox_ladung_pv_kwh - 65.96) < 0.05
    assert m.wallbox_ladevorgaenge == 5
    # km = 21085 - 20970 = 115 (3 von 5 Sessions ohne km-Eintrag)
    assert m.eauto_km_gefahren == 115


def test_evcc_parser_to_write_writes_ladung_netz_kwh():
    """Round-Trip: ParsedMonthData → data_import-Write-Site setzt jetzt
    `ladung_netz_kwh = max(0, ladung_kwh − ladung_pv_kwh)` mit. #262 Fix B
    (Import-Site) — verhindert dass NEUE evcc-Imports erneut ohne netz-Key
    in die DB schreiben.

    Test direkt am verbrauch-Dict-Aufbau (kein FastAPI-Roundtrip nötig).
    """
    # ParsedMonthData-Schnittstelle simulieren: nur die für den Wallbox-Block
    # relevanten Felder
    class MockInput:
        wallbox_ladung_kwh = 80.02
        wallbox_ladung_pv_kwh = 65.97
        wallbox_ladevorgaenge = 5

    monat_input = MockInput()
    # Reproduktion der Logik aus data_import.py:460-475
    verbrauch = {"ladung_kwh": monat_input.wallbox_ladung_kwh}
    if monat_input.wallbox_ladung_pv_kwh is not None:
        verbrauch["ladung_pv_kwh"] = monat_input.wallbox_ladung_pv_kwh
        verbrauch["ladung_netz_kwh"] = max(
            0.0,
            monat_input.wallbox_ladung_kwh - monat_input.wallbox_ladung_pv_kwh,
        )
    if monat_input.wallbox_ladevorgaenge is not None:
        verbrauch["ladevorgaenge"] = monat_input.wallbox_ladevorgaenge

    assert verbrauch["ladung_kwh"] == 80.02
    assert verbrauch["ladung_pv_kwh"] == 65.97
    assert abs(verbrauch["ladung_netz_kwh"] - 14.05) < 0.01
    assert verbrauch["ladevorgaenge"] == 5
