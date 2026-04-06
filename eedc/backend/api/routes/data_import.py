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
from backend.services.activity_service import log_activity

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


class InvestitionsZuordnung(BaseModel):
    """
    Optionale manuelle Zuordnung von Import-Werten zu Investitionen.
    Wird nur benötigt wenn mehrere Investitionen desselben Typs vorhanden sind.
    """
    # PV: {inv_id: anteil_prozent} — muss 100 ergeben, sonst proportional
    pv: dict[int, float] = {}
    # Batterie: {inv_id: anteil_prozent} — muss 100 ergeben, sonst proportional
    batterie: dict[int, float] = {}
    # Wallbox: ID der zu verwendenden Wallbox (None = erste)
    wallbox_id: Optional[int] = None
    # E-Auto: ID des zu verwendenden E-Autos (None = erste)
    eauto_id: Optional[int] = None


class ApplyRequest(BaseModel):
    monate: list[ApplyMonthInput]
    zuordnung: Optional[InvestitionsZuordnung] = None


class ApplyResponse(BaseModel):
    erfolg: bool
    importiert: int
    uebersprungen: int
    fehler: list[str]
    warnungen: list[str]


class ZuordnungInvestition(BaseModel):
    id: int
    bezeichnung: str
    kwp: Optional[float] = None       # PV-Module
    kwh: Optional[float] = None       # Speicher
    default_anteil: float = 0.0       # vorberechneter Default-Anteil in %


class ZuordnungInfo(BaseModel):
    benoetigt_zuordnung: bool
    pv_module: list[ZuordnungInvestition] = []
    speicher: list[ZuordnungInvestition] = []
    wallboxen: list[ZuordnungInvestition] = []
    eautos: list[ZuordnungInvestition] = []


# ─── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/parsers", response_model=list[ParserInfoResponse])
async def get_parsers():
    """Verfügbare Portal-Export-Parser mit Anleitungen."""
    return [p.to_dict() for p in list_parsers()]


@router.get("/zuordnung-info/{anlage_id}", response_model=ZuordnungInfo)
async def get_zuordnung_info(
    anlage_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Gibt Investitions-Informationen zurück die für den Zuordnungs-Schritt benötigt werden.

    benoetigt_zuordnung=True wenn mindestens ein Investitionstyp mehrfach vorhanden ist
    (z.B. 2 PV-Module, 2 Speicher). In diesem Fall sollte der Wizard den Zuordnungs-Schritt
    anzeigen.

    Default-Anteile werden proportional nach kWp (PV) bzw. Kapazität (Speicher) berechnet.
    """
    result = await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id)
    )
    investitionen = result.scalars().all()

    pv_module = [i for i in investitionen if i.typ == "pv-module"]
    speicher = [i for i in investitionen if i.typ == "speicher"]
    wallboxen = [i for i in investitionen if i.typ == "wallbox"]
    eautos = [i for i in investitionen if i.typ == "e-auto"]

    benoetigt = len(pv_module) > 1 or len(speicher) > 1 or len(wallboxen) > 1 or len(eautos) > 1

    def pv_anteil(inv: Investition, alle: list[Investition]) -> float:
        total = sum((i.parameter or {}).get("leistung_kwp", 0) or 0 for i in alle)
        kwp = (inv.parameter or {}).get("leistung_kwp", 0) or 0
        if total > 0:
            return round(kwp / total * 100, 1)
        return round(100.0 / len(alle), 1) if alle else 0.0

    def bat_anteil(inv: Investition, alle: list[Investition]) -> float:
        total = sum((i.parameter or {}).get("kapazitaet_kwh", 0) or 0 for i in alle)
        kwh = (inv.parameter or {}).get("kapazitaet_kwh", 0) or 0
        if total > 0:
            return round(kwh / total * 100, 1)
        return round(100.0 / len(alle), 1) if alle else 0.0

    return ZuordnungInfo(
        benoetigt_zuordnung=benoetigt,
        pv_module=[
            ZuordnungInvestition(
                id=i.id,
                bezeichnung=i.bezeichnung or i.typ,
                kwp=(i.parameter or {}).get("leistung_kwp"),
                default_anteil=pv_anteil(i, pv_module),
            ) for i in pv_module
        ],
        speicher=[
            ZuordnungInvestition(
                id=i.id,
                bezeichnung=i.bezeichnung or i.typ,
                kwh=(i.parameter or {}).get("kapazitaet_kwh"),
                default_anteil=bat_anteil(i, speicher),
            ) for i in speicher
        ],
        wallboxen=[
            ZuordnungInvestition(id=i.id, bezeichnung=i.bezeichnung or i.typ)
            for i in wallboxen
        ],
        eautos=[
            ZuordnungInvestition(id=i.id, bezeichnung=i.bezeichnung or i.typ)
            for i in eautos
        ],
    )


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
    datenquelle: str = Query("portal_import", description="Datenquelle (portal_import, cloud_import)"),
    db: AsyncSession = Depends(get_db),
):
    """Bestätigte Monatswerte aus Portal-Import oder Cloud-Import in die Datenbank übernehmen."""
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

            zuordnung = data.zuordnung

            # ── PV-Erzeugung ─────────────────────────────────────────────────
            pv_erzeugung: Optional[float] = None
            if monat_input.pv_erzeugung_kwh is not None and monat_input.pv_erzeugung_kwh > 0:
                if pv_module:
                    pv_kwh = monat_input.pv_erzeugung_kwh
                    if zuordnung and zuordnung.pv:
                        # Manuelle Zuordnung: % pro Modul
                        for inv in pv_module:
                            anteil = zuordnung.pv.get(inv.id, 0) / 100.0
                            pv_anteil = round(pv_kwh * anteil, 1)
                            if pv_anteil > 0:
                                await _upsert_investition_monatsdaten(
                                    db, inv.id, jahr, monat,
                                    {"pv_erzeugung_kwh": pv_anteil}, ueberschreiben
                                )
                    else:
                        # Proportional nach kWp (Default)
                        w = await _distribute_legacy_pv_to_modules(
                            db, pv_kwh, pv_module, jahr, monat, ueberschreiben
                        )
                        if importiert == 0:
                            warnungen.extend(w)
                pv_erzeugung = monat_input.pv_erzeugung_kwh

            # ── Batterie ──────────────────────────────────────────────────────
            bat_ladung: Optional[float] = None
            bat_entladung: Optional[float] = None
            bat_ladung_raw = monat_input.batterie_ladung_kwh
            bat_entladung_raw = monat_input.batterie_entladung_kwh
            if (bat_ladung_raw or 0) > 0 or (bat_entladung_raw or 0) > 0:
                if speicher:
                    if zuordnung and zuordnung.batterie:
                        # Manuelle Zuordnung: % pro Speicher
                        for inv in speicher:
                            anteil = zuordnung.batterie.get(inv.id, 0) / 100.0
                            vd = {}
                            if bat_ladung_raw and bat_ladung_raw > 0:
                                vd["ladung_kwh"] = round(bat_ladung_raw * anteil, 1)
                            if bat_entladung_raw and bat_entladung_raw > 0:
                                vd["entladung_kwh"] = round(bat_entladung_raw * anteil, 1)
                            if vd:
                                await _upsert_investition_monatsdaten(
                                    db, inv.id, jahr, monat, vd, ueberschreiben
                                )
                    else:
                        # Proportional nach Kapazität (Default)
                        w = await _distribute_legacy_battery_to_storages(
                            db, bat_ladung_raw or 0, bat_entladung_raw or 0,
                            speicher, jahr, monat, ueberschreiben
                        )
                        if importiert == 0:
                            warnungen.extend(w)
                bat_ladung = bat_ladung_raw
                bat_entladung = bat_entladung_raw

            # ── Monatsdaten schreiben ─────────────────────────────────────────
            if monat_input.einspeisung_kwh is not None:
                md.einspeisung_kwh = monat_input.einspeisung_kwh
            if monat_input.netzbezug_kwh is not None:
                md.netzbezug_kwh = monat_input.netzbezug_kwh
            if monat_input.eigenverbrauch_kwh is not None:
                md.eigenverbrauch_kwh = monat_input.eigenverbrauch_kwh
            if pv_erzeugung is not None:
                md.pv_erzeugung_kwh = pv_erzeugung
            if bat_ladung is not None:
                md.batterie_ladung_kwh = bat_ladung
            if bat_entladung is not None:
                md.batterie_entladung_kwh = bat_entladung
            md.datenquelle = datenquelle

            # ── Wallbox ───────────────────────────────────────────────────────
            if monat_input.wallbox_ladung_kwh is not None and monat_input.wallbox_ladung_kwh > 0:
                if wallboxen:
                    # Manuelle Zuordnung oder erste Wallbox
                    wb = next(
                        (w for w in wallboxen if zuordnung and w.id == zuordnung.wallbox_id),
                        wallboxen[0]
                    )
                    verbrauch = {"ladung_kwh": monat_input.wallbox_ladung_kwh}
                    if monat_input.wallbox_ladung_pv_kwh is not None:
                        verbrauch["ladung_pv_kwh"] = monat_input.wallbox_ladung_pv_kwh
                    if monat_input.wallbox_ladevorgaenge is not None:
                        verbrauch["ladevorgaenge"] = monat_input.wallbox_ladevorgaenge
                    await _upsert_investition_monatsdaten(
                        db, wb.id, jahr, monat, verbrauch, ueberschreiben
                    )
                    if len(wallboxen) > 1 and not (zuordnung and zuordnung.wallbox_id) and importiert == 0:
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

            # ── E-Auto ────────────────────────────────────────────────────────
            if monat_input.eauto_km_gefahren is not None and monat_input.eauto_km_gefahren > 0:
                eautos = [i for i in investitionen if i.typ == "e-auto"]
                if eautos:
                    ea = next(
                        (e for e in eautos if zuordnung and e.id == zuordnung.eauto_id),
                        eautos[0]
                    )
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

    await log_activity(
        kategorie="portal_import",
        aktion=f"Portal-Import: {importiert} Monate importiert",
        erfolg=len(fehler) == 0,
        details=f"Quelle: {datenquelle}, übersprungen: {uebersprungen}",
        details_json={"importiert": importiert, "uebersprungen": uebersprungen, "fehler": fehler[:5]},
        anlage_id=anlage_id,
    )

    return ApplyResponse(
        erfolg=len(fehler) == 0,
        importiert=importiert,
        uebersprungen=uebersprungen,
        fehler=fehler[:20],
        warnungen=warnungen[:10],
    )
