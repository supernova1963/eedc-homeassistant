"""
Prefetch-Service für Solar- und Wetterprognosen.

Füllt den In-Memory-Cache proaktiv im Hintergrund, damit
Aussichten-Seiten sofort bedient werden können.
Läuft alle 45 Minuten (innerhalb des 60-Min Cache-TTL).
"""

import asyncio
import logging
import random

from sqlalchemy import select

from backend.core.database import get_session
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.solar_forecast_service import (
    get_solar_prognose,
    get_multi_string_prognose,
    PVStringConfig,
    DEFAULT_SYSTEM_LOSSES,
)
from backend.services.wetter_service import fetch_open_meteo_forecast

logger = logging.getLogger(__name__)

PREFETCH_JITTER_MAX = 60  # Ein Jitter pro Durchlauf, nicht pro Call


async def prefetch_all_prognosen() -> dict:
    """
    Scheduler-Job: Prefetcht Solar- und Wetterprognosen für alle Anlagen.

    Ein einzelner Random-Jitter am Anfang verteilt die Last auf Open-Meteo.
    Danach werden alle API-Calls ohne zusätzlichen Jitter ausgeführt.
    """
    await asyncio.sleep(random.uniform(5, PREFETCH_JITTER_MAX))

    results = {}
    async with get_session() as db:
        anlagen_result = await db.execute(
            select(Anlage).where(
                Anlage.latitude.isnot(None),
                Anlage.longitude.isnot(None),
            )
        )
        anlagen = anlagen_result.scalars().all()

        for anlage in anlagen:
            try:
                result = await _prefetch_for_anlage(anlage, db)
                results[anlage.id] = result
            except Exception as e:
                logger.warning(f"Prefetch Anlage {anlage.id}: {type(e).__name__}: {e}")
                results[anlage.id] = {"status": "fehler", "error": str(e)}

    ok = sum(1 for r in results.values() if r.get("status") == "ok")
    logger.info(f"Prognose-Prefetch: {ok}/{len(results)} Anlagen erfolgreich")
    return results


async def _prefetch_for_anlage(anlage: Anlage, db) -> dict:
    """Prefetcht Solar-Prognose und Wetter-Forecast für eine Anlage."""
    wetter_modell = anlage.wetter_modell or "auto"

    # PV-Module + Balkonkraftwerke laden
    inv_result = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage.id,
            Investition.typ.in_(["pv-module", "balkonkraftwerk"]),
            Investition.aktiv == True,
        )
    )
    alle_pv = inv_result.scalars().all()

    if not alle_pv:
        return {"status": "keine_pv"}

    # String-Konfigurationen erstellen
    strings = []
    for pv in alle_pv:
        kwp = pv.leistung_kwp or 0
        if kwp <= 0:
            continue
        params = pv.parameter or {}
        neigung = params.get("neigung_grad") or params.get("neigung", 35)
        ausrichtung = params.get("ausrichtung_grad") or params.get("ausrichtung", 0)
        if isinstance(ausrichtung, str):
            ausrichtung_map = {
                "sued": 0, "süd": 0, "s": 0,
                "ost": -90, "o": -90, "e": -90,
                "west": 90, "w": 90,
                "nord": 180, "n": 180,
                "suedost": -45, "südost": -45, "so": -45,
                "suedwest": 45, "südwest": 45, "sw": 45,
            }
            ausrichtung = ausrichtung_map.get(ausrichtung.lower(), 0)
        strings.append(PVStringConfig(
            name=pv.bezeichnung or f"String {pv.id}",
            kwp=kwp, neigung=int(neigung), ausrichtung=int(ausrichtung),
        ))

    if not strings:
        return {"status": "keine_strings"}

    # System-Verluste aus PVGIS
    pvgis_result = await db.execute(
        select(PVGISPrognose).where(
            PVGISPrognose.anlage_id == anlage.id,
            PVGISPrognose.ist_aktiv == True,
        ).order_by(PVGISPrognose.abgerufen_am.desc()).limit(1)
    )
    pvgis = pvgis_result.scalar_one_or_none()
    system_losses = (
        pvgis.system_losses / 100 if pvgis and pvgis.system_losses
        else DEFAULT_SYSTEM_LOSSES
    )

    # Alle Prefetch-Calls parallel starten (skip_jitter=True)
    unique_orientations = set((s.neigung, s.ausrichtung) for s in strings)
    has_multi = len(unique_orientations) > 1

    coros = []

    if has_multi:
        for tage in (7, 14):
            coros.append(get_multi_string_prognose(
                anlage.latitude, anlage.longitude, strings,
                days=tage, system_losses=system_losses,
                wetter_modell=wetter_modell, skip_jitter=True,
            ))
    else:
        total_kwp = sum(s.kwp for s in strings)
        for tage in (7, 14):
            coros.append(get_solar_prognose(
                anlage.latitude, anlage.longitude, total_kwp,
                strings[0].neigung, strings[0].ausrichtung,
                days=tage, system_losses=system_losses,
                wetter_modell=wetter_modell, skip_jitter=True,
            ))

    # Wetter-Forecast (für Aussichten kurzfristig)
    coros.append(fetch_open_meteo_forecast(
        anlage.latitude, anlage.longitude, days=7, skip_jitter=True,
    ))
    coros.append(fetch_open_meteo_forecast(
        anlage.latitude, anlage.longitude, days=16, skip_jitter=True,
    ))

    await asyncio.gather(*coros, return_exceptions=True)

    return {"status": "ok", "strings": len(strings), "multi": has_multi}
