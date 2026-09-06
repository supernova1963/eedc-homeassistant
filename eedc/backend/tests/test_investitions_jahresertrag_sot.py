"""Ein Jahres-Ertrag, eine Quelle (§9.2 Geldseite, Bauschritt 11a).

`einsparung_prognose_jahr` wurde an drei Stellen unabhängig summiert
(`crud.py` je Investition, `aussichten.py::ertrag_jahr_ges` **mit**
Aktiv-Filter, `ha_export.py::jahres_ertraege_ges` **ohne**). Die
§9.2-Geldseite hätte die Regel „Abgabe rechnet aus gemessenen Monatserlösen"
dort dreimal eingebaut. `jahresertrag_posten` beantwortet sie einmal.

Geprüft wird hier die **Regel**; das Umhängen der drei Aufrufer ist 11b/11c
und bekommt seine eigene Symmetrie-Probe.

⚠ Die erste Probe läuft bewusst über die **Datenbank** und `lade_monats_fakten`,
nicht über eine Attrappe: Der ganze Sinn des Flags ist, dass es von
`InvestitionMonatsdaten` bis in `SonstigesGeraetFakten` durchkommt. Eine
Fixture, die `hat_einspeise_erloes` selbst setzt, würde genau die Strecke
überspringen, um die es geht ([[feedback_probe_unerreichbarer_zustand]]).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.core.berechnungen.investitions_jahresertrag import (
    BEZEICHNUNG_ABGABE,
    BEZEICHNUNG_ERTRAGSFELD,
    jahresertrag_posten,
)
from backend.models import Anlage, Investition, Monatsdaten
from backend.models.investition import InvestitionMonatsdaten
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot  # noqa: F401
from backend.models.tages_energie_profil import (  # noqa: F401
    TagesEnergieProfil,
    TagesZusammenfassung,
)
from backend.services.monats_fakten import lade_monats_fakten

JAHR = 2025


async def _anlage_mit_abgabe(db, erloese: dict[int, float | None],
                             ertrag_jahr: float | None = None):
    """Eine Anlage mit EINEM Abgabe-Gerät; ``erloese`` = {Monat: Betrag|None}."""
    a = Anlage(anlagenname="abgabe", leistung_kwp=10.0,
               installationsdatum=date(JAHR, 1, 1))
    db.add(a)
    await db.flush()
    inv = Investition(
        anlage_id=a.id, typ="sonstiges", bezeichnung="Allg. Strom",
        anschaffungsdatum=date(JAHR, 1, 1), anschaffungskosten_gesamt=1000.0,
        parameter={"kategorie": "abgabe"},
        einsparung_prognose_jahr=ertrag_jahr,
    )
    db.add(inv)
    await db.flush()
    for monat, betrag in erloese.items():
        db.add(Monatsdaten(anlage_id=a.id, jahr=JAHR, monat=monat,
                           einspeisung_kwh=100.0, netzbezug_kwh=100.0))
        daten: dict = {"abgabe_kwh": 50.0}
        if betrag is not None:
            daten["einspeise_erloes_euro"] = betrag
        db.add(InvestitionMonatsdaten(investition_id=inv.id, jahr=JAHR,
                                      monat=monat, verbrauch_daten=daten))
    await db.commit()
    return a, inv


@pytest.mark.asyncio
async def test_gemessene_monatserloese_werden_mit_eigener_monatszahl_getragen(db):
    """Drei gepflegte Monate à 30 € ⇒ Posten(90 €, 3) — nicht (90 €, 12).

    Der Unterschied ist die ganze Pointe von F-20: Wer seit drei Monaten
    pflegt, hat 360 €/Jahr, nicht 90 €.
    """
    a, inv = await _anlage_mit_abgabe(db, {1: 30.0, 2: 30.0, 3: 30.0})
    fakten = await lade_monats_fakten(db, a.id, von=(JAHR, 1), bis=(JAHR, 12))

    posten = jahresertrag_posten(inv, fakten)
    assert posten is not None
    assert posten.bezeichnung == BEZEICHNUNG_ABGABE
    assert posten.summe_euro == pytest.approx(90.0)
    assert posten.monate == 3, f"Monatszahl {posten.monate} statt 3"


@pytest.mark.asyncio
async def test_gemessen_schlaegt_geschaetzt_und_addiert_nicht(db):
    """Beide gepflegt ⇒ NUR der gemessene zählt (Vorrang, P7-Bauform)."""
    a, inv = await _anlage_mit_abgabe(db, {1: 30.0}, ertrag_jahr=500.0)
    fakten = await lade_monats_fakten(db, a.id, von=(JAHR, 1), bis=(JAHR, 12))

    posten = jahresertrag_posten(inv, fakten)
    assert posten is not None
    assert posten.bezeichnung == BEZEICHNUNG_ABGABE
    assert posten.summe_euro == pytest.approx(30.0), (
        f"{posten.summe_euro} — der Schätzwert ist mitgezählt worden")


@pytest.mark.asyncio
async def test_eine_gepflegte_null_ist_eine_aussage(db):
    """Unentgeltliche Abgabe: 0 € gepflegt ⇒ BEWERTET, nicht „nicht bewertet".

    Das ist der Fall, für den `hat_einspeise_erloes` überhaupt existiert — am
    Betrag allein ist er von „nichts gepflegt" nicht zu unterscheiden.
    """
    a, inv = await _anlage_mit_abgabe(db, {1: 0.0})
    fakten = await lade_monats_fakten(db, a.id, von=(JAHR, 1), bis=(JAHR, 12))

    posten = jahresertrag_posten(inv, fakten)
    assert posten is not None, "gepflegte 0 wurde als nicht-gepflegt gelesen"
    assert posten.bezeichnung == BEZEICHNUNG_ABGABE
    assert posten.summe_euro == pytest.approx(0.0)
    assert posten.monate == 1


@pytest.mark.asyncio
async def test_ohne_jede_pflege_bleibt_es_unbewertet(db):
    """Weder Monatserlös noch Ertrag/Jahr ⇒ None. Keine Fake-0 (N-87/N-258)."""
    a, inv = await _anlage_mit_abgabe(db, {1: None, 2: None})
    fakten = await lade_monats_fakten(db, a.id, von=(JAHR, 1), bis=(JAHR, 12))

    assert jahresertrag_posten(inv, fakten) is None


@pytest.mark.asyncio
async def test_abgabe_ohne_monatswert_faellt_auf_das_ertragsfeld_zurueck(db):
    """Nur „Ertrag/Jahr" gepflegt ⇒ §8/1 gilt, und der Posten heißt auch so."""
    a, inv = await _anlage_mit_abgabe(db, {1: None}, ertrag_jahr=240.0)
    fakten = await lade_monats_fakten(db, a.id, von=(JAHR, 1), bis=(JAHR, 12))

    posten = jahresertrag_posten(inv, fakten)
    assert posten is not None
    assert posten.bezeichnung == BEZEICHNUNG_ERTRAGSFELD
    assert posten.monate == 12


@pytest.mark.asyncio
async def test_wallbox_bleibt_bei_paragraph_8_1(db):
    """Regressions-Anker für die ~120 Anwender ohne Abgabe-Gerät.

    Eine Wallbox hat das Feld `einspeise_erloes_euro` gar nicht (Registry) und
    darf von der neuen Regel nicht berührt werden — sie liest weiter
    „Ertrag/Jahr", und zwar mit `monate=12`.
    """
    a = Anlage(anlagenname="wb", leistung_kwp=10.0,
               installationsdatum=date(JAHR, 1, 1))
    db.add(a)
    await db.flush()
    wb = Investition(anlage_id=a.id, typ="wallbox", bezeichnung="Wallbox",
                     anschaffungsdatum=date(JAHR, 1, 1),
                     anschaffungskosten_gesamt=800.0,
                     einsparung_prognose_jahr=120.0)
    db.add(wb)
    db.add(Monatsdaten(anlage_id=a.id, jahr=JAHR, monat=1,
                       einspeisung_kwh=100.0, netzbezug_kwh=100.0))
    await db.commit()
    fakten = await lade_monats_fakten(db, a.id, von=(JAHR, 1), bis=(JAHR, 12))

    posten = jahresertrag_posten(wb, fakten)
    assert posten is not None
    assert posten.bezeichnung == BEZEICHNUNG_ERTRAGSFELD
    assert posten.summe_euro == pytest.approx(120.0)
    assert posten.monate == 12
