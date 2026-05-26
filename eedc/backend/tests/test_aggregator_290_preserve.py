"""Regression #290: aggregator-Schutz für manuelle Reaggregation ohne Daten.

Hintergrund detLAN (2026-05-23): Klick auf "Tag neu aggregieren" für 21. Mai
liefert "0/24 Stunden mit Messdaten — keine Snapshots in der DB und
HA-Statistics nicht erreichbar", aber die Wärmepumpe-Spalte sprang trotzdem
von 6,3 auf 52,8 kWh. Ursache:

1. `aggregate_day` löscht zuerst die alte TZ, dann baut neu — bei 0 Stunden
   blieb nur die (selbst-geheilte, falsche) Boundary-Diff übrig.
2. Für `datum == today` lief die Snapshot-Boundary-Diff trotz fehlendem
   `snap[Folgetag 00:00]` weiter und lieferte "today-so-far aus dem
   kWh-Counter" statt einem sauberen Tagesgrenz-Wert → Drift gegen Σ-Hourly.

Diese Tests halten beide Schutzmechanismen fest:

- **Preserve**: `source == Source.MANUAL_REPAIR` + `stunden_count == 0` →
  bestehende `komponenten_kwh` / `komponenten_starts` bleiben unverändert.
- **Snapshot-Today-skip**: `datum == date.today()` ohne aktiven LTS-Pfad →
  Snapshot-`get_komponenten_tageskwh` wird NICHT aufgerufen (Snapshot-
  Variante hat das `snap[Folgetag 00:00]`-Self-Heal-Problem).

Hinweis: seit B-clean v3.34.1 (Audit §5.1.1 / #620 MartyBr) ist der
Today-SKIP NUR noch auf die Snapshot-Variante beschränkt. Bei aktivem
LTS-Pfad wird `get_komponenten_tageskwh_lts` für `datum == today` jetzt
aufgerufen — die LTS-Variante ist slot-basiert und hat kein Self-Heal-
Risiko. Verhalten geprüft in `test_symmetrie_aggregator_today.py`.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.anlage import Anlage
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.energie_profil.source import Source


async def _mqtt_anchor(db, anlage_id: int, datum: date) -> None:
    """Setzt einen MQTT-Energy-Snapshot in den 24h vor `datum`, damit
    `aggregate_day` den synthetischen 24h-Pfad nimmt statt None zu returnen.
    """
    db.add(MqttEnergySnapshot(
        anlage_id=anlage_id,
        timestamp=datetime.combine(datum, datetime.min.time()) - timedelta(hours=1),
        energy_key="netzbezug",
        value_kwh=100.0,
    ))
    await db.flush()


def _empty_tagesverlauf(_self, anlage, db, tage_zurueck):
    """Reproduziert detLAN's "Tag neu aggregieren" mit 0 Daten:
    `punkte` ist eine leere Liste statt None — `aggregate_day` durchläuft
    dann den Pfad, der NICHT früh `return None`, sondern weiter durchläuft.
    Mit leeren `punkte` bleibt `stunden_count = 0`.
    """
    return {"serien": [], "punkte": []}


@pytest.mark.asyncio
async def test_manuell_0h_behaelt_komponenten_kwh(db) -> None:
    """`aggregate_day(source=Source.MANUAL_REPAIR)` mit 0 Stunden Daten muss
    die bestehenden `komponenten_kwh` aus der alten TZ-Zeile beibehalten."""
    from backend.services.energie_profil.aggregator import aggregate_day

    # Setup: Anlage minimal + alte TZ-Zeile mit guten Werten
    anlage = Anlage(
        anlagenname="Test #290",
        leistung_kwp=10.0,
        standort_plz="10115",
        standort_land="DE",
        wechselrichter_hersteller="generic",
        sensor_mapping={},  # leer — MQTT-Energy-Pfad statt Live-Sensoren
    )
    db.add(anlage)
    await db.flush()

    gestern = date.today() - timedelta(days=1)
    alte_tz = TagesZusammenfassung(
        anlage_id=anlage.id,
        datum=gestern,
        stunden_verfuegbar=24,
        komponenten_kwh={"waermepumpe_1": 6.3, "pv_2": 12.0},
        komponenten_starts={"wp_starts_anzahl": {"1": 9}},
        datenquelle="ha_statistiken",
    )
    db.add(alte_tz)
    await _mqtt_anchor(db, anlage.id, gestern)
    await db.commit()

    # Mocks: kein Live-Tagesverlauf, keine Snapshots — `stunden_count`
    # bleibt 0, Boundary-Diff liefert nichts.
    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={"serien": [], "punkte": []}),
    ), patch(
        "backend.services.snapshot.aggregator.get_komponenten_tageskwh",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        result = await aggregate_day(anlage, gestern, db, source=Source.MANUAL_REPAIR)

    assert result is not None
    # Komponenten-Aggregate wurden bewahrt, nicht durch leere Werte ersetzt
    # (detLAN-Fall: Boundary-Diff hätte Müll geliefert, Σ-Hourly war leer)
    assert result.komponenten_kwh == {"waermepumpe_1": 6.3, "pv_2": 12.0}
    assert result.komponenten_starts == {"wp_starts_anzahl": {"1": 9}}


@pytest.mark.asyncio
async def test_scheduler_0h_setzt_komponenten_kwh_auf_none(db) -> None:
    """Scheduler-Aggregation (nicht manuell) ohne Daten löscht weiterhin —
    sonst würden alte Werte ewig bleiben, wenn der Tag legitim leer ist."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = Anlage(
        anlagenname="Test #290 b",
        leistung_kwp=10.0,
        standort_plz="10115",
        standort_land="DE",
        wechselrichter_hersteller="generic",
        sensor_mapping={},  # leer — MQTT-Energy-Pfad statt Live-Sensoren
    )
    db.add(anlage)
    await db.flush()

    gestern = date.today() - timedelta(days=1)
    alte_tz = TagesZusammenfassung(
        anlage_id=anlage.id,
        datum=gestern,
        stunden_verfuegbar=24,
        komponenten_kwh={"waermepumpe_1": 6.3},
        datenquelle="ha_statistiken",
    )
    db.add(alte_tz)
    await _mqtt_anchor(db, anlage.id, gestern)
    await db.commit()

    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={"serien": [], "punkte": []}),
    ), patch(
        "backend.services.snapshot.aggregator.get_komponenten_tageskwh",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        result = await aggregate_day(anlage, gestern, db, source=Source.SCHEDULER)

    assert result is not None
    # Scheduler bewahrt NICHT — leer ist hier die ehrliche Antwort
    assert result.komponenten_kwh is None


@pytest.mark.asyncio
async def test_heute_ueberspringt_boundary_diff(db) -> None:
    """Für `datum == today` darf die Snapshot-Boundary-Diff nicht laufen —
    sonst liefert Self-Healing aus HA-history einen Inflationswert (#290
    detLAN 30,5 vs 3,57). Seit B-clean v3.34.1 (Audit §5.1.1) gilt der
    SKIP nur noch für die Snapshot-Variante; die LTS-Variante ist slot-
    basiert und wird für today aufgerufen (Test:
    `test_symmetrie_aggregator_today.py`)."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = Anlage(
        anlagenname="Test #290 c",
        leistung_kwp=10.0,
        standort_plz="10115",
        standort_land="DE",
        wechselrichter_hersteller="generic",
        sensor_mapping={},  # leer — MQTT-Energy-Pfad statt Live-Sensoren
    )
    db.add(anlage)
    await db.flush()

    heute = date.today()
    await _mqtt_anchor(db, anlage.id, heute)
    await db.commit()

    boundary_mock = AsyncMock(return_value={"waermepumpe_99": 99.9})
    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={"serien": [], "punkte": []}),
    ), patch(
        "backend.services.snapshot.aggregator.get_komponenten_tageskwh",
        new=boundary_mock,
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        result = await aggregate_day(anlage, heute, db, source=Source.SCHEDULER)

    assert result is not None
    # Boundary-Diff darf für heute NICHT aufgerufen worden sein
    boundary_mock.assert_not_called()
    # Komponenten-Aggregate aus Σ-Hourly = leer (keine Live-Daten gemockt)
    assert result.komponenten_kwh is None
