"""
Home Assistant WebSocket Client für Long-Term Statistics.

Die HA REST API bietet keinen Zugriff auf Long-Term Statistics.
Diese sind nur über die WebSocket API verfügbar.

Verwendet den Befehl 'recorder/statistics_during_period' um
monatliche Statistiken für Energy-Sensoren abzurufen.
"""

import asyncio
import json
import os
from datetime import datetime, date
from typing import Optional
from calendar import monthrange
import websockets
from websockets.exceptions import ConnectionClosed, WebSocketException

from backend.core.config import settings


class HAWebSocketClient:
    """WebSocket Client für Home Assistant Long-Term Statistics."""

    def __init__(self):
        self.supervisor_token = settings.supervisor_token

        # URL je nach Umgebung
        if self.supervisor_token:
            # Im Add-on Container
            self.ws_url = "ws://supervisor/core/websocket"
        else:
            # Lokale Entwicklung
            ha_host = os.environ.get("HA_HOST", "homeassistant.local")
            ha_port = os.environ.get("HA_PORT", "8123")
            self.ws_url = f"ws://{ha_host}:{ha_port}/api/websocket"
            self.supervisor_token = os.environ.get("HA_TOKEN", "")

        self._message_id = 0

    def _next_id(self) -> int:
        """Generiert eine eindeutige Nachrichten-ID."""
        self._message_id += 1
        return self._message_id

    async def get_statistics(
        self,
        statistic_ids: list[str],
        start_time: datetime,
        end_time: datetime,
        period: str = "month"
    ) -> dict:
        """
        Holt Long-Term Statistics über WebSocket.

        Args:
            statistic_ids: Liste von Sensor-IDs (z.B. ["sensor.pv_energy_total"])
            start_time: Startzeit
            end_time: Endzeit
            period: Aggregationsperiode ("hour", "day", "week", "month")

        Returns:
            Dict mit statistic_id als Key und Liste von Datenpunkten als Value.
            Jeder Datenpunkt enthält: start, end, state, sum, mean, min, max, change
        """
        if not self.supervisor_token:
            raise Exception("Kein Home Assistant Token verfügbar")

        async with websockets.connect(
            self.ws_url,
            additional_headers={"Authorization": f"Bearer {self.supervisor_token}"}
        ) as ws:
            # 1. Auth-Required Nachricht empfangen
            auth_required = json.loads(await ws.recv())
            if auth_required.get("type") != "auth_required":
                raise Exception(f"Unerwartete Nachricht: {auth_required}")

            # 2. Authentifizierung senden
            await ws.send(json.dumps({
                "type": "auth",
                "access_token": self.supervisor_token
            }))

            # 3. Auth-Ergebnis empfangen
            auth_result = json.loads(await ws.recv())
            if auth_result.get("type") == "auth_invalid":
                raise Exception(f"Authentifizierung fehlgeschlagen: {auth_result.get('message')}")
            if auth_result.get("type") != "auth_ok":
                raise Exception(f"Unerwartete Auth-Antwort: {auth_result}")

            # 4. Statistics-Abfrage senden
            msg_id = self._next_id()
            await ws.send(json.dumps({
                "id": msg_id,
                "type": "recorder/statistics_during_period",
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "statistic_ids": statistic_ids,
                "period": period
            }))

            # 5. Ergebnis empfangen
            result = json.loads(await ws.recv())

            if not result.get("success"):
                error = result.get("error", {})
                raise Exception(f"Abfrage fehlgeschlagen: {error.get('message', 'Unbekannter Fehler')}")

            return result.get("result", {})

    async def get_statistics_safe(
        self,
        statistic_ids: list[str],
        start_time: datetime,
        end_time: datetime,
        period: str = "month",
        max_retries: int = 3,
        timeout_seconds: float = 30.0
    ) -> dict:
        """
        Holt Statistics mit Retry-Logik und Timeout.

        Args:
            statistic_ids: Liste von Sensor-IDs
            start_time: Startzeit
            end_time: Endzeit
            period: Aggregationsperiode
            max_retries: Maximale Wiederholungsversuche
            timeout_seconds: Timeout in Sekunden

        Returns:
            Dict mit Statistics oder leeres Dict bei Fehler
        """
        last_error = None

        for attempt in range(max_retries):
            try:
                async with asyncio.timeout(timeout_seconds):
                    return await self.get_statistics(
                        statistic_ids, start_time, end_time, period
                    )
            except asyncio.TimeoutError:
                last_error = "Timeout bei WebSocket-Verbindung"
            except ConnectionClosed as e:
                last_error = f"WebSocket-Verbindung geschlossen: {e}"
            except WebSocketException as e:
                last_error = f"WebSocket-Fehler: {e}"
            except Exception as e:
                last_error = str(e)

            if attempt < max_retries - 1:
                await asyncio.sleep(1)  # Kurz warten vor Retry

        # Nach allen Retries: Fehler loggen und leeres Dict zurückgeben
        print(f"[HAWebSocket] Fehler nach {max_retries} Versuchen: {last_error}")
        return {}

    async def get_monthly_statistics(
        self,
        sensor_id: str,
        year: int,
        start_month: int = 1,
        end_month: int = 12
    ) -> list[dict]:
        """
        Holt monatliche Statistiken für ein Jahr.

        Convenience-Methode die get_statistics aufruft und
        das Ergebnis in ein einfacheres Format umwandelt.

        Args:
            sensor_id: Sensor-ID (z.B. "sensor.pv_energy_total")
            year: Jahr
            start_month: Startmonat (1-12)
            end_month: Endmonat (1-12)

        Returns:
            Liste von Dicts mit {jahr, monat, summe_kwh}
        """
        start_time = datetime(year, start_month, 1)
        _, last_day = monthrange(year, end_month)
        end_time = datetime(year, end_month, last_day, 23, 59, 59)

        stats = await self.get_statistics_safe(
            [sensor_id], start_time, end_time, "month"
        )

        monthly_data = []
        sensor_stats = stats.get(sensor_id, [])

        for entry in sensor_stats:
            start_str = entry.get("start")
            # "change" ist die Differenz im Zeitraum für total_increasing Sensoren
            change = entry.get("change", 0) or 0

            if start_str:
                try:
                    dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    monthly_data.append({
                        "jahr": dt.year,
                        "monat": dt.month,
                        "summe_kwh": round(change, 2),
                        "hat_daten": change > 0
                    })
                except ValueError:
                    pass

        return monthly_data

    async def test_connection(self) -> dict:
        """
        Testet die WebSocket-Verbindung zu Home Assistant.

        Returns:
            Dict mit Verbindungsstatus und Details
        """
        if not self.supervisor_token:
            return {
                "connected": False,
                "error": "Kein Supervisor Token verfügbar"
            }

        try:
            async with asyncio.timeout(10):
                async with websockets.connect(self.ws_url) as ws:
                    # Auth-Required
                    msg = json.loads(await ws.recv())
                    if msg.get("type") != "auth_required":
                        return {"connected": False, "error": "Unerwartete Antwort"}

                    ha_version = msg.get("ha_version", "unbekannt")

                    # Auth senden
                    await ws.send(json.dumps({
                        "type": "auth",
                        "access_token": self.supervisor_token
                    }))

                    # Auth-Ergebnis
                    result = json.loads(await ws.recv())
                    if result.get("type") == "auth_ok":
                        return {
                            "connected": True,
                            "ha_version": ha_version,
                            "message": "WebSocket-Verbindung erfolgreich"
                        }
                    else:
                        return {
                            "connected": False,
                            "error": result.get("message", "Authentifizierung fehlgeschlagen")
                        }

        except asyncio.TimeoutError:
            return {"connected": False, "error": "Timeout"}
        except Exception as e:
            return {"connected": False, "error": str(e)}
