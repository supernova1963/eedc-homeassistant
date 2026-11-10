"""Wächter W-1 und W-3 (Etappe E2 «Daten-Checker: ein Handgriff je Befund», Bauplan §4).

W-1: jeder `CheckErgebnis(`-Aufruf unter `services/daten_checker/` trägt `code=` als Literal; jeder Code steht im Katalog
`handgriffe.py`, der Katalog hat keine Waisen. W-3: die Altfelder `link`/`action_*` setzt kein Erzeuger — sie sind in
`kategorien.py` aus `ziel`/`altlink`/`action` abgeleitet (Properties).

Schwesterdateien: test_daten_checker_ziele.py (W-2/W-6), test_daten_checker_texte_fixtures.py (W-8),
test_daten_checker_schema_durchreichung.py (Antwort-Schema).
"""

from __future__ import annotations

import ast
from collections import Counter

from backend.services.daten_checker.handgriffe import HANDGRIFFE, KLASSEN
from backend.tests.werkzeug_daten_checker_stellen import erzeuger_dateien, stellen

#: Erzeuger-Stellen am Stand E2 (Erhebung Teil A/B: 194). Ein neuer Erzeuger ⇒ Zahl anheben UND Katalog-Zeile.
STELLEN = 194
#: Distinkte Codes in E2 = 194 − 6 Zusammenlegungen (tragen den Code ihres Partners). 182 nach E5 (V2-Restzeilen entfallen).
CODES = 188
ALTFELDER = ("link", "action_kind", "action_params", "action_label")


def test_jede_stelle_traegt_code_als_literal():
    alle = stellen()
    ohne = [f"{s.datei}:{s.zeile}" for s in alle if not isinstance(s.code, str)]
    assert not ohne, f"CheckErgebnis ohne `code=`-Literal: {ohne}"
    assert len(alle) == STELLEN


def test_jeder_code_im_katalog_und_katalog_ohne_waisen():
    benutzt = {s.code for s in stellen()}
    assert benutzt - set(HANDGRIFFE) == set(), f"Code ohne Katalog-Zeile: {sorted(benutzt - set(HANDGRIFFE))}"
    assert set(HANDGRIFFE) - benutzt == set(), f"Katalog-Waise: {sorted(set(HANDGRIFFE) - benutzt)}"
    assert len(benutzt) == CODES


def test_zusammenlegungen_teilen_genau_sechs_mal_einen_code():
    """Teil B: 6 Erzeuger gehen in den Code ihres Partners (V3); sonst ist jeder Code einmal vergeben."""
    mehrfach = {c: n for c, n in Counter(s.code for s in stellen()).items() if n > 1}
    assert mehrfach == {"betriebsart_standalone": 2, "wetterreihe_nachziehen": 3, "standort_fehlt": 2,
                        "tageswerte_ok": 2, "stand_sensoren_ok": 2}


def test_katalog_klassen_sind_bekannt():
    assert {h.klasse for h in HANDGRIFFE.values()} <= set(KLASSEN)
    assert Counter(h.klasse for h in HANDGRIFFE.values()) == {"sprung": 117, "aktion": 18, "auskunft": 17, "ok": 30,
                                                              "entfaellt": 6}


def test_w3_kein_erzeuger_setzt_altfelder():
    verstoss = [f"{s.datei}:{s.zeile} {f}" for s in stellen() for f in ALTFELDER if f in s.kw]
    verstoss += [f"{s.datei}:{s.zeile} **" for s in stellen() if s.sterne]
    assert not verstoss, f"Altfelder nur über ziel/altlink/action (W-3): {verstoss}"


def test_w3_kein_erzeuger_schreibt_altfelder_nachtraeglich():
    verstoss = []
    for pfad in erzeuger_dateien():
        for n in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
            if isinstance(n, (ast.Assign, ast.AugAssign)):
                ziele = n.targets if isinstance(n, ast.Assign) else [n.target]
                verstoss += [f"{pfad.name}:{n.lineno}" for z in ziele
                             if isinstance(z, ast.Attribute) and z.attr in ALTFELDER]
    assert not verstoss


def test_altfelder_sind_abgeleitet():
    from backend.services.daten_checker.kategorien import KEIN_LINK, Aktion, CheckErgebnis
    from backend.services.daten_checker.ziele import HEUTE_INVESTITIONEN, ziel_komponente, ziel_monat

    e = CheckErgebnis(kategorie="x", schwere="info", meldung="m", ziel=ziel_monat(2026, 5, geraet=3, feld="ladung_kwh"))
    assert e.link == "/einstellungen/daten?erfassen=2026-05" and e.klasse == "sprung"
    e = CheckErgebnis(kategorie="x", schwere="info", meldung="m", ziel=ziel_komponente(7, feld="aktiv"),
                      altlink=HEUTE_INVESTITIONEN)
    assert e.link == "/einstellungen/investitionen"
    e = CheckErgebnis(kategorie="x", schwere="info", meldung="m", ziel=ziel_komponente(7, feld="aktiv"), altlink=KEIN_LINK)
    assert e.link is None
    e = CheckErgebnis(kategorie="x", schwere="info", meldung="m", action=Aktion("reaggregate_day", {"datum": "d"}, "L"))
    assert (e.action_kind, e.action_params, e.action_label, e.link, e.klasse) == (
        "reaggregate_day", {"datum": "d"}, "L", None, "aktion")
