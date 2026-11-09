"""Dateilänge je Produktivdatei gegen eine eingecheckte Baseline (Wächter seit 9.11.2026, Päckchen CC Nachlauf N3).

Schwesterdateien: `test_kognitive_komplexitaet.py` (dasselbe Muster, eine Ebene tiefer: Funktion statt Datei) ·
Frontend-Hälfte `frontend/scripts/check-dateilaenge.mjs` (`npm run check:dateilaenge`, Baseline
`frontend/dateilaenge-baseline.txt`).

**Anlass (Frage Gernot 9.11.2026: «wie kann es sein, dass es wächst — haben wir keine Regel/Wächter?»).** Das
Refactoring-Kriterium (Entscheid 19.09.2026, «Funktion vor Datei») kennt zwei Schwellen: Funktion > 50 kognitiv —
seit 14.10. gewächtert — und Datei > 900 netto. Die zweite stand nur im Werkzeug
`~/.claude/plans/refactoring-werkzeug/komplexitaet.py`; keine Regel hielt eine Datei auf, die darüber wuchs.

**Was gilt (Entscheid Gernot 9.11.2026 spät: «Ich folge deiner Empfehlung»):**

1. **Keine neue Datei über 900 netto.** Eine Datei, die nicht in `dateilaenge_baseline.txt` steht und über 900 liegt,
   ist rot — aufteilen (Schwesterdateien, Muster `live_wetter.py` → `live_wetter_antwort.py`), nicht eintragen.
2. **Eine Datei der Baseline wächst höchstens auf `Baseline-Wert × 1,02`.** Die Toleranz ist eine Annahme: ein Fix darf
   eine große Datei um ein paar Zeilen verlängern, ohne dass jeder Fix zum Umbau wird; ein Umbau schreibt die Baseline
   neu, und der Diff zeigt die Richtung.
3. **Die Baseline schrumpft nur.** Fällt eine Datei unter 900 (oder verschwindet sie), wird der Test rot, bis die
   Baseline neu geschrieben ist — so sinkt die Zahl sichtbar im Commit.
4. `AUSNAHMEN` mit Grund (erzeugte Tabellen, keine Logik).

**Maß: netto-Codezeilen** — Zeilen ohne Leerzeile, ohne reine Kommentarzeile, ohne mehrzeiligen String (Docstring) —
**dieselbe Definition wie `komplexitaet.py::netto`** (tokenize-basiert; `wc -l` ist kein Kriterium), damit Werkzeug,
Vorlage und Gate eine Zahl nennen. Geprüft am 9.11.2026: alle 523 Produktivdateien bitgleich mit
`python3 komplexitaet.py --datei 900 --json …` (Feld `dateien[].netto`).

**Wenn dieser Test rot wird:** Datei bewusst aufgeteilt oder gekürzt? Dann die Baseline neu schreiben und den Diff im
Commit mitschicken:

    cd eedc && python -c "from backend.tests.test_dateilaenge import baseline_schreiben; baseline_schreiben()"

Eine Baseline-Datei über der Toleranz oder eine neue Datei über 900 ist dagegen kein Baseline-Fall, sondern ein
Umbau-Fall.
"""
from __future__ import annotations

import io
import tokenize
from pathlib import Path

import pytest

from backend.tests.quellbaum import produktivbaum

BASELINE = Path(__file__).with_name("dateilaenge_baseline.txt")

#: Das Datei-Kriterium des Refactoring-Werkzeugs (Entscheid Gernot 19.09.2026).
SCHWELLE = 900
#: Annahme: so weit darf eine Baseline-Datei durch Fixes wachsen, bevor ein Umbau fällig ist.
TOLERANZ = 1.02

#: Dateien, die die Regel nicht trifft — mit dem Grund, den ein Prüfer lesen soll. Ein neuer Eintrag braucht den Beleg,
#: dass die Datei eine erzeugte Tabelle ohne Logik ist.
AUSNAHMEN: dict[str, str] = {
    "services/plz_to_state.py": "Datentabelle PLZ → Bundesland (ein Literal), keine Logik — derselbe Ausschluss wie im "
                                "Werkzeug komplexitaet.py und im Komplexitäts-Wächter",
}


def netto(zeilen: list[str]) -> int:
    """Netto-Codezeilen — wörtlich `komplexitaet.py::netto` (Zeilen − reine Kommentarzeilen − Leerzeilen − Zeilen
    mehrzeiliger String-Token)."""
    src = "\n".join(zeilen) + "\n"
    k = sum(1 for z in zeilen if z.strip().startswith("#"))
    leer = sum(1 for z in zeilen if not z.strip())
    d = 0
    try:
        for t in tokenize.generate_tokens(io.StringIO(src).readline):
            if t.type == tokenize.STRING and t.start[0] != t.end[0]:
                d += t.end[0] - t.start[0] + 1
    except Exception:  # noqa: BLE001 — wie das Werkzeug: ein Tokenizer-Fehler zählt die Datei brutto
        pass
    return max(len(zeilen) - k - leer - d, 0)


def messen() -> dict[str, int]:
    """`datei` (relativ zu `backend/`) → netto-Codezeilen, über den Produktivbaum ohne `AUSNAHMEN`."""
    return {d.rel: netto(d.quelle.splitlines()) for d in produktivbaum() if d.rel not in AUSNAHMEN}


def baseline_lesen() -> dict[str, int]:
    out: dict[str, int] = {}
    for zeile in BASELINE.read_text().splitlines():
        if not zeile.strip() or zeile.startswith("#"):
            continue
        wert, datei = zeile.split("\t", 1)
        out[datei] = int(wert)
    return out


def baseline_schreiben() -> None:
    """Den Bestand über `SCHWELLE` neu schreiben (nach einem Umbau; Diff gehört in den Commit)."""
    werte = messen()
    zeilen = [f"{v}\t{k}" for k, v in sorted(werte.items()) if v > SCHWELLE]
    BASELINE.write_text(
        f"# Bestand der Produktivdateien mit mehr als {SCHWELLE} netto-Codezeilen — darf nur schrumpfen.\n"
        "# Neu schreiben: siehe test_dateilaenge.py (Docstring). Format: netto<TAB>datei (relativ zu backend/)\n"
        + "\n".join(zeilen) + "\n"
    )
    print(f"{len(zeilen)} Dateien > {SCHWELLE} netto nach {BASELINE.name} geschrieben")


@pytest.fixture(scope="module")
def werte() -> dict[str, int]:
    return messen()


def test_keine_neue_datei_ueber_900(werte):
    baseline = baseline_lesen()
    neu = {k: v for k, v in werte.items() if v > SCHWELLE and k not in baseline}
    assert not neu, (
        f"{len(neu)} neue Datei(en) über {SCHWELLE} netto-Codezeilen — kein Baseline-Fall, sondern aufteilen "
        "(Schwesterdatei):\n  " + "\n  ".join(f"{v:5}  {k}" for k, v in sorted(neu.items(), key=lambda x: -x[1]))
    )


def test_bestand_waechst_hoechstens_um_die_toleranz(werte):
    baseline = baseline_lesen()
    gewachsen = {k: (alt, werte[k]) for k, alt in baseline.items() if werte.get(k, 0) > alt * TOLERANZ}
    assert not gewachsen, (
        f"Datei(en) im Bestand über Baseline × {TOLERANZ} gewachsen — aufteilen, die Baseline wird nicht hochgesetzt:\n  "
        + "\n  ".join(f"{alt:5} → {neu:5}  {k}" for k, (alt, neu) in sorted(gewachsen.items()))
    )


def test_baseline_ist_aktuell(werte):
    """Unter 900 gefallen oder verschwunden ⇒ Baseline neu schreiben, damit die Zahl im Commit sinkt."""
    baseline = baseline_lesen()
    veraltet = {k: (alt, werte.get(k)) for k, alt in baseline.items() if werte.get(k, 0) <= SCHWELLE}
    assert not veraltet, (
        f"{len(veraltet)} Baseline-Eintrag/-Einträge liegen jetzt ≤ {SCHWELLE} oder fehlen — Baseline neu schreiben "
        "(Docstring) und den Diff committen:\n  "
        + "\n  ".join(f"{alt:5} → {str(neu):>5}  {k}" for k, (alt, neu) in sorted(veraltet.items()))
    )


def test_ausnahmen_sind_noch_noetig(werte):
    """Eine Ausnahme für eine Datei, die es nicht mehr gibt, ist tot — raus damit."""
    vorhanden = {d.rel for d in produktivbaum()}
    tot = [k for k in AUSNAHMEN if k not in vorhanden]
    assert not tot, "Ausnahme(n) ohne Datei — aus AUSNAHMEN streichen:\n  " + "\n  ".join(tot)
