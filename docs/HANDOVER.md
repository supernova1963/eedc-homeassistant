# EEDC Entwickler-Handover

**Stand:** 2026-02-05
**Version:** 0.6.0

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
│       │   ├── components/discovery/  # Discovery UI
│       │   ├── hooks/useDiscovery.ts
│       │   └── pages/
│       └── dist/                   # Build Output
```

---

## Aktuell implementierte Features

### Auto-Discovery (v0.6.0) - Zuletzt bearbeitet

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

### 2. Discovery erstellt Investitionen mit Minimaldaten

**Problem:** Nur Name, Typ, Hersteller werden gesetzt. Fehlend: Kaufpreis, Datum, technische Parameter.

**Workaround:** Investitionen nach Discovery manuell ergänzen.

**Mögliche Verbesserung:** Nach Erstellung direkt Bearbeitungsdialog öffnen.

### 3. Sensor-Erkennung ist herstellerspezifisch

**Problem:** Stark gefilterte Sensor-Vorschläge funktionieren nur für bekannte Hersteller (SMA, evcc).

**Lösung implementiert:** "Empfohlen/Alle" Toggle in `SensorMappingPanel.tsx`
- "Empfohlen" zeigt erkannte Sensoren
- "Alle" zeigt alle Energy-Sensoren (kWh, `total_increasing`)

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

1. **Dashboard: E-Auto (2.4)** - Auswertung für E-Auto-Investitionen
2. **Dashboard: Speicher (2.6)** - Auswertung für Batteriespeicher
3. **Dashboard: Wallbox (2.7)** - Auswertung für Wallbox
4. **PDF-Export (2.12)** - jsPDF Integration

### Optional

- WebSocket für Long-Term Statistics debuggen (2.1b)
- String-Import aus HA vervollständigen (2.16b)
- Nach Discovery → Bearbeitungsdialog öffnen

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
feat(ha): Add Auto-Discovery for HA devices
fix(ha): Improve SMA sensor detection
docs: Update handover documentation
```

---

## Wichtige Dateien zum Einlesen

1. **Architektur:** `PROJEKTPLAN.md`
2. **Aktueller Stand:** `docs/STATUS.md`
3. **Discovery-Logik:** `backend/api/routes/ha_integration.py` (Zeilen 50-300)
4. **Discovery-UI:** `frontend/src/components/discovery/DiscoveryDialog.tsx`
5. **API-Typen:** `frontend/src/api/ha.ts`

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
