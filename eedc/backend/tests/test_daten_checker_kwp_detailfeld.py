"""Daten-Checker liest die Modul-kWp über den SoT-Helper, nicht aus der Spalte.

N66 (#229-Klasse): `Investition.leistung_kwp` existiert als Tabellen-Spalte UND
als Schlüssel im `parameter`-JSON — je nachdem, über welches Formular/welchen
Import die Komponente entstanden ist. Der Stammdaten-Check las nur die Spalte.
Bei einer Anlage, deren Nennleistung ausschließlich im Detail-Feld gepflegt ist,
stand dort NULL → Summe 0 → „PV-Module kWp stimmt nicht mit Anlagenleistung
überein" bei einer korrekt gepflegten Anlage.

Der wichtigere der beiden Fälle ist der zweite: ein Fix, der die Prüfung
stilllegt, wäre schlimmer als die Falschmeldung. Deshalb steht jedem
„kein Befund"-Test ein „Befund bleibt"-Test gegenüber.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckSeverity

_ABWEICHUNG = "PV-Module kWp stimmt nicht mit Anlagenleistung überein"
_FEHLT = "Leistung (kWp) fehlt"


async def _anlage_mit_modul(db, *, anlagen_kwp: float, spalte, parameter: dict) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=anlagen_kwp)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach Süd",
        anschaffungsdatum=date(2022, 5, 1), leistung_kwp=spalte,
        ausrichtung="Süd", neigung_grad=30, parameter=parameter,
    ))
    await db.commit()
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()


async def test_kwp_nur_im_detailfeld_ist_keine_abweichung(db):
    """Spalte leer, `parameter.kwp` = Anlagenleistung ⇒ kein Befund."""
    anlage = await _anlage_mit_modul(
        db, anlagen_kwp=9.8, spalte=None, parameter={"kwp": 9.8},
    )

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    assert not [r for r in ergebnisse if _ABWEICHUNG in r.meldung], (
        f"Falschmeldung trotz gepflegter kWp: {[r.meldung for r in ergebnisse]}"
    )
    ok = [r for r in ergebnisse if r.meldung.startswith("PV-Module:")]
    assert len(ok) == 1 and ok[0].schwere == CheckSeverity.OK
    assert "9.8 kWp" in ok[0].meldung


async def test_echte_abweichung_wird_weiter_gemeldet(db):
    """Der Fix darf die Prüfung nicht stilllegen: 6,0 vs. 9,8 bleibt ein Befund."""
    anlage = await _anlage_mit_modul(
        db, anlagen_kwp=9.8, spalte=None, parameter={"kwp": 6.0},
    )

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    treffer = [r for r in ergebnisse if _ABWEICHUNG in r.meldung]
    assert len(treffer) == 1, f"Befund erwartet, war: {[r.meldung for r in ergebnisse]}"
    assert treffer[0].schwere == CheckSeverity.WARNING
    assert "6.0 kWp" in treffer[0].details


async def test_kwp_in_der_spalte_bleibt_unveraendert(db):
    """Gegenprobe für den Regelfall — die Spalte hat weiterhin Vorrang."""
    anlage = await _anlage_mit_modul(
        db, anlagen_kwp=9.8, spalte=9.8, parameter={},
    )

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    assert not [r for r in ergebnisse if _ABWEICHUNG in r.meldung]


async def test_investitions_check_meldet_kein_fehlendes_kwp_bei_detailfeld(db):
    """Zweite Lesestelle derselben Klasse: „Leistung (kWp) fehlt" pro Modul.

    Hier steht der andere Legacy-Schlüssel (`leistung_kwp` im JSON) — beide
    Konventionen deckt `get_pv_kwp` seit `ed3020b2` ab.
    """
    anlage = await _anlage_mit_modul(
        db, anlagen_kwp=9.8, spalte=None, parameter={"leistung_kwp": 9.8},
    )

    ergebnisse = DatenChecker(db)._check_investitionen(anlage, [])

    assert not [r for r in ergebnisse if _FEHLT in r.meldung], (
        f"Falschmeldung trotz gepflegter kWp: {[r.meldung for r in ergebnisse]}"
    )


async def test_investitions_check_meldet_wirklich_fehlendes_kwp(db):
    """Gegenprobe: weder Spalte noch Detail-Feld ⇒ Befund bleibt."""
    anlage = await _anlage_mit_modul(
        db, anlagen_kwp=9.8, spalte=None, parameter={},
    )

    ergebnisse = DatenChecker(db)._check_investitionen(anlage, [])

    treffer = [r for r in ergebnisse if _FEHLT in r.meldung]
    assert len(treffer) == 1, f"Befund erwartet, war: {[r.meldung for r in ergebnisse]}"
    assert treffer[0].schwere == CheckSeverity.WARNING
