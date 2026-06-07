"""
#655 — MQTT-Outbound konsolidiert: ein Pfad, echte success/failed-Zahlen.

Regression gegen den `published`-Key-Bug: Scheduler-Auto-Publish und manuelle
Route meldeten „erfolg=True, 0 Sensoren" über einen nicht existenten Dict-Key.
Jetzt liefert `publish_anlage_sensors` die realen Zahlen, und der Broker wird
konsistent aufgelöst (Override → ENV → Default).
"""

import pytest

from backend.services import ha_mqtt_sync


class _FakeClient:
    """Ersetzt MQTTClient: meldet verfügbar + feste Publish-Statistik."""
    is_available = True

    def __init__(self, *args, **kwargs):
        pass

    async def publish_all_sensors(self, sensor_values, anlage_id, anlage_name):
        return {"total": 3, "success": 2, "failed": 1, "errors": ["x: ConnectionRefusedError: nope"]}


class _Anlage:
    id = 7
    anlagenname = "Testanlage"


async def test_publish_anlage_sensors_liefert_echte_zahlen(monkeypatch):
    monkeypatch.setattr(ha_mqtt_sync, "MQTTClient", _FakeClient)
    import backend.api.routes.ha_export as ha_export

    async def fake_calc(db, anlage):
        return [object(), object(), object()]

    monkeypatch.setattr(ha_export, "calculate_anlage_sensors", fake_calc)

    r = await ha_mqtt_sync.publish_anlage_sensors(None, _Anlage())

    assert r["available"] is True and r["no_data"] is False
    assert (r["total"], r["success"], r["failed"]) == (3, 2, 1)
    # Regression #655: kein „published"-Key, echte Fehlerzahl + Grund sichtbar
    assert "published" not in r
    assert r["failed"] == 1
    assert r["errors"] and "ConnectionRefusedError" in r["errors"][0]


async def test_publish_anlage_sensors_keine_daten(monkeypatch):
    monkeypatch.setattr(ha_mqtt_sync, "MQTTClient", _FakeClient)
    import backend.api.routes.ha_export as ha_export

    async def fake_calc(db, anlage):
        return []

    monkeypatch.setattr(ha_export, "calculate_anlage_sensors", fake_calc)

    r = await ha_mqtt_sync.publish_anlage_sensors(None, _Anlage())
    assert r["no_data"] is True
    assert r["success"] == 0 and r["total"] == 0


async def test_publish_anlage_sensors_mqtt_nicht_verfuegbar(monkeypatch):
    class _Unavailable(_FakeClient):
        is_available = False

    monkeypatch.setattr(ha_mqtt_sync, "MQTTClient", _Unavailable)
    r = await ha_mqtt_sync.publish_anlage_sensors(None, _Anlage())
    assert r["available"] is False


async def test_publish_all_sensors_sammelt_fehlergruende(monkeypatch):
    """#655: ein Publish-Fehler wird nicht verschluckt, sondern mit Grund gemeldet."""
    pytest.importorskip("aiomqtt")
    from backend.services.mqtt_client import MQTTClient
    from backend.services.ha_sensors_export import SensorDefinition, SensorValue, SensorCategory

    client = MQTTClient()

    async def boom(*args, **kwargs):
        raise ConnectionRefusedError("Broker nicht erreichbar")

    # Discovery wirft → Grund muss in errors landen, failed hochzählen
    monkeypatch.setattr(client, "publish_sensor_discovery", boom)

    sd = SensorDefinition(
        key="autarkie_prozent", name="Autarkie", unit="%", icon="mdi:flash",
        category=SensorCategory.ENERGIE, formel="x",
    )
    sv = SensorValue(definition=sd, value=42.0)

    result = await client.publish_all_sensors([sv], anlage_id=1, anlage_name="Test")

    assert result["failed"] == 1 and result["success"] == 0
    assert result["errors"]
    assert "ConnectionRefusedError" in result["errors"][0]
    assert "autarkie_prozent" in result["errors"][0]


def test_resolve_mqtt_config_leeres_objekt_faellt_auf_env(monkeypatch):
    monkeypatch.setenv("MQTT_HOST", "10.0.0.9")
    monkeypatch.setenv("MQTT_PORT", "8883")
    monkeypatch.delenv("MQTT_USER", raising=False)
    monkeypatch.delenv("MQTT_PASSWORD", raising=False)

    # Leeres Frontend-Config (alle None) → ENV, NICHT core-mosquitto (#655)
    c = ha_mqtt_sync.resolve_mqtt_config()
    assert c.host == "10.0.0.9"
    assert c.port == 8883

    # Expliziter Override gewinnt über ENV
    c2 = ha_mqtt_sync.resolve_mqtt_config(host="broker.local", port=1884)
    assert c2.host == "broker.local"
    assert c2.port == 1884
