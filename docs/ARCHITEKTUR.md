
# EEDC Architektur-Dokumentation

**Version 3.1** | Stand: März 2026

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
| **APScheduler** | 3.x | Scheduler für Cron-Jobs |

### Frontend

| Technologie | Version | Zweck |
|-------------|---------|-------|
| **React** | 18.x | UI Framework |
| **TypeScript** | 5.x | Typsichere Programmierung |
| **Vite** | 5.x | Build Tool & Dev Server |
| **Tailwind CSS** | 3.x | Styling |
| **Recharts** | 2.x | Diagramme |
| **react-simple-maps** | 3.x | Choropleth Deutschlandkarte |
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
    │   │       ├── aussichten.py          # Prognosen (4 Tabs)
    │   │       ├── community.py           # Community-Teilen & Benchmark
    │   │       ├── import_export/         # Modulares Package
    │   │       │   ├── __init__.py       # Router-Kombination
    │   │       │   ├── schemas.py        # Pydantic-Modelle
    │   │       │   ├── helpers.py        # Hilfsfunktionen
    │   │       │   ├── csv_operations.py
    │   │       │   ├── json_operations.py
    │   │       │   ├── pdf_operations.py  # PDF-Export
    │   │       │   └── demo_data.py
    │   │       ├── wetter.py
    │   │       ├── pvgis.py
    │   │       ├── ha_export.py
    │   │       ├── ha_import.py
    │   │       ├── ha_integration.py
    │   │       ├── ha_statistics.py       # HA-Statistik Bulk-Import
    │   │       ├── sensor_mapping.py      # Sensor-Mapping CRUD
    │   │       ├── monatsabschluss.py     # Monatsabschluss-Wizard API
    │   │       ├── portal_import.py         # Portal-CSV-Parser
    │   │       ├── custom_import.py          # Custom CSV/JSON Import
    │   │       ├── cloud_import.py           # Cloud-API Import
    │   │       ├── live_dashboard.py        # Live Dashboard API (NEU v3.0.0)
    │   │       ├── aktueller_monat.py       # Aktueller Monat API
    │   │       ├── daten_checker.py         # Daten-Checker API
    │   │       ├── system_logs.py           # Protokolle API
    │   │       └── connector.py             # Geräte-Connector API
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
    │   │   ├── settings.py         # App-Einstellungen
    │   │   ├── activity_log.py    # Aktivitäts-Protokolle
    │   │   ├── mqtt_energy_snapshot.py # MQTT Energy Snapshots (NEU v3.0.0)
    │   │   └── tages_energie_profil.py # Energieprofil: Stundenwerte + Tagessummary (NEU v3.1.0)
    │   │
    │   ├── utils/                # Hilfsfunktionen
    │   │   └── sonstige_positionen.py  # Sonstige Erträge/Ausgaben
    │   │
    │   └── services/            # Business Logic
    │       ├── wetter_service.py
    │       ├── brightsky_service.py       # DWD-Daten via Bright Sky API
    │       ├── solar_forecast_service.py  # Open-Meteo Solar mit GTI
    │       ├── prognose_service.py        # Prognose-Berechnungen
    │       ├── pdf_service.py             # PDF-Generierung
    │       ├── ha_sensors_export.py
    │       ├── ha_state_service.py        # HA State-Abfragen
    │       ├── mqtt_client.py
    │       ├── ha_mqtt_sync.py            # MQTT Sync Service
    │       ├── vorschlag_service.py       # Intelligente Vorschläge
    │       ├── scheduler.py               # APScheduler für Cron-Jobs
    │       ├── ha_statistics_service.py   # HA-DB Statistik-Abfragen
    │       ├── community_service.py       # Community-Datenaufbereitung
    │       ├── plz_to_state.py           # PLZ→Bundesland Mapping (8.308 Einträge)
    │       ├── live_power_service.py      # Live Dashboard Aggregation (NEU v3.0.0)
    │       ├── mqtt_inbound_service.py   # MQTT-Inbound Subscribe + Cache (NEU v3.0.0)
    │       ├── mqtt_energy_history_service.py # MQTT Snapshots (NEU v3.0.0)
    │       ├── energie_profil_service.py  # Energieprofil: Aggregation + Rollup (NEU v3.1.0)
    │       ├── daten_checker.py          # Datenqualitätsprüfung
    │       ├── activity_service.py       # Aktivitäts-Logging
    │       └── cloud_import/              # Cloud-Import-Provider
    │           ├── __init__.py
    │           ├── base.py                 # ABC + Registry
    │           ├── ecoflow_powerocean.py
    │           ├── solaredge.py
    │           ├── fronius_solarweb.py
    │           ├── huawei_fusionsolar.py
    │           ├── growatt.py
    │           └── deye_solarman.py
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
        │   │   ├── portalImport.ts
        │   │   ├── cloudImport.ts
        │   │   ├── customImport.ts
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
        │   │   ├── CloudImportWizard.tsx
        │   │   ├── CustomImportWizard.tsx
        │   │   ├── Einrichtung.tsx          # Datenquellen-Hub
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
| anlagenname | VARCHAR(255) | Bezeichnung |
| leistung_kwp | FLOAT | Anlagenleistung in kWp |
| installationsdatum | DATE | Inbetriebnahme (optional) |
| standort_land | VARCHAR(5) | Land: DE, AT oder CH |
| standort_plz | VARCHAR(10) | Postleitzahl |
| standort_ort | VARCHAR(255) | Ort |
| standort_strasse | VARCHAR(255) | Adresse |
| latitude | FLOAT | Breitengrad (für PVGIS) |
| longitude | FLOAT | Längengrad (für PVGIS) |
| ausrichtung | VARCHAR(50) | DEPRECATED – jetzt bei PV-Modul Investitionen |
| neigung_grad | FLOAT | DEPRECATED – jetzt bei PV-Modul Investitionen |
| wechselrichter_hersteller | VARCHAR(50) | sma, fronius, kostal, etc. |
| mastr_id | VARCHAR(20) | MaStR-ID der Anlage |
| versorger_daten | JSON | Versorger & Zähler |
| wetter_provider | VARCHAR(30) | auto, open-meteo, brightsky, open-meteo-solar |
| sensor_mapping | JSON | HA-Sensor-Mapping |
| community_hash | VARCHAR(64) | Hash für Community-Löschung |
| steuerliche_behandlung | VARCHAR(30) | `keine_ust` oder `regelbesteuerung` |
| ust_satz_prozent | FLOAT | USt-Satz: DE=19, AT=20, CH=8.1 |
| created_at | DATETIME | Erstellungsdatum |
| updated_at | DATETIME | Letztes Update |

#### Monatsdaten

**Wichtig**: Diese Tabelle enthält primär Zählerwerte (Einspeisung, Netzbezug).

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
| durchschnittstemperatur | FLOAT | Wetter-API |
| sonderkosten_euro | FLOAT | Manuelle Eingabe |
| sonderkosten_beschreibung | VARCHAR(500) | Beschreibung der Sonderkosten |
| datenquelle | VARCHAR(50) | manual, csv, ha_import |
| notizen | VARCHAR(1000) | Freitext |
| created_at | DATETIME | Erstellungsdatum |
| updated_at | DATETIME | Letztes Update |

**Legacy-Felder (nicht mehr verwenden):**
- `pv_erzeugung_kwh` → Verwende InvestitionMonatsdaten
- `batterie_ladung_kwh` → Verwende InvestitionMonatsdaten
- `batterie_entladung_kwh` → Verwende InvestitionMonatsdaten
- `batterie_ladung_netz_kwh` → Arbitrage (Legacy)
- `batterie_ladepreis_cent` → Arbitrage (Legacy)

#### Investitionen

| Feld | Typ | Beschreibung |
|------|-----|--------------|
| id | INTEGER | Primary Key |
| anlage_id | INTEGER | Foreign Key → Anlage |
| typ | VARCHAR(50) | Investitionstyp (siehe InvestitionTyp Enum) |
| bezeichnung | VARCHAR(255) | Name der Komponente |
| anschaffungsdatum | DATE | Inbetriebnahme |
| anschaffungskosten_gesamt | FLOAT | Kaufpreis + Installation |
| anschaffungskosten_alternativ | FLOAT | Alternativkosten (z.B. neuer Verbrenner) |
| betriebskosten_jahr | FLOAT | Jährliche Betriebskosten |
| leistung_kwp | FLOAT | Leistung in kWp (PV-Module) |
| ausrichtung | VARCHAR(50) | Modulausrichtung (PV-Module) |
| neigung_grad | FLOAT | Modulneigung in Grad (PV-Module) |
| ha_entity_id | VARCHAR(255) | HA Entity-ID (für String-IST-Erfassung) |
| parameter | JSON | Typ-spezifische Parameter |
| einsparung_prognose_jahr | FLOAT | Jahres-Einsparungsprognose |
| co2_einsparung_prognose_kg | FLOAT | CO2-Einsparungsprognose |
| aktiv | BOOLEAN | Aktiv/Inaktiv |
| parent_investition_id | INTEGER | Foreign Key → Investitionen (für Parent-Child) |
| created_at | DATETIME | Erstellungsdatum |
| updated_at | DATETIME | Letztes Update |

**Investitionstypen:**

| Typ | Parameter (JSON) |
|-----|------------------|
| `wechselrichter` | - |
| `pv-module` | anzahl_module, modul_leistung_wp, ausrichtung, neigung_grad |
| `speicher` | kapazitaet_kwh, arbitrage_faehig |
| `e-auto` | v2h_faehig, nutzt_v2h, ist_dienstlich |
| `waermepumpe` | effizienz_modus, jaz, cop_heizung, cop_warmwasser, heizwaermebedarf_kwh, warmwasserbedarf_kwh, leistung_kw, pv_anteil_prozent, alter_energietraeger, alter_preis_cent_kwh, sg_ready |
| `wallbox` | ist_dienstlich |
| `balkonkraftwerk` | leistung_wp, anzahl, hat_speicher, speicher_kapazitaet_wh |
| `sonstiges` | kategorie (erzeuger/verbraucher/speicher), beschreibung |

**Stammdaten-Felder:**

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
| created_at | DATETIME | Erstellungsdatum |
| updated_at | DATETIME | Letztes Update |

**Hinweis:** Sonstige Erträge/Ausgaben werden in `verbrauch_daten` als `sonstige_ertraege` / `sonstige_ausgaben` Arrays gespeichert (v2.4.0).

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

**versorger_daten Struktur (Anlage):**

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
| netzbezug_arbeitspreis_cent_kwh | FLOAT | Preis pro kWh Netzbezug |
| einspeiseverguetung_cent_kwh | FLOAT | Vergütung pro kWh Einspeisung |
| grundpreis_euro_monat | FLOAT | Monatlicher Grundpreis |
| gueltig_ab | DATE | Gültigkeitsbeginn |
| gueltig_bis | DATE | Gültigkeitsende (NULL = aktuell gültig) |
| tarifname | VARCHAR(255) | Name des Tarifs |
| anbieter | VARCHAR(255) | Stromanbieter |
| vertragsart | VARCHAR(50) | fix, dynamisch, etc. |
| verwendung | VARCHAR(30) | `allgemein`, `waermepumpe` oder `wallbox` |
| created_at | DATETIME | Erstellungsdatum |
| updated_at | DATETIME | Letztes Update |

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
| `/api/sensor-mapping` | sensor_mapping.py | **Sensor-Mapping CRUD** |
| `/api/monatsabschluss` | monatsabschluss.py | **Monatsabschluss-Wizard** |
| `/api/scheduler` | scheduler.py | **Scheduler Status/Trigger** |
| `/api/community` | community.py | **Community-Teilen & Benchmark** |
| `/api/live` | live_dashboard.py | **Live Dashboard + MQTT-Inbound** (NEU v3.0.0) |
| `/api/aktueller-monat` | aktueller_monat.py | **Aktueller Monat Dashboard** |
| `/api/daten-checker` | daten_checker.py | **Datenqualitäts-Prüfung** |
| `/api/system-logs` | system_logs.py | **Aktivitäts-Protokolle** |
| `/api/portal-import` | portal_import.py | Portal-CSV Import (SMA, Fronius, EVCC) |
| `/api/cloud-import` | cloud_import.py | Cloud-API Import (SolarEdge, Fronius, Huawei, Growatt, Deye, EcoFlow) |
| `/api/custom-import` | custom_import.py | Custom CSV/JSON Import mit Feld-Mapping |

### Wichtige Endpoints

#### Cockpit (Dashboard-Daten)

```
GET /api/cockpit/uebersicht/{anlage_id}?jahr=2025       # Haupt-Dashboard
GET /api/cockpit/prognose-vs-ist/{anlage_id}             # PVGIS SOLL vs IST
GET /api/cockpit/nachhaltigkeit/{anlage_id}              # CO2-Bilanz
GET /api/cockpit/komponenten-zeitreihe/{anlage_id}       # Komponenten-Zeitreihen
GET /api/cockpit/pv-strings/{anlage_id}                  # String-Vergleich (Jahres-Ansicht)
GET /api/cockpit/pv-strings-gesamtlaufzeit/{anlage_id}   # String-Vergleich (Gesamtlaufzeit)
```

`uebersicht` liefert aggregierte Daten für alle Dashboard-Sektionen:
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
GET /api/aussichten/wetter/{anlage_id}        # Wetterdaten für Prognose
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

#### Sensor-Mapping API

```
GET    /api/sensor-mapping/{anlage_id}                    # Aktuelles Mapping abrufen
GET    /api/sensor-mapping/{anlage_id}/available-sensors   # Verfügbare HA-Sensoren
POST   /api/sensor-mapping/{anlage_id}                    # Mapping speichern
DELETE /api/sensor-mapping/{anlage_id}                    # Mapping löschen
GET    /api/sensor-mapping/{anlage_id}/status             # Kurzstatus
POST   /api/sensor-mapping/{anlage_id}/init-start-values  # MQTT-Startwerte initialisieren
```

**Mapping-Strategien:**
- `sensor` - Direkter HA-Sensor
- `kwp_verteilung` - Anteilige Verteilung nach kWp
- `cop_berechnung` - COP-basierte Berechnung (Wärmepumpe)
- `ev_quote` - Eigenverbrauchsquote-Berechnung
- `manuell` - Manuelle Eingabe im Wizard
- `keine` - Nicht erfassen

#### Monatsabschluss API

```
GET  /api/monatsabschluss/{anlage_id}/{jahr}/{monat}    # Status + Vorschläge
POST /api/monatsabschluss/{anlage_id}/{jahr}/{monat}    # Abschluss durchführen
GET  /api/monatsabschluss/naechster/{anlage_id}         # Nächster offener Monat
GET  /api/monatsabschluss/historie/{anlage_id}          # Letzte Abschlüsse
```

**VorschlagService liefert intelligente Vorschläge:**
- `vormonat` (Konfidenz 80%) - Wert vom Vormonat
- `vorjahr` (Konfidenz 70%) - Wert vom gleichen Monat im Vorjahr
- `berechnung` (Konfidenz 60%) - COP/EV-Quote basierte Berechnung
- `durchschnitt` (Konfidenz 50%) - Durchschnitt aller vorhandenen Werte

#### Scheduler API

```
GET  /api/scheduler                               # Scheduler-Status
POST /api/scheduler/monthly-snapshot              # Manueller Monatswechsel-Trigger
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

**Plausibilitätsprüfungen:**
- Legacy-Spalten (`PV_Erzeugung_kWh`, `Batterie_*_kWh`) werden validiert
- Fehler wenn NUR Legacy und PV-Module/Speicher existieren
- Fehler bei Mismatch Legacy vs. Summe Komponenten-Werte
- Warnung wenn redundant (±0.5 kWh Toleranz)
- Negative Werte werden blockiert
- Plausibilitätswarnungen (Sonnenstunden > 400h, Globalstrahlung > 250)

#### JSON Export/Import (Export-Version 1.1)

```
GET  /api/import/export/{anlage_id}          # Vollständiger JSON-Export
GET  /api/import/template/{anlage_id}        # CSV-Template herunterladen
GET  /api/import/template/{anlage_id}/download  # CSV-Template Download
GET  /api/import/pdf/{anlage_id}             # PDF-Export
POST /api/import/demo                        # Demo-Daten erstellen
DELETE /api/import/demo                      # Demo-Daten löschen
```

**Export** - Vollständige Anlage mit allen verknüpften Daten:
- Anlage-Stammdaten (inkl. versorger_daten, mastr_id, wetter_provider)
- **sensor_mapping** - HA Sensor-Zuordnungen
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

**Hinweis:** EEDC verwendet `HashRouter` (nicht BrowserRouter) für HA Ingress-Kompatibilität.
URLs im Browser erscheinen als `/#/cockpit` statt `/cockpit`.

```
/                       → Redirect zu /cockpit
│
│
├── /live               → LiveDashboard (Echtzeit-Leistungsdaten)
│                         EnergieFluss (SVG), GaugeChart (SoC), Tagesverlauf
├── /cockpit            → Dashboard (Übersicht)
│   ├── /aktueller-monat → AktuellerMonat (Live-Monatsdaten aus HA/Connector)
│   ├── /pv-anlage      → PVAnlageDashboard
│   ├── /e-auto         → EAutoDashboard
│   ├── /waermepumpe    → WaermepumpeDashboard
│   ├── /speicher       → SpeicherDashboard
│   ├── /wallbox        → WallboxDashboard
│   ├── /balkonkraftwerk → BalkonkraftwerkDashboard
│   └── /sonstiges      → SonstigesDashboard
│
├── /auswertungen       → Auswertung.tsx (6 Client-Side Tabs)
│   │                     Tabs: Energie, PV-Anlage, Komponenten, Finanzen, CO2, Investitionen
│   ├── /roi            → ROIDashboard (Jahres-Rendite p.a.)
│   ├── /prognose       → PrognoseVsIst
│   └── /export         → PDF-Export
│
├── /community          → Community.tsx (6 Client-Side Tabs)
│                         Tabs: Übersicht, PV-Ertrag, Komponenten, Regional, Trends, Statistiken
│                         (Tabs via useState, KEINE URL-Sub-Routes)
│
├── /aussichten         → Aussichten.tsx (4 Client-Side Tabs)
│                         Tabs: Kurzfristig, Langfristig, Trend, Finanzen
│                         (Tabs via useState, KEINE URL-Sub-Routes)
│
├── /monatsabschluss/:anlageId              → MonatsabschlussWizard
├── /monatsabschluss/:anlageId/:jahr/:monat → MonatsabschlussWizard (Monat)
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
    ├── /allgemein      → Settings.tsx
    ├── /einrichtung       → Einrichtung.tsx (Datenquellen-Hub)
    ├── /cloud-import      → CloudImportWizard.tsx
    ├── /custom-import     → CustomImportWizard.tsx
    ├── /portal-import     → PortalImportWizard.tsx
    ├── /daten-checker    → DatenChecker.tsx
    └── /protokolle       → Protokolle.tsx
```

### Komponenten-Hierarchie

```
main.tsx
├── ThemeProvider
└── AppWithSetup
    └── App.tsx
        └── HashRouter
            └── Layout.tsx
                ├── TopNavigation.tsx
                │   ├── Logo
                │   ├── MainTabs (Live, Cockpit, Auswertungen, Community, Aussichten)
                │   ├── SettingsDropdown (5 Kategorien)
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
GET /api/wetter/monat/koordinaten/{lat}/{lon}/{jahr}/{monat}  # Direkt per Koordinaten
GET /api/wetter/provider/{anlage_id}                          # Verfügbare Provider
GET /api/wetter/vergleich/{anlage_id}/{jahr}/{monat}          # Provider-Vergleich
GET /api/solar-prognose/{anlage_id}?tage=7                    # GTI-basierte PV-Prognose
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

**Erweiterte Methoden:**
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

### HA Statistics Service

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
```
GET  /api/ha-statistics/status                                     # Prüft DB-Verfügbarkeit
GET  /api/ha-statistics/monatswerte/{anlage_id}/{jahr}/{monat}     # Einzelner Monat
GET  /api/ha-statistics/verfuegbare-monate/{anlage_id}             # Alle Monate mit Daten
GET  /api/ha-statistics/alle-monatswerte/{anlage_id}               # Bulk-Abfrage
GET  /api/ha-statistics/monatsanfang/{anlage_id}/{jahr}/{monat}    # Zählerstand am Monatsanfang
GET  /api/ha-statistics/import-vorschau/{anlage_id}                # Vorschau mit Konflikten
POST /api/ha-statistics/import/{anlage_id}                         # Import mit Überschreib-Schutz
```

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
- `mqtt_energy_snapshot_job` - Alle 5 Minuten (NEU v3.0.0)
  - Speichert MQTT Energy-Zählerstände in SQLite
- `mqtt_energy_cleanup_job` - Täglich 03:00 (NEU v3.0.0)
  - Löscht Snapshots älter als 31 Tage
- `energie_profil_aggregation_job` - Täglich 00:15 (NEU v3.1.0)
  - Aggregiert Vortag für alle Anlagen → `TagesEnergieProfil` + `TagesZusammenfassung`

### HA MQTT Sync Service

**Datei:** `backend/services/ha_mqtt_sync.py`

**Funktion:** Koordiniert MQTT-Sensoren basierend auf Sensor-Mapping.

**Hauptfunktionen:**
- `setup_sensors_for_anlage()` - Erstellt alle MQTT Entities
- `trigger_month_rollover()` - Führt Monatswechsel durch

### Live Power Service (NEU v3.0.0)

**Datei:** `backend/services/live_power_service.py`

**Funktion:** Aggregiert Echtzeit-Leistungsdaten aus HA-Sensoren oder MQTT-Inbound für das Live Dashboard.

**Datenquellen (Priorität):**
1. HA-Sensoren (via Sensor-Mapping) — direkte REST-API-Abfrage
2. MQTT-Inbound Cache — In-Memory-Werte von subscribten Topics

**Berechnung:**
- Jede Investition wird als `LiveKomponente` mit `erzeugung_kw` / `verbrauch_kw` geliefert
- Haushalt = Residual: `max(0, Σ Quellen - Σ Senken)` (keine eigene Messung nötig)
- SoC-Gauges für Speicher und E-Auto (Key: `soc_{invId}`)
- Tages-kWh: HA-Statistiken → MQTT-Snapshots → leer (Fallback-Kette)

**API-Endpoints:**
```
GET /api/live/power/{anlage_id}        # Alle Leistungsdaten + Gauges + Tagesverlauf
GET /api/live/power/{anlage_id}/demo   # Demo-Modus mit Zufallswerten
```

### MQTT Inbound Service (NEU v3.0.0)

**Datei:** `backend/services/mqtt_inbound_service.py`

**Funktion:** Subscribt EEDC-definierte MQTT-Topics und cached Werte im Speicher.

**Topic-Struktur:**
```
eedc/{anlage_id}/live/{key}    → Echtzeit-Leistung (kW)
eedc/{anlage_id}/energy/{key}  → Zählerstände (kWh, monoton steigend)
```

**Hauptfunktionen:**
- `MqttInboundCache` — Thread-safe In-Memory-Cache für Live- und Energy-Werte
- `get_all_energy_raw()` — Aktuelle Zählerstände für Snapshot-Service

### MQTT Energy History Service (NEU v3.0.0)

**Datei:** `backend/services/mqtt_energy_history_service.py`

**Funktion:** SQLite-basierte Mini-History für Tageswerte aus MQTT Energy-Daten.

**Mechanismus:**
- Tabelle `mqtt_energy_snapshots` speichert Zählerstand-Snapshots alle 5 Minuten
- Tageswert = Differenz zwischen aktuellem Stand und Mitternacht-Snapshot
- Retention: 31 Tage, automatischer Cleanup um 03:00

### Energieprofil Service (NEU v3.1.0)

**Dateien:**

- `backend/services/energie_profil_service.py` — Aggregationslogik
- `backend/models/tages_energie_profil.py` — Datenmodelle

**Funktion:** Langfristige Persistierung stündlicher Energiedaten. HA-History hat nur ~10 Tage Retention — dieser Service sichert die Daten dauerhaft in SQLite.

**Datenmodelle:**

| Tabelle | Granularität | Inhalt |
| --- | --- | --- |
| `TagesEnergieProfil` | 24 Zeilen/Tag/Anlage | Stündliche kW-Werte: PV, Verbrauch, Einspeisung, Netzbezug, Batterie, Überschuss, Defizit + Wetter (Temperatur, Globalstrahlung) + SoC + Komponenten-JSON |
| `TagesZusammenfassung` | 1 Zeile/Tag/Anlage | Tagessummen (Überschuss/Defizit kWh), Peaks (PV, Netzbezug, Einspeisung kW), Batterie-Vollzyklen, Wetter-Min/Max, Performance Ratio, Datenqualität (stunden_verfuegbar) |

**Datenfluss-Pipeline:**

```
                           Scheduler (00:15 täglich)
                                    │
                    ┌───────────────┼──────────────────┐
                    ▼               ▼                  ▼
            HA Sensor History   MQTT Snapshots    Open-Meteo Archive
            (via get_tagesverlauf)                (Wetter-IST)
                    │               │                  │
                    └───────┬───────┘                  │
                            ▼                          │
                   aggregate_day()  ◄──────────────────┘
                     │          │
                     ▼          ▼
         TagesEnergieProfil   TagesZusammenfassung
         (24 Stunden-Zeilen)  (1 Tages-Zeile)
                                │
                                ▼  (beim Monatsabschluss)
                         rollup_month()
                                │
                                ▼
                     Monatsdaten-Felder aktualisiert
                     (ueberschuss_kwh, defizit_kwh,
                      batterie_vollzyklen, performance_ratio,
                      peak_netzbezug_kw)
```

**Hauptfunktionen:**

| Funktion | Trigger | Beschreibung |
| --- | --- | --- |
| `aggregate_day()` | Scheduler / Monatsabschluss | Holt Tagesverlauf + Wetter + SoC, berechnet 24 Stundenprofile + Tageszusammenfassung |
| `aggregate_yesterday_all()` | Scheduler 00:15 | Ruft `aggregate_day()` für alle Anlagen mit Sensor-Mapping auf |
| `rollup_month()` | Monatsabschluss | Aggregiert `TagesZusammenfassung` → `Monatsdaten`-Felder (Summe/Durchschnitt/Max) |
| `backfill_range()` | Monatsabschluss | Nachberechnung eines Datumsbereichs (limitiert durch HA-History ~10 Tage) |

**Berechnungsdetails:**

- **Überschuss/Defizit:** Pro Stunde `max(0, PV - Verbrauch)` bzw. umgekehrt, Summe = kWh (kW × 1h)
- **Batterie-Vollzyklen:** `Σ |ΔSoC| / 200` (ein Vollzyklus = 0→100→0 = 200% ΔSoC)
- **Performance Ratio:** `PV_Ertrag_kWh / (Strahlung_Wh/m² × kWp / 1000)`
- **Wetter:** Open-Meteo Historical API (Archiv) oder Forecast API (heute)
- **SoC:** Aus HA Sensor History (Stundenmittel)

**Integration mit Monatsabschluss:**

Beim Monatsabschluss werden zwei Schritte ausgeführt:
1. `backfill_range()` — Fehlende Tage nachberechnen (soweit HA-History reicht)
2. `rollup_month()` — Tagesdaten in Monatsdaten verdichten

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

### ROI-Metriken (Wichtig: Unterschiedliche Bedeutungen!)

| Metrik | Wo | Formel | Bedeutung |
|--------|-----|--------|-----------|
| **Jahres-Rendite** | Cockpit, Auswertung/Investitionen | `Jahres-Ertrag / Investition × 100` | Rendite pro Jahr (p.a.) |
| **Amortisations-Fortschritt** | Aussichten/Finanzen | `Kum. Erträge / Investition × 100` | Wie viel % bereits abbezahlt |

**Mehrkosten-Ansatz für Investitionen:**
Bei der ROI-Berechnung werden **Mehrkosten** gegenüber Alternativen berücksichtigt:
- **PV-System**: Volle Kosten (keine Alternative)
- **Wärmepumpe**: Kosten minus Gasheizung (`alternativ_kosten_euro` Parameter)
- **E-Auto**: Kosten minus Verbrenner (`alternativ_kosten_euro` Parameter)

### Community-Integration

```
EEDC Add-on                              Community Server
┌──────────────────────┐                 ┌──────────────────┐
│ CommunityShare.tsx   │ ── POST ──────→ │ /api/submit      │
│ CommunityVergleich   │ ── Proxy ─────→ │ /api/benchmark/  │
│   .tsx (embedded)    │                 │   anlage/{hash}  │
│ "Im Browser öffnen"  │ ── Link ──────→ │ /?anlage=HASH    │
└──────────────────────┘                 └──────────────────┘
```

**Relevante Dateien:**
- `backend/services/community_service.py` – Datenaufbereitung + Anonymisierung
- `backend/services/plz_to_state.py` – Vollständiges PLZ→Bundesland Dictionary (8.308 Einträge, O(1) Lookup)
- `backend/api/routes/community.py` – API Routes + Benchmark-Proxy
- `frontend/src/pages/CommunityShare.tsx` – Upload UI
- `frontend/src/pages/CommunityVergleich.tsx` – Benchmark-Analyse (6 Tabs)
- `frontend/src/api/community.ts` – API Client

### Cloud-Import-Provider (v2.7.0+)

**Verzeichnis:** `backend/services/cloud_import/`

**Architektur:** ABC-Pattern mit `@register_provider` Decorator und Provider-Registry.

**Verfügbare Provider (alle ungetestet):**

| Provider | API | Auth |
|----------|-----|------|
| EcoFlow PowerOcean | Developer API | HMAC-SHA256 |
| SolarEdge | Monitoring API v1 | API-Key |
| Fronius SolarWeb | SolarWeb API | AccessKeyId + AccessKeyValue |
| Huawei FusionSolar | thirdData API | XSRF-Token |
| Growatt | OpenAPI | MD5-Auth |
| Deye/Solarman | SolarMAN OpenAPI v1.1.0 | OAuth2 + SHA256 |

**Output:** Alle Provider liefern `ParsedMonthData` als einheitliches Format.

### Custom-Import (v2.8.0)

**Datei:** `backend/api/routes/custom_import.py`

**Funktion:** Beliebige CSV/JSON-Dateien mit benutzerdefinierbarem Feld-Mapping importieren.

**Features:**
- Automatische CSV-Dialekt-Erkennung (Trennzeichen, Dezimalformat)
- Auto-Mapping anhand von Spaltenbezeichnungen (deutsch + englisch)
- Einheiten-Umrechnung (Wh/kWh/MWh)
- Mapping-Templates in Settings-Tabelle speicherbar
- 4-Schritt-Wizard: Upload → Mapping → Vorschau → Import

**API-Endpoints:**
```
POST   /api/custom-import/analyze          # Datei analysieren, Spalten erkennen
POST   /api/custom-import/preview          # Mapping anwenden, Vorschau
GET    /api/custom-import/templates        # Gespeicherte Templates laden
POST   /api/custom-import/templates/{name} # Template speichern
DELETE /api/custom-import/templates/{name} # Template löschen
GET    /api/custom-import/fields           # Verfügbare EEDC-Zielfelder
```

---

## 9. Entwickler-Workflow

### Repository-Struktur

**`eedc-homeassistant` ist die Source of Truth** für alle Änderungen (Backend, Frontend, Docs, HA-Config).

Das `eedc`-Standalone-Repo ist ein **Spiegel** und wird ausschließlich per Release-Script synchronisiert.

```
eedc-homeassistant (Source of Truth)
├── eedc/backend/          ─── release.sh ───→  eedc (Standalone-Spiegel)
├── eedc/frontend/         ─── release.sh ───→  eedc (Standalone-Spiegel)
├── website/
├── docs/
└── CHANGELOG.md

eedc-community (unabhängig)
```

**Regeln:**

- Alle Änderungen in `eedc-homeassistant` machen, nie direkt in `eedc`
- Immer auf `main` arbeiten (keine Feature-Branches, Einzelentwickler-Projekt)
- Kein `git subtree` (abgeschafft)

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

### Release-Workflow

Ein Script erledigt alles — Version bumpen, committen, taggen, pushen und Standalone-Repo synchronisieren:

```bash
cd /home/gernot/claude/eedc-homeassistant
./scripts/release.sh 2.8.6
```

Das Script aktualisiert automatisch alle 4 Versionsdateien:

| Datei | Feld |
| ----- | ---- |
| `eedc/backend/core/config.py` | `APP_VERSION` |
| `eedc/frontend/src/config/version.ts` | `APP_VERSION` |
| `eedc/config.yaml` | `version` (HA Add-on) |
| `eedc/run.sh` | Version im Echo |

**Wichtig:** HA Add-ons erkennen Updates über das `version`-Feld in `config.yaml`. Jede Änderung, die beim User ankommen soll, benötigt ein Release.

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

*Letzte Aktualisierung: März 2026*
