"""
Datenquellen-V4 B8-2 — evidenz-basierte Lazy-Auflösung beim `/felder`-Aufruf.

Deckt Gernots 3-Stufen-Regel (2026-07-16) ab:
1. HA-Sensor zugeordnet → HA (keine Inhaltsprüfung)
2. sonst Gateway-Topic → Gateway (keine Inhaltsprüfung)
3. sonst Inbound-mit-Wert → Inbound; sonst → keine

Kern-Invariante: POSITIVE Evidenz (HA/Gateway/Inbound-mit-Wert) wird additiv
festgeschrieben, damit Anzeige UND Read-Through (C2a/C2b) übereinstimmen; ein
stummes Inbound-Topic wird NUR als „keine" ANGEZEIGT, NIE auto-persistiert
(self-healing, kein auto-keine-Ballast). Bestehende explizite Einträge (auch
bewusstes „keine") bleiben unberührt; wiederholter Aufruf ist idempotent.
"""


import pytest
from sqlalchemy import select

from backend.api.routes import datenquellen as dq
from backend.api.routes.datenquellen import get_datenquellen_felder
from backend.models.anlage import Anlage
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping
from backend.services.datenquellen_resolver import resolve_effektive_quelle
from backend.tests import factories


# ─── resolve_effektive_quelle (pur — Entscheidungstabelle) ───────────────

class _FakeGW:
    def __init__(self, id, aktiv=True):
        self.id = id
        self.aktiv = aktiv


_MAPPING = {
    "basis": {
        "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.einsp"},
        "netzbezug": {"strategie": "manuell"},  # kein HA-Sensor
    },
}
_BL: dict = {}
_IL: dict = {}
_TOPIC_EINSP = "eedc/1_Demo/energy/einspeisung_kwh"
_TOPIC_NETZ = "eedc/1_Demo/energy/netzbezug_kwh"


def test_stufe1_ha_ohne_inhaltspruefung():
    """HA-Sensor zugeordnet → HA, unabhängig von einem Inbound-Wert."""
    display, persist, gw = resolve_effektive_quelle(
        "basis_energy_einspeisung_kwh", _TOPIC_EINSP, _MAPPING, _BL, _IL,
        {}, "ha_app", inbound_hat_wert=False,
    )
    assert display == "ha_app"
    assert persist == {"quelle": "ha_app", "entity_id": "sensor.einsp"}
    assert gw is None


def test_stufe1_ha_meldet_paralleles_gateway_zur_deaktivierung():
    """HA gewinnt vor Gateway (§2h) → die parallele Gateway-Zeile wird gemeldet."""
    gwrow = _FakeGW(id=7)
    display, persist, gw = resolve_effektive_quelle(
        "basis_energy_einspeisung_kwh", _TOPIC_EINSP, _MAPPING, _BL, _IL,
        {"energy/einspeisung_kwh": gwrow}, "ha_connector", inbound_hat_wert=True,
    )
    assert display == "ha_connector"
    assert persist["quelle"] == "ha_connector"
    assert gw is gwrow  # zur §2h-Deaktivierung zurückgegeben


def test_stufe2_gateway_ohne_inhaltspruefung():
    """Kein HA, aber Gateway-Topic → Gateway (auch ohne Inbound-Wert)."""
    gwrow = _FakeGW(id=9)
    display, persist, gw = resolve_effektive_quelle(
        "basis_energy_netzbezug_kwh", _TOPIC_NETZ, _MAPPING, _BL, _IL,
        {"energy/netzbezug_kwh": gwrow}, "ha_app", inbound_hat_wert=False,
    )
    assert display == "mqtt_gateway"
    assert persist == {"quelle": "mqtt_gateway", "mapping_id": 9}
    assert gw is None


def test_stufe3_inbound_mit_wert_persistiert():
    """Kein HA/Gateway, Inbound liefert Wert → Inbound (positive Evidenz)."""
    display, persist, gw = resolve_effektive_quelle(
        "basis_energy_netzbezug_kwh", _TOPIC_NETZ, _MAPPING, _BL, _IL,
        {}, "ha_app", inbound_hat_wert=True,
    )
    assert display == "mqtt_inbound_standard"
    assert persist == {"quelle": "mqtt_inbound_standard"}
    assert gw is None


def test_stufe3_inbound_stumm_keine_nicht_persistiert():
    """Kein HA/Gateway, Inbound stumm → „keine" NUR anzeigen, NICHT persistieren."""
    display, persist, gw = resolve_effektive_quelle(
        "basis_energy_netzbezug_kwh", _TOPIC_NETZ, _MAPPING, _BL, _IL,
        {}, "ha_app", inbound_hat_wert=False,
    )
    assert display == "keine"
    assert persist is None  # ← self-healing: kein auto-keine-Ballast
    assert gw is None


# ─── End-to-End über den /felder-Handler ─────────────────────────────────

async def _anlage_mit_pv(db, sensor_mapping: dict) -> Anlage:
    return await factories.anlage_mit_pv(db, sensor_mapping)


class _FakeCache:
    """Minimaler MQTT-Inbound-Cache: nur `_energy`/`_live` wie `_cache_wert` erwartet."""
    def __init__(self, aid, energy=None, live=None):
        self._energy = {aid: energy or {}}
        self._live = {aid: live or {}}


class _FakeSvc:
    def __init__(self, cache):
        self.cache = cache


def _felder_flat(resp) -> dict:
    out = {}
    for g in resp["gruppen"]:
        for f in g["felder"]:
            out[f["id"]] = f
    return out


@pytest.mark.asyncio
async def test_felder_ha_first_persistiert_und_deaktiviert_gateway(db):
    """HA-gemapptes Feld → HA persistiert; paralleles Gateway §2h deaktiviert."""
    a = await _anlage_mit_pv(db, {
        "investitionen": {
            "1": {
                "felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}},
                "live": {"leistung_w": "sensor.pv_w"},
            },
        },
    })
    gw = MqttGatewayMapping(
        anlage_id=a.id, quell_topic="shellies/em/power",
        ziel_key="live/inv/1_PV/leistung_w", aktiv=True,
    )
    db.add(gw)
    await db.flush()

    resp = await get_datenquellen_felder(a.id, db)
    felder = _felder_flat(resp)
    quellen = a.sensor_mapping.get("quellen", {})

    # HA-first materialisiert (Add-on → ha_app / Standalone → ha_connector)
    assert quellen["inv_energy_1_pv_erzeugung_kwh"]["quelle"] in ("ha_app", "ha_connector")
    assert quellen["inv_energy_1_pv_erzeugung_kwh"]["entity_id"] == "sensor.pv"
    assert quellen["inv_live_1_leistung_w"]["quelle"] in ("ha_app", "ha_connector")
    # Anzeige stimmt mit Persistenz überein
    assert felder["inv_live_1_leistung_w"]["quelle"] in ("ha_app", "ha_connector")
    assert felder["inv_live_1_leistung_w"]["ha_entity"] == "sensor.pv_w"
    # §2h: paralleles Gateway deaktiviert (nicht gelöscht)
    assert gw.aktiv is False
    still = (await db.execute(
        select(MqttGatewayMapping).where(MqttGatewayMapping.id == gw.id)
    )).scalar_one()
    assert still is not None


@pytest.mark.asyncio
async def test_felder_stummes_inbound_zeigt_keine_ohne_persistenz(db):
    """Kein HA/Gateway, kein Cache-Wert → alle Felder „keine", NICHTS persistiert."""
    a = await _anlage_mit_pv(db, {})  # keine HA-Sensoren

    resp = await get_datenquellen_felder(a.id, db)
    felder = _felder_flat(resp)

    assert felder, "es sollten Felder aufgelistet sein"
    assert all(f["quelle"] == "keine" for f in felder.values())
    # Self-healing: kein auto-keine in der DB
    assert not a.sensor_mapping.get("quellen")


@pytest.mark.asyncio
async def test_felder_inbound_mit_wert_persistiert_nur_gefuetterte(db, monkeypatch):
    """Nur Felder mit tatsächlichem Inbound-Wert → Inbound persistiert; Rest keine."""
    a = await _anlage_mit_pv(db, {})
    # Nur netzbezug_kwh liefert einen Wert im Inbound-Cache.
    cache = _FakeCache(a.id, energy={"netzbezug_kwh": (5.5, None)})
    monkeypatch.setattr(dq, "get_mqtt_inbound_service", lambda: _FakeSvc(cache), raising=False)
    # Der Handler importiert den Service lokal aus dem Service-Modul → dort patchen.
    import backend.services.mqtt_inbound_service as mis
    monkeypatch.setattr(mis, "get_mqtt_inbound_service", lambda: _FakeSvc(cache))

    resp = await get_datenquellen_felder(a.id, db)
    felder = _felder_flat(resp)
    quellen = a.sensor_mapping.get("quellen", {})

    # Gefüttertes Feld → Inbound (persistiert), Anzeige zeigt den Wert
    assert quellen.get("basis_energy_netzbezug_kwh", {}).get("quelle") == "mqtt_inbound_standard"
    assert felder["basis_energy_netzbezug_kwh"]["quelle"] == "mqtt_inbound_standard"
    assert felder["basis_energy_netzbezug_kwh"]["wert"] == 5.5
    # Ein stummes Feld bleibt keine + un-persistiert
    assert "basis_energy_einspeisung_kwh" not in quellen
    assert felder["basis_energy_einspeisung_kwh"]["quelle"] == "keine"


@pytest.mark.asyncio
async def test_felder_respektiert_explizite_wahl_und_idempotent(db):
    """Bewusstes „keine" bleibt; zweiter Aufruf schreibt nichts Neues."""
    a = await _anlage_mit_pv(db, {
        "investitionen": {
            "1": {"felder": {"pv_erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.pv"}}},
        },
        "quellen": {
            "inv_energy_1_pv_erzeugung_kwh": {"quelle": "keine"},  # bewusste Wahl
        },
    })

    resp1 = await get_datenquellen_felder(a.id, db)
    felder1 = _felder_flat(resp1)
    # Bewusste keine-Wahl NICHT auf HA überschrieben
    assert a.sensor_mapping["quellen"]["inv_energy_1_pv_erzeugung_kwh"] == {"quelle": "keine"}
    assert felder1["inv_energy_1_pv_erzeugung_kwh"]["quelle"] == "keine"

    q_nach_1 = dict(a.sensor_mapping["quellen"])
    # Zweiter Aufruf: idempotent — dieselbe quellen-Map
    await get_datenquellen_felder(a.id, db)
    assert dict(a.sensor_mapping["quellen"]) == q_nach_1
