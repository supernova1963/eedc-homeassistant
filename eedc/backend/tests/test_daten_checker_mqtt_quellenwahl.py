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
- Felder ohne Quellen-Eintrag, **die Pflicht sind** (der Kernfall aus #134 —
  Publisher-Automation fehlt). Ein stummes Inbound persistiert nichts, ist also
  unterscheidbar. Seit dem Entscheid Gernots vom 13.10.2026 gilt das nur noch
  für Pflichtfelder (dieselbe Einstufung wie die Datenquellen-Fläche); ein
  optionales Feld erwartet der Check nur, wenn es auf MQTT-Inbound oder
  Gateway zugeordnet ist (Abschnitt am Dateiende).
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


def _auf_inbound(anlage, match_keys, quelle: str = QUELLE_INBOUND) -> None:
    """Gespeicherte Quellenwahl MQTT-Inbound (bzw. ``quelle``) für diese Felder.

    Entscheid Gernot 13.10.2026: ein optionales Feld erwartet der Check nur,
    wenn es belegt ist. Die Proben zur Wallbox-Regel (#425) und zur Gerätefrage
    (N-746) belegen ihre optionalen Felder deshalb — ohne Eintrag fielen sie
    schon durch die Pflicht-Stufe heraus, und die Probe prüfte die Regel nicht
    mehr, um die es ihr geht.
    """
    quellen = dict((anlage.sensor_mapping or {}).get("quellen") or {})
    for mk in match_keys:
        quellen[feld_id_aus_match_key(mk)] = {"quelle": quelle}
    anlage.sensor_mapping = {**(anlage.sensor_mapping or {}), "quellen": quellen}


@pytest.mark.asyncio
async def test_wallbox_mit_ladezaehler_nimmt_dem_auto_die_ladefelder(db, monkeypatch):
    """(a) gruaGits Fall: Wallbox misst per MQTT ⇒ Lade-/Verbrauchsfelder am Auto
    nicht erwartet — auch wenn sie auf MQTT zugeordnet sind; Ladestand
    (zugeordnet) und km (Pflicht) bleiben erwartet."""
    anlage, wb, auto = await _anlage_mit_auto(db)
    stumm = _auto_stumm(
        auto, "ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh", "verbrauch_kwh",
        "km_gefahren", live=("soc",),
    )
    _auf_inbound(anlage, stumm - {("inv_energy", str(auto.id), "km_gefahren")})
    details = await _stumm_gemeldet(db, monkeypatch, anlage, stumm, _wb_mqtt(wb))
    pfad = f"/inv/{auto.id}_ID3/"
    assert f"{pfad}km_gefahren" in details
    assert f"{pfad}soc" in details
    for feld in ("ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh", "verbrauch_kwh"):
        assert f"{pfad}{feld}" not in details, feld


@pytest.mark.asyncio
async def test_ohne_wallbox_zaehler_bleiben_die_ladefelder_erwartet(db, monkeypatch):
    """(b) Gegenprobe: dieselbe Anlage, aber die Wallbox liefert keinen Zähler ⇒
    das Auto trägt seine Ladung selbst, die (zugeordneten) Felder bleiben erwartet."""
    anlage, _wb, auto = await _anlage_mit_auto(db)
    stumm = _auto_stumm(
        auto, "ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh", "verbrauch_kwh",
    )
    _auf_inbound(anlage, stumm)
    details = await _stumm_gemeldet(db, monkeypatch, anlage, stumm, set())
    pfad = f"/inv/{auto.id}_ID3/"
    for feld in ("ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh", "verbrauch_kwh"):
        assert f"{pfad}{feld}" in details, feld


@pytest.mark.asyncio
async def test_v2h_bleibt_neben_der_wallbox_erwartet(db, monkeypatch):
    """(c) Die Rückspeisung misst keine Wallbox: ein auf MQTT zugeordnetes
    `v2h_entladung_kwh` bleibt erwartet, auch wenn die Wallbox die Ladung deckt.
    (Bis 13.10.2026 „ohne gespeicherte Wahl" — seitdem erwartet der Check ein
    optionales Feld nur belegt, s. `_auf_inbound`.)"""
    anlage, wb, auto = await _anlage_mit_auto(db, v2h=True)
    stumm = _auto_stumm(auto, "v2h_entladung_kwh", "ladung_kwh")
    _auf_inbound(anlage, stumm)
    details = await _stumm_gemeldet(db, monkeypatch, anlage, stumm, _wb_mqtt(wb))
    pfad = f"/inv/{auto.id}_ID3/"
    assert f"{pfad}v2h_entladung_kwh" in details
    assert f"{pfad}ladung_kwh" not in details


# ─── N-746: erwartet wird nur, was es an diesem Gerät gibt ──────────────────
#
# Die Erwartungsliste kommt aus `get_alle_felder_fuer_investition` — ohne
# Bedingungsfilter, weil die Datenquellen-Fläche und die Migrationen alle Felder
# brauchen. Der Check nahm sie ungefiltert: ein E-Auto ohne „V2H-fähig" trug
# dauerhaft „…/v2h_entladung_kwh erwartet, nie empfangen", ein Speicher ohne
# Netzladung `ladung_netz_kwh`, eine Wärmepumpe ohne getrennte Strommessung
# `strom_heizen_kwh` und `strom_warmwasser_kwh` — Topics, auf die niemand
# publizieren soll. Die Frage steht jetzt in der Filterkette des Checks
# (`groesse_gibt_es_am_geraet`, harte Sorte), nicht in der Registry.

async def _anlage_mit_geraet(db, typ: str, parameter: dict):
    anlage = Anlage(anlagenname="Haus", leistung_kwp=10.0, sensor_mapping={})
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ=typ, bezeichnung="Geraet", parameter=parameter,
    )
    db.add(inv)
    await db.flush()
    return anlage, inv


_GERAETEFRAGE_FAELLE = [
    pytest.param("e-auto", {"v2h_faehig": True}, ("v2h_entladung_kwh",), id="e-auto-v2h"),
    pytest.param("speicher", {"laedt_aus_netz": True}, ("ladung_netz_kwh",), id="speicher-netzladung"),
    pytest.param(
        "waermepumpe", {"getrennte_strommessung": True},
        ("strom_heizen_kwh", "strom_warmwasser_kwh"), id="wp-getrennte-strommessung",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("typ, parameter_mit, felder", _GERAETEFRAGE_FAELLE)
async def test_groesse_ohne_geraet_wird_nicht_erwartet(
    db, monkeypatch, typ, parameter_mit, felder,
):
    """Ohne die Eigenschaft gibt es die Größe am Gerät nicht ⇒ kein erwartetes
    Topic, auch nicht mit Eintrag; mit ihr bleibt sie erwartet (Gegenprobe im
    selben Test). Beide Geräte tragen die Felder belegt (`_auf_inbound`) — sonst
    nähme die Pflicht-Stufe (13.10.2026) die optionalen schon vorher heraus."""
    anlage_ohne, inv_ohne = await _anlage_mit_geraet(db, typ, {})
    stumm = {("inv_energy", str(inv_ohne.id), f) for f in felder}
    _auf_inbound(anlage_ohne, stumm)
    details = await _stumm_gemeldet(db, monkeypatch, anlage_ohne, stumm, set())
    for feld in felder:
        assert f"/inv/{inv_ohne.id}_Geraet/{feld}" not in details, feld

    anlage_mit, inv_mit = await _anlage_mit_geraet(db, typ, parameter_mit)
    stumm = {("inv_energy", str(inv_mit.id), f) for f in felder}
    _auf_inbound(anlage_mit, stumm)
    details = await _stumm_gemeldet(db, monkeypatch, anlage_mit, stumm, set())
    for feld in felder:
        assert f"/inv/{inv_mit.id}_Geraet/{feld}" in details, feld


@pytest.mark.asyncio
@pytest.mark.parametrize("typ, parameter_mit, felder", _GERAETEFRAGE_FAELLE)
async def test_geraetefrage_nimmt_genau_diese_topics(
    db, _inbound_laeuft, typ, parameter_mit, felder,
):
    """Leerer Cache: der Unterschied zwischen beiden Geräten ist genau die Zahl
    der Größen, die es nur mit der Eigenschaft gibt — nicht mehr, nicht weniger.

    Seit dem Entscheid vom 13.10.2026 mit **allen** Feldern beider Anlagen auf
    MQTT zugeordnet: so ist die Pflicht-Stufe auf beiden Seiten durch, und der
    Unterschied misst allein die Gerätefrage (ohne Einträge zählte er bei der
    getrennten Strommessung zusätzlich das dann nur noch erweiterte
    `stromverbrauch_kwh`)."""
    anlage_ohne, _ = await _anlage_mit_geraet(db, typ, {})
    anlage_mit, _ = await _anlage_mit_geraet(db, typ, parameter_mit)
    for a in (anlage_ohne, anlage_mit):
        _auf_inbound(a, [e["match_key"] for e in await build_expected_topics(db, a)])
    assert await _anzahl(db, anlage_mit) - await _anzahl(db, anlage_ohne) == len(felder)


@pytest.mark.asyncio
async def test_split_klima_erwartet_kein_warmwasser(db, monkeypatch):
    """Dieselbe Regel, gemessene Reichweite: eine Luft-Luft-Anlage hat keinen
    Warmwasserkreis (N-304) — `warmwasser_kwh` ist dort kein erwartetes Topic,
    auch zugeordnet nicht."""
    anlage, inv = await _anlage_mit_geraet(db, "waermepumpe", {"wp_art": "luft_luft"})
    _auf_inbound(anlage, [("inv_energy", str(inv.id), "warmwasser_kwh")])
    details = await _stumm_gemeldet(
        db, monkeypatch, anlage, {("inv_energy", str(inv.id), "warmwasser_kwh")}, set(),
    )
    assert f"/inv/{inv.id}_Geraet/warmwasser_kwh" not in details


@pytest.mark.asyncio
async def test_erweitertes_feld_nur_zugeordnet_erwartet(db, monkeypatch):
    """Gegenprobe zur weichen Sorte: ein Betriebsart-Feld an einer
    Nicht-Luft-Luft-WP ist untypisch, nicht unmöglich (URTEIL_ERWEITERT) — die
    Gerätefrage (N-746) nimmt es NICHT heraus.

    ⚠ Bis zum 13.10.2026 hieß diese Probe „erweitertes Feld bleibt erwartet"
    und prüfte das Feld OHNE Eintrag. Entscheid Gernot 13.10.2026: ohne Eintrag
    erwartet der Check nur Pflichtfelder, und ein erweitertes Feld ist nie
    Pflicht (`get_feld_bedarf`, B2). Die Gerätefrage bleibt trotzdem geprüft:
    zugeordnet ist das Feld erwartet."""
    anlage, inv = await _anlage_mit_geraet(db, "waermepumpe", {})
    mk = ("inv_energy", str(inv.id), "betriebsart_strom_heizen_kwh")
    ohne = await _stumm_gemeldet(db, monkeypatch, anlage, {mk}, set())
    assert f"/inv/{inv.id}_Geraet/betriebsart_strom_heizen_kwh" not in ohne

    _auf_inbound(anlage, [mk])
    mit = await _stumm_gemeldet(db, monkeypatch, anlage, {mk}, set())
    assert f"/inv/{inv.id}_Geraet/betriebsart_strom_heizen_kwh" in mit


@pytest.mark.asyncio
async def test_warntext_nennt_den_handgriff_keine(db, _inbound_laeuft):
    """Der Ausweg für ein Feld, das man nicht über MQTT liefert, steht in der
    Meldung selbst — nicht nur im Handbuch (§4.8)."""
    anlage = Anlage(anlagenname="Haus", leistung_kwp=10.0, sensor_mapping={})
    db.add(anlage)
    await db.flush()
    details = await _betroffene(db, anlage)
    assert details, "Gegenprobe: ohne Befund prüft dieser Test nichts"
    assert "Einstellungen → Datenquellen" in details
    assert "„Keine“" in details
    # Entscheid 13.10.2026: der Text sagt, warum ein optionales Feld fehlt.
    assert "Optionale Felder erwartet eedc hier nur" in details


# ─── Entscheid Gernot 13.10.2026: erwartet wird Pflicht und Belegtes ────────
#
# Bis dahin galt „ohne Eintrag ⇒ erwartet" für jedes Feld. Gemessen am HEAD vor
# dem Entscheid: eine Luft-Wasser-WP ohne Einträge trug 17 Topics als „erwartet,
# nie empfangen" (12 Energie, davon acht Betriebsart-Felder, + 5 Live), ein
# E-Auto ohne Wallbox 9. Jetzt erwartet der Check ein Feld ohne gespeicherte
# Quellenwahl nur, wenn die Datenquellen-Fläche es als Pflicht einstuft
# (`stufe_bedarf_ein` über `_pflicht_ohne_eintrag`), und jedes Feld, das auf
# MQTT-Inbound oder Gateway zugeordnet ist. Folge, bewusst mitgenommen: ein
# optionales, nie zugeordnetes Feld meldet der Check nicht mehr.

from datetime import date  # noqa: E402


async def _erwartete_topics(db, monkeypatch, anlage) -> set[str]:
    """Die vollständige Menge der Topics, die der Check erwartet.

    Je Topic ein Lauf, in dem genau dieses eine stumm ist — so steht es in der
    „nie empfangen"-Zeile genau dann, wenn der Check es erwartet (die
    Sechser-Kürzung greift bei einem einzigen Topic nicht)."""
    erwartet = set()
    for e in await build_expected_topics(db, anlage):
        if not e.get("topic"):
            continue
        details = await _stumm_gemeldet(
            db, monkeypatch, anlage, {tuple(e["match_key"])}, set(),
        )
        if e["topic"] in details:
            erwartet.add(e["topic"])
    return erwartet


def _endungen(topics: set[str], marker: str) -> set[str]:
    """Letztes Pfad-Segment der Topics, die ``marker`` enthalten."""
    return {t.rsplit("/", 1)[1] for t in topics if marker in t}


@pytest.mark.asyncio
async def test_pflicht_ohne_eintrag_wird_erwartet(db, monkeypatch):
    """Speicher ohne Einträge: Ladung und Entladung sind Pflicht ⇒ erwartet."""
    anlage, inv = await _anlage_mit_geraet(db, "speicher", {})
    erwartet = await _erwartete_topics(db, monkeypatch, anlage)
    assert _endungen(erwartet, f"/energy/inv/{inv.id}_") == {"ladung_kwh", "entladung_kwh"}


@pytest.mark.asyncio
async def test_optional_ohne_eintrag_wird_nicht_erwartet(db, monkeypatch):
    """Speicher mit Netzladung, ohne Einträge: `ladung_netz_kwh` (optional, am
    Gerät vorhanden) und die Live-Felder sind nicht erwartet."""
    anlage, inv = await _anlage_mit_geraet(db, "speicher", {"laedt_aus_netz": True})
    erwartet = await _erwartete_topics(db, monkeypatch, anlage)
    assert "ladung_netz_kwh" not in _endungen(erwartet, f"/inv/{inv.id}_")
    assert _endungen(erwartet, f"/live/inv/{inv.id}_") == set()


@pytest.mark.asyncio
@pytest.mark.parametrize("quelle", [QUELLE_INBOUND, QUELLE_GATEWAY])
async def test_optional_mit_mqtt_eintrag_wird_erwartet(db, monkeypatch, quelle):
    """Dasselbe Feld, auf MQTT-Inbound bzw. Gateway zugeordnet ⇒ erwartet —
    ebenso ein zugeordnetes Live-Feld."""
    anlage, inv = await _anlage_mit_geraet(db, "speicher", {"laedt_aus_netz": True})
    _auf_inbound(anlage, [
        ("inv_energy", str(inv.id), "ladung_netz_kwh"),
        ("inv_live", str(inv.id), "soc"),
    ], quelle=quelle)
    erwartet = await _erwartete_topics(db, monkeypatch, anlage)
    assert "ladung_netz_kwh" in _endungen(erwartet, f"/energy/inv/{inv.id}_")
    assert _endungen(erwartet, f"/live/inv/{inv.id}_") == {"soc"}


@pytest.mark.asyncio
async def test_pflicht_auf_keine_wird_nicht_erwartet(db, monkeypatch):
    """#389 bleibt: ein Pflichtfeld, bewusst auf „Keine" gestellt, ist kein
    erwartetes Topic — die Pflicht-Stufe holt es nicht zurück."""
    anlage, inv = await _anlage_mit_geraet(db, "speicher", {})
    _auf_inbound(anlage, [("inv_energy", str(inv.id), "ladung_kwh")], quelle=QUELLE_KEINE)
    erwartet = await _erwartete_topics(db, monkeypatch, anlage)
    assert _endungen(erwartet, f"/energy/inv/{inv.id}_") == {"entladung_kwh"}


@pytest.mark.asyncio
async def test_luft_wasser_wp_ohne_eintraege_nur_pflichtfelder(db, monkeypatch):
    """Der Ausgangsfall: Luft-Wasser-WP ohne Einträge. Am HEAD vor dem Entscheid
    17 Topics am Gerät (12 Energie, davon acht Betriebsart-Felder, + 5 Live);
    jetzt die drei Pflichtfelder — Strom gesamt und die Wärmemenge auf beiden
    Wegen der ALTERNATIV-Gruppe `wp_waerme` (keiner ist belegt, also zeigt die
    Fläche beide als offen)."""
    anlage, inv = await _anlage_mit_geraet(db, "waermepumpe", {"wp_art": "luft_wasser"})
    erwartet = await _erwartete_topics(db, monkeypatch, anlage)
    am_geraet = {t for t in erwartet if f"/inv/{inv.id}_" in t}
    assert _endungen(am_geraet, "/energy/") == {
        "stromverbrauch_kwh", "heizenergie_kwh", "waerme_kwh",
    }
    assert len(am_geraet) == 3


@pytest.mark.asyncio
async def test_wp_waermemenge_ein_weg_belegt_deckt_den_anderen(db, monkeypatch):
    """ALTERNATIV-Gruppe wie auf der Fläche (N-391): ist `waerme_kwh` auf MQTT
    zugeordnet, ist `heizenergie_kwh` keine Pflicht mehr ⇒ nicht erwartet."""
    anlage, inv = await _anlage_mit_geraet(db, "waermepumpe", {"wp_art": "luft_wasser"})
    _auf_inbound(anlage, [("inv_energy", str(inv.id), "waerme_kwh")])
    erwartet = await _erwartete_topics(db, monkeypatch, anlage)
    assert _endungen(erwartet, f"/energy/inv/{inv.id}_") == {
        "stromverbrauch_kwh", "waerme_kwh",
    }


@pytest.mark.asyncio
async def test_basis_felder_nach_derselben_regel(db, monkeypatch):
    """Anlage ohne Geräte, ohne Einträge: die drei Pflicht-Zählerstände sind
    erwartet, die fünf Live-Felder (optional) nicht; ein zugeordnetes
    Live-Feld ist erwartet."""
    anlage = Anlage(anlagenname="Haus", leistung_kwp=10.0, sensor_mapping={})
    db.add(anlage)
    await db.flush()
    erwartet = await _erwartete_topics(db, monkeypatch, anlage)
    assert _endungen(erwartet, "/energy/") == {
        "einspeisung_kwh", "netzbezug_kwh", "pv_gesamt_kwh",
    }
    assert _endungen(erwartet, "/live/") == set()

    _auf_inbound(anlage, [("basis_live", "netzbezug_w")])
    erwartet = await _erwartete_topics(db, monkeypatch, anlage)
    assert _endungen(erwartet, "/live/") == {"netzbezug_w"}


@pytest.mark.asyncio
async def test_basis_pv_gesamt_gedeckt_durch_belegtes_modul(db, monkeypatch):
    """ALTERNATIV-Gruppe `pv_energie` über die Ebenen (N-456: die Anlagen-Ebene
    deckt in beide Richtungen): trägt ein PV-Modul seinen Zähler per HA-Sensor,
    ist `pv_gesamt_kwh` keine Pflicht mehr — wie auf der Fläche."""
    anlage, inv = await _anlage_mit_geraet(db, "pv-module", {})
    vorher = await _erwartete_topics(db, monkeypatch, anlage)
    assert "pv_gesamt_kwh" in _endungen(vorher, "/energy/")

    _auf_inbound(anlage, [("inv_energy", str(inv.id), "pv_erzeugung_kwh")], quelle=QUELLE_HA_APP)
    nachher = await _erwartete_topics(db, monkeypatch, anlage)
    assert "pv_gesamt_kwh" not in _endungen(nachher, "/energy/")


@pytest.mark.asyncio
@pytest.mark.parametrize("typ, parameter", [
    pytest.param("waermepumpe", {"wp_art": "luft_wasser"}, id="wp-luft-wasser"),
    pytest.param(
        "waermepumpe", {"wp_art": "luft_wasser", "getrennte_strommessung": True},
        id="wp-getrennte-strommessung",
    ),
    pytest.param("waermepumpe", {"wp_art": "luft_luft"}, id="split-klima"),
    pytest.param("e-auto", {}, id="e-auto"),
    pytest.param("speicher", {"laedt_aus_netz": True}, id="speicher"),
    pytest.param("pv-module", {}, id="pv-module"),
    pytest.param("balkonkraftwerk", {}, id="bkw"),
    pytest.param("wallbox", {}, id="wallbox"),
])
async def test_pflicht_ist_dieselbe_wie_auf_der_flaeche(db, monkeypatch, typ, parameter):
    """Eine Wahrheit, zwei Leser: ohne Einträge erwartet der Check genau die
    Felder, die die Datenquellen-Fläche (`get_datenquellen_felder`) als
    „pflicht" führt — abzüglich der Felder, die es am Gerät nicht gibt (N-746;
    die Fläche lässt sie nach `ohne_nicht_zuordenbare` gar nicht erst stehen
    oder führt sie dort, wo nur der Check sie herausnimmt)."""
    from backend.api.routes.datenquellen import get_datenquellen_felder
    from backend.core.field_definitions.bedingungen import groesse_gibt_es_am_geraet

    anlage = Anlage(anlagenname="Haus", leistung_kwp=10.0, sensor_mapping={})
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ=typ, bezeichnung="Geraet", parameter=parameter,
        anschaffungsdatum=date(2024, 1, 1),
    )
    db.add(inv)
    await db.flush()

    topic_je_fid = {
        feld_id_aus_match_key(e["match_key"]): e
        for e in await build_expected_topics(db, anlage)
    }
    erwartet = await _erwartete_topics(db, monkeypatch, anlage)

    # Die Fläche mit LEEREM Cache lesen: sonst sähe ihre 3-Stufen-Auflösung die
    # Werte der Ein-Topic-Läufe als „Inbound mit Wert", schriebe sie als Quelle
    # fest, und die Gruppen-Deckung verschöbe die Pflicht.
    class _Leer:
        _running = True
        cache = _CacheAllesDaAusser(anlage.id, [], set())

    monkeypatch.setattr(
        "backend.services.mqtt_inbound_service.get_mqtt_inbound_service",
        lambda: _Leer(),
    )
    resp = await get_datenquellen_felder(anlage.id, db)
    assert not (anlage.sensor_mapping or {}).get("quellen"), (
        "Gegenprobe: die Fläche darf hier nichts festschreiben — sonst vergleicht "
        "der Test zwei verschiedene Belegungen"
    )
    flaeche_pflicht = set()
    for g in resp["gruppen"]:
        for f in g["felder"]:
            e = topic_je_fid.get(f["id"])
            if f.get("bedarf") != "pflicht" or e is None or not e.get("topic"):
                continue
            if e["match_key"][0] in ("inv_energy", "inv_live") and not groesse_gibt_es_am_geraet(
                e["typ"], e["feld"], parameter,
            ):
                continue
            flaeche_pflicht.add(e["topic"])
    assert flaeche_pflicht, "Gegenprobe: ohne Pflichtfeld prüft dieser Test nichts"
    assert erwartet == flaeche_pflicht
