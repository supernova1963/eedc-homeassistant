"""P-433-2 S2 / E3 (Datenquellen Variante C, #431, 24.10.2026) — Betriebsart je Wärmepumpen-Feld.

**Registry (Gruppe 0):** jedes Feld der Wärmepumpe (kWh und Live) trägt genau eine `betriebsart` aus
`WP_BETRIEBSARTEN`; die Kühl-/Kältemengen-Felder gehören zu `kuehlen`. Die Mengenart (Strom ⇔ Wärme)
wird aus dem bestehenden Thermisch-SoT abgeleitet, nicht getippt.

**Route:** `/datenquellen/{id}/felder` reicht `betriebsart` und `menge` je Feld durch, je Wärmepumpe das
Stammdatum `kuehlung_art` und die aus dem Modus ableitbaren Betriebsarten. Für andere Typen bleibt die
Antwort, wie sie war (nur die zwei neuen Feldschlüssel mit ``None``) — der Hub-Block «Einstellungen →
Zuordnungen» liest dieselbe Antwort.

**Fälle über die Route** (Bauplan §3 E3 «Proben»): luft_wasser · luft_luft · brauchwasser · Sole passiv
ohne Kühlfeld · Mathek (getrennt, passiv) · pipp086 (Betriebsart-Zähler Heizen) · Betriebsmodus-Sensor ·
MartyBr (Kühl-Leistung ohne Stammdatum).
Ihre Projektion steht als Fixture in `frontend/src/test/datenquellen-wp-faelle.json`; die Client-Probe
`DatenquellenZuordnung.betriebsart.test.tsx` bildet daraus die Blöcke. **Diese Datei hält die Fixture
am Code:** weicht die Route ab, ist `test_fixture_der_client_probe_ist_aktuell` rot. Neu schreiben:

    cd eedc && EEDC_DQ_WP_FIXTURE=schreiben python -m pytest backend/tests/test_p433_2_datenquellen_betriebsart.py -q

Der HA-Zugriff ist der einzige gemockte Teil.

Schwesterdateien: test_p433_0_betriebsmodus_werte.py (Werte-Liste am Feld „Betriebsmodus“ derselben Route),
test_datenquellen_speicher_felder.py, test_thermische_felder_benennen_ihre_groesse.py.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from backend.api.routes import datenquellen as dq_modul
from backend.api.routes.datenquellen import get_datenquellen_felder
from backend.core.betriebsmodus import AUFGETEILTE_MODI, BETRIEBSART_NUTZENERGIE_FELD, BETRIEBSART_STROM_FELD, MESSBARE_MODI
from backend.core.field_definitions import (
    INVESTITION_FELDER,
    LIVE_FELDER_INV,
    WP_BETRIEBSARTEN,
    WP_MENGE_STROM,
    WP_MENGE_WAERME,
    _SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG,
    wp_betriebsart,
    wp_menge,
)
from backend.core.investition_parameter import kuehlung_art
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.mqtt_gateway_mapping import MqttGatewayMapping  # noqa: F401

_FIXTURE = Path(__file__).resolve().parents[2] / "frontend" / "src" / "test" / "datenquellen-wp-faelle.json"
_VORRANG = "Betriebsart-Zähler; hat Vorrang vor „Strom Heizen“. Wer getrennt misst, lässt dieses Feld leer."

#: Feldschlüssel der Antwort am HEAD vor E3 (`0edd0cfb`, gemessen 24.10.2026) — als Literal, damit die
#: Probe nicht aus dem neuen Code abgeleitet ist.
_FELD_SCHLUESSEL_VORHER = {
    "ausgewertet_in", "bedarf", "bedarf_grund", "bedarf_text", "einheit", "erweitert", "feld",
    "gateway_topic", "ha_entity", "ha_name", "hinweis", "id", "invertieren", "kategorie", "label",
    "nur_ha", "probleme", "quelle", "standard_topic", "typ", "wert", "wert_klartext", "wert_text",
    "wert_zeit", "zulaessige_werte", "zustand",
}
_GRUPPEN_SCHLUESSEL_VORHER = {"felder", "id", "titel", "typ"}


# ═══ Registry ════════════════════════════════════════════════════════════════

def _wp_felder() -> list[tuple[str, dict]]:
    return [(f["feld"], f) for f in INVESTITION_FELDER["waermepumpe"]] + [
        (f["key"], f) for f in LIVE_FELDER_INV["waermepumpe"]
    ]


def test_jedes_wp_feld_traegt_genau_eine_betriebsart():
    offen = [k for k, f in _wp_felder() if not isinstance(f.get("betriebsart"), str)]
    fremd = [k for k, f in _wp_felder() if f.get("betriebsart") not in WP_BETRIEBSARTEN]
    assert offen == [] and fremd == [], f"ohne Betriebsart: {offen}; unbekannte Betriebsart: {fremd}"
    assert len({k for k, _ in _wp_felder()}) == len(_wp_felder()), "ein Feld-Key, eine Zeile"


def test_kuehl_und_kaeltemengen_felder_gehoeren_zum_kuehlen():
    """Erhoben am Key (`kuehl`/`kaelte`), nicht aus einer Liste: 3 Felder am 24.10.2026."""
    kuehl = sorted(k for k, _ in _wp_felder() if "kuehl" in k or "kaelte" in k)
    assert kuehl == ["betriebsart_nutzenergie_kuehlen_kwh", "betriebsart_strom_kuehlen_kwh", "leistung_kuehlen_w"]
    assert {wp_betriebsart(k) for k in kuehl} == {"kuehlen"}


def test_betriebsart_felder_folgen_dem_kanon():
    for modus in MESSBARE_MODI:
        assert wp_betriebsart(BETRIEBSART_STROM_FELD[modus]) == modus
        assert wp_betriebsart(BETRIEBSART_NUTZENERGIE_FELD[modus]) == modus
    # Innengeräte-Suffix (#263) löst über `basis_feld_key` auf.
    assert wp_betriebsart("betriebsart_strom_kuehlen_kwh-3") == "kuehlen"
    assert wp_betriebsart("ladung_kwh") is None


def test_mengenart_folgt_dem_thermisch_sot():
    for k, f in _wp_felder():
        if f.get("einheit") != "kWh":
            assert wp_menge(k) is None, k
            continue
        thermisch = "thermisch" in _SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG.get(("waermepumpe", k), "").lower()
        assert wp_menge(k) == (WP_MENGE_WAERME if thermisch else WP_MENGE_STROM), k
    assert wp_menge("heizenergie_kwh") == WP_MENGE_WAERME
    assert wp_menge("stromverbrauch_kwh") == WP_MENGE_STROM


def test_vorrang_hinweis_nur_am_betriebsart_zaehler_heizen():
    hinweise = {f["feld"]: f["hinweis"] for f in INVESTITION_FELDER["waermepumpe"]}
    assert hinweise[BETRIEBSART_STROM_FELD["heizen"]].startswith(_VORRANG)
    andere = [k for k, h in hinweise.items() if _VORRANG in h and k != BETRIEBSART_STROM_FELD["heizen"]]
    assert andere == []


@pytest.mark.parametrize("wert,erwartet", [
    ({"kuehlung_art": "passiv"}, "passiv"), ({"kuehlung_art": " Aktiv "}, "aktiv"),
    ({"kuehlung_art": "keine"}, "keine"), ({}, "keine"), ({"kuehlung_art": "quatsch"}, "keine"), (None, "keine"),
])
def test_kuehlung_art_ist_ein_stammdatum_mit_vorgabe(wert, erwartet):
    assert kuehlung_art(wert) == erwartet


# ═══ Route — die Fälle ═══════════════════════════════════════════════════════

_E = "sensor."

#: Fall → (Parameter, zugeordnete Felder). Ein zugeordnetes Feld bekommt einen HA-Sensor mit Wert.
FAELLE: dict[str, tuple[dict, tuple[str, ...]]] = {
    "luft_wasser": ({"wp_art": "luft_wasser"}, ()),
    "luft_luft": ({"wp_art": "luft_luft"}, ()),
    "brauchwasser": ({"wp_art": "brauchwasser"}, ()),
    "sole_passiv_ohne_kuehlfeld": (
        {"wp_art": "sole_wasser", "kuehlung_art": "passiv"}, ("stromverbrauch_kwh", "heizenergie_kwh"),
    ),
    "mathek": (
        {"wp_art": "sole_wasser", "kuehlung_art": "passiv", "getrennte_strommessung": True},
        ("strom_heizen_kwh", "strom_warmwasser_kwh", "heizenergie_kwh", "warmwasser_kwh",
         "warmwasser_temperatur_c", "leistung_w"),
    ),
    "pipp086": ({"wp_art": "luft_wasser"}, ("stromverbrauch_kwh", "betriebsart_strom_heizen_kwh")),
    "betriebsmodus": (
        {"wp_art": "luft_wasser", "kuehlung_art": "aktiv"}, ("stromverbrauch_kwh", "heizenergie_kwh", "betriebsmodus"),
    ),
    "martybr": ({"wp_art": "luft_wasser"}, ("stromverbrauch_kwh", "leistung_kuehlen_w")),
}

#: Was die Client-Probe von einem Feld braucht — ohne IDs (Autoinkrement), Hinweistexte und Werte.
_PROJEKTION = ("feld", "label", "einheit", "kategorie", "zustand", "quelle", "bedarf", "bedarf_text",
               "erweitert", "betriebsart", "menge")


async def _route_fuer(db, monkeypatch, parameter: dict, belegt: tuple[str, ...]) -> dict:
    anlage = Anlage(anlagenname="P433-2", leistung_kwp=10.0, sensor_mapping={})
    db.add(anlage)
    await db.flush()
    inv = Investition(anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Wärmepumpe", parameter=parameter)
    db.add(inv)
    await db.flush()
    quellen, live = {}, {}
    for feld in belegt:
        art = "inv_live" if not feld.endswith("_kwh") else "inv_energy"
        quellen[f"{art}_{inv.id}_{feld}"] = {"quelle": "ha_app", "entity_id": f"{_E}{feld}"}
        if art == "inv_live":
            live[feld] = f"{_E}{feld}"
    anlage.sensor_mapping = {"quellen": quellen, "investitionen": {str(inv.id): {"live": live}}}
    db.add(anlage)
    await db.flush()

    async def _fake_detail(_db, entity_ids):
        return {
            eid: {"wert": None if eid.endswith("betriebsmodus") else 1.0,
                  "wert_text": "heat" if eid.endswith("betriebsmodus") else None,
                  "einheit": None, "state_class": None, "friendly_name": eid}
            for eid in entity_ids
        }

    monkeypatch.setattr(dq_modul, "_ha_states_detail", _fake_detail)
    return await get_datenquellen_felder(anlage.id, db)


def _wp_gruppe(resp: dict) -> dict:
    (g,) = [g for g in resp["gruppen"] if g["typ"] == "waermepumpe"]
    return g


def _projektion(g: dict) -> dict:
    return {
        "titel": g["titel"],
        "kuehlung_art": g["kuehlung_art"],
        "modus_ableitbar": g["modus_ableitbar"],
        "felder": [{k: f[k] for k in _PROJEKTION} for f in g["felder"]],
    }


def _betriebsarten_mit_sichtbarem_feld(g: dict) -> set[str]:
    return {f["betriebsart"] for f in g["felder"] if not f["erweitert"]}


async def test_jedes_wp_feld_der_route_traegt_betriebsart_und_menge(db, monkeypatch):
    for name, (param, belegt) in FAELLE.items():
        g = _wp_gruppe(await _route_fuer(db, monkeypatch, param, belegt))
        assert all(f["betriebsart"] in WP_BETRIEBSARTEN for f in g["felder"]), name
        assert all((f["menge"] is not None) == (f["einheit"] == "kWh") for f in g["felder"]), name
        assert g["modus_ableitbar"] == sorted(AUFGETEILTE_MODI)


async def test_betriebsarten_folgen_der_registry_je_bauart(db, monkeypatch):
    """Welche Betriebsarten ein Feld in der ersten Reihe haben — die Registry (`bedingung`/`weich`) entscheidet.

    Nacharbeit H1 (Master 24.10.2026): die Live-Felder tragen dieselben weichen Bedingungen wie ihre
    kWh-Geschwister (Leistung Heizen `!brauchwasser`, Leistung/Temperatur Warmwasser `!luft_luft`), und die
    Kühl-Felder folgen der Funktion `kuehlt` (Klimagerät oder `kuehlung_art`). Damit gilt: luft_wasser ohne
    Kühlung hat keinen Kühlen-Block, Brauchwasser keinen Heizen-Block, Luft-Luft keinen Warmwasser-Block,
    Sole passiv einen Kühlen-Block.
    """
    erwartet = {
        "luft_wasser": {"geraet", "heizen", "warmwasser"},
        "luft_luft": {"geraet", "heizen", "kuehlen", "lueften", "entfeuchten"},
        "brauchwasser": {"geraet", "warmwasser"},
        "sole_passiv_ohne_kuehlfeld": {"geraet", "heizen", "warmwasser", "kuehlen"},
        "betriebsmodus": {"geraet", "heizen", "warmwasser", "kuehlen"},
    }
    for name, sichtbar in erwartet.items():
        param, belegt = FAELLE[name]
        g = _wp_gruppe(await _route_fuer(db, monkeypatch, param, belegt))
        assert _betriebsarten_mit_sichtbarem_feld(g) == sichtbar, name


async def test_martybr_kuehl_leistung_ohne_stammdatum_bleibt_oben_weil_zugeordnet(db, monkeypatch):
    """Luft-Wasser-WP ohne `kuehlung_art`, aber mit zugeordneter Kühl-Leistung (MartyBr, T89667 #200):
    die Zuordnung hebt das Feld in die erste Reihe, die Kühl-Zähler bleiben unter «Weitere Größen»."""
    param, belegt = FAELLE["martybr"]
    g = _wp_gruppe(await _route_fuer(db, monkeypatch, param, belegt))
    felder = {f["feld"]: f for f in g["felder"]}
    assert (felder["leistung_kuehlen_w"]["erweitert"], felder["leistung_kuehlen_w"]["quelle"]) == (False, "ha_app")
    assert felder["betriebsart_strom_kuehlen_kwh"]["erweitert"] is True
    assert "kuehlen" in _betriebsarten_mit_sichtbarem_feld(g)
    # Gegenprobe: ohne Zuordnung steht dasselbe Feld unter «Weitere Größen».
    g0 = _wp_gruppe(await _route_fuer(db, monkeypatch, param, ()))
    assert {f["feld"]: f for f in g0["felder"]}["leistung_kuehlen_w"]["erweitert"] is True


def test_kuehlt_ist_klimageraet_oder_stammdatum():
    from backend.core.field_definitions import _bedingungs_werte

    assert _bedingungs_werte({"wp_art": "luft_luft"})["kuehlt"] is True
    assert _bedingungs_werte({"wp_art": "sole_wasser", "kuehlung_art": "passiv"})["kuehlt"] is True
    assert _bedingungs_werte({"wp_art": "luft_wasser", "kuehlung_art": "aktiv"})["kuehlt"] is True
    assert _bedingungs_werte({"wp_art": "luft_wasser"})["kuehlt"] is False
    assert _bedingungs_werte({"wp_art": "luft_wasser", "kuehlung_art": "keine"})["kuehlt"] is False


def test_neue_bedingungen_sind_alle_weich():
    """Die Nacharbeit H1 nimmt nie ein Feld weg: jede Bedingung der vier Live-Felder und der Kühl-Zähler
    ist weich (Urteil höchstens «erweitert», also nie Pflicht und im Lesepfad vorhanden)."""
    from backend.core.field_definitions import URTEIL_NEIN, _bedingungs_werte, bedingungs_urteil

    betroffen = [f for _, f in _wp_felder()
                 if (f.get("feld") or f.get("key")) in {
                     "leistung_heizen_w", "leistung_warmwasser_w", "warmwasser_temperatur_c", "leistung_kuehlen_w",
                     "betriebsart_strom_kuehlen_kwh", "betriebsart_nutzenergie_kuehlen_kwh"}]
    assert len(betroffen) == 6
    for f in betroffen:
        for art in ("luft_wasser", "sole_wasser", "grundwasser", "luft_luft", "brauchwasser"):
            for kuehlung in ("keine", "passiv", "aktiv"):
                w = _bedingungs_werte({"wp_art": art, "kuehlung_art": kuehlung})
                assert bedingungs_urteil(f.get("bedingung"), f.get("weich"), w) != URTEIL_NEIN, (f, art, kuehlung)


async def test_kuehlung_art_reist_je_geraet(db, monkeypatch):
    for name, art in (("luft_wasser", "keine"), ("sole_passiv_ohne_kuehlfeld", "passiv"), ("betriebsmodus", "aktiv")):
        param, belegt = FAELLE[name]
        assert _wp_gruppe(await _route_fuer(db, monkeypatch, param, belegt))["kuehlung_art"] == art, name


async def test_pipp086_betriebsart_zaehler_heizen_steht_vorn_mit_vorrang_hinweis(db, monkeypatch):
    param, belegt = FAELLE["pipp086"]
    g = _wp_gruppe(await _route_fuer(db, monkeypatch, param, belegt))
    (f,) = [f for f in g["felder"] if f["feld"] == "betriebsart_strom_heizen_kwh"]
    assert (f["betriebsart"], f["erweitert"], f["quelle"]) == ("heizen", False, "ha_app")
    assert f["hinweis"].startswith(_VORRANG)


async def test_andere_typen_unveraendert(db, monkeypatch):
    anlage = Anlage(anlagenname="P433-2-andere", leistung_kwp=10.0, sensor_mapping={})
    db.add(anlage)
    await db.flush()
    for typ in ("speicher", "wallbox", "e-auto", "waermepumpe"):
        db.add(Investition(anlage_id=anlage.id, typ=typ, bezeichnung=typ, parameter={}))
    await db.flush()
    resp = await get_datenquellen_felder(anlage.id, db)
    for g in resp["gruppen"]:
        neu = {"kuehlung_art", "modus_ableitbar"} if g["typ"] == "waermepumpe" else set()
        assert set(g) == _GRUPPEN_SCHLUESSEL_VORHER | neu, g["typ"]
        for f in g["felder"]:
            assert set(f) == _FELD_SCHLUESSEL_VORHER | {"betriebsart", "menge"}, f["feld"]
            if g["typ"] != "waermepumpe":
                assert f["betriebsart"] is None and f["menge"] is None, f["feld"]


async def test_fixture_der_client_probe_ist_aktuell(db, monkeypatch):
    ist = {}
    for name, (param, belegt) in FAELLE.items():
        ist[name] = _projektion(_wp_gruppe(await _route_fuer(db, monkeypatch, param, belegt)))
    text = json.dumps(ist, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if os.environ.get("EEDC_DQ_WP_FIXTURE") == "schreiben":
        _FIXTURE.write_text(text, encoding="utf-8")
    assert _FIXTURE.exists(), f"Fixture fehlt: {_FIXTURE} — Befehl im Docstring"
    assert _FIXTURE.read_text(encoding="utf-8") == text, (
        "Die Route liefert für die WP-Fälle etwas anderes als die Fixture der Client-Probe — "
        "absichtlich? Dann neu schreiben (Docstring) und den Diff mitschicken."
    )
