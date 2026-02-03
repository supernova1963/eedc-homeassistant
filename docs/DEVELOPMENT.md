# EEDC Development Guide

## Voraussetzungen

- Python 3.11+
- Node.js 18+
- Docker (für Add-on Tests)

## Lokale Entwicklung

### Backend

```bash
cd eedc/backend

# Virtual Environment erstellen
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows

# Dependencies installieren
pip install -r requirements.txt

# Development Server starten
uvicorn main:app --reload --port 8099

# API Docs öffnen
# http://localhost:8099/api/docs
```

### Frontend

```bash
cd eedc/frontend

# Dependencies installieren
npm install

# Development Server starten
npm run dev

# Öffne http://localhost:3000
```

### Beide zusammen

Terminal 1:
```bash
cd eedc/backend && uvicorn main:app --reload --port 8099
```

Terminal 2:
```bash
cd eedc/frontend && npm run dev
```

## Docker Build

```bash
cd eedc

# Image bauen
docker build -t eedc-addon .

# Container starten
docker run -p 8099:8099 -v $(pwd)/data:/data eedc-addon

# Öffne http://localhost:8099
```

## Home Assistant Add-on Test

Für Tests in einer echten Home Assistant Umgebung:

1. Home Assistant Entwicklungsumgebung einrichten (z.B. HA OS in VM)
2. Repository als lokales Add-on hinzufügen
3. Add-on installieren und starten

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
