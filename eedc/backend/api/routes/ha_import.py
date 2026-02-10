"""
Home Assistant Import Routes

Ermöglicht den automatisierten Import von Monatsdaten aus Home Assistant.
Generiert YAML-Konfiguration für HA Template-Sensoren und Utility Meter.
"""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.models.investition import Investition, InvestitionTyp, InvestitionMonatsdaten
from backend.models.monatsdaten import Monatsdaten

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Pydantic Schemas
# =============================================================================

class SensorFeld(BaseModel):
    """Ein erwartetes Feld für einen Investitionstyp."""
    key: str
    label: str
    unit: str
    required: bool = False
    hint: str | None = None


class InvestitionMitSensorFeldern(BaseModel):
    """Investition mit den erwarteten Sensor-Feldern."""
    id: int
    bezeichnung: str
    typ: str
    felder: list[SensorFeld]
    parameter: dict | None = None


class SensorMapping(BaseModel):
    """Zuordnung von HA-Sensoren zu Investitions-Feldern."""
    investition_id: int
    mappings: dict[str, str] = Field(
        ...,
        description="Mapping von Feldname zu HA entity_id, z.B. {'km_gefahren': 'sensor.car_km_monthly'}"
    )


class SensorMappingRequest(BaseModel):
    """Request zum Speichern der Sensor-Zuordnungen."""
    mappings: list[SensorMapping]


class MonatsdatenImportRequest(BaseModel):
    """Request für den Import von Monatsdaten aus HA."""
    jahr: int = Field(..., ge=2000, le=2100)
    monat: int = Field(..., ge=1, le=12)
    # Basis-Monatsdaten
    einspeisung_kwh: float = Field(..., ge=0)
    netzbezug_kwh: float = Field(..., ge=0)
    pv_erzeugung_kwh: float | None = Field(None, ge=0)
    # Optionale Wetterdaten
    globalstrahlung_kwh_m2: float | None = Field(None, ge=0)
    sonnenstunden: float | None = Field(None, ge=0)
    # Investitions-Daten (pro investition_id)
    investitionen: dict[str, dict] | None = Field(
        None,
        description="Daten pro Investition: {'1': {'km_gefahren': 1200, 'verbrauch_kwh': 216}}"
    )


class ImportResult(BaseModel):
    """Ergebnis eines Imports."""
    erfolg: bool
    monatsdaten_id: int | None = None
    investitionen_importiert: int = 0
    fehler: list[str] = []
    hinweise: list[str] = []


# =============================================================================
# Feld-Definitionen pro Investitionstyp
# =============================================================================

def get_felder_fuer_typ(typ: str, parameter: dict | None = None) -> list[SensorFeld]:
    """Gibt die erwarteten Felder für einen Investitionstyp zurück."""

    if typ == "e-auto":
        felder = [
            SensorFeld(key="km_gefahren", label="Gefahrene km", unit="km"),
            SensorFeld(key="verbrauch_kwh", label="Verbrauch", unit="kWh"),
            SensorFeld(key="ladung_pv_kwh", label="Ladung aus PV", unit="kWh"),
            SensorFeld(key="ladung_netz_kwh", label="Ladung aus Netz", unit="kWh"),
            SensorFeld(key="ladung_extern_kwh", label="Externe Ladung", unit="kWh", hint="Öffentliche Ladesäulen"),
            SensorFeld(key="ladung_extern_euro", label="Externe Kosten", unit="€"),
        ]
        # V2H wenn aktiviert
        if parameter and (parameter.get("nutzt_v2h") or parameter.get("v2h_faehig")):
            felder.append(SensorFeld(key="v2h_entladung_kwh", label="V2H Entladung", unit="kWh"))
        return felder

    elif typ == "speicher":
        felder = [
            SensorFeld(key="ladung_kwh", label="Ladung", unit="kWh", required=True),
            SensorFeld(key="entladung_kwh", label="Entladung", unit="kWh", required=True),
        ]
        # Arbitrage wenn aktiviert
        if parameter and parameter.get("arbitrage_faehig"):
            felder.extend([
                SensorFeld(key="speicher_ladung_netz_kwh", label="Netzladung", unit="kWh", hint="Arbitrage"),
                SensorFeld(key="speicher_ladepreis_cent", label="Ø Ladepreis", unit="ct/kWh", hint="Arbitrage"),
            ])
        return felder

    elif typ == "wallbox":
        return [
            SensorFeld(key="ladung_kwh", label="Heimladung", unit="kWh", required=True),
            SensorFeld(key="ladevorgaenge", label="Ladevorgänge", unit="Anzahl"),
        ]

    elif typ == "waermepumpe":
        return [
            SensorFeld(key="stromverbrauch_kwh", label="Stromverbrauch", unit="kWh", required=True),
            SensorFeld(key="heizenergie_kwh", label="Heizenergie", unit="kWh"),
            SensorFeld(key="warmwasser_kwh", label="Warmwasser", unit="kWh"),
        ]

    elif typ == "pv-module":
        return [
            SensorFeld(key="pv_erzeugung_kwh", label="Erzeugung", unit="kWh", required=True),
        ]

    elif typ == "balkonkraftwerk":
        felder = [
            SensorFeld(key="pv_erzeugung_kwh", label="Erzeugung", unit="kWh", required=True),
        ]
        # Speicher wenn vorhanden
        if parameter and parameter.get("hat_speicher"):
            felder.extend([
                SensorFeld(key="speicher_ladung_kwh", label="Speicher Ladung", unit="kWh"),
                SensorFeld(key="speicher_entladung_kwh", label="Speicher Entladung", unit="kWh"),
            ])
        return felder

    elif typ == "sonstiges":
        kategorie = parameter.get("kategorie", "erzeuger") if parameter else "erzeuger"
        if kategorie == "erzeuger":
            return [
                SensorFeld(key="erzeugung_kwh", label="Erzeugung", unit="kWh", required=True),
            ]
        elif kategorie == "verbraucher":
            return [
                SensorFeld(key="verbrauch_kwh", label="Verbrauch", unit="kWh", required=True),
            ]
        elif kategorie == "speicher":
            return [
                SensorFeld(key="ladung_kwh", label="Ladung", unit="kWh"),
                SensorFeld(key="entladung_kwh", label="Entladung", unit="kWh"),
            ]

    return []


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/investitionen/{anlage_id}", response_model=list[InvestitionMitSensorFeldern])
async def get_investitionen_mit_feldern(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt alle aktiven Investitionen einer Anlage mit den erwarteten Sensor-Feldern zurück.

    Diese Felder werden benötigt für:
    - Sensor-Zuordnung im Frontend
    - YAML-Generierung für Utility Meter
    """
    # Anlage prüfen
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    # Aktive Investitionen laden
    result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.aktiv == True)
        .order_by(Investition.typ, Investition.bezeichnung)
    )
    investitionen = result.scalars().all()

    return [
        InvestitionMitSensorFeldern(
            id=inv.id,
            bezeichnung=inv.bezeichnung,
            typ=inv.typ,
            felder=get_felder_fuer_typ(inv.typ, inv.parameter),
            parameter=inv.parameter,
        )
        for inv in investitionen
    ]


@router.post("/sensor-mapping/{anlage_id}")
async def save_sensor_mapping(
    anlage_id: int,
    request: SensorMappingRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Speichert die Sensor-Zuordnungen für Investitionen.

    Die Mappings werden in Investition.parameter['ha_sensors'] gespeichert.
    """
    for mapping in request.mappings:
        result = await db.execute(
            select(Investition)
            .where(Investition.id == mapping.investition_id)
            .where(Investition.anlage_id == anlage_id)
        )
        inv = result.scalar_one_or_none()

        if not inv:
            raise HTTPException(
                status_code=404,
                detail=f"Investition {mapping.investition_id} nicht gefunden"
            )

        # Sensor-Mapping in Parameter speichern
        if inv.parameter is None:
            inv.parameter = {}
        inv.parameter["ha_sensors"] = mapping.mappings

    await db.commit()

    return {"status": "ok", "message": f"{len(request.mappings)} Mappings gespeichert"}


@router.get("/yaml/{anlage_id}")
async def generate_yaml(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Generiert YAML-Konfiguration für Home Assistant.

    Beinhaltet:
    - Utility Meter für monatliche Aggregation
    - REST Command für EEDC Import
    - Automation für monatlichen Import
    """
    from backend.services.ha_yaml_generator import generate_ha_yaml

    # Anlage laden
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    # Investitionen laden
    result = await db.execute(
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.aktiv == True)
    )
    investitionen = result.scalars().all()

    yaml_content = generate_ha_yaml(anlage, investitionen)

    return {
        "anlage_id": anlage_id,
        "anlage_name": anlage.anlagenname,
        "yaml": yaml_content,
        "hinweise": [
            "Diese YAML-Konfiguration in configuration.yaml einfügen",
            "Home Assistant danach neu starten",
            "Utility Meter werden monatlich zurückgesetzt",
            "Automation sendet Daten am 1. jeden Monats um 00:05",
        ]
    }


@router.post("/from-ha/{anlage_id}", response_model=ImportResult)
async def import_from_ha(
    anlage_id: int,
    request: MonatsdatenImportRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Importiert Monatsdaten aus Home Assistant.

    Dieser Endpoint wird von einer HA-Automation aufgerufen.
    Unterstützt sowohl Basis-Monatsdaten als auch Investitions-Monatsdaten.
    """
    fehler: list[str] = []
    hinweise: list[str] = []
    investitionen_count = 0

    # Anlage prüfen
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        return ImportResult(erfolg=False, fehler=[f"Anlage {anlage_id} nicht gefunden"])

    # Prüfen ob Monatsdaten bereits existieren
    result = await db.execute(
        select(Monatsdaten)
        .where(Monatsdaten.anlage_id == anlage_id)
        .where(Monatsdaten.jahr == request.jahr)
        .where(Monatsdaten.monat == request.monat)
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update
        existing.einspeisung_kwh = request.einspeisung_kwh
        existing.netzbezug_kwh = request.netzbezug_kwh
        if request.pv_erzeugung_kwh is not None:
            existing.pv_erzeugung_kwh = request.pv_erzeugung_kwh
        if request.globalstrahlung_kwh_m2 is not None:
            existing.globalstrahlung_kwh_m2 = request.globalstrahlung_kwh_m2
        if request.sonnenstunden is not None:
            existing.sonnenstunden = request.sonnenstunden
        existing.datenquelle = "ha_import"

        # Berechnete Felder aktualisieren
        pv = existing.pv_erzeugung_kwh or 0
        einsp = existing.einspeisung_kwh or 0
        batt_ladung = existing.batterie_ladung_kwh or 0
        batt_entladung = existing.batterie_entladung_kwh or 0

        existing.direktverbrauch_kwh = max(0, pv - einsp - batt_ladung)
        existing.eigenverbrauch_kwh = existing.direktverbrauch_kwh + batt_entladung
        existing.gesamtverbrauch_kwh = existing.eigenverbrauch_kwh + request.netzbezug_kwh

        monatsdaten_id = existing.id
        hinweise.append(f"Monatsdaten {request.monat}/{request.jahr} aktualisiert")
    else:
        # Neu erstellen
        pv = request.pv_erzeugung_kwh or 0
        direktverbrauch = max(0, pv - request.einspeisung_kwh)

        md = Monatsdaten(
            anlage_id=anlage_id,
            jahr=request.jahr,
            monat=request.monat,
            einspeisung_kwh=request.einspeisung_kwh,
            netzbezug_kwh=request.netzbezug_kwh,
            pv_erzeugung_kwh=request.pv_erzeugung_kwh,
            direktverbrauch_kwh=direktverbrauch,
            eigenverbrauch_kwh=direktverbrauch,
            gesamtverbrauch_kwh=direktverbrauch + request.netzbezug_kwh,
            globalstrahlung_kwh_m2=request.globalstrahlung_kwh_m2,
            sonnenstunden=request.sonnenstunden,
            datenquelle="ha_import",
        )
        db.add(md)
        await db.flush()
        monatsdaten_id = md.id
        hinweise.append(f"Monatsdaten {request.monat}/{request.jahr} erstellt")

    # Investitions-Monatsdaten importieren
    if request.investitionen:
        for inv_id_str, daten in request.investitionen.items():
            try:
                inv_id = int(inv_id_str)

                # Investition prüfen
                result = await db.execute(
                    select(Investition)
                    .where(Investition.id == inv_id)
                    .where(Investition.anlage_id == anlage_id)
                )
                inv = result.scalar_one_or_none()

                if not inv:
                    fehler.append(f"Investition {inv_id} nicht gefunden")
                    continue

                # Existierende InvestitionMonatsdaten prüfen
                result = await db.execute(
                    select(InvestitionMonatsdaten)
                    .where(InvestitionMonatsdaten.investition_id == inv_id)
                    .where(InvestitionMonatsdaten.jahr == request.jahr)
                    .where(InvestitionMonatsdaten.monat == request.monat)
                )
                existing_imd = result.scalar_one_or_none()

                if existing_imd:
                    # Merge mit existierenden Daten
                    existing_imd.verbrauch_daten = {**existing_imd.verbrauch_daten, **daten}
                else:
                    # Neu erstellen
                    imd = InvestitionMonatsdaten(
                        investition_id=inv_id,
                        jahr=request.jahr,
                        monat=request.monat,
                        verbrauch_daten=daten,
                    )
                    db.add(imd)

                investitionen_count += 1

            except ValueError as e:
                fehler.append(f"Ungültige Investitions-ID: {inv_id_str}")
            except Exception as e:
                fehler.append(f"Fehler bei Investition {inv_id_str}: {str(e)}")

    await db.commit()

    logger.info(
        f"HA-Import für Anlage {anlage_id}: {request.monat}/{request.jahr} - "
        f"{investitionen_count} Investitionen importiert"
    )

    return ImportResult(
        erfolg=len(fehler) == 0,
        monatsdaten_id=monatsdaten_id,
        investitionen_importiert=investitionen_count,
        fehler=fehler,
        hinweise=hinweise,
    )
