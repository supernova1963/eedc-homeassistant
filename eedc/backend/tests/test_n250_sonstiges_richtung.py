"""N-250 — die Richtung eines *Sonstiges*-Geräts ohne gepflegte Kategorie.

**N-250 (Cockpit → Monat, Block „Sonstige Geräte").** Ein Gerät vom Typ
*Sonstiges* **ohne gepflegte Kategorie** war unsichtbar, obwohl seine Zahlen in
den Summen darüber mitliefen: `aktueller_monat.py` las
`parameter.get("kategorie", "erzeuger")` und filterte den Erzeuger-Zweig mit
`erzeugung > 0`. Ein ungepflegter **Verbraucher** fiel damit durch beide Maschen.
Der Default war zugleich der einzige seiner Art im Baum — die beiden
Tages-Schreibpfade und der Tages-Layer lesen eine leere Kategorie als
*Verbraucher*, `monats_fakten` nimmt ohne sie **beide** Felder mit.

"""

from __future__ import annotations

import pytest


# ───────────────────── N-250: die Richtung ohne Kategorie ───────────────────


@pytest.mark.parametrize(
    "kategorie,hat_erzeugung,erwartet",
    [
        # Gepflegt schlägt alles — auch gegen den Wert.
        ("erzeuger", False, "erzeuger"),
        ("verbraucher", True, "verbraucher"),
        # Ungepflegt: der Wert entscheidet. Das ist der gemeldete Fall —
        # vorher landete ein Verbrauchsgerät im Erzeuger-Zweig und war hinter
        # `erzeugung > 0` unsichtbar.
        (None, False, "verbraucher"),
        ("", False, "verbraucher"),
        (None, True, "erzeuger"),
        # Eine dritte, unbekannte Kategorie fällt nicht durch: sie wird wie
        # „ungepflegt" behandelt statt still zum Erzeuger zu werden. Relevant
        # für #377 (Gas/Öl/Wasser), das genau eine dritte Kategorie vorsieht.
        ("zaehler", False, "verbraucher"),
    ],
)
def test_n250_richtung_ohne_kategorie_kommt_aus_dem_wert(
    kategorie, hat_erzeugung, erwartet
) -> None:
    from backend.core.berechnungen import sonstiges_richtung

    assert sonstiges_richtung(kategorie, hat_erzeugung) == erwartet


# Stellen, die den Erzeuger-Default noch tragen — **nicht** vergessen, sondern
# offen und benannt. Der Fund N-250 nannte eine Stelle; dieser Wächter hat beim
# ersten Lauf drei weitere gefunden, und sie brauchen eine eigene Entscheidung:
#
# * `core/field_definitions.py` (2×) entscheidet, **welche Felder** ein
#   Sonstiges-Gerät überhaupt bekommt — und zwar bevor ein Wert existiert, aus
#   dem sich die Richtung ableiten ließe. Hier den Default zu drehen ist keine
#   Kosmetik: Ein Bestandsgerät ohne gepflegte Kategorie, in dem heute
#   Erzeugungswerte stehen, bekäme im Formular Verbrauchsfelder — die gepflegten
#   Werte wären nicht mehr sichtbar. Das ist eine Migrationsfrage, keine Zeile.
# * `api/routes/investitionen/dashboards.py` aggregiert über viele Monate; ein
#   „hat Erzeugung" gibt es dort nicht als einzelnen Wert.
#
# Wer eine dieser Zeilen auflöst, streicht sie hier. Die Liste darf **nicht**
# wachsen — eine neue Fundstelle ist ein Fehler, kein Eintrag.
N250_OFFENE_ERZEUGER_DEFAULTS = {
    "core/field_definitions.py",
    "api/routes/investitionen/dashboards.py",
}


def test_n250_kein_neuer_erzeuger_default_im_baum() -> None:
    """Baumweiter Wächter statt Regression auf eine einzelne Zeile.

    `get("kategorie", "erzeuger")` war die Fundstelle; sie darf an keiner
    **neuen** Stelle auftauchen — auch nicht an einer, die es heute noch nicht
    gibt. Wo die Richtung entschieden wird, entscheidet sie `sonstiges_richtung`.

    Kommentarzeilen zählen nicht: Ein Prüfer, der den Text über einer Zeile
    mitliest, misst das falsche Objekt — dieselbe Klasse wie der falsch-negative
    Abnahme-Prüfer, der eine Commit-Message für einen CHANGELOG-Eintrag hielt.
    """
    import re
    from pathlib import Path

    wurzel = Path(__file__).resolve().parents[1]
    muster = re.compile(r"""get\(\s*["']kategorie["']\s*,\s*["']erzeuger["']""")
    treffer = {
        str(p.relative_to(wurzel))
        for p in wurzel.rglob("*.py")
        if "tests" not in p.parts and "venv" not in p.parts
        for zeile in p.read_text(encoding="utf-8").splitlines()
        if muster.search(zeile) and not zeile.lstrip().startswith("#")
    }

    assert treffer <= N250_OFFENE_ERZEUGER_DEFAULTS, (
        "Neuer Erzeuger-Default für die Sonstiges-Kategorie: "
        f"{sorted(treffer - N250_OFFENE_ERZEUGER_DEFAULTS)}. "
        "Die Richtung kommt aus `sonstiges_richtung` (N-250)."
    )
    # Gegenrichtung: eine aufgelöste Stelle muss aus der Liste verschwinden,
    # sonst deckelt sie irgendwann Arbeit, die längst getan ist.
    assert treffer == N250_OFFENE_ERZEUGER_DEFAULTS, (
        "Die Ausnahmeliste nennt Stellen, die es nicht mehr gibt: "
        f"{sorted(N250_OFFENE_ERZEUGER_DEFAULTS - treffer)}."
    )
