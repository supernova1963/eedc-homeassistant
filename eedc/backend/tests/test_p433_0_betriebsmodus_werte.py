"""P-433-0 (Konzept #433 E12, 24.10.2026) — die Werte-Tabelle des Betriebsmodus nach außen.

(a) **Am Feld:** die Datenquellen-Fläche liefert am Feld „Betriebsmodus“ die Werte, die eedc versteht —
abgeleitet aus dem Kanon (`core/betriebsmodus.py::_ZUSTAND_ZU_KANON`), nicht getippt.

(b) **Im Daten-Checker:** liefert der zugeordnete Sensor einen Wert außerhalb der Tabelle (Matheks
Prioritäts-Slugs `heating`, `standby`, `pool`), fällt die Stunde still auf `unbestimmt` und ihr Strom in „nicht
aufgeteilt“. ``_check_klima_modus_sensor`` meldet nur den fehlenden Sensor; ``_check_klima_modus_wert`` nennt
den unbekannten Wert. Proben: still ohne Auslöser · still im Grenzfall · Meldung mit richtigem Inhalt.
Der HA-Zugriff ist der einzige gemockte Teil.
"""

from __future__ import annotations

from datetime import date

import pytest

import backend.services.ha_state_service as hss
from backend.api.routes import datenquellen as dq_modul
from backend.api.routes.datenquellen import get_datenquellen_felder
from backend.core.betriebsmodus import (
    _ZUSTAND_ZU_KANON,
    UNBESTIMMT,
    UNBESTIMMT_ZUSTAENDE,
    betriebsmodus_werte_je_betriebsart,
    betriebsmodus_werte_klartext,
    ist_bekannter_betriebsmodus_wert,
)
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401
from backend.services.daten_checker import DatenChecker
from backend.services.daten_checker.kategorien import CheckKategorie, LINK_DATENQUELLEN

_MODUS = "sensor.wp_prioritaet"
_KAT = CheckKategorie.KLIMA_MODUS_WERT.value


# ═══ Der Kanon-Export ════════════════════════════════════════════════════════

def test_werte_je_betriebsart_deckt_die_tabelle_vollstaendig():
    """Jeder Tabellen-Wert steht genau einmal in der Ausgabe, unter seiner Betriebsart — keine zweite Liste."""
    gruppen = betriebsmodus_werte_je_betriebsart()
    flach = [(w, g["kanon"]) for g in gruppen for w in g["werte"]]
    assert sorted(flach) == sorted(_ZUSTAND_ZU_KANON.items())
    assert gruppen[0] == {"kanon": "heizen", "label": "Heizen", "werte": ["heat", "heizen"]}
    assert gruppen[-1]["kanon"] == UNBESTIMMT


def test_unbestimmte_zustaende_und_bekannt_pruefung():
    assert UNBESTIMMT_ZUSTAENDE == {"auto", "heat_cool", "automatik"}
    assert ist_bekannter_betriebsmodus_wert(" Heat ")
    assert ist_bekannter_betriebsmodus_wert("automatik"), "bewusst unbestimmt ist bekannt"
    assert not ist_bekannter_betriebsmodus_wert("heating"), "hvac_action-Wort, kein Zustand"
    assert not ist_bekannter_betriebsmodus_wert(None)


def test_klartext_nennt_alle_werte():
    satz = betriebsmodus_werte_klartext()
    for roh in _ZUSTAND_ZU_KANON:
        assert roh in satz, roh
    assert satz.endswith("als unbestimmt gezählt: auto, heat_cool, automatik")


# ═══ (a) Am Feld der Zuordnungs-Fläche ══════════════════════════════════════

async def _anlage_fuer_flaeche(db, monkeypatch):
    anlage = Anlage(anlagenname="P433", leistung_kwp=10.0, sensor_mapping={"investitionen": {}})
    db.add(anlage)
    await db.flush()
    inv = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Nibe",
                      parameter={"wp_art": "luft_wasser"})
    db.add(inv)
    await db.flush()
    anlage.sensor_mapping = {
        "quellen": {f"inv_live_{inv.id}_betriebsmodus": {"quelle": "ha_app", "entity_id": _MODUS}},
        "investitionen": {str(inv.id): {"live": {"betriebsmodus": _MODUS}}},
    }
    db.add(anlage)
    await db.flush()

    async def _fake_detail(_db, entity_ids):
        return {_MODUS: {"wert": None, "wert_text": "heating", "einheit": None,
                         "state_class": None, "friendly_name": "WP Priorität"}} if _MODUS in entity_ids else {}

    monkeypatch.setattr(dq_modul, "_ha_states_detail", _fake_detail)
    return anlage


async def _felder(db, anlage_id) -> dict:
    resp = await get_datenquellen_felder(anlage_id, db)
    return {f["feld"]: f for g in resp["gruppen"] for f in g["felder"]}


async def test_feld_betriebsmodus_traegt_die_werte_aus_dem_kanon(db, monkeypatch):
    anlage = await _anlage_fuer_flaeche(db, monkeypatch)
    felder = await _felder(db, anlage.id)

    assert felder["betriebsmodus"]["zulaessige_werte"] == betriebsmodus_werte_je_betriebsart()
    # Die Nachbarschaft bleibt: der Rohwert und seine Deutung stehen weiter daneben.
    assert felder["betriebsmodus"]["wert_klartext"] == "Unbestimmt"


async def test_zahlenfeld_traegt_keine_werte_liste(db, monkeypatch):
    anlage = await _anlage_fuer_flaeche(db, monkeypatch)
    felder = await _felder(db, anlage.id)

    zahlenfelder = [f for k, f in felder.items() if not f["zustand"]]
    assert zahlenfelder, "Probe ohne Gegenstand"
    assert all(f["zulaessige_werte"] is None for f in zahlenfelder)


# ═══ (b) Der Daten-Checker ══════════════════════════════════════════════════

class _FakeHa:
    def __init__(self, zustaende: dict, *, verfuegbar: bool = True):
        self._z = zustaende
        self.is_available = verfuegbar
        self.gefragt: list[str] = []

    async def get_zustand_states_batch(self, entity_ids):
        self.gefragt.extend(entity_ids)
        return {e: self._z.get(e) for e in entity_ids}


async def _anlage_mit_modus(db, live: dict | None = None, *, zweite: bool = False):
    anlage = Anlage(anlagenname="P433-Checker", leistung_kwp=10.0, installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Nibe S1255",
                      anschaffungsdatum=date(2025, 1, 1), parameter={"wp_art": "luft_wasser"})
    db.add(inv)
    await db.flush()
    invs = {str(inv.id): {"live": live if live is not None else {"betriebsmodus": _MODUS}}}
    if zweite:
        inv2 = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Zweit-WP",
                           anschaffungsdatum=date(2025, 1, 1), parameter={"wp_art": "luft_wasser"})
        db.add(inv2)
        await db.flush()
        invs[str(inv2.id)] = {"live": {"betriebsmodus": _MODUS}}
    anlage.sensor_mapping = {"investitionen": invs}
    await db.commit()
    return anlage, inv


async def _meldungen(db, anlage, monkeypatch, fake: _FakeHa):
    monkeypatch.setattr(hss, "get_ha_state_service", lambda: fake)
    return await DatenChecker(db)._check_klima_modus_wert(anlage)


async def test_still_ohne_zuordnung_und_ohne_ha_abfrage(db, monkeypatch):
    anlage, _ = await _anlage_mit_modus(db, live={})
    fake = _FakeHa({_MODUS: ("heating", None)})
    assert await _meldungen(db, anlage, monkeypatch, fake) == []
    assert fake.gefragt == [], "ohne Zuordnung wird HA gar nicht gefragt"


async def test_still_ohne_ha_verbindung(db, monkeypatch):
    anlage, _ = await _anlage_mit_modus(db)
    fake = _FakeHa({_MODUS: ("heating", None)}, verfuegbar=False)
    assert await _meldungen(db, anlage, monkeypatch, fake) == []


async def test_still_bei_unknown_und_unavailable(db, monkeypatch):
    """`get_zustand_states_batch` liefert dafür ``None`` — kein Wert ist kein falscher Wert."""
    anlage, _ = await _anlage_mit_modus(db)
    assert await _meldungen(db, anlage, monkeypatch, _FakeHa({_MODUS: None})) == []


@pytest.mark.parametrize("zustand", ["heat", " Warmwasser ", "kühlen", "off", "auto", "heat_cool", "automatik"])
async def test_still_bei_bekanntem_und_bewusst_unbestimmtem_wert(db, monkeypatch, zustand):
    anlage, _ = await _anlage_mit_modus(db)
    assert await _meldungen(db, anlage, monkeypatch, _FakeHa({_MODUS: (zustand, None)})) == []


async def test_still_wenn_hvac_action_die_richtung_nennt(db, monkeypatch):
    """Grenzfall: der Zustand ist unbekannt, aber der Ist-Betrieb schlägt ihn — die Stunde ist nicht unbestimmt."""
    anlage, _ = await _anlage_mit_modus(db)
    assert await _meldungen(db, anlage, monkeypatch, _FakeHa({_MODUS: ("pool", "heating")})) == []


async def test_still_bei_mehrdeutiger_quelle(db, monkeypatch):
    """N-340: verschiedene Modus-Quellen an einem Gerät ergeben keinen Wert — das meldet der Nachbar."""
    anlage, _ = await _anlage_mit_modus(db, live={"betriebsmodus-1": _MODUS, "betriebsmodus-2": "sensor.anders"})
    fake = _FakeHa({_MODUS: ("heating", None), "sensor.anders": ("standby", None)})
    assert await _meldungen(db, anlage, monkeypatch, fake) == []


async def test_meldet_den_unbekannten_wert_mit_der_werte_liste(db, monkeypatch):
    """Matheks Slug `heating` (Prioritäts-Template-Sensor, #433) — der gemeldete Fall."""
    anlage, inv = await _anlage_mit_modus(db)
    ergebnisse = await _meldungen(db, anlage, monkeypatch, _FakeHa({_MODUS: ("heating", None)}))

    assert len(ergebnisse) == 1, [e.meldung for e in ergebnisse]
    e = ergebnisse[0]
    assert (e.kategorie, e.schwere, e.investition_id, e.link) == (_KAT, "info", inv.id, LINK_DATENQUELLEN)
    assert "„heating“" in e.meldung and "Nibe S1255" in e.meldung
    assert _MODUS in e.details
    assert betriebsmodus_werte_klartext() in e.details, "die Liste kommt aus dem Kanon"
    assert "nicht aufgeteilt" in e.details and "Weg B" in e.details
    assert e.action_kind is None, "kein Reparatur-Knopf"


async def test_eine_quelle_an_zwei_geraeten_meldet_je_geraet(db, monkeypatch):
    anlage, _ = await _anlage_mit_modus(db, zweite=True)
    fake = _FakeHa({_MODUS: ("standby", None)})
    ergebnisse = await _meldungen(db, anlage, monkeypatch, fake)

    assert sorted(e.meldung.split("“")[0] for e in ergebnisse) == ["„Nibe S1255", "„Zweit-WP"]
    assert fake.gefragt == [_MODUS], "eine Entität, ein Abruf"


async def test_check_anlage_fuehrt_die_pruefung(db, monkeypatch):
    """Verdrahtung: der Befund erscheint im vollen Lauf."""
    anlage, _ = await _anlage_mit_modus(db)
    monkeypatch.setattr(hss, "get_ha_state_service", lambda: _FakeHa({_MODUS: ("pool", None)}))

    result = await DatenChecker(db).check_anlage(anlage.id)

    assert [e.kategorie for e in result.ergebnisse].count(_KAT) == 1
