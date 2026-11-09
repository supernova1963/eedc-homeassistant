"""Rechenstellen außerhalb des Berechnungs-Layers — das Werkzeug hinter ``test_dezentrale_rechenstellen.py`` (Päckchen Z3).

Kern der Erhebung «dezentrale Berechnungen» vom 9.11.2026 (Python-``ast``, nur lesend), ohne deren Bericht-, JSON- und
Konstanten-Teile. Jeder binäre Rechenausdruck (``+ - * / // % **`` und die erweiterten Zuweisungen) mit einem Fach-Operanden
(Name nach ``FACH``) oder einem Zahl-Literal ist ein Treffer; Zeitarithmetik, Index, f-String und ``range`` fallen weg.
Jeder Operand bekommt eine **Rolle** nach seinem Namen (E Energie · G Geld · P Leistung · Q Quote · C CO₂ · T Zeit ·
S sonst · L Literal), der Treffer eine **Gestalt** (``E/E``, ``E*G`` …) und **Marker**:

* ``einheit`` — ein Literal aus ``EINHEITEN`` (× 100, ÷ 1000 …) oder ``…_prozent``/``…_cent`` mit 100,
* ``zaehler`` — ``± 1``,
* ``aggregation`` — erweiterte Zuweisung oder ``sum``/``len``-Operand,
* ``layer-aufruf`` — die umgebende Funktion ruft einen Namen aus ``core.berechnungen``,
* ``docstring-token`` — Docstring der Funktion oder ein Kommentar ±2 Zeilen nennt N-/F-/DI-/P-/ADR-Token.

Schlüssel ohne Zeilennummer (verschiebt sich nicht beim Formatieren, Muster ``test_kognitive_komplexitaet.py``):
``datei::qualname::operator::operanden-ohne-leerzeichen``. Gleiche Schlüssel zählen mehrfach (Multimenge).

Baseline neu schreiben (nach einem bewussten Umzug in den Layer oder einer bewusst gelassenen Stelle; Diff in den Commit):

    cd eedc && backend/venv/bin/python -m backend.tests.werkzeug_rechenstellen --baseline

Lizenz: wie das Repository.
"""
from __future__ import annotations

import argparse
import ast
import io
import re
import tokenize
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from backend.tests.quellbaum import produktivbaum

BASELINE = Path(__file__).with_name("rechenstellen_baseline.txt")

#: Gestalten, die der Wächter führt (Auftrag Päckchen Z, Einwertung Master 9.11.2026): Quote zweier Mengen, Differenz zweier
#: Mengen, Menge × Preis, Menge × Literal, Preis ÷ Menge (gewichteter Ø), Differenz zweier Geldbeträge.
GESTALTEN = frozenset({"E/E", "E-E", "E*G", "E*L", "G/E", "G-G"})
#: Dateiklassen, die der Wächter führt — ``core/`` außerhalb des Layers wird erhoben, aber nicht geführt.
KLASSEN = frozenset({"route", "service"})
#: Treffer mit diesen Markern sind keine Kandidaten (Einheitenumrechnung, Zähler, Funktion ruft schon den Layer).
OHNE_MARKER = frozenset({"einheit", "zaehler", "layer-aufruf"})

FACH = re.compile(
    r"kwh|wh|euro|cent|ct|kg|prozent|anteil|preis|kosten|ersparnis|erloes|verguetung|co2|ertrag|leistung|kw\b|kwp|faktor|"
    r"wirkungsgrad|effizienz|cop|jaz|az\b|ladung|entladung|"
    r"verbrauch|erzeugung|einspeisung|netzbezug|bezug|soc|kapazitaet|km|liter|gas|waerme|temperatur|grad|strahlung|ghi|gti|"
    r"degradation|amortisation|roi|rendite|zins|"
    r"abschreibung|steuer|ust|mwst|bilanz|autarkie|eigenverbrauch|peak|spitze|mittel|summe|saldo|tarif|grundgebuehr")
ZEIT = re.compile(r"timedelta|datetime|date\(|day|hour|minute|second|stunde|tag\b|monat\b|jahr\b")
EINHEITEN = {100, 1000, 1e6, 12, 24, 60, 3600, 365, 365.25, 7, 30, 31, 0.001, 0.01}
TOKEN = re.compile(r"\b(?:N-|F-|DI-)\d|\bP(?:1[0-5]|[1-9])\b|\bADR")
OPS = {ast.Mult: "*", ast.Div: "/", ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**", ast.Add: "+", ast.Sub: "-"}

ROLLEN = [
    ("E", re.compile(r"kwh|wh\b|mwh|erzeugung|verbrauch|einspeisung|netzbezug|bezug|ladung|entladung|eigenverbrauch|menge"
                     r"|ertrag(?!.*(euro|cent))")),
    ("G", re.compile(r"euro|cent|\bct\b|preis|kosten|ersparnis|erloes|verguetung|tarif|grundgebuehr|betrag|zins|abschreibung"
                     r"|steuer|ust|mwst|rendite")),
    ("P", re.compile(r"\bkw\b|kwp|\bw\b|leistung|peak|spitze")),
    ("Q", re.compile(r"prozent|anteil|quote|faktor|wirkungsgrad|effizienz|cop|jaz|\baz\b|autarkie|degradation|verlust")),
    ("C", re.compile(r"co2|\bkg\b")),
    ("T", re.compile(r"stunden|minuten|sekunden|tage\b|\bh\b|dauer|zeit")),
]
REIHE = "EGPQCTSL"


@dataclass(frozen=True)
class Rechenstelle:
    datei: str
    zeile: int
    funktion: str
    klasse: str
    operator: str
    operanden: tuple[str, str]
    gestalt: str
    marker: tuple[str, ...]

    @property
    def schluessel(self) -> str:
        return f"{self.datei}::{self.funktion}::{self.operator}::" + ",".join("".join(o.split()) for o in self.operanden)

    @property
    def gefuehrt(self) -> bool:
        """Gehört zur Menge, die der Wächter gegen die Baseline vergleicht."""
        return self.gestalt in GESTALTEN and self.klasse in KLASSEN and not (set(self.marker) & OHNE_MARKER)


def rolle_name(name: str) -> str:
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name).replace("_", " ").lower().strip()
    for r, rx in ROLLEN:
        if rx.search(s):
            return r
    return "S"


def gestalt_von(rl: str, rr: str, op: str) -> str:
    basis = op.rstrip("=") if len(op) > 1 and op.endswith("=") else op
    aug = basis != op
    if basis in ("*", "+") and not aug and REIHE.index(rl) > REIHE.index(rr):
        rl, rr = rr, rl
    return f"{rl}{basis}{rr}"


def litwert(n: ast.AST):
    """Zahlwert eines reinen Zahl-Teilbaums, sonst ``None``."""
    if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool):
        return n.value
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
        v = litwert(n.operand)
        return None if v is None else (-v if isinstance(n.op, ast.USub) else v)
    if isinstance(n, ast.BinOp) and type(n.op) in OPS:
        a, b = litwert(n.left), litwert(n.right)
        if a is None or b is None:
            return None
        try:
            return {ast.Mult: lambda: a * b, ast.Div: lambda: a / b, ast.FloorDiv: lambda: a // b, ast.Mod: lambda: a % b,
                    ast.Pow: lambda: a ** b if abs(b) < 20 else None, ast.Add: lambda: a + b,
                    ast.Sub: lambda: a - b}[type(n.op)]()
        except Exception:  # noqa: BLE001 — ein Literal-Teilbaum, der nicht rechnet, ist eben kein Zahlwert
            return None
    return None


def ident(n: ast.AST):
    """``(bezeichner, via)`` oder ``None`` — Name, Attribut oder Subscript mit String-Schlüssel."""
    if isinstance(n, ast.Name):
        return n.id, "name"
    if isinstance(n, ast.Attribute):
        return n.attr, "attr"
    if isinstance(n, ast.Subscript):
        s = n.slice
        if isinstance(s, ast.Constant) and isinstance(s.value, str):
            return s.value, "key"
    return None


def alle_idents(n: ast.AST) -> list[str]:
    out = []
    for x in ast.walk(n):
        if isinstance(x, ast.Name):
            out.append(x.id)
        elif isinstance(x, ast.Attribute):
            out.append(x.attr)
        elif isinstance(x, ast.Constant) and isinstance(x.value, str):
            out.append(x.value)
    return out


def klasse(rel: str) -> str:
    if rel.startswith("api/"):
        return "route"
    if rel.startswith("services/"):
        return "service"
    return "core-ohne-layer"


def _layer_importe(tree: ast.Module) -> tuple[set[str], set[str]]:
    namen, aliase = set(), set()
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            m = n.module or ""
            if "core.berechnungen" in m or (n.level and m.startswith("berechnungen")) or m.endswith("berechnungen"):
                for a in n.names:
                    namen.add(a.asname or a.name)
            elif m.endswith("core") or m == "core":
                for a in n.names:
                    if a.name == "berechnungen":
                        aliase.add(a.asname or a.name)
        elif isinstance(n, ast.Import):
            for a in n.names:
                if "core.berechnungen" in a.name:
                    aliase.add(a.asname or a.name.split(".")[-1])
    return namen, aliase


def _kommentare(quelle: str) -> dict[int, str]:
    out = {}
    try:
        for t in tokenize.generate_tokens(io.StringIO(quelle).readline):
            if t.type == tokenize.COMMENT:
                out[t.start[0]] = t.string
    except (tokenize.TokenError, IndentationError):
        pass
    return out


class _Besucher(ast.NodeVisitor):
    def __init__(self, rel: str, tree: ast.Module, layer_namen: set[str], layer_aliase: set[str], komm: dict[int, str]):
        self.rel, self.layer_namen, self.layer_aliase, self.komm = rel, layer_namen, layer_aliase, komm
        self.stack: list[str] = []
        self.parents: dict[ast.AST, ast.AST] = {}
        self.treffer: list[Rechenstelle] = []
        for p in ast.walk(tree):
            for c in ast.iter_child_nodes(p):
                self.parents[c] = p

    def _qual(self) -> str:
        return ".".join(self.stack) if self.stack else "<modul>"

    def visit_ClassDef(self, n):  # noqa: N802 — ast.NodeVisitor-Schnittstelle
        self.stack.append(n.name)
        self.generic_visit(n)
        self.stack.pop()

    def visit_FunctionDef(self, n):  # noqa: N802
        self.stack.append(n.name)
        self.generic_visit(n)
        self.stack.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def _funktionen_oben(self, node):
        out, p = [], self.parents.get(node)
        while p is not None:
            if isinstance(p, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append(p)
            p = self.parents.get(p)
        return out

    def _ausgeschlossen(self, node) -> bool:
        c, p = node, self.parents.get(node)
        while p is not None:
            if isinstance(p, ast.JoinedStr):
                return True
            if (isinstance(p, ast.Subscript) and c is p.slice) or isinstance(p, ast.Slice):
                return True
            if isinstance(p, ast.Call) and isinstance(p.func, ast.Name) and p.func.id == "range" and c in p.args:
                return True
            if isinstance(p, ast.stmt):
                break
            c, p = p, self.parents.get(p)
        return False

    def _layer_aufruf(self, node) -> bool:
        for f in self._funktionen_oben(node):
            for c in ast.walk(f):
                if isinstance(c, ast.Call):
                    fn = c.func
                    if isinstance(fn, ast.Name) and fn.id in self.layer_namen:
                        return True
                    if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id in self.layer_aliase:
                        return True
        return False

    def _beleg(self, node, zeile: int) -> bool:
        for f in self._funktionen_oben(node)[:1]:
            if TOKEN.search(ast.get_docstring(f) or ""):
                return True
        return any(z in self.komm and TOKEN.search(self.komm[z]) for z in range(zeile - 2, zeile + 3))

    def _rolle(self, x, v) -> str:
        if v is not None:
            return "L"
        i = ident(x)
        return rolle_name(i[0]) if i else "S"

    def _marker(self, node, links, rechts, lv, rv, opsym, aug) -> list[str]:
        marker = []
        lit = [v for v in (lv, rv) if v is not None]
        pc = ident(rechts if lv is None else links)
        einh = any(v in EINHEITEN for v in lit)
        if pc and re.search(r"(_prozent|_cent)$", pc[0].lower()) and any(v == 100 for v in lit) and opsym in ("/", "*"):
            einh = True
        if einh:
            marker.append("einheit")
        if opsym in ("+", "-") and rv == 1 and lv is None:
            marker.append("zaehler")
        if aug or any(isinstance(x, ast.Call) and isinstance(x.func, ast.Name) and x.func.id in ("sum", "len")
                      for x in (links, rechts)):
            marker.append("aggregation")
        if self._layer_aufruf(node):
            marker.append("layer-aufruf")
        if self._beleg(node, node.lineno):
            marker.append("docstring-token")
        return marker

    def _pruefe(self, node, links, rechts, opsym, aug=False):
        if self._ausgeschlossen(node):
            return
        if any(isinstance(x, ast.JoinedStr) or (isinstance(x, ast.Constant) and isinstance(x.value, (str, bytes)))
               for x in (links, rechts)):
            return
        lv, rv = litwert(links), litwert(rechts)
        if lv is not None and rv is not None:
            return
        tl, tr = ast.unparse(links), ast.unparse(rechts)
        fach = any(i and FACH.search(i[0].lower().lstrip("_")) for i in (ident(links), ident(rechts)))
        if not (fach or lv is not None or rv is not None):
            return
        if ZEIT.search((tl + " " + tr).lower()) and not FACH.search(
                " ".join(i.lower() for i in alle_idents(links) + alle_idents(rechts))):
            return
        op = opsym + ("=" if aug else "")
        self.treffer.append(Rechenstelle(
            datei=self.rel, zeile=node.lineno, funktion=self._qual(), klasse=klasse(self.rel), operator=op,
            operanden=(" ".join(tl.split()), " ".join(tr.split())),
            gestalt=gestalt_von(self._rolle(links, lv), self._rolle(rechts, rv), op),
            marker=tuple(self._marker(node, links, rechts, lv, rv, opsym, aug)),
        ))

    def visit_BinOp(self, n):  # noqa: N802
        if type(n.op) in OPS:
            self._pruefe(n, n.left, n.right, OPS[type(n.op)])
        self.generic_visit(n)

    def visit_AugAssign(self, n):  # noqa: N802
        if type(n.op) in OPS:
            self._pruefe(n, n.target, n.value, OPS[type(n.op)], aug=True)
        self.generic_visit(n)


def rechenstellen() -> list[Rechenstelle]:
    """Alle Treffer unter ``api/``, ``services/`` und ``core/`` ohne ``core/berechnungen/`` (der Layer selbst)."""
    out: list[Rechenstelle] = []
    for datei in produktivbaum():
        rel = datei.rel
        if not rel.startswith(("api/", "services/", "core/")) or rel.startswith("core/berechnungen/"):
            continue
        namen, aliase = _layer_importe(datei.baum)
        b = _Besucher(rel, datei.baum, namen, aliase, _kommentare(datei.quelle))
        b.visit(datei.baum)
        out.extend(b.treffer)
    out.sort(key=lambda t: (t.datei, t.zeile))
    return out


def gefuehrte() -> list[Rechenstelle]:
    return [t for t in rechenstellen() if t.gefuehrt]


def baseline_lesen() -> Counter:
    zaehler: Counter = Counter()
    for zeile in BASELINE.read_text(encoding="utf-8").splitlines():
        if not zeile.strip() or zeile.startswith("#"):
            continue
        zaehler[zeile.split("\t", 1)[0]] += 1
    return zaehler


def baseline_schreiben() -> int:
    zeilen = sorted(f"{t.schluessel}\t{t.gestalt}" for t in gefuehrte())
    BASELINE.write_text(
        "# Rechenstellen außerhalb des Layers (Gestalten E/E E-E E*G E*L G/E G-G, Routen/Services, ohne einheit/zaehler/\n"
        "# layer-aufruf) — darf nur schrumpfen. Neu schreiben: siehe werkzeug_rechenstellen.py. Format: schluessel<TAB>gestalt\n"
        + "\n".join(zeilen) + "\n",
        encoding="utf-8",
    )
    return len(zeilen)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--baseline", action="store_true", help="Baseline neu schreiben")
    ap.add_argument("--liste", action="store_true", help="geführte Rechenstellen mit Datei:Zeile zeigen")
    a = ap.parse_args()
    if a.baseline:
        print(f"{baseline_schreiben()} Rechenstellen nach {BASELINE.name} geschrieben")
    elif a.liste:
        for t in gefuehrte():
            print(f"{t.datei}:{t.zeile}\t{t.gestalt}\t{t.operanden[0]} {t.operator} {t.operanden[1]}\t{','.join(t.marker)}")
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
