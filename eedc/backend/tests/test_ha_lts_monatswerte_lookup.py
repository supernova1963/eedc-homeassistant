"""
Charakterisierungs-Tests für HAStatisticsService — Monatswerte + Punkt-Lookup.

Spur 0 des Backend-Refactoring-Plans (docs/drafts/REFACTORING-BACKEND-PLAN-
20260614.md): Bevor `services/ha_statistics_service.py` (1208 Z.) entschlackt
wird, fixieren diese Tests das aktuelle Verhalten der bislang UNGETESTETEN
öffentlichen Methoden.

Alle Tests für `HAStatisticsService` liegen einheitlich unter dem Präfix
`test_ha_lts_*` (lts = Long-Term Statistics) — ein Präfix, damit die Abdeckung
aus jeder Suchrichtung vollständig auffindbar bleibt. Die stündlichen Reader
sind in den Schwester-Dateien abgedeckt:
  - test_ha_lts_hourly_reader.py         → get_hourly_kwh_deltas_for_day
  - test_ha_lts_minmax_reader.py         → get_hourly_minmax_sensor_data
  - test_ha_lts_mean_reader.py           → get_hourly_mean_for_day
  - test_live_tagesverlauf_short_term.py → get_short_term_5min_for_day
Diese Datei ergänzt die andere Hälfte:

  - get_metadata / filter_valid_sensor_ids / count_statistics_sensors
  - get_sensor_monatswert / get_monatswerte  (sum-vs-state #131 + Einheit)
  - get_verfuegbare_monate  (Aktueller-Monat-Ausschluss + Monatsgenerierung)
  - get_monatsanfang_wert
  - get_value_at  (Off-by-one-Periodenlogik v3.25.9, has_sum/state/short_term)
  - get_hourly_sensor_data  (W→kW, kWh-Skip)

Self-contained Standalone-Script:

    eedc/backend/venv/bin/python eedc/backend/tests/test_ha_lts_monatswerte_lookup.py

Tricky: Seeding via time.mktime(naive_local) und Query via
datetime(start_ts,'unixepoch','localtime') interpretieren die Wanduhrzeit
konsistent — die Tests sind damit TZ-unabhängig (gleiches Muster wie die
bestehenden test_ha_lts_*-Fixtures).
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


# ---------------------------------------------------------------------------
# Fixture-Helfer (lokal, wie in den bestehenden test_ha_lts_*-Dateien)
# ---------------------------------------------------------------------------

def _make_service_with_mock_db() -> HAStatisticsService:
    """HAStatisticsService mit In-Memory-SQLite + HA-konformem Schema
    (statistics_meta, statistics, statistics_short_term). Umgeht _init_engine."""
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
        for tbl in ("statistics", "statistics_short_term"):
            conn.execute(text(f"""
                CREATE TABLE {tbl} (
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


def _seed_sensor(svc, entity_id: str, unit: str, has_sum: bool = True) -> int:
    with svc._engine.begin() as conn:
        result = conn.execute(
            text("INSERT INTO statistics_meta (statistic_id, unit_of_measurement, has_sum, has_mean) "
                 "VALUES (:sid, :unit, :hs, :hm)"),
            {"sid": entity_id, "unit": unit, "hs": 1 if has_sum else 0,
             "hm": 0 if has_sum else 1},
        )
        return result.lastrowid


def _seed_row(svc, mid: int, when: datetime, *, state=None, sum_val=None,
              mean=None, table: str = "statistics") -> None:
    ts = time_module.mktime(when.timetuple())
    with svc._engine.begin() as conn:
        conn.execute(
            text(f"INSERT INTO {table} (metadata_id, start_ts, state, sum, mean) "
                 "VALUES (:mid, :ts, :state, :sum, :mean)"),
            {"mid": mid, "ts": ts, "state": state, "sum": sum_val, "mean": mean},
        )


# ---------------------------------------------------------------------------
# Metadaten-Trio
# ---------------------------------------------------------------------------

def test_get_metadata_bekannt_und_unbekannt():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh", has_sum=True)
    with svc._engine.connect() as conn:
        meta = svc.get_metadata(conn, "sensor.pv")
        assert meta is not None
        assert meta.id == mid
        assert meta.unit == "kWh"
        assert meta.has_sum is True
        assert svc.get_metadata(conn, "sensor.gibt_es_nicht") is None


def test_filter_valid_sensor_ids_erhaelt_reihenfolge():
    svc = _make_service_with_mock_db()
    _seed_sensor(svc, "sensor.a", "kWh")
    _seed_sensor(svc, "sensor.c", "kWh")
    valid, missing = svc.filter_valid_sensor_ids(
        ["sensor.a", "sensor.b", "sensor.c", "sensor.d"]
    )
    assert valid == ["sensor.a", "sensor.c"]
    assert missing == ["sensor.b", "sensor.d"]


def test_count_statistics_sensors():
    svc = _make_service_with_mock_db()
    assert svc.count_statistics_sensors() == 0
    _seed_sensor(svc, "sensor.a", "kWh")
    _seed_sensor(svc, "sensor.b", "W", has_sum=False)
    assert svc.count_statistics_sensors() == 2


# ---------------------------------------------------------------------------
# Monatswert: sum-bevorzugt (#131), state-Fallback, Einheiten-Konvertierung
# ---------------------------------------------------------------------------

def test_monatswert_sum_bevorzugt_vor_state():
    """MAX(sum)−MIN(sum) ist die reset-bereinigte Monatssumme (#131).
    Auch wenn `state` zwischendrin zurücksetzt (Tagesreset-Zähler), bleibt
    das sum-Delta korrekt."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh", has_sum=True)
    # state springt (Tagesreset), sum läuft monoton weiter
    _seed_row(svc, mid, datetime(2026, 5, 2, 0, 0), state=8.0, sum_val=100.0)
    _seed_row(svc, mid, datetime(2026, 5, 15, 0, 0), state=3.0, sum_val=160.0)
    _seed_row(svc, mid, datetime(2026, 5, 28, 0, 0), state=9.0, sum_val=200.0)

    with svc._engine.connect() as conn:
        meta = svc.get_metadata(conn, "sensor.pv")
        wert = svc.get_sensor_monatswert(conn, meta, "sensor.pv", 2026, 5)
    assert wert is not None
    assert wert.start_wert == 100.0
    assert wert.end_wert == 200.0
    assert wert.differenz == 100.0  # sum-basiert, nicht state (das wäre 6.0)


def test_monatswert_state_fallback_wenn_sum_null():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.zaehler", "kWh", has_sum=False)
    _seed_row(svc, mid, datetime(2026, 5, 3, 0, 0), state=10.0, sum_val=None)
    _seed_row(svc, mid, datetime(2026, 5, 20, 0, 0), state=42.0, sum_val=None)

    with svc._engine.connect() as conn:
        meta = svc.get_metadata(conn, "sensor.zaehler")
        wert = svc.get_sensor_monatswert(conn, meta, "sensor.zaehler", 2026, 5)
    assert wert is not None
    assert wert.start_wert == 10.0
    assert wert.end_wert == 42.0
    assert wert.differenz == 32.0


def test_monatswert_einheit_wh_skaliert_nach_kwh():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv_wh", "Wh", has_sum=True)
    _seed_row(svc, mid, datetime(2026, 5, 5, 0, 0), sum_val=1000.0)
    _seed_row(svc, mid, datetime(2026, 5, 25, 0, 0), sum_val=5000.0)

    with svc._engine.connect() as conn:
        meta = svc.get_metadata(conn, "sensor.pv_wh")
        wert = svc.get_sensor_monatswert(conn, meta, "sensor.pv_wh", 2026, 5)
    assert wert is not None
    assert wert.start_wert == 1.0   # 1000 Wh → 1 kWh
    assert wert.end_wert == 5.0
    assert wert.differenz == 4.0


def test_monatswert_anderer_monat_ausgeschlossen():
    """Nur Zeilen im Zielmonat zählen; April-/Juni-Werte verändern das Delta nicht."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh", has_sum=True)
    _seed_row(svc, mid, datetime(2026, 4, 30, 0, 0), sum_val=50.0)   # Vormonat
    _seed_row(svc, mid, datetime(2026, 5, 2, 0, 0), sum_val=100.0)
    _seed_row(svc, mid, datetime(2026, 5, 28, 0, 0), sum_val=200.0)
    _seed_row(svc, mid, datetime(2026, 6, 1, 0, 0), sum_val=999.0)   # Folgemonat

    with svc._engine.connect() as conn:
        meta = svc.get_metadata(conn, "sensor.pv")
        wert = svc.get_sensor_monatswert(conn, meta, "sensor.pv", 2026, 5)
    assert wert.differenz == 100.0


def test_monatswert_keine_daten_gibt_none():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh", has_sum=True)
    with svc._engine.connect() as conn:
        meta = svc.get_metadata(conn, "sensor.pv")
        assert svc.get_sensor_monatswert(conn, meta, "sensor.pv", 2026, 5) is None


def test_get_monatswerte_aggregiert_und_skippt_unbekannte():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh", has_sum=True)
    _seed_row(svc, mid, datetime(2026, 5, 2, 0, 0), sum_val=100.0)
    _seed_row(svc, mid, datetime(2026, 5, 28, 0, 0), sum_val=130.0)

    resp = svc.get_monatswerte(["sensor.pv", "sensor.fehlt"], 2026, 5)
    assert resp.jahr == 2026
    assert resp.monat == 5
    assert resp.monat_name == "Mai"
    assert len(resp.sensoren) == 1  # unbekannter Sensor übersprungen
    assert resp.sensoren[0].differenz == 30.0


# ---------------------------------------------------------------------------
# get_monatsanfang_wert: MIN(state) im Monat
# ---------------------------------------------------------------------------

def test_monatsanfang_wert_min_state():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh", has_sum=True)
    _seed_row(svc, mid, datetime(2026, 5, 1, 0, 0), state=12.5)
    _seed_row(svc, mid, datetime(2026, 5, 15, 0, 0), state=80.0)
    assert svc.get_monatsanfang_wert("sensor.pv", 2026, 5) == 12.5


def test_monatsanfang_wert_unbekannt_gibt_none():
    svc = _make_service_with_mock_db()
    assert svc.get_monatsanfang_wert("sensor.weg", 2026, 5) is None


# ---------------------------------------------------------------------------
# get_verfuegbare_monate: Monatsgenerierung + Aktueller-Monat-Ausschluss
# ---------------------------------------------------------------------------

def test_verfuegbare_monate_generierung_vergangenheit():
    """Drei Monate weit in der Vergangenheit → keine Aktueller-Monat-Logik,
    pinnt reine Min/Max- + Monatsgenerierung."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh", has_sum=True)
    _seed_row(svc, mid, datetime(2024, 1, 10, 0, 0), sum_val=10.0)
    _seed_row(svc, mid, datetime(2024, 2, 10, 0, 0), sum_val=20.0)
    _seed_row(svc, mid, datetime(2024, 3, 10, 0, 0), sum_val=30.0)

    resp = svc.get_verfuegbare_monate(["sensor.pv"])
    assert resp.erstes_datum == date(2024, 1, 10)
    assert resp.letztes_datum == date(2024, 3, 10)
    assert resp.anzahl_monate == 3
    assert [(m.jahr, m.monat) for m in resp.monate] == [
        (2024, 1), (2024, 2), (2024, 3)
    ]
    assert resp.monate[0].monat_name == "Januar"


def test_verfuegbare_monate_aktueller_monat_ausgeschlossen():
    """Daten bis in den laufenden Monat → letztes_datum wird auf den
    Ersten des VORMONATS begrenzt (unvollständiger Monat ausgeschlossen)."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh", has_sum=True)
    today = date.today()
    # Startpunkt: vor 2 Monaten; Endpunkt: heute (laufender Monat)
    if today.month <= 2:
        start = date(today.year - 1, today.month + 10, 5)
    else:
        start = date(today.year, today.month - 2, 5)
    _seed_row(svc, mid, datetime(start.year, start.month, start.day, 0, 0), sum_val=10.0)
    _seed_row(svc, mid, datetime(today.year, today.month, max(1, today.day), 12, 0), sum_val=99.0)

    resp = svc.get_verfuegbare_monate(["sensor.pv"])
    # erwarteter Vormonats-Erster
    if today.month == 1:
        erwartet_letzter = date(today.year - 1, 12, 1)
    else:
        erwartet_letzter = date(today.year, today.month - 1, 1)
    assert resp.letztes_datum == erwartet_letzter
    # laufender Monat darf nicht in der Liste sein
    assert (today.year, today.month) not in [(m.jahr, m.monat) for m in resp.monate]


def test_verfuegbare_monate_unbekannte_sensoren_werfen():
    svc = _make_service_with_mock_db()
    try:
        svc.get_verfuegbare_monate(["sensor.weg"])
    except ValueError:
        pass
    else:
        raise AssertionError("ValueError erwartet bei komplett unbekannten Sensoren")


# ---------------------------------------------------------------------------
# get_value_at: Off-by-one-Periodenlogik (v3.25.9), has_sum/state/short_term
# ---------------------------------------------------------------------------

def test_value_at_hourly_periodenende_off_by_one():
    """Wert AT 12:00 = Zeile bei start_ts=11:00 (state/sum am Periodenende).
    Die Zeile bei start_ts=12:00 (= Wert um 13:00) darf NICHT zurückkommen."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh", has_sum=True)
    _seed_row(svc, mid, datetime(2026, 5, 15, 11, 0), sum_val=500.0)
    _seed_row(svc, mid, datetime(2026, 5, 15, 12, 0), sum_val=600.0)

    wert = svc.get_value_at("sensor.pv", datetime(2026, 5, 15, 12, 0))
    assert wert == 500.0


def test_value_at_has_sum_kein_state_fallback():
    """has_sum-Zähler mit sum=NULL → None (niemals auf state zurückfallen),
    sonst entstünden Counter-Spikes (#... sum/state-Mismatch)."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh", has_sum=True)
    _seed_row(svc, mid, datetime(2026, 5, 15, 11, 0), state=42.0, sum_val=None)
    assert svc.get_value_at("sensor.pv", datetime(2026, 5, 15, 12, 0)) is None


def test_value_at_power_sensor_ohne_energieeinheit_none():
    """Power-Sensor (W, has_sum=False) liefert nie kumulative Energie (#200)."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.leistung", "W", has_sum=False)
    _seed_row(svc, mid, datetime(2026, 5, 15, 11, 0), state=1234.0)
    assert svc.get_value_at("sensor.leistung", datetime(2026, 5, 15, 12, 0)) is None


def test_value_at_einheit_wh_skaliert():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv_wh", "Wh", has_sum=True)
    _seed_row(svc, mid, datetime(2026, 5, 15, 11, 0), sum_val=3000.0)
    assert svc.get_value_at("sensor.pv_wh", datetime(2026, 5, 15, 12, 0)) == 3.0


def test_value_at_short_term_5min_periode():
    """short_term=True → Periode 5 Min, liest statistics_short_term.
    Wert AT 12:00 = Zeile bei start_ts=11:55."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh", has_sum=True)
    _seed_row(svc, mid, datetime(2026, 5, 15, 11, 55), sum_val=700.0,
              table="statistics_short_term")
    wert = svc.get_value_at(
        "sensor.pv", datetime(2026, 5, 15, 12, 0), short_term=True
    )
    assert wert == 700.0


def test_value_at_ausserhalb_toleranz_none():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh", has_sum=True)
    # Zeile 5 h vom Ziel-Periodenende entfernt, Toleranz 60 Min → kein Treffer
    _seed_row(svc, mid, datetime(2026, 5, 15, 6, 0), sum_val=500.0)
    wert = svc.get_value_at(
        "sensor.pv", datetime(2026, 5, 15, 12, 0), toleranz_minuten=60
    )
    assert wert is None


# ---------------------------------------------------------------------------
# get_hourly_sensor_data: W→kW, kWh-Skip
# ---------------------------------------------------------------------------

def test_hourly_sensor_data_w_zu_kw():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv_w", "W", has_sum=False)
    _seed_row(svc, mid, datetime(2026, 5, 15, 10, 0), mean=2000.0)
    _seed_row(svc, mid, datetime(2026, 5, 15, 11, 0), mean=3000.0)

    result = svc.get_hourly_sensor_data(["sensor.pv_w"], date(2026, 5, 15), date(2026, 5, 15))
    tag = result["sensor.pv_w"]["2026-05-15"]
    assert tag[10] == 2.0
    assert tag[11] == 3.0


def test_hourly_sensor_data_kw_unveraendert_und_prozent():
    svc = _make_service_with_mock_db()
    mid_kw = _seed_sensor(svc, "sensor.pv_kw", "kW", has_sum=False)
    mid_soc = _seed_sensor(svc, "sensor.soc", "%", has_sum=False)
    _seed_row(svc, mid_kw, datetime(2026, 5, 15, 9, 0), mean=4.5)
    _seed_row(svc, mid_soc, datetime(2026, 5, 15, 9, 0), mean=88.0)

    result = svc.get_hourly_sensor_data(
        ["sensor.pv_kw", "sensor.soc"], date(2026, 5, 15), date(2026, 5, 15)
    )
    assert result["sensor.pv_kw"]["2026-05-15"][9] == 4.5
    assert result["sensor.soc"]["2026-05-15"][9] == 88.0


def test_hourly_sensor_data_kwh_counter_uebersprungen():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv_kwh", "kWh", has_sum=True)
    _seed_row(svc, mid, datetime(2026, 5, 15, 9, 0), mean=5.0)
    result = svc.get_hourly_sensor_data(["sensor.pv_kwh"], date(2026, 5, 15), date(2026, 5, 15))
    assert result == {}  # Energie-Zähler ist kein Leistungssensor


# ---------------------------------------------------------------------------
# Standalone-Runner (Haus-Stil der test_ha_lts_*-Dateien)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    fehler = 0
    for t in tests:
        try:
            t()
            print(f"  ✓ {t.__name__}")
        except Exception:
            fehler += 1
            print(f"  ✗ {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - fehler}/{len(tests)} grün")
    sys.exit(1 if fehler else 0)
