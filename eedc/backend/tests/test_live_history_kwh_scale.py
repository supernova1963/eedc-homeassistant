"""
Akzeptanztest für `_energy_delta`-Einheiten-Skalierung (#232 NongJoWo).

Self-contained Standalone-Script:

    eedc/backend/venv/bin/python eedc/backend/tests/test_live_history_kwh_scale.py

Hintergrund (#232 NongJoWo): Live-Heute zeigte PV/Eigenverbrauch/Hausverbrauch
mit Faktor 1000. Ursache: `_energy_delta_via_statistics` liefert Rohwerte
aus der HA-Statistics-`sum`-Spalte, **in der vom Sensor angegebenen Einheit**.
Bei Wh-Sensoren waren die ausgegebenen Werte 1000× zu groß. `_KWH_SCALE`
wurde im state-history-Fallback angewandt, im Statistics-Pfad jedoch übersehen
— klassischer halber Fix (#200 hatte `_is_energy_sensor` durchgezogen, ohne
auch die Statistics-Skalierung mitzuziehen).

Geprüft:
  1. Wh-Sensor mit Statistics-Pfad: 31442700 - 0 = 31442700 → 31442.7 kWh
  2. kWh-Sensor mit Statistics-Pfad: 31.4 → 31.4 kWh (unverändert)
  3. MWh-Sensor: 0.0314 → 31.4 kWh
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path
from unittest.mock import patch

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.services.live_history_service import _energy_delta  # noqa: E402


def test_wh_sensor_statistics_pfad_durchreicht_kwh():
    """Wh-Sensor im Statistics-Pfad: `get_value_at` skaliert intern bereits
    Wh → kWh (ha_statistics_service.py:736-738), liefert den Wert also
    schon in kWh. `_energy_delta` darf den Wert nicht nochmal skalieren.
    """
    eid = "sensor.pv_gesamt_energy"
    sensor_units = {eid: "Wh"}
    history = {eid: []}  # leer, da Statistics-Pfad genutzt wird

    # Mock simuliert echtes Verhalten: get_value_at hat bereits skaliert,
    # _energy_delta_via_statistics gibt damit einen kWh-Wert zurück.
    with patch(
        "backend.services.live_history_service._energy_delta_via_statistics",
        return_value=31442.7,  # bereits in kWh
    ):
        from datetime import datetime
        result = _energy_delta(
            eid, history, sensor_units,
            start=datetime(2026, 5, 13, 0, 0, 0),
            end=datetime(2026, 5, 13, 12, 11, 40),
        )

    assert result == 31442.7, (
        f"Wh-Sensor: Statistics-Pfad ist schon in kWh, _energy_delta darf "
        f"nicht doppelt skalieren — erwartet 31442.7 kWh, war {result!r}"
    )


def test_kwh_sensor_statistics_pfad_unveraendert():
    """kWh-Sensor: keine Skalierung notwendig (scale = 1.0)."""
    eid = "sensor.pv_kwh"
    sensor_units = {eid: "kWh"}
    history = {eid: []}

    with patch(
        "backend.services.live_history_service._energy_delta_via_statistics",
        return_value=31.4,
    ):
        from datetime import datetime
        result = _energy_delta(
            eid, history, sensor_units,
            start=datetime(2026, 5, 13, 0, 0, 0),
            end=datetime(2026, 5, 13, 12, 0, 0),
        )

    assert result == 31.4, f"kWh-Sensor muss unverändert bleiben, war {result!r}"


def test_mwh_sensor_statistics_pfad_skaliert_auf_kwh():
    """MWh-Sensor im Statistics-Pfad: `get_value_at` skaliert bereits selbst
    mit `_ENERGY_UNIT_TO_KWH` (ha_statistics_service.py:736-738), liefert
    den Wert also schon in kWh zurück. `_energy_delta` darf diesen Pfad
    NICHT nochmal mit `_KWH_SCALE` multiplizieren — sonst Faktor 1000²
    (NongJoWo-Befund #242, Forum 2026-05-16: 8.11 kWh wurden als 8097
    kWh angezeigt).
    """
    eid = "sensor.pv_mwh"
    sensor_units = {eid: "MWh"}
    history = {eid: []}

    # Mock simuliert echtes Verhalten: get_value_at hat bereits skaliert,
    # _energy_delta_via_statistics gibt damit einen kWh-Wert zurück.
    with patch(
        "backend.services.live_history_service._energy_delta_via_statistics",
        return_value=31.4,  # bereits in kWh
    ):
        from datetime import datetime
        result = _energy_delta(
            eid, history, sensor_units,
            start=datetime(2026, 5, 13, 0, 0, 0),
            end=datetime(2026, 5, 13, 12, 0, 0),
        )

    # _energy_delta darf den schon-skalierten Wert nicht nochmal mit 1000
    # multiplizieren.
    assert abs(result - 31.4) < 0.0001, (
        f"MWh-Sensor: Statistics-Pfad ist schon in kWh, _energy_delta darf "
        f"nicht doppelt skalieren — erwartet 31.4 kWh, war {result!r}"
    )


def test_wh_sensor_state_history_fallback_skaliert_weiterhin():
    """Regressionsschutz: state-history-Fallback skalierte schon vor #232
    — der muss weiterhin korrekt skalieren."""
    from datetime import datetime
    eid = "sensor.pv_wh_fallback"
    sensor_units = {eid: "Wh"}
    # State-history mit zwei Punkten (Anfang/Ende), beide in Wh
    history = {eid: [
        (datetime(2026, 5, 13, 0, 0, 0), 0.0),
        (datetime(2026, 5, 13, 12, 0, 0), 31_442_700.0),
    ]}

    # Statistics-Pfad gibt None zurück → Fallback greift
    with patch(
        "backend.services.live_history_service._energy_delta_via_statistics",
        return_value=None,
    ):
        result = _energy_delta(
            eid, history, sensor_units,
            start=datetime(2026, 5, 13, 0, 0, 0),
            end=datetime(2026, 5, 13, 12, 0, 0),
        )

    # 31442700 Wh × 0.001 = 31442.7 kWh (unverändert vs. v3.27.x, kein Regress)
    assert result == 31442.7, (
        f"state-history-Fallback skaliert auch — erwartet 31442.7, "
        f"war {result!r}"
    )


# ── Runner ──────────────────────────────────────────────────────────────────


_TESTS = [
    test_wh_sensor_statistics_pfad_durchreicht_kwh,
    test_kwh_sensor_statistics_pfad_unveraendert,
    test_mwh_sensor_statistics_pfad_skaliert_auf_kwh,
    test_wh_sensor_state_history_fallback_skaliert_weiterhin,
]


def _main() -> int:
    failures = 0
    for fn in _TESTS:
        try:
            fn()
            print(f"OK   {fn.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {fn.__name__}: {e}")
            traceback.print_exc()
        except Exception as e:
            failures += 1
            print(f"ERR  {fn.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
    if failures:
        print(f"\n{failures}/{len(_TESTS)} Tests fehlgeschlagen.")
        return 1
    print(f"\nAlle {len(_TESTS)} Tests grün.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
