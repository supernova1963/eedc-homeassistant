# EEDC - Energie Effizienz Data Center

Standalone PV-Analyse-Software mit optionalem Live-Monitoring.

## Features

- **Live Dashboard** - Echtzeit-Energiefluss mit animiertem SVG-Diagramm, SoC-Gauges, Tagesverlauf, Wetter-Prognose
- **MQTT-Inbound** - Universelle Datenbrücke für jedes Smarthome-System (HA, Node-RED, ioBroker, FHEM, openHAB). Auch als Alternative für HA-Nutzer mit MariaDB/MySQL statt SQLite als Recorder-DB.
- **Aktueller Monat** - Live-Cockpit mit Energie-Bilanz, Vorjahresvergleich und Datenquellen-Indikatoren
- **PV-Anlagen-Management** - Wechselrichter, PV-Module, Speicher, E-Auto, Wärmepumpe, Wallbox, BKW
- **Monatliche Auswertung** - Eigenverbrauchsquote, Autarkiegrad, ROI-Analyse (6 Tabs + Community)
- **Prognosen** - Kurzfristig (Wetter), Langfristig (PVGIS), Trend-Analyse, Finanz-Prognose
- **Cloud-Import** - SolarEdge, Fronius, Huawei, Growatt, Deye/Solarman + Custom CSV/JSON
- **9 Geräte-Connectors** - SMA, Fronius, go-eCharger, Shelly, OpenDTU, Kostal, sonnenBatterie, Tasmota
- **Community-Benchmark** - Anonymer Vergleich auf [energy.raunet.eu](https://energy.raunet.eu)
- **Steuerliche Features** - Kleinunternehmerregelung, Spezialtarife, Firmenwagen
- **Import/Export** - CSV, JSON, PDF-Berichte

## Empfohlene Nutzung

Datendichte Analyse-App, optimal auf **Desktop**. Smartphone in Standard-Anzeigegröße funktioniert für die Live-Sichten; für tiefere Auswertungen ist ein größerer Bildschirm sinnvoll. Bei stark erhöhtem Anzeigezoom (iOS „Größerer Text", HA-Companion-Seitenzoom über Standard) können einzelne Layouts eng werden.

## Schnellstart

### Mit Docker (empfohlen)

```bash
docker-compose up -d
```

EEDC ist erreichbar unter: http://localhost:8099

### Entwicklung

```bash
# Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8099

# Frontend (separates Terminal)
cd frontend
npm install && npm run dev
```

- Frontend: http://localhost:3000 (Vite Proxy auf Backend)
- API Docs: http://localhost:8099/api/docs

## Architektur

| Komponente | Technologie |
|---|---|
| Backend | FastAPI, SQLAlchemy, SQLite |
| Frontend | React, TypeScript, Vite, Tailwind CSS, Recharts |
| Deployment | Docker, docker-compose |

## Verwandte Projekte

| Repository | Beschreibung |
|---|---|
| [eedc-homeassistant](https://github.com/supernova1963/eedc-homeassistant) | EEDC als Home Assistant Add-on (mit MQTT, HA-Statistik-Import) |
| [eedc-community](https://github.com/supernova1963/eedc-community) | Anonymer Community-Benchmark-Server |

## Lizenz

Dieses Projekt ist für private Nutzung bestimmt.
