"""Zählerlücken wie HA — Schnitt 6: Tag (R7), Regelmarke (R9), R6 — von Ende zu Ende.

Vorlage `plans/vorlage-zaehlerluecken-ha-weg.md` Fassung 7. Proben:
P3 (mameier: die PV-Zeile 22:00 fehlt jede Nacht — beide Tage behalten EV,
Autarkie, Gesamtverbrauch und die Grundlast-Stunde 0, `verworfen = {}`),
P18 (der Aggregator schreibt nie NULL — auch Leistungspfad-only ⇒ `{}`),
R6-Probe (Batterie fehlt ⇒ Verbrauch gebildet; andere Spanne ⇒ `None`).

Schwesterdateien: test_tagesbilanz_pv_nicht_erfasst.py (R7 am Layer),
test_monatsauswertung_abdeckung_n92.py (R8), test_zaehlerluecken_lts_tabelle.py.
"""
from __future__ import annotations

import os
import time as _time
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select, text

from backend.core.berechnungen.spannen import verbrauch_spannen_passen
from backend.models import Anlage, Investition
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil._helpers import StrompreisStunden
from backend.services.energie_profil.source import Source
from backend.tests import ha_lts_helfer

D_MINUS_1 = date(2026, 5, 14)
D = date(2026, 5, 15)


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


def _s(sid):
    return {"strategie": "sensor", "sensor_id": sid}


def _mameier_svc():
    """PV (SMA-Wechselrichter schläft): die Zeile start_ts 22:00 fehlt jede
    Nacht, PV nachts 0. Netz/Einspeisung vollständig; nachts 0,4 kWh Bezug."""
    svc = ha_lts_helfer.mach_service(thread_sicher=True)
    reihen = {"sensor.pv": [], "sensor.einsp": [], "sensor.netz": []}
    t = datetime(2026, 5, 12, 0)
    w = {"sensor.pv": 1000.0, "sensor.einsp": 500.0, "sensor.netz": 800.0}
    while t <= datetime(2026, 5, 16, 22):
        tag = 8 <= t.hour <= 17
        if not (t.hour == 22):
            reihen["sensor.pv"].append((t.timestamp(), round(w["sensor.pv"], 3)))
        reihen["sensor.einsp"].append((t.timestamp(), round(w["sensor.einsp"], 3)))
        reihen["sensor.netz"].append((t.timestamp(), round(w["sensor.netz"], 3)))
        w["sensor.pv"] += 2.0 if tag else 0.0
        w["sensor.einsp"] += 1.0 if tag else 0.0
        w["sensor.netz"] += 0.0 if tag else 0.4
        t += timedelta(hours=1)
    for sid, zeilen in reihen.items():
        mid = ha_lts_helfer.sensor(svc, sid, "kWh", has_sum=True, has_mean=False)
        with svc._engine.begin() as conn:
            for ts, wert in zeilen:
                conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) "
                                  "VALUES (:m, :t, :w, :w)"), {"m": mid, "t": ts, "w": wert})
    return svc


def _tv():
    punkte = [{"zeit": f"{h:02d}:00", "werte": {"pv_gesamt": 0.1}} for h in range(24)]
    return {"serien": [{"key": "pv_gesamt", "kategorie": "pv", "seite": "quelle",
                        "bidirektional": False}],
            "punkte": punkte, "vortagsrand": [{"zeit": "23:00", "werte": {"pv_gesamt": 0.1}}]}


async def _anlage(db):
    anlage = Anlage(anlagenname="mameier", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1),
                    sensor_mapping={"basis": {"einspeisung": _s("sensor.einsp"),
                                              "netzbezug": _s("sensor.netz")},
                                    "investitionen": {}})
    db.add(anlage)
    await db.flush()
    inv = Investition(anlage_id=anlage.id, typ="pv-module", bezeichnung="Dach",
                      anschaffungsdatum=date(2025, 1, 1), leistung_kwp=10.0,
                      parameter={"leistung_kwp": 10.0})
    db.add(inv)
    await db.flush()
    anlage.sensor_mapping = {**anlage.sensor_mapping, "investitionen": {
        str(inv.id): {"felder": {"pv_erzeugung_kwh": _s("sensor.pv")}}}}
    await db.commit()
    return anlage


def _quellen(svc):
    from contextlib import ExitStack
    st = ExitStack()
    st.enter_context(patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service",
                           return_value=svc))
    for ziel, wert in (
        ("backend.services.energie_profil._helpers._get_wetter_ist", {}),
        ("backend.services.energie_profil._helpers._get_strompreis_stunden",
         StrompreisStunden(sensor={}, boerse={})),
        ("backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv", {}),
        ("backend.services.sensor_snapshot_service.get_hourly_counter_sum_by_feld", {}),
    ):
        st.enter_context(patch(ziel, new=AsyncMock(return_value=wert)))
    return st


async def _laufe(db, anlage, svc):
    from backend.services.energie_profil.aggregator import aggregate_day
    with _quellen(svc):
        for tag in (D_MINUS_1, D):
            await aggregate_day(anlage, tag, db, source=Source.MANUAL_REPAIR,
                                prefetched_tagesverlauf=_tv())
            await db.commit()


# ── P3: mameier ───────────────────────────────────────────────────────────


async def test_p3_mameier_beide_tage_behalten_ev_autarkie_verbrauch_und_grundlast(db):
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    anlage = await _anlage(db)
    await _laufe(db, anlage, _mameier_svc())

    tep = {(r.datum, r.stunde): r for r in (await db.execute(
        select(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == anlage.id))).scalars()}
    assert tep[(D_MINUS_1, 23)].pv_kw is None                  # Slot 23 leer …
    assert tep[(D_MINUS_1, 23)].spannen is None                # … ohne Spanne
    assert tep[(D, 0)].pv_kw == 0.0                            # 0-Bündel …
    assert tep[(D, 0)].spannen is None                         # … n = 1

    tz = {t.datum: t for t in (await db.execute(
        select(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == anlage.id))).scalars()}
    assert tz[D_MINUS_1].verworfen == {} and tz[D].verworfen == {}

    zeilen = {z.datum: z for z in await baue_tage_werte(db, anlage, D_MINUS_1, D)}
    for tag in (D_MINUS_1, D):
        z = zeilen[tag]
        assert z.eigenverbrauch is not None, tag
        assert z.autarkie is not None, tag
        assert z.gesamtverbrauch is not None, tag
        assert z.grundlast_kw is not None, tag
    assert zeilen[D].eigenverbrauch == pytest.approx(10.0)     # 20 PV − 10 Einsp
    # Grundlast D: Median der Stunden 0–4, Stunde 0 zählt mit (0,4 kW)
    assert zeilen[D].grundlast_kw == pytest.approx(0.4)


# ── P18: der neue Aggregator schreibt nie NULL ────────────────────────────


async def test_p18_leistungspfad_ohne_zaehler_schreibt_die_marke(db):
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = Anlage(anlagenname="nur Leistung", leistung_kwp=5.0, sensor_mapping={})
    db.add(anlage)
    await db.commit()
    with _quellen(ha_lts_helfer.mach_service(thread_sicher=True)):
        tz = await aggregate_day(anlage, D, db, source=Source.MANUAL_REPAIR,
                                 prefetched_tagesverlauf=_tv())
    await db.commit()
    assert tz is not None
    roh = (await db.execute(text(
        "SELECT verworfen FROM tages_zusammenfassung WHERE anlage_id = :a"), {"a": anlage.id})).scalar_one()
    assert roh == "{}"                                         # Regelmarke, nie NULL


# ── R6 ────────────────────────────────────────────────────────────────────


def test_r6_batterie_fehlt_verbrauch_gebildet_andere_spanne_none():
    assert verbrauch_spannen_passen(None, batterie_da=False) is True
    assert verbrauch_spannen_passen({"pv": 3, "netzbezug": 3, "einspeisung": 3},
                                    batterie_da=False) is True
    assert verbrauch_spannen_passen({"batterie": 6}, batterie_da=True) is False
    assert verbrauch_spannen_passen({"batterie": 6}, batterie_da=False) is True
    assert verbrauch_spannen_passen({"netzbezug": 9}, batterie_da=False) is False


# ── Grundlast-Guard (§2) ──────────────────────────────────────────────────


async def test_grundlast_laesst_die_gebuendelte_nachtzeile_aus(db):
    """Alle drei Verbrauchs-Achsen trugen dieselbe 3-h-Lücke ⇒ R6 bildet den
    Verbrauch (gleiche Spanne) — 1,2 kWh über drei Stunden sind aber keine
    „Nachtleistung" von 1,2 kW. Die Zeile fällt aus der Grundlast, ihre
    Energie bleibt im Tagesverbrauch."""
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    anlage = Anlage(anlagenname="Guard", leistung_kwp=5.0)
    db.add(anlage)
    await db.flush()
    jetzt = datetime(2026, 9, 26)
    db.add(TagesZusammenfassung(anlage_id=anlage.id, datum=D, verworfen={},
                                source_provenance={}, created_at=jetzt, updated_at=jetzt))
    for h, vb, sp in ((0, 0.4, None), (4, 1.2, {"pv": 3, "netzbezug": 3, "einspeisung": 3})):
        db.add(TagesEnergieProfil(anlage_id=anlage.id, datum=D, stunde=h, pv_kw=0.0,
                                  netzbezug_kw=vb, einspeisung_kw=0.0, verbrauch_kw=vb,
                                  spannen=sp, source_provenance={}))
    await db.commit()
    zeile = (await baue_tage_werte(db, anlage, D, D))[0]
    assert zeile.grundlast_kw == pytest.approx(0.4)             # mit der Zeile: Median 0,8
    assert zeile.gesamtverbrauch == pytest.approx(1.6)          # Energie bleibt
