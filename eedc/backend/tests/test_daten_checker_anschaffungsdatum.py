"""Daten-Checker meldet Investitionen ohne Anschaffungsdatum.

Seit v4.0.1 ist das Anschaffungsdatum im Formular Pflicht — für Bestandsdaten
kann es aber fehlen. Ohne das Datum zählt die Komponente in Auswertungen über
den gesamten Zeitraum mit (auch vor der Anschaffung, siehe
`Investition.ist_aktiv_an`) und die Amortisationskurve hat keinen Nullpunkt
(`basis_jahr` im ROI-Dashboard).

Der Befund verlinkt direkt in das Formular der betroffenen Komponente, damit der
Nutzer sie nicht in allen Typ-Blöcken suchen muss.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckSeverity


async def _anlage_mit(db, *, anschaffungsdatum: date | None) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Hausspeicher",
        anschaffungsdatum=anschaffungsdatum, parameter={"kapazitaet_kwh": 10.0},
    ))
    await db.commit()
    # `monatsdaten` mitladen: der Speicher-Zweig des Checkers greift darauf zu
    # (Netzladungs-Plausibilität) und würde sonst lazy nachladen wollen.
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()


async def test_fehlendes_anschaffungsdatum_ist_ein_fehler(db):
    anlage = await _anlage_mit(db, anschaffungsdatum=None)

    ergebnisse = DatenChecker(db)._check_investitionen(anlage, [])

    treffer = [r for r in ergebnisse if "Anschaffungsdatum fehlt" in r.meldung]
    assert len(treffer) == 1, f"genau ein Befund erwartet, war: {[r.meldung for r in ergebnisse]}"
    assert treffer[0].schwere == CheckSeverity.ERROR
    # Sprung direkt in das Formular der Komponente, nicht nur auf die Liste.
    inv_id = anlage.investitionen[0].id
    assert treffer[0].link == f"/einstellungen/komponenten?bearbeiten={inv_id}"


async def test_mit_anschaffungsdatum_kein_befund(db):
    anlage = await _anlage_mit(db, anschaffungsdatum=date(2024, 3, 1))

    ergebnisse = DatenChecker(db)._check_investitionen(anlage, [])

    assert not [r for r in ergebnisse if "Anschaffungsdatum fehlt" in r.meldung]
