"""
Unit-Tests für die zwei WP-Aggregations-Bugs aus Issue #230 (Forum #491).

Bug 1 — WP-Starts Stunden-Plausibilitäts-Cap:
    Counter-Spike (z.B. 49.073) aus HA-Statistics sum/state-Mix (#184) muss in
    `get_hourly_counter_sum_by_feld` auf 0 geklemmt werden, damit Stunden-Tab
    und Tages-Tab nicht drift'n.

Bug 2 — WP-Kategorisierung bei getrennte_strommessung:
    `_categorize_counter` muss `strom_heizen_kwh` und `strom_warmwasser_kwh`
    als `verbrauch_wp` erkennen, wenn `parameter.getrennte_strommessung=True`
    — analog zu `get_wp_strom_kwh` (SoT in field_definitions.py).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from backend.models import Anlage, Investition  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.snapshot import (
    get_hourly_counter_sum_by_feld,
    get_komponenten_tageskwh,
)
from backend.services.snapshot.keys import _categorize_counter


# ───────────────────────────── Fixture ──────────────────────────────


async def _make_anlage_with_wp(
    session: AsyncSession,
    *,
    getrennte_strommessung: bool,
) -> tuple[Anlage, Investition]:
    """Anlage + Wärmepumpe-Investition + Sensor-Mapping (split oder single)."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="DE")
    session.add(anlage)
    await session.flush()
    inv = Investition(
        anlage_id=anlage.id,
        typ="waermepumpe",
        bezeichnung="Vitocal Test",
        parameter={"getrennte_strommessung": getrennte_strommessung},
    )
    session.add(inv)
    await session.flush()

    if getrennte_strommessung:
        felder = {
            "strom_heizen_kwh": {
                "strategie": "sensor", "sensor_id": "sensor.wp_heizen",
            },
            "strom_warmwasser_kwh": {
                "strategie": "sensor", "sensor_id": "sensor.wp_ww",
            },
            "wp_starts_anzahl": {
                "strategie": "sensor", "sensor_id": "sensor.wp_starts",
            },
        }
    else:
        felder = {
            "stromverbrauch_kwh": {
                "strategie": "sensor", "sensor_id": "sensor.wp_strom",
            },
            "wp_starts_anzahl": {
                "strategie": "sensor", "sensor_id": "sensor.wp_starts",
            },
        }
    anlage.sensor_mapping = {
        "investitionen": {str(inv.id): {"felder": felder}}
    }
    await session.commit()
    return anlage, inv


async def _put_snapshot(
    session: AsyncSession,
    anlage_id: int,
    sensor_key: str,
    zeitpunkt: datetime,
    wert: float,
) -> None:
    session.add(SensorSnapshot(
        anlage_id=anlage_id,
        sensor_key=sensor_key,
        zeitpunkt=zeitpunkt,
        wert_kwh=wert,
        quelle="ha_statistics",
    ))


# ───────────────────────────── Bug 2: Kategorisierung ──────────────────────────────


def test_kategorisierung_wp_getrennt_strommessung():
    """Bei getrennte_strommessung=True → strom_heizen_kwh + strom_warmwasser_kwh."""
    p_split = {"getrennte_strommessung": True}
    assert _categorize_counter("strom_heizen_kwh", "waermepumpe", p_split) == "verbrauch_wp"
    assert _categorize_counter("strom_warmwasser_kwh", "waermepumpe", p_split) == "verbrauch_wp"
    # Gesamt-Sensor wird im Split-Modus IGNORIERT, damit keine Doppelzählung
    # passiert (analog zu get_wp_strom_kwh).
    assert _categorize_counter("stromverbrauch_kwh", "waermepumpe", p_split) is None
    # Thermische Felder bleiben ungezählt (Wärme ≠ Strom)
    assert _categorize_counter("heizenergie_kwh", "waermepumpe", p_split) is None
    assert _categorize_counter("warmwasser_kwh", "waermepumpe", p_split) is None


def test_kategorisierung_wp_single_sensor():
    """Ohne getrennte_strommessung → nur stromverbrauch_kwh."""
    p_single = {"getrennte_strommessung": False}
    assert _categorize_counter("stromverbrauch_kwh", "waermepumpe", p_single) == "verbrauch_wp"
    assert _categorize_counter("strom_heizen_kwh", "waermepumpe", p_single) is None
    assert _categorize_counter("strom_warmwasser_kwh", "waermepumpe", p_single) is None


def test_kategorisierung_wp_legacy_kein_param():
    """Legacy-Anlagen ohne parameter-Dict: default = single-Sensor-Modus."""
    assert _categorize_counter("stromverbrauch_kwh", "waermepumpe", None) == "verbrauch_wp"
    assert _categorize_counter("strom_heizen_kwh", "waermepumpe", None) is None


# ───────────────────────────── Bug 2: get_komponenten_tageskwh ──────────────────────────────


async def test_komponenten_tageskwh_wp_split_sensors_summieren(db):
    """Mit getrennte_strommessung: Tages-WP-Verbrauch = strom_heizen + strom_warmwasser."""
    anlage, inv = await _make_anlage_with_wp(db, getrennte_strommessung=True)

    datum = date(2026, 5, 10)
    tag_start = datetime.combine(datum, datetime.min.time())
    tag_ende = tag_start + timedelta(days=1)

    # Tages-Diff: Heizen 200,3 + Warmwasser 44,8 = 245,1 kWh
    await _put_snapshot(db, anlage.id, f"inv:{inv.id}:strom_heizen_kwh", tag_start, 1000.0)
    await _put_snapshot(db, anlage.id, f"inv:{inv.id}:strom_heizen_kwh", tag_ende, 1200.3)
    await _put_snapshot(db, anlage.id, f"inv:{inv.id}:strom_warmwasser_kwh", tag_start, 500.0)
    await _put_snapshot(db, anlage.id, f"inv:{inv.id}:strom_warmwasser_kwh", tag_ende, 544.8)
    await db.commit()

    result = await get_komponenten_tageskwh(
        db, anlage, {str(inv.id): inv}, datum
    )
    assert f"waermepumpe_{inv.id}" in result
    assert abs(result[f"waermepumpe_{inv.id}"] - 245.1) < 0.01


async def test_komponenten_tageskwh_wp_single_sensor(db):
    """Ohne getrennte_strommessung: Tages-WP-Verbrauch = stromverbrauch_kwh."""
    anlage, inv = await _make_anlage_with_wp(db, getrennte_strommessung=False)

    datum = date(2026, 5, 10)
    tag_start = datetime.combine(datum, datetime.min.time())
    tag_ende = tag_start + timedelta(days=1)

    await _put_snapshot(db, anlage.id, f"inv:{inv.id}:stromverbrauch_kwh", tag_start, 1000.0)
    await _put_snapshot(db, anlage.id, f"inv:{inv.id}:stromverbrauch_kwh", tag_ende, 1247.9)
    await db.commit()

    result = await get_komponenten_tageskwh(
        db, anlage, {str(inv.id): inv}, datum
    )
    assert f"waermepumpe_{inv.id}" in result
    assert abs(result[f"waermepumpe_{inv.id}"] - 247.9) < 0.01


# ───────────────────────────── Bug 1: Plausibilitäts-Cap ──────────────────────────────


async def test_hourly_counter_cap_spike_geklemmt(db):
    """Ein einzelner 49.073-Snapshot-Spike in einer Stunde wird auf 0 geklemmt,
    damit Stunden-Tab und Tages-Tab konsistent bleiben."""
    anlage, inv = await _make_anlage_with_wp(db, getrennte_strommessung=True)

    datum = date(2026, 5, 7)
    # Backward-Konvention: Slot h = snap[h] − snap[h−1] mit Start bei
    # Vortag-23. Wir füllen die 25 Snapshots so, dass Slot 1 (von Stunde 0
    # auf 1) auf 49.073 hochspringt und dann wieder runter — der Spike
    # selbst ist absurd, alle umliegenden Werte normal.
    sensor_key = f"inv:{inv.id}:wp_starts_anzahl"
    snaps = []
    for h in range(25):
        ts = datetime.combine(datum, datetime.min.time()) + timedelta(hours=h - 1)
        if h == 1:
            wert = 1_000_049_073.0  # Spike bei Snapshot um Stunde 0:00
        elif h >= 2:
            wert = 100.0 + h  # nach Spike: normale Sequenz
        else:
            wert = 100.0
        snaps.append((ts, wert))
        await _put_snapshot(db, anlage.id, sensor_key, ts, wert)
    await db.commit()

    result = await get_hourly_counter_sum_by_feld(
        db, anlage, {str(inv.id): inv}, datum, "wp_starts_anzahl",
    )
    # Backward-Konvention (#144): Slot h = snap[Heute h:00] − snap[Heute (h−1):00],
    # mit Slot 0 = snap[00:00] − snap[Vortag 23:00].
    #   Slot 0: 1.000.049.073 − 100 = SPIKE → 0
    #   Slot 1: 102 − 1.000.049.073 = negativ → 0
    #   Slot 2: 103 − 102 = 1
    assert all(v is not None for v in result.values())
    assert result[0] == 0, "Spike-Slot muss geklemmt sein"
    assert result[1] == 0, "Folge-Slot mit negativem Delta muss geklemmt sein"
    assert result[2] == 1, "Normaler Slot nach Spike läuft regulär"


async def test_hourly_counter_normal_werte_passieren(db):
    """Realistische WP-Start-Werte (z.B. 2-15 Starts/h) werden NICHT geklemmt."""
    anlage, inv = await _make_anlage_with_wp(db, getrennte_strommessung=True)

    datum = date(2026, 5, 8)
    sensor_key = f"inv:{inv.id}:wp_starts_anzahl"
    # Vortag-23 = 100, plus 5 Starts in jeder Folgestunde → 24×5 = 120 Tages-Total
    for h in range(25):
        ts = datetime.combine(datum, datetime.min.time()) + timedelta(hours=h - 1)
        await _put_snapshot(db, anlage.id, sensor_key, ts, 100.0 + h * 5)
    await db.commit()

    result = await get_hourly_counter_sum_by_feld(
        db, anlage, {str(inv.id): inv}, datum, "wp_starts_anzahl",
    )
    # Jeder Slot = 5
    for h in range(24):
        assert result[h] == 5, f"Slot {h} = {result[h]} (expected 5)"
