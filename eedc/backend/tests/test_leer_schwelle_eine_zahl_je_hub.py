"""Speicher-Hub: eine Leer-Schwelle, nicht zwei (Nachlese 4.0.50, A4).

**Zwei Blöcke derselben Fläche nannten zwei Zahlen.** Sizing-Simulator und
Speicher-Potential stehen im selben Komponenten-Hub und leiten „ab wann gibt
dieser Speicher nichts mehr ab?" aus derselben Formel ab
(`core/berechnungen/speicher_potential.leer_schwelle_prozent`, #379). Der Eingang
war verschieden:

* **Sizing** (`services/speicher_sizing_service.py`) — die **rohen** Summen.
* **Potential** (`api/routes/investitionen/speicher_potential.py`) — die auf eine
  Nachkommastelle **gerundeten** Antwortfelder.

Bei 10,24 kWh netto / 12,8 kWh brutto sagte dieselbe Anlage im selben Hub
**23,0 %** und **23,3 %**. Die Rundung ist eine Anzeigeentscheidung; sie darf
keine Rechengröße verschieben — und die Schwelle ist eine: sie entscheidet in
`messe_soc_nutzung` über `tage_bis_leer` und in `berechne_zusatzpotential`, ab
wann Netzbezug als Fehlmenge zählt.

**Der Ausschlag ist klein und die Wirkung nicht.** 23,3 statt 23,0 sind 0,3
Prozentpunkte; eine Nacht, deren Tiefpunkt bei 23,2 % liegt, gilt in einem Block
als leergelaufen und im anderen nicht. Genau diese Klasse zeigt
`test_die_0_3_pp_entscheiden_einen_zyklus`.

⚠ **Feste Daten, kein `date.today()`** (`test_konformitaet_echte_uhr_in_tests.py`).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from backend.api.routes.investitionen import (
    get_speicher_potential,
    get_speicher_sizing,
)
from backend.models import Anlage, Investition, Strompreis
from backend.models.tages_energie_profil import TagesEnergieProfil

#: Die Melder-Anlage aus N-546 — 12,8 brutto / 10,24 netto.
#: (1 − 10,24/12,8) × 100 = 20,0 + 3 pp Toleranz = **23,0 %**.
#: Gerundet: (1 − 10,2/12,8) × 100 = 20,3125 + 3 = 23,3125 ⇒ 23,3 %.
KAPAZITAET = {"kapazitaet_kwh": 12.8, "nutzbare_kapazitaet_kwh": 10.24,
              "wirkungsgrad_prozent": 95}


async def _seed(db) -> int:
    anlage = Anlage(anlagenname="A4", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher",
        anschaffungsdatum=date(2025, 6, 1), parameter=dict(KAPAZITAET),
    ))
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=35.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    return anlage.id


def _tag(db, anlage_id: int, tag: date, *, soc: float):
    """Ein voller Tag; ``soc`` ist der nächtliche Tiefpunkt, tagsüber 80 %."""
    for h in range(24):
        db.add(TagesEnergieProfil(
            anlage_id=anlage_id, datum=tag, stunde=h,
            pv_kw=6.0 if 10 <= h < 16 else 0.0, verbrauch_kw=0.7,
            soc_prozent=80.0 if 10 <= h < 16 else soc,
        ))


def _zyklus_tag(db, anlage_id: int, tag: date, *, nacht_soc: float):
    """Ein Tag mit vollem Speicher am Mittag und Netzbezug in der Nacht.

    Mittags voll (100 %) **und** Einspeisung ⇒ ein Überschuss-Ereignis, das
    einen Zyklus öffnet bzw. schließt. Nachts der Tiefpunkt samt Netzbezug —
    genau die Menge, die als Fehlmenge zählt, **sobald** der Speicher als leer
    gilt. Lückenlos 24 Stunden, wie `berechne_zusatzpotential` es verlangt.
    """
    for h in range(24):
        if 10 <= h < 16:
            db.add(TagesEnergieProfil(
                anlage_id=anlage_id, datum=tag, stunde=h,
                pv_kw=6.0, verbrauch_kw=0.7,
                soc_prozent=100.0, einspeisung_kw=5.0,
            ))
        elif h < 8:
            db.add(TagesEnergieProfil(
                anlage_id=anlage_id, datum=tag, stunde=h,
                pv_kw=0.0, verbrauch_kw=1.0,
                soc_prozent=nacht_soc, netzbezug_kw=1.0,
            ))
        else:
            db.add(TagesEnergieProfil(
                anlage_id=anlage_id, datum=tag, stunde=h,
                pv_kw=0.0, verbrauch_kw=0.7, soc_prozent=60.0,
            ))


async def _sizing(db, anlage_id: int):
    return await get_speicher_sizing(
        anlage_id, von=None, bis=None, richtpreis_eur_je_kwh=None, db=db,
    )


async def _potential(db, anlage_id: int):
    return await get_speicher_potential(anlage_id, von=None, bis=None, db=db)


async def test_beide_sichten_nennen_dieselbe_leer_schwelle(db):
    """23,0 % hier wie dort — vorher 23,3 % im Potential."""
    anlage_id = await _seed(db)
    for i in range(3):
        _tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i), soc=30.0)
    await db.commit()

    potential = await _potential(db, anlage_id)

    assert potential.soc_leer_prozent == 23.0, "aus 10,24/12,8, nicht aus 10,2/12,8"
    assert potential.soc_leer_ist_abgeleitet is True
    # Die Antwortfelder bleiben gerundet — das ist Absicht und keine Nebenfolge.
    assert potential.kapazitaet_kwh == 10.2
    assert potential.kapazitaet_brutto_kwh == 12.8


async def test_die_0_3_pp_entscheiden_einen_zyklus(db):
    """Ein Tiefpunkt zwischen 23,0 und 23,3 — hier trennen sich die zwei Zahlen.

    23,2 % liegt **über** der richtigen Schwelle (23,0) und **unter** der alten
    gerundeten (23,3). Mit der alten galt die Nacht als aufgebraucht: der
    Netzbezug danach zählte als Fehlmenge, der Zyklus als „leergelaufen", und
    die Sicht schlug einen größeren Speicher vor. Mit der richtigen Schwelle
    hatte der Speicher noch Reserve — mehr Kapazität hätte nichts gebracht.
    Derselbe Speicher, dieselben Stunden, zwei Empfehlungen.
    """
    anlage_id = await _seed(db)
    for i in range(2):
        _zyklus_tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i), nacht_soc=23.2)
    await db.commit()

    potential = await _potential(db, anlage_id)
    sizing = await _sizing(db, anlage_id)

    assert potential.soc_leer_prozent == 23.0
    assert potential.soc_min_prozent == pytest.approx(23.2)
    assert potential.zyklen_gesamt >= 1, "ohne Zyklus wäre die Probe blind"
    assert potential.zyklen_leergelaufen == 0, (
        "mit der alten Schwelle 23,3 % wäre der Zyklus leergelaufen"
    )
    assert potential.nutzbares_zusatzpotential_kwh == 0.0, (
        "und genau dann stünde hier eine Empfehlung für einen größeren Speicher"
    )
    assert sizing.soc_nutzung is not None
    assert sizing.soc_nutzung.tage_bis_leer == 0, "dieselbe Entscheidung im Sizing"


async def test_knapp_unter_der_schwelle_zaehlt_weiter_als_leer(db):
    """Die Gegenrichtung: 22,9 % ist unter 23,0 — die Regel selbst bleibt scharf.

    Ohne diesen Fall bliebe offen, ob der Zyklus oben nur deshalb nicht
    leerlief, weil die Schwelle gar nicht mehr wirkt.
    """
    anlage_id = await _seed(db)
    for i in range(2):
        _zyklus_tag(db, anlage_id, date(2026, 6, 1) + timedelta(days=i), nacht_soc=22.9)
    await db.commit()

    potential = await _potential(db, anlage_id)
    sizing = await _sizing(db, anlage_id)

    assert potential.soc_leer_prozent == 23.0
    assert potential.zyklen_leergelaufen >= 1
    assert potential.nutzbares_zusatzpotential_kwh > 0
    assert sizing.soc_nutzung is not None
    assert sizing.soc_nutzung.tage_bis_leer == 2


async def test_ohne_gepflegte_netto_kapazitaet_bleibt_der_rueckfall(db):
    """Wer nichts pflegt, sieht exakt das Verhalten von vorher (Abnahmekriterium).

    Ohne `nutzbare_kapazitaet_kwh` fällt `get_speicher_nutzbare_kapazitaet_kwh`
    still auf brutto zurück ⇒ netto == brutto ⇒ keine Reserve ⇒ `SOC_LEER_PROZENT`.
    """
    anlage = Anlage(anlagenname="A4-roh", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher",
        anschaffungsdatum=date(2025, 6, 1),
        parameter={"kapazitaet_kwh": 12.8, "wirkungsgrad_prozent": 95},
    ))
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=35.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    for i in range(3):
        _tag(db, anlage.id, date(2026, 6, 1) + timedelta(days=i), soc=30.0)
    await db.commit()

    potential = await _potential(db, anlage.id)

    assert potential.soc_leer_prozent == 5.0, "SOC_LEER_PROZENT"
    assert potential.soc_leer_ist_abgeleitet is False


async def test_ohne_speicher_bleibt_die_antwort_heil(db):
    """Die Hoisting-Umstellung der beiden Summen darf den Leerfall nicht kippen.

    Vor A4 standen `summe`/`summe_brutto` innerhalb von `if speicher:`. Sie
    stehen jetzt außerhalb — über einer **leeren** Liste, und `sum(())` ist 0.
    """
    anlage = Anlage(anlagenname="A4-leer", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Strompreis(
        anlage_id=anlage.id, gueltig_ab=date(2024, 1, 1),
        netzbezug_arbeitspreis_cent_kwh=35.0, einspeiseverguetung_cent_kwh=8.0,
    ))
    await db.commit()

    potential = await _potential(db, anlage.id)

    assert potential.anzahl_speicher == 0
    assert potential.kapazitaet_kwh is None
    assert potential.kapazitaet_brutto_kwh is None
    assert potential.soc_leer_prozent == 5.0
    assert potential.soc_leer_ist_abgeleitet is False
