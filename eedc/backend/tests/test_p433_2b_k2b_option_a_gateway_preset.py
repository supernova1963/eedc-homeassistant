"""P-433-2b K2b «Option A, Gateway-Text, Preset evcc» — Backend-Proben (Bauplan K2 Fassung 2 §1 K2-7/K2-8/K2-9,
§3b E1–E3, §5 K2b; Entscheid D3 Gateway-Knopf am Modus-Feld bleibt aus).

Was hier gesichert wird, und warum jede Gruppe existiert:

1. **Option A — Registry und Kanon.** Drei Rollen-Felder `evcc_verbunden`/`evcc_laedt`/`evcc_freigegeben` (Zustand,
   Kanon an/aus, HA-Domänen binary_sensor/sensor/input_boolean, nur live). ``on``/``true`` ⇒ an, ``off``/``false`` ⇒
   aus; ``1``/``0`` **nur** über MQTT (Sprengsatz S8: eine Ziffer in der HA-Tabelle) — eine HA-Ziffer ist ein fremder
   Wert mit Checker-INFO.
2. **Option A — Leser.** Der Ladezustand entsteht aus den drei Feldern, **nur wenn kein gemessener vorliegt**
   (Sprengsatz S7); ohne «lädt»/«freigegeben» nur verbunden/kein Fahrzeug.
3. **Gateway-Weiche.** An ein Zustandsfeld geht der Text unverändert (Faktor/Offset unangewendet), ein Wort auf ein
   Zahlenfeld bleibt ein Transform-Fehler ohne Republish (Sprengsatz S9); der Betriebsmodus bleibt beim Zahlen-Weg
   (D3, Modus-Pfad bitgleich); positionale Aufrufer bleiben.
4. **Preset «evcc Ladepunkt».** Zeilen, Faktoren nur mit belegter Einheit (Sprengsatz S10: Faktor ``1e-9`` auf
   Sekunden), Zustandsfelder ohne Faktor, Vorgaben der Variablen.
5. **Datenquellen, Wissensbasis.**

Schwesterdateien: test_p433_2b_k1_emob.py (K1-Felder, Kanal-Katalog inkl. Option-A-Felder), test_p433_2b_k2a_fahrzeug.py
(Textfeld, Inbound «leer ist ein Wert»), test_standalone_s1_betriebsmodus_mqtt.py (Modus über MQTT),
test_datenquellen_invert.py (positionaler Aufruf `transform_payload(…, True)`). Client: `DatenquellenZuordnung.k2b.test.tsx`.
"""

from __future__ import annotations

import asyncio
from datetime import date
from types import SimpleNamespace

import pytest

from backend.core import zustands_kanon as zk
from backend.core.field_definitions import ZUSTAND_LIVE_FELDER, get_live_felder_fuer_investition
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services import betriebsmodus_live as bml
from backend.services import mqtt_gateway_service as gws
from backend.services import mqtt_inbound_service as mis

OPTION_A = ("evcc_verbunden", "evcc_laedt", "evcc_freigegeben")


# ── 1 · Option A: Registry und Kanon ─────────────────────────────────────────

def test_registry_drei_rollen_felder_an_der_wallbox():
    felder = {f["key"]: f for f in get_live_felder_fuer_investition("wallbox", {})}
    for key in OPTION_A:
        f = felder[key]
        assert f["zustand"] is True and f["kanon"] == key and not f.get("text")
        assert f["ha_domaenen"] == ("binary_sensor", "sensor", "input_boolean")
        assert f["nur_live"] and f["erweitert"] and f["abschnitt"] == "zustand"
        assert "nur nötig ohne ladezustand-sensor" in f["hinweis"].lower()
        assert ("wallbox", key) in ZUSTAND_LIVE_FELDER
        assert key in zk.ZUSTANDS_FELDER
    assert not any(k in {f["key"] for f in get_live_felder_fuer_investition("e-auto", {})} for k in OPTION_A)


@pytest.mark.parametrize("feld", OPTION_A)
@pytest.mark.parametrize("roh,kanon", [("on", "an"), ("ON ", "an"), ("true", "an"), ("off", "aus"), ("false", "aus"),
                                       ("an", "an"), ("aus", "aus")])
def test_kanon_an_aus_ha_und_mqtt(feld, roh, kanon):
    assert zk.normalisiere(feld, roh) == kanon
    assert zk.normalisiere(feld, roh, codes=True) == kanon
    assert zk.label(feld, kanon)


@pytest.mark.parametrize("feld", OPTION_A)
def test_ziffern_nur_ueber_mqtt(feld):
    """Sprengsatz S8 («1» in der HA-Tabelle): eine Ziffer aus einem HA-Sensor ist ein Rohcode, kein «an»."""
    assert zk.normalisiere(feld, "1") is None and zk.normalisiere(feld, "0") is None
    assert not zk.ist_bekannter_wert(feld, "1")
    assert zk.normalisiere(feld, "1", codes=True) == "an"
    assert zk.normalisiere(feld, "0.0", codes=True) == "aus"
    assert zk.ist_bekannter_wert(feld, "1", codes=True)
    tab = zk.werte_je_kanon(feld)
    assert [g["kanon"] for g in tab] == ["an", "aus"]
    assert all(not w.isdigit() for g in tab for w in g["werte"])
    assert any("1" in g["werte"] for g in zk.werte_je_kanon(feld, codes=True))


# ── 2 · Option A: Leser ──────────────────────────────────────────────────────

class _FakeHa:
    def __init__(self, zustaende: dict, verfuegbar: bool = True):
        self._z = zustaende
        self.is_available = verfuegbar

    async def get_zustand_states_batch(self, entity_ids):
        return {e: self._z.get(e) for e in entity_ids}


@pytest.fixture(autouse=True)
def _takt():
    bml.cache_leeren()
    yield
    bml.cache_leeren()


def _stelle_ha(monkeypatch, zustaende: dict, verfuegbar: bool = True) -> None:
    fake = _FakeHa(zustaende, verfuegbar)
    monkeypatch.setattr("backend.services.ha_state_service.get_ha_state_service", lambda: fake)


def _stelle_inbound(monkeypatch):
    cache = mis.MqttInboundCache()
    monkeypatch.setattr(mis, "_mqtt_inbound_service", SimpleNamespace(cache=cache))
    return cache


async def _anlage(db, *, wb_live=None, quellen=None):
    anlage = Anlage(anlagenname="K2b", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="evcc Carport",
                     anschaffungsdatum=date(2025, 1, 1))
    db.add(wb)
    await db.flush()
    mapping: dict = {"investitionen": {str(wb.id): {"live": wb_live}} if wb_live is not None else {}}
    if quellen is not None:
        mapping["quellen"] = quellen(wb.id)
    anlage.sensor_mapping = mapping
    await db.commit()
    return anlage, wb


_EVCC_HA = {"evcc_verbunden": "binary_sensor.evcc_carport_connected",
            "evcc_laedt": "binary_sensor.evcc_carport_charging",
            "evcc_freigegeben": "binary_sensor.evcc_carport_enabled"}


def _ha_states(verbunden, laedt, frei):
    return {"binary_sensor.evcc_carport_connected": (verbunden, None) if verbunden else None,
            "binary_sensor.evcc_carport_charging": (laedt, None) if laedt else None,
            "binary_sensor.evcc_carport_enabled": (frei, None) if frei else None}


@pytest.mark.parametrize("verbunden,laedt,frei,erwartet", [
    ("on", "on", "on", "laedt"),            # Abnahme: connected on + charging on ⇒ «Lädt»
    ("on", "off", "off", "wartet"),         # Abnahme: enabled off ⇒ «Wartet»
    ("on", "off", "on", "verbunden"),
    ("off", "off", "on", "kein_fahrzeug"),
    ("off", "on", "on", "kein_fahrzeug"),   # nicht verbunden schlägt ein widersprüchliches «lädt»
    ("on", "on", "off", "laedt"),           # lädt vor freigegeben (Lese-Reihenfolge K2-7)
])
async def test_option_a_ha_ergibt_den_ladezustand(db, monkeypatch, verbunden, laedt, frei, erwartet):
    anlage, wb = await _anlage(db, wb_live=dict(_EVCC_HA))
    _stelle_ha(monkeypatch, _ha_states(verbunden, laedt, frei))
    z = await bml.lade_zustaende_live(db, anlage)
    assert z[(wb.id, "ladezustand")] == erwartet


async def test_gemessener_ladezustand_gewinnt(db, monkeypatch):
    """Sprengsatz S7: Option A überschreibt nie einen gemessenen Ladezustand."""
    anlage, wb = await _anlage(db, wb_live=dict(_EVCC_HA, ladezustand="sensor.wallbox_status_ladevorgang"))
    _stelle_ha(monkeypatch, {**_ha_states("on", "on", "on"),
                             "sensor.wallbox_status_ladevorgang": ("sleep_mode", None)})
    z = await bml.lade_zustaende_live(db, anlage)
    assert z[(wb.id, "ladezustand")] == "verbunden"
    assert z[(wb.id, "evcc_laedt")] == "an", "die Rollen-Werte bleiben im Ergebnis"


async def test_ladezustand_unknown_laesst_option_a_zu(db, monkeypatch):
    """Ein zugeordneter, aber stummer Ladezustand (``unknown``) ist kein gemessener — Option A springt ein."""
    anlage, wb = await _anlage(db, wb_live=dict(_EVCC_HA, ladezustand="sensor.wb"))
    _stelle_ha(monkeypatch, {**_ha_states("on", "off", "off"), "sensor.wb": ("unknown", None)})
    assert (await bml.lade_zustaende_live(db, anlage))[(wb.id, "ladezustand")] == "wartet"


async def test_ohne_laedt_und_freigegeben_nur_verbunden_oder_kein_fahrzeug(db, monkeypatch):
    anlage, wb = await _anlage(db, wb_live={"evcc_verbunden": "binary_sensor.evcc_carport_connected"},
                               quellen=lambda w: {f"inv_live_{w}_{f}": {"quelle": "keine"}
                                                  for f in ("evcc_laedt", "evcc_freigegeben", "ladezustand")})
    _stelle_ha(monkeypatch, _ha_states("on", None, None))
    assert (await bml.lade_zustaende_live(db, anlage))[(wb.id, "ladezustand")] == "verbunden"
    bml.cache_leeren()
    _stelle_ha(monkeypatch, _ha_states("off", None, None))
    assert (await bml.lade_zustaende_live(db, anlage))[(wb.id, "ladezustand")] == "kein_fahrzeug"


async def test_ohne_verbunden_kein_ladezustand(db, monkeypatch):
    """Nie geraten: «lädt» allein (ohne «verbunden») ergibt keinen Chip."""
    anlage, wb = await _anlage(db, wb_live={"evcc_laedt": "binary_sensor.evcc_carport_charging"},
                               quellen=lambda w: {f"inv_live_{w}_{f}": {"quelle": "keine"}
                                                  for f in ("evcc_verbunden", "evcc_freigegeben", "ladezustand")})
    _stelle_ha(monkeypatch, _ha_states(None, "on", None))
    z = await bml.lade_zustaende_live(db, anlage)
    assert (wb.id, "ladezustand") not in z and z[(wb.id, "evcc_laedt")] == "an"


async def test_ha_ziffer_ergibt_keinen_zustand_und_eine_info(db, monkeypatch):
    """Abnahme: HA ``1`` ⇒ kein Zustand + Checker-INFO (G5/W7)."""
    from backend.services.daten_checker import DatenChecker

    anlage, wb = await _anlage(db, wb_live=dict(_EVCC_HA),
                               quellen=lambda w: {f"inv_live_{w}_ladezustand": {"quelle": "keine"}})
    _stelle_ha(monkeypatch, _ha_states("1", "1", "1"))
    z = await bml.lade_zustaende_live(db, anlage)
    assert not any(k[0] == wb.id for k in z), z
    meldungen = await DatenChecker(db)._check_emob_zustand_wert(anlage)
    assert sorted(m.kategorie for m in meldungen) == ["emob_zustand_wert"] * 3
    assert all(m.schwere == "info" and m.investition_id == wb.id and "„1“" in m.meldung for m in meldungen)


async def test_option_a_ueber_mqtt_true_false_und_ziffern(db, monkeypatch):
    """Abnahme: MQTT ``1`` ⇒ an; evcc schreibt Bools als ``true``/``false``."""
    anlage, wb = await _anlage(db)
    cache = _stelle_inbound(monkeypatch)
    basis = f"eedc/{anlage.id}_K2b/live/inv/{wb.id}_evcc"
    cache.on_message(f"{basis}/evcc_verbunden", "1")
    cache.on_message(f"{basis}/evcc_laedt", "false")
    cache.on_message(f"{basis}/evcc_freigegeben", "false")
    _stelle_ha(monkeypatch, {}, verfuegbar=False)
    z = await bml.lade_zustaende_live(db, anlage)
    assert z[(wb.id, "evcc_verbunden")] == "an" and z[(wb.id, "ladezustand")] == "wartet"
    # Lab-Fall: `unknown` auf dem Ladezustand-Topic (Cache ohne TTL) ⇒ kein gemessener ⇒ Option A
    cache.on_message(f"{basis}/ladezustand", "unknown")
    cache.on_message(f"{basis}/evcc_laedt", "true")
    bml.cache_leeren()
    assert (await bml.lade_zustaende_live(db, anlage))[(wb.id, "ladezustand")] == "laedt"
    cache.on_message(f"{basis}/ladezustand", "fertig")
    bml.cache_leeren()
    assert (await bml.lade_zustaende_live(db, anlage))[(wb.id, "ladezustand")] == "fertig"


def test_kombiniere_option_a_als_reine_funktion():
    erg = bml._kombiniere_option_a({(1, "evcc_verbunden"): "an", (1, "evcc_laedt"): "an",
                                    (2, "evcc_verbunden"): "an", (2, "ladezustand"): "fehler",
                                    (3, "evcc_freigegeben"): "aus", (4, "evcc_verbunden"): "aus"})
    assert erg[(1, "ladezustand")] == "laedt"
    assert erg[(2, "ladezustand")] == "fehler"
    assert (3, "ladezustand") not in erg
    assert erg[(4, "ladezustand")] == "kein_fahrzeug"


# ── 3 · Gateway-Weiche (K2-8, G4) ────────────────────────────────────────────

def test_transform_text_ohne_faktor_und_offset():
    t = gws.transform_payload
    assert t(" pv ", "plain", None, None, 2.0, 5.0, als_text=True) == "pv"
    assert t("", "plain", None, None, 1.0, 0.0, als_text=True) == ""
    assert t('{"lp": {"mode": "now"}}', "json", "lp.mode", None, 1.0, 0.0, als_text=True) == "now"
    assert t('{"connected": true}', "json", "connected", None, 1.0, 0.0, als_text=True) == "True"
    assert t('["a", "b"]', "json_array", None, 1, 1.0, 0.0, als_text=True) == "b"
    assert t('{"x": 1}', "json", None, None, 1.0, 0.0, als_text=True) is None
    assert t("kaputt{", "json", "x", None, 1.0, 0.0, als_text=True) is None


def test_transform_zahl_bitgleich_und_positional():
    t = gws.transform_payload
    assert t("42", "plain", None, None, 1.0, 0.0) == 42.0
    assert t("42", "plain", None, None, 1.0, 0.0, True) == -42.0
    assert t("pv", "plain", None, None, 1.0, 0.0) is None
    assert t('{"a": {"b": "12.5"}}', "json", "a.b", None, 2.0, 1.0) == 26.0
    assert t('{"a": [1, {"b": 3}]}', "json", "a.1.b", None, 1.0, 0.0) == 3.0
    assert t("[1, 2.5]", "json_array", None, 1, 2.0, 0.0) == 5.0
    assert t("[1]", "json_array", None, None, 1.0, 0.0) is None
    with pytest.raises(TypeError):
        t("pv", "plain", None, None, 1.0, 0.0, False, True)  # ``als_text`` nur als Schlüsselwort


@pytest.mark.parametrize("ziel,text", [
    ("live/inv/4_SMA/lademodus", True),
    ("live/inv/{inv_id}/evcc_verbunden", True),
    ("live/inv/4/fahrzeug_am_ladepunkt", True),
    ("live/inv/4/leistung_w", False),
    ("live/inv/4/sitzung_kwh", False),
    ("live/inv/7/betriebsmodus", False),      # D3: der Modus bleibt beim Zahlen-Weg
    ("live/inv/7/betriebsmodus-3", False),
])
def test_als_text_folgt_dem_zielfeld(ziel, text):
    assert gws._als_text(ziel) is text


class _Client:
    def __init__(self):
        self.gesendet: list[tuple[str, str]] = []

    async def publish(self, topic, payload):
        self.gesendet.append((topic, payload))


def _gateway(ziel_key: str, **kw) -> gws.MqttGatewayService:
    svc = gws.MqttGatewayService("localhost", 1883)
    svc.load_mappings([gws.GatewayMapping(id=1, anlage_id=3, quell_topic="evcc/loadpoints/1/x", ziel_key=ziel_key,
                                          **kw)])
    return svc


def _sende(svc, payload: str) -> _Client:
    client = _Client()
    msg = SimpleNamespace(topic="evcc/loadpoints/1/x", payload=payload.encode())
    asyncio.run(svc._handle_message(client, msg))
    return client


def test_gateway_reicht_text_an_ein_zustandsfeld():
    """Abnahme: Gateway ``lademodus`` ← ``pv`` ⇒ Republish ``pv`` (Faktor unangewendet)."""
    svc = _gateway("live/inv/4/lademodus", faktor=0.001)
    assert _sende(svc, "pv").gesendet == [("eedc/3/live/inv/4/lademodus", "pv")]
    assert svc.get_status()["weitergeleitet"] == 1 and svc.get_status()["transform_fehler"] == 0


def test_gateway_text_auf_zahlenfeld_ist_fehler():
    """Sprengsatz S9: ein Wort auf ``leistung_w`` ⇒ ``transform_fehler``, kein Republish."""
    svc = _gateway("live/inv/4/leistung_w")
    assert _sende(svc, "pv").gesendet == []
    assert svc.get_status()["transform_fehler"] == 1 and svc.get_status()["weitergeleitet"] == 0
    assert _sende(svc, "1234.5678").gesendet == [("eedc/3/live/inv/4/leistung_w", "1234.57")], "Zahl wie bisher"


def test_gateway_modus_bleibt_beim_zahlenweg():
    """D3 / HALT-Regel «Weiche berührt den Modus-Pfad»: am Betriebsmodus ändert sich nichts."""
    svc = _gateway("live/inv/7/betriebsmodus")
    assert _sende(svc, "2").gesendet == [("eedc/3/live/inv/7/betriebsmodus", "2.0")]
    assert _sende(svc, "heizen").gesendet == []


def test_gateway_leerer_fahrzeugname_erreicht_den_cache_als_leer():
    """Gateway ⇒ Inbound: der leere ``vehicleName`` (evcc ``nil``) wird als ``""`` abgelegt (Gast, K2a G2)."""
    svc = _gateway("live/inv/4/fahrzeug_am_ladepunkt")
    gesendet = _sende(svc, "").gesendet
    assert gesendet == [("eedc/3/live/inv/4/fahrzeug_am_ladepunkt", "")]
    cache = mis.MqttInboundCache()
    cache.on_message(*gesendet[0])
    assert cache.get_all_live_inv(3)["4"]["fahrzeug_am_ladepunkt"] == ""


def test_route_vorschau_als_text():
    from backend.api.routes.mqtt_gateway import TransformTestRequest, test_transform

    text = asyncio.run(test_transform(TransformTestRequest(payload=" now ", faktor=0.5, als_text=True)))
    assert text == {"erfolg": True, "wert_text": "now", "ziel_payload": "now"}
    zahl = asyncio.run(test_transform(TransformTestRequest(payload="1234.5678", faktor=0.001)))
    assert zahl == {"erfolg": True, "wert": 1.2346, "ziel_payload": "1.23"}
    assert asyncio.run(test_transform(TransformTestRequest(payload="pv")))["erfolg"] is False


# ── 4 · Preset «evcc Ladepunkt» (K2-9) ───────────────────────────────────────

def _evcc(variablen=None, inv=4):
    from backend.services.mqtt_presets import generate_mappings

    return generate_mappings("evcc_ladepunkt", 1, variablen or {}, inv)


def test_preset_zeilen_und_ziele():
    zeilen = {m["quell_topic"].rsplit("/", 1)[-1]: m for m in _evcc()}
    assert list(zeilen) == ["chargePower", "sessionEnergy", "chargeDuration", "chargeRemainingDuration",
                            "phasesActive", "chargeTotalImport", "mode", "connected", "charging", "enabled",
                            "vehicleName"]
    assert len(zeilen) == 11
    ziel = {k: m["ziel_key"].rsplit("/", 1)[-1] for k, m in zeilen.items()}
    assert ziel == {"chargePower": "leistung_w", "sessionEnergy": "sitzung_kwh", "chargeDuration": "sitzung_dauer_s",
                    "chargeRemainingDuration": "restzeit_min", "phasesActive": "phasen_aktiv",
                    "chargeTotalImport": "ladung_kwh", "mode": "lademodus",
                    "connected": "evcc_verbunden", "charging": "evcc_laedt", "enabled": "evcc_freigegeben",
                    "vehicleName": "fahrzeug_am_ladepunkt"}
    assert all(m["preset_id"] == "evcc_ladepunkt" for m in zeilen.values())
    # Der Zählerstand gehört unter `energy/` (eedc bildet die Differenzen), alles andere ist live.
    assert zeilen["chargeTotalImport"]["ziel_key"] == "energy/inv/4/ladung_kwh"
    assert all(m["ziel_key"].startswith("live/inv/4/") for k, m in zeilen.items() if k != "chargeTotalImport")
    # Nicht im Preset: Auto-Werte und undokumentierte Topics (P7).
    assert not {"vehicleSoc", "vehicleRange", "chargeCurrent", "effectiveLimitSoc"} & set(zeilen)


def test_preset_faktoren_nur_mit_belegter_einheit():
    zeilen = {m["quell_topic"].rsplit("/", 1)[-1]: m for m in _evcc()}
    assert zeilen["sessionEnergy"]["faktor"] == pytest.approx(0.001)          # Wh ⇒ kWh
    assert zeilen["chargeDuration"]["faktor"] == 1.0                           # s (time.Duration ⇒ ganze Sekunden)
    assert zeilen["chargeRemainingDuration"]["faktor"] == pytest.approx(1 / 60)  # s ⇒ min
    assert zeilen["chargePower"]["faktor"] == 1.0 and zeilen["phasesActive"]["faktor"] == 1.0
    assert zeilen["chargeTotalImport"]["faktor"] == 1.0                        # kWh an der Quelle (api.MeterEnergy)
    for m in zeilen.values():
        assert m["offset"] == 0.0 and m["payload_typ"] == "plain" and m["invertieren"] is False
        if gws._als_text(m["ziel_key"]):
            assert m["faktor"] == 1.0, "Zustandsfelder ohne Faktor"


def test_preset_sitzung_ein_echter_payload_ueber_das_gateway():
    """Sprengsatz S10 (Faktor ``1e-9`` auf Sekunden): 2 h 10 min Sitzung bleiben 7 800 s, Restzeit 42 min."""
    zeilen = {m["quell_topic"].rsplit("/", 1)[-1]: m for m in _evcc()}

    def durch(key, payload):
        m = zeilen[key]
        return gws.transform_payload(payload, m["payload_typ"], m["json_pfad"], m["array_index"], m["faktor"],
                                     m["offset"], als_text=gws._als_text(m["ziel_key"]))

    assert durch("chargeDuration", "7800") == 7800.0
    assert durch("chargeRemainingDuration", "2520") == pytest.approx(42.0)
    assert durch("sessionEnergy", "9876.543") == pytest.approx(9.876543)
    assert durch("chargePower", "11040.5") == 11040.5
    assert durch("connected", "true") == "true" and durch("mode", "smart") == "smart"
    assert durch("vehicleName", "") == ""


def test_preset_zaehlerstand_als_zahl_auf_das_energy_topic():
    """Entscheid Master H1: `chargeTotalImport` ist kWh — die Zahl geht ohne Faktor auf `energy/…/ladung_kwh`."""
    m = {x["quell_topic"].rsplit("/", 1)[-1]: x for x in _evcc()}["chargeTotalImport"]
    svc = _gateway(m["ziel_key"], faktor=m["faktor"], offset=m["offset"])
    gesendet = _sende(svc, "1286.62").gesendet
    assert gesendet == [("eedc/3/energy/inv/4/ladung_kwh", "1286.62")]
    cache = mis.MqttInboundCache()
    cache.on_message(*gesendet[0])
    assert cache._energy[3]["inv/4/ladung_kwh"][0] == 1286.62


def test_preset_vorgaben_und_eigene_variablen():
    topics = [m["quell_topic"] for m in _evcc()]
    assert topics[0] == "evcc/loadpoints/1/chargePower"
    eigene = [m["quell_topic"] for m in _evcc({"prefix": "haus/evcc", "loadpoint": "2"})]
    assert eigene[0] == "haus/evcc/loadpoints/2/chargePower"
    assert [m["quell_topic"] for m in _evcc({"prefix": "  ", "loadpoint": ""})] == topics
    with pytest.raises(ValueError):
        _evcc(inv=None)


def test_preset_liste_traegt_die_vorgaben():
    from backend.api.routes.mqtt_presets import get_presets

    p = {x.id: x for x in asyncio.run(get_presets())}["evcc_ladepunkt"]
    assert p.gruppe == "Wallbox" and p.erfordert_investition
    assert {v.key: v.vorgabe for v in p.variablen} == {"prefix": "evcc", "loadpoint": "1"}


def test_kosmetik_rc13_anleitung_ohne_investitions_auswahl():
    """Kosmetik rc13 (K-2): seit K4 öffnet der Preset-Dialog am Gerät — keine Anleitung sagt mehr, man solle die
    Investition auswählen. Die API sagt es ihr eigenes Mal (`generate_mappings` ⇒ ValueError ohne `investition_id`)."""
    from backend.services.mqtt_presets import list_presets

    for p in list_presets():
        assert "auswählen" not in p.anleitung, p.id
    with pytest.raises(ValueError, match="Investition"):
        _evcc(inv=None)


def test_kosmetik_rc13_lademodus_woerter_wie_der_kanon():
    """Kosmetik rc13 (K-2, Halt H1 Entscheid Master): die evcc-Zeile nennt die Wörter, die evcc sendet — heute
    off · smart · now (`api.ChargeMode`), ältere Versionen pv · minpv —, und jedes davon kennt der Kanon."""
    import re

    from backend.services.mqtt_presets import get_preset

    zeile = next(m for m in get_preset("evcc_ladepunkt").mappings if m.ziel_key.endswith("/lademodus"))
    woerter = re.findall(r"\b(off|smart|now|pv|minpv)\b", zeile.beschreibung)
    assert woerter == ["off", "smart", "now", "pv", "minpv"]
    assert all(zk.ist_bekannter_wert(zk.LADEMODUS, w) for w in woerter)


# ── 5 · Datenquellen, Wissensbasis ───────────────────────────────────────────

def test_datenquellen_werte_tabelle_und_klartext_option_a():
    from backend.api.routes import datenquellen as dq

    e = {"feld": "evcc_freigegeben", "zustand": True}
    assert [g["kanon"] for g in dq._zulaessige_werte(e, "ha_app")] == ["an", "aus"]
    assert not any("0" in g["werte"] for g in dq._zulaessige_werte(e, "ha_app"))
    assert any("0" in g["werte"] for g in dq._zulaessige_werte(e, "mqtt_gateway"))
    assert dq._wert_klartext(e, "off", "ha_app") == "Nicht freigegeben"
    assert dq._wert_klartext(e, "0", "ha_app") is None
    assert dq._wert_klartext(e, "0", "mqtt_gateway") == "Nicht freigegeben"
    sensor = {"entity_id": "binary_sensor.evcc_carport_enabled", "attributes": {}}
    assert dq._ha_sensor_relevant(sensor, True, zustand=True, domaenen=dq._ha_domaenen("evcc_freigegeben", "wallbox"))


def test_wissensbasis_schlaegt_die_binaer_sensoren_vor():
    from backend.core.ha_integrations_wissen import analysiere_vorschlaege

    ids = ["binary_sensor.evcc_carport_connected", "binary_sensor.evcc_carport_charging",
           "binary_sensor.evcc_carport_enabled", "select.evcc_carport_mode"]
    vor = lambda feld: [v["entity_id"] for v in analysiere_vorschlaege(ids, feld, "wallbox")["vorschlaege"]]  # noqa: E731
    assert vor("evcc_verbunden") == ["binary_sensor.evcc_carport_connected"]
    assert vor("evcc_laedt") == ["binary_sensor.evcc_carport_charging"]
    assert vor("evcc_freigegeben") == ["binary_sensor.evcc_carport_enabled"]
