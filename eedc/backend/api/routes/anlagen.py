"""
Anlagen API Routes

CRUD Endpoints für PV-Anlagen.
"""

from typing import Optional, Any
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from datetime import date

from backend.api.deps import get_db
from backend.models.anlage import Anlage


# =============================================================================
# Pydantic Schemas
# =============================================================================

class AnlageBase(BaseModel):
    """Basis-Schema für Anlage."""
    anlagenname: str = Field(..., min_length=1, max_length=255)
    leistung_kwp: float = Field(..., gt=0)
    installationsdatum: Optional[date] = None
    standort_plz: Optional[str] = Field(None, max_length=10)
    standort_ort: Optional[str] = Field(None, max_length=255)
    standort_strasse: Optional[str] = Field(None, max_length=255)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    ausrichtung: Optional[str] = Field(None, max_length=50)
    neigung_grad: Optional[float] = Field(None, ge=0, le=90)
    wechselrichter_hersteller: Optional[str] = Field(None, max_length=50, description="Wechselrichter-Hersteller für Discovery-Filter")
    # Home Assistant Sensor-Konfiguration
    ha_sensor_pv_erzeugung: Optional[str] = Field(None, max_length=255)
    ha_sensor_einspeisung: Optional[str] = Field(None, max_length=255)
    ha_sensor_netzbezug: Optional[str] = Field(None, max_length=255)
    ha_sensor_batterie_ladung: Optional[str] = Field(None, max_length=255)
    ha_sensor_batterie_entladung: Optional[str] = Field(None, max_length=255)
    # Erweiterte Stammdaten
    mastr_id: Optional[str] = Field(None, max_length=20, description="Marktstammdatenregister-ID der Anlage")
    versorger_daten: Optional[dict[str, Any]] = Field(None, description="Versorger und Zähler als JSON")
    # Wetterdaten-Provider
    wetter_provider: Optional[str] = Field(None, max_length=30, description="Wetterdaten-Provider (auto, brightsky, open-meteo, open-meteo-solar)")
    # Community
    community_hash: Optional[str] = Field(None, max_length=64, description="Hash für Community-Teilen (read-only)")


class AnlageCreate(AnlageBase):
    """Schema für Anlage-Erstellung."""
    # community_hash wird nicht bei Create akzeptiert (nur über Community-API gesetzt)
    community_hash: None = None


class AnlageUpdate(BaseModel):
    """Schema für Anlage-Update (alle Felder optional)."""
    anlagenname: Optional[str] = Field(None, min_length=1, max_length=255)
    leistung_kwp: Optional[float] = Field(None, gt=0)
    installationsdatum: Optional[date] = None
    standort_plz: Optional[str] = Field(None, max_length=10)
    standort_ort: Optional[str] = Field(None, max_length=255)
    standort_strasse: Optional[str] = Field(None, max_length=255)
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    ausrichtung: Optional[str] = Field(None, max_length=50)
    neigung_grad: Optional[float] = Field(None, ge=0, le=90)
    wechselrichter_hersteller: Optional[str] = Field(None, max_length=50)
    ha_sensor_pv_erzeugung: Optional[str] = Field(None, max_length=255)
    ha_sensor_einspeisung: Optional[str] = Field(None, max_length=255)
    ha_sensor_netzbezug: Optional[str] = Field(None, max_length=255)
    ha_sensor_batterie_ladung: Optional[str] = Field(None, max_length=255)
    ha_sensor_batterie_entladung: Optional[str] = Field(None, max_length=255)
    mastr_id: Optional[str] = Field(None, max_length=20)
    versorger_daten: Optional[dict[str, Any]] = None
    wetter_provider: Optional[str] = Field(None, max_length=30)


class SensorConfigUpdate(BaseModel):
    """Schema für Sensor-Konfiguration Update."""
    pv_erzeugung: Optional[str] = Field(None, max_length=255)
    einspeisung: Optional[str] = Field(None, max_length=255)
    netzbezug: Optional[str] = Field(None, max_length=255)
    batterie_ladung: Optional[str] = Field(None, max_length=255)
    batterie_entladung: Optional[str] = Field(None, max_length=255)


class SensorConfigResponse(BaseModel):
    """Schema für Sensor-Konfiguration Response."""
    pv_erzeugung: Optional[str] = None
    einspeisung: Optional[str] = None
    netzbezug: Optional[str] = None
    batterie_ladung: Optional[str] = None
    batterie_entladung: Optional[str] = None


class GeocodeResponse(BaseModel):
    """Schema für Geocoding Response."""
    latitude: float
    longitude: float
    display_name: str


class AnlageResponse(AnlageBase):
    """Schema für Anlage-Response."""
    id: int

    class Config:
        from_attributes = True


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.get("/", response_model=list[AnlageResponse])
async def list_anlagen(db: AsyncSession = Depends(get_db)):
    """
    Gibt alle Anlagen zurück.

    Returns:
        list[AnlageResponse]: Liste aller Anlagen
    """
    result = await db.execute(select(Anlage).order_by(Anlage.anlagenname))
    anlagen = result.scalars().all()
    return anlagen


@router.get("/{anlage_id}", response_model=AnlageResponse)
async def get_anlage(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """
    Gibt eine einzelne Anlage zurück.

    Args:
        anlage_id: ID der Anlage

    Returns:
        AnlageResponse: Die Anlage

    Raises:
        404: Anlage nicht gefunden
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anlage mit ID {anlage_id} nicht gefunden"
        )

    return anlage


@router.post("/", response_model=AnlageResponse, status_code=status.HTTP_201_CREATED)
async def create_anlage(data: AnlageCreate, db: AsyncSession = Depends(get_db)):
    """
    Erstellt eine neue Anlage.

    Args:
        data: Anlagen-Daten

    Returns:
        AnlageResponse: Die erstellte Anlage
    """
    anlage = Anlage(**data.model_dump())
    db.add(anlage)
    await db.flush()
    await db.refresh(anlage)
    return anlage


@router.put("/{anlage_id}", response_model=AnlageResponse)
async def update_anlage(anlage_id: int, data: AnlageUpdate, db: AsyncSession = Depends(get_db)):
    """
    Aktualisiert eine Anlage.

    Args:
        anlage_id: ID der Anlage
        data: Zu aktualisierende Felder

    Returns:
        AnlageResponse: Die aktualisierte Anlage

    Raises:
        404: Anlage nicht gefunden
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anlage mit ID {anlage_id} nicht gefunden"
        )

    # Nur übergebene Felder aktualisieren
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(anlage, field, value)

    await db.flush()
    await db.refresh(anlage)
    return anlage


@router.delete("/{anlage_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_anlage(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """
    Löscht eine Anlage.

    Args:
        anlage_id: ID der Anlage

    Raises:
        404: Anlage nicht gefunden
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anlage mit ID {anlage_id} nicht gefunden"
        )

    await db.delete(anlage)


@router.get("/{anlage_id}/sensors", response_model=SensorConfigResponse)
async def get_sensor_config(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """
    Gibt die HA-Sensor-Konfiguration einer Anlage zurück.

    Args:
        anlage_id: ID der Anlage

    Returns:
        SensorConfigResponse: Die Sensor-Konfiguration
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anlage mit ID {anlage_id} nicht gefunden"
        )

    return SensorConfigResponse(
        pv_erzeugung=anlage.ha_sensor_pv_erzeugung,
        einspeisung=anlage.ha_sensor_einspeisung,
        netzbezug=anlage.ha_sensor_netzbezug,
        batterie_ladung=anlage.ha_sensor_batterie_ladung,
        batterie_entladung=anlage.ha_sensor_batterie_entladung,
    )


@router.patch("/{anlage_id}/sensors", response_model=SensorConfigResponse)
async def update_sensor_config(
    anlage_id: int,
    data: SensorConfigUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Aktualisiert die HA-Sensor-Konfiguration einer Anlage.

    Args:
        anlage_id: ID der Anlage
        data: Sensor-Konfiguration

    Returns:
        SensorConfigResponse: Die aktualisierte Konfiguration
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anlage mit ID {anlage_id} nicht gefunden"
        )

    # Sensor-Felder aktualisieren
    if data.pv_erzeugung is not None:
        anlage.ha_sensor_pv_erzeugung = data.pv_erzeugung or None
    if data.einspeisung is not None:
        anlage.ha_sensor_einspeisung = data.einspeisung or None
    if data.netzbezug is not None:
        anlage.ha_sensor_netzbezug = data.netzbezug or None
    if data.batterie_ladung is not None:
        anlage.ha_sensor_batterie_ladung = data.batterie_ladung or None
    if data.batterie_entladung is not None:
        anlage.ha_sensor_batterie_entladung = data.batterie_entladung or None

    await db.flush()
    await db.refresh(anlage)

    return SensorConfigResponse(
        pv_erzeugung=anlage.ha_sensor_pv_erzeugung,
        einspeisung=anlage.ha_sensor_einspeisung,
        netzbezug=anlage.ha_sensor_netzbezug,
        batterie_ladung=anlage.ha_sensor_batterie_ladung,
        batterie_entladung=anlage.ha_sensor_batterie_entladung,
    )


@router.get("/geocode/lookup", response_model=GeocodeResponse)
async def geocode_address(
    plz: str,
    ort: Optional[str] = None,
    land: str = "Germany"
):
    """
    Ermittelt Koordinaten aus PLZ/Ort via OpenStreetMap Nominatim.

    Args:
        plz: Postleitzahl
        ort: Ortsname (optional, verbessert Genauigkeit)
        land: Land (default: Germany)

    Returns:
        GeocodeResponse: Koordinaten und Anzeigename

    Raises:
        404: Keine Koordinaten gefunden
        503: Geocoding-Service nicht erreichbar
    """
    # Nominatim API URL
    base_url = "https://nominatim.openstreetmap.org/search"

    # Query aufbauen
    query_parts = [plz]
    if ort:
        query_parts.append(ort)
    query_parts.append(land)

    params = {
        "q": ", ".join(query_parts),
        "format": "json",
        "limit": 1,
        "addressdetails": 1,
    }

    headers = {
        "User-Agent": "EEDC-HomeAssistant/0.8.0 (PV-Anlagen-Verwaltung)"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(base_url, params=params, headers=headers, timeout=10.0)
            response.raise_for_status()
            results = response.json()

        if not results:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Keine Koordinaten für PLZ {plz} gefunden"
            )

        result = results[0]
        return GeocodeResponse(
            latitude=float(result["lat"]),
            longitude=float(result["lon"]),
            display_name=result.get("display_name", f"{plz}, {land}")
        )

    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Geocoding-Service nicht erreichbar: {str(e)}"
        )
