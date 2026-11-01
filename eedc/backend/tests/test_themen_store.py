"""Themen-Kacheln (4.2.0, Bauplan TH-E1 §1.1/§1.7) — der Store `services/themen_store.py`, die Feld-ID, der Live-Key.

Geprüft wird die Wirkung der reinen Funktionen auf einem `sensor_mapping`-Dict: Kennungen aus **einem** monotonen
Zähler (nie ``max()+1``, Ü10), Entfernen liefert die Feld-IDs der Quellen, Positionen werden geklemmt, Eingaben
getrimmt und begrenzt. Dazu die zwei Kopplungen nach außen: ``inv_thema_`` steht in `INV_FELD_PRAEFIXE` (Sprengsatz
S2 — ohne ihn räumt das Geräte-Löschen nicht und der Import remapped nicht) und `UEBERBLICK_TYPEN` ist der Spiegel
der Frontend-Konstante (Vorbild der Probe: `test_398_betriebsmodus_live.py::test_icons_sind_im_client_registriert`,
die eine Backend-Konstante gegen den Quelltext des Clients liest).

Schwesterdateien: test_themen_routen.py, test_themen_live.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.core.field_definitions import ist_thema_key, ist_zustand_feld
from backend.services import themen_store as store
from backend.services.datenquellen_mapping_sync import INV_FELD_PRAEFIXE, inv_feld_der_investition
from backend.utils.investition_filter import UEBERBLICK_TYPEN


def _mapping() -> dict:
    return {"investitionen": {"7": {"live": {"leistung_w": "sensor.p"}}}, "quellen": {}}


def test_kennungen_kommen_aus_einem_monotonen_zaehler():
    m = _mapping()
    t1 = store.thema_anlegen(m, 7)
    e1 = store.eintrag_anlegen(m, 7, t1["id"])
    t2 = store.thema_anlegen(m, 7, "Service")
    assert (t1["id"], e1["id"], t2["id"]) == ("t1", "e2", "t3")
    # Entfernen gibt keine Kennung frei — die nächste ist e4, nicht e2 (sonst erbte sie die alte Quelle).
    store.eintrag_entfernen(m, 7, "t1", "e2")
    assert store.eintrag_anlegen(m, 7, "t1")["id"] == "e4"
    assert m["investitionen"]["7"]["themen"]["naechste_id"] == 5
    # Der bestehende Geräte-Teilbaum bleibt unberührt.
    assert m["investitionen"]["7"]["live"] == {"leistung_w": "sensor.p"}


def test_vorgaben_namen_und_labels():
    m = {}
    assert store.thema_anlegen(m, 3)["name"] == "Thema 1"
    assert store.thema_anlegen(m, 3)["name"] == "Thema 2"
    assert store.eintrag_anlegen(m, 3, "t1")["label"] == "Eintrag 1"
    assert store.eintrag_anlegen(m, 3, "t1")["label"] == "Eintrag 2"
    assert store.ist_vorgabe_label("Eintrag 12") and not store.ist_vorgabe_label("Türen")


@pytest.mark.parametrize("name", ["", "   ", "x" * 41])
def test_name_leer_oder_zu_lang_ist_ein_fehler(name):
    with pytest.raises(store.ThemenFehler):
        store.thema_anlegen({}, 1, name)


def test_name_und_label_werden_getrimmt_und_begrenzt():
    m = {}
    assert store.thema_anlegen(m, 1, "  Fahrzeugzustand ")["name"] == "Fahrzeugzustand"
    assert store.eintrag_anlegen(m, 1, "t1", "x" * 60)["label"] == "x" * 60
    with pytest.raises(store.ThemenFehler):
        store.eintrag_anlegen(m, 1, "t1", "x" * 61)
    with pytest.raises(store.ThemenFehler):
        store.eintrag_umbenennen(m, 1, "t1", "e2", " ")


def test_positionen_werden_geklemmt():
    m = {}
    for name in ("A", "B", "C"):
        store.thema_anlegen(m, 1, name)
    store.thema_verschieben(m, 1, "t3", -5)
    assert [t["name"] for t in store.lade_themen(m, 1)["liste"]] == ["C", "A", "B"]
    store.thema_verschieben(m, 1, "t3", 99)
    assert [t["name"] for t in store.lade_themen(m, 1)["liste"]] == ["A", "B", "C"]
    for label in ("x", "y", "z"):
        store.eintrag_anlegen(m, 1, "t1", label)
    store.eintrag_verschieben(m, 1, "t1", "e6", 0)
    assert [e["label"] for e in store.lade_themen(m, 1)["liste"][0]["eintraege"]] == ["z", "x", "y"]


def test_entfernen_liefert_die_feld_ids():
    m = {}
    store.thema_anlegen(m, 7, "Zustand")
    store.eintrag_anlegen(m, 7, "t1", "Türen")
    store.eintrag_anlegen(m, 7, "t1", "Reifen")
    eintrag, fid = store.eintrag_entfernen(m, 7, "t1", "e2")
    assert (eintrag["label"], fid) == ("Türen", "inv_thema_7_e2")
    thema, fids = store.thema_entfernen(m, 7, "t1")
    assert (thema["name"], fids) == ("Zustand", ["inv_thema_7_e3"])
    assert store.lade_themen(m, 7)["liste"] == []


def test_unbekanntes_thema_oder_eintrag():
    m = {}
    store.thema_anlegen(m, 1)
    with pytest.raises(store.ThemaNichtGefunden):
        store.thema_umbenennen(m, 1, "t9", "x")
    with pytest.raises(store.ThemaNichtGefunden):
        store.eintrag_entfernen(m, 1, "t1", "e9")
    assert store.finde_eintrag(m, 1, "e9") is None


def test_lade_themen_ohne_store_und_mit_beschaedigtem_store():
    assert store.lade_themen({}, 4) == {"naechste_id": 1, "liste": []}
    assert store.lade_themen(None, 4) == {"naechste_id": 1, "liste": []}
    kaputt = {"investitionen": {"4": {"themen": {"liste": [{"id": "t2", "name": "N", "eintraege": [{"id": "e5"}, "x"]}]}}}}
    assert store.lade_themen(kaputt, 4)["liste"] == [{"id": "t2", "name": "N", "eintraege": [{"id": "e5", "label": ""}]}]
    # Ein fehlender Zähler wird einmal aus dem Bestand gebildet — über der höchsten Kennung.
    assert store.eintrag_anlegen(kaputt, 4, "t2")["id"] == "e6"


def test_feld_id_und_topic_key():
    assert store.eintrag_feld_id(7, "e3") == "inv_thema_7_e3"
    assert store.eintrag_von_feld_id("inv_thema_7_e3") == (7, "e3")
    for falsch in ("inv_live_7_e3", "inv_thema_x_e3", "inv_thema_7_t3", "inv_thema_7", None):
        assert store.eintrag_von_feld_id(falsch) is None
    assert store.eintrag_topic_key("e3") == "thema_e3"
    assert ist_thema_key("thema_e3") and not ist_thema_key("thema_") and not ist_thema_key("thema_x1")
    # Ein Themen-Key ist kein Registry-Zustandsfeld (Bauplan §0) — die Weichen nehmen ihn eigens auf.
    assert not ist_zustand_feld("thema_e3")


def test_label_aus_friendly_name_nur_bei_vorgabe():
    m = {}
    store.thema_anlegen(m, 2)
    store.eintrag_anlegen(m, 2, "t1")
    assert store.eintrag_label_setzen_wenn_vorgabe(m, 2, "e2", " Carport Türschloss ")
    assert store.finde_eintrag(m, 2, "e2")[1]["label"] == "Carport Türschloss"
    # Ein eigenes Label bleibt.
    assert not store.eintrag_label_setzen_wenn_vorgabe(m, 2, "e2", "Anderer Name")


def test_kein_wert():
    assert [store.wert_text(x) for x in (None, "", " ", "unknown", "unavailable", " locked ", 0)] == [
        None, None, None, None, None, "locked", "0",
    ]


def test_s2_inv_thema_steht_in_den_feld_praefixen():
    """Sprengsatz S2: ohne den Präfix fänden Geräte-Löschen und Import-Remap die Themen-Quellen nicht."""
    assert "inv_thema_" in INV_FELD_PRAEFIXE
    assert inv_feld_der_investition("inv_thema_7_e3", 7) == "e3"
    assert inv_feld_der_investition("inv_thema_70_e3", 7) is None


def test_ueberblick_typen_spiegel():
    """`UEBERBLICK_TYPEN` (Backend) = `v4/KomponentenTypV4.tsx:UEBERBLICK_TYPEN` (Frontend), als Menge und in Folge."""
    quelle = (Path(__file__).resolve().parents[2] / "frontend/src/v4/KomponentenTypV4.tsx").read_text(encoding="utf-8")
    zeile = quelle.split("export const UEBERBLICK_TYPEN", 1)[1].split("\n", 1)[0]
    assert tuple(re.findall(r"'([^']+)'", zeile)) == UEBERBLICK_TYPEN
