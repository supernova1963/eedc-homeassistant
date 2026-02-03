"""
EEDC - Energie Effizienz Data Center
FastAPI Backend Application

Dieses Backend dient als API-Server für das EEDC Home Assistant Add-on.
Es stellt Endpoints für Anlagen, Monatsdaten, Investitionen und Auswertungen bereit.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.core.config import settings
from backend.core.database import init_db
from backend.api.routes import anlagen, monatsdaten, investitionen, strompreise, import_export, ha_integration


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifecycle Management für die FastAPI App.

    Beim Start:
    - Datenbank initialisieren (Tabellen erstellen falls nicht vorhanden)

    Beim Shutdown:
    - Ressourcen freigeben
    """
    # Startup
    print("EEDC Backend startet...")
    await init_db()
    print("Datenbank initialisiert.")

    yield

    # Shutdown
    print("EEDC Backend wird beendet...")


# FastAPI App erstellen
app = FastAPI(
    title="EEDC API",
    description="Energie Effizienz Data Center - API für PV-Anlagen Auswertung",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/api/docs",      # Swagger UI
    redoc_url="/api/redoc",    # ReDoc
    openapi_url="/api/openapi.json"
)

# CORS Middleware (für Development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In Produktion einschränken
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# API Routes
# =============================================================================

# Prefix /api für alle Backend-Endpoints
app.include_router(anlagen.router, prefix="/api/anlagen", tags=["Anlagen"])
app.include_router(monatsdaten.router, prefix="/api/monatsdaten", tags=["Monatsdaten"])
app.include_router(investitionen.router, prefix="/api/investitionen", tags=["Investitionen"])
app.include_router(strompreise.router, prefix="/api/strompreise", tags=["Strompreise"])
app.include_router(import_export.router, prefix="/api/import", tags=["Import/Export"])
app.include_router(ha_integration.router, prefix="/api/ha", tags=["Home Assistant"])


# =============================================================================
# Health Check
# =============================================================================

@app.get("/api/health", tags=["System"])
async def health_check():
    """
    Health Check Endpoint für Docker/HA.

    Returns:
        dict: Status und Version
    """
    return {
        "status": "healthy",
        "version": "0.1.0",
        "database": "connected"
    }


@app.get("/api/settings", tags=["System"])
async def get_settings():
    """
    Gibt aktuelle Einstellungen zurück (ohne sensible Daten).

    Returns:
        dict: Öffentliche Konfiguration
    """
    return {
        "version": "0.1.0",
        "database_path": str(settings.database_path),
        "ha_integration_enabled": bool(settings.supervisor_token),
        "ha_sensors_configured": {
            "pv_erzeugung": bool(settings.ha_sensor_pv),
            "einspeisung": bool(settings.ha_sensor_einspeisung),
            "netzbezug": bool(settings.ha_sensor_netzbezug),
        }
    }


# =============================================================================
# Frontend Serving (SPA)
# =============================================================================

# Statische Dateien (JS, CSS, Assets)
frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"

if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """
        Serve React SPA.

        Alle Routen die nicht mit /api beginnen werden an das Frontend weitergeleitet.
        """
        # Versuche zuerst die Datei direkt zu finden
        file_path = frontend_dist / full_path
        if file_path.is_file():
            return FileResponse(file_path)

        # Sonst index.html für SPA Routing
        return FileResponse(frontend_dist / "index.html")
else:
    @app.get("/")
    async def no_frontend():
        """Fallback wenn Frontend nicht gebaut wurde."""
        return {
            "message": "EEDC API läuft. Frontend nicht gefunden.",
            "hint": "Bitte 'npm run build' im frontend/ Verzeichnis ausführen.",
            "api_docs": "/api/docs"
        }
