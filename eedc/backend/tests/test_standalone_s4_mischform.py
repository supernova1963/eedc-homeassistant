"""Standalone-Gleichstand Sitzung 4 — Mischform: HA-Add-on mit MQTT-Geräten ohne HA-Zuordnung (HA-Bauform §9).

Der Fall (Lab Winterborn 26.10.2026): eedc läuft mit HA-Verbindung (Supervisor- oder Long-Lived-Token), die Geräte liefern
ihre Leistung aber nur über MQTT-Inbound — keine `live`-Zuordnung auf eine HA-Entität (B8-Stempel
`mqtt_inbound_standard`). Bis S3 kehrte `get_tagesverlauf` mit Token und leerer Zuordnung leer um: keine Kurve, und
`aggregate_day` schrieb Stundenzeilen ohne Gerätewerte (am laufenden Tag mit Komponenten-Drift-Warnung im Protokoll).

* **M-1 Weiche:** HA verfügbar + leere `live`-Zuordnung ⇒ MQTT-Zweig (HA unbefragt; ohne Snapshots leer).
* **M-2 Teilmischung:** HA-Zuordnung für manche Geräte, andere nur MQTT ⇒ die Geräte ohne HA-Leistungs-Entität bekommen
  ihre Serie aus den Snapshots, Netz/PV gesamt/Preis bleiben beim HA-Zweig — nur, wenn MQTT-Inbound eingerichtet ist
  (sonst keine zusätzliche Query, Antwort wie vorher). Der F-26-Rückfall fragt nur den HA-Anteil. Eine Zuordnung ganz
  ohne HA-Leistungs-, Netz- oder Preis-Entität (z. B. nur Temperaturen aus HA) nimmt mit MQTT-Inbound den MQTT-Zweig.
* **M-3 Tagesaggregation:** `aggregate_day` schreibt für die Mischform-Anlage Gerätewerte je Stunde aus der Kurve;
  `komponenten_kwh[Wärmepumpe]` deckt sich mit Σ Stunden — am laufenden Tag ohne Drift-Warnung.

Schwesterdateien: test_standalone_s3_tagesverlauf_mittelung.py (reine MQTT-Anlage ohne Token),
test_tagesverlauf_standalone_ha_verbindung.py (Weggabelung F-26, N-598), test_408_wrapper_reicht_vortagsrand_durch.py.
"""

from __future__ import annotations

import logging
from contextlib import ExitStack
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.mqtt_live_snapshot import MqttLiveSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services import live_tagesverlauf_service as ltv
from backend.services import mqtt_inbound_service as mis
from backend.services import mqtt_live_history_service as mlh
from backend.services.energie_profil.source import Source
from backend.services.ha_state_service import get_ha_state_service
from backend.services.snapshot.tages_tabelle import TagesTabelle
from backend.tests import factories

#: Ein fester Tag, die Uhr am Folgetag (`tage_zurueck = 1`) — keine Probe liest die Prozessuhr. Die Heute-Probe stellt
#: die Uhr des Aggregators (`aggregator.date`) und des Tagesverlaufs auf TAG 12:30.
TAG = date(2026, 9, 4)
JETZT = datetime(2026, 9, 5, 12, 0, 0)
HEUTE_MITTAG = datetime(2026, 9, 4, 12, 30, 0)


@pytest.fixture
def ha_verbindung():
    """HA-Verbindung per Long-Lived-Token am Singleton setzen — und aufräumen (Muster F-26-Proben)."""
    svc = get_ha_state_service()
    vorher = (svc.api_url, svc.token)
    svc.api_url = "http://ha.example:8123/api"
    svc.token = "langlebiger-token"
    yield svc
    svc.api_url, svc.token = vorher


@pytest.fixture(autouse=True)
def _ohne_marktabruf(monkeypatch):
    from backend.services import strompreis_markt_service as sms

    async def keine_preise(land, tag):
        return {}

    monkeypatch.setattr(sms, "get_strompreis_stunden", keine_preise)


def _feste_uhr_klasse(jetzt: datetime):
    class _Uhr(datetime):
        @classmethod
        def now(cls, tz=None):
            return jetzt if tz is None else jetzt.astimezone(tz)
    return _Uhr


@pytest.fixture(autouse=True)
def _feste_uhr(monkeypatch):
    from backend.services.energie_profil import _helpers

    monkeypatch.setattr(ltv, "datetime", _feste_uhr_klasse(JETZT))
    monkeypatch.setattr(_helpers, "_tage_zurueck", lambda tag: (JETZT.date() - tag).days)


@pytest.fixture
def inbound(monkeypatch):
    """MQTT-Inbound eingerichtet (Dienst initialisiert) — der Schalter der Teilmischung."""
    monkeypatch.setattr(mis, "_mqtt_inbound_service", object())


class _Zaehler:
    """Zählt HA-History- und Snapshot-Abrufe; die HA-History liefert je Entity einen festen Wert im Fenster."""

    def __init__(self, monkeypatch, ha_werte: dict[str, float] | None = None):
        self.ha: list = []
        self.snap = 0
        self._ha_werte = ha_werte or {}
        echte_snaps = mlh.get_snapshots_for_range

        async def ha(ids, start, end):
            self.ha.append(sorted(ids))
            hist = {}
            for eid in ids:
                if eid in self._ha_werte:
                    t, pts = start, []
                    while t < end:
                        if t.date() == TAG and 10 <= t.hour < 12:
                            pts.append((t, self._ha_werte[eid]))
                        t += timedelta(minutes=5)
                    hist[eid] = pts
            return hist, {eid: "W" for eid in ids}

        async def snaps(*args, **kwargs):
            self.snap += 1
            return await echte_snaps(*args, **kwargs)

        monkeypatch.setattr(ltv, "get_history_normalized", ha)
        monkeypatch.setattr(mlh, "get_snapshots_for_range", snaps)


def _snaps(db, anlage_id: int, werte: dict[str, float], tag: date = TAG) -> None:
    """10:00–12:00 alle 5 Minuten je Komponenten-Key ein Wert (5-Minuten-Mittel wie seit S2)."""
    beginn = datetime.combine(tag, datetime.min.time()) + timedelta(hours=10)
    for i in range(24):
        ts = beginn + timedelta(minutes=5 * i)
        for key, wert in werte.items():
            db.add(MqttLiveSnapshot(anlage_id=anlage_id, timestamp=ts, component_key=key, value_w=wert,
                                    ts_unix=int(ts.timestamp())))


def _tz(tag: date = TAG) -> int:
    return (JETZT.date() - tag).days


def _slot(erg: dict, zeit: str) -> dict:
    return next(p["werte"] for p in erg["punkte"] if p["zeit"] == zeit)


async def _anlage(db, mapping: dict, *geraete: tuple[str, str]):
    a = await factories.anlage(db, anlagenname="Mischform", leistung_kwp=8.0, sensor_mapping=mapping)
    invs = [await factories.investition(db, a.id, typ, bezeichnung=name, anschaffungsdatum=date(2020, 1, 1))
            for typ, name in geraete]
    await db.commit()
    return a, invs


# ═══ M-1 Weiche: HA verfügbar + leere `live`-Zuordnung ⇒ MQTT-Zweig ═══════════════════════════════════════════════

@pytest.mark.asyncio
@pytest.mark.parametrize("mapping", [
    {},
    {"basis": {}, "investitionen": {}},
    {"basis": {"live": {}}, "investitionen": {"1": {"live": {}}}},
    {"quellen": {"basis_live_netzbezug_w": {"quelle": "mqtt_inbound_standard"}}},
], ids=["mapping-leer", "bloecke-leer", "live-leer", "nur-b8-stempel"])
async def test_m1_ha_verfuegbar_leere_zuordnung_kurve_aus_mqtt(db, ha_verbindung, monkeypatch, mapping):
    """Lab-Lage: Serien und Punkte aus den Snapshots, HA unbefragt (vorher: leer vor jeder Abfrage)."""
    zaehler = _Zaehler(monkeypatch)
    a, (pv,) = await _anlage(db, mapping, ("pv-module", "PV Süd"))
    _snaps(db, a.id, {f"inv:{pv.id}:leistung_w": 2000.0, "basis:netzbezug_w": 300.0})
    await db.commit()

    erg = await ltv.get_tagesverlauf(a, db, _tz(), mit_vortagsrand=True)

    assert [s["key"] for s in erg["serien"]] == [f"pv_{pv.id}", "netzbezug", "haushalt"]
    assert _slot(erg, "10:00") == {f"pv_{pv.id}": 2.0, "netzbezug": 0.3, "haushalt": -2.3}
    assert {p["zeit"] for p in erg["punkte"] if p["werte"]} == {f"{h:02d}:{m:02d}" for h in (10, 11) for m in range(0, 60, 10)}
    assert erg == await ltv._get_tagesverlauf_mqtt(a, db, _tz(), mit_vortagsrand=True), "genau der MQTT-Zweig"
    assert zaehler.ha == [], "ohne Zuordnung wird HA nicht befragt"


@pytest.mark.asyncio
async def test_m1_ha_verfuegbar_leere_zuordnung_ohne_snapshots_leer_wie_bisher(db, ha_verbindung, monkeypatch):
    zaehler = _Zaehler(monkeypatch)
    a, _ = await _anlage(db, {}, ("pv-module", "PV Süd"))

    assert await ltv.get_tagesverlauf(a, db, _tz()) == {"serien": [], "punkte": []}
    assert (zaehler.ha, zaehler.snap) == ([], 1), "eine Snapshot-Query, keine HA-Abfrage"


@pytest.mark.asyncio
async def test_m1_mit_zuordnung_ha_zweig_wie_bisher(db, ha_verbindung, monkeypatch):
    """HA trägt Leistung ⇒ HA-Zweig, kein Rückfall; MQTT-Snapshots desselben Geräts werden nicht gelesen (ohne Inbound)."""
    a, (pv,) = await _anlage(db, {}, ("pv-module", "PV Süd"))
    a.sensor_mapping = {"basis": {"live": {"netzbezug_w": "sensor.netz"}},
                        "investitionen": {str(pv.id): {"live": {"leistung_w": "sensor.pv"}}}}
    zaehler = _Zaehler(monkeypatch, {"sensor.pv": 1500.0, "sensor.netz": 100.0})
    _snaps(db, a.id, {f"inv:{pv.id}:leistung_w": 9999.0})
    await db.commit()

    erg = await ltv.get_tagesverlauf(a, db, _tz())

    assert _slot(erg, "10:00")[f"pv_{pv.id}"] == 1.5, "Wert aus HA"
    assert zaehler.snap == 0 and len(zaehler.ha) == 1


# ═══ M-2 Teilmischung ═════════════════════════════════════════════════════════════════════════════════════════════

async def _zwei_wps(db):
    a, (wp_ha, wp_mqtt) = await _anlage(db, {}, ("waermepumpe", "WP Haus"), ("waermepumpe", "WP Garage"))
    a.sensor_mapping = {"basis": {"live": {"netzbezug_w": "sensor.netz"}},
                        "investitionen": {str(wp_ha.id): {"live": {"leistung_w": "sensor.wp_haus"}}}}
    _snaps(db, a.id, {f"inv:{wp_mqtt.id}:leistung_w": 1200.0, "basis:netzbezug_w": 7777.0})
    await db.commit()
    return a, wp_ha, wp_mqtt


@pytest.mark.asyncio
async def test_m2_zwei_wps_eine_ha_eine_mqtt_beide_serien_netz_aus_ha(db, ha_verbindung, monkeypatch, inbound):
    zaehler = _Zaehler(monkeypatch, {"sensor.wp_haus": 800.0, "sensor.netz": 2500.0})
    a, wp_ha, wp_mqtt = await _zwei_wps(db)

    erg = await ltv.get_tagesverlauf(a, db, _tz(), mit_vortagsrand=True)

    assert [s["key"] for s in erg["serien"]] == [
        f"waermepumpe_{wp_ha.id}", f"waermepumpe_{wp_mqtt.id}", "netzbezug", "haushalt"]
    assert _slot(erg, "10:00") == {
        f"waermepumpe_{wp_ha.id}": -0.8, f"waermepumpe_{wp_mqtt.id}": -1.2, "netzbezug": 2.5, "haushalt": -0.5,
    }, "Netz aus HA (nicht 7,777 aus MQTT), Restverbrauch über beide Geräte"
    assert erg["uebersprungen"] == []
    assert _slot(erg, "12:00") == {}
    assert zaehler.snap == 1 and zaehler.ha == [["sensor.netz", "sensor.wp_haus"]], "MQTT-Keys gehen nie an HA"


@pytest.mark.asyncio
async def test_m2_ohne_mqtt_inbound_wie_bisher_ohne_query(db, ha_verbindung, monkeypatch):
    """Kein MQTT-Inbound eingerichtet ⇒ keine Snapshot-Query, das MQTT-Gerät bleibt «nicht dargestellt» wie vorher."""
    zaehler = _Zaehler(monkeypatch, {"sensor.wp_haus": 800.0, "sensor.netz": 2500.0})
    a, wp_ha, wp_mqtt = await _zwei_wps(db)

    erg = await ltv.get_tagesverlauf(a, db, _tz())

    assert [s["key"] for s in erg["serien"]] == [f"waermepumpe_{wp_ha.id}", "netzbezug", "haushalt"]
    assert erg["uebersprungen"] == ["WP Garage"]
    assert zaehler.snap == 0


@pytest.mark.asyncio
async def test_m2_geraet_mit_ha_entitaet_bleibt_beim_ha_zweig(db, ha_verbindung, monkeypatch, inbound):
    """Ein Gerät mit HA-Leistungs-Entität bekommt keine zweite Serie aus MQTT — auch wenn Snapshots da sind."""
    zaehler = _Zaehler(monkeypatch, {"sensor.wp_haus": 800.0, "sensor.netz": 2500.0})
    a, wp_ha, wp_mqtt = await _zwei_wps(db)
    _snaps(db, a.id, {f"inv:{wp_ha.id}:leistung_w": 5000.0})
    await db.commit()

    erg = await ltv.get_tagesverlauf(a, db, _tz())

    keys = [s["key"] for s in erg["serien"]]
    assert keys.count(f"waermepumpe_{wp_ha.id}") == 1
    assert _slot(erg, "10:00")[f"waermepumpe_{wp_ha.id}"] == -0.8, "Wert aus HA, nicht 5,0 aus MQTT"
    assert zaehler.snap == 1


@pytest.mark.asyncio
async def test_m2_mqtt_erzeuger_ersetzt_pv_gesamt_wie_ein_ha_erzeuger(db, ha_verbindung, monkeypatch, inbound):
    """Eine Regel: ein Erzeuger mit eigener Serie ersetzt «PV Gesamt» — egal ob die Serie aus HA oder MQTT kommt."""
    _Zaehler(monkeypatch, {"sensor.pv_gesamt": 3000.0, "sensor.netz": 100.0})
    a, (pv,) = await _anlage(db, {}, ("pv-module", "PV Süd"))
    a.sensor_mapping = {"basis": {"live": {"pv_gesamt_w": "sensor.pv_gesamt", "netzbezug_w": "sensor.netz"}}}
    _snaps(db, a.id, {f"inv:{pv.id}:leistung_w": 2000.0})
    await db.commit()

    erg = await ltv.get_tagesverlauf(a, db, _tz())

    keys = [s["key"] for s in erg["serien"]]
    assert f"pv_{pv.id}" in keys and "pv_gesamt" not in keys, keys
    assert _slot(erg, "10:00")[f"pv_{pv.id}"] == 2.0


@pytest.mark.asyncio
async def test_m2_rueckfall_f26_fragt_nur_den_ha_anteil(db, ha_verbindung, monkeypatch, inbound):
    """HA-Zuordnung zeigt ins Leere, ein MQTT-Gerät trägt Leistung ⇒ der Rückfall in den MQTT-Zweig greift weiter
    (der Anwender behält Netz aus MQTT) — ohne die Regel «nur der HA-Anteil» bliebe das leere HA-Netz stehen."""
    _Zaehler(monkeypatch, {})                                     # HA ohne Verlauf
    a, wp_ha, wp_mqtt = await _zwei_wps(db)

    erg = await ltv.get_tagesverlauf(a, db, _tz())

    assert erg == await ltv._get_tagesverlauf_mqtt(a, db, _tz())
    assert _slot(erg, "10:00")["netzbezug"] == 7.78, "Netz aus MQTT"


@pytest.mark.asyncio
async def test_m2_zuordnung_ohne_ha_leistungs_entitaet_nimmt_mqtt_zweig(db, ha_verbindung, monkeypatch, inbound):
    """Nur eine Temperatur aus HA, Leistung und Netz über MQTT ⇒ die Kurve des MQTT-Zweigs (vorher leer)."""
    zaehler = _Zaehler(monkeypatch)
    a, (wp,) = await _anlage(db, {}, ("waermepumpe", "WP Haus"))
    a.sensor_mapping = {"investitionen": {str(wp.id): {"live": {"vorlauf_temperatur_c": "sensor.vorlauf"}}}}
    _snaps(db, a.id, {f"inv:{wp.id}:leistung_w": 900.0, "basis:netzbezug_w": 1000.0})
    await db.commit()

    erg = await ltv.get_tagesverlauf(a, db, _tz())

    assert erg == await ltv._get_tagesverlauf_mqtt(a, db, _tz())
    assert _slot(erg, "10:00") == {f"waermepumpe_{wp.id}": -0.9, "netzbezug": 1.0, "haushalt": -0.1}
    assert zaehler.ha == []


@pytest.mark.asyncio
async def test_m2_zuordnung_ohne_ha_leistungs_entitaet_ohne_inbound_leer_wie_bisher(db, ha_verbindung, monkeypatch):
    zaehler = _Zaehler(monkeypatch)
    a, (wp,) = await _anlage(db, {}, ("waermepumpe", "WP Haus"))
    a.sensor_mapping = {"investitionen": {str(wp.id): {"live": {"vorlauf_temperatur_c": "sensor.vorlauf"}}}}
    _snaps(db, a.id, {f"inv:{wp.id}:leistung_w": 900.0})
    await db.commit()

    assert await ltv.get_tagesverlauf(a, db, _tz()) == {"serien": [], "punkte": []}
    assert (zaehler.ha, zaehler.snap) == ([], 0)


# ═══ M-3 Tagesaggregation der Mischform-Anlage ═══════════════════════════════════════════════════════════════════

def _nebenquellen(wp_id: int):
    """HA-LTS leer (die MQTT-Geräte stehen nicht im Recorder), die Zählertabelle des Snapshot-Pfads mit dem MQTT-
    Stromzähler der WP: 1 kWh in Slot 11 und 12 (Backward-Slot = Energie [h-1, h)), Tageswert 2 kWh."""
    from backend.services.energie_profil._helpers import StrompreisStunden

    tabelle = TagesTabelle(stunden={11: {"wp": 1.0}, 12: {"wp": 1.0}},
                           komponenten_kwh={f"waermepumpe_{wp_id}": 2.0})
    stack = ExitStack()
    for ziel, wert in (
        ("backend.services.snapshot.aggregator.snapshot_tagestabelle", tabelle),
        ("backend.services.snapshot.lts_aggregator.lts_tagestabelle", None),
        ("backend.services.sensor_snapshot_service.get_daily_counter_deltas_by_inv", {}),
        ("backend.services.energie_profil._helpers._get_strompreis_stunden", StrompreisStunden(sensor={}, boerse={})),
    ):
        stack.enter_context(patch(ziel, new=AsyncMock(return_value=wert)))
    return stack


async def _aggregiere_lab_lage(db, caplog, tag: date):
    from backend.services.energie_profil.aggregator import aggregate_day

    a, (wp,) = await _anlage(db, {}, ("waermepumpe", "Nibe"))
    a.sensor_mapping = {"quellen": {f"inv_live_{wp.id}_leistung_w": {"quelle": "mqtt_inbound_standard"},
                                    f"inv_energy_{wp.id}_stromverbrauch_kwh": {"quelle": "mqtt_inbound_standard"}}}
    _snaps(db, a.id, {f"inv:{wp.id}:leistung_w": 1000.0}, tag)
    db.add(MqttEnergySnapshot(anlage_id=a.id, energy_key=f"inv/{wp.id}/stromverbrauch_kwh", value_kwh=12347.0,
                              timestamp=datetime.combine(tag, datetime.min.time()) - timedelta(hours=1)))
    await db.commit()
    with _nebenquellen(wp.id), caplog.at_level(logging.WARNING):
        tz = await aggregate_day(a, tag, db, source=Source.SCHEDULER)
    assert tz is not None
    zeilen = (await db.execute(select(TagesEnergieProfil).where(TagesEnergieProfil.anlage_id == a.id)
                               .order_by(TagesEnergieProfil.stunde))).scalars().all()
    return wp, tz, zeilen


def _drift_logs(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "Drift" in r.getMessage()]


@pytest.mark.asyncio
async def test_m3_aggregate_day_vergangener_tag_geraetewerte_je_stunde(db, ha_verbindung, caplog):
    wp, tz, zeilen = await _aggregiere_lab_lage(db, caplog, TAG)

    mit_wp = {z.stunde: (z.komponenten or {}).get(f"waermepumpe_{wp.id}") for z in zeilen
              if (z.komponenten or {}).get(f"waermepumpe_{wp.id}") is not None}
    assert mit_wp == {11: -1.0, 12: -1.0}, "Gerätewerte je Stunde aus der MQTT-Kurve (vorher: keine)"
    assert sum(z.waermepumpe_kw or 0 for z in zeilen) == pytest.approx(2.0)
    assert tz.komponenten_kwh[f"waermepumpe_{wp.id}"] == pytest.approx(2.0)
    assert _drift_logs(caplog) == []


@pytest.mark.asyncio
async def test_m3_laufender_tag_wie_standalone_mit_zuordnung(db, ha_verbindung, caplog, monkeypatch):
    """Am laufenden Tag trägt die Mischform-Anlage jetzt Gerätewerte je Stunde, und ihr WP-Tageswert ist die Σ der
    Kurve — genau wie bei einer Standalone-Anlage mit `live`-Zuordnung (Snapshot-Pfad ohne Tageswert am laufenden Tag,
    #290 Bug B). Die Σ trägt die Senke mit Vorzeichen (−2,0); die Komponenten-Invariante vergleicht sie mit den
    positiven Zählerstunden (+2,0) — die Drift-Warnung des laufenden Tages bleibt deshalb (vorher «tatsächlich 0»,
    jetzt «tatsächlich −2,0»), wie sie für Standalone mit Zuordnung schon vor S4 stand. Benannt im Baubericht S4
    (Halt M-3), nicht in dieser Sitzung geändert."""
    from backend.services.energie_profil import _helpers, aggregator

    class _Heute(date):
        @classmethod
        def today(cls):
            return TAG

    monkeypatch.setattr(aggregator, "date", _Heute)
    monkeypatch.setattr(ltv, "datetime", _feste_uhr_klasse(HEUTE_MITTAG))
    monkeypatch.setattr(_helpers, "_tage_zurueck", lambda tag: (TAG - tag).days)

    wp, tz, zeilen = await _aggregiere_lab_lage(db, caplog, TAG)

    assert {z.stunde for z in zeilen if (z.komponenten or {}).get(f"waermepumpe_{wp.id}") is not None} == {11, 12}
    assert sum(z.waermepumpe_kw or 0 for z in zeilen) == pytest.approx(2.0)
    assert tz.komponenten_kwh == {f"waermepumpe_{wp.id}": -2.0}, "Live-Σ der Kurve (vorher: keine)"


@pytest.mark.asyncio
async def test_m3_tageszeile_traegt_den_wp_tageswert(db, ha_verbindung, caplog):
    """Die Tageszeile in der DB (Leser der Tagessicht) — nicht nur das Rückgabeobjekt."""
    wp, _, _ = await _aggregiere_lab_lage(db, caplog, TAG)
    gespeichert = (await db.execute(select(TagesZusammenfassung).where(TagesZusammenfassung.datum == TAG))).scalars().one()
    assert gespeichert.komponenten_kwh[f"waermepumpe_{wp.id}"] == pytest.approx(2.0)
