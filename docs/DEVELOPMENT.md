
# EEDC Development Guide

**Version 3.6** | Stand: März 2026

---

## Voraussetzungen

- Python 3.11+
- Node.js 20+ (empfohlen via nvm; `eedc/frontend/.nvmrc` enthält `20`)
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

# Node 20 aktivieren (falls nvm genutzt wird)
nvm use 20

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

- Frontend: http://localhost:3000 (Vite Dev Server, Proxy zu Backend)
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

## Repository-Workflow

**`eedc-homeassistant` ist die Source of Truth.** Alle Änderungen (Backend, Frontend, Docs, HA-Config) hier machen. Das `eedc`-Standalone-Repo ist ein Spiegel und wird per Release-Script synchronisiert.

Siehe [RELEASE-WORKFLOW.md](RELEASE-WORKFLOW.md) für Details.

## Versionierung

Ein Release-Script bumpt alle Versionsdateien, committed, taggt, pusht und synchronisiert das Standalone-Repo:

```bash
./scripts/release.sh 3.2.0
```

| Datei | Feld |
| ----- | ---- |
| `eedc/backend/core/config.py` | `APP_VERSION` |
| `eedc/frontend/src/config/version.ts` | `APP_VERSION` |
| `eedc/config.yaml` | `version` (HA Add-on) |
| `eedc/run.sh` | Echo-Statement |
| `eedc/Dockerfile` | `io.hass.version` Label |
| `CHANGELOG.md` | Neuer Eintrag (manuell vor Release) |

**Wichtig:** HA Add-ons erkennen Updates über `config.yaml`. Jede Änderung, die beim User ankommen soll, benötigt ein Release.

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

- `Monatsdaten.pv_erzeugung_kwh` — Nutze `InvestitionMonatsdaten`
- `Monatsdaten.batterie_*` — Nutze `InvestitionMonatsdaten`

---

## Projektstruktur

```
eedc-homeassistant/
├── README.md                    # Projekt-Übersicht
├── CHANGELOG.md                 # Versionshistorie
├── CLAUDE.md                    # KI-Entwicklungskontext
│
├── scripts/
│   ├── release.sh               # Release + Sync (ein Script für alles)
│   └── github-traffic.sh        # GitHub Traffic-Statistiken
│
├── docs/
│   ├── BENUTZERHANDBUCH.md      # Endbenutzer-Index (verlinkt Handbucher)
│   ├── HANDBUCH_INSTALLATION.md # Teil I: Installation & Einrichtung
│   ├── HANDBUCH_BEDIENUNG.md    # Teil II: Bedienung
│   ├── HANDBUCH_EINSTELLUNGEN.md# Teil III: Einstellungen & Sensor-Mapping
│   ├── HANDBUCH_INFOTHEK.md     # Modul: Infothek
│   ├── ARCHITEKTUR.md           # Technische Dokumentation
│   ├── BERECHNUNGEN.md          # Berechnungsreferenz
│   ├── DEVELOPMENT.md           # Diese Datei
│   ├── RELEASE-WORKFLOW.md      # Release-Prozess
│   ├── GLOSSAR.md               # Begriffe & Support
│   ├── MQTT_INBOUND.md          # MQTT-Inbound Doku
│   ├── FLYER.md                 # Promotional Texte
│   └── archive/                 # Archivierte Dokumente
│
├── website/                     # Astro Starlight Website
│   ├── astro.config.mjs         # Sidebar-Konfiguration
│   └── src/content/docs/        # Website-Seiten (manuell mit docs/ sync halten)
│
└── eedc/                        # Die Anwendung
    ├── config.yaml              # HA Add-on Konfiguration
    ├── Dockerfile               # Multi-Stage Build
    ├── run.sh                   # Container Startscript
    ├── docker-compose.yml       # Standalone-Deployment
    │
    ├── backend/
    │   ├── main.py              # FastAPI Entry Point
    │   ├── requirements.txt
    │   ├── api/routes/
    │   │   ├── aktueller_monat.py   # Aktueller-Monat Dashboard
    │   │   ├── anlagen.py           # Anlagen CRUD
    │   │   ├── aussichten.py        # Prognosen (4 Tabs)
    │   │   ├── cloud_import.py      # Cloud-API Import
    │   │   ├── cockpit.py           # Dashboard-Aggregation
    │   │   ├── community.py         # Community-Benchmark
    │   │   ├── connector.py         # 9 Geräte-Connectors
    │   │   ├── custom_import.py     # CSV/JSON Feld-Mapping
    │   │   ├── daten_checker.py     # Datenqualitäts-Prüfung
    │   │   ├── data_import.py       # Portal-CSV Parser
    │   │   ├── ha_export.py         # MQTT Export zu HA
    │   │   ├── ha_import.py         # HA Import
    │   │   ├── ha_integration.py    # HA Integration
    │   │   ├── ha_statistics.py     # HA-DB Statistik (SQLite)
    │   │   ├── import_export/       # CSV, JSON, Demo, PDF
    │   │   ├── investitionen.py     # Komponenten, ROI
    │   │   ├── live_dashboard.py    # Live Dashboard Kern-API
    │   │   ├── live_mqtt_inbound.py # Live MQTT Endpoints
    │   │   ├── live_wetter.py      # Live Wetter + Verbrauchsprofil
    │   │   ├── monatsabschluss.py   # Monatsabschluss-Wizard
    │   │   ├── monatsdaten.py       # Monatsdaten CRUD
    │   │   ├── pvgis.py             # PVGIS-Daten
    │   │   ├── sensor_mapping.py    # Sensor-Zuordnung
    │   │   ├── solar_prognose.py    # Solar-Prognose
    │   │   ├── strompreise.py       # Tarife, Spezialtarife
    │   │   ├── system_logs.py       # System-Logs + Energieprofile
    │   │   └── wetter.py            # Wetter Multi-Provider
    │   │
    │   ├── core/                # Config, DB, Calculations
    │   ├── models/
    │   │   ├── ...                        # Anlage, Monatsdaten, Investition, etc.
    │   │   └── tages_energie_profil.py    # TagesEnergieProfil + TagesZusammenfassung
    │   └── services/
    │       ├── brightsky_service.py        # DWD-Daten via Bright Sky API
    │       ├── cloud_import/               # Cloud-Import-Provider (5 Provider)
    │       ├── community_service.py        # Community-Datenaufbereitung
    │       ├── ha_mqtt_sync.py             # MQTT Sync Service
    │       ├── ha_state_service.py         # HA State API
    │       ├── ha_statistics_service.py    # HA-DB Statistik-Abfragen
    │       ├── mqtt_client.py              # HA Export + MQTT Auto-Discovery
    │       ├── mqtt_inbound_service.py     # MQTT-Inbound (Live + Energy)
    │       ├── mqtt_energy_history_service.py # Energy-Snapshots (SQLite)
    │       ├── energie_profil_service.py    # Tages-Aggregation + Monats-Rollup
    │       ├── pdf_service.py              # PDF-Export
    │       ├── plz_to_state.py             # PLZ→Bundesland Mapping
    │       ├── prognose_service.py         # Prognose-Berechnungen
    │       ├── scheduler.py                # APScheduler für Cron-Jobs
    │       ├── solar_forecast_service.py   # Open-Meteo Solar GTI
    │       ├── vorschlag_service.py        # Intelligente Vorschläge
    │       └── wetter_service.py           # Multi-Provider Wetterdaten
    │
    └── frontend/
        ├── package.json
        ├── vite.config.ts
        ├── src/
        │   ├── api/                 # API Clients
        │   │   ├── aktuellerMonat.ts    # Aktueller Monat
        │   │   ├── anlagen.ts           # Anlagen CRUD
        │   │   ├── aussichten.ts        # Prognosen
        │   │   ├── cloudImport.ts       # Cloud-API Import
        │   │   ├── cockpit.ts           # Dashboard
        │   │   ├── community.ts         # Community-Benchmark
        │   │   ├── connector.ts         # Geräte-Connectors
        │   │   ├── customImport.ts      # CSV/JSON Feld-Mapping
        │   │   ├── datenChecker.ts      # Datenqualität
        │   │   ├── haStatistics.ts      # HA-Statistik
        │   │   ├── liveDashboard.ts     # Live Dashboard + MQTT
        │   │   ├── monatsabschluss.ts   # Monatsabschluss
        │   │   ├── portalImport.ts      # Portal-CSV Import
        │   │   ├── sensorMapping.ts     # Sensor-Zuordnung
        │   │   ├── system.ts            # System-Info
        │   │   └── systemLogs.ts        # System-Logs
        │   │
        │   ├── components/
        │   │   ├── ui/              # Shared UI (Card, Button, etc.)
        │   │   ├── live/            # Live Dashboard Komponenten
        │   │   │   ├── EnergieFluss.tsx           # Animiertes SVG-Diagramm (Kern)
        │   │   │   ├── EnergieFlussBackground.tsx # SVG Hintergrund + Animationen
        │   │   │   ├── EnergieBilanz.tsx          # Gespiegelte Balken
        │   │   │   ├── TagesverlaufChart.tsx # 24h-Chart
        │   │   │   └── WetterWidget.tsx     # Wetter IST/Prognose
        │   │   ├── sensor-mapping/  # Sensor-Wizard Steps
        │   │   └── setup-wizard/    # Ersteinrichtung
        │   │
        │   ├── pages/
        │   │   ├── LiveDashboard.tsx        # Echtzeit-Monitoring
        │   │   ├── AktuellerMonat.tsx       # Laufender Monat
        │   │   ├── Dashboard.tsx            # Cockpit
        │   │   ├── Auswertung.tsx           # Analysen (6 Tabs)
        │   │   ├── CommunityVergleich.tsx   # Community (6 Tabs)
        │   │   ├── Aussichten.tsx           # Prognosen (4 Tabs)
        │   │   ├── MqttInboundSetup.tsx     # MQTT-Inbound Einrichtung
        │   │   ├── MonatsabschlussWizard.tsx
        │   │   ├── SensorMappingWizard.tsx
        │   │   ├── HAStatistikImport.tsx
        │   │   ├── CloudImportWizard.tsx
        │   │   ├── CustomImportWizard.tsx
        │   │   ├── DataImportWizard.tsx     # Portal-Import
        │   │   ├── DatenChecker.tsx         # Datenqualität
        │   │   ├── Settings.tsx             # Einstellungen
        │   │   ├── PVAnlageDashboard.tsx    # PV-Anlage
        │   │   ├── SpeicherDashboard.tsx    # Speicher
        │   │   ├── BalkonkraftwerkDashboard.tsx
        │   │   ├── SonstigesDashboard.tsx
        │   │   └── auswertung/             # Tab-Komponenten
        │   │       ├── EnergieTab.tsx
        │   │       ├── KomponentenTab.tsx
        │   │       ├── FinanzenTab.tsx
        │   │       └── InvestitionenTab.tsx
        │   │
        │   ├── hooks/               # React Hooks
        │   └── config/              # Version, etc.
        └── dist/                    # Production Build
```

---

## Datenbank

- **Typ:** SQLite
- **Pfad:** `/data/eedc.db`
- **Schema:** Wird beim ersten Start automatisch erstellt

Für Schema-Änderungen:

1. Model in `backend/models/` anpassen
2. Backend neu starten (Schema wird automatisch aktualisiert)

**Hinweis:** SQLAlchemy fügt neue Spalten nicht automatisch zu bestehenden Tabellen hinzu. Bei neuen Spalten manuell `ALTER TABLE` ausführen oder die DB neu erstellen.

Die `parameter` JSON-Spalte in `investitionen` wird automatisch erweitert (kein ALTER TABLE nötig).

---

## Tests

```bash
# Backend: Syntax-Check (kein pytest installiert)
python -c "import ast; ast.parse(open('backend/main.py').read())"

# Frontend: TypeScript Type-Check
cd eedc/frontend && npx tsc --noEmit
```

---

## API Dokumentation

Nach dem Start des Backends verfügbar unter:

| Format       | URL                                    |
| ------------ | -------------------------------------- |
| Swagger UI   | `http://localhost:8099/api/docs`        |
| ReDoc        | `http://localhost:8099/api/redoc`       |
| OpenAPI JSON | `http://localhost:8099/api/openapi.json`|

### API-Routen Übersicht

| Modul              | Prefix               | Beschreibung                                            |
| ------------------ | -------------------- | ------------------------------------------------------- |
| **Live Dashboard** | `/api/live` | Echtzeit-Daten, MQTT-Inbound, Tagesverlauf, Energiefluss |
| **Aktueller Monat** | `/api/aktueller-monat` | Laufender Monat mit Multi-Source-Daten |
| **Cockpit** | `/api/cockpit` | Dashboard-Aggregation, KPIs |
| **Aussichten** | `/api/aussichten` | Prognosen (Kurzfrist, Langfrist, Trend, Finanzen) |
| **Monatsdaten** | `/api/monatsdaten` | CRUD + Berechnungen |
| **Monatsabschluss** | `/api/monatsabschluss` | Wizard mit Datenquellen-Status |
| **Investitionen** | `/api/investitionen` | Komponenten, ROI |
| **Anlagen** | `/api/anlagen` | Anlagen CRUD |
| **Strompreise** | `/api/strompreise` | Tarife, Spezialtarife |
| **Sensor-Mapping** | `/api/sensor-mapping` | HA Sensor-Zuordnung |
| **Import/Export** | `/api/import` | CSV, JSON, Demo, PDF |
| **Portal-Import** | `/api/portal-import` | CSV-Upload (SMA, Fronius, evcc) |
| **Cloud-Import** | `/api/cloud-import` | Cloud-API Import (5 Provider) |
| **Custom-Import** | `/api/custom-import` | CSV/JSON mit Feld-Mapping |
| **Connectors** | `/api/connectors` | 9 Geräte-Connectors |
| **Community** | `/api/community` | Community-Benchmark |
| **Wetter** | `/api/wetter` | Open-Meteo, Bright Sky, PVGIS TMY |
| **PVGIS** | `/api/pvgis` | PVGIS-Daten + Horizontprofil |
| **Solar-Prognose** | `/api/solar-prognose` | Open-Meteo Solar GTI |
| **System** | `/api/system` | Daten-Checker, Logs, Energieprofile |
| **HA Integration** | `/api/ha` | HA-Status, MQTT Export |
| **HA Statistics** | `/api/ha-statistics` | HA-DB Langzeitstatistik (SQLite + MariaDB) |
| **HA Import** | `/api/ha-import` | HA Datenimport |
| **Infothek** | `/api/infothek` | Verträge, Zähler, Dokumente (CRUD + Datei-Upload) |
| **MQTT-Gateway** | `/api/mqtt-gateway` | Topic-Mapping, Geräte-Presets |
| **Scheduler** | `/api/scheduler` | Cron-Jobs, Monatswechsel |

> **Hinweis:** HA-spezifische Routen (`/api/ha*`, `/api/sensor-mapping`, `/api/ha-statistics`) sind nur aktiv wenn `HA_MODE=true`.

---

## Weiterführende Dokumentation

- [Architektur](ARCHITEKTUR.md) - Detaillierte technische Dokumentation
- [Berechnungen](BERECHNUNGEN.md) - Alle Berechnungsformeln und -ketten
- [Benutzerhandbuch](BENUTZERHANDBUCH.md) - Für Endbenutzer
- [Infothek-Handbuch](HANDBUCH_INFOTHEK.md) - Verträge & Dokumente
- [MQTT-Inbound](MQTT_INBOUND.md) - Topic-Struktur und Beispiel-Flows
- [CLAUDE.md](../CLAUDE.md) - KI-Entwicklungskontext

---

*Letzte Aktualisierung: März 2026*
