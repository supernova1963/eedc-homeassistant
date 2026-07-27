"""
SoT-Helper für Investitions-Werte mit Spalten/Parameter-Fallback.

Hintergrund #229 (JanKgh, SolarEdge-Multi-String-Setup):
Manche Investitions-Felder existieren sowohl als eigene Tabellen-Spalte
(z.B. `Investition.leistung_kwp`) als auch potenziell als Schlüssel im
`parameter`-JSON. Die Spalte ist Source of Truth — wenn die Verteilungs-
Helper aber nur `parameter[key]` lesen, finden sie bei Spalten-gepflegten
Anlagen 0 vor und fallen auf Gleichverteilung zurück (1/N je Modul statt
anteilig nach Modulleistung).

Regel: Spalte hat Vorrang. Parameter-JSON nur als Fallback für Felder
ohne dedizierte Spalte oder für Legacy-Datensätze.

Folgt Memory `feedback_aggregations_drift.md`: bei Drift an mehreren
Read-Sites zentraler Helper statt Einzel-Patch.
"""

from __future__ import annotations

from typing import Any


_COLUMN_FOR_PARAM: dict[str, str] = {
    # parameter-key → Investition-Spalten-Attribut
    # (Schlüssel-SoT: `core/investition_parameter.py`; hier bewusst als Literal,
    # damit `utils/` importfrei bleibt und `core/` weiter auf `utils/` zeigen
    # darf statt umgekehrt.)
    "leistung_kwp": "leistung_kwp",
    # weitere wenn Spalten hinzukommen (kapazitaet_kwh ist aktuell nur im
    # parameter-JSON, daher hier nicht gemappt)
}

# 0-Semantik (N-C) — Felder, bei denen ein Spaltenwert von exakt 0 „nicht
# gepflegt" bedeutet und der parameter-Fallback deshalb greifen MUSS.
#
# Bewusste, feldweise Ausnahme von der Projektregel „0-Werte mit `is not None`
# prüfen": die Regel schützt echte Messgrößen, bei denen 0 eine Aussage ist
# (0 kWh Verbrauch). Eine Nennleistung von 0 kWp ist keine Aussage. Vorher
# lieferten die beiden SoT-Helper für dieselbe Investition (Spalte 0.0,
# `parameter["leistung_kwp"] = 8.4`) verschiedene Zahlen: `get_pv_kwp` 8.4,
# `get_inv_value` 0.0. Der Durchfall kann nur gewinnen — er ersetzt eine 0
# durch eine echte Zahl oder liefert dieselbe 0. Begründung im Original:
# `core/investition_kennwerte.py::get_pv_kwp`.
#
# Generisch (`is not None`) bleibt es für jedes andere Feld — kämen Spalten
# hinzu, bei denen 0 ein gültiger Wert ist, wäre ein pauschaler Falsy-Check
# genau die Falle, die die Projektregel meint.
_NULL_SPALTE_IST_UNGEPFLEGT: frozenset[str] = frozenset({"leistung_kwp"})


def get_inv_value(inv: Any, key: str, default: float = 0.0) -> float:
    """Liest einen numerischen Investitions-Wert mit Spalten/Parameter-Fallback.

    Reihenfolge:
      1. Tabellen-Spalte (falls für `key` gemappt) — bei Feldern aus
         `_NULL_SPALTE_IST_UNGEPFLEGT` zählt ein Spaltenwert von 0 als „fehlt"
      2. parameter-JSON
      3. default
    """
    column_attr = _COLUMN_FOR_PARAM.get(key)
    if column_attr is not None:
        val = getattr(inv, column_attr, None)
        if val is not None and not (key in _NULL_SPALTE_IST_UNGEPFLEGT and not val):
            return val
    return (inv.parameter or {}).get(key, default) or default
