"""
Sensor-Mapping API Routes

Ermöglicht die Zuordnung von Home Assistant Sensoren zu EEDC-Feldern.
Das Mapping wird in der Anlage als JSON gespeichert und für MQTT Auto-Discovery verwendet.
"""

from enum import Enum
from typing import Optional, Any
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
import httpx

from backend.core.database import get_session
from backend.core.config import settings
from backend.models.anlage import Anlage
from backend.models.investition import Investition


# =============================================================================
# Enums und Schemas
# =============================================================================

class StrategieTyp(str, Enum):
    """Verfügbare Schätzungsstrategien für Feldwerte."""
    SENSOR = "sensor"               # Direkter HA-Sensor
    KWP_VERTEILUNG = "kwp_verteilung"  # Anteilig nach kWp
    EV_QUOTE = "ev_quote"           # Nach Eigenverbrauchsquote
    COP_BERECHNUNG = "cop_berechnung"  # COP × Stromverbrauch
    MANUELL = "manuell"             # Manuelle Eingabe im Wizard
    KEINE = "keine"                 # Nicht erfassen


class FeldMapping(BaseModel):
    """Mapping für ein einzelnes Feld."""
    strategie: StrategieTyp
    sensor_id: Optional[str] = None  # Bei strategie=sensor
    parameter: Optional[dict[str, Any]] = None  # Zusätzliche Parameter

    class Config:
        use_enum_values = True


class BasisMapping(BaseModel):
    """Mapping für die Basis-Sensoren (Zähler)."""
    einspeisung: Optional[FeldMapping] = None
    netzbezug: Optional[FeldMapping] = None
    pv_gesamt: Optional[FeldMapping] = None  # Optional, für kWp-Verteilung


class InvestitionFelder(BaseModel):
    """Felder-Mapping für eine Investition."""
    felder: dict[str, FeldMapping]


class SensorMappingRequest(BaseModel):
    """Request zum Speichern des Sensor-Mappings."""
    basis: BasisMapping
    investitionen: dict[str, InvestitionFelder] = Field(
        default_factory=dict,
        description="Key = Investition-ID als String"
    )


class InvestitionInfo(BaseModel):
    """Informationen zu einer Investition für den Wizard."""
    id: int
    typ: str
    bezeichnung: str
    erwartete_felder: list[str]
    kwp: Optional[float] = None  # Für PV-Module
    cop: Optional[float] = None  # Für Wärmepumpen


class SensorMappingResponse(BaseModel):
    """Response mit aktuellem Mapping und verfügbaren Investitionen."""
    anlage_id: int
    anlage_name: str
    mapping: Optional[dict[str, Any]] = None
    mqtt_setup_complete: bool = False
    mqtt_setup_timestamp: Optional[str] = None
    investitionen: list[InvestitionInfo] = []
    gesamt_kwp: float = 0.0


class HASensorInfo(BaseModel):
    """Home Assistant Sensor für Dropdown-Auswahl."""
    entity_id: str
    friendly_name: Optional[str] = None
    unit: Optional[str] = None
    device_class: Optional[str] = None
    state: Optional[str] = None


class SetupResult(BaseModel):
    """Ergebnis des MQTT-Setup."""
    success: bool
    message: str
    created_sensors: int = 0
    errors: list[str] = []


# =============================================================================
# Erwartete Felder pro Investitionstyp
# =============================================================================

ERWARTETE_FELDER = {
    "pv-module": ["pv_erzeugung_kwh"],
    "speicher": ["ladung_kwh", "entladung_kwh", "ladung_netz_kwh"],
    "waermepumpe": ["stromverbrauch_kwh", "heizenergie_kwh", "warmwasser_kwh"],
    "e-auto": ["ladung_pv_kwh", "ladung_netz_kwh", "km_gefahren", "v2h_entladung_kwh"],
    "wallbox": ["ladung_kwh"],
    "balkonkraftwerk": ["pv_erzeugung_kwh", "eigenverbrauch_kwh"],
}


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


async def _get_anlage(anlage_id: int, session: AsyncSession) -> Anlage:
    """Hilfsfunktion zum Laden einer Anlage."""
    result = await session.execute(
        select(Anlage).where(Anlage.id == anlage_id)
    )
    anlage = result.scalar_one_or_none()
    if not anlage:
        raise HTTPException(status_code=404, detail=f"Anlage {anlage_id} nicht gefunden")
    return anlage


@router.get("/{anlage_id}", response_model=SensorMappingResponse)
async def get_sensor_mapping(anlage_id: int):
    """
    Gibt aktuelles Sensor-Mapping und verfügbare Investitionen zurück.

    Enthält:
    - Aktuelles Mapping (falls vorhanden)
    - Liste aller Investitionen mit erwarteten Feldern
    - MQTT-Setup-Status
    """
    async with get_session() as session:
        anlage = await _get_anlage(anlage_id, session)

        # Investitionen laden
        inv_result = await session.execute(
            select(Investition)
            .where(Investition.anlage_id == anlage_id)
            .order_by(Investition.typ, Investition.bezeichnung)
        )
        investitionen_db = inv_result.scalars().all()

        # Investitions-Infos aufbereiten
        investitionen: list[InvestitionInfo] = []
        gesamt_kwp = 0.0

        for inv in investitionen_db:
            # Erwartete Felder basierend auf Typ
            felder = ERWARTETE_FELDER.get(inv.typ, [])

            # kWp für PV-Module
            kwp = None
            if inv.typ == "pv-module":
                kwp = inv.parameter.get("leistung_kwp") if inv.parameter else None
                if kwp:
                    gesamt_kwp += kwp

            # COP für Wärmepumpen
            cop = None
            if inv.typ == "waermepumpe" and inv.parameter:
                # JAZ oder COP aus Parametern
                cop = inv.parameter.get("jaz") or inv.parameter.get("cop_heizung")

            investitionen.append(InvestitionInfo(
                id=inv.id,
                typ=inv.typ,
                bezeichnung=inv.bezeichnung,
                erwartete_felder=felder,
                kwp=kwp,
                cop=cop,
            ))

        # Mapping aus Anlage extrahieren
        mapping = anlage.sensor_mapping or {}
        mqtt_complete = mapping.get("mqtt_setup_complete", False)
        mqtt_timestamp = mapping.get("mqtt_setup_timestamp")

        return SensorMappingResponse(
            anlage_id=anlage_id,
            anlage_name=anlage.anlagenname,
            mapping=mapping,
            mqtt_setup_complete=mqtt_complete,
            mqtt_setup_timestamp=mqtt_timestamp,
            investitionen=investitionen,
            gesamt_kwp=gesamt_kwp,
        )


@router.get("/{anlage_id}/available-sensors", response_model=list[HASensorInfo])
async def get_available_sensors(
    anlage_id: int,
    filter_energy: bool = True,
):
    """
    Holt verfügbare Sensoren aus Home Assistant für Dropdown-Auswahl.

    Args:
        anlage_id: ID der Anlage (für Validierung)
        filter_energy: Nur Energy-relevante Sensoren anzeigen

    Returns:
        Liste der verfügbaren HA-Sensoren, sortiert nach entity_id
    """
    # Anlage existiert?
    async with get_session() as session:
        await _get_anlage(anlage_id, session)

    if not settings.supervisor_token:
        raise HTTPException(
            status_code=503,
            detail="Keine Verbindung zu Home Assistant (kein Supervisor Token)"
        )

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.ha_api_url}/states",
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                timeout=10.0
            )

            if response.status_code != 200:
                raise HTTPException(status_code=502, detail="Fehler beim Abrufen der HA-States")

            states = response.json()
            sensors: list[HASensorInfo] = []

            for state in states:
                entity_id = state.get("entity_id", "")

                # Nur Sensoren
                if not entity_id.startswith("sensor."):
                    continue

                attrs = state.get("attributes", {})
                device_class = attrs.get("device_class", "")
                unit = attrs.get("unit_of_measurement", "")

                # Filter auf Energy-relevante Sensoren
                if filter_energy:
                    if device_class not in ["energy", "power", "battery", "temperature", "distance"]:
                        if unit not in ["kWh", "Wh", "W", "kW", "km", "°C"]:
                            continue

                sensors.append(HASensorInfo(
                    entity_id=entity_id,
                    friendly_name=attrs.get("friendly_name"),
                    unit=unit or None,
                    device_class=device_class or None,
                    state=state.get("state"),
                ))

            # Nach Entity-ID sortieren
            sensors.sort(key=lambda x: x.entity_id)
            return sensors

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"HA-Verbindungsfehler: {str(e)}")


@router.post("/{anlage_id}", response_model=SetupResult)
async def save_sensor_mapping(
    anlage_id: int,
    mapping: SensorMappingRequest,
):
    """
    Speichert Sensor-Mapping und erstellt MQTT Entities.

    Ablauf:
    1. Validierung der Sensor-IDs (existieren in HA?)
    2. Speichern in Anlage.sensor_mapping
    3. MQTT Discovery für alle Felder mit Strategie "sensor"
    4. Return: Status und Anzahl erstellter Entities

    Note: MQTT-Setup erfolgt in Teil 2 der Implementierung.
    """
    async with get_session() as session:
        anlage = await _get_anlage(anlage_id, session)

        # Mapping in JSON-Struktur konvertieren
        mapping_dict: dict[str, Any] = {
            "basis": {},
            "investitionen": {},
            "mqtt_setup_complete": False,  # Wird in Teil 2 auf True gesetzt
            "mqtt_setup_timestamp": None,
        }

        # Basis-Sensoren
        if mapping.basis.einspeisung:
            mapping_dict["basis"]["einspeisung"] = mapping.basis.einspeisung.model_dump()
        if mapping.basis.netzbezug:
            mapping_dict["basis"]["netzbezug"] = mapping.basis.netzbezug.model_dump()
        if mapping.basis.pv_gesamt:
            mapping_dict["basis"]["pv_gesamt"] = mapping.basis.pv_gesamt.model_dump()

        # Investitionen
        for inv_id, inv_mapping in mapping.investitionen.items():
            mapping_dict["investitionen"][inv_id] = {
                "felder": {
                    feld: fm.model_dump()
                    for feld, fm in inv_mapping.felder.items()
                }
            }

        # Timestamp setzen
        mapping_dict["updated_at"] = datetime.utcnow().isoformat()

        # In Anlage speichern
        anlage.sensor_mapping = mapping_dict
        flag_modified(anlage, "sensor_mapping")

        await session.commit()

        # Zähle konfigurierte Sensoren
        sensor_count = 0
        for basis_field in mapping_dict["basis"].values():
            if isinstance(basis_field, dict) and basis_field.get("strategie") == "sensor":
                sensor_count += 1
        for inv_data in mapping_dict["investitionen"].values():
            if isinstance(inv_data, dict):
                for feld_data in inv_data.get("felder", {}).values():
                    if isinstance(feld_data, dict) and feld_data.get("strategie") == "sensor":
                        sensor_count += 1

        return SetupResult(
            success=True,
            message=f"Sensor-Mapping gespeichert. {sensor_count} Sensor(en) zugeordnet.",
            created_sensors=0,  # MQTT-Setup erfolgt in Teil 2
            errors=[],
        )


@router.delete("/{anlage_id}")
async def delete_sensor_mapping(anlage_id: int):
    """
    Löscht das Sensor-Mapping einer Anlage.

    In Teil 2 werden auch die MQTT Entities entfernt.
    """
    async with get_session() as session:
        anlage = await _get_anlage(anlage_id, session)

        if not anlage.sensor_mapping:
            raise HTTPException(status_code=404, detail="Kein Sensor-Mapping vorhanden")

        # Mapping löschen
        anlage.sensor_mapping = None
        flag_modified(anlage, "sensor_mapping")

        await session.commit()

        return {
            "success": True,
            "message": "Sensor-Mapping gelöscht",
        }


@router.get("/{anlage_id}/status")
async def get_mapping_status(anlage_id: int):
    """
    Gibt den Status des Sensor-Mappings zurück.

    Nützlich für Schnellabfragen ohne komplettes Mapping.
    """
    async with get_session() as session:
        anlage = await _get_anlage(anlage_id, session)

        mapping = anlage.sensor_mapping or {}

        # Zähle konfigurierte Strategien
        sensor_count = 0
        kwp_count = 0
        cop_count = 0
        manuell_count = 0

        def count_strategies(data: dict):
            nonlocal sensor_count, kwp_count, cop_count, manuell_count
            strategie = data.get("strategie")
            if strategie == "sensor":
                sensor_count += 1
            elif strategie == "kwp_verteilung":
                kwp_count += 1
            elif strategie == "cop_berechnung":
                cop_count += 1
            elif strategie == "manuell":
                manuell_count += 1

        # Basis-Felder
        for feld in mapping.get("basis", {}).values():
            if isinstance(feld, dict):
                count_strategies(feld)

        # Investitionen
        for inv_data in mapping.get("investitionen", {}).values():
            if isinstance(inv_data, dict):
                for feld in inv_data.get("felder", {}).values():
                    if isinstance(feld, dict):
                        count_strategies(feld)

        return {
            "configured": bool(mapping),
            "mqtt_setup_complete": mapping.get("mqtt_setup_complete", False),
            "mqtt_setup_timestamp": mapping.get("mqtt_setup_timestamp"),
            "updated_at": mapping.get("updated_at"),
            "counts": {
                "sensor": sensor_count,
                "kwp_verteilung": kwp_count,
                "cop_berechnung": cop_count,
                "manuell": manuell_count,
            }
        }
