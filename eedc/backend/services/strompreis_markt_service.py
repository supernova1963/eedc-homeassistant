"""
Strompreis-Markt-Service — Öffentliche EPEX Day-Ahead Preise via aWATTar API.

Liefert stündliche Börsenpreise (EPEX Spot DE/AT) für:
  1. Tagesverlauf-Overlay als Fallback (wenn kein eigener Sensor konfiguriert)
  2. Stündliche Mitschrift ins TagesEnergieProfil

Datenquelle: aWATTar API (frei, kein Auth nötig)
  - DE: https://api.awattar.de/v1/marketdata
  - AT: https://api.awattar.at/v1/marketdata

Einheit intern: ct/kWh (aWATTar liefert EUR/MWh → ÷ 10)
Cache: 2h TTL (Day-Ahead Preise ändern sich nur 1× täglich um 13:00 CET)

⚠ **Ein Tag ist ein Tag der Marktzone, nicht der UTC-Tag** (F-6, 2026-08-06):
Bis dahin wurde das Abfragefenster in UTC gebildet, die zurückgelieferten
Stunden aber über die **lokale** Uhr zugeordnet. Beide Enden passten nicht
zueinander — in Mitteleuropa fehlten die Stunden 0 und 1 des angefragten Tages
(im Winter die Stunde 0), und an ihrer Stelle standen die Preise des
**Folgetages**. Das Ergebnis hatte 24 Einträge und sah damit vollständig aus.
In einem Container ohne ``TZ`` (Docker-Default UTC) war das Fenster stimmig,
die Schlüssel aber UTC-Stunden — gegen ``Europe/Berlin`` gehalten, wie es der
HA-Export tut, lagen sie zwei Stunden daneben.

Beide Enden laufen jetzt über ``_markt_tz()``: Fenster von lokaler Mitternacht
bis lokaler Mitternacht, Stundenschlüssel in derselben Zone. Die Prozesszone
spielt keine Rolle mehr.
"""

import logging
import time
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import httpx

logger = logging.getLogger(__name__)

# ── API ──────────────────────────────────────────────────────────────────

AWATTAR_URLS = {
    "DE": "https://api.awattar.de/v1/marketdata",
    "AT": "https://api.awattar.at/v1/marketdata",
}

# Zeitzone der Gebotszone. DE und AT teilen sich CET/CEST — die Unterscheidung
# ist trotzdem benannt, damit ein dritter Markt nicht stillschweigend Berlin erbt.
MARKT_TZ = {
    "DE": ZoneInfo("Europe/Berlin"),
    "AT": ZoneInfo("Europe/Vienna"),
}


def _markt_tz(markt: str) -> ZoneInfo:
    """Zeitzone der Gebotszone; unbekannte Märkte fallen auf Berlin zurück."""
    return MARKT_TZ.get(markt, MARKT_TZ["DE"])

# ── Cache (einfacher In-Memory-Cache, reicht für Day-Ahead) ─────────────

_cache: dict[str, tuple[float, dict[int, float]]] = {}
CACHE_TTL = 7200  # 2 Stunden

# ── Negative Cache ──────────────────────────────────────────────────────

_error_cache: dict[str, float] = {}
ERROR_TTL_RATE_LIMIT = 300
ERROR_TTL_SERVER_ERROR = 120
ERROR_TTL_NETWORK = 60


def _cache_key(markt: str, datum: date) -> str:
    return f"awattar:{markt}:{datum.isoformat()}"


async def fetch_marktpreise(
    datum: date,
    markt: str = "DE",
    timeout: float = 15.0,
) -> Optional[dict[int, float]]:
    """
    Holt EPEX Day-Ahead Preise für einen Tag.

    Args:
        datum: Tag für den Preise geholt werden
        markt: "DE" oder "AT"
        timeout: HTTP-Timeout

    Returns:
        dict {stunde: preis_ct_kwh} (0-23) oder None bei Fehler.
        Preise sind Netto-Börsenpreise (ohne Steuern/Netzentgelte/Aufschläge).
    """
    key = _cache_key(markt, datum)

    # Cache prüfen
    cached = _cache.get(key)
    if cached and cached[0] > time.monotonic():
        return cached[1]

    # Error-Cache prüfen
    err_expires = _error_cache.get(key)
    if err_expires and err_expires > time.monotonic():
        return None

    url = AWATTAR_URLS.get(markt)
    if not url:
        logger.warning("Strompreis-Markt: Unbekannter Markt '%s'", markt)
        return None

    # aWATTar erwartet Unix-Millisekunden. Das Fenster läuft von Mitternacht bis
    # Mitternacht **der Marktzone** (F-6) — ein UTC-Fenster schnitt in
    # Mitteleuropa die ersten ein bis zwei Stunden des Tages ab und hängte
    # dafür die ersten Stunden des Folgetages an.
    tz = _markt_tz(markt)
    start_dt = datetime(datum.year, datum.month, datum.day, tzinfo=tz)
    # Wanduhr-Arithmetik: +1 Tag ist am Umstellungswochenende 23 bzw. 25 Stunden.
    end_dt = start_dt + timedelta(days=1)
    params = {
        "start": str(int(start_dt.timestamp() * 1000)),
        "end": str(int(end_dt.timestamp() * 1000)),
    }

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

    except httpx.TimeoutException:
        logger.warning("Strompreis-Markt: Timeout für %s %s", markt, datum)
        _error_cache[key] = time.monotonic() + ERROR_TTL_NETWORK
        return None
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        ttl = ERROR_TTL_RATE_LIMIT if status == 429 else ERROR_TTL_SERVER_ERROR
        logger.warning("Strompreis-Markt: HTTP %d für %s %s", status, markt, datum)
        _error_cache[key] = time.monotonic() + ttl
        return None
    except Exception as e:
        logger.warning("Strompreis-Markt: Fehler für %s %s: %s", markt, datum, e)
        _error_cache[key] = time.monotonic() + ERROR_TTL_NETWORK
        return None

    # Response parsen: [{start_timestamp, end_timestamp, marketprice, unit}]
    entries = data.get("data", [])
    if not entries:
        logger.debug("Strompreis-Markt: Keine Daten für %s %s", markt, datum)
        return None

    preise: dict[int, float] = {}
    for entry in entries:
        ts_ms = entry.get("start_timestamp")
        mp = entry.get("marketprice")  # EUR/MWh
        if ts_ms is None or mp is None:
            continue
        # Stunde in der MARKTZONE, nicht in der Prozesszone (F-6): ohne die
        # explizite Zone trug der Schlüssel auf einem UTC-Container die
        # UTC-Stunde, während der HA-Export ihn gegen die Berliner Stunde hielt.
        lokal = datetime.fromtimestamp(ts_ms / 1000, tz=tz)
        if lokal.date() != datum:
            # Kann nur der Rand des Fensters sein — gehört nicht zu diesem Tag.
            continue
        stunde = lokal.hour
        # Am Ende der Sommerzeit gibt es die Stunde 2 zweimal. Ein
        # `dict[int, float]` kann das nicht abbilden; die **erste** (also die
        # vor der Rückstellung) gewinnt, statt still von der zweiten
        # überschrieben zu werden. Im Frühjahr fehlt die Stunde 2 entsprechend
        # ganz — der Tag hat dann 23 Einträge, und das ist richtig so.
        if stunde in preise:
            continue
        # EUR/MWh → ct/kWh (÷ 10)
        preise[stunde] = round(mp / 10, 2)

    if preise:
        _cache[key] = (time.monotonic() + CACHE_TTL, preise)
        logger.debug("Strompreis-Markt: %d Stunden für %s %s geladen", len(preise), markt, datum)

    return preise if preise else None


async def get_strompreis_stunden(
    anlage_land: Optional[str],
    datum: date,
) -> dict[int, float]:
    """
    Convenience-Wrapper: Holt Marktpreise passend zum Anlagen-Land.

    Args:
        anlage_land: ISO-Code des Landes (z.B. "DE", "AT") oder None → "DE"
        datum: Tag

    Returns:
        dict {stunde: ct_kwh} oder {} wenn nicht verfügbar
    """
    markt = "AT" if anlage_land and anlage_land.upper() in ("AT", "AUT") else "DE"
    result = await fetch_marktpreise(datum, markt=markt)
    return result or {}
