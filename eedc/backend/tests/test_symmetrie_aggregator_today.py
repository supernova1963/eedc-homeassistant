"""Symmetrie-Test S0 für aggregate_day-Verhalten bei datum == today.

Verankert den B-clean-Fix v3.34.1 (#620 MartyBr simon42, Audit §5.1.1):
die SKIP-Bedingung in `aggregator.py` wurde von `datum >= today` auf
`datum > today` gelockert, damit der LTS-Pfad für den laufenden Tag eine
slot-basierte Teilsumme liefern kann (siehe `get_hourly_kwh_deltas_for_day`-
Docstring + `get_komponenten_tageskwh_lts`).

Parametrisiert über die vier Aggregator-Konstellationen aus Audit §3.6:
  1. HA-Add-on datum < today  — LTS-Pfad, historischer Tag (Status quo)
  2. HA-Add-on datum == today — LTS-Pfad, NEU gefüllt durch B-clean-Fix
  3. Standalone-MQTT datum < today — kein LTS, Snapshot-Fallback (Status quo)
  4. HA-Add-on datum > today  — Zukunft, SKIP bleibt (komponenten_kwh = None)

Pflicht-Aussage:
  - (1), (2), (3) liefern komponenten_kwh-Dicts mit identischer Key-Menge.
    Werte dürfen abweichen, weil Datenlage abweicht (Teilsumme vs Volltag,
    Standalone vs LTS) — aber keine Schlüssel-Lücken.
  - (4) liefert komponenten_kwh = None (bewusste Asymmetrie heute/Zukunft).

ADR-001-Pflicht ([[feedback_aggregator_symmetrie]]): bei parallelen
Schreib-Pfaden auf dieselbe Aggregat-Tabelle muss ein Symmetrie-Test
existieren. Ohne diesen Test wäre der Modus-3-Dead-Spot aus Audit §5.1.1
weiterhin in unsichtbarer Bug-Klasse.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.models.anlage import Anlage
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.energie_profil.source import Source


_LTS_HOURLY = {
    h: {
        "pv": 1.2,
        "einspeisung": 0.5,
        "netzbezug": 0.3,
        "verbrauch": 1.0,
        "wp": 0.4,
        "wallbox": None,
        "batterie_netto": 0.0,
        "verbrauch_sonstiges": None,
    }
    for h in range(24)
}

# Für today: nur die ersten 8 Stunden gefüllt (simuliert :30-Aufruf um 08:30).
_LTS_HOURLY_TEILTAG = {
    h: _LTS_HOURLY[h] if h < 8 else {
        "pv": None, "einspeisung": None, "netzbezug": None, "verbrauch": None,
        "wp": None, "wallbox": None, "batterie_netto": None, "verbrauch_sonstiges": None,
    }
    for h in range(24)
}

_KOMPONENTEN_KEYS = {"pv_3", "einspeisung", "netzbezug", "waermepumpe_7"}

_LTS_KOMP_VOLLTAG = {
    "pv_3": 28.8,
    "einspeisung": 12.0,
    "netzbezug": 7.2,
    "waermepumpe_7": 9.6,
}

_LTS_KOMP_TEILTAG = {
    "pv_3": 9.6,
    "einspeisung": 4.0,
    "netzbezug": 2.4,
    "waermepumpe_7": 3.2,
}


def _anlage_mit_lts_mapping() -> Anlage:
    return Anlage(
        anlagenname="S0-Test",
        leistung_kwp=10.0,
        standort_plz="10115",
        standort_land="DE",
        wechselrichter_hersteller="generic",
        sensor_mapping={
            "basis": {
                "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einsp"},
                "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.bezug"},
            },
            "investitionen": {
                "3": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}}},
                "7": {"felder": {"stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": "sensor.wp"}}},
            },
        },
    )


async def _mqtt_anchor(db, anlage_id: int, datum: date) -> None:
    """24h vor `datum` einen MQTT-Energy-Snapshot setzen — damit
    `aggregate_day` den synthetischen 24h-Pfad nimmt (sonst returnt es None
    bei leerem sensor_mapping.live)."""
    db.add(MqttEnergySnapshot(
        anlage_id=anlage_id,
        timestamp=datetime.combine(datum, datetime.min.time()) - timedelta(hours=1),
        energy_key="netzbezug",
        value_kwh=100.0,
    ))
    await db.flush()


@pytest.mark.asyncio
async def test_aggregate_day_today_ha_addon_lts_pfad_gefuellt(db) -> None:
    """Konstellation 2 (§3.6 Modus 3 — B-clean-Fix-Pfad):
    HA-Add-on, datum == today, LTS-Pfad aktiv → komponenten_kwh nicht None,
    Teilsumme aus den schon vergangenen Stunden-Slots."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = _anlage_mit_lts_mapping()
    db.add(anlage)
    await db.flush()

    heute = date.today()
    await _mqtt_anchor(db, anlage.id, heute)
    await db.commit()

    boundary_snap_mock = AsyncMock(return_value={"INVALID": 99.9})

    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={"serien": [], "punkte": []}),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
        new=AsyncMock(return_value=_LTS_HOURLY_TEILTAG),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
        new=AsyncMock(return_value=_LTS_KOMP_TEILTAG),
    ), patch(
        "backend.services.snapshot.aggregator.get_komponenten_tageskwh",
        new=boundary_snap_mock,
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        result = await aggregate_day(anlage, heute, db, source=Source.SCHEDULER)

    assert result is not None
    # B-clean: komponenten_kwh ist NICHT mehr None für today im LTS-Modus.
    assert result.komponenten_kwh is not None
    assert set(result.komponenten_kwh.keys()) == _KOMPONENTEN_KEYS
    # Snapshot-Fallback wurde NICHT aufgerufen (#290 Bug B Schutz bleibt).
    boundary_snap_mock.assert_not_called()


@pytest.mark.asyncio
async def test_aggregate_day_historisch_ha_addon_lts_pfad_gefuellt(db) -> None:
    """Konstellation 1: HA-Add-on, datum < today, LTS-Pfad — Status quo."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = _anlage_mit_lts_mapping()
    db.add(anlage)
    await db.flush()

    gestern = date.today() - timedelta(days=1)
    await _mqtt_anchor(db, anlage.id, gestern)
    await db.commit()

    boundary_snap_mock = AsyncMock(return_value={"INVALID": 99.9})

    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={"serien": [], "punkte": []}),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
        new=AsyncMock(return_value=_LTS_HOURLY),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
        new=AsyncMock(return_value=_LTS_KOMP_VOLLTAG),
    ), patch(
        "backend.services.snapshot.aggregator.get_komponenten_tageskwh",
        new=boundary_snap_mock,
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        result = await aggregate_day(anlage, gestern, db, source=Source.SCHEDULER)

    assert result is not None
    assert result.komponenten_kwh is not None
    assert set(result.komponenten_kwh.keys()) == _KOMPONENTEN_KEYS
    boundary_snap_mock.assert_not_called()


@pytest.mark.asyncio
async def test_aggregate_day_historisch_standalone_snapshot_pfad_gefuellt(db) -> None:
    """Konstellation 3: Standalone-MQTT, datum < today — LTS leer →
    Snapshot-Fallback. Live-Σ-Riemann aus der Stunden-Schleife läuft mit
    (kwh_source_label != "external:ha_statistics:hourly")."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = _anlage_mit_lts_mapping()
    db.add(anlage)
    await db.flush()

    gestern = date.today() - timedelta(days=1)
    await _mqtt_anchor(db, anlage.id, gestern)
    await db.commit()

    boundary_snap_mock = AsyncMock(return_value=_LTS_KOMP_VOLLTAG)

    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={"serien": [], "punkte": []}),
    ), patch(
        # LTS-Stunden-Pfad failt → Fallback → kwh_source_label = "auto:monatsabschluss"
        "backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.sensor_snapshot_service.get_hourly_kwh_by_category",
        new=AsyncMock(return_value=_LTS_HOURLY),
    ), patch(
        "backend.services.snapshot.aggregator.get_komponenten_tageskwh",
        new=boundary_snap_mock,
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        result = await aggregate_day(anlage, gestern, db, source=Source.SCHEDULER)

    assert result is not None
    assert result.komponenten_kwh is not None
    assert set(result.komponenten_kwh.keys()) == _KOMPONENTEN_KEYS
    # Snapshot-Boundary wurde aufgerufen (Standalone-Pfad)
    boundary_snap_mock.assert_called_once()


@pytest.mark.asyncio
async def test_aggregate_day_zukunft_ha_addon_skip_bleibt(db) -> None:
    """Konstellation 4 (§3.6 Modus 5b — bewusste Asymmetrie heute/Zukunft):
    datum > today → SKIP bleibt, komponenten_kwh = None.

    Verifiziert die `datum > date.today()` Schwelle: B-clean lockert nur
    today, nicht die Zukunft. Schützt gegen versehentliche Umformulierung
    in einer späteren Refactor-Session (z.B. `datum >= today + 1d`)."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = _anlage_mit_lts_mapping()
    db.add(anlage)
    await db.flush()

    morgen = date.today() + timedelta(days=1)
    await _mqtt_anchor(db, anlage.id, morgen)
    await db.commit()

    lts_komp_mock = AsyncMock(return_value=_LTS_KOMP_VOLLTAG)
    boundary_snap_mock = AsyncMock(return_value=_LTS_KOMP_VOLLTAG)

    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={"serien": [], "punkte": []}),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
        new=AsyncMock(return_value=_LTS_HOURLY),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
        new=lts_komp_mock,
    ), patch(
        "backend.services.snapshot.aggregator.get_komponenten_tageskwh",
        new=boundary_snap_mock,
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        result = await aggregate_day(anlage, morgen, db, source=Source.SCHEDULER)

    assert result is not None
    # Zukunft: KEIN Boundary-Aufruf, weder LTS noch Snapshot.
    lts_komp_mock.assert_not_called()
    boundary_snap_mock.assert_not_called()
    # komponenten_kwh = None (kein Schreiber für Zukunfts-Tag).
    assert result.komponenten_kwh is None


@pytest.mark.asyncio
async def test_aggregate_day_today_lts_leer_edge_case_0005_scheduler(db) -> None:
    """Edge-Case: Scheduler-Job um 00:05 für `datum == today`.

    Zu dem Zeitpunkt hat HA-Statistics noch keine Stunde des neuen Tages
    geschrieben (start_ts=00:00 heute wird erst um 01:00 heute geschrieben).
    `get_hourly_kwh_deltas_for_day` liefert für alle 24 Slots `None`,
    `get_komponenten_tageskwh_lts` summiert keine valide-Slots → leeres Dict.

    Erwartung: komponenten_kwh = None (Sentinel-Verhalten unverändert,
    KEIN leeres Dict, damit Read-Sites das Fehlen vom Wert eindeutig
    unterscheiden können). QS-Trigger 3 aus dem Handover."""
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = _anlage_mit_lts_mapping()
    db.add(anlage)
    await db.flush()

    heute = date.today()
    await _mqtt_anchor(db, anlage.id, heute)
    await db.commit()

    # LTS-Hourly aktiv, aber Komponenten-Tagessumme leer (00:05-Szenario).
    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value={"serien": [], "punkte": []}),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
        new=AsyncMock(return_value=_LTS_HOURLY_TEILTAG),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
        new=AsyncMock(return_value={}),
    ), patch(
        "backend.services.snapshot.aggregator.get_komponenten_tageskwh",
        new=AsyncMock(return_value={"INVALID": 99.9}),
    ) as boundary_snap_mock, patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        result = await aggregate_day(anlage, heute, db, source=Source.SCHEDULER)

    assert result is not None
    # Sentinel: None, nicht leeres Dict.
    assert result.komponenten_kwh is None
    # Snapshot-Fallback bleibt für today inaktiv (#290 Bug B Schutz).
    boundary_snap_mock.assert_not_called()


@pytest.mark.asyncio
async def test_aggregate_day_bkw_regression_live_sigma_bypass_aktiv(db) -> None:
    """BKW-Bug-Fix Regressions-Schutz (Audit §4.9 / §5.1.1 Maßnahme 1).

    Bei aktivem LTS-Pfad MUSS Live-Σ-Riemann (Z. 395-406) AUS bleiben.
    Sonst landet ein BKW-Inverter als `pv_<id>` aus dem Live-Service-Pfad
    UND als `bkw_<id>` aus dem Boundary-Pfad in komponenten_summen
    (Schema-Mismatch BKW → Doppelzählung, Rainer-PN 2026-05-19).

    Der Test simuliert: LTS-Pfad aktiv, Live-Tagesverlauf liefert eine
    BKW-Serie mit Live-Key `pv_11`, Boundary-LTS liefert `bkw_11`. Ohne
    den Live-Σ-Bypass würden beide Keys parallel in komponenten_summen
    landen — mit Bypass nur `bkw_11`.
    """
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = _anlage_mit_lts_mapping()
    db.add(anlage)
    await db.flush()

    gestern = date.today() - timedelta(days=1)
    await _mqtt_anchor(db, anlage.id, gestern)
    await db.commit()

    # Live-Tagesverlauf mit BKW-Serie (Key `pv_11`) — sollte NICHT in
    # komponenten_summen landen, weil Live-Σ-Bypass im LTS-Modus aktiv ist.
    live_tv = {
        "serien": [
            {"key": "pv_11", "kategorie": "pv", "investition_id": 11, "leistung_kwp": 0.6},
        ],
        "punkte": [
            {"zeit": f"{h:02d}:00", "werte": {"pv_11": 0.3}}
            for h in range(24)
        ],
    }
    # Boundary-LTS-Variante liefert BKW mit korrekter Key-Konvention `bkw_11`.
    bkw_boundary = {"bkw_11": 7.2}

    with patch(
        "backend.services.live_power_service.LivePowerService.get_tagesverlauf",
        new=AsyncMock(return_value=live_tv),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_hourly_kwh_by_category_lts",
        new=AsyncMock(return_value=_LTS_HOURLY),
    ), patch(
        "backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
        new=AsyncMock(return_value=bkw_boundary),
    ), patch(
        "backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv",
        new=AsyncMock(return_value={}),
    ):
        result = await aggregate_day(anlage, gestern, db, source=Source.SCHEDULER)

    assert result is not None
    assert result.komponenten_kwh is not None
    # Nur Boundary-Key `bkw_11`, KEIN Live-Pfad-Key `pv_11`.
    assert "bkw_11" in result.komponenten_kwh
    assert "pv_11" not in result.komponenten_kwh, (
        "BKW-Bug-Regression: Live-Σ-Bypass greift nicht — Live-Key `pv_11` "
        "wurde fälschlich akkumuliert. Live-Service-Schema-Mismatch zur "
        "Boundary-Key-Konvention führt zur Doppelzählung."
    )
