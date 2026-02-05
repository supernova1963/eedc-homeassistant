"""
Home Assistant Integration API Routes

Endpoints für HA-Sensor-Zugriff und Datenimport.
Erweitert um String-basierte IST-Erfassung für PV-Module.
"""

from typing import Optional
from datetime import datetime, date
from calendar import monthrange
import re
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
import httpx

from backend.api.deps import get_db
from backend.core.config import settings
from backend.models.investition import Investition, InvestitionTyp
from backend.models.string_monatsdaten import StringMonatsdaten
from backend.models.monatsdaten import Monatsdaten
from backend.models.anlage import Anlage

# WebSocket für Long-Term Statistics (optional, derzeit experimentell)
try:
    from backend.services.ha_websocket import HAWebSocketClient
    HAS_WEBSOCKET = True
except ImportError:
    HAS_WEBSOCKET = False


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
# Discovery Schemas
# =============================================================================

class DiscoveredSensor(BaseModel):
    """Ein entdeckter HA-Sensor mit Mapping-Vorschlag."""
    entity_id: str
    friendly_name: Optional[str] = None
    unit_of_measurement: Optional[str] = None
    device_class: Optional[str] = None
    state_class: Optional[str] = None
    current_state: Optional[str] = None
    suggested_mapping: Optional[str] = None  # pv_erzeugung, einspeisung, etc.
    confidence: int = 0  # 0-100


class DiscoveredDevice(BaseModel):
    """Ein entdecktes HA-Gerät mit Investitions-Vorschlag."""
    id: str                           # z.B. "evcc_loadpoint_1"
    integration: str                  # sma, evcc, smart, wallbox
    device_type: str                  # inverter, ev, wallbox, battery
    suggested_investition_typ: Optional[str] = None  # e-auto, wallbox, speicher, etc.
    name: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    sensors: list[DiscoveredSensor] = []
    suggested_parameters: dict = {}   # Vorgeschlagene Parameter für Investition
    confidence: int = 0               # 0-100
    priority: int = 0                 # Höher = bevorzugt (evcc > wallbox)
    already_configured: bool = False  # Bereits als Investition vorhanden


class SensorMappingSuggestions(BaseModel):
    """Sensor-Mapping Vorschläge für alle 5 Felder."""
    pv_erzeugung: list[DiscoveredSensor] = []
    einspeisung: list[DiscoveredSensor] = []
    netzbezug: list[DiscoveredSensor] = []
    batterie_ladung: list[DiscoveredSensor] = []
    batterie_entladung: list[DiscoveredSensor] = []


class DiscoveryResult(BaseModel):
    """Gesamtergebnis der Auto-Discovery."""
    ha_connected: bool
    devices: list[DiscoveredDevice] = []
    sensor_mappings: SensorMappingSuggestions = SensorMappingSuggestions()
    warnings: list[str] = []
    current_mappings: HASensorMapping = HASensorMapping()


class MonthlyStatistic(BaseModel):
    """Monatliche Statistik aus HA."""
    jahr: int
    monat: int
    summe_kwh: float
    hat_daten: bool = True


class HAMonthlyDataRequest(BaseModel):
    """Anfrage für monatliche Daten aus HA Long-Term Statistics."""
    statistic_id: str = Field(..., description="HA Statistik-ID (z.B. sensor:pv_energy_total)")
    start_jahr: int
    start_monat: int = 1
    end_jahr: Optional[int] = None
    end_monat: Optional[int] = None


class HAMonthlyDataResponse(BaseModel):
    """Monatliche Statistik-Daten aus HA."""
    statistic_id: str
    monate: list[MonthlyStatistic]
    hinweis: Optional[str] = None


class HAImportMonatsdatenRequest(BaseModel):
    """Anfrage für Import von Monatsdaten aus HA."""
    anlage_id: int
    jahr: int
    monat: Optional[int] = None  # None = ganzes Jahr
    ueberschreiben: bool = False  # Existierende Daten überschreiben?


# =============================================================================
# Router
# =============================================================================

router = APIRouter()


@router.get("/status")
async def get_ha_status():
    """
    Prüft die Verbindung zu Home Assistant (REST + WebSocket).

    Returns:
        dict: Status der HA-Verbindung
    """
    if not settings.supervisor_token:
        return {
            "connected": False,
            "rest_api": False,
            "websocket": False,
            "message": "Kein Supervisor Token gefunden. Läuft EEDC als HA Add-on?"
        }

    result = {
        "connected": False,
        "rest_api": False,
        "websocket": False,
        "ha_version": None,
        "message": ""
    }

    # REST API testen
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.ha_api_url}/",
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                timeout=5.0
            )
            if response.status_code == 200:
                result["rest_api"] = True
                data = response.json()
                result["ha_version"] = data.get("version")
    except Exception as e:
        result["message"] = f"REST API Fehler: {str(e)}"

    # WebSocket testen (optional)
    if HAS_WEBSOCKET:
        try:
            ws_client = HAWebSocketClient()
            ws_status = await ws_client.test_connection()
            result["websocket"] = ws_status.get("connected", False)
            if ws_status.get("ha_version"):
                result["ha_version"] = ws_status["ha_version"]
            if not result["websocket"] and ws_status.get("error"):
                result["message"] += f" WebSocket: {ws_status['error']}"
        except Exception as e:
            result["message"] += f" WebSocket Fehler: {str(e)}"

    # Gesamtstatus
    result["connected"] = result["rest_api"] or result["websocket"]
    if result["connected"] and not result["message"]:
        if result["rest_api"] and result["websocket"]:
            result["message"] = "REST API und WebSocket verbunden"
        elif result["rest_api"]:
            result["message"] = "REST API verbunden, WebSocket nicht verfügbar"
        else:
            result["message"] = "WebSocket verbunden, REST API nicht verfügbar"

    return result


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


# =============================================================================
# Long-Term Statistics API (Monatswerte aus Zählern)
# =============================================================================

async def _get_ha_statistics_monthly(
    statistic_id: str,
    start_date: date,
    end_date: date
) -> list[dict]:
    """
    Holt monatliche Statistiken aus HA.

    Verwendet die History API für kurzzeitige Daten (~10 Tage).
    Für ältere Daten (Long-Term Statistics) ist WebSocket erforderlich,
    was derzeit noch nicht zuverlässig funktioniert.

    Args:
        statistic_id: z.B. "sensor.pv_energy_total"
        start_date: Startdatum
        end_date: Enddatum

    Returns:
        Liste von {start, change} pro Monat
    """
    if not settings.supervisor_token:
        return []

    monthly_data = []

    # History API (für aktuelle Monate mit kurzzeitigen Daten)
    async with httpx.AsyncClient() as client:
        current = date(start_date.year, start_date.month, 1)

        while current <= end_date:
            _, last_day = monthrange(current.year, current.month)
            month_end = date(current.year, current.month, last_day)

            month_start_ts = datetime.combine(current, datetime.min.time()).isoformat()
            month_end_ts = datetime.combine(month_end, datetime.max.time()).isoformat()

            change_value = None

            try:
                response = await client.get(
                    f"{settings.ha_api_url}/history/period/{month_start_ts}",
                    params={
                        "filter_entity_id": statistic_id,
                        "end_time": month_end_ts,
                        "minimal_response": "true",
                        "no_attributes": "true",
                    },
                    headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                    timeout=30.0
                )

                if response.status_code == 200:
                    data = response.json()

                    if data and len(data) > 0 and len(data[0]) > 0:
                        states = data[0]

                        valid_values = []
                        for s in states:
                            try:
                                state_str = s.get("state", "")
                                if state_str not in ("unknown", "unavailable", ""):
                                    val = float(state_str)
                                    if val >= 0:
                                        valid_values.append(val)
                            except (ValueError, TypeError):
                                pass

                        if len(valid_values) >= 2:
                            first_val = valid_values[0]
                            last_val = valid_values[-1]
                            change_value = last_val - first_val

                            if change_value < 0:
                                change_value = 0
                                for i in range(1, len(valid_values)):
                                    diff = valid_values[i] - valid_values[i-1]
                                    if diff > 0:
                                        change_value += diff

            except Exception:
                pass

            if change_value is not None and change_value > 0:
                monthly_data.append({
                    "start": datetime.combine(current, datetime.min.time()).isoformat(),
                    "change": round(change_value, 2)
                })

            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

    return monthly_data


@router.post("/statistics/monthly", response_model=HAMonthlyDataResponse)
async def get_monthly_statistics(request: HAMonthlyDataRequest):
    """
    Holt monatliche Statistiken aus Home Assistant Long-Term Statistics.

    Berechnet Monatswerte aus fortlaufenden Zählern (total_increasing).

    Args:
        request: Statistik-ID und Zeitraum

    Returns:
        HAMonthlyDataResponse: Monatliche Werte
    """
    if not settings.supervisor_token:
        raise HTTPException(
            status_code=503,
            detail="Keine Verbindung zu Home Assistant"
        )

    end_jahr = request.end_jahr or request.start_jahr
    end_monat = request.end_monat or 12

    start_date = date(request.start_jahr, request.start_monat, 1)
    _, last_day = monthrange(end_jahr, end_monat)
    end_date = date(end_jahr, end_monat, last_day)

    try:
        stats = await _get_ha_statistics_monthly(
            request.statistic_id,
            start_date,
            end_date
        )

        monate = []
        for stat in stats:
            # HA gibt "start" als ISO-Timestamp und "change" als Differenz
            start_str = stat.get("start", "")
            change = stat.get("change", 0) or 0

            if start_str:
                try:
                    dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                    monate.append(MonthlyStatistic(
                        jahr=dt.year,
                        monat=dt.month,
                        summe_kwh=round(change, 2),
                        hat_daten=change > 0
                    ))
                except ValueError:
                    pass

        hinweis = None
        if not monate:
            hinweis = "Keine Statistiken verfügbar. Sensor muss state_class 'total_increasing' haben."

        return HAMonthlyDataResponse(
            statistic_id=request.statistic_id,
            monate=monate,
            hinweis=hinweis
        )

    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"HA-Verbindungsfehler: {str(e)}")


@router.post("/import/monatsdaten", response_model=HAImportResult)
async def import_monatsdaten_from_ha(
    request: HAImportMonatsdatenRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Importiert Monatsdaten aus Home Assistant Long-Term Statistics.

    Verwendet die konfigurierten Sensor-Mappings und berechnet
    Monatswerte aus den fortlaufenden Zählern.

    WICHTIG: Existierende manuelle Daten werden NICHT überschrieben,
    es sei denn, ueberschreiben=True ist gesetzt.

    Args:
        request: Anlage-ID, Jahr und Optionen

    Returns:
        HAImportResult: Ergebnis des Imports
    """
    if not settings.supervisor_token:
        return HAImportResult(
            erfolg=False,
            monate_importiert=0,
            fehler="Keine Verbindung zu Home Assistant"
        )

    # Anlage prüfen
    result = await db.execute(select(Anlage).where(Anlage.id == request.anlage_id))
    anlage = result.scalar_one_or_none()
    if not anlage:
        return HAImportResult(
            erfolg=False,
            monate_importiert=0,
            fehler=f"Anlage {request.anlage_id} nicht gefunden"
        )

    # Sensor-Mappings aus Settings
    sensor_mapping = {
        "pv_erzeugung": settings.ha_sensor_pv,
        "einspeisung": settings.ha_sensor_einspeisung,
        "netzbezug": settings.ha_sensor_netzbezug,
        "batterie_ladung": settings.ha_sensor_batterie_ladung,
        "batterie_entladung": settings.ha_sensor_batterie_entladung,
    }

    # Prüfen ob Mappings konfiguriert sind
    configured_sensors = {k: v for k, v in sensor_mapping.items() if v}
    if not configured_sensors:
        return HAImportResult(
            erfolg=False,
            monate_importiert=0,
            fehler="Keine HA-Sensoren konfiguriert. Bitte unter Einstellungen zuweisen."
        )

    # Zeitraum bestimmen
    start_monat = request.monat or 1
    end_monat = request.monat or 12
    start_date = date(request.jahr, start_monat, 1)
    _, last_day = monthrange(request.jahr, end_monat)
    end_date = date(request.jahr, end_monat, last_day)

    # Statistiken für alle konfigurierten Sensoren abrufen
    sensor_data: dict[str, dict[tuple[int, int], float]] = {}

    for field, sensor_id in configured_sensors.items():
        try:
            stats = await _get_ha_statistics_monthly(sensor_id, start_date, end_date)
            sensor_data[field] = {}

            for stat in stats:
                start_str = stat.get("start", "")
                change = stat.get("change", 0) or 0

                if start_str and change > 0:
                    try:
                        dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                        sensor_data[field][(dt.year, dt.month)] = round(change, 2)
                    except ValueError:
                        pass
        except Exception:
            pass

    # Monate importieren
    monate_importiert = 0
    monate_uebersprungen = 0

    for monat in range(start_monat, end_monat + 1):
        key = (request.jahr, monat)

        # Existierende Daten prüfen
        result = await db.execute(
            select(Monatsdaten)
            .where(Monatsdaten.anlage_id == request.anlage_id)
            .where(Monatsdaten.jahr == request.jahr)
            .where(Monatsdaten.monat == monat)
        )
        existing = result.scalar_one_or_none()

        # Daten aus HA sammeln
        ha_daten = {
            "pv_erzeugung_kwh": sensor_data.get("pv_erzeugung", {}).get(key),
            "einspeisung_kwh": sensor_data.get("einspeisung", {}).get(key),
            "netzbezug_kwh": sensor_data.get("netzbezug", {}).get(key),
            "batterie_ladung_kwh": sensor_data.get("batterie_ladung", {}).get(key),
            "batterie_entladung_kwh": sensor_data.get("batterie_entladung", {}).get(key),
        }

        # Prüfen ob HA-Daten vorhanden
        hat_ha_daten = any(v is not None for v in ha_daten.values())
        if not hat_ha_daten:
            continue

        if existing and not request.ueberschreiben:
            # Existierende Daten nicht überschreiben
            monate_uebersprungen += 1
            continue

        if existing:
            # Update nur Felder, die HA-Daten haben
            for field, value in ha_daten.items():
                if value is not None:
                    setattr(existing, field, value)
            existing.datenquelle = "home_assistant"
            existing.updated_at = datetime.utcnow()
        else:
            # Neuen Eintrag erstellen
            new_entry = Monatsdaten(
                anlage_id=request.anlage_id,
                jahr=request.jahr,
                monat=monat,
                pv_erzeugung_kwh=ha_daten.get("pv_erzeugung_kwh") or 0,
                einspeisung_kwh=ha_daten.get("einspeisung_kwh") or 0,
                netzbezug_kwh=ha_daten.get("netzbezug_kwh") or 0,
                batterie_ladung_kwh=ha_daten.get("batterie_ladung_kwh"),
                batterie_entladung_kwh=ha_daten.get("batterie_entladung_kwh"),
                datenquelle="home_assistant"
            )
            db.add(new_entry)

        monate_importiert += 1

    await db.flush()

    fehler = None
    if monate_uebersprungen > 0:
        fehler = f"{monate_uebersprungen} Monate übersprungen (bereits vorhanden). Setze ueberschreiben=true um zu aktualisieren."

    return HAImportResult(
        erfolg=monate_importiert > 0,
        monate_importiert=monate_importiert,
        fehler=fehler
    )


@router.get("/import/preview/{anlage_id}")
async def preview_ha_import(
    anlage_id: int,
    jahr: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Zeigt Vorschau der verfügbaren HA-Daten für Import.

    Hilft dem Nutzer zu sehen, welche Monate aus HA importiert werden können
    und welche bereits manuell erfasst wurden.

    Args:
        anlage_id: ID der Anlage
        jahr: Jahr

    Returns:
        dict: Verfügbare HA-Daten und existierende Monatsdaten
    """
    # Existierende Monatsdaten laden
    result = await db.execute(
        select(Monatsdaten)
        .where(Monatsdaten.anlage_id == anlage_id)
        .where(Monatsdaten.jahr == jahr)
    )
    existierende = {m.monat: m for m in result.scalars().all()}

    # HA-Daten abrufen (wenn verfügbar)
    ha_verfuegbar = {}
    if settings.supervisor_token and settings.ha_sensor_pv:
        try:
            start_date = date(jahr, 1, 1)
            end_date = date(jahr, 12, 31)
            stats = await _get_ha_statistics_monthly(
                settings.ha_sensor_pv,
                start_date,
                end_date
            )
            for stat in stats:
                start_str = stat.get("start", "")
                change = stat.get("change", 0) or 0
                if start_str:
                    try:
                        dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                        ha_verfuegbar[dt.month] = round(change, 2)
                    except ValueError:
                        pass
        except Exception:
            pass

    # Vorschau erstellen
    monate = []
    for monat in range(1, 13):
        existiert = monat in existierende
        ha_wert = ha_verfuegbar.get(monat)

        monate.append({
            "monat": monat,
            "existiert_in_db": existiert,
            "datenquelle": existierende[monat].datenquelle if existiert else None,
            "pv_erzeugung_db": existierende[monat].pv_erzeugung_kwh if existiert else None,
            "pv_erzeugung_ha": ha_wert,
            "kann_importieren": ha_wert is not None and not existiert,
            "kann_aktualisieren": ha_wert is not None and existiert,
        })

    return {
        "anlage_id": anlage_id,
        "jahr": jahr,
        "ha_verbunden": bool(settings.supervisor_token),
        "sensor_konfiguriert": bool(settings.ha_sensor_pv),
        "monate": monate
    }


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


# =============================================================================
# Auto-Discovery Endpoint
# =============================================================================

# Integration-spezifische Erkennungsmuster
# SMA Sensoren haben das Prefix sensor.sn_SERIENNUMMER_ (z.B. sensor.sn_3012412676_pv_gen_meter)
INTEGRATION_PATTERNS = {
    "sma": {
        # SMA Sensoren beginnen mit sensor.sn_ gefolgt von Seriennummer
        "prefix_pattern": r"^sensor\.sn_\d+_",
        "device_type": "inverter",
        # Sensor-Mappings für Monatsdaten
        "pv_erzeugung": ["pv_gen_meter", "pv_gen", "total_yield"],
        "einspeisung": ["metering_total_yield"],
        "netzbezug": ["metering_total_absorbed"],
        "batterie_ladung": ["battery_charge_total"],
        "batterie_entladung": ["battery_discharge_total"],
        # Geräteerkennung
        "inverter_indicators": ["inverter_power_limit", "inverter_condition", "pv_power"],
        "battery_indicators": ["battery_soc", "battery_charge_total", "battery_discharge_total"],
    },
    "evcc": {
        "prefix": "sensor.evcc_",
        "device_types": {
            "loadpoint": "wallbox",
            "vehicle": "ev",
            "site": "site",
        },
        "pv_erzeugung": ["site_pv_power", "pv_power"],
        "einspeisung": ["grid_export"],
        "netzbezug": ["grid_power", "grid_import"],
    },
    "smart": {
        "prefix": "sensor.smart_",
        "device_type": "ev",
        "ev_indicators": ["battery_level", "range", "charging", "soc", "odometer"],
    },
    "wallbox": {
        "prefix": "sensor.wallbox_",
        "device_type": "wallbox",
        "wallbox_indicators": ["charging_power", "charged_energy", "charging_status"],
    },
}


def _is_sma_sensor(entity_id: str) -> bool:
    """Prüft ob ein Sensor ein SMA-Sensor ist (sensor.sn_NUMMER_...)."""
    return bool(re.match(r'^sensor\.sn_\d+_', entity_id.lower()))


def _classify_sensor(entity_id: str, attrs: dict) -> tuple[str, str | None, int]:
    """
    Klassifiziert einen Sensor nach Integration und Mapping-Typ.

    Returns:
        tuple: (integration, suggested_mapping, confidence)
    """
    entity_lower = entity_id.lower()
    friendly_name = (attrs.get("friendly_name") or "").lower()
    device_class = attrs.get("device_class", "")
    state_class = attrs.get("state_class", "")
    unit = attrs.get("unit_of_measurement", "")

    # SMA Sensoren (sensor.sn_NUMMER_...)
    if _is_sma_sensor(entity_id):
        patterns = INTEGRATION_PATTERNS["sma"]

        # Extrahiere den Sensor-Namen nach der Seriennummer (z.B. "pv_gen_meter" aus "sensor.sn_3012412676_pv_gen_meter")
        match = re.match(r'^sensor\.sn_\d+_(.+)$', entity_lower)
        sensor_name = match.group(1) if match else ""

        for mapping_type in ["pv_erzeugung", "einspeisung", "netzbezug", "batterie_ladung", "batterie_entladung"]:
            keywords = patterns.get(mapping_type, [])
            for kw in keywords:
                # Exakter Match auf Sensor-Namen
                if sensor_name == kw or sensor_name.startswith(kw):
                    # Höhere Confidence für state_class: total_increasing und kWh
                    if state_class == "total_increasing" and unit == "kWh":
                        return ("sma", mapping_type, 95)
                    elif state_class == "total_increasing":
                        return ("sma", mapping_type, 90)
                    else:
                        return ("sma", mapping_type, 70)
        return ("sma", None, 50)

    # evcc Sensoren
    if entity_lower.startswith("sensor.evcc_"):
        patterns = INTEGRATION_PATTERNS["evcc"]
        for mapping_type in ["pv_erzeugung", "einspeisung", "netzbezug"]:
            keywords = patterns.get(mapping_type, [])
            for kw in keywords:
                if kw in entity_lower or kw in friendly_name:
                    conf = 85 if state_class == "total_increasing" else 65
                    return ("evcc", mapping_type, conf)
        return ("evcc", None, 50)

    # Smart Sensoren (E-Auto)
    if entity_lower.startswith("sensor.smart_"):
        return ("smart", None, 50)

    # Wallbox Sensoren
    if entity_lower.startswith("sensor.wallbox_"):
        return ("wallbox", None, 50)

    # Generische Energy-Sensoren
    if device_class == "energy" and unit in ["kWh", "Wh"]:
        # Versuche aus Namen zu erkennen
        if any(kw in entity_lower or kw in friendly_name for kw in ["pv", "solar", "erzeugung"]):
            return ("generic", "pv_erzeugung", 60)
        if any(kw in entity_lower or kw in friendly_name for kw in ["export", "einspeisung", "feed"]):
            return ("generic", "einspeisung", 60)
        if any(kw in entity_lower or kw in friendly_name for kw in ["import", "netzbezug", "grid"]):
            return ("generic", "netzbezug", 60)

    return ("unknown", None, 0)


def _extract_devices_from_sensors(sensors: list[dict]) -> list[DiscoveredDevice]:
    """
    Extrahiert Geräte aus der Sensor-Liste und gruppiert sie.
    """
    devices: dict[str, DiscoveredDevice] = {}

    # Erste Pass: Sammle alle SMA-Sensoren um Geräte zu identifizieren
    sma_sensors: dict[str, list[dict]] = {}  # serial -> sensors
    sma_inverter_power: dict[str, int] = {}  # serial -> power_limit in W
    sma_has_battery: dict[str, bool] = {}    # serial -> has battery

    for sensor in sensors:
        entity_id = sensor["entity_id"]
        entity_lower = entity_id.lower()

        if _is_sma_sensor(entity_id):
            # Extrahiere Seriennummer
            match = re.match(r'^sensor\.sn_(\d+)_(.+)$', entity_lower)
            if match:
                serial = match.group(1)
                sensor_name = match.group(2)

                if serial not in sma_sensors:
                    sma_sensors[serial] = []
                sma_sensors[serial].append(sensor)

                # Prüfe auf Wechselrichter-Leistung
                if sensor_name == "inverter_power_limit":
                    try:
                        power = int(float(sensor.get("state", 0)))
                        sma_inverter_power[serial] = power
                    except (ValueError, TypeError):
                        pass

                # Prüfe auf Batterie
                if "battery" in sensor_name and sensor_name not in ["battery_power_charge_total", "battery_power_discharge_total"]:
                    sma_has_battery[serial] = True

    # Zweite Pass: Erstelle SMA-Geräte
    for serial, serial_sensors in sma_sensors.items():
        # SMA Wechselrichter erstellen
        inverter_power_w = sma_inverter_power.get(serial, 0)
        inverter_power_kw = inverter_power_w / 1000 if inverter_power_w > 0 else None

        device_id = f"sma_inverter_{serial}"
        devices[device_id] = DiscoveredDevice(
            id=device_id,
            integration="sma",
            device_type="inverter",
            suggested_investition_typ="wechselrichter",
            name=f"SMA Wechselrichter (SN: {serial})",
            manufacturer="SMA",
            model=f"SN: {serial}",
            sensors=[],
            suggested_parameters={
                "bezeichnung": f"SMA Wechselrichter",
                "hersteller": "SMA",
                "leistung_kw": inverter_power_kw,
            },
            confidence=90,
            priority=80,
        )

        # Sensoren zum Wechselrichter hinzufügen
        for sensor in serial_sensors:
            entity_id = sensor["entity_id"]
            attrs = sensor.get("attributes", {})
            _, mapping, conf = _classify_sensor(entity_id, attrs)

            devices[device_id].sensors.append(DiscoveredSensor(
                entity_id=entity_id,
                friendly_name=attrs.get("friendly_name"),
                unit_of_measurement=attrs.get("unit_of_measurement"),
                device_class=attrs.get("device_class"),
                state_class=attrs.get("state_class"),
                current_state=sensor.get("state"),
                suggested_mapping=mapping,
                confidence=conf,
            ))

        # Wenn Batterie vorhanden, separates Speicher-Gerät erstellen
        if sma_has_battery.get(serial, False):
            battery_device_id = f"sma_battery_{serial}"
            devices[battery_device_id] = DiscoveredDevice(
                id=battery_device_id,
                integration="sma",
                device_type="battery",
                suggested_investition_typ="speicher",
                name=f"SMA Speicher (SN: {serial})",
                manufacturer="SMA",
                model=f"SN: {serial}",
                sensors=[],
                suggested_parameters={
                    "bezeichnung": f"Batteriespeicher (SMA)",
                    "hersteller": "SMA",
                },
                confidence=85,
                priority=75,
            )

            # Batterie-Sensoren hinzufügen
            for sensor in serial_sensors:
                entity_lower = sensor["entity_id"].lower()
                if "battery" in entity_lower:
                    attrs = sensor.get("attributes", {})
                    devices[battery_device_id].sensors.append(DiscoveredSensor(
                        entity_id=sensor["entity_id"],
                        friendly_name=attrs.get("friendly_name"),
                        unit_of_measurement=attrs.get("unit_of_measurement"),
                        device_class=attrs.get("device_class"),
                        state_class=attrs.get("state_class"),
                        current_state=sensor.get("state"),
                    ))

    # Dritte Pass: Andere Integrationen
    for sensor in sensors:
        entity_id = sensor["entity_id"]
        attrs = sensor.get("attributes", {})
        entity_lower = entity_id.lower()

        # Überspringe SMA-Sensoren (bereits verarbeitet)
        if _is_sma_sensor(entity_id):
            continue

        # evcc Loadpoints (Wallbox) - HÖCHSTE Priorität
        if entity_lower.startswith("sensor.evcc_") and "loadpoint" in entity_lower:
            match = re.search(r'loadpoint[_]?(\d+)?', entity_lower)
            lp_num = match.group(1) if match and match.group(1) else "1"
            device_id = f"evcc_loadpoint_{lp_num}"

            if device_id not in devices:
                devices[device_id] = DiscoveredDevice(
                    id=device_id,
                    integration="evcc",
                    device_type="wallbox",
                    suggested_investition_typ="wallbox",
                    name=f"evcc Wallbox {lp_num}",
                    manufacturer="evcc",
                    sensors=[],
                    suggested_parameters={
                        "bezeichnung": f"Wallbox (evcc LP{lp_num})",
                        "hersteller": "evcc managed",
                    },
                    confidence=95,
                    priority=100,
                )

            devices[device_id].sensors.append(DiscoveredSensor(
                entity_id=entity_id,
                friendly_name=attrs.get("friendly_name"),
                unit_of_measurement=attrs.get("unit_of_measurement"),
                device_class=attrs.get("device_class"),
                state_class=attrs.get("state_class"),
                current_state=sensor.get("state"),
            ))

        # evcc Vehicles (E-Auto) - HÖCHSTE Priorität
        elif entity_lower.startswith("sensor.evcc_") and "vehicle" in entity_lower:
            match = re.search(r'vehicle[_]?(\d+)?', entity_lower)
            v_num = match.group(1) if match and match.group(1) else "1"
            device_id = f"evcc_vehicle_{v_num}"

            if device_id not in devices:
                friendly = attrs.get("friendly_name", "")
                vehicle_name = friendly.split()[0] if friendly else f"Fahrzeug {v_num}"

                devices[device_id] = DiscoveredDevice(
                    id=device_id,
                    integration="evcc",
                    device_type="ev",
                    suggested_investition_typ="e-auto",
                    name=f"evcc {vehicle_name}",
                    manufacturer="evcc",
                    sensors=[],
                    suggested_parameters={
                        "bezeichnung": vehicle_name,
                        "hersteller": "evcc managed",
                    },
                    confidence=95,
                    priority=100,
                )

            devices[device_id].sensors.append(DiscoveredSensor(
                entity_id=entity_id,
                friendly_name=attrs.get("friendly_name"),
                unit_of_measurement=attrs.get("unit_of_measurement"),
                device_class=attrs.get("device_class"),
                state_class=attrs.get("state_class"),
                current_state=sensor.get("state"),
            ))

        # Smart E-Auto
        elif entity_lower.startswith("sensor.smart_"):
            ev_keywords = ["battery", "range", "soc", "charging", "odometer"]
            if any(kw in entity_lower for kw in ev_keywords):
                device_id = "smart_ev"

                if device_id not in devices:
                    devices[device_id] = DiscoveredDevice(
                        id=device_id,
                        integration="smart",
                        device_type="ev",
                        suggested_investition_typ="e-auto",
                        name="Smart #1",
                        manufacturer="Smart",
                        model="#1",
                        sensors=[],
                        suggested_parameters={
                            "bezeichnung": "Smart #1",
                            "hersteller": "Smart",
                            "batterie_kwh": 66.0,
                        },
                        confidence=85,
                        priority=50,
                    )

                devices[device_id].sensors.append(DiscoveredSensor(
                    entity_id=entity_id,
                    friendly_name=attrs.get("friendly_name"),
                    unit_of_measurement=attrs.get("unit_of_measurement"),
                    device_class=attrs.get("device_class"),
                    state_class=attrs.get("state_class"),
                    current_state=sensor.get("state"),
                ))

        # Wallbox Integration
        elif entity_lower.startswith("sensor.wallbox_"):
            device_id = "wallbox_native"

            if device_id not in devices:
                devices[device_id] = DiscoveredDevice(
                    id=device_id,
                    integration="wallbox",
                    device_type="wallbox",
                    suggested_investition_typ="wallbox",
                    name="Wallbox",
                    manufacturer="Wallbox",
                    sensors=[],
                    suggested_parameters={
                        "bezeichnung": "Wallbox",
                        "hersteller": "Wallbox",
                    },
                    confidence=80,
                    priority=30,
                )

            devices[device_id].sensors.append(DiscoveredSensor(
                entity_id=entity_id,
                friendly_name=attrs.get("friendly_name"),
                unit_of_measurement=attrs.get("unit_of_measurement"),
                device_class=attrs.get("device_class"),
                state_class=attrs.get("state_class"),
                current_state=sensor.get("state"),
            ))

    return list(devices.values())


def _extract_sensor_mappings(sensors: list[dict]) -> SensorMappingSuggestions:
    """
    Extrahiert Sensor-Mapping-Vorschläge aus der Sensor-Liste.
    Berücksichtigt SMA-Sensoren mit sensor.sn_NUMMER_ Prefix.
    """
    mappings = SensorMappingSuggestions()

    for sensor in sensors:
        entity_id = sensor["entity_id"]
        attrs = sensor.get("attributes", {})

        # Nur Energy-Sensoren mit kWh für Mappings
        unit = attrs.get("unit_of_measurement", "")
        state_class = attrs.get("state_class", "")

        # Für Monatsdaten-Import brauchen wir total_increasing Sensoren mit kWh
        if state_class != "total_increasing" or unit != "kWh":
            continue

        integration, mapping_type, confidence = _classify_sensor(entity_id, attrs)

        if mapping_type and confidence >= 50:
            discovered = DiscoveredSensor(
                entity_id=entity_id,
                friendly_name=attrs.get("friendly_name"),
                unit_of_measurement=unit,
                device_class=attrs.get("device_class"),
                state_class=state_class,
                current_state=sensor.get("state"),
                suggested_mapping=mapping_type,
                confidence=confidence,
            )

            # Zu entsprechender Liste hinzufügen
            if mapping_type == "pv_erzeugung":
                mappings.pv_erzeugung.append(discovered)
            elif mapping_type == "einspeisung":
                mappings.einspeisung.append(discovered)
            elif mapping_type == "netzbezug":
                mappings.netzbezug.append(discovered)
            elif mapping_type == "batterie_ladung":
                mappings.batterie_ladung.append(discovered)
            elif mapping_type == "batterie_entladung":
                mappings.batterie_entladung.append(discovered)

    # Nach Confidence sortieren (höchste zuerst)
    mappings.pv_erzeugung.sort(key=lambda x: x.confidence, reverse=True)
    mappings.einspeisung.sort(key=lambda x: x.confidence, reverse=True)
    mappings.netzbezug.sort(key=lambda x: x.confidence, reverse=True)
    mappings.batterie_ladung.sort(key=lambda x: x.confidence, reverse=True)
    mappings.batterie_entladung.sort(key=lambda x: x.confidence, reverse=True)

    return mappings


@router.get("/discover", response_model=DiscoveryResult)
async def discover_ha_devices(
    anlage_id: Optional[int] = Query(None, description="Anlage-ID für Duplikat-Prüfung"),
    db: AsyncSession = Depends(get_db)
):
    """
    Durchsucht Home Assistant nach Geräten und Sensoren.

    Erkennt automatisch:
    - SMA Wechselrichter (Sensor-Mappings für PV, Grid, Batterie)
    - evcc Loadpoints (Wallbox) und Vehicles (E-Auto)
    - Smart E-Auto Integration
    - Wallbox Integration

    evcc hat Priorität für E-Auto und Wallbox Daten.

    Args:
        anlage_id: Optional - wenn angegeben, werden existierende Investitionen geprüft

    Returns:
        DiscoveryResult: Gefundene Geräte und Sensor-Mapping-Vorschläge
    """
    result = DiscoveryResult(
        ha_connected=False,
        current_mappings=HASensorMapping(
            pv_erzeugung=settings.ha_sensor_pv or None,
            einspeisung=settings.ha_sensor_einspeisung or None,
            netzbezug=settings.ha_sensor_netzbezug or None,
            batterie_ladung=settings.ha_sensor_batterie_ladung or None,
            batterie_entladung=settings.ha_sensor_batterie_entladung or None,
        )
    )

    if not settings.supervisor_token:
        result.warnings.append("Kein Supervisor Token gefunden. EEDC läuft nicht als HA Add-on.")
        return result

    # Alle HA-States abrufen
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{settings.ha_api_url}/states",
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                timeout=15.0
            )

            if response.status_code != 200:
                result.warnings.append(f"HA API Fehler: {response.status_code}")
                return result

            states = response.json()
            result.ha_connected = True

    except Exception as e:
        result.warnings.append(f"HA Verbindungsfehler: {str(e)}")
        return result

    # Nur Sensoren filtern
    sensors = [
        {
            "entity_id": s["entity_id"],
            "state": s.get("state"),
            "attributes": s.get("attributes", {}),
        }
        for s in states
        if s["entity_id"].startswith("sensor.")
    ]

    # Geräte extrahieren
    devices = _extract_devices_from_sensors(sensors)

    # Bereits konfigurierte Investitionen prüfen
    if anlage_id:
        inv_result = await db.execute(
            select(Investition).where(Investition.anlage_id == anlage_id)
        )
        existing_investitions = inv_result.scalars().all()

        # Prüfe auf Duplikate basierend auf Typ und Bezeichnung
        for device in devices:
            for inv in existing_investitions:
                # Typ-Matching
                type_match = (
                    (device.suggested_investition_typ == "e-auto" and inv.typ == InvestitionTyp.E_AUTO.value) or
                    (device.suggested_investition_typ == "wallbox" and inv.typ == InvestitionTyp.WALLBOX.value) or
                    (device.suggested_investition_typ == "speicher" and inv.typ == InvestitionTyp.SPEICHER.value)
                )

                # Name-Ähnlichkeit prüfen
                if type_match:
                    device_name_lower = device.name.lower()
                    inv_name_lower = (inv.bezeichnung or "").lower()

                    # Einfache Ähnlichkeitsprüfung
                    if (device_name_lower in inv_name_lower or
                        inv_name_lower in device_name_lower or
                        device.integration in inv_name_lower):
                        device.already_configured = True
                        break

    # Duplikate filtern: evcc hat Vorrang
    evcc_wallbox = any(d.integration == "evcc" and d.device_type == "wallbox" for d in devices)
    evcc_ev = any(d.integration == "evcc" and d.device_type == "ev" for d in devices)

    filtered_devices = []
    for device in devices:
        # Wallbox native überspringen wenn evcc Wallbox vorhanden
        if device.id == "wallbox_native" and evcc_wallbox:
            result.warnings.append("Wallbox-Integration gefunden, aber evcc wird bevorzugt.")
            continue

        # Smart EV überspringen wenn evcc Vehicle vorhanden
        if device.id == "smart_ev" and evcc_ev:
            result.warnings.append("Smart #1 gefunden, aber evcc-Vehicle wird bevorzugt.")
            continue

        filtered_devices.append(device)

    # Nach Priorität sortieren
    filtered_devices.sort(key=lambda x: x.priority, reverse=True)
    result.devices = filtered_devices

    # Sensor-Mappings extrahieren
    result.sensor_mappings = _extract_sensor_mappings(sensors)

    return result


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
