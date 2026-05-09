"""
Einmalige Daten-Migrationen rund um sensor_snapshots und TagesEnergieProfil.

Nicht zu verwechseln mit den Schema-Migrationen in `core/database.py:_run_migrations`
(synchron, SQLite-DDL). Hier: asynchrone Daten-Re-Berechnungen, die Snapshot-
Reads und Aggregator-Aufrufe brauchen.

Idempotenz wird vom Aufrufer (`core/database.py`) über eine `migrations`-Tabelle
gesteuert — die Funktionen hier sind selbst nicht idempotent gegen Doppelaufrufe.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def migrate_3c_p2_counter_backward(session: AsyncSession) -> dict[str, int]:
    """Etappe 3c P2: bestehende `wp_starts_anzahl`-Stundenwerte auf Backward (#144) umrechnen.

    Vor v3.27 wurde der Counter-Pfad als Forward implementiert (Slot h =
    `snap[h+1] − snap[h]`), entgegen der #144-Festlegung. Nach Etappe 3c P2 läuft
    er als Backward (Slot h = `snap[h] − snap[h-1]`). Bestehende Tage müssen
    einmalig re-aggregiert werden, sonst sieht der User Forward-Werte für alte
    Tage und Backward-Werte für neue.

    Pro betroffenem (Anlage, Datum)-Paar wird `get_hourly_counter_sum_by_feld`
    neu aufgerufen und die 24 Stundenwerte in `tages_energie_profil` geschrieben.
    Lücken (None) werden mit-übertragen.

    Returns:
        {"fixed": <Anzahl Tage>, "skipped": <Tage ohne Anlage/mit Fehler>}
    """
    from backend.models.anlage import Anlage
    from backend.models.investition import Investition
    from backend.models.tages_energie_profil import TagesEnergieProfil
    from backend.services.snapshot.aggregator import get_hourly_counter_sum_by_feld

    pairs_result = await session.execute(
        select(TagesEnergieProfil.anlage_id, TagesEnergieProfil.datum)
        .where(TagesEnergieProfil.wp_starts_anzahl.isnot(None))
        .distinct()
    )
    pairs = pairs_result.all()

    if not pairs:
        logger.info("Etappe 3c P2 Migration: keine Counter-Stundenwerte vorhanden — übersprungen")
        return {"fixed": 0, "skipped": 0}

    logger.info(f"Etappe 3c P2 Migration: {len(pairs)} (Anlage,Tag)-Paare mit wp_starts_anzahl")

    # Anlage + Investitionen pro anlage_id einmal cachen — vermeidet N+1.
    anlage_cache: dict[int, Anlage] = {}
    invs_cache: dict[int, dict] = {}

    fixed = 0
    skipped = 0
    for anlage_id, datum in pairs:
        if anlage_id not in anlage_cache:
            anlage = await session.get(Anlage, anlage_id)
            if anlage is None:
                skipped += 1
                continue
            anlage_cache[anlage_id] = anlage
            invs_result = await session.execute(
                select(Investition).where(Investition.anlage_id == anlage_id)
            )
            invs_cache[anlage_id] = {str(i.id): i for i in invs_result.scalars().all()}

        try:
            neue_werte = await get_hourly_counter_sum_by_feld(
                session,
                anlage_cache[anlage_id],
                invs_cache[anlage_id],
                datum,
                "wp_starts_anzahl",
            )
        except Exception as e:
            logger.warning(
                f"Etappe 3c P2 Migration Anlage={anlage_id} {datum}: "
                f"{type(e).__name__}: {e}"
            )
            skipped += 1
            continue

        # Pro Stunde update — auch NULL setzen, wo bei Backward eine Lücke ist
        # (Anker fehlt → ehrlicher als alter Forward-Wert).
        for h in range(24):
            val = neue_werte.get(h)
            await session.execute(
                text(
                    "UPDATE tages_energie_profil SET wp_starts_anzahl = :v "
                    "WHERE anlage_id = :a AND datum = :d AND stunde = :h"
                ),
                {"v": val, "a": anlage_id, "d": datum, "h": h},
            )
        fixed += 1

    await session.commit()
    logger.info(
        f"Etappe 3c P2 Migration fertig: {fixed} Tage Backward-neu-gerechnet, "
        f"{skipped} skipped"
    )
    return {"fixed": fixed, "skipped": skipped}
