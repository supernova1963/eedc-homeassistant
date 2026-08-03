"""
HA State Service - Holt aktuelle Sensor-Werte aus Home Assistant.

Wird verwendet für:
- Monatsabschluss-Vorschläge aus MQTT-Monatssensoren
- Live-Werte für Dashboards
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Optional

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)


# ── Gezielter States-Abruf (statt Voll-Dump) ──────────────────────────
#
# `GET /api/states` liefert **alle** Entities der Instanz inklusive Attribute.
# Auf einer gewachsenen Installation sind das Megabytes, die HA Core in seinem
# eigenen Event-Loop serialisieren muss — gemessen 2026-08-03 auf einer Instanz
# mit 3457 Entities: ~2,4 MB je Abruf. Das Live-Cockpit pollt alle 5 s, im
# Add-on läuft jedes dieser Pakete zusätzlich durch den Ingress-Proxy, also ein
# zweites Mal durch denselben Event-Loop. Wer daraus zwanzig Sensoren
# herausfiltert, hat den Rest umsonst transportiert.
#
# Deshalb: `GET /api/states/<entity_id>` je gebrauchter Entity, gebündelt über
# EINEN httpx-Client (Keep-Alive, eine TCP-Verbindung) und mit begrenzter
# Parallelität. Der alte Kommentar „1 HTTP-Call statt N" optimierte die falsche
# Achse — N winzige Antworten sind für HA billiger als eine riesige.
#
# **Nicht** hierher gehören die Aufrufer, die tatsächlich alle Entities
# aufzählen (Sensor-Auswahllisten, Solcast-/Prognose-Discovery). Die brauchen
# den Voll-Dump und laufen auf Anforderung, nicht getaktet.
_PARALLEL_LIMIT = 8

# TTL des Live-Caches. Kürzer als der 5-s-Poll des Cockpits, damit ein einzelner
# Tab weiterhin frische Werte sieht — aber lang genug, dass sich zwei versetzt
# pollende Tabs (oder Browser) die Abrufe teilen, statt HA zu verdoppeln.
_STATE_CACHE_TTL = 3.0

# (api_url, entity_id) → (zeitpunkt, roher State-Dict oder None).
# Der api_url-Anteil trennt Supervisor- und Remote-Verbindung; sonst würde ein
# Wechsel der aktiven HA-Verbindung alte Werte weiterreichen.
_state_cache: dict[tuple[str, str], tuple[float, Optional[dict]]] = {}


async def fetch_selected_states(
    api_url: str,
    token: str,
    entity_ids: list[str],
    *,
    timeout: float = 10.0,
    use_cache: bool = True,
) -> dict[str, Optional[dict]]:
    """Rohe State-Dicts genau der angefragten Entities — ohne Voll-Dump.

    Args:
        api_url: Basis-URL der HA-API (Supervisor ODER Remote).
        token: Bearer-Token derselben Verbindung.
        entity_ids: die tatsächlich gebrauchten Entity-IDs.
        timeout: je Einzelabruf.
        use_cache: TTL-Cache benutzen. Aus für Pfade, die zwingend den
            Momentanwert brauchen (Diagnose, Reparatur).

    Returns:
        entity_id → State-Dict wie von HA geliefert, oder None wenn die Entity
        nicht existiert bzw. der Abruf scheiterte. Ein Fehler bei einer Entity
        nimmt die anderen nicht mit.
    """
    if not api_url or not token or not entity_ids:
        return {}

    now = time.monotonic()
    ergebnis: dict[str, Optional[dict]] = {}
    offen: list[str] = []

    for eid in dict.fromkeys(entity_ids):  # Reihenfolge halten, Duplikate raus
        if use_cache:
            treffer = _state_cache.get((api_url, eid))
            if treffer is not None and (now - treffer[0]) < _STATE_CACHE_TTL:
                ergebnis[eid] = treffer[1]
                continue
        offen.append(eid)

    if not offen:
        return ergebnis

    kopf = {"Authorization": f"Bearer {token}"}
    sperre = asyncio.Semaphore(_PARALLEL_LIMIT)

    async def hole(client: httpx.AsyncClient, eid: str) -> tuple[str, Optional[dict]]:
        async with sperre:
            try:
                resp = await client.get(f"{api_url}/states/{eid}", headers=kopf)
            except Exception:  # noqa: BLE001 — Netz/TLS: diese eine Entity fehlt
                return eid, None
            if resp.status_code != 200:
                return eid, None
            try:
                return eid, resp.json()
            except Exception:  # noqa: BLE001 — unerwarteter Body
                return eid, None

    grenzen = httpx.Limits(
        max_connections=_PARALLEL_LIMIT,
        max_keepalive_connections=_PARALLEL_LIMIT,
    )
    async with httpx.AsyncClient(timeout=timeout, limits=grenzen) as client:
        for eid, daten in await asyncio.gather(*(hole(client, e) for e in offen)):
            ergebnis[eid] = daten
            # Auch ein None wird gecacht: ein nicht existierender oder gerade
            # nicht erreichbarer Sensor darf den 5-s-Poll nicht in einen
            # Dauer-Retry verwandeln.
            _state_cache[(api_url, eid)] = (now, daten)

    return ergebnis


def _state_wert_und_einheit(daten: Optional[dict]) -> Optional[tuple[float, str]]:
    """(Zahlwert, Einheit) aus einem rohen State-Dict — oder None.

    None steht für „kein verwertbarer Messwert": Entity fehlt, State ist
    `unknown`/`unavailable` oder nicht numerisch. Die Unterscheidung zwischen
    diesen Fällen trifft der Aufrufer nicht, sie ist für ihn dieselbe.
    """
    if not daten:
        return None
    state = daten.get("state")
    if state in [None, "unknown", "unavailable", ""]:
        return None
    try:
        wert = float(state)
    except (ValueError, TypeError):
        return None
    einheit = (daten.get("attributes") or {}).get("unit_of_measurement", "")
    return (wert, einheit or "")


class HAStateService:
    """Holt Sensor-States aus Home Assistant via Supervisor API."""

    _UNIT_CACHE_TTL = 3600  # 1 Stunde

    def __init__(self):
        self.api_url = settings.ha_api_url
        self.token = settings.supervisor_token
        # entity_id → (zeitpunkt, einheit). Die Einheit ist bewusst auch dann
        # gemerkt, wenn sie leer ist — siehe get_sensor_units().
        self._unit_cache: dict[str, tuple[float, str]] = {}

    @property
    def is_available(self) -> bool:
        """Prüft ob HA-API verfügbar ist."""
        return bool(self.token)

    async def get_sensor_state(self, entity_id: str) -> Optional[float]:
        """
        Holt den aktuellen State eines Sensors.

        Args:
            entity_id: HA Entity-ID (z.B. "sensor.sma_netzeinspeisung_pv")

        Returns:
            Float-Wert oder None wenn nicht verfügbar
        """
        result = await self.get_sensor_state_with_unit(entity_id)
        return result[0] if result else None

    async def get_sensor_state_with_unit(self, entity_id: str) -> Optional[tuple[float, str]]:
        """
        Holt State + Einheit eines Sensors.

        HA gibt den State in der `suggested_unit_of_measurement` zurück, nicht
        in der nativen Einheit. Z.B. E3DC-Sensoren: nativ W, angezeigt als kW.
        Die Einheit steht in attributes.unit_of_measurement.

        Returns:
            (wert, einheit) oder None wenn nicht verfügbar
        """
        if not self.is_available:
            return None

        treffer = await self.get_sensor_states_batch([entity_id])
        return treffer.get(entity_id)

    async def get_sensor_states_batch(
        self, entity_ids: list[str]
    ) -> dict[str, Optional[tuple[float, str]]]:
        """
        Holt State + Einheit für mehrere Entities — nur für die angefragten.

        Läuft über `fetch_selected_states` (ein Abruf je Entity, gebündelt über
        einen Client, TTL-Cache) statt über den Voll-Dump `/api/states`. Warum,
        steht dort ausführlich; kurz: der Voll-Dump kostete auf einer Instanz
        mit 3457 Entities ~2,4 MB — je Poll, alle 5 s, im Event-Loop von HA.

        Returns:
            Dict entity_id → (wert, einheit) oder entity_id → None
        """
        if not self.is_available or not entity_ids:
            return {}

        roh = await fetch_selected_states(self.api_url, self.token, entity_ids)
        return {eid: _state_wert_und_einheit(daten) for eid, daten in roh.items()}

    async def get_sensor_units(self, entity_ids: list[str]) -> dict[str, str]:
        """
        Holt unit_of_measurement für mehrere Entities (In-Memory-Cache, 1h TTL).

        Gemerkt wird die Einheit **auch dann, wenn sie leer ist**. Vorher landete
        nur im Cache, wer eine hatte (`if unit:`) — ein einziger Sensor ohne
        `unit_of_measurement` im Mapping stand damit dauerhaft auf der
        Fehlliste, und weil die Fehlliste den Neuabruf auslöste, lief der
        Voll-Dump bei **jedem** Aufruf. Der 1h-TTL war in dem Fall wirkungslos.

        **„Noch nie geholt" wird an der Abwesenheit geprüft, nicht an einem
        Zeitstempel 0.0.** `time.monotonic()` zählt ab dem Systemstart, nicht ab
        1970: auf einer Box, die seit weniger als einer Stunde läuft, ist
        `now - 0.0 < TTL` — ein leerer Cache galt damit als frisch, es wurde
        nichts geholt, und die Funktion lieferte in der ersten Betriebsstunde
        durchgehend `{}`. Genau daran ist der Beleg unten in CI gefallen und
        auf einer Maschine mit Tagen an Laufzeit nicht.
        """
        if not self.is_available or not entity_ids:
            return {}

        now = time.monotonic()
        fehlend = [
            eid for eid in dict.fromkeys(entity_ids)
            if eid not in self._unit_cache
            or now - self._unit_cache[eid][0] >= self._UNIT_CACHE_TTL
        ]

        if fehlend:
            roh = await fetch_selected_states(self.api_url, self.token, fehlend)
            for eid, daten in roh.items():
                if daten is None:
                    continue  # nicht erreichbar → beim nächsten Mal erneut
                einheit = (daten.get("attributes") or {}).get("unit_of_measurement", "")
                self._unit_cache[eid] = (now, einheit or "")

        # Nur belegte Einheiten ausliefern — unveränderter Vertrag: der Aufrufer
        # unterscheidet „keine Einheit" nicht von „nicht gefunden".
        return {
            eid: self._unit_cache[eid][1]
            for eid in entity_ids
            if self._unit_cache.get(eid, (0.0, ""))[1]
        }

    async def get_sensor_history(
        self,
        entity_ids: list[str],
        start: datetime,
        end: Optional[datetime] = None,
    ) -> dict[str, list[tuple[datetime, float]]]:
        """
        Holt Sensor-History aus HA via /api/history/period.

        Args:
            entity_ids: Liste von Entity-IDs
            start: Startzeitpunkt
            end: Endzeitpunkt (default: jetzt)

        Returns:
            Dict entity_id → [(zeitpunkt, wert), ...] sortiert nach Zeit
        """
        if not self.is_available or not entity_ids:
            return {}

        end = end or datetime.now()

        try:
            params = {
                "filter_entity_id": ",".join(entity_ids),
                "end_time": end.isoformat(),
                "minimal_response": "",
                "no_attributes": "",
            }

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/history/period/{start.isoformat()}",
                    headers={"Authorization": f"Bearer {self.token}"},
                    params=params,
                    timeout=15.0,
                )

                if response.status_code != 200:
                    logger.warning(f"HA History API: Status {response.status_code}")
                    return {}

                data = response.json()

            result: dict[str, list[tuple[datetime, float]]] = {}

            for entity_history in data:
                if not entity_history:
                    continue

                entity_id = entity_history[0].get("entity_id", "")
                points: list[tuple[datetime, float]] = []

                for state_entry in entity_history:
                    state = state_entry.get("state") or state_entry.get("s")
                    if state in [None, "unknown", "unavailable", ""]:
                        continue

                    try:
                        val = float(state)
                    except (ValueError, TypeError):
                        continue

                    # last_changed oder last_updated
                    ts_str = (
                        state_entry.get("last_changed")
                        or state_entry.get("last_updated")
                        or state_entry.get("lu")
                    )
                    if not ts_str:
                        continue

                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        # In lokale Zeit konvertieren (naive datetime)
                        ts = ts.astimezone().replace(tzinfo=None)
                    except (ValueError, TypeError):
                        continue

                    points.append((ts, val))

                if points:
                    points.sort(key=lambda p: p[0])
                    result[entity_id] = points

            return result

        except Exception as e:
            logger.warning(f"HA History API Fehler: {type(e).__name__}: {e}")
            return {}


# Singleton
_ha_state_service: Optional[HAStateService] = None


def get_ha_state_service() -> HAStateService:
    """Gibt die Singleton-Instanz zurück."""
    global _ha_state_service
    if _ha_state_service is None:
        _ha_state_service = HAStateService()
    return _ha_state_service
