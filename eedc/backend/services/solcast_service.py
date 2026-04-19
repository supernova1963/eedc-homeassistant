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
    elif modus in ("ha_sensor", "ha_auto"):
        return await _fetch_solcast_ha_auto()
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

    elif modus in ("ha_sensor", "ha_auto"):
        from backend.core.config import settings as app_settings
        if not app_settings.supervisor_token:
            return ("ha_nicht_erreichbar",
                    "HA-Supervisor nicht erreichbar (Standalone-Modus). "
                    "Die HA-Integration funktioniert nur im HA-Add-on. "
                    "Für Standalone nutze den API-Modus mit einem eigenen Solcast-Key.")
        # Prüfe ob der Cache Daten hat (= letzter Abruf erfolgreich)
        cached = _cache_get("solcast_ha:auto")
        if cached is None:
            # Kein Cache → entweder erster Abruf oder Sensor nicht vorhanden
            return ("ok", "Solcast HA-Integration aktiviert. Daten werden beim nächsten Seitenaufruf geladen. "
                    "Falls nach dem Laden keine Solcast-Daten erscheinen: "
                    "Prüfe ob die Solcast HA-Integration (BJReplay) installiert und konfiguriert ist.")
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


# ── HA-Sensor-Pfad (Auto-Discovery) ────────────────────────────────────────────

# BJReplay Solcast HA-Integration: Auto-Discovery per Suffix-Pattern.
# Die Entity-IDs werden je nach HA-Sprache anders generiert
# (z.B. "prognose_heute" vs. "vorhersage_heute" vs. "forecast_today").
# Die Suffixe (_heute/_today, _morgen/_tomorrow, _tag_N/_day_N) sind
# über alle Sprachen stabil — darüber matchen wir.
_SOLCAST_SUFFIX_MAP = {
    "_heute": "heute",
    "_today": "heute",
    "_morgen": "morgen",
    "_tomorrow": "morgen",
    "_tag_3": "tag_3",
    "_day_3": "tag_3",
    "_tag_4": "tag_4",
    "_day_4": "tag_4",
    "_tag_5": "tag_5",
    "_day_5": "tag_5",
    "_tag_6": "tag_6",
    "_day_6": "tag_6",
    "_tag_7": "tag_7",
    "_day_7": "tag_7",
}

_SOLCAST_PREFIX = "sensor.solcast_pv_forecast_"

# Cache für aufgelöste Entity-IDs (überlebt Server-Neustart nicht, aber das ist ok)
_resolved_entities: dict[str, str] = {}
_resolved_ts: float = 0.0
_RESOLVE_TTL = 3600  # 1 Stunde — Entity-IDs ändern sich quasi nie


async def _resolve_solcast_entities() -> dict[str, str]:
    """
    Findet Solcast-Entities über /api/states + Suffix-Pattern.

    Sucht alle Entities mit Prefix 'sensor.solcast_pv_forecast_' und
    matcht deren Suffix gegen bekannte Tages-Patterns (_heute/_today,
    _morgen/_tomorrow, _tag_N/_day_N).

    Robust gegenüber:
    - HA-Spracheinstellungen (deutsch/englisch/etc.)
    - Umbenennungen durch BJReplay-Updates
    - unique_id-Änderungen in HA

    Returns:
        Dict logischer_name → entity_id, z.B. {"heute": "sensor.solcast_pv_forecast_prognose_heute"}
    """
    global _resolved_entities, _resolved_ts
    import time

    now = time.monotonic()
    if _resolved_entities and (now - _resolved_ts) < _RESOLVE_TTL:
        return _resolved_entities

    from backend.services.ha_state_service import get_ha_state_service
    ha_svc = get_ha_state_service()
    if not ha_svc.is_available:
        return {}

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{ha_svc.api_url}/states",
                headers={"Authorization": f"Bearer {ha_svc.token}"},
                timeout=10.0,
            )
            if response.status_code != 200:
                return {}

            resolved: dict[str, str] = {}
            for item in response.json():
                eid = item.get("entity_id", "")
                if not eid.startswith(_SOLCAST_PREFIX):
                    continue
                # Suffix matchen (längste zuerst um _tag_3 vor _3 zu priorisieren)
                for suffix, key in sorted(
                    _SOLCAST_SUFFIX_MAP.items(), key=lambda x: -len(x[0])
                ):
                    if eid.endswith(suffix) and key not in resolved:
                        resolved[key] = eid
                        break

            if resolved:
                _resolved_entities = resolved
                _resolved_ts = now
                logger.info(
                    f"Solcast Entity-IDs aufgelöst: {len(resolved)}/7 "
                    f"(z.B. heute={resolved.get('heute', '?')})"
                )

            return resolved

    except Exception as e:
        logger.warning(f"Solcast Discovery Fehler: {type(e).__name__}: {e}")
        return {}


async def _fetch_solcast_ha_auto() -> Optional[SolcastForecast]:
    """
    Liest Solcast-Daten aus der HA Solcast-Integration (BJReplay).

    Erkennt Sensoren automatisch über die Entity Registry (unique_id),
    unabhängig von der HA-Spracheinstellung.
    Tageswerte (Heute bis Tag 7) direkt aus Sensor-States.
    Stundenprofil + p10/p90 aus dem detailedHourly-Attribut des Heute-Sensors.
    """
    cache_key = "solcast_ha:auto"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    try:
        from backend.services.ha_state_service import get_ha_state_service
        ha_svc = get_ha_state_service()
        if not ha_svc.is_available:
            return None

        # Entity-IDs dynamisch auflösen (gecacht, 1h TTL)
        entity_map = await _resolve_solcast_entities()
        if not entity_map or "heute" not in entity_map:
            logger.debug("Solcast HA: Keine Solcast-Entities in der Entity Registry gefunden")
            return None

        # Alle 7 Tages-Sensoren in einem Batch-Call lesen
        entity_ids = list(entity_map.values())
        ha_batch = await ha_svc.get_sensor_states_batch(entity_ids)

        # Heute prüfen
        heute_entity = entity_map["heute"]
        if not ha_batch.get(heute_entity):
            logger.debug("Solcast HA: Heute-Sensor nicht verfügbar")
            return None

        today_kwh = ha_batch[heute_entity][0]
        heute = date.today()

        # 7-Tage-Werte aus Sensor-States
        tage_voraus = []
        for day_offset, key in enumerate(["heute", "morgen", "tag_3", "tag_4", "tag_5", "tag_6", "tag_7"]):
            entity = entity_map.get(key)
            if not entity:
                continue
            state = ha_batch.get(entity)
            if state:
                datum = heute + timedelta(days=day_offset)
                tage_voraus.append({
                    "datum": datum.isoformat(),
                    "kwh": round(state[0], 1),
                    "p10": 0,  # Wird aus detailedHourly nachgezogen
                    "p90": 0,
                })

        # detailedHourly-Attribut für Stundenprofil + p10/p90
        hourly_p50 = [0.0] * 24
        hourly_p10 = [0.0] * 24
        hourly_p90 = [0.0] * 24
        today_attrs = await _get_ha_sensor_attributes(heute_entity)

        if today_attrs:
            detailed = today_attrs.get("detailedHourly") or today_attrs.get("detailed_hourly") or []
            tz = ZoneInfo("Europe/Berlin")
            # p10/p90 pro Tag aggregieren
            tage_p_dict: dict[str, dict[str, float]] = {}

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

                # Stundenwerte für heute
                if dt.date() == heute:
                    hourly_p50[stunde] += pv_p50 * 0.5
                    hourly_p10[stunde] += pv_p10 * 0.5
                    hourly_p90[stunde] += pv_p90 * 0.5

                # p10/p90 pro Tag
                if datum_str not in tage_p_dict:
                    tage_p_dict[datum_str] = {"p10": 0, "p90": 0}
                tage_p_dict[datum_str]["p10"] += pv_p10 * 0.5
                tage_p_dict[datum_str]["p90"] += pv_p90 * 0.5

            # p10/p90 in tage_voraus nachziehen
            for tag in tage_voraus:
                p_data = tage_p_dict.get(tag["datum"])
                if p_data:
                    tag["p10"] = round(p_data["p10"], 1)
                    tag["p90"] = round(p_data["p90"], 1)

        # Morgen/Heute aus tage_voraus
        morgen_kwh = tage_voraus[1]["kwh"] if len(tage_voraus) > 1 else 0
        morgen_p10 = tage_voraus[1]["p10"] if len(tage_voraus) > 1 else 0
        morgen_p90 = tage_voraus[1]["p90"] if len(tage_voraus) > 1 else 0
        heute_p10 = tage_voraus[0]["p10"] if tage_voraus else 0
        heute_p90 = tage_voraus[0]["p90"] if tage_voraus else 0

        result = SolcastForecast(
            daily_kwh=round(today_kwh, 1),
            daily_p10_kwh=heute_p10,
            daily_p90_kwh=heute_p90,
            tomorrow_kwh=morgen_kwh,
            tomorrow_p10_kwh=morgen_p10,
            tomorrow_p90_kwh=morgen_p90,
            hourly_kw=[round(v, 2) for v in hourly_p50],
            hourly_p10_kw=[round(v, 2) for v in hourly_p10],
            hourly_p90_kw=[round(v, 2) for v in hourly_p90],
            tage_voraus=tage_voraus,
            quelle="solcast_ha",
        )

        _cache_set(cache_key, result, CACHE_TTL_HA_SENSOR)
        logger.info(
            f"Solcast HA: Heute={result.daily_kwh} kWh, "
            f"Morgen={result.tomorrow_kwh} kWh, "
            f"{len(tage_voraus)} Tage"
        )
        return result

    except Exception as e:
        logger.warning(f"Solcast HA Fehler: {type(e).__name__}: {e}")
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
