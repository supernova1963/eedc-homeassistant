"""Börsenpreis-Rang-Berechnung für den HA-Export (#150 Slice B).

Reine Rang-Logik (Berechnungs-Layer, ADR-001): bewertet die stündlichen
Day-Ahead-Börsenpreise eines Tages und ordnet jeder Stunde einen Rang zu.

Tag- und Nacht-Fenster werden **getrennt** bewertet (je eigenes 1–5/99-Ranking).
Welche Stunden zum Tag- bzw. Nacht-Fenster gehören, entscheidet der Aufrufer
solar-basiert (Sonnenauf-/-untergang); diese Funktion ist davon unabhängig und
rein deterministisch testbar.

„Günstig" ist seit Rainer-PN 2026-06-11 zweistufig: Rang 1–5 je Fenster UND
Preis mindestens 10 % unter dem Tagesdurchschnitt ohne die 3 Peak-Stunden.
Ohne die Schwelle waren die Top-5 rein relativ — die „günstige Stunden"-Anzahl
stand damit praktisch konstant auf 10, und ein erzwungener Verbrauch /
eine Netzladung in einer „günstigen", aber kaum billigeren Stunde ergibt
keinen Sinn.

eedc liefert damit nur einen **Trigger-Wert** — keine Lade-/Entlade-Strategie.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional

# Maximal die fünf günstigsten Stunden je Fenster bekommen Rang 1–5
# (1 = billigste), alle übrigen Rang 99 (teuer/Rest).
GUENSTIG_TOP_N = 5
RANG_TEUER = 99

# Günstig-Schwelle: Preis muss ≥10 % unter dem Durchschnitt der Tagespreise
# ohne die PEAK_AUSSCHLUSS_N teuersten Stunden liegen (Rainer-Definition:
# „24 Tagespreise minus 3 Peakpreise, aus den verbleibenden 21 den
# Durchschnitt, günstig = 10 % darunter").
GUENSTIG_SCHWELLE_FAKTOR = 0.90
PEAK_AUSSCHLUSS_N = 3


@dataclass
class PreisRangErgebnis:
    """Ergebnis der Rang-Bewertung eines Tages."""

    rang_aktuell: Optional[int]                 # Rang der aktuellen Stunde (1–5 oder 99); None wenn kein Preis
    guenstige_stunden_anzahl: int               # Σ als günstig markierter Stunden (Rang 1–5) über beide Fenster
    rang_profil: dict[int, int] = field(default_factory=dict)  # {stunde: rang} aller bewerteten Stunden
    guenstige_stunden_tag: int = 0              # günstige Stunden im Tag-Fenster
    guenstige_stunden_nacht: int = 0            # günstige Stunden im Nacht-Fenster
    schwelle_cent: Optional[float] = None       # Günstig-Schwelle (ct/kWh); None wenn zu wenige Preise


def guenstig_schwelle(
    preise_nach_stunde: Mapping[int, Optional[float]],
) -> Optional[float]:
    """Günstig-Schwelle des Tages: Ø der Preise ohne die 3 Peaks, −10 %.

    Returns ``None``, wenn nach Peak-Ausschluss keine Basis bleibt (weniger
    als ``PEAK_AUSSCHLUSS_N + 1`` Preise) — dann greift keine Schwelle.
    """
    werte = sorted(p for p in preise_nach_stunde.values() if p is not None)
    if len(werte) <= PEAK_AUSSCHLUSS_N:
        return None
    basis = werte[:-PEAK_AUSSCHLUSS_N]
    return (sum(basis) / len(basis)) * GUENSTIG_SCHWELLE_FAKTOR


def _rang_im_fenster(
    preise_nach_stunde: Mapping[int, Optional[float]],
    stunden: Iterable[int],
    schwelle: Optional[float],
) -> dict[int, int]:
    """Rangfolge innerhalb eines Fensters: günstigste Stunde = 1.

    Nur Stunden mit vorhandenem Preis werden bewertet. Rang 1–N bekommen
    höchstens die ``GUENSTIG_TOP_N`` billigsten Stunden — und nur, solange ihr
    Preis die Günstig-Schwelle unterschreitet (``schwelle is None`` → keine
    Schwelle, rein relatives Ranking).
    """
    vorhanden = [
        (h, preise_nach_stunde[h])
        for h in stunden
        if h in preise_nach_stunde and preise_nach_stunde[h] is not None
    ]
    # Sekundärschlüssel Stunde: stabile, reproduzierbare Reihenfolge bei Preisgleichheit.
    sortiert = sorted(vorhanden, key=lambda x: (x[1], x[0]))
    raenge: dict[int, int] = {}
    for idx, (h, preis) in enumerate(sortiert):
        guenstig = idx < GUENSTIG_TOP_N and (schwelle is None or preis <= schwelle)
        raenge[h] = (idx + 1) if guenstig else RANG_TEUER
    return raenge


def berechne_preis_rang(
    preise_nach_stunde: Mapping[int, Optional[float]],
    tag_stunden: Iterable[int],
    nacht_stunden: Iterable[int],
    aktuelle_stunde: int,
) -> PreisRangErgebnis:
    """Bewertet Tag- und Nacht-Fenster getrennt und liest den Rang der aktuellen Stunde.

    Die Günstig-Schwelle wird über ALLE Tagespreise gebildet (nicht je
    Fenster), das Ranking selbst bleibt fensterweise.

    Args:
        preise_nach_stunde: {Stunde 0–23: Börsenpreis ct/kWh}.
        tag_stunden: Stunden des Tag-Fensters (Sonnenauf→-untergang).
        nacht_stunden: Stunden des Nacht-Fensters.
        aktuelle_stunde: Stunde, deren Rang als ``rang_aktuell`` zurückkommt.

    Returns:
        PreisRangErgebnis (rang_aktuell, günstige-Stunden-Anzahl gesamt /
        Tag / Nacht, Schwelle, Profil je Stunde).
    """
    schwelle = guenstig_schwelle(preise_nach_stunde)

    tag_raenge = _rang_im_fenster(preise_nach_stunde, tag_stunden, schwelle)
    nacht_raenge = _rang_im_fenster(preise_nach_stunde, nacht_stunden, schwelle)
    raenge: dict[int, int] = {**tag_raenge, **nacht_raenge}

    guenstig_tag = sum(1 for r in tag_raenge.values() if r <= GUENSTIG_TOP_N)
    guenstig_nacht = sum(1 for r in nacht_raenge.values() if r <= GUENSTIG_TOP_N)
    return PreisRangErgebnis(
        rang_aktuell=raenge.get(aktuelle_stunde),
        guenstige_stunden_anzahl=guenstig_tag + guenstig_nacht,
        rang_profil=raenge,
        guenstige_stunden_tag=guenstig_tag,
        guenstige_stunden_nacht=guenstig_nacht,
        schwelle_cent=round(schwelle, 3) if schwelle is not None else None,
    )
