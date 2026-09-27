"""N-567 — ein Nachtrag, den nur das Deckel-Fenster durchlässt, wird benannt (nicht verworfen).

Seit dem Deckel-Fenster (Vorlage Zählerlücken §10 Nachträge II) prüft der Deckel eine Menge gegen
die Zeit seit der letzten Änderung des Standes: der Lab-Fall 24.05.2026 (SMA-Zähler 13–15 Uhr still,
dann +37 kWh PV und +33 kWh Einspeisung) bleibt Menge — wie in HA. Dieselbe Regel lässt einen Sprung
nach einer Nacht mit echten Nullen durch, und der wäre nirgends sichtbar (vorher stand er bei
Fenster n in `verworfen`). Fable-Nachmessung des Lücken-Baus, Punkt 4d.

Jetzt merkt sich die Tagestabelle je Achse `nachtrag` (Menge über Schwelle × n, die nur dank des
Fensters passiert ist), die Tageszeile trägt sie (`TagesZusammenfassung.nachtrag`), der Monatswert
nennt `nachtrag_kwh`, und der Daten-Checker zeigt die Tage als INFO mit dem Satz „eedc folgt hier
HA: die Menge stand in HA in derselben Stunde". **Kein Verwerfen, keine Anzeigeregel.**

Schwesterdateien: test_zaehlerluecken_deckel_fenster.py (die Fenster-Regel selbst),
test_zaehlerluecken_tagesregel.py (Aufbau `aggregate_day` über die LTS).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select, text

from backend.models import Anlage, Investition
from backend.models.tages_energie_profil import TagesZusammenfassung
from backend.services.energie_profil.source import Source
from backend.tests import ha_lts_helfer
from backend.tests.test_ha_lts_monatswerte_lookup import (
    _make_service_with_mock_db, _seed_row, _seed_sensor,
)
from backend.tests.test_zaehlerluecken_lts_tabelle import (  # noqa: F401  (Fixture berlin)
    BIS, VON, _basis_anlage, _reihe, _svc_sql, _tabelle, berlin,
)
from backend.tests.test_zaehlerluecken_tagesregel import _quellen, _s, _tv

TAG = date(2026, 5, 15)        # Tag der `_basis_anlage`-Reihen (VON 14.05. 12:00 … BIS 15.05. 22:00)


def _eingefroren(normal: float, nachtrag: float):
    """Lab-24.05.-Form: 13–15 Uhr steht der Zähler, um 16 Uhr kommt `nachtrag`."""
    def f(t: datetime) -> float:
        if t.date() != TAG:
            return normal if 8 <= t.hour <= 17 else 0.0
        return {13: 0.0, 14: 0.0, 15: 0.0, 16: nachtrag}.get(t.hour, normal if 8 <= t.hour <= 17 else 0.0)
    return f


# ── Tagestabelle ────────────────────────────────────────────────────────────

async def test_24_05_form_nachtrag_pv_37_einspeisung_33_nichts_verworfen():
    zeilen, mapping, invs = _basis_anlage()
    zeilen["sensor.pv"] = _reihe(VON, BIS, 1000.0, _eingefroren(2.0, 37.0))
    zeilen["sensor.einsp"] = _reihe(VON, BIS, 500.0, _eingefroren(1.0, 33.0))
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs, kwp=10.0)      # Schwelle 15 kWh/h
    assert tab.nachtrag == {"pv": 37.0, "einspeisung": 33.0}
    assert tab.verworfen == {}
    # Benannt, nicht abgezogen: die Menge steht in der Nachtragsstunde wie in HA.
    assert max(z["pv"] or 0 for z in tab.stunden.values()) == 37.0


async def test_tag_ohne_nullzeilen_kein_nachtrag():
    zeilen, mapping, invs = _basis_anlage()
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs, kwp=10.0)
    assert tab.nachtrag == {} and tab.verworfen == {}


async def test_buendel_ueber_eine_luecke_ist_kein_nachtrag():
    """R2-Bündel (fehlende HA-Zeilen, n = 3): das Fenster ist n — kein Nachtrag."""
    ohne = {datetime(2026, 5, 15, h) for h in (9, 10)}
    zeilen, mapping, invs = _basis_anlage()
    zeilen["sensor.pv"] = _reihe(VON, BIS, 1000.0, lambda t: 13.0 if 8 <= t.hour <= 10 else 0.0, ohne)
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs, kwp=10.0)
    assert tab.nachtrag == {} and tab.verworfen == {}


async def test_nachtrag_unter_schwelle_mal_n_ist_kein_nachtrag():
    """Nach Nullstunden, aber nicht mehr als eine Stunde erzeugen kann: nichts zu benennen."""
    zeilen, mapping, invs = _basis_anlage()
    zeilen["sensor.pv"] = _reihe(VON, BIS, 1000.0, _eingefroren(2.0, 14.0))
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs, kwp=10.0)
    assert tab.nachtrag == {}


async def test_sprung_ueber_dem_fenster_bleibt_verworfen_und_ist_kein_nachtrag():
    zeilen, mapping, invs = _basis_anlage()
    zeilen["sensor.pv"] = _reihe(VON, BIS, 1000.0, _eingefroren(2.0, 90.0))   # 90 > 15 × 4
    tab = await _tabelle(_svc_sql(zeilen), mapping, invs, kwp=10.0)
    assert tab.verworfen == {"pv": 90.0}
    assert tab.nachtrag == {}


# ── Monat (get_sensor_monatswert) ───────────────────────────────────────────

def _monat_24_05(nachtrag: float):
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.sma", "kWh")
    s = 19383.0
    _seed_row(svc, mid, datetime(2026, 4, 30, 23, 0), sum_val=s)
    for h, d in ((11, 7.0), (12, 8.0), (13, 0.0), (14, 0.0), (15, 0.0), (16, nachtrag), (17, 7.0)):
        s += d
        _seed_row(svc, mid, datetime(2026, 5, 24, h, 0), sum_val=s)
    return svc


@pytest.mark.parametrize("deckel, erwartet", [(18.48, 37.0), (None, 0.0)])
def test_monat_nachtrag_kwh(deckel, erwartet):
    svc = _monat_24_05(37.0)
    with svc._engine.connect() as conn:
        meta = svc.get_metadata(conn, "sensor.sma")
        w = svc.get_sensor_monatswert(conn, meta, "sensor.sma", 2026, 5, deckel_kwh_je_stunde=deckel)
    assert w.nachtrag_kwh == erwartet
    assert w.verworfen_kwh == 0.0
    assert w.differenz == 59.0                        # der Nachtrag ZÄHLT (7 + 8 + 37 + 7)


def test_monat_ohne_nullstunden_kein_nachtrag():
    svc = _make_service_with_mock_db()
    mid = _seed_sensor(svc, "sensor.sma", "kWh")
    s = 100.0
    _seed_row(svc, mid, datetime(2026, 4, 30, 23, 0), sum_val=s)
    for h in range(8, 18):
        s += 5.0
        _seed_row(svc, mid, datetime(2026, 5, 24, h, 0), sum_val=s)
    with svc._engine.connect() as conn:
        meta = svc.get_metadata(conn, "sensor.sma")
        w = svc.get_sensor_monatswert(conn, meta, "sensor.sma", 2026, 5, deckel_kwh_je_stunde=18.48)
    assert (w.nachtrag_kwh, w.verworfen_kwh, w.differenz) == (0.0, 0.0, 50.0)


# ── Tageszeile, Tagessicht und Daten-Checker (aggregate_day über die LTS) ───

D_MINUS_1 = date(2026, 5, 14)
D = date(2026, 5, 15)


def _svc_eingefroren():
    """PV/Einspeisung/Netz wie `test_zaehlerluecken_tagesregel._mameier_svc`, am 15.05. aber
    13–15 Uhr eingefroren und um 16 Uhr der Nachtrag (+37 PV, +33 Einspeisung)."""
    svc = ha_lts_helfer.mach_service(thread_sicher=True)
    reihen = {"sensor.pv": [], "sensor.einsp": [], "sensor.netz": []}
    t = datetime(2026, 5, 12, 0)
    w = {"sensor.pv": 1000.0, "sensor.einsp": 500.0, "sensor.netz": 800.0}
    while t <= datetime(2026, 5, 16, 22):
        for sid in reihen:
            reihen[sid].append((t.timestamp(), round(w[sid], 3)))
        tag = 8 <= t.hour <= 17
        pv, einsp = (2.0, 1.0) if tag else (0.0, 0.0)
        if t.date() == D and 13 <= t.hour <= 15:
            pv, einsp = 0.0, 0.0
        if t.date() == D and t.hour == 16:
            pv, einsp = 37.0, 33.0
        w["sensor.pv"] += pv
        w["sensor.einsp"] += einsp
        w["sensor.netz"] += 0.0 if tag else 0.4
        t += timedelta(hours=1)
    for sid, zeilen in reihen.items():
        mid = ha_lts_helfer.sensor(svc, sid, "kWh", has_sum=True, has_mean=False)
        with svc._engine.begin() as conn:
            for ts, wert in zeilen:
                conn.execute(text("INSERT INTO statistics (metadata_id, start_ts, state, sum) "
                                  "VALUES (:m, :t, :w, :w)"), {"m": mid, "t": ts, "w": wert})
    return svc


async def _anlage(db):
    anlage = Anlage(anlagenname="N567", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1),
                    sensor_mapping={"basis": {"einspeisung": _s("sensor.einsp"),
                                              "netzbezug": _s("sensor.netz")}, "investitionen": {}})
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


async def _laufe(db, anlage):
    from backend.services.energie_profil.aggregator import aggregate_day
    with _quellen(_svc_eingefroren()):
        for tag in (D_MINUS_1, D):
            await aggregate_day(anlage, tag, db, source=Source.MANUAL_REPAIR,
                                prefetched_tagesverlauf=_tv())
            await db.commit()


@pytest.mark.asyncio
async def test_tageszeile_traegt_nachtrag_und_checker_nennt_den_tag(db):
    from backend.services.daten_checker import DatenChecker
    from backend.services.energie_profil.tage_werte import baue_tage_werte

    anlage = await _anlage(db)
    await _laufe(db, anlage)

    tz = {t.datum: t for t in (await db.execute(
        select(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == anlage.id))).scalars()}
    assert tz[D].nachtrag == {"pv": 37.0, "einspeisung": 33.0}
    assert tz[D].verworfen == {}                          # nichts verworfen — wie HA
    assert tz[D_MINUS_1].nachtrag is None                 # Tag ohne Nullzeilen ⇒ nichts
    roh = (await db.execute(text(
        "SELECT nachtrag FROM tages_zusammenfassung WHERE anlage_id = :a AND datum = :d"),
        {"a": anlage.id, "d": D_MINUS_1.isoformat()})).scalar_one()
    assert roh is None                                    # echtes SQL-NULL
    assert "nachtrag" not in (tz[D].source_provenance or {})   # Markierung, keine Herkunft

    zeilen = {z.datum: z for z in await baue_tage_werte(db, anlage, D_MINUS_1, D)}
    assert zeilen[D].nachtrag == {"pv": 37.0, "einspeisung": 33.0}
    assert zeilen[D_MINUS_1].nachtrag is None

    (e,) = await DatenChecker(db)._check_nachtrag_nach_eingefrorenem_zaehler(anlage)
    assert e.schwere.value == "info"
    assert "1 Tag(e)" in e.meldung and D.isoformat() in e.meldung
    assert f"{D.isoformat()}: Einspeisung 33,0 kWh, PV 37,0 kWh" in e.details
    # LTS-Herkunft ⇒ der HA-Satz, nicht der Satz für Zählerstände.
    assert "Aus der HA-Langzeitstatistik gerechnet" in e.details
    assert "eedc folgt hier Home Assistant: die Menge stand in HA in derselben Stunde" in e.details
    assert "in der der Zähler sie gemeldet hat" not in e.details
    assert e.action_kind is None                          # nur benennen, kein Knopf
    assert D_MINUS_1.isoformat() not in e.details


@pytest.mark.asyncio
async def test_checker_still_ohne_nachtrag(db):
    from backend.services.daten_checker import DatenChecker
    a = Anlage(anlagenname="still", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=D, verworfen={}, nachtrag=None))
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=D_MINUS_1, verworfen={"pv": 90.0}))
    await db.commit()
    assert await DatenChecker(db)._check_nachtrag_nach_eingefrorenem_zaehler(a) == []


@pytest.mark.asyncio
async def test_checker_zehn_tage_und_rest_neueste_zuerst(db):
    from backend.services.daten_checker import DatenChecker
    a = Anlage(anlagenname="viele", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    for i in range(12):
        db.add(TagesZusammenfassung(anlage_id=a.id, datum=date(2026, 5, 1) + timedelta(days=i),
                                    verworfen={}, nachtrag={"pv": 20.0 + i}))
    await db.commit()
    (e,) = await DatenChecker(db)._check_nachtrag_nach_eingefrorenem_zaehler(a)
    assert "12 Tag(e)" in e.meldung
    assert e.details.index("2026-05-12") < e.details.index("2026-05-03")
    assert "2026-05-01" not in e.details and "… und 2 weitere" in e.details


def test_checker_ist_eingehaengt():
    import inspect
    from backend.services.daten_checker import DatenChecker
    assert "self._check_nachtrag_nach_eingefrorenem_zaehler(anlage)" in inspect.getsource(
        DatenChecker.check_anlage)


# ── Standalone: derselbe Nachtrag im Snapshot-/MQTT-Pfad, anderer Satz ───────

def _staende_eingefroren(tag: date) -> dict[str, list[tuple[datetime, float]]]:
    """Zählerstände (Snapshot-Konvention: Stand AM Zeitpunkt) für Vortag + Tag — am Tag
    13–15 Uhr eingefroren, um 16 Uhr +37 PV / +33 Einspeisung; nachts 0,4 kWh Bezug."""
    reihen = {"inv:{pv}:pv_erzeugung_kwh": [], "basis:einspeisung": [], "basis:netzbezug": []}
    w = {k: s for k, s in zip(reihen, (1000.0, 500.0, 800.0))}
    t = datetime.combine(tag - timedelta(days=2), datetime.min.time())
    while t <= datetime.combine(tag, datetime.min.time()) + timedelta(hours=23):
        for k in reihen:
            reihen[k].append((t, round(w[k], 3)))
        h = (t + timedelta(hours=1))          # Zuwachs der Stunde, die bei t+1 endet
        am_tag = h.date() == tag
        sonne = 8 <= h.hour <= 17
        pv, einsp = (2.0, 1.0) if sonne else (0.0, 0.0)
        if am_tag and 13 <= h.hour <= 15:
            pv, einsp = 0.0, 0.0
        if am_tag and h.hour == 16:
            pv, einsp = 37.0, 33.0
        w["inv:{pv}:pv_erzeugung_kwh"] += pv
        w["basis:einspeisung"] += einsp
        w["basis:netzbezug"] += 0.0 if sonne else 0.4
        t += timedelta(hours=1)
    return reihen


@pytest.mark.asyncio
async def test_standalone_snapshot_tageszeile_traegt_nachtrag_und_zaehler_satz(db):
    """Die Frage des Nachmessers, gemessen statt gelesen: entsteht im Snapshot-Pfad ein
    `nachtrag`? Ja — dieselbe Tagestabelle. Der Checker nennt ihn mit dem Satz für
    Zählerstände, nicht mit dem HA-Satz (Entscheid Master 26.09.)."""
    from unittest.mock import MagicMock, patch
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.daten_checker import DatenChecker
    from backend.services.energie_profil.aggregator import aggregate_day

    anlage = await _anlage(db)
    pv_id = next(iter(anlage.sensor_mapping["investitionen"]))
    for sk, staende in _staende_eingefroren(D).items():
        for ts, w in staende:
            db.add(SensorSnapshot(anlage_id=anlage.id, sensor_key=sk.format(pv=pv_id), zeitpunkt=ts,
                                  wert_kwh=w, quelle="mqtt"))
    await db.commit()

    kein_ha = MagicMock()
    kein_ha.is_available = False
    with _quellen(kein_ha), \
            patch("backend.services.snapshot.reader.get_ha_statistics_service", return_value=kein_ha):
        for tag in (D_MINUS_1, D):
            await aggregate_day(anlage, tag, db, source=Source.MANUAL_REPAIR,
                                prefetched_tagesverlauf=_tv())
            await db.commit()

    tz = {t.datum: t for t in (await db.execute(
        select(TagesZusammenfassung).where(TagesZusammenfassung.anlage_id == anlage.id))).scalars()}
    assert tz[D].nachtrag == {"pv": 37.0, "einspeisung": 33.0}
    assert tz[D].verworfen == {}
    assert tz[D_MINUS_1].nachtrag is None
    quellen = {e.get("source") for e in (tz[D].source_provenance or {}).values() if isinstance(e, dict)}
    assert "external:ha_statistics:daily" not in quellen      # wirklich ein Snapshot-Tag

    (e,) = await DatenChecker(db)._check_nachtrag_nach_eingefrorenem_zaehler(anlage)
    assert "Aus Zählerständen gerechnet" in e.details
    assert f"{D.isoformat()}: Einspeisung 33,0 kWh, PV 37,0 kWh" in e.details
    assert "Die Menge steht in der Stunde, in der der Zähler sie gemeldet hat" in e.details
    assert "stand in HA in derselben Stunde" not in e.details


@pytest.mark.asyncio
async def test_checker_gemischt_je_herkunft_ein_satz(db):
    from backend.services.daten_checker import DatenChecker
    a = Anlage(anlagenname="gemischt", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=D, verworfen={}, nachtrag={"pv": 37.0},
                                source_provenance={"ueberschuss_kwh": {"source": "external:ha_statistics:daily"}}))
    db.add(TagesZusammenfassung(anlage_id=a.id, datum=D_MINUS_1, verworfen={}, nachtrag={"pv": 20.0},
                                source_provenance={"ueberschuss_kwh": {"source": "auto:monatsabschluss"}}))
    await db.commit()
    (e,) = await DatenChecker(db)._check_nachtrag_nach_eingefrorenem_zaehler(a)
    lts_teil, zaehler_teil = e.details.split("Aus Zählerständen gerechnet")
    assert f"{D.isoformat()}: PV 37,0 kWh" in lts_teil and "stand in HA in derselben Stunde" in lts_teil
    assert f"{D_MINUS_1.isoformat()}: PV 20,0 kWh" in zaehler_teil
    assert "in der der Zähler sie gemeldet hat" in zaehler_teil
    assert "stand in HA" not in zaehler_teil
