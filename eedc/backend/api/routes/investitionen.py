"""
Investitionen API Routes

CRUD Endpoints für Investitionen (E-Auto, Wärmepumpe, Speicher, etc.).
"""

from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from datetime import date

from backend.api.deps import get_db
from backend.models.investition import Investition, InvestitionTyp
from backend.models.anlage import Anlage


# =============================================================================
# Pydantic Schemas
# =============================================================================

class InvestitionBase(BaseModel):
    """Basis-Schema für Investition."""
    typ: str = Field(..., description="Investitionstyp (e-auto, speicher, etc.)")
    bezeichnung: str = Field(..., min_length=1, max_length=255)
    anschaffungsdatum: Optional[date] = None
    anschaffungskosten_gesamt: Optional[float] = Field(None, ge=0)
    anschaffungskosten_alternativ: Optional[float] = Field(None, ge=0)
    betriebskosten_jahr: Optional[float] = Field(None, ge=0)
    parameter: Optional[dict[str, Any]] = None
    aktiv: bool = True
    parent_investition_id: Optional[int] = None


class InvestitionCreate(InvestitionBase):
    """Schema für Investition-Erstellung."""
    anlage_id: int


class InvestitionUpdate(BaseModel):
    """Schema für Investition-Update."""
    bezeichnung: Optional[str] = Field(None, min_length=1, max_length=255)
    anschaffungsdatum: Optional[date] = None
    anschaffungskosten_gesamt: Optional[float] = Field(None, ge=0)
    anschaffungskosten_alternativ: Optional[float] = Field(None, ge=0)
    betriebskosten_jahr: Optional[float] = Field(None, ge=0)
    parameter: Optional[dict[str, Any]] = None
    aktiv: Optional[bool] = None
    parent_investition_id: Optional[int] = None


class InvestitionResponse(InvestitionBase):
    """Schema für Investition-Response."""
    id: int
    anlage_id: int
    einsparung_prognose_jahr: Optional[float]
    co2_einsparung_prognose_kg: Optional[float]

    class Config:
        from_attributes = True


class InvestitionTypInfo(BaseModel):
    """Info über einen Investitionstyp."""
    typ: str
    label: str
    beschreibung: str
    parameter_schema: dict[str, Any]


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.get("/typen", response_model=list[InvestitionTypInfo])
async def list_investition_typen():
    """
    Gibt alle verfügbaren Investitionstypen mit Parameter-Schema zurück.

    Dies hilft dem Frontend, dynamische Formulare zu erstellen.

    Returns:
        list[InvestitionTypInfo]: Liste der Typen mit Schema
    """
    return [
        InvestitionTypInfo(
            typ=InvestitionTyp.E_AUTO.value,
            label="E-Auto",
            beschreibung="Elektrofahrzeug mit optionalem V2H",
            parameter_schema={
                "km_jahr": {"type": "number", "label": "Jahresfahrleistung (km)", "required": True},
                "verbrauch_kwh_100km": {"type": "number", "label": "Verbrauch (kWh/100km)", "required": True},
                "pv_anteil_prozent": {"type": "number", "label": "PV-Anteil Ladung (%)", "default": 60},
                "benzinpreis_euro": {"type": "number", "label": "Benzinpreis (Euro/L)", "default": 1.85},
                "nutzt_v2h": {"type": "boolean", "label": "V2H aktiv", "default": False},
                "v2h_entlade_preis_cent": {"type": "number", "label": "V2H Entladepreis (ct/kWh)"},
            }
        ),
        InvestitionTypInfo(
            typ=InvestitionTyp.WAERMEPUMPE.value,
            label="Wärmepumpe",
            beschreibung="Wärmepumpe für Heizung/Warmwasser",
            parameter_schema={
                "jaz": {"type": "number", "label": "Jahresarbeitszahl (JAZ)", "required": True},
                "waermebedarf_kwh": {"type": "number", "label": "Wärmebedarf (kWh/Jahr)", "required": True},
                "pv_anteil_prozent": {"type": "number", "label": "PV-Anteil (%)", "default": 30},
                "alter_energietraeger": {"type": "select", "label": "Alter Energieträger",
                                         "options": ["gas", "oel", "strom"]},
                "alter_preis_cent_kwh": {"type": "number", "label": "Alter Preis (ct/kWh)"},
            }
        ),
        InvestitionTypInfo(
            typ=InvestitionTyp.SPEICHER.value,
            label="Batteriespeicher",
            beschreibung="Stromspeicher mit optionaler Arbitrage",
            parameter_schema={
                "kapazitaet_kwh": {"type": "number", "label": "Kapazität (kWh)", "required": True},
                "wirkungsgrad_prozent": {"type": "number", "label": "Wirkungsgrad (%)", "default": 95},
                "nutzt_arbitrage": {"type": "boolean", "label": "Arbitrage aktiv", "default": False},
                "lade_durchschnittspreis_cent": {"type": "number", "label": "Ø Ladepreis Arbitrage (ct/kWh)"},
                "entlade_vermiedener_preis_cent": {"type": "number", "label": "Ø Entladepreis Arbitrage (ct/kWh)"},
            }
        ),
        InvestitionTypInfo(
            typ=InvestitionTyp.WALLBOX.value,
            label="Wallbox",
            beschreibung="Ladestation für E-Fahrzeuge",
            parameter_schema={
                "leistung_kw": {"type": "number", "label": "Ladeleistung (kW)", "required": True},
            }
        ),
        InvestitionTypInfo(
            typ=InvestitionTyp.WECHSELRICHTER.value,
            label="Wechselrichter",
            beschreibung="PV-Wechselrichter",
            parameter_schema={
                "leistung_ac_kw": {"type": "number", "label": "AC-Leistung (kW)", "required": True},
                "leistung_dc_kw": {"type": "number", "label": "DC-Leistung (kW)"},
                "wirkungsgrad_prozent": {"type": "number", "label": "Wirkungsgrad (%)", "default": 97},
                "hersteller": {"type": "string", "label": "Hersteller"},
                "modell": {"type": "string", "label": "Modell"},
            }
        ),
        InvestitionTypInfo(
            typ=InvestitionTyp.PV_MODULE.value,
            label="PV-Module",
            beschreibung="Photovoltaik-Module (Strings)",
            parameter_schema={
                "leistung_kwp": {"type": "number", "label": "Leistung (kWp)", "required": True},
                "anzahl_module": {"type": "integer", "label": "Anzahl Module"},
                "ausrichtung": {"type": "select", "label": "Ausrichtung",
                               "options": ["Süd", "Südost", "Südwest", "Ost", "West", "Ost-West"]},
                "neigung_grad": {"type": "number", "label": "Neigung (°)"},
                "hersteller": {"type": "string", "label": "Hersteller"},
                "modell": {"type": "string", "label": "Modell"},
                "jahresertrag_prognose_kwh": {"type": "number", "label": "Jahresertrag Prognose (kWh)"},
            }
        ),
        InvestitionTypInfo(
            typ=InvestitionTyp.BALKONKRAFTWERK.value,
            label="Balkonkraftwerk",
            beschreibung="Mini-PV-Anlage",
            parameter_schema={
                "leistung_wp": {"type": "number", "label": "Leistung (Wp)", "required": True},
                "jahresertrag_prognose_kwh": {"type": "number", "label": "Jahresertrag Prognose (kWh)"},
            }
        ),
        InvestitionTypInfo(
            typ=InvestitionTyp.SONSTIGES.value,
            label="Sonstiges",
            beschreibung="Andere Investition",
            parameter_schema={
                "beschreibung": {"type": "string", "label": "Beschreibung"},
            }
        ),
    ]


@router.get("/", response_model=list[InvestitionResponse])
async def list_investitionen(
    anlage_id: Optional[int] = Query(None, description="Filter nach Anlage"),
    typ: Optional[str] = Query(None, description="Filter nach Typ"),
    aktiv: Optional[bool] = Query(None, description="Filter nach Status"),
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt Investitionen zurück, optional gefiltert.

    Args:
        anlage_id: Optional - nur Investitionen dieser Anlage
        typ: Optional - nur dieser Investitionstyp
        aktiv: Optional - nur aktive/inaktive

    Returns:
        list[InvestitionResponse]: Liste der Investitionen
    """
    query = select(Investition)

    if anlage_id:
        query = query.where(Investition.anlage_id == anlage_id)
    if typ:
        query = query.where(Investition.typ == typ)
    if aktiv is not None:
        query = query.where(Investition.aktiv == aktiv)

    query = query.order_by(Investition.typ, Investition.bezeichnung)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{investition_id}", response_model=InvestitionResponse)
async def get_investition(investition_id: int, db: AsyncSession = Depends(get_db)):
    """
    Gibt eine einzelne Investition zurück.

    Args:
        investition_id: ID der Investition

    Returns:
        InvestitionResponse: Die Investition

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Investition).where(Investition.id == investition_id))
    inv = result.scalar_one_or_none()

    if not inv:
        raise HTTPException(status_code=404, detail="Investition nicht gefunden")

    return inv


@router.post("/", response_model=InvestitionResponse, status_code=status.HTTP_201_CREATED)
async def create_investition(data: InvestitionCreate, db: AsyncSession = Depends(get_db)):
    """
    Erstellt eine neue Investition.

    Args:
        data: Investitions-Daten

    Returns:
        InvestitionResponse: Die erstellte Investition

    Raises:
        404: Anlage nicht gefunden
        400: Ungültiger Typ
    """
    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == data.anlage_id))
    if not anlage_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Typ validieren
    valid_types = [t.value for t in InvestitionTyp]
    if data.typ not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Ungültiger Typ. Erlaubt: {valid_types}"
        )

    inv = Investition(**data.model_dump())
    db.add(inv)
    await db.flush()
    await db.refresh(inv)
    return inv


@router.put("/{investition_id}", response_model=InvestitionResponse)
async def update_investition(
    investition_id: int,
    data: InvestitionUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Aktualisiert eine Investition.

    Args:
        investition_id: ID der Investition
        data: Zu aktualisierende Felder

    Returns:
        InvestitionResponse: Die aktualisierte Investition

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Investition).where(Investition.id == investition_id))
    inv = result.scalar_one_or_none()

    if not inv:
        raise HTTPException(status_code=404, detail="Investition nicht gefunden")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(inv, field, value)

    await db.flush()
    await db.refresh(inv)
    return inv


@router.delete("/{investition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_investition(investition_id: int, db: AsyncSession = Depends(get_db)):
    """
    Löscht eine Investition.

    Args:
        investition_id: ID der Investition

    Raises:
        404: Nicht gefunden
    """
    result = await db.execute(select(Investition).where(Investition.id == investition_id))
    inv = result.scalar_one_or_none()

    if not inv:
        raise HTTPException(status_code=404, detail="Investition nicht gefunden")

    await db.delete(inv)
