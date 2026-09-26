"""Zählerlücken wie HA — Schnitt 8: Wärme/Klima-Tagesleser mit Anker (R1).

Vorlage `plans/vorlage-zaehlerluecken-ha-weg.md` Fassung 7 §2 (Zeile
„Wärme/Klima-Tagesleser"): der Rückfall bei fehlendem Tagesrand ist nicht mehr
„erster Stand im Fenster", sondern **der letzte Stand vor dem Fenster** —
beliebig weit zurück, wie HA eine Stunde rechnet. Erst ohne jeden Stand davor
(die Reihe beginnt im Fenster) rückt der Rand in das Fenster.

Schwesterdateien: test_zaehlerluecken_snapshot.py (Snapshot-Tagestabelle),
test_n434_tagesfenster_betriebsart.py, test_waerme_verlauf_bereichs_leser.py.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from backend.models import Investition
from backend.models.sensor_snapshot import SensorSnapshot

DATUM = date(2026, 1, 15)
T0 = datetime.combine(DATUM, datetime.min.time())
KEY = "inv:7:heizenergie_kwh"


def _ohne_ha():
    svc = MagicMock()
    svc.is_available = False
    return patch("backend.services.snapshot.reader.get_ha_statistics_service", return_value=svc)


async def _staende(db, paare):
    for ts, w in paare:
        db.add(SensorSnapshot(anlage_id=1, sensor_key=KEY, zeitpunkt=ts, wert_kwh=w, quelle="mqtt"))
    await db.commit()


async def test_tagesdetail_rand_fehlt_letzter_stand_davor_traegt(db):
    from backend.services.snapshot.aggregator import _tagesdetail_boundary_diff_mit_grund

    # Letzter Stand gestern 15:00 (100), dann erst heute 04:00 (120) … 24:00 (140)
    await _staende(db, [(T0 - timedelta(hours=9), 100.0), (T0 + timedelta(hours=4), 120.0),
                        (T0 + timedelta(hours=24), 140.0)])
    anlage = SimpleNamespace(id=1)
    with _ohne_ha():
        menge, grund = await _tagesdetail_boundary_diff_mit_grund(
            db, anlage, {}, KEY, None, T0, T0 + timedelta(days=1), DATUM,
            rueckfall_tagesrand=True,
        )
    assert grund is None
    assert menge.wert_kwh == pytest.approx(40.0)          # ab dem Anker, nicht ab 04:00 (20)
    assert menge.seit == T0 - timedelta(hours=9)
    assert menge.ab_tagesbeginn is True                   # keine Einschränkung auszuweisen


async def test_tagesdetail_reihe_beginnt_im_fenster_rueckt_auf_den_ersten_stand(db):
    from backend.services.snapshot.aggregator import _tagesdetail_boundary_diff_mit_grund

    await _staende(db, [(T0 + timedelta(hours=11), 50.0), (T0 + timedelta(hours=24), 58.0)])
    with _ohne_ha():
        menge, _ = await _tagesdetail_boundary_diff_mit_grund(
            db, SimpleNamespace(id=1), {}, KEY, None, T0, T0 + timedelta(days=1), DATUM,
            rueckfall_tagesrand=True,
        )
    assert menge.wert_kwh == pytest.approx(8.0)
    assert menge.ab_tagesbeginn is False                  # „ab 11 Uhr" bleibt ausgewiesen


async def test_bereichsleser_mitternachtsluecke_folgetag_traegt_die_energie(db):
    from backend.services.snapshot.bereichs_leser import lade_tageswerte_je_geraet

    d0, d1 = date(2026, 1, 14), date(2026, 1, 15)
    t0 = datetime.combine(d0, datetime.min.time())
    # Stände 14.01 00:00 (10) · 14.01 18:00 (16) · — Lücke über Mitternacht — · 15.01 06:00 (22) · 16.01 00:00 (30)
    await _staende(db, [(t0, 10.0), (t0 + timedelta(hours=18), 16.0),
                        (t0 + timedelta(hours=30), 22.0), (t0 + timedelta(hours=48), 30.0)])
    inv = SimpleNamespace(id=7, typ="waermepumpe", parameter={}, parent_investition_id=None)
    anlage = SimpleNamespace(id=1, sensor_mapping={"investitionen": {"7": {"felder": {
        "heizenergie_kwh": {"strategie": "sensor", "sensor_id": "sensor.wm"}}}}})
    with _ohne_ha():
        erg = await lade_tageswerte_je_geraet(
            db, anlage, {"7": inv}, d0, d1, {("waermepumpe", "heizenergie_kwh"): "wp_heizung_kwh"},
        )
    assert d0 not in erg                                  # Tagesende fehlt ⇒ keine Aussage
    assert erg[d1]["wp_heizung_kwh"]["7"] == pytest.approx(14.0)   # 30 − 16 (Anker 18:00)
