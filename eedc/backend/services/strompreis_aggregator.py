"""
Strompreis-Aggregator — Verbrauchsgewichteter Monats-Durchschnittspreis.

Berechnet aus stündlichen TagesEnergieProfil-Daten den effektiven
Durchschnitts-Strompreis für einen Monat:

    Ø_effektiv = Σ(strompreis_cent × netzbezug_kw) / Σ(netzbezug_kw)

Nutzt nur `strompreis_cent` (Endpreis aus HA-Sensor, z.B. Tibber/aWATTar),
NICHT `boersenpreis_cent` — Börsenpreis ist kein Endkundenpreis.

Wird als Vorschlag im Monatsabschluss-Wizard verwendet (Phase 2 aus
docs/archive/KONZEPT-STROMPREIS-MITSCHRIFT.md).
"""

from __future__ import annotations

import logging
from calendar import monthrange
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import and_, extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.berechnungen.zeittarif import (
    gewichteter_arbeitspreis_cent,
    hat_zeitfenster,
)
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


# =============================================================================
# Zeittarif (HT/NT) — N-267
# =============================================================================
#
# ⭐ Warum das HIER steht und nicht in einem eigenen Modul: Die Frage ist
# dieselbe wie oben — „welcher EINE Preis beschreibt diesen Monat?" —, und sie
# wird mit derselben Formel beantwortet (Σ Preis × Menge ÷ Σ Menge über die
# Stundenzeilen). Verschieden ist allein die **Herkunft des Stundenpreises**:
# oben gemessen (`strompreis_cent` aus dem HA-Sensor), hier aus dem Tarif
# abgeleitet. Ein zweites Modul wäre ein zweiter Turm über demselben
# Sachverhalt — die Bauform, gegen die der Daten-Checker an neun Stellen
# ausdrücklich gebaut ist.

async def wirksamer_arbeitspreis_cent(
    db: AsyncSession,
    anlage_id: int,
    jahr: int,
    monat: int,
    tarif,
    *,
    cache: Optional[dict] = None,
) -> float:
    """Der Arbeitspreis, mit dem dieser Monat zu rechnen ist (ct/kWh).

    **Ohne Zeitfenster ist das der Stammpreis** — dann wird die Datenbank gar
    nicht erst gefragt. Mit Fenstern wird der Preis über den **gemessenen**
    Netzbezug der Stundenzeilen gewichtet (ADR-002/P8: der Wert beschreibt
    diesen Monat, nicht heute).

    ⚠ **Fällt auf den Stammpreis zurück, wenn keine Stundenwerte vorliegen** —
    also bei handgetragenen Monatswerten. Das ist der Hochtarif und damit **zu
    hoch**, aber es ist der Preis, den der Anwender ohne das Fenster gezahlt
    hätte: nachvollziehbar, nie erfunden. Wer es genauer braucht, trägt den
    Monats-Ø im Monatsabschluss ein — dasselbe Feld, das der dynamische Tarif
    seit jeher benutzt (`netzbezug_durchschnittspreis_cent`), und dieses Feld
    schlägt den Wert hier ohnehin (`resolve_netzbezug_preis_cent`).

    ⛔ **Kein geschätzter NT-Anteil.** Er wäre „eine Zahl, die genauer aussieht,
    als sie ist" (Gernots Antwort an den Melder in #380) und ein Feld, das zum
    Falschausfüllen einlädt — die #392-Lehre.

    Args:
        tarif: Die Tarifzeile des Monats (``Strompreis`` oder ``None``).
        cache: Optionales ``{(tarif_id, jahr, monat): preis}`` je Anfrage —
            Cockpit → Jahr fragt sonst denselben Monat mehrfach, weil
            ``lade_monats_fakten`` und ``baue_finanz_zeile`` ihn beide brauchen.
    """
    if tarif is None:
        from backend.core.wirtschaftlichkeit_defaults import NETZBEZUG_DEFAULT_CENT
        return NETZBEZUG_DEFAULT_CENT

    stammpreis = tarif.netzbezug_arbeitspreis_cent_kwh
    if not hat_zeitfenster(tarif):
        return stammpreis

    schluessel = (tarif.id, jahr, monat)
    if cache is not None and schluessel in cache:
        return cache[schluessel]

    result = await db.execute(
        select(
            TagesEnergieProfil.datum,
            TagesEnergieProfil.stunde,
            TagesEnergieProfil.netzbezug_kw,
        ).where(
            and_(
                TagesEnergieProfil.anlage_id == anlage_id,
                extract("year", TagesEnergieProfil.datum) == jahr,
                extract("month", TagesEnergieProfil.datum) == monat,
            )
        )
    )
    gewichtet = gewichteter_arbeitspreis_cent(tarif, result.all())
    preis = stammpreis if gewichtet is None else round(gewichtet, 4)

    if cache is not None:
        cache[schluessel] = preis
    return preis
