# EEDC – Promotional Texte

Drei Varianten für verschiedene Kanäle.

---

## Variante 1: Reddit (r/homeassistant, r/solar)
*Short, punchy, English. Headline + Bullets + Links*

---

### EEDC – Free, local PV analysis for Home Assistant (and standalone) [v3.1]

I built a Home Assistant add-on that gives you a complete analysis of your PV system – fully local, no cloud, no subscription fees. Major v3 update with real-time monitoring.

**What does it do?**

- **Live Dashboard** – Real-time power monitoring with animated energy flow diagram, SoC gauges, 24h timeline, weather forecast with actual vs. predicted overlay
- **MQTT-Inbound** – Universal data bridge: works with any smart home system (HA, Node-RED, ioBroker, FHEM, openHAB) via standardized MQTT topics. Built-in HA automation generator.
- **Current Month** – Live energy balance from HA statistics, connectors, or MQTT – with data source indicators per field
- **Dashboard** – Hero KPIs with year-over-year trends, energy flow diagram, ring gauges for self-sufficiency & self-consumption, sparklines
- **6 Analysis Tabs + Community** – Energy, PV system, components, finances, CO2, investments + dedicated community section
- **ROI Tracking** – When will your system pay for itself? Progress bar with estimated payback date
- **Multi-Component** – PV, battery storage, EV, heat pump, wallbox, balcony PV
- **Forecasting** – 7-day weather forecast, 12-month PVGIS projection, trend analysis with degradation detection, financial forecast
- **Cloud Import** – Pull historical data from SolarEdge, Fronius, Huawei, Growatt, Deye/Solarman + custom CSV/JSON
- **9 Device Connectors** – SMA, Fronius, go-eCharger, Shelly, OpenDTU, Kostal, sonnenBatterie, Tasmota
- **Community Benchmark** – Anonymous comparison with other PV systems via [live community server](https://energy.raunet.eu) (optional, data deletable anytime)
- **Tax Features** – Small business regulation (Germany), special tariffs for heat pump/wallbox, company car support
- **Standalone** – Also runs without Home Assistant (Docker)
- **DACH Support** – Germany, Austria, Switzerland

**Installation:** Add the repository to your HA add-on store:
```
https://github.com/supernova1963/eedc-homeassistant
```
Search for "EEDC" and install. Demo data loads with one click.

**Links:**
- [Website & Docs](https://supernova1963.github.io/eedc-homeassistant/)
- [GitHub (Add-on)](https://github.com/supernova1963/eedc-homeassistant)
- [GitHub (Community Server)](https://github.com/supernova1963/eedc-community)
- [Releases](https://github.com/supernova1963/eedc-homeassistant/releases)
- [Community Dashboard](https://energy.raunet.eu) – live anonymous PV benchmark

---

## Variante 2: Home Assistant Community Forum
*Ausführlicher, strukturiert, mit Abschnittstiteln. Typischer Forum-Post-Stil.*

---

### EEDC – Energie Effizienz Data Center | PV-Analyse Add-on für Home Assistant

Hallo zusammen,

ich möchte euch mein selbst entwickeltes Home Assistant Add-on vorstellen: **EEDC** (Energie Effizienz Data Center) – eine vollständige Auswertungs- und Wirtschaftlichkeitsplattform für Photovoltaik-Anlagen.

**Kernprinzipien:**
- **Alles lokal** – Keine Cloud, keine Registrierung, alle Daten bleiben bei euch
- **Standalone-fähig** – Funktioniert mit oder ohne Home Assistant
- **Echtzeit + Monatlich** – Live-Leistungsdaten und langfristige Auswertungen in einem Tool

---

#### Live Dashboard (NEU in v3.0)

Echtzeit-Monitoring eurer PV-Anlage:
- **Animiertes Energiefluss-Diagramm** – SVG mit Flusslinien, SoC-Pegelanzeige für Speicher und E-Auto
- **Tagesverlauf** – 24h-Chart mit PV, Verbrauch, Netz, Speicher (auch historisch abrufbar)
- **Wetter-Widget** – Stunden-Prognose mit IST/Prognose-Overlay zum Vergleich
- **Heute/Gestern kWh** – Tagessummen pro Komponente
- **Demo-Modus** für Erstnutzer ohne konfigurierte Sensoren

---

#### MQTT-Inbound – Universelle Datenbrücke (NEU in v3.0)

EEDC ist nicht auf Home Assistant beschränkt. Über vordefinierte MQTT-Topics kann **jedes Smarthome-System** Daten liefern:
- **HA Automation Generator** – Wizard ordnet HA-Sensoren den EEDC-Topics zu und generiert fertige YAML-Automationen
- **Beispiel-Flows** für Node-RED, ioBroker, FHEM, openHAB
- **Energy → Monatsabschluss** – MQTT-Energiedaten als Vorschläge im Monatsabschluss-Wizard (Konfidenz 91%)

---

#### Aktueller Monat

Live-Cockpit für den laufenden Monat:
- **Energie-Bilanz**, Komponenten-Karten, Finanz-Übersicht
- **Vorjahresvergleich** und SOLL/IST-Vergleich
- **Datenquellen-Indikatoren** pro Feld (HA-Statistik, Connector, MQTT, Gespeichert)

---

#### Das Cockpit

Das Dashboard zeigt auf einen Blick:
- **Hero-Leiste** mit den 3 wichtigsten KPIs und Trend-Vergleich zum Vorjahr
- **Energie-Fluss-Diagramm**: Wohin fließt euer PV-Strom? Woher kommt euer Hausverbrauch?
- **Ring-Gauges** für Autarkie und Eigenverbrauchsquote
- **Sparkline** mit monatlichen PV-Erträgen über den gesamten Zeitraum
- **Amortisations-Fortschrittsbalken** mit geschätztem Amortisationsjahr

---

#### Auswertungen (6 Tabs)

| Tab | Inhalt |
|-----|--------|
| **Energie** | Monats-Charts, Jahresvergleich, Delta-Indikatoren |
| **PV-Anlage** | String-Performance, SOLL-IST vs. PVGIS, Degradation |
| **Komponenten** | Speicher-Effizienz, WP-JAZ, E-Auto-Quellen, Wallbox, BKW |
| **Finanzen** | Einspeisung, Einsparungen, Netto-Ertrag, Amortisation |
| **CO2** | Vermiedene Emissionen, Vergleich zu Netzbezug |
| **Investitionen** | ROI pro Komponente, Jahres-Rendite p.a. |

#### Community (eigener Hauptmenüpunkt, 6 Tabs)

Anonymer Benchmark mit anderen PV-Anlagen: Übersicht, PV-Ertrag, Komponenten, Regional, Trends, Statistiken

---

#### Aussichten (4 Prognose-Module)

- **Kurzfristig** – 7-Tage Wetterprognose mit GTI-basierter PV-Erzeugung
- **Langfristig** – 12-Monats-Prognose basierend auf PVGIS-Daten
- **Trend-Analyse** – Degradationserkennung und saisonale Muster
- **Finanzen** – Amortisationsprognose und Finanzplanung bis zum Break-Even

---

#### Datenimport – Viele Wege führen nach EEDC

- **HA-Statistik** – Direkt aus der HA Recorder-Langzeitstatistik (SQLite)
- **Cloud-Import** – SolarEdge, Fronius, Huawei, Growatt, Deye/Solarman
- **Custom-Import** – Beliebige CSV/JSON-Dateien mit flexiblem Feld-Mapping
- **9 Geräte-Connectors** – SMA, Fronius, go-eCharger, Shelly, OpenDTU, Kostal, sonnenBatterie, Tasmota
- **MQTT Energy** – Monatswerte aus MQTT-Topics (91% Konfidenz)
- **Portal-Import** – CSV-Upload von Herstellerportalen (SMA Sunny Portal, Fronius Solarweb, evcc)
- **Manuell** – Geführter Monatsabschluss-Wizard

> **Hinweis für MariaDB/MySQL-Nutzer:** Die HA-Statistik-Funktion liest direkt aus der SQLite-Datenbank. Wer MariaDB oder MySQL als Recorder-Backend nutzt, kann stattdessen **MQTT-Inbound** als gleichwertige Alternative verwenden – der integrierte Automations-Generator erstellt die passenden HA-Automationen automatisch.

---

#### Steuerliche Features

- **Kleinunternehmerregelung** – USt auf Eigenverbrauch bei Regelbesteuerung
- **Spezialtarife** – Separate Strompreise für Wärmepumpe und Wallbox
- **Firmenwagen** – Dienstliches Laden mit AG-Erstattung in der ROI-Berechnung
- **Sonstige Positionen** – Flexible Erträge und Ausgaben pro Monat

---

#### Community-Vergleich (optional)

Wer möchte, kann seine anonymisierten Daten mit der Community teilen. Die Daten werden an den separaten [Community-Server](https://energy.raunet.eu) übertragen ([Open Source](https://github.com/supernova1963/eedc-community)):

- Nur Bundesland/Land wird übertragen – keine Adresse, keine PLZ, kein Rückschluss auf Person
- **6 Analyse-Tabs im Add-on**: Übersicht, PV-Ertrag, Komponenten, Regional, Trends, Statistiken
- **Web-Dashboard**: Schneller Überblick direkt unter [energy.raunet.eu](https://energy.raunet.eu)
- **Achievements** (z.B. Autarkiemeister, Solarprofi) und Rang-Badges (Top 10%)
- **Choropleth-Karte** mit Bundesland-Vergleich und Performance-Metriken
- Jederzeit löschbar – ein Klick entfernt alle geteilten Daten

---

#### Unterstützte Komponenten

PV-Anlage (inkl. String-Vergleich) | Batteriespeicher (AC & DC) | E-Auto (V2H-fähig, Firmenwagen) | Wärmepumpe (JAZ/SCOP/COP) | Wallbox | Balkonkraftwerk | Sonstiges (Erzeuger/Verbraucher/Speicher)

---

#### Installation

1. HA → Einstellungen → Add-ons → Add-on Store → Repositories
2. URL hinzufügen: `https://github.com/supernova1963/eedc-homeassistant`
3. "EEDC" installieren, starten, in Sidebar anzeigen aktivieren
4. Demo-Daten laden (ein Klick) – sofort alle Features ausprobieren

Alternativ als **Docker-Container** ohne HA:
```bash
git clone https://github.com/supernova1963/eedc.git && cd eedc
docker compose up -d
# → http://localhost:8099
```

---

#### Tech Stack

Backend: FastAPI + SQLAlchemy + SQLite | Frontend: React + TypeScript + Tailwind + Recharts

---

Feedback, Feature-Wünsche und Fehlerberichte gerne als [GitHub Issue](https://github.com/supernova1963/eedc-homeassistant/issues) oder direkt hier im Thread.

**Links:**
- Website & Docs: https://supernova1963.github.io/eedc-homeassistant/
- GitHub (Add-on): https://github.com/supernova1963/eedc-homeassistant
- GitHub (Community-Server): https://github.com/supernova1963/eedc-community
- Changelog: https://github.com/supernova1963/eedc-homeassistant/blob/main/CHANGELOG.md
- Community Live: https://energy.raunet.eu

---

## Variante 3: Deutsche PV-Foren & Facebook-Gruppen
*Freundlicher, persönlicher Ton, weniger technisch, mehr Nutzen im Vordergrund*

---

### Kostenlose PV-Auswertungs-Software – auch für Home Assistant

Hallo in die Runde!

Ich habe ein Tool entwickelt, das mich selbst bei meiner eigenen PV-Anlage begeistert – und vielleicht hilft es auch euch weiter.

**EEDC** wertet eure Photovoltaik-Anlage komplett aus: Energiebilanz, Wirtschaftlichkeit, Amortisation, CO2 – alles auf einen Blick, und das komplett kostenlos und ohne Cloud.

---

**Was bringt EEDC konkret?**

**Was passiert gerade auf meinem Dach?** – Ein Live Dashboard zeigt in Echtzeit, wohin euer PV-Strom fließt: animiertes Energiefluss-Diagramm, Tagesverlauf, Wetter-Prognose mit Ist/Soll-Vergleich

**Wann ist meine Anlage abbezahlt?** – Ein Fortschrittsbalken zeigt, wie viel Prozent der Investition bereits zurückgeflossen sind, und schätzt das Amortisationsjahr

**Wie autark bin ich wirklich?** – Autarkie und Eigenverbrauchsquote als anschauliche Ringdiagramme, nicht nur als Zahl

**Wohin fließt mein PV-Strom?** – Ein Energie-Fluss-Diagramm zeigt Direktverbrauch, Speichernutzung und Einspeisung auf einen Blick

**Lohnt sich der Speicher?** – Effizienz, Vollzyklen, PV-Anteil und mehr

**Wie gut ist meine Wärmepumpe?** – JAZ-Berechnung und Vergleich mit der Community

**Wie fährt mein E-Auto?** – PV-Anteil der Ladungen, Kostenersparnis, V2H-Auswertung, Firmenwagen-Unterstützung

**Bin ich gut im Vergleich?** – Optionaler anonymer Community-Vergleich mit anderen Anlagen in Deutschland, Österreich und der Schweiz. Eigenes Web-Dashboard unter [energy.raunet.eu](https://energy.raunet.eu)

**Steuerlich korrekt** – Kleinunternehmerregelung, Spezialtarife für WP/Wallbox, sonstige Erträge & Ausgaben

---

**Für wen ist das?**

- Home Assistant Nutzer → als Add-on mit einem Klick installierbar
- Alle anderen → läuft auch standalone als Docker-Container oder lokal
- Nicht nur HA: Per MQTT kann jedes Smarthome-System Daten liefern (Node-RED, ioBroker, FHEM, openHAB)
- Deutschland, Österreich und die Schweiz

---

**Daten eingeben geht ganz einfach:**
- Automatisch aus der Home Assistant Langzeitstatistik
- Cloud-Import: SolarEdge, Fronius, Huawei, Growatt, Deye/Solarman
- 9 Geräte-Connectors: SMA, Fronius, go-eCharger, Shelly, OpenDTU, Kostal u.a.
- Per CSV/JSON-Import (auch mit eigenen Spaltenbezeichnungen)
- Manuell über ein geführtes Formular (Monatsabschluss-Wizard)
- Demo-Daten zum Ausprobieren – ein Klick, und alles ist befüllt

---

**Kostet nichts, läuft lokal, keine Registrierung.**

Zum Projekt: https://supernova1963.github.io/eedc-homeassistant/
Community-Vergleich: https://energy.raunet.eu

Fragen und Feedback sind herzlich willkommen!

---

## Kurz-Version (für Kommentare / Kurzbeschreibungen)

### Deutsch
> **EEDC** ist ein kostenloses, lokal laufendes PV-Analyse-Tool für Home Assistant (auch standalone). Live Dashboard mit animiertem Energiefluss, Echtzeit-Monitoring via MQTT (funktioniert mit jedem Smarthome-System), ROI-Tracking, Prognosen, Cloud-Import (SolarEdge, Fronius, Huawei u.a.), Speicher/WP/E-Auto-Auswertung, steuerliche Behandlung und optionaler Community-Benchmark. DACH-Support (DE/AT/CH). Demo-Daten inklusive.
> https://supernova1963.github.io/eedc-homeassistant/

### English
> **EEDC** is a free, fully local PV analysis tool for Home Assistant (also standalone). Live dashboard with animated energy flow, real-time monitoring via MQTT (works with any smart home system), ROI tracking, forecasting, cloud import (SolarEdge, Fronius, Huawei & more), battery/heat pump/EV analysis, tax features, and optional anonymous community benchmark. Supports Germany, Austria, Switzerland. Demo data included.
> https://supernova1963.github.io/eedc-homeassistant/
