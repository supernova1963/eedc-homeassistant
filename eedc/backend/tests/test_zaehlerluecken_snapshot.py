"""Zählerlücken wie HA — Schnitt 5: Snapshot-/MQTT-Pfad (T3, E1, E5), Vorschau (Ü7), Fensterschalter.

Vorlage `plans/vorlage-zaehlerluecken-ha-weg.md` Fassung 7. Proben:
P14 (Tagesmengen Snapshot == LTS; Anker gestern 15:00, erster Stand heute
04:00 ⇒ Slot 4 trägt das Bündel n = 13, Slots 0–3 leer, keine Interpolation),
E1 (linear nur innen), Tagesreset (Stunde: Menge · Tag: keine Aussage),
P17 (Reaggregator-Vorschau: „neu" == Aggregator, „alt" == gespeicherte Zeile),
P19 (E5-Fensterschalter: Snapshot-Tag mit Regelmarke liest die WP-Teilmengen im
Stundenfenster).

Schwesterdateien: test_zaehlerluecken_lts_tabelle.py (HA-Pfad, dieselbe
Rechnung), test_n434_tagesfenster_betriebsart.py (Fenster der Tageszeile),
test_hourly_kategorie_symmetrie.py (Vorschau ohne Doppelmapping).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import text

from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.sensor_snapshot import SensorSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.energie_profil._provenance_helpers import seed_tz_provenance
from backend.services.snapshot.aggregator import snapshot_tagestabelle
from backend.services.snapshot.lts_aggregator import lts_tagestabelle
from backend.tests import ha_lts_helfer

DATUM = date(2026, 1, 15)
T0 = datetime.combine(DATUM, datetime.min.time())


def _inv(inv_id, typ, parameter=None):
    ns = SimpleNamespace(id=inv_id, anlage_id=1, typ=typ, parameter=parameter or {},
                         parent_investition_id=None, aktiv=True,
                         anschaffungsdatum=None, stilllegungsdatum=None)
    ns.ist_aktiv_an = Investition.ist_aktiv_an.__get__(ns)
    return ns


def _s(sid):
    return {"strategie": "sensor", "sensor_id": sid}


MAPPING = {"basis": {"netzbezug": _s("sensor.netz")},
           "investitionen": {"3": {"felder": {"pv_erzeugung_kwh": _s("sensor.pv")}}}}
INVS = {"3": _inv(3, "pv-module", {"leistung_kwp": 10.0})}
ANLAGE = SimpleNamespace(id=1, anlagenname="S", leistung_kwp=10.0, sensor_mapping=MAPPING)


def _staende(von: datetime, bis: datetime, start: float, pro_h: float, ohne=()):
    """[(zeitpunkt, stand)] je voller Stunde — Stand AM Zeitpunkt (Snapshot-Konvention)."""
    out, t, w = [], von, start
    while t <= bis:
        if t not in ohne:
            out.append((t, round(w, 3)))
        w += pro_h
        t += timedelta(hours=1)
    return out


async def _snapshot_db(db, reihen: dict[str, list[tuple[datetime, float]]]):
    for sk, staende in reihen.items():
        for ts, w in staende:
            db.add(SensorSnapshot(anlage_id=1, sensor_key=sk, zeitpunkt=ts,
                                  wert_kwh=w, quelle="ha_statistics"))
    await db.commit()


def _lts_svc(reihen_lts: dict[str, list[tuple[datetime, float]]]):
    """HA-Recorder mit denselben Ständen: Zähler(t) = sum @ start_ts = t − 1 h."""
    svc = ha_lts_helfer.mach_service(thread_sicher=True)
    for sid, staende in reihen_lts.items():
        mid = ha_lts_helfer.sensor(svc, sid, "kWh", has_sum=True, has_mean=False)
        with svc._engine.begin() as conn:
            for ts, w in staende:
                conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) "
                                  "VALUES (:m, :t, :w, :w)"),
                             {"m": mid, "t": (ts - timedelta(hours=1)).timestamp(), "w": w})
    return svc


def _ohne_ha():
    svc = MagicMock()
    svc.is_available = False
    return patch("backend.services.snapshot.reader.get_ha_statistics_service", return_value=svc)


# ── P14: Tagesmengen Snapshot == LTS, Anker vor dem Fenster ⇒ Bündel ─────────


async def test_p14_anker_gestern_15_uhr_buendel_n_13_keine_interpolation(db):
    netz = (_staende(T0 - timedelta(days=1, hours=0), T0 - timedelta(hours=9), 100.0, 1.0)   # bis gestern 15:00
            + _staende(T0 + timedelta(hours=4), T0 + timedelta(hours=23), 200.0, 1.0))       # ab heute 04:00
    pv = _staende(T0 - timedelta(days=1), T0 + timedelta(hours=23), 500.0, 0.5)
    await _snapshot_db(db, {"basis:netzbezug": netz, "inv:3:pv_erzeugung_kwh": pv})
    with _ohne_ha():
        snap = await snapshot_tagestabelle(db, ANLAGE, INVS, DATUM)

    anker = [w for ts, w in netz if ts == T0 - timedelta(hours=9)][0]
    assert all(snap.stunden[h]["netzbezug"] is None for h in range(4))   # Slots 0–3 leer
    assert snap.stunden[4]["netzbezug"] == pytest.approx(200.0 - anker)
    assert snap.stunden[4]["spannen"] == {"netzbezug": 13}
    assert snap.stunden[4]["verbrauch"] is None                           # R6

    # Dieselben Stände als HA-Langzeitstatistik ⇒ dieselben Stunden und Tageswerte
    svc = _lts_svc({"sensor.netz": netz, "sensor.pv": pv})
    with patch("backend.services.snapshot.lts_aggregator.get_ha_statistics_service", return_value=svc):
        lts = await lts_tagestabelle(ANLAGE, INVS, DATUM)
    for h in range(24):
        for achse in ("pv", "netzbezug"):
            a, b = snap.stunden[h][achse], lts.stunden[h][achse]
            assert (a is None and b is None) or a == pytest.approx(b), (h, achse, a, b)
        assert snap.stunden[h]["spannen"] == lts.stunden[h]["spannen"]
    assert snap.komponenten_kwh == pytest.approx(lts.komponenten_kwh)


async def test_e1_linear_nur_zwischen_staenden_im_fenster(db):
    netz = _staende(T0 - timedelta(hours=1), T0 + timedelta(hours=23), 100.0, 2.0,
                    ohne={T0 + timedelta(hours=h) for h in (5, 6, 7)})
    await _snapshot_db(db, {"basis:netzbezug": netz})
    with _ohne_ha():
        tab = await snapshot_tagestabelle(db, ANLAGE, INVS, DATUM)
    # innere Lücke: interpoliert, je Stunde 2,0, keine Spanne (E1 wie #145)
    assert [tab.stunden[h]["netzbezug"] for h in (5, 6, 7, 8)] == pytest.approx([2.0] * 4)
    assert all(tab.stunden[h]["spannen"] is None for h in range(24))


# ── R4 im Snapshot-Pfad: Tagesreset ist eine Menge, der Tageswert keine Aussage ──


async def test_tagesreset_stunde_menge_tag_ohne_aussage(db):
    """utility_meter mit Tages-Reset: Slot 0 (über Mitternacht) = Energie seit dem
    Reset (R4: Menge, kein Verwerfen). Der Tageswert dieses Zählers bleibt
    abgelehnt (Rücksprung-Entscheid 28.08., SOLL Wärme/Klima §3.1)."""
    staende = [(T0 - timedelta(hours=1), 30.0)] + [
        (T0 + timedelta(hours=h), 0.1 + h * 1.0) for h in range(24)
    ]
    await _snapshot_db(db, {"basis:netzbezug": staende})
    with _ohne_ha():
        tab = await snapshot_tagestabelle(db, ANLAGE, INVS, DATUM)
    assert tab.stunden[0]["netzbezug"] == pytest.approx(0.1)
    assert tab.stunden[1]["netzbezug"] == pytest.approx(1.0)
    assert tab.verworfen == {}
    assert "netzbezug" not in tab.komponenten_kwh


async def test_ruecksprung_ohne_tagesreset_verworfen(db):
    staende = _staende(T0 - timedelta(hours=1), T0 + timedelta(hours=23), 100.0, 1.0)
    staende = [(ts, (w if ts < T0 + timedelta(hours=10) else w - 50.0)) for ts, w in staende]
    await _snapshot_db(db, {"basis:netzbezug": staende})
    with _ohne_ha():
        tab = await snapshot_tagestabelle(db, ANLAGE, INVS, DATUM)
    assert tab.verworfen == {"netzbezug": pytest.approx(49.0)}
    assert tab.stunden[10]["netzbezug"] is None


# ── P17: Reaggregator-Vorschau ─────────────────────────────────────────────


async def test_p17_vorschau_neu_gleich_aggregator_alt_gleich_gespeicherte_zeile(db):
    from backend.services.snapshot.reaggregator import get_reaggregate_preview

    netz = (_staende(T0 - timedelta(days=1), T0 - timedelta(hours=9), 100.0, 1.0)
            + _staende(T0 + timedelta(hours=4), T0 + timedelta(hours=23), 200.0, 1.0))
    await _snapshot_db(db, {"basis:netzbezug": netz})
    db.add(TagesEnergieProfil(anlage_id=1, datum=DATUM, stunde=4, netzbezug_kw=0.7,
                              source_provenance={}))
    await db.commit()
    ohne = MagicMock(); ohne.is_available = False
    with _ohne_ha(), patch("backend.services.snapshot.reaggregator.get_ha_statistics_service",
                           return_value=ohne):
        prev = await get_reaggregate_preview(db, ANLAGE, INVS, DATUM)
        tab = await snapshot_tagestabelle(db, ANLAGE, INVS, DATUM)
    zeile = [z for z in prev["slot_deltas"] if z["stunde"] == 4 and z["kategorie"] == "netzbezug"][0]
    assert zeile["neu_kwh"] == pytest.approx(round(tab.stunden[4]["netzbezug"], 3))
    assert zeile["spanne_neu"] == 13
    assert zeile["alt_kwh"] == 0.7                                   # gespeicherte Stundenzeile
    assert prev["tagesumme_alt"] == {"netzbezug": 0.7}


# ── P19: E5-Fensterschalter ────────────────────────────────────────────────


async def test_p19_snapshot_tag_mit_marke_liest_teilmengen_im_stundenfenster(db):
    """Fixture wie N-434 (`test_n434_tagesfenster_betriebsart._anlage`), aber als
    **Snapshot-Tag mit Regelmarke**: `komponenten_kwh` steht seit E5 im
    Stundenfenster (s23 − s_−1), die Betriebsart-Teilmenge muss dort gelesen
    werden. Randstunde gestern 2,0 / heute 0,2 — ohne Schalter stünden 1,8 kWh
    „nicht aufgeteilt" bei einem Gerät, das nur heizt."""
    from backend.api.routes.energie_profil.views import get_tag_detail

    anlage = Anlage(anlagenname="P19", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="LW",
                      anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=15000.0,
                      parameter={"wp_art": "luft_wasser"})
    db.add(inv)
    await db.flush()
    s_m1, s_0 = 100.0, 102.0
    s_23 = s_0 + 5.0
    s_24 = s_23 + 0.2
    feld = "betriebsart_strom_heizen_kwh"
    for ts, w in ((T0 - timedelta(hours=1), s_m1), (T0, s_0),
                  (T0 + timedelta(hours=23), s_23), (T0 + timedelta(hours=24), s_24)):
        db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=f"inv:{inv.id}:{feld}",
                              zeitpunkt=ts, wert_kwh=w, quelle="mqtt"))
    anlage.sensor_mapping = {"investitionen": {str(inv.id): {"felder": {
        feld: {"strategie": "sensor", "sensor_id": "sensor.wp_heizen"}}}}}
    bezug = s_23 - s_m1
    tz = TagesZusammenfassung(anlage_id=anlage.id, datum=DATUM, verworfen={},
                              komponenten_kwh={f"waermepumpe_{inv.id}": round(bezug, 3)})
    seed_tz_provenance(tz, writer="test", source="auto:monatsabschluss")   # Snapshot-Pfad
    db.add(tz)
    await db.commit()

    r = await get_tag_detail(anlage.id, DATUM, db)
    assert r.wp_modus_strom_heizen_kwh == pytest.approx(bezug, abs=0.01)
    assert r.wp_modus_nicht_aufgeteilt_kwh == pytest.approx(0.0, abs=0.01)
