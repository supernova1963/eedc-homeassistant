"""Jede Checker-Kategorie muss im Frontend ankommen — sonst ist sie unsichtbar.

**Der belegte Fall: F-21 (10.08.2026).** `emob_doppelzaehlung_tage` und
`phev_anteil_unbestimmt` fehlten in `config/datenCheckerKategorien.ts` — im
Label-Map **und** in der Reihenfolge. Der Kommentar dort sagt es selbst:

    ⚠ Diese Liste ist **kein Sortier-Wunsch, sondern ein Filter**: die
    Daten-Checker-Seite rendert `map` über sie, eine fehlende Kategorie
    erscheint dort also gar nicht.

Der Doppelzählungs-Befund trug einen Reparatur-Knopf und war damit
unerreichbar — Backend grün, Anwender blind. Gefunden hat das ein Mensch,
kein Prüfer; danach wurde keiner gebaut.

**Diese Probe ist der Prüfer.** Sie liest die Enum und die TS-Datei als Text —
dasselbe Verfahren wie `test_live_tagesverlauf_farben_kanon.py`, das den
Farb-Kanon gegen den Service hält. Baseline am 23.08.2026: 27 Kategorien,
beide Listen vollständig.
"""

from __future__ import annotations

from pathlib import Path

from backend.services.daten_checker.kategorien import CheckKategorie

_TS = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "config" / "datenCheckerKategorien.ts"
).read_text(encoding="utf-8")

# Die Datei trägt beide Karten hintereinander; getrennt wird am Namen der
# zweiten, damit ein Label die Reihenfolge nicht versehentlich mitdeckt.
_LABELS, _REIHENFOLGE = _TS.split("KATEGORIE_REIHENFOLGE", 1)


def test_jede_kategorie_hat_ein_label():
    fehlen = [k.value for k in CheckKategorie if f"{k.value}:" not in _LABELS]
    assert not fehlen, (
        f"Ohne Label im Frontend: {fehlen} — die Kategorie erscheint mit ihrem "
        "technischen Namen statt mit einem Satz, den ein Anwender liest."
    )


def test_jede_kategorie_steht_in_der_reihenfolge():
    fehlen = [k.value for k in CheckKategorie if f"'{k.value}'" not in _REIHENFOLGE]
    assert not fehlen, (
        f"Nicht in KATEGORIE_REIHENFOLGE: {fehlen} — diese Liste ist ein "
        "FILTER, nicht ein Sortier-Wunsch. Die Befunde dieser Kategorie "
        "erscheinen im Daten-Checker gar nicht (F-21)."
    )


def test_die_probe_liest_wirklich_zwei_listen():
    """Gegenprobe an der Probe selbst: die Trennung muss etwas trennen.

    Stünde die Aufteilung schief, deckte das Label-Map beide Prüfungen ab und
    ein Fehlen in der Reihenfolge bliebe unbemerkt — ein Prüfer, der aufs
    falsche Objekt zeigt.
    """
    assert "KATEGORIE_LABELS" in _LABELS
    assert "KATEGORIE_LABELS" not in _REIHENFOLGE
    assert len(_REIHENFOLGE) > 100
