"""
Home Assistant Integration API Routes

Endpoints für HA-Sensor-Zugriff und Datenimport.
Erweitert um String-basierte IST-Erfassung für PV-Module.
"""

from typing import Optional
from datetime import datetime, date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from backend.api.deps import get_db
from backend.core.config import settings
from backend.models.investition import Investition, InvestitionTyp
from backend.models.string_monatsdaten import StringMonatsdaten


# =============================================================================
# Pydantic Schemas
# =============================================================================

class HASensor(BaseModel):
    """Ein Home Assistant Sensor."""
    entity_id: str
    friendly_name: Optional[str]
    unit_of_measurement: Optional[str]
    device_class: Optional[str]
    state: Optional[str]


class HASensorMapping(BaseModel):
    """Sensor-Mapping Konfiguration."""
    pv_erzeugung: Optional[str] = None
    einspeisung: Optional[str] = None
    netzbezug: Optional[str] = None
    batterie_ladung: Optional[str] = None
    batterie_entladung: Optional[str] = None


class HAStatisticsRequest(BaseModel):
    """Anfrage für HA Statistiken."""
    sensor_id: str
    start_date: date
    end_date: date
    period: str = "month"  # hour, day, week, month


class HAStatisticsResponse(BaseModel):
    """Statistik-Daten von HA."""
    sensor_id: str
    data: list[dict]


class HAImportResult(BaseModel):
    """Ergebnis des HA-Imports."""
    erfolg: bool
    monate_importiert: int
    fehler: Optional[str] = None


class StringMonatsdatenCreate(BaseModel):
    """String-Monatsdaten erstellen/aktualisieren."""
    investition_id: int
    jahr: int
    monat: int
    pv_erzeugung_kwh: float


class StringMonatsdatenResponse(BaseModel):
    """String-Monatsdaten Response."""
    id: int
    investition_id: int
    investition_bezeichnung: str
    jahr: int
    monat: int
    pv_erzeugung_kwh: float

    class Config:
        from_attributes = True


class StringImportRequest(BaseModel):
    """Anfrage für String-Daten Import aus HA."""
    investition_id: int
    jahr: int
    monat: Optional[int] = None  # None = ganzes Jahr


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.get("/status")
async def get_ha_status():
    """
    Prüft die Verbindung zu Home Assistant.

    Returns:
        dict: Status der HA-Verbindung
    """
    if not settings.supervisor_token:
        return {
            "connected": False,
            "message": "Kein Supervisor Token gefunden. Läuft EEDC als HA Add-on?"
        }

    # Versuche HA API zu erreichen
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.ha_api_url}/",
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                timeout=5.0
            )
            if response.status_code == 200:
                return {
                    "connected": True,
                    "message": "Verbindung zu Home Assistant erfolgreich"
                }
            else:
                return {
                    "connected": False,
                    "message": f"HA API antwortet mit Status {response.status_code}"
                }
    except Exception as e:
        return {
            "connected": False,
            "message": f"Fehler bei HA-Verbindung: {str(e)}"
        }


@router.get("/sensors", response_model=list[HASensor])
async def list_energy_sensors():
    """
    Listet alle Energy-relevanten Sensoren aus Home Assistant auf.

    Returns:
        list[HASensor]: Liste der Sensoren
    """
    if not settings.supervisor_token:
        raise HTTPException(
            status_code=503,
            detail="Keine Verbindung zu Home Assistant (kein Supervisor Token)"
        )

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.ha_api_url}/states",
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                timeout=10.0
            )

            if response.status_code != 200:
                raise HTTPException(status_code=502, detail="Fehler beim Abrufen der HA-States")

            states = response.json()

            # Filtere Energy-relevante Sensoren
            energy_sensors = []
            for state in states:
                attrs = state.get("attributes", {})
                device_class = attrs.get("device_class", "")
                unit = attrs.get("unit_of_measurement", "")

                # Energy-relevante Sensoren finden
                if device_class in ["energy", "power", "battery"] or unit in ["kWh", "Wh", "W", "kW"]:
                    energy_sensors.append(HASensor(
                        entity_id=state["entity_id"],
                        friendly_name=attrs.get("friendly_name"),
                        unit_of_measurement=unit,
                        device_class=device_class,
                        state=state.get("state")
                    ))

            # Nach Entity-ID sortieren
            energy_sensors.sort(key=lambda x: x.entity_id)
            return energy_sensors

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"HA-Verbindungsfehler: {str(e)}")


@router.get("/mapping", response_model=HASensorMapping)
async def get_sensor_mapping():
    """
    Gibt die aktuelle Sensor-Mapping Konfiguration zurück.

    Returns:
        HASensorMapping: Aktuelle Zuordnung
    """
    return HASensorMapping(
        pv_erzeugung=settings.ha_sensor_pv or None,
        einspeisung=settings.ha_sensor_einspeisung or None,
        netzbezug=settings.ha_sensor_netzbezug or None,
        batterie_ladung=settings.ha_sensor_batterie_ladung or None,
        batterie_entladung=settings.ha_sensor_batterie_entladung or None,
    )


@router.post("/statistics", response_model=HAStatisticsResponse)
async def get_sensor_statistics(request: HAStatisticsRequest):
    """
    Holt Statistik-Daten für einen Sensor aus Home Assistant.

    Args:
        request: Sensor-ID und Zeitraum

    Returns:
        HAStatisticsResponse: Statistik-Daten
    """
    if not settings.supervisor_token:
        raise HTTPException(
            status_code=503,
            detail="Keine Verbindung zu Home Assistant"
        )

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            # HA Statistics API
            # Hinweis: Die genaue API kann je nach HA-Version variieren
            start_time = datetime.combine(request.start_date, datetime.min.time())
            end_time = datetime.combine(request.end_date, datetime.max.time())

            response = await client.get(
                f"{settings.ha_api_url}/history/period/{start_time.isoformat()}",
                params={
                    "filter_entity_id": request.sensor_id,
                    "end_time": end_time.isoformat(),
                    "minimal_response": "true",
                    "significant_changes_only": "true",
                },
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                timeout=30.0
            )

            if response.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Fehler beim Abrufen der Statistiken: {response.status_code}"
                )

            data = response.json()

            return HAStatisticsResponse(
                sensor_id=request.sensor_id,
                data=data[0] if data else []
            )

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"HA-Verbindungsfehler: {str(e)}")


@router.post("/import/{anlage_id}", response_model=HAImportResult)
async def import_from_ha(
    anlage_id: int,
    jahr: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Importiert Monatsdaten aus Home Assistant für ein Jahr.

    Verwendet die konfigurierten Sensor-Mappings um Daten aus der
    HA History zu aggregieren.

    Args:
        anlage_id: ID der Anlage
        jahr: Jahr für den Import

    Returns:
        HAImportResult: Ergebnis des Imports
    """
    # TODO: Implementierung des tatsächlichen Imports
    # Dies erfordert:
    # 1. Sensor-Mapping laden
    # 2. Für jeden Monat die HA-Statistiken abrufen
    # 3. Werte aggregieren (sum für kWh)
    # 4. Monatsdaten erstellen/aktualisieren

    return HAImportResult(
        erfolg=False,
        monate_importiert=0,
        fehler="HA-Import noch nicht implementiert. Bitte CSV-Import verwenden."
    )


# =============================================================================
# String-Monatsdaten Endpoints (für SOLL-IST pro PV-Modul)
# =============================================================================

@router.get("/string-sensors")
async def list_string_sensors():
    """
    Listet alle verfügbaren String/MPPT-Sensoren aus Home Assistant auf.

    Filtert nach typischen String-Sensoren von Wechselrichtern
    (Fronius, SMA, Huawei, etc.)

    Returns:
        list[HASensor]: Liste der String-Sensoren
    """
    if not settings.supervisor_token:
        raise HTTPException(
            status_code=503,
            detail="Keine Verbindung zu Home Assistant (kein Supervisor Token)"
        )

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.ha_api_url}/states",
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                timeout=10.0
            )

            if response.status_code != 200:
                raise HTTPException(status_code=502, detail="Fehler beim Abrufen der HA-States")

            states = response.json()

            # Filtere String/MPPT-relevante Sensoren
            string_sensors = []
            string_keywords = [
                "string", "mppt", "dc_power", "dc_energy",
                "pv1", "pv2", "pv3", "pv4",  # Huawei
                "string_1", "string_2", "string_3",  # Fronius
            ]

            for state in states:
                entity_id = state["entity_id"].lower()
                attrs = state.get("attributes", {})
                unit = attrs.get("unit_of_measurement", "")

                # String-relevante Sensoren finden
                is_string_sensor = any(kw in entity_id for kw in string_keywords)
                is_energy_unit = unit in ["kWh", "Wh", "W", "kW"]

                if is_string_sensor and is_energy_unit:
                    string_sensors.append(HASensor(
                        entity_id=state["entity_id"],
                        friendly_name=attrs.get("friendly_name"),
                        unit_of_measurement=unit,
                        device_class=attrs.get("device_class", ""),
                        state=state.get("state")
                    ))

            # Nach Entity-ID sortieren
            string_sensors.sort(key=lambda x: x.entity_id)
            return string_sensors

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"HA-Verbindungsfehler: {str(e)}")


@router.get("/string-monatsdaten/{anlage_id}")
async def get_string_monatsdaten(
    anlage_id: int,
    jahr: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Gibt alle String-Monatsdaten für eine Anlage zurück.

    Args:
        anlage_id: ID der Anlage
        jahr: Optional - Jahr filtern

    Returns:
        list: String-Monatsdaten mit Investitions-Details
    """
    # PV-Module der Anlage laden
    query = (
        select(Investition)
        .where(Investition.anlage_id == anlage_id)
        .where(Investition.typ == InvestitionTyp.PV_MODULE.value)
        .where(Investition.aktiv == True)
    )
    result = await db.execute(query)
    pv_module = {inv.id: inv for inv in result.scalars().all()}

    if not pv_module:
        return []

    # String-Monatsdaten laden
    query = select(StringMonatsdaten).where(
        StringMonatsdaten.investition_id.in_(pv_module.keys())
    )
    if jahr:
        query = query.where(StringMonatsdaten.jahr == jahr)

    query = query.order_by(StringMonatsdaten.jahr.desc(), StringMonatsdaten.monat.desc())
    result = await db.execute(query)
    daten = result.scalars().all()

    # Mit Investitions-Details anreichern
    return [
        {
            "id": d.id,
            "investition_id": d.investition_id,
            "investition_bezeichnung": pv_module[d.investition_id].bezeichnung,
            "leistung_kwp": pv_module[d.investition_id].leistung_kwp,
            "ausrichtung": pv_module[d.investition_id].ausrichtung,
            "jahr": d.jahr,
            "monat": d.monat,
            "pv_erzeugung_kwh": d.pv_erzeugung_kwh,
        }
        for d in daten
    ]


@router.post("/string-monatsdaten")
async def create_string_monatsdaten(
    data: StringMonatsdatenCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Erstellt oder aktualisiert String-Monatsdaten.

    Args:
        data: String-Monatsdaten

    Returns:
        dict: Erstellte/aktualisierte Daten
    """
    # Prüfe ob Investition existiert und ein PV-Modul ist
    result = await db.execute(
        select(Investition).where(Investition.id == data.investition_id)
    )
    investition = result.scalar_one_or_none()

    if not investition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investition {data.investition_id} nicht gefunden"
        )

    if investition.typ != InvestitionTyp.PV_MODULE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur PV-Module können String-Monatsdaten haben"
        )

    # Prüfe ob Eintrag bereits existiert
    result = await db.execute(
        select(StringMonatsdaten)
        .where(StringMonatsdaten.investition_id == data.investition_id)
        .where(StringMonatsdaten.jahr == data.jahr)
        .where(StringMonatsdaten.monat == data.monat)
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Update
        existing.pv_erzeugung_kwh = data.pv_erzeugung_kwh
        existing.updated_at = datetime.utcnow()
        await db.flush()
        await db.refresh(existing)
        return {
            "id": existing.id,
            "investition_id": existing.investition_id,
            "jahr": existing.jahr,
            "monat": existing.monat,
            "pv_erzeugung_kwh": existing.pv_erzeugung_kwh,
            "updated": True
        }
    else:
        # Create
        new_entry = StringMonatsdaten(
            investition_id=data.investition_id,
            jahr=data.jahr,
            monat=data.monat,
            pv_erzeugung_kwh=data.pv_erzeugung_kwh
        )
        db.add(new_entry)
        await db.flush()
        await db.refresh(new_entry)
        return {
            "id": new_entry.id,
            "investition_id": new_entry.investition_id,
            "jahr": new_entry.jahr,
            "monat": new_entry.monat,
            "pv_erzeugung_kwh": new_entry.pv_erzeugung_kwh,
            "updated": False
        }


@router.delete("/string-monatsdaten/{id}")
async def delete_string_monatsdaten(
    id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Löscht einen String-Monatsdaten Eintrag.

    Args:
        id: ID des Eintrags

    Returns:
        dict: Bestätigung
    """
    result = await db.execute(
        select(StringMonatsdaten).where(StringMonatsdaten.id == id)
    )
    entry = result.scalar_one_or_none()

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"String-Monatsdaten {id} nicht gefunden"
        )

    await db.delete(entry)
    return {"message": "Gelöscht", "id": id}


@router.post("/string-monatsdaten/import")
async def import_string_from_ha(
    request: StringImportRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Importiert String-Monatsdaten aus Home Assistant.

    Verwendet die ha_entity_id des PV-Moduls um die HA-Statistiken
    abzurufen und zu aggregieren.

    Args:
        request: Import-Anfrage mit Investition und Zeitraum

    Returns:
        HAImportResult: Ergebnis des Imports
    """
    # PV-Modul laden
    result = await db.execute(
        select(Investition).where(Investition.id == request.investition_id)
    )
    investition = result.scalar_one_or_none()

    if not investition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investition {request.investition_id} nicht gefunden"
        )

    if investition.typ != InvestitionTyp.PV_MODULE.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur PV-Module können String-Daten importieren"
        )

    if not investition.ha_entity_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="PV-Modul hat keine Home Assistant Entity-ID zugewiesen"
        )

    if not settings.supervisor_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Keine Verbindung zu Home Assistant"
        )

    # TODO: HA Statistics API für monatliche Aggregation implementieren
    # Dies erfordert Zugriff auf die HA Long-Term Statistics
    # Für jetzt: Platzhalter-Antwort

    return HAImportResult(
        erfolg=False,
        monate_importiert=0,
        fehler="Automatischer HA-Import noch nicht implementiert. Bitte String-Daten manuell erfassen."
    )
