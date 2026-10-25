"""P-433-3 Sitzung 1 (#432, Konzept #433 Stufe 3, 25.10.2026) — Vorlauf, Rücklauf, Zusatzheizung live je Gerät.

**Registry (S1-1):** drei Live-Felder der Wärmepumpe — `vorlauf_temperatur_c`, `ruecklauf_temperatur_c` (°C),
`heizstab_leistung_w` (W) — Betriebsart `geraet`, **ohne Bedingung** (P13: an jeder Bauart in der ersten Reihe), je
ein Leser (`core/feld_auswertungen.py`, Wächter `test_jedes_feld_hat_eine_auswertung.py`), Mittelwert-Kanal im
Katalog. **Kein kWh-Feld in S1** (G1: der Heizstab-Zähler kommt mit seinem Leser in S2).

**Live je Gerät (S1-2):** der Wärmepumpen-Knoten trägt `vorlauf_c`, `ruecklauf_c`, `warmwasser_c`, `heizstab_w`
(Builder `_wp_geraete_werte`); das anlagenweite `warmwasser_temperatur_c` bleibt (erste WP mit Wert). Keine Summe
ändert sich — die Heizstab-Leistung ist ein Teil der Geräteleistung und wird nie addiert.

**Matheks Entitäten** (#432/#433, 23.10.2026) sind die Fixture der Live-, Datenquellen- und Checker-Proben:
Vorlauf `sensor.supply_line_bt2_30006`, Rücklauf `sensor.return_line_bt3_30008`, Zusatzheizung
`sensor.power_internal_additional_heat_31028`.

**Checker (S1-5):** INFO je Gerät «Sensor ohne Langzeitstatistik», wenn ein zugeordneter Vorlauf-/Rücklauf-/
Zusatzheizungs-Sensor in HA kein `state_class: measurement` trägt.

Schwesterdateien: test_341_live_merkmale.py (Bilanz bitgleich bis auf die Knoten-Zusätze, `P433_3_KNOTEN_FELDER`),
test_p433_2_datenquellen_betriebsart.py (Fixture der Client-Probe), test_p433_0_betriebsmodus_werte.py (Checker-Muster).
"""

from __future__ import annotations

from datetime import date

import pytest

from backend.api.routes import datenquellen as dq_modul
from backend.api.routes import live_dashboard
from backend.api.routes.datenquellen import get_datenquellen_felder
from backend.core.feld_auswertungen import KOMP_WP, sichten_fuer
from backend.core.field_definitions import (
    FELD_EINHEITEN,
    INVESTITION_FELDER,
    LIVE_FELDER_INV,
    WP_BETRIEBSART_GERAET,
    get_live_felder_fuer_investition,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.services import ha_state_service as hss
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckKategorie, CheckSeverity, LINK_DATENQUELLEN
from backend.services.kanal.katalog import ist_mean_spiegel
from backend.services.live_komponenten_builder import build_komponenten
from backend.services.live_power_service import LivePowerService

NEU = ("vorlauf_temperatur_c", "ruecklauf_temperatur_c", "heizstab_leistung_w")

#: Matheks Nibe-Entitäten (#432/#433, 23.10.2026).
MATHEK = {
    "vorlauf_temperatur_c": "sensor.supply_line_bt2_30006",
    "ruecklauf_temperatur_c": "sensor.return_line_bt3_30008",
    "heizstab_leistung_w": "sensor.power_internal_additional_heat_31028",
}
_KAT = CheckKategorie.SENSOR_OHNE_LANGZEITSTATISTIK.value


# ═══ S1-1 Registry ═══════════════════════════════════════════════════════════

def _live_feld(key: str) -> dict:
    (f,) = [f for f in LIVE_FELDER_INV["waermepumpe"] if f["key"] == key]
    return f


def test_drei_live_felder_am_geraet_ohne_bedingung():
    for key, einheit in zip(NEU, ("°C", "°C", "W")):
        f = _live_feld(key)
        assert f["einheit"] == einheit and FELD_EINHEITEN[key] == einheit, key
        assert f["betriebsart"] == WP_BETRIEBSART_GERAET, key
        assert "bedingung" not in f and "weich" not in f, f"{key}: P13 — an jeder Wärmepumpe zuordenbar"
        assert not f.get("zustand") and not f.get("je_innengeraet"), key
    assert [_live_feld(k)["label"] for k in NEU] == ["Vorlauf", "Rücklauf", "Leistung Zusatzheizung"]


@pytest.mark.parametrize("wp_art", ["luft_wasser", "sole_wasser", "grundwasser", "luft_luft", "brauchwasser"])
def test_an_jeder_bauart_in_der_ersten_reihe(wp_art):
    felder = {f["key"]: f for f in get_live_felder_fuer_investition("waermepumpe", {"wp_art": wp_art})}
    for key in NEU:
        assert key in felder and not felder[key].get("erweitert"), (wp_art, key)


def test_kein_kwh_feld_in_s1():
    """G1: der Heizstab-Zähler kommt in der Sitzung seines Lesers (S2) — S1 legt keine Menge an.

    Seit S2 steht genau EIN solches Feld da, ``heizstab_strom_kwh`` (Proben ``test_p433_3_s2_heizstab_zusatzheizung.py``).
    """
    namen = {f["feld"] for f in INVESTITION_FELDER["waermepumpe"]}
    assert {n for n in namen if "heizstab" in n or "zusatzheizung" in n} == {"heizstab_strom_kwh"}


def test_jedes_neue_feld_hat_einen_leser_im_komponenten_hub():
    for key in NEU:
        assert KOMP_WP in sichten_fuer("waermepumpe", key), key
    assert KOMP_WP in sichten_fuer("waermepumpe", "warmwasser_temperatur_c")


def test_mittelwert_kanal_im_katalog():
    """B7: kein neuer Datenpfad — der Kanal legt °C/W-Live-Felder als Mittelwert-Spiegel an."""
    for key in NEU:
        assert ist_mean_spiegel(f"inv:7:{key}", "waermepumpe"), key


# ═══ S1-2 Live je Gerät ══════════════════════════════════════════════════════

def _wp(inv_id: int, name: str = "Nibe S1255") -> Investition:
    return Investition(id=inv_id, anlage_id=1, typ="waermepumpe", bezeichnung=name,
                       anschaffungsdatum=date(2020, 1, 1), parameter={"wp_art": "sole_wasser"})


def _bau(inv_values: dict, invs: list[Investition]) -> dict:
    anlage = Anlage(id=1, anlagenname="P433-3", leistung_kwp=10.0)
    return build_komponenten(
        anlage, {"einspeisung_w": 0.0, "netzbezug_w": 2000.0}, inv_values,
        {str(i.id): i for i in invs}, {str(i.id): {k: f"sensor.{k}" for k in v} for i, v in
                                       zip(invs, inv_values.values())},
    )


def _knoten(res: dict, inv_id: int) -> dict:
    (k,) = [k for k in res["komponenten"] if k["key"] == f"waermepumpe_{inv_id}"]
    return k


def _mathek_live_werte() -> dict[str, dict[str, float]]:
    """Matheks Entitäten durch den echten Sammel-Schritt (`_collect_values`) — HA-Werte nach Entität."""
    live_map = {"7": {"leistung_w": "sensor.nibe_power", **MATHEK,
                      "warmwasser_temperatur_c": "sensor.hot_water_top_bt7_30013"}}
    sensor_values = {
        "sensor.nibe_power": 1200.4,
        "sensor.supply_line_bt2_30006": 34.23,
        "sensor.return_line_bt3_30008": 29.07,
        "sensor.power_internal_additional_heat_31028": 1500.4,
        "sensor.hot_water_top_bt7_30013": 48.26,
    }
    anlage = Anlage(id=1, anlagenname="P433-3", leistung_kwp=10.0)
    _basis, werte = LivePowerService.__new__(LivePowerService)._collect_values(anlage, {}, live_map, sensor_values)
    return werte


def test_mathek_vorlauf_ruecklauf_zusatzheizung_am_knoten():
    werte = _mathek_live_werte()
    k = _knoten(_bau(werte, [_wp(7)]), 7)
    assert (k["vorlauf_c"], k["ruecklauf_c"], k["warmwasser_c"], k["heizstab_w"]) == (34.2, 29.1, 48.3, 1500.0)
    # Spreizung aus dem Layer, aus den angezeigten Werten: 34,2 − 29,1 = 5,1 K (nicht 5,2 aus 34,23 − 29,07).
    assert k["spreizung_k"] == 5.1


def test_summen_unveraendert_heizstab_wird_nie_addiert():
    """`test_341`-Muster: dieselbe Anlage mit und ohne die neuen Werte — Bilanz, Gauges, Knoten bitgleich bis auf
    die vier Zusätze. Die Heizstab-Leistung (1500 W) liegt über der Geräteleistung (1200 W): würde sie addiert,
    stünde der Verbrauch bei 2,7 kW."""
    werte = _mathek_live_werte()
    ohne = {"7": {"leistung_w": werte["7"]["leistung_w"]}}
    mit, vorher = _bau(werte, [_wp(7)]), _bau(ohne, [_wp(7)])
    zusaetze = ("vorlauf_c", "ruecklauf_c", "spreizung_k", "warmwasser_c", "heizstab_w")
    mit_ohne_zusaetze = {**mit, "komponenten": [{f: w for f, w in k.items() if f not in zusaetze}
                                                 for k in mit["komponenten"]],
                         "warmwasser_temperatur_c": None}
    assert mit_ohne_zusaetze == vorher
    assert _knoten(mit, 7)["verbrauch_kw"] == 1.2 and mit["summe_verbrauch_kw"] == vorher["summe_verbrauch_kw"]
    assert mit["warmwasser_temperatur_c"] == 48.3, "der Anlagenwert bleibt (E-P3-7)"


def test_ohne_zuordnung_kein_schluessel_und_im_modell_none():
    res = _bau({"7": {"leistung_w": 800.0}}, [_wp(7)])
    k = _knoten(res, 7)
    assert not {"vorlauf_c", "ruecklauf_c", "spreizung_k", "warmwasser_c", "heizstab_w"} & set(k)
    modell = live_dashboard.LiveKomponente(**k).model_dump()
    assert (modell["vorlauf_c"], modell["ruecklauf_c"], modell["spreizung_k"], modell["warmwasser_c"],
            modell["heizstab_w"]) == (None,) * 5


def test_null_ist_ein_wert():
    """0 W Zusatzheizung ist «steht», nicht «fehlt» (`is not None`, CLAUDE.md)."""
    k = _knoten(_bau({"7": {"leistung_w": 800.0, "heizstab_leistung_w": 0.0}}, [_wp(7)]), 7)
    assert k["heizstab_w"] == 0.0


def test_zwei_waermepumpen_tragen_je_ihre_werte():
    """Sprengsatz-Ziel (Bauplan §4 S1): Kachel E auf den Anlagenwert zurück ⇒ diese Probe und die Client-Probe rot."""
    werte = {
        "7": {"leistung_w": 1200.0, "vorlauf_temperatur_c": 34.2, "warmwasser_temperatur_c": 48.0},
        "8": {"leistung_w": 600.0, "vorlauf_temperatur_c": 41.5, "warmwasser_temperatur_c": 52.4,
              "heizstab_leistung_w": 2000.0},
    }
    res = _bau(werte, [_wp(7), _wp(8, "Zweit-WP")])
    k7, k8 = _knoten(res, 7), _knoten(res, 8)
    assert (k7["vorlauf_c"], k7["warmwasser_c"], "heizstab_w" in k7) == (34.2, 48.0, False)
    assert "spreizung_k" not in k7, "nur Vorlauf ⇒ keine Spreizung"
    assert (k8["vorlauf_c"], k8["warmwasser_c"], k8["heizstab_w"]) == (41.5, 52.4, 2000.0)
    assert res["warmwasser_temperatur_c"] == 48.0, "anlagenweit: die erste WP mit Wert"


def test_demo_waermepumpe_traegt_die_geraetewerte():
    daten = live_dashboard.LiveDashboardResponse(**live_dashboard._generate_demo_data(1, "Demo")).model_dump()
    (wp,) = [k for k in daten["komponenten"] if k["key"] == "waermepumpe_5"]
    assert 33.0 <= wp["vorlauf_c"] <= 35.0 and 4.5 <= wp["vorlauf_c"] - wp["ruecklauf_c"] <= 5.5
    assert wp["heizstab_w"] == 0.0
    assert wp["spreizung_k"] == round(wp["vorlauf_c"] - wp["ruecklauf_c"], 1)
    assert wp["warmwasser_c"] == daten["warmwasser_temperatur_c"]


def test_spreizung_im_layer():
    """Eine Formel, ein Ort (Nacharbeit A3): `core/berechnungen/temperatur.spreizung_k` — Builder und Demo rufen sie."""
    from backend.core.berechnungen.temperatur import spreizung_k

    assert spreizung_k(34.2, 29.1) == pytest.approx(5.1)
    assert spreizung_k(30.0, 32.5) == pytest.approx(-2.5), "Kühlbetrieb: Rücklauf über Vorlauf, kein Betrag"
    assert spreizung_k(None, 29.1) is None and spreizung_k(34.2, None) is None
    assert spreizung_k(0.0, 0.0) == 0.0


# ═══ S1-4 Datenquellen ═══════════════════════════════════════════════════════

async def _anlage_mathek(db, *, live: dict | None = None, quellen: dict | None = None,
                         aktiv: bool = True) -> tuple[Anlage, Investition]:
    anlage = Anlage(anlagenname="P433-3-Mathek", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Nibe S1255",
                      anschaffungsdatum=date(2025, 1, 1),
                      stilllegungsdatum=None if aktiv else date(2025, 6, 30),
                      parameter={"wp_art": "sole_wasser", "kuehlung_art": "passiv", "getrennte_strommessung": True})
    db.add(inv)
    await db.flush()
    live = dict(MATHEK) if live is None else live
    if quellen is None:
        quellen = {f"inv_live_{inv.id}_{k}": {"quelle": "ha_app", "entity_id": e} for k, e in live.items()}
    anlage.sensor_mapping = {"quellen": quellen, "investitionen": {str(inv.id): {"live": live}}}
    await db.commit()
    return anlage, inv


async def test_datenquellen_mathek_im_block_geraet_gesamt(db, monkeypatch):
    anlage, _ = await _anlage_mathek(db)

    async def _fake_detail(_db, entity_ids):
        return {e: {"wert": 30.0, "wert_text": None, "einheit": None, "state_class": "measurement",
                    "friendly_name": e} for e in entity_ids}

    monkeypatch.setattr(dq_modul, "_ha_states_detail", _fake_detail)
    resp = await get_datenquellen_felder(anlage.id, db)
    (g,) = [g for g in resp["gruppen"] if g["typ"] == "waermepumpe"]
    felder = {f["feld"]: f for f in g["felder"]}
    for key, entity in MATHEK.items():
        f = felder[key]
        assert (f["betriebsart"], f["erweitert"], f["quelle"], f["ha_entity"]) == (
            WP_BETRIEBSART_GERAET, False, "ha_app", entity), key
        assert f["menge"] is None and f["kategorie"] == "live", key
        assert KOMP_WP in f["ausgewertet_in"], key


# ═══ S1-5 Checker «Sensor ohne Langzeitstatistik» ═════════════════════════════

class _FakeHa:
    def __init__(self, klassen: dict, *, verfuegbar: bool = True):
        self._k = klassen
        self.is_available = verfuegbar
        self.gefragt: list[str] = []

    async def get_sensor_state_classes(self, entity_ids):
        self.gefragt.extend(entity_ids)
        return {e: self._k[e] for e in entity_ids if e in self._k}

    # Für den vollen Lauf (`check_anlage`): die Nachbarn fragen dieselbe Dienst-Instanz.
    async def get_sensor_units(self, entity_ids):
        return {}

    async def get_zustand_states_batch(self, entity_ids):
        return {}


async def _meldungen(db, anlage, monkeypatch, fake: _FakeHa):
    monkeypatch.setattr(hss, "get_ha_state_service", lambda: fake)
    return await DatenChecker(db)._check_sensor_ohne_langzeitstatistik(anlage)


async def test_meldet_je_geraet_die_sensoren_ohne_measurement(db, monkeypatch):
    anlage, inv = await _anlage_mathek(db)
    fake = _FakeHa({MATHEK["vorlauf_temperatur_c"]: "measurement",
                    MATHEK["ruecklauf_temperatur_c"]: "",
                    MATHEK["heizstab_leistung_w"]: "total"})
    (e,) = await _meldungen(db, anlage, monkeypatch, fake)
    assert (e.kategorie, e.schwere, e.investition_id, e.link) == (_KAT, CheckSeverity.INFO.value, inv.id,
                                                                  LINK_DATENQUELLEN)
    assert e.meldung == "„Nibe S1255“: 2 Sensor(en) ohne Langzeitstatistik — Live ja, Tagesverlauf nein"
    assert "Rücklauf (sensor.return_line_bt3_30008)" in e.details
    assert "Leistung Zusatzheizung (sensor.power_internal_additional_heat_31028)" in e.details
    assert "supply_line" not in e.details
    assert sorted(fake.gefragt) == sorted(MATHEK.values()), "ein Abruf, genau die drei Sensoren"


async def test_still_wenn_alle_measurement_tragen(db, monkeypatch):
    anlage, _ = await _anlage_mathek(db)
    assert await _meldungen(db, anlage, monkeypatch, _FakeHa({e: "measurement" for e in MATHEK.values()})) == []


async def test_still_ohne_ha_und_ohne_state(db, monkeypatch):
    anlage, _ = await _anlage_mathek(db)
    assert await _meldungen(db, anlage, monkeypatch, _FakeHa({}, verfuegbar=False)) == []
    assert await _meldungen(db, anlage, monkeypatch, _FakeHa({})) == [], "nicht gelesen ist nicht «ohne»"


async def test_nur_die_drei_felder_und_nur_ha_zuordnungen(db, monkeypatch):
    """Warmwasser-Temperatur gehört nicht dazu (Bauplan S1-5); eine Zuordnung auf MQTT hat keine HA-Statistik."""
    live = {**MATHEK, "warmwasser_temperatur_c": "sensor.hot_water_top_bt7_30013"}
    anlage, inv = await _anlage_mathek(db, live=live, quellen={})
    anlage.sensor_mapping = {
        "quellen": {f"inv_live_{inv.id}_heizstab_leistung_w": {"quelle": "mqtt_inbound_standard", "entity_id": None}},
        "investitionen": {str(inv.id): {"live": live}},
    }
    await db.commit()
    fake = _FakeHa({e: "" for e in live.values()})
    (e,) = await _meldungen(db, anlage, monkeypatch, fake)
    assert e.meldung.startswith("„Nibe S1255“: 2 Sensor(en)")
    assert sorted(fake.gefragt) == sorted([MATHEK["vorlauf_temperatur_c"], MATHEK["ruecklauf_temperatur_c"]])


async def test_still_an_stillgelegter_waermepumpe_und_ohne_zuordnung(db, monkeypatch):
    anlage, _ = await _anlage_mathek(db, aktiv=False)
    fake = _FakeHa({e: "" for e in MATHEK.values()})
    assert await _meldungen(db, anlage, monkeypatch, fake) == []
    anlage2, _ = await _anlage_mathek(db, live={})
    assert await _meldungen(db, anlage2, monkeypatch, fake) == []
    assert fake.gefragt == [], "ohne Kandidaten wird HA nicht gefragt"


async def test_check_anlage_fuehrt_die_pruefung(db, monkeypatch):
    """Verdrahtung: der Befund erscheint im vollen Lauf."""
    anlage, _ = await _anlage_mathek(db)
    monkeypatch.setattr(hss, "get_ha_state_service", lambda: _FakeHa({e: "" for e in MATHEK.values()}))
    result = await DatenChecker(db).check_anlage(anlage.id)
    assert [e.kategorie for e in result.ergebnisse].count(_KAT) == 1


async def test_state_class_kommt_aus_demselben_state_abruf(monkeypatch):
    """`get_sensor_state_classes` liest `fetch_selected_states` (Abruf der Einheit) — leer heißt «ohne», fehlt heißt
    «nicht gelesen»."""
    gefragt: list = []

    async def _fetch(api_url, token, entity_ids, **_kw):
        gefragt.append(list(entity_ids))
        return {
            MATHEK["vorlauf_temperatur_c"]: {"attributes": {"state_class": "measurement", "unit_of_measurement": "°C"}},
            MATHEK["ruecklauf_temperatur_c"]: {"attributes": {"unit_of_measurement": "°C"}},
            MATHEK["heizstab_leistung_w"]: None,
        }

    monkeypatch.setattr(hss, "fetch_selected_states", _fetch)
    svc = hss.HAStateService()
    monkeypatch.setattr(svc, "api_url", "http://ha")
    monkeypatch.setattr(svc, "token", "token")
    assert await svc.get_sensor_state_classes(list(MATHEK.values())) == {
        MATHEK["vorlauf_temperatur_c"]: "measurement",
        MATHEK["ruecklauf_temperatur_c"]: "",
    }
    assert gefragt == [list(MATHEK.values())]
    monkeypatch.setattr(svc, "token", "")
    assert await svc.get_sensor_state_classes(list(MATHEK.values())) == {}
