"""
HA Statistics API Routes

Endpoints für den Zugriff auf Home Assistant Langzeitstatistiken.

Ermöglicht:
- Monatswerte für einen bestimmten Monat abrufen
- Alle verfügbaren Monate ermitteln
- Bulk-Import aller historischen Monatswerte
- MQTT-Startwerte initialisieren
"""

from datetime import date
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.models.anlage import Anlage
from backend.services.ha_statistics_service import (
    get_ha_statistics_service,
    MonatswertResponse,
    AlleMonateResponse,
    SensorMonatswert,
)

router = APIRouter()


# =============================================================================
# Response Models
# =============================================================================

class MappedMonatswert(BaseModel):
    """Monatswert mit EEDC-Feld-Zuordnung."""
    feld: str
    feld_label: str
    sensor_id: str
    start_wert: float
    end_wert: float
    differenz: float
    einheit: str = "kWh"


class AnlagenMonatswertResponse(BaseModel):
    """Monatswerte für eine Anlage mit Feld-Zuordnung."""
    anlage_id: int
    anlage_name: str
    jahr: int
    monat: int
    monat_name: str
    basis: list[MappedMonatswert]
    investitionen: dict[str, list[MappedMonatswert]]  # investition_id -> felder


class VerfuegbareMonate(BaseModel):
    """Verfügbare Monate für eine Anlage."""
    anlage_id: int
    anlage_name: str
    erstes_datum: date
    letztes_datum: date
    anzahl_monate: int
    monate: list[dict]  # [{"jahr": 2024, "monat": 10, "monat_name": "Oktober"}, ...]


class StatusResponse(BaseModel):
    """Status der HA-Statistics-Integration."""
    verfuegbar: bool
    db_pfad: Optional[str]
    hinweis: str


# =============================================================================
# Feld-Labels für bessere Lesbarkeit
# =============================================================================

FELD_LABELS = {
    # Basis
    "einspeisung": "Einspeisung",
    "netzbezug": "Netzbezug",
    "pv_gesamt": "PV Erzeugung Gesamt",
    # PV-Module
    "pv_erzeugung_kwh": "PV Erzeugung",
    # Speicher
    "ladung_kwh": "Ladung",
    "entladung_kwh": "Entladung",
    "ladung_netz_kwh": "Ladung aus Netz",
    # E-Auto
    "ladung_pv_kwh": "Ladung PV",
    "km_gefahren": "Kilometer",
    "v2h_entladung_kwh": "V2H Entladung",
    # Wärmepumpe
    "stromverbrauch_kwh": "Stromverbrauch",
    "heizenergie_kwh": "Heizenergie",
    "warmwasser_kwh": "Warmwasser",
}


# =============================================================================
# Helper Functions
# =============================================================================

async def get_anlage_with_mapping(db: AsyncSession, anlage_id: int) -> Anlage:
    """Holt Anlage und prüft ob sensor_mapping vorhanden."""
    result = await db.execute(select(Anlage).where(Anlage.id == anlage_id))
    anlage = result.scalar_one_or_none()

    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")

    if not anlage.sensor_mapping:
        raise HTTPException(
            status_code=400,
            detail="Keine Sensor-Zuordnung konfiguriert. Bitte zuerst Sensoren zuordnen."
        )

    return anlage


def extract_sensor_ids_from_mapping(sensor_mapping: dict) -> list[str]:
    """Extrahiert alle sensor_ids aus dem Mapping."""
    sensor_ids = []

    # Basis-Sensoren
    basis = sensor_mapping.get("basis", {})
    for feld, config in basis.items():
        if config and config.get("strategie") == "sensor" and config.get("sensor_id"):
            sensor_ids.append(config["sensor_id"])

    # Investitions-Sensoren
    investitionen = sensor_mapping.get("investitionen", {})
    for inv_id, inv_config in investitionen.items():
        felder = inv_config.get("felder", {})
        for feld, config in felder.items():
            if config and config.get("strategie") == "sensor" and config.get("sensor_id"):
                sensor_ids.append(config["sensor_id"])

    return sensor_ids


def map_sensor_values_to_fields(
    sensor_mapping: dict,
    sensoren: list[SensorMonatswert]
) -> tuple[list[MappedMonatswert], dict[str, list[MappedMonatswert]]]:
    """
    Ordnet Sensorwerte den EEDC-Feldern zu.

    Returns:
        Tuple von (basis_felder, investitions_felder)
    """
    # Sensor-Werte als Dict für schnellen Zugriff
    sensor_values = {s.sensor_id: s for s in sensoren}

    basis_felder: list[MappedMonatswert] = []
    inv_felder: dict[str, list[MappedMonatswert]] = {}

    # Basis-Felder
    basis = sensor_mapping.get("basis", {})
    for feld, config in basis.items():
        if config and config.get("strategie") == "sensor":
            sensor_id = config.get("sensor_id")
            if sensor_id and sensor_id in sensor_values:
                sv = sensor_values[sensor_id]
                basis_felder.append(MappedMonatswert(
                    feld=feld,
                    feld_label=FELD_LABELS.get(feld, feld),
                    sensor_id=sensor_id,
                    start_wert=sv.start_wert,
                    end_wert=sv.end_wert,
                    differenz=sv.differenz,
                    einheit=sv.einheit
                ))

    # Investitions-Felder
    investitionen = sensor_mapping.get("investitionen", {})
    for inv_id, inv_config in investitionen.items():
        felder = inv_config.get("felder", {})
        inv_felder[inv_id] = []

        for feld, config in felder.items():
            if config and config.get("strategie") == "sensor":
                sensor_id = config.get("sensor_id")
                if sensor_id and sensor_id in sensor_values:
                    sv = sensor_values[sensor_id]
                    inv_felder[inv_id].append(MappedMonatswert(
                        feld=feld,
                        feld_label=FELD_LABELS.get(feld, feld),
                        sensor_id=sensor_id,
                        start_wert=sv.start_wert,
                        end_wert=sv.end_wert,
                        differenz=sv.differenz,
                        einheit=sv.einheit
                    ))

    return basis_felder, inv_felder


# =============================================================================
# Endpoints
# =============================================================================

@router.get("/status", response_model=StatusResponse)
async def get_ha_statistics_status():
    """
    Prüft ob HA-Statistik-Abfrage verfügbar ist.

    Returns:
        Status der Integration
    """
    service = get_ha_statistics_service()

    if service.is_available:
        return StatusResponse(
            verfuegbar=True,
            db_pfad=str(service.db_path),
            hinweis="HA-Datenbank verfügbar. Statistik-Abfragen möglich."
        )
    else:
        return StatusResponse(
            verfuegbar=False,
            db_pfad=None,
            hinweis="HA-Datenbank nicht gefunden. Nur im HA-Addon verfügbar."
        )


@router.get("/monatswerte/{anlage_id}/{jahr}/{monat}", response_model=AnlagenMonatswertResponse)
async def get_monatswerte(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Holt Monatswerte für einen bestimmten Monat aus HA-Statistiken.

    Args:
        anlage_id: ID der Anlage
        jahr: Jahr (z.B. 2024)
        monat: Monat (1-12)

    Returns:
        Monatswerte für alle gemappten Sensoren
    """
    if monat < 1 or monat > 12:
        raise HTTPException(status_code=400, detail="Monat muss zwischen 1 und 12 liegen")

    service = get_ha_statistics_service()
    if not service.is_available:
        raise HTTPException(
            status_code=503,
            detail="HA-Datenbank nicht verfügbar. Diese Funktion ist nur im HA-Addon nutzbar."
        )

    anlage = await get_anlage_with_mapping(db, anlage_id)
    sensor_ids = extract_sensor_ids_from_mapping(anlage.sensor_mapping)

    if not sensor_ids:
        raise HTTPException(
            status_code=400,
            detail="Keine Sensor-Zuordnungen mit Strategie 'sensor' gefunden."
        )

    # Werte aus HA-DB holen
    try:
        response = service.get_monatswerte(sensor_ids, jahr, monat)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler bei DB-Abfrage: {e}")

    # Auf EEDC-Felder mappen
    basis_felder, inv_felder = map_sensor_values_to_fields(
        anlage.sensor_mapping,
        response.sensoren
    )

    return AnlagenMonatswertResponse(
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        jahr=jahr,
        monat=monat,
        monat_name=response.monat_name,
        basis=basis_felder,
        investitionen=inv_felder
    )


@router.get("/verfuegbare-monate/{anlage_id}", response_model=VerfuegbareMonate)
async def get_verfuegbare_monate(
    anlage_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Ermittelt alle Monate mit verfügbaren HA-Statistik-Daten.

    Args:
        anlage_id: ID der Anlage

    Returns:
        Liste aller Monate mit Daten
    """
    service = get_ha_statistics_service()
    if not service.is_available:
        raise HTTPException(
            status_code=503,
            detail="HA-Datenbank nicht verfügbar. Diese Funktion ist nur im HA-Addon nutzbar."
        )

    anlage = await get_anlage_with_mapping(db, anlage_id)
    sensor_ids = extract_sensor_ids_from_mapping(anlage.sensor_mapping)

    if not sensor_ids:
        raise HTTPException(
            status_code=400,
            detail="Keine Sensor-Zuordnungen mit Strategie 'sensor' gefunden."
        )

    try:
        response = service.get_verfuegbare_monate(sensor_ids)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler bei DB-Abfrage: {e}")

    return VerfuegbareMonate(
        anlage_id=anlage.id,
        anlage_name=anlage.anlagenname,
        erstes_datum=response.erstes_datum,
        letztes_datum=response.letztes_datum,
        anzahl_monate=response.anzahl_monate,
        monate=[
            {
                "jahr": m.jahr,
                "monat": m.monat,
                "monat_name": m.monat_name
            }
            for m in response.monate
        ]
    )


@router.get("/alle-monatswerte/{anlage_id}", response_model=list[AnlagenMonatswertResponse])
async def get_alle_monatswerte(
    anlage_id: int,
    ab_jahr: Optional[int] = Query(None, description="Nur Monate ab diesem Jahr"),
    ab_monat: Optional[int] = Query(None, description="Nur Monate ab diesem Monat (mit ab_jahr)"),
    db: AsyncSession = Depends(get_db)
):
    """
    Holt alle verfügbaren Monatswerte aus HA-Statistiken.

    Ideal für:
    - Initialbefüllung bei neuer Installation
    - Nachträgliche Korrektur fehlender Monate
    - Bulk-Import historischer Daten

    Args:
        anlage_id: ID der Anlage
        ab_jahr: Optional - nur Monate ab diesem Jahr
        ab_monat: Optional - nur Monate ab diesem Monat (erfordert ab_jahr)

    Returns:
        Liste aller Monatswerte
    """
    service = get_ha_statistics_service()
    if not service.is_available:
        raise HTTPException(
            status_code=503,
            detail="HA-Datenbank nicht verfügbar. Diese Funktion ist nur im HA-Addon nutzbar."
        )

    anlage = await get_anlage_with_mapping(db, anlage_id)
    sensor_ids = extract_sensor_ids_from_mapping(anlage.sensor_mapping)

    if not sensor_ids:
        raise HTTPException(
            status_code=400,
            detail="Keine Sensor-Zuordnungen mit Strategie 'sensor' gefunden."
        )

    # Ab-Datum berechnen
    ab_datum = None
    if ab_jahr:
        ab_datum = date(ab_jahr, ab_monat or 1, 1)

    try:
        raw_responses = service.get_alle_monatswerte(sensor_ids, ab_datum)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler bei DB-Abfrage: {e}")

    # Auf EEDC-Felder mappen
    ergebnisse = []
    for raw in raw_responses:
        basis_felder, inv_felder = map_sensor_values_to_fields(
            anlage.sensor_mapping,
            raw.sensoren
        )

        ergebnisse.append(AnlagenMonatswertResponse(
            anlage_id=anlage.id,
            anlage_name=anlage.anlagenname,
            jahr=raw.jahr,
            monat=raw.monat,
            monat_name=raw.monat_name,
            basis=basis_felder,
            investitionen=inv_felder
        ))

    return ergebnisse


@router.get("/monatsanfang/{anlage_id}/{jahr}/{monat}")
async def get_monatsanfang_werte(
    anlage_id: int,
    jahr: int,
    monat: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Holt die Zählerstände am Monatsanfang.

    Nützlich für die Initialisierung der MQTT-Startwerte.

    Args:
        anlage_id: ID der Anlage
        jahr: Jahr
        monat: Monat (1-12)

    Returns:
        Dict mit Zählerständen pro Sensor
    """
    if monat < 1 or monat > 12:
        raise HTTPException(status_code=400, detail="Monat muss zwischen 1 und 12 liegen")

    service = get_ha_statistics_service()
    if not service.is_available:
        raise HTTPException(
            status_code=503,
            detail="HA-Datenbank nicht verfügbar. Diese Funktion ist nur im HA-Addon nutzbar."
        )

    anlage = await get_anlage_with_mapping(db, anlage_id)
    sensor_ids = extract_sensor_ids_from_mapping(anlage.sensor_mapping)

    startwerte = {}
    for sensor_id in sensor_ids:
        wert = service.get_monatsanfang_wert(sensor_id, jahr, monat)
        if wert is not None:
            startwerte[sensor_id] = wert

    return {
        "anlage_id": anlage.id,
        "anlage_name": anlage.anlagenname,
        "jahr": jahr,
        "monat": monat,
        "startwerte": startwerte
    }
