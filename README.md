# eedc - Energie Effizienz Data Center

Home Assistant Add-on zur lokalen Auswertung und Wirtschaftlichkeitsanalyse von PV-Anlagen.

## Features

- **Setup-Wizard** - Geführte Ersteinrichtung (7 Schritte, vereinfacht in v0.9)
- **Lokale Datenspeicherung** - Alle Daten bleiben auf deinem Home Assistant
- **PV-Anlagen Verwaltung** - Stammdaten, Leistung, Standort
- **Multi-Modul PV-Anlagen** - Verschiedene Dachflächen mit individueller Ausrichtung/Neigung
- **Parent-Child Beziehungen** - PV-Module → Wechselrichter, Speicher → Hybrid-WR (v0.9)
- **PVGIS Integration** - Ertragsprognosen pro PV-Modul von der EU-Kommission
- **Prognose vs. IST** - Vergleich der erwarteten mit tatsächlicher Erzeugung
- **Monatsdaten Erfassung** - Manuell oder CSV-Import
- **Personalisierte CSV-Vorlagen** - Dynamische Spalten basierend auf Investitionen (v0.9)
- **Umfassende Auswertungen** - Autarkie, Eigenverbrauch, Wirtschaftlichkeit
- **Investitions-Tracking** - E-Auto, Wärmepumpe, Speicher, Wallbox, PV-Module, Balkonkraftwerk
- **ROI-Dashboard** - Amortisationsberechnung für alle Investitionen
- **HA Auto-Discovery** - Erkennung von Geräten (nur für Ersteinrichtung)
- **Dark Mode** - Vollständige Unterstützung

## Aktueller Status (v0.9.1 Beta)

**Was funktioniert:**
- ✅ **Setup-Wizard** (7 Schritte, vereinfacht)
- ✅ Anlagen, Monatsdaten, Strompreise, Investitionen (CRUD)
- ✅ **CSV-Import/Export** (personalisierte Spalten basierend auf Investitionen)
- ✅ Dashboard mit KPIs und Charts
- ✅ Auswertung (4 Tabs: Übersicht, PV, Finanzen, CO2)
- ✅ ROI-Dashboard mit Amortisationsberechnung
- ✅ **PVGIS Integration** (Prognose pro PV-Modul)
- ✅ **Prognose vs. IST** Vergleich
- ✅ **Parent-Child Beziehungen** (PV-Module → Wechselrichter)
- ✅ **HA Auto-Discovery** (nur für Ersteinrichtung)
- ✅ **Dynamische Formulare** (V2H/Arbitrage nur wenn aktiviert)
- ✅ **Monatsdaten Spaltenkonfiguration** (Toggle-Buttons)
- ✅ Settings mit echten DB-Stats
- ✅ Dark Mode
- ✅ Docker-Build
- ✅ **HA Ingress Integration** (nahtlose Sidebar-Integration)
- ✅ **HA Backup** (SQLite in /data Volume)

**v0.9.1 Änderungen:**
- Zentrale Versionskonfiguration (Frontend + Backend)
- Dynamische Formularfelder (V2H nur bei v2h_faehig, Arbitrage nur bei arbitrage_faehig)
- PV-Module mit Anzahl/Leistung pro Modul für kWp-Berechnung
- Monatsdaten-Tabelle mit konfigurierbaren Spalten (localStorage)
- Fixes: 0-Wert Import, berechnete Felder bei pv_erzeugung=0

**v0.9.0 Änderungen:**
- HA-Monatsdaten-Import entfernt (war zu unzuverlässig)
- Datenerfassung nur noch via CSV oder manuell
- Personalisierte CSV-Vorlagen (Spalten nach Investitions-Bezeichnung)
- Parent-Child Validierung für PV-Module und Speicher

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

## Unterstützte Geräte (Auto-Discovery)

**Wechselrichter:** SMA, Fronius, Kostal, Huawei/FusionSolar, Growatt, SolaX, Sungrow, GoodWe, Enphase

**Wärmepumpen:** Viessmann, Daikin, Vaillant, Bosch, Mitsubishi, Panasonic, Stiebel Eltron, Nibe, Alpha Innotec, Lambda, iDM, Toshiba, LG

**Balkonkraftwerke:** EcoFlow, Hoymiles, Anker SOLIX, APSystems, Deye, OpenDTU/AhoyDTU

**E-Autos & Wallboxen:** evcc (höchste Priorität), Smart, Wallbox (native Integration)

## Roadmap

Siehe [PROJEKTPLAN.md](PROJEKTPLAN.md) für Details.

- [x] Phase 0: Projekt-Setup ✅
- [x] Phase 1: MVP (Grundfunktionen) ✅
- [ ] Phase 2: Erweiterte Features (HA Energy Import ✅, Auto-Discovery ✅, Setup-Wizard ✅, PVGIS ✅, PDF-Export)
- [ ] Phase 3: KI-Insights, Wetter-Integration

## Lizenz

MIT License - siehe [LICENSE](LICENSE)

## Ursprung

Basiert auf dem Konzept der [EEDC-WebApp](https://github.com/supernova1963/eedc-webapp), reimplementiert als lokale Home Assistant Lösung.
