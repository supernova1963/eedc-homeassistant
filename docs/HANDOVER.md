# EEDC Entwickler-Handover

**Stand:** 2026-02-05
**Version:** 0.7.0

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
│   ├── config.yaml             # HA Add-on Konfiguration
│   ├── Dockerfile
│   ├── backend/
│   │   ├── main.py             # FastAPI Entry, Version
│   │   ├── api/routes/
│   │   │   └── ha_integration.py   # Discovery, Sensor-Import
│   │   ├── models/
│   │   └── services/
│   │       └── ha_websocket.py     # (deaktiviert)
│   └── frontend/
│       ├── src/
│       │   ├── api/ha.ts           # HA API Client
│       │   ├── components/
│       │   │   ├── discovery/      # Discovery UI
│       │   │   ├── setup-wizard/   # Setup-Wizard (v0.7.0)
│       │   │   └── AppWithSetup.tsx
│       │   ├── hooks/
│       │   │   ├── useDiscovery.ts
│       │   │   └── useSetupWizard.ts
│       │   └── pages/
│       └── dist/                   # Build Output
```

---

## Aktuell implementierte Features

### Setup-Wizard (v0.7.0) - Zuletzt bearbeitet

**Frontend:** `frontend/src/components/setup-wizard/`

Der Setup-Wizard führt neue Benutzer durch die Ersteinrichtung:

1. **WelcomeStep** - Einführung und Features
2. **AnlageStep** - Name, Leistung, Standort, Koordinaten
3. **HAConnectionStep** - HA-Verbindung prüfen (überspringbar)
4. **StrompreiseStep** - Mit deutschen Standardwerten (EEG-Vergütung nach Anlagengröße)
5. **DiscoveryStep** - Geräte aus Home Assistant erkennen
6. **InvestitionenStep** - Kaufpreis, Datum, technische Details ergänzen
7. **SummaryStep** - Übersicht vor Abschluss
8. **CompleteStep** - Erfolgsmeldung

**State-Management:** `frontend/src/hooks/useSetupWizard.ts`

- State wird in LocalStorage gespeichert (Wizard kann fortgesetzt werden)
- Strompreis-Defaults basierend auf Anlagengröße (≤10kWp: 8.2ct, 10-40kWp: 7.1ct, >40kWp: 5.8ct)

**Integration:** `frontend/src/components/AppWithSetup.tsx`

- Prüft beim Start ob Anlagen vorhanden sind
- Zeigt Wizard wenn keine Anlage existiert und Wizard nicht abgeschlossen

### Auto-Discovery (v0.6.0)

**Backend:** `backend/api/routes/ha_integration.py`

```python
# Wichtige Funktionen
_is_sma_sensor(entity_id)     # Regex: r'^sensor\.sn_\d+_'
_extract_devices_from_sensors()  # SMA, evcc, Smart, Wallbox
_classify_energy_sensor()      # Sensor-Mapping-Vorschläge
```

**Frontend:** `frontend/src/components/discovery/`
- `DiscoveryDialog.tsx` - Hauptdialog
- `DeviceCard.tsx` - Geräte-Karten mit Checkbox
- `SensorMappingPanel.tsx` - Sensor-Zuordnung mit Empfohlen/Alle Toggle
- `ConfirmationSummary.tsx` - Zusammenfassung vor Erstellung

**API-Endpoint:**
```
GET /api/ha/discover?anlage_id={id}
```

**Erkannte Integrationen:**
| Integration | Prefix | Erkennung |
|-------------|--------|-----------|
| SMA | `sensor.sn_NUMMER_` | Regex `sn_\d+_` |
| evcc | `sensor.evcc_` | Standard-Prefix |
| Smart E-Auto | `sensor.smart_` | Standard-Prefix |
| Wallbox | `sensor.wallbox_` | Standard-Prefix |

**Priorität:** evcc > native Integration (evcc überdeckt Wallbox/Smart)

---

## Bekannte Probleme & Workarounds

### 1. HA Long-Term Statistics nicht abrufbar

**Problem:** HA REST API (`/api/history/period/`) liefert nur ~10 Tage History. Long-Term Statistics (für Energy Dashboard) sind nur via WebSocket erreichbar.

**Auswirkung:** Import älterer Monate nicht möglich.

**Vorbereitet:** `backend/services/ha_websocket.py` (deaktiviert)

**Mögliche Lösungen:**
1. WebSocket-URL für Add-on-Container finden und debuggen
2. Direkter SQLite-Zugriff auf HA DB (`statistics` Tabelle)
3. Custom Component für REST-Zugriff

### 2. Discovery erkennt nur bestimmte Hersteller

**Problem:** Nur SMA, evcc, Smart, Wallbox werden automatisch erkannt.

**Workaround:** "Empfohlen/Alle" Toggle zeigt alle Energy-Sensoren für manuelle Auswahl.

**Mögliche Verbesserung:** Generischere Hersteller-Erkennung (Fronius, Huawei, Kostal, etc.)

---

## Test-Umgebung des Benutzers

| Gerät | Integration | Sensoren |
|-------|-------------|----------|
| SMA Wechselrichter | SMA | `sensor.sn_3012412676_*` |
| SMA Speicher | SMA (Battery) | `battery_charge_total`, `battery_discharge_total` |
| Wallbox | evcc | `sensor.evcc_loadpoint_*` |
| E-Auto | evcc | `sensor.evcc_vehicle_*` |

**Wichtige SMA-Sensoren:**
- `pv_gen_meter` → PV-Erzeugung
- `metering_total_yield` → Einspeisung
- `metering_total_absorbed` → Netzbezug
- `inverter_power_limit` → Wechselrichter-Leistung (10000W)

---

## Nächste Schritte (Priorität)

### Offen in Phase 2

1. **PDF-Export (2.12)** - jsPDF Integration (Dependencies vorhanden, keine Implementierung)
2. **Dashboard: Wärmepumpe (2.5)** - Auswertung für Wärmepumpen

### Optional

- WebSocket für Long-Term Statistics debuggen (2.1b)
- String-Import aus HA vervollständigen (2.16b)
- Generischere Hersteller-Erkennung

---

## Code-Konventionen

### Backend (Python)
- FastAPI mit Pydantic Schemas
- SQLAlchemy 2.0 ORM
- Async für HA API Calls

### Frontend (TypeScript)
- React 18 mit Hooks
- Tailwind CSS (Dark Mode Support)
- Lucide React Icons
- Custom Hooks in `/hooks/`

### Git Commits
```
feat(wizard): Add Setup-Wizard for first-time users
fix(ha): Improve SMA sensor detection
docs: Update handover documentation
```

---

## Wichtige Dateien zum Einlesen

1. **Architektur:** `PROJEKTPLAN.md`
2. **Aktueller Stand:** `docs/STATUS.md`
3. **Setup-Wizard:** `frontend/src/hooks/useSetupWizard.ts`
4. **Discovery-Logik:** `backend/api/routes/ha_integration.py` (Zeilen 50-300)
5. **Discovery-UI:** `frontend/src/components/discovery/DiscoveryDialog.tsx`
6. **API-Typen:** `frontend/src/api/ha.ts`

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

*Erstellt: 2026-02-05*
