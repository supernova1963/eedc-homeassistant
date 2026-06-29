"""
Akzeptanztest v3.45.9:
`DatenChecker._check_batterie_vorzeichen_historie()` erkennt Alt-Tage mit
vertauschtem Batterie-Vorzeichen per Daten-Signal — gespeichertes Tages-Netto
(summe_batterie_netto_kwh aus TagesZusammenfassung.komponenten_kwh) gegen einen
frischen HA-LTS-Read mit aktueller Konvention (ENTLADUNG positiv). Bietet
Bereichs- (reaggregate_range) + Einzeltag-Knöpfe (reaggregate_day).

Self-contained:

    eedc/backend/venv/bin/python eedc/backend/tests/test_batterie_vorzeichen_historie_check.py

Testet:
  1. Entgegengesetzte Vorzeichen → Summen-Eintrag (reaggregate_range) + Einzeltag-Einträge
  2. Gleiche Richtung trotz Magnitude-Drift → kein Konflikt (nur OK; isoliert Achse-2)
  3. Kein nennenswertes Batterie-Netto → Kategorie unsichtbar (leer)
  4. Standalone (kein HA-LTS) → leer
  5. Span > 31 Tage → Bereichs-Knopf auf jüngstes 31-Tage-Fenster begrenzt + Rest-Hinweis
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.services.daten_checker import DatenChecker, CheckKategorie  # noqa: E402

_KAT = CheckKategorie.BATTERIE_VORZEICHEN_HISTORIE.value


def _make_tz(datum: date, batterie_netto: float):
    """TagesZusammenfassung-duck mit gespeichertem Batterie-Netto."""
    return SimpleNamespace(
        id=1, anlage_id=1, datum=datum,
        komponenten_kwh={"batterie_5": batterie_netto, "netzbezug": 2.0},
    )


def _make_anlage():
    return SimpleNamespace(id=1, sensor_mapping={
        "investitionen": {"5": {"felder": {
            "ladung_kwh": {"strategie": "sensor", "sensor_id": "sensor.bat_l"},
        }}},
    })


def _make_inv(inv_id=5, typ="speicher"):
    return SimpleNamespace(id=inv_id, anlage_id=1, typ=typ, parameter={})


def _build_checker(tz_list, invs_list, ha_tageskwh_func, ha_available=True):
    db = MagicMock()
    call_count = {"n": 0}

    async def _execute(stmt):
        result = MagicMock()
        call_count["n"] += 1
        scalars = MagicMock()
        # 1. execute: TagesZusammenfassung — 2.: Investition
        scalars.all = MagicMock(
            return_value=tz_list if call_count["n"] == 1 else invs_list
        )
        result.scalars = MagicMock(return_value=scalars)
        return result

    db.execute = _execute
    checker = DatenChecker(db)

    ha_svc = MagicMock()
    ha_svc.is_available = ha_available

    async def _ha_lts(anlage, invs, datum):
        return ha_tageskwh_func(datum)

    patches = [
        patch("backend.services.ha_statistics_service.get_ha_statistics_service",
              return_value=ha_svc),
        patch("backend.services.snapshot.lts_aggregator.get_komponenten_tageskwh_lts",
              side_effect=_ha_lts),
    ]
    return checker, patches


async def _run_check(tz_list, invs_list, ha_func, ha_available=True):
    checker, patches = _build_checker(tz_list, invs_list, ha_func, ha_available)
    for p in patches:
        p.start()
    try:
        return await checker._check_batterie_vorzeichen_historie(_make_anlage())
    finally:
        for p in patches:
            p.stop()


async def test_vorzeichen_konflikt_erkannt():
    """Gespeichert −4 (alt), frisch +4 (kanonisch) → Konflikt."""
    test_datum = date.today() - timedelta(days=1)
    tz_list = [_make_tz(test_datum, -4.0)]   # alte Richtung gespeichert
    ha_func = lambda d: {"batterie_5": 4.0}  # frisch, ENTLADUNG positiv
    result = await _run_check(tz_list, [_make_inv()], ha_func)

    range_eintraege = [r for r in result if r.action_kind == "reaggregate_range"]
    assert len(range_eintraege) == 1, f"Erwartet 1 Bereichs-Eintrag, bekommen {result}"
    re_ = range_eintraege[0]
    assert re_.schwere == "warning"
    assert re_.action_params == {
        "anlage_id": 1, "von": test_datum.isoformat(), "bis": test_datum.isoformat(),
    }, f"params: {re_.action_params}"
    assert re_.action_label == "Zeitraum neu aggregieren"

    day_eintraege = [r for r in result if r.action_kind == "reaggregate_day"]
    assert len(day_eintraege) == 1, f"Erwartet 1 Einzeltag-Eintrag, bekommen {len(day_eintraege)}"
    assert day_eintraege[0].action_params == {
        "anlage_id": 1, "datum": test_datum.isoformat(),
    }


async def test_gleiche_richtung_magnitude_drift_kein_konflikt():
    """Stored +3, frisch +8 (gleiche Richtung, große Magnitude-Drift) →
    KEIN Vorzeichen-Konflikt. Isoliert Achse-2-Magnitude vom Vorzeichen-Thema."""
    tz_list = [_make_tz(date.today() - timedelta(days=1), 3.0)]
    ha_func = lambda d: {"batterie_5": 8.0}
    result = await _run_check(tz_list, [_make_inv()], ha_func)

    assert len(result) == 1, f"Erwartet nur OK-Eintrag, bekommen {result}"
    assert result[0].schwere == "ok"
    assert not any(r.action_kind for r in result)


async def test_kein_batterie_netto_leer():
    """Tages-Netto unter Schwelle (kein/winziger Speicher) → Kategorie leer."""
    tz_list = [_make_tz(date.today() - timedelta(days=i), 0.2) for i in range(1, 6)]
    ha_func = lambda d: {"batterie_5": -0.2}
    result = await _run_check(tz_list, [_make_inv()], ha_func)
    assert result == [], f"Erwartet leer (keine nennenswerte Batterie), bekommen {result}"


async def test_standalone_leer():
    """Kein HA-LTS → keine Referenz → leer, kein Crash."""
    tz_list = [_make_tz(date.today() - timedelta(days=1), -4.0)]
    ha_func = lambda d: {"batterie_5": 4.0}
    result = await _run_check(tz_list, [_make_inv()], ha_func, ha_available=False)
    assert result == [], f"Erwartet leer im Standalone, bekommen {result}"


async def test_span_groesser_31_fenster_begrenzt():
    """40 Konflikt-Tage → Bereichs-Knopf nur jüngstes 31-Tage-Fenster, Rest-Hinweis."""
    today = date.today()
    tz_list = [_make_tz(today - timedelta(days=i), -4.0) for i in range(1, 41)]
    ha_func = lambda d: {"batterie_5": 4.0}
    result = await _run_check(tz_list, [_make_inv()], ha_func)

    range_eintraege = [r for r in result if r.action_kind == "reaggregate_range"]
    assert len(range_eintraege) == 1
    params = range_eintraege[0].action_params
    neuester = today - timedelta(days=1)
    erwartet_von = neuester - timedelta(days=30)  # 31-Tage-Fenster (max 31 Tage)
    assert params["bis"] == neuester.isoformat()
    assert params["von"] == erwartet_von.isoformat(), f"von: {params['von']}"
    # Rest-Hinweis im Summen-Detail
    assert "ältere" in range_eintraege[0].details
    # Einzeltag-Einträge auf 15 begrenzt + Rest-Hinweis-Eintrag
    day_eintraege = [r for r in result if r.action_kind == "reaggregate_day"]
    assert len(day_eintraege) == 15, f"Erwartet 15 Einzeltage, bekommen {len(day_eintraege)}"
    rest_hinweise = [r for r in result if r.action_kind is None and "weitere" in r.meldung]
    assert len(rest_hinweise) == 1


_TESTS = [
    test_vorzeichen_konflikt_erkannt,
    test_gleiche_richtung_magnitude_drift_kein_konflikt,
    test_kein_batterie_netto_leer,
    test_standalone_leer,
    test_span_groesser_31_fenster_begrenzt,
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
