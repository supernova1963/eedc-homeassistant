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


async def test_ok_zweig_nennt_die_reichweite_monat(db):
    """Achse-B-OK gilt nur für Monatswerte — der Detailtext muss das sagen.

    Forum #32 (Johannes, 2026-07-28): Monatsdaten vollständig, Cockpit/Tag
    durchgehend 0 kWh, Daten-Checker still. Ursache ist keine Fehlbewertung,
    sondern eine zu weit gelesene Aussage: Tages-/Stundenwerte kommen
    ausschließlich aus kumulativen kWh-Zählern (`snapshot/lts_aggregator` liest
    nur den `felder`-Zweig, nie `live`) und bleiben ohne sie leer. Die Schwere
    bleibt bewusst OK — sonst bekäme jede sauber importiert gepflegte Anlage
    eine Dauerwarnung.
    """
    anlage = await _seed(db)
    db.add(_md(anlage.id, 2025, 1, "custom_import"))
    await db.commit()
    anlage = await _reload(db, anlage.id)
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())

    checker = DatenChecker(db)
    ergebnisse = checker._check_energieprofil_abdeckung(anlage, monatsdaten)

    quelle_oks = [r for r in ergebnisse if "Custom-Import" in r.meldung]
    assert quelle_oks, "OK-Meldungen mit Quellen-Hinweis erwartet"
    for r in quelle_oks:
        assert r.schwere == CheckSeverity.OK, (
            f"Schwere muss OK bleiben (keine Dauerwarnung), war: {r.schwere}"
        )
        assert r.details and "Tages- und Stundenwerte" in r.details, (
            "Der OK-Text muss seine Reichweite nennen (Monat ≠ Tag/Stunde), "
            f"fand: {r.details!r}"
        )


async def test_warnung_verweist_auf_datenquellen_flaeche(db):
    """Der WARNING-Zweig schickt in die Datenquellen-Fläche, nicht in den
    seit v4.0.0 abgelösten Sensor-Mapping-Wizard."""
    anlage = await _seed(db)
    db.add(_md(anlage.id, 2025, 1, "ha_statistics"))
    await db.commit()
    anlage = await _reload(db, anlage.id)
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())

    checker = DatenChecker(db)
    ergebnisse = checker._check_energieprofil_abdeckung(anlage, monatsdaten)

    mit_link = [r for r in ergebnisse if r.link]
    assert mit_link, "Abdeckungs-Warnungen sollen einen Sprungpunkt tragen"
    for r in mit_link:
        assert r.link == "/einstellungen/datenquellen", (
            f"Link muss auf die Datenquellen-Fläche zeigen, war: {r.link}"
        )
        assert "Sensor-Mapping-Wizard" not in (r.details or ""), (
            "Der Wizard existiert seit v4.0.0 nicht mehr"
        )
        assert "leistung_w" not in (r.details or ""), (
            "Interne Feldkürzel gehören nicht in Anwendertexte"
        )
