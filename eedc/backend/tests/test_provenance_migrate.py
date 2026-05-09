"""
Unit-Tests für services/provenance_migrate.py (Etappe 3d Päckchen 3).

Self-contained Standalone-Script (kein pytest im Projekt).
Aufruf: eedc/backend/venv/bin/python eedc/backend/tests/test_provenance_migrate.py

Akzeptanz-Tests:
- Frische DB ohne Aggregat-Rows → Migration läuft, schreibt nichts.
- Pre-3d-Row ohne `source_provenance` → markiert mit `legacy:unknown`,
  Top-Level- und JSON-Sub-Keys getrennt.
- Row mit existierender Provenance → bleibt unverändert (idempotent).
- Re-Run der Migration ist No-Op auf bereits markierten Rows.
- Hierarchie-Pflicht: nach legacy:unknown-Markierung gewinnt jeder neue
  Schreiber (manual:form, auto:monatsabschluss, fallback:*) automatisch.
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from backend.core.database import Base  # noqa: E402
from backend.models import (  # noqa: E402, F401
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.services.provenance import write_with_provenance  # noqa: E402
from backend.services.provenance_migrate import (  # noqa: E402
    migrate_3d_p3_initial_provenance_legacy_unknown,
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


async def _make_anlage(session: AsyncSession) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="DE")
    session.add(anlage)
    await session.commit()
    return anlage


async def _make_inv(session: AsyncSession, anlage_id: int) -> Investition:
    inv = Investition(anlage_id=anlage_id, typ="e-auto", bezeichnung="Test-EV")
    session.add(inv)
    await session.commit()
    return inv


# ───────────────────────────── Test-Cases ────────────────────────────────


async def test_empty_db_returns_zero_counts():
    """Frische DB: kein Crash, alle counts = 0."""
    async with _session_ctx() as session:
        counts = await migrate_3d_p3_initial_provenance_legacy_unknown(session)
        assert counts == {
            "monatsdaten": 0,
            "investition_monatsdaten": 0,
            "tages_zusammenfassung": 0,
            "tages_energie_profil": 0,
        }


async def test_legacy_row_gets_provenance_top_level():
    """Pre-3d Monatsdaten-Row ohne source_provenance → markiert mit legacy:unknown."""
    async with _session_ctx() as session:
        anlage = await _make_anlage(session)
        md = Monatsdaten(
            anlage_id=anlage.id, jahr=2024, monat=3,
            einspeisung_kwh=120.5, netzbezug_kwh=42.0,
            pv_erzeugung_kwh=300.0,
        )
        # Bestandsdaten heißt: source_provenance = leeres dict (Default).
        session.add(md)
        await session.commit()

        counts = await migrate_3d_p3_initial_provenance_legacy_unknown(session)
        assert counts["monatsdaten"] == 1, counts

        await session.refresh(md)
        prov = md.source_provenance
        # Drei beschriebene Top-Level-Felder bekommen alle einen legacy-Eintrag
        for field in ("einspeisung_kwh", "netzbezug_kwh", "pv_erzeugung_kwh"):
            assert field in prov, f"{field} fehlt in {list(prov.keys())}"
            assert prov[field]["source"] == "legacy:unknown"
            assert prov[field]["writer"] == "initial_migration"
        # Identifier dürfen NICHT markiert sein
        for skip in ("id", "anlage_id", "jahr", "monat", "source_provenance", "source_hash"):
            assert skip not in prov


async def test_legacy_investition_monatsdaten_json_subkeys():
    """Pre-3d InvestitionMonatsdaten → verbrauch_daten-Sub-Keys werden markiert, NICHT die JSON-Spalte als Top-Level."""
    async with _session_ctx() as session:
        anlage = await _make_anlage(session)
        inv = await _make_inv(session, anlage.id)
        imd = InvestitionMonatsdaten(
            investition_id=inv.id, jahr=2024, monat=4,
            verbrauch_daten={"km_gefahren": 1200, "ladung_kwh": 130.5},
        )
        session.add(imd)
        await session.commit()

        await migrate_3d_p3_initial_provenance_legacy_unknown(session)
        await session.refresh(imd)
        prov = imd.source_provenance

        # Sub-Keys gemarkiert
        assert "verbrauch_daten.km_gefahren" in prov
        assert "verbrauch_daten.ladung_kwh" in prov
        assert prov["verbrauch_daten.km_gefahren"]["source"] == "legacy:unknown"

        # Top-Level-Eintrag „verbrauch_daten" darf NICHT existieren — sonst
        # würde Per-Sub-Key-Hierarchie (P2) blockiert.
        assert "verbrauch_daten" not in prov


async def test_existing_provenance_is_preserved():
    """Row mit existierender Provenance → wird NICHT überschrieben."""
    async with _session_ctx() as session:
        anlage = await _make_anlage(session)
        md = Monatsdaten(
            anlage_id=anlage.id, jahr=2024, monat=5,
            einspeisung_kwh=100.0, netzbezug_kwh=20.0,
        )
        # Simuliert: ein neuer Schreiber war schon da
        md.source_provenance = {
            "einspeisung_kwh": {
                "source": "manual:form", "writer": "user@local",
                "at": "2026-05-01T10:00:00", "input_hash": None,
            }
        }
        session.add(md)
        await session.commit()

        counts = await migrate_3d_p3_initial_provenance_legacy_unknown(session)
        assert counts["monatsdaten"] == 0, "Row mit Provenance darf nicht migriert werden"

        await session.refresh(md)
        # Bestehender Eintrag unverändert
        assert md.source_provenance["einspeisung_kwh"]["source"] == "manual:form"
        # NICHT zusätzlich legacy:unknown auf netzbezug_kwh — komplett geskipt.
        assert "netzbezug_kwh" not in md.source_provenance


async def test_idempotent_double_run():
    """Re-Run der Migration auf schon markierten Rows ist No-Op."""
    async with _session_ctx() as session:
        anlage = await _make_anlage(session)
        md = Monatsdaten(
            anlage_id=anlage.id, jahr=2024, monat=6,
            einspeisung_kwh=80.0, netzbezug_kwh=15.0,
        )
        session.add(md)
        await session.commit()

        first = await migrate_3d_p3_initial_provenance_legacy_unknown(session)
        assert first["monatsdaten"] == 1
        second = await migrate_3d_p3_initial_provenance_legacy_unknown(session)
        assert second["monatsdaten"] == 0, "zweiter Lauf darf nichts mehr markieren"


async def test_legacy_unknown_loses_to_any_new_writer():
    """Hierarchie-Pflicht: nach Legacy-Markierung gewinnt jeder neue Schreiber.

    Das ist der Sinn der Migration: ohne Provenance würde der neue Schreiber
    via `existing=None` stumm gewinnen. Mit `legacy:unknown` als niedrigster
    Stufe bleibt das Verhalten gleich, aber der Audit-Log dokumentiert den
    Pfad.
    """
    async with _session_ctx() as session:
        anlage = await _make_anlage(session)
        md = Monatsdaten(
            anlage_id=anlage.id, jahr=2024, monat=7,
            einspeisung_kwh=50.0,
        )
        session.add(md)
        await session.commit()

        await migrate_3d_p3_initial_provenance_legacy_unknown(session)
        await session.refresh(md)
        assert md.source_provenance["einspeisung_kwh"]["source"] == "legacy:unknown"

        # Manual:form schreibt drauf
        result = await write_with_provenance(
            session, md, "einspeisung_kwh", 99.9,
            source="manual:form", writer="user@local",
        )
        assert result.decision == "applied", result
        await session.commit()
        await session.refresh(md)
        assert md.source_provenance["einspeisung_kwh"]["source"] == "manual:form"

        # Fallback gewinnt auch (ist niedriger als manual:form, aber höher als legacy)
        anlage2 = await _make_anlage(session)
        md2 = Monatsdaten(
            anlage_id=anlage2.id, jahr=2024, monat=8,
            einspeisung_kwh=40.0,
        )
        session.add(md2)
        await session.commit()
        await migrate_3d_p3_initial_provenance_legacy_unknown(session)

        result2 = await write_with_provenance(
            session, md2, "einspeisung_kwh", 41.0,
            source="fallback:sensor_snapshot", writer="snapshot",
        )
        assert result2.decision == "applied", "fallback:* schlägt legacy:unknown"
        await session.commit()


# ───────────────────────────── Runner ────────────────────────────────────


async def main():
    cases = [
        test_empty_db_returns_zero_counts,
        test_legacy_row_gets_provenance_top_level,
        test_legacy_investition_monatsdaten_json_subkeys,
        test_existing_provenance_is_preserved,
        test_idempotent_double_run,
        test_legacy_unknown_loses_to_any_new_writer,
    ]
    fails = 0
    for case in cases:
        try:
            await case()
            print(f"OK   {case.__name__}")
        except Exception:
            fails += 1
            print(f"FAIL {case.__name__}")
            traceback.print_exc()
    if fails:
        print(f"\n{fails}/{len(cases)} Tests fehlgeschlagen.")
        sys.exit(1)
    else:
        print(f"\nAlle {len(cases)} Tests grün.")


if __name__ == "__main__":
    asyncio.run(main())
