"""Proben eigene Summe (HA-Bauform E1, Auftrag Punkt 4 „Eigene Summe (MQTT / ohne HA)").

**Referenzrechnung.** ``_ha_referenz`` ist eine Abschrift der Summenschleife aus HA 2026.9.2
(``sensor/recorder.py::compile_statistics`` Z. 736-822 und ``reset_detected`` Z. 475-500, Kopie unter
``plans/ha-bauform-werkzeug/ha-quelltext-2026.9.2/sensor_recorder.py``) für ``total_increasing`` ohne
``last_reset`` — Variablennamen wie dort, Zweige in derselben Reihenfolge, Logging weggelassen. Sie
ist bewusst NICHT die Produktfunktion: verglichen wird gegen HAs Text, nicht gegen sich selbst.

Die Fälle des Auftrags: Abfall unter 90 % (Reset), Dip zwischen 90 und 100 %, negativer Wert,
480 → 0 → 480 (= +480, Absicht), dazu eine feste Zufallsfolge über viele Perioden.

Schwesterdateien: test_kanal_spiegel.py, test_kanal_mitschrift_betriebsart.py, test_kanal_bestand_unberuehrt.py, test_kanal_feld_deckung.py.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pytest
from sqlalchemy import insert, select
from sqlalchemy.orm.attributes import flag_modified

from backend.core.berechnungen.ha_summe import PeriodenSumme, ha_summe_der_periode
from backend.models.kanal import FAMILIE_MITSCHRIFT, Kanal, KanalQuelle, KanalStatistik
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.services.kanal.schreiber import schreibe_eigene_summe
from backend.tests import factories


class _Fehler(Exception):
    pass


def _ha_referenz(perioden: list[list[float]]) -> list[tuple[float, float] | None]:
    """HAs Schleife über mehrere Perioden; je Periode ``(sum, state)`` oder ``None`` (keine Zeile)."""
    last_stat = None
    out = []
    for valid_float_states in perioden:
        if not valid_float_states:     # Z. 610f.: `if not valid_float_states: continue`
            out.append(None)
            continue
        old_last_reset = None
        if last_stat is None:
            new_state = old_state = None
            _sum = 0.0
        else:
            new_state = old_state = last_stat["state"]
            _sum = last_stat["sum"] or 0.0
        last_reset = None
        for fstate in valid_float_states:
            reset = False
            if old_state is None and last_reset is None:
                reset = True
            else:
                try:
                    # reset_detected(hass, entity_id, fstate, new_state, state)
                    previous_fstate = new_state
                    if previous_fstate is None:
                        detected = False
                    else:
                        if fstate < 0:
                            raise _Fehler
                        detected = fstate < 0.9 * previous_fstate
                    if old_state is None or detected:
                        reset = True
                except _Fehler:
                    continue
            if reset:
                if old_state is not None and new_state is not None:
                    _sum += new_state - old_state
                new_state = fstate
                old_last_reset = last_reset
                if old_state is not None:
                    old_state = 0.0
                else:
                    old_state = new_state
            else:
                new_state = fstate
        del old_last_reset
        if new_state is None or old_state is None:
            out.append(None)
            continue
        _sum += new_state - old_state
        last_stat = {"sum": _sum, "state": new_state}
        out.append((_sum, new_state))
    return out


def _produkt(perioden):
    vorher = None
    out = []
    for p in perioden:
        e = ha_summe_der_periode(vorher, p)
        if e is None:
            out.append(None)
            continue
        out.append((e.sum, e.state))
        vorher = e
    return out


@pytest.mark.parametrize("name,perioden,letzte_summe", [
    ("stetig", [[100.0, 101.0], [102.5], [104.0, 104.0]], 4.0),
    ("abfall_unter_90_prozent_ist_reset", [[100.0, 110.0], [5.0, 12.0]], 10.0 + 12.0),
    ("dip_zwischen_90_und_100_kein_reset", [[100.0, 110.0], [100.0], [112.0]], 12.0),
    ("negativer_wert_verworfen", [[100.0, 110.0], [-3.0, 111.0]], 11.0),
    ("480_0_480_ergibt_plus_480", [[480.0], [0.0], [480.0]], 480.0),
    ("480_0_480_in_einer_periode", [[480.0], [0.0, 480.0]], 480.0),
    ("erster_stand_ist_nullpunkt", [[500.0, 503.0]], 3.0),
    ("periode_ohne_stand_keine_zeile", [[10.0], [], [12.0]], 2.0),
])
def test_ha_regel_gegen_referenz(name, perioden, letzte_summe):
    ref = _ha_referenz(perioden)
    assert _produkt(perioden) == ref, name
    letzte = [r for r in ref if r is not None][-1]
    assert letzte[0] == pytest.approx(letzte_summe), name


def test_ha_regel_gegen_referenz_zufallsfolge():
    rnd = random.Random(20261005)
    perioden, stand = [], 1000.0
    for _ in range(400):
        p = []
        for _ in range(rnd.randint(0, 6)):
            r = rnd.random()
            if r < 0.04:
                stand = 0.0                         # Reset
            elif r < 0.07:
                stand *= rnd.uniform(0.9, 1.0)      # Dip
            elif r < 0.09:
                p.append(-rnd.uniform(1, 50))       # negativ
                continue
            elif r < 0.11:
                stand *= rnd.uniform(0.3, 0.89)     # Abfall
            else:
                stand += rnd.uniform(0, 3)
            p.append(round(stand, 3))
        perioden.append(p)
    assert _produkt(perioden) == _ha_referenz(perioden)


# ── Schreiber über MQTT-Rohstände ───────────────────────────────────────────

T0 = datetime(2026, 6, 10, 0)


async def _anlage(db, *, kwp=10.0, quellen=None):
    a = await factories.anlage(db, leistung_kwp=kwp, sensor_mapping={"basis": {}, "investitionen": {}})
    pv = await factories.investition(db, typ="pv-module", anlage_id=a.id)
    if quellen:
        a.sensor_mapping = {**a.sensor_mapping, "quellen": quellen}
        flag_modified(a, "sensor_mapping")
    await db.commit()
    return a, pv


async def _staende(db, anlage_id, key, folge: dict[int, list[float]]):
    """``{stunde: [Stand, …]}`` → ``mqtt_energy_snapshots`` im 5-Minuten-Raster ab ``T0 + h``."""
    zeilen = []
    for h, werte in folge.items():
        for i, w in enumerate(werte):
            zeilen.append({"anlage_id": anlage_id, "energy_key": key, "value_kwh": w,
                           "timestamp": T0 + timedelta(hours=h, minutes=5 * i)})
    await db.execute(insert(MqttEnergySnapshot), zeilen)
    await db.commit()


async def _lauf(db, a, stunden):
    for h in stunden:
        await schreibe_eigene_summe(db, a, T0 + timedelta(hours=h, minutes=5))
        await db.commit()


async def _kanal(db, a, key):
    k = (await db.execute(select(Kanal).where(Kanal.anlage_id == a.id, Kanal.key == key))).scalar_one_or_none()
    if k is None:
        return None, []
    rows = (await db.execute(select(KanalStatistik).where(KanalStatistik.kanal_id == k.id)
                             .order_by(KanalStatistik.start_ts))).scalars().all()
    return k, rows


async def test_eigene_summe_ist_die_referenzrechnung_je_stunde(db):
    a, _ = await _anlage(db)
    folge = {0: [480.0, 481.0], 1: [482.0, 0.0, 3.0], 2: [480.0], 3: [470.0, 475.0], 4: [-2.0, 476.0]}
    await _staende(db, a.id, "netzbezug_kwh", folge)
    await _lauf(db, a, [1, 2, 3, 4, 5])
    k, rows = await _kanal(db, a, "basis:netzbezug")
    ref = _ha_referenz([folge[h] for h in range(5)])
    assert [(r.sum, r.state) for r in rows] == ref
    assert {r.familie for r in rows} == {FAMILIE_MITSCHRIFT} and k.art == "sum"
    q = (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id))).scalars().all()
    assert [(x.familie, x.statistic_id, x.offset) for x in q] == [("mitschrift", "netzbezug_kwh", 0.0)]


async def test_480_0_480_ergibt_plus_480_im_kanal(db):
    """Die Folge des Zählersprungs (N-586): wie in HA +480 — Absicht, festgehalten."""
    a, _ = await _anlage(db, kwp=0.0)
    await _staende(db, a.id, "netzbezug_kwh", {0: [480.0], 1: [0.0], 2: [480.0]})
    await _lauf(db, a, [1, 2, 3])
    _, rows = await _kanal(db, a, "basis:netzbezug")
    assert rows[-1].sum - rows[0].sum == pytest.approx(480.0)


async def test_nachholen_ueber_eine_luecke_und_kein_doppeltes_schreiben(db):
    a, _ = await _anlage(db)
    await _staende(db, a.id, "netzbezug_kwh", {0: [10.0], 1: [11.0], 3: [15.0]})
    await _lauf(db, a, [1])           # nur Stunde 0
    await _lauf(db, a, [4, 4])        # holt 1 und 3 nach; Stunde 2 ohne Stand bleibt leer
    _, rows = await _kanal(db, a, "basis:netzbezug")
    starts = [datetime.fromtimestamp(r.start_ts) for r in rows]
    assert starts == [T0, T0 + timedelta(hours=1), T0 + timedelta(hours=3)]
    assert [r.sum for r in rows] == [0.0, 1.0, 5.0]


async def test_deckel_bleibt_schreibfilter_auf_pv_und_einspeisung(db):
    """10 kWp ⇒ Schwelle 15 kWh je Stunde (``schwelle_pv_einspeisung_stunde_kwh``). Ein Sprung von
    +250 kWh in einer Stunde wird verworfen: der Stand läuft weiter, die Summe nicht. Der Netzbezug
    hat keinen Deckel (``ACHSEN_MIT_DECKEL``) und trägt denselben Sprung."""
    a, pv = await _anlage(db, kwp=10.0)
    folge = {0: [100.0], 1: [104.0], 2: [354.0], 3: [358.0]}
    await _staende(db, a.id, f"inv/{pv.id}/pv_erzeugung_kwh", folge)
    await _staende(db, a.id, "netzbezug_kwh", folge)
    await _lauf(db, a, [1, 2, 3, 4])
    _, pvrows = await _kanal(db, a, f"inv:{pv.id}:pv_erzeugung_kwh")
    assert [r.sum for r in pvrows] == [0.0, 4.0, 4.0, 8.0]
    assert [r.state for r in pvrows] == [100.0, 104.0, 354.0, 358.0]
    _, netz = await _kanal(db, a, "basis:netzbezug")
    assert [r.sum for r in netz] == [0.0, 4.0, 254.0, 258.0]


async def test_deckel_fenster_waechst_mit_der_luecke(db):
    """Drei Stunden ohne Stand (Lücke): n = 4 ⇒ Schwelle 60 kWh; +40 kWh nach der Lücke bleiben."""
    a, pv = await _anlage(db, kwp=10.0)
    await _staende(db, a.id, f"inv/{pv.id}/pv_erzeugung_kwh", {0: [100.0], 4: [140.0]})
    await _lauf(db, a, [1, 5])
    _, rows = await _kanal(db, a, f"inv:{pv.id}:pv_erzeugung_kwh")
    assert [r.sum for r in rows] == [0.0, 40.0]


async def test_stand_feld_schreibt_den_stand_ohne_summe(db):
    a, _ = await _anlage(db)
    wb = await factories.investition(db, typ="wallbox", anlage_id=a.id)
    await db.commit()
    await _staende(db, a.id, f"inv/{wb.id}/ladevorgaenge", {0: [7.0, 8.0], 1: [-1.0], 2: [9.0]})
    await _lauf(db, a, [1, 2, 3])
    k, rows = await _kanal(db, a, f"inv:{wb.id}:ladevorgaenge")
    assert k.art == "stand"
    assert [(r.sum, r.state) for r in rows] == [(None, 8.0), (None, 9.0)]   # Stunde 1: nur negativ ⇒ keine Zeile


async def test_ha_oder_keine_zugeordnet_schreibt_mqtt_nicht(db):
    a, _ = await _anlage(db, quellen={
        "basis_energy_netzbezug_kwh": {"quelle": "ha_app", "entity_id": "sensor.netz"},
        "basis_energy_einspeisung_kwh": {"quelle": "keine"},
    })
    await _staende(db, a.id, "netzbezug_kwh", {0: [1.0]})
    await _staende(db, a.id, "einspeisung_kwh", {0: [1.0]})
    await _lauf(db, a, [1])
    assert (await db.execute(select(Kanal))).first() is None


async def test_gespiegeltes_feld_bekommt_keine_zweite_familie_aus_mqtt(db):
    a, _ = await _anlage(db)
    a.sensor_mapping = {"basis": {"netzbezug": {"strategie": "sensor", "sensor_id": "sensor.netz"}},
                        "investitionen": {}}
    flag_modified(a, "sensor_mapping")
    await db.commit()
    await _staende(db, a.id, "netzbezug_kwh", {0: [1.0]})
    await _lauf(db, a, [1])
    assert (await db.execute(select(Kanal))).first() is None


def test_periodensumme_traegt_den_vorwert_weiter():
    e = ha_summe_der_periode(PeriodenSumme(sum=10.0, state=480.0), [0.0, 480.0])
    assert (e.sum, e.state) == (490.0, 480.0)


async def test_nachholen_nach_langer_pause_setzt_die_summe_fort(db):
    """Letzte Zeile 60 Stunden zurück (vor dem 48-Stunden-Fenster): die Summe läuft vom
    gespeicherten Stand weiter, nicht ab einem neuen Nullpunkt."""
    a, _ = await _anlage(db)
    await _staende(db, a.id, "netzbezug_kwh", {0: [10.0], 1: [11.0], 61: [20.0], 62: [21.0]})
    await _lauf(db, a, [1, 2])
    await _lauf(db, a, [63])
    _, rows = await _kanal(db, a, "basis:netzbezug")
    assert [r.sum for r in rows] == [0.0, 1.0, 10.0, 11.0]
