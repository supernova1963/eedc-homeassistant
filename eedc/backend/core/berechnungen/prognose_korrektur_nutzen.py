"""Wächter «Korrektur nur, wenn sie hilft» — die Entscheidungsregel (Päckchen CC, 9.11.2026, Konzept §7 M3).

eedc korrigiert die OpenMeteo-Rohprognose mit gelernten Faktoren (Korrekturprofil-Kaskade). Ist die korrigierte Day-Ahead-
Prognose über die letzten 30 Tage **schlechter** als die Rohprognose, setzt der Kanon die Korrektur aus (Faktor 1,0) — eedc
zeigt dann den Rohwert, bis die Korrektur wieder gewinnt. Zielmarke Z1: eedc nie dauerhaft schlechter als OpenMeteo roh.

**Hysterese:** aussetzen, wenn ``MAE_Kaskade > MAE_roh + Toleranz``; wieder einschalten erst bei
``MAE_Kaskade ≤ MAE_roh + Toleranz − Hysterese``; dazwischen bleibt der bisherige Zustand (kein Flattern von Tag zu Tag).
Unter ``min_tage`` gepaarten Tagen wird **nie** ausgesetzt — zu wenig Grundlage für ein Urteil.

**Annahmen** (benannt, nicht gemessen optimiert): Toleranz 2 Punkte, Hysterese 1 Punkt, mindestens 14 Tage. An Winterborn
lag die Kaskade am 9.11.2026 gleichauf mit OpenMeteo (Konzept §8, Faktoren ≈ 1,0) — der Wächter wäre dort inaktiv; er ist die
Garantie für Anlagen, deren Profile aus einer anderen Jahreszeit stammen.

Das Stunden-Lernen (``services/korrekturprofil_aggregator.py``, gegen ``lern_soll_stundenprofil_kwh``) ist von der Weiche
unberührt: gelernt wird weiter, nur die Anzeige folgt der Rohprognose, solange die Korrektur nicht hilft.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

#: Annahme: so viele Prozentpunkte MAE darf die Korrektur schlechter sein, bevor sie ausgesetzt wird.
KORREKTUR_TOLERANZ_PUNKTE: float = 2.0
#: Annahme: so viele Punkte muss die Korrektur unter die Toleranz zurück, bevor sie wieder greift.
KORREKTUR_HYSTERESE_PUNKTE: float = 1.0
#: Annahme: unter so vielen gepaarten Tagen (Kaskade und roh mit IST) wird nie ausgesetzt.
KORREKTUR_MIN_TAGE: int = 14
#: Fenster des Vergleichs (Tage vor heute) — dasselbe wie die Ampel-Schwelle `eedc_mae_prozent`.
KORREKTUR_FENSTER_TAGE: int = 30


@dataclass(frozen=True)
class KorrekturNutzen:
    """Ergebnis des Wächters: beide MAE (Prozent, ``None`` = keine Grundlage), gepaarte Tage, Zustand."""

    mae_kaskade_prozent: Optional[float]
    mae_roh_prozent: Optional[float]
    tage: int
    ausgesetzt: bool


def korrektur_aussetzen(
    mae_kaskade_prozent: Optional[float],
    mae_roh_prozent: Optional[float],
    *,
    bisher_ausgesetzt: bool,
    tage: int,
    toleranz_punkte: float = KORREKTUR_TOLERANZ_PUNKTE,
    hysterese_punkte: float = KORREKTUR_HYSTERESE_PUNKTE,
    min_tage: int = KORREKTUR_MIN_TAGE,
) -> bool:
    """Soll der Kanon die Korrektur aussetzen? Schwelle mit Hysterese, nie unter ``min_tage``, nie ohne beide MAE."""
    if mae_kaskade_prozent is None or mae_roh_prozent is None or tage < min_tage:
        return False
    if mae_kaskade_prozent > mae_roh_prozent + toleranz_punkte:
        return True
    if mae_kaskade_prozent <= mae_roh_prozent + toleranz_punkte - hysterese_punkte:
        return False
    return bisher_ausgesetzt
