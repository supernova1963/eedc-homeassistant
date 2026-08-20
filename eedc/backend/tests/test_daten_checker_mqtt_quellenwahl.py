"""Daten-Checker MQTT-Topic-Abdeckung: erwartet nur, was auch über MQTT kommt (F-50, #389).

Gemeldet von gruaGit: vier Felder waren bewusst auf „Keine" gestellt (die Werte
kommen von anderen Komponenten) — der Checker meldete sie trotzdem dauerhaft als
„erwartet, nie empfangen", und ein auf „Keine" gestelltes `leistung_w` am E-Auto
zusätzlich als „veraltet".

Ursache: die Erwartungsliste kommt aus der Felder-Registry
(`build_expected_topics`) und kannte die Zuordnung des Anwenders gar nicht.
Gemessen war der Befund größer als die Meldung — ein per **HA-Sensor**
zugeordnetes Feld kann im Inbound-Cache nie einen Wert haben (dort schreibt
ausschließlich `on_message`) und lief in dieselbe Falle.

Was ausdrücklich DRIN bleiben muss:
- Felder ohne Quellen-Eintrag (der Kernfall aus #134 — Publisher-Automation
  fehlt). Ein stummes Inbound persistiert nichts, ist also unterscheidbar.
- Felder auf **Gateway**: der Gateway-Service re-publisht auf das
  EEDC-Inbound-Topic, der Wert landet im selben Cache. Ein stummes
  Gateway-Mapping ist eine echte Lücke.
"""

from __future__ import annotations

import re

import pytest

from backend.models import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.services.daten_checker import CheckSeverity, DatenChecker
from backend.services.datenquellen_resolver import (
    QUELLE_GATEWAY,
    QUELLE_HA_APP,
    QUELLE_HA_CONNECTOR,
    QUELLE_INBOUND,
    QUELLE_KEINE,
    erwartet_inbound_topic,
    feld_id_aus_match_key,
)


# ─── Der reine Helfer: eine Quelle, eine Erwartung ──────────────────────────

def test_ohne_eintrag_wird_erwartet():
    """Der Kernfall aus #134 — niemand hat gewählt, das Topic bleibt erwartet."""
    assert erwartet_inbound_topic({}, "basis_energy_pv_gesamt_kwh") is True


@pytest.mark.parametrize("quelle", [QUELLE_KEINE, QUELLE_HA_APP, QUELLE_HA_CONNECTOR])
def test_gewaehlte_nicht_mqtt_quelle_erwartet_nichts(quelle):
    quellen = {"basis_energy_pv_gesamt_kwh": {"quelle": quelle}}
    assert erwartet_inbound_topic(quellen, "basis_energy_pv_gesamt_kwh") is False


@pytest.mark.parametrize("quelle", [QUELLE_GATEWAY, QUELLE_INBOUND])
def test_mqtt_quellen_bleiben_erwartet(quelle):
    """Gateway re-publisht in denselben Cache — ein stummes Mapping ist eine Lücke."""
    quellen = {"basis_live_netzbezug_w": {"quelle": quelle}}
    assert erwartet_inbound_topic(quellen, "basis_live_netzbezug_w") is True


def test_kaputter_eintrag_wird_erwartet():
    """Kein dict, kein `quelle`-Schlüssel: im Zweifel melden statt schweigen."""
    assert erwartet_inbound_topic({"x": "keine"}, "x") is True
    assert erwartet_inbound_topic({"x": {}}, "x") is True


def test_feld_id_trifft_die_kennung_der_flaeche():
    """Beide Seiten müssen dieselbe Zeichenkette bilden — sonst greift der
    Filter ins Leere und der Fehlalarm bliebe unbemerkt bestehen."""
    from backend.api.routes.datenquellen import _feld_id

    for mk in [
        ("basis_energy", "pv_gesamt_kwh"),
        ("basis_live", "netzbezug_w"),
        ("inv_live", 9, "leistung_w"),
        ("inv_energy", 3, "ladung_kwh"),
    ]:
        assert feld_id_aus_match_key(mk) == _feld_id(mk)


# ─── Der Checker selbst ─────────────────────────────────────────────────────

class _FakeCache:
    """Leerer Inbound-Cache: kein Feld hat je einen Wert getragen."""

    def get_all_live_raw(self):
        return {}

    def get_all_energy_raw(self):
        return {}


class _FakeService:
    _running = True
    cache = _FakeCache()


@pytest.fixture
def _inbound_laeuft(monkeypatch):
    monkeypatch.setattr(
        "backend.services.mqtt_inbound_service.get_mqtt_inbound_service",
        lambda: _FakeService(),
    )


async def _betroffene(db, anlage) -> str:
    """Die „nie empfangen"-Detailzeile des Checks (leer, wenn kein Befund).

    ⚠ Sie nennt nur die ersten SECHS Topics („+n weitere") — taugt also für
    „steht drin", nicht als Abwesenheitsbeleg. Dafür `_anzahl`.
    """
    befunde = await DatenChecker(db=db)._check_mqtt_topic_abdeckung(anlage)
    treffer = [b for b in befunde if "nie empfangen" in b.meldung]
    if not treffer:
        return ""
    assert treffer[0].schwere == CheckSeverity.WARNING.value
    return treffer[0].details


async def _anzahl(db, anlage) -> int:
    """Wie viele Topics meldet der Check als „nie empfangen"?"""
    befunde = await DatenChecker(db=db)._check_mqtt_topic_abdeckung(anlage)
    treffer = [b for b in befunde if "nie empfangen" in b.meldung]
    if not treffer:
        return 0
    return int(re.match(r"(\d+) MQTT-Topic", treffer[0].meldung).group(1))


@pytest.mark.asyncio
async def test_auf_keine_gestelltes_feld_wird_nicht_mehr_gemeldet(db, _inbound_laeuft):
    """gruaGits Fall: bewusst abgewählt ⇒ kein Dauer-Hinweis."""
    anlage = Anlage(anlagenname="Test", leistung_kwp=10.0, sensor_mapping={})
    db.add(anlage)
    await db.flush()

    vorher = await _betroffene(db, anlage)
    assert "pv_gesamt_kwh" in vorher, "Gegenprobe: ohne Wahl muss das Feld gemeldet werden"

    anlage.sensor_mapping = {
        "quellen": {"basis_energy_pv_gesamt_kwh": {"quelle": QUELLE_KEINE}}
    }
    nachher = await _betroffene(db, anlage)
    assert "pv_gesamt_kwh" not in nachher
    # Die übrigen Basis-Felder bleiben unberührt — gefiltert wird je Feld.
    assert "einspeisung_kwh" in nachher


@pytest.mark.asyncio
async def test_ha_sensor_zaehlt_genauso(db, _inbound_laeuft):
    """Die gemessene Klasse, die über die Meldung hinausgeht: in den
    Inbound-Cache schreibt nur `on_message` — ein HA-Feld kann dort nie
    einen Wert haben und ist deshalb kein erwartetes Topic."""
    anlage = Anlage(
        anlagenname="Test", leistung_kwp=10.0,
        sensor_mapping={"quellen": {
            "basis_energy_einspeisung_kwh": {
                "quelle": QUELLE_HA_APP, "entity_id": "sensor.einspeisung",
            }
        }},
    )
    db.add(anlage)
    await db.flush()

    ohne = Anlage(anlagenname="Test", leistung_kwp=10.0, sensor_mapping={})
    db.add(ohne)
    await db.flush()

    # Genau ein Feld fällt weg — nicht mehr und nicht weniger.
    assert await _anzahl(db, anlage) == await _anzahl(db, ohne) - 1


@pytest.mark.asyncio
async def test_gateway_bleibt_gemeldet(db, _inbound_laeuft):
    """Sprengsatz-Gegenprobe: würde Gateway mitgefiltert, verschwände eine
    echte Lücke — der Re-Publish landet im selben Cache."""
    anlage = Anlage(
        anlagenname="Test", leistung_kwp=10.0,
        sensor_mapping={"quellen": {
            "basis_energy_netzbezug_kwh": {"quelle": QUELLE_GATEWAY, "mapping_id": 1}
        }},
    )
    db.add(anlage)
    await db.flush()

    ohne = Anlage(anlagenname="Test", leistung_kwp=10.0, sensor_mapping={})
    db.add(ohne)
    await db.flush()

    assert await _anzahl(db, anlage) == await _anzahl(db, ohne)


@pytest.mark.asyncio
async def test_meldung_traegt_den_vollen_topic_pfad(db, _inbound_laeuft):
    """#389, dritter Punkt: „leistung_w" gibt es an jedem Gerät — erst der
    Pfad sagt, an welchem."""
    anlage = Anlage(anlagenname="Haus", leistung_kwp=10.0, sensor_mapping={})
    db.add(anlage)
    await db.flush()
    db.add(Investition(
        anlage_id=anlage.id, typ="e_auto", bezeichnung="ID.3",
        anschaffungsdatum=None,
    ))
    await db.flush()

    details = await _betroffene(db, anlage)
    assert f"eedc/{anlage.id}_Haus/energy/" in details
