# eedc - Energie Effizienz Data Center

Home Assistant Add-on zur lokalen Auswertung und Wirtschaftlichkeitsanalyse von PV-Anlagen.

## Features

- **Setup-Wizard** - Geführte Ersteinrichtung (7 Schritte)
- **Lokale Datenspeicherung** - Alle Daten bleiben auf deinem Home Assistant
- **PV-Anlagen Verwaltung** - Stammdaten, Leistung, Standort
- **Multi-Modul PV-Anlagen** - Verschiedene Dachflächen mit individueller Ausrichtung/Neigung
- **Parent-Child Beziehungen** - PV-Module → Wechselrichter, Speicher → Hybrid-WR
- **PVGIS Integration** - Ertragsprognosen pro PV-Modul von der EU-Kommission
- **Prognose vs. IST** - Vergleich der erwarteten mit tatsächlicher Erzeugung
- **Monatsdaten Erfassung** - Manuell oder CSV-Import
- **Personalisierte CSV-Vorlagen** - Dynamische Spalten basierend auf Investitionen
- **Umfassende Auswertungen** - Autarkie, Eigenverbrauch, Wirtschaftlichkeit, Jahresvergleich
- **Investitions-Tracking** - E-Auto, Wärmepumpe, Speicher, Wallbox, PV-Module, Balkonkraftwerk
- **ROI-Dashboard** - Amortisationsberechnung für alle Investitionen
- **HA Sensor Export** - Berechnete KPIs zurück an Home Assistant (REST API oder MQTT Discovery)
- **HA Auto-Discovery** - Erkennung von Geräten (nur für Ersteinrichtung)
- **Dark Mode** - Vollständige Unterstützung

## Aktueller Status (v0.9.3 Beta)

**Was funktioniert:**
- ✅ **Setup-Wizard** (7 Schritte)
- ✅ Anlagen, Monatsdaten, Strompreise, Investitionen (CRUD)
- ✅ **CSV-Import/Export** (personalisierte Spalten basierend auf Investitionen)
- ✅ Dashboard mit KPIs und Charts
- ✅ **Auswertungen** (5 Tabs: Jahresvergleich, PV-Anlage, Investitionen, Finanzen, CO2)
- ✅ **Jahresvergleich** mit Delta-Indikatoren und Monatsvergleichs-Charts
- ✅ **Investitionen-Tab** mit ROI-Dashboard und Amortisationskurve
- ✅ ROI-Dashboard mit Amortisationsberechnung
- ✅ **PVGIS Integration** (Prognose pro PV-Modul)
- ✅ **Prognose vs. IST** Vergleich
- ✅ **HA Sensor Export** (REST API + MQTT Discovery)
- ✅ **Parent-Child Beziehungen** (PV-Module → Wechselrichter)
- ✅ **HA Auto-Discovery** (nur für Ersteinrichtung)
- ✅ **Dynamische Formulare** (V2H/Arbitrage nur wenn aktiviert)
- ✅ **Monatsdaten Spaltenkonfiguration** (Toggle-Buttons)
- ✅ Settings mit echten DB-Stats
- ✅ Dark Mode
- ✅ Docker-Build
- ✅ **HA Ingress Integration** (nahtlose Sidebar-Integration)
- ✅ **HA Backup** (SQLite in /data Volume)

### v0.9.3 Änderungen

1. **HA Sensor Export** - Berechnete KPIs können an Home Assistant zurückgegeben werden:
   - REST API: Sensoren über `rest` Platform in configuration.yaml
   - MQTT Discovery: Native HA-Entitäten via MQTT Auto-Discovery
   - YAML-Generator für einfache Integration
   - Sensor-Übersicht mit Formeln und aktuellen Werten

2. **Auswertungen neu strukturiert**:
   - Jahresvergleich (Übersicht): Monats-Charts, Δ%-Indikatoren, Jahrestabelle
   - PV-Anlage: Kombinierte Übersicht + PV-Details
   - Investitionen (NEU): ROI-Dashboard, Amortisationskurve, Kosten nach Kategorie
   - Finanzen & CO2: unverändert

3. **SubTabs für Einstellungen**: Bessere Navigation zwischen allen Einstellungs-Seiten

### v0.9.2 Änderungen

- Balkonkraftwerk Dashboard mit optionalem Speicher
- Sonstiges Dashboard (flexible Kategorie: Erzeuger/Verbraucher/Speicher)
- Sonderkosten-Felder für alle Investitionstypen
- Demo-Daten erweitert

### v0.9.1 Änderungen

- Zentrale Versionskonfiguration
- Dynamische Formularfelder
- PV-Module mit Anzahl/Leistung
- Monatsdaten-Spalten konfigurierbar

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

## Konfiguration

### Sensor-Import (optional)

In den Add-on Optionen können Home Assistant Sensoren für den Datenimport zugeordnet werden:

```yaml
ha_sensors:
  pv_erzeugung: sensor.fronius_pv_energy_total
  einspeisung: sensor.grid_export_energy
  netzbezug: sensor.grid_import_energy
  batterie_ladung: sensor.battery_charge_energy
  batterie_entladung: sensor.battery_discharge_energy
```

### MQTT Export (optional)

Für den Export berechneter KPIs an Home Assistant via MQTT:

```yaml
mqtt:
  enabled: true
  host: core-mosquitto
  port: 1883
  username: ""
  password: ""
  auto_publish: false
  publish_interval_minutes: 60
```

---

## Entwicklung

### Voraussetzungen

- Python 3.11+
- Node.js 18+
- Docker/Podman (optional, für Container-Tests)

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

### Docker/Podman Build & Test

```bash
cd eedc

# Build
docker build -t eedc-test .
# oder: podman build -t eedc-test .

# Run
docker run -p 8099:8099 -v $(pwd)/data:/data eedc-test
# oder: podman run -p 8099:8099 -v $(pwd)/data:/data eedc-test
```

App: http://localhost:8099

---

## Projektstruktur

```
eedc-homeassistant/
├── CLAUDE.md               # Kontext für Claude Code (KI-Entwicklung)
├── README.md               # Diese Datei
├── docs/
│   └── DEVELOPMENT.md      # Entwickler-Dokumentation
└── eedc/                   # Das Add-on
    ├── config.yaml         # HA Add-on Konfiguration
    ├── Dockerfile          # Multi-Stage Build
    ├── run.sh              # Container Startscript
    ├── backend/            # Python FastAPI Backend
    │   ├── main.py
    │   ├── requirements.txt
    │   ├── api/routes/     # API Endpoints
    │   ├── core/           # Config, DB, Calculations
    │   ├── models/         # SQLAlchemy Models
    │   └── services/       # HA Export, MQTT Client
    └── frontend/           # React Vite Frontend
        ├── package.json
        └── src/
            ├── api/        # API Client
            ├── components/ # UI Components
            ├── pages/      # Seiten
            └── hooks/      # React Hooks
```

## Unterstützte Geräte (Auto-Discovery)

**Wechselrichter:** SMA, Fronius, Kostal, Huawei/FusionSolar, Growatt, SolaX, Sungrow, GoodWe, Enphase

**Wärmepumpen:** Viessmann, Daikin, Vaillant, Bosch, Mitsubishi, Panasonic, Stiebel Eltron, Nibe, Alpha Innotec, Lambda, iDM, Toshiba, LG

**Balkonkraftwerke:** EcoFlow, Hoymiles, Anker SOLIX, APSystems, Deye, OpenDTU/AhoyDTU

**E-Autos & Wallboxen:** evcc (höchste Priorität), Smart, Wallbox (native Integration)

## Roadmap

- [x] Phase 0: Projekt-Setup ✅
- [x] Phase 1: MVP (Grundfunktionen) ✅
- [x] Phase 2: Erweiterte Features (HA Energy Import, Auto-Discovery, Setup-Wizard, PVGIS, HA Export) ✅
- [ ] Phase 3: PDF-Export, KI-Insights, Wetter-Integration

## Lizenz

MIT License - siehe [LICENSE](LICENSE)

## Ursprung

Basiert auf dem Konzept der [EEDC-WebApp](https://github.com/supernova1963/eedc-webapp), reimplementiert als lokale Home Assistant Lösung.
