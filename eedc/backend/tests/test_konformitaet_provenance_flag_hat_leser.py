"""Wächter **W1** — kein Provenance-Flag ohne Weg in die Antwort.

`docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md` §3 Regel 2: *„Ein Provenance-Flag ohne
Leser ist kein Provenance. Wer eines einführt, liefert es im selben Schritt
aus."* §2.4 nennt das den **schärfsten Einzelbefund** der Inventur vom
28.08.2026, und er war kein Gedankenspiel: `ErzeugungFakten.pv_vollstaendig`
wurde gesetzt, in die Meta-Gruppe gereicht und von zwei Tests geprüft — aber von
**keiner Route** gelesen. Ein vollständig gebautes, getestetes Flag, das die
Antwort nie erreichte.

**Gegenstand:** jedes **boolesche** Feld der Domänen-Schicht (`services/`,
`core/`), dessen Name auf ``_vollstaendig``/``_unvollstaendig`` endet, braucht
mindestens **einen Attributzugriff** unter ``backend/api/``. Nur dann kann es
überhaupt in einer Antwort landen.

⛔ **Warum Attributzugriff und nicht Textsuche — am eigenen Prüfer gelernt
(29.08.2026).** Die erste Fassung suchte den Namen als Text und blieb bei der
Gegenprobe **grün**, obwohl die Auslieferung testweise komplett zurückgebaut
war. Drei Gründe, alle gemessen:

* eine **Kommentarzeile** nennt den Namen (`aktueller_monat.py` erklärt in einem
  Docstring, warum das Flag dort nur bedingt gilt) — und zählte als Leser;
* eine gleichnamige **Funktion** an anderer Stelle (`pv_monatswerte.ist_vollstaendig`)
  zählte als Leser des Feldes `AussichtenResponse.ist_vollstaendig` — die
  Namensgleichheit über Klassengrenzen hinweg, vor der ADR-002 warnt;
* die **TypeScript-Typdeklaration** des Clients nennt den Namen, ist aber kein
  Beleg, dass das Backend das Feld je füllt.

*Ein Prüfer, der bei zurückgebautem Fix grün bleibt, hat nichts gemessen.* Die
Gegenprobe steht deshalb als eigener Test in dieser Datei.

⛔ **Schema-Felder unter `api/` sind ausdrücklich NICHT Gegenstand.** Sie *sind*
die Antwort; ihr Konsument sitzt im Client, und den kann dieser Prüfer nicht
sehen. Wer sie mitprüfen will, braucht eine andere Bauform (Response-Vertrag
gegen Client-Nutzung) — das ist W3 im Bauschnitt, eine Regression je Endpoint.

**Schwesterdateien:** `test_konformitaet_echte_uhr_in_tests.py` und
`test_konformitaet_schwesterdateien.py` (dieselbe Familie strukturell prüfender
Wächter), dazu die Ergebnis-Regression zu derselben Regel,
`test_unvollstaendige_werte_b1_b3.py` — sie prüft, **was** ausgeliefert wird,
dieser Wächter prüft, **dass überhaupt** ausgeliefert wird.

⛔ **Und ausdrücklich kein Grep-Wächter gegen `or 0`.** Den gibt es bewusst
nicht: dieselbe Form ist im Connector-/Wetter-Layer richtig (rund 40 Stellen) und
im Wert-Pfad falsch — der Unterschied liegt nicht im Ausdruck (ADR-002). W1
prüft eine Eigenschaft, die **strukturell** entscheidbar ist.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
API = BACKEND / "api"

SUFFIXE = ("_vollstaendig", "_unvollstaendig")
DOMAENE = ("services", "core")

#: Bewusst leer. Kommt eine Ausnahme dazu, gehört die Begründung hierher — und
#: die Frage, warum ein Flag ohne Weg in die Antwort überhaupt existiert.
AUSNAHMEN: dict[str, str] = {}


def _py_dateien(wurzel: Path) -> list[Path]:
    return [
        p for p in wurzel.rglob("*.py")
        if "venv" not in p.parts and "tests" not in p.parts
    ]


def _baum(pfad: Path) -> ast.AST | None:
    try:
        return ast.parse(pfad.read_text(encoding="utf-8"))
    except SyntaxError:  # pragma: no cover — eine defekte Datei fällt anderswo auf
        return None


def domaenen_flags() -> list[tuple[str, Path, int]]:
    """Boolesche `*_vollstaendig`-Felder in `services/`/`core/`.

    Nur `bool` — `list[...]`/`Optional[...]` sind keine Provenance-Flags. Ohne
    diese Einschränkung fiele `SizingErgebnis.vollstaendig: list[SizingStunde]`
    mit hinein: ein Feld, dessen Name zufällig so endet.
    """
    treffer: list[tuple[str, Path, int]] = []
    for pfad in _py_dateien(BACKEND):
        if pfad.relative_to(BACKEND).parts[0] not in DOMAENE:
            continue
        baum = _baum(pfad)
        if baum is None:
            continue
        for knoten in ast.walk(baum):
            if not isinstance(knoten, ast.AnnAssign) or not isinstance(knoten.target, ast.Name):
                continue
            name = knoten.target.id
            ist_bool = isinstance(knoten.annotation, ast.Name) and knoten.annotation.id == "bool"
            if name.endswith(SUFFIXE) and ist_bool:
                treffer.append((name, pfad, knoten.lineno))
    return treffer


def attributzugriffe_unter_api() -> set[str]:
    """Alle `irgendwas.<attr>`-Zugriffe unter `backend/api/`.

    Attributzugriff, nicht Textsuche: ein Kommentar, ein String und eine
    gleichnamige Funktion sind damit draußen.
    """
    namen: set[str] = set()
    for pfad in _py_dateien(API):
        baum = _baum(pfad)
        if baum is None:
            continue
        for knoten in ast.walk(baum):
            if isinstance(knoten, ast.Attribute):
                namen.add(knoten.attr)
            # `ErgebnisTyp(pv_vollstaendig=…)` ist ebenfalls eine Verwendung:
            # die Route reicht das Flag weiter, statt es zu lesen.
            elif isinstance(knoten, ast.keyword) and knoten.arg:
                namen.add(knoten.arg)
    return namen


def test_w1_jedes_domaenen_flag_erreicht_eine_route():
    """Baseline **0** — gemessen, nicht gesetzt.

    Am 29.08.2026 erhoben: `pv_vollstaendig` (`services/monats_fakten.py`),
    `anfang_vollstaendig` (`services/zaehlerstaende.py`), `om_vollstaendig`
    (`services/prognose_kanon.py`). Vor dem B1-Bau erreichte **`pv_vollstaendig`
    keine Route** — dieser Test wäre rot gewesen. Genau so war er im Bauschnitt
    geplant: „W1 startet rot … er wird mit dem Bau-Schritt scharf gestellt, der
    das Flag ausliefert, nicht vorher."
    """
    erreichbar = attributzugriffe_unter_api()
    tot = [
        f"{name} ({pfad.relative_to(BACKEND.parent)}:{zeile})"
        for name, pfad, zeile in domaenen_flags()
        if name not in AUSNAHMEN and name not in erreichbar
    ]
    assert not tot, (
        "Provenance-Flag der Domänen-Schicht ohne Zugriff unter backend/api/ — "
        "es erreicht keine Antwort und ist damit kein Provenance "
        "(KONZEPT-UNVOLLSTAENDIGE-WERTE §2.4/§3 Regel 2):\n  "
        + "\n  ".join(tot)
    )


def test_w1_sieht_ueberhaupt_flags():
    """Untergrenze: ein Prüfer über einer leeren Menge meldet zwangsläufig „grün".

    Dieselbe Bauform, an der `nutzt_arbitrage` im Stammdaten-Checker jahrelang
    schwieg — die Bedingung war nach einer Umbenennung dauerhaft falsch, und
    niemand merkte es, weil nie etwas gemeldet wurde.
    """
    namen = {name for name, _, _ in domaenen_flags()}
    assert "pv_vollstaendig" in namen
    assert len(namen) >= 3, f"nur {namen} gefunden — sieht der Sucher noch richtig hin?"


def test_w1_wuerde_den_rueckbau_bemerken():
    """**Die Gegenprobe, als Test statt als Handgriff.**

    Der Prüfer bekommt eine Zugriffsmenge OHNE `pv_vollstaendig` vorgesetzt —
    also den Stand vom 28.08.2026 — und muss das Flag melden. Ohne diesen Test
    stünde nur die Behauptung da, W1 wäre damals rot gewesen; die erste Fassung
    von W1 wäre es **nicht** gewesen, und das ist erst bei der Gegenprobe
    aufgefallen.
    """
    ohne = attributzugriffe_unter_api() - {"pv_vollstaendig"}
    tot = [n for n, _, _ in domaenen_flags() if n not in ohne]
    assert "pv_vollstaendig" in tot, (
        "W1 bemerkt den Rückbau der Auslieferung nicht — er zeigt aufs falsche Objekt."
    )
