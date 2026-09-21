"""S2/B2 — der zweite HA-Komponententyp (`binary_sensor`) und die bestandsgetriebene Rücknahme.

**Warum das ein eigenes Paket ist.** Bis zum 21.09.2026 publizierte eedc genau
einen Komponententyp: `homeassistant/sensor/{unique_id}/config`
(`mqtt_client.py::_get_config_topic` war die einzige Stelle im Baum, die
`discovery_prefix` benutzte). Ein zweiter Typ berührt **drei** Dinge auf einmal
— das Config-Topic, die erlaubten Felder im Payload und die Form des Zustands —
und, weil alle drei Topics mit `retain=True` liegen, auch die **Rücknahme**.

**Und die Rücknahme hatte eine offene Flanke, die erst dadurch sichtbar wurde.**
`belegte_sensor_eintraege` kennt die **heutigen** Definitionen. eedc hat aber
schon einmal einen anderen Typ publiziert: die MWD-Startwerte als
`homeassistant/number/eedc_{anlage_id}_mwd_{feld}_start/config`
(v1.1.0-beta.1, 17.02.2026; ersetzt am 13.03.2026 mit `77c6e211`). In Gernots
Produktion stehen davon bis heute 19 Entitäten. *Eine Liste, die nur die
Gegenwart kennt, kann die Vergangenheit nicht aufräumen — und sagt nie, dass
sie es nicht tut.*

⛔ **Kein Test hier spricht einen echten Broker an.** Muster ist der
`_FakeMqttClient` aus `test_400_mqtt_sensor_abwahl.py`; für die Topic-Ebene
steht hier ein `_FakeBroker`, der retained Nachrichten hält und wie aiomqtt
aussieht.
"""

import json

import pytest

from backend.services.ha_sensors_export import (
    ALL_SENSOR_DEFINITIONS,
    KOMPONENTEN_TYPEN,
    SensorDefinition,
    SensorValue,
    get_all_sensor_definitions,
)
from backend.services.mqtt_client import MQTTClient, MQTTConfig


# ── 1 · Die Menge der Komponententypen ist geschlossen ──────────────────────

def test_nur_zwei_komponententypen():
    """eedc publiziert `sensor` und `binary_sensor` — sonst nichts (KONZEPT §2).

    ⛔ **Das ist eine Entscheidung, kein technischer Riegel** — und genau
    deshalb steht hier ein Wächter und kein Kommentar. Ein `switch` wäre
    derselbe Handgriff wie der `binary_sensor`; wer ihn tut, soll diese Zeile
    rot sehen und die Entscheidung vom 31.08.2026 bewusst ändern, statt sie
    nebenbei zu unterlaufen.
    """
    assert set(KOMPONENTEN_TYPEN) == {"sensor", "binary_sensor"}
    fremd = sorted({
        d.komponente for d in get_all_sensor_definitions()
        if d.komponente not in KOMPONENTEN_TYPEN
    })
    assert not fremd, f"Definitionen mit unbekanntem Komponententyp: {fremd}"


def test_jede_gruppe_traegt_ihre_definitionen():
    """Selbstschutz: läuft der Wächter überhaupt über etwas?"""
    assert len(get_all_sensor_definitions()) >= 70
    assert sum(
        1 for d in get_all_sensor_definitions() if d.komponente == "binary_sensor"
    ) >= 4, "ohne binary_sensor-Definition beweist die ganze Datei nichts"


# ── 2 · Topics je Komponente ────────────────────────────────────────────────

def _def(key: str) -> SensorDefinition:
    for d in get_all_sensor_definitions():
        if d.key == key:
            return d
    raise AssertionError(f"Definition {key} fehlt")


def test_config_topic_traegt_den_komponententyp():
    client = MQTTClient(MQTTConfig(host="localhost"))
    sensor = _def("eedc_ueberschuss_heute_kwh")
    binaer = _def("eedc_ueberschuss_verfuegbar")

    assert client._get_config_topic(sensor, 7) == (
        "homeassistant/sensor/eedc_7_eedc_ueberschuss_heute_kwh/config"
    )
    assert client._get_config_topic(binaer, 7) == (
        "homeassistant/binary_sensor/eedc_7_eedc_ueberschuss_verfuegbar/config"
    )


def test_state_topic_haengt_NICHT_am_komponententyp():
    """Der Wert liegt bei beiden unter `eedc/anlage/{id}/{key}`.

    ⚠ Das ist Absicht: der Zustand ist eine Nachricht über die **Größe**, nicht
    über die HA-Komponente. Würde er den Typ tragen, verschöbe ein späterer
    Typwechsel einer Definition die Historie des Anwenders.
    """
    client = MQTTClient(MQTTConfig(host="localhost"))
    assert client._get_state_topic(_def("eedc_ueberschuss_verfuegbar"), 7) == (
        "eedc/anlage/7/eedc_ueberschuss_verfuegbar"
    )


def test_alle_topics_folgt_dem_komponententyp_von_selbst():
    """Publish und Rücknahme bilden dieselbe Adresse — die #400-Klasse."""
    client = MQTTClient(MQTTConfig(host="localhost"))
    binaer = _def("eedc_guenstige_stunde")
    topics = client.alle_topics(binaer, 3, 42)
    assert topics[0].startswith("homeassistant/binary_sensor/")
    assert topics[0] == client._get_config_topic(binaer, 3, 42)


def test_binary_sensor_belegt_vier_topics_ein_sensor_drei():
    """B2b: das Verfügbarkeits-Topic liegt retained und gehört in die Rücknahme.

    ⛔ **Die Zahl ist der Punkt.** Ein retained Topic, das die Rücknahme nicht
    kennt, bleibt für immer auf dem Broker liegen — genau die #400-Klasse, nur
    mit einem `offline` statt einem Messwert. Deshalb steht hier `4` und nicht
    „mindestens 3".
    """
    client = MQTTClient(MQTTConfig(host="localhost"))
    binaer = _def("eedc_guenstige_stunde")
    gewoehnlich = _def("eedc_speicher_soc_prozent")

    binaer_topics = client.alle_topics(binaer, 3, 42)
    assert len(binaer_topics) == 4, binaer_topics
    assert binaer_topics[-1] == (
        "eedc/anlage/3/investition/42/eedc_guenstige_stunde/availability"
    )
    assert binaer_topics[-1] == binaer_topics[1] + "/availability", (
        "das Verfügbarkeits-Topic hängt am State-Topic, nicht an der Komponente"
    )

    assert len(client.alle_topics(gewoehnlich, 3)) == 3, (
        "ein `sensor` bekommt kein Verfügbarkeits-Topic — dort gilt weiter "
        "der Leerwert `\"None\"` (X-3/N-405)"
    )


# ── 3 · Discovery-Payload ───────────────────────────────────────────────────

def test_binary_payload_ohne_einheit_und_state_class():
    client = MQTTClient(MQTTConfig(host="localhost"))
    payload = client._build_discovery_payload(
        _def("eedc_prognose_auffaellig"), 1, "Testanlage"
    )
    assert payload["payload_on"] == "ON" and payload["payload_off"] == "OFF"
    assert "unit_of_measurement" not in payload
    assert "state_class" not in payload
    assert payload["device_class"] == "problem"


def test_binary_payload_traegt_den_verfuegbarkeits_vertrag():
    """B2b — ADR-002/P4 für einen Typ, der keinen Leerwert kennt.

    ⛔ **Warum das nicht kosmetisch ist:** ohne diesen Kanal behält ein
    `binary_sensor` ohne Eingang seinen **letzten** Zustand, und eine
    Automation liest ihn als Wahrheit. Fällt der Preisabruf aus, stünde
    `eedc_guenstige_stunde` womöglich dauerhaft auf `ON`. P4 verlangt, dass
    ein fehlender Eingang sichtbar ist — in HA heißt das „nicht verfügbar".
    """
    client = MQTTClient(MQTTConfig(host="localhost"))
    binaer = _def("eedc_guenstige_stunde")
    payload = client._build_discovery_payload(binaer, 1, "Testanlage")

    assert payload["availability_topic"] == payload["state_topic"] + "/availability"
    assert payload["payload_available"] == "online"
    assert payload["payload_not_available"] == "offline"


def test_jeder_binary_sensor_traegt_den_vertrag_nicht_nur_einer():
    """Baumweit statt am Beispiel — ein neuer binary_sensor ohne Kanal fällt auf."""
    client = MQTTClient(MQTTConfig(host="localhost"))
    binaere = [d for d in get_all_sensor_definitions() if d.komponente == "binary_sensor"]
    assert len(binaere) >= 4, "Wächter liefe ins Leere"

    ohne = [
        d.key for d in binaere
        if "availability_topic" not in client._build_discovery_payload(d, 1, "A")
    ]
    assert not ohne, f"binary_sensor ohne Verfügbarkeits-Kanal: {ohne}"


def test_sensor_payload_traegt_keinen_verfuegbarkeits_kanal():
    """Gegenrichtung (N-405): ein `sensor` meldet weiter `\"None\"` statt offline.

    ⚠ Das ist kein Versehen, sondern die Trennlinie: ein `sensor` **kann**
    „unbekannt" zeigen, ein `binary_sensor` kann es nicht. Bekäme der `sensor`
    hier einen Verfügbarkeits-Kanal, verlöre der Anwender die Unterscheidung
    zwischen „Wert fehlt" und „eedc redet nicht mehr".
    """
    client = MQTTClient(MQTTConfig(host="localhost"))
    payload = client._build_discovery_payload(
        _def("eedc_speicher_soc_prozent"), 1, "Testanlage"
    )
    assert "availability_topic" not in payload
    assert "payload_not_available" not in payload


def test_sensor_payload_bleibt_wie_bisher():
    """Gegenrichtung: ein gewöhnlicher Sensor verliert nichts."""
    client = MQTTClient(MQTTConfig(host="localhost"))
    payload = client._build_discovery_payload(
        _def("eedc_speicher_soc_prozent"), 1, "Testanlage"
    )
    assert payload["unit_of_measurement"] == "%"
    assert payload["state_class"] == "measurement"
    assert "payload_on" not in payload


# ── 4 · Der Zustand eines binary_sensor ─────────────────────────────────────

class _FakeBroker:
    """Ein Broker mit Gedächtnis: hält retained Nachrichten und liefert sie aus.

    Er ersetzt `aiomqtt.Client` als Kontextmanager. Bewusst so klein wie
    möglich — er muss `publish`, `subscribe` und `messages` können, mehr nicht.
    """

    def __init__(self, retained: dict[str, bytes] | None = None):
        self.retained: dict[str, bytes] = dict(retained or {})
        self.abos: list[str] = []
        #: Jede Nachricht in der Reihenfolge ihres Eintreffens — ein Broker mit
        #: Gedaechtnis allein kann nicht sagen, WANN etwas kam, und die
        #: Reihenfolge `online` vor `ON` ist Teil des B2b-Vertrags.
        self.verlauf: list[tuple[str, bytes]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def publish(self, topic, payload, retain=False):
        roh = payload.encode("utf-8") if isinstance(payload, str) else (payload or b"")
        self.verlauf.append((str(topic), roh))
        if retain and len(roh) == 0:
            self.retained.pop(str(topic), None)     # leer = Tombstone
        elif retain:
            self.retained[str(topic)] = roh

    async def subscribe(self, filt):
        self.abos.append(filt)

    @staticmethod
    def _passt(topic: str, filt: str) -> bool:
        if filt.endswith("/#"):
            return topic.startswith(filt[:-2] + "/") or topic == filt[:-2]
        t, f = topic.split("/"), filt.split("/")
        if len(t) != len(f):
            return False
        return all(fi == "+" or fi == ti for ti, fi in zip(t, f))

    @property
    def messages(self):
        gehalten = [
            (t, p) for t, p in sorted(self.retained.items())
            if any(self._passt(t, f) for f in self.abos)
        ]

        class _Nachricht:
            def __init__(self, topic, payload):
                self.topic = topic
                self.payload = payload

        async def _gen():
            for t, p in gehalten:
                yield _Nachricht(t, p)
            # Danach schweigt ein echter Broker, bis etwas Neues kommt —
            # genau darauf wartet `verwaiste_topics` in seinen 1,5 s.
            import asyncio
            await asyncio.sleep(10)

        return _gen()


def _broker_einhaengen(monkeypatch, broker):
    from backend.services import mqtt_client as modul

    class _Fabrik:
        def __call__(self, **kwargs):
            return broker

    monkeypatch.setattr(modul, "aiomqtt", type("X", (), {"Client": _Fabrik()})())
    monkeypatch.setattr(modul, "MQTT_AVAILABLE", True)


async def test_binary_sensor_publiziert_on_und_off(monkeypatch):
    broker = _FakeBroker()
    _broker_einhaengen(monkeypatch, broker)
    client = MQTTClient(MQTTConfig(host="localhost"))
    d = _def("eedc_guenstige_stunde")

    await client.publish_sensor_value(SensorValue(definition=d, value=True), 1)
    assert broker.retained["eedc/anlage/1/eedc_guenstige_stunde"] == b"ON"

    await client.publish_sensor_value(SensorValue(definition=d, value=False), 1)
    assert broker.retained["eedc/anlage/1/eedc_guenstige_stunde"] == b"OFF"


async def test_binary_sensor_meldet_sich_online_bevor_er_den_zustand_sagt(monkeypatch):
    """B2b — die Reihenfolge ist Teil des Vertrags.

    ⚠ Umgekehrt sähe HA für einen Augenblick einen Zustand an einer Entität,
    die es noch für nicht verfügbar hält, und verwürfe ihn.
    """
    broker = _FakeBroker()
    _broker_einhaengen(monkeypatch, broker)
    client = MQTTClient(MQTTConfig(host="localhost"))
    d = _def("eedc_guenstige_stunde")

    await client.publish_sensor_value(SensorValue(definition=d, value=True), 1)

    assert broker.retained["eedc/anlage/1/eedc_guenstige_stunde/availability"] == b"online"
    assert broker.retained["eedc/anlage/1/eedc_guenstige_stunde"] == b"ON"
    reihenfolge = [t for t, _p in broker.verlauf]
    assert reihenfolge.index("eedc/anlage/1/eedc_guenstige_stunde/availability") < \
        reihenfolge.index("eedc/anlage/1/eedc_guenstige_stunde"), reihenfolge


async def test_binary_sensor_ohne_wert_meldet_offline_und_keinen_zustand(monkeypatch):
    """B2b (ADR-002/P4) — HA kennt für einen `binary_sensor` keinen Leerwert
    (`"None"` wäre „No matching payload found"). eedc publiziert deshalb keinen
    Zustand — **und meldet die Entität `offline`**, damit HA sie als *nicht
    verfügbar* führt.

    ⛔ **Bis B2b behielt sie hier ihren letzten Zustand**, und eine Automation
    bekam ihn als Wahrheit: ein ausgefallener Preisabruf ließ
    `eedc_guenstige_stunde` dauerhaft auf `ON` stehen. Das retained State-Topic
    trägt weiterhin `ON` — das ist in Ordnung und sogar nötig, denn ein leerer
    Zustand ist dieselbe Fehlermeldung; **maßgeblich für HA ist der
    Verfügbarkeits-Kanal.**
    """
    broker = _FakeBroker()
    _broker_einhaengen(monkeypatch, broker)
    client = MQTTClient(MQTTConfig(host="localhost"))
    d = _def("eedc_speicher_voll")
    topic = "eedc/anlage/1/eedc_speicher_voll"

    await client.publish_sensor_value(SensorValue(definition=d, value=True), 1)
    assert broker.retained[topic + "/availability"] == b"online", "Vorbedingung"
    broker.verlauf.clear()

    ergebnis = await client.publish_sensor_value(SensorValue(definition=d, value=None), 1)

    assert ergebnis is False
    assert broker.retained[topic + "/availability"] == b"offline"
    assert [t for t, _p in broker.verlauf] == [topic + "/availability"], (
        "in dieser Lage wird NUR die Verfügbarkeit publiziert — kein Zustand, "
        "keine Attribute"
    )
    assert broker.retained[topic] == b"ON", (
        "das State-Topic bleibt unangetastet; die Entität ist über den "
        "Verfügbarkeits-Kanal nicht verfügbar, nicht über einen Fehlerwert"
    )


async def test_binary_sensor_kommt_nach_offline_wieder_zurueck(monkeypatch):
    """Die Gegenrichtung: ein Eingang, der wiederkommt, macht die Entität wieder
    verfügbar — sonst wäre ein einmaliger Ausfall dauerhaft."""
    broker = _FakeBroker()
    _broker_einhaengen(monkeypatch, broker)
    client = MQTTClient(MQTTConfig(host="localhost"))
    d = _def("eedc_speicher_voll")
    topic = "eedc/anlage/1/eedc_speicher_voll"

    await client.publish_sensor_value(SensorValue(definition=d, value=None), 1)
    assert broker.retained[topic + "/availability"] == b"offline"

    await client.publish_sensor_value(SensorValue(definition=d, value=False), 1)
    assert broker.retained[topic + "/availability"] == b"online"
    assert broker.retained[topic] == b"OFF"


async def test_gewoehnlicher_sensor_bekommt_kein_verfuegbarkeits_topic(monkeypatch):
    """Gegenrichtung zu N-405: der `sensor`-Pfad ist von B2b unberührt."""
    broker = _FakeBroker()
    _broker_einhaengen(monkeypatch, broker)
    client = MQTTClient(MQTTConfig(host="localhost"))
    for wert in (None, 42.0):
        await client.publish_sensor_value(
            SensorValue(definition=_def("eedc_speicher_soc_prozent"), value=wert), 1
        )
    assert not [t for t in broker.retained if t.endswith("/availability")]


async def test_gewoehnlicher_sensor_bekommt_weiterhin_den_leerwert(monkeypatch):
    """Gegenrichtung zu X-3: ein `sensor` ohne Wert meldet weiterhin `"None"`."""
    broker = _FakeBroker()
    _broker_einhaengen(monkeypatch, broker)
    client = MQTTClient(MQTTConfig(host="localhost"))
    await client.publish_sensor_value(
        SensorValue(definition=_def("eedc_speicher_soc_prozent"), value=None), 1
    )
    assert broker.retained["eedc/anlage/1/eedc_speicher_soc_prozent"] == b"None"


# ── 5 · Bestandsgetriebene Rücknahme ────────────────────────────────────────

_ALTLAST = "homeassistant/number/eedc_1_mwd_einspeisung_start/config"
_ALTLAST_2 = "homeassistant/number/eedc_1_mwd_netzbezug_start/config"
_FREMD = "homeassistant/sensor/other_1/config"
_FREMDE_ANLAGE = "homeassistant/sensor/eedc_2_autarkie_prozent/config"


def _bestand() -> dict[str, bytes]:
    """Ein Broker, wie ihn eine Installation von vor dem 13.03.2026 zeigt."""
    return {
        _ALTLAST: json.dumps({"name": "MWD Einspeisung Start"}).encode(),
        _ALTLAST_2: json.dumps({"name": "MWD Netzbezug Start"}).encode(),
        "eedc/anlage/1/mwd_einspeisung_start": b"0",
        _FREMD: json.dumps({"name": "Fremde Integration"}).encode(),
        _FREMDE_ANLAGE: json.dumps({"name": "Andere eedc-Anlage"}).encode(),
    }


async def test_verwaiste_topics_findet_die_altlast(monkeypatch):
    broker = _FakeBroker(_bestand())
    _broker_einhaengen(monkeypatch, broker)
    client = MQTTClient(MQTTConfig(host="localhost"))

    gefunden = await client.verwaiste_topics(1, bekannte=set(), sammelzeit_s=0.2)

    assert _ALTLAST in gefunden and _ALTLAST_2 in gefunden
    assert "eedc/anlage/1/mwd_einspeisung_start" in gefunden


async def test_verwaiste_topics_fasst_nichts_fremdes_an(monkeypatch):
    """⛔ Die Grenze der ganzen Bauform: **nur eigene Topics dieser Anlage.**

    ⚠ Der Filter greift im Code, nicht im Abo — MQTT kennt keinen
    Praefix-Platzhalter (`+` = eine ganze Ebene). Die Probe prueft deshalb das
    **Ergebnis**, und zusaetzlich, dass das Abo nicht breiter ist als noetig.
    """
    broker = _FakeBroker(_bestand())
    _broker_einhaengen(monkeypatch, broker)
    client = MQTTClient(MQTTConfig(host="localhost"))

    gefunden = await client.verwaiste_topics(1, bekannte=set(), sammelzeit_s=0.2)

    assert _FREMD not in gefunden, "ein fremdes Topic wird nicht geraeumt"
    assert _FREMDE_ANLAGE not in gefunden, "auch keine andere eedc-Anlage"
    assert broker.abos == [
        "homeassistant/+/+/config", "eedc/anlage/1/#",
    ], "nur Discovery-Configs und der eigene State-Zweig"


async def test_verwaiste_topics_meldet_bekannte_nicht_doppelt(monkeypatch):
    broker = _FakeBroker(_bestand())
    _broker_einhaengen(monkeypatch, broker)
    client = MQTTClient(MQTTConfig(host="localhost"))

    gefunden = await client.verwaiste_topics(1, bekannte={_ALTLAST}, sammelzeit_s=0.2)
    assert _ALTLAST not in gefunden and _ALTLAST_2 in gefunden


async def test_remove_sensors_raeumt_neu_und_alt_und_laesst_fremdes_liegen(monkeypatch):
    """Der ganze Weg: publizieren (sensor + binary_sensor), Altlast daneben,
    dann „Sensoren entfernen" — und danach ist nur noch Fremdes da."""
    broker = _FakeBroker(_bestand())
    _broker_einhaengen(monkeypatch, broker)
    client = MQTTClient(MQTTConfig(host="localhost"))

    eintraege = [
        (_def("eedc_ueberschuss_heute_kwh"), 1, None),
        (_def("eedc_guenstige_stunde"), 1, None),
    ]
    for d, aid, iid in eintraege:
        await client.publish_sensor_discovery(d, aid, "Testanlage", iid)
        await client.publish_sensor_value(
            SensorValue(definition=d, value=True if d.komponente == "binary_sensor" else 7.0),
            aid, iid,
        )
    assert any("binary_sensor" in t for t in broker.retained), "Vorbedingung"

    ergebnis = await client.remove_sensors(eintraege, anlage_id_bestand=1)

    assert ergebnis["fehler"] is None
    assert ergebnis["sensoren"] == 2
    assert sorted(ergebnis["altlast_topics"]) == sorted(
        [_ALTLAST, _ALTLAST_2, "eedc/anlage/1/mwd_einspeisung_start"]
    )
    # Auf dem Broker liegt nur noch, was nicht uns gehört.
    assert set(broker.retained) == {_FREMD, _FREMDE_ANLAGE}


_MONATSDATEN = "eedc/anlage/1/monatsdaten/2026/07"


async def test_verwaiste_topics_laesst_finale_monatsdaten_liegen(monkeypatch):
    """⛔ Gemessen im HAOS-Lab am 21.09.2026: die erste Fassung nahm die retained
    Monatsabschluss-Nachricht (`publish_final_month_data`) als „verwaist" mit.

    Sie liegt unter dem eigenen State-Praefix, steht in keiner Sensor-Definition
    und ist trotzdem kein Sensor — der Knopf heisst „Sensoren entfernen", und ein
    Monatsabschluss publiziert seine Nachricht genau einmal. Das Topic bleibt;
    die MWD-Altlast daneben faellt weiterhin.
    """
    bestand = _bestand()
    bestand[_MONATSDATEN] = json.dumps({"pv_erzeugung_kwh": 812.0}).encode()
    broker = _FakeBroker(bestand)
    _broker_einhaengen(monkeypatch, broker)
    client = MQTTClient(MQTTConfig(host="localhost"))

    gefunden = await client.verwaiste_topics(1, bekannte=set(), sammelzeit_s=0.2)
    assert _MONATSDATEN not in gefunden, "finale Monatsdaten sind kein Sensor"
    assert _ALTLAST in gefunden, "die Altlast daneben faellt weiterhin"

    ergebnis = await client.remove_sensors([], anlage_id_bestand=1)
    assert _MONATSDATEN not in ergebnis["altlast_topics"]
    assert _MONATSDATEN in broker.retained, "die Nachricht liegt nach dem Entfernen noch"


async def test_abwahl_nimmt_auch_das_verfuegbarkeits_topic_zurueck(monkeypatch):
    """B2b — der Weg OHNE Bestandsaufnahme, und das ist der kritische.

    ⛔ **Die Abwahl eines einzelnen Sensors** (`ha_export/konfig.py`) fragt den
    Broker nicht ab; sie räumt genau das, was `alle_topics` nennt. Fehlte das
    vierte Topic dort, bliebe ein `offline` für immer liegen — ohne Config-Topic
    unsichtbar in HA, aber sichtbar in jedem MQTT-Client, und der
    Bestätigen-Dialog verspricht dem Anwender etwas anderes (#400).
    """
    broker = _FakeBroker()
    _broker_einhaengen(monkeypatch, broker)
    client = MQTTClient(MQTTConfig(host="localhost"))
    d = _def("eedc_guenstige_stunde")

    await client.publish_sensor_discovery(d, 1, "Testanlage")
    await client.publish_sensor_value(SensorValue(definition=d, value=True), 1)
    assert any(t.endswith("/availability") for t in broker.retained), "Vorbedingung"

    ergebnis = await client.remove_sensors([(d, 1, None)])

    assert ergebnis["fehler"] is None
    assert ergebnis["altlast_topics"] == [], "keine Bestandsaufnahme auf diesem Weg"
    assert broker.retained == {}, broker.retained


async def test_bestandsgetriebene_ruecknahme_faengt_ein_altes_verfuegbarkeits_topic(monkeypatch):
    """Und die zweite Hälfte: auch ein Topic, das die heutigen Definitionen gar
    nicht mehr bilden, wird gefunden — es liegt unter `eedc/anlage/{id}/#`.

    Das ist der Fall „ein `binary_sensor` wurde später zum `sensor`" bzw. „eine
    Definition ist entfallen": der Verfügbarkeits-Kanal bliebe sonst zurück.
    """
    verwaist = "eedc/anlage/1/eedc_ehemals_binaer/availability"
    broker = _FakeBroker({verwaist: b"online"})
    _broker_einhaengen(monkeypatch, broker)
    client = MQTTClient(MQTTConfig(host="localhost"))

    gefunden = await client.verwaiste_topics(1, bekannte=set(), sammelzeit_s=0.2)
    assert verwaist in gefunden, (
        "`eedc/anlage/{id}/#` deckt den Verfügbarkeits-Zweig ab — ohne eigene Regel"
    )


async def test_remove_sensors_ohne_bestandsaufnahme_bleibt_wie_bisher(monkeypatch):
    """Gegenrichtung: ohne `anlage_id_bestand` wird nichts abgefragt.

    Das ist der Weg der **Abwahl** (`ha_export/konfig.py`): sie nimmt genau die
    abgewählten Definitionen zurück und hat mit Altlast nichts zu tun.
    """
    broker = _FakeBroker(_bestand())
    _broker_einhaengen(monkeypatch, broker)
    client = MQTTClient(MQTTConfig(host="localhost"))

    ergebnis = await client.remove_sensors(
        [(_def("eedc_ueberschuss_heute_kwh"), 1, None)]
    )
    assert ergebnis["altlast_topics"] == []
    assert _ALTLAST in broker.retained, "die Altlast bleibt unberührt"
    assert broker.abos == [], "kein Abonnement, keine Bestandsaufnahme"
