"""Wer den Monatspreis bildet, fährt die volle Kaskade — und wer noch nicht (#412).

Schwesterdateien: `test_aufgeloester_monatspreis_kaskade.py` (die Kaskade),
`test_flex_oe_erreicht_alle_sichten.py` (die Drift, die sie beseitigt hat),
`test_wurzelmuster_konformitaet.py` (dieselbe Wächter-Bauform für P8/P10).

**Wozu dieser Wächter.** `resolve_netzbezug_preis_cent` löst **zwei** Stufen
auf — gepflegt, sonst der übergebene Preis. Seit #412 gibt es vier:
gepflegt → **gemessen** → Zeitfenster → Stamm (`aufgeloester_monatspreis`). Eine
Stelle, die beim alten Helfer bleibt, ist deshalb nicht falsch, aber **blind für
die Messung**: Sie zeigt bei einem dynamischen Tarif ohne Monatsabschluss den
Stammpreis, während die Sicht daneben den gemessenen Ø nennt.

⭐ **Die Liste ist die Restschuld, nicht die Erlaubnis.** Sie wird beim nächsten
Eingriff an der jeweiligen Fläche kleiner — dieselbe Bauform wie
`P10_NOCH_NICHT_MIGRIERT` (ADR-002), die auf 0 gelaufen ist. Wächst sie, ist
eine neue Stelle entstanden, die niemand bemerkt hätte.
"""

from __future__ import annotations

import ast
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_HELFER = "resolve_netzbezug_preis_cent"

#: Stellen, die den **zweistufigen** Helfer noch benutzen — je Eintrag der
#: Grund, warum sie (noch) nicht auf die volle Kaskade gehoben sind.
#:
#: ⚠ Keine davon ist falsch: Der gepflegte Ø erreicht sie alle. Ihnen fehlt
#: allein die **gemessene** Stufe.
KASKADE_NOCH_NICHT: dict[str, str] = {
    # N-712/N-713 (12.10.2026): `aussichten/finanz_rueckblick.py` (E-Auto-Monatspreis im Rückblick) und
    # `investitionen/dashboard_speicher.py` (Speicher-Spread) lesen den Monatspreis jetzt aus den Monats-Fakten
    # (`tarife_der_monate`, volle Kaskade) — beide Einträge sind gestrichen.
    # Einzelne Monatszeile über `GET /monatsdaten/{id}` — liefert die Rohwerte
    # der Zeile, nicht die aufbereitete Sicht.
    "backend/api/routes/monatsdaten.py": "Rohwert-Route, eigene Bedeutung",
}


def _stellen_mit_altem_helfer() -> set[str]:
    treffer: set[str] = set()
    for pfad in (_BACKEND).rglob("*.py"):
        if "venv" in pfad.parts or "tests" in pfad.parts:
            continue
        quelle = pfad.read_text(encoding="utf-8")
        if _HELFER not in quelle:
            continue
        baum = ast.parse(quelle)
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.Call):
                continue
            name = getattr(knoten.func, "id", None) or getattr(knoten.func, "attr", None)
            if name == _HELFER:
                treffer.add(f"backend/{pfad.relative_to(_BACKEND).as_posix()}")
    return treffer


def test_keine_neue_stelle_umgeht_die_kaskade():
    """Die Restschuld wächst nicht."""
    gefunden = _stellen_mit_altem_helfer()
    neu = sorted(gefunden - set(KASKADE_NOCH_NICHT))

    assert neu == [], (
        f"{len(neu)} neue Stelle(n) bilden den Monatspreis mit dem "
        f"ZWEISTUFIGEN `{_HELFER}`: {neu}\n"
        "Seit #412 gibt es vier Stufen (gepflegt → gemessen → Zeitfenster → "
        "Stamm) in `strompreis_aggregator.aufgeloester_monatspreis`. Wer beim "
        "alten Helfer bleibt, zeigt bei einem dynamischen Tarif ohne "
        "Monatsabschluss den Stammpreis, während die Nachbarsicht den "
        "gemessenen Ø nennt — dieselbe Größe, zwei Zahlen.\n"
        "Entweder umstellen oder mit Begründung in `KASKADE_NOCH_NICHT` "
        "eintragen."
    )


def test_die_restschuld_ist_nicht_veraltet():
    """Eine erledigte Zeile verschwindet aus der Liste.

    ⚠ Ohne diese Gegenrichtung bliebe die Liste stehen, nachdem die Arbeit
    getan ist — und behauptete eine Schuld, die es nicht mehr gibt. Genau der
    Fall, den `ist-waerme-klima.md` §4 am 06.09.2026 hatte.
    """
    gefunden = _stellen_mit_altem_helfer()
    erledigt = sorted(set(KASKADE_NOCH_NICHT) - gefunden)

    assert erledigt == [], (
        f"{len(erledigt)} Eintrag/Einträge in `KASKADE_NOCH_NICHT` treffen auf "
        f"keine Fundstelle mehr: {erledigt}. Zeile löschen."
    )
