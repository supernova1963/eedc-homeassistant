"""R3, Nachträge II (Vorlage §10): das Fenster des Deckels ist die Zeit seit der
letzten Änderung des Standes — nicht die Spanne n.

Lab 24.05.2026: drei SMA-Zähler stehen 13–15 Uhr still (Zeilen mit Delta 0, die
evcc-Leistung wiederholt dreimal bitgleich 10 151 W), um 16 Uhr kommt der
Nachtrag von vier Stunden, +37 kWh. Nach R2 hat die Nachtragsstunde n = 1; der
Deckel × n verwarf echte Energie, die HA zeigt (G1). Jetzt: Schwelle × Stunden
seit der letzten Zeile desselben Sensors mit Delta ≠ 0 (ab Anker, Anteil der
Nullzeilen höchstens 24 h, nie unter n). `spannen` bleibt n — die 37 kWh stehen
wie in HA in der 16-Uhr-Stunde. Gilt für Tag, Monat und Spike-Checker.

Schwesterdateien: test_zaehlerluecken_lts_tabelle.py (P7, Deckel × Spanne),
test_zaehlerluecken_n563_monatswert.py (Monatsdeckel), test_zaehlerluecken_r3_deckel_spanne.py.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from backend.core.berechnungen.spannen import deckel_fenster_je_slot, deckel_fenster_stunden
from backend.tests.test_ha_lts_monatswerte_lookup import (
    _make_service_with_mock_db, _seed_row, _seed_sensor,
)
from backend.tests.test_zaehlerluecken_lts_tabelle import (  # noqa: F401  (Fixture berlin)
    BIS, VON, _basis_anlage, _reihe, _svc_sql, _tabelle, berlin,
)

TAG = date(2026, 5, 15)


def _eingefroren(t: datetime) -> float:
    """PV wie am Lab-24.05.: 11 → +7, 12 → +8, 13–15 still, 16 → +37 (Nachtrag)."""
    if t.date() != TAG:
        return 2.0 if 8 <= t.hour <= 17 else 0.0
    return {10: 2.0, 11: 7.0, 12: 8.0, 13: 0.0, 14: 0.0, 15: 0.0, 16: 37.0, 17: 7.0}.get(t.hour, 0.0)


# ── Helfer ───────────────────────────────────────────────────────────────────

def test_fenster_nie_unter_n_und_nullanteil_bis_24():
    assert deckel_fenster_stunden(1, 4) == 4
    assert deckel_fenster_stunden(129, 129) == 129            # Bündel behält sein n
    assert deckel_fenster_stunden(1, 40) == 24                # Nullzeilen höchstens 24 h
    assert deckel_fenster_stunden(3, 0) == 3


def test_fenster_je_slot_nullzeilen_verlaengern_die_naechste_aenderung():
    slots = [(12, 8.0, 1), (13, 0.0, 1), (14, 0.0, 1), (15, 0.0, 1), (16, 37.0, 1), (17, 7.0, 1)]
    f = deckel_fenster_je_slot(slots)
    assert f[16] == 4 and f[17] == 1 and f[12] == 1
    # Nullzeile nach einer Lücke trägt n = 1 (R2), ihre reale Dauer zählt trotzdem
    assert deckel_fenster_je_slot([(5, 1.0, 1), (9, 0.0, 1), (10, 3.0, 1)])[10] == 5
    # ein Rücksprung ist eine Änderung und beendet den Lauf
    assert deckel_fenster_je_slot([(1, 0.0, 1), (2, -5.0, 1), (3, 9.0, 1)])[3] == 1


# ── Tag (lts_tagestabelle) ───────────────────────────────────────────────────

async def test_24_05_nachtrag_bleibt_menge_nichts_verworfen():
    zeilen, mapping, invs = _basis_anlage()
    zeilen["sensor.pv"] = _reihe(VON, BIS, 1000.0, _eingefroren)
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs, kwp=10.0)   # Schwelle 15 kWh/h
    assert tab.verworfen == {}
    # `_reihe`: der Zuwachs der Stunde t steht in der Zeile t+1 ⇒ Slot t+2.
    assert tab.stunden[18]["pv"] == 37.0                     # die Nachtragsstunde
    assert (tab.stunden[18]["spannen"] or {}).get("pv") is None   # n = 1, Markierung unverändert
    for h in (15, 16, 17):
        assert tab.stunden[h]["pv"] == 0.0                   # Nullzeilen bleiben Nullstunden
    assert tab.komponenten_kwh["pv_3"] == round(sum(
        (z["pv"] or 0) for z in tab.stunden.values()), 3)


async def test_gegenprobe_echter_sprung_nach_langer_luecke_bleibt_verworfen():
    """evcc_pv-Form: +31 368 über eine 129-h-Lücke — Fenster 129 × 15 = 1 935 ≪ 31 368."""
    zeilen, mapping, invs = _basis_anlage()
    luecke = {VON + timedelta(hours=i) for i in range(1, 20)}   # Zeilen 13:00…07:00 fehlen
    sprung = lambda t: 31368.0 if t == datetime(2026, 5, 15, 7) else 0.0
    zeilen["sensor.pv"] = _reihe(VON - timedelta(hours=110), BIS, 1000.0, sprung, luecke)
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs, kwp=10.0)
    assert tab.verworfen.get("pv") == 31368.0


# ── Monat (get_sensor_monatswert mit Deckel) ────────────────────────────────

def test_monat_24_05_nachtrag_zaehlt_mit_deckel():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.sma", "kWh")
    s = 19383.0
    _seed_row(svc, mid, datetime(2026, 4, 30, 23, 0), sum_val=s)
    for h, d in ((11, 7.0), (12, 8.0), (13, 0.0), (14, 0.0), (15, 0.0), (16, 37.0), (17, 7.0)):
        s += d
        _seed_row(svc, mid, datetime(2026, 5, 24, h, 0), sum_val=s)
    with svc._engine.connect() as conn:
        meta = svc.get_metadata(conn, "sensor.sma")
        w = svc.get_sensor_monatswert(conn, meta, "sensor.sma", 2026, 5, deckel_kwh_je_stunde=18.48)
    assert w.verworfen_kwh == 0.0
    assert w.differenz == 59.0                           # 7 + 8 + 0 + 0 + 0 + 37 + 7


def test_monat_gegenprobe_sprung_nach_nicht_null_bleibt_verworfen():
    """Monat 11/2025, evcc_pv-Form: 393,01 mit Deckel, der Sprung bleibt verworfen."""
    from backend.tests.test_zaehlerluecken_n563_monatswert import _evcc_pv_november
    svc = _make_service_with_mock_db()
    _evcc_pv_november(svc)
    with svc._engine.connect() as conn:
        meta = svc.get_metadata(conn, "sensor.evcc_pv")
        w = svc.get_sensor_monatswert(conn, meta, "sensor.evcc_pv", 2025, 11,
                                      deckel_kwh_je_stunde=15.0)
    assert (w.differenz, w.verworfen_kwh) == (393.01, 31368.25)


# ── Spike-Checker liest dieselbe Regel ──────────────────────────────────────

@pytest.mark.asyncio
async def test_spike_checker_nachtrag_nach_eingefrorenem_stand_ist_kein_spike(db):
    from backend.models import Anlage
    from backend.models.tages_energie_profil import TagesEnergieProfil
    from backend.services.daten_checker import DatenChecker

    a = Anlage(anlagenname="Spike", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    werte = {12: 8.0, 13: 0.0, 14: 0.0, 15: 0.0, 16: 37.0, 17: 7.0}
    for h, v in werte.items():
        db.add(TagesEnergieProfil(anlage_id=a.id, datum=TAG, stunde=h, pv_kw=v))
    tag2 = TAG + timedelta(days=1)
    for h, v in {12: 8.0, 13: 5.0, 14: 6.0, 15: 7.0, 16: 37.0}.items():   # Stand ändert sich jede Stunde
        db.add(TagesEnergieProfil(anlage_id=a.id, datum=tag2, stunde=h, pv_kw=v))
    await db.commit()
    spikes = await DatenChecker(db)._spike_tage(a, TAG, tag2, 10.0)
    assert TAG not in spikes                                  # Fenster 4 h × 15 = 60 ≥ 37
    assert spikes[tag2] == [(16, "pv_kw", 37.0)]              # Fenster 1 h × 15 = 15 < 37
