"""Daten-Checker Achse C: der Anlagen-Zählerstand deckt die Erzeuger ab.

Gegenstück zu Achse B (`test_daten_checker_custom_import_quelle.py`, manuelle
Pflege) und zur Datenquellen-Fläche
(`test_datenquellen_pv_aggregat_tagesebene.py`).

Mit Stufe 1 zu F-7 ist `basis["pv_gesamt"]` ein Snapshot-Zähler und trägt Monat,
Tag und Stunde für die ganze Anlage. Ohne diesen Zweig meldete der Checker
weiterhin „Komponente ohne vollständige kWh-Zähler-Abdeckung", während die
Datenquellen-Fläche denselben Anwender als vollständig versorgt führt — genau
der Selbstwiderspruch aus T89667 #109, nur seitenverkehrt.

⛔ **Die Kopplung an die Alles-oder-nichts-Regel ist mit #406 gefallen.** Hier
stand: „sobald ein Erzeuger selbst misst, ist das Aggregat für Tag und Stunde
abgeschaltet — dann sind die übrigen Erzeuger wirklich ungedeckt und die
Warnung muss bleiben." Das war **nur wahr, weil der Defekt da war**: die
Verdrängung fragte die Zuordnung statt die Daten und machte die Anlagensumme zu
klein. Mit der Präzedenz je Tag (`core/berechnungen/pv_tages_praezedenz.py`)
trägt das Aggregat die Bilanz gerade dann, wenn die Einzelzähler sie nicht
vollständig tragen — die Warnung wäre jetzt eine Falschmeldung.

⚠ Die Frage des Checkers bleibt die von F-7: **ist die Bilanz gedeckt?**, nicht
**ist sie aufgeschlüsselt?**. Was ein eigener Zähler zusätzlich brächte, steht
an der Komponenten-Zeile der Datenquellen-Fläche.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition  # noqa: F401
from backend.services.daten_checker import DatenChecker, CheckSeverity


def _sensor(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


async def _seed(db: AsyncSession, *, mapping: dict) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, sensor_mapping=mapping)
    db.add(anlage)
    await db.flush()
    for bez, kwp in (("West", 5.0), ("Ost", 5.0)):
        db.add(Investition(
            anlage_id=anlage.id, typ="pv-module", bezeichnung=bez,
            leistung_kwp=kwp, anschaffungsdatum=date(2024, 1, 1), aktiv=True,
        ))
    await db.flush()
    return anlage


async def _reload(db: AsyncSession, anlage_id: int) -> Anlage:
    return (await db.execute(
        select(Anlage).options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage_id)
    )).scalar_one()


def _basis() -> dict:
    return {
        "pv_gesamt": _sensor("sensor.pv_anlage_gesamt"),
        "einspeisung": _sensor("sensor.einspeisung"),
        "netzbezug": _sensor("sensor.netzbezug"),
    }


async def test_anlagenzaehler_deckt_alle_erzeuger(db):
    """Summenzähler belegt, kein Erzeuger misst selbst ⇒ keine Warnung."""
    anlage = await _seed(db, mapping={"basis": _basis(), "investitionen": {}})
    await db.commit()
    anlage = await _reload(db, anlage.id)

    ergebnisse = DatenChecker(db)._check_energieprofil_abdeckung(anlage)

    warnings = [r for r in ergebnisse if r.schwere == CheckSeverity.WARNING]
    assert not warnings, (
        "Ein Anlagen-Zählerstand deckt Tag und Stunde für die ganze Anlage — "
        "dafür darf es keine Abdeckungs-Warnung geben, fand:\n"
        + "\n".join(f"  {w.meldung}" for w in warnings)
    )
    treffer = [r for r in ergebnisse if "Anlagen-Zählerstand" in r.meldung]
    assert treffer, (
        "OK-Meldung mit Aggregat-Hinweis erwartet, fand:\n"
        + "\n".join(f"  {r.schwere.value}: {r.meldung}" for r in ergebnisse)
    )
    assert treffer[0].meldung.startswith("2 Erzeuger"), treffer[0].meldung
    # Der Text muss den Preis nennen, sonst führt er in die Alles-oder-nichts-Falle.
    assert "sobald einer gemessen wird" in (treffer[0].details or "")


async def test_teilbelegung_ist_keine_luecke_mehr(db):
    """⛔ Diese Probe hieß bis #406 `test_teilbelegung_bleibt_eine_warnung` und
    forderte das Gegenteil.

    Ihre Begründung — „die Tagessumme ist zu niedrig" — beschrieb den Defekt,
    nicht die Regel: das Aggregat wurde an der ZUORDNUNG verdrängt. Seit der
    Präzedenz je Tag trägt es die Bilanz genau in dieser Lage. Eine Warnung
    hier wäre die Falschmeldung, die der Bau beseitigt hat.
    """
    anlage = await _seed(db, mapping={"basis": _basis(), "investitionen": {}})
    west_id = (await db.execute(
        select(Investition.id).where(Investition.anlage_id == anlage.id)
        .order_by(Investition.id)
    )).scalars().first()
    anlage.sensor_mapping = {
        "basis": _basis(),
        "investitionen": {
            str(west_id): {"felder": {"pv_erzeugung_kwh": _sensor("sensor.west_kwh")}},
        },
    }
    await db.commit()
    anlage = await _reload(db, anlage.id)

    ergebnisse = DatenChecker(db)._check_energieprofil_abdeckung(anlage)

    warnings = [
        r for r in ergebnisse
        if r.schwere == CheckSeverity.WARNING and "Abdeckung" in r.meldung
    ]
    assert not warnings, (
        "Bei Teilbelegung trägt der Anlagen-Zählerstand die Bilanz (#406) — "
        "eine Abdeckungs-Warnung ist hier eine Falschmeldung, fand:\n"
        + "\n".join(f"  {r.schwere.value}: {r.meldung}" for r in ergebnisse)
    )
    # Die OK-Meldung nennt weiterhin den Anlagen-Zählerstand als Deckung —
    # sonst stünde die Anlage ohne Aussage da, und der F-7-Selbstwiderspruch
    # (Fläche „vollständig", Checker schweigt) käme in dritter Fassung zurück.
    treffer = [r for r in ergebnisse if "Anlagen-Zählerstand" in r.meldung]
    assert treffer, (
        "OK-Meldung mit Aggregat-Hinweis erwartet, fand:\n"
        + "\n".join(f"  {r.schwere.value}: {r.meldung}" for r in ergebnisse)
    )
    # Und der mit Stufe 1 abgelöste Satz darf nicht zurückkehren.
    assert "ersetzt das nicht" not in (treffer[0].details or "")


async def test_ohne_aggregat_bleibt_alles_wie_bisher(db):
    """Regressionsschutz: kein Summenzähler ⇒ unverändertes Verhalten."""
    anlage = await _seed(db, mapping={
        "basis": {
            "einspeisung": _sensor("sensor.einspeisung"),
            "netzbezug": _sensor("sensor.netzbezug"),
        },
        "investitionen": {},
    })
    await db.commit()
    anlage = await _reload(db, anlage.id)

    ergebnisse = DatenChecker(db)._check_energieprofil_abdeckung(anlage)

    warnings = [
        r for r in ergebnisse
        if r.schwere == CheckSeverity.WARNING and "Abdeckung" in r.meldung
    ]
    assert warnings and warnings[0].meldung.startswith("2 von 2"), [
        r.meldung for r in ergebnisse
    ]
