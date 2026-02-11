# EEDC Entwickler-Handover

**Stand:** 2026-02-05
**Version:** 0.8.1

Dieses Dokument dient als Kontext für die Fortsetzung der Entwicklung auf einem neuen Rechner oder in einer neuen Session.

---

## Schnellstart

```bash
# Repository klonen
git clone https://github.com/supernova1963/eedc-homeassistant.git
cd eedc-homeassistant

# Backend starten
cd eedc/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8099

# Frontend starten (neues Terminal)
cd eedc/frontend
npm install
npm run dev

# API Docs: http://localhost:8099/docs
# Frontend: http://localhost:5173
```

---

## Projekt-Struktur

```
eedc-homeassistant/
├── PROJEKTPLAN.md              # Feature-Roadmap und Architektur
├── docs/
│   ├── STATUS.md               # Aktueller Implementierungsstand (v0.8.1)
│   ├── STATUS_v0.7.md          # Archiv v0.7.x
│   ├── HANDOVER.md             # Dieses Dokument
│   └── DEVELOPMENT.md          # Development Guide
├── eedc/
│   ├── config.yaml             # HA Add-on Konfiguration (Version hier!)
│   ├── Dockerfile
│   ├── backend/
│   │   ├── main.py             # FastAPI Entry
│   │   ├── api/routes/
│   │   │   ├── ha_integration.py   # Discovery, Sensor-Import, INTEGRATION_PATTERNS
│   │   │   └── anlagen.py          # Geocoding, Sensor-Config
│   │   ├── models/
│   │   │   └── anlage.py           # ha_sensor_* Felder
│   │   └── services/
│   │       └── ha_websocket.py     # (deaktiviert)
│   └── frontend/
│       ├── src/
│       │   ├── api/
│       │   │   └── ha.ts           # HA API Client
│       │   ├── components/
│       │   │   ├── setup-wizard/   # Setup-Wizard
│       │   │   │   └── steps/
│       │   │   │       ├── InvestitionenStep.tsx   # Investitionen bearbeiten
│       │   │   │       ├── SensorConfigStep.tsx    # Sensor-Zuordnung
│       │   │   │       └── SummaryStep.tsx         # Individualisierte nächste Schritte
│       │   │   ├── layout/
│       │   │   └── AppWithSetup.tsx
│       │   ├── hooks/
│       │   │   ├── useDiscovery.ts
│       │   │   └── useSetupWizard.ts
│       │   └── pages/
│       │       └── Monatsdaten.tsx   # HA-Import UI
│       └── dist/                     # Build Output (wird committed!)
```

---

## Versions-Update Checkliste

Bei jeder neuen Version müssen diese Dateien aktualisiert werden:

1. **`eedc/config.yaml`** - `version: "X.Y.Z"` (HA Add-on Version)
2. **`eedc/frontend/src/components/layout/Layout.tsx`** - Footer-Text
3. **`eedc/frontend/src/components/layout/Sidebar.tsx`** - Footer-Text
4. **Frontend neu bauen:** `cd eedc/frontend && npm run build`
5. **Commit & Push**

---

## Aktuell implementierte Features (v0.8.1)

### Setup-Wizard

**Frontend:** `frontend/src/components/setup-wizard/`

Der Wizard führt neue Benutzer durch die Ersteinrichtung:

1. **WelcomeStep** - Einführung
2. **AnlageStep** - Name, Leistung, Standort, Geocoding
3. **HAConnectionStep** - HA-Verbindung prüfen (Features: Geräte-Erkennung, Sensor-Zuordnung)
4. **StrompreiseStep** - Strompreise mit deutschen Defaults
5. **DiscoveryStep** - Geräte aus HA erkennen
6. **InvestitionenStep** - Kaufpreis, Datum, Details ergänzen (mit Scroll/Highlight bei neuen)
7. **SensorConfigStep** - HA-Sensoren zuordnen
8. **SummaryStep** - Übersicht mit **individualisierten nächsten Schritten**
9. **CompleteStep** - Erfolgsmeldung

**Wichtige Änderung v0.8.1:** SummaryStep zeigt jetzt dynamisch generierte nächste Schritte basierend auf dem, was fehlt (z.B. "PV-Module anlegen" wenn keine vorhanden).

### Auto-Discovery

**Backend:** `backend/api/routes/ha_integration.py`

**INTEGRATION_PATTERNS** enthält alle unterstützten Hersteller:

- 9 Wechselrichter-Hersteller
- 6 Balkonkraftwerk-Hersteller
- 13 Wärmepumpen-Hersteller
- evcc, Smart, Wallbox

### HA-Import

**Backend:** `backend/api/routes/ha_integration.py`
**Frontend:** `frontend/src/pages/Monatsdaten.tsx`

- Sensor-Konfiguration: Anlage-Tabelle hat Priorität über config.yaml
- Import-Vorschau mit Loading-Overlay
- Details-Feedback (welche Sensoren Daten lieferten)

**Einschränkung:** HA REST API liefert nur ~10 Tage History. Long-Term Statistics benötigen WebSocket (nicht aktiv).

---

## Bekannte Probleme & Design-Entscheidungen

### 1. Monatsdaten-Import aus Wizard entfernt

**Grund:** HA History API liefert nur ~10 Tage Daten. Der Wizard suggerierte eine Funktionalität, die praktisch nicht funktioniert.

**Lösung:** Wizard fokussiert auf Setup, Monatsdaten werden separat erfasst (manuell, CSV, oder HA-Import für aktuelle Monate).

### 2. PV-Module nicht automatisch erkannt

**Grund:** PV-Module haben keine eigenen HA-Sensoren.

**Lösung:** Wizard zeigt Hinweis-Box, dass PV-Module manuell angelegt werden müssen.

### 3. LocalStorage bei Wizard-Reset

**Problem:** Bei Wizard-Problemen beide Keys löschen:
- `eedc_setup_wizard_completed`
- `eedc_setup_wizard_state`

**Aber:** Auto-Start prüft jetzt primär die DB (keine Anlagen = Wizard starten).

---

## Test-Umgebung des Benutzers

| Gerät | Integration | Sensoren |
|-------|-------------|----------|
| SMA Wechselrichter | SMA | `sensor.sn_3012412676_*` |
| SMA Speicher | SMA (Battery) | `battery_charge_total`, `battery_discharge_total` |
| Wallbox | evcc | `sensor.evcc_loadpoint_*` |
| E-Auto (Smart #1) | evcc | `sensor.evcc_vehicle_*` |

---

## Nächste Schritte (Priorität)

### Kurzfristig
1. **Monatsdaten-Seite verbessern** - UX für manuelle Erfassung
2. **Investitionen-Seite** - Direkter Zugang zu PV-Module hinzufügen

### Mittelfristig
3. **Dashboard: Wärmepumpe** - Backend Discovery vorbereitet
4. **PDF-Export** - jsPDF Dependencies vorhanden

### Zukunftsvision (User-Wunsch)
5. **EEDC-Gerät in Home Assistant erstellen:**
   - Berechnete KPIs als HA-Sensoren bereitstellen
   - Eigenverbrauchsquote, Autarkiegrad, ROI-Status
   - Am Wechselrichter-Gerät oder als eigenes Gerät

---

## Code-Konventionen

### Backend (Python)
- FastAPI mit Pydantic Schemas
- SQLAlchemy 2.0 ORM (Async)
- `create_all()` für DB-Schema (keine Migrationen)

### Frontend (TypeScript)
- React 18 mit Hooks
- Tailwind CSS (Dark Mode Support)
- Lucide React Icons
- Custom Hooks in `/hooks/`

### Git Commits
```
feat(wizard): Add Setup-Wizard for first-time users
fix(import): Use anlage-based sensor config for HA import
refactor(wizard): Simplify wizard, remove Monatsdaten focus
docs: Update documentation for v0.8.1
chore: Bump add-on version to X.Y.Z
```

---

## Wichtige Dateien zum Einlesen

1. **Aktueller Stand:** `docs/STATUS.md`
2. **Architektur:** `PROJEKTPLAN.md`
3. **Setup-Wizard Hook:** `frontend/src/hooks/useSetupWizard.ts`
4. **Wizard Summary:** `frontend/src/components/setup-wizard/steps/SummaryStep.tsx` (NextStepsSection)
5. **Discovery-Logik:** `backend/api/routes/ha_integration.py` (INTEGRATION_PATTERNS)
6. **HA-Import:** `backend/api/routes/ha_integration.py` (import_monatsdaten_from_ha)
7. **Monatsdaten-Seite:** `frontend/src/pages/Monatsdaten.tsx`

---

## Session-Zusammenfassung (2026-02-05)

### Erledigte Aufgaben:

1. **v0.8.0 Push:** Code war noch nicht auf GitHub, jetzt gepusht

2. **HA-Import Fix:** Sensor-Konfiguration aus Anlage wird jetzt verwendet (nicht nur config.yaml)

3. **HA-Import UX:** Loading-Overlay und Details-Feedback hinzugefügt

4. **Wizard Vereinfachung (v0.8.1):**
   - Monatsdaten-Referenzen entfernt (HAConnectionStep, CompleteStep, SummaryStep)
   - Individualisierte "Nächste Schritte" in SummaryStep
   - Hinweis-Box für fehlende PV-Module
   - Scroll und Highlight bei neuen Investitionen

5. **Dokumentation aktualisiert:**
   - STATUS.md archiviert als STATUS_v0.7.md
   - Neue STATUS.md für v0.8.1
   - HANDOVER.md aktualisiert

### Offene Diskussion:

**User-Wunsch für Zukunft:** EEDC-Gerät in Home Assistant erstellen, das berechnete KPIs (Eigenverbrauchsquote, Autarkiegrad, ROI) als Sensoren bereitstellt. Dies würde die Werte im HA Energy Dashboard oder auf HA Dashboards nutzbar machen.

---

*Erstellt: 2026-02-05*
*Version: 0.8.1*
