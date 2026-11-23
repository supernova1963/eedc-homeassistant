"""Counter-Drift (WP-Starts, Betriebsstunden) — seit Fund-Päckchen F (F6, 23.11.2026) ohne Reskalierung.

Bis dahin wurde die Stunden-Σ auf den Tages-Boundary-Diff reskaliert (Variante 2-light, KONZEPT-COUNTER-DAILY-DRIFT.md).
Jetzt tragen die Stunden, was die Stände hergeben: eine Lücke bündelt die Menge in der ersten Stunde danach, Σ Stunden ist
die Menge im Fenster der Stunden (``CounterStunden.fenster``). Pflicht-Invariante `pruefe_counter_konsistent` feuert bei
künstlicher Drift. Proben zu Fenster und Lücke: ``test_funde_f.py``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen import (
    assert_counter_konsistent,
    pruefe_counter_konsistent,
)
from backend.models import Anlage, Investition  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.snapshot import (
    get_daily_counter_deltas_by_inv,
    get_hourly_counter_sum_by_feld,
)


# ─── Invariante ─────────────────────────────────────────────────────────────

def test_invariante_feuert_bei_drift():
    """`pruefe_counter_konsistent` erkennt Drift; `assert_*` wirft."""
    stunden = {h: (None if h == 12 else 5) for h in range(24)}  # Σ = 115
    bericht = pruefe_counter_konsistent(stunden, 120.0, name="counter:wp_starts_anzahl")
    assert not bericht.konsistent
    assert bericht.erwartet == 120.0 and bericht.tatsaechlich == 115
    with pytest.raises(AssertionError):
        assert_counter_konsistent(stunden, 120.0)


# ─── Integration mit echten Snapshots ─────────────────────────────────────────

async def _make_anlage_mit_wp(session: AsyncSession) -> tuple[Anlage, Investition]:
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, standort_land="DE")
    session.add(anlage)
    await session.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="WP",
        parameter={"getrennte_strommessung": False},
    )
    session.add(inv)
    await session.flush()
    anlage.sensor_mapping = {"investitionen": {str(inv.id): {"felder": {
        "wp_starts_anzahl": {"strategie": "sensor", "sensor_id": "sensor.wp_starts"},
    }}}}
    await session.commit()
    return anlage, inv


async def test_null_slot_snapshot_integration(db):
    """Echter NULL-Slot (F6): ein fehlender Stunden-Snapshot lässt die Stunde 12 leer, die Stunde 13 trägt das Bündel; die
    Stunden-Σ ist ohne Umrechnung die Menge im Fenster und hier der Tageswert (gleichmäßiger Zähler)."""
    anlage, inv = await _make_anlage_mit_wp(db)
    datum = date(2026, 5, 10)
    sensor_key = f"inv:{inv.id}:wp_starts_anzahl"
    # Vortag-23 .. Folgetag-0: +5 Starts/h. Tages-Total = 120. Den Snapshot an Stunde 12:00 AUSLASSEN.
    for h in range(26):
        if h - 1 == 12:
            continue
        ts = datetime.combine(datum, datetime.min.time()) + timedelta(hours=h - 1)
        db.add(SensorSnapshot(
            anlage_id=anlage.id, sensor_key=sensor_key, zeitpunkt=ts,
            wert_kwh=100.0 + h * 5, quelle="ha_statistics",
        ))
    await db.commit()

    invs = {str(inv.id): inv}
    hourly = await get_hourly_counter_sum_by_feld(db, anlage, invs, datum, "wp_starts_anzahl")
    daily = await get_daily_counter_deltas_by_inv(db, anlage, invs, datum)
    daily_total = float(sum(daily["wp_starts_anzahl"].values()))

    assert hourly[12] is None and hourly[13] == 10                      # Bündel in der Stunde danach
    assert sum(v for v in hourly.values() if v is not None) == 120 == daily_total
    assert hourly.fenster == 120.0
    assert pruefe_counter_konsistent(hourly, hourly.fenster).konsistent
