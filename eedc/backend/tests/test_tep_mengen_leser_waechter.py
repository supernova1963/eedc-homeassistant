"""Wächter S5-R6: wer die Mengen-Spalten der Stunden- und Tageszeile roh liest (HA-Bauform S5, Bauplan §4 S5-R6, §10a, §10f).

**Regel.** Seit S5a gibt es für Stundenmengen EINE Lesestelle — ``services/energie_profil/kanal_stunden.py``
(``stunden_der_tage``: an einem Kanal-Tag die Mischzeilen, sonst die Stundenzeile; dazu ``pv_ist_je_tag``,
``komponenten_der_tage``, ``verworfen_der_tage`` für die Tagesmengen der Tageszeile). Keine Funktion außerhalb der
erlaubten Liste liest die **15 Mengen-Spalten** (``MENGEN``) aus ``TagesEnergieProfil`` (TEP) oder
``TagesZusammenfassung`` (TZ) selbst — sonst rechnete sie an einem Kanal-Tag die gefalteten Mengen der Stundenzeile
statt der Mengen von *Cockpit → Tag* (die «zweite Wahrheit», die S5 beendet).

**Empfänger-Regel (kein Namens-Sweep, E-S5-0 Etappe 2):** eine Funktion zählt, wenn sie

1. TEP/TZ als **ORM-Empfänger** hat — ``select(…)``/``.query(…)`` mit dem Modell oder einer seiner Spalten als
   Argument, oder einen Attributzugriff ``Modell.<Spalte>`` am Modell selbst —, **und**
2. auf eine Mengen-Spalte zugreift: Attribut ``x.<spalte>`` (gleich welcher Empfänger), ``getattr(x, "<spalte>")``,
   oder eine Literal-Zeichenkette ``"<spalte>"`` in einer Funktion mit dynamischem ``getattr``.

Die Mischzeile trägt dieselben Attributnamen wie die Stundenzeile (S5-R1, «Datenform der TEP-Zeile») — ein Leser,
der ``stunden_der_tage`` ruft und ``zeile.pv_kw`` liest, hat keinen ORM-Empfänger und ist grün.

**Modellnamen**, die der Wächter kennt: ``from backend.models.tages_energie_profil import …`` (auch ``as``-Alias,
auch über ``backend.models``), ``import backend.models.tages_energie_profil as m`` (``m.TagesEnergieProfil``), die
Klassennamen selbst, und lokale Aliase ``tz = TagesZusammenfassung`` bzw. ``tz, tep = TagesZusammenfassung,
TagesEnergieProfil``. Je Funktion gilt die äußerste ``def`` (eingeschachtelte gehören dazu); Modulcode zählt als
Funktion ``<modul>``.

**Stand nach S5a: leer** (Gleichheit wie ``IMPORTEURE_STAND`` in ``test_kanal_lesen_waechter.py``, Bauplan §10f): außerhalb
der Liste liest NIEMAND roh. Wer eine Ausnahme braucht, trägt sie mit Grund in ``ERLAUBT`` ein.

**Benannt (E-S5-2 H-E → A):** die Daten-Checker-Regeln lesen über ``komponenten_der_tage`` — deren Mischung trägt nur die
Bilanz- und Sonstiges-Schlüssel aus den Kanälen; ``wallbox_<id>``/``eauto_<id>``/``waermepumpe_<id>`` bleiben an jedem Tag
die der Tageszeile (die E-Mob-Doppelzählung prüft gespeicherte Altlast; S5b nimmt den Befund an Kanal-Tagen weg).

**Nicht erfasst (benannt):** ``text("SELECT pv_kw …")`` (rohes SQL — es steht im Baum nur in ``erlaubt``-Dateien und
in ``kanal_stunden._LUECKE_SQL`` über ``kanal_statistik``), zusammengesetzte Spaltennamen (``f"{achse}_kw"``) und eine
Zeile, die über einen Rückgabewert aus einer anderen Funktion kommt (``rows = await _lade(...)`` und dann
``r.pv_kw`` — der Wächter sieht den Empfänger in ``_lade``, nicht beim Leser; deshalb laden die Lesestellen ihre
Zeilen selbst).

Schwesterdateien: ``test_kanal_lesen_waechter.py`` (Importeure der Lese-Schicht), ``test_s5_stunden_der_tage.py``.
"""

from __future__ import annotations

import ast

from backend.tests.quellbaum import produktivbaum

#: Die 15 Mengen-Spalten (Bauplan S5 §4 S5-R6, Auftrag E-S5-2 Punkt 7).
MENGEN = frozenset({
    "pv_kw", "verbrauch_kw", "einspeisung_kw", "netzbezug_kw", "batterie_kw", "waermepumpe_kw", "wallbox_kw",
    "ueberschuss_kw", "defizit_kw", "spannen", "komponenten_kwh", "verworfen", "nachtrag", "ueberschuss_kwh",
    "defizit_kwh",
})
MODELLE = ("TagesEnergieProfil", "TagesZusammenfassung")
MODELL_MODUL = "backend.models.tages_energie_profil"

#: Erlaubt: Datei (relativ zu ``backend/``, Präfix mit ``/`` am Ende = Verzeichnis) oder ``datei::funktion`` → Grund.
ERLAUBT: dict[str, str] = {
    "services/energie_profil/kanal_stunden.py": "die Lesestelle selbst (S5-R1: stunden_der_tage, pv_ist_je_tag, …)",
    "services/snapshot/": "Bestands-Tagespfad (Lesart 1, Schreiber und Reaggregation; S5b E-S5-4)",
    "services/energie_profil/aggregator.py": "Schreiber aggregate_day (S5b E-S5-3)",
    "services/energie_profil/monats_aus_tagen.py": "Monats-Faltung Lesart 1 (falte_monat, Bauplan §3 (A))",
    "api/routes/energie_profil/repair.py": "Werkbank-Reparatur (repair*)",
    "api/routes/repair.py": "Werkbank-Reparatur (repair*)",
    "services/repair_orchestrator.py": "Werkbank-Reparatur (repair*)",
    "services/verwerfen_vor_quellbeginn.py": "Werkbank «Werte vor dem Sensorbeginn verwerfen» (schreibt die Zeilen)",
    "api/routes/energie_profil/diagnose.py::get_debug_rohdaten": "zeigt bewusst die gespeicherte Zeile (§10a)",
    "services/energie_profil/rollup.py": "Schreiber S5b (Monats-Rollup, §10a)",
    "services/energie_profil/archiv_nachzug.py": "Schreiber S5b (PR beim Archiv-Nachzug, §10a)",
    # Sichten-Mischpfade (O-3, §10f): sie mischen an einem Kanal-Tag selbst (mische_komponenten/mische_verworfen) und
    # lesen an Bestandstagen die Tageszeile (Lesart 1).
    "api/routes/energie_profil/monat.py::_komponenten_summen": "Sichten-Mischpfad (O-3)",
    "api/routes/energie_profil/monat.py::_tagesbilanz": "Sichten-Mischpfad (O-3)",
    "api/routes/energie_profil/tage.py::get_tages_zusammenfassungen": "Sichten-Mischpfad (O-3)",
    "api/routes/energie_profil/tage.py::_komp": "Sichten-Mischpfad (O-3)",
    "services/energie_profil/modus_split_monat.py::_lade_tages_eingaenge": "Sichten-Mischpfad (O-3, Rückfall V-1)",
    "services/energie_profil/tage_werte.py::_tagesbilanz": "Sichten-Mischpfad (O-3)",
    "services/energie_profil/waerme_verlauf.py::_zaehlerstrom_je_tag": "Sichten-Mischpfad (O-3, H-4)",
    # Lesart-1-Regeln des Daten-Checkers (§10f): Gegenstand ist die gespeicherte Zeile.
    "services/daten_checker/energieprofil.py::_check_bestandstage_ohne_regelmarke": "Lesart-1-Regel E7 (§10f)",
    "services/daten_checker/energieprofil.py::_check_nachtrag_nach_eingefrorenem_zaehler": (
        "Lesart-1-Regel N-567 (§10f) — nimmt Kanal-Tage aus, dort wirkt kein Deckel"),
    # E-S5-2 H-W → A (Entscheid Master 18.10.2026):
    "api/routes/energie_profil/serien.py::get_stundenwerte": (
        "Sichten-Mischpfad /stunden, Vortag…Folgetag über stunden_des_tages"),
    "services/energie_profil/vergleichstage.py::<modul>": "Lesart-1-Kandidaten, E-S5-1b H-4 (_SPALTE)",
    "services/energie_profil/vergleichstage.py::tage_ohne_tagesvergleich": "Lesart-1-Kandidaten, E-S5-1b H-4",
    "services/korrekturprofil_aggregator.py::_lade_tagesist_skalar": (
        "TZ nur lern_soll_kwh — Prognose-Feld, Mengen aus der Lesestelle; Fehlalarm der Regel"),
    "api/routes/ha_export/anlage_steuerung.py::_ueberschuss_heute": (
        "HA-Export-Mischpfad: Bestandstag TZ, Kanal-Tag Σ Mischzeilen; der AST sieht ihn nicht (Abfrage in "
        "_lade_tagesprofil), die TSV schon — als Dokumentation in der Liste"),
}

#: Funktionen außerhalb der Liste, die roh lesen — Stand nach S5a: leer (Bauplan §10f; E-S5-2 H-W → A, Entscheid Master).
STAND: set[tuple[str, str]] = set()


def _erlaubt(rel: str, funktion: str) -> bool:
    for schluessel in ERLAUBT:
        datei, _, fn = schluessel.partition("::")
        if fn:
            if rel == datei and funktion == fn:
                return True
        elif rel == datei or (datei.endswith("/") and rel.startswith(datei)):
            return True
    return False


def _modellnamen(baum: ast.Module) -> tuple[set[str], set[str]]:
    """(Namen der Modellklassen, Namen des Modell-Moduls) aus den Importen einer Datei (auch in Funktionen)."""
    klassen: set[str] = set(MODELLE)
    module: set[str] = set()
    for n in ast.walk(baum):
        if isinstance(n, ast.ImportFrom) and n.module in (MODELL_MODUL, "backend.models", "models.tages_energie_profil",
                                                          "models"):
            klassen |= {a.asname or a.name for a in n.names if a.name in MODELLE}
            module |= {a.asname or a.name for a in n.names if a.name == "tages_energie_profil"}
        elif isinstance(n, ast.Import):
            module |= {a.asname for a in n.names if a.name == MODELL_MODUL and a.asname}
    return klassen, module


def _ist_modell(knoten: ast.AST, klassen: set[str], module: set[str]) -> bool:
    if isinstance(knoten, ast.Name):
        return knoten.id in klassen
    if isinstance(knoten, ast.Attribute) and knoten.attr in MODELLE:
        return isinstance(knoten.value, ast.Name) and knoten.value.id in module
    return False


def _lokale_aliase(fn: ast.AST, klassen: set[str], module: set[str]) -> set[str]:
    """``tz = TagesZusammenfassung`` und ``tz, tep = TagesZusammenfassung, TagesEnergieProfil`` in der Funktion."""
    namen = set(klassen)
    for n in ast.walk(fn):
        if not isinstance(n, ast.Assign):
            continue
        for ziel in n.targets:
            if isinstance(ziel, ast.Name) and _ist_modell(n.value, namen, module):
                namen.add(ziel.id)
            elif isinstance(ziel, ast.Tuple) and isinstance(n.value, ast.Tuple):
                for z, w in zip(ziel.elts, n.value.elts):
                    if isinstance(z, ast.Name) and _ist_modell(w, namen, module):
                        namen.add(z.id)
    return namen


def _wurzel_ist_modell(knoten: ast.AST, klassen: set[str], module: set[str]) -> bool:
    """``TEP``, ``TEP.datum``, ``TEP.datum.desc()``, ``getattr(TEP, s)`` — ein Ausdruck, der am Modell hängt."""
    for n in ast.walk(knoten):
        if _ist_modell(n, klassen, module):
            return True
    return False


def _empfaenger(fn: ast.AST, klassen: set[str], module: set[str]) -> bool:
    for n in ast.walk(fn):
        if isinstance(n, ast.Call):
            name = n.func.attr if isinstance(n.func, ast.Attribute) else getattr(n.func, "id", None)
            if name in ("select", "query") and any(_wurzel_ist_modell(a, klassen, module) for a in n.args):
                return True
        if isinstance(n, ast.Attribute) and _ist_modell(n.value, klassen, module):
            return True
    return False


def _mengen_zugriffe(fn: ast.AST) -> list[tuple[int, str]]:
    funde: list[tuple[int, str]] = []
    dyn_getattr = False
    for n in ast.walk(fn):
        if isinstance(n, ast.Attribute) and n.attr in MENGEN:
            funde.append((n.lineno, n.attr))
        elif isinstance(n, ast.Call) and getattr(n.func, "id", None) == "getattr" and len(n.args) >= 2:
            arg = n.args[1]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                if arg.value in MENGEN:
                    funde.append((n.lineno, arg.value))
            else:
                dyn_getattr = True
    if dyn_getattr:
        funde += [(n.lineno, n.value) for n in ast.walk(fn)
                  if isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in MENGEN]
    return funde


def _funktionen(baum: ast.Module):
    """(Name, Knoten) je äußerster Funktion (Methoden einzeln) und ``<modul>`` für den Modulcode."""
    modul = ast.Module(body=[s for s in baum.body if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef,
                                                                        ast.ClassDef))], type_ignores=[])
    yield "<modul>", modul
    for s in baum.body:
        if isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield s.name, s
        elif isinstance(s, ast.ClassDef):
            for m in s.body:
                if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    yield m.name, m


def roh_leser(baum: ast.Module) -> dict[str, list[tuple[int, str]]]:
    """Je Funktion mit ORM-Empfänger TEP/TZ ihre Zugriffe auf Mengen-Spalten."""
    klassen, module = _modellnamen(baum)
    out: dict[str, list[tuple[int, str]]] = {}
    for name, fn in _funktionen(baum):
        namen = _lokale_aliase(fn, klassen, module)
        if not _empfaenger(fn, namen, module):
            continue
        zugriffe = _mengen_zugriffe(fn)
        if zugriffe:
            out[name] = zugriffe
    return out


def _alle() -> dict[tuple[str, str], list[tuple[int, str]]]:
    out: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for datei in produktivbaum():
        if datei.rel.startswith("models/"):
            continue
        for fn, zugriffe in roh_leser(datei.baum).items():
            out[(datei.rel, fn)] = zugriffe
    return out


def test_ausserhalb_der_erlaubten_liste_liest_niemand_roh():
    ausserhalb = {k: v for k, v in _alle().items() if not _erlaubt(*k)}
    assert set(ausserhalb) == STAND, (
        "Funktionen lesen Mengen-Spalten aus TagesEnergieProfil/TagesZusammenfassung roh (S5-R6):\n  "
        + "\n  ".join(f"{rel}::{fn} — " + ", ".join(f"{z}:{s}" for z, s in sorted(set(v))[:6])
                      for (rel, fn), v in sorted(ausserhalb.items()))
        + "\n\nStundenmengen über kanal_stunden.stunden_der_tage, Tagesmengen über pv_ist_je_tag/komponenten_der_tage/"
        "verworfen_der_tage. Eine begründete Ausnahme gehört mit Grund in ERLAUBT."
    )


def test_jeder_eintrag_der_liste_trifft_etwas():
    """Die Liste wächst nicht still: jede Datei bzw. Funktion der Liste existiert (auch eingeschachtelt — ``tage._komp``,
    ``monat._tagesbilanz`` stehen in ``get_tages_zusammenfassungen`` bzw. ``_monatsbilanz``; der Wächter meldet je äußerster
    Funktion, ein eingeschachtelter Eintrag benennt den Mischpfad, den die Liste meint)."""
    dateien = {d.rel: d for d in produktivbaum()}
    fehlt = []
    for schluessel in ERLAUBT:
        datei, _, fn = schluessel.partition("::")
        if datei.endswith("/"):
            if not any(r.startswith(datei) for r in dateien):
                fehlt.append(schluessel)
            continue
        if datei not in dateien:
            fehlt.append(schluessel)
        elif fn and fn != "<modul>" and fn not in {n.name for n in ast.walk(dateien[datei].baum)
                               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}:
            fehlt.append(schluessel)
    assert not fehlt, f"Einträge in ERLAUBT ohne Datei/Funktion im Baum: {fehlt}"


def test_positivkontrolle_die_erlaubten_leser_werden_gefunden():
    """Der Wächter sieht die Lesestelle und den Schreiber — sonst prüfte er nichts."""
    funde = _alle()
    assert ("services/energie_profil/kanal_stunden.py", "verworfen_der_tage") in funde
    assert any(rel == "services/energie_profil/aggregator.py" for rel, _ in funde)
    assert ("services/daten_checker/energieprofil.py", "_check_bestandstage_ohne_regelmarke") in funde


# ── Gegenproben: jede Form wird gefunden ──────────────────────────────────────

GEGENPROBEN = {
    "select": (
        "from backend.models.tages_energie_profil import TagesEnergieProfil\n"
        "async def f(db):\n    rows = (await db.execute(select(TagesEnergieProfil))).scalars().all()\n"
        "    return [r.pv_kw for r in rows]\n"),
    "query": (
        "from backend.models.tages_energie_profil import TagesZusammenfassung\n"
        "def f(db):\n    return [z.komponenten_kwh for z in db.query(TagesZusammenfassung).all()]\n"),
    "modell-attribut": (
        "from backend.models.tages_energie_profil import TagesZusammenfassung\n"
        "async def f(db):\n    return await db.execute(select(TagesZusammenfassung.datum, TagesZusammenfassung.verworfen))\n"),
    "lokaler-alias": (
        "from backend.models.tages_energie_profil import TagesZusammenfassung\n"
        "async def f(db):\n    tz = TagesZusammenfassung\n    return await db.execute(select(tz.datum, tz.nachtrag))\n"),
    "getattr-literal": (
        "from backend.models.tages_energie_profil import TagesEnergieProfil as TEP\n"
        "async def f(db):\n    rows = (await db.execute(select(TEP))).scalars().all()\n"
        "    return [getattr(r, 'einspeisung_kw') for r in rows]\n"),
    "literal-liste": (
        "from backend.models.tages_energie_profil import TagesEnergieProfil\n"
        "FELDER = ('pv_kw', 'netzbezug_kw')\n"
        "async def f(db):\n    rows = (await db.execute(select(TagesEnergieProfil))).scalars().all()\n"
        "    return [[getattr(r, s) for s in ('pv_kw', 'netzbezug_kw')] for r in rows]\n"),
    "alias-import": (
        "from backend.models import TagesEnergieProfil as T\n"
        "async def f(db):\n    return [r.spannen for r in (await db.execute(select(T))).scalars()]\n"),
    "modul-alias": (
        "import backend.models.tages_energie_profil as m\n"
        "async def f(db):\n    return [r.wallbox_kw for r in (await db.execute(select(m.TagesEnergieProfil))).scalars()]\n"),
    "methode": (
        "from backend.models.tages_energie_profil import TagesZusammenfassung\n"
        "class C:\n    async def f(self):\n"
        "        return [z.defizit_kwh for z in (await self.db.execute(select(TagesZusammenfassung))).scalars()]\n"),
}

#: Formen, die NICHT zählen: die Mischzeile aus der Lesestelle (kein ORM-Empfänger), Bahnen der Stundenzeile.
GEGENPROBEN_GRUEN = {
    "lesestelle": (
        "from backend.services.energie_profil.kanal_stunden import stunden_der_tage\n"
        "async def f(db):\n    return [z.pv_kw for z in await stunden_der_tage(db, 1, None, None)]\n"),
    "bahn": (
        "from backend.models.tages_energie_profil import TagesEnergieProfil\n"
        "async def f(db):\n    return [r.soc_prozent for r in (await db.execute(select(TagesEnergieProfil))).scalars()]\n"),
}


def test_gegenprobe_jede_form_wird_gefunden():
    for name, quelle in GEGENPROBEN.items():
        assert roh_leser(ast.parse(quelle)), f"Form {name!r} nicht gefunden"


def test_gegenprobe_lesestelle_und_bahnen_bleiben_gruen():
    for name, quelle in GEGENPROBEN_GRUEN.items():
        assert not roh_leser(ast.parse(quelle)), f"Form {name!r} fälschlich gefunden"


def test_gegenprobe_eine_neue_route_mit_select_tep_pv_kw_wuerde_rot(monkeypatch):
    """Eine neue Route, die ``select(TagesEnergieProfil)`` liest und ``pv_kw`` summiert, macht den Wächter rot."""
    import backend.tests.test_tep_mengen_leser_waechter as w
    from backend.tests.quellbaum import Quelldatei

    quelle = GEGENPROBEN["select"]
    neu = Quelldatei(pfad=None, rel="api/routes/neue_sicht.py", quelle=quelle, baum=ast.parse(quelle))
    echt = produktivbaum()
    monkeypatch.setattr(w, "produktivbaum", lambda: (*echt, neu))
    ausserhalb = {k for k in w._alle() if not w._erlaubt(*k)}
    assert ("api/routes/neue_sicht.py", "f") in ausserhalb
    assert ausserhalb != STAND
