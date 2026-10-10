"""N-656 — Snapshot-Job: ein DB-Fehler bei EINER Anlage nimmt den anderen ihre Stunde nicht mehr.

Alle Anlagen laufen in EINER Sitzung; ``snapshot_anlage`` flusht nur, committet wird am Ende von ``get_session``.
Bis 10.10.2026 stand um den Aufruf ein ``try`` ohne Rollback: scheiterte das Speichern einer Anlage (z. B. „database
is locked"), blieb die Sitzung im Zustand „Rollback ausstehend" — jede folgende Anlage scheiterte, der Commit auch, und
die Stunde fehlte für ALLE Anlagen, auch für die davor geschriebenen (Analyse 10.10., Minimalfall). Mit HA heilt die
Lesekaskade das aus der Statistik; MQTT-Stunden sind Live-Werte und kommen nicht wieder (Entscheid Gernot 10.10.2026:
Rollback dort, wo die Daten nicht wiederherstellbar sind). Jetzt: ein SAVEPOINT je Anlage.

Gehalten wird an drei Anlagen, die mittlere wirft beim Flush eine echte ``IntegrityError`` (Unique-Bedingung von
``sensor_snapshots``):

1. Stundenlauf ``sensor_snapshot_job``: die erste und die dritte Anlage haben ihren Snapshot; der Fehler steht im
   Aktivitätsprotokoll (Kategorie ``scheduler``, ``erfolg`` falsch, Anlage 2).
2. Startlauf ``sensor_snapshot_startup_recovery`` (der einzige Nachtrag der MQTT-Stunden einer Neustart-Lücke): die
   erste und die dritte Anlage haben alle sieben nachgeholten Stunden.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.models.activity_log import ActivityLog
from backend.models.anlage import Anlage
from backend.models.sensor_snapshot import SensorSnapshot
from backend.tests import pv_achse_matrix as mx


@pytest.fixture
async def drei_anlagen():
    """``(sitzungen, [id1, id2, id3])`` — Datei-DB (SAVEPOINT wie im Produkt), drei Anlagen ohne Zuordnung."""
    verz = tempfile.mkdtemp(prefix="eedc-n656-")
    engine, db = await mx._neue_db(f"{verz}/x.db")
    await db.close()
    macher = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def sitzungen():
        # dieselbe Form wie `core.database.get_session`: Commit am Ende, Rollback bei Fehler
        async with macher() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    async with sitzungen() as s:
        anlagen = [Anlage(anlagenname=f"A{i}", leistung_kwp=5.0) for i in (1, 2, 3)]
        s.add_all(anlagen)
        await s.flush()
        ids = [a.id for a in anlagen]
    try:
        yield sitzungen, ids
    finally:
        await engine.dispose()
        shutil.rmtree(verz, ignore_errors=True)


def _falscher_schreiber(kaputt_id: int):
    """Ersatz für ``snapshot_anlage``: schreibt einen Zählerstand und flusht; bei ``kaputt_id`` zweimal denselben
    Schlüssel — der Flush wirft eine echte ``IntegrityError`` in der gemeinsamen Sitzung."""
    async def schreibe(db, anlage, zeitpunkt=None, **_):
        db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key="basis:einspeisung", zeitpunkt=zeitpunkt,
                              wert_kwh=100.0, quelle="mqtt_inbound"))
        if anlage.id == kaputt_id:
            db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key="basis:einspeisung", zeitpunkt=zeitpunkt,
                                  wert_kwh=100.0, quelle="mqtt_inbound"))
        await db.flush()
        return 1
    return schreibe


async def _snapshots_je_anlage(sitzungen) -> dict[int, int]:
    async with sitzungen() as s:
        rows = (await s.execute(
            select(SensorSnapshot.anlage_id, func.count()).group_by(SensorSnapshot.anlage_id)
        )).all()
    return {aid: n for aid, n in rows}


async def test_stundenlauf_zweite_anlage_wirft_die_anderen_behalten_ihren_snapshot(drei_anlagen, monkeypatch):
    import backend.core.database as dbmod
    import backend.services.sensor_snapshot_service as sss
    from backend.services import scheduler
    from backend.services.kanal import nachfuellen as nf

    sitzungen, (a1, a2, a3) = drei_anlagen
    monkeypatch.setattr(dbmod, "get_session", sitzungen)
    monkeypatch.setattr(sss, "snapshot_anlage", _falscher_schreiber(a2))
    monkeypatch.setattr(nf, "nachfuellen_anstossen", lambda: None)

    await scheduler.sensor_snapshot_job()

    assert await _snapshots_je_anlage(sitzungen) == {a1: 1, a3: 1}
    async with sitzungen() as s:
        fehler = (await s.execute(
            select(ActivityLog.anlage_id).where(
                ActivityLog.kategorie == "scheduler", ActivityLog.erfolg.is_(False),
            )
        )).scalars().all()
    assert a2 in fehler


async def test_startlauf_zweite_anlage_wirft_die_anderen_behalten_ihre_stunden(drei_anlagen, monkeypatch):
    import backend.core.database as dbmod
    import backend.services.energie_profil_service as eps
    import backend.services.sensor_snapshot_service as sss
    from backend.services import scheduler

    async def null(*_a, **_k):
        return 0

    sitzungen, (a1, a2, a3) = drei_anlagen
    monkeypatch.setattr(dbmod, "get_session", sitzungen)
    monkeypatch.setattr(sss, "snapshot_anlage", _falscher_schreiber(a2))
    monkeypatch.setattr(sss, "live_snapshot_if_missing", null)
    monkeypatch.setattr(sss, "snapshot_anlage_5min", null)
    monkeypatch.setattr(eps, "aggregate_today_all", null)

    await scheduler.sensor_snapshot_startup_recovery()

    assert await _snapshots_je_anlage(sitzungen) == {a1: 7, a3: 7}
