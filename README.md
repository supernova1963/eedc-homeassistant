<p align="center">
  <img src="https://raw.githubusercontent.com/supernova1963/eedc-homeassistant/main/docs/images/eedc-logo-full.png" alt="eedc Logo" width="400">
</p>

<p align="center">
  <strong>Dokumentationsstand 4.0.0</strong> | Standalone PV-Analyse mit optionaler Home Assistant Integration
</p>

<p align="center">
  <a href="https://github.com/supernova1963/eedc-homeassistant/releases/latest"><img src="https://img.shields.io/github/v/release/supernova1963/eedc-homeassistant" alt="Aktuelles Release"></a>
  <a href="https://github.com/supernova1963/eedc-homeassistant/releases/latest"><img src="https://img.shields.io/github/release-date/supernova1963/eedc-homeassistant" alt="Release-Datum"></a>
  <a href="https://supernova1963.github.io/eedc-homeassistant/"><img src="https://img.shields.io/badge/Website-GitHub%20Pages-blue" alt="Website"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

---

## Was ist eedc?

**eedc** (Energie Effizienz Data Center) ist eine lokale Anwendung zur umfassenden Auswertung und Wirtschaftlichkeitsanalyse von Photovoltaik-Anlagen. Die Software läuft standalone oder als Home Assistant App und speichert alle Daten lokal.

### Warum eedc?

- **Keine Cloud-Abhängigkeit** – Alle Daten bleiben auf deinem Server
- **Standalone-fähig** – Funktioniert ohne Home Assistant
- **Echtzeit-Monitoring** – Live Dashboard mit animiertem Energiefluss
- **Universelle Anbindung** – MQTT-Inbound für jedes Smarthome-System
- **Umfassende Analyse** – Von Energiebilanz bis ROI-Berechnung
- **Multi-Komponenten** – PV-Anlage, Speicher, E-Auto, Wärmepumpe, Wallbox, Balkonkraftwerk

---

## Die Oberfläche: drei Achsen

eedc sortiert alle Funktionen nach drei einfachen Fragen. Alle Daten bleiben erhalten, alte Lesezeichen werden umgeleitet.

| Achse | Frage | Inhalt |
|---|---|---|
| **Cockpit** | Wann? | Zeit-Achse: Live · Tag · Monat · Jahr/Gesamt · Aussicht |
| **Komponenten** | Was? | Deine Geräte, je Status → Verlauf → Vergleich → Wirtschaftlichkeit |
| **Auswertungen** | Wie ausgewertet? | Anlagenweite Schnitte: Finanzen · ROI · Prognose-vs-IST · CO₂ · Tabelle |

---

## Empfohlene Nutzung

eedc ist eine **datendichte Analyse-App** — viele KPIs nebeneinander, feinachsige Charts, Tabellen mit vielen Spalten. Optimal nutzbar auf **Desktop**. Smartphone in Standard-Anzeigegröße funktioniert für Live-Dashboard und einfache Sichten; für die datendichten Auswertungs-Bereiche ist ein größerer Bildschirm sinnvoll. Bei stark erhöhtem Anzeigezoom (iOS „Größerer Text", HA-Companion-Seitenzoom über Standard) können einzelne Layouts eng werden.

---

## Features

### Cockpit – Die Zeit-Achse

Ein Aufbau, fünf Zeitfenster (Kennzahlen oben, Verlauf/Energiefluss in der Mitte, Komponenten-Sektionen darunter):

- **Live** – animiertes Energiefluss-Diagramm (SVG mit Flusslinien, SoC-Pegelanzeige, Tages-kWh-Tooltips), 24h-Tagesverlauf mit PV/Verbrauch/Netz/Speicher, Wetter-Widget mit IST/Prognose-Overlay, Heute/Gestern-kWh je Komponente. Demo-Modus für Erstnutzer ohne Sensoren.
- **Tag** – jeden einzelnen Tag mit Stundenverlauf und Tagesbilanz durchblättern (auch historisch).
- **Monat** – Energie-Bilanz mit Datenquellen-Indikatoren pro Feld, Vorjahres- und SOLL/IST-Vergleich, Finanz-Überblick je Komponente, Social-Media-Textvorlage.
- **Jahr / Gesamt** – Hero-Leiste (Top-KPIs + Jahres-Trend), Energie-Fluss-Diagramm, Ring-Gauges, Sparklines, Amortisations-Fortschrittsbalken und Jahres-Rendite je Investition, Formel-Tooltips.
- **Aussicht** – 14-Tage-Kurzfristprognose (Open-Meteo, mehrere Wettermodelle: ICON-CH2/D2/EU, ECMWF IFS, auto), 12-Monats-Langfristprognose (PVGIS + Performance-Ratio), Trend-Analyse mit Degradations- und Saison-Erkennung, Finanzprognose bis zur Amortisation.

### Komponenten – Deine Geräte

Jedes Gerät mit fester Gliederung **Status → Verlauf → Vergleich → Wirtschaftlichkeit** – die früheren Geräte-Dashboards und Geräte-Tabs sind hier zusammengeführt:

- **PV-Anlage** – SOLL-IST-Vergleich pro String, Degradationsanalyse, spezifischer Ertrag, Performance Ratio
- **Speicher** – Lade-/Entladezyklen, Netzladungsanteil und -kosten, Kapazität, Wirkungsgrad
- **Wärmepumpe** – COP/JAZ/SCOP, Heiz- vs. Warmwasseranteil, Kompressor-Starts
- **E-Auto** – Fahrleistung, PV-Ladeanteil, V2H-Entladung, Firmenwagen-Unterstützung
- **Wallbox** – geladene Energie, PV-Anteil, Ladekosten
- **Balkonkraftwerk & sonstige Erzeuger** – fließen in Autarkie und Eigenverbrauch ein

### Auswertungen – Analytische Schnitte über die Anlage

Anlagenweite Auswertungen (Geräte-Details liegen unter *Komponenten*):

- **Finanzen** – T-Konto mit wählbarem Zeitraum: Erträge · Einsparungen · Aufwendungen · Saldo je Komponente, inkl. „Ergebnis nach Stromrechnung"
- **ROI** – Amortisationskurve und Parent-Child-Aggregation, Realisierungsquote (Prognose vs. Realität)
- **Prognose vs. IST** – Genauigkeits-Vergleich der Prognosequellen (Open-Meteo / eedc kalibriert / Solcast) gegen den IST-Ertrag, mit MAE und Bias
- **CO₂** – vermiedene Emissionen über die ganze Anlage (PV-Eigenverbrauch, Wärmepumpe, E-Mobilität)
- **Tabelle (Energie-Explorer)** – alle 22 Monatsspalten sortierbar, Spaltenauswahl per localStorage, Vorjahresvergleich mit Δ-Farbkodierung, CSV/JSON-Export

### Du gestaltest jede Sicht selbst

- **Blöcke verschieben** (↑/↓), **Fokus/Vollbild** (⤢), **Einklappen** (⌄)
- **Parkplatz** – nicht benötigte Anzeigen per Langdruck/Rechtsklick auf den Parkplatz legen; jederzeit zurückholbar, nichts geht verloren
- eedc merkt sich deine Anordnung pro Sicht

### MQTT-Inbound – Universelle Datenbrücke

- **Jedes Smarthome-System** – HA, Node-RED, ioBroker, FHEM, openHAB
- **HA Automation Generator** – Wizard erstellt fertige YAML-Automationen
- **Energy → Monatsdaten** – MQTT-Energiedaten als Vorschläge (Konfidenz 91%)

### Datenquellen – Geräte direkt anbinden

- **Ein Feld, eine Quelle** – jedem eedc-Feld genau eine Quelle zuordnen (HA-Sensor, MQTT-Topic oder Geräte-Connector), mit Sensor-Suche, Themen-Baum, Vorzeichen-Invertierung und Prüfung je Feld
- **Geräte-Presets** – vordefinierte Mappings für gängige Geräte (Shelly, OpenDTU, Tasmota, ...)
- **9 Geräte-Connectors** – SMA ennexOS, SMA WebConnect, Fronius, go-eCharger, Shelly, OpenDTU, Kostal, sonnenBatterie, Tasmota SML

### Datenerfassung – Viele Wege führen nach eedc

- **HA-Statistik** – Direkt aus der HA Recorder-Langzeitstatistik (SQLite **und MariaDB/MySQL**)
- **Cloud-Import** – SolarEdge, Fronius, Huawei, Growatt, Deye/Solarman, EcoFlow PowerOcean
- **Custom-Import** – Beliebige CSV/JSON-Dateien mit flexiblem Feld-Mapping
- **MQTT Energy** – Monatswerte aus MQTT-Topics (91% Konfidenz)
- **Portal-Import** – CSV-Upload von Herstellerportalen (SMA Sunny Portal, Fronius Solarweb, evcc)
- **Monatsabschluss-Formular** – ein Formular für die monatliche Datenerfassung (Neuanlage und Korrektur), mit Datenquellen-Status
- **Demo-Daten** zum Ausprobieren

### Infothek – Verträge & Dokumente

- **14 Kategorien** mit Vorlagen: Strom-, Gas-, Wasser-, Einspeisevertrag, Versicherung, Wartung, MaStR, ...
- **Datei-Upload** – Fotos (JPEG, PNG, HEIC) und PDFs pro Eintrag, direkt in der Datenbank gespeichert
- **Investitions-Verknüpfung** – Wartungsvertrag → Wechselrichter, Garantie → Speicher, ...
- **PDF-Export** aller Infothek-Einträge für den klassischen Hefter

### Steuerliche Features

- **Kleinunternehmerregelung** – USt auf Eigenverbrauch bei Regelbesteuerung
- **Spezialtarife** – Separate Strompreise für Wärmepumpe und Wallbox
- **Firmenwagen** – Dienstliches Laden mit AG-Erstattung in der ROI-Berechnung
- **Sonstige Positionen** – Flexible Erträge und Ausgaben pro Monat

### Investitions-Management

- **Parent-Child Beziehungen**: PV-Module → Wechselrichter, DC-Speicher → Hybrid-WR
- **Typ-spezifische Parameter**: V2H, Arbitrage, kWp, Ausrichtung, Neigung
- **ROI-Berechnung** pro Komponente und aggregiert

### Community-Vergleich (optional)

- **Anonymer Benchmark** mit anderen PV-Anlagen auf [energy.raunet.eu](https://energy.raunet.eu)
- **Analyse-Sichten**: Übersicht, PV-Ertrag, Komponenten, Regional, Statistiken
- **Achievements** und Rang-Badges
- Jederzeit löschbar – ein Klick entfernt alle geteilten Daten

---

## Schnellstart

### Option 1: Home Assistant Add-on

1. Repository zu HA Add-ons hinzufügen:
   ```
   https://github.com/supernova1963/eedc-homeassistant
   ```
2. Add-on "eedc" installieren und starten
3. Über die Sidebar öffnen

### Option 2: Standalone mit Docker

```bash
# Standalone-Repository klonen
git clone https://github.com/supernova1963/eedc.git
cd eedc

# Mit Docker Compose starten
docker compose up -d

# Browser öffnen
open http://localhost:8099
```

> **Multi-Arch:** Das Docker-Image steht für `amd64` und `arm64` (Raspberry Pi 4/5, Apple Silicon) bereit.

> **Hinweis:** Das Standalone-Deployment nutzt das eigenständige [eedc Repository](https://github.com/supernova1963/eedc).

### Option 3: Lokale Entwicklung

```bash
# Backend starten
cd eedc && source backend/venv/bin/activate
uvicorn backend.main:app --reload --port 8099

# Frontend starten (neues Terminal)
cd eedc/frontend && npm run dev

# Browser öffnen
open http://localhost:3000
```

---

## Dokumentation

> **Tipp:** Die Dokumentation ist auch als Website verfügbar: **[supernova1963.github.io/eedc-homeassistant](https://supernova1963.github.io/eedc-homeassistant/)**

| Dokument | Beschreibung |
|----------|--------------|
| [Benutzerhandbuch](https://github.com/supernova1963/eedc-homeassistant/blob/main/docs/BENUTZERHANDBUCH.md) | Vollständige Anleitung für Endbenutzer |
| [Infothek-Handbuch](https://github.com/supernova1963/eedc-homeassistant/blob/main/docs/HANDBUCH_INFOTHEK.md) | Verträge, Zähler & Dokumente verwalten |
| [Architektur](https://github.com/supernova1963/eedc-homeassistant/blob/main/docs/ARCHITEKTUR.md) | Technische Dokumentation für Entwickler |
| [Changelog](https://github.com/supernova1963/eedc-homeassistant/blob/main/CHANGELOG.md) | Versionshistorie und Änderungen |
| [Entwicklung](https://github.com/supernova1963/eedc-homeassistant/blob/main/docs/DEVELOPMENT.md) | Setup für lokale Entwicklung |

---

## Screenshots

### Cockpit
Die Zeit-Achse zeigt alle wichtigen KPIs auf einen Blick:
- Energiebilanz (Erzeugung, Verbrauch, Einspeisung)
- Effizienz-Kennzahlen (Autarkie, Eigenverbrauchsquote)
- Komponenten-Status (Speicher, E-Auto, Wärmepumpe)
- Finanzielle Auswertung (Einsparungen, ROI)
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/supernova1963/eedc-homeassistant/main/docs/images/cockpit_main-dark.png">
  <img src="https://raw.githubusercontent.com/supernova1963/eedc-homeassistant/main/docs/images/cockpit_main.png" alt="eedc Cockpit">
</picture>

### Komponenten
Jedes Gerät mit fester Gliederung Status → Verlauf → Vergleich → Wirtschaftlichkeit:
- PV-String-Performance nach Ausrichtung
- Speicher-Zyklen und Netzladungsanteil
- Wärmepumpen-JAZ und E-Auto-Bilanz
- Amortisationskurven für alle Investitionen
<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/supernova1963/eedc-homeassistant/main/docs/images/komponenten_speicher-dark.png">
  <img src="https://raw.githubusercontent.com/supernova1963/eedc-homeassistant/main/docs/images/komponenten_speicher.png" alt="eedc Komponenten – Speicher">
</picture>

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
│              Externe APIs / Datenquellen                │
│  Open-Meteo │ PVGIS │ MQTT │ HA │ Cloud-APIs │ Connectors│
└─────────────────────────────────────────────────────────┘
```

---

## Repositories

| Repository | Zweck |
|---|---|
| **[eedc-homeassistant](https://github.com/supernova1963/eedc-homeassistant)** (dieses) | Source of Truth: HA-Add-on + Website + Dokumentation |
| **[eedc](https://github.com/supernova1963/eedc)** | Standalone-Distribution (wird per Release-Script synchronisiert) |
| **[eedc-community](https://github.com/supernova1963/eedc-community)** | Anonymer Community-Benchmark-Server |

---

## Home Assistant Integration

eedc bietet flexible Home Assistant Integration mit mehreren Ansätzen:

### Datenquellen (Empfohlen)

Unter **Einstellungen → Datenquellen** ordnest du jedem eedc-Feld genau eine Quelle zu – eine Fläche statt zweier Wizards:
- Basis-Felder: PV-Erzeugung, Einspeisung, Netzbezug, Außentemperatur
- PV-Module: Pro String oder kWp-Verteilung
- Speicher: Ladung, Entladung, Netz-Ladung
- E-Auto: km, Ladung (PV/Netz/Extern), V2H
- Wärmepumpe: Strom, Heizung (COP-Berechnung möglich)
- **Quelle je Feld**: HA-Sensor, MQTT-Topic oder Geräte-Connector
- **Vorzeichen-Inversion** pro Feld (bei bidirektionalen Sensoren)
- **Prüfung je Feld** zeigt Probleme (falsche Einheit, fehlende Statistik …) direkt an

### MQTT-Inbound (Universell)

Über vordefinierte MQTT-Topics kann jedes Smarthome-System Daten liefern:
- Integrierter **HA Automation Generator** erstellt fertige YAML-Automationen
- Beispiel-Flows für Node-RED, ioBroker, FHEM, openHAB
- Auch für HA-Nutzer mit **MariaDB/MySQL** als Recorder-DB empfohlen
- **Ein Broker für beide Richtungen** (Empfangen + Export) – Richtungs-Schalter unter *Einstellungen → Integration*

### Monatlicher Abschluss

Der **Monatsabschluss** ist ein Formular für die monatliche Datenerfassung:
- Automatische Vorschläge aus HA-Statistik, MQTT, Connectors, Vormonat oder Vorjahr
- COP-basierte Berechnungen für Wärmepumpen
- Datenquellen-Status mit Konfidenz-Anzeige

---

## Beitragen

Beiträge sind willkommen! Bitte lies zuerst die [Entwickler-Dokumentation](https://github.com/supernova1963/eedc-homeassistant/blob/main/docs/DEVELOPMENT.md).

---

## Lizenz

MIT License - siehe [LICENSE](https://github.com/supernova1963/eedc-homeassistant/blob/main/LICENSE)

---

*Erstellt mit Leidenschaft fuer die Energiewende*
