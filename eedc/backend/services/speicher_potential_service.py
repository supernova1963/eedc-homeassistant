"""Lädt die Stundenreihe für die Speicher-Potentialanalyse (#358 Phase 2).

Trennung wie in ADR-001: die **Formel** steht in
`core/berechnungen/speicher_potential.py`, hier liegt allein das **Sourcing** —
Stunden aus `TagesEnergieProfil` holen, in `SpeicherStunde` übersetzen, je Monat
gruppieren.

⚠ **Der SoC in `TagesEnergieProfil` hat keine `investition_id` — und er ist bei
mehreren Speichern KEIN Mischwert** (N-239, am Code gemessen 2026-08-12; dieser
Docstring behauptete bis dahin das Gegenteil).
`energie_profil/_helpers.py::_get_soc_history` nimmt den **ersten** gemappten
SoC-Sensor mit Daten und bricht ab. Bei zwei Speichern beschreibt die Auswertung
also **ein** Gerät — welches, entscheidet die Reihenfolge im Sensor-Mapping. Die
Route gibt `anzahl_speicher` mit aus, damit die Sicht es sagen kann, statt eine
Genauigkeit zu suggerieren, die die Datenlage nicht hergibt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.speicher_potential import (
    SOC_VOLL_PROZENT,
    PotentialErgebnis,
    SpeicherStunde,
    berechne_zusatzpotential,
)
from backend.models.tages_energie_profil import TagesEnergieProfil


@dataclass
class MonatsPotential:
    """Ein Monat der Auswertung."""

    jahr: int
    monat: int
    nutzbares_zusatzpotential_kwh: float
    ueberschuss_kwh: float
    stunden_voll: int
    zyklen_gesamt: int
    zyklen_leergelaufen: int
    #: Verteilung der Stunden auf SoC-Bins (0–10, 10–20, … 90–100) — die Heatmap-Zeile.
    soc_bins: list[int]


@dataclass
class PotentialAuswertung:
    gesamt: PotentialErgebnis
    monate: list[MonatsPotential]
    tage_mit_daten: int
    von: Optional[date]
    bis: Optional[date]


#: Zehn Bins à 10 Prozentpunkte — die Zeile der Monat-×-SoC-Heatmap.
SOC_BIN_ANZAHL = 10


def _bin_index(soc: float) -> int:
    """SoC-Prozent → Bin 0–9. 100 % fällt in den obersten Bin, nicht daneben."""
    return min(SOC_BIN_ANZAHL - 1, max(0, int(soc // (100 / SOC_BIN_ANZAHL))))


def _als_speicher_stunde(zeile: TagesEnergieProfil) -> SpeicherStunde:
    """Stundenmittel in kW ⇒ kWh der Stunde: numerisch identisch, benannt verschieden.

    Die Spalten heißen `_kw`, tragen aber das **Stundenmittel**; über eine Stunde
    integriert ist der Zahlenwert derselbe. Der Layer rechnet ausdrücklich in kWh,
    deshalb wird hier umbenannt statt stillschweigend gemischt.
    """
    return SpeicherStunde(
        soc_prozent=zeile.soc_prozent,
        einspeisung_kwh=zeile.einspeisung_kw or 0.0,
        netzbezug_kwh=zeile.netzbezug_kw or 0.0,
    )


async def lade_potential_auswertung(
    db: AsyncSession,
    anlage_id: int,
    von: Optional[date] = None,
    bis: Optional[date] = None,
) -> PotentialAuswertung:
    """Wertet den Zeitraum aus — gesamt **und** je Monat.

    Die Gesamt-Auswertung läuft über die **durchgehende** Reihe, nicht über die
    Summe der Monatswerte: ein Zyklus, dessen Überschuss am 31. anfällt und dessen
    Nacht in den 1. reicht, würde sonst an der Monatsgrenze zerschnitten. Die
    Monatswerte sind deshalb eine Aufschlüsselung **zur Anzeige**, ihre Summe kann
    minimal von der Gesamtzahl abweichen — bewusst, und in der Sicht so benannt.
    """
    query = (
        select(TagesEnergieProfil)
        .where(TagesEnergieProfil.anlage_id == anlage_id)
        .order_by(TagesEnergieProfil.datum, TagesEnergieProfil.stunde)
    )
    if von is not None:
        query = query.where(TagesEnergieProfil.datum >= von)
    if bis is not None:
        query = query.where(TagesEnergieProfil.datum <= bis)

    zeilen = list((await db.execute(query)).scalars().all())
    if not zeilen:
        return PotentialAuswertung(
            gesamt=berechne_zusatzpotential([]), monate=[], tage_mit_daten=0,
            von=None, bis=None,
        )

    gesamt = berechne_zusatzpotential([_als_speicher_stunde(z) for z in zeilen])

    nach_monat: dict[tuple[int, int], list[TagesEnergieProfil]] = {}
    for zeile in zeilen:
        nach_monat.setdefault((zeile.datum.year, zeile.datum.month), []).append(zeile)

    monate: list[MonatsPotential] = []
    for (jahr, monat), monats_zeilen in sorted(nach_monat.items()):
        teil = berechne_zusatzpotential([_als_speicher_stunde(z) for z in monats_zeilen])
        bins = [0] * SOC_BIN_ANZAHL
        for zeile in monats_zeilen:
            if zeile.soc_prozent is not None:
                bins[_bin_index(zeile.soc_prozent)] += 1
        monate.append(MonatsPotential(
            jahr=jahr,
            monat=monat,
            nutzbares_zusatzpotential_kwh=round(teil.nutzbares_zusatzpotential_kwh, 1),
            ueberschuss_kwh=round(teil.ueberschuss_gesamt_kwh, 1),
            stunden_voll=teil.stunden_voll,
            zyklen_gesamt=teil.zyklen_gesamt,
            zyklen_leergelaufen=teil.zyklen_leergelaufen,
            soc_bins=bins,
        ))

    return PotentialAuswertung(
        gesamt=gesamt,
        monate=monate,
        tage_mit_daten=len({z.datum for z in zeilen}),
        von=zeilen[0].datum,
        bis=zeilen[-1].datum,
    )


__all__ = [
    "MonatsPotential",
    "PotentialAuswertung",
    "SOC_BIN_ANZAHL",
    "SOC_VOLL_PROZENT",
    "lade_potential_auswertung",
]
