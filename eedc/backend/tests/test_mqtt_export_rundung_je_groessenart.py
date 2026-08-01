"""
Akzeptanztest: der MQTT-Export liefert kurze Zahlen — je Größenart passend.

Rainer-PN 89905/2: „der Export an HA liefert lange Nachkommastellen, ganze
Zahlen würden reichen". Der Publisher rundete jede Größe gleich (`round(v, 2)`),
egal ob kWh-Jahressumme, Euro-Betrag oder Prozentquote.

Entscheid B7: Rundung **pro Größenart**, EINMAL definiert
(`services/ha_sensors_export.py::runde_exportwert`) — Energie ganzzahlig, Geld
auf Cent, Prozent auf eine Stelle, Leistung mit Stellen. Leitplanke: kein
echter Wert kippt durch die Rundung auf 0 (aus 0,35 kW darf keine 0 werden).

Der Test misst die **erzeugte Payload**, nicht die Hilfsfunktion allein.
"""

from __future__ import annotations

import pytest

from backend.services.ha_sensors_export import (
    SensorCategory,
    SensorDefinition,
    SensorValue,
    get_sensor_definition,
    runde_exportwert,
)


# ---------------------------------------------------------------------------
# aiomqtt-Doppel: sammelt (topic, payload) statt zu verbinden
# ---------------------------------------------------------------------------
class _FakeSession:
    def __init__(self, sink: list):
        self._sink = sink

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def publish(self, topic, payload=None, retain=False, **kwargs):
        self._sink.append((topic, payload))


class _FakeAiomqtt:
    def __init__(self):
        self.published: list = []

    def Client(self, **kwargs):  # noqa: N802 — Name kommt von aiomqtt
        return _FakeSession(self.published)


def _sv(key: str, value) -> SensorValue:
    definition = get_sensor_definition(key)
    assert definition is not None, key
    return SensorValue(definition=definition, value=value)


async def _publish(monkeypatch, sensor_values) -> dict[str, str]:
    """Publiziert die Werte und gibt {sensor_key: State-Payload} zurück."""
    import backend.services.mqtt_client as mqtt_mod

    fake = _FakeAiomqtt()
    monkeypatch.setattr(mqtt_mod, "aiomqtt", fake)
    monkeypatch.setattr(mqtt_mod, "MQTT_AVAILABLE", True)

    client = mqtt_mod.MQTTClient()
    result = await client.publish_all_sensors(sensor_values, anlage_id=1, anlage_name="Test")
    assert result["failed"] == 0, result["errors"]

    return {
        topic.rsplit("/", 1)[-1]: payload
        for topic, payload in fake.published
        if topic.startswith("eedc/anlage/1/") and not topic.endswith("/attributes")
    }


async def test_payload_rundet_je_groessenart(monkeypatch):
    """Je Größenart eine Zusicherung — direkt an der publizierten Payload."""
    kw_definition = SensorDefinition(
        key="test_leistung_kw", name="Leistung", unit="kW", icon="mdi:flash",
        category=SensorCategory.ANLAGE, formel="Testwert",
    )

    states = await _publish(monkeypatch, [
        _sv("pv_erzeugung_gesamt_kwh", 12345.6789),     # Energie → ganzzahlig
        _sv("netto_ertrag_euro", 1234.5678),            # Geld → 2 Stellen
        _sv("autarkie_prozent", 67.891),                # Prozent → 1 Stelle
        _sv("co2_ersparnis_kg", 4321.987),              # Menge → ganzzahlig
        _sv("amortisation_jahre", 12.3456),             # Jahre → 1 Stelle
        SensorValue(definition=kw_definition, value=1.2345),  # Leistung → Stellen
        _sv("letzter_import_monat_name", "Juli 2026"),  # Text bleibt Text
    ])

    assert states["pv_erzeugung_gesamt_kwh"] == "12346"
    assert states["netto_ertrag_euro"] == "1234.57"
    assert states["autarkie_prozent"] == "67.9"
    assert states["co2_ersparnis_kg"] == "4322"
    assert states["amortisation_jahre"] == "12.3"
    assert states["test_leistung_kw"] == "1.23"
    assert states["letzter_import_monat_name"] == "Juli 2026"


async def test_kein_wert_kippt_durch_rundung_auf_null(monkeypatch):
    """Die Leitplanke: kleine, aber echte Werte bleiben sichtbar."""
    kw_definition = SensorDefinition(
        key="test_leistung_kw", name="Leistung", unit="kW", icon="mdi:flash",
        category=SensorCategory.ANLAGE, formel="Testwert",
    )

    states = await _publish(monkeypatch, [
        _sv("eedc_prognose_rest_today_kwh", 0.35),   # Rest-Prognose am Abend
        _sv("netto_ertrag_euro", 0.004),             # Cent-Bruchteil
        SensorValue(definition=kw_definition, value=0.35),
        _sv("einspeisung_gesamt_kwh", 0.0),          # echte 0 bleibt 0
    ])

    assert states["eedc_prognose_rest_today_kwh"] not in ("0", "0.0")
    assert float(states["eedc_prognose_rest_today_kwh"]) == pytest.approx(0.3)
    assert float(states["netto_ertrag_euro"]) == pytest.approx(0.004)
    assert states["test_leistung_kw"] == "0.35"
    assert states["einspeisung_gesamt_kwh"] == "0"


async def test_sensor_anzahl_und_namen_unveraendert(monkeypatch):
    """Die Rundung fasst weder die Sensor-Liste noch die Discovery-Namen an."""
    import json
    import backend.services.mqtt_client as mqtt_mod

    fake = _FakeAiomqtt()
    monkeypatch.setattr(mqtt_mod, "aiomqtt", fake)
    monkeypatch.setattr(mqtt_mod, "MQTT_AVAILABLE", True)

    werte = [
        _sv("pv_erzeugung_gesamt_kwh", 12345.6789),
        _sv("netto_ertrag_euro", 1234.5678),
        _sv("autarkie_prozent", 67.891),
    ]
    client = mqtt_mod.MQTTClient()
    result = await client.publish_all_sensors(werte, anlage_id=1, anlage_name="Test")

    assert result["total"] == len(werte) and result["success"] == len(werte)

    state_topics = [t for t, _ in fake.published
                    if t.startswith("eedc/anlage/1/") and not t.endswith("/attributes")]
    assert state_topics == [f"eedc/anlage/1/{sv.definition.key}" for sv in werte]

    discovery = [json.loads(p) for t, p in fake.published if t.startswith("homeassistant/")]
    assert [d["name"] for d in discovery] == [sv.definition.name for sv in werte]
    assert [d["unique_id"] for d in discovery] == [f"eedc_1_{sv.definition.key}" for sv in werte]


def test_runde_exportwert_laesst_nicht_numerisches_in_ruhe():
    """Text, None und Bool gehen unverändert durch (Monatsname, Uhrzeit …)."""
    assert runde_exportwert("18:00", "") == "18:00"
    assert runde_exportwert(None, "kWh") is None
    assert runde_exportwert(True, "") is True
    assert runde_exportwert(7, "kWh") == 7           # int bleibt int
    assert isinstance(runde_exportwert(12345.6, "kWh"), int)
