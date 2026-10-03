"""W1 — Ergebnisgrößen entstehen nur in der Ergebnis-Leiter (Paket „Ergebnisgrößen Monat/Jahr", 03.10.2026).

**Regel (ADR-001, Lehre N-12/13/18 + #358):** Netto-Ertrag, Ergebnis, SOLL-Erfüllung und ihre Zwischenstufen werden
genau einmal gebildet — in ``core/berechnungen/ergebnis.py``. Bis zu diesem Paket gab es zwölf Bildungsstellen des
Netto-Ertrags mit verschiedener Zusammensetzung (N-601: 212,00 € gegen 206,30 € für denselben Monat), zwei des
Monatsergebnisses und zwei der SOLL-Erfüllung (N-356). Ein Symmetrie-Test hält nur die Stellen, die er aufruft;
dieser Wächter fängt auch die Stelle, die es heute noch nicht gibt.

**Was er findet (AST, baumweit ohne ``tests/``):** einen Namen ``*netto_ertrag*``, ``*gesamtnettoertrag*``,
``*ergebnis_euro*``, ``*soll_erfuellung*``, ``netto_bilanz*``, ``netto_nach_bk`` oder ``kumulative_ersparnis``, der aus
einem Ausdruck mit Rechenoperation (``BinOp``, auch verschachtelt in Aufrufen wie ``round(a + b, 2)``) gebildet wird —
in allen sechs Formen, die der Baum kennt (Gegenprüfung G6):

1. Zuweisung an einen Namen                 ``netto_ertrag = a + b``
2. erweiterte Zuweisung                      ``netto_ertrag -= ust``  (immer — sie IST die Rechnung)
3. Schlüsselwort-Argument                    ``Antwort(netto_ertrag_euro=a + b)``
4. Subscript mit String-Schlüssel            ``result["gesamtnettoertrag_euro"] = round(a - b, 2)``
5. Dict-Literal-Schlüssel                    ``{"netto_ertrag_euro": einsp + ev}``
6. ``round(BinOp)`` als Wert einer der Formen ``x = round(a + b, 2)``

Ein Ausdruck OHNE Rechenoperation (``netto_ertrag_euro=_erg["netto_ertrag"]``) ist Weitergabe, kein Bilden.

**Ausnahmen** sind klassifiziert, je mit Grund — drei Kategorien wie beim P10-Wächter:
``EIGENE_GROESSE`` (fachlich eine andere Größe, eigener Entscheid), ``ALTFELD`` (G4: ``gesamtnettoertrag_euro`` bleibt
mit alter Bedeutung bis zum letzten Leser) und ``NOCH_NICHT_MIGRIERT`` (Konsumenten, die Commit C3 auf die Leiter hängt —
Obergrenze im Test, Ziel 0).

Schwesterdateien: test_ergebnis_leiter.py (Regeln der Leiter), test_ergebnis_symmetrie_monat_jahr.py (W3),
test_ergebnis_monat_probe.py (P2/P5/P12/N-602).
"""

from __future__ import annotations

import ast
import fnmatch
from typing import Iterator

import pytest

from backend.tests.quellbaum import produktivbaum

LAYER = "core/berechnungen/ergebnis.py"

MUSTER = (
    "*netto_ertrag*", "*gesamtnettoertrag*", "*ergebnis_euro*", "*soll_erfuellung*",
    "netto_bilanz*", "netto_nach_bk", "kumulative_ersparnis",
)

#: (datei, name) → Grund. Fachlich eigene Größen — Entscheid in der Vorlage §4 E6 / §5 B5.
EIGENE_GROESSE: dict[tuple[str, str], str] = {
    ("api/routes/aussichten/finanz_prognose.py", "netto_ertrag"):
        "Aussichten-Prognose eines Monats: Hochrechnung, keine Ist-Leiter (E6, eigener Entscheid — Benennung)",
    ("api/routes/aussichten/finanz_prognose.py", "jahres_netto_ertrag"):
        "Aussichten „Jahres-Netto-Ertrag“: Stufe 3 einer Hochrechnung unter dem Namen von Stufe 1 (E6, §9 Nr. 3)",
    ("core/calculations.py", "netto_ertrag"):
        "`GET /monatsdaten/{id}` — kein Frontend-Aufrufer; Entfernung ist ein eigener Entscheid (E6, §9 Nr. 2)",
    ("api/routes/ha_export/anlage_komponenten.py", "historischer_netto_ertrag"):
        "ROI-Größe (Netto-Ertrag + WP- + E-Auto-Ersparnis, ohne Stromrechnung) — eigene Frage (B5, ROI-Zeile)",
    ("api/routes/cockpit/uebersicht.py", "kumulative_ersparnis"):
        "ROI-Zwischenstufe der Übersicht (Netto-Ertrag + WP + E-Mob − Betriebskosten des Zeitraums, OHNE Stromrechnung) "
        "— Zähler des ROI-Fortschritts, keine Stufe der Leiter (B5, Empfehlung der Vorlage: Ausnahme, kein neuer UI-Begriff)",
    ("services/pdf/builders/jahresbericht.py", "netto_nach_bk"):
        "ROI-Zwischenstufe des Jahresberichts (Netto-Ertrag − Betriebskosten des Zeitraums, ohne Stromrechnung) — "
        "Zähler von Rendite und Amortisation (B5, wie `kumulative_ersparnis`)",
    ("api/routes/monatsdaten.py", "netto_bilanz_euro"):
        "Auswertungen → Tabelle: Netto-Ertrag (seit A1 mit Sonstigem) − Netzbezugskosten OHNE WP-/E-Mob-Ersparnis und Betriebskosten — "
        "eine eigene Größe dieser Tabelle, nicht Stufe 2 der Leiter (B5-Prüfung im Bau, Feld-Docstring)",
    ("services/energie_profil/tage_werte.py", "netto_bilanz"):
        "Cockpit → Tag: dieselbe Tabellen-Größe wie `netto_bilanz_euro` der Monatsreihe, je Tag (eigene Größe)",
}

#: G4 — Altfelder mit alter Bedeutung bis zum letzten Leser. Leer seit C3 (`gesamtnettoertrag_euro` entfernt).
ALTFELD: dict[tuple[str, str], str] = {}

#: Konsumenten, die noch nicht auf die Leiter umgehängt sind. Leer seit C3 (B5 abgearbeitet); die Liste bleibt als
#: Andockpunkt und darf nur schrumpfen.
NOCH_NICHT_MIGRIERT: dict[tuple[str, str], str] = {}
OBERGRENZE_NOCH_NICHT_MIGRIERT = 0


def _hat_rechnung(knoten: ast.AST) -> bool:
    """Steckt irgendwo im Ausdruck eine Rechenoperation (auch in Aufruf-Argumenten wie ``round(a + b, 2)``)?"""
    return any(isinstance(n, ast.BinOp) for n in ast.walk(knoten))


def _passt(name: str) -> bool:
    return any(fnmatch.fnmatchcase(name, m) for m in MUSTER)


def bildungen(baum: ast.AST) -> Iterator[tuple[str, int, str]]:
    """(name, zeile, form) je Bildung einer Ergebnisgröße aus einer Rechnung."""
    for n in ast.walk(baum):
        if isinstance(n, ast.Assign):
            if not _hat_rechnung(n.value):
                continue
            for ziel in n.targets:
                for z in ast.walk(ziel):
                    if isinstance(z, ast.Name) and _passt(z.id):
                        yield z.id, n.lineno, "Zuweisung"
                    elif isinstance(z, ast.Attribute) and _passt(z.attr):
                        yield z.attr, n.lineno, "Attribut"
                    elif (isinstance(z, ast.Subscript) and isinstance(z.slice, ast.Constant)
                          and isinstance(z.slice.value, str) and _passt(z.slice.value)):
                        yield z.slice.value, n.lineno, "Subscript"
        elif isinstance(n, ast.AnnAssign) and n.value is not None and _hat_rechnung(n.value):
            if isinstance(n.target, ast.Name) and _passt(n.target.id):
                yield n.target.id, n.lineno, "Zuweisung"
        elif isinstance(n, ast.AugAssign):
            z = n.target
            if isinstance(z, ast.Name) and _passt(z.id):
                yield z.id, n.lineno, "erweiterte Zuweisung"
            elif (isinstance(z, ast.Subscript) and isinstance(z.slice, ast.Constant)
                  and isinstance(z.slice.value, str) and _passt(z.slice.value)):
                yield z.slice.value, n.lineno, "erweiterte Zuweisung"
        elif isinstance(n, ast.keyword):
            if n.arg and _passt(n.arg) and _hat_rechnung(n.value):
                yield n.arg, n.value.lineno, "Schlüsselwort"
        elif isinstance(n, ast.Dict):
            for k, v in zip(n.keys, n.values):
                if (isinstance(k, ast.Constant) and isinstance(k.value, str) and _passt(k.value)
                        and _hat_rechnung(v)):
                    yield k.value, k.lineno, "Dict-Literal"


def _funde() -> list[tuple[str, str, int, str]]:
    out = []
    for datei in produktivbaum():
        if datei.rel == LAYER:
            continue
        for name, zeile, form in bildungen(datei.baum):
            out.append((datei.rel, name, zeile, form))
    return out


def test_ergebnisgroessen_entstehen_nur_in_der_leiter():
    erlaubt = {**EIGENE_GROESSE, **ALTFELD, **NOCH_NICHT_MIGRIERT}
    verstoesse = [f for f in _funde() if (f[0], f[1]) not in erlaubt]
    assert not verstoesse, (
        "Ergebnisgröße außerhalb von core/berechnungen/ergebnis.py aus einer Rechnung gebildet:\n  "
        + "\n  ".join(f"{d}:{z} `{n}` ({form})" for d, n, z, form in verstoesse)
        + "\n\nDie Größe kommt aus der Leiter (`berechne_ergebnis`, `soll_erfuellung`, `falte_zeitraum`). "
        "Ist sie fachlich eine ANDERE Größe, gehört sie mit Grund in EIGENE_GROESSE."
    )


def test_jede_ausnahme_trifft_noch_eine_stelle():
    """Eine Ausnahme ohne Fundstelle ist ein Persil-Schein für die nächste — sie muss mit der Stelle gehen."""
    getroffen = {(d, n) for d, n, _z, _f in _funde()}
    tot = [k for k in {**EIGENE_GROESSE, **ALTFELD, **NOCH_NICHT_MIGRIERT} if k not in getroffen]
    assert not tot, f"Ausnahmen ohne Fundstelle — streichen: {tot}"


def test_noch_nicht_migriert_waechst_nicht():
    assert len(NOCH_NICHT_MIGRIERT) <= OBERGRENZE_NOCH_NICHT_MIGRIERT


# ── Selbsttest (G6): jede der sechs Altformen wird gefunden ────────────────────────────────────────────────────────

ALTFORMEN = {
    "Zuweisung": "netto_ertrag = einspeise + ev\n",
    "erweiterte Zuweisung": "netto_ertrag -= ust_eigenverbrauch\n",
    "Schlüsselwort": "Antwort(netto_ertrag_euro=einspeise + ev)\n",
    "Subscript": 'result["gesamtnettoertrag_euro"] = round(e + v - k, 2)\n',
    "Dict-Literal": 'zeile = {"netto_ertrag_euro": einsp_eur + ev_eur + sonstige_eur}\n',
    "round(BinOp)": "monatsergebnis_euro = round(gesamt - bk + sonst, 2)\n",
}


@pytest.mark.parametrize("form,quelle", list(ALTFORMEN.items()))
def test_selbsttest_jede_altform_wird_gefunden(form, quelle):
    gefunden = list(bildungen(ast.parse(quelle)))
    assert gefunden, f"Altform „{form}“ wird nicht erkannt: {quelle!r}"


def test_selbsttest_weitergabe_ohne_rechnung_ist_kein_fund():
    assert not list(bildungen(ast.parse('Antwort(netto_ertrag_euro=_erg["netto_ertrag"], ergebnis_euro=x)\n')))


# ── G1: der USt-Satz hat genau EINEN Eingang ───────────────────────────────────────────────────────────────────────

USt_EINGANG_ERLAUBT = {"services/ust_satz.py", "core/berechnungen/ust_eigenverbrauch.py", "core/berechnungen/ergebnis.py"}


def test_ust_jahresanteil_nur_im_eingang():
    """Bis 03.10.2026 bildeten sieben Stellen ihren eigenen ``UstJahresanteil(`` — drei Lesarten desselben Satzes
    (Probe: 20,21 · 35,96 · 18,90 €). Seit G1 wählt nur ``services/ust_satz.py``, was in den Satz eingeht."""
    funde = []
    for datei in produktivbaum():
        if datei.rel in USt_EINGANG_ERLAUBT:
            continue
        for n in ast.walk(datei.baum):
            if isinstance(n, ast.Call) and getattr(n.func, "id", getattr(n.func, "attr", None)) == "UstJahresanteil":
                funde.append(f"{datei.rel}:{n.lineno}")
    assert not funde, "UstJahresanteil außerhalb von services/ust_satz.py gebildet:\n  " + "\n  ".join(funde)
