"""MQTT-Discovery: **alle** eedc-Sensoren gehören unter das Anlagen-Gerät.

## Der gemeldete Fall

Mit v4.0.30 erreichten die gerätebezogenen Sensoren erstmals MQTT — und legten
dabei je Investition ein **eigenes HA-Gerät** an. Zwei Melder innerhalb von
24 Stunden, unabhängig voneinander:

* **rapahl** (PN, 27.08.2026): acht eedc-Geräte, **sechs davon mit genau einer
  Entität**. *„Bisher gab es ein übergeordnetes Gerät mit den darunterliegenden
  Entitäten. Der Anlagenname wurde Teil des Sensornamens. Eine einheitliche
  Struktur wäre mir am liebsten."*
* **Knallfrosch** (simon42-Forum T89667 #236): sechs neue Geräte auf einmal,
  *„alle nur um die Investkosten zu liefern"*.

⭐ **Warum ein Aufräumen in Home Assistant nicht genügt** — rapahls
entscheidender Satz: *„Die kann man zwar bereinigen, aber in der Registry
bleiben die drin."* Eine Abwahl muss auf der **sendenden** Seite passieren; die
Gliederung ebenso.

**Entscheid Gernot (28.08.2026):** Alle eedc-Sensoren gehören unter die
**Anlage**, *„da die Benutzer sonst ein zusätzliches Gerät zu dem Gerät der
Integration bekommen"*.

## Was diese Datei bewacht — und warum es sie vorher nicht gab

⛔ **Beim Umbau ist KEINE einzige der 151 MQTT-Proben rot geworden.** Die
Gerätezuordnung war ungewächtert: Man konnte sie in beide Richtungen ändern,
ohne dass etwas gemeldet hätte. Genau deshalb steht sie jetzt hier.

⭐ **Die wichtigste Probe ist nicht die Gruppierung, sondern die Invarianz**
(`test_unique_id_und_state_topic_bleiben_unberuehrt`): `unique_id` und
`state_topic` hängen an der **Investition**, nicht am Gerät. Nur weil sie
gleich bleiben, erkennt HA dieselbe Entität wieder und hängt sie lediglich um
— **Langzeitstatistik, `entity_id` und Automationen bleiben erhalten.** Das
war die Bedingung, unter der diese Umstellung überhaupt vertretbar war. Die
verworfene Alternative (Werte als Attribute unter Sammel-Sensoren) scheiterte
genau daran: **Attribute kennen keine Langzeitstatistik.**

Schwesterdateien: `test_mqtt_discovery_entity_category.py` (dasselbe Payload,
andere Achse — welche Sensoren als *Diagnose* gelten) ·
`test_ha_export_sensor_klassen_vertrag.py` (der Vertrag der Definitionen) ·
`test_mqtt_export_toggle_b7_5b.py` (ob überhaupt publiziert wird).
"""

from __future__ import annotations

from backend.services.ha_sensors_export import (
    E_AUTO_SENSOREN,
    INVESTITION_SENSOREN,
    WAERMEPUMPE_SENSOREN,
    get_all_sensor_definitions,
)
from backend.services.mqtt_client import MQTTClient

ANLAGE_ID = 7
ANLAGE_NAME = "Strom, PV, Heizung"
INV_ID = 42
INV_NAME = "Daikin3 ECH₂O"


def _payload(sensor, *, mit_investition: bool):
    client = MQTTClient()
    if mit_investition:
        return client._build_discovery_payload(
            sensor, anlage_id=ANLAGE_ID, anlage_name=ANLAGE_NAME,
            investition_id=INV_ID, investition_name=INV_NAME,
        )
    return client._build_discovery_payload(
        sensor, anlage_id=ANLAGE_ID, anlage_name=ANLAGE_NAME,
    )


def test_geraetebezogene_sensoren_haengen_am_anlagen_geraet():
    """Kein `eedc_inv_*`-Gerät mehr — das war der gemeldete Fall."""
    for sensor in (*WAERMEPUMPE_SENSOREN, *E_AUTO_SENSOREN, *INVESTITION_SENSOREN):
        geraet = _payload(sensor, mit_investition=True)["device"]
        assert geraet["identifiers"] == [f"eedc_anlage_{ANLAGE_ID}"], sensor.key
        assert geraet["name"] == f"eedc - {ANLAGE_NAME}", sensor.key


def test_anlagensensoren_unveraendert_am_selben_geraet():
    """Die Gegenrichtung: Für sie ändert sich nichts, und das muss so bleiben."""
    for sensor in get_all_sensor_definitions():
        geraet = _payload(sensor, mit_investition=False)["device"]
        assert geraet["identifiers"] == [f"eedc_anlage_{ANLAGE_ID}"], sensor.key


def test_unique_id_und_state_topic_bleiben_unberuehrt():
    """⭐ **Die Probe, die die Zusage an den Anwender trägt.**

    Beide Werte hängen an der Investition, nicht am Gerät. Bleiben sie gleich,
    erkennt HA dieselbe Entität wieder: `entity_id`, Langzeitstatistik und
    Automationen überleben die Umgliederung. Ändert jemand hier etwas, ist es
    **kein Umhängen mehr, sondern ein Datenverlust** — dann melden sich diese
    beiden Zeilen.
    """
    for sensor in WAERMEPUMPE_SENSOREN:
        p = _payload(sensor, mit_investition=True)
        assert p["unique_id"] == f"eedc_{ANLAGE_ID}_{INV_ID}_{sensor.key}"
        assert p["state_topic"].endswith(
            f"/anlage/{ANLAGE_ID}/investition/{INV_ID}/{sensor.key}"
        )


def test_der_geraetename_wandert_in_den_sensornamen():
    """Sonst hießen die Kennzahlen zweier Wärmepumpen unter derselben Anlage gleich.

    ⭐ **Der sichtbare Name bleibt dabei derselbe.** HA setzt ihn aus
    Gerätename + Sensorname zusammen: vorher „eedc - Daikin3 ECH₂O" + „COP
    Durchschnitt", jetzt „eedc - Strom, PV, Heizung" + „Daikin3 ECH₂O COP
    Durchschnitt". Die Gruppierung ändert sich, die Beschriftung nicht.
    """
    sensor = next(s for s in WAERMEPUMPE_SENSOREN if s.key == "wp_cop_durchschnitt")
    p = _payload(sensor, mit_investition=True)
    assert p["name"] == f"{INV_NAME} {sensor.name}"
    assert p["name"].startswith(INV_NAME)


def test_ohne_investitionsnamen_kein_none_praefix():
    """Altaufrufe reichen keinen Namen — dann bleibt es beim nackten Sensornamen.

    ⛔ Ohne diese Zeile stünde in HA „None COP Durchschnitt". Ein Prüfer, der
    nur den Normalfall kennt, hätte das nicht gefangen.
    """
    client = MQTTClient()
    sensor = next(s for s in WAERMEPUMPE_SENSOREN if s.key == "wp_cop_durchschnitt")
    p = client._build_discovery_payload(
        sensor, anlage_id=ANLAGE_ID, anlage_name=ANLAGE_NAME, investition_id=INV_ID,
    )
    assert p["name"] == sensor.name
    assert "None" not in p["name"]


def test_anlagensensoren_tragen_kein_geraete_praefix():
    """Die Gegenprobe zum Namens-Umbau: Er darf NUR investitionsbezogen greifen.

    Ohne sie wäre nicht gezeigt, dass die Namensänderung diskriminiert — ein
    Präfix auf jedem Sensor hätte alle 56 Anlagen-Namen verschoben.
    """
    for sensor in get_all_sensor_definitions():
        assert _payload(sensor, mit_investition=False)["name"] == sensor.name, sensor.key
