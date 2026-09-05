"""Wächter (#408): ein Delegations-Wrapper in `LivePowerService` trägt jeden Parameter seines Ziels.

Die Klasse hinter #408: ``LivePowerService.get_tagesverlauf`` ist eine
**Kopie** der Signatur von ``live_tagesverlauf_service.get_tagesverlauf``.
Als das Ziel mit N-382 ``mit_vortagsrand`` bekam, blieb die Kopie stehen —
und nichts hielt beide zusammen. Gemessen am 05.09.2026 (AST über alle
Methoden der Klasse): zwei solche Wrapper, einer gebrochen, der zweite
(``get_verbrauchsprofil``) bindet seinen Zusatzparameter selbst.

Die Regel: **Jeder Parameter des Ziels ist entweder ein Parameter des
Wrappers und wird weitergereicht, oder er wird im Wrapper gebunden — und
diese Bindung steht hier klassifiziert.** Ein Parameter, der am Ziel neu
dazukommt, macht diesen Test rot, bis der Wrapper ihn kennt.

Grenze, benannt: Der Test erkennt einen Wrapper an der Bauform
``from backend.services.<modul> import <fn> as <alias>`` im Methodenrumpf
plus ``return await <alias>(…)``. Eine Delegation in anderer Form sieht er
nicht — dann ist die Form zu ergänzen, nicht die Regel.

Schwesterdateien: test_408_wrapper_reicht_vortagsrand_durch.py (der Fall des
Melders durch den echten Wrapper), test_slot_konvention_leistungspfad.py
(der N-382-Bau, der den Parameter am Ziel eingeführt hat).
"""

from __future__ import annotations

import ast
import importlib
import inspect
from pathlib import Path

import pytest

QUELLE = Path(__file__).resolve().parents[1] / "services" / "live_power_service.py"

#: Ziel-Parameter, die der Wrapper bewusst selbst bindet — mit Grund.
GEBUNDEN: dict[str, dict[str, str]] = {
    "get_verbrauchsprofil": {
        "kwh_cache": "`self._kwh_cache` — der Cache des Singletons, kein Aufrufer-Parameter",
    },
}


def _wrapper_der_klasse() -> list[tuple[str, str, str, ast.Call, list[str]]]:
    """(Methodenname, Zielmodul, Zielfunktion, Delegations-Call, Wrapper-Parameter)."""
    baum = ast.parse(QUELLE.read_text(encoding="utf-8"))
    klasse = next(
        n for n in baum.body
        if isinstance(n, ast.ClassDef) and n.name == "LivePowerService"
    )
    gefunden = []
    for fn in klasse.body:
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        aliase: dict[str, tuple[str, str]] = {}
        for knoten in ast.walk(fn):
            if isinstance(knoten, ast.ImportFrom) and (knoten.module or "").startswith("backend.services."):
                for a in knoten.names:
                    aliase[a.asname or a.name] = (knoten.module, a.name)
        if not aliase:
            continue
        for knoten in ast.walk(fn):
            if not (isinstance(knoten, ast.Return) and isinstance(knoten.value, ast.Await)):
                continue
            call = knoten.value.value
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in aliase:
                modul, ziel = aliase[call.func.id]
                params = [a.arg for a in fn.args.args if a.arg != "self"] + [
                    a.arg for a in fn.args.kwonlyargs
                ]
                gefunden.append((fn.name, modul, ziel, call, params))
    return gefunden


def test_es_gibt_die_gemessenen_wrapper() -> None:
    """Aufbau-Kontrolle: findet der Test die beiden Wrapper vom 05.09.2026 nicht,
    prüft er nichts — dann hat sich die Bauform geändert, nicht die Regel."""
    namen = {w[0] for w in _wrapper_der_klasse()}
    assert {"get_tagesverlauf", "get_verbrauchsprofil"} <= namen, namen


@pytest.mark.parametrize("wrapper", _wrapper_der_klasse(), ids=lambda w: w[0])
def test_wrapper_traegt_jeden_parameter_seines_ziels(wrapper) -> None:
    name, modul, zielname, call, params = wrapper
    ziel = getattr(importlib.import_module(modul), zielname)
    ziel_params = [
        p.name for p in inspect.signature(ziel).parameters.values()
        if p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
    ]
    gebunden = GEBUNDEN.get(name, {})

    fehlt = [p for p in ziel_params if p not in params and p not in gebunden]
    assert not fehlt, (
        f"`LivePowerService.{name}` kennt {fehlt} nicht, das Ziel "
        f"`{modul}.{zielname}` schon — genau die Lücke aus #408. Entweder in die "
        "Wrapper-Signatur aufnehmen und weiterreichen, oder in `GEBUNDEN` mit Grund "
        "eintragen."
    )

    # Weiterreichen: alles, was der Wrapper vom Ziel kennt, muss im Aufruf
    # ankommen — Keyword-only-Parameter des Ziels namentlich.
    weitergereicht = {kw.arg for kw in call.keywords if kw.arg}
    positional = len(call.args)
    ziel_sig = inspect.signature(ziel).parameters
    for p in ziel_params:
        if p in gebunden:
            continue
        if ziel_sig[p].kind is inspect.Parameter.KEYWORD_ONLY:
            assert p in weitergereicht, (
                f"`LivePowerService.{name}` nimmt `{p}` an, reicht es aber nicht "
                f"als Keyword an `{zielname}` weiter."
            )
    nicht_keyword = [p for p in ziel_params if ziel_sig[p].kind is not inspect.Parameter.KEYWORD_ONLY]
    assert positional + len([p for p in nicht_keyword if p in weitergereicht]) >= len(nicht_keyword), (
        f"`LivePowerService.{name}` reicht nicht alle Positionsparameter an `{zielname}` weiter."
    )

    tot = [p for p in gebunden if p not in ziel_params]
    assert not tot, f"`GEBUNDEN[{name!r}]` nennt Parameter, die das Ziel nicht mehr hat: {tot}"
