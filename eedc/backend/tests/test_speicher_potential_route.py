"""Die Potentialanalyse liefert am Endpoint, was die Formel rechnet (#358 Phase 2).

Die Layer-Tests in `test_speicher_zusatzpotential.py` prüfen die Formel; hier geht
es um die Strecke davor: Stunden aus `TagesEnergieProfil` laden, in kWh übersetzen,
je Monat gruppieren, und die **Kapazität netto** ausweisen (v4.0.2-Kanon).

Der Sommer-Fall bildet die Messung nach, die das Paket ausgelöst hat: viel
Überschuss bei vollem Speicher, aber nie eine leere Nacht — die Route muss dann
`0` melden und `deckelung_greift` setzen, nicht die Überschusssumme.
"""

from __future__ import annotations

from datetime import date

from backend.api.routes.investitionen import get_speicher_potential
from backend.models import Anlage, Investition
from backend.models.tages_energie_profil import TagesEnergieProfil


async def _seed(db, *, mit_speicher: bool = True) -> int:
    anlage = Anlage(anlagenname="Potential-Test", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    if mit_speicher:
        db.add(Investition(
            anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher 10 kWh",
            anschaffungsdatum=date(2024, 1, 1),
            parameter={"kapazitaet_kwh": 10, "nutzbare_kapazitaet_kwh": 9.2},
        ))
    return anlage.id


def _stunde(anlage_id: int, tag: date, stunde: int, soc, einspeisung=0.0, netzbezug=0.0):
    return TagesEnergieProfil(
        anlage_id=anlage_id, datum=tag, stunde=stunde,
        soc_prozent=soc, einspeisung_kw=einspeisung, netzbezug_kw=netzbezug,
    )


async def test_sommerfall_meldet_null_statt_der_ueberschusssumme(db):
    """Voller Speicher, viel Einspeisung — aber die Nacht endet bei 40 %."""
    anlage_id = await _seed(db)
    tag = date(2026, 6, 10)
    for h in range(10, 18):
        db.add(_stunde(anlage_id, tag, h, 100.0, einspeisung=8.0))
    for h in range(18, 24):
        db.add(_stunde(anlage_id, tag, h, 40.0, netzbezug=0.5))
    await db.commit()

    antwort = await get_speicher_potential(anlage_id, von=None, bis=None, db=db)

    assert antwort.ueberschuss_kwh == 64.0
    assert antwort.nutzbares_zusatzpotential_kwh == 0.0
    assert antwort.deckelung_greift is True
    assert antwort.zyklen_leergelaufen == 0
    assert antwort.stunden_voll == 8


async def test_leergelaufene_nacht_wird_bis_zum_nachtbezug_gutgeschrieben(db):
    anlage_id = await _seed(db)
    tag = date(2026, 3, 10)
    for h in range(10, 14):
        db.add(_stunde(anlage_id, tag, h, 100.0, einspeisung=5.0))
    db.add(_stunde(anlage_id, tag, 20, 30.0))
    for h in (21, 22, 23):
        db.add(_stunde(anlage_id, tag, h, 2.0, netzbezug=1.5))
    await db.commit()

    antwort = await get_speicher_potential(anlage_id, von=None, bis=None, db=db)

    assert antwort.ueberschuss_kwh == 20.0
    assert antwort.nutzbares_zusatzpotential_kwh == 4.5
    assert antwort.zyklen_leergelaufen == 1


async def test_monate_werden_getrennt_ausgewiesen_mit_soc_bins(db):
    """Je Monat eine Zeile — die Heatmap braucht die SoC-Verteilung."""
    anlage_id = await _seed(db)
    for h in range(10, 14):
        db.add(_stunde(anlage_id, date(2026, 6, 10), h, 100.0, einspeisung=5.0))
    for h in range(10, 13):
        db.add(_stunde(anlage_id, date(2026, 7, 10), h, 15.0))
    await db.commit()

    antwort = await get_speicher_potential(anlage_id, von=None, bis=None, db=db)

    assert [(m.jahr, m.monat) for m in antwort.monate] == [(2026, 6), (2026, 7)]
    juni, juli = antwort.monate
    assert sum(juni.soc_bins) == 4
    assert juni.soc_bins[-1] == 4, "100 % gehört in den obersten Bin, nicht daneben"
    assert juli.soc_bins[1] == 3, "15 % liegt im Bin 10–20 %"
    assert juli.ueberschuss_kwh == 0.0


async def test_kapazitaet_wird_netto_ausgewiesen(db):
    """v4.0.2-Kanon: wo der Speicher durchfahren wird, gilt der nutzbare Hub."""
    anlage_id = await _seed(db)
    db.add(_stunde(anlage_id, date(2026, 6, 10), 12, 50.0))
    await db.commit()

    antwort = await get_speicher_potential(anlage_id, von=None, bis=None, db=db)

    assert antwort.kapazitaet_kwh == 9.2, "9,2 ist netto; 10 wäre die Nennkapazität"
    assert antwort.anzahl_speicher == 1


async def test_zeitraum_grenzen_werden_beachtet(db):
    anlage_id = await _seed(db)
    for h in range(10, 14):
        db.add(_stunde(anlage_id, date(2026, 6, 10), h, 100.0, einspeisung=5.0))
    for h in range(10, 14):
        db.add(_stunde(anlage_id, date(2026, 7, 10), h, 100.0, einspeisung=9.0))
    await db.commit()

    nur_juni = await get_speicher_potential(
        anlage_id, von=date(2026, 6, 1), bis=date(2026, 6, 30), db=db
    )

    assert nur_juni.ueberschuss_kwh == 20.0
    assert [(m.jahr, m.monat) for m in nur_juni.monate] == [(2026, 6)]
    assert nur_juni.von == date(2026, 6, 10)


async def test_anlage_ohne_stundendaten_antwortet_leer_statt_zu_werfen(db):
    """Eine neue Anlage hat noch keine Historie — das ist kein Fehler."""
    anlage_id = await _seed(db)
    await db.commit()

    antwort = await get_speicher_potential(anlage_id, von=None, bis=None, db=db)

    assert antwort.tage_mit_daten == 0
    assert antwort.monate == []
    assert antwort.nutzbares_zusatzpotential_kwh == 0.0
    assert antwort.deckelung_greift is False
    assert antwort.von is None


async def test_anlage_ohne_speicher_liefert_keine_kapazitaet(db):
    """Ohne Speicher gibt es keine Kapazität — aber die Route hält.

    Die SoC-Reihe kann trotzdem gefüllt sein (Altbestand, gelöschte Investition),
    deshalb ist das kein 404.
    """
    anlage_id = await _seed(db, mit_speicher=False)
    db.add(_stunde(anlage_id, date(2026, 6, 10), 12, 100.0, einspeisung=3.0))
    await db.commit()

    antwort = await get_speicher_potential(anlage_id, von=None, bis=None, db=db)

    assert antwort.anzahl_speicher == 0
    assert antwort.kapazitaet_kwh is None
