"""
Monatsabschluss Auto-Aggregator (Etappe 3d P3 Refactoring-Tail).

Kapselt die Energie-Profil-Auto-Aggregation, die nach jedem Wizard-Save
im Background-Task läuft (`_post_save_hintergrund`). Drei Schritte in
fester Reihenfolge:

1. **Closing-Month-Backfill** — `backfill_range()` ruft `aggregate_day` für
   alle Tage des Monats. Schreibt `TagesZusammenfassung` +
   `TagesEnergieProfil`. Nach P3-Architektur-Commit Source
   `auto:monatsabschluss` (über `aggregate_day`'s `datenquelle`-Parameter).
2. **Monats-Rollup** — `rollup_month()` aggregiert `TagesZusammenfassung`
   in fünf `Monatsdaten`-Top-Level-Felder. Source `auto:monatsabschluss`.
3. **Einmaliger Auto-Vollbackfill** — `resolve_and_backfill_from_statistics`
   läuft genau einmal pro Anlage beim ersten Monatsabschluss nach Upgrade
   (Flag `Anlage.vollbackfill_durchgefuehrt`). Source `external:ha_statistics`.

MQTT-Publish und Community-Share sind disjunkt zur Auto-Aggregation und
bleiben im Background-Orchestrator (`_post_save_hintergrund` in
`routes/monatsabschluss.py`).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage
from backend.services.energie_profil import (
    backfill_range,
    resolve_and_backfill_from_statistics,
    rollup_month,
)

logger = logging.getLogger(__name__)


@dataclass
class MonatsabschlussAggregationResult:
    """Ergebnis-Bundle der Auto-Aggregation (Diagnose-/Telemetrie-Zwecke)."""
    backfill_count: int = 0
    rollup_ok: bool = False
    vollbackfill_status: str = ""
    vollbackfill_geschrieben: int = 0
    vollbackfill_verarbeitet: int = 0


async def run_post_monatsabschluss_aggregation(
    anlage: Anlage,
    jahr: int,
    monat: int,
    db: AsyncSession,
) -> MonatsabschlussAggregationResult:
    """
    Auto-Aggregations-Pipeline nach Monatsabschluss-Wizard-Save.

    Verhalten unverändert vs. inline-Variante in `_post_save_hintergrund`:
    Schritt 1+2 in einem Try-Block (Rollup nur wenn Backfill nicht crasht),
    Schritt 3 nur wenn Anlage.vollbackfill_durchgefuehrt=False, Flag wird
    immer gesetzt — auch bei Fehler — sonst Endlos-Retry bei defekter HA-DB.
    """
    erster_tag = date(jahr, monat, 1)
    letzter_tag = (
        date(jahr + 1, 1, 1) - timedelta(days=1) if monat == 12
        else date(jahr, monat + 1, 1) - timedelta(days=1)
    )

    result = MonatsabschlussAggregationResult()

    # 1+2. Closing-Month-Backfill + Monats-Rollup
    try:
        result.backfill_count = await backfill_range(
            anlage, erster_tag, letzter_tag, db,
        )
        if result.backfill_count > 0:
            await db.commit()
        result.rollup_ok = await rollup_month(anlage.id, jahr, monat, db)
        await db.commit()
    except Exception as e:
        logger.warning(f"Energie-Profil Rollup fehlgeschlagen: {type(e).__name__}: {e}")

    # 3. Einmaliger Auto-Vollbackfill aus HA Long-Term Statistics.
    # Läuft genau einmal pro Anlage beim ersten Monatsabschluss nach Upgrade.
    # Doppelläufe mit dem Closing-Month-Backfill oben sind idempotent durch
    # skip_existing in backfill_from_statistics. Flag wird IMMER gesetzt —
    # auch bei Fehler — sonst Endlos-Retry bei defekter HA-DB.
    if not anlage.vollbackfill_durchgefuehrt:
        try:
            backfill = await resolve_and_backfill_from_statistics(
                anlage, db, bis=letzter_tag,
            )
            result.vollbackfill_status = backfill.status
            result.vollbackfill_geschrieben = backfill.geschrieben
            result.vollbackfill_verarbeitet = backfill.verarbeitet

            if backfill.missing_eids:
                logger.warning(
                    f"Auto-Vollbackfill Anlage {anlage.id}: "
                    f"{len(backfill.missing_eids)} Sensor(en) ignoriert: {backfill.missing_eids}"
                )
            if backfill.status == "ok":
                logger.info(
                    f"Auto-Vollbackfill Anlage {anlage.id}: "
                    f"{backfill.geschrieben}/{backfill.verarbeitet} Tage von "
                    f"{backfill.von} bis {backfill.bis}"
                )
            else:
                logger.info(f"Auto-Vollbackfill Anlage {anlage.id} übersprungen: {backfill.detail}")
        except Exception as e:
            logger.warning(f"Auto-Vollbackfill Anlage {anlage.id} Fehler: {type(e).__name__}: {e}")
            await db.rollback()

        # Direktes UPDATE statt ORM-Attribut: robust gegen abgebrochene Session
        await db.execute(
            sql_update(Anlage)
            .where(Anlage.id == anlage.id)
            .values(vollbackfill_durchgefuehrt=True)
        )
        await db.commit()

    return result
