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


def param_zahl(params, key: str, default=None):
    """Zahlenwert eines `parameter`-Felds — „nicht gepflegt" in ALLEN Gestalten ⇒ `default`.

    „Nicht gepflegt" hat drei Gestalten (F-71, rapahl T89667 #253): der fehlende
    Schlüssel, das geleerte Formularfeld (``""`` — seit v4.0.35 der Rückweg aus
    einer gepflegten Zahl) und ein unbrauchbarer Wert aus einem Import. Wer
    stattdessen ``params.get(key, DEFAULT)`` schreibt, bekommt bei den letzten
    beiden den Rohwert und rechnet damit — genau der 500er von N-571
    (Auswertungen → ROI, Cockpit → Aussicht, Komponenten → Speicher).

    **``0`` und ``"0"`` bleiben 0.0** — die Anwesenheit zählt, nicht die Größe
    (F-15/N-188: beim PV-Ladeanteil ist 0 eine Aussage). Deshalb NICHT
    {@link get_inv_value} verwenden: dessen ``or default`` ersetzt die
    gepflegte 0 durch den Default. Bool-Felder (``v2h_faehig``,
    ``arbitrage_faehig``) laufen NICHT über diesen Helfer — dort ist die
    truthy-Lesart (``""`` = False = Default) die richtige.

    ⚠ **Ausnahme-Bauform für Drei-Wege-Stellen** (heute nur
    `aussichten/finanz_prognose._gepflegter_pv_anteil`, N-277/N-354): wo
    „nie gepflegt" (⇒ Default) und „ausdrücklich zurückgenommen" (⇒ fällt aus
    dem Mittel) verschieden wirken, schreibt der Aufrufer
    ``DEFAULT if key not in params else param_zahl(params, key)``.
    """
    if not params:
        return default
    wert = params.get(key)
    if wert is None or isinstance(wert, bool):
        # bool ist in Python eine Zahl (float(True) = 1.0) — ein Bool-Wert in
        # einem Zahlenfeld ist ein Datenfehler, kein Wert.
        return default
    if isinstance(wert, (int, float)):
        # Gepflegte Zahl UNVERÄNDERT durchreichen (int bleibt int): ein
        # `float()` hier würde jeden f-String und jede JSON-Antwort mit dieser
        # Zahl umformatieren („15000 km/Jahr" → „15000.0 km/Jahr") — eine
        # Golden-Master-Drift ohne fachlichen Grund.
        return wert
    try:
        return float(wert)
    except (TypeError, ValueError):
        return default
