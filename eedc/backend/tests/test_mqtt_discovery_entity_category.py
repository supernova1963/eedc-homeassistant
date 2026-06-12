"""
HA-Export: Status-Sensoren als entity_category "diagnostic" (rapahl-Folge).

Die vier LETZTER_IMPORT_SENSOREN landen in HA im Diagnose-Bereich des
eedc-Geräts, alle übrigen Sensoren bleiben unkategorisiert. Der Payload-Builder
darf das Feld nur setzen, wenn die Definition es vorgibt — sonst würde HA
jede Entität umkategorisieren.
"""

from backend.services.ha_sensors_export import (
    LETZTER_IMPORT_SENSOREN,
    get_all_sensor_definitions,
)
from backend.services.mqtt_client import MQTTClient

STATUS_KEYS = {s.key for s in LETZTER_IMPORT_SENSOREN}


def test_status_sensoren_haben_diagnostic_im_discovery_payload():
    client = MQTTClient()
    assert STATUS_KEYS == {
        "letzter_import_jahr",
        "letzter_import_monat",
        "letzter_import_monat_name",
        "anzahl_monate_erfasst",
    }
    for sensor in LETZTER_IMPORT_SENSOREN:
        payload = client._build_discovery_payload(sensor, anlage_id=1, anlage_name="Test")
        assert payload["entity_category"] == "diagnostic", sensor.key


def test_alle_anderen_sensoren_ohne_entity_category():
    client = MQTTClient()
    for sensor in get_all_sensor_definitions():
        if sensor.key in STATUS_KEYS:
            continue
        payload = client._build_discovery_payload(sensor, anlage_id=1, anlage_name="Test")
        assert "entity_category" not in payload, sensor.key
