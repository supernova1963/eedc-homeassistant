"""Zählerlücken wie HA — Schnitt 3: `get_hourly_slots_for_day` (R1/R2, T1/T2).

Vorlage `plans/vorlage-zaehlerluecken-ha-weg.md` Fassung 7. Die Slot-Tabelle
legt je Stunde ab, was HA für diese Stunde zeigt: Stand(h) minus den letzten
**vorhandenen** Stand davor, Anker über den **Boundary-Index**, Spanne n in
**realen** Stunden. Proben P2 (Rohpfad), P5 (SQL == WS inkl. Anker-start_ts
und n), P8 (kein Anker), P9 (DST), dazu die Projektion
`get_hourly_kwh_deltas_for_day` (n == 1 ⇒ Wert, sonst None).

Schwesterdateien: test_ha_lts_hourly_reader.py (Rohpfad, bleibt unverändert),
test_ha_statistics_websocket_transport.py (Transport-Symmetrie),
test_zaehlerluecken_schema.py.
"""
from __future__ import annotations

import os
import time as _time
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import text

from backend.services.ha_statistics_service import SensorSlotReihe, StundenSlot
from backend.services.ha_statistics_ws import WsSensorMeta
from backend.tests import ha_lts_helfer
from backend.tests.test_ha_statistics_websocket_transport import _service_mit_ws, _zeile

SID = "sensor.zaehler"


@pytest.fixture
def berlin():
    """Die DST-Proben rechnen in Europe/Berlin — auch auf dem UTC-/Auckland-Runner."""
    alt = os.environ.get("TZ")
    os.environ["TZ"] = "Europe/Berlin"
    _time.tzset()
    try:
        yield
    finally:
        if alt is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = alt
        _time.tzset()


def _beide(zeilen: list[tuple[float, float]], unit: str = "kWh"):
    """(SQL-Service, WS-Service) mit denselben Zeilen [(start_ts, sum)]."""
    sql = ha_lts_helfer.mach_service()
    mid = ha_lts_helfer.sensor(sql, SID, unit, has_sum=True, has_mean=False)
    # Roh-`start_ts` statt `ha_lts_helfer.zeile` (mktime aus Wanduhr): die
    # Herbst-Doppelstunde 02:00 CEST/CET ist als Wanduhr nicht eindeutig.
    with sql._engine.begin() as conn:
        for ts, wert in zeilen:
            conn.execute(text(
                "INSERT INTO statistics (metadata_id, start_ts, state, sum) "
                "VALUES (:mid, :ts, :w, :w)"), {"mid": mid, "ts": ts, "w": wert})
    ws, _ = _service_mit_ws(
        {SID: WsSensorMeta(unit, True, False)},
        {SID: [_zeile(ts, sum=wert, state=wert) for ts, wert in zeilen]},
    )
    return sql, ws


def _stunden(von: datetime, bis: datetime, start: float, pro_h: float, ohne=()):
    """Stundenzeilen [von, bis] (lokale Wanduhr), Zähler steigt pro Stunde um pro_h."""
    out, t, w = [], von, start
    while t <= bis:
        if t not in ohne:
            out.append((t.timestamp(), round(w, 3)))
        w += pro_h
        t += timedelta(hours=1)
    return out


# ── P2 (Rohpfad): eine Zeile fehlt mitten am Tag ───────────────────────────


def test_p2_zeile_fehlt_naechster_slot_traegt_beide_stunden(berlin):
    datum = date(2026, 5, 15)
    zeilen = _stunden(datetime(2026, 5, 14, 22), datetime(2026, 5, 15, 22), 1000.0, 5.0,
                      ohne={datetime(2026, 5, 15, 11)})
    sql, _ = _beide(zeilen)
    reihe = sql.get_hourly_slots_for_day([SID], datum)[SID]
    assert 12 not in reihe.slots                       # Stand(12) fehlt ⇒ Slot leer
    assert reihe.slots[13] == StundenSlot(10.0, 2)     # trägt beide Stunden
    assert reihe.slots[0] == StundenSlot(5.0, 1)
    # Σ Stunden = HA-Tag: Stand(23) − Stand(−1)
    assert round(sum(s.delta for s in reihe.slots.values()), 3) == 24 * 5.0
    # Projektion behält die alte Form: der Bündel-Slot erscheint als Lücke
    proj = sql.get_hourly_kwh_deltas_for_day([SID], datum)[SID]
    assert proj[12] is None and proj[13] is None and proj[14] == 5.0


# ── P5: SQL == WS je Sensor und Tag, inklusive Anker-start_ts und n ─────────


@pytest.mark.parametrize("fall", ["lueckenlos", "anker_vor_fenster", "wh", "kein_anker", "anker_weit",
                                  "anker_null"])
def test_p5_sql_gleich_ws(berlin, fall):
    datum = date(2026, 5, 15)
    unit = "kWh"
    if fall == "lueckenlos":
        zeilen = _stunden(datetime(2026, 5, 14, 12), datetime(2026, 5, 15, 22), 500.0, 2.0)
    elif fall == "anker_vor_fenster":
        # Vortag 17:00 ist die letzte Zeile, dann erst heute 03:00 wieder.
        zeilen = (_stunden(datetime(2026, 5, 14, 10), datetime(2026, 5, 14, 17), 500.0, 1.0)
                  + _stunden(datetime(2026, 5, 15, 3), datetime(2026, 5, 15, 22), 530.0, 1.0))
    elif fall == "wh":
        unit = "Wh"
        zeilen = (_stunden(datetime(2026, 5, 14, 10), datetime(2026, 5, 14, 17), 500_000.0, 1000.0)
                  + _stunden(datetime(2026, 5, 15, 3), datetime(2026, 5, 15, 22), 530_000.0, 1000.0))
    elif fall == "kein_anker":
        zeilen = _stunden(datetime(2026, 5, 15, 5), datetime(2026, 5, 15, 22), 0.0, 1.5)
    elif fall == "anker_weit":  # Anker 20 Tage vorher — der WS-Weg braucht das 32-Tage-Fenster
        zeilen = ([(datetime(2026, 4, 25, 9).timestamp(), 100.0)]
                  + _stunden(datetime(2026, 5, 15, 3), datetime(2026, 5, 15, 22), 300.0, 1.0))
    else:  # anker_null: die letzte Zeile vor dem Fenster hat sum NULL — sie ist kein Anker
        zeilen = (_stunden(datetime(2026, 5, 14, 10), datetime(2026, 5, 14, 16), 500.0, 1.0)
                  + [(datetime(2026, 5, 14, 17).timestamp(), None)]
                  + _stunden(datetime(2026, 5, 15, 3), datetime(2026, 5, 15, 22), 530.0, 1.0))
    sql, ws = _beide(zeilen, unit)
    a = sql.get_hourly_slots_for_day([SID], datum)
    b = ws.get_hourly_slots_for_day([SID], datum)
    assert a == b, f"SQL {a} ≠ WS {b}"
    reihe = a[SID]
    if fall == "anker_vor_fenster":
        # Zähler(4) = sum @ 03:00 heute; Anker = Vortag 17:00 ⇒ 10 reale Stunden
        assert reihe.anker_start_ts == datetime(2026, 5, 14, 17).timestamp()
        assert reihe.slots[4] == StundenSlot(round(530.0 - 507.0, 3), 10)
        assert all(h not in reihe.slots for h in range(4))
    if fall == "wh":
        assert reihe.slots[4] == StundenSlot(23.0, 10)   # Wh → kWh, auch am Anker
    if fall == "kein_anker":
        assert reihe.anker_start_ts is None
        assert 6 not in reihe.slots                      # erste Zeile der Reihe: kein Anker
        assert reihe.slots[7] == StundenSlot(1.5, 1)
    if fall == "anker_null":
        assert reihe.anker_start_ts == datetime(2026, 5, 14, 16).timestamp()
        assert reihe.slots[4] == StundenSlot(round(530.0 - 506.0, 3), 11)
    if fall == "anker_weit":
        assert reihe.slots[4].n == round((datetime(2026, 5, 15, 3).timestamp()
                                          - datetime(2026, 4, 25, 9).timestamp()) / 3600)
        assert reihe.slots[4].delta == 200.0


# ── P8: kein Anker ⇒ Slot leer, keine Spanne (benannte HA-Abweichung) ────────


def test_p8_kein_anker_slot_leer_ohne_spanne(berlin):
    datum = date(2026, 5, 15)
    zeilen = _stunden(datetime(2026, 5, 15, 9), datetime(2026, 5, 15, 12), 50.0, 2.0)
    sql, _ = _beide(zeilen)
    reihe = sql.get_hourly_slots_for_day([SID], datum)[SID]
    # Zähler(10) ist die erste Zeile überhaupt: HA nähme 0 als Anker und zeigte
    # 50 kWh in dieser Stunde — eedc lässt sie einmal je neuer Reihe aus.
    assert reihe == SensorSlotReihe(
        slots={11: StundenSlot(2.0, 1), 12: StundenSlot(2.0, 1), 13: StundenSlot(2.0, 1)},
        anker_start_ts=None,
    )


# ── P9: DST ───────────────────────────────────────────────────────────────


def test_p9_herbst_doppelslot_n_zwei_und_summe_wie_ha(berlin):
    """Lab-Zeilen 26.10.2025 (sensor.sma_netzbezug): 01:00 CEST 1554 · 02:00 CEST
    1555 · 02:00 CET 1555. Beide 02:00-Zeilen fallen auf Index 3; der Anker über
    den Index ist 01:00 CEST ⇒ Slot 3 = 1 kWh über 2 reale Stunden."""
    datum = date(2025, 10, 26)
    t0 = datetime(2025, 10, 25, 22).timestamp()          # 22:00 CEST Vortag
    # 22:00 CEST · 23:00 · 00:00 · 01:00 CEST · 02:00 CEST · 02:00 CET · 03:00 · …
    werte = [1551, 1552, 1553, 1554, 1555, 1555, 1556] + list(range(1557, 1557 + 19))
    zeilen = [(t0 + i * 3600, float(w)) for i, w in enumerate(werte)]
    # letzte Zeile = 26.10. 22:00 CET
    assert datetime.fromtimestamp(zeilen[-1][0]) == datetime(2025, 10, 26, 22)
    sql, ws = _beide(zeilen)
    reihe = sql.get_hourly_slots_for_day([SID], datum)[SID]
    assert reihe == ws.get_hourly_slots_for_day([SID], datum)[SID]
    assert reihe.slots[3] == StundenSlot(1.0, 2)
    assert round(sum(s.delta for s in reihe.slots.values()), 3) == zeilen[-1][1] - zeilen[0][1]


def test_p9_fruehjahr_leerer_index_ohne_spanne_folgeslot_n_eins(berlin):
    datum = date(2026, 3, 29)
    t0 = datetime(2026, 3, 28, 22).timestamp()           # 22:00 CET Vortag
    zeilen = [(t0 + i * 3600, 100.0 + i) for i in range(24)]   # 23 reale Stunden bis 22:00 CEST
    assert datetime.fromtimestamp(zeilen[-1][0]) == datetime(2026, 3, 29, 22)
    sql, ws = _beide(zeilen)
    reihe = sql.get_hourly_slots_for_day([SID], datum)[SID]
    assert reihe == ws.get_hourly_slots_for_day([SID], datum)[SID]
    assert 3 not in reihe.slots                           # Ortsstunde 02:00 gibt es nicht
    assert reihe.slots[4] == StundenSlot(1.0, 1)          # 3600 s real
    assert all(s.n == 1 for s in reihe.slots.values())
    assert round(sum(s.delta for s in reihe.slots.values()), 3) == zeilen[-1][1] - zeilen[0][1]


# ── R2: 0-Regel je Sensor ──────────────────────────────────────────────────


def test_r2_null_buendel_hat_n_eins(berlin):
    datum = date(2026, 5, 15)
    zeilen = [z for z in _stunden(datetime(2026, 5, 14, 22), datetime(2026, 5, 15, 22), 10.0, 0.0)
              if datetime.fromtimestamp(z[0]).hour not in (2, 3, 4)]
    sql, _ = _beide(zeilen)
    reihe = sql.get_hourly_slots_for_day([SID], datum)[SID]
    assert reihe.slots[6] == StundenSlot(0.0, 1)
