"""
Akzeptanztest für Etappe 5 (v3.31.0):
`HAStatisticsService.get_hourly_mean_for_day()` — Stunden-Mean roh + Einheit
für einen Sensor und Tag. Verwendet von `_get_soc_history` (Speicher-SoC %)
und `_get_strompreis_stunden` (Sensor-Endpreis EUR/kWh, cent/kWh, …).

Im Gegensatz zu `get_hourly_sensor_data()` werden Rohwerte zurückgegeben —
ohne Einheitenumrechnung. Der Aufrufer kennt seinen Kontext besser.

Self-contained Standalone-Script:

    eedc/backend/venv/bin/python eedc/backend/tests/test_ha_lts_mean_reader.py
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


def _make_service_with_mock_db() -> HAStatisticsService:
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
                mean REAL
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


def _seed_mean(svc: HAStatisticsService, metadata_id: int, when: datetime, mean: float) -> None:
    ts = time_module.mktime(when.timetuple())
    with svc._engine.begin() as conn:
        conn.execute(
            text("INSERT INTO statistics (metadata_id, start_ts, state, sum, mean) "
                 "VALUES (:mid, :ts, NULL, NULL, :mean)"),
            {"mid": metadata_id, "ts": ts, "mean": mean},
        )


def test_soc_prozent_24_slots():
    """SoC-Sensor in Prozent: roher Mean wird durchgereicht."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.speicher_soc", "%")

    datum = date(2026, 5, 15)
    for h in range(24):
        _seed_mean(svc, mid, datetime(2026, 5, 15, h, 0), 50.0 + h)

    slots, unit = svc.get_hourly_mean_for_day("sensor.speicher_soc", datum)
    assert unit == "%", f"unit: {unit}"
    assert len(slots) == 24, f"slots: {len(slots)}"
    for h in range(24):
        assert slots[h] == 50.0 + h, f"slot {h}: {slots[h]}"


def test_strompreis_eur_kwh_rohwert():
    """EUR/kWh-Strompreis: 0.30 wird als roher Wert zurückgeliefert,
    keine /1000-Konvertierung (im Gegensatz zu get_hourly_sensor_data)."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.tibber_price", "EUR/kWh")

    datum = date(2026, 5, 15)
    _seed_mean(svc, mid, datetime(2026, 5, 15, 12, 0), 0.30)

    slots, unit = svc.get_hourly_mean_for_day("sensor.tibber_price", datum)
    assert unit == "EUR/kWh", f"unit: {unit}"
    assert slots[12] == 0.30, f"slot 12: {slots[12]}"


def test_unbekannter_sensor_leer():
    """Sensor nicht in statistics_meta → ({}, None), kein Crash."""
    svc = _make_service_with_mock_db()

    slots, unit = svc.get_hourly_mean_for_day("sensor.does_not_exist", date(2026, 5, 15))
    assert slots == {}, f"slots: {slots}"
    assert unit is None, f"unit: {unit}"


def test_anderer_tag_wird_ignoriert():
    """Mean-Werte vom Folgetag werden nicht aufgenommen (Boundary-Test)."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.soc", "%")

    # 23:00 datum + 23:00 folgetag → letzterer darf NICHT enthalten sein
    _seed_mean(svc, mid, datetime(2026, 5, 15, 23, 0), 80.0)
    _seed_mean(svc, mid, datetime(2026, 5, 16, 23, 0), 90.0)

    slots, _ = svc.get_hourly_mean_for_day("sensor.soc", date(2026, 5, 15))
    assert slots == {23: 80.0}, f"slots: {slots}"


def test_null_mean_wird_uebersprungen():
    """Eine Stunde mit mean=NULL liefert keinen Eintrag im Result."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.soc", "%")

    _seed_mean(svc, mid, datetime(2026, 5, 15, 10, 0), 65.0)
    # h=11 absichtlich auslassen
    _seed_mean(svc, mid, datetime(2026, 5, 15, 12, 0), 67.0)

    slots, _ = svc.get_hourly_mean_for_day("sensor.soc", date(2026, 5, 15))
    assert 10 in slots
    assert 11 not in slots
    assert 12 in slots


_TESTS = [
    test_soc_prozent_24_slots,
    test_strompreis_eur_kwh_rohwert,
    test_unbekannter_sensor_leer,
    test_anderer_tag_wird_ignoriert,
    test_null_mean_wird_uebersprungen,
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
