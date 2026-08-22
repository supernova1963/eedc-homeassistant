"""
Unit-Tests für services/import_writer.py (Etappe 3d Päckchen 2).

Akzeptanz-Tests aus Konzept Sektion 8 Päckchen 2:
- INSERT-Pfad (keine existing)
- UPDATE mit Full-Payload-No-Op (gleicher Hash)
- UPDATE mit ueberschreiben=False (Status-quo-Skip)
- UPDATE mit ueberschreiben=True (Hierarchie blockiert manuelle Werte)
- UPDATE mit ueberschreiben=True + gleiche Source-Klasse (Last-Writer-Wins)
- payload_hash canonical (Reihenfolge-unabhängig)
"""

from __future__ import annotations

import traceback

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
from backend.services.import_writer import (
    payload_hash,
    upsert_investition_monatsdaten_with_provenance,
)
from backend.services.provenance import write_json_subkey_with_provenance


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


async def test_insert_path_initial_write(db):
    """Frische Investition + Aufruf → INSERT, alle Sub-Keys applied."""
    inv = await _make_inv(db)

    result = await upsert_investition_monatsdaten_with_provenance(
        db,
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 1200.0, "ladung_kwh": 130.0},
        source="manual:csv_import",
        writer="user@example.com",
    )
    await db.commit()

    assert result.inserted is True
    assert result.no_op_full_payload is False
    assert result.applied_count == 2
    assert result.rejected_count == 0

    imd = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == inv.id
        )
    )).scalar_one()
    assert imd.verbrauch_daten == {"km_gefahren": 1200.0, "ladung_kwh": 130.0}
    assert imd.source_hash is not None
    assert imd.source_hash == payload_hash({"km_gefahren": 1200.0, "ladung_kwh": 130.0})
    # 2 applied audit entries (pro Sub-Key)
    assert (await _audit_decisions(db)) == ["applied", "applied"]


async def test_full_payload_no_op_emits_single_audit(db):
    """Identischer Payload-Hash → no_op_full_payload + EIN Audit-Eintrag."""
    inv = await _make_inv(db)

    await upsert_investition_monatsdaten_with_provenance(
        db,
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 1200.0, "ladung_kwh": 130.0},
        source="external:cloud_import:fronius_solarweb",
        writer="cloud_account_42",
    )
    await db.commit()

    # Re-Import mit IDENTISCHEM Payload (auch andere Reihenfolge zählt als gleich)
    result = await upsert_investition_monatsdaten_with_provenance(
        db,
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={"ladung_kwh": 130.0, "km_gefahren": 1200.0},
        source="external:cloud_import:fronius_solarweb",
        writer="cloud_account_42",
        ueberschreiben=True,
    )
    await db.commit()

    assert result.inserted is False
    assert result.no_op_full_payload is True
    assert result.applied_count == 0  # keine Sub-Keys durchgegangen
    # Audit: 2 applied (Initial-Insert) + 1 no_op_same_value (Sentinel)
    assert (await _audit_decisions(db)) == [
        "applied", "applied", "no_op_same_value",
    ]


async def test_update_ueberschreiben_false_skips_existing_subkeys(db):
    """ueberschreiben=False: bestehende Sub-Keys bleiben unangetastet,
    nur fehlende werden ergänzt — Status-quo-Verhalten."""
    inv = await _make_inv(db)

    await upsert_investition_monatsdaten_with_provenance(
        db, investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 1200.0},
        source="manual:csv_import", writer="initial",
    )
    # Zweiter Import: km_gefahren existiert schon → skipped, ladung_kwh neu → applied
    result = await upsert_investition_monatsdaten_with_provenance(
        db, investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 9999.0, "ladung_kwh": 130.0},
        source="manual:csv_import", writer="follow_up",
        ueberschreiben=False,
    )
    await db.commit()

    assert result.skipped_existing == ["km_gefahren"]
    assert result.applied_count == 1
    # km_gefahren = 1200 (unverändert), ladung_kwh = 130 (neu)
    imd = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == inv.id
        )
    )).scalar_one()
    assert imd.verbrauch_daten == {"km_gefahren": 1200.0, "ladung_kwh": 130.0}


async def test_update_ueberschreiben_true_ersetzt_auch_manuelle_subkeys(db):
    """ueberschreiben=True ersetzt auch manuell gepflegte Sub-Keys (12.08.).

    ⚠ **Dieser Test stand bis zum 12.08. auf dem Kopf**
    (`..._blocks_manual_per_subkey`, Zusicherung `rejected_count == 1`) und galt
    als „Akzeptanz-Test für P2". Die Hierarchie schützte die Handarbeit auch
    dann, wenn der Anwender ausdrücklich „Bestehende Monate überschreiben"
    angekreuzt hatte — eedc tat also etwas anderes als angeordnet und meldete
    es hinterher als „geschützt". Dass ein CSV-Import (`manual:csv_import`)
    beim selben Klick durchkam und ein Cloud-Import nicht, war zusätzlich
    inkonsistent: derselbe Anwender, dieselbe Absicht, zwei Ergebnisse.

    **Was den Schutz ersetzt:** der Wizard fragt vorher `zaehle_manuelle_werte`
    und nennt die Zahl, bevor der Haken wirkt. Ohne Haken gewinnt Handarbeit
    unverändert unbedingt — FrodoVDRs Anliegen (#251) bleibt gewahrt, siehe
    `test_update_ohne_haken_schuetzt_manuelle_werte_weiterhin`.
    """
    inv = await _make_inv(db)

    # Schritt 1: Form-Schreiber pflegt verbrauch_daten manuell — geht NICHT
    # über den Wrapper, sondern direkt über write_json_subkey, wie es der
    # Form-Pfad in P3 tun wird (Stand-in-Setup für den Test).
    imd_seed = InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={}, source_provenance={}, source_hash=None,
    )
    db.add(imd_seed)
    await db.flush()
    await write_json_subkey_with_provenance(
        db, imd_seed, "verbrauch_daten", "km_gefahren", 1200.0,
        source="manual:form", writer="alice@example.com",
    )
    await db.commit()

    # Schritt 2: Cloud-Import bringt km_gefahren UND ladung_kwh
    result = await upsert_investition_monatsdaten_with_provenance(
        db,
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 1500.0, "ladung_kwh": 130.0},
        source="external:cloud_import:fronius_solarweb",
        writer="cloud_account_42",
        ueberschreiben=True,
    )
    await db.commit()

    assert result.applied_count == 2
    assert result.rejected_count == 0
    # Wert-Check: der angeordnete Import gewinnt auf BEIDEN Sub-Keys.
    imd = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == inv.id
        )
    )).scalar_one()
    assert imd.verbrauch_daten == {"km_gefahren": 1500.0, "ladung_kwh": 130.0}
    # ⚑ Und die Herkunft bleibt EHRLICH: der Wert kommt aus dem Import, nicht
    # aus einer Reparatur. Stünde hier `repair`, prallte der nächste reguläre
    # Import an Stufe 0 ab — die Falle wäre nur verschoben.
    for sub_key in ("km_gefahren", "ladung_kwh"):
        assert imd.source_provenance[f"verbrauch_daten.{sub_key}"]["source"] == \
            "external:cloud_import:fronius_solarweb", sub_key


async def test_update_ohne_haken_schuetzt_manuelle_werte_weiterhin(db):
    """Die Gegenprobe zu FrodoVDR #251: OHNE Haken bleibt Handarbeit unangetastet.

    Fiele diese Zusicherung, hätte der 12.08.-Umbau die Hierarchie nicht
    präzisiert, sondern abgeschafft.
    """
    inv = await _make_inv(db)
    imd_seed = InvestitionMonatsdaten(
        investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={}, source_provenance={}, source_hash=None,
    )
    db.add(imd_seed)
    await db.flush()
    await write_json_subkey_with_provenance(
        db, imd_seed, "verbrauch_daten", "km_gefahren", 1200.0,
        source="manual:form", writer="alice@example.com",
    )
    await db.commit()

    await upsert_investition_monatsdaten_with_provenance(
        db, investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 1500.0, "ladung_kwh": 130.0},
        source="external:cloud_import:fronius_solarweb",
        writer="cloud_account_42",
        ueberschreiben=False,
    )
    await db.commit()

    imd = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == inv.id
        )
    )).scalar_one()
    assert imd.verbrauch_daten["km_gefahren"] == 1200.0, "Handarbeit gefallen"
    assert imd.source_provenance["verbrauch_daten.km_gefahren"]["source"] == "manual:form"


async def test_update_ueberschreiben_true_same_class_last_writer_wins(db):
    """ueberschreiben=True bei zwei Source-Labels gleicher Priorität (z.B.
    zwei Cloud-Provider): Last-Writer-Wins, kein rejected."""
    inv = await _make_inv(db)

    await upsert_investition_monatsdaten_with_provenance(
        db, investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 1200.0},
        source="external:cloud_import:fronius_solarweb",
        writer="account_1",
    )
    result = await upsert_investition_monatsdaten_with_provenance(
        db, investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={"km_gefahren": 1500.0},
        source="external:cloud_import:solaredge",  # andere Provider, gleiche Klasse
        writer="account_2",
        ueberschreiben=True,
    )
    await db.commit()

    assert result.applied_count == 1
    assert result.rejected_count == 0
    imd = (await db.execute(
        select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id == inv.id
        )
    )).scalar_one()
    assert imd.verbrauch_daten["km_gefahren"] == 1500.0
    assert imd.source_provenance["verbrauch_daten.km_gefahren"]["source"] == \
        "external:cloud_import:solaredge"


async def test_empty_payload_returns_no_op_no_db_writes(db):
    """Leerer Payload → kein DB-Write, kein Audit-Eintrag."""
    inv = await _make_inv(db)

    result = await upsert_investition_monatsdaten_with_provenance(
        db, investition_id=inv.id, jahr=2026, monat=4,
        verbrauch_daten={},
        source="manual:csv_import", writer="user",
    )
    await db.commit()

    assert result.inserted is False
    assert result.applied_count == 0
    # Keine InvestitionMonatsdaten-Row angelegt
    rows = (await db.execute(select(InvestitionMonatsdaten))).scalars().all()
    assert rows == []
    assert (await _audit_decisions(db)) == []


# ─────────────────────────────── Runner ──────────────────────────────────


_SYNC_TESTS = [test_payload_hash_is_canonical]
