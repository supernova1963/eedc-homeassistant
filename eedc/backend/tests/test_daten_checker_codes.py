"""Wächter W-1 und W-3 (Etappe E2 «Daten-Checker: ein Handgriff je Befund», Bauplan §4).

W-1: jeder `CheckErgebnis(`-Aufruf unter `services/daten_checker/` trägt `code=` als Literal; jeder Code steht im Katalog
`handgriffe.py`, der Katalog hat keine Waisen. W-3: die Altfelder `link`/`action_*` sind seit E5 entfernt — kein Erzeuger
setzt sie, `CheckErgebnis` kennt sie nicht mehr (der Handgriff steht in `ziel`/`action`, der Knopf-Text in `knopf`).

Schwesterdateien: test_daten_checker_ziele.py (W-2/W-6), test_daten_checker_texte_fixtures.py (W-8),
test_daten_checker_schema_durchreichung.py (Antwort-Schema).
"""

from __future__ import annotations

import ast
from collections import Counter

from backend.services.daten_checker.handgriffe import HANDGRIFFE, KLASSEN
from backend.tests.werkzeug_daten_checker_stellen import erzeuger_dateien, stellen

#: Erzeuger-Stellen seit E5: 194 (Erhebung Teil A/B) − 6 Restzeilen (V2, entfallen) − 6 Partner-Erzeuger der
#: Zusammenlegungen (V3: Nr 116, 93, 94, 133, 34, 123 gehen in die Zeile ihres Ziel-Codes auf). Ein neuer Erzeuger ⇒
#: Zahl anheben UND Katalog-Zeile.
STELLEN = 182
#: Distinkte Codes seit E5 (Konzept §3.1 R1): 194 − 6 Zusammenlegungen − 6 Restzeilen = 182; jeder Code an genau einer Stelle.
CODES = 182
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


def test_zusammenlegungen_sind_vollzogen():
    """E5 V3: die sechs Partner-Erzeuger sind in der Zeile ihres Ziel-Codes aufgegangen — jeder Code an genau einer Stelle,
    die V2-Restzeilen gibt es nicht mehr."""
    mehrfach = {c: n for c, n in Counter(s.code for s in stellen()).items() if n > 1}
    assert mehrfach == {}
    restzeilen = {"drift_weitere_tage", "batterie_vorzeichen_weitere", "tageswerte_fehlen_weitere", "emob_weitere_monate",
                  "monate_fehlen_weitere", "wp_arbeitszahl_weitere"}
    assert restzeilen.isdisjoint({s.code for s in stellen()}) and restzeilen.isdisjoint(HANDGRIFFE)


def test_katalog_klassen_sind_bekannt():
    assert {h.klasse for h in HANDGRIFFE.values()} <= set(KLASSEN)
    assert Counter(h.klasse for h in HANDGRIFFE.values()) == {"sprung": 117, "aktion": 18, "auskunft": 17, "ok": 30}


def test_w3_kein_erzeuger_setzt_altfelder():
    verstoss = [f"{s.datei}:{s.zeile} {f}" for s in stellen() for f in ALTFELDER if f in s.kw]
    verstoss += [f"{s.datei}:{s.zeile} **" for s in stellen() if s.sterne]
    assert not verstoss, f"Altfelder sind entfallen (W-3): {verstoss}"


def test_w3_kein_erzeuger_schreibt_altfelder_nachtraeglich():
    verstoss = []
    for pfad in erzeuger_dateien():
        for n in ast.walk(ast.parse(pfad.read_text(encoding="utf-8"))):
            if isinstance(n, (ast.Assign, ast.AugAssign)):
                ziele = n.targets if isinstance(n, ast.Assign) else [n.target]
                verstoss += [f"{pfad.name}:{n.lineno}" for z in ziele
                             if isinstance(z, ast.Attribute) and z.attr in ALTFELDER]
    assert not verstoss


def test_altfelder_entfernt_knopf_je_klasse():
    """W-3 nach E5 und E5.7 L1: kein Altfeld mehr; `knopf` nennt den Knopf aller drei Klassen (Aktion aus der Operation,
    Sprung aus dem Katalog, Auskunft «Was gilt», OK ohne Knopf)."""
    from backend.services.daten_checker.kategorien import Aktion, CheckErgebnis
    from backend.services.daten_checker.ziele import ziel_datenquelle, ziel_komponente

    e = CheckErgebnis(kategorie="x", schwere="info", meldung="m")
    assert all(not hasattr(e, f) for f in ALTFELDER)
    assert (e.klasse, e.knopf) == ("auskunft", "Was gilt")
    e = CheckErgebnis(kategorie="x", schwere="warning", meldung="m", code="anschaffungsdatum_fehlt",
                      ziel=ziel_komponente(7, feld="anschaffungsdatum"))
    assert (e.klasse, e.knopf) == ("sprung", "Gerät bearbeiten")
    e = CheckErgebnis(kategorie="x", schwere="info", meldung="m", action=Aktion("reaggregate_day", {"datum": "d"}))
    assert (e.klasse, e.knopf) == ("aktion", "Tag neu aufbauen")
    e = CheckErgebnis(kategorie="x", schwere="ok", meldung="m", code="drift_ok")
    assert e.knopf is None
    # E4 ⚑1: ein Aktion-Code im Zweig ohne Reparaturweg springt auf das fehlende Feld — Knopf «Sensor zuordnen».
    e = CheckErgebnis(kategorie="x", schwere="warning", meldung="m", code="tageswerte_fehlen_tage",
                      ziel=ziel_datenquelle(feld="netzbezug_w"))
    assert (e.klasse, e.knopf) == ("sprung", "Sensor zuordnen")


def test_jeder_sprung_code_hat_einen_knopf():
    """E5.7 L1: ein Katalog-Eintrag der Klasse Sprung ohne `knopf` ist rot — sonst stünde ein leerer Knopf an der Zeile."""
    from backend.services.daten_checker.handgriffe import SPRUNG

    ohne = [c for c, h in HANDGRIFFE.items() if h.klasse == SPRUNG and not h.knopf]
    assert not ohne, f"Sprung-Code ohne Knopf-Text: {ohne}"
    ohne_alternative = [c for c, h in HANDGRIFFE.items() if h.knopf_sprung is not None and h.klasse == SPRUNG]
    assert not ohne_alternative, "knopf_sprung nur an Aktion-Codes (Zweig ohne Reparaturweg)"
