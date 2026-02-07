# CLAUDE.md - Projekt-Kontext für Claude Code

## Projektübersicht

**eedc** (Energie Effizienz Data Center) ist ein Home Assistant Add-on zur lokalen PV-Anlagen-Auswertung.

**Version:** 0.9.2 Beta
**Status:** Beta-ready für Tests

## Tech-Stack

### Backend (Python)
- FastAPI + SQLAlchemy 2.0 + SQLite
- Pfad: `eedc/backend/`
- Start: `uvicorn backend.main:app --reload --port 8099`
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
```

### Kernkomponenten
```
Backend:
  - main.py                    # FastAPI App, Health/Settings/Stats
  - api/routes/import_export.py # CSV Import/Export (dynamische Spalten)
  - api/routes/monatsdaten.py   # Monatsdaten CRUD + Berechnungen
  - api/routes/investitionen.py # Investitionen mit Parent-Child
  - core/config.py              # Settings + Version

Frontend:
  - components/forms/MonatsdatenForm.tsx  # Dynamische Felder (V2H, Arbitrage)
  - components/forms/InvestitionForm.tsx  # Investitions-Parameter
  - pages/Monatsdaten.tsx                 # Tabelle mit Spalten-Toggle
  - components/setup-wizard/              # 7-Schritt Wizard
```

## Datenmodell-Konzepte

### Parent-Child Beziehungen
- **PV-Module → Wechselrichter** (Pflicht wenn WR vorhanden)
- **Speicher → Wechselrichter** (Optional, für Hybrid-WR)
- E-Auto, Wallbox, Wärmepumpe: eigenständig

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
# Backend starten
cd eedc/backend
source venv/bin/activate
uvicorn backend.main:app --reload --port 8099

# Frontend starten (neues Terminal)
cd eedc/frontend
npm run dev

# Build für Production
npm run build

# Docker Build
cd eedc && docker build -t eedc-test .
```

## UI-Struktur

- **TopNavigation.tsx**: Horizontale Hauptnavigation (Cockpit, Auswertungen, Einstellungen)
- **SubTabs.tsx**: Kontextabhängige Sub-Tabs unter der Hauptnavigation
- **Layout.tsx**: Kombiniert TopNavigation + SubTabs (kein Sidebar!)

## Offene Features / Roadmap

- [ ] PDF-Export
- [ ] KI-Insights
- [ ] SOLL-IST Vergleich pro String (Frontend)

## Letzte Änderungen (v0.9.2)

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
