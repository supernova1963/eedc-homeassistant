# EEDC Architektur-Dokumentation

**Version 2.4.0** | Stand: Februar 2026

---

## Inhaltsverzeichnis

1. [Übersicht](#1-übersicht)
2. [Technologie-Stack](#2-technologie-stack)
3. [Projektstruktur](#3-projektstruktur)
4. [Datenmodell](#4-datenmodell)
5. [API-Architektur](#5-api-architektur)
6. [Frontend-Architektur](#6-frontend-architektur)
7. [Services](#7-services)
8. [Design-Entscheidungen](#8-design-entscheidungen)
9. [Entwickler-Workflow](#9-entwickler-workflow)

---

## 1. Übersicht

### Architektur-Prinzipien

1. **Standalone-First**: EEDC funktioniert ohne externe Abhängigkeiten
2. **Lokale Datenspeicherung**: SQLite-Datenbank, alle Daten bleiben lokal
3. **Optionale Integration**: Home Assistant ist optional, nicht erforderlich
4. **Monatliche Granularität**: Datenerfassung und Auswertung auf Monatsbasis

### System-Architektur

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                              │
│                    (React Frontend)                         │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP/REST
┌────────────────────────┴────────────────────────────────────┐
│                     FastAPI Backend                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │  Routes  │  │ Services │  │  Models  │  │   Core   │     │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘     │
└────────────────────────┬────────────────────────────────────┘
                         │ SQLAlchemy
┌────────────────────────┴────────────────────────────────────┐
│                      SQLite Database                        │
│                      (/data/eedc.db)                        │
└─────────────────────────────────────────────────────────────┘

Externe APIs (optional):
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  Open-Meteo │  │ Bright Sky  │  │    PVGIS    │  │ Home Asst.  │
│  (Wetter)   │  │   (DWD)     │  │  (Prognose) │  │   (MQTT)    │
└─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘
```

---

## 2. Technologie-Stack

### Backend

| Technologie | Version | Zweck |
|-------------|---------|-------|
| **Python** | 3.11+ | Programmiersprache |
| **FastAPI** | 0.109+ | REST API Framework |
| **SQLAlchemy** | 2.0+ | ORM (Object-Relational Mapping) |
| **SQLite** | 3.x | Datenbank |
| **Pydantic** | 2.x | Datenvalidierung |
| **httpx** | 0.26+ | HTTP Client für externe APIs |
| **aiomqtt** | optional | MQTT Client für HA Export |
| **APScheduler** | 3.x | Scheduler für Cron-Jobs (NEU) |

### Frontend

| Technologie | Version | Zweck |
|-------------|---------|-------|
| **React** | 18.x | UI Framework |
| **TypeScript** | 5.x | Typsichere Programmierung |
| **Vite** | 5.x | Build Tool & Dev Server |
| **Tailwind CSS** | 3.x | Styling |
| **Recharts** | 2.x | Diagramme |
| **react-simple-maps** | 3.x | Choropleth Deutschlandkarte (NEU v2.2.0) |
| **Lucide React** | - | Icons |
| **React Router** | 6.x | Routing |

### Deployment

| Variante | Technologie |
|----------|-------------|
| **Home Assistant Add-on** | Docker (Ingress) |
| **Standalone** | Docker |
| **Entwicklung** | Uvicorn + Vite Dev Server |

---

## 3. Projektstruktur

```
eedc-homeassistant/
├── README.md                    # Projekt-Übersicht
├── CHANGELOG.md                 # Versionshistorie
├── CLAUDE.md                    # KI-Entwicklungskontext
├── LICENSE                      # MIT Lizenz
│
├── docs/                        # Dokumentation
│   ├── BENUTZERHANDBUCH.md      # Endbenutzer-Anleitung
│   ├── ARCHITEKTUR.md           # Diese Datei
│   ├── DEVELOPMENT.md           # Entwickler-Setup
│   └── archive/                 # Archivierte Dokumente
│
└── eedc/                        # Das Add-on/Die Anwendung
    ├── config.yaml              # HA Add-on Konfiguration
    ├── Dockerfile               # Multi-Stage Build
    ├── run.sh                   # Container Startscript
    │
    ├── backend/                 # Python FastAPI Backend
    │   ├── main.py              # FastAPI App Entry Point
    │   ├── requirements.txt     # Python Dependencies
    │   │
    │   ├── api/                 # API Layer
    │   │   ├── deps.py          # Dependency Injection
    │   │   └── routes/          # API Endpoints
    │   │       ├── anlagen.py
    │   │       ├── monatsdaten.py
    │   │       ├── investitionen.py
    │   │       ├── strompreise.py
    │   │       ├── cockpit.py
    │   │       ├── import_export/     # Modulares Package
    │   │       │   ├── __init__.py   # Router-Kombination
    │   │       │   ├── schemas.py    # Pydantic-Modelle
    │   │       │   ├── helpers.py    # Hilfsfunktionen
    │   │       │   ├── csv_operations.py
    │   │       │   ├── json_operations.py
    │   │       │   ├── pdf_operations.py  # PDF-Export (NEU beta.12)
    │   │       │   └── demo_data.py
    │   │       ├── wetter.py
    │   │       ├── pvgis.py
    │   │       ├── ha_export.py
    │   │       ├── ha_import.py
    │   │       ├── ha_integration.py
    │   │       ├── sensor_mapping.py     # Sensor-Mapping CRUD (NEU)
    │   │       └── monatsabschluss.py    # Monatsabschluss-Wizard API (NEU)
    │   │
    │   ├── core/                # Kernfunktionalität
    │   │   ├── config.py        # Settings + Version
    │   │   ├── database.py      # SQLAlchemy Setup
    │   │   └── calculations.py  # Berechnungslogik
    │   │
    │   ├── models/              # SQLAlchemy Models
    │   │   ├── anlage.py
    │   │   ├── monatsdaten.py
    │   │   ├── investition.py
    │   │   ├── strompreis.py
    │   │   ├── pvgis_prognose.py
    │   │   └── string_monatsdaten.py
    │   │
    │   └── services/            # Business Logic
    │       ├── wetter_service.py
    │       ├── pdf_service.py       # PDF-Generierung
    │       ├── ha_sensors_export.py
    │       ├── mqtt_client.py
    │       ├── ha_mqtt_sync.py      # MQTT Sync Service
    │       ├── vorschlag_service.py # Intelligente Vorschläge
    │       ├── scheduler.py         # APScheduler für Cron-Jobs
    │       ├── ha_statistics_service.py # HA-DB Statistik-Abfragen (NEU v2.0.0)
    │       └── community_service.py     # Community-Datenaufbereitung (NEU v2.0.3)
    │
    └── frontend/                # React Frontend
        ├── package.json
        ├── vite.config.ts
        ├── tailwind.config.js
        │
        ├── src/
        │   ├── main.tsx         # React Entry Point
        │   ├── App.tsx          # Router Setup
        │   │
        │   ├── api/             # API Client Layer
        │   │   ├── anlagen.ts
        │   │   ├── monatsdaten.ts
        │   │   ├── investitionen.ts
        │   │   ├── cockpit.ts
        │   │   ├── wetter.ts
        │   │   └── ...
        │   │
        │   ├── components/      # React Komponenten
        │   │   ├── layout/      # Layout (TopNav, SubTabs)
        │   │   ├── forms/       # Formulare
        │   │   ├── ui/          # Wiederverwendbare UI
        │   │   ├── setup-wizard/ # Setup-Wizard
        │   │   └── pv/          # PV-spezifische Komponenten
        │   │
        │   ├── pages/           # Seiten-Komponenten
        │   │   ├── Dashboard.tsx
        │   │   ├── Auswertung.tsx
        │   │   ├── auswertung/  # Auswertungs-Tabs
        │   │   └── ...
        │   │
        │   ├── hooks/           # Custom React Hooks
        │   ├── utils/           # Hilfsfunktionen
        │   └── config/          # Konfiguration
        │
        └── dist/                # Production Build
```

---

## 4. Datenmodell

### Entity-Relationship Diagramm

```
┌─────────────────────────────────────────────────────────────┐
│                          Anlage                             │
│  id, name, adresse, koordinaten, ausrichtung, neigung       │
└────────────┬──────────────────────┬────────────────┬────────┘
             │                      │                │
             │ 1:n                  │ 1:n            │ 1:n
             ▼                      ▼                ▼
┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐
│    Monatsdaten     │  │    Strompreise     │  │   Investitionen    │
│  (Zählerwerte)     │  │  (Tarife)          │  │   (Komponenten)    │
└────────────────────┘  └────────────────────┘  └─────────┬──────────┘
                                                          │
                                                          │ 1:n
                                                          ▼
                                              ┌────────────────────────┐
                                              │ InvestitionMonatsdaten │
                                              │   (Komponenten-Daten)  │
                                              └────────────────────────┘
```

### Tabellen im Detail

#### Anlage

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primary Key |
| name | VARCHAR | Bezeichnung |
| strasse | VARCHAR | Adresse |
| plz | VARCHAR | Postleitzahl |
| stadt | VARCHAR | Ort |
| latitude | FLOAT | Breitengrad |
| longitude | FLOAT | Längengrad |
| ausrichtung | VARCHAR | Himmelsrichtung |
| neigung_grad | FLOAT | Dachneigung |
| leistung_kwp | FLOAT | Anlagenleistung |
| mastr_id | VARCHAR(20) | MaStR-ID der Anlage |
| standort_land | VARCHAR(5) | Land: DE, AT oder CH (v2.3.0) |
| versorger_daten | JSON | Versorger & Zähler |
| wetter_provider | VARCHAR(30) | Bevorzugter Wetter-Provider (auto, open-meteo, brightsky, open-meteo-solar) |
| sensor_mapping | JSON | HA-Sensor-Mapping |
| steuerliche_behandlung | VARCHAR(30) | `keine_ust` oder `regelbesteuerung` (v2.4.0) |
| ust_satz_prozent | FLOAT | USt-Satz: DE=19, AT=20, CH=8.1 (v2.4.0) |
| created_at | DATETIME | Erstellungsdatum |

#### Monatsdaten

**Wichtig**: Diese Tabelle enthält NUR Zählerwerte (Einspeisung, Netzbezug).

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primary Key |
| anlage_id | INTEGER | Foreign Key → Anlage |
| jahr | INTEGER | Jahr |
| monat | INTEGER | Monat (1-12) |
| einspeisung_kwh | FLOAT | Zählerwert Einspeisung |
| netzbezug_kwh | FLOAT | Zählerwert Netzbezug |
| direktverbrauch_kwh | FLOAT | Berechnet |
| eigenverbrauch_kwh | FLOAT | Berechnet |
| gesamtverbrauch_kwh | FLOAT | Berechnet |
| globalstrahlung_kwh_m2 | FLOAT | Wetter-API |
| sonnenstunden | FLOAT | Wetter-API |
| datenquelle | VARCHAR | manual, csv, ha_import |
| notizen | TEXT | Freitext |

**Legacy-Felder (nicht mehr verwenden):**
- `pv_erzeugung_kwh` → Verwende InvestitionMonatsdaten
- `batterie_ladung_kwh` → Verwende InvestitionMonatsdaten
- `batterie_entladung_kwh` → Verwende InvestitionMonatsdaten

#### Investitionen

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primary Key |
| anlage_id | INTEGER | Foreign Key → Anlage |
| typ | VARCHAR | Investitionstyp |
| bezeichnung | VARCHAR | Name der Komponente |
| kosten_euro | FLOAT | Kaufpreis + Installation |
| lebensdauer_jahre | INTEGER | Erwartete Lebensdauer |
| installationsdatum | DATE | Inbetriebnahme |
| parameter | JSON | Typ-spezifische Parameter |
| parent_investition_id | INTEGER | Foreign Key → Investitionen (für Parent-Child) |
| aktiv | BOOLEAN | Aktiv/Inaktiv |

**Investitionstypen:**

| Typ | Parameter (JSON) |
|-----|------------------|
| `wechselrichter` | - |
| `pv-module` | anzahl_module, modul_leistung_wp, ausrichtung, neigung_grad |
| `speicher` | kapazitaet_kwh, arbitrage_faehig |
| `e-auto` | v2h_faehig, nutzt_v2h |
| `waermepumpe` | effizienz_modus, jaz, cop_heizung, cop_warmwasser, heizwaermebedarf_kwh, warmwasserbedarf_kwh, leistung_kw, pv_anteil_prozent, alter_energietraeger, alter_preis_cent_kwh, sg_ready |
| `wallbox` | - |
| `balkonkraftwerk` | leistung_wp, anzahl, hat_speicher, speicher_kapazitaet_wh |
| `sonstiges` | kategorie (erzeuger/verbraucher/speicher), beschreibung |

**Stammdaten-Felder (NEU in beta.6):**

Alle Investitionstypen können zusätzlich folgende Felder im `parameter` JSON enthalten:

| Gruppe | Felder |
|--------|--------|
| **Gerätedaten** | `stamm_hersteller`, `stamm_modell`, `stamm_seriennummer`, `stamm_garantie_bis`, `stamm_notizen` |
| **Ansprechpartner** | `ansprechpartner_firma`, `ansprechpartner_name`, `ansprechpartner_telefon`, `ansprechpartner_email`, `ansprechpartner_ticketsystem`, `ansprechpartner_kundennummer`, `ansprechpartner_vertragsnummer` |
| **Wartung** | `wartung_vertragsnummer`, `wartung_anbieter`, `wartung_gueltig_bis`, `wartung_kuendigungsfrist`, `wartung_leistungsumfang` |

Typ-spezifische Zusatzfelder:
- **Wechselrichter:** `stamm_mastr_id`
- **Speicher:** `stamm_garantie_zyklen`
- **PV-Module:** `stamm_garantie_leistung_prozent`
- **E-Auto:** `stamm_kennzeichen`, `stamm_fahrgestellnummer`, `stamm_erstzulassung`, `stamm_garantie_batterie_km`, `stamm_foerderung_*`
- **Wärmepumpe:** `stamm_foerderung_aktenzeichen`, `stamm_foerderung_betrag_euro`
- **Balkonkraftwerk:** `stamm_anmeldung_netzbetreiber`, `stamm_anmeldung_marktstammdaten`

#### InvestitionMonatsdaten

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primary Key |
| investition_id | INTEGER | Foreign Key → Investitionen |
| jahr | INTEGER | Jahr |
| monat | INTEGER | Monat (1-12) |
| verbrauch_daten | JSON | Typ-spezifische Messwerte |
| einsparung_monat_euro | FLOAT | Berechnet |
| co2_einsparung_kg | FLOAT | Berechnet |
| sonderkosten_euro | FLOAT | Reparatur, Wartung |

**verbrauch_daten Struktur je nach Investitionstyp:**

```json
// PV-Module
{
  "pv_erzeugung_kwh": 450.5
}

// Speicher
{
  "ladung_kwh": 200.0,
  "entladung_kwh": 185.0,
  "ladung_netz_kwh": 50.0,        // Arbitrage
  "ladepreis_cent": 15.5          // Arbitrage
}

// E-Auto
{
  "km_gefahren": 1200,
  "verbrauch_kwh": 216.0,
  "ladung_pv_kwh": 130.0,
  "ladung_netz_kwh": 86.0,
  "ladung_extern_kwh": 50.0,
  "ladung_extern_euro": 25.0,
  "v2h_entladung_kwh": 25.0
}

// Wärmepumpe
{
  "stromverbrauch_kwh": 450.0,
  "heizenergie_kwh": 1800.0,
  "warmwasser_kwh": 200.0
}

// Wallbox
{
  "ladung_kwh": 150.5,
  "ladevorgaenge": 10
}

// Balkonkraftwerk (mit optionalem Speicher)
{
  "pv_erzeugung_kwh": 45.0,
  "eigenverbrauch_kwh": 40.0,
  "speicher_ladung_kwh": 10.0,
  "speicher_entladung_kwh": 8.0
}

// Sonstiges - Erzeuger (v2.4.0)
{
  "erzeugung_kwh": 120.0,
  "eigenverbrauch_kwh": 100.0,
  "einspeisung_kwh": 20.0
}

// Sonstiges - Verbraucher (v2.4.0)
{
  "verbrauch_kwh": 200.0,
  "bezug_pv_kwh": 80.0,
  "bezug_netz_kwh": 120.0
}

// Sonstiges - Speicher (v2.4.0)
{
  "ladung_kwh": 50.0,
  "entladung_kwh": 45.0
}

// Sonstige Erträge & Ausgaben (alle Typen, v2.4.0)
{
  "sonstige_ertraege": [{"bezeichnung": "Einspeisebonus", "betrag": 15.0}],
  "sonstige_ausgaben": [{"bezeichnung": "Versicherung", "betrag": 8.50}]
}
```

**versorger_daten Struktur (Anlage, NEU in beta.6):**

```json
{
  "strom": {
    "name": "Stadtwerke München",
    "kundennummer": "12345678",
    "portal_url": "https://kundenportal.swm.de",
    "notizen": "",
    "zaehler": [
      {"bezeichnung": "Einspeisung", "nummer": "1EMH0012345678", "notizen": ""},
      {"bezeichnung": "Bezug", "nummer": "1EMH0087654321", "notizen": "Zweirichtungszähler"}
    ]
  },
  "gas": {
    "name": "Stadtwerke München",
    "kundennummer": "G-98765",
    "zaehler": [{"bezeichnung": "Erdgas", "nummer": "G12345678", "notizen": ""}]
  },
  "wasser": {
    "name": "Wasserwerke XY",
    "kundennummer": "W-11111",
    "zaehler": [{"bezeichnung": "Kaltwasser", "nummer": "WZ-123", "notizen": ""}]
  }
}
```

#### Strompreise

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primary Key |
| anlage_id | INTEGER | Foreign Key → Anlage |
| bezugspreis_cent | FLOAT | Preis pro kWh Netzbezug |
| einspeiseverguetung_cent | FLOAT | Vergütung pro kWh Einspeisung |
| gueltig_ab | DATE | Gültigkeitsbeginn |
| gueltig_bis | DATE | Gültigkeitsende (optional) |
| verwendung | VARCHAR(20) | `allgemein`, `waermepumpe` oder `wallbox` (v2.4.0) |

### Parent-Child Beziehungen

```
Wechselrichter (Parent)
├── PV-Module (Child) [Pflicht]
└── DC-Speicher (Child) [Optional, für Hybrid-WR]

AC-Speicher [Eigenständig]
E-Auto [Eigenständig]
Wärmepumpe [Eigenständig]
Wallbox [Eigenständig]
Balkonkraftwerk [Eigenständig]
Sonstiges [Eigenständig]
```

**PV-System ROI-Aggregation:**
- Wechselrichter + zugeordnete PV-Module + DC-Speicher = "PV-System"
- ROI wird auf System-Ebene berechnet
- Einsparungen werden proportional nach kWp verteilt

---

## 5. API-Architektur

### Route-Übersicht

| Prefix | Datei | Beschreibung |
|--------|-------|--------------|
| `/api/anlagen` | anlagen.py | PV-Anlagen CRUD, Geocoding |
| `/api/monatsdaten` | monatsdaten.py | Monatsdaten CRUD, Berechnungen |
| `/api/investitionen` | investitionen.py | Komponenten CRUD, ROI (Jahres-Rendite) |
| `/api/strompreise` | strompreise.py | Stromtarife CRUD |
| `/api/cockpit` | cockpit.py | Aggregierte Dashboard-Daten (Jahres-Rendite) |
| `/api/aussichten` | aussichten.py | **Prognosen: Kurzfristig, Langfristig, Trend, Finanzen** |
| `/api/import` | import_export/ | CSV Import/Export, JSON-Export, **PDF-Export**, Demo-Daten |
| `/api/wetter` | wetter.py | Wetter-API (Multi-Provider: Open-Meteo, Bright Sky, PVGIS) |
| `/api/solar-prognose` | solar_prognose.py | GTI-basierte PV-Ertragsprognose |
| `/api/pvgis` | pvgis.py | PVGIS Ertragsprognosen |
| `/api/ha/export` | ha_export.py | HA Sensor Export (REST, MQTT) |
| `/api/ha-import` | ha_import.py | Investitions-Felder (CSV-Template) |
| `/api/ha` | ha_integration.py | HA Discovery, String-Import |
| `/api/sensor-mapping` | sensor_mapping.py | **Sensor-Mapping CRUD** (NEU) |
| `/api/monatsabschluss` | monatsabschluss.py | **Monatsabschluss-Wizard** (NEU) |
| `/api/scheduler` | scheduler.py | **Scheduler Status/Trigger** (NEU) |
| `/api/community` | community.py | **Community-Teilen & Benchmark** (NEU v2.0.3) |

### Wichtige Endpoints

#### Cockpit (Dashboard-Daten)

```
GET /api/cockpit/uebersicht/{anlage_id}?jahr=2025
```

Liefert aggregierte Daten für alle Dashboard-Sektionen:
- Energiebilanz (Erzeugung, Verbrauch, Einspeisung)
- Effizienz (Autarkie, EV-Quote)
- Komponenten-Status
- Finanzen (inkl. `jahres_rendite_prozent` = Jahres-Ertrag / Investition), CO2

**Datenquellen:**
- Monatsdaten: Einspeisung, Netzbezug
- InvestitionMonatsdaten: Alle Komponenten-Details

#### Aussichten (Prognosen)

```
GET /api/aussichten/kurzfristig/{anlage_id}   # 7-Tage Wetterprognose
GET /api/aussichten/langfristig/{anlage_id}   # 12-Monats-Prognose (PVGIS)
GET /api/aussichten/trend/{anlage_id}         # Trend-Analyse + Degradation
GET /api/aussichten/finanzen/{anlage_id}      # Finanz-Prognose + Amortisation
```

**4 Prognose-Tabs:**
- **Kurzfristig**: 7-Tage Wetterprognose (Open-Meteo) mit Erzeugungsschätzung
- **Langfristig**: 12-Monats-Prognose basierend auf PVGIS und Performance-Ratio
- **Trend**: Jahresvergleich, saisonale Muster, Degradationsberechnung
- **Finanzen**: Amortisations-Fortschritt, Komponenten-Beiträge, Mehrkosten-Ansatz

**ROI-Metrik**: `amortisations_fortschritt_prozent` = Kumulierte Erträge / Investition
(Unterscheidet sich von Cockpit `jahres_rendite_prozent`!)

#### Sensor-Mapping API (NEU v1.1.0)

```
GET  /api/sensor-mapping/{anlage_id}              # Aktuelles Mapping abrufen
POST /api/sensor-mapping/{anlage_id}              # Mapping speichern
GET  /api/sensor-mapping/{anlage_id}/felder       # Verfügbare Felder
GET  /api/sensor-mapping/{anlage_id}/sensoren     # HA-Sensoren auflisten
```

**Mapping-Strategien:**
- `sensor` - Direkter HA-Sensor
- `kwp_verteilung` - Anteilige Verteilung nach kWp
- `cop_berechnung` - COP-basierte Berechnung (Wärmepumpe)
- `ev_quote` - Eigenverbrauchsquote-Berechnung
- `manuell` - Manuelle Eingabe im Wizard
- `keine` - Nicht erfassen

#### Monatsabschluss API (NEU v1.1.0)

```
GET  /api/monatsabschluss/{anlage_id}/status?jahr=2026&monat=2     # Status prüfen
GET  /api/monatsabschluss/{anlage_id}/naechster                    # Nächster offener Monat
POST /api/monatsabschluss/{anlage_id}/abschliessen                 # Abschluss durchführen
GET  /api/monatsabschluss/{anlage_id}/historie                     # Letzte Abschlüsse
```

**VorschlagService liefert intelligente Vorschläge:**
- `vormonat` (Konfidenz 80%) - Wert vom Vormonat
- `vorjahr` (Konfidenz 70%) - Wert vom gleichen Monat im Vorjahr
- `berechnung` (Konfidenz 60%) - COP/EV-Quote basierte Berechnung
- `durchschnitt` (Konfidenz 50%) - Durchschnitt aller vorhandenen Werte

#### Scheduler API (NEU v1.1.0)

```
GET  /api/scheduler/status                        # Scheduler-Status
POST /api/scheduler/trigger-monthly               # Manueller Monatswechsel-Trigger
```

#### Aggregierte Monatsdaten

```
GET /api/monatsdaten/aggregiert/{anlage_id}?jahr=2025
```

Liefert Monatsdaten mit allen Komponenten-Summen:
- Zählerwerte aus Monatsdaten (Einspeisung, Netzbezug)
- PV-Erzeugung aggregiert aus allen PV-Modulen
- Speicher-Daten (Ladung, Entladung)
- WP/E-Auto/Wallbox-Daten
- Berechnete Kennzahlen (Direktverbrauch, Eigenverbrauch, Autarkie)

#### CSV Import

```
POST /api/import/csv/{anlage_id}
Content-Type: multipart/form-data

file: [CSV-Datei]
```

**Verarbeitung:**
1. CSV parsen (flexible Spalten-Erkennung)
2. Basis-Felder → Monatsdaten-Tabelle
3. Investitions-Felder → InvestitionMonatsdaten-Tabelle
4. Duplikate: Upsert (überschreiben)
5. `flag_modified()` für JSON-Felder

**Plausibilitätsprüfungen (NEU in beta.8):**
- Legacy-Spalten (`PV_Erzeugung_kWh`, `Batterie_*_kWh`) werden validiert
- Fehler wenn NUR Legacy und PV-Module/Speicher existieren
- Fehler bei Mismatch Legacy vs. Summe Komponenten-Werte
- Warnung wenn redundant (±0.5 kWh Toleranz)
- Negative Werte werden blockiert
- Plausibilitätswarnungen (Sonnenstunden > 400h, Globalstrahlung > 250)

#### JSON Export/Import (Export-Version 1.1)

```
GET  /api/import/export/{anlage_id}/full    # Export
POST /api/import/json                        # Import
```

**Export** - Vollständige Anlage mit allen verknüpften Daten:
- Anlage-Stammdaten (inkl. versorger_daten, mastr_id, wetter_provider)
- **sensor_mapping** (NEU in beta.5) - HA Sensor-Zuordnungen
- Strompreise
- Investitionen (hierarchisch mit Children)
- Monatsdaten mit InvestitionMonatsdaten (inkl. durchschnittstemperatur, sonderkosten)
- PVGIS-Prognosen

**Import** - Restore aus JSON-Export:
- Erstellt neue Anlage (oder überschreibt bei gleichem Namen)
- sensor_mapping wird importiert, aber `mqtt_setup_complete=false`
- Rückwärtskompatibel mit Export-Version 1.0
### Request/Response Pattern

```python
# Typisches Schema-Pattern
class MonatsdatenCreate(BaseModel):
    anlage_id: int
    jahr: int
    monat: int
    einspeisung_kwh: float
    netzbezug_kwh: float
    investitions_daten: Optional[Dict[int, Dict]] = None

class MonatsdatenResponse(MonatsdatenCreate):
    id: int
    direktverbrauch_kwh: Optional[float]
    eigenverbrauch_kwh: Optional[float]
    # ... berechnete Felder
```

---

## 6. Frontend-Architektur

### Routing-Struktur

```
/                       → Redirect zu /cockpit
│
├── /cockpit            → Dashboard (Übersicht)
│   ├── /pv-anlage      → PVAnlageDashboard
│   ├── /e-auto         → EAutoDashboard
│   ├── /waermepumpe    → WaermepumpeDashboard
│   ├── /speicher       → SpeicherDashboard
│   ├── /wallbox        → WallboxDashboard
│   ├── /balkonkraftwerk → BalkonkraftwerkDashboard
│   └── /sonstiges      → SonstigesDashboard
│
├── /auswertungen       → Auswertung.tsx (6 Tabs)
│   ├── /roi            → ROIDashboard (Jahres-Rendite p.a.)
│   └── /prognose       → PrognoseVsIst
│
├── /community          → CommunityVergleich.tsx (6 Tabs, v2.1.0)
│   ├── Übersicht       → Achievements, Radar-Chart, Rang-Badges
│   ├── PV-Ertrag       → Monatlicher Vergleich, Histogramm
│   ├── Komponenten     → Speicher, WP, E-Auto, Wallbox, BKW Deep-Dives
│   ├── Regional        → Bundesland-Ranking, Choropleth-Karte (v2.2.0)
│   ├── Trends          → Ertragsverlauf, Saisonale Performance
│   └── Statistiken     → Community-weite Auswertungen
│
├── /aussichten         → Aussichten.tsx (4 Tabs)
│   ├── /kurzfristig    → KurzfristigTab (7-Tage Wetter)
│   ├── /langfristig    → LangfristigTab (12-Monats PVGIS)
│   ├── /trend          → TrendTab (Jahresvergleich, Degradation)
│   └── /finanzen       → FinanzenTab (Amortisations-Fortschritt)
│
└── /einstellungen
    ├── /anlage         → Anlagen.tsx
    ├── /strompreise    → Strompreise.tsx
    ├── /investitionen  → Investitionen.tsx
    ├── /monatsdaten    → Monatsdaten.tsx
    ├── /import         → Import.tsx
    ├── /demo           → Import.tsx (Demo-Sektion)
    ├── /pvgis          → PVGISSettings.tsx
    ├── /ha-import      → HAImportSettings.tsx
    ├── /ha-export      → HAExportSettings.tsx
    └── /allgemein      → Settings.tsx
```

### Komponenten-Hierarchie

```
App.tsx
├── ThemeProvider
└── BrowserRouter
    └── Layout.tsx
        ├── TopNavigation.tsx
        │   ├── Logo
        │   ├── MainTabs (Cockpit, Auswertungen, Community, Aussichten)
        │   ├── SettingsDropdown
        │   └── ThemeToggle
        │
        ├── SubTabs.tsx (kontextabhängig)
        │
        └── <Outlet /> (React Router)
            └── [Page Component]
```

### State Management

**Kein globaler State-Store** – stattdessen:

1. **React Query / SWR Pattern** für Server-State
2. **Context** für Theme
3. **localStorage** für Präferenzen (Spalten-Toggle, Wizard-Status)
4. **URL-Parameter** für Filter (Jahr, Anlage)

### API-Client Pattern

```typescript
// api/cockpit.ts
export const cockpitApi = {
  getUebersicht: async (anlageId: number, jahr?: number) => {
    const params = jahr ? `?jahr=${jahr}` : '';
    const response = await fetch(`/api/cockpit/uebersicht/${anlageId}${params}`);
    return response.json();
  },
  // ...
};

// Verwendung in Komponente
const [data, setData] = useState<CockpitData | null>(null);

useEffect(() => {
  cockpitApi.getUebersicht(anlageId, jahr).then(setData);
}, [anlageId, jahr]);
```

### Custom Hooks

| Hook | Zweck |
|------|-------|
| `useAnlagen()` | PV-Anlagen laden |
| `useMonatsdaten(anlageId)` | Monatsdaten mit Filter |
| `useInvestitionen(anlageId)` | Komponenten |
| `useAktuellerStrompreis(anlageId)` | Aktueller Tarif |
| `useSetupWizard()` | Wizard-State & Navigation |

---

## 7. Services

### Wetter-Service (Multi-Provider)

**Dateien:**
- `backend/services/wetter_service.py` – Multi-Provider Orchestrierung
- `backend/services/brightsky_service.py` – DWD-Daten via Bright Sky API
- `backend/services/solar_forecast_service.py` – Open-Meteo Solar mit GTI

**Funktion:** Wetterdaten für Globalstrahlung und Sonnenstunden aus verschiedenen Quellen.

**Verfügbare Provider:**

| Provider | Region | Beschreibung |
|----------|--------|--------------|
| **auto** (Standard) | - | Automatische Auswahl basierend auf Standort |
| **brightsky** | Deutschland | DWD-Daten via Bright Sky REST API (höchste Qualität) |
| **open-meteo** | Weltweit | Open-Meteo Archive API |
| **open-meteo-solar** | Weltweit | Open-Meteo Solar mit GTI für geneigte Module |

**Fallback-Kette:**
1. Gewählter Provider
2. Alternative (z.B. Open-Meteo wenn Bright Sky fehlschlägt)
3. PVGIS TMY (langjährige Durchschnittswerte)
4. Statische Defaults (Mitteleuropa-Durchschnitt)

**API-Endpoints:**
```
GET /api/wetter/monat/{anlage_id}/{jahr}/{monat}?provider=auto
GET /api/wetter/provider/{anlage_id}           # Verfügbare Provider
GET /api/wetter/vergleich/{anlage_id}/{jahr}/{monat}  # Provider-Vergleich
GET /api/solar-prognose/{anlage_id}?tage=7     # GTI-basierte PV-Prognose
```

**GTI (Global Tilted Irradiance):**
Open-Meteo Solar berechnet Strahlung für geneigte PV-Module:
- Neigung und Ausrichtung aus PV-Modul-Konfiguration
- Temperaturkorrektur (Wirkungsgradminderung bei Hitze)
- Multi-String-Unterstützung für verschiedene Ausrichtungen

### Sensor-Export Service

**Datei:** `backend/services/ha_sensors_export.py`

**Funktion:** Definition und Berechnung aller exportierbaren KPIs.

**Sensor-Kategorien:**
- `ANLAGE_SENSOREN` – PV-Gesamt
- `INVESTITION_SENSOREN` – ROI, Amortisation
- `E_AUTO_SENSOREN` – Mobilität
- `WAERMEPUMPE_SENSOREN` – Wärme
- `SPEICHER_SENSOREN` – Batterie

**Sensor-Definition:**
```python
SensorDefinition(
    key="pv_erzeugung_kwh",
    name="PV Erzeugung",
    unit="kWh",
    icon="mdi:solar-power",
    device_class="energy",
    state_class="total_increasing",
    formel="Σ(PV-Module.pv_erzeugung_kwh)"
)
```

### MQTT Client

**Datei:** `backend/services/mqtt_client.py`

**Funktion:** Publizieren von Sensoren via MQTT Auto-Discovery.

**Erweiterte Methoden (NEU v1.1.0):**
- `publish_number_discovery()` - Erstellt Number-Entities für Monatsstarts
- `publish_calculated_sensor()` - Erstellt Sensoren mit value_template
- `update_month_start_value()` - Aktualisiert retained Startwerte
- `publish_monatsdaten()` - Publiziert finale Monatswerte

**Topics:**
```
homeassistant/sensor/eedc_{anlage_id}_{key}/config  → Discovery
eedc/{anlage_id}/{key}                              → State
eedc/{anlage_id}/{key}/attributes                   → Attributes
```

### HA Statistics Service (NEU v2.0.0)

**Datei:** `backend/services/ha_statistics_service.py`

**Funktion:** Direkter SQLite-Zugriff auf Home Assistant Langzeitstatistiken.

**Voraussetzungen:**
- Volume-Mapping `config:ro` für Lesezugriff auf `/config/home-assistant_v2.db`
- Sensor-Mapping konfiguriert

**Hauptfunktionen:**
- `get_monatswerte()` - Einzelner Monat aus HA-Statistik
- `get_alle_monatswerte()` - Bulk-Abfrage aller historischen Monate
- `get_verfuegbare_monate()` - Liste aller Monate mit Daten
- `get_monatsanfang_wert()` - Zählerstand am Monatsanfang für MQTT-Startwerte

**API-Endpoints:**
- `GET /api/ha-statistics/status` - Prüft DB-Verfügbarkeit
- `GET /api/ha-statistics/monatswerte/{anlage_id}/{jahr}/{monat}` - Einzelner Monat
- `GET /api/ha-statistics/alle-monatswerte/{anlage_id}` - Bulk-Abfrage
- `GET /api/ha-statistics/import-vorschau/{anlage_id}` - Vorschau mit Konflikten
- `POST /api/ha-statistics/import/{anlage_id}` - Import mit Überschreib-Schutz

### VorschlagService

**Datei:** `backend/services/vorschlag_service.py`

**Funktion:** Intelligente Vorschläge für Monatsabschluss-Wizard.

**Vorschlags-Hierarchie:**
1. **Vormonat** (Konfidenz 80%) - Bester Indikator für kontinuierliche Werte
2. **Vorjahr** (Konfidenz 70%) - Gleicher Monat, saisonale Korrelation
3. **Berechnung** (Konfidenz 60%) - COP/EV-Quote basiert
4. **Durchschnitt** (Konfidenz 50%) - Fallback aus allen vorhandenen Werten

### Scheduler Service

**Datei:** `backend/services/scheduler.py`

**Funktion:** APScheduler-basierte Cron-Jobs für automatische Aufgaben.

**Jobs:**
- `monthly_snapshot_job` - Läuft am 1. jedes Monats um 00:01
  - Liest Sensor-Werte via HA MQTT
  - Erstellt Vorschläge für den Monatsabschluss
  - Sendet Notifications (optional)

### HA MQTT Sync Service

**Datei:** `backend/services/ha_mqtt_sync.py`

**Funktion:** Koordiniert MQTT-Sensoren basierend auf Sensor-Mapping.

**Hauptfunktionen:**
- `setup_sensors_for_anlage()` - Erstellt alle MQTT Entities
- `trigger_month_rollover()` - Führt Monatswechsel durch

---

## 8. Design-Entscheidungen

### Warum Standalone-First?

**Problem:** Komplexe HA-Integration erwies sich als problematisch:
- EVCC liefert andere Datenstrukturen als erwartet
- Utility Meter können nicht programmatisch zugeordnet werden
- Jede Haus-Automatisierung ist anders

**Lösung:** EEDC ist primär Standalone:
- Datenerfassung: CSV-Import oder manuelles Formular
- Wetter-Daten: Open-Meteo/PVGIS (HA-unabhängig)
- HA-Export: Optional, nur für berechnete KPIs

### Warum InvestitionMonatsdaten statt Monatsdaten?

**Problem:** Ursprünglich wurden Speicher-Daten in `Monatsdaten` gespeichert.

**Probleme:**
- Nicht skalierbar für mehrere Speicher
- Inkonsistent mit anderen Komponenten
- Schwer erweiterbar

**Lösung:** Alle Komponenten-Details in `InvestitionMonatsdaten`:
- `Monatsdaten` = Nur Zählerwerte (Einspeisung, Netzbezug)
- `InvestitionMonatsdaten` = Alle Komponenten-Details

### Warum Parent-Child für PV-Module?

**Grund:** PV-System ROI-Berechnung:
- Wechselrichter-Kosten müssen auf PV-System verteilt werden
- Einzelne Module haben keine eigene Amortisation
- Aggregation ermöglicht realistische ROI-Aussagen

### Warum JSON für Parameter?

**Grund:** Flexibilität bei typ-spezifischen Feldern:
- Speicher braucht `kapazitaet_kwh`, E-Auto braucht `v2h_faehig`
- Schema-Evolution ohne DB-Migrationen
- SQLite unterstützt JSON-Queries

**Achtung:** SQLAlchemy erkennt JSON-Änderungen nicht automatisch!
```python
from sqlalchemy.orm.attributes import flag_modified
investition.parameter["key"] = "value"
flag_modified(investition, "parameter")
db.commit()
```

### Warum 0-Werte explizit prüfen?

**Problem:** Python wertet `0` als `False`:
```python
if val:  # Falsch! 0 wird als False gewertet
if val is not None:  # Richtig!
```

**Konsequenz:** Überall `is not None` statt `if val`.

---

## 9. Entwickler-Workflow

### Lokale Entwicklung

**Terminal 1 – Backend:**
```bash
cd eedc
source backend/venv/bin/activate
uvicorn backend.main:app --reload --port 8099
```

**Terminal 2 – Frontend:**
```bash
cd eedc/frontend
npm run dev
```

**URLs:**
- Frontend: http://localhost:3000 (Vite Dev Server, Proxy zu Backend)
- API Docs: http://localhost:8099/api/docs

### Production Build

```bash
cd eedc/frontend
npm run build
# Output: dist/
```

### Docker Build

```bash
cd eedc
docker build -t eedc .
docker run -p 8099:8099 -v $(pwd)/data:/data eedc
```

### Versionierung

Bei neuen Releases diese Dateien aktualisieren:

1. `eedc/backend/core/config.py` – `APP_VERSION`
2. `eedc/frontend/src/config/version.ts` – `APP_VERSION`
3. `eedc/config.yaml` – `version`
4. `CHANGELOG.md` – Änderungen dokumentieren
5. `eedc/run.sh` – Version in Echo

### Git Commit Conventions

```
feat(wizard): Add Setup-Wizard for first-time users
fix(import): Fix 0-value handling in CSV import
refactor(cockpit): Use InvestitionMonatsdaten for all components
docs: Update BENUTZERHANDBUCH
chore: Bump version to 1.0.0-beta.1
```

### Tests

```bash
# Backend Tests
cd eedc/backend
pytest

# Frontend Tests (noch nicht implementiert)
cd eedc/frontend
npm test
```

---

## Anhang: API-Referenz

Vollständige API-Dokumentation unter:
- Swagger UI: http://localhost:8099/api/docs
- ReDoc: http://localhost:8099/api/redoc
- OpenAPI JSON: http://localhost:8099/api/openapi.json

---

*Letzte Aktualisierung: Februar 2026*
