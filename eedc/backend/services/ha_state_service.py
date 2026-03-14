"""
HA State Service - Holt aktuelle Sensor-Werte aus Home Assistant.

Wird verwendet für:
- Monatsabschluss-Vorschläge aus MQTT-Monatssensoren
- Live-Werte für Dashboards
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)


class HAStateService:
    """Holt Sensor-States aus Home Assistant via Supervisor API."""

    def __init__(self):
        self.api_url = settings.ha_api_url
        self.token = settings.supervisor_token

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
        if not self.is_available:
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/states/{entity_id}",
                    headers={"Authorization": f"Bearer {self.token}"},
                    timeout=5.0
                )

                if response.status_code != 200:
                    return None

                data = response.json()
                state = data.get("state")

                # Ungültige States ignorieren
                if state in [None, "unknown", "unavailable", ""]:
                    return None

                try:
                    return float(state)
                except (ValueError, TypeError):
                    return None

        except Exception:
            return None

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
            logger.warning(f"HA History API Fehler: {e}")
            return {}


# Singleton
_ha_state_service: Optional[HAStateService] = None


def get_ha_state_service() -> HAStateService:
    """Gibt die Singleton-Instanz zurück."""
    global _ha_state_service
    if _ha_state_service is None:
        _ha_state_service = HAStateService()
    return _ha_state_service
