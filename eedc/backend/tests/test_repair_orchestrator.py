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

Schwesterdateien: test_repair_operationen_checker.py (die vier Operationen der Daten-Checker-Knöpfe, E3).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta

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
from backend.tests import factories


@pytest.fixture(autouse=True)
def _reset_repair_singleton():
    """Modul-Singleton vor jedem Test leeren — sonst leaken Plans aus dem
    Vorgänger-Test in `list_plans()`."""
    _reset_state_for_tests()


async def _make_anlage(session: AsyncSession) -> Anlage:
    a = await factories.anlage(session, standort_land="DE")
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


# ── N-793: je Lauf eine Zeile im Aktivitätsprotokoll ────────────────────────


async def _orchestrator_zeilen(db: AsyncSession) -> list:
    from backend.models.activity_log import ActivityLog
    zeilen = (await db.execute(select(ActivityLog).where(ActivityLog.kategorie == "repair"))).scalars().all()
    return [z for z in zeilen if "plan_id" in (z.details_json or {})]


async def test_execute_schreibt_genau_eine_protokollzeile(db):
    """W-12 (N-793): ein Execute ⇒ genau eine neue Zeile aus dem Orchestrator, in derselben Sitzung (N-532)."""
    anlage = await _make_anlage(db)
    await _seed_cloud_md(db, anlage.id, 2026, 4)
    assert await _orchestrator_zeilen(db) == []
    req = RepairOperationRequest(anlage_id=anlage.id, operation=RepairOperationType.RESET_CLOUD_IMPORT, params={})
    plan_obj = await plan(req, db)
    assert await _orchestrator_zeilen(db) == []              # die Vorschau schreibt nichts
    result = await execute(plan_obj.plan_id, db)

    zeilen = await _orchestrator_zeilen(db)
    assert len(zeilen) == 1
    z = zeilen[0]
    assert z.details_json["plan_id"] == str(plan_obj.plan_id)
    assert z.details_json["operation"] == "reset_cloud_import"
    assert z.details_json["actual_changes"] == result.actual_changes
    assert z.anlage_id == anlage.id and z.erfolg is True
    assert z.aktion == "Reparatur: Cloud-Import-Werte zurücksetzen"  # E5: ohne Bereich endet die Aktion nicht auf «— —»
    assert z.details.startswith("Änderungen: ")


async def test_protokollzeile_nennt_den_bereich_und_den_anwender_satz():
    """Bereich aus den Parametern (Datum ISO), Anwender-Satz der Operation vor den Zählern."""
    from types import SimpleNamespace

    from backend.services import repair_protokoll as rp

    aufrufe: list[dict] = []

    class _Sitzung:
        def add(self, eintrag):
            aufrufe.append({"aktion": eintrag.aktion, "details": eintrag.details, "json": eintrag.details_json})

    plan_obj = SimpleNamespace(
        plan_id=uuid.uuid4(), anlage_id=3, operation=RepairOperationType.REAGGREGATE_RANGE,
        operation_params={"von": date(2026, 1, 3), "bis": "2026-01-09", "mit_resnap": True},
    )
    await rp.protokolliere_lauf(plan_obj, {}, {"erfolgreich": 7}, _Sitzung())
    plan_obj.operation, plan_obj.operation_params = RepairOperationType.REAGGREGATE_DAY, {"datum": "2026-11-02"}
    await rp.protokolliere_lauf(plan_obj, {"quelle_text": "Zählerwerte aus Home Assistant."}, {}, _Sitzung())

    assert aufrufe[0]["aktion"] == "Reparatur: Mehrere Tage neu aggregieren — 2026-01-03 – 2026-01-09"
    assert aufrufe[0]["json"]["params"]["von"] == "2026-01-03"
    assert aufrufe[0]["details"] == "Änderungen: erfolgreich 7"
    assert aufrufe[1]["aktion"] == "Reparatur: Tag neu aggregieren — 2026-11-02"
    assert aufrufe[1]["details"] == "Zählerwerte aus Home Assistant."


async def test_wrapper_route_und_werkbank_route_protokollieren(db, monkeypatch):
    """Routen-Beleg (N-793): «Kraftstoffpreise nachpflegen» über die Wrapper-Route (`_run_via_orchestrator`, wie die
    Knöpfe im Daten-Checker) und ein Werkbank-Lauf über `POST /api/repair/execute/{plan_id}` — je eine Zeile."""
    from backend.api.routes.energie_profil.repair import kraftstoffpreis_backfill_tages
    from backend.api.routes.repair import execute_plan
    from backend.services import kraftstoff_preis_service as kps

    async def _ohne_netz(anlage_id, land, db):
        return {"aktualisiert": 0}

    monkeypatch.setattr(kps, "backfill_kraftstoffpreise", _ohne_netz)
    anlage = await _make_anlage(db)
    await kraftstoffpreis_backfill_tages(anlage.id, db=db)
    zeilen = await _orchestrator_zeilen(db)
    assert [(z.aktion, z.anlage_id) for z in zeilen] == [("Reparatur: Kraftstoffpreise nachpflegen", anlage.id)]

    await _seed_cloud_md(db, anlage.id, 2026, 4)
    plan_obj = await plan(RepairOperationRequest(
        anlage_id=anlage.id, operation=RepairOperationType.RESET_CLOUD_IMPORT, params={}), db)
    await execute_plan(plan_obj.plan_id, db=db)
    zeilen = await _orchestrator_zeilen(db)
    assert len(zeilen) == 2 and str(plan_obj.plan_id) in {z.details_json["plan_id"] for z in zeilen}


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
        # E6.D D6: ein Satz für den Vorschau-Kasten des Daten-Checkers, ohne Mechanik-Wort (W-4).
        assert "Der laufende Tag lässt sich erst morgen neu aufbauen" in str(e), str(e)
        from backend.services.daten_checker.handgriffe import MECHANIK_WOERTER
        assert not [w for w in MECHANIK_WOERTER if w in str(e).lower()], str(e)
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
    # auch nach Fehler weiter: jeder Tag läuft. N-791: ein Tag ohne Ergebnis (4/3) läuft zusätzlich durch Stufe 3
    # (Zähler aus HA ohne Leistungskurve), die nicht mehr an der Live-Zuordnung hängt — daher die Tage, nicht die Aufrufe.
    assert sorted(set(aufruf_daten)) == [date(2026, 4, d) for d in range(1, 8)]
    assert aufruf_daten.count(date(2026, 4, 3)) == 2
    # Fehler-Details enthalten die zwei betroffenen Tage. Der Grund nennt jetzt
    # den ZUSTAND, nicht pauschal „keine_daten": liefert der reguläre Weg nichts,
    # versucht die Reparatur es über HA-LTS — und diese Test-Anlage hat gar keine
    # Live-Zuordnung, also kann auch der Rückfall nichts holen (#89667/72).
    gruende = {d["datum"]: d["grund"] for d in summary["fehler_details"]}
    assert gruende["2026-04-03"] == "keine_live_zuordnung"
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


# ── Die Vorschau spricht nur für das, was sie gemessen hat (N-415) ───────────
#
# Melder Knallfrosch (Forum simon42 T89667 #302/#304): Nach dem v4.0.39-Fehler
# fehlten ihm Stundenwerte. Die Vorschau meldete „0 boundaries_changed ·
# 0 slots_changed · 0 counter_fields_changed" und dazu „Reaggregate würde nichts
# inhaltlich verändern (nur Provenance-Stempel)" — er führte trotzdem aus, und
# der Tag war repariert.
#
# Am Code gemessen: Die Vorschau vergleicht die **Zählerstände** (Snapshots)
# gegen die HA-Statistik. Der Lauf baut darüber hinaus das **Tages-Aggregat**
# neu auf (`_reparatur_aggregat`) — genau das, was bei ihm fehlte. Auf das
# Aggregat hat die Vorschau nie geschaut und trotzdem für es gesprochen.

async def _plan_tag(db, anlage_id: int, datum_iso: str):
    """Einen REAGGREGATE_DAY-Plan bauen und zurückgeben."""
    return await plan(
        RepairOperationRequest(
            anlage_id=anlage_id,
            operation=RepairOperationType.REAGGREGATE_DAY,
            params={"datum": datum_iso, "mit_resnap": False},
        ),
        db,
    )


async def test_die_vorschau_behauptet_nicht_mehr_dass_nichts_passiert(db):
    """⛔ Der Satz, der einen Anwender von seiner Reparatur abgehalten hätte.

    Ohne Snapshots ist die Zählerstands-Seite trivial unverändert — genau die
    Lage, in der die alte Fassung „Reaggregate würde nichts inhaltlich
    verändern" schrieb.
    """
    a = await _make_anlage(db)
    p = await _plan_tag(db, a.id, "2026-09-05")

    text = " ".join(p.warnings)
    assert "nichts inhaltlich verändern" not in text, (
        "Die Vorschau spricht wieder für die ganze Operation, obwohl sie nur "
        "die Zählerstände gemessen hat")
    assert "Provenance-Stempel" not in text


async def test_die_vorschau_nennt_ihren_gegenstand_und_ihre_grenze(db):
    """Sie sagt, WAS geprüft wurde — und dass das Aggregat davon nicht erfasst ist."""
    a = await _make_anlage(db)
    p = await _plan_tag(db, a.id, "2026-09-05")

    text = " ".join(p.warnings)
    assert "Zählerstände" in text, f"Gegenstand nicht genannt: {p.warnings}"
    assert "Tageszusammenfassung" in text or "Stundenwerte" in text, (
        f"Die Grenze der Vorschau ist nicht benannt: {p.warnings}")


async def test_fehlende_stunden_werden_beziffert(db):
    """Der Melderfall: unvollständiges Tages-Aggregat bei sauberen Zählerständen.

    Neun von 24 Stunden gespeichert ⇒ die Vorschau nennt die Zahl und sagt,
    dass der Lauf die fehlenden nachträgt. Das ist eine **gezählte** Aussage,
    keine Vorhersage — sie kann nicht danebenliegen.
    """
    a = await _make_anlage(db)
    tag = date(2026, 9, 5)
    for stunde in range(9):
        db.add(TagesEnergieProfil(anlage_id=a.id, datum=tag, stunde=stunde, pv_kw=1.0))
    await db.commit()

    p = await _plan_tag(db, a.id, tag.isoformat())

    text = " ".join(p.warnings)
    assert "9 von 24" in text, f"Die Stundenzahl fehlt: {p.warnings}"
    assert p.operation_preview.get("aggregat_stunden_vorhanden") == 9


async def test_ein_vollstaendiger_tag_wird_nicht_angemahnt(db):
    """Gegenprobe — sonst stünde der Hinweis an jedem Tag und wäre wertlos.

    Ohne sie wäre die Probe darüber auch dann grün, wenn jemand den Hinweis
    unbedingt ausgibt.
    """
    a = await _make_anlage(db)
    tag = date(2026, 9, 4)
    for stunde in range(24):
        db.add(TagesEnergieProfil(anlage_id=a.id, datum=tag, stunde=stunde, pv_kw=1.0))
    await db.commit()

    p = await _plan_tag(db, a.id, tag.isoformat())

    text = " ".join(p.warnings)
    assert "von 24 Stunden gespeichert" not in text, (
        f"Ein vollständiger Tag wird angemahnt: {p.warnings}")
    assert p.operation_preview.get("aggregat_stunden_vorhanden") == 24


async def test_die_stundenzahl_zaehlt_nur_den_eigenen_tag(db):
    """Ein Nachbartag darf die Zahl nicht auffüllen — sonst meldet sie 24,
    während der geprüfte Tag leer ist."""
    a = await _make_anlage(db)
    for stunde in range(24):
        db.add(TagesEnergieProfil(anlage_id=a.id, datum=date(2026, 9, 4),
                                  stunde=stunde, pv_kw=1.0))
    await db.commit()

    p = await _plan_tag(db, a.id, "2026-09-05")
    assert p.operation_preview.get("aggregat_stunden_vorhanden") == 0


async def test_die_schluessel_der_vorschau_sind_der_vertrag_mit_der_anzeige(db):
    """Die Werkbank beschriftet diese Schlüssel — sie dürfen nicht still wandern.

    Bis zum 06.09.2026 rendert die Werkbank die **rohen** Schlüssel („0
    boundaries_changed"); seither übersetzt sie `REPARATUR_AENDERUNG_LABELS`.
    Eine Umbenennung hier ließe die Anzeige stillschweigend wieder englisch
    werden — deshalb steht der Satz der Schlüssel hier fest.
    Client-Hälfte: `src/test/check-reparatur-labels.test.ts`.
    """
    a = await _make_anlage(db)
    p = await _plan_tag(db, a.id, "2026-09-05")

    assert set(p.estimated_changes) == {
        "boundaries_changed", "slots_changed", "counter_fields_changed"
    }, (f"Die Schlüssel haben sich geändert: {sorted(p.estimated_changes)} — "
        "die Label-Map im Client zieht nicht von allein nach")


def test_e5_actual_changes_nur_mengen():
    """E5 (Nachmessung E3 ⚑5): Kennungen, Kalenderangaben und Wahrheitswerte der Operations-Antwort sind keine Mengen —
    sie stehen weder in der Ergebnis- noch in der Protokollzeile."""
    from backend.services.repair_protokoll import mengen

    antwort = {"anlage_id": 1, "investition_id": 7, "monatsdaten_id": 3, "jahr": 2026, "monat": 5, "erfolg": True,
               "gefuellt": 2, "geloescht": 0, "satz": "x", "monate": ["05/2026"]}
    assert mengen(antwort) == {"gefuellt": 2, "geloescht": 0}


async def test_e5_execute_nichts_zu_tun_ist_409_ohne_zeile(db, monkeypatch):
    """E5: ein Plan «nichts zu tun» ⇒ Route 409 mit dem Satz, kein Lauf, keine Protokollzeile."""
    from fastapi import HTTPException

    from backend.api.routes.repair import execute_plan
    from backend.services import repair_orchestrator as orch

    anlage = await _make_anlage(db)
    req = RepairOperationRequest(anlage_id=anlage.id, operation=RepairOperationType.RESET_CLOUD_IMPORT, params={})
    plan_obj = await plan(req, db)
    plan_obj.operation_preview["nichts_zu_tun"] = "Es gibt nichts zurückzusetzen."
    with pytest.raises(HTTPException) as e:
        await execute_plan(plan_obj.plan_id, db=db)
    assert e.value.status_code == 409 and "Es gibt nichts zurückzusetzen." in e.value.detail
    assert await _orchestrator_zeilen(db) == []
    assert plan_obj.plan_id not in orch._results
