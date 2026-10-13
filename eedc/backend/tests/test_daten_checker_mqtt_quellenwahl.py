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


# ─── N-316: der Ausweg muss den Weg nennen, den es GIBT ─────────────────────
#
# Drei Meldungen der Kategorie boten als Ausweg „Daten → Einrichtung →
# MQTT-Inbound" an — die v3-Navigation. Seit v4.0.0 sind die Alt-Wizards
# abgelöst, und der Empfangs-Schalter („Daten über MQTT empfangen") sitzt unter
# Einstellungen → Integration. Der Link war nicht kaputt (routeManifest leitet
# `einstellungen/mqtt-inbound` um), zeigte aber auf die Datenquellen-Fläche —
# und dort lässt sich MQTT gar nicht abschalten.
#
# ⚠ Warum dieser Test existiert: Beim Bau wurde der Sprengsatz gezündet
# (Meldungstext zerstört + Link auf LINK_DATENQUELLEN zurückgedreht) — **373
# Tests blieben grün**. Es gab für diese drei Meldungen keinen Prüfer. Reinste
# F-27/F-30/F-51-Klasse („Text nennt einen Weg, den es nicht gibt"), und bei
# F-51 war die Lehre dieselbe: der Test hatte die falsche Aussage
# festgeschrieben. Hier hatte er sie gar nicht erst angesehen.

from backend.services.daten_checker.kategorien import LINK_INTEGRATION  # noqa: E402


def _mqtt_meldungen(befunde):
    return [b for b in befunde if "MQTT-Topic" in b.meldung or "Subscriber" in b.meldung]


@pytest.mark.asyncio
async def test_ausweg_nennt_integration_statt_der_v3_navigation(db, _inbound_laeuft):
    """Jede MQTT-Meldung weist nach Einstellungen → Integration — Text UND Link."""
    anlage = Anlage(anlagenname="Haus", leistung_kwp=10.0, sensor_mapping={})
    db.add(anlage)
    await db.flush()

    befunde = await DatenChecker(db=db)._check_mqtt_topic_abdeckung(anlage)
    gemeldet = _mqtt_meldungen(befunde)
    assert gemeldet, "Gegenprobe: ohne Befund prüft dieser Test nichts"

    for b in gemeldet:
        details = b.details or ""
        # Der Weg, den es nicht mehr gibt — in keiner Schreibweise.
        assert "Daten → Einrichtung" not in details, b.meldung
        assert "MQTT-Inbound deaktivieren" not in details, b.meldung
        # Der Weg, den es gibt.
        assert "Einstellungen → Integration" in details, b.meldung
        assert b.link == LINK_INTEGRATION, b.meldung


@pytest.mark.asyncio
async def test_auch_die_subscriber_info_weist_nach_integration(db, monkeypatch):
    """Der dritte Text: MQTT ist aktiviert, aber der Subscriber läuft nicht.
    Er trägt denselben Ausweg und lief bis N-316 auf dieselbe Fehlweisung."""
    from backend.models.settings import Settings as SettingsModel

    class _Aus:
        _running = False
        cache = _FakeCache()

    monkeypatch.setattr(
        "backend.services.mqtt_inbound_service.get_mqtt_inbound_service",
        lambda: _Aus(),
    )
    db.add(SettingsModel(key="mqtt_inbound", value={"enabled": True}))
    anlage = Anlage(anlagenname="Haus", leistung_kwp=10.0, sensor_mapping={})
    db.add(anlage)
    await db.flush()

    befunde = await DatenChecker(db=db)._check_mqtt_topic_abdeckung(anlage)
    treffer = [b for b in befunde if "Subscriber" in b.meldung]
    assert treffer, "Gegenprobe: die INFO-Meldung muss hier entstehen"
    for b in treffer:
        assert "Daten → Einrichtung" not in (b.details or "")
        assert "Einstellungen → Integration" in (b.details or "")
        assert b.link == LINK_INTEGRATION


# ─── #425 (gruaGit): die Wallbox-Regel gilt auch für die Topic-Erwartung ────
#
# Der Energieprofil-Check überspringt ein E-Auto, dessen Ladung eine Wallbox mit
# Ladezähler deckt; der MQTT-Check erwartete dessen Energie-Topics trotzdem —
# seit v4.0.51 auch „Heim: gesamt" (`ladung_kwh`), für das kein Bestand eine
# gespeicherte Wahl hat. Gemeldet als „erwartet, nie empfangen".
#
# ⚠ Die Probe oben (`test_meldung_traegt_den_vollen_topic_pfad`) legt das Auto
# mit `typ="e_auto"` an — den Registry-Schlüssel gibt es nicht (`e-auto`), sie
# prüft damit nichts über das Auto. Hier richtig geschrieben.

from datetime import datetime  # noqa: E402

from backend.services.mqtt_topic_registry import build_expected_topics  # noqa: E402


class _CacheAllesDaAusser:
    """Inbound-Cache, in dem jedes erwartete Topic angekommen ist — außer den
    genannten. So steht in der „nie empfangen"-Zeile genau, was der Check von
    den stummen Topics noch erwartet (und die Sechser-Grenze greift nicht).

    Ein FESTER Zeitstempel (keine Prozessuhr, N-167): angekommene Topics gelten
    damit als „veraltet", nie als „nie empfangen" — geprüft wird nur Letzteres."""

    def __init__(self, anlage_id: int, eintraege: list[dict], stumm: set[tuple]):
        jetzt = datetime(2026, 1, 1, 12, 0)
        live: dict = {"basis": {}, "inv": {}}
        energy: dict = {}
        for e in eintraege:
            mk = e["match_key"]
            if tuple(mk) in stumm or not e.get("topic"):
                continue
            if mk[0] == "basis_live":
                live["basis"][mk[1]] = (1.0, jetzt)
            elif mk[0] == "inv_live":
                live["inv"].setdefault(mk[1], {})[mk[2]] = (1.0, jetzt)
            elif mk[0] == "basis_energy":
                energy[mk[1]] = (1.0, jetzt)
            elif mk[0] == "inv_energy":
                energy[f"inv/{mk[1]}/{mk[2]}"] = (1.0, jetzt)
        self._live = {anlage_id: live}
        self._energy = {anlage_id: energy}

    def get_all_live_raw(self):
        return self._live

    def get_all_energy_raw(self):
        return self._energy


async def _stumm_gemeldet(db, monkeypatch, anlage, stumm: set[tuple], mqtt_zaehler: set[str]) -> str:
    """Die „nie empfangen"-Zeile, wenn nur `stumm` nicht ankommt.

    ``mqtt_zaehler`` reicht die Menge der angekommenen MQTT-Zählerstände durch, wie
    der Orchestrator (`DatenChecker.check_anlage`) — ohne Zeitfenster der Prozessuhr."""
    eintraege = await build_expected_topics(db, anlage)

    class _Service:
        _running = True
        cache = _CacheAllesDaAusser(anlage.id, eintraege, stumm)

    monkeypatch.setattr(
        "backend.services.mqtt_inbound_service.get_mqtt_inbound_service",
        lambda: _Service(),
    )
    befunde = await DatenChecker(db=db)._check_mqtt_topic_abdeckung(anlage, mqtt_zaehler)
    treffer = [b for b in befunde if "nie empfangen" in b.meldung]
    return treffer[0].details if treffer else ""


async def _anlage_mit_auto(db, *, v2h: bool = False):
    anlage = Anlage(anlagenname="Haus", leistung_kwp=10.0, sensor_mapping={})
    db.add(anlage)
    await db.flush()
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="WB")
    auto = Investition(
        anlage_id=anlage.id, typ="e-auto", bezeichnung="ID3",
        parameter={"v2h_faehig": True} if v2h else {},
    )
    db.add_all([wb, auto])
    await db.flush()
    return anlage, wb, auto


def _wb_mqtt(wb) -> set[str]:
    """gruaGits Wallbox: Ladezähler per MQTT, Stände kommen an (`sensor_key` wie
    `snapshot/reader.mqtt_zaehler_keys`)."""
    return {f"inv:{wb.id}:ladung_kwh"}


def _auto_stumm(auto, *felder_energy, live=()) -> set[tuple]:
    return (
        {("inv_energy", str(auto.id), f) for f in felder_energy}
        | {("inv_live", str(auto.id), f) for f in live}
    )


@pytest.mark.asyncio
async def test_wallbox_mit_ladezaehler_nimmt_dem_auto_die_ladefelder(db, monkeypatch):
    """(a) gruaGits Fall: Wallbox misst per MQTT ⇒ Lade-/Verbrauchsfelder am Auto
    nicht erwartet; Ladestand und km bleiben erwartet."""
    anlage, wb, auto = await _anlage_mit_auto(db)
    stumm = _auto_stumm(
        auto, "ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh", "verbrauch_kwh",
        "km_gefahren", live=("soc",),
    )
    details = await _stumm_gemeldet(db, monkeypatch, anlage, stumm, _wb_mqtt(wb))
    pfad = f"/inv/{auto.id}_ID3/"
    assert f"{pfad}km_gefahren" in details
    assert f"{pfad}soc" in details
    for feld in ("ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh", "verbrauch_kwh"):
        assert f"{pfad}{feld}" not in details, feld


@pytest.mark.asyncio
async def test_ohne_wallbox_zaehler_bleiben_die_ladefelder_erwartet(db, monkeypatch):
    """(b) Gegenprobe: dieselbe Anlage, aber die Wallbox liefert keinen Zähler ⇒
    das Auto trägt seine Ladung selbst, die Felder bleiben erwartet."""
    anlage, _wb, auto = await _anlage_mit_auto(db)
    stumm = _auto_stumm(
        auto, "ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh", "verbrauch_kwh",
    )
    details = await _stumm_gemeldet(db, monkeypatch, anlage, stumm, set())
    pfad = f"/inv/{auto.id}_ID3/"
    for feld in ("ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh", "verbrauch_kwh"):
        assert f"{pfad}{feld}" in details, feld


@pytest.mark.asyncio
async def test_v2h_bleibt_neben_der_wallbox_erwartet(db, monkeypatch):
    """(c) Die Rückspeisung misst keine Wallbox: `v2h_entladung_kwh` ohne
    gespeicherte Wahl bleibt erwartet, auch wenn die Wallbox die Ladung deckt."""
    anlage, wb, auto = await _anlage_mit_auto(db, v2h=True)
    stumm = _auto_stumm(auto, "v2h_entladung_kwh", "ladung_kwh")
    details = await _stumm_gemeldet(db, monkeypatch, anlage, stumm, _wb_mqtt(wb))
    pfad = f"/inv/{auto.id}_ID3/"
    assert f"{pfad}v2h_entladung_kwh" in details
    assert f"{pfad}ladung_kwh" not in details
