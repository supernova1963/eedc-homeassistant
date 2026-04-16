"""
Infothek API Router

CRUD-Endpunkte für Infothek-Einträge (Verträge, Zähler, Kontakte, Dokumentation).
"""

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, File, status
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.infothek import InfothekEintrag, InfothekDatei, InfothekInvestition
from backend.models.anlage import Anlage
from backend.models.strompreis import Strompreis
from backend.models.investition import Investition
from backend.services.infothek_pdf_service import generate_infothek_pdf
from backend.services.infothek_datei_service import (
    validiere_dateityp, verarbeite_bild, validiere_pdf,
    ERLAUBTE_TYPES, MAX_DATEIEN_PRO_EINTRAG,
)

from sqlalchemy import desc
from backend.services.infothek_migration import check_migration_status, migrate_investition


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
        "label": "Vertragspartner",
        "icon": "User",
        "felder": {
            "firma": {"type": "string", "label": "Firma"},
            "strasse": {"type": "string", "label": "Straße + Nr."},
            "plz_ort": {"type": "string", "label": "PLZ / Ort"},
            "kundennummer": {"type": "string", "label": "Kundennummer"},
            "name": {"type": "string", "label": "Name (Ansprechpartner)"},
            "position": {"type": "string", "label": "Position"},
            "telefon": {"type": "string", "label": "Telefon"},
            "email": {"type": "string", "label": "E-Mail"},
            "ticketsystem_url": {"type": "string", "label": "Ticketsystem / Portal"},
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
        "label": "Komponente / Datenblatt",
        "icon": "BadgeCheck",
        "felder": {
            "hersteller": {"type": "string", "label": "Hersteller"},
            "produkt": {"type": "string", "label": "Produkt / Modell"},
            "serien_nummer": {"type": "string", "label": "Seriennummer"},
            "einbau_datum": {"type": "date", "label": "Einbau am"},
            "installation_firma": {"type": "string", "label": "Installiert von (Firma)"},
            "garantie_nummer": {"type": "string", "label": "Garantie-Nummer"},
            "garantie_bis": {"type": "date", "label": "Garantie gültig bis"},
            "erweiterung": {"type": "select", "label": "Garantie-Erweiterung", "options": ["Ja", "Nein"]},
            "bedingungen": {"type": "text", "label": "Garantie-Bedingungen"},
            "technische_daten": {"type": "text", "label": "Technische Daten"},
            "letzte_pruefung": {"type": "date", "label": "Letzte Prüfung / Wartung"},
            "naechste_pruefung": {"type": "date", "label": "Nächste Prüfung / Wartung"},
            "datenblatt_url": {"type": "string", "label": "Link zum Hersteller-Datenblatt"},
            "zugehoerige_vertraege": {"type": "text", "label": "Sonstige zugehörige Verträge / Dokumente"},
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
    "messstellenbetreiber": {
        "label": "Messstellenbetreiber",
        "icon": "Gauge",
        "felder": {
            "zaehler_nummer": {"type": "string", "label": "Zählernummer"},
            "betreiber": {"type": "string", "label": "Messstellenbetreiber"},
            "zaehler_typ": {"type": "select", "label": "Zähler-Typ", "options": ["Konventionell", "Moderne Messeinrichtung (mME)", "Intelligentes Messsystem (iMSys/Smart Meter)"]},
            "zaehler_hersteller": {"type": "string", "label": "Zähler-Hersteller"},
            "einbaudatum": {"type": "date", "label": "Einbaudatum"},
            "eichdatum": {"type": "date", "label": "Eichdatum"},
            "naechster_wechsel": {"type": "date", "label": "Nächster Wechsel / Eichfrist"},
            "messstellenvertrag_nr": {"type": "string", "label": "Vertragsnummer"},
            "jahresgebuehr_euro": {"type": "number", "label": "Jahresgebühr (€)"},
            "kundennummer": {"type": "string", "label": "Kundennummer"},
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
    in_anlagendoku: bool = Field(default=True)


class InfothekEintragCreate(InfothekEintragBase):
    """Schema für Erstellung."""
    anlage_id: int
    investition_id: Optional[int] = None  # Legacy 1:1 (Rückwärtskompatibilität)
    investition_ids: Optional[list[int]] = None  # N:M Verknüpfung
    ansprechpartner_id: Optional[int] = None


class InfothekEintragUpdate(BaseModel):
    """Schema für Update — alle Felder optional."""
    bezeichnung: Optional[str] = Field(None, min_length=1, max_length=255)
    kategorie: Optional[str] = Field(None, min_length=1, max_length=50)
    notizen: Optional[str] = None
    parameter: Optional[dict] = None
    investition_id: Optional[int] = None  # Legacy 1:1
    investition_ids: Optional[list[int]] = None  # N:M
    ansprechpartner_id: Optional[int] = None
    sortierung: Optional[int] = None
    aktiv: Optional[bool] = None
    in_anlagendoku: Optional[bool] = None


class InfothekEintragResponse(InfothekEintragBase):
    """Schema für Response."""
    id: int
    anlage_id: int
    investition_id: Optional[int] = None  # Legacy: erstes Element oder None
    investition_ids: list[int] = []  # N:M Verknüpfungen
    ansprechpartner_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SortierungItem(BaseModel):
    """Ein Item für Batch-Sortierung."""
    id: int
    sortierung: int


class InfothekDateiResponse(BaseModel):
    """Schema für Datei-Response (ohne BLOB-Daten)."""
    id: int
    eintrag_id: int
    dateiname: str
    dateityp: str
    mime_type: str
    beschreibung: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


# =============================================================================
# Helper: Junction Table Sync + Response-Erweiterung
# =============================================================================

async def _sync_junction(db: AsyncSession, eintrag_id: int, investition_ids: list[int]):
    """Synchronisiert die N:M Junction Table für einen Infothek-Eintrag."""
    # Alte Verknüpfungen löschen
    await db.execute(
        delete(InfothekInvestition)
        .where(InfothekInvestition.infothek_eintrag_id == eintrag_id)
    )
    # Neue einfügen
    for inv_id in investition_ids:
        db.add(InfothekInvestition(infothek_eintrag_id=eintrag_id, investition_id=inv_id))


async def _get_investition_ids(db: AsyncSession, eintrag_id: int) -> list[int]:
    """Lädt die verknüpften Investition-IDs aus der Junction Table."""
    result = await db.execute(
        select(InfothekInvestition.investition_id)
        .where(InfothekInvestition.infothek_eintrag_id == eintrag_id)
    )
    return [row[0] for row in result.all()]


async def _get_investition_ids_batch(db: AsyncSession, eintrag_ids: list[int]) -> dict[int, list[int]]:
    """Lädt die verknüpften Investition-IDs für mehrere Einträge (Batch)."""
    if not eintrag_ids:
        return {}
    result = await db.execute(
        select(InfothekInvestition.infothek_eintrag_id, InfothekInvestition.investition_id)
        .where(InfothekInvestition.infothek_eintrag_id.in_(eintrag_ids))
    )
    mapping: dict[int, list[int]] = {}
    for eintrag_id, inv_id in result.all():
        mapping.setdefault(eintrag_id, []).append(inv_id)
    return mapping


def _resolve_investition_ids(
    investition_ids: Optional[list[int]],
    investition_id: Optional[int],
) -> list[int]:
    """Löst investition_ids auf: N:M hat Vorrang, Fallback auf Legacy 1:1."""
    if investition_ids is not None:
        return investition_ids
    if investition_id is not None:
        return [investition_id]
    return []


def _eintrag_to_response(eintrag: InfothekEintrag, inv_ids: list[int]) -> dict:
    """Baut ein Response-Dict mit investition_ids aus einem InfothekEintrag."""
    return {
        "id": eintrag.id,
        "anlage_id": eintrag.anlage_id,
        "bezeichnung": eintrag.bezeichnung,
        "kategorie": eintrag.kategorie,
        "notizen": eintrag.notizen,
        "parameter": eintrag.parameter,
        "sortierung": eintrag.sortierung,
        "aktiv": eintrag.aktiv,
        "in_anlagendoku": eintrag.in_anlagendoku if hasattr(eintrag, 'in_anlagendoku') else True,
        "investition_id": inv_ids[0] if inv_ids else None,
        "investition_ids": inv_ids,
        "ansprechpartner_id": eintrag.ansprechpartner_id,
        "created_at": eintrag.created_at,
        "updated_at": eintrag.updated_at,
    }


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
    eintraege = result.scalars().all()

    # Batch-Load der Junction-Verknüpfungen
    ids = [e.id for e in eintraege]
    inv_map = await _get_investition_ids_batch(db, ids)
    return [_eintrag_to_response(e, inv_map.get(e.id, [])) for e in eintraege]


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
    inv_ids = await _get_investition_ids(db, eintrag.id)
    return _eintrag_to_response(eintrag, inv_ids)


@router.post("/", response_model=InfothekEintragResponse, status_code=status.HTTP_201_CREATED)
async def create_eintrag(
    item: InfothekEintragCreate,
    db: AsyncSession = Depends(get_db),
):
    """Erstellt einen neuen Infothek-Eintrag."""
    # investition_ids aus Request extrahieren (nicht ans Model durchreichen)
    data = item.model_dump(exclude={"investition_ids"})
    inv_ids = _resolve_investition_ids(item.investition_ids, item.investition_id)
    # Legacy-Feld synchron halten
    data["investition_id"] = inv_ids[0] if inv_ids else None

    db_item = InfothekEintrag(**data)
    db.add(db_item)
    await db.flush()  # ID generieren

    # Junction Table befüllen
    if inv_ids:
        await _sync_junction(db, db_item.id, inv_ids)

    await db.commit()
    await db.refresh(db_item)
    return _eintrag_to_response(db_item, inv_ids)


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

    # Junction Table synchronisieren wenn investition_ids gesetzt
    inv_ids_updated = False
    if "investition_ids" in update_data:
        inv_ids = update_data.pop("investition_ids") or []
        await _sync_junction(db, eintrag_id, inv_ids)
        update_data["investition_id"] = inv_ids[0] if inv_ids else None
        inv_ids_updated = True
    elif "investition_id" in update_data:
        inv_id = update_data.get("investition_id")
        inv_ids = [inv_id] if inv_id else []
        await _sync_junction(db, eintrag_id, inv_ids)
        inv_ids_updated = True

    for key, value in update_data.items():
        if key == "investition_ids":
            continue
        setattr(db_item, key, value)

    db.add(db_item)
    await db.commit()
    await db.refresh(db_item)

    final_inv_ids = await _get_investition_ids(db, eintrag_id) if not inv_ids_updated else inv_ids
    return _eintrag_to_response(db_item, final_inv_ids)


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


# =============================================================================
# Vorbelegung (Etappe 3) — Felder aus Systemdaten vorbelegen
# =============================================================================

@router.get("/vorbelegung/{kategorie}")
async def get_vorbelegung(
    kategorie: str,
    anlage_id: int = Query(..., description="Anlage-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Gibt Vorbelegungsdaten für eine Kategorie aus vorhandenen Systemdaten zurück."""
    prefill: dict[str, object] = {}

    if kategorie == "stromvertrag":
        # Aktuellsten Strompreis-Tarif laden (verwendung=allgemein)
        result = await db.execute(
            select(Strompreis)
            .where(Strompreis.anlage_id == anlage_id, Strompreis.verwendung == "allgemein")
            .order_by(desc(Strompreis.gueltig_ab))
            .limit(1)
        )
        tarif = result.scalar_one_or_none()
        if tarif:
            if tarif.anbieter:
                prefill["anbieter"] = tarif.anbieter
            if tarif.netzbezug_arbeitspreis_cent_kwh is not None:
                prefill["tarif_ct_kwh"] = tarif.netzbezug_arbeitspreis_cent_kwh

        # versorger_daten aus Anlage
        anlage_result = await db.execute(
            select(Anlage).where(Anlage.id == anlage_id)
        )
        anlage = anlage_result.scalar_one_or_none()
        if anlage and anlage.versorger_daten:
            strom = anlage.versorger_daten.get("strom", {})
            if strom.get("kundennummer"):
                prefill.setdefault("kundennummer", strom["kundennummer"])
            if strom.get("name") and "anbieter" not in prefill:
                prefill["anbieter"] = strom["name"]

    elif kategorie == "einspeisevertrag":
        # Einspeisevergütung aus Strompreis
        result = await db.execute(
            select(Strompreis)
            .where(Strompreis.anlage_id == anlage_id)
            .order_by(desc(Strompreis.gueltig_ab))
            .limit(1)
        )
        tarif = result.scalar_one_or_none()
        if tarif and tarif.einspeiseverguetung_cent_kwh is not None:
            prefill["verguetung_ct_kwh"] = tarif.einspeiseverguetung_cent_kwh

        # Inbetriebnahme aus Anlage
        anlage_result = await db.execute(
            select(Anlage).where(Anlage.id == anlage_id)
        )
        anlage = anlage_result.scalar_one_or_none()
        if anlage and anlage.installationsdatum:
            prefill["inbetriebnahme_datum"] = str(anlage.installationsdatum)

    elif kategorie == "marktstammdatenregister":
        anlage_result = await db.execute(
            select(Anlage).where(Anlage.id == anlage_id)
        )
        anlage = anlage_result.scalar_one_or_none()
        if anlage:
            if anlage.mastr_id:
                prefill["mastr_nummer"] = anlage.mastr_id
            if anlage.installationsdatum:
                prefill["inbetriebnahme_datum"] = str(anlage.installationsdatum)

    return {"kategorie": kategorie, "parameter": prefill}


# =============================================================================
# Investition-Verknüpfung (Etappe 3)
# =============================================================================

class VerknuepfungBody(BaseModel):
    """Body für Batch-Verknüpfung."""
    investition_ids: list[int] = []


@router.put("/{eintrag_id}/verknuepfung", response_model=InfothekEintragResponse)
async def update_verknuepfung(
    eintrag_id: int,
    body: Optional[VerknuepfungBody] = None,
    investition_id: Optional[int] = Query(None, description="Legacy: einzelne Investition-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Verknüpft einen Infothek-Eintrag mit Investitionen (N:M)."""
    result = await db.execute(
        select(InfothekEintrag).where(InfothekEintrag.id == eintrag_id)
    )
    eintrag = result.scalar_one_or_none()
    if not eintrag:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    # N:M Body hat Vorrang, Fallback auf Legacy Query-Param
    if body and body.investition_ids:
        inv_ids = body.investition_ids
    elif investition_id is not None:
        inv_ids = [investition_id]
    else:
        inv_ids = []

    # Junction Table + Legacy-Feld synchronisieren
    await _sync_junction(db, eintrag_id, inv_ids)
    eintrag.investition_id = inv_ids[0] if inv_ids else None
    db.add(eintrag)
    await db.commit()
    await db.refresh(eintrag)
    return _eintrag_to_response(eintrag, inv_ids)


@router.get("/investition/{investition_id}", response_model=list[InfothekEintragResponse])
async def list_eintraege_fuer_investition(
    investition_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Gibt alle Infothek-Einträge zurück, die mit einer Investition verknüpft sind."""
    result = await db.execute(
        select(InfothekEintrag)
        .join(InfothekInvestition, InfothekInvestition.infothek_eintrag_id == InfothekEintrag.id)
        .where(InfothekInvestition.investition_id == investition_id)
        .order_by(InfothekEintrag.sortierung)
    )
    eintraege = result.scalars().all()
    ids = [e.id for e in eintraege]
    inv_map = await _get_investition_ids_batch(db, ids)
    return [_eintrag_to_response(e, inv_map.get(e.id, [])) for e in eintraege]


# =============================================================================
# PDF-Export (Etappe 4)
# =============================================================================

@router.get("/export/pdf")
async def export_pdf(
    anlage_id: int = Query(..., description="Anlage-ID"),
    kategorie: Optional[str] = Query(None, description="Nur diese Kategorie exportieren"),
    db: AsyncSession = Depends(get_db),
):
    """Exportiert Infothek-Einträge als PDF."""
    # Engine-Switch (Issue #121, Phase 3) — Default bleibt reportlab.
    from backend.core.config import settings as _settings
    if (_settings.pdf_engine or "").lower() == "weasyprint":
        from backend.services.pdf import render_document
        from backend.services.pdf.builders.infothek import build_infothek_context
        try:
            ctx = await build_infothek_context(db, anlage_id, kategorie)
        except LookupError:
            raise HTTPException(status_code=404, detail="Anlage nicht gefunden")
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        try:
            pdf_bytes = render_document("infothek.html", ctx)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"PDF-Render-Fehler: {exc}")
        anlagen_name = ctx["anlage"]["name"]
        filename = f"infothek_{anlagen_name.replace(' ', '_')}"
        if kategorie:
            filename += f"_{kategorie}"
        filename += f"_{datetime.now().strftime('%Y%m%d')}.pdf"
        from fastapi.responses import Response
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # Anlage laden
    anlage_result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = anlage_result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Einträge laden (nur aktive)
    query = (
        select(InfothekEintrag)
        .where(InfothekEintrag.anlage_id == anlage_id, InfothekEintrag.aktiv == True)
        .order_by(InfothekEintrag.sortierung, InfothekEintrag.created_at.desc())
    )
    if kategorie:
        query = query.where(InfothekEintrag.kategorie == kategorie)
    result = await db.execute(query)
    eintraege_obj = result.scalars().all()

    if not eintraege_obj:
        raise HTTPException(status_code=404, detail="Keine Einträge zum Exportieren")

    # Vertragspartner-Map aufbauen
    vp_result = await db.execute(
        select(InfothekEintrag)
        .where(InfothekEintrag.anlage_id == anlage_id, InfothekEintrag.kategorie == "ansprechpartner")
    )
    vp_map = {e.id: e.bezeichnung for e in vp_result.scalars().all()}

    # Einträge als Dicts
    eintraege = [
        {
            "bezeichnung": e.bezeichnung,
            "kategorie": e.kategorie,
            "parameter": e.parameter or {},
            "notizen": e.notizen,
            "ansprechpartner_id": e.ansprechpartner_id,
        }
        for e in eintraege_obj
    ]

    pdf_bytes = generate_infothek_pdf(
        anlagen_name=anlage.anlagenname,
        eintraege=eintraege,
        vertragspartner_map=vp_map,
        kategorie_schemas=INFOTHEK_KATEGORIEN,
        filter_kategorie=kategorie,
    )

    filename = f"infothek_{anlage.anlagenname.replace(' ', '_')}"
    if kategorie:
        filename += f"_{kategorie}"
    filename += f"_{datetime.now().strftime('%Y%m%d')}.pdf"

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# =============================================================================
# Migration (Etappe 3) — stamm_* → Infothek
# =============================================================================

@router.get("/migration/status")
async def get_migration_status(
    anlage_id: int = Query(..., description="Anlage-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Prüft welche Investitionen migrierbate Stammdaten haben."""
    return await check_migration_status(db, anlage_id)


@router.post("/migration/batch")
async def migrate_all(
    anlage_id: int = Query(..., description="Anlage-ID"),
    db: AsyncSession = Depends(get_db),
):
    """Migriert alle Investitionen einer Anlage auf einmal."""
    status = await check_migration_status(db, anlage_id)
    total_created = []
    for inv in status["investitionen"]:
        created = await migrate_investition(db, inv["id"])
        total_created.extend(created)
    return {"created": total_created, "count": len(total_created)}


@router.post("/migration/{investition_id}")
async def migrate_stammdaten(
    investition_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Migriert stamm_*-Daten einer Investition in Infothek-Einträge."""
    created = await migrate_investition(db, investition_id)
    return {"created": created, "count": len(created)}


# =============================================================================
# Datei-Endpunkte (Etappe 2)
# =============================================================================

@router.post("/{eintrag_id}/dateien", response_model=InfothekDateiResponse, status_code=status.HTTP_201_CREATED)
async def upload_datei(
    eintrag_id: int,
    datei: UploadFile = File(...),
    beschreibung: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
):
    """Lädt eine Datei (Bild oder PDF) zu einem Eintrag hoch."""
    # Eintrag prüfen
    result = await db.execute(
        select(InfothekEintrag).where(InfothekEintrag.id == eintrag_id)
    )
    eintrag = result.scalar_one_or_none()
    if not eintrag:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    # Anzahl prüfen
    count_result = await db.execute(
        select(func.count(InfothekDatei.id))
        .where(InfothekDatei.eintrag_id == eintrag_id)
    )
    count = count_result.scalar() or 0
    if count >= MAX_DATEIEN_PRO_EINTRAG:
        raise HTTPException(
            status_code=400,
            detail=f"Maximal {MAX_DATEIEN_PRO_EINTRAG} Dateien pro Eintrag erlaubt."
        )

    # Dateityp validieren
    mime_type = datei.content_type or "application/octet-stream"
    try:
        dateityp = validiere_dateityp(mime_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Daten lesen (max. 50 MB)
    MAX_UPLOAD_BYTES = 50 * 1024 * 1024
    raw_daten = await datei.read(MAX_UPLOAD_BYTES + 1)
    if len(raw_daten) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Datei zu groß (max. 50 MB).")

    # Verarbeiten
    thumbnail = None
    if dateityp == "image":
        try:
            daten, thumbnail, mime_type = verarbeite_bild(raw_daten, mime_type)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    else:
        try:
            daten = validiere_pdf(raw_daten)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    # Speichern
    db_datei = InfothekDatei(
        eintrag_id=eintrag_id,
        dateiname=datei.filename or "unbekannt",
        dateityp=dateityp,
        mime_type=mime_type,
        daten=daten,
        thumbnail=thumbnail,
        beschreibung=(beschreibung.strip() or None) if beschreibung else None,
    )
    db.add(db_datei)
    await db.commit()
    await db.refresh(db_datei)
    return db_datei


@router.get("/{eintrag_id}/dateien", response_model=list[InfothekDateiResponse])
async def list_dateien(
    eintrag_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Listet alle Dateien eines Eintrags (ohne BLOB-Daten)."""
    result = await db.execute(
        select(InfothekDatei)
        .where(InfothekDatei.eintrag_id == eintrag_id)
        .order_by(InfothekDatei.created_at)
    )
    return result.scalars().all()


@router.get("/{eintrag_id}/dateien/{datei_id}")
async def get_datei(
    eintrag_id: int,
    datei_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Gibt eine Datei (volle Auflösung) zurück."""
    result = await db.execute(
        select(InfothekDatei).where(
            InfothekDatei.id == datei_id,
            InfothekDatei.eintrag_id == eintrag_id,
        )
    )
    datei = result.scalar_one_or_none()
    if not datei:
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")

    return Response(
        content=datei.daten,
        media_type=datei.mime_type,
        headers={"Content-Disposition": f'inline; filename="{datei.dateiname}"'},
    )


@router.get("/{eintrag_id}/dateien/{datei_id}/thumb")
async def get_thumbnail(
    eintrag_id: int,
    datei_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Gibt das Thumbnail eines Bildes zurück."""
    result = await db.execute(
        select(InfothekDatei).where(
            InfothekDatei.id == datei_id,
            InfothekDatei.eintrag_id == eintrag_id,
        )
    )
    datei = result.scalar_one_or_none()
    if not datei:
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")

    if datei.thumbnail is None:
        raise HTTPException(status_code=404, detail="Kein Thumbnail vorhanden (PDF)")

    return Response(
        content=datei.thumbnail,
        media_type="image/jpeg",
    )


@router.delete("/{eintrag_id}/dateien/{datei_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_datei(
    eintrag_id: int,
    datei_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Löscht eine Datei."""
    result = await db.execute(
        select(InfothekDatei).where(
            InfothekDatei.id == datei_id,
            InfothekDatei.eintrag_id == eintrag_id,
        )
    )
    datei = result.scalar_one_or_none()
    if not datei:
        raise HTTPException(status_code=404, detail="Datei nicht gefunden")
    await db.delete(datei)
    await db.commit()
