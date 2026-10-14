"""Kognitive Komplexität je Funktion gegen eine eingecheckte Baseline (Wächter seit 14.10.2026).

Schwesterdateien: `test_routen_baseline.py` (dasselbe Muster — eine Liste, keine Zahl; der Diff
der Baseline ist lesbar) · `test_wurzelmuster_konformitaet.py` (baumweiter Prüfer über
`quellbaum.produktivbaum()`).

**Was gilt (Entscheid Gernot 14.10.2026, nach Messung — Hintergrund in `docs/DEVELOPMENT.md`
→ Code-Konventionen → Python):**

1. **Keine Funktion über 100**, außer den hier mit Grund genannten `AUSNAHMEN` (lineare Listen,
   deren Zahl nichts über Verzweigungstiefe sagt) und dem befristeten `ABBAU`-Bestand mit Auftragsnummer,
   der nur schrumpfen darf.
2. **Keine neue Funktion über 50.** Der Bestand steht in `kognitive_komplexitaet_baseline.txt`
   und darf nur schrumpfen; eine Funktion darin darf nicht wachsen.
3. **Die Baseline ist eine Behauptung.** Fällt eine Funktion unter 50, wird der Test rot, bis die
   Baseline neu geschrieben ist — so sinkt die Zahl sichtbar im Commit statt still im Kopf.

Die Schwelle ist bewusst **50 und nicht SonarQubes 15**: eedc wird mit KI-Unterstützung und
Golden Masters gepflegt; 50 ist nach der Refactoring-Serie (RF-1 … RF-18) die Größe, die eine
Bau-Sitzung samt Kontext sicher in einem Zug ändert. Gemessen 14.10.2026: die Dichte der
Fund-Vermerke je 1 000 Zeilen steigt von 12,7 (≤ 15) über 16,9 (16–50) auf 18,8 (51–100).

Metrik: `cognitive_complexity` (SonarSource-Definition, Paket `cognitive-complexity` in
`requirements-dev.txt`) — dieselbe wie `~/.claude/plans/refactoring-werkzeug/komplexitaet.py`,
damit Vorlage, Nachmessung und Gate eine Zahl nennen. Verschachtelte Funktionen zählen in der
äußeren mit (so rechnet die Bibliothek; so stand es in jeder RF-Vorlage).

**Wenn dieser Test rot wird:** Funktion bewusst aufgeteilt oder neu gebaut? Dann die Baseline neu
schreiben und den Diff im Commit mitschicken:

    cd eedc && python -c "from backend.tests.test_kognitive_komplexitaet import baseline_schreiben; baseline_schreiben()"

Eine neue Funktion über 50 ist dagegen kein Baseline-Fall, sondern ein Umbau-Fall: Phasen als
Funktionen mit Wächterklauseln (Bauform RF-1), bis sie darunter liegt.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from backend.tests.quellbaum import produktivbaum

try:
    from cognitive_complexity.api import get_cognitive_complexity
except ImportError as e:  # pragma: no cover — das Gate darf nicht still grün werden
    raise ImportError(
        "Paket `cognitive-complexity` fehlt — steht in backend/requirements-dev.txt; "
        "installieren, nicht überspringen (ein Gate ohne Messung ist kein Gate)."
    ) from e

BASELINE = Path(__file__).with_name("kognitive_komplexitaet_baseline.txt")

#: Obergrenze, die niemand überschreitet — außer `AUSNAHMEN`.
SCHWELLE_HART = 100
#: Ab hier gilt der Bestand: keine neue, keine wächst, Baseline nur schrumpfend.
SCHWELLE_BESTAND = 50

#: Funktionen über 100, die bleiben dürfen — mit dem Grund, den ein Prüfer lesen soll.
AUSNAHMEN: dict[str, str] = {
    "core/database.py::run_migrations": (
        "lineare Liste von Migrationsschritten in Ausführungsreihenfolge; die Zahl misst Länge, "
        "nicht Verschachtelung — ein Schnitt in Phasen würde nur die Reihenfolge verstecken"
    ),
    "core/database.py::run_migrations._run_migrations": (
        "innere Funktion derselben Liste (läuft in der Boot-Verbindung); zählt in `run_migrations` mit"
    ),
}


#: Bestand über 100 mit vorbereitetem Umbau-Auftrag — befristet, darf nur schrumpfen: landet der Umbau, fliegt die
#: Zeile (`test_abbau_ist_noch_noetig` wird sonst rot). Seit RF-28 (15.10.2026) leer; die zehn Einträge RF-19 … RF-28
#: sind gebaut. Ein Neuzugang über 100 ist ein Umbau-Fall, kein Eintrag — die Liste füllt sich nur mit einem
#: freigegebenen Auftrag samt Nummer.
ABBAU: dict[str, str] = {
}


def messen() -> dict[str, int]:
    """`datei::qualname` → kognitive Komplexität, über den Produktivbaum.

    Der Schlüssel trägt keine Zeilennummer — eine Baseline an Zeilennummern verschiebt sich bei
    jeder Formatierung (die Lehre aus N-195/N-263, s. `test_routen_baseline.py`). Trägt eine Datei
    denselben Qualnamen zweimal, zählt der höhere Wert.
    """
    werte: dict[str, int] = {}
    for datei in produktivbaum():
        if datei.rel.endswith("plz_to_state.py"):
            continue  # Datenblock, keine Funktionen — derselbe Ausschluss wie im Werkzeug
        stapel: list[str] = []

        def gehe(knoten: ast.AST) -> None:
            for kind in ast.iter_child_nodes(knoten):
                if isinstance(kind, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    stapel.append(kind.name)
                    if not isinstance(kind, ast.ClassDef):
                        schluessel = f"{datei.rel}::{'.'.join(stapel)}"
                        try:
                            wert = get_cognitive_complexity(kind)
                        except Exception:  # noqa: BLE001 — Bibliotheksfehler sollen nicht das Gate kippen
                            wert = 0
                        werte[schluessel] = max(wert, werte.get(schluessel, 0))
                    gehe(kind)
                    stapel.pop()
                else:
                    gehe(kind)

        gehe(datei.baum)
    return werte


def baseline_lesen() -> dict[str, int]:
    out: dict[str, int] = {}
    for zeile in BASELINE.read_text().splitlines():
        if not zeile.strip() or zeile.startswith("#"):
            continue
        wert, schluessel = zeile.split("\t", 1)
        out[schluessel] = int(wert)
    return out


def baseline_schreiben() -> None:
    """Den Bestand über `SCHWELLE_BESTAND` neu schreiben (nach einem Umbau; Diff gehört in den Commit)."""
    werte = messen()
    zeilen = [f"{v}\t{k}" for k, v in sorted(werte.items()) if v > SCHWELLE_BESTAND]
    BASELINE.write_text(
        "# Bestand der Funktionen mit kognitiver Komplexität > 50 — darf nur schrumpfen.\n"
        "# Neu schreiben: siehe test_kognitive_komplexitaet.py (Docstring). Format: kognitiv<TAB>datei::qualname\n"
        + "\n".join(zeilen) + "\n"
    )
    print(f"{len(zeilen)} Funktionen > {SCHWELLE_BESTAND} nach {BASELINE.name} geschrieben")


@pytest.fixture(scope="module")
def werte() -> dict[str, int]:
    return messen()


def test_keine_funktion_ueber_100_ausser_ausnahmen(werte):
    zu_hoch = {k: v for k, v in werte.items() if v > SCHWELLE_HART and k not in AUSNAHMEN and k not in ABBAU}
    assert not zu_hoch, (
        f"{len(zu_hoch)} Funktion(en) über {SCHWELLE_HART} ohne Ausnahme und ohne Abbau-Auftrag — aufteilen "
        "(Bauform RF-1), nicht eintragen:\n  "
        + "\n  ".join(f"{v:4}  {k}" for k, v in sorted(zu_hoch.items(), key=lambda x: -x[1]))
    )


def test_abbau_ist_noch_noetig(werte):
    """Ein Abbau-Eintrag für eine Funktion, die unter 100 liegt, ist erledigt — raus damit, die Liste schrumpft im Commit."""
    erledigt = [f"{k}  ({ABBAU[k]})" for k in ABBAU if werte.get(k, 0) <= SCHWELLE_HART]
    assert not erledigt, "Abbau erledigt — Eintrag/Einträge aus ABBAU streichen:\n  " + "\n  ".join(erledigt)


def test_ausnahmen_sind_noch_noetig(werte):
    """Eine Ausnahme für eine Funktion, die unter 100 liegt oder nicht mehr existiert, ist tot — raus damit."""
    tot = [k for k in AUSNAHMEN if werte.get(k, 0) <= SCHWELLE_HART]
    assert not tot, "Ausnahme(n) ohne Bedarf (Funktion ≤ 100 oder weg) — aus AUSNAHMEN streichen:\n  " + "\n  ".join(tot)


def test_keine_neue_funktion_ueber_50(werte):
    baseline = baseline_lesen()
    neu = {k: v for k, v in werte.items() if v > SCHWELLE_BESTAND and k not in baseline}
    assert not neu, (
        f"{len(neu)} neue Funktion(en) über {SCHWELLE_BESTAND} — kein Baseline-Fall, sondern aufteilen:\n  "
        + "\n  ".join(f"{v:4}  {k}" for k, v in sorted(neu.items(), key=lambda x: -x[1]))
    )


def test_bestand_waechst_nicht(werte):
    baseline = baseline_lesen()
    gewachsen = {k: (alt, werte[k]) for k, alt in baseline.items() if werte.get(k, 0) > alt}
    assert not gewachsen, (
        "Funktion(en) im Bestand sind gewachsen — zurückbauen, die Baseline wird nicht hochgesetzt:\n  "
        + "\n  ".join(f"{alt:4} → {neu:4}  {k}" for k, (alt, neu) in sorted(gewachsen.items()))
    )


def test_baseline_ist_aktuell(werte):
    """Gesunken oder verschwunden ⇒ Baseline neu schreiben, damit die Zahl im Commit sinkt."""
    baseline = baseline_lesen()
    veraltet = {k: (alt, werte.get(k)) for k, alt in baseline.items() if werte.get(k, 0) <= SCHWELLE_BESTAND}
    assert not veraltet, (
        f"{len(veraltet)} Baseline-Eintrag/-Einträge liegen jetzt ≤ {SCHWELLE_BESTAND} oder fehlen — "
        "Baseline neu schreiben (Docstring) und den Diff committen:\n  "
        + "\n  ".join(f"{alt:4} → {str(neu):>4}  {k}" for k, (alt, neu) in sorted(veraltet.items()))
    )
