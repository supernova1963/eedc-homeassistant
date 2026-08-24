"""
Akzeptanztest für Etappe 5 (v3.31.0):
`HAStatisticsService.get_hourly_mean_for_day()` — Stunden-Mean roh + Einheit
für einen Sensor und Tag. Verwendet von `_get_soc_history` (Speicher-SoC %)
und `_get_strompreis_stunden` (Sensor-Endpreis EUR/kWh, cent/kWh, …).

Im Gegensatz zu `get_hourly_sensor_data()` werden Rohwerte zurückgegeben —
ohne Einheitenumrechnung. Der Aufrufer kennt seinen Kontext besser.

Schwesterdateien der `ha_lts`-Familie (SoT des HA-Schemas: `ha_lts_helfer.py`):
`test_ha_lts_hourly_reader.py` (Stunden-Summen) - `test_ha_lts_minmax_reader.py`
(Stunden-Min/Max) - `test_ha_lts_monatswerte_lookup.py` (Monatswerte + get_value_at).
"""

from __future__ import annotations

from datetime import date, datetime


from backend.services.ha_statistics_service import HAStatisticsService
from backend.tests import ha_lts_helfer


def _make_service_with_mock_db() -> HAStatisticsService:
    """Service auf In-Memory-SQLite mit HA-Schema — SoT: `ha_lts_helfer`."""
    return ha_lts_helfer.mach_service()


def _seed_sensor(svc: HAStatisticsService, entity_id: str, unit: str) -> int:
    return ha_lts_helfer.sensor(svc, entity_id, unit, has_sum=False)


def _seed_mean(svc: HAStatisticsService, metadata_id: int, when: datetime, mean: float) -> None:
    ha_lts_helfer.zeile(svc, metadata_id, when, mean=mean)


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
