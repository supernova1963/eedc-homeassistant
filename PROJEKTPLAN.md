# EEDC Home Assistant Add-on - Projektplan

> Energie-Effizienz Data Center als lokale Home Assistant Installation

---

## 1. LASTENHEFT

### 1.1 Projektziel

Neuimplementierung der EEDC-WebApp als Home Assistant Add-on für lokale Nutzung ohne externe Datenspeicherung. Fokus auf Datenschutz, einfache Installation und nahtlose HA-Integration.

### 1.2 Feature-Priorisierung

#### MUST (MVP - Phase 1)

| Feature | Beschreibung |
|---------|--------------|
| Monatsdaten-Erfassung | Formular + CSV-Import |
| Anlagen-Verwaltung | Stammdaten, kWp, Standort |
| Strompreis-Verwaltung | Tarife mit Gültigkeitszeiträumen |
| Investitionen | Alle Typen (E-Auto, WP, Speicher, Wallbox, Wechselrichter, PV-Module) |
| Basis-Kennzahlen | Autarkie, EV-Quote, kWh/kWp, CO2 |
| Finanzielle Bilanz | Einsparung, Erlös, Kosten |
| Monats-Übersicht | Tabelle mit allen Daten |
| Trend-Charts | Monatliche Verläufe |
| HA Ingress Support | Nahtlose Integration in HA Sidebar |
| HA Backup | Snapshots inkl. Daten |
| Dark Mode | Vollständig funktional |

#### SHOULD (Phase 2)

| Feature | Beschreibung |
|---------|--------------|
| HA Energy-Integration | Daten aus HA History ziehen |
| Arbitrage (Speicher) | Dynamische Tarife, Netzladung |
| V2H (E-Auto) | Bidirektionales Laden |
| Investitions-Dashboards | E-Auto, WP, Speicher, Wallbox |
| ROI-Berechnung | Amortisation pro Investition |
| Prognose vs. IST | Vergleich mit Hochrechnung |
| Pie-Charts | Verteilung Einspeisung/Verbrauch |
| Jahres-Vergleich | Jahr-über-Jahr |
| PDF-Export | Auswertungen drucken |
| PVGIS-Integration | Automatische Ertragsprognose |
| Setup-Wizard | Geführte Ersteinrichtung (8 Schritte) |
| HA Auto-Discovery | Automatische Geräte-Erkennung |
| Erweiterte Discovery | Wärmepumpen + Balkonkraftwerke |

#### COULD (Phase 3)

| Feature | Beschreibung |
|---------|--------------|
| KI-Insights + Optimierung | Kombiniert: Empfehlungen + Insights |
| Wetter-Daten | Open-Meteo Integration |
| Auto-Import aus HA | Automatische Monatsaggregation |

#### NICE-TO-HAVE (Phase 4 - Optional)

| Feature | Beschreibung |
|---------|--------------|
| Anonyme Benchmarks | Opt-in Vergleich mit Community |
| Cloud-Sync | Optionale Datensynchronisation |

### 1.3 Nicht-Funktionale Anforderungen

| Anforderung | Beschreibung |
|-------------|--------------|
| Performance | Abfragen < 200ms, CSV-Import < 5s für 300 Monate |
| Kompatibilität | Home Assistant 2024.1+ |
| Speicher | < 500 MB RAM, < 100 MB Disk (ohne Daten) |
| Backup | Vollständig via HA Snapshots |
| Updates | Einfache Updates via HA Add-on Store |

---

## 2. ARCHITEKTUR

### 2.1 Tech-Stack

#### Frontend
| Komponente | Technologie | Begründung |
|------------|-------------|------------|
| Framework | React 18+ | Bekannt aus eedc-webapp |
| Build Tool | Vite | Schneller als Webpack |
| Sprache | TypeScript | Type-Safety |
| Styling | Tailwind CSS | Dark Mode Support |
| Charts | Recharts | Bereits verwendet |
| PDF | jsPDF | Bereits verwendet |
| CSV | PapaParse | Bereits verwendet |

#### Backend
| Komponente | Technologie | Begründung |
|------------|-------------|------------|
| Sprache | Python 3.11+ | HA-Ökosystem Standard |
| Framework | FastAPI | Modern, async, OpenAPI |
| ORM | SQLAlchemy 2.0 | Python Standard |
| Datenbank | SQLite | Einfach, eine Datei, Backup-kompatibel |
| Validation | Pydantic | Integriert in FastAPI |

#### Home Assistant
| Komponente | Beschreibung |
|------------|--------------|
| Add-on Typ | Standalone Docker Container |
| UI-Zugang | Ingress (nahtlos in HA UI) |
| Daten-Zugriff | HA REST API + WebSocket |
| Config | options.json via HA Supervisor |

### 2.2 Architektur-Diagramm

```
┌─────────────────────────────────────────────────────────┐
│                   Home Assistant                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │              EEDC Add-on (Docker)                 │  │
│  │  ┌─────────────┐    ┌─────────────────────────┐   │  │
│  │  │   FastAPI   │◄──►│   React Frontend        │   │  │
│  │  │   Backend   │    │   (Vite Build)          │   │  │
│  │  │   :8099     │    │   (served by FastAPI)   │   │  │
│  │  └──────┬──────┘    └─────────────────────────┘   │  │
│  │         │                                         │  │
│  │         ▼                                         │  │
│  │  ┌─────────────┐    ┌─────────────────────────┐   │  │
│  │  │   SQLite    │    │   HA Supervisor API     │   │  │
│  │  │   eedc.db   │    │   (Energy-Daten)        │   │  │
│  │  └─────────────┘    └─────────────────────────┘   │  │
│  └───────────────────────────────────────────────────┘  │
│                                                         │
│  ┌─────────────────┐                                    │
│  │ HA Energy Data  │◄── Sensoren: Fronius, etc.        │
│  └─────────────────┘                                    │
└─────────────────────────────────────────────────────────┘
```

### 2.3 Datenmodell

```
┌─────────────────┐       ┌─────────────────────┐
│     anlage      │       │    strompreise      │
├─────────────────┤       ├─────────────────────┤
│ id (PK)         │       │ id (PK)             │
│ anlagenname     │       │ anlage_id (FK)      │
│ leistung_kwp    │       │ netzbezug_preis     │
│ standort_plz    │       │ einspeiseverguetung │
│ standort_ort    │       │ grundpreis_monat    │
│ ausrichtung     │       │ gueltig_ab          │
│ neigung_grad    │       │ gueltig_bis         │
│ latitude        │       │ tarifname           │
│ longitude       │       └─────────────────────┘
│ installation    │
│ created_at      │
└────────┬────────┘
         │
         │ 1:n
         ▼
┌─────────────────┐       ┌─────────────────────┐
│   monatsdaten   │       │    investitionen    │
├─────────────────┤       ├─────────────────────┤
│ id (PK)         │       │ id (PK)             │
│ anlage_id (FK)  │       │ anlage_id (FK)      │
│ jahr            │       │ typ (enum)          │
│ monat           │       │ bezeichnung         │
│ einspeisung_kwh │       │ anschaffungsdatum   │
│ netzbezug_kwh   │       │ anschaffungskosten  │
│ pv_erzeugung    │       │ parameter (JSON)    │
│ direktverbrauch │       │ aktiv               │
│ batterie_ladung │       │ created_at          │
│ batterie_entl.  │       └──────────┬──────────┘
│ globalstrahlung │                  │
│ sonnenstunden   │                  │ 1:n
│ notizen         │                  ▼
│ datenquelle     │       ┌─────────────────────┐
│ created_at      │       │ investition_monate  │
└─────────────────┘       ├─────────────────────┤
                          │ id (PK)             │
┌─────────────────┐       │ investition_id (FK) │
│    settings     │       │ jahr                │
├─────────────────┤       │ monat               │
│ key (PK)        │       │ verbrauch_daten (J) │
│ value (JSON)    │       │ kosten_daten (JSON) │
│ updated_at      │       │ created_at          │
└─────────────────┘       └─────────────────────┘
```

#### Investitions-Typen und Parameter

```python
class InvestitionTyp(Enum):
    E_AUTO = "e-auto"
    WAERMEPUMPE = "waermepumpe"
    SPEICHER = "speicher"
    WALLBOX = "wallbox"
    WECHSELRICHTER = "wechselrichter"
    PV_MODULE = "pv-module"
    BALKONKRAFTWERK = "balkonkraftwerk"
    SONSTIGES = "sonstiges"

# Parameter pro Typ (als JSON gespeichert)
E_AUTO_PARAMS = {
    "km_jahr": float,
    "verbrauch_kwh_100km": float,
    "pv_anteil_prozent": float,
    "benzinpreis_euro": float,
    "nutzt_v2h": bool,
    "v2h_entlade_preis_cent": float
}

WAERMEPUMPE_PARAMS = {
    "jaz": float,  # Jahresarbeitszahl
    "waermebedarf_kwh": float,
    "pv_anteil_prozent": float,
    "alter_energietraeger": str,  # gas, oel, etc.
    "alter_preis_cent_kwh": float
}

SPEICHER_PARAMS = {
    "kapazitaet_kwh": float,
    "wirkungsgrad_prozent": float,
    "nutzt_arbitrage": bool,
    "lade_durchschnittspreis_cent": float,
    "entlade_vermiedener_preis_cent": float
}

WALLBOX_PARAMS = {
    "leistung_kw": float
}

WECHSELRICHTER_PARAMS = {
    "leistung_ac_kw": float,
    "leistung_dc_kw": float,
    "wirkungsgrad_prozent": float,
    "hersteller": str,
    "modell": str
}

PV_MODULE_PARAMS = {
    # Direkte Felder am Investition-Model (für PVGIS):
    "leistung_kwp": float,        # investition.leistung_kwp
    "ausrichtung": str,           # investition.ausrichtung (Süd, Ost, West, Nord, etc.)
    "neigung_grad": float,        # investition.neigung_grad (0-90°)
    # Zusätzliche Parameter (JSON):
    "anzahl_module": int,
    "hersteller": str,
    "modell": str,
    "jahresertrag_prognose_kwh": float,
    "parent_wechselrichter_id": str  # Verknüpfung
}

# Hinweis: PV-Module werden als Investitionen erfasst.
# Die Gesamtleistung einer Anlage ergibt sich aus Σ leistung_kwp aller PV-Module.
# PVGIS ruft die Prognose pro Modul ab und aggregiert die Ergebnisse.
```

### 2.4 Projekt-Struktur

```
eedc-homeassistant/
├── README.md                    # Projekt-Übersicht
├── PROJEKTPLAN.md               # Dieses Dokument
├── LICENSE                      # MIT oder Apache 2.0
├── .gitignore
│
├── repository.yaml              # HA Add-on Repository Metadaten
├── repository.json              # Alternative für HACS
│
└── eedc/                        # Das Add-on
    ├── config.yaml              # HA Add-on Konfiguration
    ├── Dockerfile               # Multi-Stage Build
    ├── run.sh                   # Container Startscript
    ├── CHANGELOG.md
    │
    ├── backend/                 # Python FastAPI Backend
    │   ├── main.py              # FastAPI App Entry
    │   ├── requirements.txt     # Python Dependencies
    │   │
    │   ├── api/                 # API Layer
    │   │   ├── __init__.py
    │   │   ├── deps.py          # Dependency Injection
    │   │   └── routes/          # Endpoint-Module
    │   │       ├── __init__.py
    │   │       ├── anlagen.py
    │   │       ├── monatsdaten.py
    │   │       ├── investitionen.py
    │   │       ├── strompreise.py
    │   │       ├── import_export.py
    │   │       ├── settings.py
    │   │       └── ha_integration.py
    │   │
    │   ├── core/                # Core Funktionalität
    │   │   ├── __init__.py
    │   │   ├── config.py        # App-Konfiguration
    │   │   ├── database.py      # SQLite Setup
    │   │   └── calculations.py  # Berechnungslogik
    │   │
    │   ├── models/              # SQLAlchemy ORM Models
    │   │   ├── __init__.py
    │   │   ├── anlage.py
    │   │   ├── monatsdaten.py
    │   │   ├── investition.py
    │   │   ├── strompreis.py
    │   │   └── settings.py
    │   │
    │   ├── schemas/             # Pydantic Request/Response Schemas
    │   │   ├── __init__.py
    │   │   ├── anlage.py
    │   │   ├── monatsdaten.py
    │   │   ├── investition.py
    │   │   └── common.py
    │   │
    │   └── services/            # Externe Dienste
    │       ├── __init__.py
    │       ├── pvgis.py         # PVGIS API Client
    │       ├── open_meteo.py    # Wetter API Client
    │       └── ha_energy.py     # HA Energy Daten Abruf
    │
    ├── frontend/                # React Vite Frontend
    │   ├── package.json
    │   ├── package-lock.json
    │   ├── vite.config.ts
    │   ├── tsconfig.json
    │   ├── tailwind.config.js
    │   ├── postcss.config.js
    │   ├── index.html
    │   │
    │   ├── src/
    │   │   ├── main.tsx         # React Entry
    │   │   ├── App.tsx          # Root Component + Router
    │   │   ├── index.css        # Tailwind Imports
    │   │   │
    │   │   ├── api/             # API Client
    │   │   │   ├── client.ts    # Fetch Wrapper
    │   │   │   ├── anlagen.ts
    │   │   │   ├── monatsdaten.ts
    │   │   │   └── investitionen.ts
    │   │   │
    │   │   ├── components/      # Wiederverwendbare Komponenten
    │   │   │   ├── ui/          # Basis-UI (Button, Input, etc.)
    │   │   │   ├── charts/      # Chart-Komponenten
    │   │   │   ├── forms/       # Formular-Komponenten
    │   │   │   └── layout/      # Layout (Sidebar, Header)
    │   │   │
    │   │   ├── pages/           # Seiten-Komponenten
    │   │   │   ├── Dashboard.tsx
    │   │   │   ├── Anlagen.tsx
    │   │   │   ├── Monatsdaten.tsx
    │   │   │   ├── Investitionen.tsx
    │   │   │   ├── Auswertung.tsx
    │   │   │   ├── Import.tsx
    │   │   │   └── Settings.tsx
    │   │   │
    │   │   ├── hooks/           # Custom React Hooks
    │   │   │   ├── useAnlagen.ts
    │   │   │   ├── useMonatsdaten.ts
    │   │   │   └── useTheme.ts
    │   │   │
    │   │   ├── lib/             # Utilities & Berechnungen
    │   │   │   ├── calculations.ts
    │   │   │   ├── formatters.ts
    │   │   │   └── validators.ts
    │   │   │
    │   │   ├── types/           # TypeScript Types
    │   │   │   ├── anlage.ts
    │   │   │   ├── monatsdaten.ts
    │   │   │   └── investition.ts
    │   │   │
    │   │   └── context/         # React Context
    │   │       ├── ThemeContext.tsx
    │   │       └── AnlageContext.tsx
    │   │
    │   └── dist/                # Build Output (gitignored)
    │
    └── data/                    # Persistenter Storage (Volume)
        └── .gitkeep             # Platzhalter
```

---

## 3. HA INTEGRATION DETAILS

### 3.1 Add-on Konfiguration (config.yaml)

```yaml
name: "EEDC - Energie Daten Center"
description: "Lokale PV-Anlagen Auswertung und Wirtschaftlichkeitsanalyse"
version: "1.0.0"
slug: "eedc"
url: "https://github.com/[username]/eedc-homeassistant"
arch:
  - aarch64
  - amd64
  - armv7
init: false
homeassistant_api: true
ingress: true
ingress_port: 8099
panel_icon: "mdi:solar-power"
panel_title: "EEDC"
options:
  ha_sensors:
    pv_erzeugung: ""
    einspeisung: ""
    netzbezug: ""
    batterie_ladung: ""
    batterie_entladung: ""
schema:
  ha_sensors:
    pv_erzeugung: str?
    einspeisung: str?
    netzbezug: str?
    batterie_ladung: str?
    batterie_entladung: str?
map:
  - data:rw
ports:
  8099/tcp: null
```

### 3.2 HA Energy Daten Abruf

```python
# backend/services/ha_energy.py

import os
import aiohttp
from typing import Optional
from datetime import datetime

class HAEnergyService:
    """Service zum Abrufen von Energy-Daten aus Home Assistant."""

    def __init__(self):
        self.supervisor_token = os.environ.get("SUPERVISOR_TOKEN")
        self.base_url = "http://supervisor/core/api"

    async def get_statistics(
        self,
        statistic_id: str,
        start_time: datetime,
        end_time: datetime,
        period: str = "month"  # hour, day, week, month
    ) -> list[dict]:
        """
        Holt Statistiken für einen Sensor.

        Args:
            statistic_id: z.B. "sensor.fronius_pv_energy_total"
            start_time: Startdatum
            end_time: Enddatum
            period: Aggregationsperiode

        Returns:
            Liste von Statistik-Einträgen
        """
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"Bearer {self.supervisor_token}",
                "Content-Type": "application/json"
            }

            # WebSocket API für Statistiken
            payload = {
                "type": "recorder/statistics_during_period",
                "start_time": start_time.isoformat(),
                "end_time": end_time.isoformat(),
                "statistic_ids": [statistic_id],
                "period": period
            }

            async with session.post(
                f"{self.base_url}/websocket",
                json=payload,
                headers=headers
            ) as response:
                data = await response.json()
                return data.get(statistic_id, [])

    async def get_available_energy_sensors(self) -> list[dict]:
        """Listet alle verfügbaren Energy-Sensoren auf."""
        async with aiohttp.ClientSession() as session:
            headers = {"Authorization": f"Bearer {self.supervisor_token}"}

            async with session.get(
                f"{self.base_url}/states",
                headers=headers
            ) as response:
                states = await response.json()

                # Filtere Energy-relevante Sensoren
                energy_sensors = [
                    {
                        "entity_id": s["entity_id"],
                        "friendly_name": s["attributes"].get("friendly_name"),
                        "unit": s["attributes"].get("unit_of_measurement"),
                        "device_class": s["attributes"].get("device_class")
                    }
                    for s in states
                    if s["attributes"].get("device_class") in [
                        "energy", "power", "battery"
                    ]
                ]

                return energy_sensors
```

### 3.3 Sensor-Mapping UI

```typescript
// frontend/src/pages/Settings.tsx - Sensor-Mapping Sektion

interface SensorMapping {
  pv_erzeugung: string;
  einspeisung: string;
  netzbezug: string;
  batterie_ladung: string;
  batterie_entladung: string;
}

function SensorMappingForm() {
  const [sensors, setSensors] = useState<HASensor[]>([]);
  const [mapping, setMapping] = useState<SensorMapping>({...});

  useEffect(() => {
    // Lade verfügbare HA Sensoren
    api.getAvailableHASensors().then(setSensors);
  }, []);

  return (
    <div className="space-y-4">
      <h3>Home Assistant Sensor-Zuordnung</h3>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Ordne deine HA-Sensoren den EEDC-Feldern zu für automatischen Datenimport.
      </p>

      <SensorSelect
        label="PV-Erzeugung (kWh)"
        value={mapping.pv_erzeugung}
        sensors={sensors.filter(s => s.unit === 'kWh')}
        onChange={(v) => setMapping({...mapping, pv_erzeugung: v})}
      />

      <SensorSelect
        label="Einspeisung (kWh)"
        value={mapping.einspeisung}
        sensors={sensors.filter(s => s.unit === 'kWh')}
        onChange={(v) => setMapping({...mapping, einspeisung: v})}
      />

      {/* ... weitere Felder */}
    </div>
  );
}
```

---

## 4. BERECHNUNGSLOGIK

### 4.1 Basis-Kennzahlen

```python
# backend/core/calculations.py

from dataclasses import dataclass
from typing import Optional

@dataclass
class MonatsKennzahlen:
    """Berechnete Kennzahlen für einen Monat."""

    # Energie
    direktverbrauch_kwh: float
    gesamtverbrauch_kwh: float
    eigenverbrauch_kwh: float
    eigenverbrauchsquote_prozent: float
    autarkiegrad_prozent: float
    spezifischer_ertrag_kwh_kwp: Optional[float]

    # Finanzen
    einspeise_erloes_euro: float
    netzbezug_kosten_euro: float
    eigenverbrauch_ersparnis_euro: float
    netto_ertrag_euro: float

    # Umwelt
    co2_einsparung_kg: float


def berechne_monatskennzahlen(
    # Eingabewerte
    einspeisung_kwh: float,
    netzbezug_kwh: float,
    pv_erzeugung_kwh: float,
    batterie_ladung_kwh: float = 0,
    batterie_entladung_kwh: float = 0,
    v2h_entladung_kwh: float = 0,
    # Preise
    einspeiseverguetung_cent: float = 8.2,
    netzbezug_preis_cent: float = 30.0,
    # Anlage
    leistung_kwp: Optional[float] = None,
) -> MonatsKennzahlen:
    """
    Berechnet alle Kennzahlen für einen Monat.

    Formeln:
    - Direktverbrauch = PV-Erzeugung - Einspeisung - Batterieladung
    - Gesamtverbrauch = Direktverbrauch + Batterieentladung + Netzbezug
    - Eigenverbrauch = Direktverbrauch + Batterieentladung + V2H-Entladung
    - EV-Quote = Eigenverbrauch / PV-Erzeugung * 100
    - Autarkie = Eigenverbrauch / Gesamtverbrauch * 100
    """

    # Energie-Berechnungen
    direktverbrauch = pv_erzeugung_kwh - einspeisung_kwh - batterie_ladung_kwh
    direktverbrauch = max(0, direktverbrauch)  # Kann nicht negativ sein

    eigenverbrauch = direktverbrauch + batterie_entladung_kwh + v2h_entladung_kwh
    gesamtverbrauch = direktverbrauch + batterie_entladung_kwh + netzbezug_kwh

    # Quoten
    ev_quote = (eigenverbrauch / pv_erzeugung_kwh * 100) if pv_erzeugung_kwh > 0 else 0
    autarkie = (eigenverbrauch / gesamtverbrauch * 100) if gesamtverbrauch > 0 else 0

    # Spezifischer Ertrag
    spez_ertrag = (pv_erzeugung_kwh / leistung_kwp) if leistung_kwp else None

    # Finanzielle Berechnungen
    einspeise_erloes = einspeisung_kwh * einspeiseverguetung_cent / 100
    netzbezug_kosten = netzbezug_kwh * netzbezug_preis_cent / 100
    ev_ersparnis = eigenverbrauch * netzbezug_preis_cent / 100
    netto_ertrag = einspeise_erloes + ev_ersparnis - netzbezug_kosten

    # CO2 (0.38 kg/kWh deutscher Strommix)
    co2_einsparung = pv_erzeugung_kwh * 0.38

    return MonatsKennzahlen(
        direktverbrauch_kwh=direktverbrauch,
        gesamtverbrauch_kwh=gesamtverbrauch,
        eigenverbrauch_kwh=eigenverbrauch,
        eigenverbrauchsquote_prozent=ev_quote,
        autarkiegrad_prozent=autarkie,
        spezifischer_ertrag_kwh_kwp=spez_ertrag,
        einspeise_erloes_euro=einspeise_erloes,
        netzbezug_kosten_euro=netzbezug_kosten,
        eigenverbrauch_ersparnis_euro=ev_ersparnis,
        netto_ertrag_euro=netto_ertrag,
        co2_einsparung_kg=co2_einsparung
    )
```

### 4.2 Arbitrage-Berechnung (Speicher)

```python
def berechne_speicher_einsparung(
    kapazitaet_kwh: float,
    wirkungsgrad_prozent: float,
    netzbezug_preis_cent: float,
    einspeiseverguetung_cent: float,
    nutzt_arbitrage: bool = False,
    lade_preis_cent: float = 0,
    entlade_preis_cent: float = 0,
    zyklen_pro_jahr: int = 250,
) -> dict:
    """
    Berechnet jährliche Speicher-Einsparung.

    Ohne Arbitrage:
      Einsparung = Zyklen × Kapazität × Wirkungsgrad × (Netzbezug - Einspeisung)

    Mit Arbitrage (70/30 Modell):
      70% PV-Anteil: wie ohne Arbitrage
      30% Arbitrage: Zyklen × Kapazität × 0.30 × (Entladepreis - Ladepreis)
    """

    nutzbare_speicherung = kapazitaet_kwh * zyklen_pro_jahr * (wirkungsgrad_prozent / 100)
    standard_spread = netzbezug_preis_cent - einspeiseverguetung_cent

    if not nutzt_arbitrage:
        jahres_einsparung = nutzbare_speicherung * standard_spread / 100
        return {
            "jahres_einsparung_euro": jahres_einsparung,
            "nutzbare_speicherung_kwh": nutzbare_speicherung,
            "arbitrage_anteil_euro": 0,
            "pv_anteil_euro": jahres_einsparung
        }

    # 70/30 Modell
    pv_anteil = nutzbare_speicherung * 0.70
    arbitrage_anteil = nutzbare_speicherung * 0.30

    pv_einsparung = pv_anteil * standard_spread / 100
    arbitrage_spread = entlade_preis_cent - lade_preis_cent
    arbitrage_einsparung = arbitrage_anteil * arbitrage_spread / 100

    return {
        "jahres_einsparung_euro": pv_einsparung + arbitrage_einsparung,
        "nutzbare_speicherung_kwh": nutzbare_speicherung,
        "pv_anteil_euro": pv_einsparung,
        "arbitrage_anteil_euro": arbitrage_einsparung
    }
```

### 4.3 V2H-Berechnung (E-Auto)

```python
def berechne_v2h_einsparung(
    v2h_entladung_kwh: float,
    vermiedener_preis_cent: float,
) -> float:
    """
    Berechnet V2H-Einsparung für einen Monat.

    Einsparung = V2H-Entladung × vermiedener Netzbezugspreis
    """
    return v2h_entladung_kwh * vermiedener_preis_cent / 100
```

---

## 5. ROADMAP / ARBEITSPAKETE

### Phase 0: Projekt-Setup ✅

| # | Paket | Beschreibung | Status |
|---|-------|--------------|--------|
| 0.1 | Repository | GitHub Repo erstellen | ✅ |
| 0.2 | Grundstruktur | Verzeichnisse, config.yaml, Dockerfile | ✅ |
| 0.3 | Backend Skeleton | FastAPI + SQLite + SQLAlchemy | ✅ |
| 0.4 | Frontend Skeleton | Vite + React + Tailwind + Dark Mode | ✅ |
| 0.5 | Docker Build | Multi-Stage Build funktional | ✅ |
| 0.6 | Lokaler Test | In HA Dev-Environment testen | ✅ |

### Phase 1: MVP ✅

| # | Paket | Beschreibung | Status |
|---|-------|--------------|--------|
| 1.1 | DB Schema | SQLite Tabellen anlegen | ✅ |
| 1.2 | API: Anlagen | CRUD Endpoints | ✅ |
| 1.3 | API: Strompreise | CRUD mit Zeiträumen | ✅ |
| 1.4 | API: Investitionen | CRUD alle Typen | ✅ |
| 1.5 | API: Monatsdaten | CRUD + Berechnungen | ✅ |
| 1.6 | API: CSV-Import | Upload + Validierung | ✅ |
| 1.7 | Berechnungs-Engine | Alle Basis-Kennzahlen | ✅ |
| 1.8 | UI: Layout | Sidebar, Routing, Dark Mode | ✅ |
| 1.9 | UI: Anlagen | Formular + Liste | ✅ |
| 1.10 | UI: Strompreise | Formular + Liste | ✅ |
| 1.11 | UI: Investitionen | Dynamisches Formular | ✅ |
| 1.12 | UI: Monatsdaten | Erfassungs-Formular | ✅ |
| 1.13 | UI: CSV-Import | Upload-Dialog + Auto-Delimiter | ✅ |
| 1.14 | UI: Übersicht | Monats-Tabelle | ✅ |
| 1.15 | UI: Dashboard | KPIs + Trend-Charts | ✅ |
| 1.16 | HA Ingress | Integration getestet | ✅ |
| 1.17 | HA Backup | Daten in Snapshot (/data Volume) | ✅ |
| 1.18 | API: System Stats | Health + DB-Statistiken | ✅ |
| 1.19 | UI: Settings | Echte DB-Stats + HA-Status | ✅ |

### Phase 2: Erweitert

| # | Paket | Beschreibung | Status |
|---|-------|--------------|--------|
| 2.1 | HA Energy | Sensor-Mapping + Import | ✅ (aktuelle Monate) |
| 2.2 | Arbitrage | Speicher-Berechnung | ✅ (Backend) |
| 2.3 | V2H | E-Auto Rückspeisung | ✅ (Backend) |
| 2.4 | Dashboard: E-Auto | Auswertung | ✅ |
| 2.5 | Dashboard: WP | Auswertung | ⬜ |
| 2.6 | Dashboard: Speicher | Auswertung | ✅ |
| 2.7 | Dashboard: Wallbox | Auswertung | ✅ |
| 2.8 | ROI-Dashboard | Amortisation | ✅ |
| 2.9 | Prognose vs IST | Vergleich | ✅ |
| 2.10 | Monats-Detail | Pie-Charts | ✅ |
| 2.11 | Jahres-Vergleich | Charts | ✅ |
| 2.12 | PDF-Export | jsPDF Integration | ⬜ |
| 2.13 | PVGIS | API Integration | ✅ |
| 2.14 | API: ROI-Berechnung | Endpoint für alle Investitionen | ✅ |
| 2.15 | PV-Module als Investitionen | Multi-Modul-Unterstützung | ✅ |
| 2.16 | String-basierte IST-Erfassung | SOLL-IST pro PV-Modul via HA-Strings | ✅ (UI/API) |
| 2.17 | HA Auto-Discovery | Automatische Erkennung von HA-Geräten | ✅ |
| 2.18 | Setup-Wizard | Geführte Ersteinrichtung für neue Benutzer | ✅ |
| 2.19 | Erweiterte Discovery | Wärmepumpen (13) + Balkonkraftwerke (6) | ✅ |

### Optional / Zurückgestellt

| # | Paket | Beschreibung | Status |
|---|-------|--------------|--------|
| 2.1b | HA Long-Term Statistics | WebSocket für ältere Monate | 🔄 (vorbereitet, nicht aktiv) |
| 2.16b | String-Import aus HA | Automatischer Import via HA API | ⬜ (benötigt 2.1b) |

### Phase 3: Optimierung

| # | Paket | Beschreibung | Status |
|---|-------|--------------|--------|
| 3.1 | KI-Insights | Empfehlungs-Dashboard | ⬜ |
| 3.2 | Wetter | Open-Meteo Integration | ⬜ |
| 3.3 | Auto-Import | Automatische Aggregation | ⬜ |
| 3.4 | Performance | Caching, Optimierung | ⬜ |

---

## 6. ENTWICKLUNGS-SETUP

### Voraussetzungen

```bash
# Python 3.11+
python --version

# Node.js 18+
node --version

# Docker
docker --version

# Home Assistant (für Tests)
# Empfohlen: HA OS in VM oder ha-addon-devenv
```

### Backend Development

```bash
cd eedc/backend

# Virtual Environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# oder: venv\Scripts\activate  # Windows

# Dependencies
pip install -r requirements.txt

# Development Server
uvicorn main:app --reload --port 8099

# API Docs: http://localhost:8099/docs
```

### Frontend Development

```bash
cd eedc/frontend

# Dependencies
npm install

# Development Server
npm run dev

# Build für Produktion
npm run build
```

### Docker Build

```bash
cd eedc

# Build
docker build -t eedc-addon .

# Lokaler Test
docker run -p 8099:8099 -v $(pwd)/data:/data eedc-addon
```

---

## 7. REFERENZEN

### Home Assistant Add-on Entwicklung
- [Add-on Development Guide](https://developers.home-assistant.io/docs/add-ons/)
- [Add-on Config Reference](https://developers.home-assistant.io/docs/add-ons/configuration)
- [Ingress Documentation](https://developers.home-assistant.io/docs/add-ons/presentation#ingress)

### APIs
- [PVGIS API](https://joint-research-centre.ec.europa.eu/pvgis-photovoltaic-geographical-information-system/getting-started-pvgis/api-non-interactive-service_en)
- [Open-Meteo API](https://open-meteo.com/en/docs)
- [HA REST API](https://developers.home-assistant.io/docs/api/rest/)
- [HA WebSocket API](https://developers.home-assistant.io/docs/api/websocket/)

### Technologien
- [FastAPI](https://fastapi.tiangolo.com/)
- [SQLAlchemy 2.0](https://docs.sqlalchemy.org/en/20/)
- [React](https://react.dev/)
- [Vite](https://vitejs.dev/)
- [Tailwind CSS](https://tailwindcss.com/)
- [Recharts](https://recharts.org/)

---

---

## 8. GEPLANTE FEATURES (Details)

### 2.16 String-basierte IST-Erfassung

**Problem:**
Aktuell wird nur die Gesamterzeugung der PV-Anlage erfasst (`pv_erzeugung_kwh`). Ein echter SOLL-IST Vergleich pro PV-Modul (z.B. Süd vs. Ost vs. West) ist nicht möglich.

**Lösung:**
Home Assistant kann String/MPPT-Daten vom Wechselrichter erfassen. Diese werden mit PV-Modulen verknüpft.

**Datenmodell-Erweiterung:**

```
┌─────────────────────┐
│   investitionen     │
│   (PV-Module)       │
├─────────────────────┤
│ id (PK)             │
│ ...                 │
│ ha_entity_id (NEU)  │  ← z.B. "sensor.fronius_string1_energy"
└──────────┬──────────┘
           │ 1:n
           ▼
┌─────────────────────┐
│ string_monatsdaten  │  (NEUE Tabelle)
├─────────────────────┤
│ id (PK)             │
│ investition_id (FK) │  ← Verknüpfung zum PV-Modul
│ monatsdaten_id (FK) │  ← Verknüpfung zum Monat
│ pv_erzeugung_kwh    │  ← IST-Ertrag dieses Strings
│ created_at          │
└─────────────────────┘
```

**API-Erweiterungen:**
- `GET /api/ha/string-sensors` - Verfügbare String-Sensoren aus HA
- `PUT /api/investitionen/{id}/ha-entity` - HA-Entity zuweisen
- `POST /api/monatsdaten/{id}/import-strings` - String-Daten aus HA importieren
- `GET /api/pvgis/prognose-vs-ist/{anlage_id}/module` - SOLL-IST pro Modul

**UI-Erweiterungen:**
1. **Investitionen-Formular:** Neues Feld "Home Assistant Sensor" (Dropdown)
2. **Monatsdaten-Import:** Option "String-Daten aus HA importieren"
3. **Prognose vs. IST:** Neue Tabelle mit SOLL-IST pro PV-Modul

**Beispiel-Ausgabe:**

| PV-Modul | SOLL (PVGIS) | IST (HA) | Abweichung |
|----------|--------------|----------|------------|
| Süd 12kWp | 1.200 kWh | 1.150 kWh | -4.2% ✓ |
| Ost 5kWp | 400 kWh | 320 kWh | -20.0% ⚠️ |
| West 3kWp | 250 kWh | 245 kWh | -2.0% ✓ |

**Nutzen:**
- Schnelle Identifikation von Problemen auf einzelnen Dachflächen
- Verschattung, Verschmutzung, Defekte früh erkennen
- Optimierungspotenzial aufdecken

**Voraussetzungen:**
- Wechselrichter muss String-Daten liefern (Fronius, SMA, Huawei, etc.)
- HA-Integration für Wechselrichter muss String-Sensoren bereitstellen

---

## 9. ÄNDERUNGSHISTORIE

| Datum | Version | Änderungen |
|-------|---------|------------|
| 2026-02-03 | 0.1.0 | Initiale MVP-Implementierung |
| 2026-02-03 | 0.2.0 | ROI-Dashboard, System-Stats API, Settings-UI mit echten Daten |
| 2026-02-03 | 0.3.0 | **HA Ingress Integration erfolgreich getestet** - HashRouter, relative API-Pfade, CSV Auto-Delimiter |
| 2026-02-04 | 0.4.0 | **PVGIS Integration (2.13)** - EU PVGIS API v5.2, Prognose vs. IST, PV-Module als Investitionen mit individueller Ausrichtung |
| 2026-02-04 | 0.5.0 | **Feature 2.16** - String-basierte IST-Erfassung UI/API implementiert |
| 2026-02-04 | 0.6.0 | **Feature 2.1** - HA Energy Import (aktuelle Monate via History API), Sensor-Mapping in Settings, Import-Vorschau. WebSocket für Long-Term Statistics vorbereitet aber deaktiviert |
| 2026-02-05 | 0.6.0 | **Feature 2.17** - HA Auto-Discovery für SMA, evcc, Smart, Wallbox. Empfohlen/Alle Toggle für Sensor-Mappings |
| 2026-02-05 | 0.7.0-0.7.2 | **Feature 2.18** - Setup-Wizard mit 8 Schritten (Willkommen, Anlage, HA-Verbindung, Strompreise, PV-Module, Discovery, Investitionen, Zusammenfassung) |
| 2026-02-05 | 0.7.3 | **Fix** - Investitions-Feldnamen korrigiert (batteriekapazitaet_kwh, max_ladeleistung_kw, max_leistung_kw) |
| 2026-02-05 | 0.7.4 | **Feature 2.19** - Erweiterte Discovery: 13 Wärmepumpen-Hersteller (Viessmann, Daikin, Vaillant, Bosch, Mitsubishi, Panasonic, Stiebel Eltron, Nibe, Alpha Innotec, Lambda, iDM, Toshiba, LG) + 6 Balkonkraftwerk-Hersteller (EcoFlow, Hoymiles, Anker SOLIX, APSystems, Deye, OpenDTU) |

---

*Erstellt: 2026-02-03*
*Letzte Aktualisierung: 2026-02-05*
*Basierend auf: eedc-webapp Analyse*
