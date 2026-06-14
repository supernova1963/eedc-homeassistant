"""
Investitionen API Routes

CRUD Endpoints für Investitionen (E-Auto, Wärmepumpe, Speicher, etc.).
"""

from typing import Optional, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from pydantic import BaseModel, Field
from datetime import date

from backend.core.exceptions import not_found
from backend.api.deps import get_db
from backend.models.investition import Investition, InvestitionTyp, InvestitionMonatsdaten
from backend.utils.investition_filter import aktiv_jetzt, aktiv_im_jahr, sort_investitionen_nach_typ
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.api.routes.strompreise import (
    lade_tarife_fuer_anlage,
    resolve_strompreis_for_komponente,
)
from backend.core.investition_parameter import (
    PARAM_E_AUTO,
    PARAM_E_AUTO_DEFAULTS,
    PARAM_SPEICHER,
    PARAM_SPEICHER_DEFAULTS,
    PARAM_WAERMEPUMPE,
    PARAM_WAERMEPUMPE_DEFAULTS,
)
from backend.core.wirtschaftlichkeit_defaults import EINSPEISEVERGUETUNG_DEFAULT_CENT
from backend.core.berechnungen.speicher_wirtschaftlichkeit import (
    aggregiere_speicher_ist,
    ist_eta_degradation_alarm,
)
from backend.services.speicher_wirtschaftlichkeit import (
    EffektiverLadepreisErgebnis,
    WirkungsgradErgebnis,
    berechne_effektiver_ladepreis,
    berechne_ist_wirkungsgrad,
)
from backend.services.eauto_wirtschaftlichkeit import (
    letzter_kraftstoffpreis_aus_lookup,
    resolve_eauto_benzinpreis,
)
from backend.core.calculations import CO2_FAKTOR_STROM_KG_KWH
from backend.core.berechnungen import einspeise_erloes_euro


# ============================================================================
# Etappe C (#264): Helper-Auflösung Param-Fallback ↔ IST-Werte
# ============================================================================


def _aufloesen_wirkungsgrad(
    eta_ist: Optional[WirkungsgradErgebnis],
    *,
    param_wirkungsgrad: float,
) -> tuple[float, str]:
    """Liefert (wirkungsgrad_prozent, quelle) für die ROI-Berechnung.

    Etappe C1: Helper liefert immer ein Ergebnis. Bei `wirkungsgrad_prozent
    is None` (z. B. `quelle="fenster-zu-kurz"`) fallen wir auf den Param-Wert
    zurück, geben aber die Helper-Quelle weiter, damit das Frontend die
    Datenbasis im Badge ausweisen kann.
    """
    if eta_ist is None:
        return param_wirkungsgrad, "param"
    if eta_ist.wirkungsgrad_prozent is None:
        # Helper hat geantwortet, aber nichts berechenbar (kurzes Fenster +
        # keine SoC-Werte, oder ladung_kwh=0). Param mit Helper-Quelle.
        return param_wirkungsgrad, eta_ist.quelle
    return eta_ist.wirkungsgrad_prozent, eta_ist.quelle


def _aufloesen_ladepreis(
    eff_ladepreis: Optional[EffektiverLadepreisErgebnis],
    *,
    nutzt_arbitrage: bool,
    param_lade_preis: float,
) -> tuple[Optional[float], str]:
    """Liefert (ladepreis_cent, quelle) für die ROI-Berechnung.

    Etappe C1/C4: Helper liefert immer ein Ergebnis. Bei nicht-belastbarer
    Quelle (`keine-tep-daten`, `keine-netzladung`, `datenbasis-zu-duenn` mit
    `effektiver_ladepreis_cent=None`) Param-Fallback. Ohne Arbitrage und
    ohne Param: `None` → der Spread-Service behandelt das als kostenneutral.
    """
    if eff_ladepreis is None:
        # Helper wurde gar nicht aufgerufen (z. B. kein Speicher)
        if nutzt_arbitrage:
            return param_lade_preis, "param"
        return None, "bezugspreis-fallback"
    if eff_ladepreis.effektiver_ladepreis_cent is None:
        if nutzt_arbitrage:
            return param_lade_preis, eff_ladepreis.quelle
        return None, eff_ladepreis.quelle
    return eff_ladepreis.effektiver_ladepreis_cent, eff_ladepreis.quelle


# =============================================================================
# Pydantic Schemas
# =============================================================================

class InvestitionBase(BaseModel):
    """Basis-Schema für Investition."""
    typ: str = Field(..., description="Investitionstyp (e-auto, speicher, etc.)")
    bezeichnung: str = Field(..., min_length=1, max_length=255)
    anschaffungsdatum: Optional[date] = None
    stilllegungsdatum: Optional[date] = Field(None, description="Endmarker: ab diesem Datum zählt die Investition nicht mehr für aktuelle/künftige Auswertungen")
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
    # #284: optionales Override der grauen Herstellungs-Last (CO2) für die
    # CO2-Amortisation; leer = Default-Richtwert nach Typ/Größe.
    graue_last_kg: Optional[float] = Field(None, ge=0, description="Graue Herstellungs-Last in kg CO2 (leer = Default nach Typ/Größe)")


class InvestitionCreate(InvestitionBase):
    """Schema für Investition-Erstellung."""
    anlage_id: int


class InvestitionUpdate(BaseModel):
    """Schema für Investition-Update."""
    bezeichnung: Optional[str] = Field(None, min_length=1, max_length=255)
    anschaffungsdatum: Optional[date] = None
    stilllegungsdatum: Optional[date] = None
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
    graue_last_kg: Optional[float] = Field(None, ge=0)


class InvestitionResponse(InvestitionBase):
    """Schema für Investition-Response."""
    id: int
    anlage_id: int
    einsparung_prognose_jahr: Optional[float]
    co2_einsparung_prognose_kg: Optional[float]

    class Config:
        from_attributes = True


def _gruppiere_investitionen(
    investitionen: list[Investition],
) -> tuple[dict[int, dict], list[Investition], list[Investition]]:
    """Gruppiert Investitionen strukturell für die ROI-Berechnung.

    Reine Zwei-Pass-Zuordnung (keine DB-I/O, keine Berechnung, keine
    Anzeige-Strings) der bereits geladenen Investitions-Liste:

    - **PV-Systeme** — Wechselrichter mit zugeordneten PV-Modulen und
      DC-gekoppelten Speichern (Parent = WR). ROI nur auf System-Ebene
      sinnvoll.
    - **Standalone** — AC-gekoppelte Speicher (ohne gültigen WR-Parent) und
      alle übrigen Typen (E-Auto, Wärmepumpe, Wallbox, Balkonkraftwerk,
      Sonstiges).
    - **Orphan-PV-Module** — PV-Module ohne (gültige)
      Wechselrichter-Zuordnung (Altdaten).

    Zwei-Pass-Ansatz: erst alle Wechselrichter registrieren, damit
    `parent_investition_id` unabhängig von der Sortierung aufgelöst werden
    kann.

    Returns:
        (pv_systeme, standalone, orphan_pv_module) — `pv_systeme` als
        ``wr_id -> {"wr": Investition, "pv_module": [...], "speicher": [...]}``.
    """
    pv_systeme: dict[int, dict] = {}
    standalone: list[Investition] = []
    orphan_pv_module: list[Investition] = []

    for inv in investitionen:
        if inv.typ == InvestitionTyp.WECHSELRICHTER.value:
            pv_systeme[inv.id] = {"wr": inv, "pv_module": [], "speicher": []}

    for inv in investitionen:
        if inv.typ == InvestitionTyp.WECHSELRICHTER.value:
            continue  # bereits im ersten Pass registriert
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

    return pv_systeme, standalone, orphan_pv_module


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


# v3.25.0: Phantom-Endpoint /typen + InvestitionTypInfo + parameter_schema entfernt.
# Niemand hat das Schema im Frontend gelesen (useInvestitionTypen war exportiert, aber
# nirgends aufgerufen), und der Schema-Inhalt war historisch von Form/Wizard und
# Backend-Reads auseinandergedriftet — siehe docs/drafts/INVENTUR-INVESTITIONS-PARAMETER.md.
# Single Source of Truth ist jetzt:
#   - Frontend: eedc/frontend/src/lib/investitionParameter.ts
#   - Backend:  eedc/backend/core/investition_parameter.py


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
        .where(aktiv_jetzt())
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

    # Kanonische Typ-Reihenfolge (Fundament P4 / F7) statt alphabetisch.
    query = query.order_by(Investition.bezeichnung)

    result = await db.execute(query)
    return sort_investitionen_nach_typ(result.scalars().all())


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
        raise not_found("Investition")

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
        raise not_found("Anlage")

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
            raise not_found("Parent-Investition")
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

    # Speicher: Parent (Wechselrichter oder Balkonkraftwerk) ist optional
    elif typ == InvestitionTyp.SPEICHER.value:
        if parent_id:
            parent_result = await db.execute(
                select(Investition).where(Investition.id == parent_id)
            )
            parent = parent_result.scalar_one_or_none()
            if not parent:
                raise not_found("Parent-Investition")
            erlaubte_parent_typen = {
                InvestitionTyp.WECHSELRICHTER.value,
                InvestitionTyp.BALKONKRAFTWERK.value,
            }
            if parent.typ not in erlaubte_parent_typen:
                raise HTTPException(
                    status_code=400,
                    detail=f"Speicher können nur Wechselrichtern oder Balkonkraftwerken zugeordnet werden, nicht '{parent.typ}'"
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
        raise not_found("Investition")

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
        raise not_found("Investition")

    # sensor_mapping der Anlage aufräumen (verwaiste Einträge vermeiden)
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == inv.anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if anlage and anlage.sensor_mapping:
        inv_mapping = anlage.sensor_mapping.get("investitionen", {})
        if str(investition_id) in inv_mapping:
            del inv_mapping[str(investition_id)]
            flag_modified(anlage, "sensor_mapping")

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
    # Vorgeschlagener Default-Wert für den Benzinpreis-Slider (UI): letzter
    # `Monatsdaten.kraftstoffpreis_euro` aus dem EU Weekly Oil Bulletin, sonst
    # der Param-Default. Nur ein Hinweis — bei E-Auto-Berechnungen wird pro
    # Investition aufgelöst (Slider → per-Inv-Param → Monatsdaten → Default).
    benzinpreis_hinweis_euro: Optional[float] = None


@router.get("/roi/{anlage_id}", response_model=ROIDashboardResponse)
async def get_roi_dashboard(
    anlage_id: int,
    strompreis_cent: Optional[float] = Query(None, description="Override: Strompreis in Cent/kWh (auto aus DB wenn leer)"),
    einspeiseverguetung_cent: Optional[float] = Query(None, description="Override: Einspeisevergütung in Cent/kWh (auto aus DB wenn leer)"),
    benzinpreis_euro: Optional[float] = Query(None, description="Override: Benzinpreis in Euro/Liter (Slider). Bei None: per-Inv-Param → letzter Monatsdaten-Preis → Default 1,65."),
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
        berechne_ust_eigenverbrauch,
    )
    from sqlalchemy import func
    from backend.models.pvgis_prognose import PVGISPrognose

    # Anlage prüfen
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise not_found("Anlage")

    # Tarife laden (allgemein + Spezialtarife)
    tarife = await lade_tarife_fuer_anlage(db, anlage_id)
    allgemein_tarif = tarife.get("allgemein")
    strompreis_cent = strompreis_cent or resolve_strompreis_for_komponente(tarife, "allgemein")
    einspeiseverguetung_cent = einspeiseverguetung_cent or (allgemein_tarif.einspeiseverguetung_cent_kwh if allgemein_tarif else EINSPEISEVERGUETUNG_DEFAULT_CENT)
    wp_tarif = tarife.get("waermepumpe")
    wp_strompreis = wp_tarif.netzbezug_arbeitspreis_cent_kwh if wp_tarif else strompreis_cent
    wallbox_tarif = tarife.get("wallbox")
    wallbox_strompreis = wallbox_tarif.netzbezug_arbeitspreis_cent_kwh if wallbox_tarif else strompreis_cent

    # Investitionen laden — Issue #123: ROI historisch, spätere Stilllegung
    # darf Vergangenheit nicht löschen. Siehe Roadmap R1 für zeitanteilige Gewichtung.
    inv_stmt = (
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .order_by(Investition.id)
    )
    if jahr is not None:
        inv_stmt = inv_stmt.where(aktiv_im_jahr(jahr))
    inv_result = await db.execute(inv_stmt)
    investitionen = sort_investitionen_nach_typ(inv_result.scalars().all())

    # Benzinpreis-Lookup für E-Auto-ROI: Monatsdaten.kraftstoffpreis_euro
    # (EU Weekly Oil Bulletin, seit v3.17.0) ist die Realität. Vorher las
    # `get_roi_dashboard` nur den Query-Default 1,85 € und ignorierte sowohl
    # diese Daten als auch das per-Investition gespeicherte `benzinpreis_euro`
    # — gleiche Bug-Klasse wie der v3.25.0-Fix für jahresfahrleistung_km etc.,
    # damals für benzinpreis_euro vergessen.
    benzinpreis_md_result = await db.execute(
        select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id)
    )
    benzinpreis_lookup: dict[tuple[int, int], Optional[float]] = {
        (md.jahr, md.monat): md.kraftstoffpreis_euro
        for md in benzinpreis_md_result.scalars().all()
    }
    letzter_marktpreis = letzter_kraftstoffpreis_aus_lookup(benzinpreis_lookup)
    benzinpreis_hinweis_euro = (
        letzter_marktpreis
        if letzter_marktpreis is not None
        else float(PARAM_E_AUTO_DEFAULTS["benzinpreis_euro"])
    )

    # Sonstige Erträge & Ausgaben (manuell pro Investition/Monat gepflegt) —
    # #310 rilmor-mhrs: get_roi_dashboard hat diese realisierten Beträge nie
    # eingerechnet, während Cockpit-Monatsbericht und Aussichten-Finanzprognose
    # sie längst über `berechne_sonstige_netto` berücksichtigen. Reiner Read-
    # Pfad, SoT-Helper `utils/sonstige_positionen`.
    from backend.utils.sonstige_positionen import berechne_sonstige_netto
    inv_ids_alle = [inv.id for inv in investitionen]
    sonstige_netto_by_inv: dict[int, float] = {}
    if inv_ids_alle:
        smd_query = select(InvestitionMonatsdaten).where(
            InvestitionMonatsdaten.investition_id.in_(inv_ids_alle)
        )
        if jahr is not None:
            smd_query = smd_query.where(InvestitionMonatsdaten.jahr == jahr)
        smd_result = await db.execute(smd_query)
        for imd in smd_result.scalars().all():
            netto = berechne_sonstige_netto(imd.verbrauch_daten)
            if netto:
                sonstige_netto_by_inv[imd.investition_id] = (
                    sonstige_netto_by_inv.get(imd.investition_id, 0.0) + netto
                )

    # Bei jahr=None sind die Jahres-Einsparungen Jahresdurchschnitte → die
    # (über alle Jahre summierten) sonstigen Netto-Beträge auf dieselbe
    # Jahresbasis bringen. Divisor = Anzahl Jahre mit Monatsdaten (gleiche
    # Basis wie die PV-Einsparungs-Mittelung), mind. 1.
    _md_jahre = {j for (j, _m) in benzinpreis_lookup.keys()}
    _sonstige_divisor = max(len(_md_jahre), 1) if jahr is None else 1

    def _sonstige_jahr_fuer(inv_ids: list[int]) -> float:
        """Sonstige Netto-€/Jahr für eine Gruppe von Investitionen (eine
        Investition gehört zu genau einer ROI-Berechnung → kein Doppelzählen)."""
        summe = sum(sonstige_netto_by_inv.get(i, 0.0) for i in inv_ids)
        return summe / _sonstige_divisor

    # ==========================================================================
    # Phase 1: Gruppiere Investitionen nach PV-Systemen und Standalone
    # ==========================================================================
    # Strukturierung extrahiert nach modul-internem `_gruppiere_investitionen`
    # (rein, DB-/Anzeige-frei). `pv_systeme`: wr_id -> {wr, pv_module[], speicher[]};
    # `orphan_pv_module`: PV-Module ohne WR-Zuordnung (Altdaten).
    pv_systeme, standalone, orphan_pv_module = _gruppiere_investitionen(investitionen)

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
        # Issue #123: historische PV-Einsparung — keine aktiv-Filterung, damit
        # spätere Stilllegung Vergangenheit nicht entfernt.
        pv_ids_result = await db.execute(
            select(Investition.id)
            .where(Investition.anlage_id == anlage_id)
            .where(Investition.typ == "pv-module")
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
                    # Gespeicherte Keys sind 'e_m'/'monat' (siehe pvgis.py); zuvor
                    # las dieser Pfad 'E_m'/'month' → Summe immer 0 → PVGIS-Gewichtung
                    # griff nie, stiller Fallback auf lineare Hochrechnung.
                    pvgis_jahres_summe = sum(m.get('e_m', 0) for m in pvgis_monatswerte)
                    if pvgis_jahres_summe > 0:
                        pvgis_vorhandene_summe = sum(
                            m.get('e_m', 0) for m in pvgis_monatswerte
                            if m.get('monat', 0) in vorhandene_monate
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

        # Einsparung berechnen. §51-Erlös über SoT (ADR-001, M3); neg_preis_kwh
        # = None, weil auf Monatsdaten-Aggregat-Ebene keine Negativpreis-Spalte
        # vorliegt → volle Einspeisung wie zuvor (verhaltensneutral).
        einspeise_erloes = einspeise_erloes_euro(
            einspeisung_jahr, None, einspeiseverguetung_cent
        ).erloes_euro
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

    # Etappe B (#264): Speicher-IST-Aggregate einmal laden — sowohl für
    # DC-gekoppelte (Phase 3) als auch standalone AC-Speicher (Phase 5).
    # Pro Speicher wird `entladung_kwh` und `ladung_netz_kwh` aus allen
    # aktiven Monatsdaten summiert und auf ein Jahr hochgerechnet, damit
    # das ROI-Modell die echte PV/Netz-Aufteilung nutzen kann statt der
    # impliziten 100%-PV-Annahme.
    #
    # Etappe C (#264): zusätzlich aus dem stündlichen TagesEnergieProfil
    # den effektiven Ø-Netzladepreis (Tibber/aWATTar) und den SoC-
    # korrigierten IST-Wirkungsgrad ermitteln. Beide werden an den Spread-
    # Service durchgereicht und überstimmen den Param-Wert.
    speicher_invs_alle = [i for i in investitionen if i.typ == InvestitionTyp.SPEICHER.value]
    speicher_ist_by_inv: dict[int, "SpeicherIstAggregat | None"] = {}
    speicher_ladepreis_anlage: Optional[EffektiverLadepreisErgebnis] = None
    speicher_eta_by_inv: dict[int, "WirkungsgradErgebnis | None"] = {}
    if speicher_invs_alle:
        speicher_ids = [i.id for i in speicher_invs_alle]
        sp_imd_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id.in_(speicher_ids))
        )
        sp_imd_by_inv: dict[int, list[InvestitionMonatsdaten]] = {}
        for imd in sp_imd_result.scalars().all():
            sp_imd_by_inv.setdefault(imd.investition_id, []).append(imd)
        for sp in speicher_invs_alle:
            # Filter analog #236: Stilllegung/Inbetriebnahme respektieren.
            aktive_daten = [
                (imd.verbrauch_daten or {})
                for imd in sp_imd_by_inv.get(sp.id, [])
                if sp.ist_aktiv_im_monat(imd.jahr, imd.monat)
            ]
            speicher_ist_by_inv[sp.id] = aggregiere_speicher_ist(aktive_daten)

        # Etappe C: TEP-Lookups einmalig pro Anlage. Periode = älteste
        # Speicher-Inbetriebnahme bis heute (oder neueste Stilllegung).
        installs = [sp.anschaffungsdatum for sp in speicher_invs_alle if sp.anschaffungsdatum]
        stilllegungen = [sp.stilllegungsdatum for sp in speicher_invs_alle if sp.stilllegungsdatum]
        if installs:
            periode_von = min(installs)
            periode_bis = max(stilllegungen) if stilllegungen and len(stilllegungen) == len(speicher_invs_alle) else date.today()
            speicher_ladepreis_anlage = await berechne_effektiver_ladepreis(
                db, anlage_id=anlage_id, von=periode_von, bis=periode_bis,
            )

            # Pro Speicher η-IST aus IMD-Aggregaten und (bei kurzem Fenster)
            # SoC-Werten am Periodenrand.
            for sp in speicher_invs_alle:
                ist = speicher_ist_by_inv.get(sp.id)
                if ist is None:
                    continue
                params_sp = sp.parameter or {}
                nutzbar = params_sp.get(
                    PARAM_SPEICHER["NUTZBARE_KAPAZITAET_KWH"],
                    params_sp.get(PARAM_SPEICHER["KAPAZITAET_KWH"], 0),
                ) or 0
                speicher_eta_by_inv[sp.id] = await berechne_ist_wirkungsgrad(
                    db,
                    anlage_id=anlage_id,
                    von=periode_von,
                    bis=periode_bis,
                    ladung_kwh=ist.ladung_kwh_jahr / ist.jahres_faktor,
                    entladung_kwh=ist.entladung_kwh_jahr / ist.jahres_faktor,
                    nutzbare_kapazitaet_kwh=float(nutzbar),
                    fenster_monate=ist.anzahl_monate,
                )

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
        system_betriebskosten = (wr.betriebskosten_jahr or 0)

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
            system_betriebskosten += (inv.betriebskosten_jahr or 0)

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
            system_betriebskosten += (inv.betriebskosten_jahr or 0)

            params = inv.parameter or {}
            kapazitaet = params.get(PARAM_SPEICHER["KAPAZITAET_KWH"], 10)
            wirkungsgrad = params.get(PARAM_SPEICHER["WIRKUNGSGRAD_PROZENT"], PARAM_SPEICHER_DEFAULTS["wirkungsgrad_prozent"])
            # Bug #5 v3.25.0: vorher 'nutzt_arbitrage' (toter Schema-Key), Form/Wizard schreiben 'arbitrage_faehig'.
            nutzt_arbitrage = params.get(PARAM_SPEICHER["ARBITRAGE_FAEHIG"], PARAM_SPEICHER_DEFAULTS["arbitrage_faehig"])
            lade_preis_dc = params.get(
                PARAM_SPEICHER["LADE_DURCHSCHNITTSPREIS_CENT"],
                PARAM_SPEICHER_DEFAULTS["lade_durchschnittspreis_cent"],
            )

            ist_aggregat = speicher_ist_by_inv.get(inv.id)
            # Etappe C (#264): dyn. Ladepreis aus TEP überstimmt Param,
            # IST-η aus SoC-korrigierter Bilanz überstimmt Param-η. Beide
            # Helper liefern immer ein Ergebnis (C1); Wert ist `None` wenn
            # Datenbasis zu dünn → Fallback auf Param mit Quelle-Indikator.
            eff_ladepreis = speicher_ladepreis_anlage
            eta_ist = speicher_eta_by_inv.get(inv.id)

            wirkungsgrad_eff, wirkungsgrad_quelle = _aufloesen_wirkungsgrad(
                eta_ist, param_wirkungsgrad=wirkungsgrad,
            )
            lade_preis_eff, ladepreis_quelle = _aufloesen_ladepreis(
                eff_ladepreis,
                nutzt_arbitrage=nutzt_arbitrage,
                param_lade_preis=lade_preis_dc,
            )

            result = berechne_speicher_einsparung(
                kapazitaet_kwh=kapazitaet,
                wirkungsgrad_prozent=wirkungsgrad_eff,
                netzbezug_preis_cent=strompreis_cent,
                einspeiseverguetung_cent=einspeiseverguetung_cent,
                nutzt_arbitrage=nutzt_arbitrage,
                lade_preis_cent=lade_preis_eff,
                ist_entladung_kwh=ist_aggregat.entladung_kwh_jahr if ist_aggregat else None,
                ist_ladung_netz_kwh=ist_aggregat.ladung_netz_kwh_jahr if ist_aggregat else 0,
            )
            inv_einsparung = result.jahres_einsparung_euro
            inv_co2 = result.co2_einsparung_kg
            system_einsparung += inv_einsparung
            system_co2 += inv_co2

            komp_detail: dict[str, Any] = {'kapazitaet_kwh': kapazitaet, 'dc_gekoppelt': True}
            if ist_aggregat is not None:
                komp_detail.update({
                    'modus': 'ist',
                    'ist_entladung_kwh_jahr': round(ist_aggregat.entladung_kwh_jahr, 1),
                    'ist_ladung_netz_kwh_jahr': round(ist_aggregat.ladung_netz_kwh_jahr, 1),
                    'ist_monate': ist_aggregat.anzahl_monate,
                    'pv_anteil_euro': result.pv_anteil_euro,
                    'netz_anteil_euro': result.arbitrage_anteil_euro,
                    'effektiver_ladepreis_cent': round(lade_preis_eff, 2) if (lade_preis_eff is not None and nutzt_arbitrage) else None,
                    'ladepreis_quelle': ladepreis_quelle,
                    'verwendetes_wirkungsgrad_prozent': round(wirkungsgrad_eff, 1),
                    'wirkungsgrad_quelle': wirkungsgrad_quelle,
                })
                # Etappe C1 Diagnose-Felder für UI-Badge bei dünner Datenbasis.
                if eff_ladepreis is not None and eff_ladepreis.quelle == "datenbasis-zu-duenn":
                    komp_detail['ladepreis_abdeckung_prozent'] = round(eff_ladepreis.abdeckung_prozent, 0)
                # Etappe C3 Degradations-Alarm an der η-KPI.
                if eta_ist is not None and eta_ist.wirkungsgrad_prozent is not None:
                    komp_detail['eta_degradation_alarm'] = ist_eta_degradation_alarm(
                        ist_wirkungsgrad_prozent=eta_ist.wirkungsgrad_prozent,
                        param_wirkungsgrad_prozent=wirkungsgrad,
                    )
                    komp_detail['param_wirkungsgrad_prozent'] = round(wirkungsgrad, 1)
            else:
                komp_detail['modus'] = 'prognose'
            komponenten.append(ROIKomponente(
                investition_id=inv.id,
                bezeichnung=f"{inv.bezeichnung} ({kapazitaet} kWh)",
                typ=inv.typ,
                kosten=inv_kosten,
                kosten_alternativ=inv_alternativ,
                relevante_kosten=inv_kosten - inv_alternativ,
                einsparung=round(inv_einsparung, 2),
                co2_einsparung_kg=round(inv_co2, 1),
                detail=komp_detail,
            ))

        # System-ROI berechnen
        # #310: manuell gepflegte sonstige Erträge/Ausgaben des Systems
        # (WR + PV-Module + DC-Speicher) einrechnen.
        system_sonstige = _sonstige_jahr_fuer(
            [wr.id, *(m.id for m in pv_module), *(s.id for s in dc_speicher)]
        )
        system_einsparung += system_sonstige
        system_relevante = system_kosten - system_alternativ
        system_netto_einsparung = system_einsparung - system_betriebskosten
        roi_result = berechne_roi(system_kosten, system_einsparung, system_alternativ, system_betriebskosten)

        berechnungen.append(ROIBerechnung(
            investition_id=wr.id,  # WR-ID als System-ID
            investition_bezeichnung=f"PV-System {wr.bezeichnung}",
            investition_typ="pv-system",
            anschaffungskosten=system_kosten,
            anschaffungskosten_alternativ=system_alternativ,
            relevante_kosten=system_relevante,
            jahres_einsparung=round(system_netto_einsparung, 2),
            roi_prozent=roi_result['roi_prozent'],
            amortisation_jahre=roi_result['amortisation_jahre'],
            co2_einsparung_kg=round(system_co2, 1),
            detail_berechnung={
                **pv_detail,
                'komponenten_count': len(komponenten),
                'system_kwp': system_kwp,
                'sonstige_netto_euro': round(system_sonstige, 2),
            },
            komponenten=komponenten,
        ))

        gesamt_investition += system_kosten
        gesamt_relevante += system_relevante
        gesamt_einsparung += system_netto_einsparung
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

        # #310: sonstige Erträge/Ausgaben des Moduls einrechnen.
        orphan_sonstige = _sonstige_jahr_fuer([inv.id])
        jahres_einsparung += orphan_sonstige
        betriebskosten = inv.betriebskosten_jahr or 0
        netto_einsparung = jahres_einsparung - betriebskosten
        roi_result = berechne_roi(kosten, jahres_einsparung, alternativ, betriebskosten)

        berechnungen.append(ROIBerechnung(
            investition_id=inv.id,
            investition_bezeichnung=f"{inv.bezeichnung} (ohne WR)",
            investition_typ=inv.typ,
            anschaffungskosten=kosten,
            anschaffungskosten_alternativ=alternativ,
            relevante_kosten=relevante,
            jahres_einsparung=round(netto_einsparung, 2),
            roi_prozent=roi_result['roi_prozent'],
            amortisation_jahre=roi_result['amortisation_jahre'],
            co2_einsparung_kg=round(co2_einsparung, 1),
            detail_berechnung={
                **pv_detail,
                'hinweis': 'PV-Modul ohne Wechselrichter-Zuordnung - bitte zuordnen',
                'anteil_prozent': round(anteil * 100, 1) if gesamt_kwp > 0 else 0,
                'sonstige_netto_euro': round(orphan_sonstige, 2),
            },
        ))

        gesamt_investition += kosten
        gesamt_relevante += relevante
        gesamt_einsparung += netto_einsparung
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
            # AC-gekoppelter Speicher — Bug #5 v3.25.0 fix wie oben (DC-Speicher)
            kapazitaet = params.get(PARAM_SPEICHER["KAPAZITAET_KWH"], 10)
            wirkungsgrad = params.get(PARAM_SPEICHER["WIRKUNGSGRAD_PROZENT"], PARAM_SPEICHER_DEFAULTS["wirkungsgrad_prozent"])
            nutzt_arbitrage = params.get(PARAM_SPEICHER["ARBITRAGE_FAEHIG"], PARAM_SPEICHER_DEFAULTS["arbitrage_faehig"])
            lade_preis = params.get(PARAM_SPEICHER["LADE_DURCHSCHNITTSPREIS_CENT"], PARAM_SPEICHER_DEFAULTS["lade_durchschnittspreis_cent"])
            entlade_preis = params.get(PARAM_SPEICHER["ENTLADE_VERMIEDENER_PREIS_CENT"], PARAM_SPEICHER_DEFAULTS["entlade_vermiedener_preis_cent"])

            ist_aggregat = speicher_ist_by_inv.get(inv.id)
            # Etappe C (#264): siehe DC-Pfad oben — dieselbe Param-Fallback-
            # Auflösung via _aufloesen_wirkungsgrad / _aufloesen_ladepreis.
            eff_ladepreis = speicher_ladepreis_anlage
            eta_ist = speicher_eta_by_inv.get(inv.id)

            wirkungsgrad_eff, wirkungsgrad_quelle = _aufloesen_wirkungsgrad(
                eta_ist, param_wirkungsgrad=wirkungsgrad,
            )
            lade_preis_eff, ladepreis_quelle = _aufloesen_ladepreis(
                eff_ladepreis,
                nutzt_arbitrage=nutzt_arbitrage,
                param_lade_preis=lade_preis,
            )

            result = berechne_speicher_einsparung(
                kapazitaet_kwh=kapazitaet,
                wirkungsgrad_prozent=wirkungsgrad_eff,
                netzbezug_preis_cent=strompreis_cent,
                einspeiseverguetung_cent=einspeiseverguetung_cent,
                nutzt_arbitrage=nutzt_arbitrage,
                lade_preis_cent=lade_preis_eff,
                entlade_preis_cent=entlade_preis,
                ist_entladung_kwh=ist_aggregat.entladung_kwh_jahr if ist_aggregat else None,
                ist_ladung_netz_kwh=ist_aggregat.ladung_netz_kwh_jahr if ist_aggregat else 0,
            )
            jahres_einsparung = result.jahres_einsparung_euro
            co2_einsparung = result.co2_einsparung_kg
            detail = {
                'nutzbare_speicherung_kwh': result.nutzbare_speicherung_kwh,
                'pv_anteil_euro': result.pv_anteil_euro,
                'arbitrage_anteil_euro': result.arbitrage_anteil_euro,
                'hinweis': 'AC-gekoppelter Speicher',
                'modus': 'ist' if ist_aggregat is not None else 'prognose',
            }
            if ist_aggregat is not None:
                detail.update({
                    'ist_entladung_kwh_jahr': round(ist_aggregat.entladung_kwh_jahr, 1),
                    'ist_ladung_netz_kwh_jahr': round(ist_aggregat.ladung_netz_kwh_jahr, 1),
                    'ist_monate': ist_aggregat.anzahl_monate,
                    # `arbitrage_anteil_euro` ist im IST-Modus der gemessene
                    # Netz-Anteil-Vorteil (siehe calculations.berechne_speicher_einsparung).
                    'netz_anteil_euro': result.arbitrage_anteil_euro,
                    'effektiver_ladepreis_cent': round(lade_preis_eff, 2) if (lade_preis_eff is not None and nutzt_arbitrage) else None,
                    'ladepreis_quelle': ladepreis_quelle,
                    'verwendetes_wirkungsgrad_prozent': round(wirkungsgrad_eff, 1),
                    'wirkungsgrad_quelle': wirkungsgrad_quelle,
                })
                if eff_ladepreis is not None and eff_ladepreis.quelle == "datenbasis-zu-duenn":
                    detail['ladepreis_abdeckung_prozent'] = round(eff_ladepreis.abdeckung_prozent, 0)
                if eta_ist is not None and eta_ist.wirkungsgrad_prozent is not None:
                    detail['eta_degradation_alarm'] = ist_eta_degradation_alarm(
                        ist_wirkungsgrad_prozent=eta_ist.wirkungsgrad_prozent,
                        param_wirkungsgrad_prozent=wirkungsgrad,
                    )
                    detail['param_wirkungsgrad_prozent'] = round(wirkungsgrad, 1)

        elif inv.typ == InvestitionTyp.E_AUTO.value:
            # Bugs #1, #2, #3, #4 v3.25.0: vorher las dieser Block aus toten Schema-Keys
            # ('km_jahr', 'pv_anteil_prozent', 'benzin_verbrauch_liter_100km', 'nutzt_v2h')
            # — Form/Wizard schreiben aber 'jahresfahrleistung_km', 'pv_ladeanteil_prozent',
            # 'vergleich_verbrauch_l_100km', 'v2h_faehig'. ROI ignorierte deshalb alle vier
            # User-Eingaben und nutzte stattdessen die hier hinterlegten Defaults.
            km_jahr = params.get(PARAM_E_AUTO["JAHRESFAHRLEISTUNG_KM"], PARAM_E_AUTO_DEFAULTS["jahresfahrleistung_km"])
            verbrauch = params.get(PARAM_E_AUTO["VERBRAUCH_KWH_100KM"], PARAM_E_AUTO_DEFAULTS["verbrauch_kwh_100km"])
            pv_anteil = params.get(PARAM_E_AUTO["PV_LADEANTEIL_PROZENT"], PARAM_E_AUTO_DEFAULTS["pv_ladeanteil_prozent"])
            benzin_verbrauch = params.get(PARAM_E_AUTO["VERGLEICH_VERBRAUCH_L_100KM"], PARAM_E_AUTO_DEFAULTS["vergleich_verbrauch_l_100km"])
            nutzt_v2h = params.get(PARAM_E_AUTO["V2H_FAEHIG"], PARAM_E_AUTO_DEFAULTS["v2h_faehig"])
            v2h_entladung = params.get(PARAM_E_AUTO["V2H_ENTLADUNG_KWH_JAHR"], 0)
            v2h_preis = params.get(PARAM_E_AUTO["V2H_ENTLADE_PREIS_CENT"], strompreis_cent)

            # Benzinpreis-Auflösung: Slider-Override > per-Inv-Param > letzter
            # Monatsdaten-Preis (EU OB) > Default 1,65. Korrigiert die v3.25.0-
            # Lücke: 'benzinpreis_euro' wurde damals nicht in die Liste der
            # aus `params` zu lesenden Felder aufgenommen.
            preis = resolve_eauto_benzinpreis(
                query_override=benzinpreis_euro,
                eauto_parameter=params,
                letzter_monats_benzinpreis=letzter_marktpreis,
            )

            result = berechne_eauto_einsparung(
                km_jahr=km_jahr,
                verbrauch_kwh_100km=verbrauch,
                pv_anteil_prozent=pv_anteil,
                strompreis_cent=wallbox_strompreis,
                benzinpreis_euro_liter=preis.preis_euro,
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
                'verwendeter_benzinpreis_euro': round(preis.preis_euro, 3),
                'benzinpreis_quelle': preis.quelle,
                'hinweis': f'E-Auto: {km_jahr} km/Jahr',
            }

        elif inv.typ == InvestitionTyp.WAERMEPUMPE.value:
            # Modus-Auswahl: gesamt_jaz (Standard), scop (EU-Label) oder getrennte_cops
            effizienz_modus = params.get(PARAM_WAERMEPUMPE["EFFIZIENZ_MODUS"], PARAM_WAERMEPUMPE_DEFAULTS["effizienz_modus"])
            pv_anteil = params.get(PARAM_WAERMEPUMPE["PV_ANTEIL_PROZENT"], PARAM_WAERMEPUMPE_DEFAULTS["pv_anteil_prozent"])
            alter_energietraeger = params.get(PARAM_WAERMEPUMPE["ALTER_ENERGIETRAEGER"], PARAM_WAERMEPUMPE_DEFAULTS["alter_energietraeger"])
            alter_preis = params.get(PARAM_WAERMEPUMPE["ALTER_PREIS_CENT_KWH"], PARAM_WAERMEPUMPE_DEFAULTS["alter_preis_cent_kwh"])
            alternativ_zusatzkosten = params.get(PARAM_WAERMEPUMPE["ALTERNATIV_ZUSATZKOSTEN_JAHR"], 0) or 0
            heizwaermebedarf = params.get(PARAM_WAERMEPUMPE["HEIZWAERMEBEDARF_KWH"], PARAM_WAERMEPUMPE_DEFAULTS["heizwaermebedarf_kwh"])
            warmwasserbedarf = params.get(PARAM_WAERMEPUMPE["WARMWASSERBEDARF_KWH"], PARAM_WAERMEPUMPE_DEFAULTS["warmwasserbedarf_kwh"])

            if effizienz_modus == 'getrennte_cops':
                # Getrennte COPs für Heizung und Warmwasser
                cop_heizung = params.get(PARAM_WAERMEPUMPE["COP_HEIZUNG"], PARAM_WAERMEPUMPE_DEFAULTS["cop_heizung"])
                cop_warmwasser = params.get(PARAM_WAERMEPUMPE["COP_WARMWASSER"], PARAM_WAERMEPUMPE_DEFAULTS["cop_warmwasser"])

                result = berechne_waermepumpe_einsparung(
                    heizwaermebedarf_kwh=heizwaermebedarf,
                    warmwasserbedarf_kwh=warmwasserbedarf,
                    cop_heizung=cop_heizung,
                    cop_warmwasser=cop_warmwasser,
                    effizienz_modus='getrennte_cops',
                    strompreis_cent=wp_strompreis,
                    pv_anteil_prozent=pv_anteil,
                    alter_energietraeger=alter_energietraeger,
                    alter_preis_cent_kwh=alter_preis,
                    alternativ_zusatzkosten_jahr=alternativ_zusatzkosten,
                )
                hinweis = f'WP: COP Heizung {cop_heizung}, Warmwasser {cop_warmwasser}'

            elif effizienz_modus == 'scop':
                # EU-Label SCOP-Werte (saisonale Effizienz)
                scop_heizung = params.get(PARAM_WAERMEPUMPE["SCOP_HEIZUNG"], PARAM_WAERMEPUMPE_DEFAULTS["scop_heizung"])
                scop_warmwasser = params.get(PARAM_WAERMEPUMPE["SCOP_WARMWASSER"], PARAM_WAERMEPUMPE_DEFAULTS["scop_warmwasser"])
                vorlauftemperatur = params.get(PARAM_WAERMEPUMPE["VORLAUFTEMPERATUR"], PARAM_WAERMEPUMPE_DEFAULTS["vorlauftemperatur"])

                result = berechne_waermepumpe_einsparung(
                    heizwaermebedarf_kwh=heizwaermebedarf,
                    warmwasserbedarf_kwh=warmwasserbedarf,
                    scop_heizung=scop_heizung,
                    scop_warmwasser=scop_warmwasser,
                    effizienz_modus='scop',
                    strompreis_cent=wp_strompreis,
                    pv_anteil_prozent=pv_anteil,
                    alter_energietraeger=alter_energietraeger,
                    alter_preis_cent_kwh=alter_preis,
                    alternativ_zusatzkosten_jahr=alternativ_zusatzkosten,
                )
                hinweis = f'WP: SCOP {scop_heizung} (VL {vorlauftemperatur}°C)'

            else:
                # Standard: Ein JAZ für alles (gemessene Jahresarbeitszahl)
                jaz = params.get(PARAM_WAERMEPUMPE["JAZ"], PARAM_WAERMEPUMPE_DEFAULTS["jaz"])
                # Wärmebedarf: explizit oder aus Komponenten
                waermebedarf = params.get(PARAM_WAERMEPUMPE["WAERMEBEDARF_KWH"])
                if waermebedarf is None:
                    waermebedarf = heizwaermebedarf + warmwasserbedarf

                result = berechne_waermepumpe_einsparung(
                    waermebedarf_kwh=waermebedarf,
                    jaz=jaz,
                    effizienz_modus='gesamt_jaz',
                    strompreis_cent=wp_strompreis,
                    pv_anteil_prozent=pv_anteil,
                    alter_energietraeger=alter_energietraeger,
                    alter_preis_cent_kwh=alter_preis,
                    alternativ_zusatzkosten_jahr=alternativ_zusatzkosten,
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

            # §51-Erlös über SoT (ADR-001, M3); neg_preis_kwh = None bei dieser
            # synthetischen BKW-Schätzung → volle Einspeisung (verhaltensneutral).
            einspeise_erloes = einspeise_erloes_euro(
                einspeisung, None, einspeiseverguetung_cent
            ).erloes_euro
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

        # #310: manuell gepflegte sonstige Erträge/Ausgaben einrechnen.
        inv_sonstige = _sonstige_jahr_fuer([inv.id])
        jahres_einsparung += inv_sonstige
        if isinstance(detail, dict):
            detail['sonstige_netto_euro'] = round(inv_sonstige, 2)
        betriebskosten = inv.betriebskosten_jahr or 0
        netto_einsparung = jahres_einsparung - betriebskosten
        roi_result = berechne_roi(kosten, jahres_einsparung, alternativ, betriebskosten)

        berechnungen.append(ROIBerechnung(
            investition_id=inv.id,
            investition_bezeichnung=inv.bezeichnung,
            investition_typ=inv.typ,
            anschaffungskosten=kosten,
            anschaffungskosten_alternativ=alternativ,
            relevante_kosten=relevante,
            jahres_einsparung=round(netto_einsparung, 2),
            roi_prozent=roi_result['roi_prozent'],
            amortisation_jahre=roi_result['amortisation_jahre'],
            co2_einsparung_kg=round(co2_einsparung, 1) if co2_einsparung else None,
            detail_berechnung=detail,
        ))

        gesamt_investition += kosten
        gesamt_relevante += relevante
        gesamt_einsparung += netto_einsparung
        gesamt_co2 += co2_einsparung

    # USt auf Eigenverbrauch bei Regelbesteuerung (reduziert Gesamt-Einsparung)
    steuerliche_beh = getattr(anlage, 'steuerliche_behandlung', None) or 'keine_ust'
    if steuerliche_beh == "regelbesteuerung" and pv_detail.get('erzeugung_kwh_jahr', 0) > 0:
        alle_inv_result = await db.execute(
            select(Investition).where(Investition.anlage_id == anlage_id)
        )
        alle_inv = alle_inv_result.scalars().all()
        betriebskosten_ges = sum(i.betriebskosten_jahr or 0 for i in alle_inv)
        alle_kosten = sum(i.anschaffungskosten_gesamt or 0 for i in alle_inv)
        _ust = getattr(anlage, 'ust_satz_prozent', None)
        ust_abzug = berechne_ust_eigenverbrauch(
            eigenverbrauch_kwh=pv_detail.get('eigenverbrauch_kwh_jahr', 0),
            investition_gesamt_euro=alle_kosten,
            betriebskosten_jahr_euro=betriebskosten_ges,
            pv_erzeugung_jahr_kwh=pv_detail.get('erzeugung_kwh_jahr', 0),
            ust_satz_prozent=_ust if _ust is not None else 19.0,
        )
        gesamt_einsparung -= ust_abzug

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
        benzinpreis_hinweis_euro=round(benzinpreis_hinweis_euro, 3),
    )


