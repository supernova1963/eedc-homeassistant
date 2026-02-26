# CLAUDE.md - Entwickler-Kontext für Claude Code

> **Hinweis:** Dies ist der Kontext für KI-gestützte Entwicklung. Für Benutzer-Dokumentation siehe [docs/BENUTZERHANDBUCH.md](docs/BENUTZERHANDBUCH.md), für Architektur siehe [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).

## Projektübersicht

**eedc** (Energie Effizienz Data Center) - Standalone PV-Analyse mit optionaler HA-Integration.

**Version:** 2.4.1 | **Status:** Stable Release

## Quick Reference

### Entwicklungsserver starten
```bash
# Backend (Terminal 1)
cd eedc && source backend/venv/bin/activate
uvicorn backend.main:app --reload --port 8099

# Frontend (Terminal 2)
cd eedc/frontend && npm run dev

# URLs
# Frontend: http://localhost:3000 (Vite Proxy auf Backend)
# API Docs: http://localhost:8099/api/docs
```

### Versionierung (bei Releases aktualisieren!)
```
eedc/backend/core/config.py      → APP_VERSION
eedc/frontend/src/config/version.ts → APP_VERSION
eedc/config.yaml                 → version
eedc/run.sh                      → Echo-Statement
```

### Release-Checkliste
```bash
# 1. Version in allen Dateien aktualisieren (siehe oben)

# 2. CHANGELOG.md aktualisieren - WICHTIG: BEIDE Dateien!
#    - /CHANGELOG.md (Repository-Root)
#    - /eedc/CHANGELOG.md (Home Assistant Add-on liest diese!)
#    Am einfachsten: Root-Changelog pflegen, dann kopieren:
cp CHANGELOG.md eedc/CHANGELOG.md

# 3. Dokumentationen Version aktualisieren
#    - CLAUDE.md, BENUTZERHANDBUCH.md, ARCHITEKTUR.md, DEVELOPMENT.md

# 4. Frontend Build erstellen
cd eedc/frontend && npm run build

# 5. Git Commit, Tag erstellen und pushen
git add -A
git commit -m "feat: Version X.Y.Z - Beschreibung"
git tag -a vX.Y.Z -m "Version X.Y.Z - Beschreibung"
git push && git push origin vX.Y.Z

# 6. GitHub Release erstellen
gh release create vX.Y.Z \
  --title "vX.Y.Z - Titel" \
  --prerelease \  # nur für Beta/Alpha
  --notes "Release Notes hier..."

# Releases: https://github.com/supernova1963/eedc-homeassistant/releases
```

> **WICHTIG:** Home Assistant Add-ons lesen das Changelog aus `eedc/CHANGELOG.md`,
> nicht aus dem Repository-Root! Bei Releases immer beide Dateien synchron halten.

## Architektur-Prinzipien

1. **Standalone-First:** Keine HA-Abhängigkeit für Kernfunktionen
2. **Datenquellen getrennt:**
   - `Monatsdaten` = Zählerwerte (Einspeisung, Netzbezug)
   - `InvestitionMonatsdaten` = Komponenten-Details (PV, Speicher, E-Auto, etc.)
3. **Legacy-Felder NICHT verwenden:**
   - `Monatsdaten.pv_erzeugung_kwh` → Nutze `InvestitionMonatsdaten`
   - `Monatsdaten.batterie_*` → Nutze `InvestitionMonatsdaten`

## Kritische Code-Patterns

### SQLAlchemy JSON-Felder
```python
from sqlalchemy.orm.attributes import flag_modified

# WICHTIG: Nach Änderung an JSON-Feldern immer flag_modified aufrufen!
obj.verbrauch_daten["key"] = value
flag_modified(obj, "verbrauch_daten")  # Ohne das wird die Änderung NICHT persistiert!
db.commit()
```

### 0-Werte prüfen
```python
# FALSCH - 0 wird als False gewertet
if val:
    ...

# RICHTIG
if val is not None:
    ...
```

## Dateistruktur (wichtigste Dateien)

```
eedc/
├── backend/
│   ├── main.py                    # FastAPI Entry + /stats + Scheduler
│   ├── api/routes/
│   │   ├── cockpit.py             # Dashboard-Aggregation (jahres_rendite_prozent)
│   │   ├── aussichten.py          # Prognosen: Kurzfristig, Langfristig, Trend, Finanzen
│   │   ├── import_export/         # Import/Export Package (CSV, JSON, Demo)
│   │   ├── monatsdaten.py         # CRUD + Berechnungen
│   │   ├── investitionen.py       # Parent-Child, ROI (Jahres-Rendite p.a.)
│   │   ├── sensor_mapping.py      # HA Sensor-Zuordnung
│   │   ├── monatsabschluss.py     # Monatsabschluss-Wizard API
│   │   └── ha_statistics.py       # HA DB-Abfrage für Monatswerte (NEU v2.0.0)
│   ├── core/config.py             # APP_VERSION
│   └── services/
│       ├── wetter_service.py      # Multi-Provider Wetterdaten
│       ├── brightsky_service.py   # DWD-Daten via Bright Sky API
│       ├── solar_forecast_service.py  # Open-Meteo Solar GTI
│       ├── prognose_service.py    # Prognose-Berechnungen
│       ├── mqtt_client.py         # HA Export + MQTT Auto-Discovery
│       ├── ha_mqtt_sync.py        # MQTT Sync Service
│       ├── scheduler.py           # Cron-Jobs
│       ├── vorschlag_service.py   # Intelligente Vorschläge
│       └── ha_statistics_service.py # HA-DB Statistik-Abfragen (NEU v2.0.0)
│
└── frontend/src/
    ├── pages/
    │   ├── Dashboard.tsx          # Cockpit-Übersicht
    │   ├── Auswertung.tsx         # 7 Analyse-Tabs (inkl. Community)
    │   ├── CommunityVergleich.tsx # Community-Benchmark (NEU v2.0.3)
    │   ├── Aussichten.tsx         # 4 Prognose-Tabs
    │   ├── PVAnlageDashboard.tsx  # String-Vergleich (Jahr-Parameter!)
    │   ├── SensorMappingWizard.tsx    # HA Sensor-Zuordnung
    │   ├── MonatsabschlussWizard.tsx  # Monatliche Dateneingabe
    │   └── HAStatistikImport.tsx      # HA-Statistik Bulk-Import (NEU v2.0.0)
    ├── components/
    │   ├── forms/MonatsdatenForm.tsx  # Dynamische Felder
    │   ├── forms/SonstigePositionenFields.tsx  # Sonstige Erträge/Ausgaben (shared, NEU v2.4.0)
    │   ├── pv/PVStringVergleich.tsx   # SOLL-IST
    │   └── sensor-mapping/            # Wizard-Steps
    │       ├── FeldMappingInput.tsx
    │       ├── BasisSensorenStep.tsx
    │       ├── PVModuleStep.tsx
    │       ├── SpeicherStep.tsx
    │       ├── WaermepumpeStep.tsx
    │       ├── EAutoStep.tsx
    │       └── MappingSummaryStep.tsx
    └── config/version.ts          # APP_VERSION
```

## Datenmodell (Kurzfassung)

### Parent-Child Beziehungen
```
Wechselrichter (Parent)
├── PV-Module (Child) [PFLICHT]
└── DC-Speicher (Child) [optional, Hybrid-WR]

AC-Speicher, E-Auto, WP, Wallbox, BKW, Sonstiges = eigenständig
```

### InvestitionMonatsdaten.verbrauch_daten (JSON)
```json
// PV-Module
{ "pv_erzeugung_kwh": 450.5 }

// Speicher
{ "ladung_kwh": 200, "entladung_kwh": 185, "ladung_netz_kwh": 50 }

// E-Auto
{ "km_gefahren": 1200, "ladung_pv_kwh": 130, "ladung_netz_kwh": 86, "v2h_entladung_kwh": 25 }
// E-Auto (dienstlich → ist_dienstlich=true in Investition.parameter)
// ROI rechnet mit AG-Erstattung statt Benzinvergleich

// Wärmepumpe
{ "stromverbrauch_kwh": 450, "heizenergie_kwh": 1800, "warmwasser_kwh": 200 }

// Balkonkraftwerk (mit optionalem Speicher)
{ "pv_erzeugung_kwh": 65.0, "eigenverbrauch_kwh": 60.0, "speicher_ladung_kwh": 15, "speicher_entladung_kwh": 14 }

// Wallbox (ist_dienstlich=true → AG-Erstattung statt Eigennutzung)
{ "ladung_kwh": 180 }

// Sonstiges - Erzeuger
{ "erzeugung_kwh": 120, "eigenverbrauch_kwh": 100, "einspeisung_kwh": 20 }

// Sonstiges - Verbraucher
{ "verbrauch_kwh": 200, "bezug_pv_kwh": 80, "bezug_netz_kwh": 120 }

// Sonstiges - Speicher
{ "ladung_kwh": 50, "entladung_kwh": 45 }

// Sonstige Erträge & Ausgaben (in allen Typen via Monatsdaten-Formular)
{ "sonstige_ertraege": [{"bezeichnung": "Einspeisebonus", "betrag": 15.0}],
  "sonstige_ausgaben": [{"bezeichnung": "Versicherung", "betrag": 8.50}] }
```

### Wärmepumpe: Effizienz-Parameter (Investition.parameter)
```json
// Modus A: Gesamt-JAZ (gemessen vor Ort - genauester Wert wenn verfügbar)
{ "effizienz_modus": "gesamt_jaz", "jaz": 3.5, "heizwaermebedarf_kwh": 12000, "warmwasserbedarf_kwh": 3000 }

// Modus B: SCOP (EU-Energielabel - realistischer als Hersteller-COP) - NEU in beta.10
{ "effizienz_modus": "scop", "scop_heizung": 4.5, "scop_warmwasser": 3.2, "vorlauftemperatur": "35", "heizwaermebedarf_kwh": 12000, "warmwasserbedarf_kwh": 3000 }

// Modus C: Getrennte COPs (präzise Betriebspunkte)
{ "effizienz_modus": "getrennte_cops", "cop_heizung": 3.9, "cop_warmwasser": 3.0, "heizwaermebedarf_kwh": 12000, "warmwasserbedarf_kwh": 3000 }
```

**Effizienz-Modi im Vergleich:**
- **JAZ (Jahresarbeitszahl):** Tatsächlich gemessener Wert am Standort - der genaueste Wert
- **SCOP (Seasonal COP):** EU-genormter saisonaler COP vom Energielabel - realistischer als momentane COPs
- **Getrennte COPs:** Separate Werte für Heizung und Warmwasser - präziser bei unterschiedlichen Vorlauftemperaturen

### Anlage.versorger_daten (JSON) - NEU in beta.6
```json
{
  "strom": {
    "name": "Stadtwerke München",
    "kundennummer": "12345678",
    "portal_url": "https://kundenportal.swm.de",
    "notizen": "",
    "zaehler": [
      {"bezeichnung": "Einspeisung", "nummer": "1EMH0012345678", "notizen": ""},
      {"bezeichnung": "Bezug", "nummer": "1EMH0087654321", "notizen": ""}
    ]
  },
  "gas": { "name": "...", "kundennummer": "...", "zaehler": [...] },
  "wasser": { "name": "...", "kundennummer": "...", "zaehler": [...] }
}
```

### Investition.parameter: Stammdaten-Felder (NEU in beta.6)
```json
{
  // Bestehende technische Parameter...

  // Gerätedaten
  "stamm_hersteller": "Fronius",
  "stamm_modell": "Symo GEN24 10.0",
  "stamm_seriennummer": "12345678",
  "stamm_garantie_bis": "2032-06-15",
  "stamm_mastr_id": "SEE123456789",  // Nur Wechselrichter
  "stamm_notizen": "",

  // Ansprechpartner
  "ansprechpartner_firma": "Solar Mustermann GmbH",
  "ansprechpartner_name": "Max Mustermann",
  "ansprechpartner_telefon": "+49 123 456789",
  "ansprechpartner_email": "service@solar-mustermann.de",
  "ansprechpartner_ticketsystem": "https://portal.solar-mustermann.de",
  "ansprechpartner_kundennummer": "K-12345",
  "ansprechpartner_vertragsnummer": "V-2024-001",

  // Wartungsvertrag
  "wartung_vertragsnummer": "WV-2024-001",
  "wartung_anbieter": "Solar Mustermann GmbH",
  "wartung_gueltig_bis": "2026-12-31",
  "wartung_kuendigungsfrist": "3 Monate",
  "wartung_leistungsumfang": "Jährliche Inspektion, Reinigung"
}
```

**Vererbung:** PV-Module und DC-Speicher (mit `parent_investition_id`) erben Ansprechpartner/Wartung vom Wechselrichter. Leere Felder zeigen "(erbt von Wechselrichter)".

## API Endpoints (häufig verwendet)

```
GET  /api/cockpit/uebersicht/{anlage_id}?jahr=2025   # Dashboard-Daten
GET  /api/cockpit/pv-strings/{anlage_id}?jahr=2025   # SOLL-IST Vergleich
POST /api/import/csv/{anlage_id}                     # CSV Import
GET  /api/import/template/{anlage_id}                # CSV Template-Info
GET  /api/import/export/{anlage_id}/full             # Vollständiger JSON-Export (v1.1: inkl. sensor_mapping)
POST /api/import/json                                # JSON-Import (Backup/Restore)
GET  /api/wetter/monat/{anlage_id}/{jahr}/{monat}    # Wetter Auto-Fill
GET  /api/wetter/provider/{anlage_id}                # Verfügbare Wetter-Provider
GET  /api/wetter/vergleich/{anlage_id}/{jahr}/{monat} # Provider-Vergleich
GET  /api/solar-prognose/{anlage_id}?tage=7          # GTI-basierte PV-Prognose
GET  /api/monatsdaten/aggregiert/{anlage_id}         # Aggregierte Monatsdaten

# Aussichten (Prognosen)
GET  /api/aussichten/kurzfristig/{anlage_id}         # 7-Tage Wetterprognose
GET  /api/aussichten/langfristig/{anlage_id}         # 12-Monats-Prognose (PVGIS)
GET  /api/aussichten/trend/{anlage_id}               # Trend-Analyse + Degradation
GET  /api/aussichten/finanzen/{anlage_id}            # Finanz-Prognose + Amortisation

# Sensor-Mapping
GET  /api/sensor-mapping/{anlage_id}                 # Aktuelles Mapping abrufen
GET  /api/sensor-mapping/{anlage_id}/available-sensors # Verfügbare HA-Sensoren
POST /api/sensor-mapping/{anlage_id}                 # Mapping speichern
GET  /api/sensor-mapping/{anlage_id}/status          # Kurzstatus

# Monatsabschluss
GET  /api/monatsabschluss/{anlage_id}/{jahr}/{monat} # Status + Vorschläge
POST /api/monatsabschluss/{anlage_id}/{jahr}/{monat} # Monatsdaten speichern
GET  /api/monatsabschluss/naechster/{anlage_id}      # Nächster offener Monat
GET  /api/monatsabschluss/historie/{anlage_id}       # Letzte Abschlüsse

# Scheduler
GET  /api/scheduler                                  # Scheduler-Status
POST /api/scheduler/monthly-snapshot                 # Manueller Monatswechsel

# HA Statistics - Direkte DB-Abfrage (NEU v2.0.0)
GET  /api/ha-statistics/status                       # Prüft ob HA-DB verfügbar
GET  /api/ha-statistics/monatswerte/{anlage_id}/{jahr}/{monat}  # Einzelner Monat
GET  /api/ha-statistics/verfuegbare-monate/{anlage_id}          # Alle Monate mit Daten
GET  /api/ha-statistics/alle-monatswerte/{anlage_id}            # Bulk: Alle Monatswerte
GET  /api/ha-statistics/monatsanfang/{anlage_id}/{jahr}/{monat} # Startwerte für MQTT
GET  /api/ha-statistics/import-vorschau/{anlage_id}             # Import-Vorschau mit Konflikten
POST /api/ha-statistics/import/{anlage_id}                      # Import mit Überschreib-Schutz

# Strompreise - Spezialtarife (NEU v2.4.0)
GET  /api/strompreise/aktuell/{anlage_id}/{verwendung} # Aktueller Preis für Verwendung (mit Fallback auf allgemein)

# Community (NEU v2.0.3)
GET  /api/community/status                            # Server-Status
GET  /api/community/preview/{anlage_id}               # Vorschau der zu teilenden Daten
POST /api/community/share/{anlage_id}                 # Daten anonym teilen
DELETE /api/community/delete/{anlage_id}              # Geteilte Daten löschen
GET  /api/community/benchmark/{anlage_id}             # Benchmark-Daten abrufen (nur wenn geteilt!)
```

## ROI-Metriken (WICHTIG: Unterschiedliche Bedeutungen!)

| Metrik | Wo | Formel | Bedeutung |
|--------|-----|--------|-----------|
| **Jahres-Rendite** | Cockpit, Auswertung/Investitionen | `Jahres-Ertrag / Investition × 100` | Rendite pro Jahr (p.a.) |
| **Amortisations-Fortschritt** | Aussichten/Finanzen | `Kum. Erträge / Investition × 100` | Wie viel % bereits abbezahlt |

### Mehrkosten-Ansatz für Investitionen
Bei der ROI-Berechnung werden **Mehrkosten** gegenüber Alternativen berücksichtigt:
- **PV-System**: Volle Kosten (keine Alternative)
- **Wärmepumpe**: Kosten minus Gasheizung (`alternativ_kosten_euro` Parameter)
- **E-Auto**: Kosten minus Verbrenner (`alternativ_kosten_euro` Parameter)

## Bekannte Fallstricke

| Problem | Lösung |
|---------|--------|
| JSON-Änderungen werden nicht gespeichert | `flag_modified(obj, "field_name")` aufrufen |
| 0-Werte verschwinden | `is not None` statt `if val` |
| SOLL-IST zeigt falsches Jahr | `jahr` Parameter explizit übergeben |
| Legacy pv_erzeugung_kwh wird verwendet | InvestitionMonatsdaten abfragen |
| ROI-Werte unterschiedlich | Cockpit = Jahres-%, Aussichten = Kumuliert-% |

## Wetterdienst-Integration

### Multi-Provider Architektur
EEDC unterstützt mehrere Wetterdatenquellen mit automatischer Provider-Auswahl:

| Provider | Beschreibung | Region | Daten |
|----------|-------------|--------|-------|
| **auto** (Standard) | Automatische Auswahl | - | - |
| **brightsky** | DWD-Daten via Bright Sky REST API | Deutschland | Historisch + MOSMIX |
| **open-meteo** | Open-Meteo Archive API | Weltweit | Historisch + Forecast |
| **open-meteo-solar** | Open-Meteo Solar mit GTI | Weltweit | Forecast + GTI |

### Fallback-Kette
1. Gewählter Provider → 2. Alternative → 3. PVGIS TMY → 4. Statische Defaults

### Anlage.wetter_provider
Neues Feld zur Provider-Auswahl pro Anlage. Migration wird automatisch bei Startup ausgeführt.

### API-Endpoints
```
GET /api/wetter/monat/{anlage_id}/{jahr}/{monat}?provider=auto
GET /api/wetter/provider/{anlage_id}           # Verfügbare Provider
GET /api/wetter/vergleich/{anlage_id}/{jahr}/{monat}  # Provider-Vergleich
GET /api/solar-prognose/{anlage_id}?tage=7&pro_string=false  # GTI-Prognose
```

### GTI (Global Tilted Irradiance)
Open-Meteo Solar berechnet GTI für geneigte PV-Module basierend auf:
- Neigung und Ausrichtung aus PV-Modul-Konfiguration
- Temperaturkorrektur (Wirkungsgradminderung bei Hitze)
- Systemverluste aus PVGIS-Einstellungen

## Offene Features

- [x] PDF-Export ✓ (beta.12)
- [x] HA-Integration Bereinigung ✓ (beta.13)
- [x] Sensor-Mapping-Wizard ✓ (v1.1.0)
- [x] MQTT Auto-Discovery für Monatswerte ✓ (v1.1.0)
- [x] Monatsabschluss-Wizard ✓ (v1.1.0)
- [x] HA-Statistik Bulk-Import ✓ (v2.0.0)
- [x] Community als Hauptmenüpunkt ✓ (v2.1.0)
- [x] Sonstige Positionen ✓ (v2.4.0)
- [x] Spezialtarife WP/Wallbox ✓ (v2.4.0)
- [x] Kleinunternehmerregelung ✓ (v2.4.0)
- [x] Firmenwagen/Dienstliches Laden ✓ (v2.4.0)
- [x] Realisierungsquote ✓ (v2.4.0)
- [ ] KI-Insights

## HA-Integration Status (v2.0.0)

**Neu in v2.0.0:**
- **HA-Statistik-Import:** Direkte Abfrage der Home Assistant Langzeitstatistiken
- **Bulk-Import:** Rückwirkende Befüllung aller Monatsdaten seit Installation
- **Import-Vorschau:** Konflikt-Erkennung mit Überschreib-Schutz
- **Monatsabschluss:** "Werte aus HA laden" Button für einzelne Monate
- **Sensor-Mapping:** Startwerte aus HA-DB Option beim Setup

**Voraussetzung:**
- Volume-Mapping `config:ro` für Lesezugriff auf HA-Datenbank
- ⚠️ BREAKING CHANGE: Neuinstallation des Add-ons erforderlich!

**Features aus v1.1.0:**
- **Sensor-Mapping-Wizard:** Zuordnung HA-Sensoren zu EEDC-Feldern
- **MQTT Auto-Discovery:** Erstellt automatisch `number` und `sensor` Entities in HA
- **Monatsabschluss-Wizard:** Geführte monatliche Dateneingabe mit Vorschlägen
- **Scheduler:** Cron-Job für Monatswechsel-Snapshot (1. des Monats 00:01)

**Anlage.sensor_mapping (JSON) - NEU:**
```json
{
  "basis": {
    "einspeisung": {"strategie": "sensor", "sensor_id": "sensor.zaehler_einspeisung"},
    "netzbezug": {"strategie": "sensor", "sensor_id": "sensor.zaehler_bezug"}
  },
  "investitionen": {
    "1": {"pv_erzeugung_kwh": {"strategie": "kwp_verteilung", "parameter": {"anteil": 0.55}}}
  },
  "mqtt_setup_complete": true,
  "mqtt_setup_timestamp": "2026-02-17T10:00:00Z"
}
```

**Schätzungsstrategien:**
- `sensor` - Direkt aus HA-Sensor
- `kwp_verteilung` - Anteilig nach kWp (PV-Module)
- `cop_berechnung` - COP × Stromverbrauch (Wärmepumpe)
- `ev_quote` - Nach Eigenverbrauchsquote (E-Auto)
- `manuell` - Eingabe im Wizard
- `keine` - Nicht erfassen

**DEPRECATED (nicht mehr verwenden):**
```python
# Anlage Model - diese Felder sind deprecated:
ha_sensor_pv_erzeugung      # DEPRECATED - nutze sensor_mapping
ha_sensor_einspeisung       # DEPRECATED - nutze sensor_mapping
ha_sensor_netzbezug         # DEPRECATED - nutze sensor_mapping
ha_sensor_batterie_ladung   # DEPRECATED - nutze sensor_mapping
ha_sensor_batterie_entladung # DEPRECATED - nutze sensor_mapping
```

## Letzte Änderungen (v2.4.1)

**v2.4.1 - Version-Bump für HA Add-on Update-Erkennung**

**v2.4.0 - Steuerliche Behandlung, Spezialtarife, Sonstige Positionen, Firmenwagen:**

- **Kleinunternehmerregelung (Issue #9):** Neue Felder `steuerliche_behandlung` (`keine_ust`/`regelbesteuerung`) und `ust_satz_prozent` auf Anlage-Model. Bei Regelbesteuerung wird USt auf Eigenverbrauch als Kostenfaktor in Cockpit, Aussichten und ROI berechnet. `berechne_ust_eigenverbrauch()` in calculations.py.
- **Spezialtarife (Issue #8):** Neues Feld `verwendung` auf Strompreis-Model (`allgemein`/`waermepumpe`/`wallbox`). Neuer Endpoint `/api/strompreise/aktuell/{anlage_id}/{verwendung}` mit Fallback. Cockpit nutzt automatisch den passenden Tarif pro Komponente.
- **Sonstige Positionen (Issue #7):** Neuer Investitionstyp `sonstiges` mit Kategorien (`erzeuger`/`verbraucher`/`speicher`). Flexible verbrauch_daten je Kategorie. Sonstige Erträge & Ausgaben in MonatsdatenForm. Neue shared Component `SonstigePositionenFields`.
- **Firmenwagen & dienstliches Laden:** Neues Flag `ist_dienstlich` an Wallbox und E-Auto (in `Investition.parameter`). ROI-Berechnung berücksichtigt AG-Erstattung statt Benzinvergleich bei dienstlichen Fahrzeugen.
- **Realisierungsquote:** Neues Panel in Auswertung/Investitionen vergleicht historische Erträge mit konfigurierter Prognose. Farbkodierung: ≥90% grün, ≥70% gelb, <70% rot.
- **Methodenhinweise:** Amortisationsbalken im Cockpit und Komponenten-Dashboards (E-Auto, WP, BKW) zeigen Basis-Hinweis.
- **Grundpreis in Netzbezugskosten:** Monatlicher Stromgrundpreis (`grundpreis_euro_monat`) wird zu Netzbezugskosten addiert.
- **Bugfix (Issue #10):** Leeres Installationsdatum verursachte Setup-Wizard-Fehler

**v2.3.0 - Dashboard-Modernisierung und DACH-Onboarding:**

- **Dashboard-Modernisierung:** Hero-Leiste, Energie-Fluss-Diagramm, Ring-Gauges, Sparkline, Amortisations-Fortschrittsbalken
- **DACH-Onboarding:** `standort_land` (DE/AT/CH) im Anlage-Modell, Community-Regionszuordnung

**v2.2.0 - Regional Tab: Choropleth-Karte und Performance-Metriken:**

- **Choropleth Deutschlandkarte:** Interaktive Bundesland-Karte via `react-simple-maps` + GeoJSON (`deutschland-bundeslaender.geo.json`)
  - Farbkodierung nach spezifischem Ertrag (5 Stufen)
  - Hover-Tooltip mit Performance-Details (Speicher, WP-JAZ, E-Auto, Wallbox, BKW)
- **Performance-Metriken statt Ausstattungsquoten:** Regional-Tabelle zeigt jetzt durchschnittliche Leistungsdaten:
  - 🔋 Ø Ladung/Entladung kWh/Mon (getrennt)
  - ♨️ Ø JAZ (Jahresarbeitszahl)
  - 🚗 Ø km/Mon + kWh zuhause geladen (gesamt − extern)
  - 🔌 Ø kWh/Mon + PV-Anteil %
  - 🪟 Ø BKW-Ertrag kWh/Mon
- **Community Server Updates:** Neue Aggregationsfelder in `RegionStatistik` (`avg_speicher_ladung_kwh`, `avg_speicher_entladung_kwh`, `avg_wp_jaz`, `avg_eauto_km`, `avg_eauto_ladung_kwh`, `avg_wallbox_kwh`, `avg_wallbox_pv_anteil`, `avg_bkw_kwh`)
- **Lokale Entwicklungsumgebung:** Python 3.11 venv, VS Code Tasks (Cmd+Shift+B), `.vscode/launch.json`, `.nvmrc` (Node 20)
- **TypeScript Import-Fixes:** Casing-Korrekturen (`GeoJSON` → `Geojson`, etc.)

**v2.1.0 - Community als Hauptmenüpunkt:**

- **Community im Hauptmenü:** Eigener Navigationsbereich auf Augenhöhe mit Cockpit, Auswertungen, Aussichten
- **6 Tab-Struktur:** Übersicht, PV-Ertrag, Komponenten, Regional, Trends, Statistiken
- **Gamification:** 7 Achievements (Autarkiemeister, Effizienzwunder, Solarprofi, etc.)
- **Radar-Chart:** Eigene Performance vs. Community auf 6 Achsen
- **PV-Ertrag Deep-Dive:** Monatlicher Ertrag vs. Community-Durchschnitt, Jahresübersicht
- **Komponenten Deep-Dives:** Detaillierte Analysen für Speicher, Wärmepumpe, E-Auto, Wallbox, BKW
- **Regional Tab:** Bundesland-Vergleich und regionale Einordnung
- **Trends Tab:** Ertragsverlauf, saisonale Performance, Jahresvergleich
- **Tooltips:** Erklärungen für Community-KPIs
- **Chronologische Sortierung:** Monatsdaten korrekt sortiert in Charts

**v2.0.3 - Community-Vergleich:**

- **Community-Tab in Auswertungen:** Neuer Tab nach Teilen der Daten
- **Komponenten-Benchmarks:** Speicher, Wärmepumpe, E-Auto Vergleiche
- **Zeitraum-Auswahl:** Letzter Monat, 12 Monate, Letztes Jahr, Seit Installation
- **Zugangslogik:** Tab nur sichtbar wenn Daten geteilt wurden
- **Backend-Proxy:** `/api/community/benchmark/{anlage_id}`

**v2.0.2 - Legacy-Migration:**

- CSV-Import migriert automatisch alte Felder (PV_Erzeugung_kWh, Batterie_*)

**v2.0.1 - Selektiver Import:**

- Import-Modi (Alles/Nur Basis/Nur Komponenten) + Checkboxen pro Feld

**v2.0.0 - ⚠️ BREAKING CHANGE:**

Neuinstallation erforderlich! Volume-Mapping `config:ro` für HA-Statistik-Zugriff.
Siehe [CHANGELOG.md](CHANGELOG.md) für vollständige Versionshistorie.
