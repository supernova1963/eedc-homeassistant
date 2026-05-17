"""
Akzeptanztest für Etappe 6 (v3.31.1):
`DatenChecker._check_datenquelle_drift()` vergleicht PV-Tagessumme der
TagesZusammenfassung mit HA-LTS-Daily-Read der letzten 90 Tage und
liefert pro Drift-Tag einen CheckErgebnis-Eintrag mit Inline-Reparatur-Action.

Self-contained:

    eedc/backend/venv/bin/python eedc/backend/tests/test_etappe_6_drift_check.py

Testet:
  1. Keine Drift → ein OK-CheckErgebnis ohne Tag-Einträge
  2. Drift unter Schwelle (1 kWh / 3 %) → kein Eintrag
  3. Drift über Schwelle (3 kWh / 8 %) → INFO-Eintrag mit action_kind="reaggregate_day"
  4. Mehrere Drift-Tage → Sortierung nach |Δ| desc
  5. > 20 Drift-Tage → 20 Einträge plus „weitere"-Hinweis
  6. HA-LTS nicht verfügbar → leere Ergebnisliste (kein Crash)
  7. Anlage ohne TagesZusammenfassung → leere Ergebnisliste
  8. Tag mit eedc=0 UND ha=0 → kein Eintrag (Inbetriebnahme-Edge-Case)
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, MagicMock, AsyncMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.services.daten_checker import DatenChecker, CheckKategorie  # noqa: E402


def _make_tz(datum: date, pv_kwh: float):
    """Plain TagesZusammenfassung-duck — vermeidet ORM-Setup."""
    return SimpleNamespace(
        id=1,
        anlage_id=1,
        datum=datum,
        komponenten_kwh={"pv_3": pv_kwh, "netzbezug": 2.0},
    )


def _make_anlage():
    return SimpleNamespace(id=1, sensor_mapping={
        "investitionen": {"3": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}}}},
    })


def _make_inv(inv_id=3, typ="pv-module"):
    return SimpleNamespace(id=inv_id, anlage_id=1, typ=typ, parameter={})


def _build_checker(tz_list, invs_list, ha_tageskwh_func, ha_available=True):
    """Wickelt eine DB-Mock + Patches die externe Services."""
    db = MagicMock()
    call_count = {"n": 0}

    async def _execute(stmt):
        result = MagicMock()
        # Erstes execute: TagesZusammenfassung — zweite: Investition
        call_count["n"] += 1
        if call_count["n"] == 1:
            scalars = MagicMock()
            scalars.all = MagicMock(return_value=tz_list)
            result.scalars = MagicMock(return_value=scalars)
        else:
            scalars = MagicMock()
            scalars.all = MagicMock(return_value=invs_list)
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


async def test_keine_drift_ok_meldung():
    """Alle Tage stimmen ≈ HA-LTS → eine OK-Meldung."""
    today = date.today()
    tz_list = [_make_tz(today - timedelta(days=i), 30.0) for i in range(1, 11)]
    ha_func = lambda d: {"pv_3": 30.0}  # Identisch
    checker, patches = _build_checker(tz_list, [_make_inv()], ha_func)

    for p in patches:
        p.start()
    try:
        result = await checker._check_datenquelle_drift(_make_anlage())
    finally:
        for p in patches:
            p.stop()

    assert len(result) == 1, f"Erwartet 1 OK-Eintrag, bekommen {len(result)}"
    assert result[0].schwere == "ok"
    assert "Keine signifikanten Abweichungen" in result[0].meldung


async def test_drift_unter_schwelle_kein_eintrag():
    """Drift 1 kWh / 3 % → nicht in Liste (unter beiden Schwellen)."""
    today = date.today()
    tz_list = [_make_tz(today - timedelta(days=1), 30.0)]
    ha_func = lambda d: {"pv_3": 31.0}  # 1 kWh abweichend, ~3 %
    checker, patches = _build_checker(tz_list, [_make_inv()], ha_func)

    for p in patches:
        p.start()
    try:
        result = await checker._check_datenquelle_drift(_make_anlage())
    finally:
        for p in patches:
            p.stop()

    assert len(result) == 1, f"Erwartet 1 OK-Eintrag, bekommen {result}"
    assert result[0].schwere == "ok"


async def test_drift_ueber_schwelle_eintrag_mit_action():
    """Drift 3 kWh / 8 % → 1 INFO-Eintrag mit reaggregate_day-Action."""
    today = date.today()
    test_datum = today - timedelta(days=1)
    tz_list = [_make_tz(test_datum, 35.0)]
    ha_func = lambda d: {"pv_3": 38.0}  # 3 kWh = 7.9 % drift
    checker, patches = _build_checker(tz_list, [_make_inv()], ha_func)

    for p in patches:
        p.start()
    try:
        result = await checker._check_datenquelle_drift(_make_anlage())
    finally:
        for p in patches:
            p.stop()

    info_eintraege = [r for r in result if r.schwere == "info"]
    assert len(info_eintraege) == 1, f"Erwartet 1 INFO-Eintrag, bekommen {len(info_eintraege)}"
    eintrag = info_eintraege[0]
    assert eintrag.action_kind == "reaggregate_day", f"action_kind: {eintrag.action_kind}"
    assert eintrag.action_params == {"anlage_id": 1, "datum": test_datum.isoformat()}, \
        f"action_params: {eintrag.action_params}"
    assert eintrag.action_label == "Tag reparieren"
    assert test_datum.isoformat() in eintrag.meldung
    assert "35.0" in eintrag.meldung and "38.0" in eintrag.meldung


async def test_sortierung_nach_delta_desc():
    """Drei Drift-Tage mit Δ 1.5/6/3 → Reihenfolge im Result: 6, 3, 1.5."""
    today = date.today()
    drift_data = [
        (today - timedelta(days=10), 30.0, 36.0),  # Δ=6 kWh, 16.7 %
        (today - timedelta(days=20), 30.0, 33.0),  # Δ=3 kWh, 9.1 %
        (today - timedelta(days=5), 30.0, 31.5),   # Δ=1.5 kWh, 4.8 % → unter Schwelle!
    ]
    tz_list = [_make_tz(d, eedc) for d, eedc, _ in drift_data]
    ha_lookup = {d: {"pv_3": ha} for d, _, ha in drift_data}
    ha_func = lambda d: ha_lookup.get(d, {"pv_3": 0.0})
    checker, patches = _build_checker(tz_list, [_make_inv()], ha_func)

    for p in patches:
        p.start()
    try:
        result = await checker._check_datenquelle_drift(_make_anlage())
    finally:
        for p in patches:
            p.stop()

    info_eintraege = [r for r in result if r.schwere == "info" and r.action_kind == "reaggregate_day"]
    # 1.5 kWh ist 4.8 % → unter 5 %-Schwelle → nicht enthalten
    assert len(info_eintraege) == 2, f"Erwartet 2, bekommen {len(info_eintraege)}: {[e.meldung for e in info_eintraege]}"
    # Erster Eintrag = Δ=6 (größer)
    assert "36.0" in info_eintraege[0].meldung, f"Erster: {info_eintraege[0].meldung}"
    assert "33.0" in info_eintraege[1].meldung, f"Zweiter: {info_eintraege[1].meldung}"


async def test_max_20_eintraege_plus_rest_hinweis():
    """25 Drift-Tage → 20 Action-Einträge + 1 Hinweis-Eintrag ohne Action."""
    today = date.today()
    tz_list = []
    ha_lookup = {}
    for i in range(1, 26):
        d = today - timedelta(days=i)
        eedc = 30.0
        ha = 35.0 + i * 0.1  # Δ steigt mit i, sortierung dann nach |Δ| desc
        tz_list.append(_make_tz(d, eedc))
        ha_lookup[d] = {"pv_3": ha}
    ha_func = lambda d: ha_lookup.get(d, {"pv_3": 0.0})
    checker, patches = _build_checker(tz_list, [_make_inv()], ha_func)

    for p in patches:
        p.start()
    try:
        result = await checker._check_datenquelle_drift(_make_anlage())
    finally:
        for p in patches:
            p.stop()

    action_eintraege = [r for r in result if r.action_kind == "reaggregate_day"]
    assert len(action_eintraege) == 20, f"Erwartet 20 Action-Einträge, bekommen {len(action_eintraege)}"
    rest_hinweis = [r for r in result if r.action_kind is None and "weitere" in r.meldung]
    assert len(rest_hinweis) == 1, f"Erwartet 1 Rest-Hinweis, bekommen {len(rest_hinweis)}"
    assert "5 weitere" in rest_hinweis[0].meldung, f"Rest: {rest_hinweis[0].meldung}"


async def test_ha_lts_nicht_verfuegbar_leer():
    """Standalone-Modus → leere Ergebnisliste, kein Crash."""
    checker, patches = _build_checker(
        [_make_tz(date.today() - timedelta(days=1), 30.0)],
        [_make_inv()],
        lambda d: {"pv_3": 35.0},
        ha_available=False,
    )

    for p in patches:
        p.start()
    try:
        result = await checker._check_datenquelle_drift(_make_anlage())
    finally:
        for p in patches:
            p.stop()

    assert result == [], f"Erwartet leer, bekommen: {result}"


async def test_keine_tagesdaten_leer():
    """Frische Anlage ohne TagesZusammenfassung → leer."""
    checker, patches = _build_checker([], [], lambda d: {"pv_3": 0.0})

    for p in patches:
        p.start()
    try:
        result = await checker._check_datenquelle_drift(_make_anlage())
    finally:
        for p in patches:
            p.stop()

    assert result == [], f"Erwartet leer, bekommen: {result}"


async def test_eedc_und_ha_beide_null_kein_eintrag():
    """Inbetriebnahme-Edge-Case: eedc=0 UND ha=0 → kein Drift-Eintrag."""
    today = date.today()
    tz_list = [_make_tz(today - timedelta(days=1), 0.0)]
    ha_func = lambda d: {"pv_3": 0.0}
    checker, patches = _build_checker(tz_list, [_make_inv()], ha_func)

    for p in patches:
        p.start()
    try:
        result = await checker._check_datenquelle_drift(_make_anlage())
    finally:
        for p in patches:
            p.stop()

    # Wenn alle TZ "leer" sind, sammelt sich nichts in drift_pro_tag, also OK-Meldung.
    assert len(result) == 1
    assert result[0].schwere == "ok"


_TESTS = [
    test_keine_drift_ok_meldung,
    test_drift_unter_schwelle_kein_eintrag,
    test_drift_ueber_schwelle_eintrag_mit_action,
    test_sortierung_nach_delta_desc,
    test_max_20_eintraege_plus_rest_hinweis,
    test_ha_lts_nicht_verfuegbar_leer,
    test_keine_tagesdaten_leer,
    test_eedc_und_ha_beide_null_kein_eintrag,
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
