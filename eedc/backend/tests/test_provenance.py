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
from backend.services.provenance import (  # noqa: E402
    write_json_subkey_with_provenance,
    write_with_provenance,
)


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


async def _make_md(session: AsyncSession, jahr: int = 2026, monat: int = 4) -> Monatsdaten:
    """Erstellt Anlage + Monatsdaten und committet, damit der Helper auf einer
    realen Row arbeitet. jahr/monat optional, damit ein Test mehrere Rows
    anlegen kann (UniqueConstraint anlage_id+jahr+monat)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="DE")
    session.add(anlage)
    await session.flush()
    md = Monatsdaten(
        anlage_id=anlage.id,
        jahr=jahr,
        monat=monat,
        einspeisung_kwh=0.0,
        netzbezug_kwh=0.0,
        source_provenance={},
    )
    session.add(md)
    await session.commit()
    return md


async def _make_imd(session: AsyncSession) -> InvestitionMonatsdaten:
    """Erstellt Anlage + Investition + InvestitionMonatsdaten."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="DE")
    session.add(anlage)
    await session.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="Test-EV",
    )
    session.add(inv)
    await session.flush()
    imd = InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={}, source_provenance={},
    )
    session.add(imd)
    await session.commit()
    return imd


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


async def test_manual_overrides_repair_unconditionally():
    """FrodoVDR #251: manual:* muss IMMER schreiben können, auch gegen
    bestehende repair-Provenance. Wenn User auf Speichern klickt, ist
    das nicht verhandelbar — keine Reparatur-Werkbank-Schleife mehr.
    """
    async with _session_ctx() as session:
        md = await _make_md(session)

        # Vorbedingung: Feld steht auf repair-Quelle (z. B. durch früheren
        # RESET_CLOUD_IMPORT oder Migrations-Artefakt).
        await write_with_provenance(
            session, md, "netzbezug_kwh", 0.0,
            source="manual:form",  # wird durch force_override zu "repair"
            writer="repair_op_42",
            force_override=True,
        )
        assert md.source_provenance["netzbezug_kwh"]["source"] == "repair"

        # Manuelle Eingabe danach: muss durchgehen.
        result = await write_with_provenance(
            session, md, "netzbezug_kwh", 250.0,
            source="manual:form", writer="alice@example.com",
        )
        await session.commit()

        assert result.applied is True
        assert result.decision == "applied"
        assert "manual override" in result.reason
        assert md.netzbezug_kwh == 250.0
        assert md.source_provenance["netzbezug_kwh"]["source"] == "manual:form"


async def test_manual_subkey_overrides_repair_unconditionally():
    """Pendant zu test_manual_overrides_repair_unconditionally für
    JSON-Sub-Keys (InvestitionMonatsdaten.verbrauch_daten). Genau Frodos
    Fall — PV-String-Wert auf `0` setzen muss durchgehen, selbst wenn
    Sub-Key auf repair gestempelt wäre.
    """
    async with _session_ctx() as session:
        imd = await _make_imd(session)

        await write_json_subkey_with_provenance(
            session, imd, "verbrauch_daten", "pv_erzeugung_kwh", 999.0,
            source="manual:form", writer="repair_op_99",
            force_override=True,
        )
        assert imd.source_provenance["verbrauch_daten.pv_erzeugung_kwh"]["source"] == "repair"

        result = await write_json_subkey_with_provenance(
            session, imd, "verbrauch_daten", "pv_erzeugung_kwh", 0.0,
            source="manual:form", writer="alice@example.com",
        )
        await session.commit()

        assert result.applied is True
        assert imd.verbrauch_daten["pv_erzeugung_kwh"] == 0.0
        assert imd.source_provenance["verbrauch_daten.pv_erzeugung_kwh"]["source"] == "manual:form"


async def test_ha_lts_hourly_daily_labels_accepted():
    """Etappe 4 (v3.31.0): neue Source-Labels external:ha_statistics:hourly
    und external:ha_statistics:daily werden vom Resolver akzeptiert und
    haben EXTERNAL_AUTHORITATIVE-Priorität — schlagen auto:* und fallback:*,
    verlieren gegen manual:*."""
    async with _session_ctx() as session:
        # Hourly schlägt auto:monatsabschluss
        md1 = await _make_md(session)
        await write_with_provenance(
            session, md1, "netzbezug_kwh", 50.0,
            source="auto:monatsabschluss", writer="rollup_op",
        )
        result = await write_with_provenance(
            session, md1, "netzbezug_kwh", 75.0,
            source="external:ha_statistics:hourly", writer="lts_reader",
        )
        await session.commit()
        assert result.applied is True
        assert md1.netzbezug_kwh == 75.0
        assert md1.source_provenance["netzbezug_kwh"]["source"] == "external:ha_statistics:hourly"

        # Daily schlägt fallback:sensor_snapshot
        md2 = await _make_md(session, jahr=2026, monat=6)
        await write_with_provenance(
            session, md2, "einspeisung_kwh", 100.0,
            source="fallback:sensor_snapshot", writer="snap_agg",
        )
        result = await write_with_provenance(
            session, md2, "einspeisung_kwh", 110.0,
            source="external:ha_statistics:daily", writer="lts_reader",
        )
        await session.commit()
        assert result.applied is True
        assert md2.einspeisung_kwh == 110.0

        # Daily verliert gegen bestehendes manual:form (Schutzrichtung
        # für vom User gepflegte Werte bleibt — manual:* always wins).
        md3 = await _make_md(session, jahr=2026, monat=7)
        await write_with_provenance(
            session, md3, "netzbezug_kwh", 42.0,
            source="manual:form", writer="alice@example.com",
        )
        result = await write_with_provenance(
            session, md3, "netzbezug_kwh", 88.0,
            source="external:ha_statistics:daily", writer="lts_reader",
        )
        await session.commit()
        assert result.applied is False
        assert result.decision == "rejected_lower_priority"
        assert md3.netzbezug_kwh == 42.0


async def test_unknown_source_raises_keyerror():
    """Unbekannte Source-Labels werden NICHT stillschweigend akzeptiert
    (Memory-Linie feedback_silent_except_logs.md). KeyError ist gewollt."""
    async with _session_ctx() as session:
        md = await _make_md(session)

        raised = False
        try:
            await write_with_provenance(
                session, md, "netzbezug_kwh", 100.0,
                source="external:imaginary_provider",  # nicht in SOURCE_LABELS
                writer="phantom_op",
            )
        except KeyError:
            raised = True
        assert raised, "Unbekanntes Source-Label muss KeyError werfen"


# ─────────── Tests für write_json_subkey_with_provenance (P2) ─────────────


async def test_json_subkey_initial_write_applied():
    """Initial-Write auf leeres JSON-Dict + leere Provenance → applied.
    Sub-Key landet im verbrauch_daten-Dict, Provenance unter
    'verbrauch_daten.<sub_key>'."""
    async with _session_ctx() as session:
        imd = await _make_imd(session)

        result = await write_json_subkey_with_provenance(
            session, imd, "verbrauch_daten", "km_gefahren", 1200.0,
            source="manual:form", writer="user@example.com",
        )
        await session.commit()

        assert result.decision == "applied"
        assert imd.verbrauch_daten == {"km_gefahren": 1200.0}
        assert imd.source_provenance["verbrauch_daten.km_gefahren"]["source"] == "manual:form"
        assert (await _audit_decisions(session)) == ["applied"]


async def test_json_subkey_per_field_hierarchy_protection():
    """Manuelle km_gefahren überlebt Cloud-Sync, der parallel ladung_kwh
    ergänzt. Per-Sub-Key-Hierarchie ist der Witz."""
    async with _session_ctx() as session:
        imd = await _make_imd(session)

        # User pflegt km_gefahren manuell
        await write_json_subkey_with_provenance(
            session, imd, "verbrauch_daten", "km_gefahren", 1200.0,
            source="manual:form", writer="alice@example.com",
        )
        # Cloud-Sync versucht km_gefahren UND ladung_kwh
        r1 = await write_json_subkey_with_provenance(
            session, imd, "verbrauch_daten", "km_gefahren", 1500.0,  # destruktiv
            source="external:cloud_import:fronius_solarweb",
            writer="cloud_account_42",
        )
        r2 = await write_json_subkey_with_provenance(
            session, imd, "verbrauch_daten", "ladung_kwh", 130.0,
            source="external:cloud_import:fronius_solarweb",
            writer="cloud_account_42",
        )
        await session.commit()

        assert r1.decision == "rejected_lower_priority"
        assert r1.conflicting_source == "manual:form"
        assert r2.decision == "applied"

        # km_gefahren UNVERÄNDERT (manueller Wert geschützt),
        # ladung_kwh frisch dazu (kein Vorgänger).
        assert imd.verbrauch_daten == {"km_gefahren": 1200.0, "ladung_kwh": 130.0}
        assert imd.source_provenance["verbrauch_daten.km_gefahren"]["source"] == "manual:form"
        assert imd.source_provenance["verbrauch_daten.ladung_kwh"]["source"] == \
            "external:cloud_import:fronius_solarweb"
        # Audit-Log: 1 applied + 1 rejected + 1 applied
        assert (await _audit_decisions(session)) == ["applied", "rejected_lower_priority", "applied"]


async def test_json_subkey_force_override_writes_repair():
    """force_override auf JSON-Sub-Key durchbricht Hierarchie + setzt
    Source 'repair'."""
    async with _session_ctx() as session:
        imd = await _make_imd(session)

        await write_json_subkey_with_provenance(
            session, imd, "verbrauch_daten", "km_gefahren", 1200.0,
            source="manual:form", writer="alice@example.com",
        )
        result = await write_json_subkey_with_provenance(
            session, imd, "verbrauch_daten", "km_gefahren", 800.0,
            source="manual:form", writer="repair_op_99",
            force_override=True,
        )
        await session.commit()

        assert result.decision == "applied"
        assert imd.verbrauch_daten["km_gefahren"] == 800.0
        assert imd.source_provenance["verbrauch_daten.km_gefahren"]["source"] == "repair"


# ─────────────────────────────── Runner ──────────────────────────────────


_TESTS = [
    test_initial_write_applied,
    test_higher_priority_overrides_existing,
    test_equal_priority_last_writer_wins,
    test_lower_priority_rejected,
    test_no_op_same_value_with_input_hash,
    test_force_override_breaks_hierarchy,
    test_unknown_source_raises_keyerror,
    # FrodoVDR #251 — manuelle Eingabe gewinnt unbedingt
    test_manual_overrides_repair_unconditionally,
    test_manual_subkey_overrides_repair_unconditionally,
    # Etappe 4 (v3.31.0) — HA-LTS-Labels
    test_ha_lts_hourly_daily_labels_accepted,
    # P2 — JSON-Sub-Key-Variante
    test_json_subkey_initial_write_applied,
    test_json_subkey_per_field_hierarchy_protection,
    test_json_subkey_force_override_writes_repair,
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
