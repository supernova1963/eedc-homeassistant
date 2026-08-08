"""Symmetrie-Test M1 (Issue #318): Serien-Selektion des Tagesverlaufs.

Backfill-Pfad (`energie_profil.backfill`) und Live-Chart-Pfad
(`live_tagesverlauf_service`) bauten dieselbe Investitions-Serien-Selektion
zweimal parallel — ohne Symmetrie-Test (S1 umging die Achse). Drift: der
Pool-Dedup (#227, gleiche `leistung_w`-Entity → Wallbox vor E-Auto) lief NUR
im Live-Pfad. Da `aggregate_day` seine `punkte` für den Scheduler aus dem
Live-Pfad und für den Backfill aus dem Backfill-Pfad zieht, konnte derselbe
Tag je Trigger unterschiedliche TEP.komponenten/Peaks erzeugen — gleiche
Aggregator-Asymmetrie-Klasse wie #290/#298.

Fix: gemeinsame Quelle `baue_investitions_serien` (inkl. Pool-Dedup). Diese
Tests pinnen ihr Verhalten + zementieren, dass beide Pfade sie nutzen.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.services.live_sensor_config import baue_investitions_serien


def _inv(inv_id, typ, parameter=None, parent_investition_id=None, bezeichnung="X"):
    return SimpleNamespace(
        id=inv_id, typ=typ, parameter=parameter or {},
        parent_investition_id=parent_investition_id, bezeichnung=bezeichnung,
    )


# ─── Kern-Selektion ─────────────────────────────────────────────────────────

def test_einfache_pv_serie():
    serien, entities = baue_investitions_serien(
        {"3": {"leistung_w": "sensor.pv"}}, {"3": _inv("3", "pv-module")}
    )
    assert [s.key for s in serien] == ["pv_3"]
    assert serien[0].kategorie == "pv"
    assert serien[0].seite == "quelle"
    assert entities == {"pv_3": ["sensor.pv"]}


def test_skip_typ_wechselrichter():
    serien, _ = baue_investitions_serien(
        {"9": {"leistung_w": "sensor.wr"}}, {"9": _inv("9", "wechselrichter")}
    )
    assert serien == []


def test_wp_split_zwei_serien():
    inv = _inv("7", "waermepumpe")
    serien, entities = baue_investitions_serien(
        {"7": {"leistung_heizen_w": "sensor.h", "leistung_warmwasser_w": "sensor.w"}},
        {"7": inv},
    )
    keys = [s.key for s in serien]
    assert keys == ["waermepumpe_7_heizen", "waermepumpe_7_warmwasser"]
    assert {s.suffix for s in serien} == {"heizen", "warmwasser"}
    assert entities["waermepumpe_7_heizen"] == ["sensor.h"]


def test_eauto_parent_skip():
    serien, _ = baue_investitions_serien(
        {"1": {"leistung_w": "sensor.ea"}},
        {"1": _inv("1", "e-auto", parent_investition_id=2)},
    )
    assert serien == []


def test_sonstiges_erzeuger_seite_quelle():
    serien, _ = baue_investitions_serien(
        {"5": {"leistung_w": "sensor.x"}},
        {"5": _inv("5", "sonstiges", parameter={"kategorie": "erzeuger"})},
    )
    assert serien[0].seite == "quelle"


def test_sonstiges_speicher_bidirektional():
    serien, _ = baue_investitions_serien(
        {"5": {"leistung_w": "sensor.x"}},
        {"5": _inv("5", "sonstiges", parameter={"kategorie": "speicher"})},
    )
    assert serien[0].bidirektional is True


# ─── Pool-Dedup (#227) — der M1-Drift, der im Backfill fehlte ────────────────

def test_pool_dedup_wallbox_vor_eauto():
    """Wallbox + E-Auto teilen dieselbe leistung_w-Entity (kein parent-Link):
    nur die Wallbox-Serie überlebt — in BEIDEN Pfaden (jetzt geteilte Quelle)."""
    inv_live = {
        "1": {"leistung_w": "sensor.shared"},  # E-Auto
        "2": {"leistung_w": "sensor.shared"},  # Wallbox
    }
    investitionen = {
        "1": _inv("1", "e-auto"),
        "2": _inv("2", "wallbox"),
    }
    serien, entities = baue_investitions_serien(inv_live, investitionen)
    keys = [s.key for s in serien]
    assert keys == ["wallbox_2"]  # E-Auto dedupliziert
    assert "eauto_1" not in entities
    assert entities["wallbox_2"] == ["sensor.shared"]


def test_wallbox_verdraengt_eauto_auch_bei_getrennten_entities():
    """Getrennte Entities → die Wallbox ist trotzdem die einzige Quelle (#356).

    Bis 2026-08-08 forderte dieser Test hier **beide** Serien („keine Dedup bei
    getrennten Entities") — er beschrieb das Verhalten, nicht eine fachliche
    Absicht. Der Entity-Dedup (#227) greift nur bei geteiltem Sensor, ein
    Fahrzeug mit eigenem Ladeleistungs-Sensor lief deshalb doppelt ins
    `komponenten`-JSON: Anlage 1, 2026-08-06, Zähler 12,00 kWh → `wallbox_2`
    −12,00 **und** `eauto_1` −17,32, beide Sensoren mit Ladung in genau
    denselben fünf Stunden.

    Die Regel ist dieselbe wie auf der Monatsebene
    (`get_emob_heimladung_canonical`): Wallbox vorhanden ⇒ Wallbox ist Quelle.
    """
    inv_live = {
        "1": {"leistung_w": "sensor.ea"},
        "2": {"leistung_w": "sensor.wb"},
    }
    investitionen = {"1": _inv("1", "e-auto"), "2": _inv("2", "wallbox")}
    serien, entities = baue_investitions_serien(inv_live, investitionen)
    assert {s.key for s in serien} == {"wallbox_2"}
    assert "eauto_1" not in entities


def test_eauto_ohne_wallbox_behaelt_seine_serie():
    """Abgrenzung: ohne Wallbox ist das Fahrzeug die Quelle — Steckerlader/
    Schuko, derselbe Zweig wie `get_emob_heimladung_canonical` ohne Heimladung.
    Griffe die Regel auch hier, verlöre diese Anlage ihre Ladung komplett."""
    inv_live = {"1": {"leistung_w": "sensor.ea"}}
    investitionen = {"1": _inv("1", "e-auto")}
    serien, entities = baue_investitions_serien(inv_live, investitionen)
    assert {s.key for s in serien} == {"eauto_1"}
    assert entities["eauto_1"] == ["sensor.ea"]


# ─── Struktureller Wächter: beide Pfade nutzen die geteilte Quelle ──────────

# Der LTS-Serien-Aufbau saß bis 2026-08-01 in `backfill.py`; er liegt jetzt in
# `lts_tagesverlauf.py`, weil auch die Reparatur-Werkbank ihn braucht
# (Forum #89667/72). Der Wächter zeigt auf die Stelle, die die Selektion
# tatsächlich baut — sonst prüfte er eine Datei, die nur noch aufruft.
_LTS_TV = Path(__file__).resolve().parents[1] / "services/energie_profil/lts_tagesverlauf.py"
_LIVE_TV = Path(__file__).resolve().parents[1] / "services/live_tagesverlauf_service.py"
_BACKFILL = Path(__file__).resolve().parents[1] / "services/energie_profil/backfill.py"


def test_beide_pfade_nutzen_geteilte_quelle():
    """Wächter gegen Re-Divergenz: beide Pfade rufen baue_investitions_serien
    und reimplementieren die Selektion nicht inline."""
    for pfad in (_LTS_TV, _LIVE_TV):
        src = pfad.read_text(encoding="utf-8")
        assert "baue_investitions_serien(" in src, f"{pfad.name} nutzt die Quelle nicht"


def test_backfill_baut_keine_eigene_selektion():
    """Der Backfill ruft den LTS-Weg — er darf die Selektion nicht zurückholen."""
    src = _BACKFILL.read_text(encoding="utf-8")
    assert "lade_tagesverlauf_aus_lts" in src
    assert "baue_investitions_serien" not in src


def test_kein_paralleler_pool_dedup_mehr():
    """Der alte Live-spezifische Pool-Dedup (`_serie_priority`) darf nicht
    wieder auftauchen — die Dedup lebt jetzt nur in der geteilten Quelle."""
    for pfad in (_LTS_TV, _LIVE_TV, _BACKFILL):
        src = pfad.read_text(encoding="utf-8")
        assert "_serie_priority" not in src, f"{pfad.name} hat wieder eigenen Pool-Dedup"
