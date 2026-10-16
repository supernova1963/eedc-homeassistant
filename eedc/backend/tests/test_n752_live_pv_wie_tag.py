"""N-752 (16.10.2026) — Live «PV heute» rechnet die PV wie Cockpit → Tag.

Bis dahin zählte Live (HA-History-Pfad ``live_history_service._pv_zaehler_kwh`` und der MQTT-Zwilling
``mqtt_energy_history_service._compute_deltas``), sobald EIN Erzeuger einen eigenen Zähler hat, nur die Einzelzähler und
ließ den Anlagenzähler «PV gesamt» liegen — der Anteil der Erzeuger ohne Zähler fehlte (Melder chuck2941, #428: 2,8 statt
11,7 kWh). Der Tag nimmt den Anlagenzähler als Gesamt und verteilt den Rest kWp-gewichtet (W2,
``pv_verteilung.loese_pv_zeitraum_auf``); Live ruft seit N-752 dieselbe Funktion (``live_pv_verteilung``).

Gemessen am HEAD 52c24a38 (Runde 3, ``p7_live_gegen_tag.py``): F03 Live 3,0 / Tag 21,0 · F04, F12 12,0 / 21,0 · F05 18,0 /
21,0 · F14 12,0 / 18,0; gleich bei F01, F02, F11. Soll hier: der Tag der PV-Matrix (``pv_achse_matrix.soll_tag``) — Summe
und Werte je Gerät. Live-Eingang: je zugeordnetem kWh-Zähler der Form ein Δ = Tagesmenge seiner Rate.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.tests import pv_achse_matrix as mx

TAG = date(2026, 6, 15)
FORMEN_MIT_LUECKE = ["F03", "F04", "F05", "F12", "F14"]
FORMEN_OHNE_LUECKE = ["F01", "F02", "F11"]


def _mengen(form) -> dict[str, float]:
    return {sid: mx.tagesmenge(fn(mx.datetime(2026, 6, 15, 12))) for sid, (fn, _o, _k) in mx._reihen(form).items()}


async def _seed(fid, tmp_path):
    form = mx.FORMEN[fid]
    engine, db = await mx._neue_db(str(tmp_path / f"{fid}.db"))
    aid, ids = await mx.seed_anlage(db, form)
    return form, engine, db, aid, ids


async def _live_ha(db, aid, form) -> dict:
    from backend.services import live_history_service as lhs

    anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    mengen = _mengen(form)

    async def hist(ids, start, end):
        h, u = {}, {}
        for i in ids:
            if i in mengen:
                h[i] = [(start, 1000.0), (end - timedelta(minutes=1), 1000.0 + mengen[i])]
                u[i] = "kWh"
        return h, u

    with patch.object(lhs, "get_history_normalized", hist):
        return await lhs.get_tages_kwh(anlage, db, 0)


async def _live_mqtt(db, aid, form, ids) -> dict:
    from backend.services.live_history_service import _lade_erzeuger
    from backend.services.mqtt_energy_history_service import _compute_deltas

    anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
    invs = (await db.execute(select(Investition).where(Investition.anlage_id == aid))).scalars().all()
    inv_types = {str(i.id): i.typ for i in invs}
    mengen = _mengen(form)
    start, end = {}, {}
    for sid, (_fn, _o, key) in mx._reihen(form).items():
        mk = "pv_gesamt_kwh" if key == "basis:pv_gesamt" else (
            f"inv/{ids[key]}/pv_erzeugung_kwh" if key in ids else None)
        if mk:
            start[mk], end[mk] = 1000.0, 1000.0 + mengen[sid]
    return _compute_deltas(end, start, inv_types, await _lade_erzeuger(anlage, db, inv_types))


@pytest.mark.parametrize("fid", FORMEN_MIT_LUECKE + FORMEN_OHNE_LUECKE)
async def test_live_ha_gleich_tag(fid, tmp_path):
    form, engine, db, aid, ids = await _seed(fid, tmp_path)
    try:
        live = await _live_ha(db, aid, form)
    finally:
        await db.close()
        await engine.dispose()
    soll = mx.soll_tag(form, TAG)
    assert live["pv"] == pytest.approx(soll.summe, abs=0.05), (fid, live["pv"], soll.summe)
    if fid in FORMEN_MIT_LUECKE:
        # Tooltips je Erzeuger: Einzelzähler und verteilter Rest wie der Tag.
        for name, kwh in soll.je_geraet.items():
            assert live[f"pv_{ids[name]}"] == pytest.approx(kwh, abs=0.05), (fid, name)


@pytest.mark.parametrize("fid", FORMEN_MIT_LUECKE + FORMEN_OHNE_LUECKE)
async def test_live_mqtt_gleich_tag(fid, tmp_path):
    form, engine, db, aid, ids = await _seed(fid, tmp_path)
    try:
        live = await _live_mqtt(db, aid, form, ids)
    finally:
        await db.close()
        await engine.dispose()
    soll = mx.soll_tag(form, TAG)
    assert live["pv"] == pytest.approx(soll.summe, abs=0.05), (fid, live["pv"], soll.summe)
    if fid in FORMEN_MIT_LUECKE:
        for name, kwh in soll.je_geraet.items():
            assert live[f"pv_{ids[name]}"] == pytest.approx(kwh, abs=0.05), (fid, name)
