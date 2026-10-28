"""P-433-2b K1 «Drei Karten E-Mobilität im Hub-Überblick» — Backend-Proben (Bauplan E1–E3, E5; Blatt Fassung 3).

Was hier gesichert wird, und warum jede Gruppe existiert:

1. **Registry** — die elf Felder (Wallbox acht, E-Auto fünf, zwei Namen geteilt) stehen an beiden Typen, alle
   `erweitert`, im Abschnitt «Zustand & Sitzung», `nur_live`; vier sind Zustände (`ist_zustand_feld`).
2. **Kanon** (`core/zustands_kanon.py`) — jeder belegte Rohwert ergibt seinen Kanon, ein fremder ``None`` (kein Raten,
   K-2), die go-e-Codes nur über MQTT, «bekannt ohne Aussage» ist bekannt, aber ohne Zustand.
3. **Kanal-Katalog** — K-1 «nichts gespeichert»: kein Kanal, kein Mittel im MQTT-Snapshot.
4. **Leser** (`betriebsmodus_live.lade_zustaende_live`) — der Filter ist geöffnet (Wallbox/E-Auto, nicht nur WP), HA
   je Feld, MQTT je Feld, «keine» schließt MQTT aus, der Modus-Pfad bleibt unberührt.
5. **Builder** — Zustand und Sitzung am Wallbox-Knoten nur mit Wert; **ohne Zustandsfeld kein Zustand, auch nicht bei
   Leistung** (Sprengsatz «Zustand aus kW»); Fahrzeugwerte; Autos ohne Wallbox; Dienstwagen aus dem Stammdatum.
6. **Daten-Checker** — fremder Wert ⇒ INFO (E12-Muster), bekannter/kein Wert ⇒ still.
7. **Datenquellen** — Werte-Tabelle und Klartext je Feld, HA-Picker öffnet `select`/`device_tracker`.
8. **Demo** und **Wissensbasis**.

Schwesterdateien: test_398_betriebsmodus_live.py (Modus-Leser, Takt), test_p433_0_betriebsmodus_werte.py (E12-Muster des
Checkers), test_341_live_merkmale.py (Antwort-Form der Live-Route), test_kanal_feld_deckung.py (Kanal-Katalog).
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from backend.core import zustands_kanon as zk
from backend.core.field_definitions import get_live_felder_fuer_investition, ist_zustand_feld
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services import betriebsmodus_live as bml
from backend.services import mqtt_inbound_service as mis

WALLBOX_FELDER = ("ladezustand", "lademodus", "sitzung_kwh", "sitzung_dauer_s", "ladestrom_a", "phasen_aktiv",
                  "ziel_ladestand_prozent", "restzeit_min")
EAUTO_FELDER = ("ladezustand_fahrzeug", "reichweite_km", "ziel_ladestand_prozent", "restzeit_min", "zu_hause")
#: P-433-2b K3 (Bauplan K3-1): die drei Felder, die seitdem mitgeschrieben werden (die Seite gewechselt haben).
MITSCHRIFT_K3 = {("wallbox", "ladezustand"), ("e-auto", "ladezustand_fahrzeug"), ("e-auto", "zu_hause")}


# ── 1 · Registry ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("typ,felder", [("wallbox", WALLBOX_FELDER), ("e-auto", EAUTO_FELDER)])
def test_registry_felder_an_beiden_typen(typ, felder):
    live = {f["key"]: f for f in get_live_felder_fuer_investition(typ, {})}
    for feld in felder:
        assert feld in live, feld
        assert live[feld].get("erweitert") is True, feld
        assert live[feld].get("abschnitt") == "zustand", feld
        # P-433-2b K3: Ladezustand, Fahrzeug-Ladezustand und Standort werden mitgeschrieben (`mitschrift` statt
        # `nur_live`, Bauplan K3-1) — genau eines von beiden, die übrigen bleiben `nur_live`.
        if (typ, feld) in MITSCHRIFT_K3:
            assert live[feld].get("mitschrift") is True and "nur_live" not in live[feld], feld
        else:
            assert live[feld].get("nur_live") is True and "mitschrift" not in live[feld], feld
    # Der Bestand bleibt vorn und unverändert erste Reihe.
    assert "leistung_w" in live and not live["leistung_w"].get("erweitert")


def test_vier_zustandsfelder_und_keine_zahl():
    for typ, feld in (("wallbox", "ladezustand"), ("wallbox", "lademodus"),
                      ("e-auto", "ladezustand_fahrzeug"), ("e-auto", "zu_hause")):
        assert ist_zustand_feld(feld, typ), (typ, feld)
        assert ist_zustand_feld(feld), feld
    for feld in ("sitzung_kwh", "ladestrom_a", "reichweite_km", "ziel_ladestand_prozent"):
        assert not ist_zustand_feld(feld), feld
    assert ist_zustand_feld("betriebsmodus", "waermepumpe")


# ── 2 · Kanon ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("feld,roh,kanon", [
    # SMA EV Charger (smaev)
    ("ladezustand", "not_connected", "kein_fahrzeug"), ("ladezustand", "sleep_mode", "verbunden"),
    ("ladezustand", "active_mode", "laedt"), ("ladezustand", "station_locked", "gesperrt"),
    ("ladezustand", "station_fault", "fehler"),
    # Kanon-Wörter (Weg B), Groß/Klein und Leerzeichen egal
    ("ladezustand", " Wartet ", "wartet"), ("ladezustand", "fertig", "fertig"),
    # evcc-Lademodus und SMA
    ("lademodus", "off", "aus"), ("lademodus", "pv", "pv"), ("lademodus", "minpv", "smart"),
    ("lademodus", "now", "schnell"), ("lademodus", "smart", "smart"), ("lademodus", "smart_charging", "pv"),
    ("lademodus", "boost_charging", "schnell"), ("lademodus", "charge_stop", "aus"),
    # Smart #1 (smarthashtag) — Ladeanschluss und Ladezustand
    ("ladezustand_fahrzeug", "not_connected", "nicht_verbunden"),
    ("ladezustand_fahrzeug", "plugged_not_charging", "verbunden"),
    ("ladezustand_fahrzeug", "dc_connected", "laedt_dc"), ("ladezustand_fahrzeug", "charging", "laedt"),
    ("ladezustand_fahrzeug", "dc_charging", "laedt_dc"), ("ladezustand_fahrzeug", "complete", "fertig"),
    ("ladezustand_fahrzeug", "target_reached", "fertig"), ("ladezustand_fahrzeug", "error", "fehler"),
    ("ladezustand_fahrzeug", "plugged_in", "verbunden"),
    # HA-Zone
    ("zu_hause", "home", "zu_hause"), ("zu_hause", "not_home", "unterwegs"),
])
def test_belegte_rohwerte_ergeben_ihren_kanon(feld, roh, kanon):
    assert zk.normalisiere(feld, roh) == kanon
    assert zk.ist_bekannter_wert(feld, roh)
    assert kanon in zk.KANON[feld]


@pytest.mark.parametrize("feld,roh", [
    ("ladezustand", "charging_paused"), ("lademodus", "turbo"), ("zu_hause", "Arbeit"),
    ("ladezustand_fahrzeug", "plugged"),
])
def test_fremder_wert_wird_nicht_geraten(feld, roh):
    assert zk.normalisiere(feld, roh) is None
    assert not zk.ist_bekannter_wert(feld, roh)


def test_kein_zustand_ist_kein_wert_und_kein_fremder():
    for roh in (None, "", "unknown", "unavailable", "none"):
        assert zk.normalisiere("ladezustand", roh) is None
        assert zk.ist_kein_zustand(roh)
        assert not zk.ist_bekannter_wert("ladezustand", roh)


def test_bekannt_ohne_aussage():
    """Smart `not_charging` — angesteckt oder nicht? Bekannt (kein Checker-Hinweis), aber kein Zustand."""
    assert zk.normalisiere("ladezustand_fahrzeug", "not_charging") is None
    assert zk.ist_bekannter_wert("ladezustand_fahrzeug", "not_charging")


def test_go_e_codes_nur_ueber_mqtt():
    assert zk.normalisiere("ladezustand", "2", codes=True) == "laedt"
    assert zk.normalisiere("ladezustand", "3.0", codes=True) == "wartet"
    assert zk.normalisiere("ladezustand", "2") is None, "eine Ziffer aus HA ist ein Hersteller-Rohcode"
    assert zk.normalisiere("lademodus", "4", codes=True) == "eco"
    assert not zk.ist_bekannter_wert("ladezustand", "2")
    assert zk.ist_bekannter_wert("ladezustand", "2", codes=True)


def test_werte_tabelle_kanon_zuerst_und_jedes_label():
    for feld, kanon in zk.KANON.items():
        gruppen = zk.werte_je_kanon(feld)
        assert [g["kanon"] for g in gruppen] == list(kanon)
        for g in gruppen:
            assert g["werte"][0] == g["kanon"], "das Kanon-Wort ist die Schreibweise für Weg B"
            assert g["label"] == zk.LABEL[feld][g["kanon"]]
    assert "2" not in zk.werte_klartext("ladezustand")
    assert "2" in zk.werte_klartext("ladezustand", codes=True)


# ── 3 · Kanal-Katalog: nichts gespeichert (K-1) ──────────────────────────────

def test_kein_kanal_und_kein_snapshot_mittel():
    from backend.services.kanal import katalog as kat

    nur_live = {(z.typ, z.feld) for z in kat.zuweisungen() if z.ausnahme == kat.AUSNAHME_NUR_LIVE}
    # P-433-2b K2a (Bauplan K2 E1): das Textfeld «Fahrzeug am Ladepunkt» — `nur_live` greift vor `zustand`
    # (`katalog.py`), also kein Kanal und keine Mitschrift wie beim Betriebsmodus.
    # P-433-2b K2b (Option A): die drei evcc-Rollen-Felder ebenso.
    option_a = {"evcc_verbunden", "evcc_laedt", "evcc_freigegeben"}
    # P-433-2b K3: die drei Mitschrift-Felder haben seitdem einen `zustand:`-Kanal statt der Ausnahme.
    assert nur_live == (({("wallbox", f) for f in WALLBOX_FELDER} | {("e-auto", f) for f in EAUTO_FELDER}
                         | {("wallbox", "fahrzeug_am_ladepunkt")} | {("wallbox", f) for f in option_a})
                        - MITSCHRIFT_K3)
    mitschrift = {(z.typ, z.feld) for z in kat.zuweisungen() if z.schluessel.startswith("zustand:")}
    assert mitschrift == MITSCHRIFT_K3
    assert not set(kat.mittelwert_live_keys("wallbox", {})) & (
        set(WALLBOX_FELDER) | {"fahrzeug_am_ladepunkt"} | option_a)
    assert not set(kat.mittelwert_live_keys("e-auto", {})) & set(EAUTO_FELDER)
    assert "soc" in kat.mittelwert_live_keys("e-auto", {}), "der Bestand bleibt"
    assert not kat.ist_mean_kanal("inv:7:ziel_ladestand_prozent", "wallbox")


# ── 4 · Leser ────────────────────────────────────────────────────────────────

class _FakeHa:
    def __init__(self, zustaende: dict, verfuegbar: bool = True):
        self._z = zustaende
        self.is_available = verfuegbar
        self.gefragt: list = []

    async def get_zustand_states_batch(self, entity_ids):
        self.gefragt.append(sorted(entity_ids))
        return {e: self._z.get(e) for e in entity_ids}


@pytest.fixture(autouse=True)
def _takt():
    bml.cache_leeren()
    yield
    bml.cache_leeren()


def _stelle_ha(monkeypatch, zustaende: dict, verfuegbar: bool = True) -> _FakeHa:
    fake = _FakeHa(zustaende, verfuegbar)
    monkeypatch.setattr("backend.services.ha_state_service.get_ha_state_service", lambda: fake)
    return fake


def _stelle_inbound(monkeypatch):
    cache = mis.MqttInboundCache()
    monkeypatch.setattr(mis, "_mqtt_inbound_service", SimpleNamespace(cache=cache))
    return cache


async def _anlage(db, *, wb_live=None, ea_live=None, quellen=None, ea_param=None):
    anlage = Anlage(anlagenname="K1", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="SMA eCharger 22",
                     anschaffungsdatum=date(2025, 1, 1))
    ea = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Smart #1",
                     anschaffungsdatum=date(2025, 1, 1), parameter=ea_param or {})
    db.add_all([wb, ea])
    await db.flush()
    invs = {}
    if wb_live is not None:
        invs[str(wb.id)] = {"live": wb_live}
    if ea_live is not None:
        invs[str(ea.id)] = {"live": ea_live}
    mapping = {"investitionen": invs}
    if quellen is not None:
        mapping["quellen"] = quellen(wb.id, ea.id)
    anlage.sensor_mapping = mapping
    await db.commit()
    return anlage, wb, ea


async def test_ha_zustaende_je_feld(db, monkeypatch):
    anlage, wb, ea = await _anlage(
        db,
        wb_live={"ladezustand": "sensor.wallbox_status_ladevorgang", "lademodus": "select.evcc_carport_mode"},
        ea_live={"ladezustand_fahrzeug": "sensor.smart_ladesanschluss", "zu_hause": "device_tracker.smart"},
    )
    fake = _stelle_ha(monkeypatch, {
        "sensor.wallbox_status_ladevorgang": ("active_mode", None),
        "select.evcc_carport_mode": ("pv", None),
        "sensor.smart_ladesanschluss": ("charging", None),
        "device_tracker.smart": ("home", None),
    })
    assert await bml.lade_zustaende_live(db, anlage) == {
        (wb.id, "ladezustand"): "laedt", (wb.id, "lademodus"): "pv",
        (ea.id, "ladezustand_fahrzeug"): "laedt", (ea.id, "zu_hause"): "zu_hause",
    }
    assert len(fake.gefragt) == 1, "ein gebündelter HA-Abruf für alle Felder"


async def test_filter_geoeffnet_wallbox_ohne_waermepumpe(db, monkeypatch):
    """Sprengsatz «Filter :197 nicht geöffnet»: eine Anlage ganz ohne Wärmepumpe bekommt ihren Wallbox-Zustand."""
    anlage, wb, _ea = await _anlage(db, wb_live={"ladezustand": "sensor.wb"})
    _stelle_ha(monkeypatch, {"sensor.wb": ("sleep_mode", None)})
    assert (await bml.lade_zustaende_live(db, anlage))[(wb.id, "ladezustand")] == "verbunden"
    assert await bml.lade_betriebsmodus_live(db, anlage) == {}, "der Modus-Pfad sieht keine Wallbox"


async def test_fremder_und_unknown_fehlen(db, monkeypatch):
    anlage, wb, _ = await _anlage(db, wb_live={"ladezustand": "sensor.a", "lademodus": "sensor.b"})
    _stelle_ha(monkeypatch, {"sensor.a": ("charging_paused", None), "sensor.b": None})
    assert await bml.lade_zustaende_live(db, anlage) == {}


async def test_mqtt_je_feld_mit_codes(db, monkeypatch):
    anlage, wb, ea = await _anlage(db)
    cache = _stelle_inbound(monkeypatch)
    cache.on_message(f"eedc/{anlage.id}_K1/live/inv/{wb.id}_WB/ladezustand", "2")
    cache.on_message(f"eedc/{anlage.id}_K1/live/inv/{wb.id}_WB/lademodus", "pv")
    cache.on_message(f"eedc/{anlage.id}_K1/live/inv/{ea.id}_Smart/zu_hause", "unterwegs")
    cache.on_message(f"eedc/{anlage.id}_K1/live/inv/{ea.id}_Smart/ladezustand_fahrzeug", "Quatsch")
    _stelle_ha(monkeypatch, {}, verfuegbar=False)
    assert await bml.lade_zustaende_live(db, anlage) == {
        (wb.id, "ladezustand"): "laedt", (wb.id, "lademodus"): "pv", (ea.id, "zu_hause"): "unterwegs",
    }
    # Der Zustand liegt als roher String im Cache, nie in den Leistungswerten.
    assert cache.get_all_live_inv(anlage.id)[str(wb.id)]["ladezustand"] == "2"


async def test_quellen_keine_schliesst_mqtt_aus_und_ha_gewinnt(db, monkeypatch):
    anlage, wb, _ = await _anlage(
        db, wb_live={"lademodus": "select.evcc_carport_mode"},
        quellen=lambda w, e: {f"inv_live_{w}_ladezustand": {"quelle": "keine"}},
    )
    cache = _stelle_inbound(monkeypatch)
    cache.on_message(f"eedc/{anlage.id}_K1/live/inv/{wb.id}_WB/ladezustand", "laedt")
    cache.on_message(f"eedc/{anlage.id}_K1/live/inv/{wb.id}_WB/lademodus", "schnell")
    _stelle_ha(monkeypatch, {"select.evcc_carport_mode": ("pv", None)})
    assert await bml.lade_zustaende_live(db, anlage) == {(wb.id, "lademodus"): "pv"}


# ── 5 · Builder ──────────────────────────────────────────────────────────────

def _inv(i, typ, bez, **param):
    return Investition(id=i, typ=typ, bezeichnung=bez, anschaffungsdatum=date(2020, 1, 1), parameter=param or None)


def _baue(werte: dict, invs: list, zustand_map=None):
    from backend.services.live_komponenten_builder import build_komponenten

    anlage = Anlage(anlagenname="B", leistung_kwp=10.0)
    return build_komponenten(
        anlage, {"einspeisung_w": 0.0, "netzbezug_w": 500.0}, werte, {str(i.id): i for i in invs},
        {k: {f: f"sensor.{k}_{f}" for f in v} for k, v in werte.items()}, zustand_map=zustand_map,
    )


def _knoten(erg, key):
    return next(k for k in erg["komponenten"] if k["key"] == key)


def test_wallbox_knoten_mit_zustand_und_sitzung():
    wb, ea = _inv(4, "wallbox", "SMA eCharger 22"), _inv(5, "e-auto", "Smart #1")
    erg = _baue(
        {"4": {"leistung_w": 11000.0, "sitzung_kwh": 9.84, "sitzung_dauer_s": 7800.4, "ladestrom_a": 16.04,
               "phasen_aktiv": 3.0, "ziel_ladestand_prozent": 80.2, "restzeit_min": 79.6},
         "5": {"soc": 62.4, "reichweite_km": 312.3, "ziel_ladestand_prozent": 80.0, "restzeit_min": 80.0}},
        [wb, ea],
        {(4, "ladezustand"): "laedt", (4, "lademodus"): "pv", (5, "ladezustand_fahrzeug"): "laedt",
         (5, "zu_hause"): "zu_hause"},
    )
    k = _knoten(erg, "wallbox_4")
    assert (k["ladezustand"], k["ladezustand_label"], k["lademodus"], k["lademodus_label"]) == \
        ("laedt", "Lädt", "pv", "PV")
    assert k["sitzung"] == {"kwh": 9.84, "dauer_s": 7800.0}
    assert (k["ladestrom_a"], k["phasen_aktiv"], k["ziel_prozent"], k["restzeit_min"]) == (16.0, 3.0, 80.0, 80.0)
    assert k["fahrzeuge_zuordnung"] == "eindeutig"
    assert k["fahrzeuge"] == [{
        "investition_id": 5, "label": "Smart #1", "soc": 62.0, "kw": None, "v2h": False,
        "reichweite_km": 312.0, "ziel_prozent": 80.0, "restzeit_min": 80.0,
        "ladezustand": "laedt", "ladezustand_label": "Lädt", "zu_hause": True,
    }]
    assert "fahrzeuge_ohne_wallbox" not in erg


def test_ohne_zustandsfeld_kein_zustand_auch_bei_leistung():
    """Sprengsatz «Zustand aus kW abgeleitet»: 11 kW ohne Feld ⇒ kein `ladezustand`, kein Chip."""
    for kw in (11000.0, 0.0):
        k = _knoten(_baue({"4": {"leistung_w": kw}}, [_inv(4, "wallbox", "WB")]), "wallbox_4")
        for schluessel in ("ladezustand", "ladezustand_label", "lademodus", "sitzung", "ladestrom_a"):
            assert schluessel not in k, (kw, schluessel)


def test_autos_ohne_wallbox_und_dienstwagen():
    ea = _inv(5, "e-auto", "Firmenwagen", ist_dienstlich=True)
    erg = _baue({"5": {"soc": 45.0, "reichweite_km": 210.0}}, [ea], {(5, "ladezustand_fahrzeug"): "nicht_verbunden",
                                                                      (5, "zu_hause"): "unterwegs"})
    assert erg["fahrzeuge_ohne_wallbox"] == [{
        "investition_id": 5, "label": "Firmenwagen", "soc": 45.0, "kw": None, "v2h": False,
        "reichweite_km": 210.0, "ladezustand": "nicht_verbunden", "ladezustand_label": "Nicht verbunden",
        "zu_hause": False, "dienstwagen": True,
    }]


def test_ohne_autos_kein_schluessel():
    erg = _baue({"4": {"leistung_w": 0.0}}, [_inv(4, "wallbox", "WB")])
    assert "fahrzeuge_ohne_wallbox" not in erg


# ── 6 · Daten-Checker ────────────────────────────────────────────────────────

async def _meldungen(db, anlage):
    from backend.services.daten_checker import DatenChecker

    return await DatenChecker(db)._check_emob_zustand_wert(anlage)


async def test_checker_fremder_wert_meldet_info(db, monkeypatch):
    """Sprengsatz «fremder Zustandswert ohne Checker-INFO»."""
    anlage, wb, _ = await _anlage(db, wb_live={"ladezustand": "sensor.wb_status"})
    _stelle_ha(monkeypatch, {"sensor.wb_status": ("charging_paused", None)})
    erg = await _meldungen(db, anlage)
    assert len(erg) == 1
    m = erg[0]
    assert m.kategorie == "emob_zustand_wert" and m.schwere == "info" and m.investition_id == wb.id
    assert "charging_paused" in m.meldung and "Lädt (laedt" in m.details


async def test_checker_still_bei_bekannt_kein_wert_ohne_ha(db, monkeypatch):
    anlage, _wb, _ = await _anlage(db, wb_live={"ladezustand": "sensor.a", "lademodus": "sensor.b"},
                                   ea_live={"ladezustand_fahrzeug": "sensor.c"})
    _stelle_ha(monkeypatch, {"sensor.a": ("active_mode", None), "sensor.b": None,
                             "sensor.c": ("not_charging", None)})
    assert await _meldungen(db, anlage) == []
    _stelle_ha(monkeypatch, {"sensor.a": ("quatsch", None)}, verfuegbar=False)
    assert await _meldungen(db, anlage) == []


async def test_checker_mqtt_codes_gelten(db, monkeypatch):
    anlage, wb, ea = await _anlage(db)
    cache = _stelle_inbound(monkeypatch)
    cache.on_message(f"eedc/{anlage.id}_K1/live/inv/{wb.id}_WB/ladezustand", "4")
    cache.on_message(f"eedc/{anlage.id}_K1/live/inv/{ea.id}_S/zu_hause", "Arbeit")
    erg = await _meldungen(db, anlage)
    assert [(m.investition_id, "Arbeit" in m.meldung) for m in erg] == [(ea.id, True)]


# ── 7 · Datenquellen ─────────────────────────────────────────────────────────

def test_datenquellen_werte_tabelle_und_klartext():
    from backend.api.routes import datenquellen as dq

    e = {"feld": "ladezustand", "zustand": True}
    tab = dq._zulaessige_werte(e, "ha_app")
    assert [g["kanon"] for g in tab] == list(zk.KANON["ladezustand"])
    assert all("2" not in g["werte"] for g in tab)
    assert any("2" in g["werte"] for g in dq._zulaessige_werte(e, "mqtt_inbound_standard"))
    assert dq._wert_klartext(e, "active_mode", "ha_app") == "Lädt"
    assert dq._wert_klartext(e, "charging_paused", "ha_app") is None, "fremd: kein «Unbestimmt» wie beim Modus"
    assert dq._wert_klartext({"feld": "betriebsmodus", "zustand": True}, "cool", "ha_app") == "Kühlen"
    assert dq._zulaessige_werte({"feld": "sitzung_kwh"}) is None


def test_ha_picker_domains_je_feld():
    from backend.api.routes import datenquellen as dq

    sel = {"entity_id": "select.evcc_carport_mode", "attributes": {}}
    trk = {"entity_id": "device_tracker.smart", "attributes": {}}
    cli = {"entity_id": "climate.wohnzimmer", "attributes": {}}
    lm = dq._ha_domaenen("lademodus", "wallbox")
    assert dq._ha_sensor_relevant(sel, True, zustand=True, domaenen=lm)
    assert dq._ha_sensor_relevant(trk, True, zustand=True, domaenen=dq._ha_domaenen("zu_hause", "e-auto"))
    assert not dq._ha_sensor_relevant(cli, True, zustand=True, domaenen=lm)
    # Der Betriebsmodus bleibt bei climate + sensor (bitgleich).
    assert dq._ha_domaenen("betriebsmodus", "waermepumpe") is None
    assert dq._ha_sensor_relevant(cli, True, zustand=True) and not dq._ha_sensor_relevant(sel, True, zustand=True)


# ── 8 · Demo und Wissensbasis ────────────────────────────────────────────────

def test_demo_wallbox_traegt_zustand_und_fahrzeugwerte():
    from backend.api.routes.live_dashboard import LiveDashboardResponse, _generate_demo_data

    d = LiveDashboardResponse(**_generate_demo_data(1, "Demo")).model_dump()
    k = {x["key"]: x for x in d["komponenten"]}
    wb6 = k["wallbox_6"]
    assert wb6["ladezustand"] in ("laedt", "wartet") and wb6["lademodus"] == "pv"
    assert wb6["sitzung"] == {"kwh": 9.8, "dauer_s": 7800.0}
    assert (wb6["ladestrom_a"], wb6["phasen_aktiv"]) == (16.0, 3.0)
    assert wb6["fahrzeuge"][0]["reichweite_km"] == 312.0 and wb6["fahrzeuge"][0]["ziel_prozent"] == 80.0
    assert k["wallbox_11"]["ladezustand"] in ("verbunden", "laedt")
    assert k["wallbox_11"]["fahrzeuge"][0]["reichweite_km"] == 140.0


def test_wissensbasis_schlaegt_belegte_entitaeten_vor():
    from backend.core.ha_integrations_wissen import analysiere_vorschlaege

    ids = ["select.evcc_carport_mode", "sensor.evcc_carport_session_energy", "sensor.wallbox_status_ladevorgang",
           "sensor.smart_ladesanschluss", "sensor.smart_reichweite", "sensor.smart_reichweite_bei_voller_ladung",
           "device_tracker.smart_none_2"]
    vor = lambda feld, typ: [v["entity_id"] for v in analysiere_vorschlaege(ids, feld, typ)["vorschlaege"]]  # noqa: E731
    assert vor("lademodus", "wallbox") == ["select.evcc_carport_mode"]
    assert vor("sitzung_kwh", "wallbox") == ["sensor.evcc_carport_session_energy"]
    assert vor("ladezustand", "wallbox") == ["sensor.wallbox_status_ladevorgang"]
    assert vor("reichweite_km", "e-auto") == ["sensor.smart_reichweite"]
    assert vor("zu_hause", "e-auto") == ["device_tracker.smart_none_2"]
