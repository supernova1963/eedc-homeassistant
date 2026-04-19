"""
Solcast PV Forecast Service.

Unterstützt 3 Modi:
1. API-Zugang (Free-Tier): 10 Calls/Tag, Cache 2h
2. API-Zugang (Paid): Viele Calls, Cache 30min
3. HA-Sensor: Liest Solcast HA-Integration, Cache 5min

Config in sensor_mapping.solcast_config:
  {"modus": "api", "api_key": "xxx", "resource_ids": [...], "tier": "free"}
  {"modus": "ha_sensor", "ha_sensor": {"today_kwh": "sensor...", "tomorrow_kwh": "sensor..."}}
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

from backend.core.config import settings
from backend.services.wetter.cache import (
    _cache_get, _cache_set, _error_cache_check, _error_cache_set,
    ERROR_TTL_RATE_LIMIT, ERROR_TTL_SERVER_ERROR, ERROR_TTL_NETWORK,
)

logger = logging.getLogger(__name__)

# ── Cache-TTLs (tier-abhängig) ─────────────────────────────────────────────────
# Nutzt das bestehende L1/L2-System (RAM + SQLite-Persistenz).
# Solcast-Daten überleben Server-Neustarts — kritisch für Free-Tier (10 Calls/Tag).

CACHE_TTL_FREE = 7200      # 2 Stunden (10 Calls/Tag)
CACHE_TTL_PAID = 1800      # 30 Minuten
CACHE_TTL_HA_SENSOR = 300  # 5 Minuten


# ── Datenstruktur ──────────────────────────────────────────────────────────────

@dataclass
class SolcastForecast:
    """Gemeinsame Datenstruktur für alle 3 Solcast-Fälle."""
    daily_kwh: float              # p50 heute
    daily_p10_kwh: float
    daily_p90_kwh: float
    tomorrow_kwh: float
    tomorrow_p10_kwh: float
    tomorrow_p90_kwh: float
    hourly_kw: list[float] = field(default_factory=list)        # 24 Werte (p50)
    hourly_p10_kw: list[float] = field(default_factory=list)
    hourly_p90_kw: list[float] = field(default_factory=list)
    tage_voraus: list[dict] = field(default_factory=list)       # [{datum, kwh, p10, p90}]
    quelle: str = "solcast_api"   # "solcast_api" | "solcast_ha"


# ── Dispatcher ─────────────────────────────────────────────────────────────────

async def get_solcast_forecast(anlage) -> Optional[SolcastForecast]:
    """
    Holt Solcast-Prognose je nach Konfiguration (API oder HA-Sensor).

    Returns:
        SolcastForecast oder None wenn nicht konfiguriert/nicht verfügbar.
        Fehlerstatus über get_solcast_status() abrufbar.
    """
    cfg = (anlage.sensor_mapping or {}).get("solcast_config")
    if not cfg:
        return None

    modus = cfg.get("modus")
    if modus == "api":
        return await _fetch_solcast_api(
            cfg.get("api_key", ""),
            cfg.get("resource_ids", []),
            cfg.get("tier", "free"),
        )
    elif modus == "ha_sensor":
        return await _fetch_solcast_ha_sensor(cfg.get("ha_sensor", {}))
    else:
        logger.warning(f"Unbekannter Solcast-Modus: {modus}")
        return None


def get_solcast_status(anlage) -> tuple[str, str]:
    """
    Ermittelt Solcast-Status + benutzerfreundlichen Hinweistext.

    Returns:
        (status, hinweis) — status: "ok"|"nicht_konfiguriert"|"tageslimit"|...
    """
    cfg = (anlage.sensor_mapping or {}).get("solcast_config")
    if not cfg:
        return ("nicht_konfiguriert",
                "Solcast nicht eingerichtet. Für eine satellitenbasierte PV-Prognose "
                "kannst du einen kostenlosen Solcast-Account anlegen (solcast.com, 10 Abrufe/Tag) "
                "und den API-Key im Sensor-Mapping eintragen. Alternativ die Solcast HA-Integration nutzen.")

    modus = cfg.get("modus", "")

    if modus == "api":
        api_key = cfg.get("api_key", "")
        resource_ids = cfg.get("resource_ids", [])
        if not api_key:
            return ("auth_fehler", "Solcast API-Key fehlt im Sensor-Mapping. "
                    "Trage deinen Key unter solcast_config.api_key ein.")
        if not resource_ids:
            return ("auth_fehler", "Keine Solcast Resource-IDs konfiguriert. "
                    "Trage mindestens eine Resource-ID (Rooftop Site) ein. "
                    "Diese findest du unter solcast.com → My Sites.")

        # Prüfe Error-Cache (429 = Tageslimit)
        rid_str = ",".join(sorted(r["id"] for r in resource_ids))
        cache_key = f"solcast_api:{rid_str}"
        if _error_cache_check(cache_key):
            tier = cfg.get("tier", "free")
            return ("tageslimit",
                    f"Solcast-Tageslimit erreicht (Free: 10 Abrufe/Tag). "
                    f"Daten werden aus dem Cache geladen falls verfügbar. "
                    f"{'Nächster Abruf morgen früh.' if tier == 'free' else 'Erneuter Versuch in wenigen Minuten.'}")

        # Prüfe ob Daten im Cache sind
        cached = _cache_get(cache_key)
        if cached is not None:
            return ("ok", "")
        return ("ok", "")  # Kein Fehler bekannt, wird beim nächsten Abruf geladen

    elif modus == "ha_sensor":
        ha_cfg = cfg.get("ha_sensor", {})
        if not ha_cfg.get("today_kwh"):
            return ("ha_nicht_erreichbar",
                    "Solcast HA-Sensor nicht konfiguriert. "
                    "Trage den Entity-Name des Solcast-Prognose-Sensors ein "
                    "(z.B. sensor.solcast_pv_forecast_prognose_heute).")
        from backend.core.config import settings as app_settings
        if not app_settings.supervisor_token:
            return ("ha_nicht_erreichbar",
                    "HA-Supervisor nicht erreichbar (Standalone-Modus). "
                    "Die HA-Sensor-Variante funktioniert nur im HA-Add-on. "
                    "Für Standalone nutze den API-Modus mit einem eigenen Solcast-Key.")
        return ("ok", "")

    return ("fehler", f"Unbekannter Solcast-Modus: '{modus}'. Erlaubt: 'api' oder 'ha_sensor'.")


# ── API-Pfad ───────────────────────────────────────────────────────────────────

async def _fetch_solcast_api(
    api_key: str,
    resource_ids: list[dict],
    tier: str = "free",
) -> Optional[SolcastForecast]:
    """
    Holt Forecast direkt von der Solcast REST-API.

    Aggregiert über alle resource_ids (für Ost/West-Anlagen).
    Cache-Key basiert auf resource_id-Hash.
    """
    if not api_key or not resource_ids:
        return None

    # Cache-Key: Hash über sortierte Resource-IDs
    rid_str = ",".join(sorted(r["id"] for r in resource_ids))
    cache_key = f"solcast_api:{rid_str}"

    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    if _error_cache_check(cache_key):
        logger.debug("Solcast API: Negative-Cache-Hit")
        return None

    ttl = CACHE_TTL_FREE if tier == "free" else CACHE_TTL_PAID
    tz = ZoneInfo("Europe/Berlin")
    heute = date.today()

    # Stundenwerte aggregieren (über alle Resources)
    hourly_p50 = [0.0] * 24
    hourly_p10 = [0.0] * 24
    hourly_p90 = [0.0] * 24
    # Tageswerte: {datum_str: {kwh, p10, p90}}
    tage_dict: dict[str, dict[str, float]] = {}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            for resource in resource_ids:
                rid = resource["id"]

                resp = await client.get(
                    f"{settings.solcast_api_url}/rooftop_sites/{rid}/forecasts",
                    params={"format": "json", "hours": 168},  # 7 Tage
                    headers={"Authorization": f"Bearer {api_key}"},
                )

                if resp.status_code == 429:
                    _error_cache_set(cache_key, ERROR_TTL_RATE_LIMIT)
                    logger.warning("Solcast API: Rate Limit erreicht (429)")
                    return None
                if resp.status_code >= 500:
                    _error_cache_set(cache_key, ERROR_TTL_SERVER_ERROR)
                    logger.warning(f"Solcast API: Server-Fehler ({resp.status_code})")
                    return None

                resp.raise_for_status()
                data = resp.json()

                for period in data.get("forecasts", []):
                    # period_end ist UTC ISO-String
                    period_end_str = period.get("period_end", "")
                    try:
                        period_end = datetime.fromisoformat(
                            period_end_str.replace("Z", "+00:00")
                        ).astimezone(tz)
                    except (ValueError, TypeError):
                        continue

                    pv_p50 = period.get("pv_estimate", 0) or 0
                    pv_p10 = period.get("pv_estimate10", 0) or 0
                    pv_p90 = period.get("pv_estimate90", 0) or 0
                    period_minutes = int(period.get("period", "PT30M").replace("PT", "").replace("M", "") or 30)
                    period_hours = period_minutes / 60

                    datum_str = period_end.strftime("%Y-%m-%d")
                    stunde = period_end.hour

                    # Stundenwerte für heute aggregieren (kW → kW, Durchschnitt pro Stunde)
                    if period_end.date() == heute:
                        hourly_p50[stunde] += pv_p50 * period_hours
                        hourly_p10[stunde] += pv_p10 * period_hours
                        hourly_p90[stunde] += pv_p90 * period_hours

                    # Tageswerte aggregieren (kW × h = kWh)
                    if datum_str not in tage_dict:
                        tage_dict[datum_str] = {"kwh": 0, "p10": 0, "p90": 0}
                    tage_dict[datum_str]["kwh"] += pv_p50 * period_hours
                    tage_dict[datum_str]["p10"] += pv_p10 * period_hours
                    tage_dict[datum_str]["p90"] += pv_p90 * period_hours

    except httpx.TimeoutException:
        _error_cache_set(cache_key, ERROR_TTL_NETWORK)
        logger.warning("Solcast API: Timeout")
        return None
    except Exception as e:
        _error_cache_set(cache_key, ERROR_TTL_NETWORK)
        logger.warning(f"Solcast API Fehler: {type(e).__name__}: {e}")
        return None

    # Ergebnis aufbereiten
    heute_str = heute.isoformat()
    morgen_str = (heute + timedelta(days=1)).isoformat()

    heute_daten = tage_dict.get(heute_str, {"kwh": 0, "p10": 0, "p90": 0})
    morgen_daten = tage_dict.get(morgen_str, {"kwh": 0, "p10": 0, "p90": 0})

    # 7-Tage-Liste
    tage_voraus = []
    for datum_str in sorted(tage_dict.keys()):
        d = tage_dict[datum_str]
        tage_voraus.append({
            "datum": datum_str,
            "kwh": round(d["kwh"], 1),
            "p10": round(d["p10"], 1),
            "p90": round(d["p90"], 1),
        })

    result = SolcastForecast(
        daily_kwh=round(heute_daten["kwh"], 1),
        daily_p10_kwh=round(heute_daten["p10"], 1),
        daily_p90_kwh=round(heute_daten["p90"], 1),
        tomorrow_kwh=round(morgen_daten["kwh"], 1),
        tomorrow_p10_kwh=round(morgen_daten["p10"], 1),
        tomorrow_p90_kwh=round(morgen_daten["p90"], 1),
        hourly_kw=[round(v, 2) for v in hourly_p50],
        hourly_p10_kw=[round(v, 2) for v in hourly_p10],
        hourly_p90_kw=[round(v, 2) for v in hourly_p90],
        tage_voraus=tage_voraus,
        quelle="solcast_api",
    )

    _cache_set(cache_key, result, ttl)
    logger.info(
        f"Solcast API: Heute={result.daily_kwh} kWh, "
        f"Morgen={result.tomorrow_kwh} kWh ({len(resource_ids)} Resources)"
    )
    return result


# ── HA-Sensor-Pfad ─────────────────────────────────────────────────────────────

async def _fetch_solcast_ha_sensor(
    ha_sensor_cfg: dict,
) -> Optional[SolcastForecast]:
    """
    Liest Solcast-Daten aus HA-Sensor-Attributen.

    Die HA Solcast-Integration (BJReplay) speichert detaillierte Stundenwerte
    als Attribut 'detailedHourly' am Hauptsensor.
    Einheit beachten: prognose_aktuelle_stunde in Wh (nicht kWh)!
    """
    today_entity = ha_sensor_cfg.get("today_kwh")
    tomorrow_entity = ha_sensor_cfg.get("tomorrow_kwh")

    if not today_entity:
        return None

    cache_key = f"solcast_ha:{today_entity}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        from backend.services.ha_state_service import get_ha_state_service
        ha_svc = get_ha_state_service()
        if not ha_svc.is_available:
            return None

        # State-Werte lesen (Tages-kWh)
        today_kwh = await ha_svc.get_sensor_state(today_entity)
        tomorrow_kwh = None
        if tomorrow_entity:
            tomorrow_kwh = await ha_svc.get_sensor_state(tomorrow_entity)

        if today_kwh is None:
            return None

        # Attribute lesen für Stundenprofil + p10/p90
        today_attrs = await _get_ha_sensor_attributes(today_entity)

        hourly_p50 = [0.0] * 24
        hourly_p10 = [0.0] * 24
        hourly_p90 = [0.0] * 24
        tage_voraus = []

        if today_attrs:
            # detailedHourly: Liste von {period_start, pv_estimate, pv_estimate10, pv_estimate90}
            detailed = today_attrs.get("detailedHourly") or today_attrs.get("detailed_hourly") or []
            tz = ZoneInfo("Europe/Berlin")
            heute = date.today()
            tage_dict: dict[str, dict[str, float]] = {}

            for entry in detailed:
                period_start = entry.get("period_start", "")
                try:
                    dt = datetime.fromisoformat(period_start.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=tz)
                    else:
                        dt = dt.astimezone(tz)
                except (ValueError, TypeError):
                    continue

                pv_p50 = entry.get("pv_estimate", 0) or 0
                pv_p10 = entry.get("pv_estimate10", 0) or 0
                pv_p90 = entry.get("pv_estimate90", 0) or 0

                datum_str = dt.strftime("%Y-%m-%d")
                stunde = dt.hour

                # Stundenwerte für heute (kW-Werte, 30-Min-Perioden → addieren)
                if dt.date() == heute:
                    hourly_p50[stunde] += pv_p50 * 0.5  # kW × 0.5h
                    hourly_p10[stunde] += pv_p10 * 0.5
                    hourly_p90[stunde] += pv_p90 * 0.5

                # Tageswerte
                if datum_str not in tage_dict:
                    tage_dict[datum_str] = {"kwh": 0, "p10": 0, "p90": 0}
                tage_dict[datum_str]["kwh"] += pv_p50 * 0.5
                tage_dict[datum_str]["p10"] += pv_p10 * 0.5
                tage_dict[datum_str]["p90"] += pv_p90 * 0.5

            for datum_str in sorted(tage_dict.keys()):
                d = tage_dict[datum_str]
                tage_voraus.append({
                    "datum": datum_str,
                    "kwh": round(d["kwh"], 1),
                    "p10": round(d["p10"], 1),
                    "p90": round(d["p90"], 1),
                })

        # p10/p90 aus Tage-Attributen (Fallback wenn kein detailedHourly)
        heute_str = date.today().isoformat()
        heute_tage = next((t for t in tage_voraus if t["datum"] == heute_str), None)

        result = SolcastForecast(
            daily_kwh=round(today_kwh, 1),
            daily_p10_kwh=round(heute_tage["p10"], 1) if heute_tage else 0,
            daily_p90_kwh=round(heute_tage["p90"], 1) if heute_tage else 0,
            tomorrow_kwh=round(tomorrow_kwh, 1) if tomorrow_kwh is not None else 0,
            tomorrow_p10_kwh=0,  # Nicht einzeln verfügbar über State
            tomorrow_p90_kwh=0,
            hourly_kw=[round(v, 2) for v in hourly_p50],
            hourly_p10_kw=[round(v, 2) for v in hourly_p10],
            hourly_p90_kw=[round(v, 2) for v in hourly_p90],
            tage_voraus=tage_voraus,
            quelle="solcast_ha",
        )

        # Morgen p10/p90 aus Tage-Dict nachziehen
        morgen_str = (date.today() + timedelta(days=1)).isoformat()
        morgen_tage = next((t for t in tage_voraus if t["datum"] == morgen_str), None)
        if morgen_tage:
            result.tomorrow_p10_kwh = morgen_tage["p10"]
            result.tomorrow_p90_kwh = morgen_tage["p90"]

        _cache_set(cache_key, result, CACHE_TTL_HA_SENSOR)
        logger.info(f"Solcast HA: Heute={result.daily_kwh} kWh, Morgen={result.tomorrow_kwh} kWh")
        return result

    except Exception as e:
        logger.warning(f"Solcast HA-Sensor Fehler: {type(e).__name__}: {e}")
        return None


async def _get_ha_sensor_attributes(entity_id: str) -> Optional[dict]:
    """
    Holt alle Attribute eines HA-Sensors (nicht nur State).

    Für Solcast: detailedHourly mit 30-Min-Auflösung.
    """
    if not settings.supervisor_token:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{settings.ha_api_url}/states/{entity_id}",
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
            )
            if resp.status_code != 200:
                return None
            return resp.json().get("attributes")
    except Exception as e:
        logger.debug(f"HA Attribute lesen fehlgeschlagen ({entity_id}): {e}")
        return None
