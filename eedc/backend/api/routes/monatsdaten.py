"""
Monatsdaten API Routes

CRUD Endpoints für monatliche Energiedaten.
"""

from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from backend.api.deps import get_db
from backend.models.monatsdaten import Monatsdaten
from backend.models.anlage import Anlage
from backend.models.strompreis import Strompreis
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.core.calculations import berechne_monatskennzahlen, MonatsKennzahlen


# =============================================================================
# Pydantic Schemas
# =============================================================================

class MonatsdatenBase(BaseModel):
    """Basis-Schema für Monatsdaten."""
    jahr: int = Field(..., ge=2000, le=2100)
    monat: int = Field(..., ge=1, le=12)
    einspeisung_kwh: float = Field(..., ge=0)
    netzbezug_kwh: float = Field(..., ge=0)
    pv_erzeugung_kwh: Optional[float] = Field(None, ge=0)
    batterie_ladung_kwh: Optional[float] = Field(None, ge=0)
    batterie_entladung_kwh: Optional[float] = Field(None, ge=0)
    batterie_ladung_netz_kwh: Optional[float] = Field(None, ge=0)
    batterie_ladepreis_cent: Optional[float] = Field(None, ge=0)
    globalstrahlung_kwh_m2: Optional[float] = Field(None, ge=0)
    sonnenstunden: Optional[float] = Field(None, ge=0)
    datenquelle: Optional[str] = Field(None, max_length=50)
    notizen: Optional[str] = Field(None, max_length=1000)


class MonatsdatenCreate(MonatsdatenBase):
    """Schema für Monatsdaten-Erstellung."""
    anlage_id: int
    # Investitions-spezifische Monatsdaten (E-Auto km, Speicher Ladung, WP Verbrauch, etc.)
    investitionen_daten: Optional[dict[str, dict[str, Any]]] = None


class MonatsdatenUpdate(BaseModel):
    """Schema für Monatsdaten-Update."""
    einspeisung_kwh: Optional[float] = Field(None, ge=0)
    netzbezug_kwh: Optional[float] = Field(None, ge=0)
    # Investitions-spezifische Monatsdaten
    investitionen_daten: Optional[dict[str, dict[str, Any]]] = None
    pv_erzeugung_kwh: Optional[float] = Field(None, ge=0)
    batterie_ladung_kwh: Optional[float] = Field(None, ge=0)
    batterie_entladung_kwh: Optional[float] = Field(None, ge=0)
    batterie_ladung_netz_kwh: Optional[float] = Field(None, ge=0)
    batterie_ladepreis_cent: Optional[float] = Field(None, ge=0)
    globalstrahlung_kwh_m2: Optional[float] = Field(None, ge=0)
    sonnenstunden: Optional[float] = Field(None, ge=0)
    notizen: Optional[str] = Field(None, max_length=1000)


class KennzahlenResponse(BaseModel):
    """Berechnete Kennzahlen."""
    direktverbrauch_kwh: float
    gesamtverbrauch_kwh: float
    eigenverbrauch_kwh: float
    eigenverbrauchsquote_prozent: float
    autarkiegrad_prozent: float
    spezifischer_ertrag_kwh_kwp: Optional[float]
    einspeise_erloes_euro: float
    netzbezug_kosten_euro: float
    eigenverbrauch_ersparnis_euro: float
    netto_ertrag_euro: float
    co2_einsparung_kg: float


class MonatsdatenResponse(MonatsdatenBase):
    """Schema für Monatsdaten-Response."""
    id: int
    anlage_id: int
    direktverbrauch_kwh: Optional[float]
    eigenverbrauch_kwh: Optional[float]
    gesamtverbrauch_kwh: Optional[float]

    class Config:
        from_attributes = True


class MonatsdatenMitKennzahlen(MonatsdatenResponse):
    """Monatsdaten mit berechneten Kennzahlen."""
    kennzahlen: Optional[KennzahlenResponse] = None


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.get("/", response_model=list[MonatsdatenResponse])
async def list_monatsdaten(
    anlage_id: Optional[int] = Query(None, description="Filter nach Anlage"),
    jahr: Optional[int] = Query(None, description="Filter nach Jahr"),
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt Monatsdaten zurück, optional gefiltert.

    Args:
        anlage_id: Optional - nur Daten dieser Anlage
        jahr: Optional - nur Daten dieses Jahres

    Returns:
        list[MonatsdatenResponse]: Liste der Monatsdaten
    """
    query = select(Monatsdaten)

    if anlage_id:
        query = query.where(Monatsdaten.anlage_id == anlage_id)
    if jahr:
        query = query.where(Monatsdaten.jahr == jahr)

    query = query.order_by(Monatsdaten.jahr.desc(), Monatsdaten.monat.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{monatsdaten_id}", response_model=MonatsdatenMitKennzahlen)
async def get_monatsdaten(monatsdaten_id: int, db: AsyncSession = Depends(get_db)):
    """
    Gibt einzelne Monatsdaten mit berechneten Kennzahlen zurück.

    Args:
        monatsdaten_id: ID der Monatsdaten

    Returns:
        MonatsdatenMitKennzahlen: Monatsdaten inkl. Kennzahlen

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Monatsdaten).where(Monatsdaten.id == monatsdaten_id))
    md = result.scalar_one_or_none()

    if not md:
        raise HTTPException(status_code=404, detail="Monatsdaten nicht gefunden")

    # Anlage und Strompreis laden für Kennzahlen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == md.anlage_id))
    anlage = anlage_result.scalar_one()

    # Aktuellen Strompreis finden
    from datetime import date
    preis_query = select(Strompreis).where(
        Strompreis.anlage_id == md.anlage_id,
        Strompreis.gueltig_ab <= date(md.jahr, md.monat, 1)
    ).order_by(Strompreis.gueltig_ab.desc()).limit(1)

    preis_result = await db.execute(preis_query)
    strompreis = preis_result.scalar_one_or_none()

    # Kennzahlen berechnen
    kennzahlen = berechne_monatskennzahlen(
        einspeisung_kwh=md.einspeisung_kwh,
        netzbezug_kwh=md.netzbezug_kwh,
        pv_erzeugung_kwh=md.pv_erzeugung_kwh or 0,
        batterie_ladung_kwh=md.batterie_ladung_kwh or 0,
        batterie_entladung_kwh=md.batterie_entladung_kwh or 0,
        einspeiseverguetung_cent=strompreis.einspeiseverguetung_cent_kwh if strompreis else 8.2,
        netzbezug_preis_cent=strompreis.netzbezug_arbeitspreis_cent_kwh if strompreis else 30.0,
        leistung_kwp=anlage.leistung_kwp,
    )

    response = MonatsdatenMitKennzahlen.model_validate(md)
    response.kennzahlen = KennzahlenResponse(**kennzahlen.__dict__)
    return response


@router.post("/", response_model=MonatsdatenResponse, status_code=status.HTTP_201_CREATED)
async def create_monatsdaten(data: MonatsdatenCreate, db: AsyncSession = Depends(get_db)):
    """
    Erstellt neue Monatsdaten.

    Args:
        data: Monatsdaten

    Returns:
        MonatsdatenResponse: Die erstellten Monatsdaten

    Raises:
        404: Anlage nicht gefunden
        409: Monat existiert bereits
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == data.anlage_id))
    if not anlage_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Duplikat prüfen
    existing = await db.execute(
        select(Monatsdaten).where(
            Monatsdaten.anlage_id == data.anlage_id,
            Monatsdaten.jahr == data.jahr,
            Monatsdaten.monat == data.monat
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Monatsdaten für {data.monat}/{data.jahr} existieren bereits"
        )

    # investitionen_daten separat extrahieren (nicht Teil des Monatsdaten-Models)
    investitionen_daten = data.investitionen_daten
    md_data = data.model_dump(exclude={'investitionen_daten'})
    md = Monatsdaten(**md_data)

    # Berechnete Felder (werden berechnet wenn pv_erzeugung vorhanden)
    if md.pv_erzeugung_kwh is not None:
        md.direktverbrauch_kwh = max(0, md.pv_erzeugung_kwh - md.einspeisung_kwh - (md.batterie_ladung_kwh or 0))
        md.eigenverbrauch_kwh = md.direktverbrauch_kwh + (md.batterie_entladung_kwh or 0)
        md.gesamtverbrauch_kwh = md.eigenverbrauch_kwh + md.netzbezug_kwh
    elif md.einspeisung_kwh > 0 or md.netzbezug_kwh > 0:
        # Fallback: Gesamtverbrauch kann geschätzt werden
        md.gesamtverbrauch_kwh = md.netzbezug_kwh + md.einspeisung_kwh

    db.add(md)
    await db.flush()
    await db.refresh(md)

    # Investitions-Monatsdaten speichern (E-Auto km, Speicher Ladung, WP Verbrauch, etc.)
    if investitionen_daten:
        await _save_investitionen_monatsdaten(db, investitionen_daten, data.jahr, data.monat)

    return md


async def _save_investitionen_monatsdaten(
    db: AsyncSession,
    investitionen_daten: dict[str, dict[str, Any]],
    jahr: int,
    monat: int
) -> None:
    """
    Speichert Investitions-spezifische Monatsdaten (E-Auto km, Speicher Ladung, etc.).

    Args:
        db: Datenbank-Session
        investitionen_daten: Dict mit investition_id als Key und verbrauch_daten als Value
        jahr: Jahr
        monat: Monat
    """
    for inv_id_str, verbrauch_daten in investitionen_daten.items():
        try:
            inv_id = int(inv_id_str)
        except ValueError:
            continue

        # Prüfen ob Investition existiert
        inv_result = await db.execute(select(Investition).where(Investition.id == inv_id))
        if not inv_result.scalar_one_or_none():
            continue

        # Existierende InvestitionMonatsdaten für diesen Monat suchen
        existing_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id == inv_id)
            .where(InvestitionMonatsdaten.jahr == jahr)
            .where(InvestitionMonatsdaten.monat == monat)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            # Update existierende Daten
            existing.verbrauch_daten = verbrauch_daten
        else:
            # Neue Daten erstellen
            imd = InvestitionMonatsdaten(
                investition_id=inv_id,
                jahr=jahr,
                monat=monat,
                verbrauch_daten=verbrauch_daten
            )
            db.add(imd)

    await db.flush()


@router.put("/{monatsdaten_id}", response_model=MonatsdatenResponse)
async def update_monatsdaten(
    monatsdaten_id: int,
    data: MonatsdatenUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Aktualisiert Monatsdaten.

    Args:
        monatsdaten_id: ID der Monatsdaten
        data: Zu aktualisierende Felder

    Returns:
        MonatsdatenResponse: Die aktualisierten Monatsdaten

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Monatsdaten).where(Monatsdaten.id == monatsdaten_id))
    md = result.scalar_one_or_none()

    if not md:
        raise HTTPException(status_code=404, detail="Monatsdaten nicht gefunden")

    # investitionen_daten separat behandeln
    investitionen_daten = data.investitionen_daten
    update_data = data.model_dump(exclude_unset=True, exclude={'investitionen_daten'})
    for field, value in update_data.items():
        setattr(md, field, value)

    # Berechnete Felder aktualisieren (werden berechnet wenn pv_erzeugung vorhanden)
    if md.pv_erzeugung_kwh is not None:
        md.direktverbrauch_kwh = max(0, md.pv_erzeugung_kwh - md.einspeisung_kwh - (md.batterie_ladung_kwh or 0))
        md.eigenverbrauch_kwh = md.direktverbrauch_kwh + (md.batterie_entladung_kwh or 0)
        md.gesamtverbrauch_kwh = md.eigenverbrauch_kwh + md.netzbezug_kwh
    elif md.einspeisung_kwh > 0 or md.netzbezug_kwh > 0:
        # Fallback: Gesamtverbrauch kann geschätzt werden
        md.gesamtverbrauch_kwh = md.netzbezug_kwh + md.einspeisung_kwh

    await db.flush()
    await db.refresh(md)

    # Investitions-Monatsdaten speichern
    if investitionen_daten:
        await _save_investitionen_monatsdaten(db, investitionen_daten, md.jahr, md.monat)

    return md


@router.delete("/{monatsdaten_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_monatsdaten(monatsdaten_id: int, db: AsyncSession = Depends(get_db)):
    """
    Löscht Monatsdaten.

    Args:
        monatsdaten_id: ID der Monatsdaten

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Monatsdaten).where(Monatsdaten.id == monatsdaten_id))
    md = result.scalar_one_or_none()

    if not md:
        raise HTTPException(status_code=404, detail="Monatsdaten nicht gefunden")

    await db.delete(md)
