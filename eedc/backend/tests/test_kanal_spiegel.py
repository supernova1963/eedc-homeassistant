"""Proben Kanal-Spiegel (HA-Bauform E1, Auftrag Punkt 4 „Spiegel (HA)").

Gegen die HA-Langzeitstatistik im echten Recorder-Schema (``ha_lts_helfer``): Der Spiegel schreibt
je zugeordnetem Zähler die Stundenzeilen seit der letzten geschriebenen Stunde — ``sum`` und
``state`` wörtlich, ``start_ts`` wie HA, einzig die Einheit des heutigen Lesers umgerechnet.

Die Zeit steht fest (``ZEIT``) — keine Probe liest die Uhr.

Schwesterdateien: test_kanal_eigene_summe.py, test_kanal_mitschrift_betriebsart.py, test_kanal_bestand_unberuehrt.py, test_kanal_feld_deckung.py; Lesepfad des Bestands: test_ha_lts_hourly_reader.py.
"""

from __future__ import annotations

import time as _zeit
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from backend.models.investition import Investition
from backend.models.kanal import FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
from backend.services.kanal.schreiber import schreibe_spiegel
from backend.tests import factories, ha_lts_helfer

ZEIT = datetime(2026, 6, 10, 0)          # erste geschriebene Stunde beginnt hier
STUNDEN = 12


def _ts(dt: datetime) -> int:
    return int(_zeit.mktime(dt.timetuple()))


def _s(sid: str) -> dict:
    return {"strategie": "sensor", "sensor_id": sid}


def _reihe(svc, sid: str, unit: str, *, start=500.0, rate=1.25, luecken=(), stand=False, has_sum=True):
    mid = ha_lts_helfer.sensor(svc, sid, unit, has_sum=has_sum)
    wert = start
    zeilen = {}
    for h in range(-2, STUNDEN + 6):
        t = ZEIT + timedelta(hours=h)
        wert += rate
        if h in luecken:
            continue
        if stand:
            ha_lts_helfer.zeile(svc, mid, t, state=wert)
            zeilen[_ts(t)] = {"state": wert, "sum": None}
        else:
            ha_lts_helfer.zeile(svc, mid, t, state=wert - 300.0, sum_wert=wert)
            zeilen[_ts(t)] = {"state": wert - 300.0, "sum": wert}
    return zeilen


async def _anlage(db):
    a = await factories.anlage(db, sensor_mapping={
        "basis": {"einspeisung": _s("sensor.einsp"), "netzbezug": _s("sensor.netz_wh")},
        "investitionen": {},
    })
    sp = await factories.investition(db, typ="speicher", anlage_id=a.id)
    so = await factories.investition(db, typ="sonstiges", anlage_id=a.id,
                                     parameter={"kategorie": "zaehler", "zaehler_einheit": "m³"})
    m = dict(a.sensor_mapping)
    m["investitionen"] = {
        str(sp.id): {"felder": {"ladung_kwh": _s("sensor.ladung")}},
        str(so.id): {"felder": {"zaehlerstand": _s("sensor.gas")}},
    }
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    return a, sp, so


@pytest.fixture
def ha():
    svc = ha_lts_helfer.mach_service(thread_sicher=True)
    reihen = {
        "sensor.einsp": _reihe(svc, "sensor.einsp", "kWh", luecken=(4,)),
        "sensor.netz_wh": _reihe(svc, "sensor.netz_wh", "Wh", start=800_000.0, rate=900.0),
        "sensor.ladung": _reihe(svc, "sensor.ladung", "kWh", start=20.0, rate=0.5),
        "sensor.gas": _reihe(svc, "sensor.gas", "m³", start=1000.0, rate=0.3, stand=True, has_sum=False),
    }
    return svc, reihen


async def _zeilen(db, anlage_id: int, key: str) -> dict[int, KanalStatistik]:
    k = (await db.execute(select(Kanal).where(Kanal.anlage_id == anlage_id, Kanal.key == key))).scalar_one()
    rows = (await db.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id))).scalars().all()
    return {r.start_ts: r for r in rows}


async def _quellen(db, anlage_id: int, key: str) -> list[KanalQuelle]:
    k = (await db.execute(select(Kanal).where(Kanal.anlage_id == anlage_id, Kanal.key == key))).scalar_one()
    return list((await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id)
                                  .order_by(KanalQuelle.gueltig_ab))).scalars().all())


async def _laeufe(db, anlage, svc, stunden):
    """Stundenlauf :05 zu den vollen Stunden ``ZEIT + h`` (h in ``stunden``) — der Lauf zur Stunde T
    schreibt die Zeile mit ``start_ts = T − 1 h``."""
    n = 0
    for h in stunden:
        n += await schreibe_spiegel(db, anlage, ZEIT + timedelta(hours=h), ha_svc=svc)
        await db.commit()
    return n


async def test_erster_lauf_schreibt_nur_die_eben_abgeschlossene_stunde(db, ha):
    svc, reihen = ha
    a, sp, _ = await _anlage(db)
    await _laeufe(db, a, svc, [1])
    z = await _zeilen(db, a.id, "basis:einspeisung")
    assert list(z) == [_ts(ZEIT)]
    assert (z[_ts(ZEIT)].sum, z[_ts(ZEIT)].state) == (reihen["sensor.einsp"][_ts(ZEIT)]["sum"],
                                                      reihen["sensor.einsp"][_ts(ZEIT)]["state"])
    assert z[_ts(ZEIT)].familie == FAMILIE_SPIEGEL


async def test_gespiegelte_sum_und_state_sind_die_ha_zeilen_woertlich(db, ha):
    svc, reihen = ha
    a, sp, _ = await _anlage(db)
    await _laeufe(db, a, svc, [1, 3, 7, STUNDEN])
    for key, sid in (("basis:einspeisung", "sensor.einsp"), (f"inv:{sp.id}:ladung_kwh", "sensor.ladung")):
        z = await _zeilen(db, a.id, key)
        erwartet = {ts: w for ts, w in reihen[sid].items() if _ts(ZEIT) <= ts <= _ts(ZEIT + timedelta(hours=STUNDEN - 1))}
        assert set(z) == set(erwartet), key
        for ts, w in erwartet.items():
            assert (z[ts].sum, z[ts].state) == (w["sum"], w["state"]), (key, ts)


async def test_zweiter_lauf_schreibt_nichts_doppelt(db, ha):
    svc, _ = ha
    a, *_ = await _anlage(db)
    await _laeufe(db, a, svc, [1, 5])
    vorher = {k: (r.sum, r.state) for k, r in (await _zeilen(db, a.id, "basis:einspeisung")).items()}
    assert await _laeufe(db, a, svc, [5, 5]) == 0
    nachher = {k: (r.sum, r.state) for k, r in (await _zeilen(db, a.id, "basis:einspeisung")).items()}
    assert nachher == vorher
    assert len(await _quellen(db, a.id, "basis:einspeisung")) == 1


async def test_luecke_in_ha_bleibt_luecke(db, ha):
    """Stunde 4 fehlt in HA (``luecken=(4,)``): keine Zeile, keine Füllung; Stunde 5 trägt HAs Wert."""
    svc, reihen = ha
    a, *_ = await _anlage(db)
    await _laeufe(db, a, svc, [1, 8])
    z = await _zeilen(db, a.id, "basis:einspeisung")
    assert _ts(ZEIT + timedelta(hours=4)) not in z
    t5 = _ts(ZEIT + timedelta(hours=5))
    assert z[t5].sum == reihen["sensor.einsp"][t5]["sum"]


async def test_einheit_wie_der_heutige_leser_wh_nach_kwh_stand_unveraendert(db, ha):
    svc, reihen = ha
    a, _, so = await _anlage(db)
    await _laeufe(db, a, svc, [1, 3])
    netz = await _zeilen(db, a.id, "basis:netzbezug")
    for ts, r in netz.items():
        assert r.sum == pytest.approx(reihen["sensor.netz_wh"][ts]["sum"] * 0.001, abs=1e-12)
    gas = await _zeilen(db, a.id, f"inv:{so.id}:zaehlerstand")
    for ts, r in gas.items():
        assert (r.state, r.sum) == (reihen["sensor.gas"][ts]["state"], None)   # m³, nicht umgerechnet
    einheiten = {k.key: (k.art, k.einheit) for k in (await db.execute(select(Kanal))).scalars().all()}
    assert einheiten["basis:netzbezug"] == ("sum", "kWh")
    assert einheiten[f"inv:{so.id}:zaehlerstand"] == ("stand", "m³")


async def test_sensortausch_mit_offset_haelt_die_summe_stetig(db, ha):
    """Ab Stunde 6 zeigt die Zuordnung auf einen neuen Zähler mit ganz anderem Niveau. Neuer
    ``kanal_quelle``-Eintrag mit ``offset``; ``sum + offset`` läuft stetig weiter, und die erste Stunde
    des neuen Zählers trägt dessen eigenen Zuwachs (Anker = seine Zeile zur letzten Kanal-Stunde)."""
    svc, reihen = ha
    neu = _reihe(svc, "sensor.einsp_neu", "kWh", start=10.0, rate=2.0)
    a, *_ = await _anlage(db)
    await _laeufe(db, a, svc, [1, 6])
    m = dict(a.sensor_mapping)
    m["basis"] = {**m["basis"], "einspeisung": _s("sensor.einsp_neu")}
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    await _laeufe(db, a, svc, [9])

    quellen = await _quellen(db, a.id, "basis:einspeisung")
    assert [(q.statistic_id, q.familie) for q in quellen] == [("sensor.einsp", "spiegel"), ("sensor.einsp_neu", "spiegel")]
    z = await _zeilen(db, a.id, "basis:einspeisung")
    t_alt, t_neu = _ts(ZEIT + timedelta(hours=5)), _ts(ZEIT + timedelta(hours=6))
    assert quellen[1].gueltig_ab == t_neu
    assert z[t_neu].sum == neu[t_neu]["sum"]                                  # die Zeile bleibt wörtlich
    kanal_alt = z[t_alt].sum + quellen[0].offset
    kanal_neu = z[t_neu].sum + quellen[1].offset
    assert kanal_neu - kanal_alt == pytest.approx(neu[t_neu]["sum"] - neu[t_alt]["sum"])   # = 2,0
    werte = [z[t].sum + (quellen[1].offset if t >= t_neu else quellen[0].offset) for t in sorted(z)]
    assert all(b > a_ for a_, b in zip(werte, werte[1:]))


async def test_ohne_ha_schreibt_der_spiegel_nichts(db, ha):
    svc, _ = ha
    a, *_ = await _anlage(db)
    aus = type("Aus", (), {"is_available": False})()
    assert await schreibe_spiegel(db, a, ZEIT + timedelta(hours=3), ha_svc=aus) == 0
    assert (await db.execute(select(KanalStatistik))).first() is None


async def test_leistungssensor_ohne_sum_wird_nicht_gespiegelt(db, ha):
    """Wie der heutige Leser (#200): ``has_sum`` falsch und keine Energie-Einheit ⇒ kein Wert."""
    svc, _ = ha
    mid = ha_lts_helfer.sensor(svc, "sensor.watt", "W", has_sum=False)
    ha_lts_helfer.zeile(svc, mid, ZEIT, state=1234.0, mean=1200.0)
    a, sp, _ = await _anlage(db)
    m = dict(a.sensor_mapping)
    m["investitionen"][str(sp.id)]["felder"]["entladung_kwh"] = _s("sensor.watt")
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    await _laeufe(db, a, svc, [1])
    k = (await db.execute(select(Kanal).where(Kanal.key == f"inv:{sp.id}:entladung_kwh"))).scalar_one_or_none()
    zeilen = [] if k is None else (await db.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id))).all()
    assert zeilen == []


async def test_stillgelegtes_geraet_wird_nicht_gespiegelt(db, ha):
    """Dieselbe Auswahl wie der Bestand (`_build_counter_map` mit `_stillgelegte_inv_ids`, #377)."""
    from datetime import date

    svc, _ = ha
    a, sp, _ = await _anlage(db)
    inv = (await db.execute(select(Investition).where(Investition.id == sp.id))).scalar_one()
    inv.stilllegungsdatum = date(2000, 1, 1)
    await db.commit()
    await _laeufe(db, a, svc, [1])
    keys = {k.key for k in (await db.execute(select(Kanal))).scalars().all()}
    assert f"inv:{sp.id}:ladung_kwh" not in keys and "basis:einspeisung" in keys


async def test_nachholen_nach_langer_pause_findet_die_letzte_zeile(db, ha):
    """Drei Tage kein Lauf: die letzte Zeile liegt vor dem 48-Stunden-Fenster (`letzte_zeilen`
    fragt dann einzeln nach). Der nächste Lauf holt alle Stunden dazwischen, ohne Doppel und ohne
    die Erstlauf-Regel („nur die letzte Stunde") anzuwenden."""
    svc, _ = ha
    mid = ha_lts_helfer.sensor(svc, "sensor.lang", "kWh")
    werte = {}
    for h in range(0, 100):
        t = ZEIT + timedelta(hours=h)
        werte[_ts(t)] = 100.0 + h
        ha_lts_helfer.zeile(svc, mid, t, state=100.0 + h, sum_wert=100.0 + h)
    a, sp, _ = await _anlage(db)
    m = dict(a.sensor_mapping)
    m["basis"] = {**m["basis"], "einspeisung": _s("sensor.lang")}
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    await _laeufe(db, a, svc, [1, 2])
    await _laeufe(db, a, svc, [80])
    z = await _zeilen(db, a.id, "basis:einspeisung")
    assert sorted(z) == [_ts(ZEIT + timedelta(hours=h)) for h in range(0, 80)]
    assert all(z[ts].sum == werte[ts] for ts in z)


# ── Spiegel mean (Entscheid Master 05.10.: Option A) ────────────────────────


def _mean_reihe(svc, sid: str, unit: str, *, basis: float, stunden=range(-2, STUNDEN + 6)):
    mid = ha_lts_helfer.sensor(svc, sid, unit, has_sum=False)
    out = {}
    for h in stunden:
        t = ZEIT + timedelta(hours=h)
        m, lo, hi = basis + h * 0.5, basis + h * 0.5 - 1.0, basis + h * 0.5 + 2.0
        ha_lts_helfer.zeile(svc, mid, t, mean=m, min_wert=lo, max_wert=hi)
        out[_ts(t)] = (m, lo, hi)
    return out


async def _mean_anlage(db, svc):
    a, sp, so = await _anlage(db)
    wp = await factories.investition(db, typ="waermepumpe", anlage_id=a.id)
    m = dict(a.sensor_mapping)
    m["basis"] = {**m["basis"], "live": {"pv_gesamt_w": "sensor.pv_kw", "aussentemperatur_c": "sensor.aussen"},
                  "strompreis": _s("sensor.preis")}
    m["investitionen"] = {**m["investitionen"],
                          str(sp.id): {**m["investitionen"][str(sp.id)], "live": {"soc": "sensor.soc"}},
                          str(wp.id): {"live": {"betriebsmodus": "climate.wp", "warmwasser_temperatur_c": "sensor.ww_ohne_lts"}}}
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    reihen = {
        "sensor.pv_kw": _mean_reihe(svc, "sensor.pv_kw", "kW", basis=3.0),
        "sensor.aussen": _mean_reihe(svc, "sensor.aussen", "°C", basis=18.0),
        "sensor.preis": _mean_reihe(svc, "sensor.preis", "EUR/kWh", basis=0.25),
        "sensor.soc": _mean_reihe(svc, "sensor.soc", "%", basis=40.0),
    }
    return a, sp, wp, reihen


@pytest.fixture(autouse=True)
def _warnungen_frisch(monkeypatch):
    from backend.services.kanal import schreiber
    monkeypatch.setattr(schreiber, "_EINHEIT_GEWARNT", {})


async def test_mean_spiegel_ist_die_ha_zeile_woertlich_in_ha_einheit(db, ha):
    """mean/min/max wörtlich, start_ts = HAs Stundenbeginn, Kanal-Einheit = HAs Einheit — keine
    Umrechnung (kW bleibt kW, EUR/kWh bleibt EUR/kWh, °C wird NICHT durch 1000 geteilt)."""
    svc, _ = ha
    a, sp, wp, reihen = await _mean_anlage(db, svc)
    await _laeufe(db, a, svc, [1, 4])
    erwartet_einheit = {"basis:pv_gesamt_w": "kW", "basis:aussentemperatur_c": "°C",
                        "basis:strompreis": "EUR/kWh", f"inv:{sp.id}:soc": "%"}
    sid_je_key = {"basis:pv_gesamt_w": "sensor.pv_kw", "basis:aussentemperatur_c": "sensor.aussen",
                  "basis:strompreis": "sensor.preis", f"inv:{sp.id}:soc": "sensor.soc"}
    kanaele = {k.key: k for k in (await db.execute(select(Kanal))).scalars().all()}
    for key, einheit in erwartet_einheit.items():
        assert (kanaele[key].art, kanaele[key].einheit) == ("mean", einheit), key
        z = await _zeilen(db, a.id, key)
        assert sorted(z) == [_ts(ZEIT + timedelta(hours=h)) for h in range(0, 4)], key
        for ts, r in z.items():
            assert (r.mean, r.min, r.max) == reihen[sid_je_key[key]][ts], (key, ts)
            assert (r.sum, r.state, r.familie) == (None, None, FAMILIE_SPIEGEL)
    q = await _quellen(db, a.id, "basis:strompreis")
    assert [(x.familie, x.statistic_id) for x in q] == [("spiegel", "sensor.preis")]


async def test_mean_ohne_langzeitstatistik_und_betriebsart_bekommen_keine_spiegelzeile(db, ha):
    svc, _ = ha
    a, sp, wp, _ = await _mean_anlage(db, svc)
    await _laeufe(db, a, svc, [1, 3])
    keys = {k.key for k in (await db.execute(select(Kanal))).scalars().all()}
    assert f"inv:{wp.id}:warmwasser_temperatur_c" not in keys       # Sensor ohne Statistik
    assert not any(k.startswith(f"inv:{wp.id}:betriebsmodus") for k in keys)


async def test_mean_zweiter_lauf_schreibt_nichts_doppelt(db, ha):
    svc, _ = ha
    a, *_ = await _mean_anlage(db, svc)
    await _laeufe(db, a, svc, [1, 5])
    vorher = {ts: (r.mean, r.min, r.max) for ts, r in (await _zeilen(db, a.id, "basis:pv_gesamt_w")).items()}
    await _laeufe(db, a, svc, [5, 5])
    nachher = {ts: (r.mean, r.min, r.max) for ts, r in (await _zeilen(db, a.id, "basis:pv_gesamt_w")).items()}
    assert nachher == vorher and len(vorher) == 5
    assert len(await _quellen(db, a.id, "basis:pv_gesamt_w")) == 1


async def test_mean_andere_einheit_keine_zeile_und_ein_log_je_kanal_und_tag(db, ha, caplog):
    """Der neu zugeordnete Sensor meldet W, der Kanal führt kW: nicht schreiben, nicht umrechnen,
    einmal je Kanal und Tag loggen."""
    import logging

    svc, _ = ha
    _mean_reihe(svc, "sensor.pv_w", "W", basis=3000.0, stunden=range(-2, 40))
    a, *_ = await _mean_anlage(db, svc)
    await _laeufe(db, a, svc, [1, 3])
    m = dict(a.sensor_mapping)
    m["basis"] = {**m["basis"], "live": {**m["basis"]["live"], "pv_gesamt_w": "sensor.pv_w"}}
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    vorher = await _zeilen(db, a.id, "basis:pv_gesamt_w")
    with caplog.at_level(logging.WARNING, logger="backend.services.kanal.schreiber"):
        await _laeufe(db, a, svc, [5, 7, 9])                     # derselbe Tag
        tag1 = [r for r in caplog.records if "pv_gesamt_w" in r.getMessage()]
        await _laeufe(db, a, svc, [26])                          # nächster Tag
        tag2 = [r for r in caplog.records if "pv_gesamt_w" in r.getMessage()]
    assert len(tag1) == 1 and len(tag2) == 2
    assert await _zeilen(db, a.id, "basis:pv_gesamt_w") == vorher
    assert len(await _quellen(db, a.id, "basis:pv_gesamt_w")) == 1


async def test_mean_quellen_mqtt_nimmt_das_feld_aus_dem_spiegel(db, ha):
    """C2a: ``quellen`` auf MQTT ⇒ HA wird für dieses Feld nicht gelesen; auf HA ⇒ diese Entität."""
    svc, _ = ha
    _mean_reihe(svc, "sensor.soc_neu", "%", basis=70.0)
    a, sp, *_ = await _mean_anlage(db, svc)
    a.sensor_mapping = {**a.sensor_mapping, "quellen": {
        "basis_live_pv_gesamt_w": {"quelle": "mqtt_inbound_standard"},
        f"inv_live_{sp.id}_soc": {"quelle": "ha_app", "entity_id": "sensor.soc_neu"},
    }}
    flag_modified(a, "sensor_mapping")
    await db.commit()
    await _laeufe(db, a, svc, [1])
    keys = {k.key for k in (await db.execute(select(Kanal))).scalars().all()}
    assert "basis:pv_gesamt_w" not in keys
    assert [q.statistic_id for q in await _quellen(db, a.id, f"inv:{sp.id}:soc")] == ["sensor.soc_neu"]


# ── Nachmessung E1 (06.10.): Tausch auf einen fabrikneuen Sensor · Leseregel Stand ──


async def test_sensortausch_auf_fabrikneuen_sensor_zaehlt_die_erste_stunde(db, ha):
    """Der neue Zähler hat in HA keine Vorgeschichte (erste Zeile in Stunde 6, ``sum`` 2,0 · 4,0 · 6,0):
    ohne Ankerzeile beginnt seine Summe bei 0 — die 2,0 kWh der ersten Stunde zählen."""
    svc, reihen = ha
    mid = ha_lts_helfer.sensor(svc, "sensor.einsp_fabrikneu", "kWh")
    for h, w in ((6, 2.0), (7, 4.0), (8, 6.0)):
        ha_lts_helfer.zeile(svc, mid, ZEIT + timedelta(hours=h), state=w, sum_wert=w)
    a, *_ = await _anlage(db)
    await _laeufe(db, a, svc, [1, 6])                          # alt bis Stunde 5
    m = dict(a.sensor_mapping)
    m["basis"] = {**m["basis"], "einspeisung": _s("sensor.einsp_fabrikneu")}
    a.sensor_mapping = m
    flag_modified(a, "sensor_mapping")
    await db.commit()
    await _laeufe(db, a, svc, [9])
    quellen = await _quellen(db, a.id, "basis:einspeisung")
    z = await _zeilen(db, a.id, "basis:einspeisung")
    alt = z[_ts(ZEIT + timedelta(hours=5))].sum + quellen[0].offset
    neu = [z[_ts(ZEIT + timedelta(hours=h))].sum + quellen[1].offset for h in (6, 7, 8)]
    assert neu == pytest.approx([alt + 2.0, alt + 4.0, alt + 6.0])
    assert [z[_ts(ZEIT + timedelta(hours=h))].sum for h in (6, 7, 8)] == [2.0, 4.0, 6.0]   # wörtlich


async def test_sensortausch_bei_stand_rohzeilen_bleiben_und_delta_stimmt(db, ha):
    """Leseregel ``stand``: der Stand ist ``state`` roh (die Zahl auf dem Zähler, F-58); ``offset``
    überbrückt nur die Differenz über die Quellgrenze. Gaszähler 1002,4 m³ → neuer Zähler (2,4 zur
    letzten alten Stunde, dann 2,7 · 3,0): Versatz 1000,0, Δ über die Grenze 0,3."""
    svc, _ = ha
    alt_mid = ha_lts_helfer.sensor(svc, "sensor.gas_alt", "m³", has_sum=False)
    neu_mid = ha_lts_helfer.sensor(svc, "sensor.gas_neu", "m³", has_sum=False)
    for h in range(0, 6):
        ha_lts_helfer.zeile(svc, alt_mid, ZEIT + timedelta(hours=h), state=round(1000.9 + 0.3 * h, 6))
    for h, w in ((5, 2.4), (6, 2.7), (7, 3.0)):
        ha_lts_helfer.zeile(svc, neu_mid, ZEIT + timedelta(hours=h), state=w)
    a, _sp, so = await _anlage(db)
    key = f"inv:{so.id}:zaehlerstand"

    def _zuordnen(sid):
        m = dict(a.sensor_mapping)
        m["investitionen"] = {**m["investitionen"], str(so.id): {"felder": {"zaehlerstand": _s(sid)}}}
        a.sensor_mapping = m
        flag_modified(a, "sensor_mapping")

    _zuordnen("sensor.gas_alt")
    await db.commit()
    await _laeufe(db, a, svc, [1, 6])                          # alt bis Stunde 5 = 1002,4
    _zuordnen("sensor.gas_neu")
    await db.commit()
    await _laeufe(db, a, svc, [8])
    z = await _zeilen(db, a.id, key)
    quellen = await _quellen(db, a.id, key)
    t5, t6, t7 = (_ts(ZEIT + timedelta(hours=h)) for h in (5, 6, 7))
    assert (z[t5].state, z[t6].state, z[t7].state) == pytest.approx((1002.4, 2.7, 3.0))   # roh = Zähler
    assert quellen[1].offset == pytest.approx(1000.0)
    assert (z[t6].state + quellen[1].offset) - (z[t5].state + quellen[0].offset) == pytest.approx(0.3)
    assert z[t7].state - z[t6].state == pytest.approx(0.3)
