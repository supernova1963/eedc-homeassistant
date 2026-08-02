"""
Akzeptanztest P-4: REST und MQTT sagen für denselben Sensor dieselbe Zahl.

Vorgeschichte (N-55): beide Wege teilen sich den Produzenten
(`calculate_anlage_sensors` / `calculate_investition_sensors`), danach trennten
sie sich. MQTT rundete mit dem SoT `runde_exportwert` je Größenart; REST
serialisierte, was der Produzent lieferte — und der rundete in ~25 eigenen
Sensorzeilen vor. Ergebnis: dieselbe kWh-Größe kam über MQTT ganzzahlig und
über REST mit einer Nachkommastelle an, und der MQTT-Wert wurde zweimal
hintereinander gerundet.

Seit P-4 rundet **nur noch die Serialisierungsgrenze**:
`SensorExportItem` (REST) bzw. `publish_sensor` (MQTT). Der Produzent liefert
ungerundet. Dieser Test misst beide Payloads gegeneinander — er ist der
eigentliche Beweis der Zusammenführung, `test_mqtt_export_rundung_je_groessenart`
ist sein MQTT-seitiger Nachbar.

N-54 (zweiter Payload desselben Clients): `publish_monatsdaten` benutzt
denselben Helfer, Struktur und Topic unverändert.
"""

from __future__ import annotations

import json

import pytest

from backend.api.routes.ha_export import SensorExportItem
from backend.services.ha_sensors_export import (
    SensorCategory,
    SensorDefinition,
    SensorValue,
    get_sensor_definition,
)


# ---------------------------------------------------------------------------
# aiomqtt-Doppel (wie im MQTT-Nachbartest): sammelt (topic, payload)
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


# Eine Größe je Größenart — kWh, Geld, Prozent und dimensionslos (COP).
# Bewusst Werte mit langen Stellen, wie sie der Produzent jetzt liefert.
FAELLE: list[tuple[str, float]] = [
    ("pv_erzeugung_gesamt_kwh", 12345.6789),   # kWh          → ganzzahlig
    ("netto_ertrag_euro", 1234.5678),          # Geld         → 2 Stellen
    ("autarkie_prozent", 67.891),              # Prozent      → 1 Stelle
    ("wp_cop_durchschnitt", 3.456789),         # dimensionslos → 2 Stellen
]


def _rest_states(werte: list[SensorValue]) -> dict[str, str]:
    """REST-Payload: was `GET /ha/export/sensors` als `value` ausliefert."""
    items = [
        SensorExportItem(
            key=sv.definition.key,
            name=sv.definition.name,
            value=sv.value,
            unit=sv.definition.unit,
            icon=sv.definition.icon,
            category=sv.definition.category.value,
            formel=sv.definition.formel,
            berechnung=sv.berechnung,
            device_class=sv.definition.device_class,
            state_class=sv.definition.state_class,
        )
        for sv in werte
    ]
    # Über den JSON-Dump, nicht über das Attribut: gemessen wird, was beim
    # HA-Client ankommt.
    return {
        i["key"]: str(i["value"])
        for i in json.loads(json.dumps([m.model_dump() for m in items]))
    }


async def _mqtt_states(monkeypatch, werte: list[SensorValue]) -> dict[str, str]:
    """MQTT-Payload: der State, den `publish_all_sensors` retained schreibt."""
    import backend.services.mqtt_client as mqtt_mod

    fake = _FakeAiomqtt()
    monkeypatch.setattr(mqtt_mod, "aiomqtt", fake)
    monkeypatch.setattr(mqtt_mod, "MQTT_AVAILABLE", True)

    client = mqtt_mod.MQTTClient()
    result = await client.publish_all_sensors(werte, anlage_id=1, anlage_name="Test")
    assert result["failed"] == 0, result["errors"]

    return {
        topic.rsplit("/", 1)[-1]: payload
        for topic, payload in fake.published
        if topic.startswith("eedc/anlage/1/") and not topic.endswith("/attributes")
    }


def _sv(key: str, value) -> SensorValue:
    definition = get_sensor_definition(key)
    assert definition is not None, key
    return SensorValue(definition=definition, value=value)


async def test_rest_und_mqtt_liefern_denselben_string(monkeypatch):
    """Der Kern: je eine kWh-, Geld-, Prozent- und dimensionslose Größe."""
    werte = [_sv(key, wert) for key, wert in FAELLE]

    rest = _rest_states(werte)
    mqtt = await _mqtt_states(monkeypatch, werte)

    for key, _ in FAELLE:
        assert rest[key] == mqtt[key], (
            f"{key}: REST liefert {rest[key]!r}, MQTT {mqtt[key]!r}"
        )

    # Und die Zahlen selbst — sonst könnten beide gemeinsam falsch sein.
    assert rest["pv_erzeugung_gesamt_kwh"] == "12346"
    assert rest["netto_ertrag_euro"] == "1234.57"
    assert rest["autarkie_prozent"] == "67.9"
    assert rest["wp_cop_durchschnitt"] == "3.46"


async def test_nullkipp_schutz_gilt_auch_im_rest_pfad(monkeypatch):
    """Die Leitplanke aus `runde_exportwert` überlebt die REST-Grenze."""
    kw_definition = SensorDefinition(
        key="test_leistung_kw", name="Leistung", unit="kW", icon="mdi:flash",
        category=SensorCategory.ANLAGE, formel="Testwert",
    )
    werte = [
        _sv("eedc_prognose_rest_today_kwh", 0.35),   # kWh, würde auf 0 fallen
        _sv("netto_ertrag_euro", 0.004),             # Cent-Bruchteil
        SensorValue(definition=kw_definition, value=0.35),
        _sv("einspeisung_gesamt_kwh", 0.0),          # echte 0 bleibt 0
    ]

    rest = _rest_states(werte)
    mqtt = await _mqtt_states(monkeypatch, werte)

    assert rest["eedc_prognose_rest_today_kwh"] not in ("0", "0.0")
    assert float(rest["eedc_prognose_rest_today_kwh"]) == pytest.approx(0.3)
    assert float(rest["netto_ertrag_euro"]) == pytest.approx(0.004)
    assert rest["test_leistung_kw"] == "0.35"
    assert rest["einspeisung_gesamt_kwh"] == "0"

    for key in rest:
        assert rest[key] == mqtt[key], key


def test_rest_grenze_rundet_auch_ohne_route():
    """Die Rundung hängt am Modell, nicht an den drei Routen.

    Damit trägt sie auch eine vierte Route, die es heute noch nicht gibt —
    genau das war die Lücke: drei Einsprünge, an denen man sie hätte
    vergessen können.
    """
    item = SensorExportItem(
        key="pv_erzeugung_gesamt_kwh", name="PV", value=12345.6789, unit="kWh",
        icon="mdi:solar-power", category="energie", formel="Σ",
    )
    assert item.value == 12346
    assert isinstance(item.value, int)

    # Nicht-numerische Werte bleiben unangetastet.
    text = SensorExportItem(
        key="letzter_import_monat_name", name="Monat", value="Juli 2026", unit="",
        icon="mdi:calendar", category="status", formel="—",
    )
    assert text.value == "Juli 2026"


async def test_monatsdaten_payload_rundet_und_behaelt_struktur(monkeypatch):
    """N-54: derselbe Client, derselbe Helfer — Felder und Topic unverändert."""
    import backend.services.mqtt_client as mqtt_mod
    from backend.api.routes.monatsabschluss.wizard import MONATSDATEN_MQTT_EINHEITEN

    fake = _FakeAiomqtt()
    monkeypatch.setattr(mqtt_mod, "aiomqtt", fake)
    monkeypatch.setattr(mqtt_mod, "MQTT_AVAILABLE", True)

    client = mqtt_mod.MQTTClient()
    ok = await client.publish_monatsdaten(
        anlage_id=1, jahr=2026, monat=7,
        daten={
            "jahr": 2026, "monat": 7,
            "einspeisung_kwh": 1234.5678,
            "netzbezug_kwh": 987.6543,
        },
        einheiten=MONATSDATEN_MQTT_EINHEITEN,
    )
    assert ok

    (topic, payload), = fake.published
    assert topic == "eedc/anlage/1/monatsdaten/2026/07"

    daten = json.loads(payload)
    # Struktur: Feldnamen und Reihenfolge unverändert — daran hängen
    # fremde HA-Automationen.
    assert list(daten) == ["jahr", "monat", "einspeisung_kwh", "netzbezug_kwh"]
    assert daten["jahr"] == 2026 and daten["monat"] == 7
    assert daten["einspeisung_kwh"] == 1235
    assert daten["netzbezug_kwh"] == 988


def test_produzent_liefert_ungerundet():
    """Gegenprobe: die Rundung darf NICHT zurück in den Produzenten wandern.

    Wäre sie dort, stünde sie wieder an ~25 Sensorzeilen — und der MQTT-Wert
    würde zweimal gerundet (18,45 → 18,5 → 18 statt 18,45 → 18).
    """
    import inspect

    from backend.api.routes import ha_export

    for name in ("calculate_anlage_sensors", "calculate_investition_sensors"):
        quelle = inspect.getsource(getattr(ha_export, name))
        assert "round(" not in quelle, (
            f"{name} rundet wieder selbst — Rundung gehört an die "
            f"Serialisierungsgrenze (SensorExportItem / publish_sensor)."
        )
