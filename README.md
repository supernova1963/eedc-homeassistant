# EEDC - Energie Effizienz Data Center

Home Assistant Add-on zur lokalen Auswertung und Wirtschaftlichkeitsanalyse von PV-Anlagen.

## Features

- **Lokale Datenspeicherung** - Alle Daten bleiben auf deinem Home Assistant
- **PV-Anlagen Verwaltung** - Stammdaten, Leistung, Standort
- **Multi-Modul PV-Anlagen** - Verschiedene Dachflächen mit individueller Ausrichtung/Neigung
- **PVGIS Integration** - Automatische Ertragsprognosen von der EU-Kommission
- **Prognose vs. IST** - Vergleich der erwarteten mit tatsächlicher Erzeugung
- **Monatsdaten Erfassung** - Manuell oder CSV-Import
- **Umfassende Auswertungen** - Autarkie, Eigenverbrauch, Wirtschaftlichkeit
- **Investitions-Tracking** - E-Auto, Wärmepumpe, Speicher, Wallbox, PV-Module
- **ROI-Dashboard** - Amortisationsberechnung für alle Investitionen
- **Home Assistant Integration** - Import aus HA Energy Dashboard (aktuelle Monate)
- **Dark Mode** - Vollständige Unterstützung

## Aktueller Status

| Phase | Status | Fortschritt |
|-------|--------|-------------|
| Phase 0: Setup | ✅ | 6/6 |
| Phase 1: MVP | ✅ | 19/19 |
| Phase 2: Erweitert | 🔄 | 11/16 |

**Was funktioniert (getestet in Home Assistant):**
- ✅ Anlagen, Monatsdaten, Strompreise, Investitionen (CRUD)
- ✅ CSV-Import (mit automatischer Trennzeichen-Erkennung)
- ✅ Dashboard mit KPIs und Charts
- ✅ Auswertung (4 Tabs: Übersicht, PV, Finanzen, CO2)
- ✅ ROI-Dashboard mit Amortisationsberechnung
- ✅ **PVGIS Integration** (EU API für Ertragsprognosen)
- ✅ **Prognose vs. IST** Vergleich
- ✅ **PV-Module als Investitionen** (Multi-Dach-Unterstützung)
- ✅ **HA Energy Import** (aktuelle Monate aus HA History)
- ✅ Settings mit echten DB-Stats und Sensor-Mapping
- ✅ Dark Mode
- ✅ Docker-Build
- ✅ **HA Ingress Integration** (nahtlose Sidebar-Integration)
- ✅ **HA Backup** (SQLite in /data Volume)

**Bekannte Einschränkung:**
- ⚠️ HA-Import nur für aktuelle Monate (~10 Tage History) - ältere Daten via CSV importieren

## Installation

### Über Home Assistant Add-on Store

1. Füge dieses Repository zu deinen Add-on Repositories hinzu:
   ```
   https://github.com/supernova1963/eedc-homeassistant
   ```
2. Suche nach "EEDC" im Add-on Store
3. Klicke auf "Installieren"
4. Starte das Add-on

---

## Entwicklung

### Voraussetzungen

- Python 3.11+
- Node.js 18+
- Docker (optional)

### Schnellstart

```bash
# 1. Repository klonen
git clone git@github.com:supernova1963/eedc-homeassistant.git
cd eedc-homeassistant

# 2. Backend einrichten
cd eedc/backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. Frontend einrichten
cd ../frontend
npm install
```

### Entwicklungsserver starten

**Terminal 1 - Backend:**
```bash
cd eedc/backend
source venv/bin/activate
uvicorn backend.main:app --reload --port 8099
```

**Terminal 2 - Frontend (Dev-Mode mit Hot-Reload):**
```bash
cd eedc/frontend
npm run dev
```

Frontend: http://localhost:5173 (Proxy zu Backend)
API Docs: http://localhost:8099/api/docs

### Production Build

```bash
cd eedc/frontend
npm run build
```

### Docker Build & Test

```bash
cd eedc
docker build -t eedc-test .
docker run -p 8099:8099 -v $(pwd)/data:/data eedc-test
```

App: http://localhost:8099

---

## Konfiguration

Nach der Installation kannst du in den Add-on Optionen deine Home Assistant Sensoren zuordnen:

```yaml
ha_sensors:
  pv_erzeugung: sensor.fronius_pv_energy_total
  einspeisung: sensor.grid_export_energy
  netzbezug: sensor.grid_import_energy
  batterie_ladung: sensor.battery_charge_energy
  batterie_entladung: sensor.battery_discharge_energy
```

## Projektstruktur

```
eedc-homeassistant/
├── PROJEKTPLAN.md          # Detaillierte Architektur & Roadmap
├── README.md               # Diese Datei
└── eedc/                   # Das Add-on
    ├── config.yaml         # HA Add-on Konfiguration
    ├── Dockerfile          # Multi-Stage Build
    ├── run.sh              # Container Startscript
    ├── backend/            # Python FastAPI Backend
    │   ├── main.py
    │   ├── requirements.txt
    │   ├── api/routes/     # API Endpoints
    │   ├── core/           # Config, DB, Calculations
    │   └── models/         # SQLAlchemy Models
    └── frontend/           # React Vite Frontend
        ├── package.json
        └── src/
            ├── api/        # API Client
            ├── components/ # UI Components
            ├── pages/      # Seiten
            └── hooks/      # React Hooks
```

## Roadmap

Siehe [PROJEKTPLAN.md](PROJEKTPLAN.md) für Details.

- [x] Phase 0: Projekt-Setup ✅
- [x] Phase 1: MVP (Grundfunktionen) ✅
- [ ] Phase 2: Erweiterte Features (HA Energy Import, Investitions-Dashboards, PDF-Export, **PVGIS ✅**)
- [ ] Phase 3: KI-Insights, Wetter-Integration

## Lizenz

MIT License - siehe [LICENSE](LICENSE)

## Ursprung

Basiert auf dem Konzept der [EEDC-WebApp](https://github.com/supernova1963/eedc-webapp), reimplementiert als lokale Home Assistant Lösung.
