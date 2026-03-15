# Plan: Live-Dashboard (Stufe 2) — Echtzeit-Leistungsdaten

## Context

Stufe 1 ("Aktueller Monat") ist fertig — zeigt aggregierte kWh-Werte des laufenden Monats. Jetzt kommt **Stufe 2: Live-Dashboard** mit Echtzeit-Leistungswerten (kW) auf **Hauptmenü-Ebene** (neuer Top-Level-Tab neben Cockpit, Auswertungen, etc.).

Ziel: Der User sieht auf einen Blick, was seine PV-Anlage **gerade jetzt** produziert, wie viel ins Netz geht, wie viel verbraucht wird, und wie der Speicher steht.

## Architektur-Entscheidung: REST-Polling (5s) + MQTT-Inbound

**Frontend → Backend: REST-Polling (5s).** Kein WebSocket, kein SSE. Gruende:
- HA Ingress proxied HTTP zuverlaessig, WebSocket/SSE sind fragil hinter Ingress
- 5s Polling fuer spuerbares Live-Gefuehl, MQTT-Cache liefert sofort aktuelle Werte
- Leichtgewichtiger Call (nur In-Memory-Read, kein DB-Query)
- `websockets>=12.0` steht in requirements.txt — spaeterer Upgrade-Pfad offen

**Smarthome → Backend: MQTT-Inbound (universelle Datenbruecke).**
Statt fuer jedes Smarthome-System (ioBroker, FHEM, openHAB, HA extern) einen eigenen REST-Adapter zu bauen, definiert EEDC eine MQTT-Topic-Struktur, die User aus ihrem System heraus befuellen (z.B. via Node-RED, HA-Automation, ioBroker-Script).

Vorteile gegenueber individuellen Gateway-Adaptern:
- **Einmal bauen, ueberall nutzen** — jedes Smarthome hat MQTT-Support
- **Push statt Poll** — Werte liegen sofort im Cache, kein REST-Roundtrip zu HA
- **Standalone bekommt Live-Daten** — war vorher gar nicht moeglich
- **Community-Effekt** — User teilen ihre Node-RED-Flows / HA-Automationen
- **Kein Adapter-Code pro System** — EEDC dokumentiert Topics, User mappt selbst

## Sensor-Konzept

### Problem: Leistung (kW) vs. Energie (kWh)

Die bestehende `sensor_mapping` mappt **Energie-Sensoren** (kWh, Zaehlerstaende). Fuer Live brauchen wir **Leistungs-Sensoren** (W/kW). Das sind oft Companion-Sensoren auf demselben Geraet.

### Loesung: `live_sensors` Sektion in sensor_mapping (HA-Modus)

Neuer optionaler Block im bestehenden JSON-Feld `Anlage.sensor_mapping`:

```json
{
  "basis": { ... },
  "investitionen": { ... },
  "live_sensors": {
    "pv_leistung_w": "sensor.pv_power",
    "einspeisung_w": "sensor.grid_export_power",
    "netzbezug_w": "sensor.grid_import_power",
    "batterie_w": "sensor.battery_power",
    "batterie_soc": "sensor.battery_soc",
    "eauto_w": "sensor.ev_charger_power",
    "eauto_soc": "sensor.ev_battery_soc",
    "waermepumpe_w": "sensor.heatpump_power",
    "sonstige_w": "sensor.other_power"
  }
}
```

- Keine DB-Migration noetig (JSON-Feld erweitert sich)
- Rueckwaertskompatibel (fehlendes `live_sensors` = keine Live-Daten)
- Konfiguration ueber erweiterten SensorMappingWizard (Phase 3)

### Loesung: MQTT-Inbound (universell, Standalone + jedes Smarthome)

EEDC subscribt auf eine vordefinierte Topic-Struktur. User befuellen diese aus ihrem Smarthome-System oder Node-RED.

#### MQTT Topic-Struktur

```
eedc/{anlage_id}/
├── energy/                          # Monatswerte (kWh) — fuer Aktuellen Monat
│   ├── einspeisung_kwh              → 397.2  (retained)
│   ├── netzbezug_kwh                → 182.5  (retained)
│   ├── pv_gesamt_kwh                → 627.0  (retained)
│   └── inv/{inv_id}/ladung_kwh      → 128.6  (retained)
│
└── live/                            # Echtzeit-Leistung (W) — fuer Live Dashboard
    ├── pv_leistung_w                → 4200
    ├── einspeisung_w                → 1100
    ├── netzbezug_w                  → 0
    ├── batterie_w                   → -500   (negativ = Entladung)
    ├── batterie_soc                 → 72
    ├── eauto_w                      → 3700
    ├── eauto_soc                    → 45
    └── waermepumpe_w                → 1800
```

**Alternativ: Ein JSON-Payload pro Kategorie**

```
eedc/{anlage_id}/energy  →  { "einspeisung_kwh": 397.2, "netzbezug_kwh": 182.5, ... }
eedc/{anlage_id}/live    →  { "pv_leistung_w": 4200, "einspeisung_w": 1100, ... }
```

#### Backend: MQTT-Inbound-Cache

```python
class MqttInboundCache:
    """In-Memory-Cache fuer MQTT-Inbound-Daten."""

    def __init__(self):
        self._live: dict[int, dict[str, float]] = {}    # anlage_id → {key: wert}
        self._energy: dict[int, dict[str, float]] = {}   # anlage_id → {key: wert}
        self._last_update: dict[int, datetime] = {}

    def on_message(self, topic: str, payload: str):
        # Parse: eedc/{anlage_id}/live/{key} oder eedc/{anlage_id}/energy/{key}
        # Update Cache

    def get_live_data(self, anlage_id: int) -> dict[str, float]:
        return self._live.get(anlage_id, {})

    def get_energy_data(self, anlage_id: int) -> dict[str, float]:
        return self._energy.get(anlage_id, {})
```

Der bestehende `mqtt_client.py` wird um Subscribe erweitert:
- Subscribe auf `eedc/+/live/#` und `eedc/+/energy/#`
- Callbacks fuellen `MqttInboundCache`
- Gleicher MQTT-Client der bereits fuer KPI-Export genutzt wird

#### Datenquellen-Prioritaet (aktueller_monat.py)

MQTT-Inbound wird als eigene Quelle in die Prioritaetskette eingebaut:

```
Gespeichert (85%) → Connector (90%) → MQTT-Inbound (91%) → HA Statistics (92%) → HA Sensor (95%)
```

#### Datenquellen fuer Live Dashboard

Der `LivePowerService` liest aus drei Quellen (hoechste Prioritaet gewinnt):

| Quelle | Modus | Prioritaet |
|--------|-------|-----------|
| Connector `read_current_power()` | Standalone (direkte Geraete) | 1 (niedrigste) |
| MQTT-Inbound Cache | Universell (jedes Smarthome) | 2 |
| HA State Service | HA Add-on (live_sensors Mapping) | 3 (hoechste) |

#### Beispiel-Flows fuer User

**Node-RED (ioBroker / generisch):**
```json
[{"id":"mqtt-out","type":"mqtt out","topic":"eedc/1/live/pv_leistung_w","broker":"..."}]
```

**HA Automation:**
```yaml
trigger:
  - platform: state
    entity_id: sensor.pv_power
action:
  - service: mqtt.publish
    data:
      topic: "eedc/1/live/pv_leistung_w"
      payload: "{{ states('sensor.pv_power') }}"
```

**ioBroker JavaScript-Adapter:**
```javascript
on('sourceDP.pv_power', (obj) => {
    sendTo('mqtt.0', 'publish', {topic: 'eedc/1/live/pv_leistung_w', message: obj.state.val});
});
```

---

## Neue Dateien (5)

| # | Datei | Beschreibung |
|---|-------|-------------|
| 1 | `eedc/backend/services/live_power_service.py` | Service: liest Leistungswerte aus HA-Sensoren |
| 2 | `eedc/backend/api/routes/live_dashboard.py` | REST-Endpoint `GET /api/live/{anlage_id}` |
| 3 | `eedc/frontend/src/api/liveDashboard.ts` | API-Client + TypeScript-Typen |
| 4 | `eedc/frontend/src/pages/LiveDashboard.tsx` | Dashboard-Page mit Auto-Refresh |
| 5 | `eedc/frontend/src/components/live/EnergieBilanz.tsx` | Energiebilanz-Tabelle mit gespiegelten Balken |
| 6 | `eedc/frontend/src/components/live/GaugeChart.tsx` | SVG-Halbkreis-Gauge fuer SoC/Netz/Autarkie |

## Modifizierte Dateien (4)

| # | Datei | Aenderung |
|---|-------|-----------|
| 6 | `eedc/backend/main.py` | Router registrieren (2 Zeilen) |
| 7 | `eedc/frontend/src/App.tsx` | Import + Route `/live` |
| 8 | `eedc/frontend/src/components/layout/TopNavigation.tsx` | "Live" Tab in mainTabs + getActiveMainTab |
| 9 | `eedc/frontend/src/components/layout/SubTabs.tsx` | Early-return fuer `/live` (keine Sub-Tabs) |

---

## 1. Backend: `live_power_service.py`

```python
class LivePowerService:
    """Sammelt aktuelle Leistungswerte aus verfuegbaren Quellen."""

    async def get_live_data(self, anlage: Anlage, db: Session) -> LiveDashboardResponse:
        # 1. Pruefe ob live_sensors konfiguriert
        live_sensors = (anlage.sensor_mapping or {}).get("live_sensors", {})
        # 2. Lese jeden konfigurierten Sensor via HAStateService.get_sensor_state()
        # 3. Konvertiere W → kW falls noetig (anhand unit_of_measurement)
        # 4. Berechne Eigenverbrauch = PV - Einspeisung (falls beides vorhanden)
        # 5. Lese Tageswerte aus aktueller_monat Logik (optional)
        # 6. Return LiveDashboardResponse
```

Reuse: `ha_state_service.get_sensor_state(entity_id)` — liest beliebige HA-Sensoren.

## 2. Backend: `live_dashboard.py` Endpoint

```
GET /api/live/{anlage_id}
```

### Response: `LiveDashboardResponse`

```python
class LiveKomponente(BaseModel):
    """Eine Zeile in der Energiebilanz-Tabelle."""
    key: str                       # "pv", "netz", "batterie", "eauto", "wp", "sonstige", "haushalt"
    label: str                     # "PV-Anlage", "Stromnetz", ...
    icon: str                      # Lucide-Icon-Name: "sun", "zap", "battery", "car", "flame", "home"
    erzeugung_kw: float | None = None   # Linke Seite (Quelle)
    verbrauch_kw: float | None = None   # Rechte Seite (Verbraucher)

class LiveGauge(BaseModel):
    """Ein Gauge-Chart (SoC, Netz-Richtung, Autarkie)."""
    key: str                       # "netz", "batterie_soc", "eauto_soc", "autarkie"
    label: str
    wert: float                    # Aktueller Wert
    min_wert: float = 0            # Skala-Minimum
    max_wert: float = 100          # Skala-Maximum
    einheit: str = "%"             # "%", "kW"

class LiveDashboardResponse(BaseModel):
    anlage_id: int
    anlage_name: str
    zeitpunkt: str                # ISO timestamp
    verfuegbar: bool              # mindestens ein Wert vorhanden?

    # Energiebilanz-Tabelle (dynamische Zeilen)
    komponenten: list[LiveKomponente]
    summe_erzeugung_kw: float
    summe_verbrauch_kw: float

    # Gauge-Charts (dynamisch, nur vorhandene)
    gauges: list[LiveGauge]

    # Tages-Energie (kWh) — optional, aus HA Statistics oder MQTT-Inbound
    heute_pv_kwh: float | None = None
    heute_einspeisung_kwh: float | None = None
    heute_netzbezug_kwh: float | None = None
    heute_eigenverbrauch_kwh: float | None = None
```

### Registrierung in `main.py` (Zeile ~114)

```python
from backend.api.routes import live_dashboard
app.include_router(live_dashboard.router, prefix="/api/live", tags=["Live Dashboard"])
```

## 3. Frontend: `liveDashboard.ts`

```typescript
export interface LivePowerValues { ... }
export interface LiveDashboardResponse { ... }

export const liveDashboardApi = {
  getData: (anlageId: number) =>
    api.get<LiveDashboardResponse>(`/live/${anlageId}`),
}
```

## 4. Frontend: `LiveDashboard.tsx`

### Layout

```
┌─────────────────────────────────────────────────────────────┐
│ Live  Meine PV-Anlage              [Anlage v]  Live (10s)  │
│                                  Letztes Update: 14:32:05   │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ENERGIEBILANZ                                              │
│                                                             │
│  Quellen (kW)           │ Komponente │     Verbraucher (kW) │
│  ━━━━━━━━━━━━━━━━━━━━━━━┼━━━━━━━━━━━━┼━━━━━━━━━━━━━━━━━━━━ │
│  ████████████████ 4.2    │  [Sun] PV  │                      │
│  █ 0.3 Bezug             │ [Zap] Netz │  ███ 1.1 Einspeisung │
│  ███ 1.1 Entladung       │ [Bat] Bat. │  ██ 0.5 Ladung       │
│                          │ [Car] Auto │  ████████ 3.7         │
│                          │ [WP]  WP   │  ████ 1.8             │
│                          │ [Home]Haus │  ███ 1.2              │
│  ━━━━━━━━━━━━━━━━━━━━━━━┼━━━━━━━━━━━━┼━━━━━━━━━━━━━━━━━━━━ │
│  Summe: 5.3 kW           │            │  Summe: 7.5 kW       │
│                                                             │
│  Balken: recharts BarChart (horizontal), Quellen nach links │
│  wachsend (negative Werte), Verbraucher nach rechts.        │
│  Zeilen dynamisch: nur Komponenten mit Investition/Sensor.  │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ZUSTANDSWERTE (Gauge-Charts)                               │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  Netz    │  │ Batterie │  │  E-Auto  │  │Autarkie  │   │
│  │  ←─┼─→   │  │  72%     │  │  45%     │  │  82%     │   │
│  │ Einsp/Bez│  │  SoC     │  │  SoC     │  │ aktuell  │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                             │
│  Netz-Gauge: Mitte=0, links=Einspeisung, rechts=Bezug      │
│  SoC-Gauges: Halbkreis 0-100%, Farbe nach Fuellstand        │
│  Autarkie-Gauge: Berechnet aus PV+Batterie / Verbrauch     │
│  Nur anzeigen wenn Sensor vorhanden.                        │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  HEUTE (kWh-Tagessummen)                                    │
│  PV: 18.3 kWh | Einsp: 9.2 kWh | Bezug: 3.1 kWh          │
│  (aus HA Statistics DB oder MQTT-Inbound energy/ Topics)    │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Energiebilanz-Tabelle (Herzstück)

Implementierung mit recharts `BarChart` (horizontal, layout="vertical"):
- **Eine Zeile pro Komponente** (PV, Netz, Batterie, E-Auto, WP, Sonstige, Haushalt)
- **Linker Balken** (negativ/grün): Erzeugung/Einspeisung/Entladung
- **Rechter Balken** (positiv/bunt): Verbrauch/Bezug/Ladung
- **Mitte**: Lucide-Icon + Label als Y-Axis-Tick
- **Bidirektionale Komponenten** (Netz, Batterie, E-Auto) koennen auf beiden Seiten Balken haben
- **Dynamische Zeilen**: Nur Komponenten anzeigen, die als Investition existieren UND einen Sensor haben
- **Summenzeile**: Gesamt-Erzeugung links, Gesamt-Verbrauch rechts

### Gauge-Charts

Einfache SVG-Halbkreis-Gauges (kein externes Library):
- **Netz-Gauge**: Symmetrisch um 0, links=Einspeisung (grün), rechts=Bezug (rot)
- **SoC-Gauges**: 0-100% Halbkreis, Farbe: rot (<20%), gelb (20-50%), grün (>50%)
- **Autarkie**: Berechnet als (Eigenverbrauch / Gesamtverbrauch * 100)

### Auto-Refresh

```typescript
// useEffect + setInterval (kein React Query, da QueryClientProvider nicht eingerichtet)
const REFRESH_INTERVAL = 5_000 // 5 Sekunden

useEffect(() => {
  fetchData(false)
  intervalRef.current = setInterval(() => fetchData(true), REFRESH_INTERVAL)
  return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
}, [fetchData])
```

- Gruener pulsierender Punkt zeigt Live-Status
- "Letztes Update: HH:MM:SS" Anzeige
- Kein manueller Refresh-Button noetig (Auto-Refresh)

### Graceful Degradation

- Keine `live_sensors` und kein MQTT-Inbound → EmptyState mit Link zu Einrichtung
- HA-Modus ohne live_sensors → Hinweis auf Sensor-Zuordnung
- Standalone ohne MQTT → Hinweis auf MQTT-Einrichtung mit Beispiel-Flows
- Einzelne Sensoren null → KPICard zeigt "—"
- Komponenten nur wenn `hat_speicher`/`hat_waermepumpe`/`hat_emobilitaet`

## 5. Frontend-Komponenten: `EnergieBilanz.tsx` + `GaugeChart.tsx`

### `EnergieBilanz.tsx`

Recharts `BarChart` mit `layout="vertical"` und gespiegelten Balken:

- Props: `komponenten: LiveKomponente[]`, `summeErzeugung: number`, `summeVerbrauch: number`
- Jede Komponente = eine Zeile mit optionalem linken (Erzeugung, negativ) und rechten (Verbrauch, positiv) Balken
- Y-Achse: Custom Tick mit Lucide-Icon + Label (via `tick` Prop)
- X-Achse: kW-Skala, symmetrisch um 0
- Farben: Erzeugung/Quellen = gruen-Toene, Verbraucher = nach Typ (gelb=PV, rot=Netz, blau=Batterie, lila=Auto, orange=WP)
- Summenzeile unter dem Chart als Text

### `GaugeChart.tsx`

Wiederverwendbare SVG-Halbkreis-Gauge-Komponente:

- Props: `wert: number`, `min: number`, `max: number`, `label: string`, `einheit: string`, `farbe?: string`
- SVG `<path>` fuer Halbkreis-Bogen (180 Grad)
- Hintergrund-Bogen (grau) + Wert-Bogen (farbig, proportional zum Wert)
- Zentrierter Text mit aktuellem Wert + Einheit
- Label darunter
- Farblogik: SoC-Gauges rot/gelb/gruen nach Fuellstand, Netz-Gauge gruen(Einspeisung)/rot(Bezug)

## 6. Navigation

### TopNavigation.tsx (Zeile 17-22)

```typescript
import { ..., Activity } from 'lucide-react'

const mainTabs = [
  { name: 'Cockpit', basePath: '/cockpit', icon: LayoutDashboard },
  { name: 'Live', basePath: '/live', icon: Activity },  // NEU
  { name: 'Auswertungen', basePath: '/auswertungen', icon: BarChart3 },
  { name: 'Aussichten', basePath: '/aussichten', icon: TrendingUp },
  { name: 'Community', basePath: '/community', icon: Users },
]
```

### getActiveMainTab (Zeile 97-105)

```typescript
if (location.pathname.startsWith('/live')) return 'Live'  // NEU
```

### SubTabs.tsx

Early-return wenn Pfad `/live` ist (kein Sub-Tab-System noetig, nur eine Seite).

### App.tsx

```typescript
import LiveDashboard from './pages/LiveDashboard'
// ...
<Route path="live" element={<LiveDashboard />} />
```

---

## 7. Implementierungs-Phasen

### Phase 1: MVP — HA Live Dashboard ✅ ERLEDIGT
1. ✅ `live_power_service.py` — Service mit HA-Sensor-Lesen (live_sensors Mapping)
2. ✅ `live_dashboard.py` — REST-Endpoint
3. ✅ `main.py` — Router registrieren
4. ✅ `liveDashboard.ts` — API-Client
5. ✅ `LiveDashboard.tsx` — Page mit EnergieBilanz + Gauges + 5s Auto-Refresh
6. ✅ `App.tsx` + `TopNavigation.tsx` + `SubTabs.tsx` — Navigation (Top-Level "Live" Tab)
7. ✅ `EnergieBilanz.tsx` + `GaugeChart.tsx` — Bilanz-Tabelle + Gauge-Charts

### Phase 2: MQTT-Inbound (universelle Datenbruecke) ✅ ERLEDIGT
8. ✅ `MqttInboundService` + `MqttInboundCache` in `mqtt_inbound_service.py` — Eigenstaendiger MQTT-Subscriber mit Auto-Reconnect
9. ✅ `_collect_mqtt_inbound_data()` in `aktueller_monat.py` — Monatswerte aus MQTT Energy-Cache
10. ✅ `LivePowerService` um MQTT-Inbound-Cache als Quelle erweitern (Prioritaet 2, zwischen Connector und HA)
11. ✅ Frontend: `MqttInboundSetup.tsx` — Einrichtung, Monitor, Topic-Dokumentation, Copy-to-Clipboard
12. ✅ Frontend: Test-Funktion (empfangene Werte, Cache-Status, Clear-Cache)
13. ✅ Docs: `MQTT_INBOUND.md` — Beispiel-Flows fuer HA, Node-RED, ioBroker, FHEM, openHAB

### Phase 2b: MQTT Energy → Monatsdaten ✅ ERLEDIGT
14. ✅ `VorschlagQuelle.MQTT_INBOUND` (Konfidenz 91%) im Monatsabschluss-Wizard
15. ✅ MQTT Energy-Werte als Vorschlaege in Basis- und Investitions-Felder (generisch, alle Typen)
16. ✅ `mqtt_inbound_konfiguriert` Status-Chip im Wizard-Header
17. ✅ `datenquelle = "mqtt_inbound"` beim Speichern
18. ✅ Energy-Topic-Generierung fuer alle Investitionstypen (PV, Speicher, WP, E-Auto, Wallbox, BKW, Sonstiges)
19. ✅ Retained Messages beim Speichern der MQTT-Einstellungen seeden

### Phase 3: Sensor-Konfiguration ✅ ERLEDIGT (Auto-Detect optional)
20. ✅ `LiveSensorSection.tsx` — Wiederverwendbare Live-Sensor-Zuordnung pro Investitionstyp
21. ✅ Live-Felder in BasisSensorenStep (einspeisung_w, netzbezug_w) und allen Investitions-Steps
22. ✅ `LIVE_FIELDS` Presets pro Typ (PV, Speicher, WP, E-Auto, Wallbox, BKW)
23. ✅ SensorAutocomplete mit device_class: power Filter
24. Optional: Auto-Detect — Power-Sensoren automatisch vorschlagen (same device as energy sensor)

### Phase 3b: MQTT Energy Mini-History ✅ ERLEDIGT
25. ✅ `MqttEnergySnapshot` Model — SQLite-Tabelle fuer periodische Energy-Snapshots
26. ✅ `mqtt_energy_history_service.py` — Snapshot (5min), Cleanup (31 Tage), Tages-Delta-Berechnung
27. ✅ Scheduler-Jobs: `mqtt_energy_snapshot` (IntervalTrigger 5min) + `mqtt_energy_cleanup` (CronTrigger 03:00)
28. ✅ `_safe_get_tages_kwh` Fallback: HA-History → MQTT-Snapshots → leer
29. ✅ Initialer Snapshot 10s nach MQTT-Connect (main.py)
30. ✅ Erster-Tag-Fallback: Fruehester Snapshot des Tages statt Mitternacht

### ~~Automatischer Monatsabschluss~~ (VERWORFEN)
Bewusst nicht implementiert — gleiche Argumentation wie bei HA:
Sonderkosten, Notizen und ggf. fehlende Investitions-Felder erfordern manuelles Review.
Das bestehende Kalender-Badge in der Navigation erinnert datenquellenunabhaengig an offene Monate.

### Phase 4: Connector-Live-Daten (optional, kein MQTT)
31. `read_current_power()` Methode in DeviceConnector ABC
32. Implementierung in Fronius, SMA etc.
33. LivePowerService nutzt Connectors als Fallback

## 8. Verifikation

- Python-Syntax: `python3 -c "import ast; ast.parse(open('eedc/backend/api/routes/live_dashboard.py').read())"`
- Python-Syntax: `python3 -c "import ast; ast.parse(open('eedc/backend/services/live_power_service.py').read())"`
- TypeScript: `cd eedc/frontend && npx tsc --noEmit`
- Manuell: Backend `/api/docs` → `GET /api/live/1` testen
- Frontend: `http://localhost:3000/#/live` → Auto-Refresh beobachten
- Ohne HA: Endpoint gibt `verfuegbar: false`, UI zeigt EmptyState
