"""Daten-Checker benennt den String, dessen Modul-Details nicht zur kWp passen.

R22-2b (PN 89782, Rainer): Wer sich bei Modulanzahl oder Wp vertippt, sah bisher
nur die anlagenweite Summenregel („PV-Module kWp stimmt nicht mit Anlagenleistung
überein") — und musste alle Strings durchsuchen. Wo die optionalen Modul-Details
gepflegt sind, ist die Rechenprobe dagegen eindeutig.

Die Regel ist eine ERGÄNZUNG: ohne Modul-Details darf sie nicht anschlagen, sonst
bekäme jede Anlage ohne diese optionalen Felder einen Befund. Deshalb steht jedem
„Befund"-Test ein „kein Befund"-Test gegenüber.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage, Investition
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckSeverity

_DETAILS = "Modul-Details passen nicht zur Leistung"


async def _anlage_mit_modul(db, *, anlagen_kwp: float, spalte, parameter: dict) -> Anlage:
    anlage = Anlage(anlagenname="Test", leistung_kwp=anlagen_kwp)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach Nord-West",
        anschaffungsdatum=date(2022, 5, 1), leistung_kwp=spalte,
        ausrichtung="Nord-West", neigung_grad=30, parameter=parameter,
    ))
    await db.commit()
    return (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten))
        .where(Anlage.id == anlage.id)
    )).scalar_one()


async def test_vertippte_modulanzahl_wird_am_string_gemeldet(db):
    """18 × 400 Wp = 7,2 kWp, eingetragen 4,0 ⇒ Befund nennt String und Zahlen."""
    anlage = await _anlage_mit_modul(
        db, anlagen_kwp=4.0, spalte=4.0,
        parameter={"anzahl_module": 18, "modul_leistung_wp": 400},
    )

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    treffer = [r for r in ergebnisse if _DETAILS in r.meldung]
    assert len(treffer) == 1, f"Befund erwartet, war: {[r.meldung for r in ergebnisse]}"
    assert treffer[0].schwere == CheckSeverity.WARNING
    assert "Dach Nord-West" in treffer[0].meldung
    assert "18 Module × 400 Wp = 7.20 kWp" in treffer[0].details
    assert "4.00 kWp" in treffer[0].details


async def test_stimmige_modul_details_ergeben_keinen_befund(db):
    """9 × 400 Wp = 3,6 kWp bei eingetragenen 3,6 ⇒ still."""
    anlage = await _anlage_mit_modul(
        db, anlagen_kwp=3.6, spalte=3.6,
        parameter={"anzahl_module": 9, "modul_leistung_wp": 400},
    )

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    assert not [r for r in ergebnisse if _DETAILS in r.meldung]


async def test_ohne_modul_details_bleibt_die_regel_still(db):
    """Die Felder sind optional — ihr Fehlen ist kein Befund."""
    anlage = await _anlage_mit_modul(db, anlagen_kwp=4.0, spalte=4.0, parameter={})

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    assert not [r for r in ergebnisse if _DETAILS in r.meldung]


async def test_nur_anzahl_ohne_wp_bleibt_still(db):
    """Halb gepflegt = keine Rechenprobe möglich."""
    anlage = await _anlage_mit_modul(
        db, anlagen_kwp=4.0, spalte=4.0, parameter={"anzahl_module": 18},
    )

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    assert not [r for r in ergebnisse if _DETAILS in r.meldung]


async def test_kwp_nur_im_parameter_json_wird_mitgelesen(db):
    """#229-Klasse: die Rechenprobe vergleicht gegen `get_pv_kwp`, nicht die Spalte.

    Spalte leer, kWp nur im `parameter` — ein Spalten-Direktzugriff läse hier 0
    und meldete eine Abweichung, die es nicht gibt.
    """
    anlage = await _anlage_mit_modul(
        db, anlagen_kwp=7.2, spalte=None,
        parameter={"kwp": 7.2, "anzahl_module": 18, "modul_leistung_wp": 400},
    )

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    assert not [r for r in ergebnisse if _DETAILS in r.meldung], (
        f"Falschmeldung trotz gepflegter kWp: {[r.meldung for r in ergebnisse]}"
    )


async def test_rundungsdifferenz_unter_toleranz_ist_kein_befund(db):
    """9 × 405 Wp = 3,645 kWp gegen 3,6 ⇒ innerhalb der 0,1-kWp-Toleranz."""
    anlage = await _anlage_mit_modul(
        db, anlagen_kwp=3.6, spalte=3.6,
        parameter={"anzahl_module": 9, "modul_leistung_wp": 405},
    )

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    assert not [r for r in ergebnisse if _DETAILS in r.meldung]
