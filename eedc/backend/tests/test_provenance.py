"""
Unit-Tests für write_with_provenance() (Etappe 3d Päckchen 1).

Self-contained Standalone-Script — pytest ist (noch) nicht im Projekt
eingerichtet. Aufruf:

    eedc/backend/venv/bin/python eedc/backend/tests/test_provenance.py

Test-Funktionen heißen `test_*` und sind kompatibel zu späterem pytest-
asyncio-Einzug. Solange wir keinen pytest-Runner haben, übernimmt der
__main__-Block die Ausführung.

Konzept: docs/KONZEPT-DATENPIPELINE.md Sektion 8 Päckchen 1 — fünf
Akzeptanz-Test-Fälle:

  1. applied bei höherer Priorität
  2. applied bei gleicher Priorität (Last-Writer-Wins)
  3. rejected_lower_priority bei niedrigerer Priorität (+ Audit-Log)
  4. no_op_same_value bei identischem Wert + input_hash
  5. force_override durchbricht Hierarchie + schreibt repair-Source

Bonus-Tests: initial_write, KeyError bei unbekanntem Source-Label.
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from contextlib import asynccontextmanager
from pathlib import Path

# Projekt-Root in sys.path, damit `from backend...` funktioniert.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402

from backend.core.database import Base  # noqa: E402

# Modelle müssen für Base.metadata.create_all importiert werden.
from backend.models import (  # noqa: E402, F401
    Anlage,
    DataProvenanceLog,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.services.provenance import write_with_provenance  # noqa: E402


# ───────────────────────────── Test-Fixture ──────────────────────────────


@asynccontextmanager
async def _session_ctx():
    """In-memory SQLite + frische Schema-Anlage pro Test, mit sauberem Teardown."""
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


async def _make_md(session: AsyncSession) -> Monatsdaten:
    """Erstellt Anlage + Monatsdaten und committet, damit der Helper auf einer
    realen Row arbeitet."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="DE")
    session.add(anlage)
    await session.flush()
    md = Monatsdaten(
        anlage_id=anlage.id,
        jahr=2026,
        monat=4,
        einspeisung_kwh=0.0,
        netzbezug_kwh=0.0,
        source_provenance={},
    )
    session.add(md)
    await session.commit()
    return md


async def _audit_decisions(session: AsyncSession) -> list[str]:
    rows = (await session.execute(
        select(DataProvenanceLog).order_by(DataProvenanceLog.id)
    )).scalars().all()
    return [r.decision for r in rows]


# ───────────────────────────── Test-Cases ────────────────────────────────


async def test_initial_write_applied():
    """Initial-Write auf leere Provenance → immer applied."""
    async with _session_ctx() as session:
        md = await _make_md(session)

        result = await write_with_provenance(
            session, md, "netzbezug_kwh", 100.0,
            source="manual:form", writer="user@example.com",
        )
        await session.commit()

        assert result.applied is True
        assert result.decision == "applied"
        assert md.netzbezug_kwh == 100.0
        assert md.source_provenance["netzbezug_kwh"]["source"] == "manual:form"
        assert md.source_provenance["netzbezug_kwh"]["writer"] == "user@example.com"
        assert "at" in md.source_provenance["netzbezug_kwh"]
        assert (await _audit_decisions(session)) == ["applied"]


async def test_higher_priority_overrides_existing():
    """Bestehender FALLBACK-Eintrag wird von MANUAL überschrieben (höhere Priorität)."""
    async with _session_ctx() as session:
        md = await _make_md(session)

        await write_with_provenance(
            session, md, "netzbezug_kwh", 80.0,
            source="fallback:sensor_snapshot", writer="snapshot_aggregator",
        )
        await session.commit()

        result = await write_with_provenance(
            session, md, "netzbezug_kwh", 100.0,
            source="manual:form", writer="user@example.com",
        )
        await session.commit()

        assert result.decision == "applied"
        assert md.netzbezug_kwh == 100.0
        assert md.source_provenance["netzbezug_kwh"]["source"] == "manual:form"
        assert (await _audit_decisions(session)) == ["applied", "applied"]


async def test_equal_priority_last_writer_wins():
    """Zwei MANUAL-Schreiber: zweiter gewinnt (Last-Writer-Wins)."""
    async with _session_ctx() as session:
        md = await _make_md(session)

        await write_with_provenance(
            session, md, "netzbezug_kwh", 100.0,
            source="manual:form", writer="alice@example.com",
        )
        result = await write_with_provenance(
            session, md, "netzbezug_kwh", 105.0,
            source="manual:csv_import", writer="bob@example.com",
        )
        await session.commit()

        assert result.decision == "applied"
        assert md.netzbezug_kwh == 105.0
        assert md.source_provenance["netzbezug_kwh"]["source"] == "manual:csv_import"
        assert md.source_provenance["netzbezug_kwh"]["writer"] == "bob@example.com"


async def test_lower_priority_rejected():
    """Bestehender MANUAL-Eintrag, FALLBACK versucht zu schreiben → rejected_lower_priority."""
    async with _session_ctx() as session:
        md = await _make_md(session)

        await write_with_provenance(
            session, md, "netzbezug_kwh", 100.0,
            source="manual:form", writer="alice@example.com",
        )
        result = await write_with_provenance(
            session, md, "netzbezug_kwh", 999.0,  # destruktiver Wert
            source="fallback:sensor_snapshot", writer="snapshot_aggregator",
        )
        await session.commit()

        assert result.applied is False
        assert result.decision == "rejected_lower_priority"
        assert result.conflicting_source == "manual:form"
        # Wert UNVERÄNDERT — das ist der Witz an Risiko #1+#2.
        assert md.netzbezug_kwh == 100.0
        assert md.source_provenance["netzbezug_kwh"]["source"] == "manual:form"
        # Audit-Log dokumentiert den abgewiesenen Versuch — Diagnose-Spur für
        # „warum hat der Auto-Job heute nichts geändert?".
        assert (await _audit_decisions(session)) == ["applied", "rejected_lower_priority"]


async def test_no_op_same_value_with_input_hash():
    """Identischer Wert + identischer input_hash → no_op_same_value."""
    async with _session_ctx() as session:
        md = await _make_md(session)

        await write_with_provenance(
            session, md, "netzbezug_kwh", 100.0,
            source="external:cloud_import:fronius_solarweb",
            writer="cloud_account_42",
            input_hash="sha256:abc123",
        )
        # Re-Import mit identischem Payload — soll kein Noise erzeugen, aber
        # im Audit-Log auftauchen, damit man sehen kann, dass der Sync läuft.
        result = await write_with_provenance(
            session, md, "netzbezug_kwh", 100.0,
            source="external:cloud_import:fronius_solarweb",
            writer="cloud_account_42",
            input_hash="sha256:abc123",
        )
        await session.commit()

        assert result.applied is False
        assert result.decision == "no_op_same_value"
        assert md.netzbezug_kwh == 100.0  # unverändert
        assert (await _audit_decisions(session)) == ["applied", "no_op_same_value"]


async def test_force_override_breaks_hierarchy():
    """force_override=True schreibt unabhängig von Hierarchie + Source wird "repair"."""
    async with _session_ctx() as session:
        md = await _make_md(session)

        await write_with_provenance(
            session, md, "netzbezug_kwh", 100.0,
            source="manual:form", writer="alice@example.com",
        )
        # Repair-Operation überschreibt manuell gepflegten Wert. Source-Argument
        # ist irrelevant — effektive Source wird "repair".
        result = await write_with_provenance(
            session, md, "netzbezug_kwh", 50.0,
            source="manual:form",  # wird ignoriert
            writer="repair_op_42",
            force_override=True,
        )
        await session.commit()

        assert result.decision == "applied"
        assert md.netzbezug_kwh == 50.0
        assert md.source_provenance["netzbezug_kwh"]["source"] == "repair"
        assert md.source_provenance["netzbezug_kwh"]["writer"] == "repair_op_42"
        rows = (await session.execute(
            select(DataProvenanceLog).order_by(DataProvenanceLog.id)
        )).scalars().all()
        assert rows[-1].source == "repair"
        assert rows[-1].decision == "applied"
        assert "force_override" in rows[-1].decision_reason


# ─────────────────────────── Bonus-Test-Cases ────────────────────────────


async def test_unknown_source_raises_keyerror():
    """Unbekannte Source-Labels werden NICHT stillschweigend akzeptiert
    (Memory-Linie feedback_silent_except_logs.md). KeyError ist gewollt."""
    async with _session_ctx() as session:
        md = await _make_md(session)

        raised = False
        try:
            await write_with_provenance(
                session, md, "netzbezug_kwh", 100.0,
                source="manual:json_backup",  # wird P2 sein, in P1 noch nicht
                writer="restore_op",
            )
        except KeyError:
            raised = True
        assert raised, "Unbekanntes Source-Label muss KeyError werfen"


# ─────────────────────────────── Runner ──────────────────────────────────


_TESTS = [
    test_initial_write_applied,
    test_higher_priority_overrides_existing,
    test_equal_priority_last_writer_wins,
    test_lower_priority_rejected,
    test_no_op_same_value_with_input_hash,
    test_force_override_breaks_hierarchy,
    test_unknown_source_raises_keyerror,
]


async def _run_all() -> int:
    failures = 0
    for test in _TESTS:
        try:
            await test()
        except AssertionError as e:
            failures += 1
            print(f"FAIL {test.__name__}: {e}")
            traceback.print_exc()
            continue
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"ERROR {test.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            continue
        print(f"OK   {test.__name__}")
    return failures


if __name__ == "__main__":
    failures = asyncio.run(_run_all())
    if failures:
        print(f"\n{failures} Test(s) fehlgeschlagen.")
        sys.exit(1)
    print(f"\nAlle {len(_TESTS)} Tests grün.")
