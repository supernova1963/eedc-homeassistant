"""Tests für die Energie-kWh-Schleife der Connector-Bridge (T4).

Die Bridge wandelt einen `MeterSnapshot` in EEDC-Energy-Inbound-Topics um.
Kern-Invariante (load-bearing, [[project_kwp_verteilung_aggregator]]):
per-Investition (`energy/inv/{id}/…`) ist Pflicht; `pv_gesamt_kwh` wird NUR
als Fallback publisht, wenn keine PV-Investition zugeordnet ist — sonst zwingt
es die Aggregation in die fixe kWp-Verteilung. Nur non-None-Felder gehen raus.
"""

from backend.services.connector_mqtt_bridge import ConnectorMqttBridge, ConnectorTarget
from backend.services.connectors.base import MeterSnapshot

class FakeClient:
    """Sammelt publish()-Aufrufe als (topic, payload)-Tupel."""

    def __init__(self):
        self.published: list[tuple[str, str]] = []

    async def publish(self, topic, payload):
        self.published.append((topic, str(payload)))

def _bridge() -> ConnectorMqttBridge:
    return ConnectorMqttBridge(mqtt_host="localhost", mqtt_port=1883)

def _target(field_inv_map: dict | None = None) -> ConnectorTarget:
    return ConnectorTarget(
        anlage_id=1,
        inv_id=None,
        connector_id="dummy",
        host="h",
        username="u",
        password="p",
        field_inv_map=field_inv_map or {},
    )

def _topics(client: FakeClient) -> dict[str, str]:
    return {t: p for t, p in client.published}

async def test_pv_zugeordnet_geht_per_investition_kein_gesamt():
    """PV zugeordnet → inv-Topic, KEIN pv_gesamt_kwh (Fallback-Falle vermeiden)."""
    client = FakeClient()
    meters = MeterSnapshot(timestamp="t", pv_erzeugung_kwh=123.4)
    await _bridge()._publish_energy(client, _target({"pv": 14}), meters)

    topics = _topics(client)
    assert topics["eedc/1/energy/inv/14/pv_erzeugung_kwh"] == "123.4"
    assert "eedc/1/energy/pv_gesamt_kwh" not in topics

async def test_pv_ohne_zuordnung_faellt_auf_gesamt_zurueck():
    """Keine PV-Investition zugeordnet → Fallback pv_gesamt_kwh (anlagenweit)."""
    client = FakeClient()
    meters = MeterSnapshot(timestamp="t", pv_erzeugung_kwh=50.0)
    await _bridge()._publish_energy(client, _target({}), meters)

    topics = _topics(client)
    assert topics["eedc/1/energy/pv_gesamt_kwh"] == "50.0"
    assert not any("inv/" in t for t in topics)

async def test_speicher_zugeordnet_ladung_und_entladung():
    """Speicher-Zuordnung → ladung_kwh + entladung_kwh auf die Investition."""
    client = FakeClient()
    meters = MeterSnapshot(
        timestamp="t", batterie_ladung_kwh=30.0, batterie_entladung_kwh=20.0
    )
    await _bridge()._publish_energy(client, _target({"speicher": 15}), meters)

    topics = _topics(client)
    assert topics["eedc/1/energy/inv/15/ladung_kwh"] == "30.0"
    assert topics["eedc/1/energy/inv/15/entladung_kwh"] == "20.0"

async def test_speicher_ohne_zuordnung_wird_verworfen():
    """Batterie-Werte ohne Zuordnung → kein Topic (kein anlagenweites Basis-Topic)."""
    client = FakeClient()
    meters = MeterSnapshot(
        timestamp="t", batterie_ladung_kwh=30.0, batterie_entladung_kwh=20.0
    )
    await _bridge()._publish_energy(client, _target({}), meters)

    assert client.published == []

async def test_grid_immer_anlagenweit():
    """Einspeisung/Netzbezug sind anlagenweit — immer Basis-Topics, nie inv."""
    client = FakeClient()
    meters = MeterSnapshot(timestamp="t", einspeisung_kwh=11.0, netzbezug_kwh=22.0)
    await _bridge()._publish_energy(client, _target({"pv": 14}), meters)

    topics = _topics(client)
    assert topics["eedc/1/energy/einspeisung_kwh"] == "11.0"
    assert topics["eedc/1/energy/netzbezug_kwh"] == "22.0"

async def test_wallbox_zugeordnet():
    """Wallbox-Ladung → ladung_kwh auf die Wallbox-Investition."""
    client = FakeClient()
    meters = MeterSnapshot(timestamp="t", wallbox_ladung_kwh=7.5)
    await _bridge()._publish_energy(client, _target({"wallbox": 12}), meters)

    assert _topics(client)["eedc/1/energy/inv/12/ladung_kwh"] == "7.5"

async def test_nur_non_none_felder_publisht():
    """Fehlende Felder (None) erzeugen kein Topic."""
    client = FakeClient()
    meters = MeterSnapshot(timestamp="t", pv_erzeugung_kwh=10.0)  # nur PV
    await _bridge()._publish_energy(client, _target({"pv": 14, "wallbox": 12}), meters)

    topics = _topics(client)
    assert list(topics.keys()) == ["eedc/1/energy/inv/14/pv_erzeugung_kwh"]
