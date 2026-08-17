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
]

#: Stellen, die den rohen Quotienten mit voller Absicht behalten — je mit
#: Grund. Eine Zeile ohne Grund gehört nicht in diese Liste.
BEWUSST_ROH = {
    # Der Daten-Checker MELDET den Überschuss gerade — er braucht die
    # ungekappte Zahl, um sie im Befundtext nennen zu können.
    "services/daten_checker/stammdaten.py",
    # Prognose- und Potenzialpfade klemmen selbst (min(...)) und brauchen
    # einen Wert, keine fehlende Aussage.
    "services/speicher_potential_service.py",
    "api/routes/aussichten.py",
    # Die Heimat der Regel selbst.
    "core/berechnungen/speicher_wirkungsgrad.py",
    # ⚠ UNBEWERTET, mit Trigger (N-264): Diese beiden tragen eine DRITTE
    # Semantik für dieselbe Frage. `services/speicher_wirtschaftlichkeit.py`
    # klemmt im langen Fenster still auf `min(1.0, …)` — bei 104 % steht dort
    # also glatt „100 %" statt „nicht ermittelbar"; `speicher.py::
    # speicher_effizienz_prozent` liefert bewusst ungekappt (F-22: „Diagnose
    # statt stillem Cap") und hat seit N-252 keinen Produktivverwender mehr.
    # Beides ist ein Entscheid, kein Nachzug — deshalb hier notiert statt
    # nebenbei geändert (Regel 6). Trigger: nächster Eingriff an einer der
    # beiden Stellen.
    "services/speicher_wirtschaftlichkeit.py",
    "core/berechnungen/speicher.py",
}

#: Roher Quotient aus Entladung und Ladung — in jeder Schreibrichtung.
_ROH = re.compile(
    r"entladung[a-z_]*\s*(?:/|\*\s*100\s*/)\s*[a-z_.]*ladung"
    r"|[a-z_.]*entladung[a-z_]*\s*/\s*[a-z_.]*ladung[a-z_]*",
    re.IGNORECASE,
)


def _py_dateien():
    for pfad in BACKEND.rglob("*.py"):
        rel = pfad.relative_to(BACKEND).as_posix()
        if rel.startswith("tests/") or "/venv/" in rel:
            continue
        yield rel, pfad


def _prosa_zeilen(quelle: str) -> set[int]:
    """Zeilennummern, die zu einem String-Literal gehören (Docstrings inklusive).

    Ohne das misst der Prüfer die **Erklärung** der Regel statt ihrer
    Anwendung: Die Docstrings von `speicher.py` und
    `speicher_wirtschaftlichkeit.py` schreiben „entladung / ladung" aus, um zu
    begründen, warum man es *nicht* so machen soll. Ein Prüfer, der darüber
    rot geht, erzieht dazu, die Begründung zu löschen.
    """
    zeilen: set[int] = set()
    try:
        baum = ast.parse(quelle)
    except SyntaxError:
        # Mindestens eine Datei im Baum trägt ein BOM. Sie soll den baumweiten
        # Prüfer nicht anhalten — ohne Prosa-Filter prüft er dort strenger,
        # nie schwächer.
        return zeilen
    for knoten in ast.walk(baum):
        if isinstance(knoten, ast.Constant) and isinstance(knoten.value, str):
            ende = getattr(knoten, "end_lineno", knoten.lineno) or knoten.lineno
            zeilen.update(range(knoten.lineno, ende + 1))
    return zeilen


# ── Hälfte 1: Abwesenheit ────────────────────────────────────────────────────


def test_p252_kein_roher_eta_quotient_ausserhalb_der_ausnahmen():
    """Baumweit: niemand bildet den η-Quotienten mehr selbst."""
    treffer: list[str] = []
    for rel, pfad in _py_dateien():
        if rel in BEWUSST_ROH:
            continue
        quelle = pfad.read_text(encoding="utf-8")
        prosa = _prosa_zeilen(quelle)
        for nr, zeile in enumerate(quelle.splitlines(), 1):
            if nr in prosa:
                continue
            nackt = zeile.split("#", 1)[0]
            if _ROH.search(nackt):
                treffer.append(f"{rel}:{nr}: {zeile.strip()}")
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
