"""(e') Der Daten-Checker sieht „Ladung erfasst, Entladung fehlt" auch auf dem
heutigen Erfassungsweg — je Gerät.

**Der Befund (gemessen 22.09.2026, HEAD `786483a4`).** Die Warnung
„Batterie-Entladung nicht erfasst (Speicher vorhanden)" gibt es seit langem,
aber nur auf dem **Legacy**-Pfad: sie hängt an `Monatsdaten.batterie_*` und
feuert ausdrücklich nur, solange für den Monat **gar keine**
`InvestitionMonatsdaten` vorliegen. Auf dem heutigen Weg
(`InvestitionMonatsdaten.verbrauch_daten`) blieb ein Monat mit
`ladung_kwh > 0` und fehlender `entladung_kwh` **stumm** — derselbe Fall, den
der HA-Export seit A7 `keine-entladung` nennt.

**Warum je Gerät.** Die vorhandene Faltung (`speicher_imd_bat`) summiert über
alle Speicher und verdeckt die Lücke: zwei Geräte, eines davon vollständig,
und die Summe sieht heil aus. Der Anwender muss wissen, an welchem Gerät das
Feld fehlt — er füllt es dort.

⚠ **`entladung == 0` ist ein WERT** (ADR-002/P4) und kein Hinweis.

Schwesterdateien: `test_daten_checker_verwendungs_stapel.py` (dieselbe Prüfung
`_check_monatsdaten_plausibilitaet`, dasselbe Seeding-Muster),
`test_daten_checker_stilllegung.py` (die Zeitgrenze je Gerät) und
`test_v1_sim_start_halbe_stunde.py` — der andere Posten desselben Pakets.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.models import (  # noqa: F401
    Anlage, Investition, InvestitionMonatsdaten, Monatsdaten,
)

_NEU = "Entladung nicht erfasst (Ladung"
_LEGACY = "Batterie-Entladung nicht erfasst (Speicher vorhanden)"


async def _seed(
    db: AsyncSession,
    *,
    geraete: list[tuple[str, date, Optional[date], Optional[dict]]],
    monate: tuple[tuple[int, int], ...] = ((2024, 5),),
    legacy_batterie: bool = False,
) -> tuple[Anlage, list[Monatsdaten]]:
    """`geraete` = (Bezeichnung, Anschaffung, Stilllegung|None, IMD-Daten|None)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach", leistung_kwp=10.0,
        anschaffungsdatum=date(2024, 1, 1), aktiv=True,
    ))
    for name, anschaffung, stilllegung, daten in geraete:
        inv = Investition(
            anlage_id=anlage.id, typ="speicher", bezeichnung=name,
            anschaffungsdatum=anschaffung, stilllegungsdatum=stilllegung, aktiv=True,
            parameter={"kapazitaet_kwh": 10.0},
        )
        db.add(inv)
        await db.flush()
        if daten is not None:
            for jahr, monat in monate:
                db.add(InvestitionMonatsdaten(
                    investition_id=inv.id, jahr=jahr, monat=monat,
                    verbrauch_daten=dict(daten),
                ))
    for jahr, monat in monate:
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=jahr, monat=monat,
            einspeisung_kwh=300.0, netzbezug_kwh=200.0,
            batterie_ladung_kwh=400.0 if legacy_batterie else None,
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


async def _meldungen(db, anlage, monatsdaten, muster: str) -> list[str]:
    from backend.services.daten_checker import DatenChecker

    ergebnisse = await DatenChecker(db)._check_monatsdaten_plausibilitaet(
        anlage, monatsdaten
    )
    return [e.meldung for e in ergebnisse if muster in (e.meldung or "")]


async def test_ladung_ohne_entladung_wird_gemeldet(db):
    """400 kWh geladen, Entladungsfeld leer ⇒ genau eine Warnung, mit Gerätenamen."""
    anlage, md = await _seed(db, geraete=[
        ("Akku Keller", date(2024, 1, 1), None, {"ladung_kwh": 400.0}),
    ])

    treffer = await _meldungen(db, anlage, md, _NEU)

    assert len(treffer) == 1, f"genau eine Warnung erwartet, gefunden: {treffer}"
    assert "Akku Keller" in treffer[0], "der Anwender muss wissen, welches Gerät"
    assert "05/2024" in treffer[0]
    assert "400" in treffer[0], "die vorhandene Ladung gehört in die Meldung"


async def test_entladung_null_ist_ein_wert(db):
    """`entladung_kwh = 0` heißt „in diesem Monat nichts abgegeben" — kein Hinweis."""
    anlage, md = await _seed(db, geraete=[
        ("Akku", date(2024, 1, 1), None, {"ladung_kwh": 400.0, "entladung_kwh": 0.0}),
    ])

    assert await _meldungen(db, anlage, md, _NEU) == []


async def test_ohne_ladung_keine_warnung(db):
    """Kein Wert auf der Ladeseite ⇒ nichts zu monieren (der Monat ist unerfasst,
    dafür gibt es die Abdeckungs-Prüfung, nicht diese hier)."""
    anlage, md = await _seed(db, geraete=[
        ("Akku", date(2024, 1, 1), None, {"ladung_kwh": 0.0}),
    ])

    assert await _meldungen(db, anlage, md, _NEU) == []


async def test_nur_ein_geraet_von_zweien_wird_genannt(db):
    """⭐ Der Fall, den die Aggregation verdeckt: die Summe sieht heil aus."""
    anlage, md = await _seed(db, geraete=[
        ("Akku A", date(2024, 1, 1), None,
         {"ladung_kwh": 300.0, "entladung_kwh": 270.0}),
        ("Akku B", date(2024, 1, 1), None, {"ladung_kwh": 250.0}),
    ])

    treffer = await _meldungen(db, anlage, md, _NEU)

    assert len(treffer) == 1, f"nur das lückenhafte Gerät: {treffer}"
    assert "Akku B" in treffer[0] and "Akku A" not in treffer[0]


async def test_monat_vor_der_anschaffung_bleibt_still(db):
    """Die Zeitgrenze gilt je Gerät (Issue #226): kein Hinweis vor der Anschaffung."""
    anlage, md = await _seed(
        db,
        geraete=[("Akku", date(2024, 9, 1), None, {"ladung_kwh": 400.0})],
        monate=((2024, 5),),
    )

    assert await _meldungen(db, anlage, md, _NEU) == []


async def test_legacy_monat_bekommt_nur_die_alte_warnung(db):
    """Ein Monat ohne IMD-Zeile bleibt beim Legacy-Text — und bekommt nicht zwei."""
    anlage, md = await _seed(
        db,
        geraete=[("Akku", date(2024, 1, 1), None, None)],
        legacy_batterie=True,
    )

    assert len(await _meldungen(db, anlage, md, _LEGACY)) == 1
    assert await _meldungen(db, anlage, md, _NEU) == []
