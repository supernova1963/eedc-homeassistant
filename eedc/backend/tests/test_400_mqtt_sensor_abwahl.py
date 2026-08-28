"""#400 — Abwahl einzelner Sensoren auf der **sendenden** Seite.

**Warum das nicht in Home Assistant gelöst werden kann.** rapahl (PN, 27.08.2026):
*„All diese unstrukturierten Einträge landen in der HA-Datenbank. Die kann man
zwar bereinigen, aber in der Registry bleiben die drin."* HA kann Entitäten
deaktivieren und löschen — bei der nächsten Discovery kommen sie wieder. Zweiter
Melder derselben Woche: Knallfrosch (simon42 T89667 #236), nach dem Update
erschienen sechs neue MQTT-Geräte ohne erkennbaren Nutzen.

**Entscheid Gernot (28.08.):** Alle Sensoren bleiben per Default **an** — eine
Voreinstellung wäre eine Wette darauf, welchen Wert ein Anwender später braucht,
und wer verliert, merkt es erst, wenn die Historie fehlt. Abgewählt wird je
Sensor-**Definition**, nicht je Gerät. Vor dem Wirksamwerden fragt eedc nach und
sagt, dass die Daten in HA und auf dem Broker verloren sind.

⛔ **In Home Assistant greift eedc nicht ein** — kein Registry-Zugriff, keine
Statistik-Löschung. eedc nimmt ausschließlich **seine eigenen** retained
MQTT-Nachrichten zurück.
"""

from datetime import date

import pytest
from sqlalchemy import select

from backend.models.settings import Settings as SettingsModel
from backend.services.mqtt_broker_settings import (
    ABWAHL_FELD,
    MQTT_EXPORT_SETTINGS_KEY,
    abgewaehlte_sensoren,
    export_aktiviert,
    schreibe_export_settings,
)


async def _anlage_mit_geraet(db, typ: str = "waermepumpe"):
    from backend.models import Anlage, Investition, Monatsdaten

    anlage = Anlage(anlagenname="400", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ=typ, bezeichnung="WP Keller",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=6000.0,
    )
    db.add(inv)
    db.add(Monatsdaten(anlage_id=anlage.id, jahr=2025, monat=6,
                       einspeisung_kwh=100.0, netzbezug_kwh=50.0))
    await db.commit()
    return anlage, inv


class _FakeMqttClient:
    """Ein Broker, der mitschreibt, was publiziert und was zurückgenommen wurde."""

    def __init__(self):
        self.is_available = True
        self.laeufe: list[tuple[int | None, list[str]]] = []
        self.entfernt: list[tuple[str, int, int | None]] = []

    async def publish_all_sensors(self, sensor_values, anlage_id, anlage_name,
                                  investition_id=None, investition_name=None):
        self.laeufe.append((investition_id, [s.definition.key for s in sensor_values]))
        return {"total": len(sensor_values), "success": len(sensor_values),
                "failed": 0, "errors": []}

    async def remove_sensors(self, eintraege):
        self.entfernt.extend((d.key, a, i) for d, a, i in eintraege)
        return {"sensoren": len(eintraege), "topics": len(eintraege) * 3, "fehler": None}

    def alle_publizierten(self) -> set[str]:
        return {k for _, keys in self.laeufe for k in keys}


def _haenge_klient_ein(monkeypatch, klient):
    from backend.services import ha_mqtt_sync

    monkeypatch.setattr(ha_mqtt_sync, "MQTTClient", lambda *a, **k: klient)

    async def _broker(_db):
        return None

    monkeypatch.setattr(ha_mqtt_sync, "resolve_broker_config", _broker)


# ── 1 · Der Filter wirkt im EINZIGEN Outbound-Pfad ───────────────────────────

async def test_abgewaehlter_sensor_erreicht_den_broker_nicht(db, monkeypatch):
    """Der abgewählte Sensor fehlt im Publish — anlagenweit.

    ⛔ **Warum der Filter in `publish_anlage_sensors` sitzen MUSS:** Dieser Pfad
    publiziert die Discovery bei **jedem** Lauf neu. Ein Filter davor — in der
    Oberfläche, in der Route — würde vom nächsten Auto-Publish-Takt überholt:
    der abgewählte Sensor wäre binnen Minuten wieder in HA.
    """
    from backend.services import ha_mqtt_sync

    anlage, _ = await _anlage_mit_geraet(db)
    klient = _FakeMqttClient()
    _haenge_klient_ein(monkeypatch, klient)

    await ha_mqtt_sync.publish_anlage_sensors(db, anlage)
    vorher = klient.alle_publizierten()
    assert "einspeisung_gesamt_kwh" in vorher, "Vorbedingung: der Sensor wird publiziert"

    await schreibe_export_settings(db, **{ABWAHL_FELD: ["einspeisung_gesamt_kwh"]})

    klient.laeufe.clear()
    await ha_mqtt_sync.publish_anlage_sensors(db, anlage)
    assert "einspeisung_gesamt_kwh" not in klient.alle_publizierten()
    # Der Rest bleibt unberührt — Abwahl ist kein Abschalten des Exports.
    assert len(klient.alle_publizierten()) > 5


async def test_abwahl_gilt_auch_je_geraet(db, monkeypatch):
    """Eine Definition wird an JEDEM Gerät abgewählt, nicht nur anlagenweit.

    Das ist der Entscheid „je Sensor-Definition, nicht je Gerät" (Gernot 28.08.).
    Ohne diese Probe könnte der Filter nur im Anlagen-Zweig hängen — die
    Geräte-Sensoren durchliefen dann ungefiltert denselben Publisher.
    """
    from backend.services import ha_mqtt_sync

    anlage, inv = await _anlage_mit_geraet(db)
    klient = _FakeMqttClient()
    _haenge_klient_ein(monkeypatch, klient)

    await ha_mqtt_sync.publish_anlage_sensors(db, anlage)
    geraete_keys = {k for i, keys in klient.laeufe if i == inv.id for k in keys}
    assert geraete_keys, "Vorbedingung: es werden Geräte-Sensoren publiziert"

    opfer = sorted(geraete_keys)[0]
    await schreibe_export_settings(db, **{ABWAHL_FELD: [opfer]})

    klient.laeufe.clear()
    await ha_mqtt_sync.publish_anlage_sensors(db, anlage)
    nachher = {k for i, keys in klient.laeufe if i == inv.id for k in keys}
    assert opfer not in nachher


# ── 2 · Die Abwahl überlebt den Auto-Publish-Toggle ──────────────────────────

async def test_abwahl_ueberlebt_den_auto_publish_toggle(db):
    """⛔ **Der Fehler, der beim Bau des ZWEITEN Feldes auffällt.**

    Der Toggle schrieb ``setting.value = {"enabled": ...}`` und ersetzte damit
    den ganzen Settings-Dict. Mit der Abwahl im selben Key wäre sie beim nächsten
    Klick auf „Werte automatisch publizieren" wortlos verschwunden — der Anwender
    hätte seine abgewählten Sensoren kommentarlos zurückbekommen.
    """
    await schreibe_export_settings(db, **{ABWAHL_FELD: ["einspeisung_gesamt_kwh", "netzbezug_gesamt_kwh"]})
    await schreibe_export_settings(db, enabled=False)

    assert await abgewaehlte_sensoren(db) == {"einspeisung_gesamt_kwh", "netzbezug_gesamt_kwh"}
    assert await export_aktiviert(db) is False

    await schreibe_export_settings(db, enabled=True)
    assert await abgewaehlte_sensoren(db) == {"einspeisung_gesamt_kwh", "netzbezug_gesamt_kwh"}


async def test_ohne_eintrag_wird_alles_exportiert(db):
    """Der Default ist AN — ohne Eintrag ist die Abwahl leer, nicht unbekannt."""
    assert await abgewaehlte_sensoren(db) == set()

    # Auch ein Settings-Eintrag ohne das Feld bedeutet „nichts abgewählt".
    await schreibe_export_settings(db, enabled=True)
    assert await abgewaehlte_sensoren(db) == set()


# ── 3 · Zurücknehmen heißt ALLE DREI Topics ─────────────────────────────────

async def test_remove_sensor_nimmt_alle_drei_topics_zurueck(monkeypatch):
    """Config, Wert und Attribute — alle drei werden mit ``retain=True`` publiziert.

    ⛔ **Bis zum 28.08. nahm das Entfernen nur das Config-Topic zurück.** Die
    beiden anderen blieben mit ihrem letzten Wert dauerhaft auf dem Broker
    liegen, sichtbar in jedem MQTT-Client. Der Bestätigen-Dialog sagt dem
    Anwender, seine Daten seien aus HA **und MQTT** verloren — blieben zwei
    Drittel der Nachrichten liegen, wäre genau dieser Satz falsch.
    """
    from backend.services import mqtt_client as mc
    from backend.services.ha_sensors_export import ANLAGE_SENSOREN

    geschrieben: list[tuple[str, str, bool]] = []

    class _Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def publish(self, topic, payload, retain=False):
            geschrieben.append((topic, payload, retain))

    monkeypatch.setattr(mc, "MQTT_AVAILABLE", True)
    monkeypatch.setattr(mc, "aiomqtt", type("M", (), {"Client": _Client}))

    klient = mc.MQTTClient()
    sensor = ANLAGE_SENSOREN[0]
    assert await klient.remove_sensor(sensor, 7) is True

    topics = [t for t, _, _ in geschrieben]
    assert topics == [
        f"homeassistant/sensor/eedc_7_{sensor.key}/config",
        f"eedc/anlage/7/{sensor.key}",
        f"eedc/anlage/7/{sensor.key}/attributes",
    ]
    # Leer UND retained — nur so wird die festgehaltene Nachricht gelöscht.
    assert all(payload == "" and retain for _, payload, retain in geschrieben)


async def test_entfernen_trifft_dieselben_topics_wie_publizieren(monkeypatch):
    """Publisher und Remover bilden ihre Adressen aus **denselben** Helfern.

    Weicht der Entfernen-Pfad auch nur in einem Zeichen ab, räumt er ein Topic,
    das niemand geschrieben hat — und lässt das geschriebene liegen, ohne dass
    irgendetwas rot wird. Diese Probe hält die Deckungsgleichheit fest.
    """
    from backend.services import mqtt_client as mc
    from backend.services.ha_sensors_export import WAERMEPUMPE_SENSOREN

    monkeypatch.setattr(mc, "MQTT_AVAILABLE", True)
    klient = mc.MQTTClient()
    sensor = WAERMEPUMPE_SENSOREN[0]

    payload = klient._build_discovery_payload(sensor, 3, "Zuhause", 9, "WP")
    topics = klient.alle_topics(sensor, 3, 9)

    assert topics[0] == klient._get_config_topic(sensor, 3, 9)
    assert topics[1] == payload["state_topic"]
    assert topics[2] == payload["json_attributes_topic"]


# ── 4 · Das Entfernen erfasst, was der Publisher publiziert ──────────────────

async def test_belegte_eintraege_umfassen_auch_die_geraete_sensoren(db):
    """⛔ **Der Knopf „Sensoren entfernen" räumte bis zum 28.08. unvollständig.**

    Er zählte drei Sensorlisten von Hand auf (``ANLAGE + PROGNOSE + PREIS``) —
    34 von 44 anlagenweiten Definitionen und **keinen einzigen** gerätebezogenen,
    obwohl die seit dem 27.08. publiziert werden. Er meldete dabei „erfolgreich,
    34 entfernt": wer aufräumen wollte, behielt den Rest und hielt ihn für weg.

    *Eine handgepflegte Liste neben einem wachsenden Publisher veraltet
    zwangsläufig; sie sagt nur nie, dass sie es getan hat.*
    """
    from backend.services.ha_mqtt_sync import belegte_sensor_eintraege
    from backend.services.ha_sensors_export import (
        LETZTER_IMPORT_SENSOREN,
        SPEICHER_SENSOREN,
        WAERMEPUMPE_SENSOREN,
        get_all_sensor_definitions,
    )

    anlage, inv = await _anlage_mit_geraet(db)
    eintraege = await belegte_sensor_eintraege(db, anlage)

    alle = {d.key for d in get_all_sensor_definitions()}
    anlagenweit = {d.key for d, _, i in eintraege if i is None}
    je_geraet = {d.key for d, _, i in eintraege if i == inv.id}

    assert anlagenweit == alle, "anlagenweit fehlt eine Definition"
    assert je_geraet == alle, "je Gerät fehlt eine Definition"

    # Genau die Gruppen, die die alte Liste verlor:
    for gruppe in (SPEICHER_SENSOREN, LETZTER_IMPORT_SENSOREN):
        assert {d.key for d in gruppe} <= anlagenweit
    assert {d.key for d in WAERMEPUMPE_SENSOREN} <= je_geraet


async def test_belegte_eintraege_lassen_sich_auf_die_abwahl_einschraenken(db):
    """Beim Abwählen wird nur das NEU Abgewählte zurückgenommen, nicht alles."""
    from backend.services.ha_mqtt_sync import belegte_sensor_eintraege

    anlage, inv = await _anlage_mit_geraet(db)
    eintraege = await belegte_sensor_eintraege(
        db, anlage, nur_schluessel={"einspeisung_gesamt_kwh"}
    )

    assert {d.key for d, _, _ in eintraege} == {"einspeisung_gesamt_kwh"}
    # Anlage UND Gerät — der Schlüssel gilt überall, wo er publiziert werden kann.
    assert {i for _, _, i in eintraege} == {None, inv.id}


# ── 5 · Die Route ───────────────────────────────────────────────────────────

async def test_route_weist_unbekannte_schluessel_ab(db, monkeypatch):
    """Ein Tippfehler darf nicht als stumme Abwahl in den Settings landen.

    Sonst stünde dort ein Schlüssel, den kein Sensor trägt — er filterte nichts,
    ließe sich über die Oberfläche nie wieder entfernen (sie kennt ihn nicht) und
    würde bei jedem Speichern mitgeschleppt.
    """
    from fastapi import HTTPException

    from backend.api.routes.ha_export import AbwahlRequest, set_sensor_abwahl

    with pytest.raises(HTTPException) as fehler:
        await set_sensor_abwahl(AbwahlRequest(abgewaehlt=["gibt_es_nicht"]), db)

    assert fehler.value.status_code == 400
    assert "gibt_es_nicht" in fehler.value.detail
    assert await abgewaehlte_sensoren(db) == set(), "nichts darf gespeichert worden sein"


async def test_route_speichert_und_meldet_das_neu_abgewaehlte(db, monkeypatch):
    """Die Antwort trennt „abgewählt" von „neu abgewählt".

    Die Oberfläche braucht die Unterscheidung: der Warnhinweis nennt den
    **Verlust**, und der entsteht nur beim NEU Abgewählten. Wer nur wieder
    anwählt, verliert nichts und soll auch nicht gefragt werden.
    """
    from backend.api.routes.ha_export import AbwahlRequest, set_sensor_abwahl

    await _anlage_mit_geraet(db)

    import backend.api.routes.ha_export as route_modul

    klient = _FakeMqttClient()
    monkeypatch.setattr(route_modul, "MQTTClient", lambda *a, **k: klient)

    async def _broker(_db):
        return None

    monkeypatch.setattr(route_modul, "resolve_broker_config", _broker)

    erst = await set_sensor_abwahl(AbwahlRequest(abgewaehlt=["einspeisung_gesamt_kwh"]), db)
    assert erst["neu_abgewaehlt"] == ["einspeisung_gesamt_kwh"]
    assert erst["entfernte_topics"] > 0

    # Zweiter Aufruf mit demselben Stand: nichts NEU, also nichts zurückzunehmen.
    klient.entfernt.clear()
    zweit = await set_sensor_abwahl(
        AbwahlRequest(abgewaehlt=["einspeisung_gesamt_kwh", "netzbezug_gesamt_kwh"]), db
    )
    assert zweit["neu_abgewaehlt"] == ["netzbezug_gesamt_kwh"]
    assert {k for k, _, _ in klient.entfernt} == {"netzbezug_gesamt_kwh"}
