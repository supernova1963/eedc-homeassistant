"""
Akzeptanztest für #222 NongJoWo — Vorschau zeigt Investitions-Spalten als
zusätzliche Tabellen-Spalten (inv_werte pro Monat, inv_spalten in Response).

Self-contained Standalone-Script:

    eedc/backend/venv/bin/python eedc/backend/tests/test_custom_import_preview_inv_werte.py

Hintergrund: Vor dem Fix zeigte die Custom-Import-Vorschau für reine
E-Auto-/Wallbox-Imports eine leere Tabelle (alle "—"), obwohl der Apply
die Daten sauber landete. Banner sagte "Werte in der Vorschau-Tabelle
nicht sichtbar" — User-Vertrauen weg. Jetzt: inv_werte werden gefüllt,
inv_spalten in Response liefert die Header.

Geprüft:
  1. Auto-erkannte Spalten (NongJoWo-Fall) landen in inv_werte
  2. Manuell `inv:`-gemappte Spalten landen ebenfalls in inv_werte
  3. inv_spalten enthält nur Spalten, die in mind. einer Zeile einen Wert hatten
  4. inv_spalten ist sortiert (stabile UI-Reihenfolge)
  5. Bei Mischung manuell + auto: keine Doppelung, manuelles Mapping gewinnt
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # eedc/
sys.path.insert(0, str(_BACKEND_ROOT))

from backend.api.routes.custom_import._shared import FieldMapping, MappingConfig  # noqa: E402
from backend.api.routes.custom_import.preview import _apply_mapping  # noqa: E402


def _mapping(spalten: dict[str, str]) -> MappingConfig:
    return MappingConfig(
        mappings=[FieldMapping(spalte=s, eedc_feld=f) for s, f in spalten.items()],
        einheit="kwh",
        dezimalzeichen="komma",
    )


def test_auto_erkannte_spalten_landen_in_inv_werte():
    """#222-Hauptfall: NongJoWo-CSV nur Jahr/Monat im Mapping + 2 Auto-Spalten."""
    headers = ["Jahr", "Monat", "Wollis_ID5_Ladung_PV_kWh", "Wollis_ID5_Ladung_Netz_kWh"]
    rows = [
        {"Jahr": "2024", "Monat": "3",
         "Wollis_ID5_Ladung_PV_kWh": "94,71735445",
         "Wollis_ID5_Ladung_Netz_kWh": "95,81364555"},
        {"Jahr": "2024", "Monat": "4",
         "Wollis_ID5_Ladung_PV_kWh": "161,7951978",
         "Wollis_ID5_Ladung_Netz_kWh": "136,5118022"},
    ]
    config = _mapping({"Jahr": "jahr", "Monat": "monat"})
    auto = {"Wollis_ID5_Ladung_PV_kWh", "Wollis_ID5_Ladung_Netz_kWh"}

    monate, _warn, inv_spalten = _apply_mapping(headers, rows, config, auto)

    assert len(monate) == 2, f"erwartet 2 Monate, war {len(monate)}"
    # _convert_unit rundet bestandsgemäß auf 2 Nachkommastellen — Wert kommt aus dem
    # existierenden Pfad, nicht aus diesem Test.
    assert monate[0].inv_werte.get("Wollis_ID5_Ladung_PV_kWh") == 94.72
    assert monate[0].inv_werte["Wollis_ID5_Ladung_Netz_kWh"] == 95.81
    assert monate[1].inv_werte["Wollis_ID5_Ladung_PV_kWh"] == 161.80
    # inv_spalten sortiert
    assert inv_spalten == [
        "Wollis_ID5_Ladung_Netz_kWh",
        "Wollis_ID5_Ladung_PV_kWh",
    ], f"inv_spalten sortiert erwartet, war {inv_spalten}"


def test_manuell_inv_gemappte_spalten_landen_in_inv_werte():
    """Spalten auf `inv:5:ladung_pv_kwh` gemappt → in inv_werte mit CSV-Spaltennamen."""
    headers = ["Jahr", "Monat", "PV_Ladung", "Netz_Ladung"]
    rows = [
        {"Jahr": "2025", "Monat": "1", "PV_Ladung": "50,5", "Netz_Ladung": "20,2"},
    ]
    config = _mapping({
        "Jahr": "jahr",
        "Monat": "monat",
        "PV_Ladung": "inv:5:ladung_pv_kwh",
        "Netz_Ladung": "inv:5:ladung_netz_kwh",
    })

    monate, _warn, inv_spalten = _apply_mapping(headers, rows, config, set())

    assert len(monate) == 1
    assert abs(monate[0].inv_werte["PV_Ladung"] - 50.5) < 1e-6
    assert abs(monate[0].inv_werte["Netz_Ladung"] - 20.2) < 1e-6
    assert inv_spalten == ["Netz_Ladung", "PV_Ladung"]


def test_leere_inv_spalten_landen_nicht_in_response():
    """Auto-erkannte Spalte ist gemappt, aber Zeilen sind leer → nicht in inv_spalten."""
    headers = ["Jahr", "Monat", "Leerspalte", "Wert"]
    rows = [
        {"Jahr": "2025", "Monat": "1", "Leerspalte": "", "Wert": "10,0"},
        {"Jahr": "2025", "Monat": "2", "Leerspalte": "", "Wert": "20,0"},
    ]
    config = _mapping({"Jahr": "jahr", "Monat": "monat"})
    auto = {"Leerspalte", "Wert"}

    monate, _warn, inv_spalten = _apply_mapping(headers, rows, config, auto)

    assert len(monate) == 2
    assert "Leerspalte" not in inv_spalten, (
        f"Leere Spalte darf nicht in Header, war {inv_spalten}"
    )
    assert "Wert" in inv_spalten


def test_mischung_manuell_und_auto_keine_doppelung():
    """Wenn dieselbe CSV-Spalte manuell `inv:` UND auto-erkannt ist, manuelles Mapping gewinnt."""
    headers = ["Jahr", "Monat", "DoppelSpalte"]
    rows = [
        {"Jahr": "2025", "Monat": "1", "DoppelSpalte": "42,5"},
    ]
    config = _mapping({
        "Jahr": "jahr",
        "Monat": "monat",
        "DoppelSpalte": "inv:7:ladung_kwh",
    })
    auto = {"DoppelSpalte"}  # zusätzlich als auto markiert

    monate, _warn, inv_spalten = _apply_mapping(headers, rows, config, auto)

    assert len(monate) == 1
    # Wert nur einmal, nicht verdoppelt
    assert abs(monate[0].inv_werte["DoppelSpalte"] - 42.5) < 1e-6
    assert inv_spalten == ["DoppelSpalte"]


def test_globale_und_inv_spalten_gemischt():
    """PV-Spalte normal gemappt + Wollis-Spalten auto erkannt → beide in Vorschau."""
    headers = ["Jahr", "Monat", "PV_kWh", "Wollis_Ladung"]
    rows = [
        {"Jahr": "2025", "Monat": "5", "PV_kWh": "500,0", "Wollis_Ladung": "120,5"},
    ]
    config = _mapping({
        "Jahr": "jahr",
        "Monat": "monat",
        "PV_kWh": "pv_erzeugung_kwh",
    })
    auto = {"Wollis_Ladung"}

    monate, _warn, inv_spalten = _apply_mapping(headers, rows, config, auto)

    assert len(monate) == 1
    assert monate[0].pv_erzeugung_kwh == 500.0
    assert abs(monate[0].inv_werte["Wollis_Ladung"] - 120.5) < 1e-6
    assert inv_spalten == ["Wollis_Ladung"]


def _run_all():
    tests = [
        test_auto_erkannte_spalten_landen_in_inv_werte,
        test_manuell_inv_gemappte_spalten_landen_in_inv_werte,
        test_leere_inv_spalten_landen_nicht_in_response,
        test_mischung_manuell_und_auto_keine_doppelung,
        test_globale_und_inv_spalten_gemischt,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
            traceback.print_exc()
    if failed:
        print(f"\n{failed}/{len(tests)} Tests fehlgeschlagen")
        sys.exit(1)
    print(f"\n{len(tests)}/{len(tests)} Tests grün")


if __name__ == "__main__":
    _run_all()
