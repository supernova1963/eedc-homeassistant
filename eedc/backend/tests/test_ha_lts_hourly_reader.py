"""
Akzeptanztest für Etappe 4 Schritt 3:
`HAStatisticsService.get_hourly_kwh_deltas_for_day()` liest stündliche
kWh-Deltas direkt aus HA-LTS-Statistics — die neue Single-Source-of-Truth
für Aggregat-Tabellen (siehe `docs/KONZEPT-ETAPPE-4-HA-LTS-SOT.md`).

Self-contained Standalone-Script:

    eedc/backend/venv/bin/python eedc/backend/tests/test_ha_lts_hourly_reader.py

Testet:
  1. Glatter Tag mit kontinuierlich steigendem Counter → 24 Slots mit
     korrekten Stunden-Deltas
  2. Mit Einheit Wh (statt kWh) → korrekte Skalierung (/1000)
  3. NULL `sum` in einer Stunde → entsprechende Slots None, andere weiter
  4. Mehrere Sensoren in einem Aufruf → ein Dict-Eintrag pro Sensor
  5. Unbekannte Entity-ID → fehlt im Result (kein Crash)

Tricky: HA-Statistics-Konvention `start_ts=H` enthält Counter am Ende der
Periode (H+1). Slot h (Energie [H, H+1)) = state(start_ts=H) − state(start_ts=H-1).
"""

from __future__ import annotations

import sys
import traceback
import time as time_module
from datetime import date, datetime, timedelta
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from sqlalchemy import create_engine, text  # noqa: E402

from backend.services.ha_statistics_service import HAStatisticsService  # noqa: E402


def _make_service_with_mock_db() -> HAStatisticsService:
    """Baut einen HAStatisticsService mit In-Memory-SQLite, gefüllt mit
    HA-Statistics-konformem Schema. Umgeht den File-Path-Init-Pfad."""
    svc = HAStatisticsService.__new__(HAStatisticsService)
    svc._engine = create_engine("sqlite:///:memory:")
    svc._is_mysql = False
    svc._initialized = True  # is_available muss True liefern ohne erneutes _init_engine
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


def _seed_sensor(svc: HAStatisticsService, entity_id: str, unit: str, has_sum: bool = True) -> int:
    with svc._engine.begin() as conn:
        result = conn.execute(
            text("INSERT INTO statistics_meta (statistic_id, unit_of_measurement, has_sum, has_mean) "
                 "VALUES (:sid, :unit, :hs, 0)"),
            {"sid": entity_id, "unit": unit, "hs": 1 if has_sum else 0},
        )
        return result.lastrowid


def _seed_hourly_value(svc: HAStatisticsService, metadata_id: int, when: datetime, sum_val: float) -> None:
    """Schreibt eine statistics-Zeile. `when` ist start_ts; HA-Konvention:
    Wert ist Counter AM ENDE der Periode = when+1h."""
    ts = time_module.mktime(when.timetuple())
    with svc._engine.begin() as conn:
        conn.execute(
            text("INSERT INTO statistics (metadata_id, start_ts, state, sum) "
                 "VALUES (:mid, :ts, NULL, :sum)"),
            {"mid": metadata_id, "ts": ts, "sum": sum_val},
        )


def test_glatter_tag_24_slots():
    """Counter steigt um exakt 5 kWh pro Stunde — alle 24 Slots = 5.0."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv_energy", "kWh")

    datum = date(2026, 5, 15)
    base = 1000.0  # Counter-Wert bei 00:00 datum (= state at start_ts=23:00 vortag)
    # 25 Boundaries: start_ts=23:00 vortag bis start_ts=23:00 heute
    boundary_starts = [
        datetime(2026, 5, 14, 23, 0),  # → 00:00 heute (b_idx=0)
    ] + [
        datetime(2026, 5, 15, h, 0) for h in range(24)  # → 01:00..00:00 folgetag (b_idx=1..24)
    ]
    for i, when in enumerate(boundary_starts):
        _seed_hourly_value(svc, mid, when, base + i * 5.0)

    result = svc.get_hourly_kwh_deltas_for_day(["sensor.pv_energy"], datum)
    assert "sensor.pv_energy" in result, f"Sensor fehlt im Result: {result}"
    slots = result["sensor.pv_energy"]
    for h in range(24):
        assert slots.get(h) == 5.0, f"Slot {h}: erwartet 5.0, bekommen {slots.get(h)}"


def test_einheit_wh_wird_skaliert():
    """Counter in Wh → Werte werden durch 1000 geteilt."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv_wh", "Wh")

    datum = date(2026, 5, 15)
    # 5000 Wh pro Stunde = 5.0 kWh
    boundary_starts = [datetime(2026, 5, 14, 23, 0)] + [
        datetime(2026, 5, 15, h, 0) for h in range(24)
    ]
    for i, when in enumerate(boundary_starts):
        _seed_hourly_value(svc, mid, when, 1_000_000.0 + i * 5000.0)

    result = svc.get_hourly_kwh_deltas_for_day(["sensor.pv_wh"], datum)
    slots = result["sensor.pv_wh"]
    for h in range(24):
        assert slots.get(h) == 5.0, f"Slot {h}: erwartet 5.0 kWh aus Wh-Quelle, bekommen {slots.get(h)}"


def test_luecke_in_der_mitte_einzelne_slots_none():
    """Boundary 12:00 fehlt → Slot 11 und Slot 12 sind None, andere bleiben."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv_energy", "kWh")

    datum = date(2026, 5, 15)
    boundary_starts = [datetime(2026, 5, 14, 23, 0)] + [
        datetime(2026, 5, 15, h, 0) for h in range(24)
    ]
    # b_idx=12 = state at start_ts=11:00 → Slot 11 (end) + Slot 12 (start) betroffen
    skip_when = datetime(2026, 5, 15, 11, 0)
    for i, when in enumerate(boundary_starts):
        if when == skip_when:
            continue
        _seed_hourly_value(svc, mid, when, 1000.0 + i * 5.0)

    result = svc.get_hourly_kwh_deltas_for_day(["sensor.pv_energy"], datum)
    slots = result["sensor.pv_energy"]
    assert slots.get(11) is None, f"Slot 11 muss None sein (end-Boundary fehlt): {slots.get(11)}"
    assert slots.get(12) is None, f"Slot 12 muss None sein (start-Boundary fehlt): {slots.get(12)}"
    assert slots.get(0) == 5.0
    assert slots.get(23) == 5.0


def test_mehrere_sensoren_in_einem_aufruf():
    """Drei Sensoren auf einmal → drei Result-Einträge."""
    svc = _make_service_with_mock_db()
    mids = {
        "sensor.pv": _seed_sensor(svc, "sensor.pv", "kWh"),
        "sensor.einspeisung": _seed_sensor(svc, "sensor.einspeisung", "kWh"),
        "sensor.netzbezug": _seed_sensor(svc, "sensor.netzbezug", "kWh"),
    }

    datum = date(2026, 5, 15)
    boundary_starts = [datetime(2026, 5, 14, 23, 0)] + [
        datetime(2026, 5, 15, h, 0) for h in range(24)
    ]
    for sid, mid in mids.items():
        base = {"sensor.pv": 1000.0, "sensor.einspeisung": 500.0, "sensor.netzbezug": 800.0}[sid]
        delta = {"sensor.pv": 5.0, "sensor.einspeisung": 3.0, "sensor.netzbezug": 1.5}[sid]
        for i, when in enumerate(boundary_starts):
            _seed_hourly_value(svc, mid, when, base + i * delta)

    result = svc.get_hourly_kwh_deltas_for_day(list(mids.keys()), datum)
    assert set(result.keys()) == set(mids.keys()), f"Keys: {result.keys()}"
    assert result["sensor.pv"][10] == 5.0
    assert result["sensor.einspeisung"][10] == 3.0
    assert result["sensor.netzbezug"][10] == 1.5


def test_unbekannter_sensor_fehlt_im_result():
    """Sensor ohne statistics_meta-Eintrag wird im Result einfach ausgelassen,
    kein Crash."""
    svc = _make_service_with_mock_db()
    mid_pv = _seed_sensor(svc, "sensor.pv", "kWh")

    datum = date(2026, 5, 15)
    boundary_starts = [datetime(2026, 5, 14, 23, 0)] + [
        datetime(2026, 5, 15, h, 0) for h in range(24)
    ]
    for i, when in enumerate(boundary_starts):
        _seed_hourly_value(svc, mid_pv, when, 1000.0 + i * 5.0)

    result = svc.get_hourly_kwh_deltas_for_day(
        ["sensor.pv", "sensor.does_not_exist"], datum,
    )
    assert "sensor.pv" in result
    assert "sensor.does_not_exist" not in result


_TESTS = [
    test_glatter_tag_24_slots,
    test_einheit_wh_wird_skaliert,
    test_luecke_in_der_mitte_einzelne_slots_none,
    test_mehrere_sensoren_in_einem_aufruf,
    test_unbekannter_sensor_fehlt_im_result,
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
