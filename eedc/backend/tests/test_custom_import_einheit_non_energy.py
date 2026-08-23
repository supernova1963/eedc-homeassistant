"""
Akzeptanztest: Custom-Import-Einheit-Konvertierung greift nicht auf
Nicht-Energie-Felder (km, Ladevorgänge, €) — #229 JanKgh-Folge.

Hintergrund: `_convert_unit(value, einheit)` dividiert/multipliziert je
nach `einheit`-Setting (Wh/MWh ↔ kWh). Vor dem Fix lief jeder gemappte
Wert durch diese Konvertierung, auch wenn das Target gar keine Energie-
Größe war. Folge bei JanKgh-Setup (SolarEdge mit `einheit="wh"`):
234 km wurden zu 0,234 km gerechnet → in der UI als „0" angezeigt.

Self-contained:

    eedc/backend/venv/bin/python -m pytest \\
        eedc/backend/tests/test_custom_import_einheit_non_energy.py
"""

from __future__ import annotations

from backend.api.routes.custom_import._shared import (
    FieldMapping, MappingConfig, _is_energy_target, _maybe_convert,
)
from backend.api.routes.custom_import.preview import _apply_mapping


# ─── Helper-Logik ─────────────────────────────────────────────────────────

def test_is_energy_target_top_level_energie():
    assert _is_energy_target("pv_erzeugung_kwh") is True
    assert _is_energy_target("einspeisung_kwh") is True
    assert _is_energy_target("batterie_ladung_kwh") is True
    assert _is_energy_target("wallbox_ladung_kwh") is True


def test_is_energy_target_top_level_nicht_energie():
    assert _is_energy_target("eauto_km_gefahren") is False
    assert _is_energy_target("wallbox_ladevorgaenge") is False
    assert _is_energy_target("jahr") is False
    assert _is_energy_target("monat") is False


def test_is_energy_target_inv_kwh_feld():
    # inv:<id>:<feld_name> mit Energie-Einheit
    assert _is_energy_target("inv:5:pv_erzeugung_kwh") is True
    assert _is_energy_target("inv:7:ladung_pv_kwh") is True
    assert _is_energy_target("inv:9:stromverbrauch_kwh") is True


def test_is_energy_target_inv_nicht_energie():
    assert _is_energy_target("inv:5:km_gefahren") is False
    assert _is_energy_target("inv:7:ladevorgaenge") is False
    assert _is_energy_target("inv:5:ladung_extern_euro") is False


def test_maybe_convert_lasst_km_unveraendert_bei_wh():
    # Genau der JanKgh-Fall: 234 km, einheit="wh"
    assert _maybe_convert(234.0, "wh", "eauto_km_gefahren") == 234.0
    assert _maybe_convert(234.0, "wh", "inv:5:km_gefahren") == 234.0


def test_maybe_convert_konvertiert_kwh_bei_wh():
    # Energie-Pfad: 1000 Wh → 1 kWh
    assert _maybe_convert(1000.0, "wh", "pv_erzeugung_kwh") == 1.0
    assert _maybe_convert(1000.0, "wh", "inv:5:pv_erzeugung_kwh") == 1.0


def test_maybe_convert_runden_bei_kwh():
    assert _maybe_convert(234.567, "kwh", "eauto_km_gefahren") == 234.57


# ─── Integration: preview path mit JanKgh-Setup ───────────────────────────

def _mapping(spalten: dict[str, str], einheit: str = "wh") -> MappingConfig:
    return MappingConfig(
        mappings=[FieldMapping(spalte=s, eedc_feld=f) for s, f in spalten.items()],
        einheit=einheit,
        dezimalzeichen="auto",
    )


def test_preview_km_mit_wh_einheit_bleibt_korrekt():
    """JanKgh-Szenario: einheit=wh (für seine SolarEdge-kWh-Spalten),
    km-Spalte darf NICHT durch 1000 dividiert werden."""
    headers = ["Jahr", "Monat", "fiat500-km", "fiat500-verbrauch"]
    rows = [
        {"Jahr": "2024", "Monat": "3", "fiat500-km": "234", "fiat500-verbrauch": "1500"},
    ]
    config = _mapping({
        "Jahr": "jahr", "Monat": "monat",
        "fiat500-km": "eauto_km_gefahren",
        "fiat500-verbrauch": "pv_erzeugung_kwh",
    }, einheit="wh")

    monate, _warn, _inv = _apply_mapping(headers, rows, config, set())

    assert len(monate) == 1
    m = monate[0]
    # km muss original bleiben — kein Wh-zu-kWh-Drift
    assert m.eauto_km_gefahren == 234.0, f"km muss 234 bleiben, war {m.eauto_km_gefahren}"
    # Vergleich: kWh-Feld wird korrekt konvertiert (1500 Wh → 1.5 kWh)
    assert m.pv_erzeugung_kwh == 1.5, f"Energie-Feld konvertiert, war {m.pv_erzeugung_kwh}"


def test_preview_km_mit_kwh_einheit_unveraendert():
    """Sanity: einheit=kwh — km bleibt korrekt (Regression-Schutz)."""
    headers = ["Jahr", "Monat", "fiat500-km"]
    rows = [{"Jahr": "2024", "Monat": "3", "fiat500-km": "234"}]
    config = _mapping({
        "Jahr": "jahr", "Monat": "monat",
        "fiat500-km": "eauto_km_gefahren",
    }, einheit="kwh")

    monate, _warn, _inv = _apply_mapping(headers, rows, config, set())
    assert monate[0].eauto_km_gefahren == 234.0
