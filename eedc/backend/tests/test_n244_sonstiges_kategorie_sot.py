"""N-244 — die Kategorie-Annahme eines *Sonstiges*-Geräts kommt aus EINER Stelle.

**Der Befund in einem Satz:** Dieselbe Frage — „was ist ein *Sonstiges*-Gerät,
dessen ``parameter.kategorie`` niemand gepflegt hat?" — wurde am 17.08.2026 im
Baum dreifach verschieden beantwortet: **sechsmal** als Verbraucher (alle
wertführenden Pfade), **dreimal** als Erzeuger (Feldauswahl + Komponenten-Hub)
und **zweimal** als „beide Seiten mitnehmen" (Monats-Aggregat).

Die Folge war nicht akademisch, sondern die **N-259-Klasse**: Die
Zuordnungsfläche bot einem ungepflegten Gerät ausschließlich die vier
Erzeuger-Felder an (``erzeugung_kwh`` · ``eigenverbrauch_kwh`` ·
``einspeisung_kwh`` · ``einspeise_erloes_euro``), während der Snapshot-Pfad für
dasselbe Gerät die drei Verbraucher-Felder sucht (``verbrauch_sonstig_kwh`` ·
``bezug_pv_kwh`` · ``bezug_netz_kwh``). **Die Schnittmenge der beiden Listen ist
leer.** Wer ein solches Gerät hatte, konnte den Verbrauchssensor gar nicht
zuordnen — es sah nach „Wert fehlt" aus statt nach „Feld wird nirgends gesucht".

Dieser Wächter deckt die Richtung ab, für die es bis heute **keinen** gab: den
Verbraucher-Default. Den Erzeuger-Default bewacht seit N-250
``test_n250_sonstiges_richtung.py``; beide zusammen halten die Regel, dass eine
neue Fundstelle ein Fehler ist und kein Listeneintrag.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from backend.core.field_definitions import (
    INVESTITION_FELDER,
    SONSTIGES_FELDER_UNGEPFLEGT,
    SONSTIGES_KATEGORIE_UNGEPFLEGT,
    get_alle_felder_fuer_investition,
    get_felder_fuer_investition,
    get_felder_fuer_sonstiges,
    ist_gepflegte_sonstiges_kategorie,
)

WURZEL = Path(__file__).resolve().parents[1]

# Stellen, die den Verbraucher-Default als **Literal-Paar** tragen dürfen:
# keine. Die Annahme heißt `SONSTIGES_KATEGORIE_UNGEPFLEGT` und wird importiert.
# Die Liste darf nicht wachsen — eine neue Fundstelle ist ein Fehler, kein
# Eintrag (dieselbe Mechanik wie im N-250-Wächter nebenan).
N244_ERLAUBTE_VERBRAUCHER_LITERALE: set[str] = set()

# Die Pfade, die die Annahme brauchen — je einer der sechs Ex-Fundstellen.
# Diese Liste ist eine **Deckungs**prüfung, kein Deckel: sie fängt den Fall, in
# dem jemand eine Stelle still auf etwas anderes umstellt, statt sie zu lösen.
N244_KONSUMENTEN = {
    "services/live_tagesverlauf_service.py",
    "services/live_sensor_config.py",
    "services/snapshot/keys.py",
    "services/snapshot/komponenten_beitraege.py",
    "api/routes/energie_profil/_shared.py",
}


def _dateien_mit(muster: re.Pattern) -> set[str]:
    """Produktivdateien, in denen `muster` auf einer **Code**zeile steht.

    Kommentarzeilen zählen nicht: Ein Prüfer, der den erklärenden Text über
    einer Zeile mitliest, misst das falsche Objekt — dieselbe Klasse, die der
    N-250-Wächter im selben Verzeichnis benennt.
    """
    return {
        str(p.relative_to(WURZEL))
        for p in WURZEL.rglob("*.py")
        if "tests" not in p.parts and "venv" not in p.parts
        for zeile in p.read_text(encoding="utf-8").splitlines()
        if muster.search(zeile) and not zeile.lstrip().startswith("#")
    }


def test_n244_kein_handgeschriebener_verbraucher_default() -> None:
    """`get("kategorie", "verbraucher")` darf nur noch die Konstante sein.

    Baumweit, nicht auf die sechs bekannten Stellen beschränkt — er fängt auch
    eine siebte, die es heute noch nicht gibt.
    """
    muster = re.compile(r"""get\(\s*["']kategorie["']\s*,\s*["']verbraucher["']""")
    treffer = _dateien_mit(muster)

    assert treffer <= N244_ERLAUBTE_VERBRAUCHER_LITERALE, (
        "Neuer handgeschriebener Verbraucher-Default für die Sonstiges-Kategorie: "
        f"{sorted(treffer - N244_ERLAUBTE_VERBRAUCHER_LITERALE)}. "
        "Die Annahme heißt `SONSTIGES_KATEGORIE_UNGEPFLEGT` (N-244)."
    )


def test_n244_die_sechs_stellen_lesen_wirklich_den_sot() -> None:
    """Deckung statt Abwesenheit — der Prüfer, der die Gegenrichtung abdeckt.

    Test 1 zeigt nur, dass **kein Literal** mehr dasteht. Das wäre auch erfüllt,
    wenn jemand eine Stelle einfach löschte oder auf einen dritten Wert
    umstellte. Deshalb hier die andere Hälfte: die fünf Pfade, die die Annahme
    tatsächlich brauchen, müssen sie auch **importieren**.
    """
    fehlend = {
        pfad
        for pfad in N244_KONSUMENTEN
        if "SONSTIGES_KATEGORIE_UNGEPFLEGT" not in (WURZEL / pfad).read_text(encoding="utf-8")
    }
    assert not fehlend, (
        "Diese Stellen lesen die Sonstiges-Kategorie, ohne die benannte Annahme "
        f"zu benutzen: {sorted(fehlend)}"
    )


# ── Die Deckungsprüfung: kein Feld darf durch die Ritzen fallen ──────────────


def test_n244_ungepflegt_bietet_jedes_feld_jeder_richtung() -> None:
    """Ohne gepflegte Kategorie **alle** Felder — der Kern des Fixes.

    Das ist die Probe, die den Befund gefangen hätte: Vorher lieferte diese
    Frage die Erzeuger-Liste, und der Schnitt mit der Verbraucher-Liste war
    leer.
    """
    alle = {f["feld"] for felder in INVESTITION_FELDER["sonstiges"].values() for f in felder}
    ungepflegt = {f["feld"] for f in SONSTIGES_FELDER_UNGEPFLEGT}
    assert ungepflegt == alle, (
        "Ein Feld einer Richtung fehlt im ungepflegten Fall — genau so entsteht "
        f"ein nirgends suchbares Feld: {sorted(alle - ungepflegt)}"
    )


def test_n244_ungepflegt_traegt_beide_richtungen_konkret() -> None:
    """Namentlich, nicht nur mengenmäßig — die zwei Listen mit leerem Schnitt."""
    felder = {f["feld"] for f in get_felder_fuer_sonstiges(None)}
    assert {"verbrauch_sonstig_kwh", "bezug_pv_kwh", "bezug_netz_kwh"} <= felder
    assert {"erzeugung_kwh", "eigenverbrauch_kwh", "einspeisung_kwh"} <= felder


def test_n244_erzeuger_und_verbraucher_felder_sind_disjunkt() -> None:
    """Die Prämisse des Befunds — als Probe, nicht als Behauptung im Text.

    Fällt sie irgendwann (ein gemeinsames Feld), ist die Schärfe des Fundes weg
    und dieser Wächter sagt es, statt still weiterzulaufen.
    """
    e = {f["feld"] for f in get_felder_fuer_sonstiges("erzeuger")}
    v = {f["feld"] for f in get_felder_fuer_sonstiges("verbraucher")}
    assert not (e & v), f"Nicht mehr disjunkt: {sorted(e & v)}"


@pytest.mark.parametrize("ungepflegt", [None, "", "erzueger", "Verbraucher", "unsinn"])
def test_n244_nicht_gepflegte_werte_raten_nicht(ungepflegt) -> None:
    """Leer, unbekannt und **Tippfehler** landen alle im vollen Feldsatz.

    Der Tippfehler-Fall ist der, an dem die alte Zeile am gefährlichsten war:
    `sonstiges.get(kategorie, sonstiges.get("erzeuger"))` machte aus einem
    verschriebenen „verbraucher" still einen Erzeuger.
    """
    assert not ist_gepflegte_sonstiges_kategorie(ungepflegt)
    felder = [f["feld"] for f in get_felder_fuer_sonstiges(ungepflegt)]
    assert felder == [f["feld"] for f in SONSTIGES_FELDER_UNGEPFLEGT]


@pytest.mark.parametrize("kategorie", ["erzeuger", "verbraucher", "speicher"])
def test_n244_gepflegte_kategorie_ist_unveraendert(kategorie) -> None:
    """Ein **gepflegtes** Gerät ist ein beweisbarer No-op.

    Die ganze Änderung darf ausschließlich den ungepflegten Fall betreffen —
    sonst wäre sie eine Migrationsfrage (der Einwand, an dem N-250 diese Stelle
    bewusst offengelassen hat).
    """
    assert ist_gepflegte_sonstiges_kategorie(kategorie)
    erwartet = [f["feld"] for f in INVESTITION_FELDER["sonstiges"][kategorie]]
    assert [f["feld"] for f in get_felder_fuer_sonstiges(kategorie)] == erwartet
    assert [
        f["feld"] for f in get_felder_fuer_investition("sonstiges", {"kategorie": kategorie})
    ] == erwartet
    assert [
        f["feld"] for f in get_alle_felder_fuer_investition("sonstiges", {"kategorie": kategorie})
    ] == erwartet


def test_n244_beide_routen_reichen_die_kategorie_ungeraten_durch() -> None:
    """Die zwei Einstiege dürfen nicht selbst raten, bevor der SoT dran ist.

    Genau dort saß der Befund: nicht in `get_felder_fuer_sonstiges`, sondern in
    den zwei Aufrufern, die ihm `"erzeuger"` schon vorgekaut übergaben.
    """
    voll = [f["feld"] for f in SONSTIGES_FELDER_UNGEPFLEGT]
    for parameter in ({}, {"kategorie": ""}, {"beschreibung": "Heizstab"}):
        assert [f["feld"] for f in get_felder_fuer_investition("sonstiges", parameter)] == voll
        assert [f["feld"] for f in get_alle_felder_fuer_investition("sonstiges", parameter)] == voll


def test_n244_die_annahme_ist_die_lesart_der_schreibpfade() -> None:
    """Die Konstante muss zu `sonstiges_feld_reihenfolge` passen.

    Beide beantworten dieselbe Frage für den ungepflegten Fall; driften sie
    auseinander, schreibt der eine Pfad ein Feld, das der andere nicht führt.
    """
    from backend.core.field_definitions import sonstiges_feld_reihenfolge

    assert SONSTIGES_KATEGORIE_UNGEPFLEGT == "verbraucher"
    assert sonstiges_feld_reihenfolge(None) == sonstiges_feld_reihenfolge(
        SONSTIGES_KATEGORIE_UNGEPFLEGT
    )
    # …und die erste Position ist die Verbrauchsseite, nicht die Erzeugung.
    assert sonstiges_feld_reihenfolge(None)[0] != "erzeugung_kwh"
