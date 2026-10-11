"""**Kein Feld ohne Auswertung** — der Wächter zu R-A (WK-16f, Prinzip F-7).

## Was er hält

Ein Feld, das die Datenquellen-Fläche anbietet, muss in mindestens einer
**Sicht** oder als **HA-Sensor** verarbeitet werden. Die Liste steht in
``core/feld_auswertungen.py``; hier wird gemessen, dass sie stimmt:

===  ======================================================================
 1   Jedes Registry-Feld hat ≥ 1 Eintrag — oder steht mit Begründung in
     ``FELDER_OHNE_AUSWERTUNG_BEKANNT``.
 2   Jede genannte Datei existiert und **definiert** das genannte Symbol.
 3   Der Feldname (oder die Trägertoken aus ``Auswertung.ueber``) kommt im
     **ausführbaren** Quelltext genau dieser Funktion vor — ohne Docstring,
     Kommentar und eigenen Funktionsnamen (N-686) — *ein Symbol, das das
     Feld nicht liest, ist kein Leser.*
===  ======================================================================

## Warum es ein Wächter ist und keine Regression

Er zählt **nicht** die Felder, die es heute gibt, sondern leitet seine
Referenzmenge bei jedem Lauf aus den Registries ab
(``alle_registry_felder``). Ein Feld, das morgen dazukommt, ist am selben Tag
Teil der Prüfung — ohne dass jemand daran denken muss. Genau daran ist die
Vorgängerbauform des Park-Gates gescheitert: Sie pflegte eine eigene Liste
neben der Wahrheit und driftete gegen sie (Park-Leertest, 06.09.2026).

⛔ **Baseline 0 für Wärme/Klima.** Auf dieser Fläche gibt es keinen
Gegenprüfer — der Maintainer besitzt weder Wärmepumpe noch Klimaanlage
(Konzept Kap. 11.6). Ein „noch nicht ausgewertet" wäre dort dauerhaft
unsichtbar; deshalb darf kein ``waermepumpe``-Feld in der Ausnahmeliste stehen.

## Was er NICHT leisten kann

Er sieht den **Quelltext**, nicht die Oberfläche — und nicht, ob ein Leser
im Produktionspfad überhaupt noch gerufen wird (gemessen 11.10.2026: zwei
Einträge zeigten auf eine Funktion, die nur noch Tests riefen). Dass ``build_komponenten``
``leistung_kuehlen_w`` liest, beweist er; dass die Zahl am Ende auf einer Kachel
steht, beweisen die Render-Proben der jeweiligen Sicht. Die Grenze ist dieselbe
wie bei ``check:park-gate`` und steht aus demselben Grund im Konzept
(Kap. 11.4): *ein Quelltext-Wächter sieht keine Render-Geometrie.*
"""

from __future__ import annotations

import ast
import copy
from pathlib import Path

import pytest

from backend.core import feld_auswertungen as fa
from backend.core.feld_auswertungen import (
    FELD_AUSWERTUNGEN,
    FELDER_OHNE_AUSWERTUNG_BEKANNT,
    FELDER_OHNE_AUSWERTUNG_MAX,
    Auswertung,
    alle_registry_felder,
    auswertungen_fuer,
    sichten_fuer,
)

BACKEND = Path(__file__).resolve().parent.parent


# ─── Werkzeug ────────────────────────────────────────────────────────────────

def _symbol_quelle(datei: Path, symbol: str) -> str | None:
    """Der Quelltext eines (ggf. verschachtelten) Symbols — ``None``, wenn es
    dort nicht definiert ist.

    ⚠ **AST statt ``in``-Suche über die Datei.** Ein dateiweiter Substring-Test
    wäre grün, sobald der Feldname *irgendwo* in der Datei steht — auch in einem
    Kommentar oder im Schreibpfad daneben. Genau diese Schwäche hat der
    Gegenanker-Hinweis in Konzept Kap. 11.5 im Blick.
    """
    quelle = datei.read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    kette = symbol.split(".")

    def _suche(knoten, rest: list[str]) -> str | None:
        name = rest[0]
        for kind in ast.iter_child_nodes(knoten):
            if isinstance(
                kind, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            ) and kind.name == name:
                if len(rest) == 1:
                    return ast.get_source_segment(quelle, kind)
                gefunden = _suche(kind, rest[1:])
                if gefunden is not None:
                    return gefunden
        return None

    return _suche(baum, kette)


def _symbol_code(datei: Path, symbol: str) -> str | None:
    """Der **ausführbare** Quelltext eines Symbols — ohne Docstrings, ohne
    Kommentare und ohne den eigenen Namen (N-686).

    ⚠ **Warum nicht ``_symbol_quelle``.** Der Segment-Text trägt Docstring,
    Kommentare und die ``def``-Zeile mit. Ein Feldname, der nur dort steht, ist
    eine *Erwähnung*, kein Lesen — gemessen am 11.10.2026 waren 8 von 154
    Einträgen allein dadurch grün, einer davon (``wirksamer_arbeitspreis_cent``)
    zeigte auf ein Symbol, dessen Docstring selbst sagt, dass das Feld woanders
    gelesen wird.

    Bauform: der AST des Symbols, je Funktion/Klasse darin der Docstring
    entfernt, der Name des Symbols selbst neutralisiert, dann ``ast.unparse`` —
    Kommentare kennt der AST nicht, sie fallen dabei weg. Kein Regex: ein ``#``
    in einem String oder ein Docstring mit Anführungszeichen darin bliebe für
    ihn mehrdeutig.
    """
    quelle = datei.read_text(encoding="utf-8")
    baum = ast.parse(quelle)
    knoten = None
    ebene = baum
    for name in symbol.split("."):
        knoten = next(
            (
                k for k in ast.iter_child_nodes(ebene)
                if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and k.name == name
            ),
            None,
        )
        if knoten is None:
            return None
        ebene = knoten
    knoten = copy.deepcopy(knoten)
    for k in ast.walk(knoten):
        if isinstance(k, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if ast.get_docstring(k, clean=False) is not None:
                k.body = k.body[1:] or [ast.Pass()]
    knoten.name = "_"
    return ast.unparse(knoten)


def _alle_eintraege() -> list[tuple[tuple[str, str], Auswertung]]:
    return [
        (schluessel, a)
        for schluessel, liste in FELD_AUSWERTUNGEN.items()
        for a in liste
    ]


# ─── 1 · Jedes Feld hat eine Auswertung ──────────────────────────────────────

def test_jedes_registry_feld_hat_mindestens_eine_auswertung():
    """R-A: eine Zuordnung ist ein Versprechen — es gibt keine stille Lücke."""
    fehlt = sorted(
        f for f in alle_registry_felder()
        if f not in FELD_AUSWERTUNGEN and f not in FELDER_OHNE_AUSWERTUNG_BEKANNT
    )
    assert not fehlt, (
        "Diese Registry-Felder haben keine Auswertung und keine Begründung:\n  "
        + "\n  ".join(f"{t}/{f}" for t, f in fehlt)
        + "\n\nEntweder einen Leser bauen und ihn in `core/feld_auswertungen.py` "
        "eintragen — oder das Feld mit Begründung in "
        "`FELDER_OHNE_AUSWERTUNG_BEKANNT` führen (und den Fund melden)."
    )


def test_kein_waerme_klima_feld_steht_in_der_ausnahmeliste():
    """Baseline **0** für Wärme/Klima — hier gibt es keinen Gegenprüfer."""
    offen = sorted(f for (t, f) in FELDER_OHNE_AUSWERTUNG_BEKANNT if t == "waermepumpe")
    assert not offen, (
        f"Wärme/Klima-Felder ohne Auswertung: {offen}. Auf dieser Fläche gilt "
        "Baseline 0 (Konzept Kap. 11.6): Der Maintainer besitzt kein solches "
        "Gerät und würde eine tote Zuordnung nie bemerken."
    )


def test_die_ausnahmeliste_waechst_nicht():
    """Bauform ``P10_NOCH_NICHT_MIGRIERT`` — schrumpfen ja, wachsen nein."""
    assert len(FELDER_OHNE_AUSWERTUNG_BEKANNT) <= FELDER_OHNE_AUSWERTUNG_MAX, (
        f"{len(FELDER_OHNE_AUSWERTUNG_BEKANNT)} Felder ohne Auswertung, erlaubt "
        f"sind {FELDER_OHNE_AUSWERTUNG_MAX}. Ein neues Feld bekommt einen Leser, "
        "keinen Listeneintrag."
    )


def test_jede_ausnahme_traegt_eine_begruendung():
    ohne = [k for k, v in FELDER_OHNE_AUSWERTUNG_BEKANNT.items() if len(v.strip()) < 40]
    assert not ohne, (
        f"Ausnahme ohne tragfähige Begründung: {ohne}. Ein Listeneintrag ohne "
        "Grund ist eine Lücke mit Deckel."
    )


# ─── Gegenrichtung: keine toten Einträge ─────────────────────────────────────

def test_kein_eintrag_zeigt_auf_ein_feld_das_es_nicht_gibt():
    """Ein Eintrag für ein entferntes Feld ist Ballast und täuscht Deckung vor."""
    bekannt = alle_registry_felder()
    tot = sorted(k for k in FELD_AUSWERTUNGEN if k not in bekannt)
    assert not tot, (
        f"Einträge ohne Registry-Feld: {tot}. Entweder heißt das Feld anders "
        "oder es ist entfallen — dann gehört auch sein Eintrag weg."
    )


def test_keine_ausnahme_fuer_ein_feld_das_es_nicht_gibt():
    bekannt = alle_registry_felder()
    tot = sorted(k for k in FELDER_OHNE_AUSWERTUNG_BEKANNT if k not in bekannt)
    assert not tot, f"Ausnahme ohne Registry-Feld: {tot}"


def test_kein_feld_steht_gleichzeitig_in_beiden_listen():
    doppelt = sorted(set(FELD_AUSWERTUNGEN) & set(FELDER_OHNE_AUSWERTUNG_BEKANNT))
    assert not doppelt, (
        f"Diese Felder haben eine Auswertung UND stehen als Ausnahme: {doppelt}. "
        "Die Ausnahmeliste sagt 'es gibt keine' — beides zugleich ist keine Aussage."
    )


# ─── 2 · Datei existiert und definiert das Symbol ────────────────────────────

@pytest.mark.parametrize(
    "schluessel,auswertung",
    _alle_eintraege(),
    ids=[f"{t}/{f}:{a.symbol}" for (t, f), a in _alle_eintraege()],
)
def test_jede_genannte_stelle_existiert_und_liest_das_feld(schluessel, auswertung):
    """Prüfung 2 **und** 3 in einem Zug — sie hängen an derselben Quelle."""
    typ, feld = schluessel
    datei = BACKEND / auswertung.datei
    assert datei.is_file(), (
        f"{typ}/{feld}: Datei {auswertung.datei} gibt es nicht "
        "(umbenannt oder verschoben?)."
    )

    quelle = _symbol_quelle(datei, auswertung.symbol)
    assert quelle is not None, (
        f"{typ}/{feld}: {auswertung.datei} definiert kein Symbol "
        f"`{auswertung.symbol}`."
    )

    # N-686: gesucht wird im ausführbaren Code, nicht in Docstring, Kommentar
    # oder Funktionsnamen — eine Erwähnung ist kein Lesen.
    code = _symbol_code(datei, auswertung.symbol)
    token = auswertung.ueber or (feld,)
    fehlend = [t for t in token if t not in code]
    assert not fehlend, (
        f"{typ}/{feld}: `{auswertung.symbol}` in {auswertung.datei} nennt "
        f"{fehlend} nicht im Code (Docstring, Kommentar und Funktionsname "
        "zählen nicht) — dieses Symbol liest das Feld also nicht. "
        "Ein Eintrag, der auf die falsche Funktion zeigt, ist schlimmer als "
        "keiner: Er behauptet Deckung."
    )


# ─── 3b · Ein modus-generischer Leser muss seinen Modus nennen ───────────────

#: Leser, die über einen ``modus``-Parameter **jede** der vier Betriebsarten
#: lesen können. Ein Eintrag, der nur sie nennt, belegt gar nichts: Genau so
#: sah N-398 aus — ``betriebsart_nutzenergie_kwh`` existierte, gerufen wurde es
#: nur mit ``KUEHLEN``.
MODUS_GENERISCHE_LESER = ("betriebsart_strom_kwh", "betriebsart_nutzenergie_kwh")


def _modus_des_feldes(feld: str) -> str | None:
    """Zu welchem Betriebsmodus gehört dieses Registry-Feld? — aus dem Kanon."""
    from backend.core.betriebsmodus import (
        BETRIEBSART_NUTZENERGIE_FELD,
        BETRIEBSART_STROM_FELD,
    )
    for tabelle in (BETRIEBSART_STROM_FELD, BETRIEBSART_NUTZENERGIE_FELD):
        for modus, name in tabelle.items():
            if name == feld:
                return modus
    return None


def test_ein_generischer_leser_ohne_modus_belegt_nichts():
    """**Die Lehre aus N-398, als Regel über die Tabelle selbst.**

    ⭐ Ein Sprengsatz hat diese Probe erzwungen (14.09.2026): Streicht man aus
    einem Betriebsart-Eintrag das Modus-Token, bleibt ``betriebsart_strom_kwh``
    stehen — und der Wächter war **still**. Er hätte dann für alle vier
    Betriebsarten dieselbe generische Funktion als Beleg akzeptiert, also genau
    den Blindfleck reproduziert, gegen den er gebaut wurde.
    """
    fehlend = []
    for (typ, feld), liste in FELD_AUSWERTUNGEN.items():
        modus = _modus_des_feldes(feld)
        if modus is None:
            continue
        for a in liste:
            token = a.ueber or ()
            if any(g in token for g in MODUS_GENERISCHE_LESER) and (
                modus.upper() not in " ".join(token).upper()
            ):
                fehlend.append(f"{typ}/{feld} → {a.datei}::{a.symbol}")
    assert not fehlend, (
        "Diese Einträge nennen einen modus-generischen Leser, aber nicht den "
        f"Modus, mit dem er gerufen wird: {fehlend}. Ohne ihn belegt der "
        "Eintrag nur, dass es die Funktion gibt — nicht, dass jemand sie für "
        "DIESES Feld ruft (N-398)."
    )


# ─── Die Sicht-Namen ─────────────────────────────────────────────────────────

def test_jede_sicht_kommt_aus_den_konstanten():
    """Der Satz auf der Fläche ist eine **Wegbeschreibung** — sie muss die
    Menüpunkte wörtlich treffen, sonst schickt sie den Anwender ins Leere."""
    erlaubt = {
        wert for name, wert in vars(fa).items()
        if name.isupper() and isinstance(wert, str) and (
            "→" in wert or wert in (fa.MONATSBERICHT, fa.JAHRESBERICHT, fa.HA_SENSOREN)
        )
    }
    frei = sorted({a.sicht for _, a in _alle_eintraege()} - erlaubt)
    assert not frei, (
        f"Frei getippte Sicht-Namen: {frei}. Sie gehören als Konstante nach "
        "`core/feld_auswertungen.py`, sonst stehen bald drei Schreibweisen "
        "desselben Menüpunkts nebeneinander."
    )


# ─── Der Zugriff, den die Route benutzt ──────────────────────────────────────

def test_innengeraete_feld_erbt_die_auswertung_des_geraetefelds():
    """``…-2`` ist die Aufschlüsselung desselben Felds, nicht ein zweites."""
    basis = sichten_fuer("waermepumpe", "betriebsart_strom_kuehlen_kwh")
    je_geraet = sichten_fuer("waermepumpe", "betriebsart_strom_kuehlen_kwh-2")
    assert basis and basis == je_geraet


def test_unbekanntes_feld_liefert_leer_statt_zu_werfen():
    assert sichten_fuer("waermepumpe", "gibt_es_nicht_kwh") == []
    assert sichten_fuer(None, None) == []
    assert auswertungen_fuer("basis", "") == ()


def test_n398_die_nutzenergie_heizen_hat_jetzt_einen_leser():
    """Der Anlass des Pakets, als benannte Probe — nicht nur als Tabellenzeile.

    Bis zum 14.09.2026 war dieses Feld zuordenbar und wurde von **nichts**
    gelesen. Wer es pflegte, sah `gesamt_heizenergie_kwh` 0 und den falschen
    Grund „kein Wärmemengenzähler zugeordnet".
    """
    assert sichten_fuer("waermepumpe", "betriebsart_nutzenergie_heizen_kwh")
    for modus in ("lueften", "entfeuchten"):
        assert sichten_fuer(
            "waermepumpe", f"betriebsart_nutzenergie_{modus}_kwh"
        ), f"Nutzenergie {modus} hat keine Auswertung (E4: Menge ja, Kennzahl nein)"
