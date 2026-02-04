"""
Home Assistant Integration API Routes

Endpoints für HA-Sensor-Zugriff und Datenimport.
Erweitert um String-basierte IST-Erfassung für PV-Module.
"""

from typing import Optional
from datetime import datetime, date
from calendar import monthrange
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


# =============================================================================
# Long-Term Statistics API (Monatswerte aus Zählern)
# =============================================================================

async def _get_ha_statistics_monthly(
    statistic_id: str,
    start_date: date,
    end_date: date
) -> list[dict]:
    """
    Holt monatliche Statistiken aus HA Long-Term Statistics.

    HA speichert Statistiken für Sensoren mit state_class "total_increasing".
    Die Long-Term Statistics sind nur über WebSocket verfügbar, daher nutzen
    wir den Supervisor WebSocket-Proxy oder alternativ die History API.

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

    async with httpx.AsyncClient() as client:
        # Methode 1: Versuche WebSocket API über REST-Wrapper (HA 2023.3+)
        # Der Endpoint /api/websocket_api ist ein REST-Wrapper für WebSocket-Befehle
        start_ts = datetime.combine(start_date, datetime.min.time()).isoformat() + "Z"
        end_ts = datetime.combine(end_date, datetime.max.time()).isoformat() + "Z"

        try:
            # Versuche recorder/statistics_during_period über REST-Wrapper
            response = await client.post(
                f"{settings.ha_api_url}/history/statistics_during_period",
                json={
                    "start_time": start_ts,
                    "end_time": end_ts,
                    "statistic_ids": [statistic_id],
                    "period": "month",
                },
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                timeout=30.0
            )

            if response.status_code == 200:
                data = response.json()
                stats = data.get(statistic_id, [])

                for stat in stats:
                    stat_start = stat.get("start")
                    change = stat.get("change", 0) or stat.get("sum", 0) or 0

                    if stat_start and change > 0:
                        monthly_data.append({
                            "start": stat_start,
                            "change": round(float(change), 2)
                        })

                if monthly_data:
                    return monthly_data

        except Exception:
            pass  # Fallback zur alternativen Methode

        # Methode 2: Berechne Monatswerte aus den stündlichen Statistiken
        # Hole alle verfügbaren Statistiken und gruppiere nach Monat
        try:
            response = await client.post(
                f"{settings.ha_api_url}/history/statistics_during_period",
                json={
                    "start_time": start_ts,
                    "end_time": end_ts,
                    "statistic_ids": [statistic_id],
                    "period": "hour",  # Stündliche Daten
                },
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                timeout=60.0
            )

            if response.status_code == 200:
                data = response.json()
                stats = data.get(statistic_id, [])

                # Gruppiere nach Monat und berechne Summe der Änderungen
                monthly_changes: dict[tuple[int, int], float] = {}

                for stat in stats:
                    stat_start = stat.get("start", "")
                    change = stat.get("change", 0) or 0

                    if stat_start and change > 0:
                        try:
                            dt = datetime.fromisoformat(stat_start.replace("Z", "+00:00"))
                            key = (dt.year, dt.month)
                            monthly_changes[key] = monthly_changes.get(key, 0) + float(change)
                        except ValueError:
                            pass

                # Konvertiere zu Liste
                for (year, month), total_change in sorted(monthly_changes.items()):
                    if total_change > 0:
                        month_start = datetime(year, month, 1)
                        monthly_data.append({
                            "start": month_start.isoformat(),
                            "change": round(total_change, 2)
                        })

                if monthly_data:
                    return monthly_data

        except Exception:
            pass

        # Methode 3: Fallback - Berechne aus Anfangs-/Endwerten pro Monat
        # Hole "state" Werte (Zählerstand) am Monatsanfang/-ende
        try:
            response = await client.post(
                f"{settings.ha_api_url}/history/statistics_during_period",
                json={
                    "start_time": start_ts,
                    "end_time": end_ts,
                    "statistic_ids": [statistic_id],
                    "period": "day",
                    "types": ["state"],  # Nur Zählerstand, nicht change
                },
                headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                timeout=60.0
            )

            if response.status_code == 200:
                data = response.json()
                stats = data.get(statistic_id, [])

                # Sammle Zählerstände pro Tag
                daily_states: dict[date, float] = {}

                for stat in stats:
                    stat_start = stat.get("start", "")
                    state_val = stat.get("state") or stat.get("mean") or stat.get("max")

                    if stat_start and state_val is not None:
                        try:
                            dt = datetime.fromisoformat(stat_start.replace("Z", "+00:00"))
                            daily_states[dt.date()] = float(state_val)
                        except (ValueError, TypeError):
                            pass

                if daily_states:
                    # Berechne Monatswerte aus Differenz Monatsanfang/-ende
                    current = date(start_date.year, start_date.month, 1)

                    while current <= end_date:
                        _, last_day = monthrange(current.year, current.month)
                        month_end_date = date(current.year, current.month, last_day)

                        # Finde ersten und letzten Wert im Monat
                        month_values = [
                            (d, v) for d, v in daily_states.items()
                            if d.year == current.year and d.month == current.month
                        ]

                        if len(month_values) >= 2:
                            month_values.sort(key=lambda x: x[0])
                            first_val = month_values[0][1]
                            last_val = month_values[-1][1]
                            change = last_val - first_val

                            if change > 0:
                                monthly_data.append({
                                    "start": datetime.combine(current, datetime.min.time()).isoformat(),
                                    "change": round(change, 2)
                                })

                        # Nächster Monat
                        if current.month == 12:
                            current = date(current.year + 1, 1, 1)
                        else:
                            current = date(current.year, current.month + 1, 1)

        except Exception:
            pass

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
