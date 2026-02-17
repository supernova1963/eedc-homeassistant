# EEDC Development Guide

**Version 1.1.0-beta.1** | Stand: Februar 2026

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
    │   │   ├── cockpit.py       # Dashboard-Aggregation
    │   │   ├── aussichten.py    # Prognosen (NEU)
    │   │   └── ...              # monatsdaten, investitionen, etc.
    │   ├── core/                # Config, DB, Calculations
    │   ├── models/              # SQLAlchemy Models
    │   └── services/
    │       ├── wetter_service.py    # Open-Meteo + PVGIS
    │       ├── prognose_service.py  # Prognose-Berechnungen
    │       ├── pdf_service.py       # PDF-Export
    │       ├── mqtt_client.py       # HA Export
    │       ├── ha_mqtt_sync.py      # MQTT Sync Service (NEU)
    │       ├── vorschlag_service.py # Intelligente Vorschläge (NEU)
    │       └── scheduler.py         # APScheduler für Cron-Jobs (NEU)
    │
    └── frontend/
        ├── package.json
        ├── vite.config.ts
        ├── src/
        │   ├── api/             # API Client
        │   │   ├── cockpit.ts   # Cockpit/Dashboard
        │   │   └── aussichten.ts # Prognosen
        │   ├── components/      # UI Components
        │   ├── pages/           # Seiten
        │   │   ├── Dashboard.tsx             # Cockpit
        │   │   ├── Auswertung.tsx            # Analysen
        │   │   ├── Aussichten.tsx            # Prognosen (4 Tabs)
        │   │   ├── SensorMappingWizard.tsx   # Sensor-Mapping (NEU)
        │   │   ├── MonatsabschlussWizard.tsx # Monatsabschluss (NEU)
        │   │   └── aussichten/               # Tab-Komponenten
        │   │       ├── KurzfristTab.tsx
        │   │       ├── LangfristTab.tsx
        │   │       ├── TrendTab.tsx
        │   │       └── FinanzenTab.tsx
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

**Hinweis für bestehende Installationen (z.B. nach Update auf beta.6):**

SQLAlchemy fügt neue Spalten nicht automatisch zu bestehenden Tabellen hinzu. Bei neuen Spalten manuell ausführen:

```sql
-- Beispiel für beta.6 Stammdaten-Erweiterung:
ALTER TABLE anlagen ADD COLUMN mastr_id VARCHAR(20);
ALTER TABLE anlagen ADD COLUMN versorger_daten JSON;
```

Die `parameter` JSON-Spalte in `investitionen` wird automatisch erweitert (kein ALTER TABLE nötig).

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

### Wichtige API-Routen

| Modul | Endpoints | Beschreibung |
|-------|-----------|--------------|
| **Cockpit** | `/api/cockpit/*` | Dashboard-Aggregation, KPIs |
| **Aussichten** | `/api/aussichten/*` | Prognosen (Kurzfrist, Langfrist, Trend, Finanzen) |
| **Monatsdaten** | `/api/monatsdaten/*` | CRUD + Berechnungen |
| **Investitionen** | `/api/investitionen/*` | Komponenten, ROI |
| **Import/Export** | `/api/import/*` | CSV Import/Export, JSON-Export |
| **Wetter** | `/api/wetter/*` | Open-Meteo + PVGIS TMY |

### Aussichten API

```
GET /api/aussichten/kurzfristig/{anlage_id}     # 7-Tage Wetter-Prognose
GET /api/aussichten/langfristig/{anlage_id}     # 12-Monats PVGIS-Prognose
GET /api/aussichten/trend/{anlage_id}           # Historische Trend-Analyse
GET /api/aussichten/finanzen/{anlage_id}        # Amortisations-Prognose
```

### Sensor-Mapping API (NEU v1.1.0)

```
GET  /api/sensor-mapping/{anlage_id}              # Aktuelles Mapping abrufen
POST /api/sensor-mapping/{anlage_id}              # Mapping speichern
GET  /api/sensor-mapping/{anlage_id}/felder       # Verfügbare Felder
GET  /api/sensor-mapping/{anlage_id}/sensoren     # HA-Sensoren auflisten
```

### Monatsabschluss API (NEU v1.1.0)

```
GET  /api/monatsabschluss/{anlage_id}/status      # Status für Jahr/Monat
GET  /api/monatsabschluss/{anlage_id}/naechster   # Nächster offener Monat
POST /api/monatsabschluss/{anlage_id}/abschliessen # Abschluss durchführen
GET  /api/monatsabschluss/{anlage_id}/historie    # Letzte Abschlüsse
```

### Import/Export API (erweitert in beta.8)

```
POST /api/import/csv/{anlage_id}                # CSV Import (mit Plausibilitätsprüfung)
GET  /api/import/export/{anlage_id}/full        # Vollständiger JSON-Export
GET  /api/import/template/{anlage_id}           # CSV Template herunterladen
```

---

## Weiterführende Dokumentation

- [Architektur](ARCHITEKTUR.md) - Detaillierte technische Dokumentation
- [Benutzerhandbuch](BENUTZERHANDBUCH.md) - Für Endbenutzer
- [CLAUDE.md](../CLAUDE.md) - KI-Entwicklungskontext

---

*Letzte Aktualisierung: Februar 2026*
