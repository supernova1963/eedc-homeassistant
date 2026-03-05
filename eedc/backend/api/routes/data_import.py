"""
Portal-Import API Routes.

Ermöglicht den Import von Energiedaten aus Hersteller-Portal-Exporten (CSV).
Unterstützt Auto-Detection des Formats und Vorschau vor dem Import.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition
from backend.services.import_parsers import (
    list_parsers,
    get_parser,
    auto_detect_parser,
    ParsedMonthData,
)
from backend.api.routes.import_export.helpers import (
    _upsert_investition_monatsdaten,
    _distribute_legacy_pv_to_modules,
    _distribute_legacy_battery_to_storages,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ─── Schemas ─────────────────────────────────────────────────────────────────


class ParserInfoResponse(BaseModel):
    id: str
    name: str
    hersteller: str
    beschreibung: str
    erwartetes_format: str
    anleitung: str
    beispiel_header: str
    getestet: bool = True


class ParsedMonthResponse(BaseModel):
    jahr: int
    monat: int
    pv_erzeugung_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    batterie_ladung_kwh: Optional[float] = None
    batterie_entladung_kwh: Optional[float] = None
    eigenverbrauch_kwh: Optional[float] = None
    wallbox_ladung_kwh: Optional[float] = None
    wallbox_ladung_pv_kwh: Optional[float] = None
    wallbox_ladevorgaenge: Optional[int] = None
    eauto_km_gefahren: Optional[float] = None


class PreviewResponse(BaseModel):
    parser: ParserInfoResponse
    monate: list[ParsedMonthResponse]
    anzahl_monate: int


class ApplyMonthInput(BaseModel):
    jahr: int
    monat: int
    pv_erzeugung_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    batterie_ladung_kwh: Optional[float] = None
    batterie_entladung_kwh: Optional[float] = None
    eigenverbrauch_kwh: Optional[float] = None
    wallbox_ladung_kwh: Optional[float] = None
    wallbox_ladung_pv_kwh: Optional[float] = None
    wallbox_ladevorgaenge: Optional[int] = None
    eauto_km_gefahren: Optional[float] = None


class ApplyRequest(BaseModel):
    monate: list[ApplyMonthInput]


class ApplyResponse(BaseModel):
    erfolg: bool
    importiert: int
    uebersprungen: int
    fehler: list[str]
    warnungen: list[str]


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/parsers", response_model=list[ParserInfoResponse])
async def get_parsers():
    """Verfügbare Portal-Export-Parser mit Anleitungen."""
    return [p.to_dict() for p in list_parsers()]


@router.post("/preview", response_model=PreviewResponse)
async def preview_import(
    file: UploadFile = File(...),
    parser_id: Optional[str] = Query(None, description="Parser-ID oder leer für Auto-Detect"),
):
    """CSV hochladen und Vorschau der erkannten Monatswerte erhalten (ohne Speichern)."""
    # Datei lesen
    content_bytes = await file.read()
    try:
        content = content_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            content = content_bytes.decode("latin-1")
        except UnicodeDecodeError:
            raise HTTPException(400, "Datei konnte nicht gelesen werden. Bitte UTF-8 oder Latin-1 Encoding verwenden.")

    if not content.strip():
        raise HTTPException(400, "Die Datei ist leer.")

    # Parser wählen
    if parser_id:
        try:
            parser = get_parser(parser_id)
        except ValueError:
            raise HTTPException(400, f"Unbekannter Parser: {parser_id}")
    else:
        parser = auto_detect_parser(content, file.filename or "")
        if not parser:
            raise HTTPException(
                400,
                "Format nicht automatisch erkannt. Bitte Hersteller manuell wählen."
            )

    # Parsen
    try:
        months = parser.parse(content)
    except Exception as e:
        logger.exception("Fehler beim Parsen der Datei")
        raise HTTPException(400, f"Fehler beim Parsen: {str(e)}")

    if not months:
        raise HTTPException(400, "Keine Monatsdaten in der Datei gefunden.")

    return PreviewResponse(
        parser=ParserInfoResponse(**parser.info().to_dict()),
        monate=[ParsedMonthResponse(**m.to_dict()) for m in months],
        anzahl_monate=len(months),
    )


@router.post("/apply/{anlage_id}", response_model=ApplyResponse)
async def apply_import(
    anlage_id: int,
    data: ApplyRequest,
    ueberschreiben: bool = Query(False, description="Bestehende Monatsdaten überschreiben"),
    db: AsyncSession = Depends(get_db),
):
    """Bestätigte Monatswerte aus Portal-Import in die Datenbank übernehmen."""
    # Anlage prüfen
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(404, f"Anlage {anlage_id} nicht gefunden.")

    # Investitionen laden (für PV/Batterie-Verteilung)
    inv_result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = inv_result.scalars().all()
    pv_module = [i for i in investitionen if i.typ == "pv-module"]
    speicher = [i for i in investitionen if i.typ == "speicher"]
    wallboxen = [i for i in investitionen if i.typ == "wallbox"]

    importiert = 0
    uebersprungen = 0
    fehler: list[str] = []
    warnungen: list[str] = []

    for monat_input in data.monate:
        try:
            jahr = monat_input.jahr
            monat = monat_input.monat

            if monat < 1 or monat > 12:
                fehler.append(f"{jahr}/{monat:02d}: Ungültiger Monat")
                continue

            # Bestehende Monatsdaten prüfen
            existing = await db.execute(
                select(Monatsdaten).where(
                    Monatsdaten.anlage_id == anlage_id,
                    Monatsdaten.jahr == jahr,
                    Monatsdaten.monat == monat,
                )
            )
            existing_md = existing.scalar_one_or_none()

            if existing_md and not ueberschreiben:
                uebersprungen += 1
                continue

            # Monatsdaten erstellen oder aktualisieren
            if existing_md:
                md = existing_md
            else:
                md = Monatsdaten(anlage_id=anlage_id, jahr=jahr, monat=monat)
                db.add(md)

            # Basis-Felder setzen
            if monat_input.einspeisung_kwh is not None:
                md.einspeisung_kwh = monat_input.einspeisung_kwh
            if monat_input.netzbezug_kwh is not None:
                md.netzbezug_kwh = monat_input.netzbezug_kwh
            if monat_input.eigenverbrauch_kwh is not None:
                md.eigenverbrauch_kwh = monat_input.eigenverbrauch_kwh

            # Legacy-Felder für Batterie auf Monatsdaten-Ebene
            if monat_input.batterie_ladung_kwh is not None:
                md.batterie_ladung_kwh = monat_input.batterie_ladung_kwh
            if monat_input.batterie_entladung_kwh is not None:
                md.batterie_entladung_kwh = monat_input.batterie_entladung_kwh

            md.datenquelle = "portal_import"

            # PV-Erzeugung auf PV-Module verteilen
            if monat_input.pv_erzeugung_kwh is not None and monat_input.pv_erzeugung_kwh > 0:
                if pv_module:
                    w = await _distribute_legacy_pv_to_modules(
                        db, monat_input.pv_erzeugung_kwh, pv_module, jahr, monat, ueberschreiben
                    )
                    if importiert == 0:  # Warnung nur einmal
                        warnungen.extend(w)
                else:
                    # Kein PV-Modul angelegt → Legacy-Feld nutzen
                    md.pv_erzeugung_kwh = monat_input.pv_erzeugung_kwh

            # Batterie-Werte auf Speicher verteilen
            bat_ladung = monat_input.batterie_ladung_kwh or 0
            bat_entladung = monat_input.batterie_entladung_kwh or 0
            if (bat_ladung > 0 or bat_entladung > 0) and speicher:
                w = await _distribute_legacy_battery_to_storages(
                    db, bat_ladung, bat_entladung, speicher, jahr, monat, ueberschreiben
                )
                if importiert == 0:
                    warnungen.extend(w)

            # Wallbox-Ladung auf Wallbox-Investition verteilen
            if monat_input.wallbox_ladung_kwh is not None and monat_input.wallbox_ladung_kwh > 0:
                if wallboxen:
                    # Erste Wallbox verwenden (bei mehreren: proportional wäre Overkill)
                    wb = wallboxen[0]
                    verbrauch = {"ladung_kwh": monat_input.wallbox_ladung_kwh}
                    if monat_input.wallbox_ladung_pv_kwh is not None:
                        verbrauch["ladung_pv_kwh"] = monat_input.wallbox_ladung_pv_kwh
                    if monat_input.wallbox_ladevorgaenge is not None:
                        verbrauch["ladevorgaenge"] = monat_input.wallbox_ladevorgaenge
                    await _upsert_investition_monatsdaten(
                        db, wb.id, jahr, monat, verbrauch, ueberschreiben
                    )
                    if len(wallboxen) > 1 and importiert == 0:
                        warnungen.append(
                            f"Mehrere Wallboxen vorhanden – Ladedaten wurden der ersten "
                            f"Wallbox '{wb.bezeichnung or wb.typ}' zugeordnet."
                        )
                else:
                    if importiert == 0:
                        warnungen.append(
                            "Wallbox-Ladedaten gefunden, aber keine Wallbox als Investition angelegt. "
                            "Bitte zuerst eine Wallbox unter Investitionen anlegen."
                        )

            # E-Auto km_gefahren auf E-Auto-Investition verteilen
            if monat_input.eauto_km_gefahren is not None and monat_input.eauto_km_gefahren > 0:
                eautos = [i for i in investitionen if i.typ == "eauto"]
                if eautos:
                    ea = eautos[0]
                    await _upsert_investition_monatsdaten(
                        db, ea.id, jahr, monat,
                        {"km_gefahren": monat_input.eauto_km_gefahren},
                        ueberschreiben,
                    )

            importiert += 1

        except Exception as e:
            logger.exception(f"Fehler bei Monat {monat_input.jahr}/{monat_input.monat}")
            fehler.append(f"{monat_input.jahr}/{monat_input.monat:02d}: {str(e)}")

    await db.flush()

    return ApplyResponse(
        erfolg=len(fehler) == 0,
        importiert=importiert,
        uebersprungen=uebersprungen,
        fehler=fehler[:20],
        warnungen=warnungen[:10],
    )
