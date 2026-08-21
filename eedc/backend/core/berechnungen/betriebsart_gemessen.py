"""Gemessener Verbrauch je Betriebsart — Gerät oder Innengeräte (#263).

**Wozu diese Datei.** Seit der Konzept-Fassung vom 2026-08-21 kann eine
Split-Klimaanlage ihren Verbrauch je Betriebsart **gemessen** mitbringen, statt
ihn eedc aus dem Betriebsmodus ableiten zu lassen: vier Zähler (Heizen ·
Kühlen · Lüften · Entfeuchten), am Gerät oder je Innengerät. Wer sie in Home
Assistant nicht direkt bekommt, baut sie sich mit einem **Utility Meter** und
einem Tarif je Betriebsart.

**Die eine Regel, und sie steht nur hier** (ADR-001 — eine Auflösung ist eine
Formel, kein Routen-Detail):

1. **Das Gerätefeld gewinnt.** Wer den ganzen Verbrauch einer Betriebsart an
   einem Zähler hat, hat die vollständigere Zahl — die Innengeräte sind dann
   die Aufschlüsselung, nicht die Summe.
2. **Sonst die Summe der Innengeräte.**
3. **Sonst nichts** (``None``, nicht ``0.0``): „kein Zähler" und „Zähler stand
   auf null" sind verschiedene Aussagen. Ein ``0.0`` an dieser Stelle
   verdrängte die abgeleitete Aufteilung und ersetzte sie durch eine Null —
   die F-42-Klasse.

⛔ **Gerätefeld und Innengeräte werden NIE addiert.** Beide beschreiben
dieselbe Menge auf verschiedenen Ebenen; sie zu summieren wäre die
Doppelzählungs-Klasse, die uns beim BKW, beim Speicher und beim
Wallbox/E-Auto-Pool je einmal getroffen hat.
"""

from __future__ import annotations

from typing import Optional

from backend.core.betriebsmodus import (
    BETRIEBSART_NUTZENERGIE_FELD,
    BETRIEBSART_STROM_FELD,
    MESSBARE_MODI,
)
from backend.core.field_definitions import basis_feld_key

__all__ = [
    "betriebsart_strom_kwh",
    "betriebsart_nutzenergie_kwh",
    "hat_gemessene_betriebsart",
]


def _aufgeloest(daten: Optional[dict], basis_feld: str) -> Optional[float]:
    """Gerätefeld, sonst Σ Innengeräte, sonst ``None`` — siehe Modul-Kopf."""
    if not isinstance(daten, dict):
        return None

    direkt = daten.get(basis_feld)
    if direkt is not None:
        try:
            return float(direkt)
        except (TypeError, ValueError):
            return None

    summe = 0.0
    gefunden = False
    for key, wert in daten.items():
        if wert is None or key == basis_feld:
            continue
        if basis_feld_key(key) != basis_feld:
            continue
        try:
            summe += float(wert)
        except (TypeError, ValueError):
            continue
        gefunden = True
    return summe if gefunden else None


def betriebsart_strom_kwh(daten: Optional[dict], modus: str) -> Optional[float]:
    """Gemessener **Strom**verbrauch dieser Betriebsart, oder ``None``."""
    feld = BETRIEBSART_STROM_FELD.get(modus)
    return _aufgeloest(daten, feld) if feld else None


def betriebsart_nutzenergie_kwh(daten: Optional[dict], modus: str) -> Optional[float]:
    """Gemessene **abgegebene Nutzenergie** dieser Betriebsart, oder ``None``."""
    feld = BETRIEBSART_NUTZENERGIE_FELD.get(modus)
    return _aufgeloest(daten, feld) if feld else None


def hat_gemessene_betriebsart(daten: Optional[dict]) -> bool:
    """Bringt diese Zeile **irgendeinen** gemessenen Betriebsart-Strom mit?

    Das ist die Weiche für ADR-002/P8 an dieser Stelle: **gemessen schlägt
    abgeleitet**. Wo sie ``True`` sagt, darf die aus dem Betriebsmodus
    gerechnete Aufteilung nicht zusätzlich angewandt werden — sonst stünde
    dieselbe Menge zweimal in derselben Zeile.

    ⚠ Bewusst nur der **Strom**: die Nutzenergie ist eine andere Größe und
    verdrängt keine Stromaufteilung.
    """
    return any(
        betriebsart_strom_kwh(daten, modus) is not None for modus in MESSBARE_MODI
    )
