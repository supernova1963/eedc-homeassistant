"""
Slot-Konventions-Symmetrie über alle PV-Prognosequellen (Issue #144, #297).

Hintergrund (#297): Im Stunden-Vergleich wurde vermutet, OpenMeteo läge eine
Stunde „zu spät" und müsse +1 geshiftet werden. Das Audit 2026-06-04 (Live-API-
Messung + v3.20.0-Changelog + HA-Repro) zeigte das Gegenteil: OpenMeteos
preceding-hour-Mittel IST bereits Backward (Wert@h = [h-1, h)). Solcast und IST
sind ebenfalls Backward. Ein +1-Shift hätte den Versatz erst erzeugt.

Dieser Test nagelt die Symmetrie fest: für ein und dasselbe physische Intervall
``[05:00, 06:00)`` müssen OpenMeteo, Solcast und IST in **denselben Slot 6**
einsortieren. Wer eine Quelle verschiebt (z.B. OpenMeteo „fixt"), bricht ihn.

Plus die Tagessummen-Invariante: das Slot-Schema darf nur die Zuordnung ändern,
nie die Tagessumme.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from backend.core.berechnungen.slot_konvention import (
    backward_slot_aus_period_end,
    backward_slot_aus_period_start,
    lts_boundary_index,
    openmeteo_preceding_hour_slot,
)
from backend.services.snapshot.boundary_range import BoundaryRange
from backend.services.solar_forecast_service import _build_prognose

TAG = "2026-06-04"
# Das physische Test-Intervall: [05:00, 06:00) → Backward-Slot 6.
INTERVALL_ENDE_STUNDE = 6


# ─── Helper-Einheiten ──────────────────────────────────────────────────────


def test_openmeteo_ist_identitaet_kein_shift():
    """OpenMeteo preceding-hour: Wert@h = [h-1,h) = Slot h. KEIN Shift (#297)."""
    for h in range(24):
        assert openmeteo_preceding_hour_slot(h) == h


def test_solcast_period_start_rundet_auf_stunden_ende():
    d = date(2026, 6, 4)
    # Bucket [05:00, 05:30) und [05:30, 06:00) gehören beide zu Slot 6.
    assert backward_slot_aus_period_start(datetime(2026, 6, 4, 5, 0)) == (d, 6)
    assert backward_slot_aus_period_start(datetime(2026, 6, 4, 5, 30)) == (d, 6)


def test_solcast_period_end_rundet_auf_stunden_ende():
    d = date(2026, 6, 4)
    # period_end exakt auf voller Stunde markiert das Ende dieses Slots.
    assert backward_slot_aus_period_end(datetime(2026, 6, 4, 6, 0)) == (d, 6)
    # period_end auf :30 rundet auf die nächste volle Stunde auf.
    assert backward_slot_aus_period_end(datetime(2026, 6, 4, 5, 30)) == (d, 6)


def test_tagesuebergang_wandert_in_folgetag_slot_0():
    """Das letzte Intervall des Tages [23:00, 00:00) ist Slot 0 des Folgetags."""
    folgetag = date(2026, 6, 5)
    assert backward_slot_aus_period_start(datetime(2026, 6, 4, 23, 0)) == (folgetag, 0)
    assert backward_slot_aus_period_end(datetime(2026, 6, 5, 0, 0)) == (folgetag, 0)


# ─── IST-Seite (boundary_range) ────────────────────────────────────────────


def test_ist_boundary_range_slot_6_ist_intervall_05_06():
    """IST-Slot 6 (Snapshot-Pfad) = snap[6] − snap[5] = Energie [05:00, 06:00)."""
    rng = BoundaryRange.for_hourly_slots(date(2026, 6, 4))
    slot6 = next(p for p in rng.slot_pairs if p[0] == 6)
    slot_idx, prev_off, curr_off = slot6
    assert (prev_off, curr_off) == (5, 6)  # [05:00, 06:00)


def test_ist_lts_pfad_intervall_05_06_landet_in_slot_6():
    """IST-LTS-Pfad: [05:00, 06:00) = Zähler(6) − Zähler(5) → Backward-Slot 6.

    Regression für den Forward-Bug (Rainer/Gernot 2026-06-04): die HA-LTS-Row
    `start_ts=05:00` trägt Zähler@06:00 → Boundary-Index 6; Row `start_ts=04:00`
    trägt Zähler@05:00 → Index 5. Slot 6 = boundary[6] − boundary[5] = [05,06).
    Früher landete dieselbe Energie in Slot 5 (Forward) → IST 1 h zu früh.
    """
    d = date(2026, 6, 4)
    assert lts_boundary_index(datetime(2026, 6, 4, 5, 0), d) == 6
    assert lts_boundary_index(datetime(2026, 6, 4, 4, 0), d) == 5
    # Tagesübergang: Row 22:00 Vortag trägt Zähler@23:00 Vortag → Index -1
    # (für Slot 0 = [23:00 Vortag, 00:00 heute)); Row 23:00 Vortag → Index 0.
    assert lts_boundary_index(datetime(2026, 6, 3, 22, 0), d) == -1
    assert lts_boundary_index(datetime(2026, 6, 3, 23, 0), d) == 0
    assert lts_boundary_index(datetime(2026, 6, 4, 22, 0), d) == 23


# ─── Symmetrie: dasselbe Intervall → derselbe Slot über alle Quellen ───────


def _build_openmeteo_slot_fuer_intervall_05_06() -> list[float]:
    """Füttert _build_prognose mit GTI nur in [05:00, 06:00) und gibt stunden_kw."""
    times = [f"{TAG}T{h:02d}:00" for h in range(24)]
    gti = [0.0] * 24
    # preceding-hour: der Wert am Index 6 repräsentiert [05:00, 06:00).
    gti[6] = 500.0
    data = {
        "hourly": {
            "time": times,
            "global_tilted_irradiance": gti,
            "shortwave_radiation": [0.0] * 24,
            "temperature_2m": [15.0] * 24,
            "snowfall": [0.0] * 24,
            "cloud_cover": [0] * 24,
        },
        "daily": {
            "time": [TAG],
            "temperature_2m_max": [20.0],
            "temperature_2m_min": [10.0],
            "sunshine_duration": [3600.0],
            "precipitation_sum": [0.0],
            "snowfall_sum": [0.0],
            "weather_code": [0],
            "shortwave_radiation_sum": [1.0],
        },
    }
    resp = _build_prognose(
        data, kwp=10.0, neigung=35, ausrichtung=0, days=1,
        system_losses=0.14, longitude=8.0,
    )
    assert resp is not None and resp.tageswerte
    return resp.tageswerte[0].stunden_kw


def test_symmetrie_alle_quellen_intervall_05_06_in_slot_6():
    """OpenMeteo, Solcast und IST ordnen [05:00, 06:00) demselben Slot 6 zu."""
    # OpenMeteo (echter Service-Pfad): Ertrag muss in Slot 6 liegen, sonst nirgends.
    stunden_kw = _build_openmeteo_slot_fuer_intervall_05_06()
    assert stunden_kw[6] > 0, "OpenMeteo: [05,06)-Energie nicht in Slot 6"
    assert all(v == 0 for i, v in enumerate(stunden_kw) if i != 6), \
        "OpenMeteo: Energie in falschem Slot (möglicher +1-Shift, #297)"

    # Solcast (period_start des HA-Sensors / period_end der API): Slot 6.
    _, sc_start_slot = backward_slot_aus_period_start(datetime(2026, 6, 4, 5, 0))
    _, sc_end_slot = backward_slot_aus_period_end(datetime(2026, 6, 4, 6, 0))

    # IST Snapshot-Diff: Slot 6 deckt [05:00, 06:00) ab.
    rng = BoundaryRange.for_hourly_slots(date(2026, 6, 4))
    ist_slot = next(p[0] for p in rng.slot_pairs if (p[1], p[2]) == (5, 6))

    # IST HA-LTS: [05:00, 06:00) = Zähler(6) − Zähler(5) → Slot 6.
    # (Row start_ts=05:00 → Boundary-Index 6; früher Forward → Slot 5.)
    ist_lts_slot = lts_boundary_index(datetime(2026, 6, 4, 5, 0), date(2026, 6, 4))

    assert sc_start_slot == sc_end_slot == ist_slot == ist_lts_slot == 6, \
        "Quellen-Asymmetrie: [05,06) landet nicht überall in Slot 6"


# ─── Tagessummen-Invariante ────────────────────────────────────────────────


def test_openmeteo_tagessumme_invariant_unter_slot_zuordnung():
    """Σ stunden_kw == pv_ertrag_kwh — die Slot-Zuordnung verschiebt nur, summiert nie."""
    times = [f"{TAG}T{h:02d}:00" for h in range(24)]
    # Realistisches Tagprofil 06:00–19:00 (preceding-hour-Indizes).
    gti = [0.0] * 24
    for h, val in zip(range(6, 20), [50, 150, 300, 450, 600, 700, 750, 760, 720, 600, 430, 260, 120, 30]):
        gti[h] = float(val)
    data = {
        "hourly": {
            "time": times,
            "global_tilted_irradiance": gti,
            "shortwave_radiation": [0.0] * 24,
            "temperature_2m": [18.0] * 24,
            "snowfall": [0.0] * 24,
            "cloud_cover": [10] * 24,
        },
        "daily": {
            "time": [TAG],
            "temperature_2m_max": [24.0],
            "temperature_2m_min": [12.0],
            "sunshine_duration": [36000.0],
            "precipitation_sum": [0.0],
            "snowfall_sum": [0.0],
            "weather_code": [1],
            "shortwave_radiation_sum": [6.0],
        },
    }
    resp = _build_prognose(
        data, kwp=10.0, neigung=35, ausrichtung=0, days=1,
        system_losses=0.14, longitude=8.0,
    )
    tag = resp.tageswerte[0]
    assert abs(sum(tag.stunden_kw) - tag.pv_ertrag_kwh) < 0.05
