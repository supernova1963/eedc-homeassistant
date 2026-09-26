"""Zählerlücken wie HA — Schnitt 4: `lts_aggregator.lts_tagestabelle` (R2–R5, E3, E4).

Vorlage `plans/vorlage-zaehlerluecken-ha-weg.md` Fassung 7. Ein HA-Lesezugriff je
Tag trägt Stundenachsen, Spannen, verworfene Mengen und `komponenten_kwh` —
Σ Stunden == `komponenten_kwh` per Konstruktion. Proben P1, P2, P4, P6 (Slots
D/D+1), P7, P15, P16 an einer echten In-Memory-Recorder-DB (SQL) und am
WS-Transport.

Schwesterdateien: test_zaehlerluecken_slots.py (Slot-Tabelle),
test_lts_aggregator_konsistenz.py (Σ Hourly == Daily, jetzt über die Tabelle),
test_aggregator_symmetrie.py (Snapshot == LTS).
"""
from __future__ import annotations

import os
import time as _time
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import text

from backend.services.ha_statistics_ws import WsSensorMeta
from backend.services.snapshot.lts_aggregator import lts_tagestabelle
from backend.tests import ha_lts_helfer
from backend.tests.test_ha_statistics_websocket_transport import _service_mit_ws, _zeile

DATUM = date(2026, 5, 15)


@pytest.fixture(autouse=True)
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


def _inv(inv_id, typ, parameter=None, parent=None):
    from backend.models.investition import Investition
    ns = SimpleNamespace(id=inv_id, anlage_id=1, typ=typ, parameter=parameter or {},
                         parent_investition_id=parent, aktiv=True,
                         anschaffungsdatum=None, stilllegungsdatum=None)
    ns.ist_aktiv_an = Investition.ist_aktiv_an.__get__(ns)
    return ns


def _s(sid):
    return {"strategie": "sensor", "sensor_id": sid}


def _reihe(von: datetime, bis: datetime, start: float, pro_h, ohne=()):
    """[(start_ts, sum)] je Stunde; `pro_h` Zahl oder Funktion(stunde_dt) → kWh."""
    out, t, w = [], von, start
    while t <= bis:
        if t not in ohne:
            out.append((t.timestamp(), round(w, 3)))
        w += pro_h(t) if callable(pro_h) else pro_h
        t += timedelta(hours=1)
    return out


def _svc_sql(zeilen_je_sensor: dict):
    svc = ha_lts_helfer.mach_service(thread_sicher=True)
    for sid, zeilen in zeilen_je_sensor.items():
        mid = ha_lts_helfer.sensor(svc, sid, "kWh", has_sum=True, has_mean=False)
        with svc._engine.begin() as conn:
            for ts, w in zeilen:
                conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) "
                                  "VALUES (:m, :t, :w, :w)"), {"m": mid, "t": ts, "w": w})
    return svc


def _svc_ws(zeilen_je_sensor: dict):
    svc, _ = _service_mit_ws(
        {sid: WsSensorMeta("kWh", True, False) for sid in zeilen_je_sensor},
        {sid: [_zeile(ts, sum=w, state=w) for ts, w in z] for sid, z in zeilen_je_sensor.items()},
    )
    return svc


async def _tabelle(svc, mapping, invs, datum=DATUM, kwp=10.0):
    anlage = SimpleNamespace(id=1, anlagenname="T", leistung_kwp=kwp, sensor_mapping=mapping)
    with patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=svc):
        return await lts_tagestabelle(anlage, invs, datum)


def _summe(tab, feld):
    return round(sum((z.get(feld) or 0.0) for z in tab.stunden.values()), 3)


VON = datetime(2026, 5, 14, 12)
BIS = datetime(2026, 5, 15, 22)


def _basis_anlage(ohne_netz=(), ohne_pv=()):
    pv = lambda t: 2.0 if 8 <= t.hour <= 17 else 0.0          # nachts 0
    zeilen = {
        "sensor.pv": _reihe(VON, BIS, 1000.0, pv, ohne_pv),
        "sensor.einsp": _reihe(VON, BIS, 500.0, lambda t: 1.0 if 8 <= t.hour <= 17 else 0.0, ohne_netz),
        "sensor.netz": _reihe(VON, BIS, 800.0, lambda t: 0.0 if 8 <= t.hour <= 17 else 0.5, ohne_netz),
    }
    mapping = {"basis": {"einspeisung": _s("sensor.einsp"), "netzbezug": _s("sensor.netz")},
               "investitionen": {"3": {"felder": {"pv_erzeugung_kwh": _s("sensor.pv")}}}}
    invs = {"3": _inv(3, "pv-module", {"leistung_kwp": 10.0})}
    return zeilen, mapping, invs


# ── P1: Tag ohne Lücke — Stunden, Tag, Invariante; LTS == WS ─────────────────


async def test_p1_tag_ohne_luecke_lts_gleich_ws_und_invariante_exakt():
    zeilen, mapping, invs = _basis_anlage()
    a = await _tabelle(_svc_sql(zeilen), mapping, invs)
    b = await _tabelle(_svc_ws(zeilen), mapping, invs)
    assert a == b
    # Slot 0 = [Vortag 23:00, 00:00): Netz 0,5 kWh aus Zähler(0) − Zähler(−1)
    assert a.stunden[0]["netzbezug"] == 0.5
    assert all(z["spannen"] is None for z in a.stunden.values())
    assert a.verworfen == {}
    assert a.komponenten_kwh["pv_3"] == _summe(a, "pv") == 20.0
    assert a.komponenten_kwh["einspeisung"] == _summe(a, "einspeisung")
    assert a.komponenten_kwh["netzbezug"] == _summe(a, "netzbezug")


# ── P2: eine Zeile fehlt mitten am Tag ────────────────────────────────────


async def test_p2_zeile_fehlt_naechster_slot_traegt_beide_spannen_zwei():
    zeilen, mapping, invs = _basis_anlage(ohne_pv={datetime(2026, 5, 15, 11)})
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs)
    assert tab.stunden[12]["pv"] is None                     # Stand(12) fehlt
    assert tab.stunden[13]["pv"] == 4.0                       # zwei Stunden à 2 kWh
    assert tab.stunden[13]["spannen"] == {"pv": 2}
    assert tab.stunden[13]["verbrauch"] is None               # R6: pv n=2, Netz n=1
    assert tab.komponenten_kwh["pv_3"] == _summe(tab, "pv") == 20.0   # Σ = HA-Tag


# ── P4: 0-Regel je Sensor (+ R6) ─────────────────────────────────────────


async def test_p4_null_regel_je_sensor_nicht_auf_dem_netto():
    ohne = {datetime(2026, 5, 15, h) for h in range(2, 7)}     # 5 Zeilen fehlen ⇒ Slot 8 n=6
    zeilen, mapping, invs = _basis_anlage()
    zeilen["sensor.ladung"] = _reihe(VON, BIS, 50.0, lambda t: 2.0 / 6 if 2 <= t.hour <= 7 else 0.0, ohne)
    zeilen["sensor.entl"] = _reihe(VON, BIS, 70.0, lambda t: 2.0 / 6 if 2 <= t.hour <= 7 else 0.0, ohne)
    zeilen["sensor.pv0"] = zeilen.pop("sensor.pv")
    mapping["investitionen"]["3"]["felder"]["pv_erzeugung_kwh"] = _s("sensor.pv0")
    mapping["investitionen"]["5"] = {"felder": {"ladung_kwh": _s("sensor.ladung"),
                                                "entladung_kwh": _s("sensor.entl")}}
    invs["5"] = _inv(5, "speicher", {"kapazitaet_kwh": 10})
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs)
    # Zeilen 02:00–06:00 fehlen ⇒ Slot 8 (Zeile 07:00) trägt 6 reale Stunden.
    # Batterie +x/+x: beide Sensoren n = 6 — Netto 0 ist KEINE 0 (R2 vor der Verrechnung)
    assert tab.stunden[8]["spannen"] == {"batterie": 6}
    assert tab.stunden[8]["batterie_netto"] == 0.0
    assert tab.stunden[8]["verbrauch"] is None                # R6: Batterie andere Spanne


async def test_p4_null_buendel_n_eins_und_kleinstes_delta_behaelt_n():
    ohne = {datetime(2026, 5, 15, h) for h in range(1, 4)}
    zeilen, mapping, invs = _basis_anlage(ohne_pv=ohne)       # PV nachts 0 ⇒ 0-Bündel
    zeilen["sensor.netz"] = _reihe(VON, BIS, 800.0, lambda t: 0.001 if t.hour < 5 else 0.0, ohne)
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs)
    assert "pv" not in (tab.stunden[5]["spannen"] or {})      # 0 über 4 h ⇒ n = 1
    assert tab.stunden[5]["pv"] == 0.0
    assert tab.stunden[5]["spannen"]["netzbezug"] == 4       # 0,004 ≠ 0 ⇒ n bleibt


# ── P6 (Schnitt 4): Lücke über Mitternacht — D weniger, D+1 mehr, Σ = HA ───


async def test_p6_mitternachtsbuendel_d_weniger_d_plus_1_mehr_summe_wie_ha():
    von, bis = datetime(2026, 5, 13, 12), datetime(2026, 5, 16, 22)
    ohne = {datetime(2026, 5, 14, 19) + timedelta(hours=i) for i in range(6)}   # 19:00 … 00:00
    zeilen = {"sensor.netz": _reihe(von, bis, 800.0, 0.5, ohne)}
    mapping = {"basis": {"netzbezug": _s("sensor.netz")}, "investitionen": {}}
    d = await _tabelle(_svc_sql(zeilen), mapping, {}, datum=date(2026, 5, 14))
    d1 = await _tabelle(_svc_sql(zeilen), mapping, {}, datum=date(2026, 5, 15))
    assert d.komponenten_kwh["netzbezug"] == 10.0             # Slots 0..19, danach Lücke
    assert d1.komponenten_kwh["netzbezug"] == 14.0            # 3,5 (n=7) + 21 × 0,5
    # Σ(D, D+1) = HA-Änderung über beide Fenster
    ha = ([w for ts, w in zeilen["sensor.netz"] if ts == datetime(2026, 5, 15, 22).timestamp()][0]
          - [w for ts, w in zeilen["sensor.netz"] if ts == datetime(2026, 5, 13, 22).timestamp()][0])
    assert round(d.komponenten_kwh["netzbezug"] + d1.komponenten_kwh["netzbezug"], 3) == ha
    assert d1.stunden[2]["spannen"] == {"netzbezug": 7}      # 18:00 Vortag → 01:00 heute


# ── P7: Deckel × Spanne, Zählersprung, Deckel je Sensor-Slot ──────────────


async def test_p7_deckel_mal_spanne_laesst_buendel_durch():
    ohne = {datetime(2026, 5, 15, h) for h in (9, 10)}
    pv = lambda t: 13.0 if 8 <= t.hour <= 10 else 0.0          # 39 kWh über 3 h, Deckel 15/h
    zeilen, mapping, invs = _basis_anlage()
    zeilen["sensor.pv"] = _reihe(VON, BIS, 1000.0, pv, ohne)
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs)
    assert tab.stunden[12]["pv"] == 39.0 and tab.stunden[12]["spannen"]["pv"] == 3
    assert tab.verworfen == {}


async def test_p7_zaehlersprung_verworfen_komponenten_ohne_sprung_deckel_je_sensor():
    """Zwei PV-Zähler, einer springt (+31 368 wie evcc_pv_energy): nur SEIN Slot
    fällt; der andere bleibt in Stunde und Tag (Deckel je Sensor-Slot)."""
    zeilen, mapping, invs = _basis_anlage()
    sprung = lambda t: (31368.0 if t == datetime(2026, 5, 15, 10) else (1.0 if 8 <= t.hour <= 17 else 0.0))
    zeilen["sensor.pv2"] = _reihe(VON, BIS, 5000.0, sprung)
    mapping["investitionen"]["4"] = {"felder": {"pv_erzeugung_kwh": _s("sensor.pv2")}}
    invs["4"] = _inv(4, "pv-module", {"leistung_kwp": 5.0})
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs, kwp=15.0)
    assert tab.verworfen == {"pv": 31368.0}
    assert tab.stunden[11]["pv"] == 3.0                        # Nachbarstunde: beide Zähler
    assert tab.stunden[12]["pv"] == 2.0                        # pv (2) bleibt, pv2-Slot verworfen
    assert tab.komponenten_kwh["pv_4"] == 9.0                  # ohne den Sprung
    assert tab.komponenten_kwh["pv_3"] == 20.0
    assert round(tab.komponenten_kwh["pv_3"] + tab.komponenten_kwh["pv_4"], 3) == _summe(tab, "pv")


async def test_r4_negatives_delta_verworfen_mit_betrag():
    zeilen, mapping, invs = _basis_anlage()
    zeilen["sensor.netz"] = [(ts, (w if ts < datetime(2026, 5, 15, 9).timestamp() else w - 700.0))
                             for ts, w in zeilen["sensor.netz"]]
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs)
    assert tab.verworfen == {"netzbezug": 700.0}
    assert tab.stunden[10]["netzbezug"] is None
    assert tab.komponenten_kwh["netzbezug"] == _summe(tab, "netzbezug")


# ── P15: WP Betriebsart-Zähler (E3) ──────────────────────────────────────


async def test_p15_wp_betriebsart_zaehler_tragen_stunde_und_tag():
    zeilen = {"sensor.wp_heiz": _reihe(VON, BIS, 100.0, 0.4),
              "sensor.wp_kuehl": _reihe(VON, BIS, 50.0, 0.1)}
    mapping = {"basis": {}, "investitionen": {"7": {"felder": {
        "betriebsart_strom_heizen_kwh": _s("sensor.wp_heiz"),
        "betriebsart_strom_kuehlen_kwh": _s("sensor.wp_kuehl")}}}}
    invs = {"7": _inv(7, "waermepumpe", {})}
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs)
    assert tab.komponenten_kwh["waermepumpe_7"] == _summe(tab, "wp") == 12.0


# ── P16: BKW mit Kindern (E4) ──────────────────────────────────────────


async def test_p16_bkw_key_traegt_summe_des_rests():
    zeilen = {"sensor.bkw": _reihe(VON, BIS, 10.0, lambda t: 0.5 if 8 <= t.hour <= 17 else 0.0),
              "sensor.kind": _reihe(VON, BIS, 20.0, lambda t: 0.3 if 8 <= t.hour <= 17 else 0.0)}
    mapping = {"basis": {}, "investitionen": {
        "9": {"felder": {"pv_erzeugung_kwh": _s("sensor.bkw")}},
        "10": {"felder": {"pv_erzeugung_kwh": _s("sensor.kind")}}}}
    invs = {"9": _inv(9, "balkonkraftwerk", {"leistung_kwp": 0.8}),
            "10": _inv(10, "pv-module", {"leistung_kwp": 0.4}, parent=9),
            "11": _inv(11, "pv-module", {"leistung_kwp": 0.4}, parent=9)}
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs)
    assert round(tab.komponenten_kwh["bkw_9"], 3) == 2.0       # Σ Rest (0,5 − 0,3) × 10
    assert round(tab.komponenten_kwh["pv_10"], 3) == 3.0
    assert "pv_11" not in tab.komponenten_kwh                  # Kind ohne Zähler: keine Zerlegung (E4)
    assert round(tab.komponenten_kwh["bkw_9"] + tab.komponenten_kwh["pv_10"], 3) == _summe(tab, "pv") == 5.0
