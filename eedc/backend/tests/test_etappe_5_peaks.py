"""
Akzeptanztest für Etappe 5 (v3.31.0):
`_get_tagespeaks_aus_ha_lts()` liefert Tages-Peak-Werte für PV, Netzbezug
und Einspeisung aus HA-LTS-Stunden-Min/Max — Caller (aggregator.py) ersetzt
damit die aus 10-Min-Mittelwerten geschätzten Peaks.

Self-contained:

    eedc/backend/venv/bin/python eedc/backend/tests/test_etappe_5_peaks.py

Testet:
  1. Einzelner PV-Sensor: peak_pv = max der Stunden-max über 24 Stunden
  2. Mehrere PV-Sensoren: peak_pv = max über Stunden von Σ max
  3. Dedizierte netzbezug_w / einspeisung_w → max(max) bzw. max(max)
  4. Kombi-Sensor netz_kombi_w: max(max>0) = Bezug, max(|min<0|) = Einspeisung
  5. invert-Flag: min↔max getauscht + negiert vor Peak-Berechnung
  6. HA-LTS leer → alle Peaks None (Caller-Fallback greift)
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.services.energie_profil._helpers import _get_tagespeaks_aus_ha_lts  # noqa: E402


def _mock_db_with_invs(invs: list[tuple[int, str]]):
    """Liefert ein mock-AsyncSession dessen .execute()→ .all() die invs-Liste gibt."""
    db = MagicMock()

    async def _execute(stmt):
        result = MagicMock()
        result.all = MagicMock(return_value=invs)
        return result

    db.execute = _execute
    return db


def _anlage(sensor_mapping: dict):
    return SimpleNamespace(id=1, sensor_mapping=sensor_mapping)


def _mock_stats_svc(minmax_per_sensor: dict[str, dict[int, dict[str, float]]]):
    """Wickelt minmax als das LTS-Result-Format
    `{eid: {datum_iso: {hour: {min,max}}}}`."""
    svc = MagicMock()
    svc.is_available = True
    datum_iso = "2026-05-15"

    def _read(sensor_ids, von, _bis):
        return {
            eid: {datum_iso: minmax_per_sensor[eid]}
            for eid in sensor_ids if eid in minmax_per_sensor
        }

    svc.get_hourly_minmax_sensor_data.side_effect = _read
    return svc


async def test_einzelner_pv_sensor():
    """peak_pv = max der Stunden-max über 24 Stunden."""
    sensor_mapping = {
        "basis": {"live": {"pv_gesamt_w": "sensor.pv"}},
    }
    anlage = _anlage(sensor_mapping)
    db = _mock_db_with_invs([])

    minmax = {
        "sensor.pv": {
            10: {"min": 0.5, "max": 3.0},
            12: {"min": 1.0, "max": 8.5},
            14: {"min": 0.0, "max": 6.0},
        }
    }
    with patch("backend.core.config.HA_INTEGRATION_AVAILABLE", True), \
         patch("backend.services.ha_statistics_service.get_ha_statistics_service",
               return_value=_mock_stats_svc(minmax)):
        peaks = await _get_tagespeaks_aus_ha_lts(anlage, date(2026, 5, 15), db)

    assert peaks.pv == 8.5, f"peak_pv: {peaks.pv}"
    assert peaks.netzbezug is None
    assert peaks.einspeisung is None


async def test_mehrere_pv_sensoren_sigma_max():
    """Bei zwei PV-Sensoren: peak_pv = max über Stunden von Σ max."""
    sensor_mapping = {
        "basis": {"live": {}},
        "investitionen": {
            "3": {"live": {"leistung_w": "sensor.pv_modul1"}},
            "4": {"live": {"leistung_w": "sensor.pv_modul2"}},
        },
    }
    anlage = _anlage(sensor_mapping)
    db = _mock_db_with_invs([(3, "pv-module"), (4, "pv-module")])

    minmax = {
        "sensor.pv_modul1": {12: {"min": 0.0, "max": 5.0}, 13: {"min": 0.0, "max": 4.0}},
        "sensor.pv_modul2": {12: {"min": 0.0, "max": 3.0}, 13: {"min": 0.0, "max": 4.5}},
    }
    # Σ um 12: 5.0+3.0 = 8.0  / Σ um 13: 4.0+4.5 = 8.5 → peak 8.5
    with patch("backend.core.config.HA_INTEGRATION_AVAILABLE", True), \
         patch("backend.services.ha_statistics_service.get_ha_statistics_service",
               return_value=_mock_stats_svc(minmax)):
        peaks = await _get_tagespeaks_aus_ha_lts(anlage, date(2026, 5, 15), db)

    assert peaks.pv == 8.5, f"peak_pv: {peaks.pv}"


async def test_dedizierte_netzbezug_einspeisung():
    """Getrennte Sensoren → max(max) je Sensor."""
    sensor_mapping = {
        "basis": {"live": {
            "netzbezug_w": "sensor.bezug",
            "einspeisung_w": "sensor.einsp",
        }},
    }
    anlage = _anlage(sensor_mapping)
    db = _mock_db_with_invs([])

    minmax = {
        "sensor.bezug": {19: {"min": 0.0, "max": 4.5}, 20: {"min": 0.0, "max": 6.2}},
        "sensor.einsp": {12: {"min": 0.0, "max": 7.1}},
    }
    with patch("backend.core.config.HA_INTEGRATION_AVAILABLE", True), \
         patch("backend.services.ha_statistics_service.get_ha_statistics_service",
               return_value=_mock_stats_svc(minmax)):
        peaks = await _get_tagespeaks_aus_ha_lts(anlage, date(2026, 5, 15), db)

    assert peaks.netzbezug == 6.2
    assert peaks.einspeisung == 7.1


async def test_kombi_sensor_bezug_und_einspeisung():
    """Kombi-Sensor: positives max = Bezug, |negatives min| = Einspeisung."""
    sensor_mapping = {
        "basis": {"live": {"netz_kombi_w": "sensor.netz"}},
    }
    anlage = _anlage(sensor_mapping)
    db = _mock_db_with_invs([])

    minmax = {
        "sensor.netz": {
            12: {"min": -6.0, "max": 0.2},   # einspeisend
            19: {"min": 0.0, "max": 4.5},    # Bezug
        }
    }
    with patch("backend.core.config.HA_INTEGRATION_AVAILABLE", True), \
         patch("backend.services.ha_statistics_service.get_ha_statistics_service",
               return_value=_mock_stats_svc(minmax)):
        peaks = await _get_tagespeaks_aus_ha_lts(anlage, date(2026, 5, 15), db)

    assert peaks.netzbezug == 4.5
    assert peaks.einspeisung == 6.0


async def test_invert_flag_wird_angewendet():
    """live_invert: min↔max getauscht + negiert vor Peak-Berechnung.
    Eine Einspeisung-Anlage liefert positive Werte als Einspeisung, beim
    Invert wird sie zu negativen Werten → Einspeisung über |min|."""
    sensor_mapping = {
        "basis": {
            "live": {"einspeisung_w": "sensor.einsp"},
            "live_invert": {"einspeisung_w": True},
        },
    }
    anlage = _anlage(sensor_mapping)
    db = _mock_db_with_invs([])

    # Rohwerte: max=7.0 (positiver Peak). Nach Invert: min=-7.0, max=0.
    # best_max_positiv liefert dann None → einspeisung kommt nicht durch.
    # Korrektur: einspeisung_w als dedizierter Sensor läuft über best_max_positiv,
    # nicht über best_betrag_negativ. Mit Invert wäre das wirkungslos für diesen
    # Pfad. Wir testen invert in einem Investitions-Setting (leistung_w eines
    # Speichers mit Invert):
    sensor_mapping2 = {
        "basis": {"live": {"netz_kombi_w": "sensor.netz"}},
    }
    # Roh: min=0, max=6 (positiv = Einspeisung in Konvention dieser Anlage).
    # Mit invert wäre min=-6, max=0 → Einspeisung via best_betrag_negativ.
    sensor_mapping2["basis"]["live_invert"] = {"netz_kombi_w": True}
    anlage = _anlage(sensor_mapping2)

    minmax = {
        "sensor.netz": {12: {"min": 0.0, "max": 6.0}},
    }
    with patch("backend.core.config.HA_INTEGRATION_AVAILABLE", True), \
         patch("backend.services.ha_statistics_service.get_ha_statistics_service",
               return_value=_mock_stats_svc(minmax)):
        peaks = await _get_tagespeaks_aus_ha_lts(anlage, date(2026, 5, 15), db)

    # Nach Invert: min=-6, max=0 → Einspeisung 6, Bezug None
    assert peaks.einspeisung == 6.0, f"einspeisung: {peaks.einspeisung}"
    assert peaks.netzbezug is None, f"netzbezug: {peaks.netzbezug}"


async def test_ha_lts_leer_alle_peaks_none():
    """Kein Service / kein Sensor → alle Peaks None."""
    sensor_mapping = {
        "basis": {"live": {"pv_gesamt_w": "sensor.pv"}},
    }
    anlage = _anlage(sensor_mapping)
    db = _mock_db_with_invs([])

    svc = MagicMock()
    svc.is_available = True
    svc.get_hourly_minmax_sensor_data.return_value = {}  # leer

    with patch("backend.services.ha_statistics_service.get_ha_statistics_service",
               return_value=svc):
        peaks = await _get_tagespeaks_aus_ha_lts(anlage, date(2026, 5, 15), db)

    assert peaks.pv is None
    assert peaks.netzbezug is None
    assert peaks.einspeisung is None


_TESTS = [
    test_einzelner_pv_sensor,
    test_mehrere_pv_sensoren_sigma_max,
    test_dedizierte_netzbezug_einspeisung,
    test_kombi_sensor_bezug_und_einspeisung,
    test_invert_flag_wird_angewendet,
    test_ha_lts_leer_alle_peaks_none,
]


def _run_all() -> int:
    failures = 0
    for test in _TESTS:
        try:
            asyncio.run(test())
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
