"""Eine Quelle für „welche Dateien gehören zum Backend-Baum" — geparst, gecacht.

**Warum es diese Datei gibt.** Neun Prüfer im Testbaum laufen baumweit über den
Backend-Quelltext. Jeder trug bis zum 2026-08-24 seine **eigene** Fassung der
Frage „was ist der Produktivbaum" — neun handgeschriebene Kopien, in vier
verschiedenen Schreibweisen (`pfad.parts` · `rel.startswith((...))` ·
`"/venv/" not in str(p)` · Zusatzausschluss `alembic/`, das es gar nicht gibt).

**Zwei der neun waren falsch**, und das ist der Anlass:

* `test_n252_speicher_wirkungsgrad_deckung.py` filterte mit `"/venv/" in rel` —
  `rel` ist aber **relativ** und beginnt mit `venv/` ohne führenden Schrägstrich.
  Der Filter griff nie: der Prüfer nahm **3828 Dateien statt 337**, davon 3491
  aus dem virtualenv, und brauchte dafür **14,27 s** in einem einzigen Testfall.
* `test_datenquellen_mapping_sync.py` hatte **gar keinen** venv-Filter; er blieb
  nur billig, weil ein `"quellen" not in quelle` vorher abkürzte.

Beide meldeten grün. Ein Abwesenheitsbeweis, der Fremdcode aus `site-packages`
mitmisst, behauptet mehr, als er weiß — und niemand könnte eine Falschmeldung
aus einem fremden Paket reparieren. Neun Kopien einer Regel driften; **eine
Definition kann nicht auseinanderlaufen.**

**Der Cache ist der kleinere Gewinn, aber ein gemessener.**
`test_wurzelmuster_konformitaet.py` ruft seine Dateiquelle **16-mal** auf und
parste den Baum damit 16-mal: **27,36 s**. Mit dieser Quelle: **8,78 s**, bei
unveränderten 31 Fällen.

**Warum die Bäume geteilt werden dürfen:** kein Prüfer im Baum verändert einen
AST-Knoten — es wird ausschließlich `ast.walk` gelesen. Die Rückgaben sind
`tuple`, damit ein Aufrufer die Liste nicht versehentlich umbaut.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

# `backend/` — diese Datei liegt in `backend/tests/`.
BACKEND = Path(__file__).resolve().parents[1]

#: Verzeichnisse, die **nie** zum geprüften Baum gehören.
#: `venv/` ist Fremdcode, `__pycache__/` ist Erzeugnis.
_NIE = ("venv", "__pycache__")


@dataclass(frozen=True)
class Quelldatei:
    """Eine Python-Datei mit allem, was ein baumweiter Prüfer von ihr braucht."""

    pfad: Path
    #: Pfad relativ zu `backend/`, immer mit `/` — der Name, den Prüfer melden.
    rel: str
    quelle: str
    baum: ast.Module


def _sammle(*, tests: bool) -> tuple[tuple[Quelldatei, ...], tuple[str, ...]]:
    """Alle `.py` unter `backend/`, entweder der Produktiv- oder der Testbaum.

    Zweiter Rückgabewert: die Dateien, die **nicht** geparst werden konnten.
    Sie werden nicht still übergangen — `test_quellbaum.py` hält die Liste leer.
    """
    dateien: list[Quelldatei] = []
    kaputt: list[str] = []
    for pfad in sorted(BACKEND.rglob("*.py")):
        teile = pfad.relative_to(BACKEND).parts
        if any(t in _NIE for t in teile):
            continue
        if (teile[0] == "tests") is not tests:
            continue
        rel = pfad.relative_to(BACKEND).as_posix()
        quelle = pfad.read_text(errors="ignore")
        try:
            baum = ast.parse(quelle, filename=str(pfad))
        except SyntaxError:
            kaputt.append(rel)
            continue
        dateien.append(Quelldatei(pfad=pfad, rel=rel, quelle=quelle, baum=baum))
    return tuple(dateien), tuple(kaputt)


@lru_cache(maxsize=1)
def _produktiv() -> tuple[tuple[Quelldatei, ...], tuple[str, ...]]:
    return _sammle(tests=False)


@lru_cache(maxsize=1)
def _test() -> tuple[tuple[Quelldatei, ...], tuple[str, ...]]:
    return _sammle(tests=True)


def produktivbaum() -> tuple[Quelldatei, ...]:
    """Der Backend-Produktivcode: alles unter `backend/` ohne `tests/`, `venv/`.

    Aufsteigend nach Pfad sortiert, damit Prüfer-Meldungen stabil bleiben.
    """
    return _produktiv()[0]


def probenbaum() -> tuple[Quelldatei, ...]:
    """Der Testbaum: alles unter `backend/tests/` ohne `__pycache__/`.

    ⚠ **Sie heißt nicht `testbaum`, und das ist kein Geschmack.** Unter dem
    Namen hat pytest sie beim ersten Lauf als **Testfunktion eingesammelt**
    (`python_functions = test*` greift auf jeden importierten Namen im
    Modul-Namensraum) und mit `PytestReturnNotNoneWarning` quittiert — ein
    „Test", der nichts prüft und trotzdem grün zählt. Kein exportierter Name
    dieser Datei beginnt mit `test`; `test_quellbaum.py` hält das fest.
    """
    return _test()[0]


def nicht_parsebar() -> tuple[str, ...]:
    """Dateien beider Bäume, die `ast.parse` nicht annimmt (heute: keine).

    Ein baumweiter Prüfer, der solche Dateien **still** überspringt, verliert
    Deckung, ohne es zu melden — genau die Klasse aus N-318. Diese Liste macht
    den Verlust sichtbar.
    """
    return _produktiv()[1] + _test()[1]
