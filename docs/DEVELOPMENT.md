# EEDC Development Guide

## Voraussetzungen

- Python 3.11+
- Node.js 18+
- Docker/Podman (für Add-on Tests)

## Lokale Entwicklung

### Backend

```bash
cd eedc

# Virtual Environment erstellen (einmalig)
cd backend
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows

# Dependencies installieren
pip install -r requirements.txt

# Zurück ins eedc Verzeichnis und Server starten
cd ..
source backend/venv/bin/activate
uvicorn backend.main:app --reload --port 8099

# API Docs öffnen
# http://localhost:8099/api/docs
```

### Frontend

```bash
cd eedc/frontend

# Dependencies installieren (einmalig)
npm install

# Development Server starten
npm run dev

# Öffne http://localhost:5173
```

### Beide zusammen

Terminal 1 (Backend):
```bash
cd eedc && source backend/venv/bin/activate && uvicorn backend.main:app --reload --port 8099
```

Terminal 2 (Frontend):
```bash
cd eedc/frontend && npm run dev
```

## Docker/Podman Build

```bash
cd eedc

# Image bauen
docker build -t eedc-addon .
# oder: podman build -t eedc-addon .

# Container starten
docker run -p 8099:8099 -v $(pwd)/data:/data eedc-addon
# oder: podman run -p 8099:8099 -v $(pwd)/data:/data eedc-addon

# Öffne http://localhost:8099
```

## Home Assistant Add-on Test

Für Tests in einer echten Home Assistant Umgebung:

1. Repository zu HA Add-on Repositories hinzufügen:
   - Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories
   - URL: `https://github.com/supernova1963/eedc-homeassistant`
2. Add-on installieren und starten
3. Über Sidebar "eedc" öffnen

## Code Style

### Python
- Formatierung mit `black`
- Linting mit `ruff`
- Type Hints verwenden

### TypeScript
- ESLint Konfiguration beachten
- Strikte TypeScript Einstellungen

## API Dokumentation

Nach dem Start des Backends verfügbar unter:
- Swagger UI: http://localhost:8099/api/docs
- ReDoc: http://localhost:8099/api/redoc
- OpenAPI JSON: http://localhost:8099/api/openapi.json

## Datenbank

SQLite Datenbank unter `/data/eedc.db`.

Schema wird beim ersten Start automatisch erstellt.

Für Schema-Änderungen:
1. Model in `backend/models/` anpassen
2. Backend neu starten (Schema wird aktualisiert)

## Tests

```bash
# Backend Tests
cd eedc/backend
pytest

# Frontend Tests (noch nicht implementiert)
cd eedc/frontend
npm test
```

## Versionierung

Bei neuen Releases müssen folgende Dateien aktualisiert werden:

1. `eedc/backend/core/config.py` - `APP_VERSION`
2. `eedc/frontend/src/config/version.ts` - `APP_VERSION`
3. `eedc/config.yaml` - `version`
4. `README.md` - Changelog
5. `CLAUDE.md` - Changelog

## Wichtige Pfade

```
eedc/
├── config.yaml              # HA Add-on Konfiguration
├── Dockerfile               # Multi-Stage Build
├── run.sh                   # Container Startscript
├── backend/
│   ├── main.py              # FastAPI Entry Point
│   ├── requirements.txt
│   ├── api/
│   │   ├── deps.py          # Dependencies (get_db)
│   │   └── routes/          # API Endpoints
│   ├── core/
│   │   ├── config.py        # Settings + Version
│   │   ├── database.py      # SQLAlchemy Setup
│   │   └── calculations.py  # Berechnungslogik
│   ├── models/              # SQLAlchemy Models
│   └── services/            # HA Export, MQTT, etc.
└── frontend/
    ├── src/
    │   ├── api/             # API Client
    │   ├── components/      # UI Components
    │   ├── pages/           # Seiten
    │   ├── hooks/           # React Hooks
    │   └── config/          # Version, etc.
    └── dist/                # Production Build
```
