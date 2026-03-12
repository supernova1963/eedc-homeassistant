# Plan: Live-Dashboard (Stufe 2) — Echtzeit-Leistungsdaten

## Context

Stufe 1 ("Aktueller Monat") ist fertig — zeigt aggregierte kWh-Werte des laufenden Monats. Jetzt kommt **Stufe 2: Live-Dashboard** mit Echtzeit-Leistungswerten (kW) auf **Hauptmenü-Ebene** (neuer Top-Level-Tab neben Cockpit, Auswertungen, etc.).

Ziel: Der User sieht auf einen Blick, was seine PV-Anlage **gerade jetzt** produziert, wie viel ins Netz geht, wie viel verbraucht wird, und wie der Speicher steht.

## Architektur-Entscheidung: REST-Polling (10s)

**Kein WebSocket, kein SSE.** Gruende:
- HA Ingress proxied HTTP zuverlaessig, WebSocket/SSE sind fragil hinter Ingress
- HA-Sensoren aktualisieren sich typisch alle 10-30s — 10s Polling reicht
- TanStack Query `refetchInterval` ist trivial, kein neuer Transport-Layer noetig
- Standalone-Modus funktioniert identisch (gibt einfach weniger Felder zurueck)
- `websockets>=12.0` steht in requirements.txt — spaeterer Upgrade-Pfad offen

## Sensor-Konzept

### Problem: Leistung (kW) vs. Energie (kWh)

Die bestehende `sensor_mapping` mappt **Energie-Sensoren** (kWh, Zaehlerstaende). Fuer Live brauchen wir **Leistungs-Sensoren** (W/kW). Das sind oft Companion-Sensoren auf demselben Geraet.

### Loesung: `live_sensors` Sektion in sensor_mapping

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

    # Tages-Energie (kWh) — optional, aus mwd-Sensoren
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
│  (aus mwd-Sensoren, gleiche Quelle wie Aktueller Monat)    │
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
const { data, isLoading, isRefetching } = useQuery({
  queryKey: ['live-dashboard', selectedAnlageId],
  queryFn: () => liveDashboardApi.getData(selectedAnlageId!),
  enabled: !!selectedAnlageId,
  refetchInterval: 10_000,  // 10 Sekunden
})
```

- Gruener pulsierender Punkt zeigt Live-Status
- "Letztes Update: HH:MM:SS" Anzeige
- Kein manueller Refresh-Button noetig (Auto-Refresh)

### Graceful Degradation

- Keine `live_sensors` konfiguriert → EmptyState mit Link zu Sensor-Zuordnung
- Kein HA → "Live-Daten nur mit Home-Assistant verfuegbar"
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

### Phase 1: MVP (diese Session)
1. `live_power_service.py` — Service mit HA-Sensor-Lesen
2. `live_dashboard.py` — REST-Endpoint
3. `main.py` — Router registrieren
4. `liveDashboard.ts` — API-Client
5. `LiveDashboard.tsx` — Page mit KPI-Cards + Auto-Refresh
6. `App.tsx` + `TopNavigation.tsx` + `SubTabs.tsx` — Navigation
7. `EnergieBilanz.tsx` + `GaugeChart.tsx` — Bilanz-Tabelle + Gauge-Charts

### Phase 2: Sensor-Konfiguration (Folge-Session)
8. SensorMappingWizard um "Live-Sensoren" Tab erweitern
9. Auto-Detect von Power-Sensoren anbieten (HA device_class: power)

### Phase 3: Connector-Live-Daten (optional)
10. `read_current_power()` Methode in DeviceConnector ABC
11. Implementierung in Fronius, SMA etc.
12. LivePowerService nutzt Connectors als Fallback

## 8. Verifikation

- Python-Syntax: `python3 -c "import ast; ast.parse(open('eedc/backend/api/routes/live_dashboard.py').read())"`
- Python-Syntax: `python3 -c "import ast; ast.parse(open('eedc/backend/services/live_power_service.py').read())"`
- TypeScript: `cd eedc/frontend && npx tsc --noEmit`
- Manuell: Backend `/api/docs` → `GET /api/live/1` testen
- Frontend: `http://localhost:3000/#/live` → Auto-Refresh beobachten
- Ohne HA: Endpoint gibt `verfuegbar: false`, UI zeigt EmptyState
