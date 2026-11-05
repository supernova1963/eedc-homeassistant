"""Benannte Proben für RF-53 … RF-55 (Energie-Profil unter 50): die Zweige, die die direkten Testdateien am HEAD `c28461eca`
nicht betreten — gemessen per Bogen-Spur über die 14 direkten Dateien (`refactoring-werkzeug/rf53/ausgaben/abdeckung-tests-head.txt`).

Drei Rümpfe, je in Phasen geschnitten (Bauform RF-1); die Proben halten das Verhalten an den Stellen fest, an denen ein Schnitt
einen Zweig still verlieren könnte:

* ``services/energie_profil/_helpers.py::_get_tagespeaks_aus_ha_lts`` — Invert-Flags einer **Investition**, Statistik nicht
  verfügbar bzw. Lesefehler (Aufrufer-Fallback), Kombi-Einspeisung = größter Betrag eines negativen Minimums, BKW zählt als
  PV, Speicher nicht, Kombi entfällt neben dedizierten Netz-Sensoren.
* ``services/live_verbrauchsprofil_service.py::_profil_from_ha`` — N-536 (die Entity des Balkonkraftwerks entfällt genau dann,
  wenn **jedes** Modul-Kind misst), Kombi-Vorzeichen, ``Verbrauch = max(0, PV + Bezug − Einspeisung)``, PV-Gesamt nur ohne
  Investitions-PV, WP-Reihen als Betrag und nur mit WP-Sensor, Referenz-HDD nur mit Temperatur (N-593), die vier
  None-Ausgänge, Werktag/Wochenende, Invertierung (#58).
* ``services/ha_statistics_service.py::HAStatisticsService.get_hourly_slots_for_day`` — leere/nicht verfügbare Eingänge,
  kein Summen-Sensor, NULL-Zeile ist keine Zeile (R1), Polster-Zeile vor dem Fenster ist weder Stand noch Anker, Lesefehler
  ⇒ Warnung und ``{}``, Einheit MWh → kWh.

Schwesterdateien: ``test_etappe_5_peaks.py`` (Peaks, Etappe 5) · ``test_verbrauchsprofil_slot_konvention.py`` (Backward-Slots,
N-45/N-46) · ``test_zaehlerluecken_slots.py`` (Slot-Tabelle R1/R2, P2/P5/P8/P9). Gate der Sitzung daneben: die drei
Fixture-GMs ``skript-golden-master-tagespeaks-lts.py``, ``…-verbrauchsprofil-ha.py``, ``…-hourly-slots.py``.
"""
from __future__ import annotations

import logging
import os
import time as _time
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from backend.core.berechnungen.heizgradtage import referenz_heizgradtage
from backend.services import live_verbrauchsprofil_service as lvs
from backend.services.energie_profil._helpers import TagesPeaks, _get_tagespeaks_aus_ha_lts
from backend.services.ha_statistics_service import HAStatisticsService, SensorSlotReihe, StundenSlot
from backend.tests import ha_lts_helfer

# ─── Gemeinsam ────────────────────────────────────────────────────────────────────────────────────────────────────────


def _db(zeilen: list[tuple]):
    """AsyncSession-Attrappe: ``execute(...).all()`` liefert die Zeilen (die Investitions-Abfrage beider Rümpfe)."""
    db = MagicMock()

    async def _execute(stmt):
        res = MagicMock()
        res.all = MagicMock(return_value=list(zeilen))
        return res

    db.execute = _execute
    return db


# ─── RF-53: Tages-Peaks aus der HA-Langzeitstatistik ─────────────────────────────────────────────────────────────────

D = date(2026, 5, 15)


def _stats(minmax: dict | None, *, verfuegbar: bool = True, fehler: bool = False):
    svc = MagicMock()
    svc.is_available = verfuegbar

    def _lesen(ids, von, bis):
        if fehler:
            raise RuntimeError("Recorder weg")
        return {eid: {D.isoformat(): minmax[eid]} for eid in ids if eid in (minmax or {})}

    svc.get_hourly_minmax_sensor_data.side_effect = _lesen
    return svc


async def _peaks(mapping: dict, minmax: dict | None, invs=(), **kw) -> tuple[TagesPeaks, MagicMock]:
    svc = _stats(minmax, **kw)
    with patch("backend.services.ha_statistics_service.get_ha_statistics_service", return_value=svc):
        p = await _get_tagespeaks_aus_ha_lts(SimpleNamespace(id=1, sensor_mapping=mapping), D, _db(list(invs)))
    return p, svc


async def test_peaks_invert_flag_einer_investition_tauscht_min_und_max():
    """``live_invert`` an der Investition (nicht an der Basis): min↔max getauscht und negiert, bevor Σ max je Stunde läuft."""
    mapping = {"investitionen": {"3": {"live": {"leistung_w": "sensor.m3"}, "live_invert": {"leistung_w": True}}}}
    p, _ = await _peaks(mapping, {"sensor.m3": {12: {"min": -8.0, "max": -1.0}}}, invs=[(3, "pv-module")])
    assert p.pv == 8.0


async def test_peaks_statistik_nicht_verfuegbar_liest_nicht_und_liefert_none():
    p, svc = await _peaks({"basis": {"live": {"pv_gesamt_w": "sensor.pv"}}}, {"sensor.pv": {12: {"max": 5.0}}}, verfuegbar=False)
    assert p == TagesPeaks(None, None, None)
    svc.get_hourly_minmax_sensor_data.assert_not_called()


async def test_peaks_lesefehler_liefert_none_fuer_den_aufrufer_fallback():
    p, _ = await _peaks({"basis": {"live": {"netz_kombi_w": "sensor.netz"}}}, {}, fehler=True)
    assert p == TagesPeaks(None, None, None)


async def test_peaks_kombi_einspeisung_ist_der_groesste_betrag_eines_negativen_minimums():
    minmax = {"sensor.netz": {10: {"min": -3.0, "max": 0.5}, 12: {"min": -6.0, "max": 0.1}, 14: {"min": -2.0, "max": 1.5}}}
    p, _ = await _peaks({"basis": {"live": {"netz_kombi_w": "sensor.netz"}}}, minmax)
    assert (p.netzbezug, p.einspeisung) == (1.5, 6.0)


async def test_peaks_balkonkraftwerk_zaehlt_als_pv_speicher_nicht():
    mapping = {"investitionen": {"7": {"live": {"leistung_w": "sensor.bkw"}}, "8": {"live": {"leistung_w": "sensor.sp"}}}}
    minmax = {"sensor.bkw": {12: {"max": 0.6}}, "sensor.sp": {12: {"max": 3.0}}}
    p, svc = await _peaks(mapping, minmax, invs=[(7, "balkonkraftwerk"), (8, "speicher")])
    assert p.pv == 0.6
    assert sorted(svc.get_hourly_minmax_sensor_data.call_args.args[0]) == ["sensor.bkw"]


async def test_peaks_kombi_entfaellt_neben_dediziertem_bezug():
    mapping = {"basis": {"live": {"netz_kombi_w": "sensor.netz", "netzbezug_w": "sensor.bezug"}}}
    minmax = {"sensor.netz": {12: {"min": -6.0, "max": 9.0}}, "sensor.bezug": {19: {"min": 0.0, "max": 4.5}}}
    p, _ = await _peaks(mapping, minmax)
    assert (p.netzbezug, p.einspeisung) == (4.5, None)


# ─── RF-54: Verbrauchsprofil aus der HA-History ──────────────────────────────────────────────────────────────────────

JETZT = datetime(2026, 11, 5, 9, 17, 23)   # Donnerstag; Fenster = Slots 29.10. … 04.11. (5 Werktage, 2 Wochenendtage)
B, E, K, PV, T = "sensor.bezug", "sensor.einsp", "sensor.netz", "sensor.pv", "sensor.temp"


class _FesteUhr(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 5, 9, 17, 23, tzinfo=tz)


def _punkte(fn) -> list[tuple[datetime, float]]:
    """Alle 15 Minuten vom Fensterbeginn (28.10. 23:00) bis jetzt; ``fn(t)`` → W."""
    t, out = datetime(2026, 10, 28, 23, 0), []
    while t <= JETZT:
        out.append((t, float(fn(t))))
        t += timedelta(minutes=15)
    return out


@pytest.fixture
def ha(monkeypatch):
    """Erreichbare HA mit fester History; liefert das Dict der gefragten Sensor-Listen (zum Nachsehen)."""
    stand = {"verfuegbar": True, "history": {}, "gefragt": []}

    class _Ha:
        @property
        def is_available(self):
            return stand["verfuegbar"]

    async def _hist(ids, start, end):
        stand["gefragt"].append(sorted(ids))
        return {eid: [(ts, v) for ts, v in pts if start <= ts <= end]
                for eid, pts in stand["history"].items() if eid in ids}, {}

    monkeypatch.setattr("backend.services.ha_state_service.get_ha_state_service", lambda: _Ha())
    monkeypatch.setattr(lvs, "get_history_normalized", _hist)
    monkeypatch.setattr(lvs, "datetime", _FesteUhr)
    return stand


async def _profil(mapping: dict, invs=()):
    return await lvs._profil_from_ha(SimpleNamespace(id=1, sensor_mapping=mapping), _db(list(invs)))


def _konstant(w: float):
    return _punkte(lambda t: w)


_BKW_INV = {"7": {"live": {"leistung_w": "sensor.bkw"}}, "8": {"live": {"leistung_w": "sensor.k8"}},
            "9": {"live": {"leistung_w": "sensor.k9"}}}
_BKW_ZEILEN = [(7, "balkonkraftwerk", None), (8, "pv-module", 7), (9, "pv-module", 7)]


async def test_n536_bkw_entity_entfaellt_wenn_jedes_kind_misst(ha):
    ha["history"] = {B: _konstant(200.0), "sensor.bkw": _konstant(1000.0), "sensor.k8": _konstant(300.0), "sensor.k9": _konstant(300.0)}
    p = await _profil({"basis": {"live": {"netzbezug_w": B}}, "investitionen": _BKW_INV}, _BKW_ZEILEN)
    assert set(p["werktag"].values()) == {0.8}           # 0,3 + 0,3 + 0,2 — das BKW nicht noch einmal
    assert "sensor.bkw" not in ha["gefragt"][0]


async def test_n536_bkw_bleibt_wenn_ein_kind_nicht_misst(ha):
    ha["history"] = {B: _konstant(200.0), "sensor.bkw": _konstant(1000.0), "sensor.k8": _konstant(300.0), "sensor.k9": _konstant(300.0)}
    inv = {k: v for k, v in _BKW_INV.items() if k != "9"}
    p = await _profil({"basis": {"live": {"netzbezug_w": B}}, "investitionen": inv}, _BKW_ZEILEN)
    assert set(p["werktag"].values()) == {1.5}           # BKW 1,0 + Kind 0,3 + Bezug 0,2


async def test_kombi_positiv_ist_bezug_negativ_ist_einspeisung(ha):
    ha["history"] = {K: _punkte(lambda t: -2000.0 if t.hour == 12 else 500.0),
                     PV: _punkte(lambda t: 3000.0 if t.hour == 12 else 0.0)}
    p = await _profil({"basis": {"live": {"netz_kombi_w": K, "pv_gesamt_w": PV}}})
    assert p["werktag"][13] == 1.0                       # [12:00, 13:00): 3,0 PV − 2,0 Einspeisung
    assert p["werktag"][12] == 0.5


async def test_verbrauch_ist_max_null_aus_pv_plus_bezug_minus_einspeisung(ha):
    ha["history"] = {B: _konstant(0.0), E: _konstant(5000.0), PV: _konstant(1000.0)}
    p = await _profil({"basis": {"live": {"netzbezug_w": B, "einspeisung_w": E, "pv_gesamt_w": PV}}})
    assert set(p["werktag"].values()) == {0.0}


async def test_pv_gesamt_nur_ohne_eigene_pv_sensoren(ha):
    ha["history"] = {B: _konstant(200.0), PV: _konstant(9000.0), "sensor.m3": _konstant(1000.0)}
    p = await _profil({"basis": {"live": {"netzbezug_w": B, "pv_gesamt_w": PV}},
                       "investitionen": {"3": {"live": {"leistung_w": "sensor.m3"}}}}, [(3, "pv-module", None)])
    assert set(p["werktag"].values()) == {1.2}


async def test_waermepumpe_als_betrag_und_reihen_nur_mit_wp_sensor(ha):
    ha["history"] = {B: _konstant(200.0), "sensor.wp": _konstant(-400.0)}
    mit = await _profil({"basis": {"live": {"netzbezug_w": B}}, "investitionen": {"20": {"live": {"leistung_w": "sensor.wp"}}}},
                        [(20, "waermepumpe", None)])
    assert set(mit["wp_werktag"].values()) == {0.4} and set(mit["wp_wochenende"].values()) == {0.4}
    ohne = await _profil({"basis": {"live": {"netzbezug_w": B}}})
    assert "wp_werktag" not in ohne and "wp_wochenende" not in ohne


async def test_referenz_hdd_nur_mit_temperatur_sensor(ha):
    ha["history"] = {B: _konstant(200.0), T: _konstant(5.0)}
    mit = await _profil({"basis": {"live": {"netzbezug_w": B, "aussentemperatur_c": T}}})
    tage = {date(2026, 10, 29) + timedelta(days=i): [5.0] * 24 for i in range(7)}
    assert mit["referenz_hdd_kd"] == referenz_heizgradtage(tage)
    ohne = await _profil({"basis": {"live": {"netzbezug_w": B}}})
    assert "referenz_hdd_kd" not in ohne


async def test_die_vier_none_ausgaenge(ha):
    ha["history"] = {B: _konstant(200.0)}
    ha["verfuegbar"] = False
    assert await _profil({"basis": {"live": {"netzbezug_w": B}}}) is None           # HA nicht erreichbar
    ha["verfuegbar"] = True
    assert await _profil({"basis": {"live": {"pv_gesamt_w": PV}}}) is None          # keine Netz-Zuordnung …
    assert ha["gefragt"] == []                                                        # … und nichts gelesen
    ha["history"] = {}
    assert await _profil({"basis": {"live": {"netzbezug_w": B}}}) is None           # leere History
    ha["history"] = {B: [], PV: _konstant(1000.0)}
    assert await _profil({"basis": {"live": {"netzbezug_w": B, "pv_gesamt_w": PV}}}) is None   # Netz ohne Punkte


async def test_kombi_entfaellt_neben_bezug_auch_als_beleg(ha):
    ohne_0311 = [p for p in _konstant(300.0) if (p[0] + timedelta(hours=1)).date() != date(2026, 11, 3)]
    ha["history"] = {K: _konstant(-9000.0), B: ohne_0311}
    p = await _profil({"basis": {"live": {"netz_kombi_w": K, "netzbezug_w": B}}})
    assert set(p["werktag"].values()) == {0.3}
    assert p["tage_werktag"] == 4                        # der 03.11. hat keinen Bezugs-Beleg — der Kombi-Sensor zählt nicht


async def test_werktag_und_wochenende_getrennt(ha):
    ha["history"] = {B: _punkte(lambda t: 1000.0 if (t + timedelta(hours=1)).weekday() >= 5 else 500.0)}
    p = await _profil({"basis": {"live": {"netzbezug_w": B}}})
    assert set(p["werktag"].values()) == {0.5} and set(p["wochenende"].values()) == {1.0}
    assert (p["tage_werktag"], p["tage_wochenende"]) == (5, 2)


async def test_invertierte_einspeisung_wird_vor_dem_mittel_negiert(ha):
    ha["history"] = {B: _konstant(500.0), E: _konstant(-200.0), PV: _konstant(1000.0)}
    p = await _profil({"basis": {"live": {"netzbezug_w": B, "einspeisung_w": E, "pv_gesamt_w": PV},
                                 "live_invert": {"einspeisung_w": True}}})
    assert set(p["werktag"].values()) == {1.3}           # 1,0 + 0,5 − 0,2


async def test_sensor_ohne_punkt_in_der_stunde_traegt_null_bei(ha):
    """Beobachtet ist die Stunde über den Einspeise-Sensor; Bezug (nur gerade Stunden), PV (nie um 3 Uhr), WP (nur um 5 Uhr)
    und Temperatur (nur um 6 Uhr) fehlen in einzelnen Stunden — dort tragen sie 0 bzw. keine Temperatur bei."""
    ha["history"] = {E: _konstant(100.0), B: [p for p in _konstant(400.0) if p[0].hour % 2 == 0],
                     PV: [p for p in _konstant(1000.0) if p[0].hour != 3], "sensor.wp": [p for p in _konstant(600.0) if p[0].hour == 5],
                     T: [p for p in _konstant(8.0) if p[0].hour == 6]}
    p = await _profil({"basis": {"live": {"netzbezug_w": B, "einspeisung_w": E, "pv_gesamt_w": PV, "aussentemperatur_c": T}},
                       "investitionen": {"20": {"live": {"leistung_w": "sensor.wp"}}}}, [(20, "waermepumpe", None)])
    assert p["werktag"][4] == 0.0                         # [3:00, 4:00): kein Bezug, keine PV, 0,1 Einspeisung ⇒ max(0, …)
    assert p["werktag"][5] == 1.3                         # [4:00, 5:00): 1,0 + 0,4 − 0,1
    assert p["werktag"][6] == 0.9                         # [5:00, 6:00): kein Bezug
    assert p["wp_werktag"][6] == 0.6 and p["wp_werktag"][7] == 0.0
    tage = {date(2026, 10, 29) + timedelta(days=i): [8.0] for i in range(7)}
    assert p["referenz_hdd_kd"] == referenz_heizgradtage(tage)


# ─── RF-55: Slot-Tabelle eines Zählers ───────────────────────────────────────────────────────────────────────────────

SID = "sensor.zaehler"
DS = date(2026, 5, 15)


@pytest.fixture
def berlin():
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


def _sql(zeilen: list[tuple[float, float | None]], unit: str = "kWh", has_sum: bool = True) -> HAStatisticsService:
    svc = ha_lts_helfer.mach_service()
    mid = ha_lts_helfer.sensor(svc, SID, unit, has_sum=has_sum, has_mean=not has_sum)
    with svc._engine.begin() as conn:
        for ts, w in zeilen:
            conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) VALUES (:m, :t, :w, :w)"),
                         {"m": mid, "t": ts, "w": w})
    return svc


def _stunden(von: datetime, bis: datetime, start: float, pro_h: float, null=()):
    out, t, w = [], von, start
    while t <= bis:
        out.append((t.timestamp(), None if t in null else round(w, 3)))
        w += pro_h
        t += timedelta(hours=1)
    return out


def test_slots_leere_sensorliste_und_kein_transport_geben_leeres_dict(berlin):
    assert _sql(_stunden(datetime(2026, 5, 14, 22), datetime(2026, 5, 15, 22), 1.0, 1.0)).get_hourly_slots_for_day([], DS) == {}
    aus = HAStatisticsService()
    aus._initialized, aus._engine, aus._ws_client = True, None, None
    assert aus.get_hourly_slots_for_day([SID], DS) == {}


def test_slots_ohne_summen_spalte_kein_ergebnis(berlin):
    svc = _sql(_stunden(datetime(2026, 5, 14, 22), datetime(2026, 5, 15, 22), 1.0, 1.0), has_sum=False)
    assert svc.get_hourly_slots_for_day([SID], DS) == {}


def test_slots_null_zeile_ist_keine_zeile_naechster_slot_traegt_beide_stunden(berlin):
    zeilen = _stunden(datetime(2026, 5, 14, 22), datetime(2026, 5, 15, 22), 100.0, 2.0, null={datetime(2026, 5, 15, 7)})
    reihe = _sql(zeilen).get_hourly_slots_for_day([SID], DS)[SID]
    assert 8 not in reihe.slots and reihe.slots[9] == StundenSlot(4.0, 2)


def test_slots_polster_zeile_vor_dem_fenster_ist_weder_stand_noch_anker(berlin):
    """21:57 Vortag liegt im 5-Minuten-Polster des Fensters, fällt aber auf Index −2: kein Stand, und die Anker-Suche
    (``start_ts < ts_von``) sieht sie auch nicht — die Reihe beginnt im Fenster (R1, kein Anker)."""
    zeilen = [(datetime(2026, 5, 14, 21, 57).timestamp(), 90.0)] + _stunden(datetime(2026, 5, 15, 3), datetime(2026, 5, 15, 22), 100.0, 1.0)
    reihe = _sql(zeilen).get_hourly_slots_for_day([SID], DS)[SID]
    assert reihe.anker_start_ts is None and 4 not in reihe.slots and reihe.slots[5] == StundenSlot(1.0, 1)


def test_slots_lesefehler_warnung_und_leeres_dict(berlin, caplog):
    svc = _sql(_stunden(datetime(2026, 5, 14, 22), datetime(2026, 5, 15, 22), 1.0, 1.0))
    with svc._engine.begin() as conn:
        conn.execute(text("DROP TABLE statistics"))
    with caplog.at_level(logging.WARNING, logger="backend.services.ha_statistics_service"):
        assert svc.get_hourly_slots_for_day([SID], DS) == {}
    assert any("get_hourly_slots_for_day Fehler: OperationalError" in r.getMessage() for r in caplog.records)


def test_slots_einheit_mwh_wird_kwh_auch_am_anker(berlin):
    zeilen = ([(datetime(2026, 5, 14, 17).timestamp(), 0.5)]
              + _stunden(datetime(2026, 5, 15, 3), datetime(2026, 5, 15, 22), 0.53, 0.002))
    reihe = _sql(zeilen, unit="MWh").get_hourly_slots_for_day([SID], DS)[SID]
    assert reihe == SensorSlotReihe(
        slots={4: StundenSlot(30.0, 10), **{h: StundenSlot(2.0, 1) for h in range(5, 24)}},
        anker_start_ts=datetime(2026, 5, 14, 17).timestamp(),
    )
