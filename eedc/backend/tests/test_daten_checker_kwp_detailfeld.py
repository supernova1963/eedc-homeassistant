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

⚠ **Die Meldung selbst gibt es seit N-76/#354 nicht mehr** (Entscheid Gernot
2026-08-04): der Abgleich „Σ Module ≠ Anlagenleistung" kannte Überbelegung
nicht und ist durch die DC/AC-Prüfung ersetzt. Was diese Datei belegt, ist
davon unberührt — **dass der SoT-Helper gelesen wird und nicht die Spalte**.
Der Beleg hängt jetzt an der ausgewiesenen Summe statt an einer WARNING: steht
die kWp nur im `parameter`-JSON, muss sie in der Summe auftauchen.
"""

from __future__ import annotations



from backend.models import Anlage
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckSeverity
from backend.tests import factories

_ABWEICHUNG = "PV-Module kWp stimmt nicht mit Anlagenleistung überein"
_FEHLT = "Leistung (kWp) fehlt"


async def _anlage_mit_modul(db, *, anlagen_kwp: float, spalte, parameter: dict) -> Anlage:
    return await factories.anlage_mit_modul(
        db, anlagen_kwp=anlagen_kwp, spalte=spalte, parameter=parameter,
        bezeichnung="Dach Süd", ausrichtung="Süd",
    )


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


async def test_der_detailfeld_wert_landet_in_der_ausgewiesenen_summe(db):
    """Der Fix darf die Lesestelle nicht stilllegen.

    Früher belegte das die WARNING „6,0 vs. 9,8" — die Meldung ist mit #354
    entfallen. Der Beleg wandert damit auf die Summe selbst: läse der Check
    weiter die Spalte, stünde hier 0,0 kWp statt 6,0.
    """
    anlage = await _anlage_mit_modul(
        db, anlagen_kwp=9.8, spalte=None, parameter={"kwp": 6.0},
    )

    ergebnisse = DatenChecker(db)._check_stammdaten(anlage)

    ok = [r for r in ergebnisse if r.meldung.startswith("PV-Module:")]
    assert len(ok) == 1, f"Summenzeile erwartet, war: {[r.meldung for r in ergebnisse]}"
    assert "6.0 kWp" in ok[0].meldung, "Spalten-Direktzugriff hätte 0,0 gemeldet"


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
