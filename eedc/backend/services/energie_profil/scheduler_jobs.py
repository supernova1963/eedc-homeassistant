"""
Scheduler-Wrapper (Etappe 3d P3 Refactoring-Tail).

Tägliche und 15-minütige Jobs für Energie-Profil-Aggregation, extrahiert aus
`services/energie_profil_service.py`. Verhalten unverändert. Eigene
Schreib-Pfade entstehen nicht — beide Wrapper rufen `aggregate_day` für jede
Anlage; Provenance-Anschluss landet daher im Aggregator selbst (P3 Commit F).
Retention-Cleanup für TagesEnergieProfil > 2 Jahre bleibt im Vortags-Wrapper.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import delete, select

from backend.core.database import get_session
from backend.models.anlage import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services.energie_profil.aggregator import aggregate_day

logger = logging.getLogger(__name__)


async def aggregate_yesterday_all() -> dict:
    """
    Scheduler-Job: Finalisiert den Vortag für alle Anlagen (täglich um 00:15).

    Schreibt den Vortag final (inkl. Wetter-IST-Daten aus Archive-API),
    berechnet TagesZusammenfassung und räumt alte TagesEnergieProfil-Einträge auf.

    Retention: TagesEnergieProfil-Einträge älter als 2 Jahre werden gelöscht.
    TagesZusammenfassung bleibt dauerhaft erhalten.

    Returns:
        Dict mit Ergebnissen pro Anlage
    """
    gestern = date.today() - timedelta(days=1)
    results: dict = {}

    async with get_session() as db:
        anlagen_result = await db.execute(select(Anlage))
        anlagen = anlagen_result.scalars().all()

        for anlage in anlagen:
            try:
                zusammenfassung = await aggregate_day(
                    anlage, gestern, db, datenquelle="scheduler",
                )
                results[anlage.id] = {
                    "status": "ok" if zusammenfassung else "keine_daten",
                    "datum": gestern.isoformat(),
                }
            except Exception as e:
                logger.error(f"Anlage {anlage.id}: Aggregation fehlgeschlagen: {type(e).__name__}: {e}")
                results[anlage.id] = {"status": "fehler", "error": str(e)}

        # Retention-Cleanup: TagesEnergieProfil älter als 2 Jahre löschen
        cutoff = date.today() - timedelta(days=730)
        result = await db.execute(
            delete(TagesEnergieProfil).where(TagesEnergieProfil.datum < cutoff)
        )
        deleted = result.rowcount
        if deleted > 0:
            logger.info(f"Energie-Profil Cleanup: {deleted} Stundenwerte älter als 2 Jahre gelöscht")
        await db.commit()

    return results


async def aggregate_today_all() -> dict:
    """
    Rollierender Job: Aggregiert den laufenden Tag für alle Anlagen.

    Läuft alle 15 Minuten. Schreibt alle abgeschlossenen Stunden des heutigen
    Tages (mit 10-Minuten-Puffer, damit HA-History die Daten garantiert hat).
    Überschreibt bestehende Stunden-Einträge (Upsert via Delete+Insert).

    Die 00:15-Aggregation des Vortags finalisiert dann die Wetter-IST-Daten
    und schreibt die TagesZusammenfassung endgültig.

    Returns:
        Dict mit Ergebnissen pro Anlage
    """
    now = datetime.now()
    heute = date.today()

    letzte_abgeschlossene_stunde = now.hour - 1 if now.minute < 10 else now.hour
    if letzte_abgeschlossene_stunde < 0:
        return {}

    results: dict = {}

    async with get_session() as db:
        anlagen_result = await db.execute(select(Anlage))
        anlagen = anlagen_result.scalars().all()

        for anlage in anlagen:
            try:
                zusammenfassung = await aggregate_day(
                    anlage, heute, db, datenquelle="scheduler",
                )
                results[anlage.id] = {
                    "status": "ok" if zusammenfassung else "keine_daten",
                    "datum": heute.isoformat(),
                    "bis_stunde": letzte_abgeschlossene_stunde,
                }
            except Exception as e:
                logger.debug(f"Anlage {anlage.id}: Heute-Aggregation: {type(e).__name__}: {e}")
                results[anlage.id] = {"status": "fehler", "error": str(e)}

    return results
