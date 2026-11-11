"""Werkzeug der Daten-Checker-Wächter W-1/W-2/W-3 (Etappe E2): alle `CheckErgebnis(`-Stellen unter
`services/daten_checker/` per AST, dazu die schrumpfende Baseline der `altlink=`-Stellen.

Baseline neu schreiben (nur wenn Stellen WEGFALLEN; sie wächst nie — ein neuer Eintrag ist rot):

    cd eedc && backend/venv/bin/python -m backend.tests.werkzeug_daten_checker_stellen --baseline

Format je Zeile: ``datei::code#n<TAB>altlink-Ausdruck<TAB>Grund``; Grund ∈ ``GRUENDE`` (warum das Teil-B-Ziel den heutigen
Link nicht bitgleich ergibt). E4 hat die Datei geleert und `CheckErgebnis.altlink` entfernt — sie bleibt leer (Wächter W-2).
"""

from __future__ import annotations

import ast
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
CHECKER_DIR = BACKEND / "services" / "daten_checker"
BASELINE = Path(__file__).resolve().parent / "daten_checker_altlink_baseline.txt"
#: Dateien, die keine Erzeuger sind: die Dataclass und die Ableitung, der Ziel-Bauer, der Katalog.
KEINE_ERZEUGER = {"kategorien.py", "ziele.py", "handgriffe.py", "gruppen.py"}
GRUENDE = ("anderer_pfad", "andere_parameter", "heute_kein_link", "klasse_ohne_ziel")
#: Ziel-Bauer → Pfad, den die Oberfläche heute liest (für den Grund «anderer Pfad» vs. «andere Parameter»).
_PFAD_DES_BAUERS = {
    "ziel_komponente": "/einstellungen/komponenten", "ziel_anlage": "/einstellungen/stammdaten",
    "ziel_tarif": "/einstellungen/stammdaten", "ziel_datenquelle": "/einstellungen/datenquellen",
    "ziel_datenquelle_schluessel": "/einstellungen/datenquellen", "ziel_monat": "/einstellungen/daten",
    "ziel_monat_label": "/einstellungen/daten", "ziel_werkbank": "/einstellungen/daten",
}


@dataclass
class Stelle:
    datei: str
    zeile: int
    code: object  # str bei einem Literal, sonst der AST-Ausdruck
    kw: dict = field(default_factory=dict)  # Schlüsselwort → AST-Ausdruck
    sterne: int = 0  # **-Argumente

    def quelle(self, name: str) -> str | None:
        return ast.unparse(self.kw[name]) if name in self.kw else None


def erzeuger_dateien() -> list[Path]:
    return sorted(p for p in CHECKER_DIR.rglob("*.py") if p.name not in KEINE_ERZEUGER and "__pycache__" not in p.parts)


def stellen() -> list[Stelle]:
    out = []
    for pfad in erzeuger_dateien():
        rel = pfad.relative_to(CHECKER_DIR).as_posix()
        for n in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "CheckErgebnis":
                kw = {k.arg: k.value for k in n.keywords if k.arg}
                code = kw.get("code")
                out.append(Stelle(rel, n.lineno, code.value if isinstance(code, ast.Constant) else code, kw,
                                  sum(1 for k in n.keywords if k.arg is None)))
    return sorted(out, key=lambda s: (s.datei, s.zeile))


def _ohne_ifexp(knoten):
    """Bei `a if b else c` den Zweig a (der heutige Link bzw. das Ziel des Normalfalls)."""
    return knoten.body if isinstance(knoten, ast.IfExp) else knoten


def _altlink_pfad(knoten) -> str | None:
    from backend.services.daten_checker import ziele
    k = _ohne_ifexp(knoten)
    if isinstance(k, ast.Name):
        wert = getattr(ziele, k.id)
        return None if not isinstance(wert, str) else wert.split("?")[0]
    if isinstance(k, ast.Call) and getattr(k.func, "id", None) == "heute_monat":
        return "/einstellungen/daten"
    raise ValueError(f"altlink-Ausdruck nicht benannt: {ast.unparse(knoten)}")


def _ziel_pfad(knoten) -> str | None:
    k = _ohne_ifexp(knoten)
    if not isinstance(k, ast.Call):
        return None
    name = k.func.id
    if name == "ziel_block":
        return f"/einstellungen/{k.args[0].value}"
    if name == "ziel_komponente" and any(w.arg == "jahresbilanz" for w in k.keywords):
        return "/komponenten"
    return _PFAD_DES_BAUERS[name]


def grund(s: Stelle) -> str:
    a = s.kw["altlink"]
    if isinstance(a, ast.Name) and a.id == "KEIN_LINK":
        return "heute_kein_link"
    if "ziel" not in s.kw:
        return "klasse_ohne_ziel"
    return "andere_parameter" if _altlink_pfad(a) == _ziel_pfad(s.kw["ziel"]) else "anderer_pfad"


def altlink_schluessel(alle: list[Stelle]) -> Counter:
    zaehler, out = Counter(), Counter()
    for s in alle:
        zaehler[(s.datei, s.code)] += 1
        if "altlink" in s.kw:
            out[f"{s.datei}::{s.code}#{zaehler[(s.datei, s.code)]}\t{s.quelle('altlink')}\t{grund(s)}"] += 1
    return out


def baseline_lesen() -> Counter:
    return Counter(z for z in BASELINE.read_text(encoding="utf-8").splitlines() if z and not z.startswith("#"))


def baseline_schreiben() -> None:
    zeilen = sorted(altlink_schluessel(stellen()).elements())
    kopf = ("# Übergangsfeld `altlink=` an Daten-Checker-Erzeugern (Etappe E2 → E4) — seit E4 leer, das Feld ist entfallen.\n"
            "# Neu schreiben: python -m backend.tests.werkzeug_daten_checker_stellen --baseline. "
            "Format: datei::code#n<TAB>altlink<TAB>Grund\n")
    BASELINE.write_text(kopf + "\n".join(zeilen) + "\n", encoding="utf-8")
    print(f"{len(zeilen)} Zeilen → {BASELINE}")


if __name__ == "__main__":
    if "--baseline" in sys.argv:
        baseline_schreiben()
    else:
        alle = stellen()
        print(len(alle), "Stellen;", Counter(grund(s) for s in alle if "altlink" in s.kw))
