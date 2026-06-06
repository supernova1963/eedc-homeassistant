"""Counter-Daily-Drift — Variante 2-light (KONZEPT-COUNTER-DAILY-DRIFT.md).

Die Stunden-Σ (`TagesEnergieProfil.wp_starts_anzahl[h]`) wird aus dem Tages-
Boundary-Diff (`TagesZusammenfassung.komponenten_starts`) abgeleitet — eine
Quelle pro Tag. Bei sauberen Snapshots verhaltensneutral; bei NULL-Slots /
Snapshot-Lücken wird die Stunden-Σ so reskaliert, dass
`Σ_h wp_starts_anzahl[h] == Σ_inv komponenten_starts` bleibt.

Pflicht-Invariante `pruefe_counter_konsistent` feuert bei künstlicher Drift.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen import (
    assert_counter_konsistent,
    pruefe_counter_konsistent,
    verteile_counter_auf_stunden,
)
from backend.models import Anlage, Investition  # noqa: F401
from backend.models.sensor_snapshot import SensorSnapshot
from backend.services.snapshot import (
    get_daily_counter_deltas_by_inv,
    get_hourly_counter_sum_by_feld,
)


# ─── Helper-Unit-Tests ──────────────────────────────────────────────────────

def test_saubere_daten_unveraendert():
    """Σ_h == Tages-Σ → Stunden-Σ bleibt bit-genau erhalten (verhaltensneutral)."""
    stunden = {h: 5 for h in range(24)}  # Σ = 120
    out = verteile_counter_auf_stunden(stunden, 120.0, as_float=False)
    assert out == stunden


def test_null_slot_wird_auf_tagessumme_reskaliert():
    """Ein NULL-Slot senkt die Stunden-Σ; nach Ableitung gilt wieder Σ_h == Tages-Σ."""
    stunden = {h: (None if h in (12, 13) else 5) for h in range(24)}  # Σ_belegt = 110
    assert sum(v for v in stunden.values() if v is not None) == 110
    out = verteile_counter_auf_stunden(stunden, 120.0, as_float=False)
    # Σ exakt wiederhergestellt, Lücken bleiben Lücken, alles ganzzahlig.
    assert sum(v for v in out.values() if v is not None) == 120
    assert out[12] is None and out[13] is None
    assert all(isinstance(v, int) for v in out.values() if v is not None)


def test_float_counter_reskaliert_gebrochen():
    """Float-Counter (Betriebsstunden) behalten Nachkommastellen beim Ableiten."""
    stunden = {h: (None if h == 6 else 0.5) for h in range(24)}  # Σ_belegt = 11.5
    out = verteile_counter_auf_stunden(stunden, 12.0, as_float=True)
    assert sum(v for v in out.values() if v is not None) == pytest.approx(12.0, abs=0.05)
    assert out[6] is None


def test_tages_summe_null_zieht_belegte_slots_auf_null():
    """Boundary-Diff sagt 0 Ereignisse → belegte Slots werden 0, Lücken bleiben."""
    stunden = {0: 3, 1: None, 2: 4}
    out = verteile_counter_auf_stunden(stunden, 0.0, as_float=False)
    assert out == {0: 0, 1: None, 2: 0}


def test_invariante_feuert_bei_drift():
    """`pruefe_counter_konsistent` erkennt Drift; `assert_*` wirft."""
    stunden = {h: (None if h == 12 else 5) for h in range(24)}  # Σ = 115
    bericht = pruefe_counter_konsistent(stunden, 120.0, name="counter:wp_starts_anzahl")
    assert not bericht.konsistent
    assert bericht.erwartet == 120.0 and bericht.tatsaechlich == 115
    with pytest.raises(AssertionError):
        assert_counter_konsistent(stunden, 120.0)


def test_invariante_ok_nach_ableitung():
    """Nach `verteile_counter_auf_stunden` ist die Invariante erfüllt."""
    stunden = {h: (None if h in (12, 13) else 5) for h in range(24)}
    out = verteile_counter_auf_stunden(stunden, 120.0, as_float=False)
    assert pruefe_counter_konsistent(out, 120.0).konsistent


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
    """Echter NULL-Slot: ein fehlender Stunden-Snapshot senkt die Stunden-Σ,
    der Tages-Boundary-Diff bleibt unberührt. Nach Ableitung aus dem Boundary-
    Diff gilt wieder Σ_h == komponenten_starts[inv_id]."""
    anlage, inv = await _make_anlage_mit_wp(db)
    datum = date(2026, 5, 10)
    sensor_key = f"inv:{inv.id}:wp_starts_anzahl"
    # Vortag-23 .. Folgetag-0: +5 Starts/h. Tages-Total = 120.
    # Den Snapshot an Stunde 12:00 AUSLASSEN → Slots 12 und 13 werden NULL.
    for h in range(26):
        if h - 1 == 12:
            continue  # NULL-Slot simulieren
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

    # Vorbedingung: der NULL-Slot hat die Stunden-Σ unter den Tages-Wert gedrückt.
    roh_summe = sum(v for v in hourly.values() if v is not None)
    assert roh_summe < daily_total, (
        f"NULL-Slot sollte Drift erzeugen: hourly={roh_summe}, daily={daily_total}"
    )
    assert not pruefe_counter_konsistent(hourly, daily_total).konsistent

    # Ableitung aus dem Boundary-Diff stellt die Konsistenz her.
    abgeleitet = verteile_counter_auf_stunden(hourly, daily_total, as_float=False)
    assert sum(v for v in abgeleitet.values() if v is not None) == int(daily_total)
    assert pruefe_counter_konsistent(abgeleitet, daily_total).konsistent
