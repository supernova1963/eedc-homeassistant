"""N-603 — Anwendertexte sagen „Gesamtverbrauch" oder „Restverbrauch", nie „Hausverbrauch" (Backend-Hälfte).

Regel Gernot (03.10.2026, wörtlich): „Wir sollten den Begriff ‚Hausverbrauch' vermeiden und immer die Formel der
Berechnung im Tooltip anzeigen." Anlass #407 und die Messung, dass eedc das Wort mit zwei Bedeutungen benutzte: die
Live-Kachel meinte Eigenverbrauch + Netzbezug (Gesamtverbrauch), die Tag-Sicht und der Energiefluss den Rest nach den
separat erfassten Verbrauchern (Restverbrauch). Definitionen: GLOSSAR „Gesamtverbrauch · Eigenverbrauch ·
Restverbrauch". Frontend-Hälfte: ``npm run check:begriffe``.

**Was geprüft wird (AST, Zeichenketten-Konstanten ohne Docstrings, Kommentare sieht der Baum nicht):**

1. kein „Hausverbrauch" in den Anwendertexten des Daten-Checkers (``services/daten_checker/``), der MQTT-Topic-Hilfe
   (``services/mqtt_topic_registry.py``) und der Felddefinitionen (``core/field_definitions/``);
2. baumweit keine Zeichenkette, die genau „Haushalt" lautet — das waren die Labels des Restverbrauchs
   (Live-Tagesverlauf, Energiefluss-Knoten, Monats-Energieprofil samt PDF-Spiegel, virtuelle Serie, Demo). Die
   Schlüssel ``"haushalt"`` (klein) bleiben: sie sind API- und Datenvertrag.

Grenze: ein Text, der das Wort aus Teilen zusammensetzt, läuft vorbei — ein Review sieht ihn.

Schwesterdateien: frontend/scripts/check-begriffe.mjs, test_n346_abdeckung_nennt_hausverbrauch_grundlast.py.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

#: Geltungsbereich der Regel 1 (Vorlage `vorlage-begriffe-verbrauch.md` §4).
TEXT_BEREICH = ("services/daten_checker", "services/mqtt_topic_registry.py", "core/field_definitions")


def _dateien():
    for p in sorted(BACKEND.rglob("*.py")):
        rel = p.relative_to(BACKEND).as_posix()
        if rel.startswith(("tests/", "venv/")) or "/__pycache__/" in rel:
            continue
        yield rel, p


def _texte(pfad: Path):
    """(Zeile, Text) aller Zeichenketten-Konstanten außer Docstrings."""
    baum = ast.parse(pfad.read_text(encoding="utf-8"))
    docs = set()
    for n in ast.walk(baum):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and n.body:
            erst = n.body[0]
            if isinstance(erst, ast.Expr) and isinstance(erst.value, ast.Constant) and isinstance(erst.value.value, str):
                docs.add(id(erst.value))
    for n in ast.walk(baum):
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docs:
            yield n.lineno, n.value


def funde_hausverbrauch() -> list[str]:
    return [f"{rel}:{z}" for rel, p in _dateien() if rel.startswith(TEXT_BEREICH)
            for z, t in _texte(p) if "Hausverbrauch" in t]


def funde_haushalt_label() -> list[str]:
    return [f"{rel}:{z}" for rel, p in _dateien() for z, t in _texte(p) if t.strip() == "Haushalt"]


def test_kein_hausverbrauch_in_anwendertexten():
    funde = funde_hausverbrauch()
    assert not funde, ("„Hausverbrauch\" in einem Anwendertext — Gesamtverbrauch (Eigenverbrauch + Netzbezug) oder "
                       "Restverbrauch (Gesamtverbrauch − separat erfasste Verbraucher) schreiben:\n  " + "\n  ".join(funde))


def test_kein_label_haushalt():
    funde = funde_haushalt_label()
    assert not funde, ("Label „Haushalt\" — der Wert ist der Restverbrauch (N-603); der Schlüssel `haushalt` "
                       "bleibt:\n  " + "\n  ".join(funde))


def test_die_regel_findet_beide_formen():
    """Selbsttest an einer Textfixture — ein Prüfer, der nichts finden kann, ist grün ohne Aussage."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "probe.py"
        p.write_text('"""Docstring mit Hausverbrauch zählt nicht."""\n'
                     'X = {"label": "Haushalt"}\n'
                     'Y = f"Ohne Netzbezug ist der Hausverbrauch {1} falsch"\n', encoding="utf-8")
        texte = list(_texte(p))
    assert any(t == "Haushalt" for _z, t in texte)
    assert any("Hausverbrauch" in t for _z, t in texte)
    assert not any(t.startswith("Docstring") for _z, t in texte)
