"""
Wetter API Routes

Stellt Endpoints für automatische Wetterdaten-Abfrage bereit.

Unterstützte Datenquellen:
- Open-Meteo: Weltweit, 16-Tage Prognose
- Bright Sky (DWD): Höchste Qualität für Deutschland
- PVGIS TMY: Langjährige Durchschnittswerte als Fallback
"""

from typing import Optional, List, Literal
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.services.wetter_service import (
    get_wetterdaten,
    get_wetterdaten_multi,
    get_available_providers,
    get_provider_comparison,
    WetterProvider,
)

router = APIRouter()


# =============================================================================
# Pydantic Schemas
# =============================================================================

class StandortInfo(BaseModel):
    """Standort-Informationen."""
    latitude: float
    longitude: float
    land: str | None = None
    in_deutschland: bool = False


class ProviderInfo(BaseModel):
    """Details zum verwendeten Provider."""
    name: str
    tage_mit_daten: int | None = None
    tage_gesamt: int | None = None
    temperatur_c: float | None = None
    hinweis: str | None = None


class WetterDatenResponse(BaseModel):
    """Response für Wetterdaten-Abfrage."""
    jahr: int
    monat: int = Field(..., ge=1, le=12)
    globalstrahlung_kwh_m2: float = Field(..., ge=0, description="Globalstrahlung in kWh/m²")
    sonnenstunden: float = Field(..., ge=0, description="Sonnenstunden im Monat")
    datenquelle: str = Field(..., description="open-meteo, brightsky, pvgis-tmy oder defaults")
    standort: StandortInfo
    abdeckung_prozent: float | None = Field(None, description="Prozent der Tage mit Daten")
    hinweis: str | None = Field(None, description="Optionaler Hinweis zur Datenqualität")
    provider_info: ProviderInfo | None = Field(None, description="Details zum Provider")
    provider_versucht: list[str] | None = Field(None, description="Liste versuchter Provider")


class WetterProviderSchema(BaseModel):
    """Schema für einen Wetter-Provider."""
    id: str
    name: str
    beschreibung: str
    empfohlen: bool
    verfuegbar: bool
    hinweis: str | None = None


class WetterProviderListResponse(BaseModel):
    """Response für Provider-Liste."""
    standort: StandortInfo
    provider: list[WetterProviderSchema]
    aktueller_provider: str


class ProviderDaten(BaseModel):
    """Daten eines einzelnen Providers im Vergleich."""
    verfuegbar: bool
    globalstrahlung_kwh_m2: float | None = None
    sonnenstunden: float | None = None
    abdeckung_prozent: float | None = None
    temperatur_c: float | None = None
    hinweis: str | None = None
    fehler: str | None = None


class VergleichInfo(BaseModel):
    """Vergleichs-Statistiken."""
    durchschnitt_kwh_m2: float
    abweichung_max_prozent: float


class WetterVergleichResponse(BaseModel):
    """Response für Provider-Vergleich."""
    jahr: int
    monat: int
    standort: StandortInfo
    provider: dict[str, ProviderDaten]
    vergleich: VergleichInfo | None = None


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/monat/{anlage_id}/{jahr}/{monat}", response_model=WetterDatenResponse)
async def get_wetter_monat(
    anlage_id: int,
    jahr: int,
    monat: int,
    provider: str = Query(
        default="auto",
        description="Datenquelle: auto, open-meteo, brightsky"
    ),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt Wetterdaten (Globalstrahlung, Sonnenstunden) für einen Monat.

    Datenquellen:
    - auto: Automatische Auswahl (Bright Sky für DE, Open-Meteo sonst)
    - open-meteo: Open-Meteo Archive API (weltweit)
    - brightsky: Bright Sky / DWD (nur Deutschland, höhere Qualität)
    - Fallback: PVGIS TMY → Statische Defaults

    Args:
        anlage_id: ID der Anlage (für Koordinaten)
        jahr: Jahr (2000-2100)
        monat: Monat (1-12)
        provider: Gewünschte Datenquelle

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

    # Wetterdaten mit Multi-Provider abrufen
    data = await get_wetterdaten_multi(
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        jahr=jahr,
        monat=monat,
        provider=provider  # type: ignore
    )

    return WetterDatenResponse(**data)


@router.get("/monat/koordinaten/{latitude}/{longitude}/{jahr}/{monat}", response_model=WetterDatenResponse)
async def get_wetter_monat_by_coords(
    latitude: float,
    longitude: float,
    jahr: int,
    monat: int,
    provider: str = Query(default="auto", description="Datenquelle")
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
        provider: Datenquelle (auto, open-meteo, brightsky)

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

    # Wetterdaten mit Multi-Provider abrufen
    data = await get_wetterdaten_multi(
        latitude=latitude,
        longitude=longitude,
        jahr=jahr,
        monat=monat,
        provider=provider  # type: ignore
    )

    return WetterDatenResponse(**data)


# =============================================================================
# Neue Endpoints für Provider-Verwaltung
# =============================================================================

@router.get("/provider/{anlage_id}", response_model=WetterProviderListResponse)
async def get_wetter_provider(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt verfügbare Wetter-Provider für eine Anlage zurück.

    Berücksichtigt den Standort der Anlage:
    - Deutschland: Bright Sky verfügbar und empfohlen
    - Andere: Open-Meteo empfohlen
    """
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(
            status_code=400,
            detail="Anlage hat keine Koordinaten"
        )

    providers = get_available_providers(anlage.latitude, anlage.longitude)

    # Aktuellen Provider der Anlage ermitteln
    aktueller_provider = getattr(anlage, "wetter_provider", None) or "auto"

    # Standort bestimmen: Deutschland wenn Bright Sky verfügbar und empfohlen
    in_deutschland = any(
        p.get("id") == "brightsky" and p.get("verfuegbar") and p.get("empfohlen")
        for p in providers
    )

    # Land-Name basierend auf Standort (vereinfacht: nur DE erkennen)
    land = "Deutschland" if in_deutschland else anlage.standort_ort or None

    return WetterProviderListResponse(
        standort=StandortInfo(
            latitude=anlage.latitude,
            longitude=anlage.longitude,
            land=land,
            in_deutschland=in_deutschland
        ),
        provider=[WetterProviderSchema(**p) for p in providers],
        aktueller_provider=aktueller_provider
    )


@router.get("/vergleich/{anlage_id}/{jahr}/{monat}", response_model=WetterVergleichResponse)
async def get_wetter_vergleich(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Vergleicht Wetterdaten verschiedener Provider für denselben Monat.

    Nützlich für:
    - Transparenz und Qualitätskontrolle
    - Entscheidungshilfe für Provider-Wahl
    """
    # Validierung
    if monat < 1 or monat > 12:
        raise HTTPException(status_code=400, detail=f"Ungültiger Monat: {monat}")

    if jahr < 2000 or jahr > 2100:
        raise HTTPException(status_code=400, detail=f"Ungültiges Jahr: {jahr}")

    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    if not anlage.latitude or not anlage.longitude:
        raise HTTPException(status_code=400, detail="Anlage hat keine Koordinaten")

    comparison = await get_provider_comparison(
        anlage.latitude, anlage.longitude, jahr, monat
    )

    return WetterVergleichResponse(
        jahr=comparison["jahr"],
        monat=comparison["monat"],
        standort=StandortInfo(**comparison["standort"]),
        provider={
            name: ProviderDaten(**data)
            for name, data in comparison["provider"].items()
        },
        vergleich=VergleichInfo(**comparison["vergleich"])
        if comparison.get("vergleich") else None
    )
