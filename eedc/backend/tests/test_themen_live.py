"""Themen-Kacheln (4.2.0, Bauplan TH-E1 §1.3/§1.4/§1.7) — Live-Pfad, MQTT-Inbound, Gateway.

* `betriebsmodus_live.lade_themen_live`: HA in **einem** gebündelten Abruf (`fetch_selected_states`) für alle
  Themen-Entitäten aller Geräte, MQTT aus dem Inbound-Cache (``thema_<e>``), «keine» schließt MQTT aus,
  ``unknown``/``unavailable``/leer ⇒ der Eintrag fehlt; derselbe 60-s-Takt (`TaktErgebnis`).
* `LiveDashboardResponse.themen`: ``None`` ohne einen Wert (P9), sonst Store-Reihenfolge, Themen/Einträge ohne Wert
  fehlen (P1/P2).
* Inbound-Weiche (S3/P6): ein Wort auf ``thema_e1`` ⇒ roher String im Cache, «leer ist ein Wert», kein Zustands- und
  kein Mittelwert-Fenster; ein Wort auf ``leistung_w`` bleibt verworfen. Gateway: Text an ``thema_<e>``, Wort auf
  ``leistung_w`` ⇒ ``transform_fehler``. Der Leistungspfad nimmt ``thema_<e>`` nicht in ``inv_values`` (P9).

Schwesterdateien: test_themen_store.py, test_themen_routen.py.
"""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from backend.api.routes import live_dashboard
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services import betriebsmodus_live as bml
from backend.services import live_power_service as lps
from backend.services import mqtt_gateway_service as gws
from backend.services import mqtt_inbound_service as mis
from backend.services import themen_store as store


@pytest.fixture(autouse=True)
def _takt_leer():
    bml.cache_leeren()
    yield
    bml.cache_leeren()


class _Svc:
    def __init__(self, cache):
        self.cache = cache
        self._running = True


@pytest.fixture
def inbound(monkeypatch):
    cache = mis.MqttInboundCache()
    monkeypatch.setattr(mis, "get_mqtt_inbound_service", lambda: _Svc(cache))
    return cache


@pytest.fixture
def ha(monkeypatch):
    """HA mit gestellten States; ``ha.abrufe`` zählt die Batch-Aufrufe und ihre Entitäten."""
    stand = SimpleNamespace(states={}, abrufe=[])

    async def _verbindung(db):  # noqa: ARG001
        return "http://ha/api", "token", "ha_app"

    async def _fetch(api_url, token, entity_ids, **kw):  # noqa: ARG001
        stand.abrufe.append(sorted(entity_ids))
        return {eid: stand.states.get(eid) for eid in entity_ids}

    monkeypatch.setattr("backend.services.ha_connection.resolve_ha_connection", _verbindung)
    monkeypatch.setattr("backend.services.ha_state_service.fetch_selected_states", _fetch)
    return stand


async def _anlage(db, themen: dict[str, list[tuple[str, list[str]]]], quellen: dict | None = None):
    """``themen``: Gerätename → [(Thema, [Labels])]; Typ e-auto, Wallbox für «WB…», Speicher für «Akku»."""
    a = Anlage(anlagenname="Live", leistung_kwp=10.0, sensor_mapping={})
    db.add(a)
    await db.flush()
    mapping: dict = {}
    invs = {}
    for name, liste in themen.items():
        typ = "speicher" if name == "Akku" else "wallbox" if name.startswith("WB") else "e-auto"
        inv = Investition(anlage_id=a.id, typ=typ, bezeichnung=name, anschaffungsdatum=date(2024, 1, 1))
        db.add(inv)
        await db.flush()
        invs[name] = inv
        for thema, labels in liste:
            t = store.thema_anlegen(mapping, inv.id, thema)
            for label in labels:
                store.eintrag_anlegen(mapping, inv.id, t["id"], label)
    mapping["quellen"] = {k.format(**{n: i.id for n, i in invs.items()}): v for k, v in (quellen or {}).items()}
    a.sensor_mapping = mapping
    await db.flush()
    return a, invs


def _ha(entity: str) -> dict:
    return {"quelle": "ha_app", "entity_id": entity}


# ── lade_themen_live ──────────────────────────────────────────────────────────

async def test_ha_ein_gebuendelter_abruf_fuer_alle_geraete(db, ha, inbound):
    a, invs = await _anlage(
        db, {"Ioniq": [("Zustand", ["Türen", "Reifen"])], "WB Garage": [("Plan", ["Planzeit"])]},
        {"inv_thema_{Ioniq}_e2": _ha("lock.carport"), "inv_thema_{Ioniq}_e3": _ha("sensor.reifen"),
         "inv_thema_{WB Garage}_e2": _ha("sensor.plan")},
    )
    ha.states = {
        "lock.carport": {"state": "locked", "last_changed": "2026-11-01T06:20:43+00:00", "attributes": {}},
        "sensor.reifen": {"state": "2.4", "attributes": {"unit_of_measurement": "bar", "device_class": "pressure"}},
        "sensor.plan": {"state": "2026-11-02T07:00:00+00:00", "attributes": {"device_class": "timestamp"}},
    }
    werte = await bml.lade_themen_live(db, a)
    assert ha.abrufe == [["lock.carport", "sensor.plan", "sensor.reifen"]], "ein Abruf für alle Themen-Entitäten"
    io, wb = invs["Ioniq"].id, invs["WB Garage"].id
    assert werte[(io, "e2")] == bml.ThemenWert("locked", "", "2026-11-01T06:20:43+00:00", None, "ha", "lock.carport")
    assert werte[(io, "e3")] == bml.ThemenWert("2.4", "bar", None, "pressure", "ha", "sensor.reifen")
    assert werte[(wb, "e2")].device_class == "timestamp"
    # Derselbe 60-s-Takt: ein zweiter Leser holt nichts neu.
    await bml.lade_themen_live(db, a)
    await bml.lade_zustaende_live(db, a)
    assert len(ha.abrufe) == 1


@pytest.mark.parametrize("state", ["unknown", "unavailable", "", "  "])
async def test_p7_ohne_wert_fehlt_der_eintrag(db, ha, inbound, state):
    a, _invs = await _anlage(db, {"Ioniq": [("Zustand", ["Türen"])]}, {"inv_thema_{Ioniq}_e2": _ha("lock.x")})
    ha.states = {"lock.x": {"state": state, "attributes": {}}}
    assert await bml.lade_themen_live(db, a) == {}


async def test_mqtt_aus_dem_cache_keine_schliesst_aus(db, ha, inbound):
    a, invs = await _anlage(
        db, {"Ioniq": [("Zustand", ["Türen", "Fenster", "Licht"])]},
        {"inv_thema_{Ioniq}_e3": {"quelle": "keine"}, "inv_thema_{Ioniq}_e4": {"quelle": "mqtt_gateway", "mapping_id": 1}},
    )
    io = invs["Ioniq"].id
    for e, wert in (("e2", "locked"), ("e3", "zu"), ("e4", "an")):
        inbound.on_message(f"eedc/{a.id}/live/inv/{io}/thema_{e}", wert)
    werte = await bml.lade_themen_live(db, a)
    assert {k: v.wert for k, v in werte.items()} == {(io, "e2"): "locked", (io, "e4"): "an"}
    assert werte[(io, "e2")].quelle == "mqtt" and werte[(io, "e2")].zeitpunkt is not None
    assert ha.abrufe == [], "ohne HA-Zuordnung kein HA-Abruf"


async def test_th_e2_kennung_ha_entity_mqtt_topic(db, ha, inbound):
    """TH-E2 (Entscheid Master 1.11.2026): ``kennung`` = ``entity_id`` (HA) bzw. das volle Inbound-Topic in der Form der
    Topic-Registry (MQTT) — für den Tooltip «‹kennung› · Stand» der Karte «Themen»."""
    a, invs = await _anlage(
        db, {"Ioniq 5": [("Zustand", ["Türen", "Fenster"])]}, {"inv_thema_{Ioniq 5}_e2": _ha("lock.carport")},
    )
    io = invs["Ioniq 5"].id
    ha.states = {"lock.carport": {"state": "locked", "attributes": {}}}
    inbound.on_message(f"eedc/{a.id}/live/inv/{io}/thema_e3", "zu")
    werte = await bml.lade_themen_live(db, a)
    assert werte[(io, "e2")].kennung == "lock.carport"
    assert werte[(io, "e3")].kennung == f"eedc/{a.id}_Live/live/inv/{io}_Ioniq_5/thema_e3"
    # Dieselbe Form wie die Topic-Registry (eine Quelle für Topic-Liste, Gateway-Ziel und Tooltip).
    from backend.services.mqtt_topic_registry import build_expected_topics
    topics = {t["topic"] for t in await build_expected_topics(db, a)}
    assert werte[(io, "e3")].kennung in topics
    themen = await live_dashboard._themen_live(db, a)
    assert [e["kennung"] for e in themen[0]["eintraege"]] == ["lock.carport", werte[(io, "e3")].kennung]


async def test_mqtt_leer_im_cache_fehlt_live(db, ha, inbound):
    a, invs = await _anlage(db, {"Ioniq": [("Zustand", ["Türen"])]})
    inbound.on_message(f"eedc/{a.id}/live/inv/{invs['Ioniq'].id}/thema_e2", "")
    assert inbound.get_all_live_inv(a.id)[str(invs["Ioniq"].id)]["thema_e2"] == "", "leer ist im Cache ein Wert"
    assert await bml.lade_themen_live(db, a) == {}


async def test_typ_ohne_ueberblick_hat_keine_themen(db, ha, inbound):
    a, invs = await _anlage(db, {"Akku": []})
    mapping = dict(a.sensor_mapping)
    store.thema_anlegen(mapping, invs["Akku"].id, "von Hand")
    store.eintrag_anlegen(mapping, invs["Akku"].id, "t1", "x")
    a.sensor_mapping = mapping
    inbound.on_message(f"eedc/{a.id}/live/inv/{invs['Akku'].id}/thema_e2", "y")
    assert await bml.lade_themen_live(db, a) == {}


# ── Antwort der Live-Route ────────────────────────────────────────────────────

async def test_p9_ohne_themen_ist_themen_none(db, ha, inbound):
    a, _invs = await _anlage(db, {"Ioniq": []})
    assert await live_dashboard._themen_live(db, a) is None
    a2, _ = await _anlage(db, {"Ioniq": [("Zustand", ["Türen"])]})
    assert await live_dashboard._themen_live(db, a2) is None, "Themen ohne Wert ⇒ None"


async def test_p1_p2_reihenfolge_und_nur_mit_wert(db, ha, inbound):
    a, invs = await _anlage(db, {"Ioniq": [("Leer", ["a"]), ("Zustand", ["Türen", "Reifen", "Licht"])]})
    io = invs["Ioniq"].id
    for e, wert in (("e5", "2.4"), ("e6", "an")):  # e4 (Türen) ohne Wert
        inbound.on_message(f"eedc/{a.id}/live/inv/{io}/thema_{e}", wert)
    themen = await live_dashboard._themen_live(db, a)
    assert [(t["name"], [e["label"] for e in t["eintraege"]]) for t in themen] == [("Zustand", ["Reifen", "Licht"])]
    antwort = live_dashboard.LiveDashboardResponse(
        **{**lps.LivePowerService._empty_response(None, a), "themen": themen},
    ).model_dump()
    assert antwort["themen"][0]["eintraege"][0] == {
        "id": "e5", "label": "Reifen", "wert": "2.4", "einheit": "", "zeitpunkt": antwort["themen"][0]["eintraege"][0]["zeitpunkt"],
        "device_class": None, "quelle": "mqtt", "kennung": f"eedc/{a.id}_Live/live/inv/{io}_Ioniq/thema_e5",
    }


async def test_route_setzt_themen_neben_dem_leistungspfad(db, ha, inbound, monkeypatch):
    a, invs = await _anlage(db, {"Ioniq": [("Zustand", ["Türen"])]})

    class _Service:
        async def get_live_data(self, anlage, db):  # noqa: ARG002
            return lps.LivePowerService._empty_response(None, anlage)

    monkeypatch.setattr(live_dashboard, "get_live_power_service", lambda: _Service())
    antwort = await live_dashboard.get_live_data(a.id, demo=False, db=db)
    assert antwort["themen"] is None
    bml.cache_leeren()
    inbound.on_message(f"eedc/{a.id}/live/inv/{invs['Ioniq'].id}/thema_e2", "locked")
    antwort = await live_dashboard.get_live_data(a.id, demo=False, db=db)
    assert antwort["themen"][0]["eintraege"][0]["wert"] == "locked"
    # Die Demo trägt seit dem Galerie-Auftrag 1.11.2026 feste Themen je Gerätetyp (nicht aus dem Store, sondern aus
    # `_DEMO_THEMEN`; Probe `test_demo_hubs_vollstaendig.py`) — der echte Pfad oben bleibt davon unberührt.
    demo = live_dashboard.LiveDashboardResponse(**live_dashboard._generate_demo_data(1, "Demo"))
    assert {t.investition_id for t in demo.themen} == {4, 5, 6}


# ── Inbound, Gateway, Leistungspfad ───────────────────────────────────────────

def test_s3_p6_inbound_legt_den_text_ab_ohne_fenster():
    cache = mis.MqttInboundCache()
    cache.on_message("eedc/3/live/inv/4/thema_e1", " locked ", jetzt=1000.0)
    assert cache.get_all_live_inv(3)["4"]["thema_e1"] == "locked"
    cache.on_message("eedc/3/live/inv/4/thema_e1", "", jetzt=1010.0)
    assert cache.get_all_live_inv(3)["4"]["thema_e1"] == "", "leer ist ein Wert"
    assert cache._zustand_fenster == {} and cache._modus_fenster == {} and cache._mittel_fenster == {}
    # Ein Wort auf einem Zahlenfeld bleibt verworfen.
    cache.on_message("eedc/3/live/inv/4/leistung_w", "locked", jetzt=1020.0)
    assert "leistung_w" not in cache.get_all_live_inv(3)["4"]


class _Client:
    def __init__(self):
        self.gesendet: list[tuple[str, str]] = []

    async def publish(self, topic, payload):
        self.gesendet.append((topic, payload))


def _sende(ziel_key: str, payload: str) -> tuple[list, dict]:
    svc = gws.MqttGatewayService("localhost", 1883)
    svc.load_mappings([gws.GatewayMapping(id=1, anlage_id=3, quell_topic="q/x", ziel_key=ziel_key, faktor=0.001)])
    client = _Client()
    asyncio.run(svc._handle_message(client, SimpleNamespace(topic="q/x", payload=payload.encode())))
    return client.gesendet, svc.get_status()


def test_gateway_reicht_text_an_ein_thema_und_nicht_an_ein_zahlenfeld():
    assert gws._als_text("live/inv/4_Ioniq/thema_e1") is True
    gesendet, status = _sende("live/inv/4_Ioniq/thema_e1", "locked")
    assert gesendet == [("eedc/3/live/inv/4_Ioniq/thema_e1", "locked")] and status["transform_fehler"] == 0
    gesendet, status = _sende("live/inv/4/leistung_w", "locked")
    assert gesendet == [] and status["transform_fehler"] == 1


def test_leistungspfad_nimmt_kein_themen_topic(monkeypatch):
    cache = mis.MqttInboundCache()
    cache.on_message("eedc/3/live/inv/4/thema_e1", "locked")
    cache.on_message("eedc/3/live/inv/5/leistung_w", "1200")
    monkeypatch.setattr(mis, "get_mqtt_inbound_service", lambda: _Svc(cache))
    anlage = SimpleNamespace(id=3, sensor_mapping={})
    _basis, inv_values = lps.LivePowerService()._collect_values(anlage, {}, {}, {})
    assert inv_values == {"5": {"leistung_w": 1200.0}}, "ein Gerät nur mit Themen-Wert fehlt wie ohne Themen"
    # Gegenprobe Bestand: ein Gerät mit einem Zustandsfeld bleibt (leer) stehen wie bisher.
    cache.on_message("eedc/3/live/inv/6/betriebsmodus", "heizen")
    _basis, inv_values = lps.LivePowerService()._collect_values(anlage, {}, {}, {})
    assert inv_values == {"5": {"leistung_w": 1200.0}, "6": {}}
