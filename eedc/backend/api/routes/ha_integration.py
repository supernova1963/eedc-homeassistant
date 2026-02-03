"""
Home Assistant Integration API Routes

Endpoints für HA-Sensor-Zugriff und Datenimport.
"""

from typing import Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
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
    state: Optional[str]


class HASensorMapping(BaseModel):
    """Sensor-Mapping Konfiguration."""
    pv_erzeugung: Optional[str] = None
    einspeisung: Optional[str] = None
    netzbezug: Optional[str] = None
    batterie_ladung: Optional[str] = None
    batterie_entladung: Optional[str] = None


class HAStatisticsRequest(BaseModel):
    """Anfrage für HA Statistiken."""
    sensor_id: str
    start_date: date
    end_date: date
    period: str = "month"  # hour, day, week, month


class HAStatisticsResponse(BaseModel):
    """Statistik-Daten von HA."""
    sensor_id: str
    data: list[dict]


class HAImportResult(BaseModel):
    """Ergebnis des HA-Imports."""
    erfolg: bool
    monate_importiert: int
    fehler: Optional[str] = None


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.get("/status")
async def get_ha_status():
    """
    Prüft die Verbindung zu Home Assistant.

    Returns:
        dict: Status der HA-Verbindung
    """
    if not settings.supervisor_token:
        return {
            "connected": False,
            "message": "Kein Supervisor Token gefunden. Läuft EEDC als HA Add-on?"
        }

    # Versuche HA API zu erreichen
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.ha_api_url}/",
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                timeout=5.0
            )
            if response.status_code == 200:
                return {
                    "connected": True,
                    "message": "Verbindung zu Home Assistant erfolgreich"
                }
            else:
                return {
                    "connected": False,
                    "message": f"HA API antwortet mit Status {response.status_code}"
                }
    except Exception as e:
        return {
            "connected": False,
            "message": f"Fehler bei HA-Verbindung: {str(e)}"
        }


@router.get("/sensors", response_model=list[HASensor])
async def list_energy_sensors():
    """
    Listet alle Energy-relevanten Sensoren aus Home Assistant auf.

    Returns:
        list[HASensor]: Liste der Sensoren
    """
    if not settings.supervisor_token:
        raise HTTPException(
            status_code=503,
            detail="Keine Verbindung zu Home Assistant (kein Supervisor Token)"
        )

    try:
        import httpx
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
                attrs = state.get("attributes", {})
                device_class = attrs.get("device_class", "")
                unit = attrs.get("unit_of_measurement", "")

                # Energy-relevante Sensoren finden
                if device_class in ["energy", "power", "battery"] or unit in ["kWh", "Wh", "W", "kW"]:
                    energy_sensors.append(HASensor(
                        entity_id=state["entity_id"],
                        friendly_name=attrs.get("friendly_name"),
                        unit_of_measurement=unit,
                        device_class=device_class,
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

    Returns:
        HASensorMapping: Aktuelle Zuordnung
    """
    return HASensorMapping(
        pv_erzeugung=settings.ha_sensor_pv or None,
        einspeisung=settings.ha_sensor_einspeisung or None,
        netzbezug=settings.ha_sensor_netzbezug or None,
        batterie_ladung=settings.ha_sensor_batterie_ladung or None,
        batterie_entladung=settings.ha_sensor_batterie_entladung or None,
    )


@router.post("/statistics", response_model=HAStatisticsResponse)
async def get_sensor_statistics(request: HAStatisticsRequest):
    """
    Holt Statistik-Daten für einen Sensor aus Home Assistant.

    Args:
        request: Sensor-ID und Zeitraum

    Returns:
        HAStatisticsResponse: Statistik-Daten
    """
    if not settings.supervisor_token:
        raise HTTPException(
            status_code=503,
            detail="Keine Verbindung zu Home Assistant"
        )

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            # HA Statistics API
            # Hinweis: Die genaue API kann je nach HA-Version variieren
            start_time = datetime.combine(request.start_date, datetime.min.time())
            end_time = datetime.combine(request.end_date, datetime.max.time())

            response = await client.get(
                f"{settings.ha_api_url}/history/period/{start_time.isoformat()}",
                params={
                    "filter_entity_id": request.sensor_id,
                    "end_time": end_time.isoformat(),
                    "minimal_response": "true",
                    "significant_changes_only": "true",
                },
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                timeout=30.0
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Fehler beim Abrufen der Statistiken: {response.status_code}"
                )

            data = response.json()

            return HAStatisticsResponse(
                sensor_id=request.sensor_id,
                data=data[0] if data else []
            )

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"HA-Verbindungsfehler: {str(e)}")


@router.post("/import/{anlage_id}", response_model=HAImportResult)
async def import_from_ha(
    anlage_id: int,
    jahr: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Importiert Monatsdaten aus Home Assistant für ein Jahr.

    Verwendet die konfigurierten Sensor-Mappings um Daten aus der
    HA History zu aggregieren.

    Args:
        anlage_id: ID der Anlage
        jahr: Jahr für den Import

    Returns:
        HAImportResult: Ergebnis des Imports
    """
    # TODO: Implementierung des tatsächlichen Imports
    # Dies erfordert:
    # 1. Sensor-Mapping laden
    # 2. Für jeden Monat die HA-Statistiken abrufen
    # 3. Werte aggregieren (sum für kWh)
    # 4. Monatsdaten erstellen/aktualisieren

    return HAImportResult(
        erfolg=False,
        monate_importiert=0,
        fehler="HA-Import noch nicht implementiert. Bitte CSV-Import verwenden."
    )
