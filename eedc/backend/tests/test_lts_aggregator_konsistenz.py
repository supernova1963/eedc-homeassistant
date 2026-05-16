"""
Konsistenz-Tests für Etappe 4 (v3.31.0): die LTS-Aggregator-Funktionen
müssen so liefern, dass Σ Hourly == Daily für jede Komponente.

Damit ist beweisbar, dass Rainers ~10 % Drift (72,1 / 67 / 64,49 kWh am
15.05.2026) im HA-LTS-Pfad nicht mehr entstehen kann — beide Sichten
lesen aus derselben Quelle, Σ Hourly = Daily ist Konstruktion, kein
Glück.

Self-contained:

    eedc/backend/venv/bin/python eedc/backend/tests/test_lts_aggregator_konsistenz.py

Testet:
  1. Σ Hourly pv == Σ Daily pv_*-Keys (über alle PV-Investitionen)
  2. Σ Hourly einspeisung == Daily einspeisung
  3. Σ Hourly netzbezug == Daily netzbezug
  4. Speicher: Netto-Vorzeichen-Konsistenz (Hourly netto / Daily netto)
  5. WP, Wallbox: Σ Hourly == Σ Daily-Keys
  6. Sonstige Investitions-Typ-Keys mit korrekter Präfix-Konvention
  7. Fehlendes HA-LTS → leeres Result
  8. Anlage ohne PV-Investition → keine pv_*-Keys
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from types import SimpleNamespace  # noqa: E402

from backend.services.snapshot.lts_aggregator import (  # noqa: E402
    get_hourly_kwh_by_category_lts,
    get_komponenten_tageskwh_lts,
)


@asynccontextmanager
async def _session_ctx():
    """Dummy-Context — die LTS-Aggregator-Funktionen nutzen db nur weil die
    Snapshot-Variante das tut (Output-Vertrag-Symmetrie); LTS-Pfad liest
    direkt aus HA-Statistics."""
    yield None  # type: ignore[misc]


def _make_anlage_dict(sensor_mapping: dict):
    """Plain duck-typed Anlage — vermeidet SQLAlchemy-Instance-State-Setup."""
    return SimpleNamespace(
        id=1,
        anlagenname="Test",
        leistung_kwp=10.0,
        sensor_mapping=sensor_mapping,
    )


def _make_inv(inv_id: int, typ: str, parameter: dict | None = None):
    return SimpleNamespace(
        id=inv_id,
        anlage_id=1,
        typ=typ,
        parameter=parameter or {},
    )


def _build_mock_ha_svc(deltas_per_sensor: dict[str, dict[int, float]]) -> MagicMock:
    """Mock-HAStatisticsService: liefert vorab definierte Stunden-Deltas."""
    svc = MagicMock()
    svc.is_available = True

    def _get_deltas(sensor_ids, _datum):
        return {
            eid: deltas_per_sensor[eid]
            for eid in sensor_ids
            if eid in deltas_per_sensor
        }

    svc.get_hourly_kwh_deltas_for_day.side_effect = _get_deltas
    return svc


async def test_sigma_hourly_pv_gleich_sigma_daily_pv_keys():
    """Σ über alle Stunden für 'pv' (Hourly-Kategorie) muss exakt die Σ
    aller pv_*-Keys aus komponenten_kwh (Daily) entsprechen."""
    sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einsp"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.bezug"},
        },
        "investitionen": {
            "3": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv_modul1"}}},
            "4": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv_modul2"}}},
        },
    }
    invs = {"3": _make_inv(3, "pv-module"), "4": _make_inv(4, "pv-module")}
    anlage = _make_anlage_dict(sensor_mapping)

    # 24 Stunden mit verschiedenen Werten (typisches Tagesprofil)
    profile_pv1 = {h: max(0.0, 5.0 - abs(h - 12) * 0.5) for h in range(24)}  # ~28 kWh
    profile_pv2 = {h: max(0.0, 3.0 - abs(h - 12) * 0.3) for h in range(24)}  # ~17 kWh
    profile_einsp = {h: max(0.0, 2.0 - abs(h - 12) * 0.2) for h in range(24)}
    profile_bezug = {h: 0.5 for h in range(24)}  # konstant

    deltas = {
        "sensor.pv_modul1": profile_pv1,
        "sensor.pv_modul2": profile_pv2,
        "sensor.einsp": profile_einsp,
        "sensor.bezug": profile_bezug,
    }
    mock_svc = _build_mock_ha_svc(deltas)

    with patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=mock_svc):
        async with _session_ctx() as db:
            hourly = await get_hourly_kwh_by_category_lts(db, anlage, invs, date(2026, 5, 15))
            daily = await get_komponenten_tageskwh_lts(anlage, invs, date(2026, 5, 15))

    # Σ Hourly pv (kategorisiert, mit Cap)
    # Achtung: Cap greift bei pv > 10 kWp × 1.5 = 15 kWh pro Stunde — bei unserem
    # Profil max ~8 kWh/h, also unter Cap. Σ = ~45 kWh
    sigma_hourly_pv = sum(
        (h.get("pv") or 0.0) for h in hourly.values()
    )
    # Σ Daily pv_*-Keys
    sigma_daily_pv = sum(v for k, v in daily.items() if k.startswith("pv_"))

    assert abs(sigma_hourly_pv - sigma_daily_pv) < 0.01, (
        f"DRIFT: Hourly Σ pv = {sigma_hourly_pv:.3f}, Daily Σ pv_* = {sigma_daily_pv:.3f}"
    )


async def test_sigma_hourly_einspeisung_netzbezug():
    """Basis-Zähler: Σ Hourly == Daily."""
    sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einsp"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.bezug"},
        },
        "investitionen": {},
    }
    invs: dict = {}
    anlage = _make_anlage_dict(sensor_mapping)

    deltas = {
        "sensor.einsp": {h: 1.5 for h in range(24)},  # 36 kWh
        "sensor.bezug": {h: 0.4 for h in range(24)},  # 9.6 kWh
    }
    mock_svc = _build_mock_ha_svc(deltas)

    with patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=mock_svc):
        async with _session_ctx() as db:
            hourly = await get_hourly_kwh_by_category_lts(db, anlage, invs, date(2026, 5, 15))
            daily = await get_komponenten_tageskwh_lts(anlage, invs, date(2026, 5, 15))

    sigma_hourly_einsp = sum((h.get("einspeisung") or 0.0) for h in hourly.values())
    sigma_hourly_bezug = sum((h.get("netzbezug") or 0.0) for h in hourly.values())

    assert abs(sigma_hourly_einsp - daily["einspeisung"]) < 0.01, (
        f"einspeisung Hourly Σ={sigma_hourly_einsp:.3f} vs Daily={daily['einspeisung']:.3f}"
    )
    assert abs(sigma_hourly_bezug - daily["netzbezug"]) < 0.01, (
        f"netzbezug Hourly Σ={sigma_hourly_bezug:.3f} vs Daily={daily['netzbezug']:.3f}"
    )


async def test_speicher_vorzeichen_konsistent():
    """Speicher: Hourly batterie_netto = ladung − entladung (netto).
    Daily batterie_<id> = ebenfalls netto, dieselbe Vorzeichen-Logik."""
    sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einsp"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.bezug"},
        },
        "investitionen": {
            "5": {"felder": {
                "ladung_kwh":   {"strategie": "sensor", "sensor_id": "sensor.batt_lade"},
                "entladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.batt_entlade"},
            }},
        },
    }
    invs = {"5": _make_inv(5, "speicher")}
    anlage = _make_anlage_dict(sensor_mapping)

    # Batterie: 4 Stunden 2 kWh laden (8 kWh), 6 Stunden 1.5 kWh entladen (9 kWh)
    # Netto = -1 kWh
    ladung = {h: (2.0 if h in (10, 11, 12, 13) else 0.0) for h in range(24)}
    entladung = {h: (1.5 if h in (18, 19, 20, 21, 22, 23) else 0.0) for h in range(24)}
    deltas = {
        "sensor.einsp": {h: 0.0 for h in range(24)},
        "sensor.bezug": {h: 0.0 for h in range(24)},
        "sensor.batt_lade": ladung,
        "sensor.batt_entlade": entladung,
    }
    mock_svc = _build_mock_ha_svc(deltas)

    with patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=mock_svc):
        async with _session_ctx() as db:
            hourly = await get_hourly_kwh_by_category_lts(db, anlage, invs, date(2026, 5, 15))
            daily = await get_komponenten_tageskwh_lts(anlage, invs, date(2026, 5, 15))

    sigma_hourly_netto = sum((h.get("batterie_netto") or 0.0) for h in hourly.values())
    daily_netto = daily["batterie_5"]

    assert abs(sigma_hourly_netto - daily_netto) < 0.01, (
        f"Batterie Netto: Hourly Σ={sigma_hourly_netto:.3f} vs Daily={daily_netto:.3f}"
    )
    assert abs(daily_netto - (-1.0)) < 0.01, (
        f"Erwartet Netto -1.0 (8 lade − 9 entlade), bekommen {daily_netto}"
    )


async def test_wp_wallbox_sigma_konsistent():
    """WP + Wallbox: Hourly per Kategorie, Daily per Investitions-Key."""
    sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einsp"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.bezug"},
        },
        "investitionen": {
            "7": {"felder": {"stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": "sensor.wp"}}},
            "9": {"felder": {"ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.wb"}}},
        },
    }
    invs = {
        "7": _make_inv(7, "waermepumpe"),
        "9": _make_inv(9, "wallbox"),
    }
    anlage = _make_anlage_dict(sensor_mapping)

    deltas = {
        "sensor.einsp": {h: 0.0 for h in range(24)},
        "sensor.bezug": {h: 0.0 for h in range(24)},
        "sensor.wp":    {h: 0.4 for h in range(24)},  # 9.6 kWh
        "sensor.wb":    {h: (3.0 if 18 <= h <= 21 else 0.0) for h in range(24)},  # 12 kWh
    }
    mock_svc = _build_mock_ha_svc(deltas)

    with patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=mock_svc):
        async with _session_ctx() as db:
            hourly = await get_hourly_kwh_by_category_lts(db, anlage, invs, date(2026, 5, 15))
            daily = await get_komponenten_tageskwh_lts(anlage, invs, date(2026, 5, 15))

    sigma_hourly_wp = sum((h.get("wp") or 0.0) for h in hourly.values())
    sigma_hourly_wb = sum((h.get("wallbox") or 0.0) for h in hourly.values())

    assert abs(sigma_hourly_wp - daily["waermepumpe_7"]) < 0.01
    assert abs(sigma_hourly_wb - daily["wallbox_9"]) < 0.01


async def test_balkonkraftwerk_und_sonstiges_keys():
    """Investitions-Typ-Keys: bkw_<id>, sonstige_<id>."""
    sensor_mapping = {
        "basis": {},
        "investitionen": {
            "11": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.bkw"}}},
            "13": {"felder": {"verbrauch_kwh": {"strategie": "sensor", "sensor_id": "sensor.pool"}}},
        },
    }
    invs = {
        "11": _make_inv(11, "balkonkraftwerk"),
        "13": _make_inv(13, "sonstiges", parameter={"kategorie": "verbraucher"}),
    }
    anlage = _make_anlage_dict(sensor_mapping)

    deltas = {
        "sensor.bkw":  {h: 0.3 for h in range(24)},   # 7.2 kWh
        "sensor.pool": {h: 0.1 for h in range(24)},   # 2.4 kWh
    }
    mock_svc = _build_mock_ha_svc(deltas)

    with patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=mock_svc):
        async with _session_ctx() as db:
            daily = await get_komponenten_tageskwh_lts(anlage, invs, date(2026, 5, 15))

    assert "bkw_11" in daily, f"bkw_11-Key fehlt: {list(daily.keys())}"
    assert abs(daily["bkw_11"] - 7.2) < 0.01
    assert "sonstige_13" in daily
    # sonstiges-Verbraucher hat Vorzeichen -1 → -2.4
    assert abs(daily["sonstige_13"] - (-2.4)) < 0.01


async def test_kein_ha_lts_liefert_leer():
    """HA-LTS nicht verfügbar → beide Funktionen geben {} zurück."""
    sensor_mapping = {
        "basis": {"einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einsp"}},
        "investitionen": {},
    }
    invs: dict = {}
    anlage = _make_anlage_dict(sensor_mapping)

    mock_svc = MagicMock()
    mock_svc.is_available = False

    with patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=mock_svc):
        async with _session_ctx() as db:
            hourly = await get_hourly_kwh_by_category_lts(db, anlage, invs, date(2026, 5, 15))
            daily = await get_komponenten_tageskwh_lts(anlage, invs, date(2026, 5, 15))

    assert hourly == {}
    assert daily == {}


async def test_anlage_ohne_pv_keine_pv_keys():
    """Sensor-Mapping ohne PV → keine pv_*-Keys im Daily-Result."""
    sensor_mapping = {
        "basis": {
            "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einsp"},
            "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.bezug"},
        },
        "investitionen": {
            "7": {"felder": {"stromverbrauch_kwh": {"strategie": "sensor", "sensor_id": "sensor.wp"}}},
        },
    }
    invs = {"7": _make_inv(7, "waermepumpe")}
    anlage = _make_anlage_dict(sensor_mapping)

    deltas = {
        "sensor.einsp": {h: 0.0 for h in range(24)},
        "sensor.bezug": {h: 0.5 for h in range(24)},
        "sensor.wp":    {h: 0.3 for h in range(24)},
    }
    mock_svc = _build_mock_ha_svc(deltas)

    with patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=mock_svc):
        async with _session_ctx() as db:
            daily = await get_komponenten_tageskwh_lts(anlage, invs, date(2026, 5, 15))

    pv_keys = [k for k in daily if k.startswith("pv_")]
    bkw_keys = [k for k in daily if k.startswith("bkw_")]
    assert not pv_keys, f"Keine pv_*-Keys erwartet, gefunden: {pv_keys}"
    assert not bkw_keys


_TESTS = [
    test_sigma_hourly_pv_gleich_sigma_daily_pv_keys,
    test_sigma_hourly_einspeisung_netzbezug,
    test_speicher_vorzeichen_konsistent,
    test_wp_wallbox_sigma_konsistent,
    test_balkonkraftwerk_und_sonstiges_keys,
    test_kein_ha_lts_liefert_leer,
    test_anlage_ohne_pv_keine_pv_keys,
]


async def _run_all() -> int:
    failures = 0
    for test in _TESTS:
        try:
            await test()
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
    failures = asyncio.run(_run_all())
    if failures:
        print(f"\n{failures} von {len(_TESTS)} Tests fehlgeschlagen.")
        sys.exit(1)
    print(f"\nAlle {len(_TESTS)} Tests grün.")
