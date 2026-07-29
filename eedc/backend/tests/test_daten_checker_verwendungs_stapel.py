"""
Akzeptanztest: der Daten-Checker fragt nach, wenn mehr PV verwendet als erzeugt
wurde (N51 — „Verwendungs-Stapel > Erzeugung").

Prüfung 3 vergleicht nur Einspeisung ↔ Erzeugung. Was in den Speicher ging, kam
aber ebenfalls aus der PV — **außer** dem Arbitrage-Anteil aus dem Netz. Genau
diese Netzladung ist der Grund, warum die Prüfung als **Frage** formuliert ist
und nicht als Fehler: der häufigste Auslöser ist ein ungepflegtes Feld
„Ladung aus Netz", nicht eine falsche Messung.
        eedc/backend/tests/test_daten_checker_verwendungs_stapel.py
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten,
)

_MELDUNG = "mehr PV verwendet als erzeugt?"


async def _seed(
    db: AsyncSession, *, pv: float, einspeisung: float,
    ladung: float, netzladung: float | None,
) -> tuple[Anlage, list[Monatsdaten]]:
    """Ein PV-String (gemessen) + ein Speicher, Mai 2024."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    modul = Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    speicher = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Batterie", leistung_kwp=10.0,
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    )
    db.add_all([modul, speicher])
    await db.flush()

    db.add(InvestitionMonatsdaten(
        investition_id=modul.id, jahr=2024, monat=5,
        verbrauch_daten={"pv_erzeugung_kwh": pv},
    ))
    speicher_daten: dict = {"ladung_kwh": ladung, "entladung_kwh": ladung * 0.9}
    if netzladung is not None:
        speicher_daten["ladung_netz_kwh"] = netzladung
    db.add(InvestitionMonatsdaten(
        investition_id=speicher.id, jahr=2024, monat=5,
        verbrauch_daten=speicher_daten,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2024, monat=5,
        einspeisung_kwh=einspeisung, netzbezug_kwh=200.0,
    ))
    await db.commit()

    anlage = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    monatsdaten = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars().all())
    return anlage, monatsdaten


async def _meldungen(db, anlage, monatsdaten) -> list[str]:
    from backend.services.daten_checker import DatenChecker

    ergebnisse = await DatenChecker(db)._check_monatsdaten_plausibilitaet(
        anlage, monatsdaten
    )
    return [e.meldung for e in ergebnisse if _MELDUNG in (e.meldung or "")]


async def test_stapel_ueber_erzeugung_wird_gefragt(db):
    """800 kWh erzeugt, 500 eingespeist, 400 geladen (keine Netzladung) → Frage."""
    anlage, md = await _seed(db, pv=800.0, einspeisung=500.0, ladung=400.0, netzladung=None)

    treffer = await _meldungen(db, anlage, md)

    assert treffer, "Verwendungs-Stapel 900 > 800 kWh muss gemeldet werden"
    assert "?" in treffer[0], "Die Meldung ist bewusst als Frage formuliert"


async def test_netzladung_erklaert_den_ueberhang(db):
    """Dieselben Zahlen, aber 300 kWh der Ladung kamen aus dem Netz → still.

    Die Gegenprobe, die die ganze Prüfung trägt: ohne den Abzug der Netzladung
    wäre sie ein Dauer-Fehlalarm für jede Anlage mit Arbitrage-Ladung.
    """
    anlage, md = await _seed(db, pv=800.0, einspeisung=500.0, ladung=400.0, netzladung=300.0)

    assert not await _meldungen(db, anlage, md)


async def test_plausibler_monat_bleibt_still(db):
    """800 erzeugt, 300 eingespeist, 200 geladen → passt, keine Meldung."""
    anlage, md = await _seed(db, pv=800.0, einspeisung=300.0, ladung=200.0, netzladung=None)

    assert not await _meldungen(db, anlage, md)


async def test_kleine_abweichung_bleibt_unter_der_toleranz(db):
    """Stapel 803 gegen 800 kWh — Rundung/Messfehler, kein Befund.

    Toleranz ist `max(5, 2 % der Erzeugung)`; ohne sie meldete die Prüfung bei
    jedem Zählerstand-Rundungsrest.
    """
    anlage, md = await _seed(db, pv=800.0, einspeisung=503.0, ladung=300.0, netzladung=0.0)

    assert not await _meldungen(db, anlage, md)
