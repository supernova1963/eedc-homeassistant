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


# =============================================================================
# ROI Berechnungen
# =============================================================================

class ROIBerechnung(BaseModel):
    """Ergebnis einer ROI-Berechnung für eine Investition."""
    investition_id: int
    investition_bezeichnung: str
    investition_typ: str
    anschaffungskosten: float
    anschaffungskosten_alternativ: float
    relevante_kosten: float
    jahres_einsparung: float
    roi_prozent: Optional[float]
    amortisation_jahre: Optional[float]
    co2_einsparung_kg: Optional[float]
    detail_berechnung: dict[str, Any]


class ROIDashboardResponse(BaseModel):
    """Gesamte ROI-Übersicht für eine Anlage."""
    anlage_id: int
    anlage_name: str
    gesamt_investition: float
    gesamt_relevante_kosten: float
    gesamt_jahres_einsparung: float
    gesamt_roi_prozent: Optional[float]
    gesamt_amortisation_jahre: Optional[float]
    gesamt_co2_einsparung_kg: float
    berechnungen: list[ROIBerechnung]


@router.get("/roi/{anlage_id}", response_model=ROIDashboardResponse)
async def get_roi_dashboard(
    anlage_id: int,
    strompreis_cent: float = Query(30.0, description="Strompreis in Cent/kWh"),
    einspeiseverguetung_cent: float = Query(8.2, description="Einspeisevergütung in Cent/kWh"),
    benzinpreis_euro: float = Query(1.85, description="Benzinpreis in Euro/Liter"),
    db: AsyncSession = Depends(get_db)
):
    """
    Berechnet ROI für alle aktiven Investitionen einer Anlage.

    Args:
        anlage_id: ID der Anlage
        strompreis_cent: Aktueller Strompreis für Berechnungen
        einspeiseverguetung_cent: Aktuelle Einspeisevergütung
        benzinpreis_euro: Aktueller Benzinpreis für E-Auto-Vergleich

    Returns:
        ROIDashboardResponse: Vollständige ROI-Übersicht
    """
    from backend.core.calculations import (
        berechne_speicher_einsparung,
        berechne_eauto_einsparung,
        berechne_waermepumpe_einsparung,
        berechne_roi,
    )

    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Investitionen laden
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.aktiv == True)
        .order_by(Investition.typ)
    )
    investitionen = inv_result.scalars().all()

    berechnungen: list[ROIBerechnung] = []
    gesamt_investition = 0.0
    gesamt_relevante = 0.0
    gesamt_einsparung = 0.0
    gesamt_co2 = 0.0

    for inv in investitionen:
        params = inv.parameter or {}
        kosten = inv.anschaffungskosten_gesamt or 0
        alternativ = inv.anschaffungskosten_alternativ or 0
        relevante = kosten - alternativ
        jahres_einsparung = 0.0
        co2_einsparung = 0.0
        detail = {}

        if inv.typ == InvestitionTyp.SPEICHER.value:
            # Speicher-Berechnung
            kapazitaet = params.get('kapazitaet_kwh', 10)
            wirkungsgrad = params.get('wirkungsgrad_prozent', 95)
            nutzt_arbitrage = params.get('nutzt_arbitrage', False)
            lade_preis = params.get('lade_durchschnittspreis_cent', 12)
            entlade_preis = params.get('entlade_vermiedener_preis_cent', 35)

            result = berechne_speicher_einsparung(
                kapazitaet_kwh=kapazitaet,
                wirkungsgrad_prozent=wirkungsgrad,
                netzbezug_preis_cent=strompreis_cent,
                einspeiseverguetung_cent=einspeiseverguetung_cent,
                nutzt_arbitrage=nutzt_arbitrage,
                lade_preis_cent=lade_preis,
                entlade_preis_cent=entlade_preis,
            )
            jahres_einsparung = result.jahres_einsparung_euro
            co2_einsparung = result.co2_einsparung_kg
            detail = {
                'nutzbare_speicherung_kwh': result.nutzbare_speicherung_kwh,
                'pv_anteil_euro': result.pv_anteil_euro,
                'arbitrage_anteil_euro': result.arbitrage_anteil_euro,
            }

        elif inv.typ == InvestitionTyp.E_AUTO.value:
            # E-Auto-Berechnung
            km_jahr = params.get('km_jahr', 15000)
            verbrauch = params.get('verbrauch_kwh_100km', 18)
            pv_anteil = params.get('pv_anteil_prozent', 60)
            benzin_verbrauch = params.get('benzin_verbrauch_liter_100km', 7.0)
            nutzt_v2h = params.get('nutzt_v2h', False)
            v2h_entladung = params.get('v2h_entladung_kwh_jahr', 0)
            v2h_preis = params.get('v2h_entlade_preis_cent', strompreis_cent)

            result = berechne_eauto_einsparung(
                km_jahr=km_jahr,
                verbrauch_kwh_100km=verbrauch,
                pv_anteil_prozent=pv_anteil,
                strompreis_cent=strompreis_cent,
                benzinpreis_euro_liter=benzinpreis_euro,
                benzin_verbrauch_liter_100km=benzin_verbrauch,
                nutzt_v2h=nutzt_v2h,
                v2h_entladung_kwh_jahr=v2h_entladung,
                v2h_preis_cent=v2h_preis,
            )
            jahres_einsparung = result.jahres_einsparung_euro
            co2_einsparung = result.co2_einsparung_kg
            detail = {
                'strom_kosten_euro': result.strom_kosten_euro,
                'benzin_kosten_alternativ_euro': result.benzin_kosten_alternativ_euro,
                'v2h_einsparung_euro': result.v2h_einsparung_euro,
            }

        elif inv.typ == InvestitionTyp.WAERMEPUMPE.value:
            # Wärmepumpen-Berechnung
            jaz = params.get('jaz', 3.5)
            waermebedarf = params.get('waermebedarf_kwh', 15000)
            pv_anteil = params.get('pv_anteil_prozent', 30)
            alter_energietraeger = params.get('alter_energietraeger', 'gas')
            alter_preis = params.get('alter_preis_cent_kwh', 12)

            result = berechne_waermepumpe_einsparung(
                waermebedarf_kwh=waermebedarf,
                jaz=jaz,
                strompreis_cent=strompreis_cent,
                pv_anteil_prozent=pv_anteil,
                alter_energietraeger=alter_energietraeger,
                alter_preis_cent_kwh=alter_preis,
            )
            jahres_einsparung = result.jahres_einsparung_euro
            co2_einsparung = result.co2_einsparung_kg
            detail = {
                'wp_kosten_euro': result.wp_kosten_euro,
                'alte_heizung_kosten_euro': result.alte_heizung_kosten_euro,
            }

        else:
            # Für andere Typen: manuelle Einsparungsprognose verwenden
            jahres_einsparung = inv.einsparung_prognose_jahr or 0
            co2_einsparung = inv.co2_einsparung_prognose_kg or 0
            detail = {'hinweis': 'Manuelle Prognose verwendet'}

        # ROI berechnen
        roi_result = berechne_roi(kosten, jahres_einsparung, alternativ)

        berechnungen.append(ROIBerechnung(
            investition_id=inv.id,
            investition_bezeichnung=inv.bezeichnung,
            investition_typ=inv.typ,
            anschaffungskosten=kosten,
            anschaffungskosten_alternativ=alternativ,
            relevante_kosten=relevante,
            jahres_einsparung=jahres_einsparung,
            roi_prozent=roi_result['roi_prozent'],
            amortisation_jahre=roi_result['amortisation_jahre'],
            co2_einsparung_kg=co2_einsparung,
            detail_berechnung=detail,
        ))

        gesamt_investition += kosten
        gesamt_relevante += relevante
        gesamt_einsparung += jahres_einsparung
        gesamt_co2 += co2_einsparung

    # Gesamt-ROI
    gesamt_roi = berechne_roi(gesamt_investition, gesamt_einsparung, gesamt_investition - gesamt_relevante)

    return ROIDashboardResponse(
        anlage_id=anlage_id,
        anlage_name=anlage.anlagenname,
        gesamt_investition=round(gesamt_investition, 2),
        gesamt_relevante_kosten=round(gesamt_relevante, 2),
        gesamt_jahres_einsparung=round(gesamt_einsparung, 2),
        gesamt_roi_prozent=gesamt_roi['roi_prozent'],
        gesamt_amortisation_jahre=gesamt_roi['amortisation_jahre'],
        gesamt_co2_einsparung_kg=round(gesamt_co2, 1),
        berechnungen=berechnungen,
    )
