"""
Unit-Tests für services/provenance_migrate.py (Etappe 3d Päckchen 3).

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

import sys
import traceback

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import (  # noqa: F401
    Anlage,
    Investition,
    InvestitionMonatsdaten,
    Monatsdaten,
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.services.provenance import write_with_provenance
from backend.services.provenance_migrate import (
    migrate_3d_p3_initial_provenance_legacy_unknown,
)


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


async def test_empty_db_returns_zero_counts(db):
    """Frische DB: kein Crash, alle counts = 0."""
    counts = await migrate_3d_p3_initial_provenance_legacy_unknown(db)
    assert counts == {
        "monatsdaten": 0,
        "investition_monatsdaten": 0,
        "tages_zusammenfassung": 0,
        "tages_energie_profil": 0,
    }


async def test_legacy_row_gets_provenance_top_level(db):
    """Pre-3d Monatsdaten-Row ohne source_provenance → markiert mit legacy:unknown."""
    anlage = await _make_anlage(db)
    md = Monatsdaten(
        anlage_id=anlage.id, jahr=2024, monat=3,
        einspeisung_kwh=120.5, netzbezug_kwh=42.0,
        pv_erzeugung_kwh=300.0,
    )
    # Bestandsdaten heißt: source_provenance = leeres dict (Default).
    db.add(md)
    await db.commit()

    counts = await migrate_3d_p3_initial_provenance_legacy_unknown(db)
    assert counts["monatsdaten"] == 1, counts

    await db.refresh(md)
    prov = md.source_provenance
    # Drei beschriebene Top-Level-Felder bekommen alle einen legacy-Eintrag
    for field in ("einspeisung_kwh", "netzbezug_kwh", "pv_erzeugung_kwh"):
        assert field in prov, f"{field} fehlt in {list(prov.keys())}"
        assert prov[field]["source"] == "legacy:unknown"
        assert prov[field]["writer"] == "initial_migration"
    # Identifier dürfen NICHT markiert sein
    for skip in ("id", "anlage_id", "jahr", "monat", "source_provenance", "source_hash"):
        assert skip not in prov


async def test_legacy_investition_monatsdaten_json_subkeys(db):
    """Pre-3d InvestitionMonatsdaten → verbrauch_daten-Sub-Keys werden markiert, NICHT die JSON-Spalte als Top-Level."""
    anlage = await _make_anlage(db)
    inv = await _make_inv(db, anlage.id)
    imd = InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2024, monat=4,
        verbrauch_daten={"km_gefahren": 1200, "ladung_kwh": 130.5},
    )
    db.add(imd)
    await db.commit()

    await migrate_3d_p3_initial_provenance_legacy_unknown(db)
    await db.refresh(imd)
    prov = imd.source_provenance

    # Sub-Keys gemarkiert
    assert "verbrauch_daten.km_gefahren" in prov
    assert "verbrauch_daten.ladung_kwh" in prov
    assert prov["verbrauch_daten.km_gefahren"]["source"] == "legacy:unknown"

    # Top-Level-Eintrag „verbrauch_daten" darf NICHT existieren — sonst
    # würde Per-Sub-Key-Hierarchie (P2) blockiert.
    assert "verbrauch_daten" not in prov


async def test_existing_provenance_is_preserved(db):
    """Row mit existierender Provenance → wird NICHT überschrieben."""
    anlage = await _make_anlage(db)
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
    db.add(md)
    await db.commit()

    counts = await migrate_3d_p3_initial_provenance_legacy_unknown(db)
    assert counts["monatsdaten"] == 0, "Row mit Provenance darf nicht migriert werden"

    await db.refresh(md)
    # Bestehender Eintrag unverändert
    assert md.source_provenance["einspeisung_kwh"]["source"] == "manual:form"
    # NICHT zusätzlich legacy:unknown auf netzbezug_kwh — komplett geskipt.
    assert "netzbezug_kwh" not in md.source_provenance


async def test_idempotent_double_run(db):
    """Re-Run der Migration auf schon markierten Rows ist No-Op."""
    anlage = await _make_anlage(db)
    md = Monatsdaten(
        anlage_id=anlage.id, jahr=2024, monat=6,
        einspeisung_kwh=80.0, netzbezug_kwh=15.0,
    )
    db.add(md)
    await db.commit()

    first = await migrate_3d_p3_initial_provenance_legacy_unknown(db)
    assert first["monatsdaten"] == 1
    second = await migrate_3d_p3_initial_provenance_legacy_unknown(db)
    assert second["monatsdaten"] == 0, "zweiter Lauf darf nichts mehr markieren"


async def test_legacy_unknown_loses_to_any_new_writer(db):
    """Hierarchie-Pflicht: nach Legacy-Markierung gewinnt jeder neue Schreiber.

    Das ist der Sinn der Migration: ohne Provenance würde der neue Schreiber
    via `existing=None` stumm gewinnen. Mit `legacy:unknown` als niedrigster
    Stufe bleibt das Verhalten gleich, aber der Audit-Log dokumentiert den
    Pfad.
    """
    anlage = await _make_anlage(db)
    md = Monatsdaten(
        anlage_id=anlage.id, jahr=2024, monat=7,
        einspeisung_kwh=50.0,
    )
    db.add(md)
    await db.commit()

    await migrate_3d_p3_initial_provenance_legacy_unknown(db)
    await db.refresh(md)
    assert md.source_provenance["einspeisung_kwh"]["source"] == "legacy:unknown"

    # Manual:form schreibt drauf
    result = await write_with_provenance(
        db, md, "einspeisung_kwh", 99.9,
        source="manual:form", writer="user@local",
    )
    assert result.decision == "applied", result
    await db.commit()
    await db.refresh(md)
    assert md.source_provenance["einspeisung_kwh"]["source"] == "manual:form"

    # Fallback gewinnt auch (ist niedriger als manual:form, aber höher als legacy)
    anlage2 = await _make_anlage(db)
    md2 = Monatsdaten(
        anlage_id=anlage2.id, jahr=2024, monat=8,
        einspeisung_kwh=40.0,
    )
    db.add(md2)
    await db.commit()
    await migrate_3d_p3_initial_provenance_legacy_unknown(db)

    result2 = await write_with_provenance(
        db, md2, "einspeisung_kwh", 41.0,
        source="fallback:sensor_snapshot", writer="snapshot",
    )
    assert result2.decision == "applied", "fallback:* schlägt legacy:unknown"
    await db.commit()


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

