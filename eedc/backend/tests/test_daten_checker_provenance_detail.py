"""
Akzeptanztest für die Detail-Zeile des Quellen-Konflikt-Checks
(`_check_provenance_conflicts`, Safi105 #301).

Hintergrund: Vor v3.35.x zeigte der Hinweis nur „1× in monatsdaten" — der
Anwender konnte nicht erkennen, *welches* Feld in *welchem* Zeitraum von zwei
Quellen beschrieben wurde. Die Detail-Zeile nennt jetzt Feld + Zeitraum +
beteiligte Quellen, damit der Treffer in Einstellungen → Daten auffindbar ist.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select as _select
from sqlalchemy.orm import selectinload

from backend.models import Anlage
from backend.models.investition import Investition
from backend.models.data_provenance_log import DataProvenanceLog
from backend.services.daten_checker import (
    CheckKategorie,
    CheckSeverity,
    DatenChecker,
)


async def _seed_anlage(db) -> int:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="DE")
    db.add(anlage)
    await db.flush()
    return anlage.id


async def _add_inv(db, anlage_id: int, bezeichnung: str) -> int:
    inv = Investition(
        anlage_id=anlage_id, typ="speicher", bezeichnung=bezeichnung,
    )
    db.add(inv)
    await db.flush()
    return inv.id


async def _log(db, *, table, pk_json, field, source) -> None:
    db.add(DataProvenanceLog(
        table_name=table, row_pk_json=pk_json, field_name=field,
        source=source, writer="test", written_at=datetime.now(),
        decision="applied", decision_reason="test",
    ))


async def _run_check(db, anlage_id: int):
    anlage = (await db.execute(
        _select(Anlage)
        .where(Anlage.id == anlage_id)
        .options(selectinload(Anlage.investitionen))
    )).scalar_one()
    checker = DatenChecker(db)
    return await checker._check_provenance_conflicts(anlage)


def _konflikt(ergebnisse):
    return next(
        e for e in ergebnisse
        if e.kategorie == CheckKategorie.PROVENANCE_CONFLICT.value
    )


async def test_kein_konflikt_meldet_ok(db):
    aid = await _seed_anlage(db)
    await db.commit()

    e = _konflikt(await _run_check(db, aid))
    assert e.schwere == CheckSeverity.OK.value


async def test_detail_nennt_feld_monat_und_quellen(db):
    """monatsdaten-Konflikt → Detail-Zeile mit Feld, Jahr-Monat und Quellen."""
    aid = await _seed_anlage(db)
    pk = f'{{"anlage_id": {aid}, "jahr": 2026, "monat": 4}}'
    await _log(db, table="monatsdaten", pk_json=pk,
               field="einspeisung_kwh", source="manual:form")
    await _log(db, table="monatsdaten", pk_json=pk,
               field="einspeisung_kwh", source="external:ha_statistics")
    await db.commit()

    e = _konflikt(await _run_check(db, aid))
    assert e.schwere == CheckSeverity.INFO.value
    assert "einspeisung_kwh" in e.details
    assert "2026-04" in e.details
    assert "manuell" in e.details
    assert "HA-Statistik" in e.details


async def test_detail_nennt_komponenten_name_bei_investition(db):
    """investition_monatsdaten-Konflikt → Komponenten-Bezeichnung statt Tabelle."""
    aid = await _seed_anlage(db)
    iid = await _add_inv(db, aid, "Hausspeicher")
    pk = f'{{"investition_id": {iid}, "jahr": 2026, "monat": 3}}'
    await _log(db, table="investition_monatsdaten", pk_json=pk,
               field="ladung_kwh", source="manual:form")
    await _log(db, table="investition_monatsdaten", pk_json=pk,
               field="ladung_kwh", source="external:cloud_import:fronius_solarweb")
    await db.commit()

    e = _konflikt(await _run_check(db, aid))
    assert "Hausspeicher" in e.details
    assert "2026-03" in e.details
    assert "Cloud-Import (Fronius)" in e.details


async def test_einzelne_quelle_kein_konflikt(db):
    """Nur eine Quelle pro Feld → kein Konflikt (HAVING n_sources >= 2)."""
    aid = await _seed_anlage(db)
    pk = f'{{"anlage_id": {aid}, "jahr": 2026, "monat": 4}}'
    await _log(db, table="monatsdaten", pk_json=pk,
               field="netzbezug_kwh", source="manual:form")
    await db.commit()

    e = _konflikt(await _run_check(db, aid))
    assert e.schwere == CheckSeverity.OK.value


async def test_alte_konflikte_ausserhalb_fenster_ignoriert(db):
    """Konflikt älter als `days` → nicht gemeldet."""
    aid = await _seed_anlage(db)
    pk = f'{{"anlage_id": {aid}, "jahr": 2025, "monat": 1}}'
    alt = datetime.now() - timedelta(days=60)
    db.add(DataProvenanceLog(
        table_name="monatsdaten", row_pk_json=pk, field_name="einspeisung_kwh",
        source="manual:form", writer="test", written_at=alt,
        decision="applied", decision_reason="test",
    ))
    db.add(DataProvenanceLog(
        table_name="monatsdaten", row_pk_json=pk, field_name="einspeisung_kwh",
        source="external:ha_statistics", writer="test", written_at=alt,
        decision="applied", decision_reason="test",
    ))
    await db.commit()

    e = _konflikt(await _run_check(db, aid))
    assert e.schwere == CheckSeverity.OK.value
