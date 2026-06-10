"""Akzeptanztest: Live-Tagesverlauf-Kurve aus `statistics_short_term`.

Konsistenz-, kein Genauigkeitsfall (#135-Folge): im Add-on-Modus speist die
Butterfly-Kurve ihre Slots aus derselben SoT-Familie wie die Heute-kWh-Kacheln
(`safe_get_tages_kwh`). Für einen kWh-Zähler gilt dann **exakt**
``Σ Kurven-Slot-Energie == Tages-Zähler-Delta`` (gleiche Quelle).

Self-contained Standalone-Script:

    eedc/backend/venv/bin/python eedc/backend/tests/test_live_tagesverlauf_short_term.py

Testet:
  1. Pure Helfer: counter_deltas_zu_leistung (P = ΔkWh*12000), Skip
     negativer/None-Deltas; means_zu_leistung (Einheit-Faktor).
  2. get_short_term_5min_for_day: korrekte 5-Min-Deltas + Wh-Skalierung +
     Reset (negatives Delta) + Mean-Extraktion.
  3. Kern-Konsistenz: Σ 10-Min-Slot-Energie der Kurve == Tages-Zähler-Delta
     (das, was die kWh-Kachel rechnet) — exakt, nicht nur < 2 %.
  4. Fallback: Sensor ohne short_term-Daten → leeres Overlay.
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

from backend.services.ha_statistics_service import (  # noqa: E402
    HAStatisticsService,
    SHORT_TERM_SLOT,
)
from backend.core.berechnungen.live_tagesverlauf_5min import (  # noqa: E402
    counter_deltas_zu_leistung,
    means_zu_leistung,
)


# ── Test-DB-Setup ─────────────────────────────────────────────────────

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
            CREATE TABLE statistics_short_term (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                metadata_id INTEGER,
                start_ts REAL,
                state REAL,
                sum REAL,
                mean REAL
            )
        """))
    return svc


def _seed_sensor(svc, entity_id: str, unit: str, has_sum: bool = True) -> int:
    with svc._engine.begin() as conn:
        result = conn.execute(
            text("INSERT INTO statistics_meta (statistic_id, unit_of_measurement, has_sum, has_mean) "
                 "VALUES (:sid, :unit, :hs, :hm)"),
            {"sid": entity_id, "unit": unit, "hs": 1 if has_sum else 0, "hm": 0 if has_sum else 1},
        )
        return result.lastrowid


def _seed_row(svc, mid: int, when: datetime, sum_val=None, mean_val=None) -> None:
    ts = time_module.mktime(when.timetuple())
    with svc._engine.begin() as conn:
        conn.execute(
            text("INSERT INTO statistics_short_term (metadata_id, start_ts, state, sum, mean) "
                 "VALUES (:mid, :ts, NULL, :s, :m)"),
            {"mid": mid, "ts": ts, "s": sum_val, "m": mean_val},
        )


# ── 1. Pure Helfer ────────────────────────────────────────────────────

def test_pure_counter_deltas_zu_leistung():
    t0 = datetime(2026, 5, 15, 0, 0)
    # 0.5 kWh in 5 Min = 6000 W mittlere Leistung.
    deltas = {t0: 0.5, t0 + timedelta(minutes=5): 0.1}
    pts = counter_deltas_zu_leistung(deltas)
    assert pts == [(t0, 6000.0), (t0 + timedelta(minutes=5), 1200.0)], pts


def test_pure_counter_skip_negativ_und_none():
    t0 = datetime(2026, 5, 15, 12, 0)
    deltas = {
        t0: 0.2,
        t0 + timedelta(minutes=5): -3.0,   # Reset → skip
        t0 + timedelta(minutes=10): None,  # Lücke → skip
        t0 + timedelta(minutes=15): 0.1,
    }
    pts = counter_deltas_zu_leistung(deltas)
    assert [t for t, _ in pts] == [t0, t0 + timedelta(minutes=15)], pts


def test_pure_means_zu_leistung_einheit_faktor():
    t0 = datetime(2026, 5, 15, 10, 0)
    means = {t0: 2.5, t0 + timedelta(minutes=5): None, t0 + timedelta(minutes=10): 3.0}
    # kW → W: Faktor 1000
    pts = means_zu_leistung(means, 1000.0)
    assert pts == [(t0, 2500.0), (t0 + timedelta(minutes=10), 3000.0)], pts


# ── 2. DB-Methode ─────────────────────────────────────────────────────

def _seed_counter_day(svc, mid, datum, start_counter, schritt_kwh, n_slots, unit_scale=1.0):
    """Schreibt n_slots+1 short_term-sum-Rows ab 23:55 Vortag.

    Row bei start_ts=t hat sum = Counter am Ende von [t, t+5min) = Counter(t+5).
    Row 23:55 Vortag liefert damit Counter(00:00). Counter steigt um
    `schritt_kwh` pro 5-Min-Slot.
    """
    base = datetime.combine(datum, datetime.min.time()) - timedelta(minutes=SHORT_TERM_SLOT)
    for i in range(n_slots + 1):
        when = base + timedelta(minutes=i * SHORT_TERM_SLOT)
        counter_kwh = start_counter + i * schritt_kwh
        _seed_row(svc, mid, when, sum_val=counter_kwh / unit_scale)


def test_db_counter_deltas_korrekt():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv_kwh", "kWh")
    datum = date(2026, 5, 15)
    # 12 Slots à 0.25 kWh ab Counter 1000.
    _seed_counter_day(svc, mid, datum, 1000.0, 0.25, n_slots=12)
    bis = datetime.combine(datum, datetime.min.time()) + timedelta(minutes=12 * SHORT_TERM_SLOT)

    res = svc.get_short_term_5min_for_day(["sensor.pv_kwh"], datum, bis=bis)
    assert "sensor.pv_kwh" in res
    deltas = res["sensor.pv_kwh"]["counter_deltas"]
    # 12 Slots (00:00 .. 00:55) mit Delta 0.25.
    assert len(deltas) == 12, f"erwartet 12 Deltas, bekommen {len(deltas)}"
    for t, d in deltas.items():
        assert abs(d - 0.25) < 1e-9, f"Slot {t}: {d}"


def test_db_einheit_wh_skaliert():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv_wh", "Wh")
    datum = date(2026, 5, 15)
    # 250 Wh pro Slot = 0.25 kWh.
    _seed_counter_day(svc, mid, datum, 1_000_000.0, 0.25, n_slots=6, unit_scale=0.001)
    bis = datetime.combine(datum, datetime.min.time()) + timedelta(minutes=6 * SHORT_TERM_SLOT)

    res = svc.get_short_term_5min_for_day(["sensor.pv_wh"], datum, bis=bis)
    deltas = res["sensor.pv_wh"]["counter_deltas"]
    for t, d in deltas.items():
        assert abs(d - 0.25) < 1e-6, f"Wh-Slot {t}: {d} (erwartet 0.25 kWh)"


def test_db_reset_liefert_negatives_delta():
    """Counter springt einmal zurück → genau ein negatives Delta; der
    Pure-Helfer überspringt es (kein Riesen-Spike in der Kurve)."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.wp_kwh", "kWh")
    datum = date(2026, 5, 15)
    base = datetime.combine(datum, datetime.min.time()) - timedelta(minutes=SHORT_TERM_SLOT)
    counters = [100.0, 100.5, 101.0, 5.0, 5.5, 6.0]  # Reset bei Index 3
    for i, c in enumerate(counters):
        _seed_row(svc, mid, base + timedelta(minutes=i * SHORT_TERM_SLOT), sum_val=c)
    bis = datetime.combine(datum, datetime.min.time()) + timedelta(minutes=5 * SHORT_TERM_SLOT)

    res = svc.get_short_term_5min_for_day(["sensor.wp_kwh"], datum, bis=bis)
    deltas = res["sensor.wp_kwh"]["counter_deltas"]
    negative = [d for d in deltas.values() if d < 0]
    assert len(negative) == 1, f"erwartet genau 1 negatives Delta, bekommen {negative}"
    pts = counter_deltas_zu_leistung(deltas)
    assert all(p >= 0 for _, p in pts), "Pure-Helfer darf keine negative Leistung liefern"


def test_db_mean_extraktion_power_sensor():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.batterie_w", "W", has_sum=False)
    datum = date(2026, 5, 15)
    base = datetime.combine(datum, datetime.min.time())
    for i, mw in enumerate([1500.0, -800.0, 0.0]):  # Lade/Entlade-Vorzeichen erhalten
        _seed_row(svc, mid, base + timedelta(minutes=i * SHORT_TERM_SLOT), mean_val=mw)
    bis = base + timedelta(minutes=3 * SHORT_TERM_SLOT)

    res = svc.get_short_term_5min_for_day(["sensor.batterie_w"], datum, bis=bis)
    data = res["sensor.batterie_w"]
    assert data["has_sum"] is False
    assert not data["counter_deltas"], "Power-Sensor ohne sum → keine Counter-Deltas"
    means = means_zu_leistung(data["means"], 1.0)  # W → Faktor 1.0
    assert [v for _, v in means] == [1500.0, -800.0, 0.0], means


# ── 3. Kern-Konsistenz: Σ Kurven-Slot-Energie == Tages-Zähler-Delta ───

def _simuliere_kurven_tages_kwh(power_punkte, start, end):
    """Repliziert die 10-Min-Slot-Aggregation des Live-Tagesverlaufs und
    integriert die Slot-Leistungen zur Tages-kWh.

    Kurve: pro 10-Min-Slot avg_w = mean(Punkte in [h_start,h_end)); Slot-Wert
    in kW = avg_w/1000; Slot-Energie = Slot-kW * 10/60 h.
    """
    tages_kwh = 0.0
    for m in range(144):
        h_start = start + timedelta(minutes=m * 10)
        h_end = h_start + timedelta(minutes=10)
        if h_start >= end:
            break
        h_points = [p[1] for p in power_punkte if h_start <= p[0] < h_end]
        if h_points:
            avg_w = sum(h_points) / len(h_points)
            tages_kwh += (avg_w / 1000.0) * (10.0 / 60.0)
    return tages_kwh


def test_kern_konsistenz_kurve_gleich_zaehler_delta():
    """Kurven-Integral == (Counter(end) − Counter(00:00)) — exakt.

    Das ist genau die Größe, die safe_get_tages_kwh aus demselben Zähler zieht
    (MAX(sum)−MIN(sum) über den Tag). Gleiche Quelle ⇒ deckungsgleich.
    """
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv_kwh", "kWh")
    datum = date(2026, 5, 15)
    start = datetime.combine(datum, datetime.min.time())
    # Unregelmäßige PV-Kurve: variierende 5-Min-Schritte, 144 Slots (12 h).
    schritte = [0.0] * 12 + [round(0.05 + 0.01 * (i % 7), 4) for i in range(132)]
    base = start - timedelta(minutes=SHORT_TERM_SLOT)
    counter = 5000.0
    counter_bei_0 = None
    n = len(schritte)
    for i in range(n + 1):
        when = base + timedelta(minutes=i * SHORT_TERM_SLOT)
        _seed_row(svc, mid, when, sum_val=counter)
        if i == 1:  # Row bei 00:00 → Counter(00:05); Counter(00:00) = Row 23:55
            pass
        if when == start:
            counter_bei_0 = counter
        if i < n:
            counter += schritte[i]
    counter_end = counter  # Counter am Ende des letzten Slots
    end = base + timedelta(minutes=n * SHORT_TERM_SLOT)

    res = svc.get_short_term_5min_for_day(["sensor.pv_kwh"], datum, bis=end)
    deltas = res["sensor.pv_kwh"]["counter_deltas"]
    pts = counter_deltas_zu_leistung(deltas)
    kurve_kwh = _simuliere_kurven_tages_kwh(pts, start, end)

    zaehler_delta = counter_end - counter_bei_0
    assert abs(kurve_kwh - zaehler_delta) < 1e-6, (
        f"Kurve {kurve_kwh:.6f} != Zähler-Delta {zaehler_delta:.6f}")


# ── 4. Fallback ───────────────────────────────────────────────────────

def test_fallback_kein_short_term():
    """Sensor existiert in meta, aber keine short_term-Rows → leere Bausteine,
    Pure-Helfer liefern leere Punktlisten (Aufrufer behält rohe History)."""
    svc = _make_service_with_mock_db()
    _seed_sensor(svc, "sensor.leer_kwh", "kWh")
    datum = date(2026, 5, 15)
    res = svc.get_short_term_5min_for_day(["sensor.leer_kwh"], datum)
    data = res.get("sensor.leer_kwh", {})
    assert not data.get("counter_deltas"), data
    assert counter_deltas_zu_leistung(data.get("counter_deltas", {})) == []


def test_fallback_unbekannter_sensor():
    svc = _make_service_with_mock_db()
    res = svc.get_short_term_5min_for_day(["sensor.gibt_es_nicht"], date(2026, 5, 15))
    assert res == {}, res


_TESTS = [
    test_pure_counter_deltas_zu_leistung,
    test_pure_counter_skip_negativ_und_none,
    test_pure_means_zu_leistung_einheit_faktor,
    test_db_counter_deltas_korrekt,
    test_db_einheit_wh_skaliert,
    test_db_reset_liefert_negatives_delta,
    test_db_mean_extraktion_power_sensor,
    test_kern_konsistenz_kurve_gleich_zaehler_delta,
    test_fallback_kein_short_term,
    test_fallback_unbekannter_sensor,
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
