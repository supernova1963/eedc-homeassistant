"""
Unit-Tests für services/import_writer.py (Etappe 3d Päckchen 2).

Self-contained Standalone-Script (kein pytest im Projekt).
Aufruf: eedc/backend/venv/bin/python eedc/backend/tests/test_import_writer.py

Akzeptanz-Tests aus Konzept Sektion 8 Päckchen 2:
- INSERT-Pfad (keine existing)
- UPDATE mit Full-Payload-No-Op (gleicher Hash)
- UPDATE mit ueberschreiben=False (Status-quo-Skip)
- UPDATE mit ueberschreiben=True (Hierarchie blockiert manuelle Werte)
- UPDATE mit ueberschreiben=True + gleiche Source-Klasse (Last-Writer-Wins)
- payload_hash canonical (Reihenfolge-unabhängig)
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
    DataProvenanceLog,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.services.import_writer import (  # noqa: E402
    payload_hash,
    upsert_investition_monatsdaten_with_provenance,
)
from backend.services.provenance import write_json_subkey_with_provenance  # noqa: E402


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


async def _make_inv(session: AsyncSession) -> Investition:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="DE")
    session.add(anlage)
    await session.flush()
    inv = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Test-EV")
    session.add(inv)
    await session.commit()
    return inv


async def _audit_decisions(session: AsyncSession) -> list[str]:
    rows = (await session.execute(
        select(DataProvenanceLog).order_by(DataProvenanceLog.id)
    )).scalars().all()
    return [r.decision for r in rows]


# ───────────────────────────── Test-Cases ────────────────────────────────


def test_payload_hash_is_canonical():
    """payload_hash: gleicher Inhalt in unterschiedlicher Reihenfolge → gleicher Hash."""
    h1 = payload_hash({"km_gefahren": 1200, "ladung_kwh": 130})
    h2 = payload_hash({"ladung_kwh": 130, "km_gefahren": 1200})
    assert h1 == h2
    assert h1.startswith("sha256:")
    h3 = payload_hash({"km_gefahren": 1500, "ladung_kwh": 130})
    assert h3 != h1, "andere Werte → anderer Hash"


async def test_insert_path_initial_write():
    """Frische Investition + Aufruf → INSERT, alle Sub-Keys applied."""
    async with _session_ctx() as session:
        inv = await _make_inv(session)

        result = await upsert_investition_monatsdaten_with_provenance(
            session,
            investition_id=inv.id, jahr=2026, monat=4,
            verbrauch_daten={"km_gefahren": 1200.0, "ladung_kwh": 130.0},
            source="manual:csv_import",
            writer="user@example.com",
        )
        await session.commit()

        assert result.inserted is True
        assert result.no_op_full_payload is False
        assert result.applied_count == 2
        assert result.rejected_count == 0

        imd = (await session.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id == inv.id
            )
        )).scalar_one()
        assert imd.verbrauch_daten == {"km_gefahren": 1200.0, "ladung_kwh": 130.0}
        assert imd.source_hash is not None
        assert imd.source_hash == payload_hash({"km_gefahren": 1200.0, "ladung_kwh": 130.0})
        # 2 applied audit entries (pro Sub-Key)
        assert (await _audit_decisions(session)) == ["applied", "applied"]


async def test_full_payload_no_op_emits_single_audit():
    """Identischer Payload-Hash → no_op_full_payload + EIN Audit-Eintrag."""
    async with _session_ctx() as session:
        inv = await _make_inv(session)

        await upsert_investition_monatsdaten_with_provenance(
            session,
            investition_id=inv.id, jahr=2026, monat=4,
            verbrauch_daten={"km_gefahren": 1200.0, "ladung_kwh": 130.0},
            source="external:cloud_import:fronius_solarweb",
            writer="cloud_account_42",
        )
        await session.commit()

        # Re-Import mit IDENTISCHEM Payload (auch andere Reihenfolge zählt als gleich)
        result = await upsert_investition_monatsdaten_with_provenance(
            session,
            investition_id=inv.id, jahr=2026, monat=4,
            verbrauch_daten={"ladung_kwh": 130.0, "km_gefahren": 1200.0},
            source="external:cloud_import:fronius_solarweb",
            writer="cloud_account_42",
            ueberschreiben=True,
        )
        await session.commit()

        assert result.inserted is False
        assert result.no_op_full_payload is True
        assert result.applied_count == 0  # keine Sub-Keys durchgegangen
        # Audit: 2 applied (Initial-Insert) + 1 no_op_same_value (Sentinel)
        assert (await _audit_decisions(session)) == [
            "applied", "applied", "no_op_same_value",
        ]


async def test_update_ueberschreiben_false_skips_existing_subkeys():
    """ueberschreiben=False: bestehende Sub-Keys bleiben unangetastet,
    nur fehlende werden ergänzt — Status-quo-Verhalten."""
    async with _session_ctx() as session:
        inv = await _make_inv(session)

        await upsert_investition_monatsdaten_with_provenance(
            session, investition_id=inv.id, jahr=2026, monat=4,
            verbrauch_daten={"km_gefahren": 1200.0},
            source="manual:csv_import", writer="initial",
        )
        # Zweiter Import: km_gefahren existiert schon → skipped, ladung_kwh neu → applied
        result = await upsert_investition_monatsdaten_with_provenance(
            session, investition_id=inv.id, jahr=2026, monat=4,
            verbrauch_daten={"km_gefahren": 9999.0, "ladung_kwh": 130.0},
            source="manual:csv_import", writer="follow_up",
            ueberschreiben=False,
        )
        await session.commit()

        assert result.skipped_existing == ["km_gefahren"]
        assert result.applied_count == 1
        # km_gefahren = 1200 (unverändert), ladung_kwh = 130 (neu)
        imd = (await session.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id == inv.id
            )
        )).scalar_one()
        assert imd.verbrauch_daten == {"km_gefahren": 1200.0, "ladung_kwh": 130.0}


async def test_update_ueberschreiben_true_blocks_manual_per_subkey():
    """ueberschreiben=True + manuell gepflegter Sub-Key + Cloud-Import:
    Hierarchie schützt den manuellen Sub-Key, andere Sub-Keys aus dem
    Cloud-Payload werden legitim geschrieben. **Der Akzeptanz-Test für P2.**
    """
    async with _session_ctx() as session:
        inv = await _make_inv(session)

        # Schritt 1: Form-Schreiber pflegt verbrauch_daten manuell — geht NICHT
        # über den Wrapper, sondern direkt über write_json_subkey, wie es der
        # Form-Pfad in P3 tun wird (Stand-in-Setup für den Test).
        imd_seed = InvestitionMonatsdaten(
            investition_id=inv.id, jahr=2026, monat=4,
            verbrauch_daten={}, source_provenance={}, source_hash=None,
        )
        session.add(imd_seed)
        await session.flush()
        await write_json_subkey_with_provenance(
            session, imd_seed, "verbrauch_daten", "km_gefahren", 1200.0,
            source="manual:form", writer="alice@example.com",
        )
        await session.commit()

        # Schritt 2: Cloud-Import bringt km_gefahren UND ladung_kwh
        result = await upsert_investition_monatsdaten_with_provenance(
            session,
            investition_id=inv.id, jahr=2026, monat=4,
            verbrauch_daten={"km_gefahren": 1500.0, "ladung_kwh": 130.0},
            source="external:cloud_import:fronius_solarweb",
            writer="cloud_account_42",
            ueberschreiben=True,
        )
        await session.commit()

        assert result.applied_count == 1
        assert result.rejected_count == 1
        assert result.rejected_fields == ["km_gefahren"]
        # Wert-Check: manuell GESCHÜTZT, Cloud-Sub-Key dazu
        imd = (await session.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id == inv.id
            )
        )).scalar_one()
        assert imd.verbrauch_daten == {"km_gefahren": 1200.0, "ladung_kwh": 130.0}
        # Provenance: km_gefahren bleibt manual:form, ladung_kwh ist cloud
        assert imd.source_provenance["verbrauch_daten.km_gefahren"]["source"] == "manual:form"
        assert imd.source_provenance["verbrauch_daten.ladung_kwh"]["source"] == \
            "external:cloud_import:fronius_solarweb"


async def test_update_ueberschreiben_true_same_class_last_writer_wins():
    """ueberschreiben=True bei zwei Source-Labels gleicher Priorität (z.B.
    zwei Cloud-Provider): Last-Writer-Wins, kein rejected."""
    async with _session_ctx() as session:
        inv = await _make_inv(session)

        await upsert_investition_monatsdaten_with_provenance(
            session, investition_id=inv.id, jahr=2026, monat=4,
            verbrauch_daten={"km_gefahren": 1200.0},
            source="external:cloud_import:fronius_solarweb",
            writer="account_1",
        )
        result = await upsert_investition_monatsdaten_with_provenance(
            session, investition_id=inv.id, jahr=2026, monat=4,
            verbrauch_daten={"km_gefahren": 1500.0},
            source="external:cloud_import:solaredge",  # andere Provider, gleiche Klasse
            writer="account_2",
            ueberschreiben=True,
        )
        await session.commit()

        assert result.applied_count == 1
        assert result.rejected_count == 0
        imd = (await session.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id == inv.id
            )
        )).scalar_one()
        assert imd.verbrauch_daten["km_gefahren"] == 1500.0
        assert imd.source_provenance["verbrauch_daten.km_gefahren"]["source"] == \
            "external:cloud_import:solaredge"


async def test_empty_payload_returns_no_op_no_db_writes():
    """Leerer Payload → kein DB-Write, kein Audit-Eintrag."""
    async with _session_ctx() as session:
        inv = await _make_inv(session)

        result = await upsert_investition_monatsdaten_with_provenance(
            session, investition_id=inv.id, jahr=2026, monat=4,
            verbrauch_daten={},
            source="manual:csv_import", writer="user",
        )
        await session.commit()

        assert result.inserted is False
        assert result.applied_count == 0
        # Keine InvestitionMonatsdaten-Row angelegt
        rows = (await session.execute(select(InvestitionMonatsdaten))).scalars().all()
        assert rows == []
        assert (await _audit_decisions(session)) == []


# ─────────────────────────────── Runner ──────────────────────────────────


_SYNC_TESTS = [test_payload_hash_is_canonical]
_ASYNC_TESTS = [
    test_insert_path_initial_write,
    test_full_payload_no_op_emits_single_audit,
    test_update_ueberschreiben_false_skips_existing_subkeys,
    test_update_ueberschreiben_true_blocks_manual_per_subkey,
    test_update_ueberschreiben_true_same_class_last_writer_wins,
    test_empty_payload_returns_no_op_no_db_writes,
]


async def _run_all() -> int:
    failures = 0
    for test in _SYNC_TESTS:
        try:
            test()
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
    for test in _ASYNC_TESTS:
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
    total = len(_SYNC_TESTS) + len(_ASYNC_TESTS)
    print(f"\nAlle {total} Tests grün.")
