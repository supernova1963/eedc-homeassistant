"""Regression #408 (BMeyendriesch, 2026-09-05): der Wrapper reicht `mit_vortagsrand` durch.

Mit N-382 (`bb818a46`, v4.0.39) ruft der Aggregator
``LivePowerService.get_tagesverlauf(…, mit_vortagsrand=True)``. Das Ziel
``live_tagesverlauf_service.get_tagesverlauf`` kannte den Parameter, der
Delegations-Wrapper dazwischen nicht — ``TypeError`` bei jedem Lauf, vom
``except`` in ``aggregate_day`` zu ``keine_daten`` verschluckt. Jede Anlage
mit Stundenkurve schrieb seit dem Update keinen Tag mehr; der Vorflug des
N-388-Nachzugs (``archiv_nachzug``) meldete auf denselben Anlagen still
``uebersprungen``.

Warum keine der drei bestehenden Proben es fing: alle fuhren am Wrapper
vorbei — ``prefetched_tagesverlauf`` (Vollbackfill-Pfad), eine Attrappe, die
den neuen Parameter selbst bekam, oder ein ``patch`` auf den Wrapper als
Ganzes. Diese Proben ersetzen deshalb das **Ziel** und lassen den echten
Wrapper laufen: der Fall des Melders ist genau der Aggregator-Pfad ohne
Prefetch, und der Nachzug-Vorflug ist der zweite Aufrufer im Tag.

Schwesterdateien: test_408_wrapper_signatur_folgt_dem_ziel.py (die Klasse
dahinter als Wächter), test_aggregator_290_preserve.py (dasselbe
Aggregator-Setup, dort mit dem Wrapper als Attrappe).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.models.anlage import Anlage
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.energie_profil.source import Source

ZIEL = "backend.services.live_tagesverlauf_service.get_tagesverlauf"

# Feste Tage statt der Prozessuhr (N-167): der Aggregator behandelt nur
# `datum == heute` gesondert, jeder feste Vergangenheitstag ist der Regelfall.
GESTERN = date(2026, 9, 4)
NACHZUG_TAG = date(2026, 8, 29)

# Zwei Punkte → zwei Slots (+ Slot 0), damit `kurven_stunden` > 0 liefert
# und der Aggregator überhaupt eine Stunden-Schleife fährt.
KURVE = {
    "serien": [],
    "punkte": [
        {"zeit": "11:00", "werte": {"pv": 1000.0}},
        {"zeit": "12:00", "werte": {"pv": 1200.0}},
    ],
    "vortagsrand": [],
}


async def _anlage(db, name: str) -> Anlage:
    anlage = Anlage(
        anlagenname=name,
        leistung_kwp=10.0,
        standort_plz="10115",
        standort_land="DE",
        wechselrichter_hersteller="generic",
        sensor_mapping={},  # MQTT-Energie-Pfad: `quelle.vorhanden` über den Anker
    )
    db.add(anlage)
    await db.flush()
    return anlage


async def _mqtt_anker(db, anlage_id: int, datum: date) -> None:
    db.add(MqttEnergySnapshot(
        anlage_id=anlage_id,
        timestamp=datetime.combine(datum, datetime.min.time()) - timedelta(hours=1),
        energy_key="netzbezug",
        value_kwh=100.0,
    ))
    await db.flush()


def _nebenquellen_leer():
    """Alles außer der Tageskurve leer — die Probe misst nur die Durchreichung."""
    from contextlib import ExitStack

    from backend.services.energie_profil._helpers import StrompreisStunden

    stack = ExitStack()
    for ziel, wert in (
        ("backend.services.snapshot.aggregator.get_komponenten_tageskwh", {}),
        ("backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts", {}),
        ("backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv", {}),
        ("backend.services.energie_profil._helpers._get_strompreis_stunden",
         StrompreisStunden(sensor={}, boerse={})),
    ):
        stack.enter_context(patch(ziel, new=AsyncMock(return_value=wert)))
    return stack


@pytest.mark.asyncio
async def test_aggregator_erreicht_das_ziel_mit_vortagsrand(db) -> None:
    """Der Fall des Melders: `aggregate_day` ohne Prefetch, echter Wrapper.

    Vor dem Fix: TypeError im Wrapper → `tv_data` leer → `return None`
    (`keine_daten`). Das Ziel wurde nie erreicht.
    """
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = await _anlage(db, "Probe #408 Aggregator")
    await _mqtt_anker(db, anlage.id, GESTERN)
    await db.commit()

    ziel = AsyncMock(return_value=KURVE)
    with patch(ZIEL, new=ziel), _nebenquellen_leer():
        ergebnis = await aggregate_day(anlage, GESTERN, db, source=Source.SCHEDULER)

    assert ziel.await_count == 1, (
        "Das Ziel `live_tagesverlauf_service.get_tagesverlauf` muss über den "
        "echten Wrapper erreicht werden — vor dem Fix blieb es bei einem "
        "TypeError im Wrapper."
    )
    assert ziel.await_args.kwargs.get("mit_vortagsrand") is True, (
        "Der Aggregator verlangt seit N-382 den Vortagsrand; der Wrapper muss "
        f"`mit_vortagsrand=True` weiterreichen. Ankunft: {ziel.await_args}"
    )
    assert ergebnis is not None, (
        "Mit einer Kurve vom Ziel muss ein Tag geschrieben werden — `None` ist "
        "genau das `keine_daten` aus #408."
    )


@pytest.mark.asyncio
async def test_nachzug_vorflug_ueberspringt_nicht_wegen_wrapper(db) -> None:
    """Der zweite Aufrufer im Tag: der N-388-Vorflug in `archiv_nachzug`.

    Vor dem Fix endete er bei jedem Tag mit
    ``{"status": "uebersprungen", "grund": "vorflug_fehler"}`` — und der
    vorläufige Einstrahlungswert blieb für immer stehen.
    """
    from backend.services.energie_profil import archiv_nachzug

    anlage = await _anlage(db, "Probe #408 Nachzug")
    tag = NACHZUG_TAG
    db.add(TagesZusammenfassung(
        anlage_id=anlage.id, datum=tag, stunden_verfuegbar=2,
        datenquelle="ha_statistiken",
    ))
    await db.commit()

    ziel = AsyncMock(return_value=KURVE)
    with patch(ZIEL, new=ziel), patch.object(
        archiv_nachzug, "aggregate_day", new=AsyncMock(return_value=object()),
    ):
        ergebnis = await archiv_nachzug.nachzug_anlage(anlage, tag, db)

    assert ziel.await_count == 1 and ziel.await_args.kwargs.get("mit_vortagsrand") is True, (
        f"Der Vorflug muss das Ziel mit `mit_vortagsrand=True` erreichen. Ankunft: {ziel.await_args}"
    )
    assert ergebnis.get("grund") != "vorflug_fehler", (
        f"Der Vorflug darf nicht am Wrapper scheitern: {ergebnis}"
    )
    assert ergebnis["status"] == "ok", ergebnis
