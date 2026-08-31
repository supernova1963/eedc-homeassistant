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

from backend.core.berechnungen.slot_konvention import (
    backward_slot_aus_period_end,
    backward_slot_aus_period_start,
)
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
class TagesStundenprofil:
    """24 Backward-Slots (kWh) eines einzelnen Prognosetags, inkl. p10/p90-Band."""
    datum: date
    p50: list[float] = field(default_factory=lambda: [0.0] * 24)
    p10: list[float] = field(default_factory=lambda: [0.0] * 24)
    p90: list[float] = field(default_factory=lambda: [0.0] * 24)

    def hat_werte(self) -> bool:
        return any(v for v in self.p50)


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
    # Stundenprofile je Prognosetag, Schlüssel ist das ISO-Datum (#357).
    # ``hourly_kw`` ist die Heute-Sicht daraus und bleibt der Bestandsweg.
    #
    # Bis v4.0.8 kannte diese Struktur **nur** heute: der HA-Pfad las das
    # ``detailedForecast``-Attribut ausschließlich vom Heute-Sensor, der
    # API-Pfad verwarf alle Buckets mit ``slot_date != heute``. Wer einen
    # anderen Tag brauchte, bekam das Profil von heute als Näherung
    # (Kennzeichnung über ``hinweise``, ADR-002/P4). Belegt hat rapahl in
    # #357, dass die HA-Integration je Tages-Sensor ein eigenes Attribut
    # führt; die API liefert ohnehin 168 h. Gefüllt wird deshalb **datenge-
    # trieben**: jeder Tag, für den die Quelle Slots liefert, bekommt hier
    # einen Eintrag — kein Sonderfall „morgen", keine Annahme über Tag 3–7.
    stundenprofile: dict[str, TagesStundenprofil] = field(default_factory=dict)
    quelle: str = "solcast_api"   # "solcast_api" | "solcast_ha"

    def profil_fuer(self, datum: date) -> Optional[TagesStundenprofil]:
        """Eigenes Stundenprofil dieses Tages — ``None``, wenn die Quelle für
        den Tag nur eine Tagesmenge kennt (dann bleibt die Näherung samt
        Kennzeichnung, sie wird nicht stillschweigend ersetzt)."""
        profil = self.stundenprofile.get(datum.isoformat())
        return profil if profil is not None and profil.hat_werte() else None


def _runde_profile(profile: dict[str, TagesStundenprofil]) -> None:
    """Rundet alle Slots auf 2 NK — dieselbe Stelle wie bisher ``hourly_kw``,
    damit Heute-Sicht und Tagesprofil bitgleich bleiben."""
    for profil in profile.values():
        profil.p50 = [round(v, 2) for v in profil.p50]
        profil.p10 = [round(v, 2) for v in profil.p10]
        profil.p90 = [round(v, 2) for v in profil.p90]


# ── Dispatcher ─────────────────────────────────────────────────────────────────

async def get_solcast_forecast(anlage) -> Optional[SolcastForecast]:
    """
    Holt Solcast-Prognose je nach Konfiguration (API oder HA-Sensor).

    Reihenfolge:
    1. Explizite solcast_config vorhanden → Modus daraus (api / ha_auto)
    2. Keine Config, aber HA verfügbar → Auto-Discovery der Solcast-Integration
    3. Sonst → None

    Returns:
        SolcastForecast oder None wenn nicht konfiguriert/nicht verfügbar.
        Fehlerstatus über get_solcast_status() abrufbar.
    """
    cfg = (anlage.sensor_mapping or {}).get("solcast_config")

    if cfg:
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

    # Keine explizite Config → per Auto-Discovery in HA versuchen.
    #
    # N-156/F-26: früher stand hier ein Gate auf `HA_INTEGRATION_AVAILABLE`
    # (= SUPERVISOR_TOKEN). `_fetch_solcast_ha_auto` prüft `is_available` in
    # seiner ersten Zeile selbst und liefert ohne HA `None` — das Gate war
    # also nie nötig, sperrte aber jeden per Long-Lived-Token angebundenen
    # Standalone-Betrieb von der Auto-Erkennung aus.
    return await _fetch_solcast_ha_auto()


def get_solcast_status(anlage) -> tuple[str, str]:
    """
    Ermittelt Solcast-Status + benutzerfreundlichen Hinweistext.

    Returns:
        (status, hinweis) — status: "ok"|"nicht_konfiguriert"|"tageslimit"|...
    """
    cfg = (anlage.sensor_mapping or {}).get("solcast_config")

    if not cfg:
        # Keine explizite Config → per Auto-Discovery in HA verfügbar?
        # N-156: dieselbe Frage wie im Abruf oben, also auch dieselbe Antwort —
        # nicht „läuft das im Add-on?", sondern „ist HA erreichbar?".
        from backend.services.ha_state_service import get_ha_state_service
        if get_ha_state_service().is_available:
            cached = _cache_get("solcast_ha:auto")
            if cached is not None:
                return ("ok", "Solcast HA-Integration automatisch erkannt.")
            return ("ok", "Solcast HA-Integration wird beim nächsten Abruf geprüft.")
        return ("nicht_konfiguriert",
                "Solcast nicht eingerichtet. Für eine satellitenbasierte PV-Prognose "
                "kannst du einen kostenlosen Solcast-Account anlegen (solcast.com, 10 Abrufe/Tag) "
                "und den API-Key in den Anlagen-Einstellungen eintragen.")

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

    # Stundenwerte je Prognosetag aggregieren (über alle Resources, #357).
    # Der Abruf holt ohnehin 168 h; bis v4.0.8 landeten davon nur die
    # Heute-Slots in der Antwort, der Rest wurde verworfen.
    profile: dict[str, TagesStundenprofil] = {}
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

                    # Backward-Konvention (Issue #144): Slot N = Energie [N-1, N).
                    # Solcast-API liefert Buckets mit period_end; die Abbildung
                    # auf den Backward-Slot ist zentral in core/berechnungen/
                    # slot_konvention.py gekapselt (Symmetrie zu OpenMeteo/IST).
                    # Am Tagesübergang (period_end=23:30) wandert der Bucket
                    # korrekt in Slot 0 des Folgetags.
                    slot_date, slot_hour = backward_slot_aus_period_end(period_end)
                    datum_str = slot_date.isoformat()

                    # Stundenwerte je Tag aggregieren (kW × 0.5h = kWh)
                    profil = profile.get(datum_str)
                    if profil is None:
                        profil = TagesStundenprofil(datum=slot_date)
                        profile[datum_str] = profil
                    profil.p50[slot_hour] += pv_p50 * period_hours
                    profil.p10[slot_hour] += pv_p10 * period_hours
                    profil.p90[slot_hour] += pv_p90 * period_hours

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

    _runde_profile(profile)
    heute_profil = profile.get(heute_str)

    result = SolcastForecast(
        daily_kwh=round(heute_daten["kwh"], 1),
        daily_p10_kwh=round(heute_daten["p10"], 1),
        daily_p90_kwh=round(heute_daten["p90"], 1),
        tomorrow_kwh=round(morgen_daten["kwh"], 1),
        tomorrow_p10_kwh=round(morgen_daten["p10"], 1),
        tomorrow_p90_kwh=round(morgen_daten["p90"], 1),
        hourly_kw=list(heute_profil.p50) if heute_profil else [0.0] * 24,
        hourly_p10_kw=list(heute_profil.p10) if heute_profil else [0.0] * 24,
        hourly_p90_kw=list(heute_profil.p90) if heute_profil else [0.0] * 24,
        tage_voraus=tage_voraus,
        stundenprofile=profile,
        quelle="solcast_api",
    )

    _cache_set(cache_key, result, ttl)
    logger.info(
        f"Solcast API: Heute={result.daily_kwh} kWh, "
        f"Morgen={result.tomorrow_kwh} kWh ({len(resource_ids)} Resources)"
    )
    return result


# ── HA-Sensor-Pfad (Auto-Discovery) ────────────────────────────────────────────

# BJReplay Solcast HA-Integration.
#
# ⛔ Diese Suffix-Liste war bis zum 31.08.2026 der EINZIGE Weg, und der Satz
# darüber („über alle Sprachen stabil") war falsch: sie deckt Deutsch und
# Englisch ab und sonst nichts, und sie bricht ohnehin, sobald HA der Entity-ID
# etwas ANHÄNGT (Bereich/Gerät/Entität in wählbarer Reihenfolge). Sie ist heute
# der **letzte Rückfall** der Kaskade in `services/ha_integration_aufloeser.py`;
# davor stehen `integration_entities()` (Menge) und die `unique_id` (Rolle).
# Nicht gelöscht — wessen Sensoren heute gefunden werden, merkt nichts.
_SOLCAST_SUFFIX_MAP = {
    "_heute": "heute",
    "_today": "heute",
    "_morgen": "morgen",
    "_tomorrow": "morgen",
    "_tag_3": "tag_3",
    "_day_3": "tag_3",
    "_ubermorgen": "tag_3",
    "_uebermorgen": "tag_3",
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

# unique_id-Kern → derselbe logische Schlüssel. Am 31.08.2026 an einer echten
# Solcast-Installation GEMESSEN: die Integration vergibt die unique_id **ohne**
# Config-Entry-Präfix (`total_kwh_forecast_today`), anders als SFML. Sie ist
# sprachunabhängig und übersteht jede Umbenennung.
_SOLCAST_UNIQUE_KERNE: dict[str, str] = {
    "total_kwh_forecast_today": "heute",
    "total_kwh_forecast_tomorrow": "morgen",
    "total_kwh_forecast_d3": "tag_3",
    "total_kwh_forecast_d4": "tag_4",
    "total_kwh_forecast_d5": "tag_5",
    "total_kwh_forecast_d6": "tag_6",
    "total_kwh_forecast_d7": "tag_7",
}

# Normalisierter Anzeigename → Schlüssel. Zweiter Rückfall, falls die
# Entity-Registry nicht lesbar ist.
_SOLCAST_NAMENS_KERNE: dict[str, str] = {
    "prognose_heute": "heute", "forecast_today": "heute",
    "prognose_morgen": "morgen", "forecast_tomorrow": "morgen",
    "prognose_tag_3": "tag_3", "forecast_day_3": "tag_3",
    "prognose_tag_4": "tag_4", "forecast_day_4": "tag_4",
    "prognose_tag_5": "tag_5", "forecast_day_5": "tag_5",
    "prognose_tag_6": "tag_6", "forecast_day_6": "tag_6",
    "prognose_tag_7": "tag_7", "forecast_day_7": "tag_7",
}

# Cache für aufgelöste Entity-IDs (überlebt Server-Neustart nicht, aber das ist ok)
_resolved_entities: dict[str, str] = {}
_resolved_ts: float = 0.0
_RESOLVE_TTL = 3600  # 1 Stunde — Entity-IDs ändern sich quasi nie


async def _resolve_solcast_entities() -> dict[str, str]:
    """
    Findet die Solcast-Tages-Entities — über die Integration, nicht über Namen.

    Kaskade (SoT: ``services/ha_integration_aufloeser.py``):
    ``integration_entities('solcast_solar')`` für die **Menge**, die
    ``unique_id`` aus der Entity-Registry für die **Rolle**, danach der
    Anzeigename und zuletzt das alte Suffix-Muster.

    ⛔ **Der Docstring behauptete bis zum 31.08.2026 das Gegenteil** — er nannte
    das Verfahren „robust gegenüber HA-Spracheinstellungen" und ausdrücklich
    „robust gegenüber unique_id-Änderungen in HA", und beides trug nicht: Die
    Suffix-Liste kennt genau zwei Sprachen, und die ``unique_id`` ist gerade die
    Größe, die sich **nicht** ändert, wenn jemand seine Entität umbenennt oder
    HA das ID-Format umstellt. Die Vermeidung war die teurere Wahl; sie ist
    hiermit umgedreht und die alte Erkennung als Rückfall behalten.

    ⚑ **Zweiter Turm aufgelöst:** Dies war die *zweite* eigene Solcast-Erkennung
    neben ``services/prognose_discovery.py``. Beide laufen jetzt über denselben
    Auflöser; unterschiedlich bleiben nur die logischen Schlüssel.

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

            # Vorfilter: nur Tages-Total-Kandidaten. Er bleibt stehen, weil die
            # LETZTE Stufe der Kaskade weiterhin am Entity-ID-Suffix matcht —
            # und dort endet `..._prognose_verbleibende_leistung_heute`
            # ebenfalls auf `_heute`. Ohne den Filter würde der Rest-Sensor als
            # Tages-Total durchgehen. Für die `unique_id`-Stufe ist er
            # überflüssig, aber harmlos: alle sieben Tageswerte tragen kWh.
            kandidaten = []
            for item in response.json():
                eid = item.get("entity_id", "")
                unit = (item.get("attributes") or {}).get("unit_of_measurement", "")
                if unit != "kWh":
                    continue
                if "verbleibend" in eid or "remaining" in eid:
                    continue
                kandidaten.append(item)

            from backend.services.ha_integration_aufloeser import loese_integration_auf

            aufl = await loese_integration_auf(
                domain="solcast_solar",
                praefixe=[_SOLCAST_PREFIX],
                unique_kerne=_SOLCAST_UNIQUE_KERNE,
                namens_kerne=_SOLCAST_NAMENS_KERNE,
                muster=sorted(
                    _SOLCAST_SUFFIX_MAP.items(), key=lambda x: -len(x[0])
                ),
                states=kandidaten,
            )
            resolved: dict[str, str] = {
                key: tr.entity_id for key, tr in aufl.treffer.items()
            }

            if resolved:
                _resolved_entities = resolved
                _resolved_ts = now
                logger.info(
                    f"Solcast Entity-IDs aufgelöst: {len(resolved)}/7 "
                    f"(Menge: {aufl.menge_quelle}, Rolle: {aufl.rolle_quelle}, "
                    f"z.B. heute={resolved.get('heute', '?')})"
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
    Stundenprofil + p10/p90 aus dem DetailedForecast-Attribut des Heute-Sensors.
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

        # Alle 7 Tages-Sensoren in einem Batch-Call lesen (inkl. Attribute)
        entity_ids = list(entity_map.values())
        wanted = set(entity_ids)
        ha_states: dict[str, dict] = {}  # entity_id → {"value": float, "attrs": dict}
        try:
            async with httpx.AsyncClient() as _client:
                _resp = await _client.get(
                    f"{ha_svc.api_url}/states",
                    headers={"Authorization": f"Bearer {ha_svc.token}"},
                    timeout=10.0,
                )
                if _resp.status_code == 200:
                    for item in _resp.json():
                        eid = item.get("entity_id", "")
                        if eid not in wanted:
                            continue
                        state_val = item.get("state")
                        if state_val in [None, "unknown", "unavailable", ""]:
                            continue
                        try:
                            ha_states[eid] = {
                                "value": float(state_val),
                                "attrs": item.get("attributes") or {},
                            }
                        except (ValueError, TypeError):
                            continue
        except Exception:
            pass

        # Heute prüfen
        heute_entity = entity_map["heute"]
        if heute_entity not in ha_states:
            logger.debug("Solcast HA: Heute-Sensor nicht verfügbar")
            return None

        today_kwh = ha_states[heute_entity]["value"]
        heute = date.today()

        # 7-Tage-Werte aus Sensor-States + estimate10/estimate90 Attribute
        tage_voraus = []
        for day_offset, key in enumerate(["heute", "morgen", "tag_3", "tag_4", "tag_5", "tag_6", "tag_7"]):
            entity = entity_map.get(key)
            if not entity:
                continue
            sensor = ha_states.get(entity)
            if sensor:
                datum = heute + timedelta(days=day_offset)
                attrs = sensor["attrs"]
                tage_voraus.append({
                    "datum": datum.isoformat(),
                    "kwh": round(sensor["value"], 1),
                    "p10": round(float(attrs.get("estimate10", 0) or 0), 1),
                    "p90": round(float(attrs.get("estimate90", 0) or 0), 1),
                })

        # detailedForecast je Tages-Sensor → ein Stundenprofil pro Tag (#357).
        # Bis v4.0.8 wurde nur das Attribut des HEUTE-Sensors gelesen; die
        # übrigen Sensoren liegen aus demselben Batch-Call längst in
        # `ha_states` (inkl. Attribute), es fehlte nur die Auswertung.
        # Jeder Sensor wird gegen SEIN Datum gefiltert (`slot_date == datum`) —
        # so wie vorher gegen `heute`. Das hält Rand-Slots (23:30 → Slot 0 des
        # Folgetags) beim Tag, dessen Sensor sie liefert, und verhindert, dass
        # zwei Sensoren denselben Slot doppelt füllen.
        profile: dict[str, TagesStundenprofil] = {}
        tz = ZoneInfo("Europe/Berlin")

        for day_offset, key in enumerate(["heute", "morgen", "tag_3", "tag_4", "tag_5", "tag_6", "tag_7"]):
            entity = entity_map.get(key)
            sensor = ha_states.get(entity) if entity else None
            if not sensor:
                continue
            attrs = sensor["attrs"]
            detailed = (
                attrs.get("detailedForecast")
                or attrs.get("DetailedForecast")
                or attrs.get("detailedHourly")
                or attrs.get("detailed_hourly")
                or []
            )
            if not detailed:
                continue

            datum = heute + timedelta(days=day_offset)
            profil = TagesStundenprofil(datum=datum)

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

                # Backward-Konvention (Issue #144): Slot N = Energie [N-1, N).
                # HA-Sensor liefert periodenbeginnende 30-Min-Buckets (period_start,
                # nicht period_end wie die API). Die Abbildung auf den Backward-Slot
                # ist zentral in core/berechnungen/slot_konvention.py gekapselt.
                slot_date, slot_hour = backward_slot_aus_period_start(dt)

                if slot_date == datum:
                    profil.p50[slot_hour] += pv_p50 * 0.5
                    profil.p10[slot_hour] += pv_p10 * 0.5
                    profil.p90[slot_hour] += pv_p90 * 0.5

            if profil.hat_werte():
                profile[datum.isoformat()] = profil

        _runde_profile(profile)
        heute_profil = profile.get(heute.isoformat())
        hourly_p50 = list(heute_profil.p50) if heute_profil else [0.0] * 24
        hourly_p10 = list(heute_profil.p10) if heute_profil else [0.0] * 24
        hourly_p90 = list(heute_profil.p90) if heute_profil else [0.0] * 24

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
            stundenprofile=profile,
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

    Für Solcast: DetailedForecast (oder detailedHourly) mit 30-Min-Auflösung.
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
