"""Der HA-Energie-Import schlägt die Batterie-Sensoren am HEUTE laufenden Speicher
vor (Nachlese 4.0.50, A2).

**Der Kommentar war wahr, der Code nicht.** In `api/routes/sensor_mapping.py` stand
bis zum 22.09.2026 über der Stelle „erste **aktive** Speicher-Investition wählen",
darunter `next((i for i in investitionen if i.typ == "speicher"), None)` — ohne
`aktiv`, ohne `stilllegungsdatum`. Die Abfrage darüber sortiert nach
`Investition.id`; nach einem Gerätetausch hat das **alte** Gerät die kleinere ID.

**Die Folge trifft genau den Anwender, der alles richtig gemacht hat:** Wer den
alten Speicher nach unserer Anleitung mit Stilllegungsdatum stehen lässt (statt ihn
zu löschen) und den neuen daneben anlegt, bekam „Aus HA übernehmen" mit den
Lade-/Entlade-Entities am **ausgebauten** Gerät angeboten. Übernommen heißt: der
neue Speicher bleibt ohne Quelle und der alte sammelt Werte, die ihn nichts angehen.
Dieselbe Klasse wie N-546, nur auf der Erfassungs- statt auf der Auswertungsseite.

**Gewählt wird das jüngste laufende Gerät** (`anschaffungsdatum`, ID als Tiebreaker)
— die Gegenrichtung in `test_zwei_laufende_speicher_…` hält fest, dass das eine
bewusste Wahl ist und nicht die alte „kleinste ID" mit Filter davor.

⚠ **Feste Daten, kein `date.today()`** (`test_konformitaet_echte_uhr_in_tests.py`).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date

import pytest

from backend.api.routes import sensor_mapping as sm
from backend.models import Anlage, Investition
from backend.services.ha_energy_service import (
    BatterySuggestion,
    EnergySourceSuggestion,
    HAEnergySuggestions,
)

STILLGELEGT_VERGANGENHEIT = date(2021, 3, 31)
STILLGELEGT_ZUKUNFT = date(2099, 12, 31)

LADUNG = "sensor.akku_ladung"
ENTLADUNG = "sensor.akku_entladung"


@pytest.fixture
def route_session(monkeypatch, db):
    """Die Route öffnet ihre eigene Sitzung (`get_session`) — hier die der Probe."""
    @asynccontextmanager
    async def _fake():
        yield db

    monkeypatch.setattr(sm, "get_session", _fake)
    return db


def _vorschlaege() -> HAEnergySuggestions:
    return HAEnergySuggestions(
        available=True,
        energy_sources=[EnergySourceSuggestion(feld="netzbezug", entity_id="sensor.bezug")],
        battery=BatterySuggestion(ladung_entity=LADUNG, entladung_entity=ENTLADUNG),
    )


async def _seed(db, *, aktiv_alt: bool = True,
                stillgelegt: date | None = STILLGELEGT_VERGANGENHEIT) -> tuple[int, int, int]:
    """Anlage, dann **erst** das alte Gerät (kleinere ID), dann das neue."""
    anlage = Anlage(anlagenname="A2", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()

    alt = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher alt",
        anschaffungsdatum=date(2015, 1, 1),
        parameter={"kapazitaet_kwh": 5.06},
        aktiv=aktiv_alt, stilllegungsdatum=stillgelegt,
    )
    db.add(alt)
    await db.flush()
    neu = Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher neu",
        anschaffungsdatum=date(2025, 6, 1),
        parameter={"kapazitaet_kwh": 12.8},
    )
    db.add(neu)
    await db.commit()
    assert alt.id < neu.id, "Die Probe lebt davon, dass das alte Gerät vorn steht"
    return anlage.id, alt.id, neu.id


async def _suggest(monkeypatch, anlage_id: int):
    monkeypatch.setattr(sm, "get_ha_energy_suggestions", _vorschlaege)
    return await sm.get_ha_energy_suggest(anlage_id)


def _batterie_ziele(antwort) -> set[int]:
    return {m.inv_id for m in antwort.investition_matches if m.feld in ("ladung_kwh", "entladung_kwh")}


async def test_stillgelegter_speicher_bekommt_die_batterie_sensoren_nicht(
    db, route_session, monkeypatch
):
    anlage_id, alt_id, neu_id = await _seed(db)

    antwort = await _suggest(monkeypatch, anlage_id)

    assert _batterie_ziele(antwort) == {neu_id}, (
        "ungefiltert gewann das alte Gerät über die kleinere ID"
    )
    assert str(alt_id) not in antwort.investitionen
    assert antwort.investitionen[str(neu_id)] == {
        "ladung_kwh": LADUNG, "entladung_kwh": ENTLADUNG,
    }


async def test_abgewaehlter_speicher_ohne_datum_bekommt_sie_auch_nicht(
    db, route_session, monkeypatch
):
    """`aktiv=False` = wie gelöscht — dieselbe Regel wie in `investition_filter`."""
    anlage_id, alt_id, neu_id = await _seed(db, aktiv_alt=False, stillgelegt=None)

    antwort = await _suggest(monkeypatch, anlage_id)

    assert _batterie_ziele(antwort) == {neu_id}
    assert str(alt_id) not in antwort.investitionen


async def test_zwei_laufende_speicher_der_juengere_gewinnt(
    db, route_session, monkeypatch
):
    """Erweiterung statt Tausch: einer von beiden, und zwar der jüngere.

    Das ist die **Gegenrichtung** zum alten Verhalten — ohne diesen Fall bliebe
    offen, ob der Filter bloß vorgeschaltet wurde und weiter die kleinste ID
    gewinnt.
    """
    anlage_id, alt_id, neu_id = await _seed(db, stillgelegt=None)

    antwort = await _suggest(monkeypatch, anlage_id)

    assert _batterie_ziele(antwort) == {neu_id}
    assert str(alt_id) not in antwort.investitionen


async def test_stilllegung_in_der_zukunft_ist_noch_kein_ausbau(
    db, route_session, monkeypatch
):
    """Angekündigt ist nicht ausgebaut — der Stichtag wird gelesen, nicht das Feld.

    Beide laufen, der jüngere gewinnt; das alte Gerät ist trotz gesetztem
    Datum nicht ausgeschlossen.
    """
    anlage_id, alt_id, neu_id = await _seed(db, stillgelegt=STILLGELEGT_ZUKUNFT)

    antwort = await _suggest(monkeypatch, anlage_id)

    assert _batterie_ziele(antwort) == {neu_id}


async def test_nur_ein_stillgelegter_speicher_gibt_keinen_vorschlag(
    db, route_session, monkeypatch
):
    """Kein laufendes Gerät ⇒ kein Batterie-Vorschlag, und die Route bleibt heil.

    Ein Vorschlag auf ein ausgebautes Gerät wäre schlimmer als keiner: er sieht
    nach einer Zuordnung aus, die eedc geprüft hat.
    """
    anlage = Anlage(anlagenname="A2-leer", leistung_kwp=10.0)
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="speicher", bezeichnung="Speicher alt",
        anschaffungsdatum=date(2015, 1, 1),
        stilllegungsdatum=STILLGELEGT_VERGANGENHEIT,
    ))
    await db.commit()

    antwort = await _suggest(monkeypatch, anlage.id)

    assert _batterie_ziele(antwort) == set()
    assert antwort.investitionen == {}
    assert antwort.basis["netzbezug"] == "sensor.bezug", "der Rest der Antwort bleibt"
