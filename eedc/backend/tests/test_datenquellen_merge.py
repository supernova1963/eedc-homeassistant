"""Unit-Tests für den extrahierten Datenquellen-Prioritizer (ADR-001).

Spur A des Backend-Refactoring-Plans: die Merge-/Präzedenz-Logik aus
get_aktueller_monat wurde nach core/berechnungen/datenquellen.merge_datenquellen
herausgelöst (verhaltensneutral). Diese Unit-Tests prüfen den Helper isoliert
(kein DB/HA) — die End-to-End-Symmetrie bleibt durch
test_aktueller_monat_datenquellen_prioritaet.py abgedeckt.

Werte sind hier einfache Strings statt (float, DatenquelleInfo)-Tupel — der
Helper ist typ-agnostisch über den Wert.
"""

from __future__ import annotations

from backend.core.berechnungen import merge_datenquellen


def test_laufender_monat_praezedenz_ha_stats_gewinnt():
    """saved < connector < mqtt < ha_stats: bei Konkurrenz gewinnt ha_stats."""
    res = merge_datenquellen(
        saved={"x": "saved"},
        connector={"x": "connector"},
        mqtt_energy={"x": "mqtt"},
        ha_stats={"x": "ha"},
        ist_aktueller_monat=True,
    )
    assert res["x"] == "ha"


def test_laufender_monat_connector_ohne_hoehere_quellen():
    res = merge_datenquellen(
        saved={"x": "saved"},
        connector={"x": "connector"},
        mqtt_energy={},
        ha_stats={},
        ist_aktueller_monat=True,
    )
    assert res["x"] == "connector"


def test_vergangener_monat_setdefault_kein_override():
    """Abgeschlossener Monat: connector/ha_stats überschreiben saved NICHT."""
    res = merge_datenquellen(
        saved={"x": "saved"},
        connector={"x": "connector"},
        mqtt_energy={},  # für vergangene Monate vom Aufrufer leer
        ha_stats={"x": "ha"},
        ist_aktueller_monat=False,
    )
    assert res["x"] == "saved"


def test_vergangener_monat_fuellt_fehlende_felder():
    """Setdefault füllt Felder, die saved nicht hat (connector vor ha_stats)."""
    res = merge_datenquellen(
        saved={"a": "saved"},
        connector={"b": "connector"},
        mqtt_energy={},
        ha_stats={"b": "ha", "c": "ha"},
        ist_aktueller_monat=False,
    )
    assert res["a"] == "saved"
    assert res["b"] == "connector"  # connector kommt vor ha_stats → gewinnt das setdefault
    assert res["c"] == "ha"


def test_disjunkte_quellen_werden_vereinigt():
    res = merge_datenquellen(
        saved={"a": "s"},
        connector={"b": "c"},
        mqtt_energy={"d": "m"},
        ha_stats={"e": "h"},
        ist_aktueller_monat=True,
    )
    assert res == {"a": "s", "b": "c", "d": "m", "e": "h"}


def test_eingaben_werden_nicht_mutiert():
    saved = {"x": "saved"}
    connector = {"x": "connector"}
    merge_datenquellen(
        saved=saved, connector=connector, mqtt_energy={}, ha_stats={},
        ist_aktueller_monat=True,
    )
    assert saved == {"x": "saved"}
    assert connector == {"x": "connector"}
