# EEDC - Energie Effizienz Data Center

Standalone PV-Analyse-Software.

## Features

- **PV-Anlagen-Management** - Wechselrichter, PV-Module, Speicher, E-Auto, Wärmepumpe, Wallbox
- **Monatliche Auswertung** - Eigenverbrauchsquote, Autarkiegrad, ROI-Analyse
- **Prognosen** - Kurzfristig (Wetter), Langfristig (PVGIS), Trend-Analyse, Finanz-Prognose
- **Multi-Provider Wetter** - DWD (Bright Sky), Open-Meteo, PVGIS
- **Community-Benchmark** - Anonymer Vergleich auf [energy.raunet.eu](https://energy.raunet.eu)
- **Social-Media-Textvorlage** - Kopierfertige Monatsübersicht für Twitter/X und Facebook
- **Cloud-Provider** *(geplant)* - Automatische Datenerfassung via Hersteller-APIs (SMA)
- **Import/Export** - CSV, JSON, PDF-Berichte

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
