"""Übersicht der Größen — Erzeuger und Parser (Bauplan «Übersicht der Größen» §3, Stufen U1, U3 und U3b, 7./8.11.2026).

Schreibt ``docs/UEBERSICHT-GROESSEN.md``: jeder Eintrag der vier Registries von eedc bekommt genau eine Zeile.
Schreibt ``docs/SENSOR-REFERENZ.md`` (U3): Hand-Bausteine ``docs/sensor-referenz/NN-*.md`` in Namens-Reihenfolge, an
Markern die Tabellen der Eingabefelder und der Export-Sensoren — vollständig, jede Zeile genau einmal (Abschnitt
«SENSOR-REFERENZ» unten). Schreibt ``docs/MQTT_INBOUND.md`` (U3b): Bausteine ``docs/mqtt-inbound/NN-*.md``, an Markern
die Topic-Tabellen je Gerätetyp (Feld-Registry + Topic-Registry, Payload aus den MQTT-Lesern) und die Preset-Tabelle
(Abschnitt «MQTT_INBOUND»). Die Bausteine sind Quelle; die erzeugten Dateien werden nie von Hand geändert.

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

    scripts/groessen-uebersicht.sh              # UEBERSICHT-GROESSEN.md, SENSOR-REFERENZ.md, MQTT_INBOUND.md neu
    scripts/groessen-uebersicht.sh --baseline   # groessen_offen_baseline.txt neu schreiben (nur schrumpfend)
    scripts/groessen-uebersicht.sh --pruefen    # alle drei nur vergleichen, nichts schreiben (Exit 1 bei Abweichung)

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
from typing import Callable, ClassVar, Iterable, Mapping, Optional  # noqa: E402
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
#: Dateien, deren ``<Datei>#<anker>``-Verweise Wächter (d) prüft — dazu ``MQTT_INBOUND.md`` (U3b, erzeugt aus Bausteinen).
VERWEIS_DATEIEN: tuple[str, ...] = (*ANKER_DATEIEN, "MQTT_INBOUND.md")

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


_VERWEIS = re.compile(r"\b(" + "|".join(re.escape(d) for d in VERWEIS_DATEIEN) + r")#([^)\s\"'>]+)")


def anker_verweise(dateien: Iterable[Path]) -> list[tuple[str, int, str, str]]:
    """``(Datei, Zeile, Ziel-Datei, Anker)`` je Verweis auf BERECHNUNGEN/SENSOR-REFERENZ/MQTT_INBOUND."""
    out = []
    for pfad in dateien:
        for nr, zeile in enumerate(pfad.read_text(encoding="utf-8").splitlines(), start=1):
            for m in _VERWEIS.finditer(zeile):
                out.append((pfad.name, nr, m.group(1), unquote(m.group(2))))
    return out


def verweis_dateien() -> list[Path]:
    """``docs/*.md``, die Bausteine ``docs/sensor-referenz/*.md`` und ``docs/mqtt-inbound/*.md`` und ``CHANGELOG.md`` —
    die Dateien, die Wächter (d) prüft."""
    return (sorted(DOCS.glob("*.md")) + sorted((DOCS / "sensor-referenz").glob("*.md"))
            + sorted((DOCS / "mqtt-inbound").glob("*.md")) + [CHANGELOG])


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


# ═══════════════════════════════════════════════════════════════════════════
# SENSOR-REFERENZ (Stufe U3): Hand-Bausteine + erzeugte Tabellen an Markern
# ═══════════════════════════════════════════════════════════════════════════
#
# ``docs/SENSOR-REFERENZ.md`` = die Bausteine ``docs/sensor-referenz/NN-*.md`` in Namens-Reihenfolge; jede Marker-Zeile
# wird durch eine erzeugte Tabelle ersetzt, nach der H1 des ersten Bausteins steht die Kopfzeile. Zwei Marker-Arten:
#
#   <!-- erzeugt: eingabefelder typ=<typ>[,<typ>…] liste=monat|live [merkmal=<attr>|!<attr>] -->
#   <!-- erzeugt: export-sensoren kategorie=<kat>[,<kat>…] [komponente=sensor|binary_sensor] -->
#
# Totalität (Fehler beim Namen, ``sr_pruefung``): jede Eingabefeld-Zeile und jeder Export-Sensor steht in genau
# einem Marker; jede ``SensorCategory`` gehört genau einem Unterabschnitt (der letzten Überschrift über dem Marker);
# ein Marker ohne Zeilen und ein unbekannter Marker sind Fehler.

SR_ZIEL = DOCS / "SENSOR-REFERENZ.md"
SR_BAUSTEINE = DOCS / "sensor-referenz"
SR_KOPFZEILE = (
    f"> **Erzeugt — nicht von Hand ändern —** Bausteine in `docs/sensor-referenz/`, `{BEFEHL}`. Die Tabellen der "
    "Eingabefelder (§1–§7) und der Export-Sensoren (§11) kommen aus dem Code; ihre Spalte «Hinweise» bei den "
    "Export-Sensoren aus `eedc/backend/tests/groessen_hand.yaml`."
)
_MARKER = re.compile(r"^<!-- erzeugt: (?P<art>\S+)(?P<param>(?: [a-z_]+=\S+)*) -->\s*$")
_MARKER_ANFANG = "<!-- erzeugt:"
MARKER_EINGABE = "eingabefelder"
MARKER_EXPORT = "export-sensoren"
_MARKER_PARAMETER: dict[str, frozenset[str]] = {
    MARKER_EINGABE: frozenset({"typ", "liste", "merkmal"}),
    MARKER_EXPORT: frozenset({"kategorie", "komponente"}),
}
_MARKER_PFLICHT: dict[str, frozenset[str]] = {
    MARKER_EINGABE: frozenset({"typ", "liste"}),
    MARKER_EXPORT: frozenset({"kategorie"}),
}
#: Registry-Liste → Tabelle «monat» oder «live» (die Preis-Felder stehen bei den Live-Feldern der Anlage).
_SR_LISTE: dict[str, str] = {
    "BASIS_FELDER": "monat", "BEDINGTE_BASIS_FELDER": "monat", "OPTIONALE_FELDER": "monat",
    "INVESTITION_FELDER": "monat", "LIVE_FELDER_INV": "live", "BASIS_LIVE_FELDER": "live",
    "BASIS_PREIS_FELDER": "live",
}


@dataclass(frozen=True)
class SrFeld:
    """Eine Eingabefeld-Zeile der SENSOR-REFERENZ (eine je Registry-Eintrag, wie in der Übersicht)."""

    typ: str
    art: str
    feld: str
    liste: str
    eintrag: Mapping = field(compare=False, hash=False)
    kanal: object = field(default=None, compare=False, hash=False)

    @property
    def name(self) -> str:
        return f"{self.typ}:{self.feld}" + (f" ({self.art})" if self.art else "")


def sr_eingabefelder() -> list[SrFeld]:
    """Alle Registry-Einträge in Quellreihenfolge, mit Kanal-Zuweisung (Naht für die Gegenproben)."""
    from backend.services.kanal import katalog as kat

    listen_name = {
        "BASIS_FELDER": kat.L_BASIS, "BEDINGTE_BASIS_FELDER": kat.L_BEDINGT, "OPTIONALE_FELDER": kat.L_OPTIONAL,
        "INVESTITION_FELDER": kat.L_INV, "LIVE_FELDER_INV": kat.L_LIVE_INV,
        "BASIS_LIVE_FELDER": kat.L_LIVE_BASIS, "BASIS_PREIS_FELDER": kat.L_PREIS,
    }
    kanal = _kanal_index()
    out = []
    for liste, typ, art, f in _registry_eintraege():
        feld = f.get("feld") or f["key"]
        out.append(SrFeld(typ, art, feld, liste, f, kanal.get((listen_name[liste], None if typ == "basis" else typ, feld))))
    return out


# ── Sensortyp aus der Kanal-Art (Auftrag U3 §2, Entscheid Master H2) ────────
#
# Reihenfolge = Vorrang. ``nur_manuell`` (nicht zuordenbar, Katalog O5) entscheidet vor jeder Kanal-Art. Die Texte
# der vom Auftrag nicht benannten Arten folgen dem Katalog-Text (``services/kanal/katalog.py``):
#   stand                    «Stand-Feld … Δ des Standes, ohne Reset-Regel» / «Zählwerk … Bestandsgröße»
#   nur_live_anzeige         «Wert live aus der Integration, nichts gespeichert — reine Anzeige»
#   mean + Registry `zustand` «Zustand ⇒ Mitschrift» / «Betriebsart ⇒ Mitschrift» (kein Messwert)
#   tagesgroesse_ohne_kanal  «V2H ist eine Tagesgröße aus dem Zählerpfad (Snapshot/HA-Langzeitstatistik)»
#   snapshot_ausnahme        «Abschluss-Felder» — zuordenbar, aber nur als Monatswert, kein Stunden-/Tageskanal
SENSORTYP_MANUELL = "kein Sensor — manuell/Import"
_SENSORTYP_ART: dict[str, str] = {
    "sum": "Kumulativ oder Tagessensor",
    "mean": "Momentanwert",
    "stand": "Zählerstand (kumulativ)",
}
_SENSORTYP_AUSNAHME: dict[str, str] = {
    "abschluss_ohne_sensor": "kein Sensor — Monatsabschluss",
    "snapshot_ausnahme": "Kumulativ — nur Monatswert, kein Kanal",
    "tagesgroesse_ohne_kanal": "Kumulativ oder Tagessensor — Tagesgröße ohne Kanal",
    "nur_live_anzeige": "Momentanwert — nur Anzeige",
}


def sr_sensortyp(f: SrFeld) -> Optional[str]:
    """Sensortyp-Text eines Eingabefelds; ``None``, wo die Kanal-Art unbekannt ist (Zelle «—»)."""
    z = f.kanal
    if f.eintrag.get("nur_manuell"):
        return SENSORTYP_MANUELL
    if z is None:
        return None
    if z.ausnahme == "nur_live_anzeige" and f.eintrag.get("zustand"):
        return ("Text" if f.eintrag.get("text") else "Zustand") + " — nur Anzeige"
    if z.ausnahme:
        return _SENSORTYP_AUSNAHME.get(z.ausnahme)
    if z.art == "mean" and f.eintrag.get("zustand"):
        return "Zustand"
    return _SENSORTYP_ART.get(z.art)


#: Grund für eine leere Spalte «Sichten» bei den Handeingaben (``feld_auswertungen.alle_registry_felder``: «reine
#: Handeingaben ohne Quelle; sie stehen nie auf der Zuordnungs-Fläche»).
_SICHTEN_OPTIONAL = "— Handeingabe im Monatsabschluss, nicht auf der Zuordnungs-Fläche"


def sr_sichten(f: SrFeld) -> str:
    """Die Sichten aus ``core/feld_auswertungen.py`` (dieselbe Liste wie «ausgewertet in» der Zuordnungs-Fläche)."""
    from backend.core.feld_auswertungen import FELDER_OHNE_AUSWERTUNG_BEKANNT, sichten_fuer

    sichten = sichten_fuer(f.typ, f.feld)
    if sichten:
        return " · ".join(sichten)
    if (f.typ, f.feld) in FELDER_OHNE_AUSWERTUNG_BEKANNT:
        return f"— {FELDER_OHNE_AUSWERTUNG_BEKANNT[(f.typ, f.feld)]}"
    return _SICHTEN_OPTIONAL if f.liste == "OPTIONALE_FELDER" else "—"


def _sr_label(f: SrFeld) -> str:
    label = str(f.eintrag.get("label", ""))
    for bedingung, anders in sorted((f.eintrag.get("label_wenn") or {}).items()):
        label += f" — mit `{bedingung}`: «{anders}»"
    return label


def _sr_einheit(f: SrFeld) -> str:
    if f.eintrag.get("einheit_je_geraet"):
        return f"vom Gerät (`{f.eintrag['einheit_je_geraet']}`)"
    return str(f.eintrag.get("einheit", ""))


def _sr_feld_zelle(f: SrFeld) -> str:
    zelle_ = f"`{f.feld}`"
    return zelle_ + (f" · je Innengerät zusätzlich `{f.feld}-<id>`" if f.eintrag.get("je_innengeraet") else "")


# ── Marker ──────────────────────────────────────────────────────────────────


def marker_lesen(zeile: str, erlaubt: Optional[Mapping[str, frozenset[str]]] = None,
                 pflicht: Optional[Mapping[str, frozenset[str]]] = None) -> Optional[tuple[str, dict[str, str]]]:
    """``(art, parameter)`` einer Marker-Zeile; ``None`` für jede andere Zeile. Eine Zeile, die wie ein Marker
    beginnt, aber nicht passt, ist ein Fehler (``ValueError``). ``erlaubt``/``pflicht``: die Marker-Arten des Dokuments
    (Vorgabe: die der SENSOR-REFERENZ)."""
    erlaubt = _MARKER_PARAMETER if erlaubt is None else erlaubt
    pflicht = _MARKER_PFLICHT if pflicht is None else pflicht
    if not zeile.lstrip().startswith(_MARKER_ANFANG):
        return None
    m = _MARKER.match(zeile.strip())
    if not m or m.group("art") not in erlaubt:
        raise ValueError(f"unbekannter Marker: {zeile.strip()}")
    param = dict(p.split("=", 1) for p in m.group("param").split())
    unbekannt = sorted(set(param) - erlaubt[m.group("art")])
    fehlend = sorted(pflicht[m.group("art")] - set(param))
    if unbekannt or fehlend:
        raise ValueError(f"Marker {zeile.strip()}: unbekannte Parameter {unbekannt}, fehlende {fehlend}")
    return m.group("art"), param


def _merkmal_passt(f: SrFeld, merkmal: Optional[str]) -> bool:
    if not merkmal:
        return True
    if merkmal.startswith("!"):
        return not f.eintrag.get(merkmal[1:])
    return bool(f.eintrag.get(merkmal))


def sr_felder_des_markers(felder: Iterable[SrFeld], param: Mapping[str, str]) -> list[SrFeld]:
    """Die Zeilen eines Eingabefeld-Markers: Typen in Marker-Reihenfolge, je Typ in Registry-Reihenfolge."""
    typen = param["typ"].split(",")
    auswahl = [f for f in felder if f.typ in typen and _SR_LISTE[f.liste] == param["liste"]
               and _merkmal_passt(f, param.get("merkmal"))]
    return sorted(auswahl, key=lambda f: typen.index(f.typ))


def sr_sensoren_des_markers(sensoren: Iterable, param: Mapping[str, str]) -> list:
    """Die Zeilen eines Export-Markers in Definitions-Reihenfolge."""
    kategorien = param["kategorie"].split(",")
    komponente = param.get("komponente")
    return [s for s in sensoren if _kategorie(s) in kategorien and (not komponente or s.komponente == komponente)]


def _kategorie(s) -> str:
    return getattr(s.category, "value", str(s.category))


# ── Tabellen ────────────────────────────────────────────────────────────────


def sr_eingabe_tabelle(zeilen: list[SrFeld]) -> str:
    """Feld · Label · Einheit · Sensortyp · Bedarf · Hinweis · Sichten · Bedingung — mit «Typ» bei mehr als einem
    Typ und «Art» bei den Arten von `sonstiges`."""
    mit_typ = len({f.typ for f in zeilen}) > 1
    mit_art = any(f.art for f in zeilen)
    kopf = (["Typ"] if mit_typ else []) + (["Art"] if mit_art else []) + [
        "Feld", "Label", "Einheit", "Sensortyp", "Bedarf", "Hinweis", "Sichten", "Bedingung"]
    out = ["| " + " | ".join(kopf) + " |", "|" + "---|" * len(kopf)]
    for f in zeilen:
        spalten = ([f"`{f.typ}`"] if mit_typ else []) + ([f"`{f.art}`"] if mit_art else []) + [
            _sr_feld_zelle(f), _sr_label(f), _sr_einheit(f), sr_sensortyp(f) or "", _bedarf_text(f.typ, f.feld),
            str(f.eintrag.get("hinweis", "")), sr_sichten(f), _bedingung_text(f.eintrag)]
        out.append("| " + " | ".join(zelle(s) for s in spalten) + " |")
    return "\n".join(out)


def _sr_regel_link(abschnitt: str, anker: Mapping[str, Mapping[str, str]]) -> str:
    """Regel-Link wie in der Übersicht; ein Abschnitt der SENSOR-REFERENZ selbst als ``#anker``."""
    datei, _, a = abschnitt.partition("#")
    if datei != "SENSOR-REFERENZ.md":
        return _regel_link(abschnitt, anker)
    titel = anker.get(datei, {}).get(a, a)
    return f"[§ {titel.replace('[', '(').replace(']', ')')}](#{a})"


def sr_sensor_tabelle(sensoren: list, hand: Mapping, anker: Mapping[str, Mapping[str, str]]) -> str:
    """Schlüssel · Name · Einheit · Klassen · Formel · Regel · Hinweise (Hand-Datei ``hinweis``)."""
    kopf = ("Schlüssel", "Name", "Einheit", "Klassen", "Formel", "Regel", "Hinweise")
    out = ["| " + " | ".join(kopf) + " |", "|" + "---|" * len(kopf)]
    eintraege = hand.get(SENSOR) or {}
    for s in sensoren:
        e = eintraege.get(s.key) or {}
        regel = _sr_regel_link(e["abschnitt"], anker) if e.get("abschnitt") else ""
        hinweis = str(e.get("hinweis", "")).replace("](SENSOR-REFERENZ.md#", "](#")
        spalten = (f"`{s.key}`", s.name, s.unit or "", _klassen_text(s), s.formel, regel, hinweis)
        out.append("| " + " | ".join(zelle(x) for x in spalten) + " |")
    return "\n".join(out)


# ── Zusammensetzen und Prüfen ───────────────────────────────────────────────


def sr_bausteine_lesen(verzeichnis: Path = SR_BAUSTEINE) -> list[tuple[str, str]]:
    """``(Dateiname, Text)`` je Baustein in Namens-Reihenfolge."""
    return [(p.name, p.read_text(encoding="utf-8")) for p in sorted(verzeichnis.glob("*.md"))]


@dataclass
class _SrLauf:
    """Zustand eines Zusammensetz-Laufs: verbrauchte Zeilen, Kategorie → Unterabschnitt, Fehler."""

    marker_erlaubt: ClassVar[Mapping[str, frozenset[str]]] = _MARKER_PARAMETER
    marker_pflicht: ClassVar[Mapping[str, frozenset[str]]] = _MARKER_PFLICHT

    felder: list[SrFeld]
    sensoren: list
    hand: Mapping
    anker: Mapping[str, Mapping[str, str]]
    feld_marker: dict[int, list[str]] = field(default_factory=lambda: defaultdict(list))
    sensor_marker: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    kategorie_abschnitt: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    fehler: list[str] = field(default_factory=list)

    def tabelle(self, ort: str, abschnitt: str, art: str, param: Mapping[str, str]) -> str:
        if art == MARKER_EINGABE:
            zeilen = sr_felder_des_markers(self.felder, param)
            for f in zeilen:
                self.feld_marker[id(f)].append(ort)
            text = sr_eingabe_tabelle(zeilen) if zeilen else ""
        else:
            zeilen = sr_sensoren_des_markers(self.sensoren, param)
            for kat in param["kategorie"].split(","):
                self.kategorie_abschnitt[kat].add(abschnitt)
            for s in zeilen:
                self.sensor_marker[s.key].append(ort)
            text = sr_sensor_tabelle(zeilen, self.hand, self.anker) if zeilen else ""
        if not zeilen:
            self.fehler.append(f"{ort}: Marker ohne Zeilen ({art} {dict(param)})")
        return text

    def totalitaet(self) -> None:
        for f in self.felder:
            orte = self.feld_marker.get(id(f), [])
            if len(orte) != 1:
                self.fehler.append(f"Eingabefeld {f.name} ({f.liste}) steht in {len(orte)} Markern {orte} — Soll: genau einem")
        for s in self.sensoren:
            orte = self.sensor_marker.get(s.key, [])
            if len(orte) != 1:
                self.fehler.append(f"Export-Sensor `{s.key}` (Kategorie `{_kategorie(s)}`) steht in {len(orte)} Markern "
                                   f"{orte} — Soll: genau einem")
        for kat in sorted({_kategorie(s) for s in self.sensoren}):
            abschnitte = sorted(self.kategorie_abschnitt.get(kat, set()))
            if len(abschnitte) != 1:
                self.fehler.append(f"Kategorie `{kat}` gehört zu {len(abschnitte)} Unterabschnitten {abschnitte} — Soll: "
                                   "genau einem (ein Marker `kategorie=` darunter)")


def _sr_zusammensetzen(bausteine: list[tuple[str, str]], lauf: _SrLauf) -> str:
    return _zusammensetzen(bausteine, lauf, SR_KOPFZEILE)


def _zusammensetzen(bausteine: list[tuple[str, str]], lauf, kopfzeile: str) -> str:
    """Bausteine in Reihenfolge; jede Marker-Zeile wird durch ``lauf.tabelle(ort, abschnitt, art, param)`` ersetzt,
    nach der ersten H1 steht ``kopfzeile``. Fehler sammelt ``lauf.fehler``."""
    teile: list[str] = []
    abschnitt = ""
    kopf_gesetzt = False
    zaun: Optional[str] = None
    for name, text in bausteine:
        for nr, zeile in enumerate(text.splitlines(), start=1):
            z = _ZAUN.match(zeile)
            zaun = _zaun_wechsel(zaun, z.group(1)) if z else zaun
            u = _UEBERSCHRIFT.match(zeile) if zaun is None and not z else None
            if u:
                abschnitt = ueberschrift_text(u.group(1) or "")
            try:
                marker = marker_lesen(zeile, lauf.marker_erlaubt, lauf.marker_pflicht)
            except ValueError as e:
                lauf.fehler.append(f"{name}:{nr}: {e}")
                continue
            if marker:
                teile.append(lauf.tabelle(f"{name}:{nr}", abschnitt, *marker))
                continue
            teile.append(zeile)
            if not kopf_gesetzt and zeile.startswith("# "):
                teile += ["", kopfzeile]
                kopf_gesetzt = True
    if not kopf_gesetzt:
        lauf.fehler.append("kein Baustein beginnt mit einer H1 — die Kopfzeile hat keinen Platz")
    return "\n".join(teile) + "\n"


def sr_pruefung_und_text(bausteine: Optional[list[tuple[str, str]]] = None, felder: Optional[list[SrFeld]] = None,
                         sensoren: Optional[list] = None, hand: Optional[Mapping] = None,
                         anker: Optional[Mapping[str, Mapping[str, str]]] = None) -> tuple[list[str], str]:
    """``(Fehler, Text)`` der SENSOR-REFERENZ; jede Quelle austauschbar (Gegenproben des Wächters)."""
    lauf = _SrLauf(
        felder=sr_eingabefelder() if felder is None else felder,
        sensoren=sensor_definitionen() if sensoren is None else sensoren,
        hand=hand_lesen() if hand is None else hand,
        anker=anker_aller_zieldateien() if anker is None else anker,
    )
    text = _sr_zusammensetzen(sr_bausteine_lesen() if bausteine is None else bausteine, lauf)
    lauf.totalitaet()
    return lauf.fehler, text


def sensor_referenz_text(**quellen) -> str:
    """Die SENSOR-REFERENZ, wie sie aus Bausteinen, Registries und Hand-Datei entsteht; bricht bei Fehlern ab."""
    fehler, text = sr_pruefung_und_text(**quellen)
    if fehler:
        raise ValueError("SENSOR-REFERENZ nicht erzeugbar:\n  " + "\n  ".join(fehler))
    return text


# ═══════════════════════════════════════════════════════════════════════════
# MQTT_INBOUND (Stufe U3b): Hand-Bausteine + erzeugte Topic-Tabellen an Markern
# ═══════════════════════════════════════════════════════════════════════════
#
# ``docs/MQTT_INBOUND.md`` = die Bausteine ``docs/mqtt-inbound/NN-*.md`` in Namens-Reihenfolge, Marker wie bei der
# SENSOR-REFERENZ (dieselbe Zusammensetzung, ``_zusammensetzen``). Zwei Marker-Arten:
#
#   <!-- erzeugt: mqtt-topics ebene=basis liste=energy|live -->
#   <!-- erzeugt: mqtt-topics typ=<typ>[,<typ>…] liste=energy|live -->
#   <!-- erzeugt: mqtt-preset id=<preset-id> -->
#
# Zeilen: jeder Eintrag der Feld-Registry (Liste → ``energy``/``live`` nach ``_MQ_LISTE``) außer den Typen in
# ``SKIP_TYPEN`` (Wechselrichter, ein Satz im Baustein), dazu die drei ``BASIS_ENERGY_TOPICS`` (mit Beschreibung; ein
# gleichnamiges Basis-Feld der Registry geht in ihrer Zeile auf). Ein Feld ohne Topic steht mit Grund da
# («kein MQTT-Topic — nur manuell» bei ``nur_manuell``; die Route ``/api/live/mqtt/topics`` filtert genau diese).
#
# Totalität (Fehler beim Namen, ``mq_pruefung_und_text``): jede Zeile in genau einem Marker; jeder Marker mit Zeilen;
# kein ``SKIP_TYPEN``-Typ in einem Marker. **Sollbild:** ``build_expected_topics`` für eine Probe-Anlage mit einem Gerät
# je Typ und Variante (``_MQ_VARIANTEN``) — jedes Topic, das eedc erwartet, hat eine Zeile mit genau diesem Muster, und
# jede Zeile mit Topic wird in einer Variante erwartet. So hängt das Muster an der Topic-Registry, nicht an diesem Modul.

MQ_ZIEL = DOCS / "MQTT_INBOUND.md"
MQ_BAUSTEINE = DOCS / "mqtt-inbound"
MQ_KOPFZEILE = (
    f"> **Erzeugt — nicht von Hand ändern —** Bausteine in `docs/mqtt-inbound/`, `{BEFEHL}`. Die Topic-Tabellen je "
    "Gerätetyp und die Preset-Tabelle kommen aus dem Code (`services/mqtt_topic_registry.py`, Feld-Registry, "
    "`services/mqtt_presets.py`)."
)
MARKER_MQTT = "mqtt-topics"
MARKER_PRESET = "mqtt-preset"
_MQ_MARKER_ERLAUBT: dict[str, frozenset[str]] = {
    MARKER_MQTT: frozenset({"ebene", "typ", "liste"}),
    MARKER_PRESET: frozenset({"id"}),
}
_MQ_MARKER_PFLICHT: dict[str, frozenset[str]] = {
    MARKER_MQTT: frozenset({"liste"}),
    MARKER_PRESET: frozenset({"id"}),
}
#: Registry-Liste → Topic-Ebene (``build_expected_topics``: Monatsfelder unter ``energy/``, Live-Felder unter ``live/``).
_MQ_LISTE: dict[str, str] = {
    "BASIS_FELDER": "energy", "BEDINGTE_BASIS_FELDER": "energy", "OPTIONALE_FELDER": "energy",
    "INVESTITION_FELDER": "energy", "LIVE_FELDER_INV": "live", "BASIS_LIVE_FELDER": "live",
    "BASIS_PREIS_FELDER": "live",
}
MQ_LISTEN: tuple[str, ...] = ("energy", "live")
#: Topic-Muster wie ``build_expected_topics`` (``eedc/{aid}_{aslug}/…``, ``inv/{inv.id}_{islug}``) — das Sollbild prüft es.
MQ_PRAEFIX = "eedc/{anlage_id}_{name}"
MQ_INV = "inv/{inv_id}_{name}"
KEIN_TOPIC_MANUELL = "kein MQTT-Topic — nur manuell"
KEIN_TOPIC_ABSCHLUSS = "kein MQTT-Topic — Monatsabschluss"
#: N-780 (Päckchen U): ein Energie-Feld ohne Leser (``mqtt_topic_registry.energie_topic_ohne_leser``) hat kein Topic mehr;
#: es geht über den Monatsabschluss — von Hand, und als Vorschlag aus einem HA-Sensor nur, wo der Vorschlag das Feld aus
#: der HA-Statistik liest (``ist_zaehler_differenz_feld``, ``monatsabschluss/views.py``; Geldbeträge nicht).
KEIN_TOPIC_OHNE_LESER_HA = KEIN_TOPIC_ABSCHLUSS + " (Hand oder HA-Sensor)"
KEIN_TOPIC_OHNE_LESER_HAND = KEIN_TOPIC_ABSCHLUSS + " (Hand)"
KEIN_TOPIC = "kein MQTT-Topic"
# Payload. Energie: der Inbound-Cache nimmt jeden Schlüssel an — ob ein Wert zählt, entscheiden die LESER, und die
# werden hier befragt, nicht abgeschrieben (``mq_energie_leser``): die Zählerreihe (``snapshot/keys.py::
# _mqtt_key_to_sensor_key`` — Snapshot-Schreiber, Monatsabschluss-Vorschlag, aktueller Monat, Kanal), die «Heute»-Kachel
# (``mqtt_energy_history_service._KEY_TO_CATEGORY``/``_MQTT_FIELD_TO_LIVE_KEY``) und der Kilometerstand
# (``betriebsmodus_live._KM_FELD``). Ein Geräte-Energiefeld ohne Leser hat seit N-780 kein Topic (``_mq_ohne_leser``);
# ein Basis-Energie-Topic ohne Leser sagte es in der Payload (U3b-Halt, Entscheid Master 8.11.2026).
# Live: ein Mittelwert-Kanal (``katalog._MEAN_LIVE``: Art ``mean`` mit ``mittelwert_kanal``) wird als 5-Minuten-/
# Stundenmittel mitgeschrieben (``mqtt_live_history_service.mittel_zeilen``), alles andere ist Anzeige; Zustände mit
# Kanal ``mean`` schreibt eedc als Anteil je Wert mit.
PAYLOAD_ZAEHLER = "Zählerstand (kumuliert)"
PAYLOAD_OHNE_LESER = "wird angenommen, aber von keiner Sicht gelesen"
PAYLOAD_MITTEL = "Zahl (Momentanwert) — 5-Minuten- und Stundenmittel"
PAYLOAD_ANZEIGE = "Zahl (Momentanwert) — nur Anzeige"
#: Probe-Varianten des Sollbilds über ``{}`` hinaus — ein Live-Feld mit harter Bedingung erscheint nur, wenn eine
#: Variante sie erfüllt. Ein neues solches Feld meldet das Sollbild beim Namen («in keiner Probe-Variante erwartet»).
_MQ_VARIANTEN: dict[str, list[dict]] = {
    "waermepumpe": [{"wp_art": "luft_luft", "innengeraete": [{"id": 7, "bezeichnung": "Innengerät"}]}],
}
_MQ_PROBE_ANLAGE = ("1", "Haus")
_MQ_PROBE_GERAET = "geraet"


@dataclass(frozen=True)
class MqZeile:
    """Eine Zeile einer MQTT-Topic-Tabelle: ein Registry-Eintrag (oder ein Basis-Energy-Topic) mit Topic oder Grund."""

    typ: str
    art: str
    feld: str
    liste: str
    label: str
    einheit: str
    feld_zelle: str
    topic: Optional[str]
    ohne_topic: str
    payload: str
    bedingung: str
    beschreibung: str = ""
    quelle: str = ""
    je_innengeraet: bool = False

    @property
    def name(self) -> str:
        return f"{self.typ}:{self.feld}" + (f" ({self.art})" if self.art else "") + f" [{self.quelle}, {self.liste}]"


def mq_topic(typ: str, liste: str, feld: str) -> str:
    return f"{MQ_PRAEFIX}/{liste}" + ("" if typ == "basis" else f"/{MQ_INV}") + f"/{feld}"


def _skip_typen() -> frozenset[str]:
    from backend.services.mqtt_topic_registry import SKIP_TYPEN

    return frozenset(SKIP_TYPEN)


def _basis_energy_topics() -> list[tuple[str, str, str, str]]:
    from backend.services.mqtt_topic_registry import BASIS_ENERGY_TOPICS

    return list(BASIS_ENERGY_TOPICS)


def _werte_text(gruppen: Iterable[Mapping]) -> str:
    """Werte-Tabelle eines Zustands: das Kanon-Wort vorn, die übrigen Werte derselben Gruppe in Klammern."""
    teile = []
    for g in gruppen:
        werte = list(g["werte"])
        if g["kanon"] in werte:
            andere = ", ".join(f"`{w}`" for w in werte if w != g["kanon"])
            teile.append(f"`{g['kanon']}`" + (f" (auch {andere})" if andere else ""))
        else:
            teile.append(f"als {str(g['label']).lower()} gezählt: " + ", ".join(f"`{w}`" for w in werte))
    return " · ".join(teile)


def _zustand_payload(f: SrFeld) -> str:
    from backend.core import zustands_kanon as zk
    from backend.core.betriebsmodus import MODUS_FELD_KEY, betriebsmodus_werte_je_betriebsart

    mitschrift = f.kanal is not None and f.kanal.art == "mean"
    if f.eintrag.get("text"):
        return f"Text (getrimmt, höchstens {zk.TEXT_MAX_ZEICHEN} Zeichen) — nur Anzeige"
    if f.feld == MODUS_FELD_KEY:
        werte = _werte_text(betriebsmodus_werte_je_betriebsart(codes=True))
        weg = "Betriebsart-Mitschrift (Anteil der Stunde je Betriebsart)" if mitschrift else "nur Anzeige"
    else:
        werte = _werte_text(zk.werte_je_kanon(f.feld, codes=True))
        weg = "Zustands-Mitschrift (Anteil der Stunde je Wert)" if mitschrift else "nur Anzeige"
    return f"Zustand: {werte} — {weg}" if werte else ""


def mq_energie_leser(typ: str, feld: str) -> list[str]:
    """Die Leser, die den Wert eines Energie-Topics verarbeiten — aus den Lesern selbst, nicht aus einer Liste."""
    from backend.services.betriebsmodus_live import _KM_FELD
    from backend.services.mqtt_energy_history_service import _KEY_TO_CATEGORY, _MQTT_FIELD_TO_LIVE_KEY
    from backend.services.snapshot.keys import _mqtt_key_to_sensor_key

    leser = []
    if _mqtt_key_to_sensor_key(feld if typ == "basis" else f"inv/1/{feld}"):
        leser.append("Zählerreihe")
    if (typ == "basis" and feld in _KEY_TO_CATEGORY) or typ in _MQTT_FIELD_TO_LIVE_KEY.get(feld, {}):
        leser.append("Heute")
    if typ == "e-auto" and feld == _KM_FELD:
        leser.append("Kilometerstand")
    return leser


def mq_energie_payload(typ: str, art: str, feld: str) -> str:
    return PAYLOAD_ZAEHLER if mq_energie_leser(typ, feld) else PAYLOAD_OHNE_LESER


def mq_payload(f: SrFeld, liste: str) -> str:
    """Was eedc auf dem Topic erwartet und was es daraus macht — aus den Lesern, Registry-Merkmalen und Kanal-Katalog.
    Leer heißt: nicht aus dem Code lesbar (die Prüfung nennt die Zeile)."""
    z = f.kanal
    if liste == "energy":
        return mq_energie_payload(f.typ, f.art, f.feld)
    if f.eintrag.get("zustand"):
        return _zustand_payload(f)
    return PAYLOAD_MITTEL if z is not None and z.art == "mean" and z.mittelwert_kanal else PAYLOAD_ANZEIGE


def _mq_ohne_leser(f: SrFeld) -> bool:
    """Geräte-Energiefeld, dessen Wert kein Leser verarbeitet — dieselbe Frage wie das Flag ``ohne_leser`` von
    ``build_expected_topics`` (N-780), nicht nachgebaut."""
    from backend.services.mqtt_topic_registry import energie_topic_ohne_leser

    return (f.typ != "basis" and _MQ_LISTE[f.liste] == "energy" and not f.eintrag.get("nur_manuell")
            and energie_topic_ohne_leser(1, f.feld))


def _mq_ohne_topic(f: SrFeld) -> str:
    from backend.core.field_definitions import basis_feld_key, ist_zaehler_differenz_feld

    if f.eintrag.get("nur_manuell"):
        return KEIN_TOPIC_MANUELL
    if _mq_ohne_leser(f):
        return KEIN_TOPIC_OHNE_LESER_HA if ist_zaehler_differenz_feld(basis_feld_key(f.feld)) else KEIN_TOPIC_OHNE_LESER_HAND
    if f.kanal is not None and f.kanal.ausnahme == "abschluss_ohne_sensor":
        return KEIN_TOPIC_ABSCHLUSS
    return KEIN_TOPIC


def _mq_hat_topic(f: SrFeld) -> bool:
    """Wie ``build_expected_topics``: Basis nur die Live-Felder (Energie: ``BASIS_ENERGY_TOPICS``), je Gerät jedes
    Energie- und Live-Feld; ``nur_manuell`` und ``ohne_leser`` (N-780) filtert die Route ``/api/live/mqtt/topics`` heraus."""
    if f.typ == "basis":
        return f.liste == "BASIS_LIVE_FELDER"
    return not f.eintrag.get("nur_manuell") and not _mq_ohne_leser(f)


def _mq_zeile(f: SrFeld) -> MqZeile:
    liste = _MQ_LISTE[f.liste]
    topic = mq_topic(f.typ, liste, f.feld) if _mq_hat_topic(f) else None
    return MqZeile(
        typ=f.typ, art=f.art, feld=f.feld, liste=liste, label=_sr_label(f), einheit=_sr_einheit(f),
        feld_zelle=_sr_feld_zelle(f), topic=topic, ohne_topic="" if topic else _mq_ohne_topic(f),
        payload=mq_payload(f, liste) if topic else "", bedingung=_bedingung_text(f.eintrag), quelle=f.liste,
        je_innengeraet=bool(f.eintrag.get("je_innengeraet")),
    )


def mqtt_zeilen(felder: Optional[list[SrFeld]] = None,
                basis_energy: Optional[list[tuple[str, str, str, str]]] = None) -> list[MqZeile]:
    """Alle Zeilen: zuerst die Basis-Energy-Topics, dann die Registry in Quellreihenfolge (ohne ``SKIP_TYPEN``)."""
    felder = sr_eingabefelder() if felder is None else felder
    basis_energy = _basis_energy_topics() if basis_energy is None else basis_energy
    skip = _skip_typen()
    basis_reg = {f.feld: f for f in felder if f.typ == "basis" and _MQ_LISTE[f.liste] == "energy"}
    zeilen = []
    for key, label, einheit, beschreibung in basis_energy:
        f = basis_reg.get(key)
        zeilen.append(MqZeile(
            typ="basis", art="", feld=key, liste="energy", label=label, einheit=einheit, feld_zelle=f"`{key}`",
            topic=mq_topic("basis", "energy", key), ohne_topic="", payload=mq_energie_payload("basis", "", key),
            bedingung=_bedingung_text(f.eintrag) if f else "", beschreibung=beschreibung, quelle="BASIS_ENERGY_TOPICS",
        ))
    energy_keys = {key for key, *_rest in basis_energy}
    for f in felder:
        if f.typ in skip or (f.typ == "basis" and _MQ_LISTE[f.liste] == "energy" and f.feld in energy_keys):
            continue
        zeilen.append(_mq_zeile(f))
    return zeilen


def mq_zeilen_des_markers(zeilen: Iterable[MqZeile], param: Mapping[str, str]) -> list[MqZeile]:
    """Die Zeilen eines Topic-Markers: Typen in Marker-Reihenfolge, je Typ in Quellreihenfolge. ``ValueError`` bei einem
    falschen Marker (``ebene=``/``typ=`` beide oder keiner, unbekannte Liste, ``SKIP_TYPEN``-Typ)."""
    if ("ebene" in param) == ("typ" in param):
        raise ValueError("genau einer von `ebene=basis` oder `typ=` erwartet")
    if param["liste"] not in MQ_LISTEN:
        raise ValueError(f"`liste={param['liste']}` — erlaubt: {', '.join(MQ_LISTEN)}")
    if "ebene" in param and param["ebene"] != "basis":
        raise ValueError(f"`ebene={param['ebene']}` — erlaubt: basis")
    typen = ["basis"] if "ebene" in param else param["typ"].split(",")
    ohne = sorted(set(typen) & _skip_typen())
    if ohne:
        raise ValueError(f"Typ {ohne} hat keine Topics (SKIP_TYPEN) — ein Satz im Baustein statt eines Markers")
    auswahl = [z for z in zeilen if z.typ in typen and z.liste == param["liste"]]
    return sorted(auswahl, key=lambda z: typen.index(z.typ))


def mq_tabelle(zeilen: list[MqZeile]) -> str:
    """Feld · Label · Einheit · Topic · Payload · Bedingung — mit «Typ» bei mehr als einem Typ, «Art» bei den Arten
    von `sonstiges`, «Beschreibung» bei den Basis-Energy-Topics."""
    mit_typ = len({z.typ for z in zeilen}) > 1
    mit_art = any(z.art for z in zeilen)
    mit_beschreibung = any(z.beschreibung for z in zeilen)
    kopf = (["Typ"] if mit_typ else []) + (["Art"] if mit_art else []) + [
        "Feld", "Label", "Einheit", "Topic", "Payload", "Bedingung"] + (["Beschreibung"] if mit_beschreibung else [])
    out = ["| " + " | ".join(kopf) + " |", "|" + "---|" * len(kopf)]
    for z in zeilen:
        spalten = ([f"`{z.typ}`"] if mit_typ else []) + ([f"`{z.art}`"] if mit_art else []) + [
            z.feld_zelle, z.label, z.einheit, f"`{z.topic}`" if z.topic else z.ohne_topic, z.payload, z.bedingung,
        ] + ([z.beschreibung] if mit_beschreibung else [])
        out.append("| " + " | ".join(zelle(s) for s in spalten) + " |")
    return "\n".join(out)


def _faktor_text(faktor: float) -> str:
    """``1`` · ``0,001`` · ``1/60`` — ein Bruch, wo der Nenner keine Zehnerpotenz ist."""
    from fractions import Fraction

    if float(faktor).is_integer():
        return str(int(faktor))
    bruch = Fraction(faktor).limit_denominator(1000)
    if abs(float(bruch) - faktor) < 1e-12 and bruch.denominator not in (10, 100, 1000):
        return f"{bruch.numerator}/{bruch.denominator}"
    return f"{faktor:g}".replace(".", ",")


def _umrechnung_text(m) -> str:
    """Faktor, Offset, Vorzeichen und Payload-Form eines Preset-Mappings; an einem Zustandsfeld reicht das Gateway den
    Text weiter (``mqtt_gateway_service._als_text``) — Faktor und Offset gelten dort nicht."""
    from backend.core.field_definitions import ist_zustand_feld

    if ist_zustand_feld(m.ziel_key.rsplit("/", 1)[1]):
        teile = ["— (Text)"]
    else:
        teile = [_faktor_text(m.faktor)] + ([f"Offset {m.offset:g}"] if m.offset else [])
        teile += ["invertiert"] if m.invertieren else []
    if m.payload_typ != "plain":
        pfad = m.json_pfad if m.json_pfad is not None else m.array_index
        teile.append(f"`{m.payload_typ}`" + (f" `{pfad}`" if pfad is not None else ""))
    return " · ".join(teile)


def mq_preset_tabelle(preset) -> str:
    """Quell-Topic · Ziel in eedc · Umrechnung · Beschreibung — je Mapping des Presets eine Zeile."""
    kopf = ("Quell-Topic (Vorlage)", "Ziel in eedc", "Umrechnung", "Beschreibung (aus dem Preset)")
    out = ["| " + " | ".join(kopf) + " |", "|" + "---|" * len(kopf)]
    for m in preset.mappings:
        spalten = (f"`{m.topic_template}`", f"`{m.ziel_key}`", _umrechnung_text(m), m.beschreibung)
        out.append("| " + " | ".join(zelle(s) for s in spalten) + " |")
    return "\n".join(out)


def _preset_lesen(preset_id: str):
    from backend.services.mqtt_presets import get_preset

    return get_preset(preset_id)


@dataclass
class _MqLauf:
    """Zustand eines Zusammensetz-Laufs von MQTT_INBOUND: verbrauchte Zeilen, Fehler."""

    marker_erlaubt: ClassVar[Mapping[str, frozenset[str]]] = _MQ_MARKER_ERLAUBT
    marker_pflicht: ClassVar[Mapping[str, frozenset[str]]] = _MQ_MARKER_PFLICHT

    zeilen: list[MqZeile]
    preset: Callable[[str], object]
    zeile_marker: dict[int, list[str]] = field(default_factory=lambda: defaultdict(list))
    fehler: list[str] = field(default_factory=list)

    def tabelle(self, ort: str, _abschnitt: str, art: str, param: Mapping[str, str]) -> str:
        if art == MARKER_PRESET:
            preset = self.preset(param["id"])
            if preset is None or not getattr(preset, "mappings", None):
                self.fehler.append(f"{ort}: Preset `{param['id']}` unbekannt oder ohne Mappings")
                return ""
            return mq_preset_tabelle(preset)
        try:
            zeilen = mq_zeilen_des_markers(self.zeilen, param)
        except ValueError as e:
            self.fehler.append(f"{ort}: {e}")
            return ""
        for z in zeilen:
            self.zeile_marker[id(z)].append(ort)
        if not zeilen:
            self.fehler.append(f"{ort}: Marker ohne Zeilen ({art} {dict(param)})")
        return mq_tabelle(zeilen) if zeilen else ""

    def totalitaet(self) -> None:
        for z in self.zeilen:
            orte = self.zeile_marker.get(id(z), [])
            if len(orte) != 1:
                self.fehler.append(f"Topic-Zeile {z.name} steht in {len(orte)} Markern {orte} — Soll: genau einem")
            if z.topic and not z.payload:
                self.fehler.append(f"Topic-Zeile {z.name}: Payload nicht aus dem Code lesbar (Zustand ohne Werte-Tabelle?)")


def mq_erwartete_topics() -> list[dict]:
    """``build_expected_topics`` für die Probe-Anlage: ein Gerät je Registry-Typ und Variante (``{}``, die Varianten aus
    ``_MQ_VARIANTEN``, bei `sonstiges` jede Kategorie). Kein DB-Zugriff (Geräte werden übergeben)."""
    import asyncio
    from types import SimpleNamespace

    from backend.core.field_definitions import INVESTITION_FELDER, LIVE_FELDER_INV
    from backend.services.mqtt_topic_registry import build_expected_topics

    anlage = SimpleNamespace(id=int(_MQ_PROBE_ANLAGE[0]), anlagenname=_MQ_PROBE_ANLAGE[1], sensor_mapping={})
    geraete = []
    for typ in sorted(set(INVESTITION_FELDER) | set(LIVE_FELDER_INV)):
        varianten = [{}, *_MQ_VARIANTEN.get(typ, [])]
        if isinstance(INVESTITION_FELDER.get(typ), dict):
            varianten += [{"kategorie": k} for k in INVESTITION_FELDER[typ]]
        for parameter in varianten:
            geraete.append(SimpleNamespace(id=100 + len(geraete), typ=typ, bezeichnung=_MQ_PROBE_GERAET,
                                           parameter=parameter, anlage_id=anlage.id))
    return asyncio.run(build_expected_topics(None, anlage, geraete))


def _mq_muster(topic: str, feld: str) -> str:
    """Probe-Topic → Muster der Tabelle (IDs und Namen als Platzhalter, Innengeräte-Suffix auf das Basisfeld)."""
    aid, aname = _MQ_PROBE_ANLAGE
    muster = re.sub(rf"^eedc/{aid}_{aname}/", f"{MQ_PRAEFIX}/", topic)
    muster = re.sub(rf"/inv/\d+_{_MQ_PROBE_GERAET}/", f"/{MQ_INV}/", muster)
    return muster.rsplit("/", 1)[0] + f"/{feld}"


def mq_sollbild_fehler(zeilen: list[MqZeile], topics: list[dict]) -> list[str]:
    """Erwartete Topics (``build_expected_topics``) gegen die Zeilen — beide Richtungen, beim Namen."""
    from backend.core.field_definitions import basis_feld_key

    je_schluessel: dict[tuple[str, str, str], list[MqZeile]] = defaultdict(list)
    for z in zeilen:
        je_schluessel[(z.typ, z.liste, z.feld)].append(z)
    fehler, erwartet = [], set()
    for t in topics:
        if t.get("abschnitt") == "themen":
            continue  # Themen: je Instanz aus dem Store, Hand-Prosa (Baustein «Themen»)
        feld = basis_feld_key(t["feld"])
        schl = (t["typ"], t["kategorie"], feld)
        muster = _mq_muster(t["topic"], feld)
        kandidaten = je_schluessel.get(schl, [])
        erwartet.add(schl)
        meldung = _mq_topic_meldung(t, feld, muster, kandidaten)
        if meldung:
            fehler.append(meldung)
    for z in zeilen:
        if z.topic and (z.typ, z.liste, z.feld) not in erwartet:
            fehler.append(f"Topic-Zeile {z.name}: die Tabelle nennt `{z.topic}`, die Registry erwartet es in keiner "
                          "Probe-Variante (Bedingung? `_MQ_VARIANTEN` ergänzen)")
    return fehler


def _mq_topic_meldung(t: Mapping, feld: str, muster: str, kandidaten: list[MqZeile]) -> Optional[str]:
    if not kandidaten:
        return f"Topic `{muster}` ({t['typ']}): die Registry erwartet es, keine Tabellen-Zeile"
    if t.get("nur_manuell") or t.get("ohne_leser"):
        grund = "nur_manuell" if t.get("nur_manuell") else "ohne Leser (N-780)"
        falsch = [z.name for z in kandidaten if z.topic]
        return f"`{feld}` ({t['typ']}) ist {grund}, die Tabelle nennt ein Topic: {falsch}" if falsch else None
    if t["feld"] != feld and not all(z.je_innengeraet for z in kandidaten):
        return f"Topic `{t['topic']}`: Innengeräte-Kopie, die Zeile {kandidaten[0].name} sagt «je Innengerät» nicht"
    if not any(z.topic == muster for z in kandidaten):
        return f"Topic `{muster}` ({t['typ']}): die Tabelle nennt {[z.topic or z.ohne_topic for z in kandidaten]}"
    return None


def mq_bausteine_lesen(verzeichnis: Path = MQ_BAUSTEINE) -> list[tuple[str, str]]:
    return [(p.name, p.read_text(encoding="utf-8")) for p in sorted(verzeichnis.glob("*.md"))]


def mq_pruefung_und_text(bausteine: Optional[list[tuple[str, str]]] = None, zeilen: Optional[list[MqZeile]] = None,
                         topics: Optional[list[dict]] = None,
                         preset: Optional[Callable[[str], object]] = None) -> tuple[list[str], str]:
    """``(Fehler, Text)`` von MQTT_INBOUND; jede Quelle austauschbar (Gegenproben des Wächters)."""
    lauf = _MqLauf(zeilen=mqtt_zeilen() if zeilen is None else zeilen,
                   preset=_preset_lesen if preset is None else preset)
    text = _zusammensetzen(mq_bausteine_lesen() if bausteine is None else bausteine, lauf, MQ_KOPFZEILE)
    lauf.totalitaet()
    lauf.fehler += mq_sollbild_fehler(lauf.zeilen, mq_erwartete_topics() if topics is None else topics)
    return lauf.fehler, text


def mqtt_inbound_text(**quellen) -> str:
    """MQTT_INBOUND, wie es aus Bausteinen, Topic-Registry, Feld-Registry und Presets entsteht; bricht bei Fehlern ab."""
    fehler, text = mq_pruefung_und_text(**quellen)
    if fehler:
        raise ValueError("MQTT_INBOUND nicht erzeugbar:\n  " + "\n  ".join(fehler))
    return text


def _anker_mqtt_inbound() -> dict[str, str]:
    """Anker von MQTT_INBOUND aus den Bausteinen (Marker und Kopfzeile tragen keine Überschrift)."""
    if MQ_BAUSTEINE.is_dir():
        return {s: t for t, s in ueberschriften("\n".join(text for _n, text in mq_bausteine_lesen()))}
    return anker_der_datei(MQ_ZIEL) if MQ_ZIEL.exists() else {}


def _anker_sensor_referenz() -> dict[str, str]:
    """Anker der SENSOR-REFERENZ aus den Bausteinen (Marker und Kopfzeile tragen keine Überschrift) — so hängt der
    Erzeuger nicht an einer veralteten erzeugten Datei."""
    if SR_BAUSTEINE.is_dir():
        return {s: t for t, s in ueberschriften("\n".join(text for _n, text in sr_bausteine_lesen()))}
    return anker_der_datei(SR_ZIEL) if SR_ZIEL.exists() else {}


def anker_aller_zieldateien() -> dict[str, dict[str, str]]:
    anker = {d: anker_der_datei(DOCS / d) for d in ANKER_DATEIEN if (DOCS / d).exists()}
    if DOCS.is_dir():
        anker["SENSOR-REFERENZ.md"] = _anker_sensor_referenz()
        anker["MQTT_INBOUND.md"] = _anker_mqtt_inbound()
    return anker


def erzeugen(quellen: Optional[Quellen] = None, hand: Optional[Mapping] = None) -> str:
    """Die Datei, wie sie aus Code und Hand-Datei entsteht. Bricht bei einer ungültigen Hand-Datei ab."""
    zeilen = alle_zeilen(quellen)
    hand = hand_lesen() if hand is None else hand
    fehler = hand_formfehler(hand, zeilen)
    if fehler:
        raise ValueError("groessen_hand.yaml ungültig:\n  " + "\n  ".join(fehler))
    return dokument(zeilen, hand, anker_aller_zieldateien())


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Übersicht der Größen, SENSOR-REFERENZ und MQTT_INBOUND erzeugen (docs/UEBERSICHT-GROESSEN.md, "
                    "docs/SENSOR-REFERENZ.md, docs/MQTT_INBOUND.md).")
    gruppe = parser.add_mutually_exclusive_group()
    gruppe.add_argument("--schreiben", action="store_true", help="alle drei Dateien schreiben (Vorgabe)")
    gruppe.add_argument("--baseline", action="store_true", help="groessen_offen_baseline.txt neu schreiben")
    gruppe.add_argument("--pruefen", action="store_true", help="nur vergleichen; Exit 1 bei Abweichung")
    args = parser.parse_args(argv)
    if args.baseline:
        BASELINE.write_text(baseline_text(offene_schluessel(hand_lesen(), alle_zeilen())), encoding="utf-8")
        print(f"  {BASELINE.relative_to(REPO)} geschrieben")
        return 0
    dateien = ((ZIEL, erzeugen()), (SR_ZIEL, sensor_referenz_text()), (MQ_ZIEL, mqtt_inbound_text()))
    if args.pruefen:
        veraltet = 0
        for ziel, text in dateien:
            gleich = ziel.exists() and ziel.read_text(encoding="utf-8") == text
            veraltet += not gleich
            print(f"  {ziel.relative_to(REPO)}: {'aktuell' if gleich else 'VERALTET'}")
        return 1 if veraltet else 0
    for ziel, text in dateien:
        ziel.write_text(text, encoding="utf-8")
        print(f"  {ziel.relative_to(REPO)} geschrieben")
    return 0


if __name__ == "__main__":
    sys.exit(main())
