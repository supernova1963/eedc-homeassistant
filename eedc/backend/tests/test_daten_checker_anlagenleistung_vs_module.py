"""Der Abgleich „Anlagenleistung ≠ Σ Module" im Stammdaten-Check (F-58).

Schwesterdatei: `test_daten_checker_kwp_detailfeld.py` — die prüft die
Rechenprobe *innerhalb* einer Modul-Investition (Anzahl × Wp gegen die
gepflegte kWp), diese hier die Stufe darüber: die Anlagenleistung gegen die
Summe der Investitionen.

**Warum es diese Prüfung (wieder) gibt.** Sie existierte bis zum 2026-08-04
und ist mit N-76 Stufe 1 entfallen — dort wurde das Balkonkraftwerk aus der
Prüfsumme genommen und der DC/AC-Verhältnis-Check eingeführt, der Abgleich
selbst aber ersatzlos gestrichen. Danach hielt **nichts** mehr die
Anlagenleistung gegen die Investitionen, obwohl sie der Nenner jeder
spezifischen Kennzahl ist. Gemeldet hat es NoahPaulick (simon42 T89667 #188,
v4.0.26): nach dem Trennen einer gemeinsam erfassten Anlage meldete der
Daten-Checker ihm vier Tage „PV-Doppelerfassung" — auf Rohdaten, die stimmen.

**Die Zweiseitigkeit ist der Kern.** Fachlich gehört ein Balkonkraftwerk nicht
in die kWp der Hauptanlage (eigene MaStR-Registrierung, N-76 Stufe 1). Wer es
trotzdem eingerechnet hat, hat aber nichts falsch gemessen. Deshalb schweigt
der Check, wenn der gepflegte Wert zu **einer** der beiden Summen passt —
sonst bekäme jeder BKW-Anwender wieder die Meldung, die Stufe 1 gerade
abgeschafft hat ([[feedback_daten_checker_kein_akzeptiert]]).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models import Anlage
from backend.services.daten_checker import (
    CheckKategorie,
    CheckSeverity,
    DatenChecker,
)
from backend.tests.factories import mach_investition

# Festes Datum statt der Prozessuhr — die Suite läuft in drei Zeitzonen
# (Berlin · UTC · Auckland), ein fester Wert ist in allen dreien derselbe.
STICHTAG = date(2026, 8, 24)


async def _seed(db, *, anlage_kwp: float, module: list[float], bkw: list[float] = ()) -> int:
    anlage = Anlage(anlagenname="Test", leistung_kwp=anlage_kwp, standort_land="DE")
    db.add(anlage)
    await db.flush()
    for kwp in module:
        db.add(mach_investition("pv-module", anlage_id=anlage.id, leistung_kwp=kwp))
    for kwp in bkw:
        db.add(mach_investition("balkonkraftwerk", anlage_id=anlage.id, leistung_kwp=kwp))
    await db.flush()
    return anlage.id


async def _run(db, anlage_id: int):
    """Ladeweg wie `check_anlage` — mit Investitionen (kein Lazy-Load)."""
    anlage = (await db.execute(
        select(Anlage)
        .options(selectinload(Anlage.investitionen))
        .where(Anlage.id == anlage_id)
    )).scalar_one()
    checker = DatenChecker(db)
    # Wie `_check_stammdaten` es bildet: nur die HEUTE aktiven Module. Ohne
    # den Filter prüfte diese Datei eine Summe, die es produktiv nicht gibt.
    summe_pv = sum(
        i.leistung_kwp or 0
        for i in anlage.investitionen
        if i.typ == "pv-module" and i.ist_aktiv_an(STICHTAG)
    )
    return checker._check_anlagenleistung_gegen_module(anlage, summe_pv, STICHTAG)


def _warnungen(ergebnisse):
    return [
        e for e in ergebnisse
        if e.kategorie == CheckKategorie.STAMMDATEN.value
        and e.schwere == CheckSeverity.WARNING
    ]


async def test_gepflegter_wert_passt_zur_modulsumme_schweigt(db):
    """31,24 kWp gepflegt, 31,24 kWp Module → keine Meldung."""
    anlage_id = await _seed(db, anlage_kwp=31.24, module=[31.24])
    assert _warnungen(await _run(db, anlage_id)) == []


async def test_noahs_fall_haelfte_der_modulsumme_meldet(db):
    """Der gemeldete Fall: gepflegt 15,62, Module 31,24 → WARNING.

    Genau diese Abweichung ließ `_check_pv_ueber_erfassung` einen spezifischen
    Tagesertrag von 10,7 statt 5,35 kWh/kWp errechnen — Faktor 2, weil der
    Nenner halb so groß war wie die Anlage.
    """
    anlage_id = await _seed(db, anlage_kwp=15.62, module=[31.24])
    warnungen = _warnungen(await _run(db, anlage_id))
    assert len(warnungen) == 1
    assert "15.62" in warnungen[0].meldung and "31.24" in warnungen[0].meldung
    # Der Anwender muss beide Wege sehen — eedc leitet nichts ab.
    assert "Einstellungen" in warnungen[0].details
    assert "Investitionen" in warnungen[0].details


async def test_bkw_eingerechnet_gilt_als_zulaessige_konvention(db):
    """Gepflegt 10,8 = Module 10,0 + BKW 0,8 → keine Meldung.

    Das ist der Fall, der N-76 Stufe 1 ausgelöst hat: am eigenen Demo-Bestand
    stand 20,0 gegen 20,8, und jeder BKW-Anwender bekam eine Abweichung
    gemeldet, ohne dass etwas falsch gepflegt war.
    """
    anlage_id = await _seed(db, anlage_kwp=10.8, module=[10.0], bkw=[0.8])
    assert _warnungen(await _run(db, anlage_id)) == []


async def test_bkw_nicht_eingerechnet_gilt_ebenso(db):
    """Gepflegt 10,0 bei Modulen 10,0 + BKW 0,8 → keine Meldung.

    Die fachlich korrekte Konvention (BKW ist eine eigene Anlage) muss
    genauso schweigen wie die andere — sonst erzieht der Check zum Eintragen
    falscher Zahlen, damit Ruhe ist.
    """
    anlage_id = await _seed(db, anlage_kwp=10.0, module=[10.0], bkw=[0.8])
    assert _warnungen(await _run(db, anlage_id)) == []


async def test_passt_zu_keiner_der_beiden_summen_meldet(db):
    """Gepflegt 25,0 bei Modulen 10,0 + BKW 0,8 → WARNING mit BKW-Zusatz."""
    anlage_id = await _seed(db, anlage_kwp=25.0, module=[10.0], bkw=[0.8])
    warnungen = _warnungen(await _run(db, anlage_id))
    assert len(warnungen) == 1
    assert "Balkonkraftwerk" in warnungen[0].details


async def test_toleranz_faengt_rundung_nicht_pflege(db):
    """0,05 kWp Abweichung schweigt, 0,5 kWp meldet."""
    still = await _seed(db, anlage_kwp=10.05, module=[10.0])
    assert _warnungen(await _run(db, still)) == []
    laut = await _seed(db, anlage_kwp=10.5, module=[10.0])
    assert len(_warnungen(await _run(db, laut))) == 1


async def test_ohne_erzeuger_investitionen_kein_vergleich(db):
    """Keine Module gepflegt → nichts zu vergleichen, keine Meldung.

    Der Referenzwert ist dann die einzige Angabe und bleibt gültig; dass
    Module fehlen, meldet der Stammdaten-Check an anderer Stelle.
    """
    anlage_id = await _seed(db, anlage_kwp=10.0, module=[])
    assert _warnungen(await _run(db, anlage_id)) == []


async def test_stillgelegter_erzeuger_zaehlt_nicht_mehr_mit(db):
    """Ein stillgelegtes BKW gehört nicht mehr in die Vergleichssumme.

    Der Fall trifft gezielt die **BKW-Summe im Check**, nicht die vom Aufrufer
    übergebene Modulsumme: gepflegt 10,8 = 10,0 Module + 0,8 aktives BKW. Ein
    zusätzliches, 2024 stillgelegtes BKW über 5,0 kWp darf die Summe nicht auf
    15,8 heben — sonst passte der gepflegte Wert zu keiner der beiden Summen
    und der Check meldete nach jedem Rückbau eine Abweichung, obwohl der
    Anwender korrekt gepflegt hat.

    ⚠ Ein erster Entwurf dieser Probe hängte die Stilllegung an ein PV-Modul.
    Er blieb grün, als der Aktiv-Filter im Helper entfernt wurde: die vom
    Aufrufer übergebene Modulsumme passte dort ohnehin schon, der Filter des
    Helpers wurde nie erreicht ([[feedback_beweis_familie]]).
    """
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.8, standort_land="DE")
    db.add(anlage)
    await db.flush()
    db.add(mach_investition("pv-module", anlage_id=anlage.id, leistung_kwp=10.0))
    db.add(mach_investition("balkonkraftwerk", anlage_id=anlage.id, leistung_kwp=0.8))
    db.add(mach_investition(
        "balkonkraftwerk", anlage_id=anlage.id, leistung_kwp=5.0,
        stilllegungsdatum=date(2024, 6, 30),
    ))
    await db.flush()
    assert _warnungen(await _run(db, anlage.id)) == []
