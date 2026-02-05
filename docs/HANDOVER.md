# EEDC Entwickler-Handover

**Stand:** 2026-02-05
**Version:** 0.7.4

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
│   ├── STATUS.md               # Aktueller Implementierungsstand
│   └── HANDOVER.md             # Dieses Dokument
├── eedc/
│   ├── config.yaml             # HA Add-on Konfiguration (Version hier!)
│   ├── Dockerfile
│   ├── backend/
│   │   ├── main.py             # FastAPI Entry
│   │   ├── api/routes/
│   │   │   └── ha_integration.py   # Discovery, Sensor-Import, INTEGRATION_PATTERNS
│   │   ├── models/
│   │   └── services/
│   │       └── ha_websocket.py     # (deaktiviert)
│   └── frontend/
│       ├── src/
│       │   ├── api/ha.ts           # HA API Client
│       │   ├── components/
│       │   │   ├── discovery/      # Discovery UI
│       │   │   ├── setup-wizard/   # Setup-Wizard
│       │   │   │   └── steps/      # Wizard-Schritte inkl. InvestitionenStep.tsx
│       │   │   ├── layout/         # Layout.tsx, Sidebar.tsx (Version hier!)
│       │   │   └── AppWithSetup.tsx
│       │   ├── hooks/
│       │   │   ├── useDiscovery.ts
│       │   │   └── useSetupWizard.ts
│       │   └── pages/
│       └── dist/                   # Build Output (wird mit committed!)
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

## Aktuell implementierte Features (v0.7.4)

### Setup-Wizard (v0.7.0-0.7.4)

**Frontend:** `frontend/src/components/setup-wizard/`

Der Setup-Wizard führt neue Benutzer durch die Ersteinrichtung:

1. **WelcomeStep** - Einführung und Features
2. **AnlageStep** - Name, Leistung, Standort, Koordinaten, Wechselrichter-Hersteller
3. **HAConnectionStep** - HA-Verbindung prüfen (überspringbar)
4. **StrompreiseStep** - Mit deutschen Standardwerten (EEG-Vergütung nach Anlagengröße)
5. **PVModuleStep** - PV-Module mit Ausrichtung/Neigung
6. **DiscoveryStep** - Geräte aus Home Assistant erkennen
7. **InvestitionenStep** - Kaufpreis, Datum, technische Details ergänzen
8. **SummaryStep** - Übersicht vor Abschluss
9. **CompleteStep** - Erfolgsmeldung

**State-Management:** `frontend/src/hooks/useSetupWizard.ts`

- State wird in LocalStorage gespeichert (Wizard kann fortgesetzt werden)
- Strompreis-Defaults basierend auf Anlagengröße (≤10kWp: 8.2ct, 10-40kWp: 7.1ct, >40kWp: 5.8ct)
- **LocalStorage Keys:** `eedc_setup_wizard_completed`, `eedc_setup_wizard_state`

**Wichtig (Fix v0.7.3):** Feldnamen müssen mit `InvestitionForm.tsx` übereinstimmen:

| Typ | Wizard-Feldname | Backend-Parameter |
|-----|-----------------|-------------------|
| E-Auto | `batteriekapazitaet_kwh` | `batteriekapazitaet_kwh` |
| Speicher | `kapazitaet_kwh` | `kapazitaet_kwh` |
| Wallbox | `leistung_kw` → | `max_ladeleistung_kw` |
| Wechselrichter | `leistung_kw` → | `max_leistung_kw` |
| Wärmepumpe | `leistung_kw`, `cop` | `leistung_kw`, `cop` |
| Balkonkraftwerk | `leistung_wp`, `anzahl` | `leistung_wp`, `anzahl` |

### Auto-Discovery (v0.6.0 → v0.7.4)

**Backend:** `backend/api/routes/ha_integration.py`

**INTEGRATION_PATTERNS** enthält alle unterstützten Hersteller:

```python
INTEGRATION_PATTERNS = {
    # Wechselrichter
    "sma": {...},
    "fronius": {...},
    "kostal": {...},
    # ... 9 Hersteller

    # Balkonkraftwerke (NEU v0.7.4)
    "ecoflow": {...},
    "hoymiles": {...},
    "anker_solix": {...},
    "apsystems": {...},
    "deye": {...},
    "opensunny": {...},

    # Wärmepumpen (NEU v0.7.4)
    "viessmann": {...},
    "daikin": {...},
    "vaillant": {...},
    "bosch": {...},
    "mitsubishi_ecodan": {...},
    "panasonic_aquarea": {...},
    "stiebel_eltron": {...},
    "nibe": {...},
    "alpha_innotec": {...},
    "lambda": {...},
    "idm": {...},
    "toshiba": {...},
    "lg_therma": {...},

    # E-Autos & Wallboxen
    "evcc": {...},
    "smart": {...},
    "wallbox": {...},
}
```

**Wichtige Funktionen:**
- `_detect_manufacturer()` - Erkennt Hersteller aus Entity-ID
- `_classify_sensor()` - Klassifiziert Sensor nach Typ und Mapping
- `_extract_devices_from_sensors()` - Gruppiert Sensoren zu Geräten

**API-Endpoints:**
```
GET /api/ha/discover?anlage_id={id}&manufacturer={filter}
GET /api/ha/manufacturers
```

---

## Bekannte Probleme & Workarounds

### 1. HA Long-Term Statistics nicht abrufbar

**Problem:** HA REST API (`/api/history/period/`) liefert nur ~10 Tage History. Long-Term Statistics (für Energy Dashboard) sind nur via WebSocket erreichbar.

**Auswirkung:** Import älterer Monate nicht möglich.

**Vorbereitet:** `backend/services/ha_websocket.py` (deaktiviert)

### 2. LocalStorage bei Wizard-Reset

**Problem:** Bei Wizard-Problemen müssen BEIDE Keys gelöscht werden:
- `eedc_setup_wizard_completed`
- `eedc_setup_wizard_state`

**Browser DevTools:** Application → Local Storage → Keys löschen

---

## Test-Umgebung des Benutzers

| Gerät | Integration | Sensoren |
|-------|-------------|----------|
| SMA Wechselrichter | SMA | `sensor.sn_3012412676_*` |
| SMA Speicher | SMA (Battery) | `battery_charge_total`, `battery_discharge_total` |
| Wallbox | evcc | `sensor.evcc_loadpoint_*` |
| E-Auto (Smart #1) | evcc | `sensor.evcc_vehicle_*` |

**Wichtige SMA-Sensoren:**
- `pv_gen_meter` → PV-Erzeugung
- `metering_total_yield` → Einspeisung
- `metering_total_absorbed` → Netzbezug
- `inverter_power_limit` → Wechselrichter-Leistung (10000W)

---

## Nächste Schritte (Priorität)

### Offen in Phase 2

1. **PDF-Export (2.12)** - jsPDF Integration (Dependencies vorhanden, keine Implementierung)
2. **Dashboard: Wärmepumpe (2.5)** - Auswertung für Wärmepumpen (Backend-Discovery jetzt vorbereitet)

### Optional

- WebSocket für Long-Term Statistics debuggen (2.1b)
- String-Import aus HA vervollständigen (2.16b)

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
fix(wizard): Fix parameter field names for investments
feat(discovery): Add support for heat pumps and balcony power plants
docs: Update handover documentation
chore: Bump add-on version to X.Y.Z
```

---

## Wichtige Dateien zum Einlesen

1. **Architektur:** `PROJEKTPLAN.md`
2. **Aktueller Stand:** `docs/STATUS.md`
3. **Setup-Wizard:** `frontend/src/hooks/useSetupWizard.ts`
4. **Discovery-Logik:** `backend/api/routes/ha_integration.py` (INTEGRATION_PATTERNS)
5. **Investitionen-Formular:** `frontend/src/components/forms/InvestitionForm.tsx` (Parameter-Namen!)
6. **Wizard Investitionen:** `frontend/src/components/setup-wizard/steps/InvestitionenStep.tsx`
7. **API-Typen:** `frontend/src/api/ha.ts`, `frontend/src/api/investitionen.ts`

---

## HA Add-on Testing

```bash
# Frontend Build
cd eedc/frontend && npm run build

# In HA: Add-on neu bauen
# Settings → Add-ons → EEDC → Rebuild

# Logs prüfen
# Settings → Add-ons → EEDC → Log
```

**Sensor-Konfiguration in HA:**
```yaml
ha_sensors:
  pv_erzeugung: sensor.sn_3012412676_pv_gen_meter
  einspeisung: sensor.sn_3012412676_metering_total_yield
  netzbezug: sensor.sn_3012412676_metering_total_absorbed
  batterie_ladung: sensor.sn_3012412676_battery_charge_total
  batterie_entladung: sensor.sn_3012412676_battery_discharge_total
```

---

## Session-Zusammenfassung (2026-02-05)

### Erledigte Aufgaben:

1. **Fix v0.7.3:** Investitions-Parameter werden jetzt korrekt gespeichert
   - Feldnamen-Inkonsistenz behoben (z.B. `batterie_kwh` → `batteriekapazitaet_kwh`)
   - Wizard verwendet jetzt dieselben Namen wie `InvestitionForm.tsx`

2. **Feature v0.7.4:** Erweiterte Device-Discovery
   - 6 Balkonkraftwerk-Hersteller hinzugefügt (EcoFlow, Hoymiles, Anker, APSystems, Deye, OpenDTU)
   - 13 Wärmepumpen-Hersteller hinzugefügt (Viessmann, Daikin, Vaillant, Bosch, Mitsubishi, Panasonic, Stiebel Eltron, Nibe, Alpha Innotec, Lambda, iDM, Toshiba, LG)
   - Frontend-Formularfelder für WP (Leistung, COP) und BKW (Leistung Wp, Anzahl)

### Offene Punkte:
- PDF-Export (2.12) - für später vorgemerkt
- Dashboard: Wärmepumpe (2.5) - Backend jetzt vorbereitet

---

*Erstellt: 2026-02-05*
*Version: 0.7.4*
