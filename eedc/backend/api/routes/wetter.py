"""
Wetter API Routes

Stellt Endpoints für automatische Wetterdaten-Abfrage bereit.
Nutzt Open-Meteo für historische Daten und PVGIS TMY als Fallback.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.services.wetter_service import get_wetterdaten

router = APIRouter()


# =============================================================================
# Pydantic Schemas
# =============================================================================

class StandortInfo(BaseModel):
    """Standort-Informationen."""
    latitude: float
    longitude: float


class WetterDatenResponse(BaseModel):
    """Response für Wetterdaten-Abfrage."""
    jahr: int
    monat: int = Field(..., ge=1, le=12)
    globalstrahlung_kwh_m2: float = Field(..., ge=0, description="Globalstrahlung in kWh/m²")
    sonnenstunden: float = Field(..., ge=0, description="Sonnenstunden im Monat")
    datenquelle: str = Field(..., description="open-meteo, pvgis-tmy oder defaults")
    standort: StandortInfo
    abdeckung_prozent: float | None = Field(None, description="Prozent der Tage mit Daten (nur Open-Meteo)")
    hinweis: str | None = Field(None, description="Optionaler Hinweis zur Datenqualität")


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/monat/{anlage_id}/{jahr}/{monat}", response_model=WetterDatenResponse)
async def get_wetter_monat(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Holt Wetterdaten (Globalstrahlung, Sonnenstunden) für einen Monat.

    Datenquellen:
    - Vergangene Monate: Open-Meteo Archive API (echte historische Daten)
    - Aktuelle/Zukünftige: PVGIS TMY (langjährige Durchschnittswerte)
    - Fallback: Statische Defaults für Mitteleuropa

    Args:
        anlage_id: ID der Anlage (für Koordinaten)
        jahr: Jahr (2000-2100)
        monat: Monat (1-12)

    Returns:
        WetterDatenResponse: Wetterdaten mit Quellenangabe
    """
    # Validierung
    if monat < 1 or monat > 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Monat: {monat}. Erlaubt: 1-12"
        )

    if jahr < 2000 or jahr > 2100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiges Jahr: {jahr}. Erlaubt: 2000-2100"
        )

    # Anlage laden für Koordinaten
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anlage mit ID {anlage_id} nicht gefunden"
        )

    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Anlage hat keine Geokoordinaten. Bitte latitude/longitude in den Stammdaten ergänzen."
        )

    # Wetterdaten abrufen
    data = await get_wetterdaten(
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        jahr=jahr,
        monat=monat
    )

    return WetterDatenResponse(**data)


@router.get("/monat/koordinaten/{latitude}/{longitude}/{jahr}/{monat}", response_model=WetterDatenResponse)
async def get_wetter_monat_by_coords(
    latitude: float,
    longitude: float,
    jahr: int,
    monat: int
):
    """
    Holt Wetterdaten für beliebige Koordinaten (ohne Anlage).

    Nützlich für:
    - Standort-Prüfung vor Anlage-Erstellung
    - Vergleich verschiedener Standorte

    Args:
        latitude: Breitengrad (-90 bis +90)
        longitude: Längengrad (-180 bis +180)
        jahr: Jahr (2000-2100)
        monat: Monat (1-12)

    Returns:
        WetterDatenResponse: Wetterdaten mit Quellenangabe
    """
    # Validierung
    if monat < 1 or monat > 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Monat: {monat}. Erlaubt: 1-12"
        )

    if jahr < 2000 or jahr > 2100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiges Jahr: {jahr}. Erlaubt: 2000-2100"
        )

    if latitude < -90 or latitude > 90:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Breitengrad: {latitude}. Erlaubt: -90 bis +90"
        )

    if longitude < -180 or longitude > 180:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Ungültiger Längengrad: {longitude}. Erlaubt: -180 bis +180"
        )

    # Wetterdaten abrufen
    data = await get_wetterdaten(
        latitude=latitude,
        longitude=longitude,
        jahr=jahr,
        monat=monat
    )

    return WetterDatenResponse(**data)
