# EEDC Development Guide

**Version 1.0.0-beta.4** | Stand: Februar 2026

---

## Voraussetzungen

- Python 3.11+
- Node.js 18+
- Docker/Podman (für Container-Tests)

## Schnellstart

### 1. Repository klonen

```bash
git clone https://github.com/supernova1963/eedc-homeassistant.git
cd eedc-homeassistant
```

### 2. Backend einrichten

```bash
cd eedc/backend

# Virtual Environment erstellen (einmalig)
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows

# Dependencies installieren
pip install -r requirements.txt
```

### 3. Frontend einrichten

```bash
cd eedc/frontend

# Dependencies installieren (einmalig)
npm install
```

### 4. Entwicklungsserver starten

**Terminal 1 (Backend):**
```bash
cd eedc && source backend/venv/bin/activate
uvicorn backend.main:app --reload --port 8099
```

**Terminal 2 (Frontend):**
```bash
cd eedc/frontend && npm run dev
```

**URLs:**
- Frontend: http://localhost:5173 (mit Proxy zu Backend)
- API Docs: http://localhost:8099/api/docs
- ReDoc: http://localhost:8099/api/redoc

---

## Docker/Podman Build

```bash
cd eedc

# Image bauen
docker build -t eedc .
# oder: podman build -t eedc .

# Container starten
docker run -p 8099:8099 -v $(pwd)/data:/data eedc
# oder: podman run -p 8099:8099 -v $(pwd)/data:/data eedc

# Browser öffnen
open http://localhost:8099
```

---

## Home Assistant Add-on Test

Für Tests in einer echten Home Assistant Umgebung:

1. Repository zu HA Add-on Repositories hinzufügen:
   - Einstellungen → Add-ons → Add-on Store → ⋮ → Repositories
   - URL: `https://github.com/supernova1963/eedc-homeassistant`
2. Add-on installieren und starten
3. Über Sidebar "eedc" öffnen

---

## Versionierung

Bei neuen Releases müssen diese Dateien aktualisiert werden:

| Datei | Feld |
|-------|------|
| `eedc/backend/core/config.py` | `APP_VERSION` |
| `eedc/frontend/src/config/version.ts` | `APP_VERSION` |
| `eedc/config.yaml` | `version` |
| `eedc/run.sh` | Echo-Statement |
| `CHANGELOG.md` | Neuer Eintrag |

---

## Code-Konventionen

### Python (Backend)

- Formatierung mit `black`
- Linting mit `ruff`
- Type Hints verwenden
- Docstrings für öffentliche Funktionen

### TypeScript (Frontend)

- ESLint Konfiguration beachten
- Strikte TypeScript Einstellungen
- Functional Components mit Hooks

### Git Commits

```
feat(component): Add new feature
fix(component): Fix specific issue
refactor(component): Refactor without behavior change
docs: Update documentation
chore: Build, dependencies, etc.
```

---

## Kritische Code-Patterns

### SQLAlchemy JSON-Felder

SQLAlchemy erkennt Änderungen an JSON-Feldern nicht automatisch:

```python
from sqlalchemy.orm.attributes import flag_modified

# Nach Änderung an JSON-Feldern IMMER flag_modified aufrufen!
obj.verbrauch_daten["key"] = value
flag_modified(obj, "verbrauch_daten")
db.commit()
```

### 0-Werte korrekt prüfen

```python
# FALSCH - 0 wird als False gewertet
if val:
    ...

# RICHTIG
if val is not None:
    ...
```

### Datenquellen-Trennung

- `Monatsdaten` = Nur Zählerwerte (Einspeisung, Netzbezug)
- `InvestitionMonatsdaten` = Alle Komponenten-Details

**Legacy-Felder nicht verwenden:**
- `Monatsdaten.pv_erzeugung_kwh` ❌
- `Monatsdaten.batterie_*` ❌

---

## Projektstruktur

```
eedc-homeassistant/
├── README.md                    # Projekt-Übersicht
├── CHANGELOG.md                 # Versionshistorie
├── CLAUDE.md                    # KI-Entwicklungskontext
│
├── docs/
│   ├── BENUTZERHANDBUCH.md      # Endbenutzer-Anleitung
│   ├── ARCHITEKTUR.md           # Technische Dokumentation
│   ├── DEVELOPMENT.md           # Diese Datei
│   └── archive/                 # Archivierte Dokumente
│
└── eedc/                        # Die Anwendung
    ├── config.yaml              # HA Add-on Konfiguration
    ├── Dockerfile               # Multi-Stage Build
    ├── run.sh                   # Container Startscript
    │
    ├── backend/
    │   ├── main.py              # FastAPI Entry Point
    │   ├── requirements.txt
    │   ├── api/routes/          # API Endpoints
    │   ├── core/                # Config, DB, Calculations
    │   ├── models/              # SQLAlchemy Models
    │   └── services/            # Business Logic
    │
    └── frontend/
        ├── package.json
        ├── vite.config.ts
        ├── src/
        │   ├── api/             # API Client
        │   ├── components/      # UI Components
        │   ├── pages/           # Seiten
        │   ├── hooks/           # React Hooks
        │   └── config/          # Version, etc.
        └── dist/                # Production Build
```

---

## Datenbank

- **Typ:** SQLite
- **Pfad:** `/data/eedc.db`
- **Schema:** Wird beim ersten Start automatisch erstellt

Für Schema-Änderungen:
1. Model in `backend/models/` anpassen
2. Backend neu starten (Schema wird automatisch aktualisiert)

---

## Tests

```bash
# Backend Tests
cd eedc/backend
pytest

# Frontend Tests (noch nicht implementiert)
cd eedc/frontend
npm test
```

---

## API Dokumentation

Nach dem Start des Backends verfügbar unter:

| Format | URL |
|--------|-----|
| Swagger UI | http://localhost:8099/api/docs |
| ReDoc | http://localhost:8099/api/redoc |
| OpenAPI JSON | http://localhost:8099/api/openapi.json |

---

## Weiterführende Dokumentation

- [Architektur](ARCHITEKTUR.md) - Detaillierte technische Dokumentation
- [Benutzerhandbuch](BENUTZERHANDBUCH.md) - Für Endbenutzer
- [CLAUDE.md](../CLAUDE.md) - KI-Entwicklungskontext

---

*Letzte Aktualisierung: Februar 2026*
