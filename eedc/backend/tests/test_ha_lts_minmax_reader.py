"""
Akzeptanztest für Etappe 5 (v3.31.0):
`HAStatisticsService.get_hourly_minmax_sensor_data()` liest die im
HA-Recorder gespeicherten Stunden-Min/Max für `has_mean=True`-Sensoren.

Quelle für Tages-Peak-Werte (peak_pv_kw, peak_netzbezug_kw, peak_einspeisung_kw)
— eedc muss sie nicht aus 10-Min-Mittelwerten rekonstruieren, was Peaks
systematisch unterschätzt.

Self-contained Standalone-Script:

    eedc/backend/venv/bin/python eedc/backend/tests/test_ha_lts_minmax_reader.py
"""

from __future__ import annotations

import sys
import traceback
import time as time_module
from datetime import date, datetime
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from backend.services.ha_statistics_service import HAStatisticsService  # noqa: E402


def _make_service() -> HAStatisticsService:
    svc = HAStatisticsService.__new__(HAStatisticsService)
    svc._engine = create_engine("sqlite:///:memory:")
    svc._is_mysql = False
    svc._initialized = True
    with svc._engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE statistics_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                statistic_id TEXT,
                unit_of_measurement TEXT,
                has_sum INTEGER,
                has_mean INTEGER
            )
        """))
        conn.execute(text("""
            CREATE TABLE statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metadata_id INTEGER,
                start_ts REAL,
                state REAL,
                sum REAL,
                mean REAL,
                min REAL,
                max REAL
            )
        """))
    return svc


def _seed_sensor(svc: HAStatisticsService, entity_id: str, unit: str) -> int:
    with svc._engine.begin() as conn:
        result = conn.execute(
            text("INSERT INTO statistics_meta (statistic_id, unit_of_measurement, has_sum, has_mean) "
                 "VALUES (:sid, :unit, 0, 1)"),
            {"sid": entity_id, "unit": unit},
        )
        return result.lastrowid


def _seed_minmax(svc: HAStatisticsService, mid: int, when: datetime, mn: float, mx: float) -> None:
    ts = time_module.mktime(when.timetuple())
    with svc._engine.begin() as conn:
        conn.execute(
            text("INSERT INTO statistics (metadata_id, start_ts, state, sum, mean, min, max) "
                 "VALUES (:mid, :ts, NULL, NULL, NULL, :mn, :mx)"),
            {"mid": mid, "ts": ts, "mn": mn, "mx": mx},
        )


def test_kw_sensor_minmax_durchgereicht():
    """kW-Sensor: min/max ohne Skalierung übernommen."""
    svc = _make_service()
    mid = _seed_sensor(svc, "sensor.pv", "kW")

    datum = date(2026, 5, 15)
    _seed_minmax(svc, mid, datetime(2026, 5, 15, 12, 0), mn=2.0, mx=8.5)
    _seed_minmax(svc, mid, datetime(2026, 5, 15, 13, 0), mn=3.0, mx=9.2)

    result = svc.get_hourly_minmax_sensor_data(["sensor.pv"], datum, datum)
    slots = result["sensor.pv"]["2026-05-15"]
    assert slots[12] == {"min": 2.0, "max": 8.5}, f"slot 12: {slots[12]}"
    assert slots[13] == {"min": 3.0, "max": 9.2}, f"slot 13: {slots[13]}"


def test_w_sensor_wird_skaliert_zu_kw():
    """W-Sensor: min/max durch 1000."""
    svc = _make_service()
    mid = _seed_sensor(svc, "sensor.pv_w", "W")

    datum = date(2026, 5, 15)
    _seed_minmax(svc, mid, datetime(2026, 5, 15, 12, 0), mn=2000.0, mx=8500.0)

    result = svc.get_hourly_minmax_sensor_data(["sensor.pv_w"], datum, datum)
    slots = result["sensor.pv_w"]["2026-05-15"]
    assert slots[12] == {"min": 2.0, "max": 8.5}, f"slot 12: {slots[12]}"


def test_kwh_counter_wird_ignoriert():
    """Energie-Counter (kWh) liefert keine Peak-Daten — Sensor fehlt im Result."""
    svc = _make_service()
    mid = _seed_sensor(svc, "sensor.pv_energy", "kWh")

    datum = date(2026, 5, 15)
    _seed_minmax(svc, mid, datetime(2026, 5, 15, 12, 0), mn=1000.0, mx=1005.0)

    result = svc.get_hourly_minmax_sensor_data(["sensor.pv_energy"], datum, datum)
    assert "sensor.pv_energy" not in result, f"kWh-Counter darf nicht durchkommen: {result}"


def test_negative_einspeisung_aus_kombi_sensor():
    """Kombi-Sensor: positives max = Netzbezug, negatives min = Einspeisung."""
    svc = _make_service()
    mid = _seed_sensor(svc, "sensor.netz_kombi", "kW")

    datum = date(2026, 5, 15)
    # Mittag: stark einspeisend (min sehr negativ), nur kurz Bezug (max klein positiv)
    _seed_minmax(svc, mid, datetime(2026, 5, 15, 12, 0), mn=-6.0, mx=0.2)
    # Abend: stark bezogen
    _seed_minmax(svc, mid, datetime(2026, 5, 15, 19, 0), mn=0.0, mx=4.5)

    result = svc.get_hourly_minmax_sensor_data(["sensor.netz_kombi"], datum, datum)
    slots = result["sensor.netz_kombi"]["2026-05-15"]
    assert slots[12]["min"] == -6.0
    assert slots[19]["max"] == 4.5


def test_anderer_tag_wird_ignoriert():
    """Stunden vom Folgetag landen nicht im datum-iso-Bucket des Vortags."""
    svc = _make_service()
    mid = _seed_sensor(svc, "sensor.pv", "kW")

    _seed_minmax(svc, mid, datetime(2026, 5, 15, 23, 0), mn=0.0, mx=1.0)
    _seed_minmax(svc, mid, datetime(2026, 5, 16, 12, 0), mn=0.0, mx=8.0)

    # Nur 15.05. abfragen
    result = svc.get_hourly_minmax_sensor_data(["sensor.pv"], date(2026, 5, 15), date(2026, 5, 15))
    assert list(result["sensor.pv"].keys()) == ["2026-05-15"]
    assert result["sensor.pv"]["2026-05-15"] == {23: {"min": 0.0, "max": 1.0}}


_TESTS = [
    test_kw_sensor_minmax_durchgereicht,
    test_w_sensor_wird_skaliert_zu_kw,
    test_kwh_counter_wird_ignoriert,
    test_negative_einspeisung_aus_kombi_sensor,
    test_anderer_tag_wird_ignoriert,
]


def _run_all() -> int:
    failures = 0
    for test in _TESTS:
        try:
            test()
            print(f"OK   {test.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {test.__name__}\n     {e}")
        except Exception:
            failures += 1
            print(f"ERR  {test.__name__}")
            traceback.print_exc()
    return failures


if __name__ == "__main__":
    failures = _run_all()
    if failures:
        print(f"\n{failures} von {len(_TESTS)} Tests fehlgeschlagen.")
        sys.exit(1)
    print(f"\nAlle {len(_TESTS)} Tests grün.")
