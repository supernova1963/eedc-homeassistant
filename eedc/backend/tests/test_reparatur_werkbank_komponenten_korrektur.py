"""
Regression #290 v3.33.0: Reparatur-Werkbank korrigiert `komponenten_kwh`.

In v3.32.4 wurde `aggregate_day(datenquelle="manuell")` (heute
`source=Source.MANUAL_REPAIR`) als Symptompatch generell vom Boundary-Diff
ausgeschlossen — wegen des damals buggy LTS-Aggregators. Mit dem strukturellen
Fix in v3.33.0 ([komponenten_beitraege.py](../services/snapshot/komponenten_beitraege.py))
liefert Boundary-Diff jetzt korrekte Per-Typ-Werte. Daher:

- Bei `source=Source.MANUAL_REPAIR` MUSS Boundary-Diff laufen (sonst Reparatur
  unwirksam für die einzigen Werte, die der User reparieren wollte).
- Bei `datum >= today` BLEIBT der Skip — Self-Healing kann hier den
  AKTUELLEN Counter-Stand statt einen Tagesgrenz-Wert liefern.
- Preserve-Logik (alte Werte behalten wenn alle Quellen leer) bleibt als
  defensiver Schutz für seltene Konstellationen.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from backend.tests import ha_lts_helfer
from backend.models.anlage import Anlage
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.energie_profil.source import Source


async def _mqtt_anchor(db, anlage_id: int, datum: date) -> None:
    db.add(MqttEnergySnapshot(
        anlage_id=anlage_id,
        timestamp=datetime.combine(datum, datetime.min.time()) - timedelta(hours=1),
        energy_key="netzbezug",
        value_kwh=100.0,
    ))
    await db.flush()


@pytest.mark.asyncio
async def test_manuell_aktualisiert_komponenten_kwh_aus_boundary(db) -> None:
    """Reparatur-Werkbank-Klick (`datenquelle='manuell'`) MUSS die
    `komponenten_kwh`-Werte aus Boundary-Diff aktualisieren —
    sonst ist die Reparatur-Werkbank nutzlos für ihren Hauptzweck."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = Anlage(
        anlagenname="Test #290 v3.33.0",
        leistung_kwp=10.0,
        standort_plz="10115",
        standort_land="DE",
        wechselrichter_hersteller="generic",
        sensor_mapping={},  # leer — MQTT-Energy-Pfad
    )
    db.add(anlage)
    await db.flush()

    gestern = date.today() - timedelta(days=1)
    # Alte (buggy) Werte aus v3.31.0-LTS-Drift im DB
    alte_tz = TagesZusammenfassung(
        anlage_id=anlage.id,
        datum=gestern,
        stunden_verfuegbar=24,
        komponenten_kwh={"waermepumpe_1": 52.8, "wallbox_2": 23.24},
        datenquelle="ha_statistiken",
    )
    db.add(alte_tz)
    await _mqtt_anchor(db, anlage.id, gestern)
    await db.commit()

    # Boundary-Diff liefert die KORREKTEN Werte (so wie der v3.33.0-Helper)
    korrekte_boundary = {"waermepumpe_1": 6.3, "wallbox_2": 14.0}
    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={"serien": [], "punkte": []}),
    ), patch(
        # Zählerlücken wie HA (E5): der Snapshot-Tageswert kommt aus der Tagestabelle.
        "backend.services.snapshot.aggregator.snapshot_tagestabelle",
        new=AsyncMock(return_value=ha_lts_helfer.tages_tabelle(komponenten=korrekte_boundary)),
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        result = await aggregate_day(anlage, gestern, db, source=Source.MANUAL_REPAIR)

    assert result is not None
    # KORREKTUR: alte Bug-Werte wurden durch korrekte Boundary-Werte ersetzt
    assert result.komponenten_kwh == {"waermepumpe_1": 6.3, "wallbox_2": 14.0}


@pytest.mark.asyncio
async def test_manuell_0h_und_leerer_boundary_behaelt_alte_werte(db) -> None:
    """Wenn Boundary-Diff leer bleibt UND Σ-Hourly leer bleibt
    (z. B. HA-LTS weg, Snapshots korrupt), greift Preserve — alte Werte
    bleiben. Schutz für die seltene Konstellation."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = Anlage(
        anlagenname="Test #290 preserve",
        leistung_kwp=10.0,
        standort_plz="10115",
        standort_land="DE",
        wechselrichter_hersteller="generic",
        sensor_mapping={},
    )
    db.add(anlage)
    await db.flush()

    gestern = date.today() - timedelta(days=1)
    alte_tz = TagesZusammenfassung(
        anlage_id=anlage.id,
        datum=gestern,
        stunden_verfuegbar=24,
        komponenten_kwh={"waermepumpe_1": 6.3},
        komponenten_starts={"wp_starts_anzahl": {"1": 9}},
        datenquelle="ha_statistiken",
    )
    db.add(alte_tz)
    await _mqtt_anchor(db, anlage.id, gestern)
    await db.commit()

    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={"serien": [], "punkte": []}),
    ), patch(
        # Zählerlücken wie HA (E5): der Snapshot-Tageswert kommt aus der Tagestabelle.
        "backend.services.snapshot.aggregator.snapshot_tagestabelle",
        new=AsyncMock(return_value=ha_lts_helfer.tages_tabelle(komponenten={})),  # leer
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        result = await aggregate_day(anlage, gestern, db, source=Source.MANUAL_REPAIR)

    assert result is not None
    # Preserve: alte Werte bleiben, weil beide Quellen leer waren
    assert result.komponenten_kwh == {"waermepumpe_1": 6.3}
    assert result.komponenten_starts == {"wp_starts_anzahl": {"1": 9}}


@pytest.mark.asyncio
async def test_manuell_heute_ueberspringt_boundary_diff_weiterhin(db) -> None:
    """`datum == today` skippt Boundary auch bei `datenquelle='manuell'` —
    der today-Skip ist strukturell (Bug B), nicht symptomatisch."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = Anlage(
        anlagenname="Test #290 today",
        leistung_kwp=10.0,
        standort_plz="10115",
        standort_land="DE",
        wechselrichter_hersteller="generic",
        sensor_mapping={},
    )
    db.add(anlage)
    await db.flush()

    heute = date.today()
    await _mqtt_anchor(db, anlage.id, heute)
    await db.commit()

    boundary_mock = AsyncMock(
        return_value=ha_lts_helfer.tages_tabelle(komponenten={"waermepumpe_99": 99.9}),
    )
    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={"serien": [], "punkte": []}),
    ), patch(
        # Zählerlücken wie HA (E5): der Snapshot-Tageswert kommt aus der Tagestabelle.
        "backend.services.snapshot.aggregator.snapshot_tagestabelle",
        new=boundary_mock,
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        result = await aggregate_day(anlage, heute, db, source=Source.MANUAL_REPAIR)

    assert result is not None
    # Der Snapshot-Tageswert darf für heute NICHT geschrieben werden (Bug B bleibt).
    # Seit E5 liefert dieselbe Tabelle auch die Stunden — sie wird also gerufen;
    # ihr Tageswert aber nicht übernommen.
    assert "waermepumpe_99" not in (result.komponenten_kwh or {})
