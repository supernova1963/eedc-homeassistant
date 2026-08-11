"""F-26 — der Tagesverlauf-Weg entscheidet nach der ZUORDNUNG, nicht nach der Umgebung.

**Der gemeldete Fall** (IdleBit, Forum T89667 #142): eedc im Docker-Container,
Home Assistant per **Long-Lived-Token** angebunden, kein MQTT. Live-Werte kamen
an, Tageswerte nie. Ursache war ein Gate auf ``HA_INTEGRATION_AVAILABLE``
(= ``SUPERVISOR_TOKEN``): ohne Supervisor ging ``get_tagesverlauf`` **direkt** in
den MQTT-Fallback, der mangels Snapshots leer lieferte — woraufhin
``aggregate_day`` mit ``return None`` abbrach. Jeden Lauf, jeden Tag.

Diese Proben stellen genau diese Konstellation her: **kein Supervisor-Token**,
aber eine gesetzte Remote-Verbindung. Sie prüfen die Weggabelung, nicht die
Zahlen dahinter — die HA-Abfrage selbst wird gemockt, denn sie ist hier nicht
der Gegenstand (und die echte Kette hängt an einer erreichbaren HA-Instanz).

⚠ Der Zustand von ``HAStateService`` ist prozessweit (Singleton). Jede Probe
stellt ihn hinterher wieder her — sonst trägt sie ihre Verbindung in fremde
Tests, und genau diese Klasse steht als N-236 im Register.
"""

from __future__ import annotations

import pytest

from backend.models.anlage import Anlage
from backend.services import live_tagesverlauf_service as ltv
from backend.services.ha_state_service import get_ha_state_service


def _anlage_mit_live_zuordnung() -> Anlage:
    """Anlage mit HA-Entity-Zuordnung — der Fall des Melders.

    `basis.live` trägt **HA-Entities** (Datenquellen-V4-Resolver, Stufe 1);
    MQTT-Felder stünden in Gateway-/Inbound-Mappings, nicht hier. Genau deshalb
    darf diese Zuordnung den Weg bestimmen.
    """
    a = Anlage(id=1, anlagenname="Docker mit Token")
    a.sensor_mapping = {
        "basis": {"live": {"netzbezug_w": "sensor.netzbezug", "einspeisung_w": "sensor.einspeisung"}}
    }
    return a


def _ohne_marktabruf(monkeypatch) -> None:
    """Der HA-Weg holt nebenbei die Börsenpreise — hier nicht der Gegenstand.

    Ungemockt geht diese Probe ans Netz (der Wächter in `conftest.py` meldet sie
    als stillen Esser, N-232/N-236). Ein Test, der eine fremde API braucht,
    prüft nicht mehr nur den Code.
    """
    from backend.services import strompreis_markt_service as sms

    async def keine_preise(land, tag):
        return {}

    monkeypatch.setattr(sms, "get_strompreis_stunden", keine_preise)


class _Merker:
    """Merkt sich, welcher Weg gegangen wurde."""

    def __init__(self):
        self.mqtt_gerufen = 0

    async def mqtt(self, anlage, db, tage_zurueck=0):
        self.mqtt_gerufen += 1
        return {"serien": [], "punkte": []}


@pytest.fixture
def ha_verbindung():
    """Setzt/entfernt die Remote-Verbindung am Singleton — und räumt auf."""
    svc = get_ha_state_service()
    vorher = (svc.api_url, svc.token)

    def setzen(token):
        svc.api_url = "http://ha.example:8123/api"
        svc.token = token

    yield setzen
    svc.api_url, svc.token = vorher


@pytest.mark.asyncio
async def test_ohne_supervisor_aber_mit_token_geht_der_ha_weg(db, monkeypatch, ha_verbindung):
    """Der eigentliche Fehler: dieser Fall landete im MQTT-Fallback.

    Ohne den Fix ist ``mqtt_gerufen == 1`` und die Antwort leer — womit
    ``aggregate_day`` abbricht und der Tag nie einen Wert bekommt.
    """
    ha_verbindung("langlebiger-token")
    merker = _Merker()
    monkeypatch.setattr(ltv, "_get_tagesverlauf_mqtt", merker.mqtt)

    # Der HA-Weg selbst ist hier nicht der Gegenstand: seine History-Abfrage
    # wird gemockt, damit die Probe die WEGGABELUNG misst und nicht das Netz.
    async def fake_history(ids, start, end):
        return ({eid: [(start, 100.0)] for eid in ids}, {eid: "W" for eid in ids})

    monkeypatch.setattr(ltv, "get_history_normalized", fake_history)
    _ohne_marktabruf(monkeypatch)

    ergebnis = await ltv.get_tagesverlauf(_anlage_mit_live_zuordnung(), db)

    assert merker.mqtt_gerufen == 0, "MQTT-Fallback trotz erreichbarer HA-Verbindung"
    assert ergebnis.get("punkte"), "HA-Weg liefert keine Punkte"


@pytest.mark.asyncio
async def test_ohne_jede_ha_verbindung_bleibt_es_beim_mqtt_weg(db, monkeypatch, ha_verbindung):
    """Der reine MQTT-Betrieb ist unberührt — er hat keinen Token.

    Ohne diese Probe wäre die Korrektur eine Wette darauf, dass niemand nur
    MQTT nutzt.
    """
    ha_verbindung(None)
    merker = _Merker()
    monkeypatch.setattr(ltv, "_get_tagesverlauf_mqtt", merker.mqtt)

    await ltv.get_tagesverlauf(_anlage_mit_live_zuordnung(), db)

    assert merker.mqtt_gerufen == 1, "ohne HA-Verbindung muss der MQTT-Weg greifen"


@pytest.mark.asyncio
async def test_leerer_ha_weg_faellt_auf_mqtt_zurueck(db, monkeypatch, ha_verbindung):
    """Niemand darf durch die Korrektur schlechter dastehen (F-26, Teil 2).

    Wer HA angebunden hat, dessen `live`-Zuordnung aber ins Leere zeigt
    (umbenannte Entity, abgeschalteter Recorder), bekam vorher seine
    MQTT-Kurve — die behält er.
    """
    ha_verbindung("langlebiger-token")

    async def mqtt_mit_daten(anlage, db, tage_zurueck=0):
        return {"serien": [{"key": "netz"}], "punkte": [{"zeit": "10:00", "werte": {}}]}

    monkeypatch.setattr(ltv, "_get_tagesverlauf_mqtt", mqtt_mit_daten)

    async def leere_history(ids, start, end):
        return ({}, {})

    monkeypatch.setattr(ltv, "get_history_normalized", leere_history)
    _ohne_marktabruf(monkeypatch)

    ergebnis = await ltv.get_tagesverlauf(_anlage_mit_live_zuordnung(), db)

    assert ergebnis["punkte"], "MQTT-Rückfall greift nicht, wenn der HA-Weg leer bleibt"


@pytest.mark.asyncio
async def test_ohne_zuordnung_wird_gar_kein_weg_gegangen(db, monkeypatch, ha_verbindung):
    """Keine Live-Zuordnung ⇒ leer, ohne eine einzige Abfrage.

    Die Wegwahl darf nicht dazu führen, dass eine Anlage ohne Zuordnung
    plötzlich HA befragt.
    """
    ha_verbindung("langlebiger-token")
    merker = _Merker()
    monkeypatch.setattr(ltv, "_get_tagesverlauf_mqtt", merker.mqtt)

    leer = Anlage(id=2, anlagenname="ohne Zuordnung")
    leer.sensor_mapping = {}

    ergebnis = await ltv.get_tagesverlauf(leer, db)

    assert ergebnis == {"serien": [], "punkte": []}
    assert merker.mqtt_gerufen == 0
