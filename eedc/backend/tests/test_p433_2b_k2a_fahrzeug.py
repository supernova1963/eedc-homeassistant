"""P-433-2b K2a «Fahrzeug am Ladepunkt, Gast, Zuordnung» — Backend-Proben (Bauplan K2 Fassung 2 §3 E1–E3, §5 K2a;
Definitions-Blatt Fassung 3 §4/§5b/§6; Entscheide D1 eindeutig bei genau einer Rest-Wallbox · D2 Rohtext nicht auf der
Karte).

Was hier gesichert wird, und warum jede Gruppe existiert:

1. **Feldart Text** — `fahrzeug_am_ladepunkt` ist ein Zustandsfeld mit `text: True` ohne Kanon; die Menge
   `TEXT_LIVE_FELDER` ist **aus der Registry abgeleitet** (Wächter gegen eine getippte Liste, Sprengsatz S6); jedes
   Textfeld trägt `zustand` (sonst liefe es in den 5-s-Poller). `zustands_kanon.text`: «leer» ist ein Wert, «keine
   Antwort» nicht (E-K2-2), ≤ 80 Zeichen (E-K2-1). Stammdatum `kennung_in_steuerung` in Vergleichsform.
2. **Inbound** — die eine Weiche «leer ist ein Wert» nur für Textfelder (Sprengsatz S4); der Modus-Pfad bleibt.
3. **Leser** — ``""`` nur aus einer Antwort (HA-State da, MQTT-Cache-Eintrag da), nie aus dem Zuordnungs-Default
   (Sprengsatz S2, W1).
4. **Builder** — Treffer ⇒ «eindeutig» + Quelle Steuerung, Gast nur bei Fahrzeug am Ladepunkt (Sprengsatz S3), Text
   ohne Treffer ⇒ «unbekannt», D1, keine Korrelation (Sprengsatz S1), `parent_key` und Summen unverändert (Sprengsatz
   S5, zusätzlich Golden Master live-komponenten).
5. **Daten-Checker** — der Zustands-Check nimmt das Textfeld aus; `emob_kennung_unbekannt` nennt den Rohtext.
6. **Datenquellen, Topics, Wissensbasis, Demo, Antwort-Form.**

Schwesterdateien: test_p433_2b_k1_emob.py (K1-Felder, Kanon, Leser, Kanal-Katalog inkl. Textfeld),
test_standalone_s1_betriebsmodus_mqtt.py (Modus über MQTT, «leerer Payload verworfen»), test_341_live_merkmale.py.
"""

from __future__ import annotations

from backend.tests.werkzeug_befund import befund_link
import importlib.util
from datetime import date
from types import SimpleNamespace

import pytest

from backend.core import zustands_kanon as zk
from backend.core.field_definitions import (
    TEXT_LIVE_FELDER,
    ZUSTAND_LIVE_FELDER,
    get_live_felder_fuer_investition,
    ist_text_feld,
    ist_zustand_feld,
)
from backend.core.investition_parameter import PARAM_E_AUTO, kennung_in_steuerung
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.services import betriebsmodus_live as bml
from backend.services import mqtt_inbound_service as mis

FELD = "fahrzeug_am_ladepunkt"


# ── 1 · Feldart Text ─────────────────────────────────────────────────────────

def test_textfeld_in_der_registry():
    live = {f["key"]: f for f in get_live_felder_fuer_investition("wallbox", {})}
    f = live[FELD]
    assert f["zustand"] is True and f["text"] is True
    assert "kanon" not in f, "ein Textfeld hat keinen Kanon"
    assert f["erweitert"] is True and f["nur_live"] is True and f["abschnitt"] == "zustand"
    assert set(f["ha_domaenen"]) == {"select", "sensor", "input_text"}
    assert FELD not in {x["key"] for x in get_live_felder_fuer_investition("e-auto", {})}
    # Reihenfolge: der Ladezustand bleibt das erste Zustandsfeld des Abschnitts (Kopf «Zustands-Chip»).
    zustaende = [x["key"] for x in get_live_felder_fuer_investition("wallbox", {}) if x.get("zustand")]
    assert zustaende[0] == "ladezustand"


def test_text_ist_zustand_und_nichts_sonst():
    assert TEXT_LIVE_FELDER == {("wallbox", FELD)}
    assert ist_text_feld(FELD) and ist_text_feld(FELD, "wallbox") and not ist_text_feld(FELD, "e-auto")
    assert ist_zustand_feld(FELD, "wallbox"), "ein Textfeld erbt alle Zustands-Weichen"
    for feld in ("ladezustand", "lademodus", "betriebsmodus", "sitzung_kwh", "leistung_w"):
        assert not ist_text_feld(feld), feld
    assert FELD not in zk.ZUSTANDS_FELDER, "kein Kanon, keine Werte-Tabelle"


def test_waechter_jedes_textfeld_traegt_zustand_und_ist_abgeleitet():
    """G1 (Sprengsatz S6): die Textfeld-Menge kommt aus der Registry, keine getippte Liste daneben.

    Die Probe legt ein zweites Textfeld in eine **Kopie** der Registry-Tabelle und baut `karten.py` daraus neu (eigener
    Modulname, `sys.modules` bleibt unberührt): eine abgeleitete Menge kennt das neue Feld, eine getippte nicht.
    """
    from backend.core.field_definitions import registry

    for typ, felder in registry.LIVE_FELDER_INV.items():
        for f in felder:
            if f.get("text"):
                assert f.get("zustand") is True, (typ, f["key"])
                assert (typ, f["key"]) in TEXT_LIVE_FELDER
    assert TEXT_LIVE_FELDER <= ZUSTAND_LIVE_FELDER

    original = registry.LIVE_FELDER_INV
    kopie = {typ: list(felder) for typ, felder in original.items()}
    kopie["e-auto"] = kopie["e-auto"] + [{"key": "probe_text", "label": "Probe", "einheit": "", "zustand": True,
                                          "text": True}]
    registry.LIVE_FELDER_INV = kopie
    try:
        import backend.core.field_definitions.karten as karten_echt

        spec = importlib.util.spec_from_file_location("_karten_probe_k2a", karten_echt.__file__)
        neu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(neu)
    finally:
        registry.LIVE_FELDER_INV = original
    assert ("e-auto", "probe_text") in neu.TEXT_LIVE_FELDER
    assert neu.ist_text_feld("probe_text", "e-auto")


@pytest.mark.parametrize("roh,erwartet", [
    (None, None), ("unknown", None), ("unavailable", None), (" Unavailable ", None),
    ("", ""), ("   ", ""), ("null", ""), ("NULL", ""), ("None", ""), ("-", ""),
    (" ID.4 ", "ID.4"), ("Smart #1", "Smart #1"), ("x" * 100, "x" * 80),
])
def test_text_leer_ist_ein_wert_keine_antwort_nicht(roh, erwartet):
    assert zk.text(FELD, roh) == erwartet


def test_kennung_in_steuerung_vergleichsform():
    assert PARAM_E_AUTO["KENNUNG_IN_STEUERUNG"] == "kennung_in_steuerung"

    def auto(param):
        return Investition(id=1, typ="e-auto", bezeichnung="A", anschaffungsdatum=date(2020, 1, 1), parameter=param)

    assert kennung_in_steuerung(auto({"kennung_in_steuerung": "  ID.4 "})) == "id.4"
    assert kennung_in_steuerung(auto({"kennung_in_steuerung": "   "})) is None
    assert kennung_in_steuerung(auto({"kennung_in_steuerung": 4})) is None
    assert kennung_in_steuerung(auto({})) is None
    assert kennung_in_steuerung(auto(None)) is None
    assert zk.text_schluessel(" ZOE ") == kennung_in_steuerung(auto({"kennung_in_steuerung": "zoe"}))


# ── 2 · Inbound ──────────────────────────────────────────────────────────────

def _topic(anlage_id: int, inv_id: int, feld: str) -> str:
    return f"eedc/{anlage_id}_A/live/inv/{inv_id}_WB/{feld}"


def test_inbound_leerer_text_ist_ein_wert():
    """Sprengsatz S4 (W2): ein leerer Payload am Textfeld landet als «» im Cache — und überschreibt den Namen."""
    cache = mis.MqttInboundCache()
    cache.on_message(_topic(1, 4, FELD), " Smart ")
    assert cache.get_all_live_inv(1)["4"][FELD] == "Smart"
    cache.on_message(_topic(1, 4, FELD), "")
    assert cache.get_all_live_inv(1)["4"][FELD] == ""


def test_inbound_modus_pfad_unveraendert():
    cache = mis.MqttInboundCache()
    cache.on_message(_topic(1, 4, "ladezustand"), "laedt")
    cache.on_message(_topic(1, 4, "ladezustand"), "")
    assert cache.get_all_live_inv(1)["4"]["ladezustand"] == "laedt", "ein leerer Kanon-Zustand bleibt verworfen"
    assert mis._wert_aus_payload(True, "", "t") is None
    assert mis._wert_aus_payload(True, "", "t", ist_text=True) == ""
    assert mis._wert_aus_payload(False, "", "t", ist_text=False) is None


# ── 3 · Leser ────────────────────────────────────────────────────────────────

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
    monkeypatch.setattr("backend.services.ha_state_service.get_ha_state_service",
                        lambda: _FakeHa(zustaende, verfuegbar))


def _stelle_inbound(monkeypatch) -> mis.MqttInboundCache:
    cache = mis.MqttInboundCache()
    monkeypatch.setattr(mis, "_mqtt_inbound_service", SimpleNamespace(cache=cache))
    return cache


async def _anlage(db, *, wb_live=None, kennung=None, zweites_auto=None):
    anlage = Anlage(anlagenname="K2a", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    wb = Investition(anlage_id=anlage.id, typ="wallbox", bezeichnung="SMA eCharger 22",
                     anschaffungsdatum=date(2025, 1, 1))
    ea = Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="Smart #1", anschaffungsdatum=date(2025, 1, 1),
                     parameter={"kennung_in_steuerung": kennung} if kennung is not None else {})
    db.add_all([wb, ea])
    if zweites_auto is not None:
        db.add(Investition(anlage_id=anlage.id, typ="e-auto", bezeichnung="ID.4", anschaffungsdatum=date(2025, 1, 1),
                           parameter={"kennung_in_steuerung": zweites_auto}))
    await db.flush()
    anlage.sensor_mapping = {"investitionen": {str(wb.id): {"live": wb_live}} if wb_live is not None else {}}
    await db.commit()
    return anlage, wb, ea


async def test_leser_ha_null_ist_leer_und_name_bleibt_text(db, monkeypatch):
    anlage, wb, _ = await _anlage(db, wb_live={FELD: "select.evcc_carport_vehicle_name",
                                               "ladezustand": "sensor.wb_status"})
    _stelle_ha(monkeypatch, {"select.evcc_carport_vehicle_name": ("null", None), "sensor.wb_status": ("sleep_mode", None)})
    z = await bml.lade_zustaende_live(db, anlage)
    assert z[(wb.id, FELD)] == "" and z[(wb.id, "ladezustand")] == "verbunden"
    bml.cache_leeren()
    _stelle_ha(monkeypatch, {"select.evcc_carport_vehicle_name": (" My Smart ", None)})
    assert (await bml.lade_zustaende_live(db, anlage))[(wb.id, FELD)] == "My Smart"


async def test_leser_ha_ohne_antwort_kein_eintrag(db, monkeypatch):
    anlage, wb, _ = await _anlage(db, wb_live={FELD: "select.evcc_carport_vehicle_name"})
    _stelle_ha(monkeypatch, {"select.evcc_carport_vehicle_name": None})
    assert (wb.id, FELD) not in await bml.lade_zustaende_live(db, anlage)


async def test_leser_mqtt_leer_nur_mit_cache_eintrag(db, monkeypatch):
    """Sprengsatz S2 (W1): ohne Cache-Eintrag kein «» — der Zuordnungs-Default «ohne HA ⇒ MQTT» erfindet keinen Gast."""
    anlage, wb, _ = await _anlage(db)
    cache = _stelle_inbound(monkeypatch)
    _stelle_ha(monkeypatch, {}, verfuegbar=False)
    cache.on_message(_topic(anlage.id, wb.id, "ladezustand"), "verbunden")
    z = await bml.lade_zustaende_live(db, anlage)
    assert z == {(wb.id, "ladezustand"): "verbunden"}, "Wallbox ohne Textquelle: kein Text, also kein Gast"
    bml.cache_leeren()
    cache.on_message(_topic(anlage.id, wb.id, FELD), "")
    assert (await bml.lade_zustaende_live(db, anlage))[(wb.id, FELD)] == ""


# ── 4 · Builder ──────────────────────────────────────────────────────────────

def _inv(i, typ, bez, **param):
    return Investition(id=i, typ=typ, bezeichnung=bez, anschaffungsdatum=date(2020, 1, 1), parameter=param or None)


def _baue(werte: dict, invs: list, zustand_map=None, live=None):
    from backend.services.live_komponenten_builder import build_komponenten

    lm = live if live is not None else {k: {"leistung_w": f"sensor.{k}"} for k, v in werte.items() if "leistung_w" in v}
    return build_komponenten(
        Anlage(anlagenname="B", leistung_kwp=10.0), {"einspeisung_w": 0.0, "netzbezug_w": 9000.0}, werte,
        {str(i.id): i for i in invs}, lm, zustand_map=zustand_map,
    )


def _knoten(erg, key):
    return next(k for k in erg["komponenten"] if k["key"] == key)


def _labels(k):
    return [f["label"] for f in k.get("fahrzeuge") or []]


WB1, WB2 = _inv(4, "wallbox", "Garage"), _inv(6, "wallbox", "Carport")
ZOE = _inv(8, "e-auto", "Zoe", kennung_in_steuerung="ZOE")
IONIQ = _inv(9, "e-auto", "Ioniq", kennung_in_steuerung="ioniq", ist_dienstlich=True)
ZWEI_WB = {"4": {"leistung_w": 3000.0}, "6": {"leistung_w": 2000.0}, "8": {"soc": 20.0}, "9": {"soc": 55.0}}


def test_treffer_an_wb1_nennt_nur_dieses_auto_und_d1():
    erg = _baue(ZWEI_WB, [WB1, WB2, ZOE, IONIQ], {(4, FELD): " Ioniq ", (4, "ladezustand"): "laedt"})
    wb1, wb2 = _knoten(erg, "wallbox_4"), _knoten(erg, "wallbox_6")
    assert _labels(wb1) == ["Ioniq"] and wb1["fahrzeuge_zuordnung"] == "eindeutig"
    assert wb1["fahrzeuge_quelle"] == "steuerung" and "gast" not in wb1 and "fahrzeug_unbekannt" not in wb1
    assert wb1["fahrzeuge"][0]["dienstwagen"] is True
    # D1: genau eine Wallbox ohne Steuerungs-Aussage ⇒ «eindeutig» mit dem Rest; sie nennt das Auto 2 nicht.
    assert _labels(wb2) == ["Zoe"] and wb2["fahrzeuge_zuordnung"] == "eindeutig" and "fahrzeuge_quelle" not in wb2
    assert "fahrzeuge_ohne_wallbox" not in erg


def test_treffer_verschiebt_parent_key_nicht_und_keine_summe():
    """Sprengsatz S5 (K2-5): Schritt 1 reihum bleibt — Ioniq (eigener Knoten) steht im Bild unter Wallbox 6."""
    werte = dict(ZWEI_WB, **{"9": {"leistung_w": 2999.0, "soc": 55.0}})
    ohne = _baue(werte, [WB1, WB2, ZOE, IONIQ], {})
    mit = _baue(werte, [WB1, WB2, ZOE, IONIQ], {(4, FELD): "ioniq"})
    assert _knoten(mit, "eauto_9")["parent_key"] == _knoten(ohne, "eauto_9")["parent_key"] == "wallbox_6"
    assert _labels(_knoten(mit, "wallbox_4")) == ["Ioniq"]
    for schluessel in ("summe_erzeugung_kw", "summe_verbrauch_kw", "verbrauch_gesamt_kw", "gauges"):
        assert mit[schluessel] == ohne[schluessel], schluessel
    assert _knoten(mit, "haushalt") == _knoten(ohne, "haushalt")


def test_gast_bei_leerem_text_und_fahrzeug_am_ladepunkt():
    for zustand in ("verbunden", "wartet", "laedt", "fertig"):
        erg = _baue({"4": {"leistung_w": 7400.0}, "8": {"soc": 40.0}}, [WB1, ZOE],
                    {(4, FELD): "", (4, "ladezustand"): zustand})
        k = _knoten(erg, "wallbox_4")
        assert k["gast"] is True and k["fahrzeuge"] == [], zustand
        assert k["fahrzeuge_zuordnung"] == "eindeutig" and k["fahrzeuge_quelle"] == "steuerung"
        assert [f["label"] for f in erg["fahrzeuge_ohne_wallbox"]] == ["Zoe"], "das Auto steht an keiner Wallbox"


def test_kein_gast_ohne_fahrzeug_am_ladepunkt():
    """Sprengsatz S3: leerer Text bei «kein Fahrzeug», «gesperrt», «Fehler» oder ohne Ladezustand ⇒ kein Gast — K1."""
    werte, invs = {"4": {"leistung_w": 0.0}, "8": {"soc": 40.0}}, [WB1, ZOE]
    k1 = _baue(werte, invs, {(4, "ladezustand"): "kein_fahrzeug"})
    for zustand in ("kein_fahrzeug", "gesperrt", "fehler", None):
        zm = {(4, FELD): ""}
        if zustand is not None:
            zm[(4, "ladezustand")] = zustand
        k = _knoten(_baue(werte, invs, zm), "wallbox_4")
        assert "gast" not in k and "fahrzeuge_quelle" not in k, zustand
        assert _labels(k) == ["Zoe"] and k["fahrzeuge_zuordnung"] == "eindeutig"
    assert _knoten(_baue(werte, invs, {(4, FELD): "", (4, "ladezustand"): "kein_fahrzeug"}), "wallbox_4") == \
        _knoten(k1, "wallbox_4")


def test_ohne_textquelle_kein_gast():
    """W1: Wallbox ohne Text-Antwort und «verbunden» ⇒ kein Gast, Ergebnis wie K1."""
    k = _knoten(_baue({"4": {"leistung_w": 0.0}, "8": {"soc": 40.0}}, [WB1, ZOE],
                      {(4, "ladezustand"): "verbunden"}), "wallbox_4")
    assert "gast" not in k and _labels(k) == ["Zoe"] and k["fahrzeuge_zuordnung"] == "eindeutig"


def test_text_ohne_treffer_ist_unbekannt():
    erg = _baue({"4": {"leistung_w": 3000.0}, "8": {"soc": 20.0}}, [WB1, ZOE],
                {(4, FELD): "fremd", (4, "ladezustand"): "laedt"})
    k = _knoten(erg, "wallbox_4")
    assert k["fahrzeug_unbekannt"] is True and k["fahrzeuge"] == [] and k["fahrzeuge_quelle"] == "steuerung"
    assert k["fahrzeuge_zuordnung"] == "eindeutig" and "gast" not in k
    assert [f["label"] for f in erg["fahrzeuge_ohne_wallbox"]] == ["Zoe"]


def test_keine_korrelation_aus_zwei_verbunden():
    """Sprengsatz S1 (Blatt §4 «Nie»): Auto meldet verbunden ∧ Wallbox meldet verbunden ⇒ keine Zuordnung."""
    erg = _baue(ZWEI_WB, [WB1, WB2, ZOE, IONIQ],
                {(4, "ladezustand"): "verbunden", (6, "ladezustand"): "kein_fahrzeug",
                 (9, "ladezustand_fahrzeug"): "verbunden", (8, "ladezustand_fahrzeug"): "nicht_verbunden"})
    for key in ("wallbox_4", "wallbox_6"):
        k = _knoten(erg, key)
        assert k["fahrzeuge_zuordnung"] == "geschaetzt" and "fahrzeuge_quelle" not in k, key
    # reihum nach ID, wie K1: Zoe (8) → Wallbox 4, Ioniq (9) → Wallbox 6
    assert (_labels(_knoten(erg, "wallbox_4")), _labels(_knoten(erg, "wallbox_6"))) == (["Zoe"], ["Ioniq"])


def test_zwei_rest_wallboxen_reihum_geschaetzt():
    wb3 = _inv(7, "wallbox", "Hof")
    werte = dict(ZWEI_WB, **{"7": {"leistung_w": 1000.0}, "10": {"soc": 70.0}})
    id3 = _inv(10, "e-auto", "ID3")
    erg = _baue(werte, [WB1, WB2, wb3, ZOE, IONIQ, id3], {(4, FELD): "ioniq"})
    assert _labels(_knoten(erg, "wallbox_4")) == ["Ioniq"]
    assert [_knoten(erg, k)["fahrzeuge_zuordnung"] for k in ("wallbox_6", "wallbox_7")] == ["geschaetzt"] * 2
    assert (_labels(_knoten(erg, "wallbox_6")), _labels(_knoten(erg, "wallbox_7"))) == (["Zoe"], ["ID3"])


def test_ein_auto_nur_an_einer_wallbox():
    """Zwei Wallboxen melden denselben Namen: die erste (nach ID) bekommt das Auto, die zweite «unbekannt»."""
    erg = _baue(ZWEI_WB, [WB1, WB2, ZOE, IONIQ], {(4, FELD): "zoe", (6, FELD): "Zoe"})
    assert _labels(_knoten(erg, "wallbox_4")) == ["Zoe"]
    assert _knoten(erg, "wallbox_6")["fahrzeug_unbekannt"] is True
    assert [f["label"] for f in erg["fahrzeuge_ohne_wallbox"]] == ["Ioniq"]


def test_ohne_text_bitgleich_zu_k1():
    """Bestand: ein Zustand ohne Textfeld (und ein Text an keiner Wallbox mit Knoten) ändert nichts an K1."""
    import json

    zm = {(4, "ladezustand"): "laedt", (6, "ladezustand"): "verbunden"}
    a = _baue(ZWEI_WB, [WB1, WB2, ZOE, IONIQ], zm)
    b = _baue(ZWEI_WB, [WB1, WB2, ZOE, IONIQ], {**zm, (99, FELD): "ioniq"})
    assert json.dumps(a) == json.dumps(b)
    assert _knoten(a, "wallbox_4")["fahrzeuge_zuordnung"] == "geschaetzt"


# ── 5 · Daten-Checker ────────────────────────────────────────────────────────

async def _checker(db):
    from backend.services.daten_checker import DatenChecker

    return DatenChecker(db)


async def test_checker_kennung_unbekannt_mit_rohtext(db, monkeypatch):
    anlage, wb, ea = await _anlage(db, wb_live={FELD: "select.evcc_carport_vehicle_name"}, kennung="Smart")
    _stelle_ha(monkeypatch, {"select.evcc_carport_vehicle_name": ("fremd", None)})
    erg = await (await _checker(db))._check_emob_kennung_unbekannt(anlage)
    assert len(erg) == 1
    m = erg[0]
    assert m.kategorie == "emob_kennung_unbekannt" and m.schwere == "info" and m.investition_id == wb.id
    assert "„fremd“" in m.meldung and "SMA eCharger 22" in m.meldung
    assert "Kennung in der Steuerung" in m.details
    # E6.D D3 (W-14): der Befund gehört zur Wallbox, der Sprung zum E-Auto — das Feld gibt es nur dort.
    assert befund_link(m) == f"/einstellungen/komponenten?bearbeiten={ea.id}&feld=kennung_in_steuerung"


async def test_checker_kennung_unbekannt_zwei_autos_oeffnet_uebersicht(db, monkeypatch):
    """E6.D D3: mit zwei E-Autos kennt der Erzeuger das passende nicht — der Sprung öffnet die Komponenten-Übersicht."""
    anlage, wb, _ea = await _anlage(db, wb_live={FELD: "select.evcc_carport_vehicle_name"}, kennung="Smart",
                                    zweites_auto="id4")
    _stelle_ha(monkeypatch, {"select.evcc_carport_vehicle_name": ("fremd", None)})
    (m,) = await (await _checker(db))._check_emob_kennung_unbekannt(anlage)
    assert m.investition_id == wb.id and befund_link(m) == "/einstellungen/komponenten"
    # Der Zustands-Check («fremder Wert») nimmt das Textfeld aus — ein Name ist kein unbekannter Kanon-Wert.
    assert await (await _checker(db))._check_emob_zustand_wert(anlage) == []


@pytest.mark.parametrize("ha_wert", [("SMART", None), ("null", None), None])
async def test_checker_still_bei_treffer_gast_und_ohne_antwort(db, monkeypatch, ha_wert):
    anlage, _wb, _ea = await _anlage(db, wb_live={FELD: "select.evcc_carport_vehicle_name"}, kennung=" smart ")
    _stelle_ha(monkeypatch, {"select.evcc_carport_vehicle_name": ha_wert})
    assert await (await _checker(db))._check_emob_kennung_unbekannt(anlage) == []


async def test_checker_ueber_mqtt_und_zweites_auto(db, monkeypatch):
    anlage, wb, _ea = await _anlage(db, kennung="Smart", zweites_auto="id4")
    cache = _stelle_inbound(monkeypatch)
    _stelle_ha(monkeypatch, {}, verfuegbar=False)
    cache.on_message(_topic(anlage.id, wb.id, FELD), "ID4")
    assert await (await _checker(db))._check_emob_kennung_unbekannt(anlage) == []
    cache.on_message(_topic(anlage.id, wb.id, FELD), "Tesla")
    erg = await (await _checker(db))._check_emob_kennung_unbekannt(anlage)
    assert [("„Tesla“" in m.meldung, m.investition_id) for m in erg] == [(True, wb.id)]


async def test_checker_ruft_den_neuen_check(db):
    """Die Kategorie hängt im Gesamtlauf (`DatenChecker.check_all`-Reihe) — ohne HA/MQTT still."""
    import inspect

    from backend.services import daten_checker as dc

    assert "_check_emob_kennung_unbekannt(anlage)" in inspect.getsource(dc)


# ── 6 · Datenquellen, Topics, Wissensbasis, Demo, Antwort-Form ───────────────

def test_datenquellen_textfeld_ohne_tabelle_und_ohne_klartext():
    from backend.api.routes import datenquellen as dq

    e = {"feld": FELD, "zustand": True}
    assert dq._zulaessige_werte(e, "ha_app") is None
    assert dq._zulaessige_werte(e, "mqtt_inbound_standard") is None
    assert dq._wert_klartext(e, "id4", "ha_app") is None, "kein «Unbestimmt» wie beim Modus"
    assert dq._wert_klartext(e, "", "mqtt_inbound_standard") is None
    sel = {"entity_id": "select.evcc_carport_vehicle_name", "attributes": {}}
    txt = {"entity_id": "input_text.fahrzeug", "attributes": {}}
    dom = dq._ha_domaenen(FELD, "wallbox")
    assert dq._ha_sensor_relevant(sel, True, zustand=True, domaenen=dom)
    assert dq._ha_sensor_relevant(txt, True, zustand=True, domaenen=dom)


async def test_topic_ist_zustand_also_kein_initialwert(db):
    """`live_mqtt_inbound.py` publiziert den Startwert «0» nur für Topics ohne `zustand` — ein Text bekäme sonst «0»."""
    from backend.services.mqtt_topic_registry import build_expected_topics

    anlage, wb, _ = await _anlage(db)
    topics = [t for t in await build_expected_topics(db, anlage) if t.get("feld") == FELD]
    assert len(topics) == 1 and topics[0]["zustand"] is True
    assert f"/live/inv/{wb.id}_" in topics[0]["topic"] and topics[0]["topic"].endswith(f"/{FELD}")


def test_wissensbasis_evcc_vehicle_name():
    from backend.core.ha_integrations_wissen import analysiere_vorschlaege

    ids = ["select.evcc_carport_vehicle_name", "select.evcc_carport_mode", "sensor.evcc_carport_session_energy"]
    vor = lambda feld: [v["entity_id"] for v in analysiere_vorschlaege(ids, feld, "wallbox")["vorschlaege"]]  # noqa: E731
    assert vor(FELD) == ["select.evcc_carport_vehicle_name"]
    assert vor("lademodus") == ["select.evcc_carport_mode"]


def test_demo_steuerung_und_d1():
    from backend.api.routes.live_dashboard import LiveDashboardResponse, _generate_demo_data

    d = LiveDashboardResponse(**_generate_demo_data(1, "Demo")).model_dump()
    k = {x["key"]: x for x in d["komponenten"]}
    assert k["wallbox_6"]["fahrzeuge_zuordnung"] == "eindeutig" and k["wallbox_6"]["fahrzeuge_quelle"] == "steuerung"
    assert [f["label"] for f in k["wallbox_6"]["fahrzeuge"]] == ["VW ID.4"]
    assert k["wallbox_11"]["fahrzeuge_zuordnung"] == "eindeutig" and k["wallbox_11"]["fahrzeuge_quelle"] is None
    assert [f["label"] for f in k["wallbox_11"]["fahrzeuge"]] == ["Renault Zoe"]


def test_antwort_form_traegt_die_drei_kennzeichen():
    """⛔ FastAPI verwirft Undeklariertes still — die drei Schlüssel müssen im Response-Modell stehen."""
    from backend.api.routes.live_dashboard import LiveKomponente

    k = LiveKomponente(key="wallbox_4", label="WB", icon="plug", fahrzeuge=[], fahrzeuge_zuordnung="eindeutig",
                       fahrzeuge_quelle="steuerung", gast=True, fahrzeug_unbekannt=False).model_dump()
    assert (k["fahrzeuge_quelle"], k["gast"], k["fahrzeug_unbekannt"]) == ("steuerung", True, False)
    leer = LiveKomponente(key="wallbox_4", label="WB", icon="plug").model_dump()
    assert (leer["fahrzeuge_quelle"], leer["gast"], leer["fahrzeug_unbekannt"]) == (None, False, False)
    with pytest.raises(Exception):
        LiveKomponente(key="w", label="W", icon="plug", fahrzeuge_zuordnung="steuerung")
