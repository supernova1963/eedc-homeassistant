"""
Geteilte Helper für das Energie-Profil-Subsystem.

Wetter-IST (Open-Meteo Historical/Forecast/Archive), SoC-History (HA-Sensor),
Strompreis-Stunden (HA-Sensor + aWATTar-Börsenpreis) und der `_tage_zurueck`-
Wrapper für `get_tagesverlauf`. Diese Funktionen werden lazy aus `aggregator.py`
und `backfill.py` importiert; sie haben keinen eigenen Schreib-Pfad.

Extrahiert aus `services/energie_profil_service.py` im 3d-Etappenabschluss-Tail
(2026-05-10). Verhalten unverändert.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.anlage import Anlage

logger = logging.getLogger(__name__)


def _tage_zurueck(datum: date) -> int:
    """Berechnet tage_zurueck Parameter für get_tagesverlauf()."""
    return (date.today() - datum).days


async def _get_wetter_ist(
    anlage: Anlage,
    datum: date,
    pv_module: Optional[list] = None,
) -> dict:
    """
    Holt Wetter-IST-Daten für einen Tag (Open-Meteo Historical).

    Zusätzlich zur horizontalen Globalstrahlung (GHI) wird — wenn PV-Module
    mit bekannter Neigung/Ausrichtung übergeben werden — die Global Tilted
    Irradiance (GTI) kWp-gewichtet über alle Orientierungsgruppen geholt.
    GTI ist die auf die Modul-Fläche projizierte Strahlung und die physikalisch
    korrekte Referenz für die Performance-Ratio-Berechnung (Issue #139).

    Args:
        anlage: Anlage-Objekt mit lat/lon
        datum: Zieltag
        pv_module: Liste von PV-Module-Investitionen (für GTI-Gruppierung).
            None/leer → nur GHI (PR bleibt dann None in der Aggregation).

    Returns:
        {stunde: {
            "temperatur_c": float,
            "globalstrahlung_wm2": float,   # horizontal, GHI
            "gti_wm2": float | None,        # modul-gewichtet, None wenn keine PV-Module
            "bewoelkung_prozent": float,    # cloud_cover 0-100
            "niederschlag_mm": float,       # precipitation in mm/h
            "wetter_code": int,             # WMO weather code
        }}
    """
    if not anlage.latitude or not anlage.longitude:
        return {}

    try:
        import asyncio
        import httpx
        from backend.core.config import settings
        from backend.api.routes.live_wetter import _get_pv_orientierungsgruppen

        gruppen = _get_pv_orientierungsgruppen(pv_module) if pv_module else []

        # Forecast-Endpoint für heute UND die letzten ARCHIVE_LAG_TAGE
        # (Open-Meteo Archive hängt 2-5 Tage hinter Echtzeit; Forecast-Endpoint
        # liefert für vergangene Tage stattdessen die Reanalyse-Approximation).
        # Archive nur für ältere Tage.
        from backend.services.wetter_backfill_service import archive_cutoff
        if datum == date.today():
            url = f"{settings.open_meteo_api_url}/forecast"
            base_params: dict = {"forecast_days": 1}
        elif datum >= archive_cutoff():
            url = f"{settings.open_meteo_api_url}/forecast"
            base_params = {
                "start_date": datum.isoformat(),
                "end_date": datum.isoformat(),
            }
        else:
            url = "https://archive-api.open-meteo.com/v1/archive"
            base_params = {
                "start_date": datum.isoformat(),
                "end_date": datum.isoformat(),
            }

        base_params.update({
            "latitude": anlage.latitude,
            "longitude": anlage.longitude,
            "timezone": "Europe/Berlin",
        })

        # Haupt-Request: Temperatur + GHI + Wetter (Bewölkung, Niederschlag, WMO-Code),
        # bei genau einer Gruppe auch GTI
        haupt_params = dict(base_params)
        hourly_vars = [
            "temperature_2m", "shortwave_radiation",
            "cloud_cover", "precipitation", "weather_code",
        ]
        if len(gruppen) == 1:
            hourly_vars.append("global_tilted_irradiance")
            haupt_params["tilt"] = gruppen[0]["neigung"]
            haupt_params["azimuth"] = gruppen[0]["ausrichtung"]
        haupt_params["hourly"] = ",".join(hourly_vars)

        multi_gti: Optional[list[float]] = None
        async with httpx.AsyncClient(timeout=15.0) as client:
            if len(gruppen) > 1:
                # Separate GTI-Calls pro Gruppe, parallel
                gti_tasks = [
                    client.get(url, params={
                        **base_params,
                        "hourly": "global_tilted_irradiance",
                        "tilt": g["neigung"],
                        "azimuth": g["ausrichtung"],
                    })
                    for g in gruppen
                ]
                haupt_resp, *gti_resps = await asyncio.gather(
                    client.get(url, params=haupt_params),
                    *gti_tasks,
                )
                # kWp-gewichtete Kombination
                kwp_gesamt = sum(g["kwp"] for g in gruppen)
                multi_gti = [0.0] * 24
                for gruppe, resp in zip(gruppen, gti_resps):
                    try:
                        resp.raise_for_status()
                        gti_vals = resp.json().get("hourly", {}).get("global_tilted_irradiance", [])
                    except Exception:
                        continue
                    if not gti_vals or kwp_gesamt <= 0:
                        continue
                    gewicht = gruppe["kwp"] / kwp_gesamt
                    for i in range(min(24, len(gti_vals))):
                        v = gti_vals[i]
                        if v is not None:
                            multi_gti[i] += v * gewicht
            else:
                haupt_resp = await client.get(url, params=haupt_params)

        haupt_resp.raise_for_status()
        data = haupt_resp.json()

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        temps = hourly.get("temperature_2m", [])
        ghi = hourly.get("shortwave_radiation", [])
        gti_single = hourly.get("global_tilted_irradiance", [])
        cloud_cover = hourly.get("cloud_cover", [])
        precip = hourly.get("precipitation", [])
        wcode = hourly.get("weather_code", [])

        gti_values = multi_gti if multi_gti is not None else gti_single

        result = {}
        for i, t in enumerate(times):
            h = int(t[11:13])
            result[h] = {
                "temperatur_c": temps[i] if i < len(temps) else None,
                "globalstrahlung_wm2": ghi[i] if i < len(ghi) else None,
                "gti_wm2": gti_values[i] if i < len(gti_values) else None,
                "bewoelkung_prozent": cloud_cover[i] if i < len(cloud_cover) else None,
                "niederschlag_mm": precip[i] if i < len(precip) else None,
                "wetter_code": wcode[i] if i < len(wcode) else None,
            }

        return result

    except Exception as e:
        logger.debug(f"Wetter-IST für {datum}: {e}")
        return {}


async def _get_soc_history(
    anlage: Anlage,
    sensor_mapping: dict,
    datum: date,
    db: AsyncSession,
) -> dict:
    """
    Holt Batterie-SoC History für einen Tag — nur stationäre Speicher.

    E-Auto-SoC darf hier NICHT enthalten sein, sonst kontaminiert er die
    Batterie-Vollzyklen-Berechnung der PV-Anlage (E-Auto-ΔSoC ≠ Speicher-ΔSoC).

    Returns:
        {stunde: float (SoC %)}
    """
    from backend.core.config import HA_INTEGRATION_AVAILABLE
    from backend.models.investition import Investition

    if not HA_INTEGRATION_AVAILABLE:
        return {}

    # Speicher-IDs für diese Anlage holen, dann SoC-Entities filtern
    inv_result = await db.execute(
        select(Investition.id).where(
            Investition.anlage_id == anlage.id,
            Investition.typ == "speicher",
        )
    )
    speicher_ids = {str(row) for row in inv_result.scalars().all()}

    if not speicher_ids:
        return {}

    soc_entities = []
    for key, val in sensor_mapping.get("investitionen", {}).items():
        if str(key) not in speicher_ids:
            continue
        if isinstance(val, dict) and val.get("live", {}).get("soc"):
            soc_entities.append(val["live"]["soc"])

    if not soc_entities:
        return {}

    try:
        from backend.services.ha_state_service import get_ha_state_service
        ha_service = get_ha_state_service()

        start = datetime.combine(datum, datetime.min.time())
        end = start + timedelta(days=1)

        history = await ha_service.get_sensor_history(soc_entities, start, end)

        # Stundenmittel berechnen (erstes SoC-Entity verwenden)
        result = {}
        for entity_id in soc_entities:
            points = history.get(entity_id, [])
            if not points:
                continue

            for h in range(24):
                h_start = start + timedelta(hours=h)
                h_end = h_start + timedelta(hours=1)
                h_points = [p[1] for p in points if h_start <= p[0] < h_end]
                if h_points and h not in result:
                    result[h] = sum(h_points) / len(h_points)

            break  # Erstes SoC-Entity reicht

        return result

    except Exception as e:
        logger.debug(f"SoC-History für {datum}: {e}")
        return {}


@dataclass
class StrompreisStunden:
    """Stündliche Strompreise aus zwei unabhängigen Quellen."""
    sensor: dict[int, float]   # Endpreis aus HA-Sensor (Tibber etc.), leer wenn kein Sensor
    boerse: dict[int, float]   # EPEX Day-Ahead Börsenpreis (aWATTar), immer befüllt


async def _get_strompreis_stunden(
    anlage: Anlage,
    sensor_mapping: dict,
    datum: date,
) -> StrompreisStunden:
    """
    Holt stündliche Strompreise für einen Tag aus zwei Quellen.

    1. HA-Sensor (Endpreis, nur wenn konfiguriert) → strompreis_cent
    2. Börsenpreis (aWATTar API, immer) → boersenpreis_cent

    Returns:
        StrompreisStunden mit sensor- und boerse-Dicts
    """
    sensor_preise: dict[int, float] = {}
    boersen_preise: dict[int, float] = {}

    # ── HA-Sensor (Endpreis, wenn konfiguriert) ──────────────────────────
    basis = sensor_mapping.get("basis", {})
    sp = basis.get("strompreis")
    sensor_id = sp.get("sensor_id") if isinstance(sp, dict) else None

    if sensor_id:
        try:
            from backend.core.config import HA_INTEGRATION_AVAILABLE
            if HA_INTEGRATION_AVAILABLE:
                from backend.services.ha_state_service import get_ha_state_service
                ha_service = get_ha_state_service()

                start = datetime.combine(datum, datetime.min.time())
                end = start + timedelta(days=1)
                history = await ha_service.get_sensor_history([sensor_id], start, end)
                units = await ha_service.get_sensor_units([sensor_id])

                points = history.get(sensor_id, [])
                if points:
                    unit = units.get(sensor_id, "")
                    faktor = 1.0
                    if unit in ("EUR/kWh", "€/kWh"):
                        faktor = 100.0
                    elif unit in ("EUR/MWh", "€/MWh"):
                        faktor = 0.1

                    for h in range(24):
                        h_start = start + timedelta(hours=h)
                        h_end = h_start + timedelta(hours=1)
                        h_pts = [p[1] * faktor for p in points if h_start <= p[0] < h_end]
                        if h_pts:
                            sensor_preise[h] = sum(h_pts) / len(h_pts)

                    if sensor_preise:
                        logger.debug("Strompreis %s: %d Stunden aus HA-Sensor %s",
                                     datum, len(sensor_preise), sensor_id)
        except Exception as e:
            logger.debug("Strompreis HA-Sensor %s für %s: %s", sensor_id, datum, e)

    # ── Börsenpreis (aWATTar/EPEX, immer) ────────────────────────────────
    try:
        from backend.services.strompreis_markt_service import get_strompreis_stunden
        land = getattr(anlage, "standort_land", None)
        boersen_preise = await get_strompreis_stunden(land, datum)
        if boersen_preise:
            logger.debug("Börsenpreis %s: %d Stunden (%s)",
                         datum, len(boersen_preise), land or "DE")
    except Exception as e:
        logger.debug("Börsenpreis für %s: %s", datum, e)

    return StrompreisStunden(sensor=sensor_preise, boerse=boersen_preise)
