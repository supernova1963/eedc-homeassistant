"""
JSON Import/Export Operations

Vollständiger Anlagen-Export und -Import im JSON-Format.
"""

import json
import logging
from datetime import datetime, date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.core.config import APP_VERSION
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.strompreis import Strompreis
from backend.models.pvgis_prognose import PVGISPrognose as PVGISPrognoseModel, PVGISMonatsprognose

from .schemas import JSONImportResult
from .helpers import _parse_date

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Export Schemas (nur für JSON Export)
# =============================================================================

class InvestitionMonatsdatenExport(BaseModel):
    """Export-Schema für Investitions-Monatsdaten."""
    jahr: int
    monat: int
    verbrauch_daten: Optional[dict] = None
    einsparung_monat_euro: Optional[float] = None
    co2_einsparung_kg: Optional[float] = None
    # Hinweis: sonderkosten_euro/notiz existieren im Model nicht,
    # wurden hier fälschlicherweise definiert - entfernt


class InvestitionExport(BaseModel):
    """Export-Schema für Investitionen (hierarchisch mit Children)."""
    typ: str
    bezeichnung: str
    anschaffungskosten_gesamt: Optional[float] = None
    anschaffungskosten_alternativ: Optional[float] = None
    betriebskosten_jahr: Optional[float] = None
    anschaffungsdatum: Optional[date] = None
    leistung_kwp: Optional[float] = None
    ausrichtung: Optional[str] = None
    neigung_grad: Optional[float] = None
    ha_entity_id: Optional[str] = None
    parameter: Optional[dict] = None
    aktiv: bool = True
    children: List["InvestitionExport"] = []
    monatsdaten: List[InvestitionMonatsdatenExport] = []


class StrompreisExport(BaseModel):
    """Export-Schema für Strompreise."""
    tarifname: Optional[str] = None
    anbieter: Optional[str] = None
    netzbezug_arbeitspreis_cent_kwh: float
    einspeiseverguetung_cent_kwh: float
    grundpreis_euro_monat: Optional[float] = None
    gueltig_ab: date
    gueltig_bis: Optional[date] = None
    vertragsart: Optional[str] = None
    verwendung: str = "allgemein"


class MonatsdatenExport(BaseModel):
    """Export-Schema für Monatsdaten (Zählerwerte)."""
    jahr: int
    monat: int
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    globalstrahlung_kwh_m2: Optional[float] = None
    sonnenstunden: Optional[float] = None
    durchschnittstemperatur: Optional[float] = None  # NEU
    sonderkosten_euro: Optional[float] = None  # NEU
    sonderkosten_beschreibung: Optional[str] = None  # NEU
    datenquelle: Optional[str] = None
    notizen: Optional[str] = None


class PVGISMonatsprognoseExport(BaseModel):
    """Export-Schema für PVGIS Monatsprognosen."""
    monat: int
    ertrag_kwh: float
    einstrahlung_kwh_m2: Optional[float] = None
    standardabweichung_kwh: Optional[float] = None


class PVGISPrognoseExport(BaseModel):
    """Export-Schema für PVGIS Prognosen."""
    latitude: float
    longitude: float
    neigung_grad: float
    ausrichtung_grad: float
    jahresertrag_kwh: float
    spezifischer_ertrag_kwh_kwp: Optional[float] = None
    system_losses: Optional[float] = None
    monatsprognosen: List[PVGISMonatsprognoseExport] = []


class AnlageExport(BaseModel):
    """Export-Schema für Anlagen-Stammdaten."""
    anlagenname: str
    leistung_kwp: float
    installationsdatum: Optional[date] = None
    standort_plz: Optional[str] = None
    standort_ort: Optional[str] = None
    standort_strasse: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    ausrichtung: Optional[str] = None
    neigung_grad: Optional[float] = None
    mastr_id: Optional[str] = None
    versorger_daten: Optional[dict] = None
    wetter_provider: Optional[str] = None
    sensor_mapping: Optional[dict] = None  # NEU: HA Sensor-Zuordnungen
    steuerliche_behandlung: Optional[str] = None
    ust_satz_prozent: Optional[float] = None
    horizont_daten: Optional[list] = None


class FullAnlageExport(BaseModel):
    """Vollständiger Export einer Anlage mit allen verknüpften Daten."""
    export_version: str = "1.1"  # v1.1: sensor_mapping, durchschnittstemperatur, sonderkosten
    export_datum: datetime
    eedc_version: str
    anlage: AnlageExport
    strompreise: List[StrompreisExport] = []
    investitionen: List[InvestitionExport] = []
    monatsdaten: List[MonatsdatenExport] = []
    pvgis_prognosen: List[PVGISPrognoseExport] = []


# Forward reference für rekursive Typen
InvestitionExport.model_rebuild()


# =============================================================================
# Helper Functions
# =============================================================================

async def _generate_unique_anlage_name(db: AsyncSession, base_name: str) -> str:
    """
    Generiert einen eindeutigen Anlagennamen.
    Wenn der Name existiert, wird "(Import N)" angehängt.
    """
    result = await db.execute(
        select(Anlage).where(Anlage.anlagenname == base_name)
    )
    if not result.scalar_one_or_none():
        return base_name

    for i in range(1, 100):
        new_name = f"{base_name} (Import {i})"
        result = await db.execute(
            select(Anlage).where(Anlage.anlagenname == new_name)
        )
        if not result.scalar_one_or_none():
            return new_name

    return f"{base_name} (Import {datetime.now().strftime('%Y%m%d_%H%M%S')})"


async def _delete_anlage_cascade(db: AsyncSession, anlage_id: int):
    """Löscht eine Anlage mit allen verknüpften Daten."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()
    if anlage:
        await db.delete(anlage)
        await db.flush()


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/export/{anlage_id}/full")
async def export_anlage_full(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Exportiert eine vollständige Anlage mit allen Daten als JSON.

    Enthält:
    - Anlage-Stammdaten (inkl. mastr_id, versorger_daten)
    - Alle Strompreise
    - Alle Investitionen (hierarchisch mit Parent-Child)
    - InvestitionMonatsdaten pro Komponente
    - Monatsdaten (Zählerwerte)
    - PVGIS-Prognosen mit Monatswerten
    """
    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail="Anlage nicht gefunden")

    # Anlage-Daten exportieren
    anlage_export = AnlageExport(
        anlagenname=anlage.anlagenname,
        leistung_kwp=anlage.leistung_kwp,
        installationsdatum=anlage.installationsdatum,
        standort_land=getattr(anlage, 'standort_land', None),
        standort_plz=anlage.standort_plz,
        standort_ort=anlage.standort_ort,
        standort_strasse=anlage.standort_strasse,
        latitude=anlage.latitude,
        longitude=anlage.longitude,
        ausrichtung=anlage.ausrichtung,
        neigung_grad=anlage.neigung_grad,
        mastr_id=anlage.mastr_id,
        versorger_daten=anlage.versorger_daten,
        wetter_provider=anlage.wetter_provider,
        sensor_mapping=anlage.sensor_mapping,  # NEU: HA Sensor-Zuordnungen
        steuerliche_behandlung=getattr(anlage, 'steuerliche_behandlung', None),
        ust_satz_prozent=getattr(anlage, 'ust_satz_prozent', None),
    )

    # Strompreise laden
    strompreise_result = await db.execute(
        select(Strompreis)
        .where(Strompreis.anlage_id == anlage_id)
        .order_by(Strompreis.gueltig_ab)
    )
    strompreise = strompreise_result.scalars().all()

    strompreise_export = [
        StrompreisExport(
            tarifname=sp.tarifname,
            anbieter=sp.anbieter,
            netzbezug_arbeitspreis_cent_kwh=sp.netzbezug_arbeitspreis_cent_kwh,
            einspeiseverguetung_cent_kwh=sp.einspeiseverguetung_cent_kwh,
            grundpreis_euro_monat=sp.grundpreis_euro_monat,
            gueltig_ab=sp.gueltig_ab,
            gueltig_bis=sp.gueltig_bis,
            vertragsart=sp.vertragsart,
            verwendung=sp.verwendung or "allgemein",
        )
        for sp in strompreise
    ]

    # Investitionen laden (hierarchisch)
    inv_result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .order_by(Investition.typ, Investition.id)
    )
    all_investitionen = list(inv_result.scalars().all())

    # InvestitionMonatsdaten laden
    inv_ids = [inv.id for inv in all_investitionen]
    imd_map: dict[int, list[InvestitionMonatsdatenExport]] = {inv_id: [] for inv_id in inv_ids}

    if inv_ids:
        imd_result = await db.execute(
            select(InvestitionMonatsdaten)
            .where(InvestitionMonatsdaten.investition_id.in_(inv_ids))
            .order_by(InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat)
        )
        for imd in imd_result.scalars().all():
            imd_export = InvestitionMonatsdatenExport(
                jahr=imd.jahr,
                monat=imd.monat,
                verbrauch_daten=imd.verbrauch_daten,
                einsparung_monat_euro=imd.einsparung_monat_euro,
                co2_einsparung_kg=imd.co2_einsparung_kg,
            )
            imd_map[imd.investition_id].append(imd_export)

    # Hierarchie aufbauen
    inv_by_id = {inv.id: inv for inv in all_investitionen}
    children_by_parent: dict[int, list[Investition]] = {}
    top_level_investments: list[Investition] = []

    for inv in all_investitionen:
        if inv.parent_investition_id:
            if inv.parent_investition_id not in children_by_parent:
                children_by_parent[inv.parent_investition_id] = []
            children_by_parent[inv.parent_investition_id].append(inv)
        else:
            top_level_investments.append(inv)

    def build_inv_export(inv: Investition) -> InvestitionExport:
        children_exports = []
        for child in children_by_parent.get(inv.id, []):
            children_exports.append(build_inv_export(child))

        return InvestitionExport(
            typ=inv.typ,
            bezeichnung=inv.bezeichnung,
            anschaffungskosten_gesamt=inv.anschaffungskosten_gesamt,
            anschaffungskosten_alternativ=inv.anschaffungskosten_alternativ,
            betriebskosten_jahr=inv.betriebskosten_jahr,
            anschaffungsdatum=inv.anschaffungsdatum,
            leistung_kwp=inv.leistung_kwp,
            ausrichtung=inv.ausrichtung,
            neigung_grad=inv.neigung_grad,
            ha_entity_id=inv.ha_entity_id,
            parameter=inv.parameter,
            aktiv=inv.aktiv,
            children=children_exports,
            monatsdaten=imd_map.get(inv.id, []),
        )

    investitionen_export = [build_inv_export(inv) for inv in top_level_investments]

    # Monatsdaten laden
    md_result = await db.execute(
        select(Monatsdaten)
        .where(Monatsdaten.anlage_id == anlage_id)
        .order_by(Monatsdaten.jahr, Monatsdaten.monat)
    )
    monatsdaten = md_result.scalars().all()

    monatsdaten_export = [
        MonatsdatenExport(
            jahr=md.jahr,
            monat=md.monat,
            einspeisung_kwh=md.einspeisung_kwh,
            netzbezug_kwh=md.netzbezug_kwh,
            globalstrahlung_kwh_m2=md.globalstrahlung_kwh_m2,
            sonnenstunden=md.sonnenstunden,
            durchschnittstemperatur=md.durchschnittstemperatur,  # NEU
            sonderkosten_euro=md.sonderkosten_euro,  # NEU
            sonderkosten_beschreibung=md.sonderkosten_beschreibung,  # NEU
            datenquelle=md.datenquelle,
            notizen=md.notizen,
        )
        for md in monatsdaten
    ]

    # PVGIS-Prognosen laden
    pvgis_result = await db.execute(
        select(PVGISPrognoseModel)
        .where(PVGISPrognoseModel.anlage_id == anlage_id)
    )
    pvgis_prognosen = pvgis_result.scalars().all()

    pvgis_export = []
    for pvgis in pvgis_prognosen:
        # Monatsprognosen laden
        mp_result = await db.execute(
            select(PVGISMonatsprognose)
            .where(PVGISMonatsprognose.prognose_id == pvgis.id)
            .order_by(PVGISMonatsprognose.monat)
        )
        monatsprognosen = mp_result.scalars().all()

        pvgis_export.append(PVGISPrognoseExport(
            latitude=pvgis.latitude,
            longitude=pvgis.longitude,
            neigung_grad=pvgis.neigung_grad,
            ausrichtung_grad=pvgis.ausrichtung_grad,
            jahresertrag_kwh=pvgis.jahresertrag_kwh,
            spezifischer_ertrag_kwh_kwp=pvgis.spezifischer_ertrag_kwh_kwp,
            system_losses=pvgis.system_losses,
            monatsprognosen=[
                PVGISMonatsprognoseExport(
                    monat=mp.monat,
                    ertrag_kwh=mp.ertrag_kwh,
                    einstrahlung_kwh_m2=mp.einstrahlung_kwh_m2,
                    standardabweichung_kwh=mp.standardabweichung_kwh,
                )
                for mp in monatsprognosen
            ],
        ))

    # Vollständiger Export
    full_export = FullAnlageExport(
        export_version="1.1",
        export_datum=datetime.now(),
        eedc_version=APP_VERSION,
        anlage=anlage_export,
        strompreise=strompreise_export,
        investitionen=investitionen_export,
        monatsdaten=monatsdaten_export,
        pvgis_prognosen=pvgis_export,
    )

    filename = f"eedc_export_{anlage.anlagenname.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.json"

    return JSONResponse(
        content=full_export.model_dump(mode="json"),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


@router.post("/json")
async def import_json(
    file: UploadFile = File(...),
    ueberschreiben: bool = Query(False, description="Existierende Anlage mit gleichem Namen überschreiben"),
    db: AsyncSession = Depends(get_db)
) -> JSONImportResult:
    """
    Importiert eine Anlage aus einer JSON-Export-Datei.

    - Erstellt neue Anlage (bei ueberschreiben=False ggf. mit Namens-Suffix)
    - Bei ueberschreiben=True wird existierende Anlage gelöscht und neu erstellt
    - Importiert alle verknüpften Daten (Strompreise, Investitionen, Monatsdaten, PVGIS)
    """
    warnungen: list[str] = []
    fehler: list[str] = []
    importiert = {
        "strompreise": 0,
        "investitionen": 0,
        "investition_monatsdaten": 0,
        "monatsdaten": 0,
        "pvgis_prognosen": 0,
        "pvgis_monatsprognosen": 0,
    }

    # 1. JSON lesen und validieren
    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
    except json.JSONDecodeError as e:
        return JSONImportResult(
            erfolg=False,
            fehler=[f"Ungültiges JSON-Format: {e}"]
        )
    except Exception as e:
        return JSONImportResult(
            erfolg=False,
            fehler=[f"Fehler beim Lesen der Datei: {e}"]
        )

    # 2. Version prüfen (1.0 und 1.1 werden unterstützt)
    export_version = data.get("export_version")
    if export_version not in ["1.0", "1.1"]:
        return JSONImportResult(
            erfolg=False,
            fehler=[f"Nicht unterstützte Export-Version: {export_version}. Unterstützt: 1.0, 1.1"]
        )
    if export_version == "1.0":
        warnungen.append("Import von Export-Version 1.0 - sensor_mapping nicht enthalten.")

    # 3. Pflichtfelder prüfen
    anlage_data = data.get("anlage")
    if not anlage_data:
        return JSONImportResult(
            erfolg=False,
            fehler=["Fehlende Anlage-Daten im Export"]
        )

    original_name = anlage_data.get("anlagenname")
    if not original_name:
        return JSONImportResult(
            erfolg=False,
            fehler=["Fehlender Anlagenname im Export"]
        )

    try:
        # 4. Prüfen ob Anlage existiert
        result = await db.execute(
            select(Anlage).where(Anlage.anlagenname == original_name)
        )
        existing_anlage = result.scalar_one_or_none()

        if existing_anlage:
            if ueberschreiben:
                logger.info(f"Überschreibe Anlage '{original_name}' (ID: {existing_anlage.id})")
                await _delete_anlage_cascade(db, existing_anlage.id)
                anlage_name = original_name
                warnungen.append(f"Existierende Anlage '{original_name}' wurde überschrieben")
            else:
                anlage_name = await _generate_unique_anlage_name(db, original_name)
                if anlage_name != original_name:
                    warnungen.append(f"Anlage wurde als '{anlage_name}' importiert (Original: '{original_name}')")
        else:
            anlage_name = original_name

        # 5. Anlage erstellen
        # Sensor-Mapping: mqtt_setup_complete auf False setzen, da IDs nicht übertragbar
        imported_sensor_mapping = anlage_data.get("sensor_mapping")
        if imported_sensor_mapping:
            # MQTT-Setup muss nach Import neu durchgeführt werden
            imported_sensor_mapping["mqtt_setup_complete"] = False
            imported_sensor_mapping["mqtt_setup_timestamp"] = None
            warnungen.append(
                "Sensor-Mapping importiert. MQTT-Setup muss nach Import erneut durchgeführt werden "
                "(Einstellungen → Home Assistant → Sensor-Zuordnung speichern)."
            )

        new_anlage = Anlage(
            anlagenname=anlage_name,
            leistung_kwp=anlage_data.get("leistung_kwp", 0),
            installationsdatum=_parse_date(anlage_data.get("installationsdatum")),
            standort_land=anlage_data.get("standort_land", "DE"),
            standort_plz=anlage_data.get("standort_plz"),
            standort_ort=anlage_data.get("standort_ort"),
            standort_strasse=anlage_data.get("standort_strasse"),
            latitude=anlage_data.get("latitude"),
            longitude=anlage_data.get("longitude"),
            ausrichtung=anlage_data.get("ausrichtung"),
            neigung_grad=anlage_data.get("neigung_grad"),
            mastr_id=anlage_data.get("mastr_id"),
            versorger_daten=anlage_data.get("versorger_daten"),
            wetter_provider=anlage_data.get("wetter_provider", "auto"),
            sensor_mapping=imported_sensor_mapping,  # NEU: HA Sensor-Zuordnungen
            steuerliche_behandlung=anlage_data.get("steuerliche_behandlung", "keine_ust"),
            ust_satz_prozent=anlage_data.get("ust_satz_prozent", 19.0),
        )
        db.add(new_anlage)
        await db.flush()
        anlage_id = new_anlage.id
        logger.info(f"Anlage '{anlage_name}' erstellt mit ID {anlage_id}")

        # 6. Strompreise importieren
        for sp_data in data.get("strompreise", []):
            strompreis = Strompreis(
                anlage_id=anlage_id,
                tarifname=sp_data.get("tarifname"),
                anbieter=sp_data.get("anbieter"),
                netzbezug_arbeitspreis_cent_kwh=sp_data.get("netzbezug_arbeitspreis_cent_kwh", 0),
                einspeiseverguetung_cent_kwh=sp_data.get("einspeiseverguetung_cent_kwh", 0),
                grundpreis_euro_monat=sp_data.get("grundpreis_euro_monat"),
                gueltig_ab=_parse_date(sp_data.get("gueltig_ab")),
                gueltig_bis=_parse_date(sp_data.get("gueltig_bis")),
                vertragsart=sp_data.get("vertragsart"),
                verwendung=sp_data.get("verwendung", "allgemein"),
            )
            db.add(strompreis)
            importiert["strompreise"] += 1

        # 7. Investitionen hierarchisch importieren
        # Mapping von Bezeichnung+Typ zu neuer ID (für sensor_mapping Korrektur)
        inv_bezeichnung_to_new_id: dict[str, int] = {}

        async def import_investition(inv_data: dict, parent_id: Optional[int] = None) -> int:
            """Importiert eine Investition rekursiv mit Children."""
            inv = Investition(
                anlage_id=anlage_id,
                typ=inv_data.get("typ", "sonstiges"),
                bezeichnung=inv_data.get("bezeichnung", "Unbenannt"),
                anschaffungskosten_gesamt=inv_data.get("anschaffungskosten_gesamt"),
                anschaffungskosten_alternativ=inv_data.get("anschaffungskosten_alternativ"),
                betriebskosten_jahr=inv_data.get("betriebskosten_jahr"),
                anschaffungsdatum=_parse_date(inv_data.get("anschaffungsdatum")),
                leistung_kwp=inv_data.get("leistung_kwp"),
                ausrichtung=inv_data.get("ausrichtung"),
                neigung_grad=inv_data.get("neigung_grad"),
                ha_entity_id=inv_data.get("ha_entity_id"),
                parameter=inv_data.get("parameter"),
                aktiv=inv_data.get("aktiv", True),
                parent_investition_id=parent_id,
            )
            db.add(inv)
            await db.flush()
            inv_id = inv.id
            importiert["investitionen"] += 1

            # Mapping von Bezeichnung+Typ zu neuer ID speichern (für sensor_mapping)
            key = f"{inv_data.get('typ', '')}:{inv_data.get('bezeichnung', '')}"
            inv_bezeichnung_to_new_id[key] = inv_id

            # Monatsdaten der Investition importieren
            for md_data in inv_data.get("monatsdaten", []):
                inv_md = InvestitionMonatsdaten(
                    investition_id=inv_id,
                    jahr=md_data.get("jahr"),
                    monat=md_data.get("monat"),
                    verbrauch_daten=md_data.get("verbrauch_daten"),
                    einsparung_monat_euro=md_data.get("einsparung_monat_euro"),
                    co2_einsparung_kg=md_data.get("co2_einsparung_kg"),
                )
                db.add(inv_md)
                importiert["investition_monatsdaten"] += 1

            # Children rekursiv importieren
            for child_data in inv_data.get("children", []):
                await import_investition(child_data, parent_id=inv_id)

            return inv_id

        for inv_data in data.get("investitionen", []):
            await import_investition(inv_data)

        # 7b. sensor_mapping komplett neu aufbauen basierend auf Bezeichnung+Typ
        # Das sensor_mapping enthält alte IDs die nicht mehr gültig sind
        if imported_sensor_mapping:
            # Wir löschen das alte Investitionen-Mapping komplett
            # Der Benutzer muss das Sensor-Mapping nach Import neu konfigurieren
            imported_sensor_mapping["investitionen"] = {}
            imported_sensor_mapping["mqtt_setup_complete"] = False
            imported_sensor_mapping["mqtt_setup_timestamp"] = None
            new_anlage.sensor_mapping = imported_sensor_mapping
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(new_anlage, "sensor_mapping")

            warnungen.append(
                "WICHTIG: Das Sensor-Mapping für Investitionen wurde zurückgesetzt, da die Investitions-IDs "
                "nach dem Import nicht mehr übereinstimmen. Bitte konfigurieren Sie das Sensor-Mapping neu "
                "(Einstellungen → Home Assistant → Sensor-Zuordnung)."
            )
            logger.info("sensor_mapping Investitionen zurückgesetzt - IDs nicht übertragbar")

        # 8. Monatsdaten (Zählerwerte) importieren
        for md_data in data.get("monatsdaten", []):
            jahr = md_data.get("jahr")
            monat = md_data.get("monat")

            if jahr is None or monat is None:
                warnungen.append("Monatsdaten ohne Jahr/Monat übersprungen")
                continue

            monatsdaten = Monatsdaten(
                anlage_id=anlage_id,
                jahr=jahr,
                monat=monat,
                einspeisung_kwh=md_data.get("einspeisung_kwh", 0),
                netzbezug_kwh=md_data.get("netzbezug_kwh", 0),
                globalstrahlung_kwh_m2=md_data.get("globalstrahlung_kwh_m2"),
                sonnenstunden=md_data.get("sonnenstunden"),
                durchschnittstemperatur=md_data.get("durchschnittstemperatur"),  # NEU
                sonderkosten_euro=md_data.get("sonderkosten_euro"),  # NEU
                sonderkosten_beschreibung=md_data.get("sonderkosten_beschreibung"),  # NEU
                datenquelle=md_data.get("datenquelle") or "json_import",
                notizen=md_data.get("notizen"),
            )
            db.add(monatsdaten)
            importiert["monatsdaten"] += 1

        # 9. PVGIS-Prognosen importieren
        for pvgis_data in data.get("pvgis_prognosen", []):
            pvgis = PVGISPrognoseModel(
                anlage_id=anlage_id,
                latitude=pvgis_data.get("latitude", 0),
                longitude=pvgis_data.get("longitude", 0),
                neigung_grad=pvgis_data.get("neigung_grad", 0),
                ausrichtung_grad=pvgis_data.get("ausrichtung_grad", 0),
                jahresertrag_kwh=pvgis_data.get("jahresertrag_kwh", 0),
                spezifischer_ertrag_kwh_kwp=pvgis_data.get("spezifischer_ertrag_kwh_kwp", 0),
                system_losses=pvgis_data.get("system_losses", 14.0),
                ist_aktiv=True,
            )
            db.add(pvgis)
            await db.flush()
            pvgis_id = pvgis.id
            importiert["pvgis_prognosen"] += 1

            # Monatsprognosen importieren
            for mp_data in pvgis_data.get("monatsprognosen", []):
                mp = PVGISMonatsprognose(
                    prognose_id=pvgis_id,
                    monat=mp_data.get("monat"),
                    ertrag_kwh=mp_data.get("ertrag_kwh", 0),
                    einstrahlung_kwh_m2=mp_data.get("einstrahlung_kwh_m2", 0),
                    standardabweichung_kwh=mp_data.get("standardabweichung_kwh", 0),
                )
                db.add(mp)
                importiert["pvgis_monatsprognosen"] += 1

        await db.commit()

        logger.info(f"JSON-Import abgeschlossen: {importiert}")

        return JSONImportResult(
            erfolg=True,
            anlage_id=anlage_id,
            anlage_name=anlage_name,
            importiert=importiert,
            warnungen=warnungen,
        )

    except Exception as e:
        await db.rollback()
        logger.exception(f"Fehler beim JSON-Import: {e}")
        return JSONImportResult(
            erfolg=False,
            fehler=[f"Import-Fehler: {str(e)}"],
            warnungen=warnungen,
        )
