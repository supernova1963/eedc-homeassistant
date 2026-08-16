"""Bewertungsgrenze E4 (2026-08-16): Basis-Daten sind ein FEHLER, kein Schoenheitsfehler.

Einspeisung und Netzbezug sind die Basis, auf der eedc ueberhaupt eine Bilanz
bildet. Fehlen sie, weiss eedc nicht, woher der Strom eines Geraets kam -- und
rechnet trotzdem: `direktverbrauch = max(0, PV - Einspeisung - Speicherladung)`
liest eine fehlende Einspeisung als **0**, wodurch die ganze Erzeugung als
Eigenverbrauch gilt und mit dem Netz- statt dem Einspeisepreis bewertet wird. An
einem echten Monat gemessen: **621,83 EUR statt 281,76 EUR**. Die alte Zahl war
nicht ungenau, sondern systematisch zu gut.

Drei Aenderungen, die dieser Test festhaelt:

* **(a)** fehlender Monat ab dem Anker: WARNING -> **ERROR**
* **(b)** Geraet (kein Erzeuger) aelter als die Anlage: neu, und zwar **INFO** --
  der Zustand ist zulaessig (E-Auto von 2017 an einer PV-Anlage von 2022) und
  bleibt es. Was ihn erwaehnenswert macht, ist die Auskunft, dass fuer die Zeit
  davor keine Bilanz existiert. Als WARNING waere es die F-30-Klasse: ein
  zulaessiger Zustand, als Defekt gemeldet -- genau daran hat fridolin22 (Forum
  T77723 #773) sein Auto umdatiert und die echte Historie verloren.
* **(c)** fehlendes `installationsdatum`: WARNING -> **ERROR**

Die Richtung der Texte ist Teil der Zusage und wird hier mitgeprueft: (b) darf
NICHT zum Umdatieren des Geraets raten.
"""

from __future__ import annotations

import re
from datetime import date

from backend.models import Anlage, Investition, Monatsdaten
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckSeverity


async def _anlage(
    db,
    *,
    installationsdatum: date | None,
    geraete: list[tuple[str, date]],
    monate: list[tuple[int, int]],
) -> int:
    anlage = Anlage(
        anlagenname="E4", leistung_kwp=10.0, installationsdatum=installationsdatum
    )
    db.add(anlage)
    await db.flush()
    for typ, datum in geraete:
        db.add(Investition(
            anlage_id=anlage.id, typ=typ, bezeichnung=f"{typ}-{datum.year}",
            anschaffungsdatum=datum, leistung_kwp=10.0,
        ))
    for jahr, monat in monate:
        db.add(Monatsdaten(
            anlage_id=anlage.id, jahr=jahr, monat=monat,
            einspeisung_kwh=100.0, netzbezug_kwh=50.0,
        ))
    await db.commit()
    return anlage.id


def _mit(ergebnisse, teil: str) -> list:
    return [e for e in ergebnisse if teil in e.meldung]


def _fehlende_monate(ergebnisse) -> list:
    """Nur die Meldungen der Form "MM/JJJJ fehlt".

    Bewusst per Muster statt per `endswith(" fehlt")`: Der erste Entwurf dieses
    Tests fing damit auch "Ausrichtung/Neigung fehlt" ein und mass eine INFO-
    Meldung einer ganz anderen Kategorie mit. Derselbe Grund wie in
    `test_daten_checker_erzeuger_vor_anlage.py::_geforderte_monate`.
    """
    return [e for e in ergebnisse if re.fullmatch(r"\d{2}/\d{4} fehlt", e.meldung)]


# ─── (a) fehlender Monat ────────────────────────────────────────────────────

async def test_fehlender_monat_ist_ein_fehler(db):
    """Ein Loch in der Historie ist ab dem Anker ein FEHLER.

    Anlage ab 01/2024, aber nur der Januar ist erfasst -- alles danach fehlt.
    """
    anlage_id = await _anlage(
        db,
        installationsdatum=date(2024, 1, 1),
        geraete=[("pv-module", date(2024, 1, 1))],
        monate=[(2024, 1)],
    )
    ergebnisse = (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse

    fehlend = _fehlende_monate(ergebnisse)
    assert fehlend, "ab 02/2024 muessen Monate fehlen"
    assert all(e.schwere == CheckSeverity.ERROR for e in fehlend), \
        [(e.meldung, e.schwere) for e in fehlend]
    # P-6: jede Meldung nennt den aufloesenden Schritt.
    assert all(e.link and "/monatsabschluss/" in e.link for e in fehlend)


async def test_sammelzeile_ab_dem_13_fehlenden_monat_ist_ebenfalls_fehler(db):
    """Die zweite Stelle derselben Regel: Ab 13 fehlenden Monaten fasst der
    Checker zusammen. Sie stand bis 2026-08-16 getrennt auf WARNING -- eine
    Anlage mit langer Luecke haette damit einen anderen Status bekommen als eine
    mit kurzer."""
    anlage_id = await _anlage(
        db,
        installationsdatum=date(2020, 1, 1),
        geraete=[("pv-module", date(2020, 1, 1))],
        monate=[(2020, 1)],
    )
    ergebnisse = (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse

    sammel = _mit(ergebnisse, "weitere Monate fehlen")
    assert len(sammel) == 1, [e.meldung for e in ergebnisse]
    assert sammel[0].schwere == CheckSeverity.ERROR


# ─── (b) Geraet aelter als die Anlage ───────────────────────────────────────

async def test_aelteres_geraet_wird_als_auskunft_gemeldet(db):
    """fridolin22s Konstellation -- und sie ist KEIN Defekt."""
    anlage_id = await _anlage(
        db,
        installationsdatum=date(2022, 4, 1),
        geraete=[("e-auto", date(2017, 1, 1)), ("pv-module", date(2022, 4, 1))],
        monate=[(2022, 4)],
    )
    ergebnisse = (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse

    treffer = _mit(ergebnisse, "Gerät älter als die Anlage")
    assert len(treffer) == 1, [e.meldung for e in ergebnisse]
    assert treffer[0].schwere == CheckSeverity.INFO
    assert "01.01.2017" in treffer[0].meldung
    assert "01.04.2022" in treffer[0].details
    # Die Richtung des Textes ist die eigentliche Zusage: nicht umdatieren.
    assert "Datiere nicht das Gerät um" in treffer[0].details


async def test_mehrere_aeltere_geraete_nennen_das_aelteste_und_die_anzahl(db):
    anlage_id = await _anlage(
        db,
        installationsdatum=date(2022, 4, 1),
        geraete=[
            ("e-auto", date(2017, 1, 1)),
            ("waermepumpe", date(2019, 8, 1)),
            ("pv-module", date(2022, 4, 1)),
        ],
        monate=[(2022, 4)],
    )
    ergebnisse = (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse

    treffer = _mit(ergebnisse, "Gerät älter als die Anlage")
    assert len(treffer) == 1
    assert "01.01.2017" in treffer[0].meldung, treffer[0].meldung
    assert "2 Geräte betroffen" in treffer[0].details


async def test_erzeuger_loest_die_auskunft_nicht_aus(db):
    """Gegenprobe: Ein ERZEUGER vor dem Anlagendatum hat seinen eigenen Befund
    (WARNING, dort stimmt wirklich eines von zwei Daten nicht). Er darf keinen
    zweiten Eintrag zur selben Sache bekommen."""
    anlage_id = await _anlage(
        db,
        installationsdatum=date(2022, 4, 1),
        geraete=[("pv-module", date(2019, 5, 1))],
        monate=[(2022, 4)],
    )
    ergebnisse = (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse

    assert _mit(ergebnisse, "Gerät älter als die Anlage") == []
    erzeuger = _mit(ergebnisse, "Erzeuger älter als die Anlage")
    assert len(erzeuger) == 1
    assert erzeuger[0].schwere == CheckSeverity.WARNING


async def test_geraet_juenger_als_die_anlage_schweigt(db):
    anlage_id = await _anlage(
        db,
        installationsdatum=date(2022, 4, 1),
        geraete=[("e-auto", date(2023, 6, 1)), ("pv-module", date(2022, 4, 1))],
        monate=[(2022, 4)],
    )
    ergebnisse = (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse

    assert _mit(ergebnisse, "älter als die Anlage") == []


async def test_ohne_anlagendatum_gibt_es_keine_auskunft_ueber_aeltere_geraete(db):
    """Ohne Anker ist "aelter als die Anlage" nicht bestimmbar -- dann schweigt
    die Zeile, statt sich einen Vergleichspunkt auszudenken. Gemeldet wird
    stattdessen das fehlende Datum selbst (siehe (c))."""
    anlage_id = await _anlage(
        db,
        installationsdatum=None,
        geraete=[("e-auto", date(2017, 1, 1)), ("pv-module", date(2024, 3, 1))],
        monate=[(2024, 3)],
    )
    ergebnisse = (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse

    assert _mit(ergebnisse, "älter als die Anlage") == []


# ─── (c) fehlendes Installationsdatum ───────────────────────────────────────

async def test_fehlendes_installationsdatum_ist_ein_fehler(db):
    anlage_id = await _anlage(
        db,
        installationsdatum=None,
        geraete=[("pv-module", date(2024, 3, 1))],
        monate=[(2024, 3)],
    )
    ergebnisse = (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse

    treffer = _mit(ergebnisse, "Installationsdatum nicht gesetzt")
    assert len(treffer) == 1
    assert treffer[0].schwere == CheckSeverity.ERROR
    # Der Grund steht dabei -- die alte Begruendung ("fuer die
    # Vollstaendigkeitspruefung") sagte nicht, was daran schiefgeht.
    assert "Einspeisung und Netzbezug" in treffer[0].details
    assert treffer[0].link == "/einstellungen/anlage"


async def test_gepflegtes_installationsdatum_meldet_ok(db):
    anlage_id = await _anlage(
        db,
        installationsdatum=date(2024, 3, 1),
        geraete=[("pv-module", date(2024, 3, 1))],
        monate=[(2024, 3)],
    )
    ergebnisse = (await DatenChecker(db).check_anlage(anlage_id)).ergebnisse

    assert _mit(ergebnisse, "Installationsdatum nicht gesetzt") == []
    assert _mit(ergebnisse, "Installationsdatum vorhanden")[0].schwere == CheckSeverity.OK
