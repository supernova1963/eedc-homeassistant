"""Standalone-Gleichstand Sitzung 1 — Betriebsmodus über MQTT (HA-Bauform §9, Bauplan Fassung 2, S1-1 … S1-5).

* **S1-1 Kanon:** Zahlencodes «0»…«5» stehen in der EINEN Werte-Tabelle (`core/betriebsmodus._ZUSTAND_ZU_KANON`) und
  gelten **nur auf dem MQTT-Weg** (`codes=True`, Entscheid des Masters zu H1 = A): ein HA-Sensor mit «1» bleibt
  `unbestimmt`, der Daten-Checker nennt ihn, Werte-Liste und Klartext am HA-Feld zeigen keine Codes; «1.0» (Gateway)
  wird an einer Stelle zu «1»; unbekannt ⇒ `unbestimmt`.
* **S1-2 Inbound:** ein Zustandsfeld landet als roher String im Cache, jedes andere bleibt `float`;
  `_collect_values` lässt Zustandskeys aus den Leistungswerten (Ü8).
* **S1-3 Fläche:** `/felder` liefert den Modus über Inbound als `wert_text`/`wert_klartext`, nie als `wert`; das
  Feld hat sein Topic, ist nicht `nur_ha`; die Monitor-Liste führt das Topic, der Initialwert «0» nicht.
* **S1-4 Live:** `_erhebe` = HA für Geräte mit Modus-Entität, MQTT für die übrigen; HA gewinnt über die
  ``live``-Entität, nie über ``quellen``; Suffix-Topics nach N-340; keine Aktion.
* **S1-5 Mitschrift:** Haltezeit je Modus im Cache, Snapshot-Zeilen nur bei Verbindung, Stunde über `ts_unix` mit
  derselben Stundenregel wie die eigene Summe des MQTT-Stroms (`schreiber._stunden_start_ts`, lokale volle Stunde —
  Modus und Strom derselben Stunde tragen denselben `start_ts`; Herbst: zwei `start_ts`), Mittel der
  vorhandenen Fenster, eigene `statistic_id` je Quelle, «Strom je Betriebsart» baut darauf.

Die Uhr steht fest (``jetzt=`` an Cache und Schreiber); keine Probe liest die echte Uhr für eine Aussage.

Schwesterdateien: test_kanal_mitschrift_betriebsart.py (HA-Hülle), test_kanal_modus_strom.py, test_398_betriebsmodus_live.py,
test_263_k2_betriebsmodus_lesen_mitschreiben.py, test_p433_0_betriebsmodus_werte.py.
"""

from __future__ import annotations

import calendar
import os
import time as _zeit
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, text

from backend.core.betriebsmodus import (
    AUS,
    MQTT_CODES,
    BETRIEBSMODUS_KANON,
    ENTFEUCHTEN,
    HEIZEN,
    KUEHLEN,
    LUEFTEN,
    UNBESTIMMT,
    WARMWASSER,
    betriebsmodus_klartext,
    betriebsmodus_werte_je_betriebsart,
    betriebsmodus_werte_klartext,
    ist_bekannter_betriebsmodus_wert,
    modus_aus_zustaenden,
    normalisiere_betriebsmodus,
)
from backend.models.kanal import FAMILIE_MITSCHRIFT, Kanal, KanalQuelle, KanalStatistik
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401 — Tabelle für `/felder`
from backend.models.mqtt_live_snapshot import MqttLiveSnapshot
from backend.services import betriebsmodus_live as bml
from backend.services import mqtt_inbound_service as mis
from backend.services.mqtt_inbound_service import MqttInboundCache
from backend.tests import factories

_STUNDE = 3600
#: Eine feste Stunde im Sommer, Unix-Sekunden auf einer vollen UTC-Stunde (UTC-unabhängig: eine ganze Stunde).
T0 = calendar.timegm((2026, 6, 10, 8, 0, 0))


@pytest.fixture(autouse=True)
def _ohne_takt_und_singleton(monkeypatch):
    """Jede Probe ohne Modus-Takt und mit eigenem Inbound-Singleton (kein Rest aus anderen Proben)."""
    bml.cache_leeren()
    monkeypatch.setattr(mis, "_mqtt_inbound_service", None)
    yield
    bml.cache_leeren()


def _stelle_inbound(monkeypatch) -> MqttInboundCache:
    cache = MqttInboundCache()
    monkeypatch.setattr(mis, "_mqtt_inbound_service", SimpleNamespace(cache=cache))
    return cache


def _topic(anlage_id: int, inv_id: int, key: str) -> str:
    return f"eedc/{anlage_id}_Test/live/inv/{inv_id}_WP/{key}"


@contextmanager
def _prozesszone(zone: str):
    """Die Prozesszone für die Dauer des Blocks (``TZ`` + ``time.tzset``) — Muster aus test_kanal_stunden_gleichheit.py."""
    alt = os.environ.get("TZ")
    os.environ["TZ"] = zone
    _zeit.tzset()
    try:
        yield
    finally:
        if alt is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = alt
        _zeit.tzset()


# ═══ S1-1 Kanon ══════════════════════════════════════════════════════════════

@pytest.mark.parametrize("code,kanon", [
    ("0", AUS), ("1", HEIZEN), ("2", WARMWASSER), ("3", KUEHLEN), ("4", LUEFTEN), ("5", ENTFEUCHTEN),
])
def test_jeder_code_hat_seinen_kanon_wert_auf_dem_mqtt_weg(code, kanon):
    assert normalisiere_betriebsmodus(code, codes=True) == kanon
    assert normalisiere_betriebsmodus(f"{code}.0", codes=True) == kanon, "Gateway reicht «1.0» weiter"
    assert ist_bekannter_betriebsmodus_wert(code, codes=True)
    assert ist_bekannter_betriebsmodus_wert(f" {code}.00 ", codes=True)


@pytest.mark.parametrize("code", sorted(MQTT_CODES))
def test_ha_ziffer_bleibt_unbestimmt_und_unbekannt(code):
    """Entscheid H1 = A: eine Ziffer aus einem HA-Sensor ist ein Hersteller-Rohcode — eedc rät nicht (wie am HEAD)."""
    assert normalisiere_betriebsmodus(code) == UNBESTIMMT
    assert normalisiere_betriebsmodus(f"{code}.0") == UNBESTIMMT
    assert not ist_bekannter_betriebsmodus_wert(code)
    assert betriebsmodus_klartext(code) == "Unbestimmt"
    assert MQTT_CODES == {"0", "1", "2", "3", "4", "5"}


@pytest.mark.parametrize("roh", ["6", "abc", "1.5", "-1", "10"])
def test_unbekannter_code_ist_unbestimmt_und_kein_bekannter_wert(roh):
    assert normalisiere_betriebsmodus(roh, codes=True) == UNBESTIMMT
    assert not ist_bekannter_betriebsmodus_wert(roh, codes=True)


def test_woerter_bleiben_wie_sie_sind():
    assert normalisiere_betriebsmodus("heat") == HEIZEN
    assert normalisiere_betriebsmodus(" Warmwasser ") == WARMWASSER
    assert normalisiere_betriebsmodus("auto") == UNBESTIMMT
    assert normalisiere_betriebsmodus("unavailable") is None
    assert normalisiere_betriebsmodus("") is None


def test_klartext_nennt_die_codes_nur_auf_dem_mqtt_weg():
    """«Heizen (heat, heizen, 1)» mit `codes=True` — dieselbe Tabelle; ohne (HA-Feld, Checker) wie am HEAD."""
    satz = betriebsmodus_werte_klartext(codes=True)
    assert "Heizen (heat, heizen, 1)" in satz
    assert "Aus (off, aus, 0)" in satz
    assert "Kühlen (cool, kuehlen, kühlen, 3)" in satz
    ohne = betriebsmodus_werte_klartext()
    assert "Heizen (heat, heizen) ·" in ohne and not any(ch.isdigit() for ch in ohne)
    assert betriebsmodus_werte_je_betriebsart()[0]["werte"] == ["heat", "heizen"]
    assert betriebsmodus_werte_je_betriebsart(codes=True)[0]["werte"] == ["heat", "heizen", "1"]


async def test_checker_meldet_eine_ha_ziffer_wie_am_head(db, monkeypatch):
    """Ein HA-Sensor mit «1» (Viessmann-Rohcode) bekommt weiter die INFO «unbekannter Wert», ohne Codes im Text."""
    from backend.tests.test_p433_0_betriebsmodus_werte import _FakeHa as _P433Ha
    from backend.tests.test_p433_0_betriebsmodus_werte import _anlage_mit_modus, _meldungen

    anlage, inv = await _anlage_mit_modus(db)
    ergebnisse = await _meldungen(db, anlage, monkeypatch, _P433Ha({"sensor.wp_prioritaet": ("1", None)}))
    assert len(ergebnisse) == 1 and ergebnisse[0].investition_id == inv.id
    assert "„1“" in ergebnisse[0].meldung
    assert betriebsmodus_werte_klartext() in ergebnisse[0].details


async def test_tagesaggregation_liest_eine_ha_ziffer_als_unbestimmt(db):
    """Der HA-Verlauf (`_get_betriebsmodus_history`) deutet «1» nicht als Heizen — die Stunde bleibt unbestimmt."""
    from unittest.mock import patch

    from backend.services.energie_profil import _helpers
    from backend.tests import ha_lts_helfer

    a = await factories.anlage(db, sensor_mapping={"basis": {}, "investitionen": {}})
    wp = await factories.investition(db, a.id, "waermepumpe")
    a.sensor_mapping = {"basis": {}, "investitionen": {str(wp.id): {"live": {"betriebsmodus": "sensor.wp_raw"}}}}
    await db.commit()
    tag = date(2026, 6, 10)
    with patch("backend.services.ha_state_service.get_ha_state_service",
               lambda: ha_lts_helfer.ZustandsVerlauf({"sensor.wp_raw": [(datetime(2026, 6, 9, 22), "1")]})):
        m = await _helpers._get_betriebsmodus_history(a, a.sensor_mapping, tag, db)
    assert m[3] == {wp.id: UNBESTIMMT}
    assert m.anteile[3][wp.id] == {UNBESTIMMT: 1.0}


def test_ein_geraet_mehrere_modus_topics_nach_n340():
    assert modus_aus_zustaenden({"betriebsmodus": "1", "betriebsmodus-3": "heizen", "leistung_w": 5.0}) == HEIZEN
    assert modus_aus_zustaenden({"betriebsmodus": "1", "betriebsmodus-3": "2"}) is None
    assert modus_aus_zustaenden({"betriebsmodus": "unknown", "betriebsmodus-3": "3"}) == KUEHLEN
    assert modus_aus_zustaenden({"leistung_w": 5.0}) is None
    assert modus_aus_zustaenden(None) is None


# ═══ S1-2 Inbound ════════════════════════════════════════════════════════════

@pytest.mark.parametrize("payload,erwartet", [("2", "2"), (" warmwasser ", "warmwasser"), ("abc", "abc"), ("1.0", "1.0")])
def test_zustandsfeld_haelt_den_rohen_string(payload, erwartet):
    c = MqttInboundCache()
    c.on_message(_topic(1, 39, "betriebsmodus"), payload, jetzt=T0)
    assert c.get_live_inv(1, "39") == {"betriebsmodus": erwartet}


def test_zahl_auf_w_key_unveraendert_und_string_verworfen():
    c = MqttInboundCache()
    c.on_message(_topic(1, 39, "leistung_w"), "812.5", jetzt=T0)
    c.on_message(_topic(1, 39, "leistung_w"), "warmwasser", jetzt=T0)
    assert c.get_live_inv(1, "39") == {"leistung_w": 812.5}
    # Energy-Topic mit dem Modus-Namen ist kein Zustand: float oder nichts.
    c.on_message("eedc/1_Test/energy/inv/39_WP/betriebsmodus", "heizen", jetzt=T0)
    assert c.get_energy_data(1) == {}


def test_suffix_key_ist_zustand_und_leerer_payload_wird_verworfen():
    c = MqttInboundCache()
    c.on_message(_topic(1, 39, "betriebsmodus-3"), "kuehlen", jetzt=T0)
    c.on_message(_topic(1, 39, "betriebsmodus"), "   ", jetzt=T0)
    assert c.get_live_inv(1, "39") == {"betriebsmodus-3": "kuehlen"}


async def test_collect_values_laesst_den_modus_aus_den_leistungswerten(db, monkeypatch):
    """Ü8: auch mit B8-Stempel auf dem Modus-Feld landet kein String in `inv_values`."""
    from backend.services.live_power_service import LivePowerService
    from backend.services.live_sensor_config import extract_quellen_live

    cache = _stelle_inbound(monkeypatch)
    a = await factories.anlage(db, sensor_mapping={"quellen": {"inv_live_39_betriebsmodus": {"quelle": "mqtt_inbound_standard"}}})
    cache.on_message(_topic(a.id, 39, "betriebsmodus"), "2", jetzt=T0)
    cache.on_message(_topic(a.id, 39, "leistung_w"), "900", jetzt=T0)
    _qb, quellen_inv, _ha = extract_quellen_live(a)
    assert quellen_inv == {"39": {"betriebsmodus": ("mqtt_inbound_standard", None, False)}}
    _basis, inv = LivePowerService()._collect_values(a, {}, {}, {}, None, None, {}, quellen_inv)
    assert inv == {"39": {"leistung_w": 900.0}}
    assert all(isinstance(v, float) for werte in inv.values() for v in werte.values())


# ═══ S1-3 Fläche, Topics ═════════════════════════════════════════════════════

async def _anlage_wp(db, *, mapping: dict | None = None, bezeichnung: str = "WP"):
    a = await factories.anlage(db, anlagenname="Test", sensor_mapping={})
    wp = await factories.investition(db, a.id, "waermepumpe", bezeichnung=bezeichnung,
                                     anschaffungsdatum=date(2024, 1, 1), parameter={"wp_art": "luft_wasser"})
    if mapping is not None:
        a.sensor_mapping = mapping
    await db.commit()
    return a, wp


async def test_felder_zeigen_den_mqtt_modus_als_text_nie_als_zahl(db, monkeypatch):
    from backend.api.routes.datenquellen import get_datenquellen_felder

    cache = _stelle_inbound(monkeypatch)
    a, wp = await _anlage_wp(db)
    cache.on_message(_topic(a.id, wp.id, "betriebsmodus"), "warmwasser", jetzt=T0)
    antwort = await get_datenquellen_felder(a.id, db=db)
    gruppe = next(g for g in antwort["gruppen"] if g["id"] == f"inv:{wp.id}")
    modus = next(f for f in gruppe["felder"] if f["feld"] == "betriebsmodus")
    assert modus["quelle"] == "mqtt_inbound_standard"
    assert modus["wert"] is None
    assert modus["wert_text"] == "warmwasser"
    assert modus["wert_klartext"] == "Warmwasser"
    assert modus["standard_topic"].endswith(f"/live/inv/{wp.id}_WP/betriebsmodus")
    assert modus["nur_ha"] is False and modus["zustand"] is True
    assert modus["zulaessige_werte"] == betriebsmodus_werte_je_betriebsart(codes=True), "am Inbound-Feld mit Codes"


def test_werte_liste_am_ha_feld_ohne_codes_am_inbound_feld_mit():
    """Eine Tabelle, ein Parameter: die Quelle des Feldes entscheidet, ob die Codes erscheinen."""
    from backend.api.routes.datenquellen import _zulaessige_werte

    feld = {"zustand": True, "feld": "betriebsmodus"}
    assert _zulaessige_werte(feld, "ha_app") == betriebsmodus_werte_je_betriebsart()
    assert _zulaessige_werte(feld, "keine") == betriebsmodus_werte_je_betriebsart()
    assert _zulaessige_werte(feld, "mqtt_inbound_standard") == betriebsmodus_werte_je_betriebsart(codes=True)
    assert _zulaessige_werte({"zustand": False, "feld": "leistung_w"}, "mqtt_inbound_standard") is None


async def test_felder_code_ueber_gateway_form_wird_gedeutet(db, monkeypatch):
    from backend.api.routes.datenquellen import get_datenquellen_felder

    cache = _stelle_inbound(monkeypatch)
    a, wp = await _anlage_wp(db)
    cache.on_message(_topic(a.id, wp.id, "betriebsmodus"), "1.0", jetzt=T0)
    antwort = await get_datenquellen_felder(a.id, db=db)
    modus = next(f for g in antwort["gruppen"] for f in g["felder"] if f["feld"] == "betriebsmodus")
    assert (modus["wert"], modus["wert_text"], modus["wert_klartext"]) == (None, "1.0", "Heizen")


async def test_monitor_liste_fuehrt_das_modus_topic_mit_kennzeichen(db):
    from backend.api.routes.live_mqtt_inbound import get_mqtt_topics

    a, wp = await _anlage_wp(db)
    topics = (await get_mqtt_topics(db=db, anlage_id=a.id))["topics"]
    modus = [t for t in topics if t["topic"].endswith(f"/inv/{wp.id}_WP/betriebsmodus")]
    assert len(modus) == 1 and modus[0]["zustand"] is True
    assert all(t["zustand"] is False for t in topics if t not in modus)


async def test_initialwert_null_geht_nicht_auf_das_modus_topic(db, monkeypatch):
    """Ein retained «0» hieße «Aus» — eedc erfände einen Modus für jede WP ohne Publisher."""
    from backend.api.routes import live_mqtt_inbound as lmi

    a, wp = await _anlage_wp(db)
    gesendet: list[list[str]] = []

    async def _publish(host, port, user, pw, topics):
        gesendet.append(list(topics))
        return len(topics)

    class _Svc:
        cache = MqttInboundCache()

        async def start(self):
            return True

        async def stop(self):
            return None

    monkeypatch.setattr(lmi, "_publish_initial_values", _publish)
    monkeypatch.setattr(mis, "init_mqtt_inbound_service", lambda *a_, **k_: _Svc())
    monkeypatch.setattr(mis, "get_mqtt_inbound_service", lambda: None)
    await lmi.save_mqtt_settings({"host": "broker.invalid", "port": 1883, "enabled": True}, db=db)
    assert gesendet, "Initial-Publish nicht erreicht — Probe zeigt aufs falsche Objekt"
    assert any(t.endswith(f"/inv/{wp.id}_WP/leistung_w") for t in gesendet[0])
    assert not any(t.endswith("/betriebsmodus") for t in gesendet[0])


async def test_abdeckungs_check_ueberwacht_das_modus_topic_weiter_nicht(db):
    """Ü4/#134: ein on-change-Modus wäre nach 2 min «veraltet» — die Erwartungsliste nimmt ihn heraus."""
    import inspect

    from backend.services.daten_checker import sensoren

    quelle = inspect.getsource(sensoren)
    assert 'not e.get("nur_manuell") and not e.get("zustand")' in quelle


# ═══ S1-4 Live ═══════════════════════════════════════════════════════════════

class _FakeHa:
    def __init__(self, zustaende: dict, verfuegbar: bool = True):
        self._z, self.is_available, self.abrufe = zustaende, verfuegbar, 0

    async def get_zustand_states_batch(self, ids):
        self.abrufe += 1
        return {e: self._z.get(e) for e in ids}


def _stelle_ha(monkeypatch, zustaende: dict, verfuegbar: bool = True) -> _FakeHa:
    dienst = _FakeHa(zustaende, verfuegbar)
    monkeypatch.setattr("backend.services.ha_state_service.get_ha_state_service", lambda: dienst)
    return dienst


@pytest.mark.parametrize("payload,erwartet", [("1", HEIZEN), ("0", AUS), ("6", UNBESTIMMT), ("warmwasser", WARMWASSER)])
async def test_live_modus_aus_mqtt(db, monkeypatch, payload, erwartet):
    cache = _stelle_inbound(monkeypatch)
    dienst = _stelle_ha(monkeypatch, {})
    a, wp = await _anlage_wp(db)
    cache.on_message(_topic(a.id, wp.id, "betriebsmodus"), payload, jetzt=T0)
    assert await bml.lade_betriebsmodus_live(db, a) == {wp.id: erwartet}
    assert await bml.lade_betriebsmodus_aktion_live(db, a) == {}, "über MQTT gibt es keine Aktion (E-SG-2)"
    assert dienst.abrufe == 0, "ohne HA-Modus-Entität wird HA nicht gefragt"


async def test_live_suffix_konflikt_laesst_das_geraet_fehlen(db, monkeypatch):
    cache = _stelle_inbound(monkeypatch)
    a, wp = await _anlage_wp(db)
    cache.on_message(_topic(a.id, wp.id, "betriebsmodus"), "1", jetzt=T0)
    cache.on_message(_topic(a.id, wp.id, "betriebsmodus-3"), "3", jetzt=T0)
    assert await bml.lade_betriebsmodus_live(db, a) == {}
    bml.cache_leeren()
    cache.on_message(_topic(a.id, wp.id, "betriebsmodus-3"), "heizen", jetzt=T0)
    assert await bml.lade_betriebsmodus_live(db, a) == {wp.id: HEIZEN}


async def test_live_ha_entitaet_gewinnt_auch_mit_b8_stempel(db, monkeypatch):
    """HA gewinnt über die `live`-Entität, nie über `quellen`: der B8-Stempel sagt nichts über HA (Ü3)."""
    cache = _stelle_inbound(monkeypatch)
    _stelle_ha(monkeypatch, {"climate.wp": ("cool", None)})
    a, wp = await _anlage_wp(db)
    a.sensor_mapping = {
        "investitionen": {str(wp.id): {"live": {"betriebsmodus": "climate.wp"}}},
        "quellen": {f"inv_live_{wp.id}_betriebsmodus": {"quelle": "mqtt_inbound_standard"}},
    }
    await db.commit()
    cache.on_message(_topic(a.id, wp.id, "betriebsmodus"), "2", jetzt=T0)
    assert await bml.lade_betriebsmodus_live(db, a) == {wp.id: KUEHLEN}


async def test_live_ha_ziffer_bleibt_unbestimmt(db, monkeypatch):
    """Live aus HA: ein Sensor mit «1» ist unbestimmt (wie am HEAD) — der Code gilt nur über MQTT."""
    _stelle_inbound(monkeypatch)
    _stelle_ha(monkeypatch, {"sensor.wp_raw": ("1", None)})
    a, wp = await _anlage_wp(db)
    a.sensor_mapping = {"investitionen": {str(wp.id): {"live": {"betriebsmodus": "sensor.wp_raw"}}}}
    await db.commit()
    assert await bml.lade_betriebsmodus_live(db, a) == {wp.id: UNBESTIMMT}


async def test_live_ha_geraet_faellt_ohne_ha_nicht_auf_mqtt_zurueck(db, monkeypatch):
    cache = _stelle_inbound(monkeypatch)
    _stelle_ha(monkeypatch, {"climate.wp": ("cool", None)}, verfuegbar=False)
    a, wp = await _anlage_wp(db, mapping={})
    a.sensor_mapping = {"investitionen": {str(wp.id): {"live": {"betriebsmodus": "climate.wp"}}}}
    await db.commit()
    cache.on_message(_topic(a.id, wp.id, "betriebsmodus"), "2", jetzt=T0)
    assert await bml.lade_betriebsmodus_live(db, a) == {}


async def test_live_quelle_keine_schliesst_mqtt_aus(db, monkeypatch):
    cache = _stelle_inbound(monkeypatch)
    a, wp = await _anlage_wp(db)
    a.sensor_mapping = {"quellen": {f"inv_live_{wp.id}_betriebsmodus": {"quelle": "keine"}}}
    await db.commit()
    cache.on_message(_topic(a.id, wp.id, "betriebsmodus"), "2", jetzt=T0)
    assert await bml.lade_betriebsmodus_live(db, a) == {}


async def test_live_ha_wp_und_mqtt_wp_in_einer_anlage(db, monkeypatch):
    cache = _stelle_inbound(monkeypatch)
    _stelle_ha(monkeypatch, {"climate.ha": ("heat", "idle")})
    a, wp_ha = await _anlage_wp(db, bezeichnung="HA")
    wp_mq = await factories.investition(db, a.id, "waermepumpe", bezeichnung="WP",
                                        anschaffungsdatum=date(2024, 1, 1), parameter={"wp_art": "luft_wasser"})
    a.sensor_mapping = {"investitionen": {str(wp_ha.id): {"live": {"betriebsmodus": "climate.ha"}}}}
    await db.commit()
    cache.on_message(_topic(a.id, wp_mq.id, "betriebsmodus"), "3", jetzt=T0)
    cache.on_message(_topic(a.id, wp_ha.id, "betriebsmodus"), "3", jetzt=T0)
    assert await bml.lade_betriebsmodus_live(db, a) == {wp_ha.id: HEIZEN, wp_mq.id: KUEHLEN}
    assert await bml.lade_betriebsmodus_aktion_live(db, a) == {wp_ha.id: "leerlauf"}


# ═══ S1-5 Haltezeit, Snapshot, Mitschrift ════════════════════════════════════

def test_haltezeit_20_min_heizen_40_min_warmwasser():
    """Halteregel je Nachricht: ein Modus gilt bis zur nächsten — die Fenster summieren sich zur Stunde."""
    c = MqttInboundCache()
    c.on_message(_topic(1, 39, "betriebsmodus"), "1", jetzt=T0)
    anteile = []
    for m in range(5, 65, 5):                       # Snapshot alle 5 min, die Nachricht «2» kommt um :20
        if m == 20:
            c.on_message(_topic(1, 39, "betriebsmodus"), "2", jetzt=T0 + 20 * 60)
        anteile.append(c.modus_anteile_abschliessen(T0 + m * 60)[1]["39"])
    assert anteile[:4] == [{HEIZEN: 1.0}] * 4
    assert anteile[4:] == [{WARMWASSER: 1.0}] * 8


def test_haltezeit_wechsel_mitten_im_fenster_und_ungesehenes():
    c = MqttInboundCache()
    c.on_message(_topic(1, 39, "betriebsmodus"), "unavailable", jetzt=T0)
    c.on_message(_topic(1, 39, "betriebsmodus"), "1", jetzt=T0 + 60)
    c.on_message(_topic(1, 39, "betriebsmodus"), "3", jetzt=T0 + 180)
    a = c.modus_anteile_abschliessen(T0 + 300)[1]["39"]
    assert a == pytest.approx({HEIZEN: 0.4, KUEHLEN: 0.4}), "die unavailable-Minute bleibt ungesehen"


def test_snapshot_schreibt_nur_bei_verbindung():
    from backend.services.mqtt_live_history_service import modus_zeilen

    c = MqttInboundCache()
    c.on_message(_topic(1, 39, "betriebsmodus"), "1", jetzt=T0)
    assert modus_zeilen(c, {1}, datetime(2026, 6, 10), T0 + 300) == [], "ohne Verbindung keine Zeile"
    c.verbinden()                                       # Reconnect: Fenster beginnen neu
    assert modus_zeilen(c, {1}, datetime(2026, 6, 10), T0 + 600) == [], "nach dem Reconnect erst mit Nachricht"
    c.on_message(_topic(1, 39, "betriebsmodus"), "2", jetzt=T0 + 600)
    rows = modus_zeilen(c, {1}, datetime(2026, 6, 10), T0 + 900)
    assert [(r.component_key, r.value_w, r.ts_unix) for r in rows] == [
        ("inv:39:betriebsmodus:warmwasser", 1.0, T0 + 900)]
    c.trennen()                                         # Broker weg
    c.on_message(_topic(1, 39, "betriebsmodus"), "1", jetzt=T0 + 1000)
    assert modus_zeilen(c, {1}, datetime(2026, 6, 10), T0 + 1200) == []
    assert modus_zeilen(c, {2}, datetime(2026, 6, 10), T0 + 1200) == []


async def test_snapshot_lauf_schreibt_modus_zeilen_mit_ts_unix(db, monkeypatch):
    from contextlib import asynccontextmanager

    from backend.services import mqtt_live_history_service as mlh

    a, wp = await _anlage_wp(db)
    cache = MqttInboundCache()
    cache.verbinden()
    t = _zeit.time()
    cache.on_message(_topic(a.id, wp.id, "betriebsmodus"), "3", jetzt=t - 120)
    cache.on_message(_topic(a.id, wp.id, "leistung_w"), "1500", jetzt=t - 120)

    @asynccontextmanager
    async def _session():
        yield db

    monkeypatch.setattr(mlh, "get_mqtt_inbound_service", lambda: SimpleNamespace(cache=cache))
    monkeypatch.setattr(mlh, "get_session", _session)
    assert await mlh.snapshot_live_cache() == 2
    rows = {r.component_key: r for r in (await db.execute(select(MqttLiveSnapshot))).scalars().all()}
    assert set(rows) == {f"inv:{wp.id}:leistung_w", f"inv:{wp.id}:betriebsmodus:kuehlen"}
    assert rows[f"inv:{wp.id}:betriebsmodus:kuehlen"].value_w == pytest.approx(1.0)
    assert all(r.ts_unix is not None for r in rows.values())


def _snap(anlage_id: int, inv_id: int, ts: int, modus: str, anteil: float = 1.0) -> MqttLiveSnapshot:
    return MqttLiveSnapshot(anlage_id=anlage_id, timestamp=datetime.fromtimestamp(ts),
                            component_key=f"inv:{inv_id}:betriebsmodus:{modus}", value_w=anteil, ts_unix=ts)


async def _mitschrift(db, a, inv_id: int) -> dict[str, dict[int, float]]:
    out: dict[str, dict[int, float]] = {}
    for modus in BETRIEBSMODUS_KANON:
        k = (await db.execute(select(Kanal).where(Kanal.anlage_id == a.id,
                                                  Kanal.key == f"modus:inv:{inv_id}:{modus}"))).scalar_one_or_none()
        if k is None:
            continue
        out[modus] = {r.start_ts: r.mean for r in (await db.execute(
            select(KanalStatistik).where(KanalStatistik.kanal_id == k.id))).scalars().all()}
    return out


async def test_mitschrift_mittel_der_stunde_und_laufende_stunde_nie(db):
    from backend.services.kanal.schreiber import schreibe_betriebsart_mitschrift_mqtt

    a, wp = await _anlage_wp(db)
    for m in range(5, 65, 5):                       # Stunde T0: 4 Fenster Heizen, 8 Fenster Warmwasser
        db.add(_snap(a.id, wp.id, T0 + m * 60 - 1, HEIZEN if m <= 20 else WARMWASSER))
    db.add(_snap(a.id, wp.id, T0 + _STUNDE + 300, KUEHLEN))       # laufende Stunde
    await db.commit()
    n = await schreibe_betriebsart_mitschrift_mqtt(db, a, datetime.fromtimestamp(T0 + _STUNDE + 600))
    await db.commit()
    z = await _mitschrift(db, a, wp.id)
    assert n == len(BETRIEBSMODUS_KANON)
    assert set(z) == set(BETRIEBSMODUS_KANON)
    assert {m: z[m][T0] for m in z} == pytest.approx(
        {m: {HEIZEN: 1 / 3, WARMWASSER: 2 / 3}.get(m, 0.0) for m in BETRIEBSMODUS_KANON})
    assert all(T0 + _STUNDE not in werte for werte in z.values()), "die laufende Stunde wird nie geschrieben"
    k = (await db.execute(select(Kanal).where(Kanal.key == f"modus:inv:{wp.id}:heizen"))).scalar_one()
    q = (await db.execute(select(KanalQuelle).where(KanalQuelle.kanal_id == k.id))).scalars().all()
    assert [(x.familie, x.statistic_id) for x in q] == [(FAMILIE_MITSCHRIFT, f"mqtt:inv/{wp.id}/betriebsmodus")]
    # Wiederholung schreibt nichts (schon-Schutz), die Zeile bleibt.
    assert await schreibe_betriebsart_mitschrift_mqtt(db, a, datetime.fromtimestamp(T0 + _STUNDE + 900)) == 0


async def test_mitschrift_teilstunde_nach_neustart_ist_mittel_der_vorhandenen_zeilen(db):
    from backend.services.kanal.schreiber import schreibe_betriebsart_mitschrift_mqtt

    a, wp = await _anlage_wp(db)
    db.add(_snap(a.id, wp.id, T0 + 45 * 60, HEIZEN))
    db.add(_snap(a.id, wp.id, T0 + 50 * 60, HEIZEN, 0.5))
    db.add(_snap(a.id, wp.id, T0 + 50 * 60, KUEHLEN, 0.5))
    # Bestandszeile ohne ts_unix (vor der Migration): wird nicht gelesen.
    db.add(MqttLiveSnapshot(anlage_id=a.id, timestamp=datetime.fromtimestamp(T0 + 10 * 60),
                            component_key=f"inv:{wp.id}:betriebsmodus:aus", value_w=1.0, ts_unix=None))
    await db.commit()
    await schreibe_betriebsart_mitschrift_mqtt(db, a, datetime.fromtimestamp(T0 + _STUNDE + 300))
    await db.commit()
    z = await _mitschrift(db, a, wp.id)
    assert z[HEIZEN][T0] == pytest.approx(0.75) and z[KUEHLEN][T0] == pytest.approx(0.25)
    assert z[AUS][T0] == 0.0


async def test_mitschrift_herbst_zwei_mal_zwei_uhr_sind_zwei_stunden(db):
    """25.10.2026, Europe/Berlin: 02:00 CEST und 02:00 CET — über `ts_unix` zwei `start_ts`."""
    from backend.services.kanal.schreiber import modus_anteile_je_stunde, schreibe_betriebsart_mitschrift_mqtt

    berlin = ZoneInfo("Europe/Berlin")
    erste = calendar.timegm((2026, 10, 25, 0, 0, 0))            # 02:00 CEST
    zweite = erste + _STUNDE                                     # 02:00 CET
    assert datetime.fromtimestamp(erste, berlin).hour == datetime.fromtimestamp(zweite, berlin).hour == 2
    a, wp = await _anlage_wp(db)
    for m in range(5, 65, 5):
        db.add(_snap(a.id, wp.id, erste + m * 60 - 1, HEIZEN))
        db.add(_snap(a.id, wp.id, zweite + m * 60 - 1, WARMWASSER))
    await db.commit()
    zeilen = (await db.execute(select(MqttLiveSnapshot.ts_unix, MqttLiveSnapshot.component_key,
                                      MqttLiveSnapshot.value_w))).all()
    with _prozesszone("Europe/Berlin"):                          # die lokale Stundenregel in der Umstellungs-Zone
        assert [ts for ts, _ in modus_anteile_je_stunde(zeilen)[wp.id]] == [erste, zweite]
        await schreibe_betriebsart_mitschrift_mqtt(db, a, datetime.fromtimestamp(zweite + _STUNDE + 60))
    await db.commit()
    z = await _mitschrift(db, a, wp.id)
    assert (z[HEIZEN][erste], z[WARMWASSER][erste]) == (1.0, 0.0)
    assert (z[HEIZEN][zweite], z[WARMWASSER][zweite]) == (0.0, 1.0)


async def test_mitschrift_ha_wp_und_mqtt_wp_je_eigene_quelle(db):
    from backend.services.energie_profil._helpers import ModusJeStunde
    from backend.services.kanal.schreiber import schreibe_betriebsart_mitschrift, schreibe_betriebsart_mitschrift_mqtt

    a, wp_ha = await _anlage_wp(db, bezeichnung="HA")
    wp_mq = await factories.investition(db, a.id, "waermepumpe", bezeichnung="WP",
                                        anschaffungsdatum=date(2024, 1, 1), parameter={"wp_art": "luft_wasser"})
    a.sensor_mapping = {"investitionen": {str(wp_ha.id): {"live": {"betriebsmodus": "climate.ha"}}}}
    await db.commit()
    for inv in (wp_ha, wp_mq):                       # auch die HA-WP publiziert — MQTT darf sie nicht schreiben
        for m in range(5, 65, 5):
            db.add(_snap(a.id, inv.id, T0 + m * 60 - 1, KUEHLEN))
    await db.commit()
    tag = datetime.fromtimestamp(T0).date()
    stunde = datetime.fromtimestamp(T0).hour + 1      # Slot h = [h-1, h)
    await schreibe_betriebsart_mitschrift(
        db, a, tag, ModusJeStunde({}, anteile={stunde: {wp_ha.id: {HEIZEN: 1.0}}}, entitaeten={wp_ha.id: "climate.ha"}),
        jetzt=datetime.fromtimestamp(T0 + 2 * _STUNDE))
    await schreibe_betriebsart_mitschrift_mqtt(db, a, datetime.fromtimestamp(T0 + 2 * _STUNDE))
    await db.commit()
    assert (await _mitschrift(db, a, wp_ha.id))[HEIZEN][T0] == 1.0, "HA-WP: HA-Mitschrift, MQTT schreibt nicht"
    assert (await _mitschrift(db, a, wp_mq.id))[KUEHLEN][T0] == 1.0
    ids = {}
    for inv in (wp_ha, wp_mq):
        k = (await db.execute(select(Kanal).where(Kanal.key == f"modus:inv:{inv.id}:heizen"))).scalar_one()
        ids[inv.id] = [q.statistic_id for q in (await db.execute(
            select(KanalQuelle).where(KanalQuelle.kanal_id == k.id))).scalars().all()]
    assert ids == {wp_ha.id: ["climate.ha"], wp_mq.id: [f"mqtt:inv/{wp_mq.id}/betriebsmodus"]}


async def test_strom_je_betriebsart_baut_auf_der_mqtt_mitschrift():
    """Die bestehende Probe «Stundenlauf schreibt den Kanal fort» mit MQTT-Mitschrift statt HA (Achsen-Form M05, MQTT)."""
    from backend.models import Anlage
    from backend.services.kanal.modus_strom import abdeckung_key, modus_strom_key
    from backend.services.kanal.schreiber import schreibe_kanaele_im_stundenlauf
    from backend.tests import achsen_matrix as am
    from backend.tests import kanal_bilanz_gleichheit as kg
    from backend.tests import pv_achse_matrix as mx

    async with kg.datenstand("achsen", "M05", "MQTT") as ds:
        wp = ds.ids["WP"]
        assert await _reihe(ds.db, abdeckung_key(wp)) == [], "MQTT-Datenstand ohne Mitschrift — Ausgangslage"
        bis = int(mx.JETZT.replace(minute=0).timestamp())
        stunden = [bis - h * _STUNDE for h in range(4, 0, -1)]          # vier abgeschlossene Stunden
        for s in stunden:
            for m in range(5, 65, 5):
                ds.db.add(_snap(ds.aid, wp, s + m * 60 - 1, HEIZEN))
        await ds.db.commit()
        anlage = (await ds.db.execute(select(Anlage).where(Anlage.id == ds.aid))).scalar_one()
        with am.umgebung(am.MATRIX_FORMEN["M05"], ds.svc):
            assert await schreibe_kanaele_im_stundenlauf(ds.db, anlage, mx.JETZT) is not None
        await ds.db.commit()
        abdeckung = dict(await _reihe(ds.db, abdeckung_key(wp)))
        heizen = dict(await _reihe(ds.db, modus_strom_key(wp, HEIZEN)))
        rest = dict(await _reihe(ds.db, modus_strom_key(wp, "rest")))
        assert set(stunden) <= set(abdeckung), "der abgeleitete Kanal deckt die Stunden der MQTT-Mitschrift"
        for vor, s in zip(stunden, stunden[1:]):
            assert abdeckung[s] - abdeckung[vor] == pytest.approx(1.0)
            assert heizen[s] - heizen[vor] > 0
            assert rest[s] - rest[vor] == pytest.approx(0.0)


async def test_modus_und_strom_derselben_stunde_tragen_denselben_start_ts(db):
    """Eine Stundenregel für beide MQTT-Familien (`_stunden_start_ts` = `_unix(_stunde_von(…))`): in Europe/Berlin tragen
    die Modus-Mitschrift und die eigene Summe des Stroms derselben Stunde denselben `start_ts`."""
    from sqlalchemy import insert

    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.services.kanal.schreiber import schreibe_betriebsart_mitschrift_mqtt, schreibe_eigene_summe

    a, wp = await _anlage_wp(db)
    with _prozesszone("Europe/Berlin"):
        beginn = datetime(2026, 6, 10, 10)                       # 10:00 Ortszeit
        beginn_ts = int(beginn.timestamp())
        await db.execute(insert(MqttEnergySnapshot), [
            {"anlage_id": a.id, "energy_key": "netzbezug_kwh", "value_kwh": 100.0 + i,
             "timestamp": beginn - timedelta(hours=1) + timedelta(minutes=5 * i)} for i in range(24)])
        for m in range(5, 65, 5):
            db.add(_snap(a.id, wp.id, beginn_ts + m * 60 - 1, HEIZEN))
        await db.commit()
        for zp in (beginn + timedelta(minutes=5), beginn + timedelta(hours=1, minutes=5)):
            await schreibe_eigene_summe(db, a, zp)
            await schreibe_betriebsart_mitschrift_mqtt(db, a, zp)
            await db.commit()
    strom = {ts for ts, _ in await _reihe(db, "basis:netzbezug")}
    modus = set((await _mitschrift(db, a, wp.id))[HEIZEN])
    assert beginn_ts in strom, sorted(strom)
    assert modus == {beginn_ts}, (sorted(modus), beginn_ts)


async def _reihe(db, key: str) -> list[tuple[int, float]]:
    return [(int(ts), float(s)) for ts, s in (await db.execute(text(
        "SELECT s.start_ts, s.sum FROM kanal_statistik s JOIN kanal k ON k.id = s.kanal_id "
        "WHERE k.key = :k ORDER BY s.start_ts"), {"k": key})).all()]


def test_migration_ts_unix_idempotent():
    from sqlalchemy import create_engine, inspect

    from backend.core.database import _migrate_mqtt_live_snapshot_ts_unix

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE mqtt_live_snapshots (id INTEGER PRIMARY KEY, anlage_id INTEGER, "
                          "timestamp DATETIME, component_key VARCHAR(120), value_w FLOAT)"))
        conn.execute(text("INSERT INTO mqtt_live_snapshots VALUES (1, 1, '2026-06-10 08:00:00', 'inv:1:leistung_w', 5.0)"))
        _migrate_mqtt_live_snapshot_ts_unix(conn)
        _migrate_mqtt_live_snapshot_ts_unix(conn)
        spalten = {c["name"] for c in inspect(conn).get_columns("mqtt_live_snapshots")}
        assert "ts_unix" in spalten
        assert conn.execute(text("SELECT ts_unix FROM mqtt_live_snapshots")).scalar() is None
    engine.dispose()
