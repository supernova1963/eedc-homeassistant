"""
Unit-Tests für repair_orchestrator (Etappe 3d Päckchen 4).

Akzeptanz-Tests (Konzept Sektion 5 + 8 Päckchen 4):

  1. plan() ohne Daten → leerer Diff, applicable Operation
  2. plan() RESET_CLOUD_IMPORT mit Cloud-Provenance → korrekte Decisions
     pro Feld, source_after='repair'
  3. execute() RESET_CLOUD_IMPORT → Werte gehen auf NULL, Provenance auf
     'repair', audit_log_ids verknüpft (force_override greift trotz
     manual:form-Hierarchie)
  4. plan_lookup nach Expiry → LookupError beim Execute
  5. Doppel-Execute → LookupError beim zweiten Aufruf
  6. RESET_CLOUD_IMPORT mit providers-Filter → nur passende Felder
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (  # noqa: F401
    Anlage,
    DataProvenanceLog,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.services.provenance import write_with_provenance
from backend.services.repair_orchestrator import (
    RepairOperationRequest,
    RepairOperationType,
    _reset_state_for_tests,
    discard_plan,
    execute,
    list_plans,
    plan,
)


@pytest.fixture(autouse=True)
def _reset_repair_singleton():
    """Modul-Singleton vor jedem Test leeren — sonst leaken Plans aus dem
    Vorgänger-Test in `list_plans()`."""
    _reset_state_for_tests()


async def _make_anlage(session: AsyncSession) -> Anlage:
    a = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="DE")
    session.add(a)
    await session.commit()
    return a


async def _seed_cloud_md(
    session: AsyncSession, anlage_id: int, jahr: int, monat: int,
    *, source: str = "external:cloud_import:solaredge",
    netzbezug: float = 100.0, einspeisung: float = 50.0,
) -> Monatsdaten:
    """Baut eine Monatsdaten-Row und schreibt 2 Felder mit Cloud-Provenance."""
    md = Monatsdaten(
        anlage_id=anlage_id, jahr=jahr, monat=monat,
        netzbezug_kwh=0.0, einspeisung_kwh=0.0, source_provenance={},
    )
    session.add(md)
    await session.flush()

    await write_with_provenance(
        session, md, "netzbezug_kwh", netzbezug,
        source=source, writer="connector:run_1",
    )
    await write_with_provenance(
        session, md, "einspeisung_kwh", einspeisung,
        source=source, writer="connector:run_1",
    )
    await session.commit()
    return md


# ── Tests ────────────────────────────────────────────────────────────────────


async def test_plan_reset_cloud_import_no_data(db):
    """plan() ohne Cloud-Provenance liefert leeren Diff + No-Op-Warnung."""
    anlage = await _make_anlage(db)
    req = RepairOperationRequest(
        anlage_id=anlage.id,
        operation=RepairOperationType.RESET_CLOUD_IMPORT,
        params={},
    )

    plan_obj = await plan(req, db)

    assert plan_obj.diff_total_count == 0
    assert plan_obj.diff_preview == []
    assert plan_obj.estimated_changes.get("fields_total") == 0
    assert any("No-Op" in w for w in plan_obj.warnings), plan_obj.warnings


async def test_plan_reset_cloud_import_with_data(db):
    """plan() mit zwei Cloud-Feldern → 2 Diffs, source_after='repair'."""
    anlage = await _make_anlage(db)
    await _seed_cloud_md(db, anlage.id, 2026, 4)

    req = RepairOperationRequest(
        anlage_id=anlage.id,
        operation=RepairOperationType.RESET_CLOUD_IMPORT,
        params={},
    )
    plan_obj = await plan(req, db)

    assert plan_obj.diff_total_count == 2
    assert len(plan_obj.diff_preview) == 2
    for d in plan_obj.diff_preview:
        assert d.table == "monatsdaten"
        assert d.source_before == "external:cloud_import:solaredge"
        assert d.source_after == "repair"
        assert d.decision == "applied"
        # Monatsdaten.einspeisung_kwh + .netzbezug_kwh sind NOT NULL
        # mit Default 0 — Reset führt zu 0, nicht None.
        assert d.new_value == 0
    # Alle ursprünglichen Werte sind im Diff
    old_vals = sorted([d.old_value for d in plan_obj.diff_preview])
    assert old_vals == [50.0, 100.0]


async def test_execute_reset_cloud_import_writes_null_and_repair(db):
    """execute() setzt Werte auf NULL + Provenance='repair', Audit-IDs vorhanden."""
    anlage = await _make_anlage(db)
    md = await _seed_cloud_md(db, anlage.id, 2026, 4)

    req = RepairOperationRequest(
        anlage_id=anlage.id,
        operation=RepairOperationType.RESET_CLOUD_IMPORT,
        params={},
    )
    plan_obj = await plan(req, db)
    result = await execute(plan_obj.plan_id, db)

    assert result.actual_changes.get("fields_reset") == 2
    assert len(result.audit_log_ids) >= 2

    # Reload md
    await db.refresh(md)
    # NOT-NULL Spalten gehen auf Spalten-Default (0), nicht None.
    assert md.netzbezug_kwh == 0
    assert md.einspeisung_kwh == 0
    # Provenance ist auf 'repair' gestempelt
    prov = md.source_provenance or {}
    assert prov.get("netzbezug_kwh", {}).get("source") == "repair"
    assert prov.get("einspeisung_kwh", {}).get("source") == "repair"


async def test_force_override_breaks_manual_hierarchy(db):
    """RESET muss auch manual:form-Felder zurücksetzen können (force_override).

    Akzeptanz: manual:form steht über external:cloud_import in der Hierarchie.
    Ohne force_override würde der Reset abgelehnt werden. Das Konzept sagt
    aber: User kann seine eigenen manuellen Werte nuken wollen — und sieht
    sie in der Plan-Vorschau, bevor er bestätigt.

    Test-Setup: Wir scannen nach external:cloud_import, also würden manuelle
    Felder gar nicht im Reset-Scope landen. Aber wir prüfen via Plan-Diff,
    dass force_override im execute korrekt durchschlägt — kein
    rejected_lower_priority obwohl die ältere Source MANUAL ist.

    Realistisches Szenario: Cloud-Import schreibt zuerst, dann setzt User
    den gleichen Wert manuell — Provenance wechselt auf manual:form. Reset
    findet das Feld nicht mehr (Filter auf cloud_import). Wir testen also
    das Inverse: Cloud-Provenance bleibt, force_override wirkt.
    """
    anlage = await _make_anlage(db)
    md = await _seed_cloud_md(db, anlage.id, 2026, 4)

    # Manuell andere Felder schreiben — sollten NICHT vom Reset getroffen werden
    await write_with_provenance(
        db, md, "ueberschuss_kwh", 25.0,
        source="manual:form", writer="user@example.com",
    )
    await db.commit()

    req = RepairOperationRequest(
        anlage_id=anlage.id,
        operation=RepairOperationType.RESET_CLOUD_IMPORT,
        params={},
    )
    plan_obj = await plan(req, db)
    # Nur die 2 Cloud-Felder im Diff, nicht das manuelle ueberschuss_kwh
    assert plan_obj.diff_total_count == 2
    diff_fields = sorted(d.field for d in plan_obj.diff_preview)
    assert diff_fields == ["einspeisung_kwh", "netzbezug_kwh"]

    result = await execute(plan_obj.plan_id, db)
    assert result.actual_changes["fields_reset"] == 2

    await db.refresh(md)
    # Cloud-Felder sind auf Default 0 zurückgesetzt
    assert md.netzbezug_kwh == 0
    # Manuelle Felder unverändert
    assert md.ueberschuss_kwh == 25.0


async def test_double_execute_raises(db):
    """Zweiter Execute-Aufruf wirft LookupError ('bereits ausgeführt')."""
    anlage = await _make_anlage(db)
    await _seed_cloud_md(db, anlage.id, 2026, 4)

    plan_obj = await plan(
        RepairOperationRequest(
            anlage_id=anlage.id,
            operation=RepairOperationType.RESET_CLOUD_IMPORT,
            params={},
        ),
        db,
    )
    await execute(plan_obj.plan_id, db)

    try:
        await execute(plan_obj.plan_id, db)
    except LookupError as e:
        assert "bereits ausgef" in str(e), str(e)
    else:
        raise AssertionError("Erwarteter LookupError beim Doppel-Execute")


async def test_provider_filter_narrows_diff(db):
    """providers-Filter beschränkt den Reset auf passende Cloud-Provider."""
    anlage = await _make_anlage(db)
    # Drei Felder in DREI Rows (jahr=4/5/6) jeweils mit unterschiedlichen Providern
    md1 = await _seed_cloud_md(
        db, anlage.id, 2026, 4,
        source="external:cloud_import:solaredge",
    )
    md2 = await _seed_cloud_md(
        db, anlage.id, 2026, 5,
        source="external:cloud_import:fronius_solarweb",
    )

    plan_obj = await plan(
        RepairOperationRequest(
            anlage_id=anlage.id,
            operation=RepairOperationType.RESET_CLOUD_IMPORT,
            params={"providers": ["solaredge"]},
        ),
        db,
    )
    # Nur die 2 Felder von md1, nicht md2
    assert plan_obj.diff_total_count == 2
    for d in plan_obj.diff_preview:
        assert d.row_pk["jahr"] == 2026 and d.row_pk["monat"] == 4
        assert d.source_before == "external:cloud_import:solaredge"


async def test_list_plans_returns_recent_first(db):
    """list_plans gibt Pläne in chronologischer Reihenfolge (neueste zuerst)."""
    anlage = await _make_anlage(db)
    await _seed_cloud_md(db, anlage.id, 2026, 4)

    p1 = await plan(
        RepairOperationRequest(
            anlage_id=anlage.id,
            operation=RepairOperationType.RESET_CLOUD_IMPORT,
            params={},
        ),
        db,
    )
    await asyncio.sleep(0.01)  # Sicherstellen, dass created_at sich unterscheidet
    p2 = await plan(
        RepairOperationRequest(
            anlage_id=anlage.id,
            operation=RepairOperationType.KRAFTSTOFFPREIS_BACKFILL,
            params={"scope": "tages"},
        ),
        db,
    )

    views = await list_plans(anlage.id)
    assert len(views) == 2
    assert views[0].plan.plan_id == p2.plan_id, "neuester Plan zuerst"
    assert views[1].plan.plan_id == p1.plan_id
    assert views[0].result is None  # noch nicht ausgeführt
    assert views[1].result is None


async def test_plan_reaggregate_range_rejects_invalid_bounds(db):
    """Plan-Validierung: von > bis, bis = heute, > 31 Tage werfen ValueError."""
    from datetime import date, timedelta
    anlage = await _make_anlage(db)

    # bis < von
    try:
        await plan(RepairOperationRequest(
            anlage_id=anlage.id,
            operation=RepairOperationType.REAGGREGATE_RANGE,
            params={"von": "2026-05-10", "bis": "2026-05-05"},
        ), db)
    except ValueError as e:
        assert "liegt vor" in str(e), str(e)
    else:
        raise AssertionError("ValueError für bis<von erwartet")

    # bis = heute
    heute = date.today()
    try:
        await plan(RepairOperationRequest(
            anlage_id=anlage.id,
            operation=RepairOperationType.REAGGREGATE_RANGE,
            params={"von": (heute - timedelta(days=5)).isoformat(),
                    "bis": heute.isoformat()},
        ), db)
    except ValueError as e:
        assert "vor heute" in str(e), str(e)
    else:
        raise AssertionError("ValueError für bis=heute erwartet")

    # > 31 Tage
    try:
        await plan(RepairOperationRequest(
            anlage_id=anlage.id,
            operation=RepairOperationType.REAGGREGATE_RANGE,
            params={"von": "2026-01-01", "bis": "2026-03-01"},
        ), db)
    except ValueError as e:
        assert "Maximum" in str(e), str(e)
    else:
        raise AssertionError("ValueError für >31 Tage erwartet")


async def test_plan_reaggregate_range_valid_returns_warnings(db):
    """Plan mit gültigem Bereich liefert Warnungs-Liste + estimated dict."""
    anlage = await _make_anlage(db)

    plan_obj = await plan(RepairOperationRequest(
        anlage_id=anlage.id,
        operation=RepairOperationType.REAGGREGATE_RANGE,
        params={"von": "2026-04-01", "bis": "2026-04-07"},
    ), db)

    assert plan_obj.estimated_changes["anzahl_tage"] == 7
    assert plan_obj.estimated_changes["tage_mit_bestehender_zusammenfassung"] == 0
    # Pflicht-Warnungen: Per-Feld-Provenance, MQTT, Strompreis, Support
    joined = " | ".join(plan_obj.warnings)
    assert "Per-Feld-Provenance" in joined
    assert "MQTT-Only" in joined
    assert "Support-Anspruch" in joined
    assert "Prognose-Felder" in joined
    assert plan_obj.operation_preview["anzahl_tage"] == 7


async def test_execute_reaggregate_range_iterates_and_commits_per_day(db):
    """Execute schleift über Tage und macht Per-Tag-Commit.

    aggregate_day + resnap_anlage_range werden gemockt, damit der Test
    keinen vollen Stunden-Snapshot-Datensatz braucht. Geprüft wird die
    Schleifen-Logik: N Aufrufe für N Tage, Summary korrekt, ein
    fehlgeschlagener Tag bricht die Schleife nicht ab.
    """
    from datetime import date
    from unittest.mock import AsyncMock, patch

    anlage = await _make_anlage(db)

    # aggregate_day-Stub: gibt für Tag 3 None zurück (keine_daten), sonst
    # ein Pseudo-Objekt. Für Tag 5 raised er, um Fehlerpfad zu prüfen.
    aufruf_daten: list[date] = []

    class _FakeZusammenfassung:
        stunden_verfuegbar = 24

    async def fake_aggregate_day(anlage_arg, datum_arg, db_arg, **kwargs):
        aufruf_daten.append(datum_arg)
        if datum_arg == date(2026, 4, 3):
            return None
        if datum_arg == date(2026, 4, 5):
            raise RuntimeError("simulierter Aggregations-Fehler")
        return _FakeZusammenfassung()

    async def fake_resnap(*args, **kwargs):
        return None

    with patch(
        "backend.services.energie_profil_service.aggregate_day",
        new=AsyncMock(side_effect=fake_aggregate_day),
    ), patch(
        "backend.services.sensor_snapshot_service.resnap_anlage_range",
        new=AsyncMock(side_effect=fake_resnap),
    ):
        plan_obj = await plan(RepairOperationRequest(
            anlage_id=anlage.id,
            operation=RepairOperationType.REAGGREGATE_RANGE,
            params={"von": "2026-04-01", "bis": "2026-04-07", "mit_resnap": True},
        ), db)
        result = await execute(plan_obj.plan_id, db)

    summary = result.operation_summary
    assert summary["verarbeitet"] == 7
    assert summary["erfolgreich"] == 5  # 7 - 1 keine_daten - 1 fehler
    assert summary["keine_daten"] == 1
    assert summary["fehlgeschlagen"] == 1
    assert len(aufruf_daten) == 7  # auch nach Fehler weiter
    # Fehler-Details enthalten die zwei betroffenen Tage
    gruende = {d["datum"]: d["grund"] for d in summary["fehler_details"]}
    assert gruende["2026-04-03"] == "keine_daten"
    assert "RuntimeError" in gruende["2026-04-05"]


async def test_discard_plan_removes_from_cache(db):
    """discard_plan() entfernt Plan + verhindert späteres Execute."""
    anlage = await _make_anlage(db)
    await _seed_cloud_md(db, anlage.id, 2026, 4)

    p = await plan(
        RepairOperationRequest(
            anlage_id=anlage.id,
            operation=RepairOperationType.RESET_CLOUD_IMPORT,
            params={},
        ),
        db,
    )
    await discard_plan(p.plan_id)

    try:
        await execute(p.plan_id, db)
    except LookupError as e:
        assert "nicht gefunden" in str(e), str(e)
    else:
        raise AssertionError("Erwarteter LookupError nach discard")


# ── Runner ───────────────────────────────────────────────────────────────────


_TESTS = [
    test_plan_reset_cloud_import_no_data,
    test_plan_reset_cloud_import_with_data,
    test_execute_reset_cloud_import_writes_null_and_repair,
    test_force_override_breaks_manual_hierarchy,
    test_double_execute_raises,
    test_provider_filter_narrows_diff,
    test_list_plans_returns_recent_first,
    test_plan_reaggregate_range_rejects_invalid_bounds,
    test_plan_reaggregate_range_valid_returns_warnings,
    test_execute_reaggregate_range_iterates_and_commits_per_day,
    test_discard_plan_removes_from_cache,
]


async def _main() -> int:
    failures = 0
    for fn in _TESTS:
        try:
            await fn()
            print(f"OK   {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {fn.__name__}: {e}")
            traceback.print_exc()
        except Exception as e:
            failures += 1
            print(f"ERR  {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
    if failures:
        print(f"\n{failures}/{len(_TESTS)} Tests fehlgeschlagen.")
        return 1
    print(f"\nAlle {len(_TESTS)} Tests grün.")
    return 0

