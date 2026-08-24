"""N-252 — der Speicher-Wirkungsgrad kommt aus EINER Regel, überall.

**Der Befund.** Sieben Stellen bildeten `entladung / ladung * 100` selbst:
*Cockpit → Jahr*, *Auswertungen → Komponenten* (je Monat), das
Speicher-Dashboard (Kachel **und** Verlaufskurve), das BKW-Dashboard, die
Wirtschaftlichkeit eines Speichers unter *Sonstiges* und der HA-Sensor
`speicher_effizienz_prozent`. Keine davon kannte eine Obergrenze — und über
100 % kann kein Speicher. Der Layer-SoT
`core/berechnungen/speicher_wirkungsgrad.py` existierte seit F-22 (Knallfrosch,
Forum T89667 #163) und deckte nur Tag und *Cockpit → Monat*.

**Warum dieser Wächter ZWEI Hälften hat.** Die Lehre aus der Runde davor: Ein
Prüfer, der nur die *Abwesenheit* eines Literals misst, lässt die stille
Umstellung auf einen dritten Wert durch. Ein Abwesenheits-Grep nach
`entladung / ladung` fängt keine Stelle, die morgen `entl * 100 / lad`
schreibt. Die zweite Hälfte ist deshalb die **Deckung**: Wer die Regel
braucht, muss sie auch importieren.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from backend.tests.quellbaum import produktivbaum

BACKEND = Path(__file__).resolve().parents[1]

#: Module, die den Speicher-η für eine Anzeige, einen Sensor oder eine
#: Geldrechnung bilden. Wer hier steht, muss den SoT importieren.
BRAUCHT_DEN_SOT = [
    "api/routes/cockpit/uebersicht.py",
    "api/routes/cockpit/komponenten.py",
    "api/routes/investitionen/dashboards.py",
    "api/routes/ha_export.py",
    "api/routes/aktueller_monat.py",
    "core/berechnungen/speicher.py",
    "services/energie_profil/tage_werte.py",
    # N-264: der letzte Pfad mit eigener Semantik (stilles Cap auf 100 %).
    "services/speicher_wirtschaftlichkeit.py",
]

#: Der Daten-Checker ist der **einzige** legitime Verwender des ungekappten
#: Diagnose-Helpers — er meldet den Überschuss und braucht ihn dafür sichtbar.
#: Er steht deshalb weder in `BRAUCHT_DEN_SOT` (er darf gerade nicht kappen)
#: noch in `BEWUSST_ROH` (er rechnet seit N-264 nicht mehr selbst, sondern ruft
#: `speicher_effizienz_prozent`). Diese Probe hält beides fest.
DIAGNOSE_VERWENDER = "services/daten_checker/stammdaten.py"

#: Stellen, die den rohen Quotienten mit voller Absicht behalten — je mit
#: Grund. Eine Zeile ohne Grund gehört nicht in diese Liste.
BEWUSST_ROH = {
    # Prognose- und Potenzialpfade klemmen selbst (min(...)) und brauchen
    # einen Wert, keine fehlende Aussage.
    "services/speicher_potential_service.py",
    "api/routes/aussichten.py",
    # Die Heimat der Regel selbst.
    "core/berechnungen/speicher_wirkungsgrad.py",
    # `speicher.py::speicher_effizienz_prozent` ist der **Diagnose**-Helper:
    # ungekappt, damit der Daten-Checker den Überschuss zeigen kann. Er darf
    # keine Anzeige-Größe liefern — das hält der Deckungs-Prüfer unten fest,
    # denn `speicher.py` steht zugleich in `BRAUCHT_DEN_SOT`.
    #
    # ⚑ N-264 (17.08.): `services/speicher_wirtschaftlichkeit.py` stand hier
    # bis eben als „unbewertet" daneben — sie klemmte im langen Fenster still
    # auf `min(1.0, …)` und zeigte bei 104 % glatt **100,0 %**, während
    # *Cockpit → Jahr* seit N-252 „—" schrieb. Die dritte Semantik ist
    # aufgelöst, die Datei ist raus aus dieser Liste und steht jetzt in
    # `BRAUCHT_DEN_SOT`.
    "core/berechnungen/speicher.py",
}

#: Roher Quotient aus Entladung und Ladung — in jeder Schreibrichtung.
_ROH = re.compile(
    r"entladung[a-z_]*\s*(?:/|\*\s*100\s*/)\s*[a-z_.]*ladung"
    r"|[a-z_.]*entladung[a-z_]*\s*/\s*[a-z_.]*ladung[a-z_]*",
    re.IGNORECASE,
)


def _py_dateien():
    """Der Produktivbaum — aus `quellbaum`, nicht mehr selbst gefiltert.

    ⚠ **Hier stand bis 2026-08-24 ein Filter, der nie griff:**
    `"/venv/" in rel` — `rel` ist **relativ** und beginnt mit `venv/` ohne
    führenden Schrägstrich. Der Prüfer nahm deshalb **3828 Dateien statt
    337**, davon 3491 aus dem virtualenv, und brauchte **14,27 s** statt
    1,32 s. Er meldete die ganze Zeit grün — ein Abwesenheitsbeweis, der
    fremde Pakete mitmisst, behauptet mehr, als er weiß.
    """
    for datei in produktivbaum():
        yield datei.rel, datei


def _ohne_prosa(quelle: str, baum: ast.Module | None = None) -> list[str]:
    """Die Quelle zeilenweise, aber mit **ausgeblendeten String-Inhalten**.

    Ohne das misst der Prüfer die **Erklärung** der Regel statt ihrer
    Anwendung: Die Docstrings von `speicher.py` und
    `speicher_wirtschaftlichkeit.py` schreiben „entladung / ladung" aus, um zu
    begründen, warum man es *nicht* so machen soll. Ein Prüfer, der darüber
    rot geht, erzieht dazu, die Begründung zu löschen.

    ⚠ **Warum spaltengenau und nicht zeilenweise.** Die erste Fassung hat
    jede Zeile verworfen, die *irgendwo* ein String-Literal enthielt — und
    fiel damit beim Sprengsatz-Durchgang zu N-264 durch: Die Zeile

        eta = type('E', (), {'quelle': 'fenster_lang',
                             'prozent': entladung_kwh / ladung_kwh})()

    trägt vier Literale und war deshalb komplett unsichtbar. Der Sprengsatz
    zündete, und der Prüfer blieb grün. **Ein Prüfer, der zu viel ausblendet,
    ist schlimmer als keiner** — er behauptet Deckung, die es nicht gibt.
    Jetzt verschwindet nur der Text *innerhalb* der Anführungszeichen; Code
    daneben bleibt sichtbar.
    """
    zeilen = quelle.splitlines()
    if baum is None:
        # Nur noch die drei Selbstproben unten parsen hier; der baumweite Lauf
        # reicht den Baum aus `quellbaum` durch.
        #
        # ⚠ Hier stand: „Mindestens eine Datei im Baum trägt ein BOM." Das war
        # eine Folge des defekten venv-Filters — die BOM-Datei lag in
        # `site-packages`. Der Produktivbaum parst heute vollständig, und
        # `test_quellbaum.py::test_nichts_wird_still_uebersprungen` hält das fest.
        try:
            baum = ast.parse(quelle)
        except SyntaxError:  # pragma: no cover — Selbstproben sind gültiger Code
            return zeilen

    # `col_offset` zählt UTF-8-**Bytes**, nicht Zeichen — bei Umlauten in
    # Docstrings läge ein Zeichen-Slice daneben.
    roh = [z.encode("utf-8") for z in zeilen]

    def leeren(idx: int, von: int, bis: int) -> None:
        if 0 <= idx < len(roh):
            z = roh[idx]
            bis = len(z) if bis < 0 else min(bis, len(z))
            von = max(0, min(von, len(z)))
            if von < bis:
                roh[idx] = z[:von] + b" " * (bis - von) + z[bis:]

    for knoten in ast.walk(baum):
        if not (isinstance(knoten, ast.Constant) and isinstance(knoten.value, str)):
            continue
        start_z = knoten.lineno - 1
        end_z = (getattr(knoten, "end_lineno", knoten.lineno) or knoten.lineno) - 1
        start_s = knoten.col_offset
        end_s = getattr(knoten, "end_col_offset", -1)
        if start_z == end_z:
            leeren(start_z, start_s, end_s)
        else:
            leeren(start_z, start_s, -1)
            for i in range(start_z + 1, end_z):
                leeren(i, 0, -1)
            leeren(end_z, 0, end_s)

    return [z.decode("utf-8", errors="replace") for z in roh]


# ── Hälfte 1: Abwesenheit ────────────────────────────────────────────────────


def test_p252_kein_roher_eta_quotient_ausserhalb_der_ausnahmen():
    """Baumweit: niemand bildet den η-Quotienten mehr selbst."""
    treffer: list[str] = []
    for rel, datei in _py_dateien():
        if rel in BEWUSST_ROH:
            continue
        original = datei.quelle.splitlines()
        for nr, zeile in enumerate(_ohne_prosa(datei.quelle, datei.baum), 1):
            nackt = zeile.split("#", 1)[0]
            if _ROH.search(nackt):
                treffer.append(f"{rel}:{nr}: {original[nr - 1].strip()}")
    assert not treffer, (
        "Roher Speicher-η-Quotient gefunden. Nutze "
        "`core/berechnungen/speicher_wirkungsgrad.speicher_wirkungsgrad` — er "
        "kappt bei 100 % und liefert die Herkunft mit:\n" + "\n".join(treffer)
    )


# ── Hälfte 2: Deckung — die eigentliche Lehre ────────────────────────────────


@pytest.mark.parametrize("rel", BRAUCHT_DEN_SOT)
def test_p252_wer_die_regel_braucht_importiert_sie(rel: str):
    """Abwesenheit allein genügt nicht.

    Ein Modul kann den Quotienten still auf eine dritte Schreibweise umstellen
    und am Grep vorbeilaufen. Dieser Prüfer misst das Gegenstück: Kommt der
    Speicher-η hier überhaupt vor, dann muss die Regel importiert sein.
    """
    pfad = BACKEND / rel
    quelle = pfad.read_text(encoding="utf-8")
    baum = ast.parse(quelle)

    importiert = any(
        isinstance(knoten, ast.ImportFrom)
        and knoten.module
        and "speicher_wirkungsgrad" in knoten.module
        or (
            isinstance(knoten, ast.ImportFrom)
            and any(a.name == "speicher_wirkungsgrad" for a in (knoten.names or []))
        )
        for knoten in ast.walk(baum)
    )
    assert importiert, (
        f"{rel} bildet einen Speicher-Wirkungsgrad, importiert aber "
        "`speicher_wirkungsgrad` nicht. Genau so entsteht die zweite "
        "Definition, die N-252 an sieben Stellen hatte."
    )


def test_p252_der_prosa_filter_blendet_text_aus_aber_keinen_code():
    """Der Prüfer über dem Prüfer — beide Richtungen.

    Beim Sprengsatz-Durchgang zu N-264 blieb der Abwesenheits-Prüfer grün,
    obwohl der Sprengsatz gezündet hatte: Die erste Fassung des Filters
    verwarf **ganze Zeilen**, sobald sie irgendein String-Literal enthielten.
    Diese Probe hält beide Fehlerrichtungen fest — zu wenig ausblenden (die
    Begründung wird als Verstoß gemeldet) und zu viel (ein Verstoß wird
    unsichtbar).
    """
    # Richtung 1: Text in einem Docstring ist unsichtbar.
    nur_prosa = '"""Erklärung: entladung_kwh / ladung_kwh ist falsch."""\nx = 1\n'
    assert not any(_ROH.search(z) for z in _ohne_prosa(nur_prosa))

    # Richtung 2: Code NEBEN einem Literal bleibt sichtbar — der Fall, an dem
    # der Filter durchfiel.
    getarnt = "e = type('E', (), {'quelle': 'lang', 'p': entladung_kwh / ladung_kwh})()\n"
    assert any(_ROH.search(z) for z in _ohne_prosa(getarnt)), (
        "Der Filter blendet Code aus, nicht nur Text — genau der Fehler, den "
        "Sprengsatz S9 aufgedeckt hat."
    )

    # Und Umlaute davor dürfen die Spaltenrechnung nicht verschieben.
    mit_umlaut = "s = 'Größe über Maß'; y = entladung_kwh / ladung_kwh\n"
    assert any(_ROH.search(z) for z in _ohne_prosa(mit_umlaut))


def test_p264_der_diagnose_verwender_ruft_den_helper_und_kappt_nicht():
    """Die Trennlinie zwischen Diagnose und Anzeige, an einer Stelle festgehalten.

    Der Daten-Checker meldet „Entladung > Ladung" und muss den Überschuss dafür
    **sehen** — er ist der einzige, der den ungekappten Helper benutzen darf.
    Nähme er `speicher_wirkungsgrad`, stünde in seiner eigenen Fehlermeldung
    „nicht ermittelbar" statt der Zahl, die den Fehler belegt.

    Umgekehrt darf er die Formel nicht **selbst** schreiben: Ein ungenutzter
    Helper neben einer handgeschriebenen Kopie derselben Formel ist exakt die
    Ausgangslage, aus der N-252 entstanden ist (N-264).
    """
    quelle = (BACKEND / DIAGNOSE_VERWENDER).read_text(encoding="utf-8")
    assert "speicher_effizienz_prozent(" in quelle, (
        "Der Daten-Checker muss den Diagnose-Helper rufen, statt die Division "
        "selbst zu schreiben."
    )
    assert "speicher_wirkungsgrad" not in quelle, (
        "Der Daten-Checker darf NICHT den kappenden SoT nehmen — sonst "
        "verschwindet die Zahl, mit der er den Befund belegt."
    )

    # Und der Helper selbst kappt weiterhin nicht — sonst wäre die Diagnose weg.
    from backend.core.berechnungen.speicher import speicher_effizienz_prozent

    assert speicher_effizienz_prozent(100.0, 107.0) == pytest.approx(107.0)


def test_p252_die_liste_der_deckungspflichtigen_ist_nicht_leer_gelaufen():
    """Gegenprobe zum Prüfer darüber.

    Streicht jemand alle Einträge aus `BRAUCHT_DEN_SOT`, liefe die
    parametrisierte Probe grün durch, ohne irgendetwas zu messen — die Klasse
    des stummen Sprengsatzes aus N-259.
    """
    assert len(BRAUCHT_DEN_SOT) >= 7
    for rel in BRAUCHT_DEN_SOT:
        assert (BACKEND / rel).exists(), f"{rel} existiert nicht (Umbenennung?)"


# ── Die Regel selbst ─────────────────────────────────────────────────────────


def test_p252_obergrenze_gilt_auch_im_langen_fenster():
    """`langes_fenster_quelle` ändert das Etikett, nicht die Grenze.

    Das ist der Kern des Befundes: *Cockpit → Jahr* schrieb „über das ganze
    Fenster gerechnet" unter einen ungekappten Quotienten und machte die
    Falschmessung damit zur bestätigten Aussage.
    """
    from backend.core.berechnungen.speicher_wirkungsgrad import speicher_wirkungsgrad

    moeglich = speicher_wirkungsgrad(100.0, 88.0, None, langes_fenster_quelle="fenster_lang")
    assert moeglich.prozent == pytest.approx(88.0)
    assert moeglich.quelle == "fenster_lang"

    unmoeglich = speicher_wirkungsgrad(100.0, 104.0, None, langes_fenster_quelle="fenster_lang")
    assert unmoeglich.prozent is None
    assert unmoeglich.quelle == "nicht-ermittelbar"


def test_p252_langes_fenster_ueberschreibt_nur_den_unkorrigierten_fall():
    """Mit ΔSoC bleibt die Quelle `soc_korrigiert` — die Messung schlägt das Etikett."""
    from backend.core.berechnungen.speicher_wirkungsgrad import speicher_wirkungsgrad

    mit_soc = speicher_wirkungsgrad(
        100.0, 104.0, -10.0, langes_fenster_quelle="fenster_lang"
    )
    assert mit_soc.quelle == "soc_korrigiert"
    assert mit_soc.prozent == pytest.approx(94.0)


def test_p252_null_prozent_ist_eine_messung_keine_leerstelle():
    """Geladen, nichts entnommen ⇒ 0 %, und das ist ein Wert.

    Die Ausgabestellen prüften `if wert` statt `is not None` und machten aus
    der 0 eine Leerstelle — die 0-Werte-Falle aus CLAUDE.md.
    """
    from backend.core.berechnungen.speicher_wirkungsgrad import speicher_wirkungsgrad

    eta = speicher_wirkungsgrad(50.0, 0.0, None)
    assert eta.prozent == 0.0
    assert eta.quelle == "roh-unkorrigiert"
