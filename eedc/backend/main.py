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

from sqlalchemy import select, func
from backend.core.config import settings, APP_VERSION, APP_NAME, APP_FULL_NAME
from backend.core.database import init_db, get_session
from backend.api.routes import anlagen, monatsdaten, investitionen, strompreise, import_export, ha_integration, ha_export, ha_import, pvgis, cockpit, wetter, aussichten, solar_prognose
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten
from backend.models.strompreis import Strompreis


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
    title=f"{APP_NAME.upper()} API",
    description=f"{APP_FULL_NAME} - API für PV-Anlagen Auswertung",
    version=APP_VERSION,
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
app.include_router(ha_export.router, prefix="/api", tags=["HA Export"])
app.include_router(pvgis.router, prefix="/api/pvgis", tags=["PVGIS"])
app.include_router(cockpit.router, prefix="/api/cockpit", tags=["Cockpit"])
app.include_router(wetter.router, prefix="/api/wetter", tags=["Wetter"])
app.include_router(ha_import.router, prefix="/api/ha-import", tags=["HA Import"])
app.include_router(aussichten.router, prefix="/api/aussichten", tags=["Aussichten"])
app.include_router(solar_prognose.router, prefix="/api/solar-prognose", tags=["Solar-Prognose"])


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
        "version": APP_VERSION,
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
        "version": APP_VERSION,
        "database_path": str(settings.database_path),
        "ha_integration_enabled": bool(settings.supervisor_token),
        "ha_sensors_configured": {
            "pv_erzeugung": bool(settings.ha_sensor_pv),
            "einspeisung": bool(settings.ha_sensor_einspeisung),
            "netzbezug": bool(settings.ha_sensor_netzbezug),
            "batterie_ladung": bool(settings.ha_sensor_batterie_ladung),
            "batterie_entladung": bool(settings.ha_sensor_batterie_entladung),
        },
        "ha_sensors": {
            "pv_erzeugung": settings.ha_sensor_pv,
            "einspeisung": settings.ha_sensor_einspeisung,
            "netzbezug": settings.ha_sensor_netzbezug,
            "batterie_ladung": settings.ha_sensor_batterie_ladung,
            "batterie_entladung": settings.ha_sensor_batterie_entladung,
        }
    }


@app.get("/api/stats", tags=["System"])
async def get_database_stats():
    """
    Gibt Datenbank-Statistiken zurück.

    Returns:
        dict: Anzahl der Datensätze pro Tabelle
    """
    async with get_session() as session:
        # Anlagen zählen
        anlagen_result = await session.execute(select(func.count()).select_from(Anlage))
        anlagen_count = anlagen_result.scalar() or 0

        # Monatsdaten zählen
        monatsdaten_result = await session.execute(select(func.count()).select_from(Monatsdaten))
        monatsdaten_count = monatsdaten_result.scalar() or 0

        # Investitionen zählen
        investitionen_result = await session.execute(select(func.count()).select_from(Investition))
        investitionen_count = investitionen_result.scalar() or 0

        # Strompreise zählen
        strompreise_result = await session.execute(select(func.count()).select_from(Strompreis))
        strompreise_count = strompreise_result.scalar() or 0

        # Zusätzliche Infos
        # Gesamte PV-Erzeugung aus InvestitionMonatsdaten (pro PV-Modul)
        # WICHTIG: Monatsdaten.pv_erzeugung_kwh ist LEGACY und wird nicht mehr gepflegt!

        # PV-Module IDs ermitteln
        pv_ids_result = await session.execute(
            select(Investition.id).where(Investition.typ == "pv-module")
        )
        pv_ids = [row[0] for row in pv_ids_result.all()]

        gesamt_erzeugung = 0.0
        if pv_ids:
            imd_result = await session.execute(
                select(InvestitionMonatsdaten)
                .where(InvestitionMonatsdaten.investition_id.in_(pv_ids))
            )
            for imd in imd_result.scalars().all():
                data = imd.verbrauch_daten or {}
                gesamt_erzeugung += data.get("pv_erzeugung_kwh", 0) or 0

        # Zeitraum der Daten
        zeitraum_result = await session.execute(
            select(
                func.min(Monatsdaten.jahr),
                func.max(Monatsdaten.jahr)
            )
        )
        zeitraum = zeitraum_result.one()
        min_jahr = zeitraum[0]
        max_jahr = zeitraum[1]

    return {
        "anlagen": anlagen_count,
        "monatsdaten": monatsdaten_count,
        "investitionen": investitionen_count,
        "strompreise": strompreise_count,
        "gesamt_erzeugung_kwh": round(gesamt_erzeugung, 0) if gesamt_erzeugung else 0,
        "daten_zeitraum": {
            "von": min_jahr,
            "bis": max_jahr
        } if min_jahr else None,
        "database_path": str(settings.database_path),
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
