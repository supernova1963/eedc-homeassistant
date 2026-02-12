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
from backend.models.investition import Investition, InvestitionTyp, InvestitionMonatsdaten
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.strompreis import Strompreis


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
    # PV-Module spezifische Felder
    leistung_kwp: Optional[float] = Field(None, ge=0, description="Leistung in kWp (für PV-Module)")
    ausrichtung: Optional[str] = Field(None, max_length=50, description="Ausrichtung (Süd, Ost, West, etc.)")
    neigung_grad: Optional[float] = Field(None, ge=0, le=90, description="Modulneigung in Grad")
    ha_entity_id: Optional[str] = Field(None, max_length=255, description="Home Assistant Entity-ID für String-Daten")


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
    # PV-Module spezifische Felder
    leistung_kwp: Optional[float] = Field(None, ge=0)
    ausrichtung: Optional[str] = Field(None, max_length=50)
    neigung_grad: Optional[float] = Field(None, ge=0, le=90)
    ha_entity_id: Optional[str] = Field(None, max_length=255)


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
                # Modus-Auswahl
                "effizienz_modus": {
                    "type": "select",
                    "label": "Berechnungsmodus",
                    "options": ["gesamt_jaz", "getrennte_cops"],
                    "default": "gesamt_jaz",
                },
                # Für Modus "gesamt_jaz"
                "jaz": {
                    "type": "number",
                    "label": "Jahresarbeitszahl (JAZ)",
                    "default": 3.5,
                    "conditional": {"effizienz_modus": "gesamt_jaz"},
                },
                # Für Modus "getrennte_cops"
                "cop_heizung": {
                    "type": "number",
                    "label": "COP Heizung",
                    "default": 3.9,
                    "conditional": {"effizienz_modus": "getrennte_cops"},
                },
                "cop_warmwasser": {
                    "type": "number",
                    "label": "COP Warmwasser",
                    "default": 3.0,
                    "conditional": {"effizienz_modus": "getrennte_cops"},
                },
                # Wärmebedarf (getrennt für bessere Gewichtung)
                "heizwaermebedarf_kwh": {
                    "type": "number",
                    "label": "Heizwärmebedarf (kWh/Jahr)",
                    "default": 12000,
                },
                "warmwasserbedarf_kwh": {
                    "type": "number",
                    "label": "Warmwasserbedarf (kWh/Jahr)",
                    "default": 3000,
                },
                # Vergleich mit alter Heizung
                "pv_anteil_prozent": {"type": "number", "label": "PV-Anteil (%)", "default": 30},
                "alter_energietraeger": {
                    "type": "select",
                    "label": "Alter Energieträger",
                    "options": ["gas", "oel", "strom"],
                    "default": "gas",
                },
                "alter_preis_cent_kwh": {"type": "number", "label": "Alter Preis (ct/kWh)", "default": 12},
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


class ParentOption(BaseModel):
    """Verfügbare Parent-Investition."""
    id: int
    bezeichnung: str
    typ: str
    required: bool = False


@router.get("/parent-options/{anlage_id}", response_model=dict[str, list[ParentOption]])
async def get_parent_options(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt verfügbare Parent-Optionen für jeden Typ zurück.

    Returns:
        dict: Typ -> Liste der möglichen Parents

    Beispiel:
        {
            "pv-module": [{"id": 1, "bezeichnung": "Fronius GEN24", "typ": "wechselrichter", "required": true}],
            "speicher": [{"id": 1, "bezeichnung": "Fronius GEN24", "typ": "wechselrichter", "required": false}]
        }
    """
    # Wechselrichter der Anlage laden
    wr_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.WECHSELRICHTER.value)
        .where(Investition.aktiv == True)
        .order_by(Investition.bezeichnung)
    )
    wechselrichter = wr_result.scalars().all()

    wr_options = [
        ParentOption(id=wr.id, bezeichnung=wr.bezeichnung, typ=wr.typ)
        for wr in wechselrichter
    ]

    return {
        # PV-Module: Wechselrichter ist Pflicht (wenn vorhanden)
        "pv-module": [
            ParentOption(id=o.id, bezeichnung=o.bezeichnung, typ=o.typ, required=len(wechselrichter) > 0)
            for o in wr_options
        ],
        # Speicher: Wechselrichter ist optional (für Hybrid-WR)
        "speicher": [
            ParentOption(id=o.id, bezeichnung=o.bezeichnung, typ=o.typ, required=False)
            for o in wr_options
        ],
        # Andere Typen: Keine Parent-Optionen
        "wechselrichter": [],
        "e-auto": [],
        "wallbox": [],
        "waermepumpe": [],
        "balkonkraftwerk": [],
        "sonstiges": [],
    }


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
        400: Ungültiger Typ oder fehlende Parent-Zuordnung
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

    # Parent-Child Validierung (v0.9)
    await _validate_parent_child(db, data.anlage_id, data.typ, data.parent_investition_id)

    inv = Investition(**data.model_dump())
    db.add(inv)
    await db.flush()
    await db.refresh(inv)
    return inv


async def _validate_parent_child(
    db: AsyncSession,
    anlage_id: int,
    typ: str,
    parent_id: Optional[int],
    exclude_id: Optional[int] = None
):
    """
    Validiert Parent-Child Beziehungen für Investitionen.

    Regeln:
    - PV-Module MÜSSEN einem Wechselrichter zugeordnet sein
    - Speicher KÖNNEN optional einem Wechselrichter zugeordnet sein (Hybrid-WR)
    - Andere Typen haben keinen Parent
    """
    # PV-Module: Parent (Wechselrichter) ist Pflicht
    if typ == InvestitionTyp.PV_MODULE.value:
        if not parent_id:
            # Prüfen ob überhaupt Wechselrichter existieren
            wr_result = await db.execute(
                select(Investition)
                .where(Investition.anlage_id == anlage_id)
                .where(Investition.typ == InvestitionTyp.WECHSELRICHTER.value)
            )
            wechselrichter = wr_result.scalars().all()
            if wechselrichter:
                raise HTTPException(
                    status_code=400,
                    detail="PV-Module müssen einem Wechselrichter zugeordnet werden. "
                           f"Verfügbare Wechselrichter: {[w.bezeichnung for w in wechselrichter]}"
                )
            # Kein Wechselrichter vorhanden - PV-Modul ohne Parent erlauben (Migration)
            return

        # Parent muss Wechselrichter sein
        parent_result = await db.execute(
            select(Investition).where(Investition.id == parent_id)
        )
        parent = parent_result.scalar_one_or_none()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent-Investition nicht gefunden")
        if parent.typ != InvestitionTyp.WECHSELRICHTER.value:
            raise HTTPException(
                status_code=400,
                detail=f"PV-Module können nur Wechselrichtern zugeordnet werden, nicht '{parent.typ}'"
            )
        if parent.anlage_id != anlage_id:
            raise HTTPException(
                status_code=400,
                detail="Parent-Investition gehört zu einer anderen Anlage"
            )

    # Speicher: Parent (Wechselrichter) ist optional
    elif typ == InvestitionTyp.SPEICHER.value:
        if parent_id:
            parent_result = await db.execute(
                select(Investition).where(Investition.id == parent_id)
            )
            parent = parent_result.scalar_one_or_none()
            if not parent:
                raise HTTPException(status_code=404, detail="Parent-Investition nicht gefunden")
            if parent.typ != InvestitionTyp.WECHSELRICHTER.value:
                raise HTTPException(
                    status_code=400,
                    detail=f"Speicher können nur Wechselrichtern (Hybrid-WR) zugeordnet werden, nicht '{parent.typ}'"
                )
            if parent.anlage_id != anlage_id:
                raise HTTPException(
                    status_code=400,
                    detail="Parent-Investition gehört zu einer anderen Anlage"
                )

    # Andere Typen: Kein Parent erlaubt
    elif parent_id:
        raise HTTPException(
            status_code=400,
            detail=f"Investitionen vom Typ '{typ}' können keinem Parent zugeordnet werden"
        )


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
        400: Ungültige Parent-Zuordnung
    """
    result = await db.execute(select(Investition).where(Investition.id == investition_id))
    inv = result.scalar_one_or_none()

    if not inv:
        raise HTTPException(status_code=404, detail="Investition nicht gefunden")

    update_data = data.model_dump(exclude_unset=True)

    # Parent-Child Validierung wenn parent_investition_id geändert wird
    if 'parent_investition_id' in update_data:
        await _validate_parent_child(
            db,
            inv.anlage_id,
            inv.typ,
            update_data['parent_investition_id'],
            exclude_id=investition_id
        )

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

class ROIKomponente(BaseModel):
    """Eine Komponente innerhalb eines PV-Systems."""
    investition_id: int
    bezeichnung: str
    typ: str  # pv-module, wechselrichter, speicher
    kosten: float
    kosten_alternativ: float
    relevante_kosten: float
    einsparung: Optional[float]  # Nur für PV-Module/Speicher, None für WR
    co2_einsparung_kg: Optional[float]
    detail: dict[str, Any]


class ROIBerechnung(BaseModel):
    """Ergebnis einer ROI-Berechnung für eine Investition oder ein PV-System."""
    investition_id: int  # Bei System: ID des Wechselrichters
    investition_bezeichnung: str
    investition_typ: str  # "pv-system" für aggregiert, sonst normal
    anschaffungskosten: float
    anschaffungskosten_alternativ: float
    relevante_kosten: float
    jahres_einsparung: float
    roi_prozent: Optional[float]
    amortisation_jahre: Optional[float]
    co2_einsparung_kg: Optional[float]
    detail_berechnung: dict[str, Any]
    komponenten: Optional[list[ROIKomponente]] = None  # Für PV-Systeme


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
    jahr: Optional[int] = Query(None, description="Jahr für Auswertung (None = alle Jahre)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Berechnet ROI für alle aktiven Investitionen einer Anlage.

    PV-Systeme (Wechselrichter + zugeordnete PV-Module + DC-Speicher) werden
    als aggregierte Einheit berechnet, da der ROI nur auf System-Ebene sinnvoll ist.

    Args:
        anlage_id: ID der Anlage
        strompreis_cent: Aktueller Strompreis für Berechnungen
        einspeiseverguetung_cent: Aktuelle Einspeisevergütung
        benzinpreis_euro: Aktueller Benzinpreis für E-Auto-Vergleich
        jahr: Optionales Jahr für die Auswertung (None = alle Jahre)

    Returns:
        ROIDashboardResponse: Vollständige ROI-Übersicht
    """
    from backend.core.calculations import (
        berechne_speicher_einsparung,
        berechne_eauto_einsparung,
        berechne_waermepumpe_einsparung,
        berechne_roi,
        CO2_FAKTOR_STROM_KG_KWH,
    )
    from sqlalchemy import func
    from backend.models.pvgis_prognose import PVGISPrognose

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
        .order_by(Investition.typ, Investition.id)
    )
    investitionen = list(inv_result.scalars().all())

    # ==========================================================================
    # Phase 1: Gruppiere Investitionen nach PV-Systemen und Standalone
    # ==========================================================================

    # PV-Systeme: Wechselrichter mit zugeordneten PV-Modulen und DC-Speichern
    pv_systeme: dict[int, dict] = {}  # wr_id -> {wr, pv_module[], speicher[]}

    # Standalone: Investitionen die nicht zu einem PV-System gehören
    standalone: list[Investition] = []

    # Orphans: PV-Module/Speicher ohne Wechselrichter-Zuordnung (Altdaten)
    orphan_pv_module: list[Investition] = []

    # Zwei-Pass-Ansatz: Erst alle Wechselrichter sammeln, damit parent_investition_id
    # korrekt aufgelöst werden kann (unabhängig von der Sortierung)
    for inv in investitionen:
        if inv.typ == InvestitionTyp.WECHSELRICHTER.value:
            pv_systeme[inv.id] = {"wr": inv, "pv_module": [], "speicher": []}

    # Zweiter Pass: PV-Module und Speicher zuordnen
    for inv in investitionen:
        if inv.typ == InvestitionTyp.WECHSELRICHTER.value:
            continue  # bereits verarbeitet
        elif inv.typ == InvestitionTyp.PV_MODULE.value:
            if inv.parent_investition_id and inv.parent_investition_id in pv_systeme:
                pv_systeme[inv.parent_investition_id]["pv_module"].append(inv)
            else:
                # PV-Modul ohne Wechselrichter-Zuordnung
                orphan_pv_module.append(inv)
        elif inv.typ == InvestitionTyp.SPEICHER.value:
            if inv.parent_investition_id and inv.parent_investition_id in pv_systeme:
                # DC-gekoppelter Speicher am Hybrid-WR
                pv_systeme[inv.parent_investition_id]["speicher"].append(inv)
            else:
                # AC-gekoppelter Speicher - eigenständig
                standalone.append(inv)
        else:
            # E-Auto, Wärmepumpe, Wallbox, Balkonkraftwerk, Sonstiges
            standalone.append(inv)

    # ==========================================================================
    # Phase 2: Hilfsfunktion für PV-Erzeugungsdaten
    # ==========================================================================

    async def berechne_pv_einsparung_aus_monatsdaten() -> tuple[float, float, dict]:
        """
        Berechnet PV-Einsparung für alle PV-Module gemeinsam.

        WICHTIG: Die PV-Erzeugung kommt aus InvestitionMonatsdaten (pro PV-Modul),
        NICHT aus Monatsdaten.pv_erzeugung_kwh (Legacy-Feld!).
        Einspeisung/Netzbezug kommen weiterhin aus Monatsdaten (Zählerwerte).
        """
        # 1. PV-Module IDs ermitteln
        pv_ids_result = await db.execute(
            select(Investition.id)
            .where(Investition.anlage_id == anlage_id)
            .where(Investition.typ == "pv-module")
            .where(Investition.aktiv == True)
        )
        pv_module_ids = [row[0] for row in pv_ids_result.all()]

        # 2. Einspeisung aus Monatsdaten (Zählerwert)
        md_query = select(
            Monatsdaten.monat,
            Monatsdaten.jahr,
            func.sum(Monatsdaten.einspeisung_kwh).label('einspeisung'),
        ).where(Monatsdaten.anlage_id == anlage_id)

        if jahr is not None:
            md_query = md_query.where(Monatsdaten.jahr == jahr)

        # 3. PV-Erzeugung aus InvestitionMonatsdaten aggregieren
        async def get_pv_erzeugung(filter_jahr: int = None) -> dict[tuple[int, int], float]:
            """Holt PV-Erzeugung aus InvestitionMonatsdaten."""
            if not pv_module_ids:
                return {}

            imd_query = select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(pv_module_ids)
            )
            if filter_jahr is not None:
                imd_query = imd_query.where(InvestitionMonatsdaten.jahr == filter_jahr)

            imd_result = await db.execute(imd_query)
            erzeugung_by_monat: dict[tuple[int, int], float] = {}
            for imd in imd_result.scalars().all():
                data = imd.verbrauch_daten or {}
                pv_kwh = data.get("pv_erzeugung_kwh", 0) or 0
                key = (imd.jahr, imd.monat)
                erzeugung_by_monat[key] = erzeugung_by_monat.get(key, 0) + pv_kwh
            return erzeugung_by_monat

        if jahr is None:
            # Alle Jahre: Jahresdurchschnitt
            md_count_query = select(
                func.count().label('total_records'),
                func.count(func.distinct(Monatsdaten.jahr)).label('anzahl_jahre')
            ).where(Monatsdaten.anlage_id == anlage_id)
            count_result = await db.execute(md_count_query)
            count_row = count_result.one()
            total_records = count_row.total_records
            anzahl_jahre = count_row.anzahl_jahre or 1

            md_query = md_query.group_by(Monatsdaten.monat)
            md_result = await db.execute(md_query)
            md_by_month = {r.monat: r for r in md_result.all()}

            # PV-Erzeugung aus InvestitionMonatsdaten
            pv_erzeugung_data = await get_pv_erzeugung()
            total_erzeugung = sum(pv_erzeugung_data.values())

            total_einspeisung = sum(r.einspeisung or 0 for r in md_by_month.values())
            anzahl_monate = len(md_by_month)

            if anzahl_monate > 0 and anzahl_jahre > 0:
                avg_einspeisung = total_einspeisung / anzahl_jahre
                avg_erzeugung = total_erzeugung / anzahl_jahre
                avg_monate_pro_jahr = total_records / anzahl_jahre

                if avg_monate_pro_jahr < 12:
                    faktor = 12.0 / avg_monate_pro_jahr
                    methode = 'durchschnitt_hochgerechnet'
                else:
                    faktor = 1.0
                    methode = 'durchschnitt'

                einspeisung_jahr = avg_einspeisung * faktor
                erzeugung_jahr = avg_erzeugung * faktor
                # Eigenverbrauch = Erzeugung - Einspeisung
                eigenverbrauch_jahr = max(0, erzeugung_jahr - einspeisung_jahr)
                hinweis = f'Jahresdurchschnitt (Ø aus {anzahl_jahre} Jahren)'
                if methode == 'durchschnitt_hochgerechnet':
                    hinweis += ', hochgerechnet auf 12 Monate'
            else:
                return 0, 0, {'hinweis': 'Keine Monatsdaten vorhanden'}
        else:
            # Einzelnes Jahr
            md_query = md_query.group_by(Monatsdaten.monat)
            md_result = await db.execute(md_query)
            md_by_month = {r.monat: r for r in md_result.all()}

            # PV-Erzeugung aus InvestitionMonatsdaten für dieses Jahr
            pv_erzeugung_data = await get_pv_erzeugung(jahr)
            total_erzeugung = sum(pv_erzeugung_data.values())

            total_einspeisung = sum(r.einspeisung or 0 for r in md_by_month.values())
            anzahl_monate = len(md_by_month)
            vorhandene_monate = sorted(md_by_month.keys())

            if anzahl_monate > 0:
                # PVGIS-Hochrechnung versuchen
                pvgis_result = await db.execute(
                    select(PVGISPrognose)
                    .where(PVGISPrognose.anlage_id == anlage_id)
                    .where(PVGISPrognose.ist_aktiv == True)
                    .order_by(PVGISPrognose.abgerufen_am.desc())
                    .limit(1)
                )
                pvgis_prognose = pvgis_result.scalar_one_or_none()

                methode = 'linear'
                faktor = 12.0 / anzahl_monate

                if pvgis_prognose and pvgis_prognose.monatswerte and anzahl_monate < 12:
                    pvgis_monatswerte = pvgis_prognose.monatswerte
                    pvgis_jahres_summe = sum(m.get('E_m', 0) for m in pvgis_monatswerte)
                    if pvgis_jahres_summe > 0:
                        pvgis_vorhandene_summe = sum(
                            m.get('E_m', 0) for m in pvgis_monatswerte
                            if m.get('month', 0) in vorhandene_monate
                        )
                        if pvgis_vorhandene_summe > 0:
                            faktor = 1.0 / (pvgis_vorhandene_summe / pvgis_jahres_summe)
                            methode = 'pvgis'

                einspeisung_jahr = total_einspeisung * faktor
                erzeugung_jahr = total_erzeugung * faktor
                # Eigenverbrauch = Erzeugung - Einspeisung
                eigenverbrauch_jahr = max(0, erzeugung_jahr - einspeisung_jahr)

                if methode == 'pvgis':
                    hinweis = f'PVGIS-gewichtete Hochrechnung für {jahr} ({anzahl_monate} Monate)'
                elif anzahl_monate >= 12:
                    hinweis = f'Berechnet aus {anzahl_monate} Monaten für {jahr}'
                else:
                    hinweis = f'Lineare Hochrechnung für {jahr} aus {anzahl_monate} Monaten'
            else:
                return 0, 0, {'hinweis': f'Keine Monatsdaten für {jahr}'}

        # Eigenverbrauch ableiten wenn nicht vorhanden
        if eigenverbrauch_jahr == 0 and erzeugung_jahr > 0:
            eigenverbrauch_jahr = erzeugung_jahr - einspeisung_jahr

        # Einsparung berechnen
        einspeise_erloes = einspeisung_jahr * einspeiseverguetung_cent / 100
        ev_ersparnis = eigenverbrauch_jahr * strompreis_cent / 100
        jahres_einsparung = einspeise_erloes + ev_ersparnis
        co2 = erzeugung_jahr * CO2_FAKTOR_STROM_KG_KWH

        detail = {
            'einspeisung_kwh_jahr': round(einspeisung_jahr, 0),
            'eigenverbrauch_kwh_jahr': round(eigenverbrauch_jahr, 0),
            'erzeugung_kwh_jahr': round(erzeugung_jahr, 0),
            'einspeise_erloes_euro': round(einspeise_erloes, 2),
            'ev_ersparnis_euro': round(ev_ersparnis, 2),
            'hinweis': hinweis,
        }

        return jahres_einsparung, co2, detail

    # ==========================================================================
    # Phase 3: Berechne ROI für PV-Systeme (aggregiert)
    # ==========================================================================

    berechnungen: list[ROIBerechnung] = []
    gesamt_investition = 0.0
    gesamt_relevante = 0.0
    gesamt_einsparung = 0.0
    gesamt_co2 = 0.0

    # PV-Einsparung einmal berechnen (wird auf Module verteilt)
    pv_jahres_einsparung, pv_co2, pv_detail = await berechne_pv_einsparung_aus_monatsdaten()

    # Gesamt-kWp aller PV-Module für proportionale Verteilung
    gesamt_kwp = sum(
        inv.leistung_kwp or 0
        for system in pv_systeme.values()
        for inv in system["pv_module"]
    )
    gesamt_kwp += sum(inv.leistung_kwp or 0 for inv in orphan_pv_module)

    for wr_id, system in pv_systeme.items():
        wr = system["wr"]
        pv_module = system["pv_module"]
        dc_speicher = system["speicher"]

        # Nur Systeme mit PV-Modulen anzeigen
        if not pv_module and not dc_speicher:
            # Wechselrichter ohne zugeordnete Komponenten - als Hinweis zeigen
            standalone.append(wr)
            continue

        # Kosten summieren
        system_kosten = (wr.anschaffungskosten_gesamt or 0)
        system_alternativ = (wr.anschaffungskosten_alternativ or 0)

        komponenten: list[ROIKomponente] = []

        # Wechselrichter als Komponente
        wr_kosten = wr.anschaffungskosten_gesamt or 0
        wr_alternativ = wr.anschaffungskosten_alternativ or 0
        komponenten.append(ROIKomponente(
            investition_id=wr.id,
            bezeichnung=wr.bezeichnung,
            typ=wr.typ,
            kosten=wr_kosten,
            kosten_alternativ=wr_alternativ,
            relevante_kosten=wr_kosten - wr_alternativ,
            einsparung=None,  # WR hat keine eigene Einsparung
            co2_einsparung_kg=None,
            detail={'hinweis': 'Wechselrichter - Einsparung über PV-Module'}
        ))

        # PV-Module Einsparung proportional nach kWp verteilen
        system_kwp = sum(inv.leistung_kwp or 0 for inv in pv_module)
        system_einsparung = 0.0
        system_co2 = 0.0

        for inv in pv_module:
            inv_kosten = inv.anschaffungskosten_gesamt or 0
            inv_alternativ = inv.anschaffungskosten_alternativ or 0
            system_kosten += inv_kosten
            system_alternativ += inv_alternativ

            # Einsparung proportional nach kWp
            inv_kwp = inv.leistung_kwp or 0
            if gesamt_kwp > 0 and inv_kwp > 0:
                anteil = inv_kwp / gesamt_kwp
                inv_einsparung = pv_jahres_einsparung * anteil
                inv_co2 = pv_co2 * anteil
            else:
                inv_einsparung = 0
                inv_co2 = 0

            system_einsparung += inv_einsparung
            system_co2 += inv_co2

            komponenten.append(ROIKomponente(
                investition_id=inv.id,
                bezeichnung=f"{inv.bezeichnung} ({inv_kwp} kWp)",
                typ=inv.typ,
                kosten=inv_kosten,
                kosten_alternativ=inv_alternativ,
                relevante_kosten=inv_kosten - inv_alternativ,
                einsparung=round(inv_einsparung, 2),
                co2_einsparung_kg=round(inv_co2, 1),
                detail={
                    'anteil_prozent': round(anteil * 100, 1) if gesamt_kwp > 0 else 0,
                    'leistung_kwp': inv_kwp,
                }
            ))

        # DC-Speicher (am Hybrid-WR)
        for inv in dc_speicher:
            inv_kosten = inv.anschaffungskosten_gesamt or 0
            inv_alternativ = inv.anschaffungskosten_alternativ or 0
            system_kosten += inv_kosten
            system_alternativ += inv_alternativ

            params = inv.parameter or {}
            kapazitaet = params.get('kapazitaet_kwh', 10)
            wirkungsgrad = params.get('wirkungsgrad_prozent', 95)
            nutzt_arbitrage = params.get('nutzt_arbitrage', False)

            result = berechne_speicher_einsparung(
                kapazitaet_kwh=kapazitaet,
                wirkungsgrad_prozent=wirkungsgrad,
                netzbezug_preis_cent=strompreis_cent,
                einspeiseverguetung_cent=einspeiseverguetung_cent,
                nutzt_arbitrage=nutzt_arbitrage,
            )
            inv_einsparung = result.jahres_einsparung_euro
            inv_co2 = result.co2_einsparung_kg
            system_einsparung += inv_einsparung
            system_co2 += inv_co2

            komponenten.append(ROIKomponente(
                investition_id=inv.id,
                bezeichnung=f"{inv.bezeichnung} ({kapazitaet} kWh)",
                typ=inv.typ,
                kosten=inv_kosten,
                kosten_alternativ=inv_alternativ,
                relevante_kosten=inv_kosten - inv_alternativ,
                einsparung=round(inv_einsparung, 2),
                co2_einsparung_kg=round(inv_co2, 1),
                detail={'kapazitaet_kwh': kapazitaet, 'dc_gekoppelt': True}
            ))

        # System-ROI berechnen
        system_relevante = system_kosten - system_alternativ
        roi_result = berechne_roi(system_kosten, system_einsparung, system_alternativ)

        berechnungen.append(ROIBerechnung(
            investition_id=wr.id,  # WR-ID als System-ID
            investition_bezeichnung=f"PV-System {wr.bezeichnung}",
            investition_typ="pv-system",
            anschaffungskosten=system_kosten,
            anschaffungskosten_alternativ=system_alternativ,
            relevante_kosten=system_relevante,
            jahres_einsparung=round(system_einsparung, 2),
            roi_prozent=roi_result['roi_prozent'],
            amortisation_jahre=roi_result['amortisation_jahre'],
            co2_einsparung_kg=round(system_co2, 1),
            detail_berechnung={
                **pv_detail,
                'komponenten_count': len(komponenten),
                'system_kwp': system_kwp,
            },
            komponenten=komponenten,
        ))

        gesamt_investition += system_kosten
        gesamt_relevante += system_relevante
        gesamt_einsparung += system_einsparung
        gesamt_co2 += system_co2

    # ==========================================================================
    # Phase 4: Orphan PV-Module (ohne Wechselrichter-Zuordnung)
    # ==========================================================================

    for inv in orphan_pv_module:
        kosten = inv.anschaffungskosten_gesamt or 0
        alternativ = inv.anschaffungskosten_alternativ or 0
        relevante = kosten - alternativ

        # Einsparung proportional nach kWp
        inv_kwp = inv.leistung_kwp or 0
        if gesamt_kwp > 0 and inv_kwp > 0:
            anteil = inv_kwp / gesamt_kwp
            jahres_einsparung = pv_jahres_einsparung * anteil
            co2_einsparung = pv_co2 * anteil
        else:
            jahres_einsparung = 0
            co2_einsparung = 0

        roi_result = berechne_roi(kosten, jahres_einsparung, alternativ)

        berechnungen.append(ROIBerechnung(
            investition_id=inv.id,
            investition_bezeichnung=f"{inv.bezeichnung} (ohne WR)",
            investition_typ=inv.typ,
            anschaffungskosten=kosten,
            anschaffungskosten_alternativ=alternativ,
            relevante_kosten=relevante,
            jahres_einsparung=round(jahres_einsparung, 2),
            roi_prozent=roi_result['roi_prozent'],
            amortisation_jahre=roi_result['amortisation_jahre'],
            co2_einsparung_kg=round(co2_einsparung, 1),
            detail_berechnung={
                **pv_detail,
                'hinweis': 'PV-Modul ohne Wechselrichter-Zuordnung - bitte zuordnen',
                'anteil_prozent': round(anteil * 100, 1) if gesamt_kwp > 0 else 0,
            },
        ))

        gesamt_investition += kosten
        gesamt_relevante += relevante
        gesamt_einsparung += jahres_einsparung
        gesamt_co2 += co2_einsparung

    # ==========================================================================
    # Phase 5: Standalone-Investitionen (wie bisher)
    # ==========================================================================

    for inv in standalone:
        params = inv.parameter or {}
        kosten = inv.anschaffungskosten_gesamt or 0
        alternativ = inv.anschaffungskosten_alternativ or 0
        relevante = kosten - alternativ
        jahres_einsparung = 0.0
        co2_einsparung = 0.0
        detail: dict[str, Any] = {}

        if inv.typ == InvestitionTyp.SPEICHER.value:
            # AC-gekoppelter Speicher
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
                'hinweis': 'AC-gekoppelter Speicher',
            }

        elif inv.typ == InvestitionTyp.E_AUTO.value:
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
                'hinweis': f'E-Auto: {km_jahr} km/Jahr',
            }

        elif inv.typ == InvestitionTyp.WAERMEPUMPE.value:
            # Modus-Auswahl: gesamt_jaz (Standard) oder getrennte_cops
            effizienz_modus = params.get('effizienz_modus', 'gesamt_jaz')
            pv_anteil = params.get('pv_anteil_prozent', 30)
            alter_energietraeger = params.get('alter_energietraeger', 'gas')
            alter_preis = params.get('alter_preis_cent_kwh', 12)

            if effizienz_modus == 'getrennte_cops':
                # Getrennte COPs für Heizung und Warmwasser
                cop_heizung = params.get('cop_heizung', 3.9)
                cop_warmwasser = params.get('cop_warmwasser', 3.0)
                heizwaermebedarf = params.get('heizwaermebedarf_kwh', 12000)
                warmwasserbedarf = params.get('warmwasserbedarf_kwh', 3000)

                result = berechne_waermepumpe_einsparung(
                    heizwaermebedarf_kwh=heizwaermebedarf,
                    warmwasserbedarf_kwh=warmwasserbedarf,
                    cop_heizung=cop_heizung,
                    cop_warmwasser=cop_warmwasser,
                    effizienz_modus='getrennte_cops',
                    strompreis_cent=strompreis_cent,
                    pv_anteil_prozent=pv_anteil,
                    alter_energietraeger=alter_energietraeger,
                    alter_preis_cent_kwh=alter_preis,
                )
                hinweis = f'WP: COP Heizung {cop_heizung}, Warmwasser {cop_warmwasser}'
            else:
                # Standard: Ein JAZ für alles
                jaz = params.get('jaz', 3.5)
                # Wärmebedarf: explizit oder aus Komponenten
                waermebedarf = params.get('waermebedarf_kwh')
                if waermebedarf is None:
                    heizwaermebedarf = params.get('heizwaermebedarf_kwh', 12000)
                    warmwasserbedarf = params.get('warmwasserbedarf_kwh', 3000)
                    waermebedarf = heizwaermebedarf + warmwasserbedarf

                result = berechne_waermepumpe_einsparung(
                    waermebedarf_kwh=waermebedarf,
                    jaz=jaz,
                    effizienz_modus='gesamt_jaz',
                    strompreis_cent=strompreis_cent,
                    pv_anteil_prozent=pv_anteil,
                    alter_energietraeger=alter_energietraeger,
                    alter_preis_cent_kwh=alter_preis,
                )
                hinweis = f'Wärmepumpe: JAZ {jaz}'

            jahres_einsparung = result.jahres_einsparung_euro
            co2_einsparung = result.co2_einsparung_kg
            detail = {
                'wp_kosten_euro': result.wp_kosten_euro,
                'alte_heizung_kosten_euro': result.alte_heizung_kosten_euro,
                'effizienz_modus': effizienz_modus,
                'hinweis': hinweis,
            }

        elif inv.typ == InvestitionTyp.BALKONKRAFTWERK.value:
            # Balkonkraftwerk hat eigenen Mikro-WR integriert
            leistung_wp = params.get('leistung_wp', 800)
            # Vereinfachte Berechnung: ca. 0.9 kWh/Wp/Jahr in Deutschland
            jahres_ertrag = leistung_wp * 0.9
            # 80% Eigenverbrauch typisch bei Balkonkraftwerk
            eigenverbrauch = jahres_ertrag * 0.8
            einspeisung = jahres_ertrag * 0.2

            einspeise_erloes = einspeisung * einspeiseverguetung_cent / 100
            ev_ersparnis = eigenverbrauch * strompreis_cent / 100
            jahres_einsparung = einspeise_erloes + ev_ersparnis
            co2_einsparung = jahres_ertrag * CO2_FAKTOR_STROM_KG_KWH

            detail = {
                'leistung_wp': leistung_wp,
                'jahres_ertrag_kwh': round(jahres_ertrag, 0),
                'eigenverbrauch_kwh': round(eigenverbrauch, 0),
                'hinweis': f'Balkonkraftwerk {leistung_wp} Wp',
            }

        elif inv.typ == InvestitionTyp.WECHSELRICHTER.value:
            # Wechselrichter ohne zugeordnete PV-Module
            detail = {
                'hinweis': 'Wechselrichter ohne zugeordnete PV-Module - bitte PV-Module zuordnen',
            }

        else:
            # Wallbox, Sonstiges
            jahres_einsparung = inv.einsparung_prognose_jahr or 0
            co2_einsparung = inv.co2_einsparung_prognose_kg or 0
            detail = {'hinweis': 'Manuelle Prognose verwendet'}

        roi_result = berechne_roi(kosten, jahres_einsparung, alternativ)

        berechnungen.append(ROIBerechnung(
            investition_id=inv.id,
            investition_bezeichnung=inv.bezeichnung,
            investition_typ=inv.typ,
            anschaffungskosten=kosten,
            anschaffungskosten_alternativ=alternativ,
            relevante_kosten=relevante,
            jahres_einsparung=round(jahres_einsparung, 2),
            roi_prozent=roi_result['roi_prozent'],
            amortisation_jahre=roi_result['amortisation_jahre'],
            co2_einsparung_kg=round(co2_einsparung, 1) if co2_einsparung else None,
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


# =============================================================================
# Investitions-Dashboards
# =============================================================================

class InvestitionMonatsdatenResponse(BaseModel):
    """Monatsdaten für eine Investition."""
    id: int
    investition_id: int
    jahr: int
    monat: int
    verbrauch_daten: dict[str, Any]
    einsparung_monat_euro: Optional[float]
    co2_einsparung_kg: Optional[float]

    class Config:
        from_attributes = True


class EAutoDashboardResponse(BaseModel):
    """E-Auto Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


class WaermepumpeDashboardResponse(BaseModel):
    """Wärmepumpe Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


class SpeicherDashboardResponse(BaseModel):
    """Speicher Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


class WallboxDashboardResponse(BaseModel):
    """Wallbox Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


class BalkonkraftwerkDashboardResponse(BaseModel):
    """Balkonkraftwerk Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


class SonstigesDashboardResponse(BaseModel):
    """Sonstiges Dashboard Daten."""
    investition: InvestitionResponse
    monatsdaten: list[InvestitionMonatsdatenResponse]
    zusammenfassung: dict[str, Any]


@router.get("/dashboard/e-auto/{anlage_id}", response_model=list[EAutoDashboardResponse])
async def get_eauto_dashboard(
    anlage_id: int,
    strompreis_cent: float = Query(30.0),
    benzinpreis_euro: float = Query(1.65),
    db: AsyncSession = Depends(get_db)
):
    """
    E-Auto Dashboard für eine Anlage.

    Zeigt alle E-Autos mit Monatsdaten, km-Statistik, PV-Anteil, Ersparnis.
    """
    # E-Autos laden
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.E_AUTO.value)
        .where(Investition.aktiv == True)
    )
    eautos = inv_result.scalars().all()

    if not eautos:
        return []

    dashboards = []
    for eauto in eautos:
        # Monatsdaten laden
        md_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id == eauto.id)
            .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
        )
        monatsdaten = md_result.scalars().all()

        # Zusammenfassung berechnen
        gesamt_km = 0
        gesamt_verbrauch = 0
        gesamt_pv_ladung = 0
        gesamt_netz_ladung = 0
        gesamt_extern_ladung = 0
        gesamt_extern_kosten = 0
        gesamt_v2h = 0

        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            gesamt_km += d.get('km_gefahren', 0)
            gesamt_verbrauch += d.get('verbrauch_kwh', 0)
            gesamt_pv_ladung += d.get('ladung_pv_kwh', 0)
            gesamt_netz_ladung += d.get('ladung_netz_kwh', 0)
            gesamt_extern_ladung += d.get('ladung_extern_kwh', 0)
            gesamt_extern_kosten += d.get('ladung_extern_euro', 0)
            gesamt_v2h += d.get('v2h_entladung_kwh', 0)

        # Heim-Ladung (Wallbox) = PV + Netz
        gesamt_heim_ladung = gesamt_pv_ladung + gesamt_netz_ladung
        # Gesamt-Ladung = Heim + Extern
        gesamt_ladung = gesamt_heim_ladung + gesamt_extern_ladung
        # PV-Anteil nur auf Heim-Ladung bezogen
        pv_anteil_heim = (gesamt_pv_ladung / gesamt_heim_ladung * 100) if gesamt_heim_ladung > 0 else 0
        # PV-Anteil auf Gesamt-Ladung
        pv_anteil_gesamt = (gesamt_pv_ladung / gesamt_ladung * 100) if gesamt_ladung > 0 else 0

        # Kosten-Berechnung
        params = eauto.parameter or {}
        benzin_verbrauch_100km = params.get('vergleich_verbrauch_l_100km', 7.5)

        # Benzin-Kosten (Alternativ-Szenario)
        benzin_kosten = (gesamt_km / 100) * benzin_verbrauch_100km * benzinpreis_euro

        # E-Auto Kosten: PV = kostenlos, Netz = Strompreis, Extern = tatsächliche Kosten
        heim_netz_kosten = gesamt_netz_ladung * strompreis_cent / 100
        strom_kosten_gesamt = heim_netz_kosten + gesamt_extern_kosten

        # Ersparnis vs. Verbrenner
        ersparnis_vs_benzin = benzin_kosten - strom_kosten_gesamt

        # V2H Ersparnis (Rückspeisung ins Haus)
        v2h_preis = params.get('v2h_entlade_preis_cent', strompreis_cent)
        v2h_ersparnis = gesamt_v2h * v2h_preis / 100

        # Wallbox-Ersparnis: Was hätte externe Ladung gekostet?
        # Durchschnittlicher externer Preis (wenn vorhanden) oder Annahme 50 ct/kWh
        extern_preis_kwh = (gesamt_extern_kosten / gesamt_extern_ladung) if gesamt_extern_ladung > 0 else 0.50
        heim_ladung_als_extern = gesamt_heim_ladung * extern_preis_kwh
        heim_kosten_tatsaechlich = heim_netz_kosten  # PV ist kostenlos
        wallbox_ersparnis = heim_ladung_als_extern - heim_kosten_tatsaechlich

        # CO2 Ersparnis (Benzin: ca. 2.37 kg CO2 pro Liter)
        benzin_co2 = (gesamt_km / 100) * benzin_verbrauch_100km * 2.37
        strom_co2 = gesamt_verbrauch * 0.38  # Strommix
        co2_ersparnis = benzin_co2 - strom_co2

        zusammenfassung = {
            'gesamt_km': round(gesamt_km, 0),
            'gesamt_verbrauch_kwh': round(gesamt_verbrauch, 1),
            'durchschnitt_verbrauch_kwh_100km': round(gesamt_verbrauch / gesamt_km * 100, 1) if gesamt_km > 0 else 0,
            # Ladung aufgeschlüsselt
            'gesamt_ladung_kwh': round(gesamt_ladung, 1),
            'ladung_heim_kwh': round(gesamt_heim_ladung, 1),
            'ladung_pv_kwh': round(gesamt_pv_ladung, 1),
            'ladung_netz_kwh': round(gesamt_netz_ladung, 1),
            'ladung_extern_kwh': round(gesamt_extern_ladung, 1),
            'ladung_extern_euro': round(gesamt_extern_kosten, 2),
            # PV-Anteile
            'pv_anteil_heim_prozent': round(pv_anteil_heim, 1),
            'pv_anteil_gesamt_prozent': round(pv_anteil_gesamt, 1),
            # V2H
            'v2h_entladung_kwh': round(gesamt_v2h, 1),
            'v2h_ersparnis_euro': round(v2h_ersparnis, 2),
            # Kosten-Vergleich
            'benzin_kosten_alternativ_euro': round(benzin_kosten, 2),
            'strom_kosten_heim_euro': round(heim_netz_kosten, 2),
            'strom_kosten_extern_euro': round(gesamt_extern_kosten, 2),
            'strom_kosten_gesamt_euro': round(strom_kosten_gesamt, 2),
            'ersparnis_vs_benzin_euro': round(ersparnis_vs_benzin, 2),
            # Wallbox-Ersparnis (durch Heimladen statt extern)
            'wallbox_ersparnis_euro': round(wallbox_ersparnis, 2),
            # Gesamt-Ersparnis
            'gesamt_ersparnis_euro': round(ersparnis_vs_benzin + v2h_ersparnis, 2),
            'co2_ersparnis_kg': round(co2_ersparnis, 1),
            'anzahl_monate': len(monatsdaten),
        }

        dashboards.append(EAutoDashboardResponse(
            investition=eauto,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


@router.get("/dashboard/waermepumpe/{anlage_id}", response_model=list[WaermepumpeDashboardResponse])
async def get_waermepumpe_dashboard(
    anlage_id: int,
    strompreis_cent: float = Query(30.0),
    db: AsyncSession = Depends(get_db)
):
    """
    Wärmepumpe Dashboard für eine Anlage.

    Zeigt alle Wärmepumpen mit COP, Heizkosten, Ersparnis vs. alte Heizung.
    """
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.WAERMEPUMPE.value)
        .where(Investition.aktiv == True)
    )
    waermepumpen = inv_result.scalars().all()

    if not waermepumpen:
        return []

    dashboards = []
    for wp in waermepumpen:
        md_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id == wp.id)
            .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
        )
        monatsdaten = md_result.scalars().all()

        gesamt_strom = 0
        gesamt_heizung = 0
        gesamt_warmwasser = 0

        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            gesamt_strom += d.get('stromverbrauch_kwh', 0)
            gesamt_heizung += d.get('heizenergie_kwh', 0)
            gesamt_warmwasser += d.get('warmwasser_kwh', 0)

        gesamt_waerme = gesamt_heizung + gesamt_warmwasser
        durchschnitt_cop = gesamt_waerme / gesamt_strom if gesamt_strom > 0 else 0

        # Kosten WP
        wp_kosten = gesamt_strom * strompreis_cent / 100

        # Vergleich alte Heizung
        params = wp.parameter or {}
        gas_preis = params.get('gas_kwh_preis_cent', 12)
        alte_heizung_kosten = gesamt_waerme * gas_preis / 100

        ersparnis = alte_heizung_kosten - wp_kosten

        # CO2 (Gas: ca. 0.2 kg/kWh, Strom: 0.38 kg/kWh)
        gas_co2 = gesamt_waerme * 0.2
        strom_co2 = gesamt_strom * 0.38
        co2_ersparnis = gas_co2 - strom_co2

        zusammenfassung = {
            'gesamt_stromverbrauch_kwh': round(gesamt_strom, 1),
            'gesamt_heizenergie_kwh': round(gesamt_heizung, 1),
            'gesamt_warmwasser_kwh': round(gesamt_warmwasser, 1),
            'gesamt_waerme_kwh': round(gesamt_waerme, 1),
            'durchschnitt_cop': round(durchschnitt_cop, 2),
            'wp_kosten_euro': round(wp_kosten, 2),
            'alte_heizung_kosten_euro': round(alte_heizung_kosten, 2),
            'ersparnis_euro': round(ersparnis, 2),
            'co2_ersparnis_kg': round(co2_ersparnis, 1),
            'anzahl_monate': len(monatsdaten),
        }

        dashboards.append(WaermepumpeDashboardResponse(
            investition=wp,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


@router.get("/dashboard/speicher/{anlage_id}", response_model=list[SpeicherDashboardResponse])
async def get_speicher_dashboard(
    anlage_id: int,
    strompreis_cent: float = Query(30.0),
    einspeiseverguetung_cent: float = Query(8.0),
    db: AsyncSession = Depends(get_db)
):
    """
    Speicher Dashboard für eine Anlage.

    Zeigt alle Speicher mit Zyklen, Effizienz, Eigenverbrauchserhöhung.
    """
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.SPEICHER.value)
        .where(Investition.aktiv == True)
    )
    speicher_list = inv_result.scalars().all()

    if not speicher_list:
        return []

    dashboards = []
    for speicher in speicher_list:
        md_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id == speicher.id)
            .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
        )
        monatsdaten = md_result.scalars().all()

        gesamt_ladung = 0
        gesamt_entladung = 0
        gesamt_arbitrage_kwh = 0
        arbitrage_preis_sum = 0
        arbitrage_count = 0

        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            gesamt_ladung += d.get('ladung_kwh', 0)
            gesamt_entladung += d.get('entladung_kwh', 0)
            # Arbitrage (Netzladung zu günstigen Zeiten)
            netzladung = d.get('speicher_ladung_netz_kwh', 0) or 0
            if netzladung > 0:
                gesamt_arbitrage_kwh += netzladung
                preis = d.get('speicher_ladepreis_cent', 0) or 0
                if preis > 0:
                    arbitrage_preis_sum += preis * netzladung
                    arbitrage_count += netzladung

        # Effizienz
        effizienz = (gesamt_entladung / gesamt_ladung * 100) if gesamt_ladung > 0 else 0

        # Zyklen (basierend auf Kapazität)
        params = speicher.parameter or {}
        kapazitaet = params.get('kapazitaet_kwh', 10)
        arbitrage_faehig = params.get('arbitrage_faehig', False)
        vollzyklen = gesamt_ladung / kapazitaet if kapazitaet > 0 else 0

        # Ersparnis: Entladung ersetzt Netzbezug (Spread zwischen Netzbezug und Einspeisung)
        spread = strompreis_cent - einspeiseverguetung_cent
        ersparnis = gesamt_entladung * spread / 100

        # Arbitrage-Gewinn: (Strompreis - Ladepreis) * Netzladung
        arbitrage_avg_preis = (arbitrage_preis_sum / arbitrage_count) if arbitrage_count > 0 else 0
        arbitrage_gewinn = gesamt_arbitrage_kwh * (strompreis_cent - arbitrage_avg_preis) / 100 if gesamt_arbitrage_kwh > 0 else 0

        zusammenfassung = {
            'gesamt_ladung_kwh': round(gesamt_ladung, 1),
            'gesamt_entladung_kwh': round(gesamt_entladung, 1),
            'effizienz_prozent': round(effizienz, 1),
            'vollzyklen': round(vollzyklen, 1),
            'zyklen_pro_monat': round(vollzyklen / len(monatsdaten), 1) if monatsdaten else 0,
            'kapazitaet_kwh': kapazitaet,
            'ersparnis_euro': round(ersparnis, 2),
            'anzahl_monate': len(monatsdaten),
            # Arbitrage-Daten
            'arbitrage_faehig': arbitrage_faehig,
            'arbitrage_kwh': round(gesamt_arbitrage_kwh, 1),
            'arbitrage_avg_preis_cent': round(arbitrage_avg_preis, 1) if arbitrage_avg_preis > 0 else None,
            'arbitrage_gewinn_euro': round(arbitrage_gewinn, 2),
        }

        dashboards.append(SpeicherDashboardResponse(
            investition=speicher,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


@router.get("/monatsdaten/{anlage_id}/{jahr}/{monat}", response_model=list[InvestitionMonatsdatenResponse])
async def get_investition_monatsdaten_by_month(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt alle InvestitionMonatsdaten für eine Anlage und einen bestimmten Monat zurück.

    Dies wird vom MonatsdatenForm benötigt, um beim Bearbeiten eines Monats
    die vorhandenen Investitionsdaten (E-Auto km, Speicher Ladung, etc.) zu laden.

    Args:
        anlage_id: ID der Anlage
        jahr: Jahr
        monat: Monat (1-12)

    Returns:
        list[InvestitionMonatsdatenResponse]: Liste der InvestitionMonatsdaten
    """
    # Alle aktiven Investitionen der Anlage laden
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.aktiv == True)
    )
    investitionen = inv_result.scalars().all()

    # InvestitionMonatsdaten für diesen Monat laden
    result = []
    for inv in investitionen:
        md_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id == inv.id)
            .where(InvestitionMonatsdaten.jahr == jahr)
            .where(InvestitionMonatsdaten.monat == monat)
        )
        imd = md_result.scalar_one_or_none()
        if imd:
            result.append(imd)

    return result


@router.get("/dashboard/wallbox/{anlage_id}", response_model=list[WallboxDashboardResponse])
async def get_wallbox_dashboard(
    anlage_id: int,
    strompreis_cent: float = Query(30.0),
    db: AsyncSession = Depends(get_db)
):
    """
    Wallbox Dashboard für eine Anlage.

    Zeigt Wallboxen mit Heimladung (aus E-Auto-Daten) und Ersparnis vs. externe Ladung.
    Die Wallbox-Daten kommen primär aus den E-Auto-Monatsdaten (ladung_pv_kwh + ladung_netz_kwh).
    """
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.WALLBOX.value)
        .where(Investition.aktiv == True)
    )
    wallboxen = inv_result.scalars().all()

    if not wallboxen:
        return []

    # E-Auto Monatsdaten für die Anlage laden (für Heimladung-Berechnung)
    eauto_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.E_AUTO.value)
        .where(Investition.aktiv == True)
    )
    eautos = eauto_result.scalars().all()

    # Aggregiere E-Auto-Heimladung über alle E-Autos
    gesamt_heim_pv = 0
    gesamt_heim_netz = 0
    gesamt_extern_kwh = 0
    gesamt_extern_euro = 0
    gesamt_ladevorgaenge = 0
    monate_set = set()

    for eauto in eautos:
        md_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id == eauto.id)
        )
        for md in md_result.scalars().all():
            d = md.verbrauch_daten or {}
            gesamt_heim_pv += d.get('ladung_pv_kwh', 0)
            gesamt_heim_netz += d.get('ladung_netz_kwh', 0)
            gesamt_extern_kwh += d.get('ladung_extern_kwh', 0)
            gesamt_extern_euro += d.get('ladung_extern_euro', 0)
            gesamt_ladevorgaenge += d.get('ladevorgaenge', 0)
            monate_set.add((md.jahr, md.monat))

    gesamt_heim_ladung = gesamt_heim_pv + gesamt_heim_netz
    anzahl_monate = len(monate_set)

    # PV-Anteil der Heimladung
    pv_anteil = (gesamt_heim_pv / gesamt_heim_ladung * 100) if gesamt_heim_ladung > 0 else 0

    # Kosten Heimladung (nur Netzstrom, PV ist "kostenlos")
    heim_kosten = gesamt_heim_netz * strompreis_cent / 100

    # Was hätte externe Ladung gekostet?
    # Durchschnittspreis extern (wenn vorhanden) oder Annahme 50 ct/kWh
    extern_preis_kwh = (gesamt_extern_euro / gesamt_extern_kwh) if gesamt_extern_kwh > 0 else 0.50
    heim_als_extern_kosten = gesamt_heim_ladung * extern_preis_kwh

    # Ersparnis durch Heimladen (Wallbox-ROI)
    ersparnis_vs_extern = heim_als_extern_kosten - heim_kosten

    dashboards = []
    for wallbox in wallboxen:
        # Wallbox-eigene Monatsdaten (falls vorhanden)
        md_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id == wallbox.id)
            .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
        )
        monatsdaten = md_result.scalars().all()

        params = wallbox.parameter or {}
        leistung_kw = params.get('leistung_kw', 11)

        zusammenfassung = {
            # Heimladung (aus E-Auto-Daten)
            'gesamt_heim_ladung_kwh': round(gesamt_heim_ladung, 1),
            'ladung_pv_kwh': round(gesamt_heim_pv, 1),
            'ladung_netz_kwh': round(gesamt_heim_netz, 1),
            'pv_anteil_prozent': round(pv_anteil, 1),
            # Externe Ladung zum Vergleich
            'extern_ladung_kwh': round(gesamt_extern_kwh, 1),
            'extern_kosten_euro': round(gesamt_extern_euro, 2),
            'extern_preis_kwh_euro': round(extern_preis_kwh, 2),
            # Kostenvergleich
            'heim_kosten_euro': round(heim_kosten, 2),
            'heim_als_extern_kosten_euro': round(heim_als_extern_kosten, 2),
            'ersparnis_vs_extern_euro': round(ersparnis_vs_extern, 2),
            # Wallbox-Info
            'leistung_kw': leistung_kw,
            'gesamt_ladevorgaenge': gesamt_ladevorgaenge,
            'ladevorgaenge_pro_monat': round(gesamt_ladevorgaenge / anzahl_monate, 1) if anzahl_monate > 0 else 0,
            'anzahl_monate': anzahl_monate,
        }

        dashboards.append(WallboxDashboardResponse(
            investition=wallbox,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


@router.get("/dashboard/balkonkraftwerk/{anlage_id}", response_model=list[BalkonkraftwerkDashboardResponse])
async def get_balkonkraftwerk_dashboard(
    anlage_id: int,
    strompreis_cent: float = Query(30.0),
    einspeiseverguetung_cent: float = Query(8.0),
    db: AsyncSession = Depends(get_db)
):
    """
    Balkonkraftwerk Dashboard für eine Anlage.

    Zeigt Balkonkraftwerke mit Erzeugung, Eigenverbrauch, Ersparnis.
    """
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.BALKONKRAFTWERK.value)
        .where(Investition.aktiv == True)
    )
    balkonkraftwerke = inv_result.scalars().all()

    if not balkonkraftwerke:
        return []

    dashboards = []
    for bkw in balkonkraftwerke:
        md_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id == bkw.id)
            .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
        )
        monatsdaten = md_result.scalars().all()

        gesamt_erzeugung = 0
        gesamt_eigenverbrauch = 0
        gesamt_einspeisung = 0
        gesamt_speicher_ladung = 0
        gesamt_speicher_entladung = 0

        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            gesamt_erzeugung += d.get('erzeugung_kwh', 0)
            gesamt_eigenverbrauch += d.get('eigenverbrauch_kwh', 0)
            gesamt_einspeisung += d.get('einspeisung_kwh', 0)
            gesamt_speicher_ladung += d.get('speicher_ladung_kwh', 0)
            gesamt_speicher_entladung += d.get('speicher_entladung_kwh', 0)

        # Parameter
        params = bkw.parameter or {}
        leistung_wp = params.get('leistung_wp', 0)
        anzahl = params.get('anzahl', 2)
        hat_speicher = params.get('hat_speicher', False)
        speicher_kapazitaet = params.get('speicher_kapazitaet_wh', 0)

        # Berechnungen
        gesamt_leistung_wp = leistung_wp * anzahl if leistung_wp else (bkw.leistung_kwp or 0) * 1000

        # Eigenverbrauchsquote
        eigenverbrauch_quote = (gesamt_eigenverbrauch / gesamt_erzeugung * 100) if gesamt_erzeugung > 0 else 0

        # Speicher-Effizienz
        speicher_effizienz = (gesamt_speicher_entladung / gesamt_speicher_ladung * 100) if gesamt_speicher_ladung > 0 else 0

        # Ersparnis: Eigenverbrauch spart Netzbezug, Einspeisung bringt Vergütung
        ersparnis_eigenverbrauch = gesamt_eigenverbrauch * strompreis_cent / 100
        erloes_einspeisung = gesamt_einspeisung * einspeiseverguetung_cent / 100
        gesamt_ersparnis = ersparnis_eigenverbrauch + erloes_einspeisung

        # CO2-Einsparung (0.38 kg/kWh für Eigenverbrauch)
        co2_ersparnis = gesamt_eigenverbrauch * 0.38

        # Spezifischer Ertrag (kWh pro kWp)
        spezifischer_ertrag = (gesamt_erzeugung / (gesamt_leistung_wp / 1000)) if gesamt_leistung_wp > 0 else 0

        zusammenfassung = {
            'gesamt_erzeugung_kwh': round(gesamt_erzeugung, 1),
            'gesamt_eigenverbrauch_kwh': round(gesamt_eigenverbrauch, 1),
            'gesamt_einspeisung_kwh': round(gesamt_einspeisung, 1),
            'eigenverbrauch_quote_prozent': round(eigenverbrauch_quote, 1),
            'spezifischer_ertrag_kwh_kwp': round(spezifischer_ertrag, 0),
            # Leistung
            'leistung_wp': gesamt_leistung_wp,
            'anzahl_module': anzahl,
            # Speicher (falls vorhanden)
            'hat_speicher': hat_speicher,
            'speicher_kapazitaet_wh': speicher_kapazitaet,
            'speicher_ladung_kwh': round(gesamt_speicher_ladung, 1) if hat_speicher else 0,
            'speicher_entladung_kwh': round(gesamt_speicher_entladung, 1) if hat_speicher else 0,
            'speicher_effizienz_prozent': round(speicher_effizienz, 1) if hat_speicher else 0,
            # Finanzen
            'ersparnis_eigenverbrauch_euro': round(ersparnis_eigenverbrauch, 2),
            'erloes_einspeisung_euro': round(erloes_einspeisung, 2),
            'gesamt_ersparnis_euro': round(gesamt_ersparnis, 2),
            # CO2
            'co2_ersparnis_kg': round(co2_ersparnis, 1),
            'anzahl_monate': len(monatsdaten),
        }

        dashboards.append(BalkonkraftwerkDashboardResponse(
            investition=bkw,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards


@router.get("/dashboard/sonstiges/{anlage_id}", response_model=list[SonstigesDashboardResponse])
async def get_sonstiges_dashboard(
    anlage_id: int,
    strompreis_cent: float = Query(30.0),
    einspeiseverguetung_cent: float = Query(8.0),
    db: AsyncSession = Depends(get_db)
):
    """
    Sonstiges Dashboard für eine Anlage.

    Zeigt sonstige Investitionen (Mini-BHKW, Pelletofen, etc.) mit kategorie-abhängigen Daten.
    """
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.SONSTIGES.value)
        .where(Investition.aktiv == True)
    )
    sonstige = inv_result.scalars().all()

    if not sonstige:
        return []

    dashboards = []
    for inv in sonstige:
        md_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id == inv.id)
            .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
        )
        monatsdaten = md_result.scalars().all()

        params = inv.parameter or {}
        kategorie = params.get('kategorie', 'erzeuger')
        beschreibung = params.get('beschreibung', '')

        # Aggregation basierend auf Kategorie
        gesamt_erzeugung = 0
        gesamt_eigenverbrauch = 0
        gesamt_einspeisung = 0
        gesamt_verbrauch = 0
        gesamt_bezug_pv = 0
        gesamt_bezug_netz = 0
        gesamt_ladung = 0
        gesamt_entladung = 0
        gesamt_sonderkosten = 0

        for md in monatsdaten:
            d = md.verbrauch_daten or {}
            gesamt_sonderkosten += d.get('sonderkosten_euro', 0)

            if kategorie == 'erzeuger':
                gesamt_erzeugung += d.get('erzeugung_kwh', 0)
                gesamt_eigenverbrauch += d.get('eigenverbrauch_kwh', 0)
                gesamt_einspeisung += d.get('einspeisung_kwh', 0)
            elif kategorie == 'verbraucher':
                gesamt_verbrauch += d.get('verbrauch_kwh', 0)
                gesamt_bezug_pv += d.get('bezug_pv_kwh', 0)
                gesamt_bezug_netz += d.get('bezug_netz_kwh', 0)
            elif kategorie == 'speicher':
                gesamt_ladung += d.get('ladung_kwh', 0)
                gesamt_entladung += d.get('entladung_kwh', 0)

        # Berechnungen je nach Kategorie
        if kategorie == 'erzeuger':
            eigenverbrauch_quote = (gesamt_eigenverbrauch / gesamt_erzeugung * 100) if gesamt_erzeugung > 0 else 0
            ersparnis_eigenverbrauch = gesamt_eigenverbrauch * strompreis_cent / 100
            erloes_einspeisung = gesamt_einspeisung * einspeiseverguetung_cent / 100
            gesamt_ersparnis = ersparnis_eigenverbrauch + erloes_einspeisung
            co2_ersparnis = gesamt_eigenverbrauch * 0.38

            zusammenfassung = {
                'kategorie': kategorie,
                'beschreibung': beschreibung,
                'gesamt_erzeugung_kwh': round(gesamt_erzeugung, 1),
                'gesamt_eigenverbrauch_kwh': round(gesamt_eigenverbrauch, 1),
                'gesamt_einspeisung_kwh': round(gesamt_einspeisung, 1),
                'eigenverbrauch_quote_prozent': round(eigenverbrauch_quote, 1),
                'ersparnis_eigenverbrauch_euro': round(ersparnis_eigenverbrauch, 2),
                'erloes_einspeisung_euro': round(erloes_einspeisung, 2),
                'gesamt_ersparnis_euro': round(gesamt_ersparnis, 2),
                'co2_ersparnis_kg': round(co2_ersparnis, 1),
                'sonderkosten_euro': round(gesamt_sonderkosten, 2),
                'anzahl_monate': len(monatsdaten),
            }

        elif kategorie == 'verbraucher':
            pv_anteil = (gesamt_bezug_pv / gesamt_verbrauch * 100) if gesamt_verbrauch > 0 else 0
            kosten_netz = gesamt_bezug_netz * strompreis_cent / 100
            # Ersparnis: PV-Strom statt Netzstrom
            ersparnis_pv = gesamt_bezug_pv * strompreis_cent / 100

            zusammenfassung = {
                'kategorie': kategorie,
                'beschreibung': beschreibung,
                'gesamt_verbrauch_kwh': round(gesamt_verbrauch, 1),
                'bezug_pv_kwh': round(gesamt_bezug_pv, 1),
                'bezug_netz_kwh': round(gesamt_bezug_netz, 1),
                'pv_anteil_prozent': round(pv_anteil, 1),
                'kosten_netz_euro': round(kosten_netz, 2),
                'ersparnis_pv_euro': round(ersparnis_pv, 2),
                'sonderkosten_euro': round(gesamt_sonderkosten, 2),
                'anzahl_monate': len(monatsdaten),
            }

        else:  # speicher
            effizienz = (gesamt_entladung / gesamt_ladung * 100) if gesamt_ladung > 0 else 0
            # Ersparnis: Spread zwischen Netzbezug und Einspeisung
            spread = strompreis_cent - einspeiseverguetung_cent
            ersparnis = gesamt_entladung * spread / 100

            zusammenfassung = {
                'kategorie': kategorie,
                'beschreibung': beschreibung,
                'gesamt_ladung_kwh': round(gesamt_ladung, 1),
                'gesamt_entladung_kwh': round(gesamt_entladung, 1),
                'effizienz_prozent': round(effizienz, 1),
                'ersparnis_euro': round(ersparnis, 2),
                'sonderkosten_euro': round(gesamt_sonderkosten, 2),
                'anzahl_monate': len(monatsdaten),
            }

        dashboards.append(SonstigesDashboardResponse(
            investition=inv,
            monatsdaten=monatsdaten,
            zusammenfassung=zusammenfassung,
        ))

    return dashboards
