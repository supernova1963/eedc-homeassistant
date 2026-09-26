"""Zählerlücken wie HA — Schnitt 4b (Vorlage §10, O1 → Option A).

Jeder Slot mit Zählerwert bekommt eine Stundenzeile, auch ohne Leistungspunkt;
sonst hält G1 (Σ Stunden = Tag) in den Zeilen nicht. Lab-Beleg: Anlage 902,
06.11.2025 — 4,0 kWh Netzbezug im Tageswert (`komponenten_kwh`), 0 in den
Stunden, weil die Leistungskurve in genau der Bündel-Stunde keinen Punkt hatte.

Schwesterdateien: test_zaehlerluecken_tagesregel.py (Harness, R7/R9 von Ende zu
Ende), test_zaehlerluecken_lts_tabelle.py (die Slot-Tabelle, aus der die Zeilen
ihre kWh nehmen).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select, text

from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil.aggregator import ergaenze_zaehlerslots
from backend.services.energie_profil.source import Source
from backend.tests import ha_lts_helfer
from backend.tests.test_zaehlerluecken_tagesregel import (  # noqa: F401  (Fixture)
    D, _anlage, _quellen, berlin,
)


def _svc_902():
    """PV läuft durch; der Netzbezug-Zähler hat eine Ein-Achsen-Lücke
    (Zeilen start_ts 00:00 … 08:00 des Tages fehlen) — Slot 10 trägt die
    Zeit seit dem Anker 23:00 des Vortags, n = 10 (Lab 06.11.2025: Slot 10 =
    4,0 kWh, n = 9 — dieselbe Form)."""
    svc = ha_lts_helfer.mach_service(thread_sicher=True)
    t = datetime(D.year, D.month, D.day) - timedelta(days=3)
    w = {"sensor.pv": 1000.0, "sensor.einsp": 500.0, "sensor.netz": 800.0}
    reihen = {k: [] for k in w}
    while t <= datetime(D.year, D.month, D.day, 23):
        luecke = t.date() == D and 0 <= t.hour <= 8
        for sid in w:
            if sid == "sensor.netz" and luecke:
                continue
            reihen[sid].append((t.timestamp(), round(w[sid], 3)))
        tag = 8 <= t.hour <= 17
        w["sensor.pv"] += 2.0 if tag else 0.0
        w["sensor.einsp"] += 1.0 if tag else 0.0
        w["sensor.netz"] += 0.0 if tag else 0.5
        t += timedelta(hours=1)
    for sid, zeilen in reihen.items():
        mid = ha_lts_helfer.sensor(svc, sid, "kWh", has_sum=True, has_mean=False)
        with svc._engine.begin() as conn:
            for ts, wert in zeilen:
                conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) "
                                  "VALUES (:m, :t, :w, :w)"), {"m": mid, "t": ts, "w": wert})
    return svc


def _tv_ohne_punkt_fuer_slot_10():
    """Leistungskurve ohne den Punkt „09:00" (deckt [09:00, 10:00) = Slot 10)."""
    punkte = [{"zeit": f"{h:02d}:00", "werte": {"pv_gesamt": 0.1}} for h in range(24) if h != 9]
    return {"serien": [{"key": "pv_gesamt", "kategorie": "pv", "seite": "quelle",
                        "bidirektional": False}],
            "punkte": punkte, "vortagsrand": [{"zeit": "23:00", "werte": {"pv_gesamt": 0.1}}]}


async def test_o1_slot_mit_zaehlerwert_ohne_leistungspunkt_bekommt_seine_zeile(db):
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = await _anlage(db)
    with _quellen(_svc_902()):
        tz = await aggregate_day(anlage, D, db, source=Source.MANUAL_REPAIR,
                                 prefetched_tagesverlauf=_tv_ohne_punkt_fuer_slot_10())
    await db.commit()

    rows = {r.stunde: r for r in (await db.execute(
        select(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == anlage.id,
                                         TagesEnergieProfil.datum == D))).scalars()}
    assert 10 in rows, "Slot 10 hat einen Zählerwert und braucht seine Zeile"
    z10 = rows[10]
    assert z10.netzbezug_kw == 4.5                   # 9 Nachtstunden × 0,5 im Bündel
    assert z10.spannen == {"netzbezug": 10}          # Anker 23:00 → 09:00
    assert z10.pv_kw == 2.0
    assert z10.komponenten is None                   # kein Leistungspunkt ⇒ keine Leistungs-Komponenten

    tz = (await db.execute(select(TagesZusammenfassung).where(
        TagesZusammenfassung.anlage_id == anlage.id, TagesZusammenfassung.datum == D))).scalar_one()
    komp = tz.komponenten_kwh or {}
    # G1 in den Zeilen: Σ Stunden = Tageswert
    assert round(sum(r.netzbezug_kw or 0 for r in rows.values()), 3) == round(komp["netzbezug"], 3)
    pv_tag = sum(v for k, v in komp.items() if k.startswith("pv_"))
    assert round(sum(r.pv_kw or 0 for r in rows.values()), 3) == round(pv_tag, 3)
    assert tz.stunden_verfuegbar == 24               # die ergänzte Zeile zählt als verarbeitet


def test_o1_ergaenzung_nur_fuer_slots_mit_zaehlerwert():
    punkte = [{"zeit": "03:00", "werte": {"x": 1.0}}]
    kwh = {
        1: {"pv": None, "netzbezug": None, "spannen": None},   # nichts gemessen
        2: {"pv": 0.0, "spannen": None},                       # gemessene 0 zählt
        3: {"pv": 1.0},                                        # hat schon einen Punkt
        5: {"netzbezug": 4.0, "spannen": {"netzbezug": 9}},
    }
    erg = ergaenze_zaehlerslots(punkte, kwh)
    assert [p["zeit"] for p in erg] == ["02:00", "03:00", "05:00"]
    assert erg[1]["werte"] == {"x": 1.0}                       # bestehender Punkt unverändert
    assert erg[0]["werte"] == {} and erg[2]["werte"] == {}
    assert ergaenze_zaehlerslots(punkte, {}) is punkte
