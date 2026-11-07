"""Übersicht der Größen — Erzeuger und Parser (Bauplan «Übersicht der Größen» §3, Stufe U1, 7.11.2026).

Schreibt ``docs/UEBERSICHT-GROESSEN.md``: jeder Eintrag der vier Registries von eedc bekommt genau eine Zeile.

======================  =====================================================================  ==========================
Ebene                   Quelle                                                                 gelesen über
======================  =====================================================================  ==========================
Eingabefeld             ``core/field_definitions/registry.py`` (sieben Listen)                 Import
Monatsgröße             ``services/monats_fakten/fakten.py`` + ``fakten_wp.py``                 Import + AST (Bau-Funktion)
Kennwert (Tabelle)      ``frontend/src/lib/werte/registry.ts``                                 Regex (kein TS-Runner)
HA-Export-Sensor        ``services/ha_sensors_export.py::get_all_sensor_definitions()``        Import
======================  =====================================================================  ==========================

**Kein zweiter Wahrheitsort.** Jede Spalte kommt aus dem Code; nur ``abschnitt`` (Regel in BERECHNUNGEN oder
SENSOR-REFERENZ), ``test``, ``backend_feld`` (Kennwerte, wo nicht ableitbar), ``code_ort`` (Überschreibung) und
``hinweis`` stehen in ``groessen_hand.yaml``; der Wächter ``test_groessen_uebersicht.py`` bindet sie an die Registries.
Einen ``formel``-Text von Hand gibt es nicht (Doktrin ``services/kanal/katalog.py``, N-259).

**Die Werte-Registry wird bewusst per Regex gelesen** — dasselbe Verfahren wie
``test_daten_checker_kategorien_erreichbar.py``: es gibt keinen TS-Runner in den devDependencies, und ein JSON-Export
wäre ein zweiter Wahrheitsort.

**Aufruf** (setzt ``DATABASE_URL`` auf eine Scratch-DB, BEVOR ``backend`` importiert wird — ``core/database.py`` baut
die Engine beim Import)::

    scripts/groessen-uebersicht.sh              # docs/UEBERSICHT-GROESSEN.md neu schreiben
    scripts/groessen-uebersicht.sh --baseline   # groessen_offen_baseline.txt neu schreiben (nur schrumpfend)
    scripts/groessen-uebersicht.sh --pruefen    # nur vergleichen, nichts schreiben (Exit 1 bei Abweichung)

Danach ``./scripts/sync-help.sh`` (In-App-Hilfe); die Website spiegelt beim Build.
"""
from __future__ import annotations

import os
import sys

if __name__ == "__main__" and not os.environ.get("DATABASE_URL"):  # pragma: no cover — Schutz vor eedc/data/eedc.db
    sys.exit("DATABASE_URL fehlt — bitte über scripts/groessen-uebersicht.sh aufrufen (Scratch-DB vor dem Import).")

import argparse  # noqa: E402
import ast  # noqa: E402
import dataclasses  # noqa: E402
import html  # noqa: E402
import re  # noqa: E402
import typing  # noqa: E402
import unicodedata  # noqa: E402
from collections import defaultdict  # noqa: E402
from dataclasses import dataclass, field  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Callable, Iterable, Mapping, Optional  # noqa: E402
from urllib.parse import unquote  # noqa: E402

import yaml  # noqa: E402

# ── Pfade ───────────────────────────────────────────────────────────────────

EEDC = Path(__file__).resolve().parents[2]
REPO = EEDC.parent
BACKEND = EEDC / "backend"
FRONTEND = EEDC / "frontend"
DOCS = REPO / "docs"
CHANGELOG = REPO / "CHANGELOG.md"
ZIEL = DOCS / "UEBERSICHT-GROESSEN.md"
HAND = Path(__file__).with_name("groessen_hand.yaml")
BASELINE = Path(__file__).with_name("groessen_offen_baseline.txt")

BEFEHL = "scripts/groessen-uebersicht.sh"
BEFEHL_BASELINE = "scripts/groessen-uebersicht.sh --baseline"

WERTE_REGISTRY_TS = FRONTEND / "src" / "lib" / "werte" / "registry.ts"
MONATS_ZEITREIHE_TS = FRONTEND / "src" / "pages" / "auswertung" / "types.ts"
MONATS_FAKTEN_DIR = BACKEND / "services" / "monats_fakten"
ZEILENBAUER_PY = BACKEND / "api" / "routes" / "monatsdaten_aggregiert.py"
TAGES_LESER_PY = (
    BACKEND / "services" / "energie_profil" / "tage_werte.py",
    BACKEND / "services" / "energie_profil" / "tage_werte_zusatz.py",
)

# ── Ebenen und Hand-Datei ───────────────────────────────────────────────────

EINGABEFELD = "eingabefeld"
MONATSGROESSE = "monatsgroesse"
KENNWERT = "kennwert"
SENSOR = "sensor"
EBENEN: tuple[str, ...] = (EINGABEFELD, MONATSGROESSE, KENNWERT, SENSOR)
#: Ebenen, deren Zeilen einen Hand-Eintrag mit ``abschnitt`` brauchen (oder in der Baseline stehen). Eingabefelder
#: nicht: alle ihre Spalten kommen aus Registry und Kanal-Katalog.
EBENEN_MIT_ABSCHNITT: tuple[str, ...] = (MONATSGROESSE, KENNWERT, SENSOR)
#: Erlaubte Felder eines Hand-Eintrags je Ebene (Bauplan §3).
HAND_FELDER: dict[str, frozenset[str]] = {
    EINGABEFELD: frozenset({"abschnitt", "test", "hinweis"}),
    MONATSGROESSE: frozenset({"abschnitt", "test", "code_ort", "hinweis"}),
    KENNWERT: frozenset({"abschnitt", "test", "backend_feld", "code_ort", "hinweis"}),
    SENSOR: frozenset({"abschnitt", "test", "code_ort", "hinweis"}),
}
#: Dateien, auf die ``abschnitt`` zeigen darf (und deren Anker Wächter (d) prüft).
ANKER_DATEIEN: tuple[str, ...] = ("BERECHNUNGEN.md", "SENSOR-REFERENZ.md")

EBENEN_TITEL: dict[str, str] = {
    EINGABEFELD: "Eingabefelder",
    MONATSGROESSE: "Monatsgrößen",
    KENNWERT: "Kennwerte der Tabelle",
    SENSOR: "HA-Export-Sensoren",
}


@dataclass(frozen=True)
class Zeile:
    """Eine Zeile der Übersicht.

    ``schluessel`` ist die Zeilen-Identität und zugleich der Schlüssel in ``groessen_hand.yaml``
    (``<typ>:<feld>`` · ``<Klasse>.<feld>`` · ``<key>`` · ``<key>``). Bei Eingabefeldern teilen sich die Arten einer
    `sonstiges`-Kategorie dieselbe Identität (wie ``FELD_BEDARF``) — die Spalte «Art» unterscheidet sie.
    """

    ebene: str
    schluessel: str
    sortierung: tuple[str, ...]
    werte: tuple[str, ...]
    #: abgeleiteter Code-Ort (``code_ort`` der Hand-Datei überschreibt ihn).
    code_ort: str = ""
    #: abgeleitetes Backend-Feld (nur Kennwerte; ``backend_feld`` der Hand-Datei füllt eine Lücke).
    backend_feld: str = ""
    hinweis: str = ""


@dataclass
class Quellen:
    """Die vier Quellen als austauschbare Leser — die Gegenprobe des Wächters reicht hier künstliche Einträge
    hinein, ohne Produktivcode oder Modulzustand umzubiegen."""

    eingabefelder: Callable[[], list[Zeile]]
    monatsgroessen: Callable[[], list[Zeile]]
    kennwerte: Callable[[], list[Zeile]]
    sensoren: Callable[[], list[Zeile]]


# ═══════════════════════════════════════════════════════════════════════════
# Ebene 1 — Eingabefelder (core/field_definitions/registry.py)
# ═══════════════════════════════════════════════════════════════════════════

#: Attribute, die eine eigene Spalte haben oder reine Darstellung sind — alles Übrige erscheint unter «Merkmale».
_EINGABE_EIGENE_SPALTE = frozenset({
    "feld", "key", "label", "einheit", "hinweis", "bedingung", "bedingung_basis", "bedingung_anlage", "weich",
    "csv_suffix", "csv_suffix_alt", "placeholder", "ha_domaenen", "label_wenn", "label_je_innengeraet",
})


def _registry_eintraege() -> Iterable[tuple[str, str, str, Mapping]]:
    """``(liste, typ, art, eintrag)`` über die sieben Registry-Listen; Anlagen-Ebene unter dem Typ ``basis``."""
    from backend.core.field_definitions import registry as reg

    for liste in ("BASIS_FELDER", "BEDINGTE_BASIS_FELDER", "OPTIONALE_FELDER"):
        for f in getattr(reg, liste):
            yield liste, "basis", "", f
    for typ, felder in reg.INVESTITION_FELDER.items():
        arten = felder.items() if isinstance(felder, dict) else (("", felder),)
        for art, liste_felder in arten:
            for f in liste_felder:
                yield "INVESTITION_FELDER", typ, art, f
    for typ, felder in reg.LIVE_FELDER_INV.items():
        for f in felder:
            yield "LIVE_FELDER_INV", typ, "", f
    for liste in ("BASIS_LIVE_FELDER", "BASIS_PREIS_FELDER"):
        for f in getattr(reg, liste):
            yield liste, "basis", "", f


def _kanal_index() -> dict[tuple[str, Optional[str], str], object]:
    from backend.services.kanal import katalog as kat

    return {(z.liste, z.typ, z.feld): z for z in kat.zuweisungen()}


def _kanal_text(z) -> str:
    if z is None:
        return "keine Zuweisung"
    if z.art:
        return f"`{z.art}` `{z.schluessel}` — {z.grund}"
    return f"kein Kanal (`{z.ausnahme}`) — {z.grund}"


def _bedingung_text(f: Mapping) -> str:
    teile = []
    if f.get("bedingung"):
        teile.append(f"`{f['bedingung']}`" + (" (weich)" if f.get("weich") else ""))
    if f.get("bedingung_basis"):
        teile.append(f"Anlage: `{f['bedingung_basis']}`")
    if f.get("bedingung_anlage"):
        teile.append(f"Anlage: `{f['bedingung_anlage']}`")
    return " · ".join(teile)


def _merkmale_text(f: Mapping) -> str:
    teile = []
    for name in sorted(k for k in f if k not in _EINGABE_EIGENE_SPALTE):
        wert = f[name]
        if wert is True:
            teile.append(f"`{name}`")
        elif isinstance(wert, (str, int, float)) and wert is not False:
            teile.append(f"`{name}={wert}`")
    if f.get("je_innengeraet"):
        teile.append("je Innengerät `<feld>-<id>`")
    return " · ".join(teile)


def _bedarf_text(typ: str, feld: str) -> str:
    from backend.core.field_definitions import get_feld_bedarf

    bedarf, gruppe = get_feld_bedarf(typ, feld)
    return f"{bedarf} ({gruppe})" if gruppe else bedarf


def eingabefeld_zeilen() -> list[Zeile]:
    """106 Zeilen (Stand 7.11.2026): eine je Registry-Eintrag; Identität ``<typ>:<feld>``."""
    from backend.services.kanal import katalog as kat

    listen_name = {
        "BASIS_FELDER": kat.L_BASIS, "BEDINGTE_BASIS_FELDER": kat.L_BEDINGT, "OPTIONALE_FELDER": kat.L_OPTIONAL,
        "INVESTITION_FELDER": kat.L_INV, "LIVE_FELDER_INV": kat.L_LIVE_INV,
        "BASIS_LIVE_FELDER": kat.L_LIVE_BASIS, "BASIS_PREIS_FELDER": kat.L_PREIS,
    }
    kanal = _kanal_index()
    zeilen = []
    for liste, typ, art, f in _registry_eintraege():
        feld = f.get("feld") or f["key"]
        z = kanal.get((listen_name[liste], None if typ == "basis" else typ, feld))
        zeilen.append(Zeile(
            ebene=EINGABEFELD, schluessel=f"{typ}:{feld}", sortierung=(typ, feld, liste, art),
            werte=(f"`{typ}`" + (f" / `{art}`" if art else ""), f"`{feld}`", f"`{liste}`", f.get("label", ""),
                   f.get("einheit", ""), _bedarf_text(typ, feld), _kanal_text(z), _bedingung_text(f),
                   _merkmale_text(f), f.get("hinweis", "")),
        ))
    return zeilen


# ═══════════════════════════════════════════════════════════════════════════
# Ebene 2 — Monatsgrößen (services/monats_fakten/fakten.py + fakten_wp.py)
# ═══════════════════════════════════════════════════════════════════════════


def fakten_klassen() -> list[type]:
    """Die frozen Dataclasses der Fakten-Schicht, in Quellreihenfolge."""
    import inspect

    from backend.services.monats_fakten import fakten, fakten_wp

    klassen = []
    for modul in (fakten, fakten_wp):
        for _name, obj in inspect.getmembers(modul, inspect.isclass):
            if dataclasses.is_dataclass(obj) and obj.__module__ == modul.__name__:
                klassen.append(obj)
    return sorted(klassen, key=lambda k: k.__name__)


def _typ_text(hint) -> Optional[str]:
    """Darstellung eines Zeilen-Typs — ``None`` für Typen, die keine Zeile sind (bool, str, Container, ORM)."""
    if hint is float or hint is int:
        return hint.__name__
    if hint == Optional[float]:
        return "float oder None"
    if hint == Optional[int]:
        return "int oder None"
    if hint == dict[int, float]:
        return "dict[int, float] je Gerät"
    return None


def _quelltext_monats_fakten() -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(MONATS_FAKTEN_DIR.glob("*.py"))}


class _FunktionsSammler(ast.NodeVisitor):
    """Sammelt je Knoten-Art Fundstellen mit dem innersten umschließenden Funktionsnamen (oder dem Ziel einer
    Modul-Zuweisung)."""

    def __init__(self) -> None:
        self.stapel: list[str] = []
        self.aufrufe: list[tuple[str, ast.Call]] = []
        self.schluessel: list[tuple[str, str]] = []

    def _ort(self) -> str:
        return self.stapel[-1] if self.stapel else "<modul>"

    def visit_FunctionDef(self, node) -> None:  # noqa: N802 — ast.NodeVisitor-Vertrag
        self.stapel.append(node.name)
        self.generic_visit(node)
        self.stapel.pop()

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        modulebene = not self.stapel and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
        if modulebene:
            self.stapel.append(node.targets[0].id)
        for ziel in node.targets:
            if isinstance(ziel, ast.Subscript) and isinstance(ziel.slice, ast.Constant):
                self._merke(ziel.slice.value)
        self.generic_visit(node)
        if modulebene:
            self.stapel.pop()

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        self.aufrufe.append((self._ort(), node))
        if _aufruf_name(node) == "dict":
            for kw in node.keywords:
                self._merke(kw.arg)
        self.generic_visit(node)

    def visit_Dict(self, node: ast.Dict) -> None:  # noqa: N802
        for k in node.keys:
            if isinstance(k, ast.Constant):
                self._merke(k.value)
        self.generic_visit(node)

    def _merke(self, wert) -> None:
        if isinstance(wert, str):
            self.schluessel.append((self._ort(), wert))


def _aufruf_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return ""


def _sammle(quelltext: str) -> _FunktionsSammler:
    sammler = _FunktionsSammler()
    sammler.visit(ast.parse(quelltext))
    return sammler


def bau_funktionen(klassen_namen: Iterable[str]) -> dict[tuple[str, str], list[str]]:
    """``(Klasse, feld)`` → Fundstellen ``<datei>::<funktion>`` jedes Konstruktor-Keywords in ``monats_fakten/*.py``.

    Ein Feld, das nur über ``dataclasses.replace`` gesetzt wird, hat hier keinen Ort (Stand 7.11.: zwei).
    """
    namen = set(klassen_namen)
    orte: dict[tuple[str, str], set[str]] = defaultdict(set)
    for datei, text in _quelltext_monats_fakten().items():
        for ort, call in _sammle(text).aufrufe:
            if _aufruf_name(call) not in namen:
                continue
            for kw in call.keywords:
                if kw.arg:
                    orte[(_aufruf_name(call), kw.arg)].add(f"monats_fakten/{datei}::{ort}")
    return {k: sorted(v) for k, v in orte.items()}


_ABKUERZUNG = re.compile(r"(?:\b(?:z|d|u|o|s|v|ggf|bzw|inkl|exkl|vgl|ca|Nr|max|min|evtl|usw|etc|bspw|Ø))\.$")


def erstsatz(text: str) -> str:
    """Der erste Satz eines Kommentars — endet an «. » vor einem Großbuchstaben/Zeichen, nicht nach einer Abkürzung."""
    text = " ".join(text.split())
    for m in re.finditer(r"[.!?](?=\s+[A-ZÄÖÜ„«»(`*⚠⭐⛔])", text):
        if not _ABKUERZUNG.search(text[: m.end()]):
            return text[: m.end()]
    return text


def feld_kommentare(quelltext: str) -> dict[tuple[str, str], str]:
    """``(Klasse, feld)`` → zusammengefügter ``#:``-Kommentarblock direkt über der Feld-Annotation."""
    zeilen = quelltext.splitlines()
    out: dict[tuple[str, str], str] = {}
    for klasse in (n for n in ast.parse(quelltext).body if isinstance(n, ast.ClassDef)):
        for knoten in klasse.body:
            if not (isinstance(knoten, ast.AnnAssign) and isinstance(knoten.target, ast.Name)):
                continue
            block: list[str] = []
            i = knoten.lineno - 2
            while i >= 0 and zeilen[i].strip().startswith("#:"):
                block.insert(0, zeilen[i].strip()[2:].strip())
                i -= 1
            if block:
                out[(klasse.name, knoten.target.id)] = " ".join(block)
    return out


def monatsgroessen_zeilen() -> list[Zeile]:
    """Numerische Felder und ``dict[int, float]`` je Gerät der Fakten-Klassen; Identität ``<Klasse>.<feld>``."""
    klassen = fakten_klassen()
    orte = bau_funktionen(k.__name__ for k in klassen)
    kommentare: dict[tuple[str, str], str] = {}
    for datei in ("fakten.py", "fakten_wp.py"):
        kommentare.update(feld_kommentare((MONATS_FAKTEN_DIR / datei).read_text(encoding="utf-8")))
    zeilen = []
    for klasse in klassen:
        hints = typing.get_type_hints(klasse)
        for f in dataclasses.fields(klasse):
            typ = _typ_text(hints[f.name])
            if typ is None:
                continue
            ort = " · ".join(f"`{o}`" for o in orte.get((klasse.__name__, f.name), []))
            zeilen.append(Zeile(
                ebene=MONATSGROESSE, schluessel=f"{klasse.__name__}.{f.name}",
                sortierung=(klasse.__name__, f.name),
                werte=(f"`{klasse.__name__}`", f"`{f.name}`", typ,
                       erstsatz(kommentare.get((klasse.__name__, f.name), ""))),
                code_ort=ort,
            ))
    return zeilen


# ═══════════════════════════════════════════════════════════════════════════
# Ebene 3 — Kennwerte der Tabelle (frontend/src/lib/werte/registry.ts, per Regex)
# ═══════════════════════════════════════════════════════════════════════════

_TS_EIGENSCHAFT = re.compile(r"(\w+):\s*('(?:[^'\\]|\\.)*'|[\w.]+)")
_TS_GRANULAR = re.compile(r"const (\w+): Granularitaet\[\] = \[([^\]]*)\]")


def _ts_eigenschaften(zeile: str) -> dict[str, str]:
    """Eigenschaften eines Objekt-Literals; ein ungequoteter Ausdruck mit Punkt (``e.bezeichnung``) bleibt als Code."""
    return {k: (v[1:-1] if v.startswith("'") else f"`{v}`" if "." in v else v)
            for k, v in _TS_EIGENSCHAFT.findall(zeile)}


def _granular_konstanten(ts: str) -> dict[str, tuple[str, ...]]:
    return {name: tuple(re.findall(r"'(\w+)'", inhalt)) for name, inhalt in _TS_GRANULAR.findall(ts)}


def _ts_block(ts: str, anfang: str, ende: str) -> str:
    start = ts.index(anfang) + len(anfang)
    return ts[start: ts.index(ende, start)]


def werte_metriken(ts: str) -> list[dict[str, object]]:
    """Die statischen Einträge von ``WERTE_METRIKEN`` (eine Objekt-Zeile je Eintrag, Kommentare übersprungen)."""
    granular = _granular_konstanten(ts)
    block = _ts_block(ts, "export const WERTE_METRIKEN: WerteMetrik[] = [", "\n]\n")
    metriken = []
    for zeile in block.splitlines():
        zeile = zeile.strip()
        if not zeile.startswith("{ key:"):
            continue
        m: dict[str, object] = dict(_ts_eigenschaften(zeile))
        m["granular"] = granular.get(str(m.get("granular")), ())
        metriken.append(m)
    return metriken


def werte_familien(ts: str) -> list[dict[str, object]]:
    """Die zwei dynamischen Familien (``erzeuger:<id>``, ``zaehler:<id>``) — je eine Zeile."""
    granular = _granular_konstanten(ts)
    familien = []
    for name, praefix_konst in (("erzeugerMetriken", "ERZEUGER_METRIK_PREFIX"),
                                ("zaehlerMetriken", "ZAEHLER_METRIK_PREFIX")):
        praefix = re.search(rf"export const {praefix_konst} = '([^']+)'", ts).group(1)
        rumpf = _ts_block(ts, f"export function {name}(", "}))")
        m: dict[str, object] = {k: v for k, v in _ts_eigenschaften(rumpf).items() if k != "key"}
        m["key"] = f"{praefix}<id>"
        m["granular"] = granular.get(str(m.get("granular")), ())
        m["familie"] = name
        familien.append(m)
    return familien


def tag_feld_abbildung(ts: str) -> dict[str, str]:
    """``TAG_FELD`` — Registry-Schlüssel, deren Tageswert unter einem anderen Feldnamen steht."""
    return dict(re.findall(r"(\w+): '(\w+)'", _ts_block(ts, "const TAG_FELD: Record<string, string> = {", "}")))


_TS_ALIAS = re.compile(r"^\s*const (\w+) = (md\.\w+|\w+)(?:\s*\?\?\s*(?:null|0))?\s*$")
_TS_RUECKGABE = re.compile(r"^\s*(\w+)(?::\s*(.+?))?,\s*(?://.*)?$")


def _alias_aufloesen(name: str, alias: Mapping[str, str]) -> Optional[str]:
    gesehen: set[str] = set()
    while name in alias and name not in gesehen:
        gesehen.add(name)
        name = alias[name]
    return name[3:] if name.startswith("md.") else None


def monats_backend_felder(ts: str) -> dict[str, str]:
    """Kennwert-Schlüssel → Feld der Monats-Antwort, aus ``createMonatsZeitreihe``.

    Ableitbar ist ``key: md.<feld>`` (auch ``?? null``/``?? 0``) und eine Kette reiner Aliase
    (``const x = md.<feld>``); eine Rechnung im Client ist es nicht — dort trägt ``groessen_hand.yaml`` das Feld.
    """
    rumpf = ts[ts.index("export function createMonatsZeitreihe("):]
    alias = {m.group(1): m.group(2) for m in map(_TS_ALIAS.match, rumpf.splitlines()) if m}
    rueckgabe = _ts_block(rumpf, "return {\n      name:", "\n    }\n")
    felder: dict[str, str] = {}
    for zeile in rueckgabe.splitlines():
        m = _TS_RUECKGABE.match(zeile)
        if not m:
            continue
        ausdruck = re.sub(r"\s*\?\?\s*(?:null|0)$", "", (m.group(2) or m.group(1)).strip())
        if re.fullmatch(r"md\.\w+|\w+", ausdruck):
            feld = _alias_aufloesen(ausdruck, alias)
            if feld:
                felder[m.group(1)] = feld
    return felder


def _schluessel_orte(pfade: Iterable[Path], *, mit_datei: bool) -> dict[str, list[str]]:
    orte: dict[str, set[str]] = defaultdict(set)
    for pfad in pfade:
        for ort, schl in _sammle(pfad.read_text(encoding="utf-8")).schluessel:
            orte[schl].add(f"{pfad.name}::{ort}" if mit_datei else ort)
    return {k: sorted(v) for k, v in orte.items()}


def _kennwert_monat(m: Mapping, felder: Mapping[str, str], bauer: Mapping[str, list[str]]) -> tuple[str, str]:
    feld = felder.get(str(m["key"]))
    if "monat" not in m["granular"] or m.get("familie"):
        return "", ""
    if not feld:
        return "", ""
    return feld, " · ".join(f"`monatsdaten_aggregiert.py::{f}`" for f in bauer.get(feld, []))


def _kennwert_tag(m: Mapping, tag_feld: Mapping[str, str], leser: Mapping[str, list[str]]) -> tuple[str, str]:
    if "tag" not in m["granular"] or m.get("familie"):
        return "", ""
    feld = tag_feld.get(str(m["key"]), str(m["key"]))
    if feld not in leser:
        return "", ""
    return feld, " · ".join(f"`{o}`" for o in leser[feld])


def _sicht_text(granular: Iterable[str]) -> str:
    return " + ".join({"monat": "Monat", "tag": "Tag"}[g] for g in granular)


def _fuss_text(m: Mapping) -> str:
    agg = str(m.get("aggregation", ""))
    return f"`{agg}` über `{m['gewicht']}`" if m.get("gewicht") else f"`{agg}`"


def _familien_hinweis(m: Mapping) -> str:
    if m.get("familie") == "erzeugerMetriken":
        return ("Familie: eine Spalte je PV-String/Balkonkraftwerk mit Tageswerten (`erzeugerMetriken`), "
                "Wert aus `TagWerte.erzeuger_kwh`.")
    if m.get("familie") == "zaehlerMetriken":
        return ("Familie: eine Spalte je Verbrauchszähler (`zaehlerMetriken`), Einheit je Gerät, "
                "Wert aus `zaehler_stand`.")
    return ""


def kennwert_zeilen() -> list[Zeile]:
    """74 statische Kennwerte + 2 Familien (Stand 7.11.2026); Identität ``<key>``."""
    ts = WERTE_REGISTRY_TS.read_text(encoding="utf-8")
    felder = monats_backend_felder(MONATS_ZEITREIHE_TS.read_text(encoding="utf-8"))
    bauer = _schluessel_orte([ZEILENBAUER_PY], mit_datei=False)
    leser = _schluessel_orte(TAGES_LESER_PY, mit_datei=True)
    tag_feld = tag_feld_abbildung(ts)
    zeilen = []
    for m in werte_metriken(ts) + werte_familien(ts):
        monat_feld, monat_ort = _kennwert_monat(m, felder, bauer)
        tag_f, tag_ort = _kennwert_tag(m, tag_feld, leser)
        zeilen.append(Zeile(
            ebene=KENNWERT, schluessel=str(m["key"]), sortierung=(str(m.get("gruppe", "")), str(m["key"])),
            werte=(f"`{m.get('gruppe', '')}`", f"`{m['key']}`", str(m.get("label", "")), str(m.get("unit", "")),
                   _sicht_text(m["granular"]), _fuss_text(m) + (" · `tagMitWaerme`" if m.get("tagMitWaerme") == "true"
                                                              else ""),
                   f"`{tag_f}`" if tag_f else "", tag_ort),
            code_ort=monat_ort, backend_feld=monat_feld, hinweis=_familien_hinweis(m),
        ))
    return zeilen


# ═══════════════════════════════════════════════════════════════════════════
# Ebene 4 — HA-Export-Sensoren (services/ha_sensors_export.py)
# ═══════════════════════════════════════════════════════════════════════════


def sensor_definitionen() -> list:
    from backend.services.ha_sensors_export import get_all_sensor_definitions

    return get_all_sensor_definitions()


def _klassen_text(s) -> str:
    teile = [f"`{s.komponente}`"]
    teile += [f"`{w}`" for w in (s.device_class, s.state_class, s.entity_category) if w]
    return " · ".join(teile)


def sensor_zeilen() -> list[Zeile]:
    """86 Export-Sensoren (Stand 7.11.2026); Identität ``<key>``."""
    zeilen = []
    for s in sensor_definitionen():
        kategorie = getattr(s.category, "value", str(s.category))
        zeilen.append(Zeile(
            ebene=SENSOR, schluessel=s.key, sortierung=(kategorie, s.key),
            werte=(f"`{kategorie}`", f"`{s.key}`", s.name, s.unit or "", _klassen_text(s), s.formel),
        ))
    return zeilen


def produktiv_quellen() -> Quellen:
    return Quellen(eingabefelder=eingabefeld_zeilen, monatsgroessen=monatsgroessen_zeilen,
                   kennwerte=kennwert_zeilen, sensoren=sensor_zeilen)


def alle_zeilen(quellen: Optional[Quellen] = None) -> dict[str, list[Zeile]]:
    """Je Ebene die Zeilen, sortiert nach Gruppe/Typ, dann Schlüssel."""
    q = quellen or produktiv_quellen()
    roh = {EINGABEFELD: q.eingabefelder(), MONATSGROESSE: q.monatsgroessen(), KENNWERT: q.kennwerte(),
           SENSOR: q.sensoren()}
    return {ebene: sorted(zeilen, key=lambda z: z.sortierung) for ebene, zeilen in roh.items()}


# ═══════════════════════════════════════════════════════════════════════════
# Überschriften und Anker (github-slugger, wie rehype-slug in MarkdownDoc.tsx und die Website)
# ═══════════════════════════════════════════════════════════════════════════

#: Zeichenklassen, die github-slugger behält (Buchstaben, Ziffern, Marken, Verbinder) — alles andere fällt außer
#: Leerzeichen und Bindestrich weg; Leerzeichen werden zu Bindestrichen.
_SLUG_BEHALTEN = ("Lu", "Ll", "Lt", "Lm", "Lo", "Nd", "Nl", "Mn", "Mc", "Me", "Pc")


def slug(text: str) -> str:
    """github-slugger ``slug()`` (v2): Kleinbuchstaben, Satz-/Symbolzeichen weg, Leerzeichen → ``-``."""
    behalten = "".join(c for c in text.lower() if c in " -" or unicodedata.category(c) in _SLUG_BEHALTEN)
    return behalten.replace(" ", "-")


_CODE_SPANNE = re.compile(r"(`+)(.+?)\1")
_ZEICHEN_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")


def ueberschrift_text(roh: str) -> str:
    """Der Text, den rehype-slug sieht: Code-Spannen wörtlich, Links als Linktext, Bilder und HTML-Tags leer."""
    roh = re.sub(r"\s+#+\s*$", "", roh.strip())
    roh = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", roh)
    roh = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", roh)
    teile = []
    letzte = 0
    for m in _CODE_SPANNE.finditer(roh):
        teile.append(_inline_text(roh[letzte:m.start()]))
        teile.append(m.group(2).strip() if m.group(2).strip() else m.group(2))
        letzte = m.end()
    teile.append(_inline_text(roh[letzte:]))
    return "".join(teile)


def _inline_text(s: str) -> str:
    s = re.sub(r"<[^>]+>", "", s)
    s = _ZEICHEN_ESCAPE.sub(r"\1", s)
    return html.unescape(s.replace("*", ""))


_ZAUN = re.compile(r"^\s{0,3}(?:>\s?)*\s{0,3}(`{3,}|~{3,})")
_UEBERSCHRIFT = re.compile(r"^\s{0,3}(?:>\s?)*\s{0,3}#{1,6}(?:\s+(.*?))?\s*$")
_SETEXT_LINIE = re.compile(r"^\s{0,3}(?:=+|-+)\s*$")
#: Zeilen, die keinen Absatz fortsetzen, der eine Setext-Überschrift tragen könnte (Liste, Tabelle, Zitat, Einzug).
_KEIN_ABSATZ = re.compile(r"^(?:\s{4,}|\s{0,3}(?:[-*+]|\d+[.)])\s|\s*[|>])")


def ueberschriften(markdown: str) -> list[tuple[str, str]]:
    """``(Text, Slug)`` je Überschrift außerhalb von Code-Zäunen — ATX (auch in Blockquotes) und Setext (Absatz über
    ``---``/``===``). Doppelte Slugs bekommen ``-1``, ``-2`` … wie im github-slugger (ein Slugger je Dokument)."""
    vorkommen: dict[str, int] = {}
    texte: list[str] = []
    zaun: Optional[str] = None
    absatz: list[str] = []
    for zeile in markdown.splitlines():
        m = _ZAUN.match(zeile)
        if m or zaun is not None:
            zaun = _zaun_wechsel(zaun, m.group(1)) if m else zaun
            absatz = []
            continue
        text, absatz = _ueberschrift_der_zeile(zeile, absatz)
        if text is not None:
            texte.append(text)
    return [(t, _eindeutig(slug(t), vorkommen)) for t in texte]


def _ueberschrift_der_zeile(zeile: str, absatz: list[str]) -> tuple[Optional[str], list[str]]:
    """(Überschriftentext oder ``None``, neuer Absatz-Puffer) für eine Zeile außerhalb von Code-Zäunen."""
    u = _UEBERSCHRIFT.match(zeile)
    if u:
        return ueberschrift_text(u.group(1) or ""), []
    if _SETEXT_LINIE.match(zeile) and absatz:
        return ueberschrift_text(" ".join(absatz)), []
    if not zeile.strip() or _KEIN_ABSATZ.match(zeile):
        return None, []
    return None, absatz + [zeile.strip()]


def _zaun_wechsel(offen: Optional[str], marke: str) -> Optional[str]:
    if offen is None:
        return marke
    return None if marke[0] == offen[0] and len(marke) >= len(offen) else offen


def _eindeutig(basis: str, vorkommen: dict[str, int]) -> str:
    ergebnis = basis
    while ergebnis in vorkommen:
        vorkommen[basis] += 1
        ergebnis = f"{basis}-{vorkommen[basis]}"
    vorkommen[ergebnis] = 0
    return ergebnis


def anker_der_datei(pfad: Path) -> dict[str, str]:
    """Slug → Überschriftentext einer Markdown-Datei."""
    return {s: t for t, s in ueberschriften(pfad.read_text(encoding="utf-8"))}


_VERWEIS = re.compile(r"\b(BERECHNUNGEN\.md|SENSOR-REFERENZ\.md)#([^)\s\"'>]+)")


def anker_verweise(dateien: Iterable[Path]) -> list[tuple[str, int, str, str]]:
    """``(Datei, Zeile, Ziel-Datei, Anker)`` je Verweis auf BERECHNUNGEN/SENSOR-REFERENZ."""
    out = []
    for pfad in dateien:
        for nr, zeile in enumerate(pfad.read_text(encoding="utf-8").splitlines(), start=1):
            for m in _VERWEIS.finditer(zeile):
                out.append((pfad.name, nr, m.group(1), unquote(m.group(2))))
    return out


def verweis_dateien() -> list[Path]:
    """``docs/*.md`` und ``CHANGELOG.md`` — die Dateien, die Wächter (d) prüft."""
    return sorted(DOCS.glob("*.md")) + [CHANGELOG]


def tote_anker(verweise: Iterable[tuple[str, int, str, str]], anker: Mapping[str, Mapping[str, str]]) -> list[str]:
    return [f"{datei}:{nr} → {ziel}#{a}" for datei, nr, ziel, a in verweise if a not in anker.get(ziel, {})]


# ═══════════════════════════════════════════════════════════════════════════
# Hand-Datei, Baseline, Prüfungen
# ═══════════════════════════════════════════════════════════════════════════


def hand_lesen(pfad: Path = HAND) -> dict[str, dict[str, dict[str, str]]]:
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    return {ebene: dict(daten.get(ebene) or {}) for ebene in EBENEN} | {
        k: v for k, v in daten.items() if k not in EBENEN
    }


def hand_formfehler(hand: Mapping, zeilen: Mapping[str, list[Zeile]]) -> list[str]:
    """Unbekannte Ebene, unbekannter Schlüssel (keine Registry kennt ihn), unerlaubtes Feld."""
    fehler = [f"unbekannte Ebene `{e}` (erlaubt: {', '.join(EBENEN)})" for e in hand if e not in EBENEN]
    for ebene in EBENEN:
        bekannt = {z.schluessel for z in zeilen.get(ebene, [])}
        for schl, eintrag in (hand.get(ebene) or {}).items():
            if schl not in bekannt:
                fehler.append(f"{ebene}: `{schl}` — keine Registry kennt diesen Schlüssel")
            if not isinstance(eintrag, dict):
                fehler.append(f"{ebene}: `{schl}` — Eintrag ist kein Mapping")
                continue
            for name in sorted(set(eintrag) - HAND_FELDER[ebene]):
                fehler.append(f"{ebene}: `{schl}` — Feld `{name}` ist hier nicht erlaubt "
                              f"(erlaubt: {', '.join(sorted(HAND_FELDER[ebene]))})")
    return fehler


def _abschnitt_fehler(wert: str, anker: Mapping[str, Mapping[str, str]]) -> Optional[str]:
    datei, _, a = str(wert).partition("#")
    if datei not in ANKER_DATEIEN or not a:
        return f"`abschnitt: {wert}` — Form `<{'|'.join(ANKER_DATEIEN)}>#<anker>` erwartet"
    if a not in anker.get(datei, {}):
        return f"`abschnitt: {wert}` — keine Überschrift in docs/{datei} hat diesen Anker"
    return None


def _test_fehler(wert: str) -> Optional[str]:
    pfad, _, name = str(wert).partition("::")
    if pfad.startswith("GM "):
        gm = pfad[3:].strip()
        entwicklung = DOCS / "DEVELOPMENT.md"
        if entwicklung.exists() and f"`{gm}`" not in entwicklung.read_text(encoding="utf-8"):
            return f"`test: {wert}` — Golden Master `{gm}` steht nicht in docs/DEVELOPMENT.md"
        return None
    datei = EEDC / pfad
    if not datei.is_file():
        return f"`test: {wert}` — Datei eedc/{pfad} fehlt (Pfad relativ zu eedc/ oder `GM <name>`)"
    if name and name not in datei.read_text(encoding="utf-8"):
        return f"`test: {wert}` — `{name}` kommt in eedc/{pfad} nicht vor"
    return None


def _code_ort_fehler(wert: str) -> Optional[str]:
    import importlib

    ort, _, name = str(wert).partition("::")
    if ort.startswith("frontend/"):
        datei = EEDC / ort
        if not datei.is_file() or (name and name not in datei.read_text(encoding="utf-8")):
            return f"`code_ort: {wert}` — eedc/{ort} fehlt oder nennt `{name}` nicht"
        return None
    try:
        obj = importlib.import_module(ort)
        for teil in filter(None, name.split(".")):
            obj = getattr(obj, teil)
    except (ImportError, AttributeError) as e:
        return f"`code_ort: {wert}` — nicht auffindbar ({type(e).__name__}: {e})"
    return None


def hand_verweisfehler(hand: Mapping, anker: Mapping[str, Mapping[str, str]], *, mit_docs: bool) -> list[str]:
    """Wächter (b): jeder ``code_ort`` existiert, jeder ``test`` existiert, jeder ``abschnitt`` trifft eine
    Überschrift. Ohne ``docs/`` (Spiegel) werden die Abschnitte nicht geprüft."""
    fehler = []
    for ebene in EBENEN:
        for schl, eintrag in (hand.get(ebene) or {}).items():
            if not isinstance(eintrag, dict):
                continue
            meldungen = [
                _abschnitt_fehler(eintrag["abschnitt"], anker) if "abschnitt" in eintrag and mit_docs else None,
                _test_fehler(eintrag["test"]) if "test" in eintrag else None,
                _code_ort_fehler(eintrag["code_ort"]) if "code_ort" in eintrag else None,
            ]
            fehler += [f"{ebene}: `{schl}` — {m}" for m in meldungen if m]
    return fehler


def offene_schluessel(hand: Mapping, zeilen: Mapping[str, list[Zeile]]) -> list[str]:
    """``<ebene>:<schlüssel>`` jeder Zeile der Ebenen Monatsgröße/Kennwert/Sensor ohne ``abschnitt``."""
    offen = []
    for ebene in EBENEN_MIT_ABSCHNITT:
        eintraege = hand.get(ebene) or {}
        for z in zeilen[ebene]:
            if not (eintraege.get(z.schluessel) or {}).get("abschnitt"):
                offen.append(f"{ebene}:{z.schluessel}")
    return sorted(offen)


_BASELINE_KOPF = (
    "# Größen ohne Hand-Eintrag mit `abschnitt` (groessen_hand.yaml) — nur schrumpfend (Bauplan «Übersicht der Größen»).\n"
    f"# Neu schreiben (nach einem Hand-Eintrag): {BEFEHL_BASELINE}\n"
    "# Eine Zeile je Schlüssel: <ebene>:<schlüssel>, sortiert.\n"
)


def baseline_lesen(pfad: Path = BASELINE) -> list[str]:
    return [z.strip() for z in pfad.read_text(encoding="utf-8").splitlines() if z.strip() and not z.startswith("#")]


def baseline_text(offen: Iterable[str]) -> str:
    return _BASELINE_KOPF + "".join(f"{s}\n" for s in sorted(offen))


# ═══════════════════════════════════════════════════════════════════════════
# Darstellung
# ═══════════════════════════════════════════════════════════════════════════


def zelle(text: str) -> str:
    """Tabellenzelle: eine Zeile, ``|`` maskiert, ``<`` außerhalb von Code-Spannen als Entität (die In-App-Hilfe
    rendert mit rehype-raw — ``<id>`` wäre sonst ein HTML-Tag)."""
    text = " ".join(str(text).split()).replace("|", "\\|")
    teile, letzte = [], 0
    for m in _CODE_SPANNE.finditer(text):
        teile += [text[letzte:m.start()].replace("<", "&lt;"), m.group(0)]
        letzte = m.end()
    teile.append(text[letzte:].replace("<", "&lt;"))
    return "".join(teile) or "—"


def _regel_link(abschnitt: str, anker: Mapping[str, Mapping[str, str]]) -> str:
    if not abschnitt:
        return ""
    datei, _, a = abschnitt.partition("#")
    titel = anker.get(datei, {}).get(a, a)
    return f"[{datei.removesuffix('.md')}: {titel.replace('[', '(').replace(']', ')')}]({abschnitt})"


_KOEPFE: dict[str, tuple[str, ...]] = {
    EINGABEFELD: ("Typ / Art", "Feld", "Liste", "Label", "Einheit", "Bedarf", "Kanal", "Bedingung", "Merkmale",
                  "Hinweis (Registry)", "Regel", "Test", "Hinweis"),
    MONATSGROESSE: ("Klasse", "Feld", "Typ", "Erklärung (`#:`-Erstsatz)", "Bau-Funktion", "Regel", "Test",
                    "Hinweis"),
    KENNWERT: ("Gruppe", "Schlüssel", "Label", "Einheit", "Sicht", "Fuß", "Feld Tag", "Tages-Leser",
               "Feld Monat", "Zeilenbauer Monat", "Regel", "Test", "Hinweis"),
    SENSOR: ("Kategorie", "Schlüssel", "Name", "Einheit", "Klassen", "Formel", "Code-Ort", "Regel", "Test",
             "Hinweis"),
}


def _hand_spalten(z: Zeile, eintrag: Mapping[str, str], anker: Mapping[str, Mapping[str, str]]) -> tuple[str, ...]:
    code_ort = f"`{eintrag['code_ort']}`" if eintrag.get("code_ort") else z.code_ort
    backend_feld = eintrag.get("backend_feld") or z.backend_feld
    hinweis = " ".join(t for t in (z.hinweis, eintrag.get("hinweis", "")) if t)
    regel = _regel_link(eintrag.get("abschnitt", ""), anker)
    test = f"`{eintrag['test']}`" if eintrag.get("test") else ""
    if z.ebene == EINGABEFELD:
        return (regel, test, hinweis)
    if z.ebene == KENNWERT:
        return (f"`{backend_feld}`" if backend_feld else "", code_ort, regel, test, hinweis)
    return (code_ort, regel, test, hinweis)


def tabelle(ebene: str, zeilen: list[Zeile], hand: Mapping, anker: Mapping[str, Mapping[str, str]]) -> str:
    kopf = _KOEPFE[ebene]
    out = ["| " + " | ".join(kopf) + " |", "|" + "---|" * len(kopf)]
    eintraege = hand.get(ebene) or {}
    for z in zeilen:
        spalten = z.werte + _hand_spalten(z, eintraege.get(z.schluessel) or {}, anker)
        out.append("| " + " | ".join(zelle(s) for s in spalten) + " |")
    return "\n".join(out)


_EINLEITUNG = {
    EINGABEFELD: (
        "Was ein Anwender zuordnet oder einträgt — eine Zeile je Eintrag der Feld-Registry "
        "(`core/field_definitions/registry.py`: Basis-, bedingte, optionale, Investitions-, Live- und Preis-Felder). "
        "**Bedarf** aus `FELD_BEDARF` ohne Geräte-Kontext (`get_feld_bedarf`), **Kanal** aus dem Kanal-Katalog "
        "(`services/kanal/katalog.py`). Die Arten einer `sonstiges`-Kategorie teilen sich die Identität "
        "`<typ>:<feld>`."
    ),
    MONATSGROESSE: (
        "Was die Monats-Fakten (`services/monats_fakten/fakten.py`, `fakten_wp.py`) je Monat tragen — nur Zahlen "
        "und Zahlen je Gerät; Wahrheitswerte, Texte, Container und ORM-Objekte sind keine Zeile. **Bau-Funktion** "
        "ist die Stelle, an der der Konstruktor das Feld setzt (AST); leer, wo es nur über `dataclasses.replace` "
        "gesetzt wird."
    ),
    KENNWERT: (
        "Die Spalten der Werte-Tabelle (`frontend/src/lib/werte/registry.ts`, `WERTE_METRIKEN`) und die zwei "
        "dynamischen Familien. **Feld Monat** ist das Feld der Monats-Antwort, aus dem `createMonatsZeitreihe` "
        "(`pages/auswertung/types.ts`) den Wert liest; **Zeilenbauer** die Funktion in "
        "`api/routes/monatsdaten_aggregiert.py`, die es schreibt. **Feld Tag** und **Tages-Leser** stammen aus "
        "`services/energie_profil/tage_werte*.py`. Leer heißt: nicht ableitbar (Rechnung im Client oder kein "
        "Wert in dieser Sicht)."
    ),
    SENSOR: (
        "Die Sensoren, die eedc nach Home Assistant exportiert (`services/ha_sensors_export.py`, "
        "`get_all_sensor_definitions()`). **Formel** ist der Text der Definition."
    ),
}


def dokument(zeilen: Mapping[str, list[Zeile]], hand: Mapping, anker: Mapping[str, Mapping[str, str]]) -> str:
    teile = [
        "# Übersicht der Größen",
        "",
        f"> **Erzeugt — nicht von Hand ändern — `{BEFEHL}`.** Quelle ist der Code; die Spalten «Regel», «Test» "
        "und «Hinweis» kommen aus `eedc/backend/tests/groessen_hand.yaml`. Der Wächter "
        "`eedc/backend/tests/test_groessen_uebersicht.py` hält Datei, Hand-Datei und Registries gleich.",
        "",
        "Jeder Eintrag der vier Registries von eedc hat hier genau eine Zeile. Dieselbe Größe heißt je Ebene "
        "anders (Eingabefeld `pv_erzeugung_kwh` · Monatsgröße `ErzeugungFakten.pv_kwh` · Kennwert `erzeugung`); "
        "verknüpft wird über die Spalten «Bau-Funktion», «Feld Monat» und «Feld Tag», nicht über den Namen. "
        "Die Regeln stehen in der [Berechnungsreferenz](BERECHNUNGEN.md), die Sensoren und ihre Zuordnung in der "
        "[Sensor-Referenz](SENSOR-REFERENZ.md).",
        "",
        "| Ebene | Zeilen | davon mit Regel-Abschnitt |",
        "|---|---|---|",
    ]
    for ebene in EBENEN:
        mit = sum(1 for z in zeilen[ebene] if ((hand.get(ebene) or {}).get(z.schluessel) or {}).get("abschnitt"))
        teile.append(f"| {EBENEN_TITEL[ebene]} | {len(zeilen[ebene])} | {mit} |")
    teile += [
        "",
        "**Grenze der Kennwert-Ebene.** Kacheln von Cockpit, Komponenten-Hubs und Auswertungen stehen in keiner "
        "Registry und haben hier keine Zeile; die meisten ihrer Größen sind als Export-Sensor oder als Spalte der "
        "Werte-Tabelle vertreten. Innengeräte-Felder (`<feld>-<id>`) und die zwei dynamischen Kennwert-Familien "
        "(`erzeuger:<id>`, `zaehler:<id>`) stehen je einmal, nicht je Instanz.",
    ]
    for nr, ebene in enumerate(EBENEN, start=1):
        teile += ["", f"## {nr}. {EBENEN_TITEL[ebene]}", "", _EINLEITUNG[ebene], "",
                  tabelle(ebene, zeilen[ebene], hand, anker)]
    return "\n".join(teile) + "\n"


def anker_aller_zieldateien() -> dict[str, dict[str, str]]:
    return {d: anker_der_datei(DOCS / d) for d in ANKER_DATEIEN if (DOCS / d).exists()}


def erzeugen(quellen: Optional[Quellen] = None, hand: Optional[Mapping] = None) -> str:
    """Die Datei, wie sie aus Code und Hand-Datei entsteht. Bricht bei einer ungültigen Hand-Datei ab."""
    zeilen = alle_zeilen(quellen)
    hand = hand_lesen() if hand is None else hand
    fehler = hand_formfehler(hand, zeilen)
    if fehler:
        raise ValueError("groessen_hand.yaml ungültig:\n  " + "\n  ".join(fehler))
    return dokument(zeilen, hand, anker_aller_zieldateien())


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Übersicht der Größen erzeugen (docs/UEBERSICHT-GROESSEN.md).")
    gruppe = parser.add_mutually_exclusive_group()
    gruppe.add_argument("--schreiben", action="store_true", help="docs/UEBERSICHT-GROESSEN.md schreiben (Vorgabe)")
    gruppe.add_argument("--baseline", action="store_true", help="groessen_offen_baseline.txt neu schreiben")
    gruppe.add_argument("--pruefen", action="store_true", help="nur vergleichen; Exit 1 bei Abweichung")
    args = parser.parse_args(argv)
    if args.baseline:
        BASELINE.write_text(baseline_text(offene_schluessel(hand_lesen(), alle_zeilen())), encoding="utf-8")
        print(f"  {BASELINE.relative_to(REPO)} geschrieben")
        return 0
    text = erzeugen()
    if args.pruefen:
        gleich = ZIEL.exists() and ZIEL.read_text(encoding="utf-8") == text
        print(f"  {ZIEL.relative_to(REPO)}: {'aktuell' if gleich else 'VERALTET'}")
        return 0 if gleich else 1
    ZIEL.write_text(text, encoding="utf-8")
    print(f"  {ZIEL.relative_to(REPO)} geschrieben")
    return 0


if __name__ == "__main__":
    sys.exit(main())
