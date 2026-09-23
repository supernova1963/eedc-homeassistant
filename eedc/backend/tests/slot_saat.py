"""Eine Stundenreihe säen, die **beide Uhren der Zeile** richtig bedient (N-387).

**Warum es diese Datei gibt.** Eine ``TagesEnergieProfil``-Zeile trägt zwei
Konventionen (SoT: ``core/berechnungen/slot_konvention.py``, Absatz „DREI
Bahnen"): die ``*_kw``-Spalten liegen **backward** (Zeile ``s`` =
``[s-1, s)``), ``soc_prozent`` / ``soc_je_speicher`` / ``strompreis_cent`` /
``boersenpreis_cent`` dagegen **forward** (Zeile ``s`` = ``[s, s+1)``). Wer eine
Probe säen will, in der *„in dieser Stunde war der Speicher voll und es wurde
eingespeist"* gilt, muss den Ladestand deshalb in die Zeile **davor** schreiben.

⛔ **Bis zum 23.09.2026 taten die Proben das nicht** — sie legten Menge und
Ladestand/Preis in dieselbe Zeile und schrieben damit genau den Versatz fest,
den N-387 beschreibt. Solange die Leser ebenso falsch paarten, war das grün.
Die Umstellung der Leser hat 28 Proben rot gemeldet; ihre **Aussage** ist
unverändert, nur ihre Saat trägt jetzt die Konvention der Produktion.

⚠ **Kein Export darf mit ``test`` beginnen** — ``python_functions = test*``
greift auf jeden Namen im Modul-Namensraum des Importeurs (dieselbe Falle wie
in ``ha_lts_helfer.py`` beschrieben).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from backend.models.tages_energie_profil import TagesEnergieProfil

#: Die Spalten, die den Perioden-**Beginn** als Schlüssel tragen (forward).
FORWARD_SPALTEN = frozenset({
    "soc_prozent", "soc_je_speicher", "strompreis_cent", "boersenpreis_cent",
})


def vorzeile(tag: date, stunde: int) -> tuple[date, int]:
    """Die Zeile, in der der Forward-Wert der Stunde ``stunde`` steht."""
    if stunde == 0:
        return tag - timedelta(days=1), 23
    return tag, stunde - 1


def tep_stunden(
    anlage_id: int,
    tag: date,
    stunden: dict[int, dict[str, Any]],
) -> list[TagesEnergieProfil]:
    """``{stunde: {spalte: wert}}`` ⇒ Zeilen, forward-Spalten eine Zeile früher.

    ``stunden[h]`` beschreibt **die Stunde, die die Zeile h trägt** — also den
    Backward-Slot ``h`` = das Intervall ``[h-1, h)``: seine Flüsse *und* den
    Ladestand bzw. Preis, der **in diesem Intervall** galt. Der Builder verteilt
    beides auf die Zeilen, in denen die Produktion sie ablegt — Flüsse nach
    ``h``, Forward-Werte nach ``h-1`` (über die Tagesgrenze nach ``23`` des
    Vortags), denn dort steht der Wert für ``[h-1, h)``.

    ⚠ ``h`` zählt damit wie die **Spalte** ``stunde``, nicht wie die Wanduhr:
    ``{0: {...}}`` beschreibt ``[Vortag 23:00, 00:00)``.

    Zeilen entstehen nur, wo etwas zu schreiben ist; zwei Stunden, die sich eine
    Zeile teilen (Fluss von ``h``, Preis von ``h+1``), werden zusammengeführt.
    """
    zeilen: dict[tuple[date, int], dict[str, Any]] = {}
    for stunde, werte in stunden.items():
        # Die Zeile der beschriebenen Stunde entsteht **immer** — auch wenn sie
        # nur Forward-Werte trägt, die eine Zeile früher landen. So sieht die
        # Saat aus wie die Produktion: der Aggregator schreibt jede Stunde eines
        # Tages, und erst eine vorhandene Zeile kann einen Preis zugeordnet
        # bekommen.
        zeilen.setdefault((tag, stunde), {})
        for spalte, wert in werte.items():
            ziel = vorzeile(tag, stunde) if spalte in FORWARD_SPALTEN else (tag, stunde)
            zeilen.setdefault(ziel, {})[spalte] = wert
    return [
        TagesEnergieProfil(anlage_id=anlage_id, datum=d, stunde=h, **werte)
        for (d, h), werte in sorted(zeilen.items())
    ]


def tep_zeilen(
    anlage_id: int,
    beschreibungen: list[dict[str, Any]],
    **feste: Any,
) -> list[TagesEnergieProfil]:
    """Wie :func:`tep_stunden`, nur für eine **flache** Liste von Stunden.

    Jede Beschreibung trägt ``datum`` und ``stunde`` und daneben die Spalten
    dieser Stunde; ``feste`` wird jeder erzeugten Zeile mitgegeben (z. B.
    ``created_at``). Forward-Spalten landen wieder in der Zeile davor.
    """
    zeilen: dict[tuple[date, int], dict[str, Any]] = {}
    for b in beschreibungen:
        tag, stunde = b["datum"], b["stunde"]
        zeilen.setdefault((tag, stunde), {})   # s. `tep_stunden`
        for spalte, wert in b.items():
            if spalte in ("datum", "stunde"):
                continue
            ziel = vorzeile(tag, stunde) if spalte in FORWARD_SPALTEN else (tag, stunde)
            zeilen.setdefault(ziel, {})[spalte] = wert
    return [
        TagesEnergieProfil(anlage_id=anlage_id, datum=d, stunde=h, **feste, **werte)
        for (d, h), werte in sorted(zeilen.items())
    ]
