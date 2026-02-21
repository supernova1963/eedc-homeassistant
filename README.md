<p align="center">
  <img src="./docs/images/eedc-logo-full.png" alt="eedc Logo" width="400">
</p>

<p align="center">
  <strong>Version 2.1.0</strong> | Standalone PV-Analyse mit optionaler Home Assistant Integration
</p>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

---

## Was ist eedc?

**eedc** (Energie Effizienz Data Center) ist eine lokale Anwendung zur umfassenden Auswertung und Wirtschaftlichkeitsanalyse von Photovoltaik-Anlagen. Die Software läuft standalone oder als Home Assistant Add-on und speichert alle Daten lokal.

### Warum eedc?

- **Keine Cloud-Abhängigkeit** – Alle Daten bleiben auf deinem Server
- **Standalone-fähig** – Funktioniert ohne Home Assistant
- **Umfassende Analyse** – Von Energiebilanz bis ROI-Berechnung
- **Flexibler Datenimport** – CSV-Import mit dynamischen Spalten
- **Multi-Komponenten** – PV-Anlage, Speicher, E-Auto, Wärmepumpe, Wallbox, Balkonkraftwerk

---

## Features

### Cockpit & Dashboards
- **Aggregierte Übersicht** mit 7 Sektionen (Energie, Effizienz, Speicher, E-Auto, Wärmepumpe, Finanzen, CO2)
- **8 spezialisierte Dashboards** für jede Komponente
- **Formel-Tooltips** zeigen Berechnungsgrundlagen per Hover
- **Jahr-Filter** für mehrjährige Auswertungen

### Auswertungen & Reporting
- **7 Analyse-Tabs**: Energie, PV-Anlage, Komponenten, Finanzen, CO2, Investitionen, Community
- **ROI-Dashboard** mit Amortisationskurve und Parent-Child Aggregation
- **SOLL-IST Vergleich** gegen PVGIS-Prognosen
- **CSV/JSON Export** für externe Weiterverarbeitung
- **Vollständiger JSON-Export** für Support und Backup (NEU)

### Aussichten (Prognosen)
- **4 Prognose-Tabs**: Kurzfristig (7 Tage), Langfristig (12 Monate), Trend-Analyse, Finanzen
- **Kurzfrist-Prognose** mit Wetter-Daten (Open-Meteo)
- **Langfrist-Prognose** mit PVGIS-Daten und Performance-Ratio
- **Trend-Analyse** mit Degradationsberechnung und saisonalen Mustern
- **Finanz-Prognose** mit Amortisations-Fortschritt und Mehrkosten-Ansatz

### Datenerfassung
- **Manuelles Formular** mit dynamischen Komponenten-Feldern
- **CSV-Import** mit personalisierten Spalten und Plausibilitätsprüfung
- **Wetter-Auto-Fill** via Open-Meteo / PVGIS TMY
- **Demo-Daten** zum Ausprobieren
- **Sensor-Mapping-Wizard** - Home Assistant Sensoren den EEDC-Feldern zuordnen
- **Monatsabschluss-Wizard** - Geführte monatliche Datenerfassung mit Vorschlägen
- **HA-Statistik Import** (NEU v2.0.0) - Automatischer Import historischer Monatswerte aus HA

### Investitions-Management
- **Parent-Child Beziehungen**: PV-Module → Wechselrichter, DC-Speicher → Hybrid-WR
- **Typ-spezifische Parameter**: V2H, Arbitrage, kWp, Ausrichtung, Neigung
- **ROI-Berechnung** pro Komponente und aggregiert
- **Erweiterte Stammdaten**: Gerätedaten, Ansprechpartner, Wartungsverträge

### Anlagen-Verwaltung
- **MaStR-ID** mit direktem Link zum Marktstammdatenregister
- **Versorger & Zähler**: Strom, Gas, Wasser mit beliebig vielen Zählern
- **Klappbare Sektionen** für übersichtliche Formulare

### Optionale Home Assistant Integration
- **MQTT Discovery** für native HA-Sensoren
- **REST API** für configuration.yaml
- **Berechnete KPIs** zurück an HA exportieren
- **Sensor-Mapping** - Flexible Zuordnung von HA-Sensoren zu EEDC-Feldern
- **Automatische Vorschläge** - Intelligente Werte aus Vormonat, Vorjahr, oder Berechnung
- **HA-Statistik Import** (NEU v2.0.0) - Bulk-Import historischer Daten aus HA-Langzeitstatistik

---

## Schnellstart

### Option 1: Home Assistant Add-on

1. Repository zu HA Add-ons hinzufügen:
   ```
   https://github.com/supernova1963/eedc-homeassistant
   ```
2. Add-on "EEDC" installieren und starten
3. Über die Sidebar öffnen

### Option 2: Standalone mit Docker

```bash
# Image bauen
cd eedc
docker build -t eedc .

# Container starten
docker run -p 8099:8099 -v $(pwd)/data:/data eedc

# Browser öffnen
open http://localhost:8099
```

### Option 3: Lokale Entwicklung

```bash
# Backend starten
cd eedc && source backend/venv/bin/activate
uvicorn backend.main:app --reload --port 8099

# Frontend starten (neues Terminal)
cd eedc/frontend && npm run dev

# Browser öffnen
open http://localhost:5173
```

---

## Dokumentation

| Dokument | Beschreibung |
|----------|--------------|
| [Benutzerhandbuch](docs/BENUTZERHANDBUCH.md) | Vollständige Anleitung für Endbenutzer |
| [Architektur](docs/ARCHITEKTUR.md) | Technische Dokumentation für Entwickler |
| [Changelog](CHANGELOG.md) | Versionshistorie und Änderungen |
| [Entwicklung](docs/DEVELOPMENT.md) | Setup für lokale Entwicklung |

---

## Screenshots

### Cockpit Übersicht
Die Hauptansicht zeigt alle wichtigen KPIs auf einen Blick:
- Energiebilanz (Erzeugung, Verbrauch, Einspeisung)
- Effizienz-Kennzahlen (Autarkie, Eigenverbrauchsquote)
- Komponenten-Status (Speicher, E-Auto, Wärmepumpe)
- Finanzielle Auswertung (Einsparungen, ROI)
![Cockpit Übersicht](./docs/images/cockpit_main.png)

### Auswertungen
Detaillierte Analysen in 7 Kategorien:
- Jahresvergleich mit Delta-Indikatoren
- PV-String-Performance nach Ausrichtung
- Arbitrage-Analyse für Speicher
- Amortisationskurven für alle Investitionen
![Auswertungen - Komponenten](./docs/images/auswertungen_komponenten.png)
---

## Architektur-Überblick

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (React)                     │
│  Vite + TypeScript + Tailwind CSS + Recharts            │
├─────────────────────────────────────────────────────────┤
│                    Backend (Python)                     │
│  FastAPI + SQLAlchemy 2.0 + SQLite                      │
├─────────────────────────────────────────────────────────┤
│              Externe APIs (optional)                    │
│  Open-Meteo (Wetter) │ PVGIS (Prognose) │ HA (Export)   │
└─────────────────────────────────────────────────────────┘
```

### Datenmodell

```
Anlage (PV-Anlage mit Standort, Ausrichtung)
  │
  ├── Monatsdaten (Zählerwerte: Einspeisung, Netzbezug)
  │
  ├── Strompreise (Bezug, Einspeisung, zeitliche Gültigkeit)
  │
  └── Investitionen (Komponenten)
        │
        ├── Wechselrichter
        │     ├── PV-Module (Pflicht-Zuordnung)
        │     └── DC-Speicher (optional)
        │
        ├── AC-Speicher (eigenständig)
        ├── E-Auto (mit optionalem V2H)
        ├── Wärmepumpe
        ├── Wallbox
        ├── Balkonkraftwerk
        └── Sonstiges
```

---

## Home Assistant Integration

EEDC bietet flexible Home Assistant Integration mit zwei Ansätzen:

### Sensor-Mapping (Empfohlen)
Mit dem **Sensor-Mapping-Wizard** ordnest du deine bestehenden HA-Sensoren den EEDC-Feldern zu:
- Basis-Sensoren: PV-Erzeugung, Einspeisung, Netzbezug
- PV-Module: Pro String oder kWp-Verteilung
- Speicher: Ladung, Entladung, Netz-Ladung
- E-Auto: km, Ladung (PV/Netz/Extern), V2H
- Wärmepumpe: Strom, Heizung (COP-Berechnung möglich)

### Monatlicher Abschluss
Der **Monatsabschluss-Wizard** unterstützt dich bei der monatlichen Datenerfassung:
- Automatische Vorschläge aus Vormonat oder Vorjahr
- COP-basierte Berechnungen für Wärmepumpen
- Durchschnittswerte als Fallback
- Direkte Übernahme oder manuelle Anpassung

---

## Roadmap

- [x] Cockpit mit aggregierter Übersicht
- [x] 8 spezialisierte Dashboards
- [x] ROI-Dashboard mit Amortisationskurve
- [x] SOLL-IST Vergleich gegen PVGIS
- [x] CSV-Import mit dynamischen Spalten
- [x] Wetter-API Integration (Open-Meteo)
- [x] MQTT Export zu Home Assistant
- [x] **Aussichten** mit 4 Prognose-Tabs (Kurzfristig, Langfristig, Trend, Finanzen)
- [x] **Erweiterte Stammdaten** für Anlagen und Investitionen
- [x] **PDF-Export** für vollständige Anlagen-Dokumentation
- [x] **Sensor-Mapping-Wizard** für HA-Integration
- [x] **Monatsabschluss-Wizard** mit intelligenten Vorschlägen
- [x] **Community-Vergleich** - Anonymer Benchmark mit anderen PV-Anlagen
- [x] **Community als Hauptmenü** - Eigener Bereich mit 6 Tabs für tiefgehende Analysen (NEU v2.1.0)
- [ ] KI-gestützte Insights

---

## Beitragen

Beiträge sind willkommen! Bitte lies zuerst die [Entwickler-Dokumentation](docs/DEVELOPMENT.md).

```bash
# Fork erstellen und klonen
git clone git@github.com:YOUR_USERNAME/eedc-homeassistant.git

# Feature-Branch erstellen
git checkout -b feature/mein-feature

# Änderungen committen
git commit -m "feat: Beschreibung der Änderung"

# Pull Request erstellen
```

---

## Lizenz

MIT License - siehe [LICENSE](LICENSE)

---

## Ursprung

Basiert auf dem Konzept der [EEDC-WebApp](https://github.com/supernova1963/eedc-webapp), reimplementiert als lokale Lösung mit optionaler Home Assistant Integration.

---

*Erstellt mit ❤️ für die Energiewende*
