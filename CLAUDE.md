# CLAUDE.md - Projekt-Kontext für Claude Code

## Projektübersicht

**eedc** (Energie Effizienz Data Center) ist ein Home Assistant Add-on zur lokalen PV-Anlagen-Auswertung.

**Version:** 0.9.5 Beta
**Status:** Beta-ready für Tests

## Tech-Stack

### Backend (Python)
- FastAPI + SQLAlchemy 2.0 + SQLite
- Pfad: `eedc/backend/`
- Start: `cd eedc && source backend/venv/bin/activate && uvicorn backend.main:app --reload --port 8099`
- API Docs: http://localhost:8099/api/docs

### Frontend (TypeScript/React)
- Vite + React 18 + Tailwind CSS + Recharts
- Pfad: `eedc/frontend/`
- Dev: `npm run dev` (Port 5173, Proxy zu 8099)
- Build: `npm run build`

## Wichtige Dateien

### Versionskonfiguration (zentral!)
```
Frontend: eedc/frontend/src/config/version.ts
Backend:  eedc/backend/core/config.py (APP_VERSION, APP_NAME)
Add-on:   eedc/config.yaml (version)
```

### Kernkomponenten
```
Backend:
  - main.py                      # FastAPI App, Health/Settings/Stats
  - api/routes/import_export.py  # CSV Import/Export (dynamische Spalten)
  - api/routes/monatsdaten.py    # Monatsdaten CRUD + Berechnungen
  - api/routes/investitionen.py  # Investitionen mit Parent-Child
  - api/routes/ha_export.py      # HA Sensor Export (REST + MQTT)
  - core/config.py               # Settings + Version
  - services/ha_sensors_export.py # Sensor-Definitionen mit Formeln
  - services/mqtt_client.py      # MQTT Discovery Client

Frontend:
  - components/forms/MonatsdatenForm.tsx  # Dynamische Felder (V2H, Arbitrage)
  - components/forms/InvestitionForm.tsx  # Investitions-Parameter
  - pages/Monatsdaten.tsx                 # Tabelle mit Spalten-Toggle
  - pages/Auswertung.tsx                  # 5 Tabs (Jahresvergleich, PV, Investitionen, Finanzen, CO2)
  - pages/HAExportSettings.tsx            # HA Export Konfiguration (MQTT/REST)
  - components/layout/SubTabs.tsx         # Kontextabhängige Sub-Navigation
  - components/layout/TopNavigation.tsx   # Hauptnavigation + Einstellungen-Dropdown
  - components/setup-wizard/              # 7-Schritt Wizard
```

## Datenmodell-Konzepte

### Parent-Child Beziehungen & PV-System Aggregation
- **PV-Module → Wechselrichter** (Pflicht! Ohne WR-Zuordnung = Warnung)
- **DC-Speicher → Wechselrichter** (Optional, für Hybrid-WR)
- **AC-Speicher**: eigenständig (keine WR-Zuordnung)
- E-Auto, Wallbox, Wärmepumpe, Balkonkraftwerk: eigenständig

**PV-System ROI-Aggregation (v0.9.5):**
- Wechselrichter + zugeordnete PV-Module + DC-Speicher werden als "PV-System" aggregiert
- ROI wird auf System-Ebene berechnet (WR-Kosten enthalten!)
- Einzelkomponenten in aufklappbaren Unterzeilen mit anteiligen Einsparungen
- PV-Einsparungen werden proportional nach kWp auf Module verteilt
- Orphan PV-Module (ohne WR) zeigen Warnung im Frontend

### Investitions-Parameter (JSON)
Typ-spezifische Felder werden in `parameter` JSON gespeichert:
- E-Auto: `v2h_faehig`, `nutzt_v2h`
- Speicher: `arbitrage_faehig`, `kapazitaet_kwh`
- PV-Module: `anzahl_module`, `modul_leistung_wp`, `ausrichtung`, `neigung_grad`
- Balkonkraftwerk: `leistung_wp`, `anzahl`, `hat_speicher`, `speicher_kapazitaet_wh`
- Sonstiges: `kategorie` (erzeuger/verbraucher/speicher), `beschreibung`

### CSV Import/Export
- Dynamische Spalten basierend auf Investitions-Bezeichnungen
- Template-Endpoint: `/api/import/template/{anlage_id}`
- V2H-Spalten nur wenn `v2h_faehig` oder `nutzt_v2h`
- Arbitrage-Spalten nur wenn `arbitrage_faehig`

## Bekannte Design-Entscheidungen

1. **HA-Import deaktiviert** (v0.9): Long-Term Statistics zu unzuverlässig
2. **Datenerfassung:** Nur CSV oder manuell
3. **0-Werte:** Prüfung mit `is not None` statt `if val:`
4. **Berechnete Felder:** `direktverbrauch`, `eigenverbrauch`, `gesamtverbrauch`

## Entwicklungs-Workflow

```bash
# Backend starten (aus eedc/ Verzeichnis!)
cd eedc
source backend/venv/bin/activate
uvicorn backend.main:app --reload --port 8099

# Frontend starten (neues Terminal)
cd eedc/frontend
npm run dev

# Build für Production
npm run build

# Docker/Podman Build
cd eedc && docker build -t eedc-test .
# oder: podman build -t eedc-test .
```

## UI-Struktur

- **TopNavigation.tsx**: Horizontale Hauptnavigation (Cockpit, Auswertungen, Einstellungen)
- **SubTabs.tsx**: Kontextabhängige Sub-Tabs unter der Hauptnavigation
  - Cockpit: Übersicht, E-Auto, Wärmepumpe, Speicher, Wallbox, Balkonkraftwerk, Sonstiges
  - Auswertungen: Jahresvergleich, ROI-Analyse, Prognose vs. IST, PDF-Export
  - Einstellungen: Anlage, Strompreise, Investitionen, Monatsdaten, Import/Export, PVGIS, HA-Integration, HA-Export, Allgemein
- **Layout.tsx**: Kombiniert TopNavigation + SubTabs (kein Sidebar!)

## Offene Features / Roadmap

- [ ] PDF-Export
- [ ] KI-Insights
- [ ] SOLL-IST Vergleich pro String (Frontend)

## Letzte Änderungen (v0.9.5)

1. **PV-System ROI-Aggregation**: Strukturelle Verbesserung der ROI-Berechnung
   - Wechselrichter + PV-Module + DC-Speicher als "PV-System" aggregiert
   - ROI auf Systemebene statt pro Einzelkomponente (realistischer!)
   - Aufklappbare Komponenten-Zeilen im Frontend (Chevron-Icon)
   - Einsparung proportional nach kWp auf Module verteilt
   - Backend: Zwei-Pass-Gruppierung in `get_roi_dashboard()`
   - Neuer Typ `pv-system` mit `komponenten[]` Array

2. **Konfigurationswarnungen im ROI-Dashboard**:
   - Warnsymbol (⚠) bei PV-Modulen ohne Wechselrichter-Zuordnung
   - Warnsymbol bei Wechselrichtern ohne zugeordnete PV-Module
   - Zusammenfassende Warnbox mit Handlungsempfehlungen

3. **ROI-Tabelle mit Tooltips**: Formeln und Berechnungen per Hover sichtbar

4. **Bugfixes**:
   - Jahr-Filter für Investitionen ROI-Dashboard funktionsfähig
   - Unterjährigkeits-Problem bei "Alle Jahre" durch Jahresmittelung gelöst
   - PV_Erzeugung_kWh Spalte in CSV-Template für Balkonkraftwerk+PV-Module
   - **Investitions-Monatsdaten werden jetzt korrekt gespeichert** (kritisch!)
     - MonatsdatenCreate/Update Schemas um `investitionen_daten` Feld erweitert
     - Neue Helper-Funktion `_save_investitionen_monatsdaten()` in monatsdaten.py
     - Behebt: Wärmepumpe, Speicher, E-Auto Dashboards zeigten leere Daten

## Änderungen (v0.9.4)

1. Jahr-Filter für ROI-Dashboard
2. Unterjährigkeits-Korrektur bei Jahresvergleich
3. PV_Erzeugung_kWh in CSV-Template

## Änderungen (v0.9.3)

1. **HA Sensor Export**: Berechnete KPIs können an HA zurückgegeben werden
   - REST API: `/api/ha/export/sensors/{anlage_id}` für HA rest platform
   - MQTT Discovery: Native HA-Entitäten via MQTT Auto-Discovery
   - YAML-Generator: `/api/ha/export/yaml/{anlage_id}` für configuration.yaml
   - Frontend: HAExportSettings.tsx mit MQTT-Config, Test, Publish
2. **Auswertungen Tabs neu strukturiert**:
   - Übersicht = Jahresvergleich (Monats-Charts, Δ%-Indikatoren, Jahrestabelle)
   - PV-Anlage = Kombinierte Übersicht + PV-Details (Charts, KPIs, Spez. Ertrag)
   - Investitionen = NEU: ROI-Dashboard, Amortisationskurve, Kosten nach Kategorie
   - Finanzen & CO2 unverändert
3. **Sensor-Definitionen zentralisiert**:
   - `backend/services/ha_sensors_export.py` - Alle KPIs mit Formeln
   - Attribute für HA: formel, berechnung, kategorie
4. **MQTT-Konfiguration**: Addon config.yaml erweitert um mqtt-Sektion
5. **SubTabs für Einstellungen**: Bessere Navigation zwischen allen Settings-Seiten

## Änderungen (v0.9.2)

1. **Balkonkraftwerk Dashboard**: Erzeugung, Eigenverbrauch, Einspeisung, opt. Speicher
2. **Sonstiges Dashboard**: Flexible Kategorie (Erzeuger/Verbraucher/Speicher)
3. **Sonderkosten-Felder**: Für alle Investitionstypen (Reparatur, Wartung)
4. **Demo-Daten erweitert**: Balkonkraftwerk (800Wp + Speicher) + Mini-BHKW
5. **Navigation korrigiert**: SubTabs statt veralteter Sidebar
6. **Feldnamen-Mappings**: Frontend/Backend Konsistenz

## Änderungen (v0.9.1)

1. Zentrale Versionskonfiguration
2. Dynamische Formulare (V2H/Arbitrage bedingt)
3. PV-Module mit Anzahl/Wp
4. Monatsdaten-Spalten konfigurierbar
5. Bugfixes: 0-Wert Import, berechnete Felder

## API Endpoints (HA Export)

```
GET  /api/ha/export/sensors              # Alle Sensor-Definitionen
GET  /api/ha/export/sensors/{anlage_id}  # Sensoren einer Anlage mit Werten
GET  /api/ha/export/yaml/{anlage_id}     # YAML-Snippet für configuration.yaml
POST /api/ha/export/mqtt/test            # MQTT-Verbindung testen
POST /api/ha/export/mqtt/publish/{id}    # Sensoren via MQTT publizieren
DELETE /api/ha/export/mqtt/remove/{id}   # Sensoren aus HA entfernen
```
