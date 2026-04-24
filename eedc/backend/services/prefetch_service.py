"""
Prefetch-Service für Solar- und Wetterprognosen.

Füllt den In-Memory-Cache proaktiv im Hintergrund, damit
Aussichten-Seiten und das Live-Wetter-Widget sofort bedient werden können.
Läuft alle 45 Minuten (innerhalb des 60-Min Cache-TTL).

Persistiert die heutige PV-Tagesprognose (+ Solcast) in TagesZusammenfassung,
damit der Lernfaktor unabhängig von Dashboard-Besuchen berechnet werden kann.
"""

import asyncio
import logging
import random
from datetime import date

import httpx
from sqlalchemy import select

from backend.core.config import settings
from backend.core.database import get_session
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.utils.investition_filter import aktiv_jetzt
from backend.models.pvgis_prognose import PVGISPrognose
from backend.services.solar_forecast_service import (
    get_solar_prognose,
    get_multi_string_prognose,
    PVStringConfig,
    DEFAULT_SYSTEM_LOSSES,
)
from backend.services.wetter.open_meteo import fetch_open_meteo_forecast
from backend.services.wetter.cache import _cache_get, _cache_set
from backend.services.wetter.models import WETTER_MODELLE

logger = logging.getLogger(__name__)

PREFETCH_JITTER_MAX = 60  # Ein Jitter pro Durchlauf, nicht pro Call


async def prefetch_all_prognosen(skip_jitter: bool = False) -> dict:
    """
    Scheduler-Job: Prefetcht Solar- und Wetterprognosen für alle Anlagen.

    Ein einzelner Random-Jitter am Anfang verteilt die Last auf Open-Meteo.
    Danach werden alle API-Calls ohne zusätzlichen Jitter ausgeführt.

    Args:
        skip_jitter: True beim Kaltstart-Prefetch (kein Wartezeit gewünscht).
    """
    if not skip_jitter:
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
            aktiv_jetzt(),
        )
    )
    alle_pv = inv_result.scalars().all()

    if not alle_pv:
        return {"status": "keine_pv"}

    # String-Konfigurationen erstellen
    from backend.services.pv_orientation import (
        get_pv_kwp, get_pv_neigung, get_pv_azimut,
    )
    strings = []
    for pv in alle_pv:
        kwp = get_pv_kwp(pv)
        if kwp <= 0:
            continue
        strings.append(PVStringConfig(
            name=pv.bezeichnung or f"String {pv.id}",
            kwp=kwp,
            neigung=get_pv_neigung(pv),
            ausrichtung=get_pv_azimut(pv),
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

    # Wetter-Forecast (für Aussichten kurzfristig) — mit Wettermodell der Anlage
    # days=7  → /aussichten/wetter/{id} (default)
    # days=14 → /aussichten/kurzfristig/{id} (default, Kurzfrist-Prognose)
    # days=16 → 14-Tage-Ansicht
    model_name, _ = WETTER_MODELLE.get(wetter_modell, (None, 16))
    coros.append(fetch_open_meteo_forecast(
        anlage.latitude, anlage.longitude, days=7, skip_jitter=True, model=model_name,
    ))
    coros.append(fetch_open_meteo_forecast(
        anlage.latitude, anlage.longitude, days=14, skip_jitter=True, model=model_name,
    ))
    coros.append(fetch_open_meteo_forecast(
        anlage.latitude, anlage.longitude, days=16, skip_jitter=True, model=model_name,
    ))

    # Live-Wetter (für WetterWidget auf Live-Seite)
    haupt_neigung = strings[0].neigung if strings else 35
    haupt_azimut = strings[0].ausrichtung if strings else 0
    hat_multi = len(unique_orientations) > 1
    coros.append(_prefetch_live_wetter(
        anlage.latitude, anlage.longitude,
        haupt_neigung, haupt_azimut, hat_multi,
        wetter_modell=wetter_modell,
    ))

    results = await asyncio.gather(*coros, return_exceptions=True)

    # ── Heutige PV-Prognose in DB persistieren (für Lernfaktor) ──
    # Erster Result ist die 7-Tage-Prognose (single oder multi)
    pv_heute_kwh = _extract_heute_kwh(results[0], has_multi)

    # Solcast parallel holen (wenn verfügbar)
    solcast_kwh = None
    solcast_p10 = None
    solcast_p90 = None
    try:
        from backend.services.solcast_service import get_solcast_forecast
        solcast = await get_solcast_forecast(anlage)
        if solcast:
            solcast_kwh = solcast.daily_kwh
            solcast_p10 = solcast.daily_p10_kwh
            solcast_p90 = solcast.daily_p90_kwh
    except Exception as e:
        logger.debug(f"Prefetch Solcast für Anlage {anlage.id}: {e}")

    if pv_heute_kwh is not None and pv_heute_kwh > 0:
        try:
            from backend.api.routes.live_wetter import _speichere_prognose
            await _speichere_prognose(
                anlage.id, date.today(), pv_heute_kwh,
                solcast_kwh=solcast_kwh,
                solcast_p10_kwh=solcast_p10,
                solcast_p90_kwh=solcast_p90,
            )
        except Exception as e:
            logger.warning(f"Prefetch Prognose-Persistierung Anlage {anlage.id}: {e}")

    return {"status": "ok", "strings": len(strings), "multi": has_multi}


def _extract_heute_kwh(result, is_multi: bool) -> float | None:
    """Extrahiert den heutigen PV-Ertrag (kWh) aus dem Prognose-Ergebnis."""
    if result is None or isinstance(result, Exception):
        return None

    heute = date.today().isoformat()

    if is_multi:
        # Multi-String: result ist ein dict mit "string_prognosen"
        if not isinstance(result, dict):
            return None
        total = 0.0
        for sp in result.get("string_prognosen", []):
            for tag in sp.get("tageswerte", []):
                if tag["datum"] == heute:
                    total += tag["pv_ertrag_kwh"]
                    break
        return round(total, 1) if total > 0 else None
    else:
        # Single-String: result ist SolarPrognoseResponse
        for tag in getattr(result, "tageswerte", []):
            if tag.datum == heute:
                return round(tag.pv_ertrag_kwh, 1)
        return None


async def _prefetch_live_wetter(
    latitude: float, longitude: float,
    neigung: int, azimut: int, hat_multi: bool,
    wetter_modell: str = "auto",
) -> None:
    """
    Prefetcht Live-Wetter-Daten (gleicher Cache-Key wie der Endpoint).

    Füllt den Cache mit den gleichen Parametern wie /api/live/{id}/wetter,
    damit der erste Seitenaufruf sofort bedient werden kann.
    """
    LIVE_WETTER_CACHE_TTL = 3600  # 60 Minuten (wie im Endpoint)
    # Cache-Key muss exakt mit live_wetter.py übereinstimmen (inkl. :m= Suffix)
    cache_key = (
        f"live_wetter:{latitude:.2f}:{longitude:.2f}"
        f":{neigung}:{azimut}:multi={hat_multi}:m={wetter_modell}"
    )

    # Nur holen wenn nicht bereits im Cache
    if _cache_get(cache_key) is not None:
        return

    hourly_vars = [
        "temperature_2m", "weather_code", "cloud_cover",
        "precipitation", "shortwave_radiation",
    ]
    if not hat_multi:
        hourly_vars.append("global_tilted_irradiance")

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": ",".join(hourly_vars),
        "daily": "sunshine_duration,temperature_2m_max,temperature_2m_min,sunrise,sunset",
        "timezone": "Europe/Berlin",
        "forecast_days": 1,
    }
    if not hat_multi:
        params["tilt"] = neigung
        params["azimuth"] = azimut

    # Wettermodell ergänzen (None = best_match = Parameter weglassen)
    model_name, _ = WETTER_MODELLE.get(wetter_modell, (None, 16))
    if model_name:
        params["models"] = model_name

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                f"{settings.open_meteo_api_url}/forecast", params=params
            )
            resp.raise_for_status()
            data = resp.json()

        _cache_set(cache_key, (data, None), LIVE_WETTER_CACHE_TTL)
        logger.debug(f"Live-Wetter Prefetch: {latitude:.2f}/{longitude:.2f}")
    except Exception as e:
        logger.debug(f"Live-Wetter Prefetch fehlgeschlagen: {e}")
