"""
Home Assistant Integration API Routes

Nur noch die grundlegende HA-Verbindungsprüfung (`GET /status`).

Die beiden V3-Reste `GET /sensors` (Energy-Sensor-Listing) und `GET /mapping`
(Legacy-`ha_sensor_*`-Settings) sind mit der V3-Bereinigung 2026-08 gefallen —
beide waren seit dem IA-V4-Flip clientlos (Sensor-Auswahl läuft über die
Datenquellen-Fläche, `datenquellen.py`). Die Legacy-Settings selbst bleiben
unangetastet (CLAUDE.md §Deprecated).

Für HA-Export: Siehe ha_export.py (MQTT + REST).
"""

from fastapi import APIRouter
import httpx

from backend.core.config import settings


router = APIRouter()


@router.get("/status")
async def get_ha_status():
    """
    Prüft die Verbindung zu Home Assistant (REST API).

    Returns:
        dict: Status der HA-Verbindung
    """
    if not settings.supervisor_token:
        return {
            "connected": False,
            "rest_api": False,
            "ha_version": None,
            "message": "Kein Supervisor Token gefunden. Läuft eedc als HA Add-on?"
        }

    result = {
        "connected": False,
        "rest_api": False,
        "ha_version": None,
        "message": ""
    }

    # REST API testen
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.ha_api_url}/",
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                timeout=5.0
            )
            if response.status_code == 200:
                result["rest_api"] = True
                result["connected"] = True
                data = response.json()
                result["ha_version"] = data.get("version")
                result["message"] = "REST API verbunden"
    except Exception as e:
        result["message"] = f"REST API Fehler: {str(e)}"

    return result
