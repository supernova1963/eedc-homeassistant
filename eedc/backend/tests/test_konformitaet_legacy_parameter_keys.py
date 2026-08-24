"""Konformitäts-Wächter: kein toter Investitions-Parameter-Schlüssel im Code.

**Der Anlass, 2026-08-23.** Die v3.25.0-Konsolidierung hat die Investitions-
Parameter auf einen Kanon gezogen (`core/investition_parameter.py`) und
Bestandsdaten per Start-Migration umbenannt
(`core/database.py::_migrate_investitionen_parameter_keys_v325`). Formular und
Wizard schreiben seither nur noch den Kanon. **Fünf Stellen las bzw. schrieb
weiterhin die alten Namen** — und weil ein fehlender Schlüssel in Python kein
Fehler ist, sondern still `None` liefert, hat das niemand gemerkt:

* `api/routes/import_export/demo_data.py` schrieb fünf alte Namen ⇒ die
  Demo-Anlage hatte ein E-Auto ohne wirksame Fahrleistung, ohne PV-Ladeanteil,
  ohne V2H, ohne Batteriekapazität und eine Wallbox ohne Ladeleistung.
* `services/daten_checker/stammdaten.py` prüfte auf `nutzt_v2h` und
  `nutzt_arbitrage` ⇒ **zwei Prüfer, die nie gemeldet haben**, plus ein
  dritter, der nur halb prüfte (`km_jahr`).
* `services/pdf/builders/anlagendokumentation.py` las vier tote Namen ⇒ vier
  Zeilen im Dokumentations-PDF, die nie erscheinen konnten.
* `models/investition.py` führte drei davon als **Docstring-Beispiel** — die
  Quelle, aus der die anderen entstanden sind.

**Abgrenzung zu ADR-002/P3-b — das ist kein zweiter Anlauf derselben Regel.**
`test_wurzelmuster_konformitaet.py::test_p3b_parameter_schluessel_stehen_im_kanon`
prüft baumweit, ob ein Literal-Schlüssel **überhaupt existiert**, und rechnet
dafür `LEGACY_PARAM_KEYS` ausdrücklich zur erlaubten Menge — ein alter Name ist
dort also **gültig**, denn die Frage lautet „kennt eedc diesen Schlüssel?".
Dieser Test stellt die andere Frage: „ist der Name noch der **aktuelle**?" Genau
deshalb konnte P3-b mit Baseline 0 grün stehen, während `demo_data.py` fünf
tote Namen schrieb. Zwei Regeln, zwei Tests; wer eine davon streicht, verliert
die andere nicht mit.

**Warum ein Wächter und nicht nur der Fix.** Der Fix repariert fünf Stellen,
die Klasse entsteht aber bei *jeder* künftigen Umbenennung neu: Wer einen
Schlüssel in den Kanon-Maps umbenennt und eine Lesestelle übersieht, bekommt
keine Fehlermeldung — er bekommt eine stille Null. Genau die Bauform der
Prüfer, die in den Etappen E1–E3 als „grün, ohne zu messen" gefunden wurden,
nur im Produktcode.

**AST statt Grep, und zwar zweimal geschärft.** Gesucht werden nicht
Textmuster und auch nicht einfach alle String-Literale, sondern **Zugriffe**:

1. *Lesen* — das Literal steht in einem Index (`params["km_jahr"]`) oder in
   einem `.get(...)`-Aufruf (`param.get("nutzt_v2h")`).
2. *Schreiben* — das Literal ist Schlüssel in einem Dict, das an ein
   `parameter=`-Argument gebunden wird (so schreiben die Demo-Daten).

⚠ **Der erste Entwurf nahm alle String-Literale und zeigte damit aufs falsche
Objekt.** Er meldete sechs Stellen für `'kwp'` — durchweg Dict-Schlüssel in
*eigenen* Ausgabe-Strukturen (`{"kwp": round(anlage.leistung_kwp, 1)}` im
Community-Payload, Ausrichtungs-Gruppen der Prognose), die mit
`Investition.parameter` nichts zu tun haben. Ein Wächter, der mit sechs
sachfremden Ausnahmen startet, bewacht nichts; er gewöhnt den Leser daran,
Einträge nachzutragen. Kommentare kennt die AST ohnehin nicht — das ist hier
erwünscht, denn mehrere Kommentare beschreiben den historischen Bug absichtlich.

Ein Docstring zählt nicht als Zugriff. Für den Docstring-Fall in
`models/investition.py` steht deshalb eine eigene, getrennte Probe unten — er
ist die Quelle, aus der die anderen Stellen abgeschrieben wurden.

⛔ **Was dieser Wächter NICHT sieht, gemessen an den eigenen Fundstellen.**
Die Gegenprobe gegen den Stand vor dem Fix fängt `demo_data.py` und
`stammdaten.py`, **nicht** aber `anlagendokumentation.py`: Dort stehen die
Schlüssel in einer Tabelle von Tupeln und werden erst später über eine
*Variable* gelesen (`params[key]`). Ein Literal, das nie selbst als Index
auftaucht, ist ohne Datenflussanalyse nicht von einem beliebigen Text zu
unterscheiden — und eine Heuristik „erstes Tupel-Element in einer Liste" würde
jede Label-Tabelle im Baum melden.

**Diese Lücke wird nicht verschwiegen, sie wird gedeckt:** Die eine bekannte
Tabelle dieser Bauform hat unten ihre eigene Probe
(`test_pdf_leseliste_nennt_nur_kanon_namen`). Kommt eine zweite Tabelle dazu,
braucht sie eine eigene — dieser Absatz ist der Hinweis darauf. *Ein Prüfer,
der seine Grenze nicht nennt, wird für einen gehalten, der sie nicht hat.*
"""

from __future__ import annotations

import ast
from pathlib import Path

from backend.tests.quellbaum import produktivbaum

import pytest

from backend.core.investition_parameter import LEGACY_PARAM_KEYS


_BACKEND_ROOT = Path(__file__).resolve().parents[1]  # eedc/backend/


# Ausnahmen — **je Datei UND je Name**, nie eine ganze Datei.
#
# ⚠ Eine dateiweite Freistellung wäre der bequeme Weg und der falsche: Sie
# stellt auch jeden Namen frei, der dort morgen dazukommt. `stammdaten.py`
# zeigt es — drei tote Zugriffe wurden am 23.08. darin repariert, zwei
# bewusste Fallbacks bleiben stehen. Wäre die Datei als Ganzes ausgenommen,
# hätte der Wächter die drei Reparaturen nie eingefordert und würde einen
# Rückfall nicht melden. Dieselbe Linie wie beim P10-Wächter, der aus genau
# diesem Grund funktions-granular arbeitet.
#
# `"*"` gibt es nur für die beiden Karten, die den Kanon überhaupt definieren.
ERLAUBT: dict[str, dict[str, str]] = {
    "core/investition_parameter.py": {"*": "SoT — führt die Legacy→Kanon-Karte selbst"},
    "core/database.py": {"*": "Start-Migration `_migrate_investitionen_parameter_keys_v325`"},
    "core/field_definitions.py": {
        "nutzt_v2h": "liest `v2h_faehig` ODER `nutzt_v2h` — bewusster Fallback für "
                     "Daten, die die Start-Migration noch nicht gesehen hat",
    },
    "services/daten_checker/stammdaten.py": {
        "leistung_ac_kw": "Prüfer nimmt Kanon `max_leistung_kw` UND den Alt-Namen — "
                          "bewusster Fallback, beide Seiten stehen im Code",
    },
}

# Legacy-Namen, die zugleich in einem ANDEREN Typ der Kanon sind. Sie können
# nicht baumweit verboten werden, weil dieselbe Zeichenkette je nach Typ
# richtig oder falsch ist.
#
# ⚠ Genau hier saß der PDF-Fehler: `leistung_kw` ist bei der Wärmepumpe der
# Kanon und war bei der Wallbox der alte Name der Ladeleistung. Eine
# typ-agnostische Leseliste kann diesen Unterschied nicht treffen — deshalb
# trägt die Liste in `anlagendokumentation.py` seit dem Fix einen Typ-Filter.
MEHRDEUTIG: dict[str, str] = {
    "leistung_kw": "Kanon der Wärmepumpe (PARAM_WAERMEPUMPE), Alt-Name der Wallbox",
    "pv_anteil_prozent": "Kanon der Wärmepumpe (PARAM_WAERMEPUMPE), Alt-Name des E-Autos",
}

# Namen, für die ein ANDERER, schärferer Wächter zuständig ist. Sie hier
# mitzuprüfen erzeugt nur Rauschen — und Rauschen ist der Anfang vom Ende
# einer Ausnahmeliste.
#
# `kwp` ist der #229-Altbestandsname der Nennleistung. Ob eine Stelle ihn
# lesen darf, entscheidet ADR-002/P3-a, und der zugehörige Wächter weiß mehr
# als dieser hier: Er unterscheidet einen Zugriff auf `inv.parameter` von
# einem gleichnamigen Schlüssel in einer fremden Struktur. Beides existiert im
# Baum — die Prognose-Gruppen und der Community-Payload führen ein eigenes
# `kwp`-Feld, das mit `Investition.parameter` nichts zu tun hat.
ANDERSWO_GEDECKT: dict[str, str] = {
    "kwp": "ADR-002/P3-a — `test_wurzelmuster_konformitaet.py::test_p3a_*` "
           "(`P3A_KENNWERT_JSON_SCHLUESSEL`, seit N-177 inkl. Subscript-Form)",
}


def _kanon_namen() -> set[str]:
    """Alle gültigen Parameter-Namen aus sämtlichen `PARAM_*`-Karten des SoT."""
    from backend.core import investition_parameter as ip

    return {
        name
        for schluessel, karte in vars(ip).items()
        if schluessel.startswith("PARAM_") and isinstance(karte, dict)
        for name in karte.values()
        if isinstance(name, str)
    }


def _python_dateien() -> list[Path]:
    """Quelle: `quellbaum.produktivbaum()`.

    Der bisherige Filter arbeitete auf dem **absoluten** Pfad und war damit
    zufällig richtig — derselbe Ausdruck auf einem relativen Pfad ist der
    Defekt, der `test_n252_…` 3491 Fremddateien mitmessen ließ.
    """
    return [datei.pfad for datei in produktivbaum()]


def _ist_string(knoten: ast.AST) -> bool:
    return isinstance(knoten, ast.Constant) and isinstance(knoten.value, str)


def parameter_zugriffe(quelle: str) -> set[str]:
    """Schlüsselnamen, mit denen die Datei auf ein Parameter-Dict zugreift.

    Erfasst wird **Zugriff**, nicht Vorkommen:

    * ``d["name"]`` — Index mit String-Literal
    * ``d.get("name")`` / ``d.get("name", default)`` — erstes Argument
    * ``parameter={"name": ...}`` — Schreibseite über das Keyword-Argument,
      mit dem eine `Investition` angelegt wird

    Ein loses Literal in einer beliebigen anderen Struktur zählt nicht — genau
    daran ist der erste Entwurf gescheitert (s. Modul-Docstring).
    """
    try:
        baum = ast.parse(quelle)
    except SyntaxError:  # pragma: no cover — eine kaputte Datei ist nicht unser Thema
        return set()

    namen: set[str] = set()
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Subscript) and _ist_string(knoten.slice):
            namen.add(knoten.slice.value)  # type: ignore[union-attr]
        elif isinstance(knoten, ast.Call):
            if (
                isinstance(knoten.func, ast.Attribute)
                and knoten.func.attr == "get"
                and knoten.args
                and _ist_string(knoten.args[0])
            ):
                namen.add(knoten.args[0].value)  # type: ignore[union-attr]
            for kw in knoten.keywords:
                if kw.arg == "parameter" and isinstance(kw.value, ast.Dict):
                    namen.update(
                        k.value for k in kw.value.keys  # type: ignore[union-attr]
                        if k is not None and _ist_string(k)
                    )
    return namen


def test_kein_legacy_parameter_key_im_backend_code() -> None:
    """Kein toter Parameter-Name als String-Literal außerhalb der Ausnahmen."""
    verboten = {
        k for k in LEGACY_PARAM_KEYS
        if k not in MEHRDEUTIG and k not in ANDERSWO_GEDECKT
    }
    assert verboten, "LEGACY_PARAM_KEYS ist leer — dann prüft dieser Test nichts mehr"

    treffer: list[str] = []
    for pfad in _python_dateien():
        rel = str(pfad.relative_to(_BACKEND_ROOT))
        frei = ERLAUBT.get(rel, {})
        if "*" in frei:
            continue
        gefunden = parameter_zugriffe(pfad.read_text(encoding="utf-8")) & verboten
        for name in sorted(gefunden - set(frei)):
            treffer.append(f"{rel}: '{name}' → Kanon ist '{LEGACY_PARAM_KEYS[name]}'")

    assert not treffer, (
        "Toter Investitions-Parameter-Schlüssel im Code — er liefert still `None`, "
        "keine Fehlermeldung:\n  " + "\n  ".join(treffer)
        + "\n\nKanon ist `core/investition_parameter.py`. Wer den Alt-Namen "
        "bewusst als Fallback liest, trägt die Datei mit Begründung in ERLAUBT ein."
    )


def test_gegenprobe_der_waechter_kann_rot_melden() -> None:
    """Der Prüfer misst wirklich — er darf nicht nur grün behaupten.

    Ohne diese Probe wäre nicht belegt, dass `_string_literale` überhaupt
    etwas findet. Genau die Lücke, die in Etappe E1 an vier Prüfern gefunden
    wurde: grün gemeldet, ohne zu messen.
    """
    # Die drei Zugriffsformen, die der Wächter treffen MUSS ...
    gefunden = parameter_zugriffe(
        'a = params["km_jahr"]\n'
        'b = param.get("nutzt_v2h")\n'
        'inv = Investition(parameter={"pv_anteil_prozent": 60})\n'
    )
    assert gefunden == {"km_jahr", "nutzt_v2h", "pv_anteil_prozent"}, gefunden

    # ... und die Form, an der der erste Entwurf gescheitert ist: ein
    # gleichnamiger Schlüssel in einer FREMDEN Struktur ist kein Zugriff auf
    # `Investition.parameter` und darf nicht rot melden.
    assert parameter_zugriffe('payload = {"kwp": round(anlage.leistung_kwp, 1)}') == set()


def test_model_docstring_nennt_keine_toten_schluessel() -> None:
    """`Investition` beschreibt die Parameter — und zwar mit gültigen Namen.

    Getrennt vom Haupttest, weil ein Docstring dort bewusst nicht zählt. Er ist
    trotzdem die gefährlichste Stelle: Aus genau diesem Beispiel sind die
    Demo-Daten, der Daten-Checker und das PDF abgeschrieben worden.
    """
    pfad = _BACKEND_ROOT / "models" / "investition.py"
    baum = ast.parse(pfad.read_text(encoding="utf-8"))
    klasse = next(
        k for k in ast.walk(baum)
        if isinstance(k, ast.ClassDef) and k.name == "Investition"
    )
    doc = ast.get_docstring(klasse) or ""

    # Der Docstring darf die alten Namen ERWÄHNEN (er warnt seit dem Fix
    # ausdrücklich vor ihnen) — aber nicht als JSON-Schlüssel führen.
    treffer = [k for k in LEGACY_PARAM_KEYS if f'"{k}":' in doc]
    assert not treffer, (
        "Der Klassen-Docstring von `Investition` führt tote Parameter-Namen als "
        f"Beispiel-Schlüssel: {treffer}. Genau daraus wurde abgeschrieben."
    )


@pytest.mark.parametrize("name,grund", sorted(MEHRDEUTIG.items()))
def test_mehrdeutige_namen_sind_begruendet(name: str, grund: str) -> None:
    """Wer einen Namen vom Wächter ausnimmt, sagt warum — und der Grund hält.

    Die Ausnahme gilt nur, solange der Name wirklich in einem anderen Typ der
    Kanon ist. Verschwindet er dort, ist die Ausnahme eine Lücke.
    """
    assert name in _kanon_namen(), (
        f"'{name}' steht als mehrdeutig ausgenommen ({grund}), ist aber in "
        "keiner Kanon-Map mehr enthalten — die Ausnahme deckt nichts und "
        "gehört gestrichen."
    )


@pytest.mark.parametrize("name,zustaendig", sorted(ANDERSWO_GEDECKT.items()))
def test_abgegrenzte_namen_sind_wirklich_anderswo_gedeckt(name: str, zustaendig: str) -> None:
    """Wer einen Namen abgibt, belegt, dass ihn jemand anders nimmt.

    Ohne diese Probe wäre `ANDERSWO_GEDECKT` eine Behauptung über einen
    fremden Test — und die altert genau so lange unbemerkt, bis jemand den
    fremden Test ändert. Fällt die Deckung dort weg, fällt sie hier auf.
    """
    from backend.tests.test_wurzelmuster_konformitaet import (
        P3A_KENNWERT_JSON_SCHLUESSEL,
    )

    assert name in P3A_KENNWERT_JSON_SCHLUESSEL, (
        f"'{name}' ist hier mit Verweis auf {zustaendig} ausgenommen, steht dort "
        "aber nicht mehr im Prüfumfang — damit prüft ihn niemand mehr."
    )


def test_pdf_leseliste_nennt_nur_kanon_namen() -> None:
    """Die Parameter-Tabelle der Anlagendokumentation liest gültige Namen.

    Eigene Probe, weil der Haupt-Wächter diese Bauform nicht erreicht (s.
    Modul-Docstring): Die Schlüssel stehen in einer Liste von Tupeln und werden
    erst später über eine Variable indiziert. Genau darin standen vier tote
    Namen, und genau deshalb fehlten im Dokumentations-PDF Fahrleistung,
    Ladeleistung, Batteriekapazität und Heizleistung — vier Zeilen, die nie
    erscheinen konnten.
    """
    pfad = _BACKEND_ROOT / "services" / "pdf" / "builders" / "anlagendokumentation.py"
    baum = ast.parse(pfad.read_text(encoding="utf-8"))

    liste = next(
        (
            knoten.value
            for knoten in ast.walk(baum)
            if isinstance(knoten, ast.Assign)
            and any(
                isinstance(ziel, ast.Name) and ziel.id == "interessant"
                for ziel in knoten.targets
            )
            and isinstance(knoten.value, ast.List)
        ),
        None,
    )
    assert liste is not None, (
        "Die Tabelle `interessant` in `anlagendokumentation.py` heißt nicht mehr so "
        "oder ist keine Liste — diese Probe zeigt dann aufs Leere und muss "
        "nachgezogen werden, statt still grün zu bleiben."
    )

    schluessel = [
        eintrag.elts[0].value
        for eintrag in liste.elts
        if isinstance(eintrag, ast.Tuple) and eintrag.elts and _ist_string(eintrag.elts[0])
    ]
    assert schluessel, "Keine Schlüssel gelesen — die Probe misst nichts"

    # ⚠ **Die Probe fragt nach dem Kanon, nicht nach der Legacy-Karte** — und
    # das ist der Unterschied zwischen „fängt einen von vier" und „fängt alle
    # vier". Nur `km_jahr` war ein *umgetaufter* Name; `heizleistung_kw`,
    # `batterie_kapazitaet_kwh` und `wallbox_leistung_kw` standen **nie** im
    # Kanon, in keiner Version. Eine Prüfung gegen `LEGACY_PARAM_KEYS` hätte
    # sie durchgelassen: Wer nur nach bekannten Alt-Namen sucht, findet die
    # erfundenen nicht.
    tot = [k for k in schluessel if k not in _kanon_namen()]
    assert not tot, (
        f"Die PDF-Parameterliste liest Namen, die in keiner Kanon-Map stehen: {tot}. "
        "Sie liefern still `None`, die Zeile erscheint dann gar nicht im Dokument. "
        "Kanon ist `core/investition_parameter.py`."
    )
