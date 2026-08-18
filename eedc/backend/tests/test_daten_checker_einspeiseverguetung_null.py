"""Daten-Checker nennt die Rechenfolge eines 0-ct-Tarifs — ab einer Menge, die zählt.

Gegenstück zum Entscheid vom 2026-08-08 (Forum T89667 #122): eedc belegt die
Einspeisevergütung nicht mehr mit einem aus der Anlagengröße geratenen EEG-Satz
vor, sondern mit **0**. Der alte Vorschlag war für jede Anlage über 10 kWp zu
niedrig (er nahm den Satz der erreichten Stufe statt des gewichteten
Mischsatzes), und jede Satz-Tabelle im Code veraltet — für 2027 laufen bereits
neue Planungen.

Damit die 0 kein stiller Verlust wird (Einspeise-Erlös 0 € in Cockpit, ROI und
Jahresbericht, sichtbar erst Monate später), meldet der Checker sie. Aber nur
mit erfasster Einspeisung: bei Volleinspeisung ohne Vergütung oder nach dem Ende
der EEG-Förderung ist 0 der richtige Wert, und ein Hinweis, den niemand
abstellen kann, ist die P-6-Falle. Deshalb steht jedem „Befund"-Fall ein
„kein Befund"-Fall gegenüber.

⚑ **Seit F-38 (#382 azywietz-web, 18.08.2026) an zwei Stellen enger gefasst** —
diese Datei beschreibt seither den neuen Stand:

1. **Schwelle** `EINSPEISUNG_MELDESCHWELLE_KWH_JAHR`. „Erfasste Einspeisung"
   allein reichte nicht: Ein Nulleinspeisungs-System speist die Regelungstoleranz
   seines Wechselrichters ein (Melder: ~5 kWh in fünf Monaten) und kann den
   Hinweis nur durch einen FALSCHEN Vergütungssatz abstellen — die P-6-Falle,
   vor der der Kommentar an der Fundstelle selbst warnte.
2. **Kein Fordern mehr, INFO statt WARNING.** Maßgabe Gernots: „Was der Benutzer
   einträgt, wird gerechnet." Die Zeile sagt jetzt, WAS gerechnet wird
   (0 ct/kWh), statt zum Eintragen aufzufordern.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition, Monatsdaten, Strompreis
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckSeverity

_MELDUNG = "rechnen die Einspeisung mit 0 ct/kWh"


async def _anlage(db, *, verguetung_cent: float, einspeisung_kwh: float) -> tuple[Anlage, list]:
    anlage = Anlage(anlagenname="Tarif-Test", leistung_kwp=12.5)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein",
        gueltig_ab=date(2025, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=30.0,
        einspeiseverguetung_cent_kwh=verguetung_cent,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=6,
        einspeisung_kwh=einspeisung_kwh, netzbezug_kwh=100.0,
    ))
    await db.commit()
    geladen = (await db.execute(
        select(Anlage)
        .options(
            selectinload(Anlage.strompreise),
            selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten),
        )
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    monate = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars())
    return geladen, monate


async def test_null_verguetung_bei_erfasster_einspeisung_wird_gemeldet(db):
    """Der Regelfall nach dem Wizard: Vorbelegung 0 nie überschrieben."""
    anlage, monate = await _anlage(db, verguetung_cent=0.0, einspeisung_kwh=800.0)

    ergebnisse = DatenChecker(db)._check_strompreise(anlage, monate)

    treffer = [r for r in ergebnisse if _MELDUNG in r.meldung]
    assert len(treffer) == 1, f"Befund erwartet, war: {[r.meldung for r in ergebnisse]}"
    # INFO, nicht WARNING: eine eingetragene 0 ist eine Angabe, kein Datenfehler.
    assert treffer[0].schwere == CheckSeverity.INFO
    assert "Mischsatz" in treffer[0].details
    # Und der Text nennt die Rechenfolge, statt zu fordern.
    assert "rechnet den Einspeise-Erlös" in treffer[0].details
    assert "Trag den Satz" not in treffer[0].details
    assert treffer[0].link == "/einstellungen/strompreise"


async def test_null_verguetung_ohne_einspeisung_schweigt(db):
    """Wer nichts einspeist, verliert durch die 0 nichts — kein Nörgeln."""
    anlage, monate = await _anlage(db, verguetung_cent=0.0, einspeisung_kwh=0.0)

    ergebnisse = DatenChecker(db)._check_strompreise(anlage, monate)

    assert not [r for r in ergebnisse if _MELDUNG in r.meldung]


async def test_gepflegter_satz_schweigt(db):
    """Derselbe Bestand mit eingetragenem Satz — kein Befund."""
    anlage, monate = await _anlage(db, verguetung_cent=7.98, einspeisung_kwh=800.0)

    ergebnisse = DatenChecker(db)._check_strompreise(anlage, monate)

    assert not [r for r in ergebnisse if _MELDUNG in r.meldung]


async def test_einspeisung_ausserhalb_des_gratis_tarifs_schweigt(db):
    """Die 0 gilt ab 2026 — Einspeisung von 2025 fällt nicht darunter.

    Ohne den Zeitraum-Abgleich meldete die Regel jeden Bestand, der IRGENDWANN
    eingespeist hat, sobald irgendein Tarif 0 ct trägt.
    """
    anlage = Anlage(anlagenname="Zwei Tarife", leistung_kwp=12.5)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein",
        gueltig_ab=date(2025, 1, 1), gueltig_bis=date(2025, 12, 31),
        netzbezug_arbeitspreis_cent_kwh=30.0, einspeiseverguetung_cent_kwh=8.2,
    ))
    db.add(Strompreis(
        anlage_id=anlage.id, verwendung="allgemein",
        gueltig_ab=date(2026, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=32.0, einspeiseverguetung_cent_kwh=0.0,
    ))
    db.add(Monatsdaten(
        anlage_id=anlage.id, jahr=2025, monat=6,
        einspeisung_kwh=800.0, netzbezug_kwh=100.0,
    ))
    await db.commit()
    geladen = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.strompreise), selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage.id)
    )).scalar_one()
    monate = list((await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage.id)
    )).scalars())

    ergebnisse = DatenChecker(db)._check_strompreise(geladen, monate)

    assert not [r for r in ergebnisse if _MELDUNG in r.meldung]


async def test_nulleinspeisung_regelungstoleranz_schweigt(db):
    """Der Melder-Fall (#382): ~1 kWh je Monat ist Regelungstoleranz, keine Lücke.

    Anker Solarbank mit 800-W-AC-Grenze; 0 ct ist der richtige Wert, und ein
    anderer wäre falsch. Ohne Schwelle blieb der Hinweis unabstellbar stehen.
    """
    anlage, monate = await _anlage(db, verguetung_cent=0.0, einspeisung_kwh=1.0)

    ergebnisse = DatenChecker(db)._check_strompreise(anlage, monate)

    assert not [r for r in ergebnisse if _MELDUNG in r.meldung], (
        "12 kWh/Jahr liegen unter der Meldeschwelle — dazu gibt es nichts zu sagen"
    )


async def test_schwelle_rechnet_auf_das_jahr_hoch(db):
    """Ein einzelner Monat mit 5 kWh ist 60 kWh/Jahr — und damit über der Schwelle.

    Die Gegenprobe zum Test darüber: dieselbe Monatsmenge, aber sie steht für
    ein ganzes Jahr in dieser Höhe. Ohne Hochrechnung entschiede die Länge des
    erfassten Zeitraums darüber, ob der Hinweis kommt.
    """
    anlage, monate = await _anlage(db, verguetung_cent=0.0, einspeisung_kwh=5.0)

    ergebnisse = DatenChecker(db)._check_strompreise(anlage, monate)

    assert [r for r in ergebnisse if _MELDUNG in r.meldung], (
        "5 kWh in EINEM erfassten Monat sind 60 kWh/Jahr — das ist über der Schwelle"
    )
