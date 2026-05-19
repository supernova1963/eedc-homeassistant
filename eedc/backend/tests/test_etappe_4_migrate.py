"""
Akzeptanztest für Etappe-4-Migration (v3.31.0):
`vollbackfill_durchgefuehrt` wird für HA-Integration-Anlagen mit Daten
zurückgesetzt, andere bleiben unverändert.

Testet:
  1. Anlage mit sensor_mapping + TZ-Daten → Flag wird False
  2. Anlage ohne sensor_mapping → Flag bleibt unverändert
  3. Anlage mit sensor_mapping, aber ohne TZ-Daten → Flag bleibt unverändert
  4. HA-LTS nicht verfügbar → keine Anlage wird verändert
  5. Idempotenz: zweimal Lauf ist OK (keine Side-Effects bei wiederholter
     Ausführung mit denselben Daten)
"""

from __future__ import annotations

import traceback
from datetime import date
from unittest.mock import patch, MagicMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Anlage
from backend.models.tages_energie_profil import TagesZusammenfassung

from backend.services.etappe_4_migrate import migrate_etappe_4_reset_vollbackfill


async def _seed_anlage(
    db: AsyncSession,
    name: str,
    sensor_mapping: dict | None,
    vollbackfill: bool,
    mit_tz_daten: bool = False,
) -> int:
    anlage = Anlage(
        anlagenname=name,
        leistung_kwp=10.0,
        sensor_mapping=sensor_mapping,
        vollbackfill_durchgefuehrt=vollbackfill,
    )
    db.add(anlage)
    await db.flush()
    if mit_tz_daten:
        db.add(TagesZusammenfassung(
            anlage_id=anlage.id, datum=date(2026, 5, 15),
            komponenten_kwh={"pv_3": 67.0},
        ))
    await db.commit()
    return anlage.id


def _mock_ha_svc(available: bool) -> MagicMock:
    svc = MagicMock()
    svc.is_available = available
    return svc


async def test_ha_anlage_mit_daten_wird_zurueckgesetzt(db):
    """Anlage mit HA-Mapping + Aggregat-Daten → Flag = False."""
    anlage_id = await _seed_anlage(
        db, "HA-Anlage",
        sensor_mapping={"basis": {"einspeisung": {"sensor_id": "sensor.x"}}},
        vollbackfill=True, mit_tz_daten=True,
    )
    with patch(
        "backend.services.etappe_4_migrate.get_ha_statistics_service",
        return_value=_mock_ha_svc(True),
    ):
        await migrate_etappe_4_reset_vollbackfill(db)
        await db.commit()

    a = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    assert a.vollbackfill_durchgefuehrt is False, (
        f"Erwartet False, bekommen {a.vollbackfill_durchgefuehrt}"
    )


async def test_anlage_ohne_sensor_mapping_unveraendert(db):
    """Anlage ohne sensor_mapping → Flag bleibt unverändert (True bleibt True)."""
    anlage_id = await _seed_anlage(
        db, "Standalone-Anlage",
        sensor_mapping=None,
        vollbackfill=True, mit_tz_daten=True,
    )
    with patch(
        "backend.services.etappe_4_migrate.get_ha_statistics_service",
        return_value=_mock_ha_svc(True),
    ):
        await migrate_etappe_4_reset_vollbackfill(db)
        await db.commit()

    a = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    assert a.vollbackfill_durchgefuehrt is True


async def test_anlage_ohne_tz_daten_unveraendert(db):
    """Anlage mit HA-Mapping, aber leerer TZ-Tabelle → Flag bleibt unverändert.
    Auto-Vollbackfill würde sowieso laufen (Flag=False ist Default), wir
    brauchen den Reset nur für Anlagen mit bereits geschriebenen Aggregaten."""
    anlage_id = await _seed_anlage(
        db, "Neu-Anlage",
        sensor_mapping={"basis": {"einspeisung": {"sensor_id": "sensor.x"}}},
        vollbackfill=True, mit_tz_daten=False,
    )
    with patch(
        "backend.services.etappe_4_migrate.get_ha_statistics_service",
        return_value=_mock_ha_svc(True),
    ):
        await migrate_etappe_4_reset_vollbackfill(db)
        await db.commit()

    a = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    assert a.vollbackfill_durchgefuehrt is True


async def test_ha_lts_nicht_verfuegbar_keine_aenderung(db):
    """HA-LTS nicht verfügbar (Standalone) → Migration läuft no-op."""
    anlage_id = await _seed_anlage(
        db, "Anlage",
        sensor_mapping={"basis": {"einspeisung": {"sensor_id": "sensor.x"}}},
        vollbackfill=True, mit_tz_daten=True,
    )
    with patch(
        "backend.services.etappe_4_migrate.get_ha_statistics_service",
        return_value=_mock_ha_svc(False),
    ):
        await migrate_etappe_4_reset_vollbackfill(db)
        await db.commit()

    a = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    assert a.vollbackfill_durchgefuehrt is True


async def test_idempotenz_zweiter_lauf_kein_problem(db):
    """Zweiter Lauf nach erstem ist auch ok — Flag bleibt False, kein Crash."""
    anlage_id = await _seed_anlage(
        db, "Anlage",
        sensor_mapping={"basis": {"einspeisung": {"sensor_id": "sensor.x"}}},
        vollbackfill=True, mit_tz_daten=True,
    )
    with patch(
        "backend.services.etappe_4_migrate.get_ha_statistics_service",
        return_value=_mock_ha_svc(True),
    ):
        await migrate_etappe_4_reset_vollbackfill(db)
        await db.commit()
        # Zweiter Lauf
        await migrate_etappe_4_reset_vollbackfill(db)
        await db.commit()

    a = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
    assert a.vollbackfill_durchgefuehrt is False


async def test_gemischter_bestand_nur_passende_anlagen(db):
    """Bei mehreren Anlagen werden nur die mit HA-Mapping+TZ-Daten geheilt."""
    a1 = await _seed_anlage(
        db, "HA+Daten",
        sensor_mapping={"basis": {"einspeisung": {"sensor_id": "sensor.x"}}},
        vollbackfill=True, mit_tz_daten=True,
    )
    a2 = await _seed_anlage(
        db, "HA+ohne-Daten",
        sensor_mapping={"basis": {"einspeisung": {"sensor_id": "sensor.y"}}},
        vollbackfill=True, mit_tz_daten=False,
    )
    a3 = await _seed_anlage(
        db, "Standalone",
        sensor_mapping=None,
        vollbackfill=True, mit_tz_daten=True,
    )

    with patch(
        "backend.services.etappe_4_migrate.get_ha_statistics_service",
        return_value=_mock_ha_svc(True),
    ):
        await migrate_etappe_4_reset_vollbackfill(db)
        await db.commit()

    for aid, soll in ((a1, False), (a2, True), (a3, True)):
        a = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
        assert a.vollbackfill_durchgefuehrt is soll, (
            f"Anlage {aid}: erwartet {soll}, bekommen {a.vollbackfill_durchgefuehrt}"
        )


_TESTS = [
    test_ha_anlage_mit_daten_wird_zurueckgesetzt,
    test_anlage_ohne_sensor_mapping_unveraendert,
    test_anlage_ohne_tz_daten_unveraendert,
    test_ha_lts_nicht_verfuegbar_keine_aenderung,
    test_idempotenz_zweiter_lauf_kein_problem,
    test_gemischter_bestand_nur_passende_anlagen,
]


async def _run_all() -> int:
    failures = 0
    for test in _TESTS:
        try:
            await test()
            print(f"OK   {test.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {test.__name__}\n     {e}")
        except Exception:
            failures += 1
            print(f"ERR  {test.__name__}")
            traceback.print_exc()
    return failures

