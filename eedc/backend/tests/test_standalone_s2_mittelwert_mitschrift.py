"""Standalone-Gleichstand Sitzung 2 — MQTT-Mitschrift der Mittelwerte (HA-Bauform §9, Bauplan Fassung 2, S2-1 … S2-4).

* **S2-1 Integrator + Snapshot (G3):** je Live-Zahlenkey ein `MittelFenster` im Inbound-Cache (Halteregel je Nachricht);
  der 5-Minuten-Snapshot schreibt das zeitgewichtete Mittel des Fensters mit `min`/`max`, nur bei lebender Verbindung,
  nur für die Keys aus `kanal/katalog.mittelwert_live_keys` (W · °C · %, ohne Preis); `strompreis_ct` bleibt ein
  Momentanwert nur für den Tagesverlauf (G7). Der Tagesverlauf liest benannte Keys und zeigt jetzt 5-Minuten-Mittel.
* **S2-2 Stundenschreiber `_mean_mitschrift`:** Zuordnung nach G1 (Zeilen da · nicht in `_mean_zuordnung` · `quellen`
  nicht HA/«keine» · Gerät aktiv), erster Lauf nur die abgeschlossene Stunde, längengewichtet über `ts_unix`, Stunde
  über `_stunden_start_ts` (Herbst zwei Zeilen), Kanal-Einheit = Registry-Einheit, Quelle `mitschrift`/MQTT-Schlüssel.
* **Wächter-Probe «nie zwei Familien in einem Kanal»** (`_zwei_familien`) am Ende jeder Schreib-Probe — außer beim
  ausdrücklichen Quellenwechsel HA→MQTT, wo die Familien zeitlich getrennt sein müssen (Spiegel vor `gueltig_ab`,
  Mitschrift ab `gueltig_ab`), wie bei der «Eigenen Summe».

Die Uhr steht fest (``jetzt=`` am Cache, ``zeitpunkt`` am Schreiber); `T0` ist eine volle UTC-Stunde — in den
Prozesszonen der Suite (Berlin · UTC · Auckland) auch eine volle Ortsstunde.

Schwesterdateien: test_standalone_s1_betriebsmodus_mqtt.py (Modus), test_kanal_spiegel.py (Spiegel mean),
test_kanal_eigene_summe.py (Quellenwechsel-Muster), test_n439_leistung_kuehlen_anzeige.py (Snapshot-Keys).
"""

from __future__ import annotations

import calendar
import os
import time as _zeit
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text

from backend.models.kanal import FAMILIE_MITSCHRIFT, FAMILIE_SPIEGEL, Kanal, KanalQuelle, KanalStatistik
from backend.models.mqtt_live_snapshot import MqttLiveSnapshot
from backend.services import mqtt_inbound_service as mis
from backend.services import mqtt_live_history_service as mlh
from backend.services.kanal.schreiber import (
    _stunden_start_ts,
    mittel_je_stunde,
    mqtt_live_statistic_id,
    mqtt_modus_statistic_id,
    schreibe_mean_mitschrift,
)
from backend.services.mqtt_inbound_service import MqttInboundCache
from backend.tests import factories

_STUNDE = 3600
T0 = calendar.timegm((2026, 6, 10, 8, 0, 0))


@pytest.fixture(autouse=True)
def _ohne_singleton(monkeypatch):
    monkeypatch.setattr(mis, "_mqtt_inbound_service", None)


@contextmanager
def _prozesszone(zone: str):
    alt = os.environ.get("TZ")
    os.environ["TZ"] = zone
    _zeit.tzset()
    try:
        yield
    finally:
        if alt is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = alt
        _zeit.tzset()


def _topic(anlage_id: int, inv_id: int | None, key: str) -> str:
    return (f"eedc/{anlage_id}_A/live/inv/{inv_id}_WP/{key}" if inv_id is not None
            else f"eedc/{anlage_id}_A/live/{key}")


def _fenster_lauf(ereignisse, snapshots, *, key="leistung_w", anlage_id=1, inv_id=39):
    """Nachrichten ``[(ts, payload)]`` und Snapshot-Zeitpunkte durch einen verbundenen Cache — die 5-Minuten-Zeilen
    ``[(ts, mittel, min, max)]`` des Keys (ein Snapshot im selben Augenblick wie eine Nachricht kommt nach ihr)."""
    c = MqttInboundCache()
    c.verbinden()
    alle = sorted([(t, 0, p) for t, p in ereignisse] + [(t, 1, None) for t in snapshots])
    zeilen = []
    for t, art, payload in alle:
        if art == 0:
            c.on_message(_topic(anlage_id, inv_id, key), payload, jetzt=t)
            continue
        fenster = c.mittel_abschliessen(t).get(anlage_id, {})
        werte = fenster.get("inv", {}).get(str(inv_id), {}) if inv_id is not None else fenster.get("basis", {})
        if key in werte:
            zeilen.append((int(t), *werte[key]))
    return zeilen


def _stunde(zeilen, start_ts: int):
    return {s: (m, lo, hi) for s, m, lo, hi in mittel_je_stunde(zeilen)}.get(start_ts)


async def _anlage_wp(db, *, mapping: dict | None = None, parameter: dict | None = None):
    a = await factories.anlage(db, anlagenname="Test", sensor_mapping=mapping or {})
    wp = await factories.investition(db, a.id, "waermepumpe", bezeichnung="WP",
                                     parameter=parameter or {"wp_art": "luft_wasser"})
    await db.commit()
    return a, wp


def _snap(anlage_id: int, key: str, ts: int, wert: float, lo: float | None = None,
          hi: float | None = None) -> MqttLiveSnapshot:
    return MqttLiveSnapshot(anlage_id=anlage_id, timestamp=datetime.fromtimestamp(ts), component_key=key,
                            value_w=wert, ts_unix=ts, min=lo, max=hi)


def _stunde_snaps(db, anlage_id: int, key: str, stunde_ts: int, wert: float, *, n: int = 12) -> None:
    for i in range(1, n + 1):
        db.add(_snap(anlage_id, key, stunde_ts + i * 300 - 1, wert))


async def _reihe(db, anlage_id: int, key: str) -> dict[int, tuple]:
    k = (await db.execute(select(Kanal).where(Kanal.anlage_id == anlage_id, Kanal.key == key))).scalar_one_or_none()
    if k is None:
        return {}
    return {z.start_ts: (z.mean, z.min, z.max, z.familie) for z in (await db.execute(
        select(KanalStatistik).where(KanalStatistik.kanal_id == k.id))).scalars().all()}


async def _quellen(db, anlage_id: int, key: str) -> list[tuple]:
    k = (await db.execute(select(Kanal).where(Kanal.anlage_id == anlage_id, Kanal.key == key))).scalar_one()
    return [(q.gueltig_ab, q.familie, q.statistic_id, q.offset) for q in (await db.execute(
        select(KanalQuelle).where(KanalQuelle.kanal_id == k.id).order_by(KanalQuelle.gueltig_ab))).scalars().all()]


async def _zwei_familien(db) -> list:
    """Wächter-Probe des Auftrags: ein Kanal mit Zeilen zweier Familien ⇒ Treffer."""
    return (await db.execute(text(
        "SELECT kanal_id FROM kanal_statistik GROUP BY kanal_id HAVING COUNT(DISTINCT familie) > 1"))).all()


async def _schreiben(db, a, bis_ts: int) -> int:
    n = await schreibe_mean_mitschrift(db, a, datetime.fromtimestamp(bis_ts))
    await db.commit()
    return n


# ═══ S2-1 Integrator ═════════════════════════════════════════════════════════

def _takt(halb_s: int, von: int, bis: int):
    return [(t, "2000" if i % 2 == 0 else "0") for i, t in enumerate(range(von, bis, halb_s))]


@pytest.mark.parametrize("phase", [0, 37, 90, 151, 222, 299])
def test_taktende_wp_3_3_min_stundenmittel_1000_bei_jeder_phase(phase):
    """G3: 3 min 2000 W, 3 min 0 W ⇒ jedes 5-Minuten-Fenster zwischen 800 und 1200 W (eine Punktprobe läge bei 0 oder
    2000), die Stunde 1000 W ± 5 %, gleich wo der Snapshot-Takt relativ zur Stunde liegt."""
    zeilen = _fenster_lauf(_takt(180, T0 - _STUNDE, T0 + 3 * _STUNDE),
                           [T0 - _STUNDE + phase + 300 * i for i in range(1, 37)])
    mittel, lo, hi = _stunde(zeilen, T0)
    assert mittel == pytest.approx(1000.0, rel=0.05)
    assert (lo, hi) == (0.0, 2000.0)
    in_der_stunde = [m for ts, m, _lo, _hi in zeilen if T0 <= ts < T0 + _STUNDE]
    assert len(in_der_stunde) == 12 and all(800.0 - 1e-6 <= m <= 1200.0 + 1e-6 for m in in_der_stunde)


@pytest.mark.parametrize("phase", [0, 75, 151, 299])
def test_takt_gleich_snapshot_laenge_integrator_1000_punktprobe_waere_0_oder_2000(phase):
    """Der diskriminierende Takt: 2,5 min an, 2,5 min aus (Periode = Snapshot-Fenster). Eine Punktprobe träfe in jeder
    Stunde dieselbe Phase (0 oder 2000 W); der Integrator gibt 1000 W."""
    zeilen = _fenster_lauf(_takt(150, T0 - _STUNDE, T0 + 3 * _STUNDE),
                           [T0 - _STUNDE + phase + 300 * i for i in range(1, 37)])
    assert _stunde(zeilen, T0)[0] == pytest.approx(1000.0, rel=0.05)


def test_null_watt_die_nacht_eine_nachricht_um_22_uhr_jede_stunde_null():
    """Halteregel über die Fenster hinweg: ein on-change-Publisher schickt um 22:00 einmal «0» ⇒ jede Nachtstunde 0 W,
    keine Lücke."""
    nacht = T0 - 10 * _STUNDE                        # 22:00 (UTC) des Vortags
    zeilen = _fenster_lauf([(nacht - 30 * 60, "800"), (nacht, "0")],
                           [nacht - 30 * 60 + 300 * i for i in range(1, 6 + 8 * 12 + 1)])
    stunden = {s: (m, lo, hi) for s, m, lo, hi in mittel_je_stunde(zeilen)}
    for h in range(1, 8):
        assert stunden[nacht + h * _STUNDE] == (0.0, 0.0, 0.0), h


def test_fenster_mittel_statt_momentanwert_mit_min_max():
    """Die Tagesverlauf-Kurve sieht seit S2 das Fenster-Mittel: 1000 W bis 2:30, dann 3000 W ⇒ 2000 W (bis S2: 3000)."""
    c = MqttInboundCache()
    c.verbinden()
    c.on_message(_topic(1, 39, "leistung_w"), "1000", jetzt=T0)
    c.on_message(_topic(1, 39, "leistung_w"), "3000", jetzt=T0 + 150)
    assert c.mittel_abschliessen(T0 + 300)[1]["inv"]["39"]["leistung_w"] == (2000.0, 1000.0, 3000.0)
    assert c.mittel_abschliessen(T0 + 600)[1]["inv"]["39"]["leistung_w"] == (3000.0, 3000.0, 3000.0)
    assert c.get_live_inv(1, "39") == {"leistung_w": 3000.0}, "der Momentanwert (Live) bleibt, wie er ist"


def test_konstanter_wert_kommt_woertlich_zurueck():
    c = MqttInboundCache()
    c.verbinden()
    c.on_message(_topic(1, 39, "vorlauf_temperatur_c"), "34.7", jetzt=T0 + 13)
    for t in (T0 + 300, T0 + 600, T0 + 901):
        assert c.mittel_abschliessen(t)[1]["inv"]["39"]["vorlauf_temperatur_c"] == (34.7, 34.7, 34.7)


def test_verbindungsverlust_leert_die_fenster_reconnect_beginnt_neu():
    c = MqttInboundCache()
    c.verbinden()
    c.on_message(_topic(1, None, "netzbezug_w"), "500", jetzt=T0)
    c.trennen()
    assert c.mittel_abschliessen(T0 + 300) == {}
    c.verbinden()
    assert c.mittel_abschliessen(T0 + 600) == {}, "nach dem Reconnect erst mit der nächsten Nachricht"
    c.on_message(_topic(1, None, "netzbezug_w"), "700", jetzt=T0 + 700)
    assert c.mittel_abschliessen(T0 + 900)[1]["basis"]["netzbezug_w"] == (700.0, 700.0, 700.0)


def test_zustand_und_energy_haben_kein_mittel_fenster():
    c = MqttInboundCache()
    c.verbinden()
    c.on_message(_topic(1, 39, "betriebsmodus"), "2", jetzt=T0)
    c.on_message("eedc/1_A/energy/inv/39_WP/stromverbrauch_kwh", "100", jetzt=T0)
    c.on_message(_topic(1, 39, "leistung_w"), "abc", jetzt=T0)
    assert c.mittel_abschliessen(T0 + 300) == {}


def test_mittel_zeilen_nur_mit_verbindung_nur_katalog_keys_kein_preis():
    from backend.services.kanal.katalog import mittelwert_live_keys

    c = MqttInboundCache()
    for key, wert in (("leistung_w", "900"), ("vorlauf_temperatur_c", "35"), ("fremd_w", "1"),
                      ("betriebsmodus", "1")):
        c.on_message(_topic(1, 39, key), wert, jetzt=T0)
    c.on_message(_topic(1, 40, "leistung_w"), "5", jetzt=T0)               # Gerät nicht in der DB
    c.on_message(_topic(1, None, "netzbezug_w"), "300", jetzt=T0)
    c.on_message(_topic(1, None, "strompreis_ct"), "31.5", jetzt=T0)
    geraete = {1: {"39": mittelwert_live_keys("waermepumpe", {"wp_art": "luft_wasser"})}}
    now = datetime.fromtimestamp(T0 + 300)
    assert mlh.mittel_zeilen(c, geraete, now, T0 + 300) == [], "ohne Verbindung keine Zeile"
    assert mlh.preis_zeilen(c, {1}, now, T0 + 300) == []
    c.verbunden = True                                                       # Fenster stehen noch (Probe)
    rows = mlh.mittel_zeilen(c, geraete, now, T0 + 300)
    assert {r.component_key: (r.value_w, r.min, r.max, r.ts_unix) for r in rows} == {
        "basis:netzbezug_w": (300.0, 300.0, 300.0, T0 + 300),
        "inv:39:leistung_w": (900.0, 900.0, 900.0, T0 + 300),
        "inv:39:vorlauf_temperatur_c": (35.0, 35.0, 35.0, T0 + 300),
    }
    preis = mlh.preis_zeilen(c, {1}, now, T0 + 300)
    assert [(r.component_key, r.value_w, r.min, r.max) for r in preis] == [("basis:strompreis_ct", 31.5, None, None)]
    assert mlh.mittel_zeilen(c, {2: {}}, now, T0 + 600) == [], "Anlage nicht in der DB"


@asynccontextmanager
async def _sitzung(db):
    yield db


async def test_snapshot_lauf_schreibt_mittel_mit_min_max_und_ts_unix(db, monkeypatch):
    a, wp = await _anlage_wp(db)
    cache = MqttInboundCache()
    cache.verbinden()
    t = _zeit.time()
    cache.on_message(_topic(a.id, wp.id, "leistung_w"), "1000", jetzt=t - 240)
    cache.on_message(_topic(a.id, wp.id, "leistung_w"), "3000", jetzt=t - 120)
    cache.on_message(_topic(a.id, wp.id, "vorlauf_temperatur_c"), "33.5", jetzt=t - 240)
    cache.on_message(_topic(a.id, None, "strompreis_ct"), "28", jetzt=t - 240)
    monkeypatch.setattr(mlh, "get_mqtt_inbound_service", lambda: SimpleNamespace(cache=cache))
    monkeypatch.setattr(mlh, "get_session", lambda: _sitzung(db))
    assert await mlh.snapshot_live_cache() == 3
    rows = {r.component_key: r for r in (await db.execute(select(MqttLiveSnapshot))).scalars().all()}
    assert set(rows) == {f"inv:{wp.id}:leistung_w", f"inv:{wp.id}:vorlauf_temperatur_c", "basis:strompreis_ct"}
    lw = rows[f"inv:{wp.id}:leistung_w"]
    assert lw.value_w == pytest.approx(2000.0, rel=0.02) and (lw.min, lw.max) == (1000.0, 3000.0)
    assert rows[f"inv:{wp.id}:vorlauf_temperatur_c"].value_w == 33.5
    assert all(r.ts_unix is not None for r in rows.values())


async def test_tagesverlauf_ignoriert_die_temperatur_zeile(db, monkeypatch):
    """S2-1: der Snapshot schreibt `vorlauf_temperatur_c`; der MQTT-Tagesverlauf baut seine Serien aus benannten Keys —
    mit und ohne die Temperatur-Zeile dasselbe Ergebnis."""
    from backend.services import live_tagesverlauf_service as ltv
    from backend.services import strompreis_markt_service as sms

    a, wp = await _anlage_wp(db)
    cache = MqttInboundCache()
    cache.verbinden()
    t = _zeit.time()
    cache.on_message(_topic(a.id, wp.id, "leistung_w"), "1500", jetzt=t - 200)
    cache.on_message(_topic(a.id, wp.id, "vorlauf_temperatur_c"), "35", jetzt=t - 200)
    cache.on_message(_topic(a.id, None, "netzbezug_w"), "400", jetzt=t - 200)
    monkeypatch.setattr(mlh, "get_mqtt_inbound_service", lambda: SimpleNamespace(cache=cache))
    monkeypatch.setattr(mlh, "get_session", lambda: _sitzung(db))

    async def _kein_preis(*_a, **_k):
        return {}

    monkeypatch.setattr(sms, "get_strompreis_stunden", _kein_preis)
    assert await mlh.snapshot_live_cache() == 3
    mit = await ltv._get_tagesverlauf_mqtt(a, db)
    await db.execute(text("DELETE FROM mqtt_live_snapshots WHERE component_key LIKE '%vorlauf%'"))
    await db.commit()
    ohne = await ltv._get_tagesverlauf_mqtt(a, db)
    assert mit == ohne
    assert any(s["key"] == f"waermepumpe_{wp.id}" for s in mit["serien"]), "die WP-Serie ist da"


def test_migration_min_max_idempotent_auch_nach_ts_unix():
    from sqlalchemy import create_engine, inspect

    from backend.core.database import _migrate_mqtt_live_snapshot_min_max, _migrate_mqtt_live_snapshot_ts_unix

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE mqtt_live_snapshots (id INTEGER PRIMARY KEY, anlage_id INTEGER, "
                          "timestamp DATETIME, component_key VARCHAR(120), value_w FLOAT)"))
        conn.execute(text("INSERT INTO mqtt_live_snapshots VALUES (1, 1, '2026-06-10 08:00:00', 'inv:1:leistung_w', 5.0)"))
        _migrate_mqtt_live_snapshot_ts_unix(conn)                    # Stand S1: ts_unix schon da
        _migrate_mqtt_live_snapshot_min_max(conn)
        _migrate_mqtt_live_snapshot_min_max(conn)
        spalten = {c["name"] for c in inspect(conn).get_columns("mqtt_live_snapshots")}
        assert {"ts_unix", "min", "max"} <= spalten
        assert conn.execute(text('SELECT "min", "max" FROM mqtt_live_snapshots')).one() == (None, None)
    engine.dispose()


# ═══ S2-2 Verdichtung (rein) ═════════════════════════════════════════════════

def test_neustart_um_10_17_elf_zeilen_in_der_stunde():
    """Snapshot-Takt :02/:07/:12, Neustart 10:17 (neuer Takt ab 10:22): die Stunde hat 11 Zeilen, jede mit dem Gewicht
    eines Fensters (die Lücke 10:12 → 10:22 zählt nicht doppelt)."""
    h10 = T0 + 2 * _STUNDE
    vorher = _fenster_lauf([(h10 - 600, "500")], [h10 - 180 + 300 * i for i in range(0, 4)])     # 9:57 … 10:12
    nachher = _fenster_lauf([(h10 + 17 * 60, "1000")], [h10 + 17 * 60 + 300 * i for i in range(1, 10)])
    zeilen = vorher + nachher
    in_stunde = [z for z in zeilen if h10 <= z[0] < h10 + _STUNDE]
    assert len(in_stunde) == 11
    assert _stunde(zeilen, h10)[0] == pytest.approx((3 * 500 + 8 * 1000) / 11)


def test_broker_ausfall_stunde_ist_mittel_der_vorhandenen_zeilen():
    zeilen = [(T0 + m * 60, 100.0, 90.0, 110.0) for m in (5, 10, 15, 20)] + \
             [(T0 + m * 60, 400.0, 400.0, 400.0) for m in (45, 50, 55)]
    mittel, lo, hi = _stunde(zeilen, T0)
    assert mittel == pytest.approx((4 * 100 + 3 * 400) / 7)
    assert (lo, hi) == (90.0, 400.0)


def test_stunde_ohne_zeilen_fehlt_und_zeile_gehoert_zur_stunde_ihres_abschlusses():
    zeilen = [(T0 + 300, 1.0, None, None), (T0 + 2 * _STUNDE, 3.0, None, None)]
    assert [s for s, *_ in mittel_je_stunde(zeilen)] == [T0, T0 + 2 * _STUNDE]
    assert mittel_je_stunde(zeilen)[0] == (T0, 1.0, 1.0, 1.0), "ohne min/max-Spalte: das Mittel als Extremum"


def test_herbst_zwei_mal_zwei_uhr_zwei_stunden():
    erste = calendar.timegm((2026, 10, 25, 0, 0, 0))            # 02:00 CEST
    zweite = erste + _STUNDE                                     # 02:00 CET
    berlin = ZoneInfo("Europe/Berlin")
    assert datetime.fromtimestamp(erste, berlin).hour == datetime.fromtimestamp(zweite, berlin).hour == 2
    zeilen = [(erste + m * 60 - 1, 10.0, None, None) for m in range(5, 65, 5)] + \
             [(zweite + m * 60 - 1, 20.0, None, None) for m in range(5, 65, 5)]
    with _prozesszone("Europe/Berlin"):
        assert [(s, m) for s, m, *_ in mittel_je_stunde(zeilen)] == [(erste, 10.0), (zweite, 20.0)]
        assert _stunden_start_ts(datetime.fromtimestamp(zweite + 60)) == zweite


def test_statistic_id_ist_der_mqtt_schluessel():
    assert mqtt_live_statistic_id("inv:7:vorlauf_temperatur_c") == "mqtt:inv/7/vorlauf_temperatur_c"
    assert mqtt_live_statistic_id("inv:7:leistung_w-3") == "mqtt:inv/7/leistung_w-3"
    assert mqtt_live_statistic_id("basis:netzbezug_w") == "mqtt:netzbezug_w"
    assert mqtt_modus_statistic_id(7) == "mqtt:inv/7/betriebsmodus", "S1-Form unverändert"


# ═══ S2-2 Stundenschreiber ═══════════════════════════════════════════════════

async def test_erster_lauf_nur_die_abgeschlossene_stunde_dann_fortlaufend(db):
    a, wp = await _anlage_wp(db)
    key = f"inv:{wp.id}:vorlauf_temperatur_c"
    for h in range(4):                                           # vier Stunden Snapshots, dazu die laufende
        _stunde_snaps(db, a.id, key, T0 + h * _STUNDE, 30.0 + h)
    db.add(_snap(a.id, key, T0 + 4 * _STUNDE + 120, 99.0))
    await db.commit()
    assert await _schreiben(db, a, T0 + 3 * _STUNDE + 300) == 1
    assert set(await _reihe(db, a.id, key)) == {T0 + 2 * _STUNDE}, "nicht rückwirkend (E2)"
    assert await _schreiben(db, a, T0 + 3 * _STUNDE + 900) == 0, "Wiederholung schreibt nichts"
    assert await _schreiben(db, a, T0 + 4 * _STUNDE + 300) == 1
    reihe = await _reihe(db, a.id, key)
    assert reihe == {T0 + 2 * _STUNDE: (32.0, 32.0, 32.0, FAMILIE_MITSCHRIFT),
                     T0 + 3 * _STUNDE: (33.0, 33.0, 33.0, FAMILIE_MITSCHRIFT)}, "laufende Stunde nie"
    k = (await db.execute(select(Kanal).where(Kanal.key == key))).scalar_one()
    assert (k.art, k.einheit) == ("mean", "°C")
    assert await _quellen(db, a.id, key) == [(T0 + 2 * _STUNDE, FAMILIE_MITSCHRIFT,
                                              f"mqtt:inv/{wp.id}/vorlauf_temperatur_c", 0.0)]
    assert await _zwei_familien(db) == []


async def test_nachholen_nach_einer_pause_ab_der_letzten_zeile(db):
    a, wp = await _anlage_wp(db)
    key = f"inv:{wp.id}:leistung_w"
    for h in range(4):
        _stunde_snaps(db, a.id, key, T0 + h * _STUNDE, 100.0 * (h + 1))
    await db.commit()
    await _schreiben(db, a, T0 + _STUNDE + 300)                  # schreibt T0
    assert await _schreiben(db, a, T0 + 4 * _STUNDE + 300) == 3, "Stundenlauf ausgefallen: ab der letzten Zeile"
    assert {s: v[0] for s, v in (await _reihe(db, a.id, key)).items()} == {
        T0: 100.0, T0 + _STUNDE: 200.0, T0 + 2 * _STUNDE: 300.0, T0 + 3 * _STUNDE: 400.0}


async def test_stunde_ohne_snapshot_bekommt_keine_zeile(db):
    a, wp = await _anlage_wp(db)
    key = f"inv:{wp.id}:leistung_w"
    _stunde_snaps(db, a.id, key, T0, 10.0)
    _stunde_snaps(db, a.id, key, T0 + 2 * _STUNDE, 30.0)
    await db.commit()
    await _schreiben(db, a, T0 + _STUNDE + 300)
    await _schreiben(db, a, T0 + 2 * _STUNDE + 300)              # Stunde T0+1h ohne Zeilen
    await _schreiben(db, a, T0 + 3 * _STUNDE + 300)
    assert set(await _reihe(db, a.id, key)) == {T0, T0 + 2 * _STUNDE}


async def test_ha_entitaet_ohne_lts_und_mqtt_liefert_keine_zeile_checker_info_bleibt(db, monkeypatch):
    """G1 (2): eine HA-Entität im ``live``-Block macht das Feld zum HA-Feld — auch ohne Langzeitstatistik. MQTT liefert
    denselben Key: keine Mitschrift-Zeile, und der Daten-Checker nennt den Sensor weiter."""
    from backend.services import ha_state_service as hss
    from backend.services.daten_checker import DatenChecker

    a, wp = await _anlage_wp(db)
    a.sensor_mapping = {"investitionen": {str(wp.id): {"live": {"vorlauf_temperatur_c": "sensor.vorlauf"}}}}
    await db.commit()
    key = f"inv:{wp.id}:vorlauf_temperatur_c"
    _stunde_snaps(db, a.id, key, T0, 35.0)
    await db.commit()
    assert await _schreiben(db, a, T0 + _STUNDE + 300) == 0
    assert (await db.execute(select(Kanal).where(Kanal.key == key))).scalar_one_or_none() is None

    class _Ha:
        is_available = True

        async def get_sensor_state_classes(self, entity_ids):
            return {e: "" for e in entity_ids}

    monkeypatch.setattr(hss, "get_ha_state_service", lambda: _Ha())
    (meldung,) = await DatenChecker(db)._check_sensor_ohne_langzeitstatistik(a)
    assert "sensor.vorlauf" in meldung.details and "5-Minuten-Mitschrift" in meldung.details
    assert meldung.meldung.endswith("Live ja, Tagesverlauf nein")


async def test_quellen_keine_schreibt_nichts_ha_quelle_auch_nicht(db):
    a, wp = await _anlage_wp(db)
    a.sensor_mapping = {"quellen": {
        f"inv_live_{wp.id}_vorlauf_temperatur_c": {"quelle": "keine", "entity_id": None},
        f"inv_live_{wp.id}_ruecklauf_temperatur_c": {"quelle": "ha_app", "entity_id": None},
    }}
    await db.commit()
    for feld in ("vorlauf_temperatur_c", "ruecklauf_temperatur_c"):
        _stunde_snaps(db, a.id, f"inv:{wp.id}:{feld}", T0, 30.0)
    await db.commit()
    assert await _schreiben(db, a, T0 + _STUNDE + 300) == 0
    assert (await db.execute(select(Kanal))).scalars().all() == []


async def test_b8_stempel_ohne_wert_schreibt_nichts_mit_wert_die_mitschrift(db):
    a, wp = await _anlage_wp(db)
    a.sensor_mapping = {"quellen": {
        f"inv_live_{wp.id}_vorlauf_temperatur_c": {"quelle": "mqtt_inbound_standard"},
        f"inv_live_{wp.id}_ruecklauf_temperatur_c": {"quelle": "mqtt_inbound_standard"},
    }}
    await db.commit()
    _stunde_snaps(db, a.id, f"inv:{wp.id}:vorlauf_temperatur_c", T0, 36.0)       # nur Vorlauf liefert
    await db.commit()
    assert await _schreiben(db, a, T0 + _STUNDE + 300) == 1
    assert [k.key for k in (await db.execute(select(Kanal))).scalars().all()] == [f"inv:{wp.id}:vorlauf_temperatur_c"]
    assert await _zwei_familien(db) == []


async def test_spiegel_kanal_mit_ha_entitaet_bekommt_nie_eine_mitschrift_zeile(db):
    a, wp = await _anlage_wp(db)
    a.sensor_mapping = {"investitionen": {str(wp.id): {"live": {"leistung_w": "sensor.wp_leistung"}}}}
    key = f"inv:{wp.id}:leistung_w"
    k = Kanal(anlage_id=a.id, key=key, art="mean", einheit="W")
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=T0 - _STUNDE, familie=FAMILIE_SPIEGEL,
                       statistic_id="sensor.wp_leistung", offset=0.0))
    db.add(KanalStatistik(kanal_id=k.id, start_ts=T0 - _STUNDE, mean=800.0, familie=FAMILIE_SPIEGEL))
    _stunde_snaps(db, a.id, key, T0, 900.0)
    await db.commit()
    assert await _schreiben(db, a, T0 + _STUNDE + 300) == 0
    assert await _reihe(db, a.id, key) == {T0 - _STUNDE: (800.0, None, None, FAMILIE_SPIEGEL)}
    assert await _zwei_familien(db) == []


async def test_quellenwechsel_ha_nach_mqtt_neue_quelle_ab_der_ersten_stunde(db):
    """Die HA-Entität ist weg, MQTT liefert: die Mitschrift setzt mit einer neuen Quelle ab ihrer ersten Stunde fort
    (Muster «Eigene Summe»). Die Familien bleiben zeitlich getrennt — Spiegel vor ``gueltig_ab``, Mitschrift ab dort."""
    a, wp = await _anlage_wp(db)
    key = f"inv:{wp.id}:vorlauf_temperatur_c"
    k = Kanal(anlage_id=a.id, key=key, art="mean", einheit="°C")
    db.add(k)
    await db.flush()
    db.add(KanalQuelle(kanal_id=k.id, gueltig_ab=T0 - 5 * _STUNDE, familie=FAMILIE_SPIEGEL,
                       statistic_id="sensor.vorlauf", offset=0.0))
    for h in range(5, 2, -1):
        db.add(KanalStatistik(kanal_id=k.id, start_ts=T0 - h * _STUNDE, mean=40.0, familie=FAMILIE_SPIEGEL))
    for h in range(-2, 2):
        _stunde_snaps(db, a.id, key, T0 + h * _STUNDE, 37.0)
    await db.commit()
    assert await _schreiben(db, a, T0 + _STUNDE + 300) == 1
    assert await _schreiben(db, a, T0 + 2 * _STUNDE + 300) == 1
    reihe = await _reihe(db, a.id, key)
    assert {s: v[3] for s, v in reihe.items()} == {
        T0 - 5 * _STUNDE: FAMILIE_SPIEGEL, T0 - 4 * _STUNDE: FAMILIE_SPIEGEL, T0 - 3 * _STUNDE: FAMILIE_SPIEGEL,
        T0: FAMILIE_MITSCHRIFT, T0 + _STUNDE: FAMILIE_MITSCHRIFT}
    assert await _quellen(db, a.id, key) == [
        (T0 - 5 * _STUNDE, FAMILIE_SPIEGEL, "sensor.vorlauf", 0.0),
        (T0, FAMILIE_MITSCHRIFT, f"mqtt:inv/{wp.id}/vorlauf_temperatur_c", 0.0)]
    gueltig_ab = T0
    assert all((v[3] == FAMILIE_SPIEGEL) == (s < gueltig_ab) for s, v in reihe.items())


async def test_innengeraet_suffix_basis_feld_und_stillgelegtes_geraet(db):
    from datetime import date

    a, wp = await _anlage_wp(db, parameter={"wp_art": "luft_luft", "innengeraete": [{"id": 3, "bezeichnung": "Büro"}]})
    alt = await factories.investition(db, a.id, "speicher", bezeichnung="Alt", stilllegungsdatum=date(2025, 1, 1))
    await db.commit()
    for key, wert in ((f"inv:{wp.id}:leistung_w-3", 450.0), ("basis:netzbezug_w", 1200.0),
                      (f"inv:{alt.id}:soc", 50.0), (f"inv:{wp.id}:fremd_w", 1.0), ("basis:strompreis_ct", 30.0),
                      (f"inv:{wp.id}:betriebsmodus:heizen", 1.0)):
        _stunde_snaps(db, a.id, key, T0, wert)
    await db.commit()
    assert await _schreiben(db, a, T0 + _STUNDE + 300) == 2
    keys = {k.key: k.einheit for k in (await db.execute(select(Kanal))).scalars().all()}
    assert keys == {f"inv:{wp.id}:leistung_w-3": "W", "basis:netzbezug_w": "W"}
    assert (await _quellen(db, a.id, "basis:netzbezug_w"))[0][2] == "mqtt:netzbezug_w"
    assert await _zwei_familien(db) == []


async def test_kanal_mit_anderer_einheit_wird_nicht_beschrieben(db):
    a, wp = await _anlage_wp(db)
    key = f"inv:{wp.id}:leistung_w"
    db.add(Kanal(anlage_id=a.id, key=key, art="mean", einheit="kW"))
    _stunde_snaps(db, a.id, key, T0, 900.0)
    await db.commit()
    assert await _schreiben(db, a, T0 + _STUNDE + 300) == 0


async def test_herbst_doppelstunde_zwei_zeilen_im_kanal(db):
    a, wp = await _anlage_wp(db)
    key = f"inv:{wp.id}:vorlauf_temperatur_c"
    erste = calendar.timegm((2026, 10, 25, 0, 0, 0))
    zweite = erste + _STUNDE
    _stunde_snaps(db, a.id, key, erste, 30.0)
    _stunde_snaps(db, a.id, key, zweite, 31.0)
    await db.commit()
    with _prozesszone("Europe/Berlin"):
        await _schreiben(db, a, zweite + 300)                    # während der zweiten 02:00: schreibt die erste
        await _schreiben(db, a, zweite + _STUNDE + 300)
    assert {s: v[0] for s, v in (await _reihe(db, a.id, key)).items()} == {erste: 30.0, zweite: 31.0}


async def test_stundenlauf_legt_keinen_preis_kanal_an_und_schreibt_die_mitschrift(db):
    """G7: ``basis:strompreis_ct`` liegt im Snapshot, aber kein Stundenlauf legt daraus einen Kanal an; die
    Mittelwert-Mitschrift läuft im Stundenlauf ohne HA (der Spiegel kehrt vorher zurück)."""
    from backend.services.kanal.schreiber import schreibe_kanaele_im_stundenlauf

    a, wp = await _anlage_wp(db)
    _stunde_snaps(db, a.id, "basis:strompreis_ct", T0, 31.0)
    _stunde_snaps(db, a.id, f"inv:{wp.id}:vorlauf_temperatur_c", T0, 35.0)
    await db.commit()
    assert await schreibe_kanaele_im_stundenlauf(db, a, datetime.fromtimestamp(T0 + _STUNDE)) is not None
    await db.commit()
    keys = {k.key for k in (await db.execute(select(Kanal))).scalars().all()}
    assert "basis:strompreis_ct" not in keys and "basis:strompreis" not in keys
    assert f"inv:{wp.id}:vorlauf_temperatur_c" in keys
    assert await _reihe(db, a.id, f"inv:{wp.id}:vorlauf_temperatur_c") == {
        T0: (35.0, 35.0, 35.0, FAMILIE_MITSCHRIFT)}
    assert await _zwei_familien(db) == []
