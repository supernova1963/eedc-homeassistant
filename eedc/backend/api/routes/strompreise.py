"""
Strompreise API Routes

CRUD Endpoints für Stromtarife.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from datetime import date

from backend.api.deps import get_db
from backend.models.strompreis import Strompreis
from backend.models.anlage import Anlage


# =============================================================================
# Pydantic Schemas
# =============================================================================

class StrompreisBase(BaseModel):
    """Basis-Schema für Strompreis."""
    netzbezug_arbeitspreis_cent_kwh: float = Field(..., ge=0)
    einspeiseverguetung_cent_kwh: float = Field(..., ge=0)
    grundpreis_euro_monat: Optional[float] = Field(0, ge=0)
    gueltig_ab: date
    gueltig_bis: Optional[date] = None
    tarifname: Optional[str] = Field(None, max_length=255)
    anbieter: Optional[str] = Field(None, max_length=255)
    vertragsart: Optional[str] = Field(None, max_length=50)
    verwendung: str = Field("allgemein", description="Tarif-Verwendung: allgemein, waermepumpe, wallbox")


class StrompreisCreate(StrompreisBase):
    """Schema für Strompreis-Erstellung."""
    anlage_id: int


class StrompreisUpdate(BaseModel):
    """Schema für Strompreis-Update."""
    netzbezug_arbeitspreis_cent_kwh: Optional[float] = Field(None, ge=0)
    einspeiseverguetung_cent_kwh: Optional[float] = Field(None, ge=0)
    grundpreis_euro_monat: Optional[float] = Field(None, ge=0)
    gueltig_ab: Optional[date] = None
    gueltig_bis: Optional[date] = None
    tarifname: Optional[str] = Field(None, max_length=255)
    anbieter: Optional[str] = Field(None, max_length=255)
    vertragsart: Optional[str] = Field(None, max_length=50)
    verwendung: Optional[str] = Field(None, description="Tarif-Verwendung: allgemein, waermepumpe, wallbox")


class StrompreisResponse(StrompreisBase):
    """Schema für Strompreis-Response."""
    id: int
    anlage_id: int

    class Config:
        from_attributes = True


# =============================================================================
# Helper: Tarife nach Verwendung laden
# =============================================================================

async def lade_tarife_fuer_anlage(db: AsyncSession, anlage_id: int) -> dict[str, Strompreis | None]:
    """
    Lädt die aktuell gültigen Tarife nach Verwendung.

    Returns:
        Dict mit Keys 'allgemein', 'waermepumpe', 'wallbox'.
        WP/Wallbox fallen auf allgemein zurück wenn kein Spezialtarif existiert.
    """
    today = date.today()
    query = select(Strompreis).where(
        Strompreis.anlage_id == anlage_id,
        Strompreis.gueltig_ab <= today,
        (Strompreis.gueltig_bis.is_(None) | (Strompreis.gueltig_bis >= today))
    ).order_by(Strompreis.gueltig_ab.desc())

    result = await db.execute(query)
    alle_preise = result.scalars().all()

    # Nach Verwendung gruppieren (erster = neuester wg. ORDER BY DESC)
    tarife: dict[str, Strompreis | None] = {"allgemein": None, "waermepumpe": None, "wallbox": None}
    for preis in alle_preise:
        verwendung = preis.verwendung or "allgemein"
        if verwendung in tarife and tarife[verwendung] is None:
            tarife[verwendung] = preis

    # Fallback: WP/Wallbox → allgemein
    allgemein = tarife["allgemein"]
    if tarife["waermepumpe"] is None:
        tarife["waermepumpe"] = allgemein
    if tarife["wallbox"] is None:
        tarife["wallbox"] = allgemein

    return tarife


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.get("/", response_model=list[StrompreisResponse])
async def list_strompreise(
    anlage_id: Optional[int] = Query(None, description="Filter nach Anlage"),
    aktuell: Optional[bool] = Query(None, description="Nur aktuell gültige"),
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt Strompreise zurück, optional gefiltert.

    Args:
        anlage_id: Optional - nur Preise dieser Anlage
        aktuell: Optional - nur aktuell gültige Tarife

    Returns:
        list[StrompreisResponse]: Liste der Strompreise
    """
    query = select(Strompreis)

    if anlage_id:
        query = query.where(Strompreis.anlage_id == anlage_id)

    if aktuell:
        today = date.today()
        query = query.where(
            and_(
                Strompreis.gueltig_ab <= today,
                (Strompreis.gueltig_bis.is_(None) | (Strompreis.gueltig_bis >= today))
            )
        )

    query = query.order_by(Strompreis.gueltig_ab.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/aktuell/{anlage_id}", response_model=StrompreisResponse)
async def get_aktueller_strompreis(anlage_id: int, db: AsyncSession = Depends(get_db)):
    """
    Gibt den aktuell gültigen Strompreis einer Anlage zurück.

    Args:
        anlage_id: ID der Anlage

    Returns:
        StrompreisResponse: Der aktuelle Tarif

    Raises:
        404: Kein aktueller Tarif gefunden
    """
    today = date.today()
    query = select(Strompreis).where(
        Strompreis.anlage_id == anlage_id,
        Strompreis.gueltig_ab <= today,
        (Strompreis.gueltig_bis.is_(None) | (Strompreis.gueltig_bis >= today))
    ).order_by(Strompreis.gueltig_ab.desc()).limit(1)

    result = await db.execute(query)
    preis = result.scalar_one_or_none()

    if not preis:
        raise HTTPException(
            status_code=404,
            detail="Kein aktueller Strompreis für diese Anlage gefunden"
        )

    return preis


@router.get("/aktuell/{anlage_id}/{verwendung}", response_model=StrompreisResponse)
async def get_aktueller_strompreis_fuer(
    anlage_id: int,
    verwendung: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt den aktuellen Tarif für eine bestimmte Verwendung zurück.
    Fällt auf 'allgemein' zurück wenn kein Spezialtarif existiert.
    """
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    preis = tarife.get(verwendung) or tarife.get("allgemein")

    if not preis:
        raise HTTPException(
            status_code=404,
            detail=f"Kein aktueller Strompreis für Verwendung '{verwendung}' gefunden"
        )

    return preis


@router.get("/{strompreis_id}", response_model=StrompreisResponse)
async def get_strompreis(strompreis_id: int, db: AsyncSession = Depends(get_db)):
    """
    Gibt einen einzelnen Strompreis zurück.

    Args:
        strompreis_id: ID des Strompreises

    Returns:
        StrompreisResponse: Der Strompreis

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Strompreis).where(Strompreis.id == strompreis_id))
    preis = result.scalar_one_or_none()

    if not preis:
        raise HTTPException(status_code=404, detail="Strompreis nicht gefunden")

    return preis


@router.post("/", response_model=StrompreisResponse, status_code=status.HTTP_201_CREATED)
async def create_strompreis(data: StrompreisCreate, db: AsyncSession = Depends(get_db)):
    """
    Erstellt einen neuen Strompreis.

    Args:
        data: Strompreis-Daten

    Returns:
        StrompreisResponse: Der erstellte Strompreis

    Raises:
        404: Anlage nicht gefunden
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == data.anlage_id))
    if not anlage_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    preis = Strompreis(**data.model_dump())
    db.add(preis)
    await db.flush()
    await db.refresh(preis)
    return preis


@router.put("/{strompreis_id}", response_model=StrompreisResponse)
async def update_strompreis(
    strompreis_id: int,
    data: StrompreisUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Aktualisiert einen Strompreis.

    Args:
        strompreis_id: ID des Strompreises
        data: Zu aktualisierende Felder

    Returns:
        StrompreisResponse: Der aktualisierte Strompreis

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Strompreis).where(Strompreis.id == strompreis_id))
    preis = result.scalar_one_or_none()

    if not preis:
        raise HTTPException(status_code=404, detail="Strompreis nicht gefunden")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(preis, field, value)

    await db.flush()
    await db.refresh(preis)
    return preis


@router.delete("/{strompreis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_strompreis(strompreis_id: int, db: AsyncSession = Depends(get_db)):
    """
    Löscht einen Strompreis.

    Args:
        strompreis_id: ID des Strompreises

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Strompreis).where(Strompreis.id == strompreis_id))
    preis = result.scalar_one_or_none()

    if not preis:
        raise HTTPException(status_code=404, detail="Strompreis nicht gefunden")

    await db.delete(preis)
