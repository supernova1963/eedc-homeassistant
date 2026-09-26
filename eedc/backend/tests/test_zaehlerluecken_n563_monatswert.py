"""P13 — N-563 / R10: der Monatswert eines Zählers ist anker-förmig (Zählerlücken wie HA).

Vorlage Fassung 7, R10: ``get_sensor_monatswert`` rechnet **neuester** ``sum`` im
Monat − **letzter** ``sum`` vor dem Monat (``sum IS NOT NULL``, beliebig weit
zurück). Ohne Anker (die Reihe beginnt im Monat) ist der älteste ``sum`` im Monat
der Anker. Einheitenfaktor wie bisher. Beide Transporte (SQL, WebSocket ohne
neuen Befehl) rechnen dieselbe Zahl.

Bis 26.09.2026 stand dort MAX(sum) − MIN(sum) im Fenster: die Zeile
``start_ts`` = Monatsbeginn trägt schon den Stand **nach** der ersten Stunde,
der Monat verlor so jedes Mal die erste Stunde — und nach einer Recorder-Lücke
über die Monatsgrenze alles bis zur ersten Zeile.

Schwesterdateien: test_zaehlerluecken_slots.py (derselbe Anker je Stunde, R1),
test_ha_lts_monatswerte_lookup.py und test_ha_statistics_websocket_transport.py
(die Bestandsproben desselben Monatswerts, deren Helfer hier genutzt werden).
"""
from __future__ import annotations

from datetime import datetime

from backend.services.ha_statistics_ws import WsSensorMeta
from backend.tests.test_ha_lts_monatswerte_lookup import (
    _make_service_with_mock_db, _seed_row, _seed_sensor,
)
from backend.tests.test_ha_statistics_websocket_transport import (
    _monatsstunden, _service_mit_ws, _zeile,
)


def _sql_wert(svc, sid, jahr=2026, monat=6):
    with svc._engine.connect() as conn:
        meta = svc.get_metadata(conn, sid)
        return svc.get_sensor_monatswert(conn, meta, sid, jahr, monat)


# ── SQL ──────────────────────────────────────────────────────────────────────

def test_p13_erste_stunde_des_monats_zaehlt():
    """Anker 31.05. 23:00 (= Stand 01.06. 00:00) = 100; die erste Juni-Zeile
    trägt 101 ⇒ die erste Stunde (1 kWh) gehört zum Juni."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh")
    _seed_row(svc, mid, datetime(2026, 5, 31, 23, 0), sum_val=100.0)
    _seed_row(svc, mid, datetime(2026, 6, 1, 0, 0), sum_val=101.0)
    _seed_row(svc, mid, datetime(2026, 6, 30, 23, 0), sum_val=200.0)
    w = _sql_wert(svc, "sensor.pv")
    assert (w.start_wert, w.end_wert, w.differenz) == (100.0, 200.0, 100.0)  # alt: 99


def test_p13_anker_beliebig_weit_zurueck_luecke_ueber_monatsgrenze():
    """Recorder-Lücke 10.05. → 05.06.: die Energie der Lücke steht im Juni —
    wie im HA-Energie-Dashboard (R1)."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh")
    _seed_row(svc, mid, datetime(2026, 5, 10, 12, 0), sum_val=90.0)
    _seed_row(svc, mid, datetime(2026, 6, 5, 12, 0), sum_val=150.0)
    _seed_row(svc, mid, datetime(2026, 6, 30, 23, 0), sum_val=200.0)
    assert _sql_wert(svc, "sensor.pv").differenz == 110.0  # alt: 50


def test_p13_ohne_anker_ist_der_aelteste_im_monat_der_anker():
    """Die Reihe beginnt im Monat ⇒ ältester `sum` im Monat; die erste Stunde der
    Reihe fehlt einmal (wie R1)."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh")
    _seed_row(svc, mid, datetime(2026, 6, 3, 8, 0), sum_val=10.0)
    _seed_row(svc, mid, datetime(2026, 6, 30, 23, 0), sum_val=70.0)
    w = _sql_wert(svc, "sensor.pv")
    assert (w.start_wert, w.differenz) == (10.0, 60.0)


def test_p13_anker_ueberspringt_null_sum():
    """Eine Zeile vor dem Monat mit `sum` NULL ist kein Anker."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh")
    _seed_row(svc, mid, datetime(2026, 5, 31, 20, 0), sum_val=95.0)
    _seed_row(svc, mid, datetime(2026, 5, 31, 23, 0), state=5.0, sum_val=None)
    _seed_row(svc, mid, datetime(2026, 6, 30, 23, 0), sum_val=200.0)
    assert _sql_wert(svc, "sensor.pv").start_wert == 95.0


def test_p13_neuester_statt_groesster_sum():
    """Endwert ist der NEUESTE `sum` im Monat, nicht MAX (HA: Stand am Ende)."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv", "kWh")
    _seed_row(svc, mid, datetime(2026, 5, 31, 23, 0), sum_val=100.0)
    _seed_row(svc, mid, datetime(2026, 6, 15, 0, 0), sum_val=180.0)
    _seed_row(svc, mid, datetime(2026, 6, 30, 23, 0), sum_val=170.0)   # HA korrigiert nach unten
    assert _sql_wert(svc, "sensor.pv").end_wert == 170.0


def test_p13_einheit_wh_auch_am_anker():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.pv_wh", "Wh")
    _seed_row(svc, mid, datetime(2026, 5, 31, 23, 0), sum_val=1000.0)
    _seed_row(svc, mid, datetime(2026, 6, 30, 23, 0), sum_val=5000.0)
    w = _sql_wert(svc, "sensor.pv_wh")
    assert (w.start_wert, w.end_wert, w.differenz) == (1.0, 5.0, 4.0)


def test_p13_state_rueckfall_unveraendert():
    """Sensor ohne `sum`: MAX(state) − MIN(state) im Monat, kein Anker."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.z", "kWh", has_sum=False)
    _seed_row(svc, mid, datetime(2026, 5, 31, 23, 0), state=1.0, sum_val=None)
    _seed_row(svc, mid, datetime(2026, 6, 3, 0, 0), state=10.0, sum_val=None)
    _seed_row(svc, mid, datetime(2026, 6, 20, 0, 0), state=42.0, sum_val=None)
    w = _sql_wert(svc, "sensor.z")
    assert (w.start_wert, w.end_wert, w.differenz) == (10.0, 42.0, 32.0)


# ── WebSocket (kein neuer Befehl, W2) ────────────────────────────────────────

def test_p13_ws_anker_in_wachsendem_fenster():
    """Letzte Zeile 5 Tage vor dem Monat ⇒ gefunden im 8-Tage-Fenster; dieselbe
    Zahl wie der SQL-Pfad."""
    sid = "sensor.zaehler"
    zeilen = {sid: [
        _zeile(datetime(2026, 5, 20, 12).timestamp(), sum=50.0),   # älter — kein Anker
        _zeile(datetime(2026, 5, 27, 12).timestamp(), sum=90.0),   # letzter vor Juni
        _zeile(datetime(2026, 6, 5, 12).timestamp(), sum=150.0),
        _zeile(datetime(2026, 6, 30, 23).timestamp(), sum=200.0),
    ]}
    svc, fake = _service_mit_ws({sid: WsSensorMeta("kWh", True, False)}, zeilen)
    w = svc.get_monatswerte([sid], 2026, 6).sensoren[0]
    assert (w.start_wert, w.differenz) == (90.0, 110.0)
    # Fenster 1 Tag (leer), dann 8 Tage (Treffer) — kein weiterer Roundtrip.
    assert len(fake.abfragen) == 3, fake.abfragen


def test_p13_ws_ohne_anker_aeltester_im_monat():
    sid = "sensor.zaehler"
    zeilen = _monatsstunden(2026, 6, sid, startwert=1000.0, pro_stunde=0.5)
    svc, _ = _service_mit_ws({sid: WsSensorMeta("kWh", True, False)}, zeilen)
    w = svc.get_monatswerte([sid], 2026, 6).sensoren[0]
    assert w.start_wert == 1000.0
    assert w.differenz == round((len(zeilen[sid]) - 1) * 0.5, 2)


# ── Vorlage §10 (W-R10): R4 und R3 gelten auch für den Monat ─────────────────
#
# Die drei Lab-Fälle (Lab-Kopie, `sensor.evcc_*`, Anlage evcc) als Form
# nachgestellt; die echten Zahlen stehen im Baubericht (§S10, gemessen an der
# Lab-Kopie): Wallbox 11/2025 = 47,08 · evcc_pv 10/2025 = 507,52 ·
# evcc_pv 11/2025 = 393,01 mit Deckel (Sprung +31 368,25 verworfen).


def test_p13_ruecksprung_wird_verworfen_nicht_abgezogen():
    """Wallbox-Form (Lab 11/2025): Anker 1906,5; am 15.11. springt `sum` auf 0,
    danach +47,08 ⇒ 47,08, nicht −1 859,42 (R10 wörtlich)."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.wb", "kWh")
    _seed_row(svc, mid, datetime(2025, 10, 31, 20, 0), sum_val=1906.5)
    _seed_row(svc, mid, datetime(2025, 11, 15, 10, 0), sum_val=1906.5)
    _seed_row(svc, mid, datetime(2025, 11, 15, 11, 0), sum_val=0.0)      # Rücksprung
    _seed_row(svc, mid, datetime(2025, 11, 30, 23, 0), sum_val=47.08)
    w = _sql_wert(svc, "sensor.wb", 2025, 11)
    assert w.differenz == 47.08
    assert w.verworfen_kwh == 1906.5
    assert (w.start_wert, w.end_wert) == (1906.5, 47.08)


def test_p13_ruecksprung_mitten_im_monat_erhaelt_die_menge_davor():
    """evcc_pv-Form (Lab 10/2025): 507,52 vor dem Rücksprung zählen, der
    Rücksprung um 31 240,17 nicht (R10 wörtlich: −30 732,65)."""
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.evcc_pv", "kWh")
    _seed_row(svc, mid, datetime(2025, 9, 30, 23, 0), sum_val=30732.65)
    _seed_row(svc, mid, datetime(2025, 10, 31, 8, 0), sum_val=31240.17)  # +507,52
    _seed_row(svc, mid, datetime(2025, 10, 31, 9, 0), sum_val=0.0)       # −31 240,17
    w = _sql_wert(svc, "sensor.evcc_pv", 2025, 10)
    assert w.differenz == 507.52
    assert w.verworfen_kwh == 31240.17


def _evcc_pv_november(svc):
    mid = _seed_sensor(svc, "sensor.evcc_pv", "kWh")
    _seed_row(svc, mid, datetime(2025, 10, 31, 20, 0), sum_val=0.0)
    _seed_row(svc, mid, datetime(2025, 11, 6, 9, 0), sum_val=200.0)      # Bündel, n = 133
    _seed_row(svc, mid, datetime(2025, 11, 6, 10, 0), sum_val=31568.25)  # +31 368,25 in 1 h
    _seed_row(svc, mid, datetime(2025, 11, 30, 23, 0), sum_val=31761.26)


def test_p13_deckel_verwirft_den_aufwaertssprung():
    """evcc_pv-Form (Lab 11/2025) mit Deckel 15 kWh/h (10 kWp): der Sprung
    +31 368,25 in einer Stunde ist verworfen; das Bündel +200 über 133 h liegt
    unter 15 × 133 und zählt (R3 × n)."""
    svc = _make_service_with_mock_db()
    _evcc_pv_november(svc)
    with svc._engine.connect() as conn:
        meta = svc.get_metadata(conn, "sensor.evcc_pv")
        w = svc.get_sensor_monatswert(conn, meta, "sensor.evcc_pv", 2025, 11,
                                      deckel_kwh_je_stunde=15.0)
    assert w.differenz == 393.01
    assert w.verworfen_kwh == 31368.25


def test_p13_ohne_deckel_zaehlt_der_aufwaertssprung_als_menge_benannt():
    """Ohne Deckel-Parameter (Feld ohne PV/Einspeisung-Achse oder Anlage ohne
    kWp) zählt der Aufwärtssprung als Menge — benannte Grenze, wie am Tag."""
    svc = _make_service_with_mock_db()
    _evcc_pv_november(svc)
    w = _sql_wert(svc, "sensor.evcc_pv", 2025, 11)
    assert w.differenz == 31761.26
    assert w.verworfen_kwh == 0.0


def test_p13_ws_rechnet_dieselbe_regel():
    sid = "sensor.wb"
    zeilen = {sid: [
        _zeile(datetime(2025, 10, 31, 20).timestamp(), sum=1906.5),
        _zeile(datetime(2025, 11, 15, 11).timestamp(), sum=0.0),
        _zeile(datetime(2025, 11, 30, 23).timestamp(), sum=47.08),
    ]}
    svc, _ = _service_mit_ws({sid: WsSensorMeta("kWh", True, False)}, zeilen)
    w = svc.get_monatswerte([sid], 2025, 11).sensoren[0]
    assert (w.differenz, w.verworfen_kwh) == (47.08, 1906.5)
    w2 = svc.get_monatswerte([sid], 2025, 11, deckel_je_sensor={sid: 15.0}).sensoren[0]
    assert w2.differenz == 47.08                       # 47,08 über 324 h liegt unter dem Deckel


# ── Zuordnung Feld → Deckel (dieselbe wie im Tagespfad) ──────────────────────

def test_p13_deckel_nur_fuer_pv_und_einspeisung_mit_anlagen_kwp():
    from types import SimpleNamespace as NS
    from backend.services.monatswert_deckel import deckel_je_sensor

    def s(sid):
        return {"strategie": "sensor", "sensor_id": sid}

    anlage = NS(leistung_kwp=10.0, sensor_mapping={
        "basis": {"einspeisung": s("sensor.einsp"), "netzbezug": s("sensor.netz"),
                  "pv_gesamt": s("sensor.pv_ges")},
        "investitionen": {
            "1": {"felder": {"pv_erzeugung_kwh": s("sensor.pv1")}},
            "2": {"felder": {"ladung_kwh": s("sensor.wb")}},
            "3": {"felder": {"pv_erzeugung_kwh": s("sensor.bkw")}},
        }})
    invs = [NS(id=1, typ="pv-module", parameter={}), NS(id=2, typ="wallbox", parameter={}),
            NS(id=3, typ="balkonkraftwerk", parameter={})]
    assert deckel_je_sensor(anlage, invs) == {
        "sensor.einsp": 15.0, "sensor.pv_ges": 15.0, "sensor.pv1": 15.0, "sensor.bkw": 15.0,
    }
    # ohne kWp kein Deckel — wie am Tag
    assert deckel_je_sensor(NS(leistung_kwp=None, sensor_mapping=anlage.sensor_mapping), invs) == {}
