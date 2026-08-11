"""N-235 — Wh am Balkonkraftwerk, kWh an der Speicher-Investition.

Beide Felder beschreiben dasselbe Gerät und stehen in derselben Maske
untereinander, tragen aber verschiedene Einheiten. Wer den Zahlenwert
überträgt, liegt um Faktor 1000 daneben; gemeldet hat das bisher nichts.
Real eingetreten bei azywietz-web (Discussion #366): Anker Solarbank 3 mit
5.376 **Wh**, in eedc als 5.376 **kWh** geführt.

Die Regel prüft **keinen Schwellenwert**, sondern den Widerspruch zweier
gepflegter Felder — deshalb prüfen die Tests unten beide Richtungen: der
richtig gepflegte Bestand (5,376 kWh) muss **schweigen**.
"""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckSeverity

_MELDUNG = "Wh statt kWh"


async def _anlage(db, speicher_kwh, bkw_wh=5376, parent: bool = True) -> Anlage:
    anlage = Anlage(anlagenname="BKW-Test", leistung_kwp=2.0)
    db.add(anlage)
    await db.flush()

    bkw_param = {"anzahl_module": 4, "leistung_pro_modul_wp": 500}
    if bkw_wh is not None:
        bkw_param["speicher_kapazitaet_wh"] = bkw_wh
    bkw = Investition(
        anlage_id=anlage.id, typ="balkonkraftwerk", bezeichnung="Toni",
        anschaffungskosten_gesamt=1367.0, anschaffungsdatum=date(2026, 3, 19),
        leistung_kwp=2.0, parameter=bkw_param,
    )
    db.add(bkw)
    await db.flush()

    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher Toni",
        anschaffungskosten_gesamt=555.0, anschaffungsdatum=date(2026, 3, 19),
        parent_investition_id=bkw.id if parent else None,
        parameter={"kapazitaet_kwh": speicher_kwh},
    ))
    await db.commit()
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()


def _treffer(anlage, db):
    return [
        r for r in DatenChecker(db)._check_investitionen(anlage, [])
        if _MELDUNG in r.meldung
    ]


async def test_gleicher_zahlenwert_in_zwei_einheiten_wird_gemeldet(db):
    """Der Fall aus #366: 5376 Wh oben, 5376 kWh unten."""
    anlage = await _anlage(db, speicher_kwh=5376.0)

    treffer = _treffer(anlage, db)

    assert len(treffer) == 1, "Der Widerspruch muss genau einmal gemeldet werden."
    befund = treffer[0]
    assert befund.schwere == CheckSeverity.WARNING
    assert "5.376 Wh" in befund.details and "5.376 kWh" in befund.details
    assert "5,376 kWh" in befund.details, (
        "Die Meldung nennt die Zahl, die einzutragen ist — sonst ist sie eine "
        "Diagnose ohne Handlung."
    )
    assert befund.investition_id is not None, (
        "Ohne `investition_id` erreicht der Befund den Komponenten-Hub nicht (F-21)."
    )


async def test_richtig_gepflegter_bestand_schweigt(db):
    """5,376 kWh neben 5376 Wh ist korrekt — kein Wort dazu.

    Das ist die teurere Hälfte der Regel: eine Meldung, die man nicht
    wegklicken kann, muss richtig sein.
    """
    anlage = await _anlage(db, speicher_kwh=5.376)

    assert _treffer(anlage, db) == []


async def test_ohne_balkonkraftwerk_als_parent_keine_meldung(db):
    """Ein eigenständiger 5.376-kWh-Speicher wäre absurd, aber die Regel
    behauptet nichts ohne den zweiten gepflegten Wert — sie ist ein
    Widerspruchs-, kein Schwellentest."""
    anlage = await _anlage(db, speicher_kwh=5376.0, parent=False)

    assert _treffer(anlage, db) == []


async def test_ohne_gepflegte_bkw_kapazitaet_keine_meldung(db):
    anlage = await _anlage(db, speicher_kwh=5376.0, bkw_wh=None)

    assert _treffer(anlage, db) == []
