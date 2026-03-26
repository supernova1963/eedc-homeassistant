"""
System Logs & Activity Log API Routes.

Endpoints für den Log-Viewer und das Aktivitätsprotokoll.
"""

import logging
import os
from typing import Optional, Literal

import httpx
from fastapi import APIRouter, Query
from pydantic import BaseModel

from backend.core.log_buffer import get_log_buffer
from backend.core.config import HA_INTEGRATION_AVAILABLE, settings
from backend.services.activity_service import get_activities, cleanup_old_activities

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Schemas
# =============================================================================

class LogEntryResponse(BaseModel):
    timestamp: str
    level: str
    logger_name: str
    message: str
    module: str


class ActivityEntryResponse(BaseModel):
    id: int
    timestamp: Optional[str] = None
    kategorie: str
    aktion: str
    erfolg: bool
    details: Optional[str] = None
    details_json: Optional[dict] = None
    anlage_id: Optional[int] = None


class ActivityListResponse(BaseModel):
    items: list[ActivityEntryResponse]
    total: int


# =============================================================================
# System Logs (Ring Buffer)
# =============================================================================

@router.get("/logs", response_model=list[LogEntryResponse])
async def get_system_logs(
    level: Optional[str] = Query(None, description="Minimum Log-Level: DEBUG, INFO, WARNING, ERROR"),
    module: Optional[str] = Query(None, description="Filter nach Modul/Logger-Name"),
    search: Optional[str] = Query(None, description="Suche in Log-Nachrichten"),
    limit: int = Query(200, ge=1, le=500, description="Max. Einträge"),
):
    """Aktuelle Log-Einträge aus dem In-Memory Ring Buffer (neueste zuerst, max. 500)."""
    buffer = get_log_buffer()
    return buffer.get_entries(level=level, module=module, search=search, limit=limit)


# =============================================================================
# Activity Log (Persistent)
# =============================================================================

@router.get("/activities", response_model=ActivityListResponse)
async def get_activity_log(
    kategorie: Optional[str] = Query(None, description="Filter nach Kategorie"),
    erfolg: Optional[bool] = Query(None, description="Filter nach Erfolg/Fehler"),
    anlage_id: Optional[int] = Query(None, description="Filter nach Anlage"),
    search: Optional[str] = Query(None, description="Suche in Aktion und Details"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Persistente Aktivitätsprotokoll-Einträge mit Filtern."""
    return await get_activities(
        kategorie=kategorie,
        erfolg=erfolg,
        anlage_id=anlage_id,
        search=search,
        limit=limit,
        offset=offset,
    )


@router.get("/activities/kategorien")
async def get_activity_kategorien():
    """Verfügbare Aktivitäts-Kategorien für Filter-Dropdown."""
    return [
        {"id": "connector_test", "label": "Connector-Test"},
        {"id": "connector_setup", "label": "Connector-Einrichtung"},
        {"id": "connector_fetch", "label": "Connector-Abruf"},
        {"id": "portal_import", "label": "Portal-Import"},
        {"id": "cloud_import", "label": "Cloud-Import"},
        {"id": "cloud_fetch", "label": "Cloud-Fetch"},
        {"id": "custom_import", "label": "Custom-Import"},
        {"id": "backup_export", "label": "Backup-Export"},
        {"id": "backup_import", "label": "Backup-Import"},
        {"id": "monatsabschluss", "label": "Monatsabschluss"},
        {"id": "ha_statistics", "label": "HA-Statistiken"},
        {"id": "scheduler", "label": "Scheduler-Jobs"},
        {"id": "mqtt", "label": "MQTT"},
        {"id": "community", "label": "Community"},
        {"id": "sensor_mapping", "label": "Sensor-Mapping"},
        {"id": "ha_export", "label": "HA-Export"},
    ]


@router.post("/activities/cleanup")
async def trigger_activity_cleanup():
    """Alte Aktivitätsprotokoll-Einträge manuell bereinigen."""
    await cleanup_old_activities()
    return {"erfolg": True, "message": "Alte Einträge bereinigt"}


# =============================================================================
# Debug-Modus & Restart
# =============================================================================

@router.get("/log-level")
async def get_log_level():
    """Aktuelles Log-Level des Root-Loggers abfragen."""
    root = logging.getLogger()
    current = logging.getLevelName(root.level)
    return {"level": current}


@router.put("/log-level")
async def set_log_level(level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Query(...)):
    """
    Log-Level zur Laufzeit ändern (kein Restart nötig).

    DEBUG zeigt alle Detail-Meldungen, INFO ist der Standard.
    """
    root = logging.getLogger()
    root.setLevel(getattr(logging, level))
    logger.info(f"Log-Level auf {level} geändert")
    return {"erfolg": True, "level": level}


@router.post("/restart")
async def restart_addon():
    """
    EEDC Add-on neu starten.

    Im HA-Modus: Supervisor API. Standalone: Prozess beenden (Container-Runtime startet neu).
    """
    if HA_INTEGRATION_AVAILABLE and settings.supervisor_token:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "http://supervisor/addons/self/restart",
                    headers={"Authorization": f"Bearer {settings.supervisor_token}"},
                )
                if response.status_code == 200:
                    return {"erfolg": True, "message": "Add-on wird neu gestartet..."}
                return {"erfolg": False, "message": f"Supervisor-Fehler: {response.status_code}"}
        except Exception as e:
            return {"erfolg": False, "message": f"{type(e).__name__}: {e}"}
    else:
        # Standalone: Prozess beenden, Container/Systemd startet neu
        import asyncio
        asyncio.get_event_loop().call_later(1.0, lambda: os._exit(0))
        return {"erfolg": True, "message": "EEDC wird neu gestartet..."}
