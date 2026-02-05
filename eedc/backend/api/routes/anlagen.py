"""
Anlagen API Routes

CRUD Endpoints für PV-Anlagen.
"""

from typing import Optional
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


class AnlageCreate(AnlageBase):
    """Schema für Anlage-Erstellung."""
    pass


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
