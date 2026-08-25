"""F-63 — jedes ``device_class``/``state_class``-Paar haelt Home Assistants Vertrag ein.

Schwesterdatei: ``test_export_rundung_rest_mqtt_gleich.py``. Sie prueft dieselbe
Sensor-Tabelle auf der Wert-Achse (runden REST und MQTT gleich?), diese hier auf
der Metadaten-Achse (darf HA das Paar ueberhaupt annehmen?).

**Der Anlass.** rapahl meldete am 24.08. per PN funf Protokollzeilen aus Home
Assistant, wortgleich::

    is using state class 'measurement' which is impossible considering
    device class ('energy') it is using; expected None or one of 'total',
    'total_increasing'

**Die Folge ist nicht die Protokollzeile.** HA schliesst eine ungueltige
Kombination von der Langzeitstatistik aus — fuer die betroffenen Sensoren gibt es
in HA gar keine Statistik, also keinen Verlauf, kein Dashboard-Diagramm, keine
Auswertung ueber Monate. Der Anwender sieht einen Sensor, der einen Wert zeigt und
sich nichts merkt.

**Warum der Waechter und nicht nur der Fix.** Die Sensor-Tabelle waechst — mit
v4.0.27 kamen die Preis- und Prognose-Sensoren dazu. Die Regel ist HAs Vertrag,
kein Ermessen, und sie ist mechanisch entscheidbar. Betroffen ist jeder
Add-on-Anwender mit aktiviertem HA-Export; der Fehler ist an der Anzeige nicht zu
sehen, sondern nur an einer Statistik, die fehlt.

**Was die Erhebung gefunden hat, was der Melder nicht sehen konnte.** Sein
Protokoll nannte funf Sensoren, alle ``device_class="energy"``. Die Erhebung ueber
alle 49 Definitionen fand einen **sechsten**: ``jahres_ersparnis_euro`` mit
``device_class="monetary"`` und ``state_class="measurement"`` — HA erlaubt fuer
``monetary`` ausschliesslich ``total``. Er stand in einer anderen Log-Zeile mit
anderem Wortlaut und fehlte deshalb im Bildausschnitt. *Ein Melder belegt einen
Fall, keine Klasse.*

Geprueft wird auf **zwei** Ebenen, weil ein Waechter auf dem Layer allein die
Stelle verfehlt, an der die Regel wirkt:

1. die Registry ``ALL_SENSOR_DEFINITIONS`` — alles, was eedc definiert;
2. der fertige **MQTT-Discovery-Payload** — das, was HA tatsaechlich liest.
"""

import pytest

from backend.services.ha_sensors_export import (
    ALL_SENSOR_DEFINITIONS,
    SensorDefinition,
)


#: Home Assistants Vertrag, uebernommen aus ``homeassistant/components/sensor/const.py``
#: (``DEVICE_CLASS_STATE_CLASSES``, Stand 2026-08-25). Hier stehen **nur** die
#: device_classes, die eedc wirklich benutzt — eine Vollkopie der rund 60 HA-Zeilen
#: waere Pflegeaufwand fuer Faelle, die es im Baum nicht gibt.
#:
#: ``None`` ist bei HA **immer** zulaessig: die Pruefung greift erst, wenn eine
#: state_class gesetzt ist.
#:
#: Kommt eine device_class dazu, die hier fehlt, meldet der Waechter rot statt
#: stillzuschweigen — der Eintrag ist dann eine Zeile mit HA-Beleg. Das ist Absicht:
#: eine Tabelle, die Unbekanntes durchwinkt, deckt genau den neuen Fall nicht.
HA_ERLAUBTE_STATE_CLASSES: dict[str, frozenset[str]] = {
    "energy": frozenset({"total", "total_increasing"}),
    "monetary": frozenset({"total"}),
    "duration": frozenset({"measurement", "total", "total_increasing"}),
}


def _alle_definitionen() -> list[tuple[str, SensorDefinition]]:
    """Jede Definition der Registry, mit ihrer Kategorie zur Fehlermeldung."""
    return [
        (kategorie, sensor)
        for kategorie, sensoren in ALL_SENSOR_DEFINITIONS.items()
        for sensor in sensoren
    ]


def _verstoesse(paare) -> list[str]:
    """Prueft ``(bezeichner, device_class, state_class)``-Tripel gegen HAs Tabelle."""
    schaeden: list[str] = []
    for bezeichner, device_class, state_class in paare:
        if not device_class or not state_class:
            continue  # ohne beides gibt es keine Regel zu verletzen
        erlaubt = HA_ERLAUBTE_STATE_CLASSES.get(device_class)
        if erlaubt is None:
            schaeden.append(
                f"{bezeichner}: device_class={device_class!r} steht nicht in "
                f"HA_ERLAUBTE_STATE_CLASSES — eintragen (mit Beleg aus HAs "
                f"DEVICE_CLASS_STATE_CLASSES) oder device_class weglassen"
            )
        elif state_class not in erlaubt:
            schaeden.append(
                f"{bezeichner}: device_class={device_class!r} + "
                f"state_class={state_class!r} — HA erwartet None oder eines von "
                f"{sorted(erlaubt)} und fuehrt sonst KEINE Langzeitstatistik"
            )
    return schaeden


def test_registry_haelt_den_ha_vertrag_ein():
    """Jede ``SensorDefinition`` traegt ein Paar, das HA annimmt."""
    definitionen = _alle_definitionen()

    # Selbstschutz: findet der Waechter die Tabelle ueberhaupt? Ein Prueferm der
    # ueber eine leere Liste laeuft, meldet gruen und beweist nichts.
    assert len(definitionen) >= 40, (
        f"nur {len(definitionen)} Sensor-Definitionen gefunden — die Registry "
        f"wurde umgebaut, der Waechter laeuft ins Leere"
    )

    schaeden = _verstoesse(
        (f"{kategorie}/{s.key}", s.device_class, s.state_class)
        for kategorie, s in definitionen
    )
    assert not schaeden, (
        f"{len(schaeden)} Sensor(en) tragen eine Kombination, die Home Assistant "
        f"ablehnt:\n  " + "\n  ".join(schaeden)
    )


def test_mqtt_discovery_payload_haelt_den_ha_vertrag_ein():
    """Und dasselbe an der Stelle, an der HA es liest — im fertigen Payload.

    Die Registry ist der Layer; der Discovery-Payload ist die Antwort. Zwischen
    beiden liegt ``_build_discovery_payload``, das die Felder einzeln uebernimmt —
    eine Umbenennung oder ein weggefallenes ``if`` faende die Registry-Probe nicht.
    """
    from backend.services.mqtt_client import MQTTClient, MQTTConfig

    client = MQTTClient(MQTTConfig(host="localhost"))
    paare = []
    for kategorie, sensor in _alle_definitionen():
        payload = client._build_discovery_payload(
            sensor=sensor, anlage_id=1, anlage_name="Testanlage"
        )
        paare.append(
            (
                f"discovery/{kategorie}/{sensor.key}",
                payload.get("device_class"),
                payload.get("state_class"),
            )
        )

    assert len(paare) >= 40, "Discovery-Payloads fehlen — Waechter laeuft ins Leere"

    schaeden = _verstoesse(paare)
    assert not schaeden, (
        f"{len(schaeden)} MQTT-Discovery-Payload(s) tragen eine Kombination, die "
        f"Home Assistant ablehnt:\n  " + "\n  ".join(schaeden)
    )


def test_waechter_meldet_einen_verstoss_auch_wirklich():
    """Gegenprobe: der Pruefer kann rot — sonst beweist sein Gruen nichts.

    Die drei Faelle sind genau die drei Zweige von ``_verstoesse``.
    """
    # F-63 selbst: die Kombination, die HA im Protokoll nennt
    assert _verstoesse([("probe", "energy", "measurement")])
    # der sechste Fall, den das Melder-Protokoll nicht zeigte
    assert _verstoesse([("probe", "monetary", "measurement")])
    # eine device_class, die in der Tabelle fehlt
    assert _verstoesse([("probe", "power", "measurement")])
    # ... und die Gegenrichtung: Gueltiges wird nicht gemeldet
    assert not _verstoesse([("probe", "energy", "total_increasing")])
    assert not _verstoesse([("probe", "monetary", "total")])
    assert not _verstoesse([("probe", None, "measurement")])
    assert not _verstoesse([("probe", "energy", None)])
