"""
Akzeptanztest: Daten-Checker Achse B (project_datenchecker_konsistenz).

Wer seine Monatsdaten per Custom-/CSV-/JSON-Import oder manuell pflegt,
braucht keinen gemappten kumulativen kWh-Sensor. Liegt eine solche
`datenquelle` in den Monatsdaten vor, gilt die Energieprofil-Abdeckung als
erfüllt — OK mit Quellen-Hinweis statt WARNING „Komponente ohne Mapping".

Logik pro Komponente: (1) Sensor-Mapping → OK(Sensor), (2) sonst manuelle
Datenquelle → OK(Quelle), (3) sonst → WARNING (unverändertes Verhalten).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition, Monatsdaten  # noqa: F401
from backend.services.daten_checker import DatenChecker, CheckSeverity


async def _seed(db: AsyncSession) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    _inv = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Süd",
        leistung_kwp=10.0, anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    db.add(_inv)
    await db.flush()
    return anlage


async def _reload(db: AsyncSession, anlage_id: int) -> Anlage:
    return (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen)).where(Anlage.id == anlage_id)
    )).scalar_one()


def _md(anlage_id: int, jahr: int, monat: int, quelle: str) -> Monatsdaten:
    return Monatsdaten(
        anlage_id=anlage_id, jahr=jahr, monat=monat,
        einspeisung_kwh=100.0, netzbezug_kwh=50.0, datenquelle=quelle,
    )


async def test_keine_mappings_aber_custom_import_ist_ok(db):
    """0 Sensor-Mappings + datenquelle=custom_import → OK, kein WARNING."""
    anlage = await _seed(db)
    db.add(_md(anlage.id, 2025, 1, "custom_import"))
    db.add(_md(anlage.id, 2025, 2, "custom_import"))
    await db.commit()
    anlage = await _reload(db, anlage.id)
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())

    checker = DatenChecker(db)
    ergebnisse = checker._check_energieprofil_abdeckung(anlage, monatsdaten)

    warnings = [r for r in ergebnisse if r.schwere == CheckSeverity.WARNING]
    assert not warnings, (
        f"Custom-Import als Quelle darf keine Abdeckungs-Warnung auslösen, fand:\n"
        + "\n".join(f"  {w.meldung}" for w in warnings)
    )
    quelle_oks = [r for r in ergebnisse if "Custom-Import" in r.meldung]
    assert quelle_oks, (
        "OK-Meldung mit Quellen-Hinweis (Custom-Import) erwartet, fand:\n"
        + "\n".join(f"  {r.schwere.value}: {r.meldung}" for r in ergebnisse)
    )


async def test_mix_sensor_und_custom_import_beide_ok(db):
    """Eine Komponente per Sensor, eine andere per Custom-Import → beide OK."""
    anlage = await _seed(db)
    # zweite Komponente ohne Sensor (Wallbox)
    db.add(Investition(
        anlage_id=anlage.id, typ="wallbox", bezeichnung="Wallbox",
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    ))
    await db.flush()
    pv_id = next(
        i.id for i in (await db.execute(select(Investition))).scalars()
        if i.bezeichnung == "Süd"
    )
    anlage.sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.eins"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.netz"},
        },
        "investitionen": {
            str(pv_id): {"felder": {
                "pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"},
            }},
        },
    }
    db.add(_md(anlage.id, 2025, 1, "custom_import"))
    await db.commit()
    anlage = await _reload(db, anlage.id)
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())

    checker = DatenChecker(db)
    ergebnisse = checker._check_energieprofil_abdeckung(anlage, monatsdaten)

    warnings = [r for r in ergebnisse if r.schwere == CheckSeverity.WARNING]
    assert not warnings, (
        f"Mix Sensor+Custom: kein WARNING erwartet, fand:\n"
        + "\n".join(f"  {w.meldung}" for w in warnings)
    )
    sensor_ok = [r for r in ergebnisse if "kWh-Zähler gemappt" in r.meldung]
    quelle_ok = [r for r in ergebnisse if "Custom-Import" in r.meldung]
    assert sensor_ok, "OK-Meldung für Sensor-Komponente erwartet"
    assert quelle_ok, "OK-Meldung für Custom-Import-Komponente erwartet"


async def test_weder_sensor_noch_quelle_warnt_wie_bisher(db):
    """Kein Sensor-Mapping + keine manuelle datenquelle → WARNING (unverändert)."""
    anlage = await _seed(db)
    # datenquelle, die NICHT als manuell gilt (Sensor-Snapshot-Pfad)
    db.add(_md(anlage.id, 2025, 1, "ha_statistics"))
    await db.commit()
    anlage = await _reload(db, anlage.id)
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())

    checker = DatenChecker(db)
    ergebnisse = checker._check_energieprofil_abdeckung(anlage, monatsdaten)

    warnings = [r for r in ergebnisse if "ohne vollständige kWh-Zähler-Abdeckung" in r.meldung]
    assert warnings, (
        "Ohne Sensor und ohne manuelle Quelle muss wie bisher gewarnt werden, fand:\n"
        + "\n".join(f"  {r.schwere.value}: {r.meldung}" for r in ergebnisse)
    )
