"""Börsenpreis-Rang-Berechnung für den HA-Export (#150 Slice B).

Reine Rang-Logik (Berechnungs-Layer, ADR-001): bewertet die stündlichen
Day-Ahead-Börsenpreise eines Tages und ordnet jeder Stunde einen Rang zu.

Tag- und Nacht-Fenster werden **getrennt** bewertet (je eigenes 1–5/99-Ranking).
Welche Stunden zum Tag- bzw. Nacht-Fenster gehören, entscheidet der Aufrufer
solar-basiert (Sonnenauf-/-untergang); diese Funktion ist davon unabhängig und
rein deterministisch testbar.

eedc liefert damit nur einen **Trigger-Wert** — keine Lade-/Entlade-Strategie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional

# Die fünf günstigsten Stunden je Fenster bekommen Rang 1–5 (1 = billigste),
# alle übrigen Rang 99 (teuer/Rest).
GUENSTIG_TOP_N = 5
RANG_TEUER = 99


@dataclass
class PreisRangErgebnis:
    """Ergebnis der Rang-Bewertung eines Tages."""

    rang_aktuell: Optional[int]                 # Rang der aktuellen Stunde (1–5 oder 99); None wenn kein Preis
    guenstige_stunden_anzahl: int               # Σ als günstig markierter Stunden (Rang 1–5) über beide Fenster
    rang_profil: dict[int, int] = field(default_factory=dict)  # {stunde: rang} aller bewerteten Stunden


def _rang_im_fenster(
    preise_nach_stunde: Mapping[int, Optional[float]],
    stunden: Iterable[int],
) -> dict[int, int]:
    """Rangfolge innerhalb eines Fensters: günstigste Stunde = 1.

    Nur Stunden mit vorhandenem Preis werden bewertet. Hat das Fenster weniger
    als ``GUENSTIG_TOP_N`` Stunden, erhalten alle einen Rang ≤ N (alle günstig).
    """
    vorhanden = [
        (h, preise_nach_stunde[h])
        for h in stunden
        if h in preise_nach_stunde and preise_nach_stunde[h] is not None
    ]
    # Sekundärschlüssel Stunde: stabile, reproduzierbare Reihenfolge bei Preisgleichheit.
    sortiert = sorted(vorhanden, key=lambda x: (x[1], x[0]))
    raenge: dict[int, int] = {}
    for idx, (h, _preis) in enumerate(sortiert):
        raenge[h] = (idx + 1) if idx < GUENSTIG_TOP_N else RANG_TEUER
    return raenge


def berechne_preis_rang(
    preise_nach_stunde: Mapping[int, Optional[float]],
    tag_stunden: Iterable[int],
    nacht_stunden: Iterable[int],
    aktuelle_stunde: int,
) -> PreisRangErgebnis:
    """Bewertet Tag- und Nacht-Fenster getrennt und liest den Rang der aktuellen Stunde.

    Args:
        preise_nach_stunde: {Stunde 0–23: Börsenpreis ct/kWh}.
        tag_stunden: Stunden des Tag-Fensters (Sonnenauf→-untergang).
        nacht_stunden: Stunden des Nacht-Fensters.
        aktuelle_stunde: Stunde, deren Rang als ``rang_aktuell`` zurückkommt.

    Returns:
        PreisRangErgebnis (rang_aktuell, günstige-Stunden-Anzahl, Profil je Stunde).
    """
    raenge: dict[int, int] = {}
    raenge.update(_rang_im_fenster(preise_nach_stunde, tag_stunden))
    raenge.update(_rang_im_fenster(preise_nach_stunde, nacht_stunden))

    guenstig = sum(1 for r in raenge.values() if r <= GUENSTIG_TOP_N)
    return PreisRangErgebnis(
        rang_aktuell=raenge.get(aktuelle_stunde),
        guenstige_stunden_anzahl=guenstig,
        rang_profil=raenge,
    )
