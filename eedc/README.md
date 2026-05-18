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

## ⚠️ Sicherheit: Standalone-Modus ist für LAN-Betrieb gedacht

Die Standalone-Distribution (dieser Container, `docker-compose up`) bietet **keine eigene Authentifizierung** auf der HTTP-API. Anders als die Home-Assistant-Add-on-Variante (die hinter dem HA-Ingress-Auth-Proxy läuft) wird der Port `8099` direkt vom Container an das Host-LAN exponiert.

**Daraus folgt:**

- ✅ Betrieb im **eigenen, vertrauenswürdigen LAN** (Heimnetz hinter Router-Firewall) ist der gedachte Anwendungsfall.
- ❌ **Niemals direkt ins Internet exponieren** — kein Port-Forwarding auf 8099, keine Cloudflare-Tunnel ohne Auth-Layer davor, kein Reverse-Proxy ohne Basic-Auth oder mTLS.
- ⚠️ **In geteilten Netzen vorsichtig** (Gäste-WLAN, WG, Co-Working): wer im selben Subnetz ist, erreicht die API. Cloud-Credentials und Anlagendaten sind damit ohne Auth lesbar.

**Wer Internet-Zugriff braucht** (Auth selbst beistellen, das ist das Anwender-Setup):

- VPN ins Heimnetz (WireGuard, Tailscale) ist der einfachste und sicherste Weg.
- Reverse-Proxy mit Basic-Auth / OAuth2-Proxy / Cloudflare Access / Tailscale Funnel davor. Das ist gelöstes Problem mit Standard-Tooling — wir bauen keinen eigenen Auth-Layer im Container nach.
- Oder: die Home-Assistant-Add-on-Variante installieren — dann übernimmt der HA-Ingress die Auth.

**LAN-Only, niemals ungeschützt ins Internet** — auch wenn die HTTPS-Verbindung TLS-verschlüsselt wäre, fehlt ohne Auth davor die Zugriffskontrolle.

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
