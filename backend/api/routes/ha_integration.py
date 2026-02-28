"""
Home Assistant Integration API Routes

Bereinigt in v1.1: Nur noch grundlegende HA-Verbindung und Sensor-Listing.
Komplexe Features (Discovery, Statistics-Import) wurden entfernt.

Für Datenerfassung: CSV-Import oder manuelle Eingabe verwenden.
Für HA-Export: Siehe ha_export.py (MQTT + REST).
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import httpx

from backend.core.config import settings


# =============================================================================
# Pydantic Schemas
# =============================================================================

class HASensor(BaseModel):
    """Ein Home Assistant Sensor."""
    entity_id: str
    friendly_name: Optional[str]
    unit_of_measurement: Optional[str]
    device_class: Optional[str]
    state_class: Optional[str] = None
    state: Optional[str]


class HASensorMapping(BaseModel):
    """Sensor-Mapping Konfiguration (Legacy, nur für Kompatibilität)."""
    pv_erzeugung: Optional[str] = None
    einspeisung: Optional[str] = None
    netzbezug: Optional[str] = None
    batterie_ladung: Optional[str] = None
    batterie_entladung: Optional[str] = None


# =============================================================================
# Router
# =============================================================================

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
            "message": "Kein Supervisor Token gefunden. Läuft EEDC als HA Add-on?"
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


@router.get("/sensors", response_model=list[HASensor])
async def list_energy_sensors():
    """
    Listet alle Energy-relevanten Sensoren aus Home Assistant auf.

    Filtert nach device_class (energy, power, battery) und
    unit_of_measurement (kWh, Wh, W, kW).

    Returns:
        list[HASensor]: Liste der Sensoren, sortiert nach entity_id
    """
    if not settings.supervisor_token:
        raise HTTPException(
            status_code=503,
            detail="Keine Verbindung zu Home Assistant (kein Supervisor Token)"
        )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.ha_api_url}/states",
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                timeout=10.0
            )

            if response.status_code != 200:
                raise HTTPException(status_code=502, detail="Fehler beim Abrufen der HA-States")

            states = response.json()

            # Filtere Energy-relevante Sensoren
            energy_sensors = []
            for state in states:
                if not state["entity_id"].startswith("sensor."):
                    continue

                attrs = state.get("attributes", {})
                device_class = attrs.get("device_class", "")
                state_class = attrs.get("state_class", "")
                unit = attrs.get("unit_of_measurement", "")

                # Energy-relevante Sensoren finden
                if device_class in ["energy", "power", "battery"] or unit in ["kWh", "Wh", "W", "kW"]:
                    energy_sensors.append(HASensor(
                        entity_id=state["entity_id"],
                        friendly_name=attrs.get("friendly_name"),
                        unit_of_measurement=unit,
                        device_class=device_class,
                        state_class=state_class,
                        state=state.get("state")
                    ))

            # Nach Entity-ID sortieren
            energy_sensors.sort(key=lambda x: x.entity_id)
            return energy_sensors

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"HA-Verbindungsfehler: {str(e)}")


@router.get("/mapping", response_model=HASensorMapping)
async def get_sensor_mapping():
    """
    Gibt die aktuelle Sensor-Mapping Konfiguration zurück.

    HINWEIS: Dieses Mapping wird nur für Legacy-Kompatibilität beibehalten.
    Neue Implementierungen sollten Sensoren direkt in den Investitionen
    speichern (ha_entity_id Feld).

    Returns:
        HASensorMapping: Aktuelle Zuordnung aus config.yaml
    """
    return HASensorMapping(
        pv_erzeugung=settings.ha_sensor_pv or None,
        einspeisung=settings.ha_sensor_einspeisung or None,
        netzbezug=settings.ha_sensor_netzbezug or None,
        batterie_ladung=settings.ha_sensor_batterie_ladung or None,
        batterie_entladung=settings.ha_sensor_batterie_entladung or None,
    )
