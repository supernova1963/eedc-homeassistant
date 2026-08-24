"""ADR-002 · Dead-Export-Wächter für `services/` — Baseline **0** (N-287 / M12).

**Was er behauptet.** Jede öffentliche Funktion, die ein Modul unter
`backend/services/` auf oberster Ebene definiert, wird irgendwo im Backend-Baum
auch **genannt** — im Produktivcode, im eigenen Modul oder in einer Probe. Wer
nirgends genannt wird, ist tot: Code, den niemand ruft, altert mit, wird
mitgelesen, mitmigriert und bei jeder Umbenennung mitgeschleppt.

**Was er ausdrücklich NICHT behauptet.** Er ist keine Erreichbarkeitsanalyse.
Als „genannt" zählt jedes Vorkommen des Namens als `Name`, als Attribut, als
Import-Alias oder als String-Literal (letzteres, damit ein per `getattr`
aufgelöster Name nicht fälschlich als tot gilt). Der Wächter irrt damit
systematisch in **eine** Richtung: Er meldet lieber zu wenig als zu viel. Ein
Fund von ihm ist deshalb belastbar, sein Schweigen ist es nicht.

**Warum der enge Schnitt.** ADR-002 formuliert die Regel als „jede öffentliche
`async def` in `services/` braucht einen **Importeur**". Wörtlich genommen
erfasst sie auch die 53 Funktionen, die nur ihr eigenes Modul ruft — davon
**40 Scheduler-Jobs**, die dort korrekt registriert werden. Die Allowlist wäre
größer als der Befund gewesen. Dasselbe Muster hat ADR-002 bei **P3-b** schon
einmal gemessen (3 falsch-positive auf 1 echten Treffer) und bei **P1**
beschrieben; **N-318** hat daraus die Lehre gezogen, dass die enge, messbare
Fassung die brauchbare ist. Dieser Wächter prüft deshalb: *überhaupt kein
Nenner im ganzen Baum*.

**Die Baseline war 6, nicht 0** (erhoben 2026-08-24, je Symbol per grep
gegengeprüft): `fetch_brightsky_forecast` · `get_brightsky_sources` ·
`generate_anlage_hash` · `pick_emob_ref_parameter` · `get_plan` ·
`klassifiziere_tag`. Sie sind im selben Paket gelöscht worden — deshalb steht
hier **keine Ausnahmeliste**, sondern die 0-Linie. Der aussagekräftigste der
sechs war `generate_anlage_hash`: der Community-Hash kommt seit Langem aus der
**Server-Antwort** (`api/routes/community.py`), die lokale Bildung war ein Rest.

**Nicht mit den Nachbarn verwechseln.** Sechs weitere Funktionen werden **nur
von Proben** gerufen (u. a. `berechne_eedc_prognose`, `kennzahlen_aus_fakten`).
Die sind nicht tot, sondern getestet; ein Wächter darüber verlangte, entweder
den Test oder die Funktion zu löschen. Sie stehen im Journal, nicht hier.
"""

from __future__ import annotations

import ast

from backend.tests.quellbaum import probenbaum, produktivbaum

#: Präfix des bewachten Bereichs. `services/` ist die Schicht, die ADR-002
#: nennt — dort entsteht öffentliche Fläche am schnellsten.
_BEREICH = "services/"


def _oeffentliche_exporte() -> dict[str, list[str]]:
    """`{Name: [Fundstelle, …]}` aller öffentlichen Top-Level-Funktionen."""
    exporte: dict[str, list[str]] = {}
    for datei in produktivbaum():
        if not datei.rel.startswith(_BEREICH):
            continue
        for knoten in datei.baum.body:
            if not isinstance(knoten, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if knoten.name.startswith("_"):
                continue
            exporte.setdefault(knoten.name, []).append(
                f"{datei.rel}:{knoten.lineno}"
            )
    return exporte


def _genannte_namen() -> set[str]:
    """Jeder Name, der im Baum irgendwo **gelesen** wird.

    Die Definitionszeile selbst zählt nicht mit: `FunctionDef.name` ist ein
    schlichtes `str`-Attribut und taucht in `ast.walk` nicht als Knoten auf.
    Genau daran erkennt der Wächter den toten Export.
    """
    namen: set[str] = set()
    for datei in produktivbaum() + probenbaum():
        for knoten in ast.walk(datei.baum):
            if isinstance(knoten, ast.ImportFrom):
                namen.update(a.name for a in knoten.names)
            elif isinstance(knoten, ast.Import):
                namen.update(a.name.split(".")[-1] for a in knoten.names)
            elif isinstance(knoten, ast.Name):
                namen.add(knoten.id)
            elif isinstance(knoten, ast.Attribute):
                namen.add(knoten.attr)
            elif isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
                # `getattr(modul, "name")` und Registrierung über Strings
                namen.add(knoten.value)
    return namen


def test_die_pruefmenge_laeuft_nicht_leer():
    """Ein Wächter über einer leeren Menge meldet grün, ohne zu messen (N-318)."""
    exporte = _oeffentliche_exporte()
    assert len(exporte) > 200, (
        f"Nur {len(exporte)} öffentliche Exporte in {_BEREICH} gefunden — "
        "der Wächter misst nicht mehr, was er zu messen behauptet."
    )
    genannt = _genannte_namen()
    assert len(genannt) > 5000, (
        f"Nur {len(genannt)} genannte Namen im Baum — die Nenner-Seite ist leer."
    )


def test_kein_toter_export_in_services():
    """Baseline 0: keine öffentliche `services/`-Funktion ohne einen Nenner."""
    genannt = _genannte_namen()
    tot = {
        name: orte
        for name, orte in _oeffentliche_exporte().items()
        if name not in genannt
    }
    assert not tot, (
        "Öffentliche Funktion in services/, die im ganzen Baum niemand nennt — "
        "weder Produktivcode noch Probe:\n  "
        + "\n  ".join(f"{name} → {', '.join(orte)}" for name, orte in sorted(tot.items()))
        + "\n\nEntweder verdrahten, testen — oder löschen. Eine Ausnahmeliste "
        "gibt es hier bewusst nicht: die Baseline war 6 und ist mit demselben "
        "Paket auf 0 gebracht worden (N-287/M12, 2026-08-24)."
    )
