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

from sqlalchemy import select

from backend.api.routes.investitionen import get_speicher_potential
from backend.models import Anlage, Investition, InvestitionMonatsdaten
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


def _stunde(
    anlage_id: int, tag: date, stunde: int, soc,
    einspeisung=0.0, netzbezug=0.0, batterie=None,
):
    """`batterie`: Vorzeichen-SoT der Spalte — positiv = Entladung, negativ = Ladung."""
    return TagesEnergieProfil(
        anlage_id=anlage_id, datum=tag, stunde=stunde,
        soc_prozent=soc, einspeisung_kw=einspeisung, netzbezug_kw=netzbezug,
        batterie_kw=batterie,
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


async def test_monate_werden_getrennt_mit_eigener_spanne_ausgewiesen(db):
    """Je Monat eine Spalte — mit **eigener** Spanne, ohne gemeinsame Skala.

    Der Vorgänger lieferte hier zehn Stundenzähler je SoC-Zehntel, aus denen die
    Sicht eine Heatmap mit global normierter Deckkraft malte. Genau daran ist sie
    gescheitert (Rainer, 13.08.): ein Winter-Extremwert bestimmte die Skala aller
    Monate. P10/P50/P90 je Monat kennen die anderen Monate nicht.
    """
    anlage_id = await _seed(db)
    for h in range(10, 14):
        db.add(_stunde(anlage_id, date(2026, 6, 10), h, 100.0, einspeisung=5.0))
    for h in range(10, 13):
        db.add(_stunde(anlage_id, date(2026, 7, 10), h, 15.0))
    await db.commit()

    antwort = await get_speicher_potential(anlage_id, von=None, bis=None, db=db)

    assert [(m.jahr, m.monat) for m in antwort.monate] == [(2026, 6), (2026, 7)]
    juni, juli = antwort.monate
    assert juni.stunden_mit_soc == 4
    assert (juni.soc_p10, juni.soc_p50, juni.soc_p90) == (100.0, 100.0, 100.0)
    assert juni.anteil_voll_prozent == 100.0
    assert juni.anteil_leer_prozent == 0.0
    # Der Juli-Wert hängt NICHT am Juni — das ist der ganze Punkt.
    assert (juli.soc_p10, juli.soc_p50, juli.soc_p90) == (15.0, 15.0, 15.0)
    assert juli.anteil_voll_prozent == 0.0
    assert juli.ueberschuss_kwh == 0.0


async def test_spanne_bleibt_leer_wenn_der_monat_keinen_ladestand_traegt(db):
    """Kein SoC ⇒ `None`, nicht 0 — sonst sähe „nicht gemessen" wie „leer" aus."""
    anlage_id = await _seed(db)
    for h in range(10, 14):
        db.add(_stunde(anlage_id, date(2026, 6, 10), h, None, einspeisung=5.0))
    await db.commit()

    antwort = await get_speicher_potential(anlage_id, von=None, bis=None, db=db)

    (juni,) = antwort.monate
    assert juni.stunden_mit_soc == 0
    assert juni.soc_p10 is None and juni.soc_p50 is None and juni.soc_p90 is None
    assert juni.anteil_voll_prozent is None
    assert juni.anteil_leer_prozent is None


async def test_netzgeladener_anteil_je_monat_ist_die_obergrenze(db):
    """`min(Ladung, Netzbezug)` je Stunde — nie über die Monatssumme gebildet.

    Die zweite Stunde ist der Fall, der eine Monatsbildung entlarven würde:
    Ladung **ohne** Netzbezug. Über den Monat summiert (`min(6, 4)`) käme 4 kWh
    Netzladung heraus; stundenweise sind es 2 — nur die erste Stunde hatte
    überhaupt Netzbezug, an dem sie hängen könnte.
    """
    anlage_id = await _seed(db)
    tag = date(2026, 2, 10)
    db.add(_stunde(anlage_id, tag, 2, 40.0, netzbezug=4.0, batterie=-2.0))
    db.add(_stunde(anlage_id, tag, 12, 60.0, batterie=-4.0))
    db.add(_stunde(anlage_id, tag, 20, 30.0, netzbezug=1.0, batterie=3.0))
    await db.commit()

    antwort = await get_speicher_potential(anlage_id, von=None, bis=None, db=db)

    (februar,) = antwort.monate
    assert februar.ladung_kwh == 6.0, "Entladestunden zählen nicht zur Ladung"
    assert februar.netz_ladung_kwh == 2.0
    assert februar.netz_ladung_anteil_prozent == 33.3


async def test_vollzyklen_kommen_aus_den_monats_fakten_mit_brutto_kapazitaet(db):
    """Der Durchsatz ist derselbe Wert wie im Cockpit — Quelle und Nenner belegt.

    **Nicht aus den Stundenzeilen gerechnet:** die Entladung stammt aus den
    Monats-Fakten (ADR-002/P10), der Nenner ist die **Brutto**-Kapazität
    (10 kWh), nicht die nutzbare (9,2). Beides zusammen ergibt exakt die Zahl,
    die `vollzyklen()` überall sonst liefert — 25 kWh ÷ 10 kWh = 2,5.
    Die Stundenzeilen tragen hier bewusst eine **andere** Entladung (4 kWh);
    würde die Sicht sie summieren, käme 0,4 heraus.
    """
    anlage_id = await _seed(db)
    speicher = (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )).scalars().one()
    db.add(InvestitionMonatsdaten(
        investition_id=speicher.id, jahr=2026, monat=6,
        verbrauch_daten={"entladung_kwh": 25.0, "ladung_kwh": 30.0},
    ))
    for h in range(10, 14):
        db.add(_stunde(anlage_id, date(2026, 6, 10), h, 80.0, batterie=1.0))
    await db.commit()

    antwort = await get_speicher_potential(anlage_id, von=None, bis=None, db=db)

    assert antwort.kapazitaet_brutto_kwh == 10.0
    assert antwort.kapazitaet_kwh == 9.2, "die Potentialzahl bleibt netto"
    assert antwort.monate[0].vollzyklen == 2.5


async def test_vollzyklen_bleiben_leer_ohne_gepflegte_kapazitaet(db):
    """Ohne Kapazität kein Durchsatz-Wert — `None` statt 0 (kein 0-Ersatz)."""
    anlage_id = await _seed(db, mit_speicher=False)
    for h in range(10, 14):
        db.add(_stunde(anlage_id, date(2026, 6, 10), h, 80.0, batterie=-1.0))
    await db.commit()

    antwort = await get_speicher_potential(anlage_id, von=None, bis=None, db=db)

    assert antwort.kapazitaet_brutto_kwh is None
    assert antwort.monate[0].vollzyklen is None


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
