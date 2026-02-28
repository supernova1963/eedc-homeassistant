"""
HA State Service - Holt aktuelle Sensor-Werte aus Home Assistant.

Wird verwendet für:
- Monatsabschluss-Vorschläge aus MQTT-Monatssensoren
- Live-Werte für Dashboards
"""

from typing import Optional
import httpx

from backend.core.config import settings


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
            entity_id: HA Entity-ID (z.B. "sensor.eedc_1_mwd_einspeisung_monat")

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

    async def get_mwd_sensor_value(
        self,
        anlage_id: int,
        feld: str,
    ) -> Optional[float]:
        """
        Holt den Wert eines EEDC-Monatssensors.

        Die MQTT Auto-Discovery erstellt Sensoren im Format:
        sensor.eedc_{anlage_id}_mwd_{feld}_monat

        Args:
            anlage_id: ID der Anlage
            feld: Feld-Key (z.B. "einspeisung", "netzbezug")

        Returns:
            Aktueller Monatswert oder None
        """
        entity_id = f"sensor.eedc_{anlage_id}_mwd_{feld}_monat"
        return await self.get_sensor_state(entity_id)


# Singleton
_ha_state_service: Optional[HAStateService] = None


def get_ha_state_service() -> HAStateService:
    """Gibt die Singleton-Instanz zurück."""
    global _ha_state_service
    if _ha_state_service is None:
        _ha_state_service = HAStateService()
    return _ha_state_service
