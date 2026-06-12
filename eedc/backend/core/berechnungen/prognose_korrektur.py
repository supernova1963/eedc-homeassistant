"""Korrigiertes Prognose-Tagesprofil — SoT für die Stunden-Korrektur (ADR-001).

Wendet pro Energie-Slot einen Korrekturfaktor (aus der Kaskade
``korrekturprofil_lookup``) auf das rohe Prognose-Stundenprofil an und leitet
den Tageswert per Konstruktion als Σ der exportierten Stunden-Slots ab.

Pflicht-Invariante (HA-Export #150, Stundenprofil-Attribute Tag+1/2/3):

    tageswert_kwh == round(Σ stundenprofil_export_kwh, 1)

Der Tageswert wird bewusst aus den **gerundeten** Export-Slots summiert —
damit stimmen Sensor-State und ``stundenprofil_kwh``-Attribut in HA exakt
überein (keine Rundungs-Drift zwischen State und Attribut).

Konsumenten: ``services/eedc_prognose_service.py`` (HA-Export #150 +
Prognosen-Vergleich-Spalte „eedc" — Symmetrie per Konstruktion).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence


@dataclass(frozen=True)
class KorrigiertesTagesprofil:
    """Korrigiertes 24-Slot-Energieprofil eines Prognose-Tages (Backward-Slots)."""

    stunden_kwh: tuple  # 24 korrigierte Slots, interne Präzision (3 Nachkommastellen)
    stundenprofil_export_kwh: tuple  # 24 Slots, gerundet auf 2 — Sensor-Attribut
    tageswert_kwh: float  # == round(Σ stundenprofil_export_kwh, 1) — Invariante


def korrigiere_tagesprofil(
    stunden_kwh: Sequence[Optional[float]],
    faktoren: Sequence[Optional[float]],
    fallback_faktor: Optional[float] = None,
) -> KorrigiertesTagesprofil:
    """Wendet Stunden-Korrekturfaktoren auf ein rohes Energieprofil an.

    Args:
        stunden_kwh: rohe Energie-Slots (Backward, Slot N = Energie [N-1, N)).
            Kürzere Listen werden mit 0 aufgefüllt, ``None``-Slots zählen als 0.
        faktoren: Korrekturfaktor je Stunde (Kaskaden-Treffer) oder ``None``
            (Kaskaden-Miss → ``fallback_faktor``).
        fallback_faktor: Legacy-Skalar (``_get_lernfaktor``) für Stunden ohne
            Kaskaden-Treffer; ``None`` → Faktor 1.0 (heutiges Verhalten bei
            frisch installierten Anlagen ohne jedes Profil).

    Returns:
        :class:`KorrigiertesTagesprofil` mit Tageswert = Σ Export-Slots.
    """
    slots: list[float] = []
    for h in range(24):
        roh = stunden_kwh[h] if h < len(stunden_kwh) else None
        if roh is None:
            roh = 0.0
        faktor = faktoren[h] if h < len(faktoren) else None
        if faktor is None:
            faktor = fallback_faktor
        if faktor is None:
            faktor = 1.0
        slots.append(round(roh * faktor, 3))

    export = tuple(round(v, 2) for v in slots)
    return KorrigiertesTagesprofil(
        stunden_kwh=tuple(slots),
        stundenprofil_export_kwh=export,
        tageswert_kwh=round(sum(export), 1),
    )
