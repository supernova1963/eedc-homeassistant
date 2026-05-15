"""
Strompreis-Aggregator — Verbrauchsgewichteter Monats-Durchschnittspreis.

Berechnet aus stündlichen TagesEnergieProfil-Daten den effektiven
Durchschnitts-Strompreis für einen Monat:

    Ø_effektiv = Σ(strompreis_cent × netzbezug_kw) / Σ(netzbezug_kw)

Nutzt nur `strompreis_cent` (Endpreis aus HA-Sensor, z.B. Tibber/aWATTar),
NICHT `boersenpreis_cent` — Börsenpreis ist kein Endkundenpreis.

Wird als Vorschlag im Monatsabschluss-Wizard verwendet (Phase 2 aus
docs/KONZEPT-STROMPREIS-MITSCHRIFT.md).
"""

from __future__ import annotations

import logging
from calendar import monthrange
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import and_, extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.tages_energie_profil import TagesEnergieProfil

logger = logging.getLogger(__name__)


@dataclass
class StrompreisAggregat:
    """Ergebnis der Monats-Strompreis-Aggregation."""
    gewichtet_cent: Optional[float]  # Verbrauchsgewichteter Ø (ct/kWh)
    arithmetisch_cent: float         # Einfacher Ø aller Stunden (ct/kWh)
    abgedeckte_stunden: int          # Stunden mit Preisdaten
    sollstunden: int                 # Theoretische Stunden im Monat

    @property
    def abdeckung(self) -> float:
        """Abdeckung als Anteil (0..1)."""
        return self.abgedeckte_stunden / self.sollstunden if self.sollstunden > 0 else 0

    @property
    def konfidenz(self) -> int:
        """Konfidenz-Score basierend auf Abdeckung."""
        if self.abdeckung > 0.95:
            return 95
        if self.abdeckung > 0.70:
            return 80
        return 60


async def berechne_monats_durchschnittspreis(
    anlage_id: int, jahr: int, monat: int, db: AsyncSession
) -> Optional[StrompreisAggregat]:
    """
    Berechnet den verbrauchsgewichteten Monats-Durchschnittspreis.

    Nur Stunden mit `strompreis_cent IS NOT NULL` werden berücksichtigt.
    Negativer Netzbezug wird auf 0 geclampt (Daten-Glitches).

    Returns:
        StrompreisAggregat oder None wenn keine Preisdaten vorhanden.
    """
    result = await db.execute(
        select(
            TagesEnergieProfil.strompreis_cent,
            TagesEnergieProfil.netzbezug_kw,
        ).where(
            and_(
                TagesEnergieProfil.anlage_id == anlage_id,
                extract("year", TagesEnergieProfil.datum) == jahr,
                extract("month", TagesEnergieProfil.datum) == monat,
                TagesEnergieProfil.strompreis_cent.isnot(None),
            )
        )
    )
    rows = result.all()

    if not rows:
        return None

    # Verbrauchsgewichteter Durchschnitt
    summe_kosten = 0.0   # ct (preis × kWh)
    summe_kwh = 0.0      # kWh
    summe_preise = 0.0   # ct (für arithmetischen Ø)

    for preis, bezug in rows:
        if preis is None:
            continue
        kw = max(0.0, bezug or 0.0)  # Negativen Netzbezug auf 0 clampen
        summe_kosten += preis * kw    # ct × kW × 1h = ct·kWh
        summe_kwh += kw
        summe_preise += preis

    n = len(rows)
    tage_im_monat = monthrange(jahr, monat)[1]
    sollstunden = tage_im_monat * 24

    gewichtet = round(summe_kosten / summe_kwh, 2) if summe_kwh > 0 else None
    arithmetisch = round(summe_preise / n, 2) if n > 0 else 0.0

    return StrompreisAggregat(
        gewichtet_cent=gewichtet,
        arithmetisch_cent=arithmetisch,
        abgedeckte_stunden=n,
        sollstunden=sollstunden,
    )
