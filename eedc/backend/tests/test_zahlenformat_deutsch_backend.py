"""N-353: Backend-Wächter für die deutsche Zahlenschreibweise in Anwendertexten.

**Warum es diesen Wächter gibt.** Die Regel „eine Zahl heißt 6,0 kWp, nicht
6.0 kWp" ist Style-Guide 0a und seit N-234 im Backend als SoT vorhanden
(heute ``core/zahlenformat.py``). Gewächtert war sie bis zum 2026-09-16 nur auf
der **Client**-Seite: ``check:de-de`` liest ausschließlich ``frontend/src``
(N-203). Der Daten-Checker schrieb deshalb weiter „6.0 kWp", während dasselbe
Gerät in der Oberfläche und in allen vier PDF-Berichten „6,0 kWp" heißt —
**85 Stellen in sieben Dateien**, am Produktivcode erhoben.

⚠ **Die Zahl war bis zum Commit falsch — hier stand 80, im CHANGELOG 83.**
Beide stammten aus Erhebungen mit dem **zu engen** Muster (s. ``MUSTER``
unten). Neu gezaehlt gegen den Stand vor der Umstellung, mit genau dem
Muster und dem Filter, die dieser Waechter heute fuehrt: 14 datenquelle ·
10 emob · 7 energieprofil · 27 monatsdaten · 24 stammdaten · 1 waermepumpe ·
2 zaehler = **85**, danach **0**. *Wer eine Zahl in einen Anwendertext
schreibt, erhebt sie mit dem Werkzeug, das am Ende im Baum steht.*

⚠ **Der Wächter prüft die FORM, nicht den Wortlaut.** Er sucht f-String-
Formatierungen mit fester Nachkommastelle (``{x:.2f}``) bzw. mit dem
Tausendertrenner-Trick (``{x:_.2f}``) in Dateien, deren Ausgabe ein Anwender
liest. Beide Defekte zählen, und der zweite ist der leisere:

* ``f"{6.0:.1f}"`` ergibt ``6.0`` statt ``6,0`` — das Dezimaltrennzeichen.
* ``f"{12000:.0f}"`` ergibt ``12000`` statt ``12.000`` — der **Tausenderpunkt**.
  Er fehlt auch bei ``:.0f``; wer nur auf den Punkt statt Komma achtet, sieht
  diese Hälfte nicht. Zwei Proben hingen daran (``1260 W`` → ``1.260 W``).

⛔ **Die Fläche ist bewusst eng gezogen und wächst nicht von selbst.**
``SCHARF`` nennt die Verzeichnisse, für die die Regel heute gilt. Alles andere
steht in ``NOCH_NICHT_UMGESTELLT`` **mit gemessener Zahl** — dieselbe Bauform
wie ``P10_NOCH_NICHT_MIGRIERT`` in ``test_wurzelmuster_konformitaet.py``: eine
Baseline, die nur fallen darf, nie steigen. Sie ist **kein Freibrief**, sondern
die Buchführung über eine Restschuld, die noch niemand beauftragt hat.

⚠ **Was der Wächter NICHT sieht:** ``str(wert)``, ``round()`` gefolgt von
Verkettung, und jede Formatierung, die zur Laufzeit zusammengesetzt wird. Er
fängt die Bauform, die 85-mal dastand — nicht jede denkbare.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

#: Verzeichnisse, in denen die Regel heute gilt. Ein Treffer hier ist rot.
SCHARF = [
    "services/daten_checker",
    # 2026-10-14: der Checker reicht Texte aus dem Berechnungskern durch
    # (`invarianten.py::pruefe_speicher_netzladung_kumulativ` → Details der
    # Warnung «Netzladung übersteigt Gesamtladung (kumulativ)», dort stand
    # «1500.000 kWh»). Gewächtert wird deshalb auch der Ort, an dem der Text
    # ENTSTEHT. Ein Verzeichnis, keine Datei — `_sammle` nimmt nur Verzeichnisse.
    # Beim Scharfschalten 13 Stellen in 3 Dateien umgestellt, danach 0.
    "core/berechnungen",
]

#: Restschuld, gemessen am 2026-09-16, nachgezogen am 2026-10-15 — Zahl darf fallen, nie steigen.
#: ⚠ Das sind **Anwendertexte**, keine Logzeilen: Stichprobe ``investitionen/roi.py::get_roi_dashboard``
#: (``f'{result.km_elektrisch:.0f} km elektrisch'``) steht in der Begründung,
#: die eine Wärmepumpen-Kachel anzeigt. Die Fläche ist erhoben, aber nicht
#: beauftragt — wer sie anfasst, zieht die Zahl hier mit herunter.
NOCH_NICHT_UMGESTELLT = {
    "api/routes": 16,   # weites Muster; 2026-09-16: 79 (das enge zaehlte 78 — s. MUSTER), 2026-10-15: 16 (nachgezogen, Entscheid Gernot)
}

#: Bewusste Ausnahmen, je Stelle begründet (N-234-Präzedenz: Koordinaten).
#: Form: (relativer Pfad, Zeilennummer-unabhängiges Textstück).
AUSNAHMEN: list[tuple[str, str]] = [
    # Noch keine. Eine Ausnahme braucht eine Begründung in dieser Liste,
    # nicht ein `noqa` an der Fundstelle.
]

# Jede f-String-Formatierung mit fester Nachkommastelle — ``{x:.2f}``,
# ``{x:_.2f}``, ``{x:+.1f}``, ``{x:>8.2f}``.
#
# ⛔ **Das Muster war beim ersten Bau ZU ENG und hat vier Stellen übersehen**
# (``{delta_signed:+.1f}``): es verlangte direkt hinter dem ``:`` entweder
# nichts, ein Komma oder einen Unterstrich — das **Vorzeichen-Flag** stand nicht
# darin. Gefunden hat es nicht der Wächter, sondern der volle pytest-Lauf: vier
# Proben sicherten „Δ +25.0 kWh" zu und blieben grün, während die halbe Meldung
# daneben schon deutsch war. *Ein Prüfer, dessen Muster enger ist als die Regel,
# meldet grün über genau die Stellen, die er nicht kennt.*
MUSTER = re.compile(r"\{[^{}]*:[^{}]*\.\d+f\}")


def _treffer(pfad: Path) -> list[tuple[int, str]]:
    """Formatierungen in dieser Datei — Kommentare und Logzeilen ausgenommen."""
    gefunden: list[tuple[int, str]] = []
    for nr, zeile in enumerate(pfad.read_text(encoding="utf-8").split("\n"), 1):
        nackt = zeile.strip()
        if nackt.startswith("#") or "logger." in zeile:
            continue
        if MUSTER.search(zeile):
            if any(str(pfad).endswith(p) and t in zeile for p, t in AUSNAHMEN):
                continue
            gefunden.append((nr, nackt[:110]))
    return gefunden


def _sammle(unterverzeichnis: str) -> list[tuple[str, int, str]]:
    wurzel = BACKEND / unterverzeichnis
    alle: list[tuple[str, int, str]] = []
    for datei in sorted(wurzel.rglob("*.py")):
        for nr, text in _treffer(datei):
            alle.append((str(datei.relative_to(BACKEND)), nr, text))
    return alle


def test_scharfe_flaechen_schreiben_deutsch():
    """In den scharfen Verzeichnissen steht keine rohe Formatierung mehr."""
    befunde = [b for v in SCHARF for b in _sammle(v)]
    assert not befunde, (
        "Rohe Zahlenformatierung in einem Anwendertext — bitte "
        "`core.zahlenformat.fmt_zahl(wert, n)` verwenden:\n"
        + "\n".join(f"  {d}:{n}  {t}" for d, n, t in befunde)
    )


def test_restschuld_waechst_nicht():
    """Die nicht umgestellten Flächen werden nicht größer.

    ⛔ Steigt eine Zahl, ist eine neue rohe Formatierung dazugekommen — dann
    gehört sie umgestellt, nicht die Baseline erhöht.
    """
    for verzeichnis, erwartet in NOCH_NICHT_UMGESTELLT.items():
        ist = len(_sammle(verzeichnis))
        assert ist <= erwartet, (
            f"{verzeichnis}: {ist} rohe Formatierungen, Baseline {erwartet}. "
            "Neue Stellen bitte gleich über `core.zahlenformat` schreiben."
        )
        if ist < erwartet:
            # Kein Fehler, aber die Zahl gehört nachgezogen — sonst deckelt eine
            # veraltete Baseline einen Rückfall.
            print(
                f"HINWEIS: {verzeichnis} steht bei {ist} statt {erwartet} — "
                "Baseline in NOCH_NICHT_UMGESTELLT nachziehen."
            )


def test_der_sot_ist_erreichbar_und_rechnet_deutsch():
    """Gegenprobe: der SoT selbst tut, was der Wächter verlangt."""
    from backend.core.zahlenformat import fmt_zahl, fmt_kwh, fmt_pct, fmt_einheit

    assert fmt_zahl(6.0, 1) == "6,0"
    assert fmt_kwh(12000) == "12.000 kWh", "der Tausenderpunkt ist die zweite Hälfte"
    assert fmt_kwh(9125.59, 1) == "9.125,6 kWh"
    assert fmt_pct(48.1372, 2) == "48,14 %", "Regel 0a: % mit Leerzeichen"
    assert fmt_einheit(6.0, "kWp", 1) == "6,0 kWp"


def test_pdf_seite_bleibt_am_gedankenstrich():
    """Der Umzug nach `core/` darf das PDF-Schriftbild nicht verändern."""
    from backend.services.pdf.formatierung import LEER, fmt_zahl as pdf_fmt

    assert LEER == "–", "der PDF-Gedankenstrich, nicht der Frontend-Token"
    assert pdf_fmt(None) == "–"
    assert pdf_fmt(12345.67, 2) == "12.345,67"


def test_kein_lokaler_nachbau_im_checker():
    """Die drei lokalen `replace('.', ',')`-Nachbauten sind abgelöst (N-182-Klasse)."""
    treffer = []
    for datei in sorted((BACKEND / "services/daten_checker").rglob("*.py")):
        quelle = datei.read_text(encoding="utf-8")
        for nr, zeile in enumerate(quelle.split("\n"), 1):
            if 'replace(".", ",")' in zeile:
                treffer.append(f"{datei.name}:{nr}")
    assert not treffer, (
        "Eigene Zahlenformatierung neben dem SoT: " + ", ".join(treffer)
    )


def test_jede_checker_datei_mit_zahlen_kennt_den_sot():
    """Wer Zahlen ausgibt, importiert den SoT — sonst ist der Sweep unvollständig."""
    ohne = []
    for datei in sorted((BACKEND / "services/daten_checker").rglob("*.py")):
        quelle = datei.read_text(encoding="utf-8")
        if "fmt_zahl(" in quelle and "from backend.core.zahlenformat" not in quelle:
            ohne.append(datei.name)
    assert not ohne, f"benutzt fmt_zahl ohne Import: {ohne}"


def test_die_module_sind_syntaktisch_heil():
    """Ein Sweep über 85 Stellen darf keine Datei zerlegen."""
    for datei in sorted((BACKEND / "services/daten_checker").rglob("*.py")):
        ast.parse(datei.read_text(encoding="utf-8"), filename=str(datei))
