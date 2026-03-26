"""
Infothek API Router

CRUD-Endpunkte für Infothek-Einträge (Verträge, Zähler, Kontakte, Dokumentation).
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.infothek import InfothekEintrag


# =============================================================================
# Kategorie-Registry — Schema-Definition pro Kategorie
# =============================================================================

INFOTHEK_KATEGORIEN: dict[str, dict] = {
    "stromvertrag": {
        "label": "Stromvertrag",
        "icon": "Zap",
        "felder": {
            "zaehler_nummer": {"type": "string", "label": "Zählernummer"},
            "anbieter": {"type": "string", "label": "Anbieter"},
            "netzbetreiber": {"type": "string", "label": "Netzbetreiber"},
            "tarif_ct_kwh": {"type": "number", "label": "Tarif (ct/kWh)"},
            "vertragsbeginn": {"type": "date", "label": "Vertragsbeginn"},
            "vertragslaufzeit_monate": {"type": "number", "label": "Vertragslaufzeit (Monate)"},
            "kuendigungsfrist_monate": {"type": "number", "label": "Kündigungsfrist (Monate)"},
            "kundennummer": {"type": "string", "label": "Kundennummer"},
        },
    },
    "einspeisevertrag": {
        "label": "Einspeisevertrag",
        "icon": "Sun",
        "felder": {
            "zaehler_nummer": {"type": "string", "label": "Zählernummer"},
            "verguetung_ct_kwh": {"type": "number", "label": "Vergütung (ct/kWh)"},
            "eeg_anlagen_nr": {"type": "string", "label": "EEG-Anlagen-Nr."},
            "inbetriebnahme_datum": {"type": "date", "label": "Inbetriebnahme"},
            "anbieter": {"type": "string", "label": "Anbieter"},
            "kundennummer": {"type": "string", "label": "Kundennummer"},
        },
    },
    "gasvertrag": {
        "label": "Gasvertrag",
        "icon": "Flame",
        "felder": {
            "zaehler_nummer": {"type": "string", "label": "Zählernummer"},
            "anbieter": {"type": "string", "label": "Anbieter"},
            "tarif_ct_kwh": {"type": "number", "label": "Tarif (ct/kWh)"},
            "jahresverbrauch_kwh": {"type": "number", "label": "Jahresverbrauch (kWh)"},
            "kundennummer": {"type": "string", "label": "Kundennummer"},
            "vertragsbeginn": {"type": "date", "label": "Vertragsbeginn"},
            "kuendigungsfrist_monate": {"type": "number", "label": "Kündigungsfrist (Monate)"},
        },
    },
    "wasservertrag": {
        "label": "Wasservertrag",
        "icon": "Droplets",
        "felder": {
            "zaehler_nummer": {"type": "string", "label": "Zählernummer"},
            "anbieter": {"type": "string", "label": "Anbieter"},
            "eichdatum": {"type": "date", "label": "Eichdatum"},
            "naechste_ablesung": {"type": "date", "label": "Nächste Ablesung"},
            "kundennummer": {"type": "string", "label": "Kundennummer"},
        },
    },
    "fernwaerme": {
        "label": "Fernwärme",
        "icon": "Thermometer",
        "felder": {
            "zaehler_nummer": {"type": "string", "label": "Zählernummer"},
            "anbieter": {"type": "string", "label": "Anbieter"},
            "anschlussleistung_kw": {"type": "number", "label": "Anschlussleistung (kW)"},
            "tarif_ct_kwh": {"type": "number", "label": "Tarif (ct/kWh)"},
            "kundennummer": {"type": "string", "label": "Kundennummer"},
        },
    },
    "brennstoff": {
        "label": "Brennstoff (Heizöl / Flüssiggas / Pellets)",
        "icon": "Logs",
        "felder": {
            "brennstoff_art": {"type": "select", "label": "Brennstoff-Art", "options": ["Heizöl", "Flüssiggas", "Pellets", "Holz"]},
            "lieferant": {"type": "string", "label": "Lieferant"},
            "tankgroesse": {"type": "string", "label": "Tankgröße"},
            "letzte_lieferung_datum": {"type": "date", "label": "Letzte Lieferung (Datum)"},
            "letzte_lieferung_menge": {"type": "number", "label": "Letzte Lieferung (Menge)"},
            "preis_pro_einheit": {"type": "number", "label": "Preis pro Einheit (€)"},
            "einheit": {"type": "select", "label": "Einheit", "options": ["Liter", "kg", "Ster"]},
            "kundennummer": {"type": "string", "label": "Kundennummer"},
        },
    },
    "versicherung": {
        "label": "Versicherung",
        "icon": "Shield",
        "felder": {
            "versicherungsnummer": {"type": "string", "label": "Versicherungsnummer"},
            "anbieter": {"type": "string", "label": "Anbieter"},
            "deckungssumme_euro": {"type": "number", "label": "Deckungssumme (€)"},
            "jahresbeitrag_euro": {"type": "number", "label": "Jahresbeitrag (€)"},
            "vertragsbeginn": {"type": "date", "label": "Vertragsbeginn"},
            "kuendigungsfrist_monate": {"type": "number", "label": "Kündigungsfrist (Monate)"},
        },
    },
    "ansprechpartner": {
        "label": "Ansprechpartner",
        "icon": "User",
        "felder": {
            "firma": {"type": "string", "label": "Firma"},
            "name": {"type": "string", "label": "Name"},
            "telefon": {"type": "string", "label": "Telefon"},
            "email": {"type": "string", "label": "E-Mail"},
            "ticketsystem_url": {"type": "string", "label": "Ticketsystem URL"},
            "kundennummer": {"type": "string", "label": "Kundennummer"},
            "position": {"type": "string", "label": "Position"},
        },
    },
    "wartungsvertrag": {
        "label": "Wartungs-/Pflegevertrag",
        "icon": "Wrench",
        "felder": {
            "anbieter": {"type": "string", "label": "Anbieter"},
            "vertragsnummer": {"type": "string", "label": "Vertragsnummer"},
            "leistungsumfang": {"type": "string", "label": "Leistungsumfang"},
            "gueltig_bis": {"type": "date", "label": "Gültig bis"},
            "kuendigungsfrist_monate": {"type": "number", "label": "Kündigungsfrist (Monate)"},
            "jahreskosten_euro": {"type": "number", "label": "Jahreskosten (€)"},
        },
    },
    "marktstammdatenregister": {
        "label": "Marktstammdatenregister",
        "icon": "Landmark",
        "felder": {
            "mastr_nummer": {"type": "string", "label": "MaStR-Nummer"},
            "anlage_typ": {"type": "string", "label": "Anlage-Typ"},
            "inbetriebnahme_datum": {"type": "date", "label": "Inbetriebnahme"},
            "status": {"type": "string", "label": "Status"},
            "letzte_aktualisierung": {"type": "date", "label": "Letzte Aktualisierung"},
        },
    },
    "foerderung": {
        "label": "Förderung",
        "icon": "Coins",
        "felder": {
            "aktenzeichen": {"type": "string", "label": "Aktenzeichen"},
            "foerderprogramm": {"type": "string", "label": "Förderprogramm"},
            "betrag_euro": {"type": "number", "label": "Betrag (€)"},
            "bewilligungsdatum": {"type": "date", "label": "Bewilligungsdatum"},
            "laufzeit_monate": {"type": "number", "label": "Laufzeit (Monate)"},
            "auflagen": {"type": "string", "label": "Auflagen"},
        },
    },
    "garantie": {
        "label": "Garantie",
        "icon": "BadgeCheck",
        "felder": {
            "hersteller": {"type": "string", "label": "Hersteller"},
            "produkt": {"type": "string", "label": "Produkt"},
            "garantie_nummer": {"type": "string", "label": "Garantie-Nummer"},
            "garantie_bis": {"type": "date", "label": "Garantie bis"},
            "erweiterung": {"type": "select", "label": "Erweiterung", "options": ["Ja", "Nein"]},
            "bedingungen": {"type": "string", "label": "Bedingungen"},
        },
    },
    "steuerdaten": {
        "label": "Steuerdaten",
        "icon": "Calculator",
        "felder": {
            "finanzamt": {"type": "string", "label": "Finanzamt"},
            "steuernummer": {"type": "string", "label": "Steuernummer"},
            "abschreibungszeitraum_jahre": {"type": "number", "label": "Abschreibungszeitraum (Jahre)"},
            "afa_typ": {"type": "select", "label": "AfA-Typ", "options": ["linear", "degressiv"]},
            "restwert_euro": {"type": "number", "label": "Restwert (€)"},
        },
    },
    "sonstiges": {
        "label": "Sonstiges",
        "icon": "FileText",
        "felder": {},
    },
}

# Übergreifende optionale Felder
UEBERGREIFENDE_FELDER = {
    "kontakt": {
        "label": "Kontakt",
        "felder": {
            "kontakt_firma": {"type": "string", "label": "Firma"},
            "kontakt_name": {"type": "string", "label": "Name"},
            "kontakt_telefon": {"type": "string", "label": "Telefon"},
            "kontakt_email": {"type": "string", "label": "E-Mail"},
        },
    },
    "vertrag": {
        "label": "Vertragsdaten",
        "felder": {
            "vertragsnummer": {"type": "string", "label": "Vertragsnummer"},
            "vertragsbeginn": {"type": "date", "label": "Vertragsbeginn"},
            "kuendigungsfrist_monate": {"type": "number", "label": "Kündigungsfrist (Monate)"},
        },
    },
}


# =============================================================================
# Pydantic Schemas
# =============================================================================

class InfothekEintragBase(BaseModel):
    """Basis-Schema für Infothek-Einträge."""
    bezeichnung: str = Field(..., min_length=1, max_length=255)
    kategorie: str = Field(..., min_length=1, max_length=50)
    notizen: Optional[str] = None
    parameter: Optional[dict] = None
    sortierung: int = Field(default=0)
    aktiv: bool = Field(default=True)


class InfothekEintragCreate(InfothekEintragBase):
    """Schema für Erstellung."""
    anlage_id: int


class InfothekEintragUpdate(BaseModel):
    """Schema für Update — alle Felder optional."""
    bezeichnung: Optional[str] = Field(None, min_length=1, max_length=255)
    kategorie: Optional[str] = Field(None, min_length=1, max_length=50)
    notizen: Optional[str] = None
    parameter: Optional[dict] = None
    sortierung: Optional[int] = None
    aktiv: Optional[bool] = None


class InfothekEintragResponse(InfothekEintragBase):
    """Schema für Response."""
    id: int
    anlage_id: int
    investition_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class SortierungItem(BaseModel):
    """Ein Item für Batch-Sortierung."""
    id: int
    sortierung: int


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.get("/", response_model=list[InfothekEintragResponse])
async def list_eintraege(
    anlage_id: int = Query(..., description="Anlage-ID"),
    kategorie: Optional[str] = Query(None, description="Filter nach Kategorie"),
    aktiv: Optional[bool] = Query(None, description="Filter nach Status"),
    db: AsyncSession = Depends(get_db),
):
    """Gibt alle Infothek-Einträge einer Anlage zurück."""
    query = (
        select(InfothekEintrag)
        .where(InfothekEintrag.anlage_id == anlage_id)
        .order_by(InfothekEintrag.sortierung, InfothekEintrag.created_at.desc())
    )

    if kategorie is not None:
        query = query.where(InfothekEintrag.kategorie == kategorie)
    if aktiv is not None:
        query = query.where(InfothekEintrag.aktiv == aktiv)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/kategorien")
async def get_kategorien():
    """Gibt alle verfügbaren Kategorien mit Feld-Schemas zurück."""
    return {
        "kategorien": INFOTHEK_KATEGORIEN,
        "uebergreifende_felder": UEBERGREIFENDE_FELDER,
    }


@router.get("/count")
async def get_count(
    anlage_id: int = Query(..., description="Anlage-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Gibt die Anzahl der Infothek-Einträge zurück (für bedingte Menü-Anzeige)."""
    result = await db.execute(
        select(func.count(InfothekEintrag.id))
        .where(InfothekEintrag.anlage_id == anlage_id)
    )
    return {"count": result.scalar() or 0}


@router.get("/{eintrag_id}", response_model=InfothekEintragResponse)
async def get_eintrag(
    eintrag_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Gibt einen einzelnen Infothek-Eintrag zurück."""
    result = await db.execute(
        select(InfothekEintrag).where(InfothekEintrag.id == eintrag_id)
    )
    eintrag = result.scalar_one_or_none()
    if not eintrag:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    return eintrag


@router.post("/", response_model=InfothekEintragResponse, status_code=status.HTTP_201_CREATED)
async def create_eintrag(
    item: InfothekEintragCreate,
    db: AsyncSession = Depends(get_db),
):
    """Erstellt einen neuen Infothek-Eintrag."""
    db_item = InfothekEintrag(**item.model_dump())
    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.put("/{eintrag_id}", response_model=InfothekEintragResponse)
async def update_eintrag(
    eintrag_id: int,
    item: InfothekEintragUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Updated einen Infothek-Eintrag."""
    result = await db.execute(
        select(InfothekEintrag).where(InfothekEintrag.id == eintrag_id)
    )
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    update_data = item.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_item, key, value)

    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)
    return db_item


@router.delete("/{eintrag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_eintrag(
    eintrag_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Löscht einen Infothek-Eintrag."""
    result = await db.execute(
        select(InfothekEintrag).where(InfothekEintrag.id == eintrag_id)
    )
    db_item = result.scalar_one_or_none()
    if not db_item:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
    await db.delete(db_item)
    await db.commit()


@router.put("/sortierung/batch")
async def update_sortierung(
    items: list[SortierungItem],
    db: AsyncSession = Depends(get_db),
):
    """Aktualisiert die Reihenfolge mehrerer Einträge."""
    for item in items:
        result = await db.execute(
            select(InfothekEintrag).where(InfothekEintrag.id == item.id)
        )
        db_item = result.scalar_one_or_none()
        if db_item:
            db_item.sortierung = item.sortierung
            db.add(db_item)

    await db.commit()
    return {"status": "ok", "updated": len(items)}
