# EEDC Standalone – Datenquellen-Integration

## Checkliste

> **Stand:** 2026-03-04 | Phase 0 + 1 + 2 + 3 + 5 abgeschlossen | **Kein Breaking Change** für eedc-homeassistant

### Voraussetzungen

- [x] GitHub: Altes eedc Repo → `eedc-archive` umbenannt
- [x] Neues `eedc` Repo erstellt (supernova1963/eedc)
- [x] Subtree-Integration in eedc-homeassistant
- [ ] SMA ennexOS Modbus aktivieren (Wechselrichter Web-UI → Externe Kommunikation)

### Phase 0: Repo-Restrukturierung ✅

- [x] 0.1 Altes `eedc` Repo zu `eedc-archive` umbenennen
- [x] 0.2 Neues `eedc` Repo erstellen (supernova1963/eedc)
- [x] 0.2a Code aus `eedc-homeassistant/eedc/` kopieren (backend, frontend, data)
- [x] 0.2b `.gitignore` erstellen
- [x] 0.2c Initial Commit + Push
- [x] 0.3 Conditional Loading einbauen
  - [x] 0.3a `backend/core/config.py` – Feature-Flag `HA_INTEGRATION_AVAILABLE`
  - [x] 0.3b `backend/main.py` – Conditional Router Registration (HA-Routes nur mit SUPERVISOR_TOKEN)
  - [x] 0.3c `frontend/src/hooks/useHAAvailable.ts` – NEU: Hook zur HA-Erkennung
  - [x] 0.3d `frontend/src/components/layout/SubTabs.tsx` – HA-Tabs conditional
  - [x] 0.3e `frontend/src/components/layout/TopNavigation.tsx` – HA-Kategorie conditional
- [x] 0.4 Standalone Deployment
  - [x] 0.4a `Dockerfile` – NEU: Standalone Docker (Multi-stage, ohne HA-Labels)
  - [x] 0.4b `docker-compose.yml` – NEU: Standalone Deployment
  - [x] 0.4c `README.md` – NEU: Standalone-Dokumentation
- [x] 0.5 Verifizierung Phase 0
  - [x] 0.5a Backend startet standalone (`uvicorn backend.main:app`) ✓ Port 8199
  - [x] 0.5b Frontend startet (`npm run dev`) ✓ Vite auf Port 3001
  - [x] 0.5c HA-Tabs NICHT sichtbar: `ha_integration_available: false`, 0 HA-Endpoints in OpenAPI
  - [x] 0.5d Core-Features: `/api/anlagen`, `/api/stats`, `/api/scheduler`, `/api/health` → alle OK
  - [x] 0.5e `docker-compose up` ✓ Container läuft, App erreichbar auf Port 8099

### Phase 1: CSV-Import mit Parser-Plugin-System ✅

Branch: `feature/portal-import`

- [x] 1.1 Parser-Architektur
  - [x] 1.1a `backend/services/import_parsers/__init__.py` – Package Init
  - [x] 1.1b `backend/services/import_parsers/base.py` – ABC `PortalExportParser` + Dataclasses
  - [x] 1.1c `backend/services/import_parsers/registry.py` – Parser Factory + `list_parsers()`
  - [x] 1.1d `backend/services/import_parsers/sma_sunny_portal.py` – SMA Parser (Classic + ennexOS)
- [x] 1.2 API-Routen
  - [x] 1.2a `backend/api/routes/data_import.py` – NEU (Upload + Parse + Apply Endpoints)
  - [x] 1.2b `backend/main.py` – Import-Router registrieren
- [x] 1.3 Frontend
  - [x] 1.3a `frontend/src/api/portalImport.ts` – NEU: API Client
  - [x] 1.3b `frontend/src/pages/DataImportWizard.tsx` – NEU: Import-Wizard
  - [x] 1.3c `frontend/src/App.tsx` – Route hinzufügen
  - [x] 1.3d `SubTabs.tsx` – Portal-Import Tab in Daten-Gruppe
- [x] 1.4 Verifizierung Phase 1
  - [x] 1.4a `GET /api/portal-import/parsers` → 3 Parser in Liste
  - [x] 1.4b CSV-Upload → Vorschau mit erkannten Monatswerten (echte ennexOS-CSV getestet)
  - [x] 1.4c E2E-Test: Übernahme → Monatsdaten korrekt befüllt (SMA WebConnect getestet)
  - [x] 1.4d Fehlermeldung bei falschem Format / fehlendem Hersteller
- [x] 1.5 Erweiterungen
  - [x] 1.5a Hilfe-Screenshot `public/help/sma-ennexos-energiebilanz.png` abgelegt
  - [ ] 1.5b Personalisierter Post-Import-Workflow (→ Phase 3 / Feature-Ideen)
  - [x] 1.5c SMA ECharger Wallbox CSV-Parser (`sma_echarger.py`)
  - [x] 1.5d EVCC Ladevorgangs-CSV-Parser (`evcc.py`) – Session-Aggregation pro Monat

**Registrierte Parser (3):** `sma_sunny_portal` (PV+Netz+Batterie), `sma_echarger` (Wallbox), `evcc` (Wallbox)

### Phase 2: SMA ennexOS Local API Connector ✅

- [x] 2.1 Connector-Architektur
  - [x] 2.1a `backend/services/connectors/__init__.py` – Package Init
  - [x] 2.1b `backend/services/connectors/base.py` – ABC `DeviceConnector` + Dataclasses
  - [x] 2.1c `backend/services/connectors/registry.py` – Connector Factory
  - [x] 2.1d `backend/services/connectors/sma_ennexos.py` – SMA ennexOS Implementation
  - [x] 2.1e `backend/services/connectors/sma_webconnect.py` – SMA WebConnect (ältere Geräte)
- [x] 2.2 Datenmodell
  - [x] 2.2a `backend/models/anlage.py` – Feld `connector_config` (JSON, nullable)
  - [x] 2.2b Automatische Migration via SQLAlchemy
- [x] 2.3 API-Routen
  - [x] 2.3a `backend/api/routes/connector.py` – NEU (Test, Setup, Status, Fetch, Disconnect)
  - [x] 2.3b `backend/main.py` – Connector-Router registriert
- [x] 2.4 Frontend
  - [x] 2.4a `frontend/src/api/connector.ts` – NEU: API Client
  - [x] 2.4b `frontend/src/pages/ConnectorSetupWizard.tsx` – NEU: Setup-Wizard
- [x] 2.5 Verifizierung Phase 2
  - [x] 2.5a Sunny Tripower 10.0 SE via WebConnect → alle 5 Felder ✓
  - [x] 2.5b SMA Wallbox EVC22 + Energy Meter via ennexOS → EM-Werte ✓
  - [x] 2.5c Credential-Sanitization im JSON-Export implementiert

**Registrierte Connectors (2):** `sma_ennexos` (Tripower X, Wallbox EVC), `sma_webconnect` (Sunny Boy, Tripower SE)

### Phase 3: Monatsdaten-Prefill Integration ✅

- [x] 3.1 Backend
  - [x] 3.1a `backend/services/vorschlag_service.py` – `PORTAL_IMPORT` + `LOCAL_CONNECTOR` als VorschlagQuelle
  - [x] 3.1b `backend/api/routes/connector.py` – `GET /connectors/monatswerte/{id}/{j}/{m}` Snapshot-Delta-Berechnung
  - [x] 3.1c `backend/api/routes/monatsabschluss.py` – Connector-Vorschläge (Konfidenz 90) automatisch, `connector_konfiguriert` Flag, `quelle`-Tracking
- [x] 3.2 Frontend
  - [x] 3.2a `MonatsabschlussWizard.tsx` – "Wechselrichter laden" Button (grün, neben HA-Button)
  - [x] 3.2b Connector-Werte als Vorschläge angezeigt, User übernimmt einzeln
  - [x] 3.2c Quellen-Labels übersetzt (`getQuelleLabel()`: Connector, Import, Vormonat etc.)
  - [x] 3.2d `connector.ts` + `monatsabschluss.ts` – API-Client + Types erweitert
- [x] 3.3 Verifizierung Phase 3
  - [x] 3.3a Monatsabschluss: Connector-Button sichtbar (nur wenn Connector konfiguriert)
  - [ ] 3.3b Live-Test: Connector-Daten laden → Werte werden als Vorschläge angezeigt
  - [x] 3.3c Portal-Import: Werte erscheinen als `aktueller_wert` mit `quelle=portal_import`
  - [x] 3.3d User kann einzelne Vorschläge per Klick übernehmen

**Hinweis:** Portal-Import schreibt direkt in Monatsdaten → Werte erscheinen automatisch. Connector-Daten kommen als Vorschläge (Snapshot-Differenz, verteilt auf PV-Module/Speicher nach kWp/Kapazität).

### Phase 4: Scheduler + Sicherheit + Polish (braucht: Phase 3)

- [ ] 4.1 Scheduler (nur für Connector, nicht CSV)
  - [ ] 4.1a `backend/services/scheduler.py` – Connector-Fetch CronJob (1. des Monats, 00:15)
  - [ ] 4.1b Nur für Anlagen mit aktivem Connector + `auto_fetch_enabled: true`
- [ ] 4.2 Sicherheit
  - [x] 4.2a `import_export/json_operations.py` – Connector-Credentials aus Export ausschließen (in Phase 2 erledigt)
  - [ ] 4.2b Auth-Fehler → UI-Hinweis "Erneut verbinden"
- [ ] 4.3 Dokumentation
  - [ ] 4.3a CHANGELOG.md aktualisieren
  - [ ] 4.3b CLAUDE.md – Datenquellen-Sektion
  - [ ] 4.3c README.md (eedc) – Anleitung Import + Connector-Setup
- [ ] 4.4 Verifizierung Phase 4
  - [ ] 4.4a Scheduler-Job manuell triggern → Daten gecached
  - [x] 4.4b JSON-Export enthält KEINE Credentials (in Phase 2 getestet)
  - [ ] 4.4c Fehlender Connector → "Erneut verbinden" Hinweis

### Phase 5: Subtree Integration ✅ (braucht: Phase 0, unabhängig von 1-4)

- [x] 5.1 `eedc-homeassistant`: bestehenden eedc/ Code entfernen (git rm)
- [x] 5.2 `git subtree add --prefix=eedc` von supernova1963/eedc ✓
- [x] 5.3 HA-spezifische Dateien zurückkopieren (Dockerfile, config.yaml, run.sh, icons, CHANGELOG)
- [x] 5.4 CLAUDE.md – Subtree-Workflow dokumentiert (inkl. Regeln)
- [x] 5.5 Verifizierung Phase 5
  - [x] 5.5a HA-Add-on startet und funktioniert vollständig ✓
  - [x] 5.5b HA-Tabs sichtbar (Sensor-Zuordnung, Statistik-Import, MQTT-Export) ✓
  - [x] 5.5c `git subtree pull` holt Änderungen aus eedc ✓ (Fix für useHAAvailable erfolgreich gepullt)
  - [x] 5.5d Bugfix: useHAAvailable auf relativen API-Pfad umgestellt (HA Ingress Kompatibilität)

---

## Kontext

### Hintergrund: SMA Cloud API nicht verfügbar

SMA hat mitgeteilt (2026-03-02), dass die Monitoring API **ausschließlich Firmen** vorbehalten ist. Die angebotene BasicReporting API (B2C) liefert nur PV-Erzeugungsdaten – keine Batterie, Netz oder Wallbox-Werte. **Daher: Strategiewechsel.**

### Neue Strategie: 3-Stufen Datenquellen-Architektur

```
Stufe 1: CSV/Excel Import (universell, manuell)
  └── Parser-Plugins pro Hersteller-Portal (Sunny Portal, Solar.web, etc.)

Stufe 2: Lokale API/Modbus Connectors (automatisiert, lokal)
  └── ennexOS REST API (SMA), Solar API (Fronius), REST (Kostal)

Stufe 3: Cloud-API Connectors (automatisiert, remote) – Zukunft
  └── SolarEdge API-Key, Enphase OAuth2 – von Community beigesteuert
```

**Warum dieser Ansatz?**
- **Testbar:** SMA Sunny Portal CSV + ennexOS Local API mit eigenem Tripower X
- **Breit:** CSV-Import funktioniert für JEDEN Hersteller (alle Portale haben Export)
- **Erweiterbar:** Community kann Parser + Connectors für ihre Hardware beitragen
- **Kein Vendor-Lock-in:** Keine Abhängigkeit von Cloud-API-Zugängen

### API-Zugang pro Hersteller (Recherche 2026-03)

| Hersteller | Cloud-API privat? | Lokale API? | CSV-Export? |
|---|---|---|---|
| **SMA** | Nein (nur Firmen) | ennexOS REST + Modbus TCP | Sunny Portal CSV |
| **SolarEdge** | Ja (Self-Service API-Key) | – | Portal CSV |
| **Fronius** | Pay-per-use | Solar API (unauthentifiziert!) | Solar.web CSV |
| **Kostal** | Nein | REST + Modbus/SunSpec | Portal begrenzt |
| **Enphase** | Ja (OAuth2, Free-Tier begrenzt) | IQ Gateway lokal | Portal Export |
| **Huawei** | Nein (nur Installer) | – | FusionSolar begrenzt |
| **Sungrow** | NDA erforderlich | – | iSolarCloud begrenzt |
| **GoodWe** | Nein (Org-Account + NDA) | – | SEMS Portal |

### Architektur-Entscheidung: Ein Codebase, zwei Deployment-Modi (unverändert)

Der Code bleibt **in einem Repository** (`eedc`). HA-spezifische Features werden **conditional geladen** basierend auf Umgebungserkennung:

```python
# Auto-detect: HA-Add-on hat SUPERVISOR_TOKEN
HA_INTEGRATION = bool(os.environ.get("SUPERVISOR_TOKEN"))
```

- **`eedc`** = Standalone-Modus (kein SUPERVISOR_TOKEN → HA-Features aus, Datenquellen an)
- **`eedc-homeassistant`** = subtree von `eedc` + HA-Config. Als Add-on hat es SUPERVISOR_TOKEN → alles aktiv

### Repo-Übersicht (Zielzustand, unverändert)

```
supernova1963/eedc                  # Standalone (reaktiviert)
├── backend/
├── frontend/
├── docker-compose.yml
├── Dockerfile
└── README.md

supernova1963/eedc-homeassistant    # HA-Add-on
├── eedc/                           # ← git subtree von supernova1963/eedc
│   ├── backend/
│   └── frontend/
├── config.yaml
├── Dockerfile                      # HA-spezifisch
├── run.sh
├── website/
└── docs/

supernova1963/eedc-community        # Community-Server (unverändert)
```

---

## Phase 1: CSV-Import mit Parser-Plugin-System

### Konzept

User exportiert Monatsdaten aus seinem Hersteller-Portal (z.B. SMA Sunny Portal) als CSV und lädt sie in EEDC hoch. Ein herstellerspezifischer Parser erkennt das Format und extrahiert die Energiewerte.

**User-Flow:**
1. Sunny Portal → Jahresansicht → CSV herunterladen (Monatswerte)
2. EEDC → "Daten importieren" → Hersteller wählen → CSV hochladen
3. EEDC parsed → Vorschau mit erkannten Werten → User bestätigt
4. Monatsdaten werden als Vorschläge befüllt

### 1.1 Parser-Architektur

```
backend/services/import_parsers/
├── __init__.py
├── base.py              # ABC PortalExportParser + Dataclasses
├── registry.py          # get_parser(), list_parsers()
└── sma_sunny_portal.py  # SMA Sunny Portal CSV Parser
```

**ABC `PortalExportParser` (base.py):**
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class ParsedMonthData:
    """Ein Monat an geparsten Energiedaten."""
    jahr: int
    monat: int
    pv_erzeugung_kwh: Optional[float] = None
    einspeisung_kwh: Optional[float] = None
    netzbezug_kwh: Optional[float] = None
    batterie_ladung_kwh: Optional[float] = None
    batterie_entladung_kwh: Optional[float] = None
    eigenverbrauch_kwh: Optional[float] = None
    # Wallbox, Wärmepumpe etc. kommen typischerweise nicht aus Portal-Exporten

@dataclass
class ParserInfo:
    """Metadaten eines Parsers für die UI."""
    id: str                    # z.B. "sma_sunny_portal"
    name: str                  # z.B. "SMA Sunny Portal"
    hersteller: str            # z.B. "SMA"
    beschreibung: str          # Kurzbeschreibung
    erwartetes_format: str     # z.B. "CSV (Semikolon-getrennt, Jahresansicht)"
    anleitung: str             # Anleitung zum Export im Portal
    beispiel_header: str       # Beispiel der ersten Zeile(n)

class PortalExportParser(ABC):
    @abstractmethod
    def info(self) -> ParserInfo:
        """Parser-Metadaten für die UI."""

    @abstractmethod
    def can_parse(self, content: str, filename: str) -> bool:
        """Prüft ob dieser Parser die Datei verarbeiten kann (Auto-Detect)."""

    @abstractmethod
    def parse(self, content: str) -> list[ParsedMonthData]:
        """Parsed die Datei und gibt Monatswerte zurück."""
```

**SMA Sunny Portal Parser (`sma_sunny_portal.py`):**

Unterstützt zwei SMA CSV-Formate:

| Format | Quelle | Separator | Datum | Dezimal |
|---|---|---|---|---|
| Portal-Download (DE) | Sunny Portal Jahresansicht | `;` | `dd.mm.yyyy` | `,` |
| Portal-Download (EN) | Sunny Portal Year view | `;` | `mm/dd/yyyy` | `.` |

Erkannte Spalten (flexibles Header-Matching):
```
Datum / Date
Ertrag / Gesamtertrag / Total Yield → pv_erzeugung_kwh
Eigenverbrauch / Self-consumption → eigenverbrauch_kwh
Einspeisung / Netzeinspeisung / Grid feed-in → einspeisung_kwh
Netzbezug / Grid consumption / Grid purchase → netzbezug_kwh
Batterieladung / Battery charge → batterie_ladung_kwh
Batterieentladung / Battery discharge → batterie_entladung_kwh
```

**Auto-Detection:** Erkennt SMA-Format anhand von:
- Semikolon als Separator
- Typische SMA-Spaltennamen (Ertrag, Eigenverbrauch, etc.)
- Optional: "SUNNY-MAIL" Header (Legacy-Format)

**Registry (`registry.py`):**
```python
_PARSERS: dict[str, type[PortalExportParser]] = {}

def register_parser(parser_class: type[PortalExportParser]):
    """Decorator zum Registrieren eines Parsers."""
    info = parser_class().info()
    _PARSERS[info.id] = parser_class

def list_parsers() -> list[ParserInfo]:
    """Alle verfügbaren Parser."""
    return [cls().info() for cls in _PARSERS.values()]

def get_parser(parser_id: str) -> PortalExportParser:
    """Parser nach ID."""
    return _PARSERS[parser_id]()

def auto_detect_parser(content: str, filename: str) -> Optional[PortalExportParser]:
    """Versucht automatisch den passenden Parser zu finden."""
    for cls in _PARSERS.values():
        parser = cls()
        if parser.can_parse(content, filename):
            return parser
    return None
```

### 1.2 API-Routen

**`backend/api/routes/data_import.py` (NEU):**

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/api/import/parsers` | Verfügbare Parser + Anleitungen |
| POST | `/api/import/preview` | CSV hochladen → geparste Vorschau (ohne Speichern) |
| POST | `/api/import/apply/{anlage_id}` | Geparste Werte als Monatsdaten übernehmen |

**Preview-Endpoint:**
```python
@router.post("/import/preview")
async def preview_import(
    file: UploadFile,
    parser_id: Optional[str] = None  # None = Auto-Detect
):
    content = (await file.read()).decode("utf-8-sig")  # BOM-safe
    if parser_id:
        parser = get_parser(parser_id)
    else:
        parser = auto_detect_parser(content, file.filename)
        if not parser:
            raise HTTPException(400, "Format nicht erkannt. Bitte Hersteller manuell wählen.")
    months = parser.parse(content)
    return {
        "parser": parser.info(),
        "monate": [asdict(m) for m in months],
        "hinweis": "Werte prüfen und bestätigen."
    }
```

**Apply-Endpoint:**
- Nimmt die bestätigten Monate entgegen
- Erstellt/aktualisiert `InvestitionMonatsdaten` pro Monat
- Nutzt bestehenden Vorschlag-Mechanismus (Quelle: `PORTAL_IMPORT`, Konfidenz: 85)

### 1.3 Frontend

**`DataImportWizard.tsx` (NEU) – 3 Schritte:**

1. **Hersteller & Datei wählen**
   - Dropdown: Parser-Liste von `/api/import/parsers`
   - Oder: "Automatisch erkennen"
   - Drag & Drop / Datei-Auswahl für CSV
   - Anleitung des gewählten Parsers anzeigen (Screenshot/Text: "So exportieren Sie im Sunny Portal")

2. **Vorschau & Prüfen**
   - Tabelle mit geparsten Monatswerten
   - Checkboxen pro Monat (einzeln ab-/anwählen)
   - Abweichungen zu bestehenden Daten markieren
   - Fehlende Monate grau, vorhandene Monate mit Vergleich

3. **Bestätigen & Importieren**
   - Zusammenfassung: X Monate importiert, Y übersprungen
   - Hinweis: "Werte wurden als Vorschläge gespeichert"

**Navigation:**
- Neue Gruppe "Datenquellen" in SubTabs/TopNavigation
- Enthält: "Portal-Import" (immer) + "Geräte-Connector" (Phase 2) + HA-Tabs (conditional)
- Route: `/einstellungen/daten-import` → DataImportWizard

---

## Phase 2: SMA ennexOS Local API Connector

### Konzept

EEDC verbindet sich direkt mit dem Wechselrichter im lokalen Netzwerk. Kumulative kWh-Zähler werden ausgelesen und Monatsdifferenzen berechnet.

**Entdeckung:** Der SMA Tripower X mit ennexOS hat eine **lokale REST API** unter `https://<ip>/api/v1/`. Diese ist besser geeignet als Modbus TCP:
- Höheres Abstraktionsniveau (JSON statt Register)
- Alle Messwerte inkl. Batterie und Netz
- Authentifizierung via lokaler OAuth2 (Username/Password → JWT)
- Genutzt von HA-Integrationen (`homeassistant_sma-ennexos`, `ha-pysmaplus`)

### ennexOS Local API Details

**Base URL:** `https://<inverter-ip>/api/v1/`

**Authentifizierung:**
```
POST /api/v1/token
Content-Type: application/x-www-form-urlencoded
grant_type=password&username=<user>&password=<password>
→ JWT access_token + refresh_token (JSESSIONID Cookie)
```

**Relevante Measurement-Channels (kumulative kWh-Zähler):**

| Channel-ID | Beschreibung | EEDC-Mapping |
|---|---|---|
| `Measurement.Metering.TotWhOut.Pv` | PV-Erzeugung gesamt (Wh) | pv_erzeugung_kwh |
| `Measurement.Metering.GridMs.TotWhOut` | Einspeisung gesamt (Wh) | einspeisung_kwh |
| `Measurement.Metering.GridMs.TotWhIn` | Netzbezug gesamt (Wh) | netzbezug_kwh |
| `Measurement.Metering.GridMs.TotWhIn.Bat` | Batterie-Ladung gesamt (Wh) | batterie_ladung_kwh |
| `Measurement.Metering.GridMs.TotWhOut.Bat` | Batterie-Entladung gesamt (Wh) | batterie_entladung_kwh |

**Monatswert-Berechnung:** Zählerstand Ende Monat − Zählerstand Anfang Monat = kWh im Monat

**Hinweis:** Self-signed TLS-Zertifikat → `verify=False` bei httpx nötig.

### 2.1 Connector-Architektur

```
backend/services/connectors/
├── __init__.py
├── base.py                 # ABC DeviceConnector + Dataclasses
├── registry.py             # Connector Factory + list_connectors()
└── sma_ennexos_local.py    # SMA ennexOS Local REST API
```

**ABC `DeviceConnector` (base.py):**
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class ConnectorInfo:
    id: str                     # z.B. "sma_ennexos_local"
    name: str                   # z.B. "SMA ennexOS (Lokal)"
    hersteller: str
    beschreibung: str
    auth_typ: str               # "password" | "api_key" | "none"
    benötigt_lokales_netzwerk: bool

@dataclass
class ConnectorStatus:
    verbunden: bool
    letzter_abruf: Optional[str]    # ISO timestamp
    fehler: Optional[str] = None

@dataclass
class MeterReading:
    """Aktuelle Zählerstände (kumulativ)."""
    timestamp: str                  # ISO timestamp
    pv_erzeugung_wh: Optional[float] = None
    einspeisung_wh: Optional[float] = None
    netzbezug_wh: Optional[float] = None
    batterie_ladung_wh: Optional[float] = None
    batterie_entladung_wh: Optional[float] = None

class DeviceConnector(ABC):
    @abstractmethod
    def info(self) -> ConnectorInfo:
        """Connector-Metadaten."""

    @abstractmethod
    async def connect(self, config: dict) -> bool:
        """Verbindung herstellen + testen. Config: {host, username, password, ...}"""

    @abstractmethod
    async def read_meters(self, config: dict) -> MeterReading:
        """Aktuelle kumulative Zählerstände auslesen."""

    @abstractmethod
    async def test_connection(self, config: dict) -> ConnectorStatus:
        """Verbindungstest."""
```

### 2.2 Datenmodell

**`backend/models/anlage.py` – Neues Feld:**
```python
connector_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
```

**JSON-Struktur:**
```json
{
  "connector_id": "sma_ennexos_local",
  "host": "192.168.1.100",
  "username": "User",
  "password": "***encrypted***",
  "auto_fetch_enabled": true,
  "meter_snapshots": {
    "2026-02-01T00:05:00": { "pv_wh": 12345000, "einsp_wh": 6789000, "... ": "..." },
    "2026-03-01T00:05:00": { "pv_wh": 12890000, "einsp_wh": 7120000, "...": "..." }
  },
  "last_fetch_timestamp": "2026-03-01T00:15:00Z"
}
```

**Monatswert-Logik:**
- Scheduler liest am 1. jeden Monats (00:15) die kumulativen Zähler
- Speichert Snapshot in `meter_snapshots`
- Differenz `snapshot[Monat] - snapshot[Vormonat]` = Monatswert in kWh
- Werte werden als Vorschläge im Monatsabschluss angezeigt

### 2.3 API-Routen

**`backend/api/routes/connector.py` (NEU):**

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/api/connector/available` | Verfügbare Connectors |
| POST | `/api/connector/test` | Verbindungstest (host, user, pw) |
| POST | `/api/connector/setup/{anlage_id}` | Connector einrichten |
| GET | `/api/connector/status/{anlage_id}` | Aktueller Status |
| POST | `/api/connector/fetch/{anlage_id}` | Manuell Zählerstände abrufen |
| DELETE | `/api/connector/disconnect/{anlage_id}` | Connector trennen |

### 2.4 Frontend

**`ConnectorSetupWizard.tsx` (NEU) – 3 Schritte:**

1. **Connector wählen + Verbinden**
   - Connector-Auswahl (SMA ennexOS, später Fronius etc.)
   - IP-Adresse + Credentials eingeben
   - "Verbindung testen" Button

2. **System-Übersicht**
   - Erkannte Messwerte anzeigen (aktuelle Zählerstände)
   - Bestätigung dass die richtigen Werte gelesen werden

3. **Automatisierung konfigurieren**
   - Auto-Fetch aktivieren (Scheduler liest monatlich)
   - Zusammenfassung + "Einrichten"

---

## Phase 3: Monatsdaten-Prefill Integration

### 3.1 Backend

**`backend/services/vorschlag_service.py` – Neue VorschlagQuellen:**
```python
PORTAL_IMPORT = "portal_import"    # Konfidenz: 85 (manuell importiert, daher leicht geringer)
LOCAL_CONNECTOR = "local_connector" # Konfidenz: 92 (automatisch, direkt vom Gerät)
# Bestehend: HA_SENSOR: 95, VORMONAT: 80
```

**Integration in MonatsabschlussWizard:**
- "Daten importieren" Dropdown mit Optionen:
  - "Aus CSV-Datei" → DataImportWizard (Phase 1)
  - "Vom Wechselrichter" → Connector-Fetch (Phase 2, nur wenn Connector aktiv)
  - "Aus Home Assistant" → bestehende HA-Integration (nur wenn HA verfügbar)

### 3.2 Frontend

**`MonatsabschlussWizard.tsx` – Erweiterung:**
- Neuer Bereich "Datenquelle" vor den Eingabefeldern
- Buttons je nach verfügbarer Quelle
- Werte werden als editierbare Vorschläge eingesetzt (gelb hinterlegt)
- Quelle wird pro Wert angezeigt (Icon: CSV-Datei / WR / HA)

---

## Phase 4: Scheduler + Sicherheit + Polish

### 4.1 Scheduler (nur Connector)

**`backend/services/scheduler.py`:**
- Neuer CronJob `connector_monthly_snapshot` (1. des Monats, 00:15)
- Liest kumulative Zähler → speichert Snapshot
- Berechnet Monatsdifferenz → cached als Vorschlag
- Nur für Anlagen mit `connector_config.auto_fetch_enabled: true`

### 4.2 Sicherheit

- `connector_config.password` verschlüsselt speichern (Fernet symmetric encryption)
- Passwords + Tokens aus JSON-Export ausschließen
- Auth-Fehler → UI-Hinweis "Erneut verbinden"
- Self-signed TLS: User muss aktiv bestätigen

---

## Zusammenfassung: Alle Dateien

### Phase 1 (CSV-Import, im eedc Repo)

| Datei | Aktion |
|---|---|
| `backend/services/import_parsers/__init__.py` | NEU |
| `backend/services/import_parsers/base.py` | NEU: ABC + Dataclasses |
| `backend/services/import_parsers/registry.py` | NEU: Parser Factory |
| `backend/services/import_parsers/sma_sunny_portal.py` | NEU: SMA Parser |
| `backend/api/routes/data_import.py` | NEU: Upload + Parse Endpoints |
| `backend/main.py` | ÄNDERN: Import-Router registrieren |
| `frontend/src/api/dataImport.ts` | NEU: API Client |
| `frontend/src/pages/DataImportWizard.tsx` | NEU: Import-Wizard |
| `frontend/src/App.tsx` | ÄNDERN: Route |
| `frontend/src/components/layout/SubTabs.tsx` | ÄNDERN: Datenquellen-Tab |
| `frontend/src/components/layout/TopNavigation.tsx` | ÄNDERN: Datenquellen-Tab |

### Phase 2 (Connector, im eedc Repo)

| Datei | Aktion |
|---|---|
| `backend/services/connectors/__init__.py` | NEU |
| `backend/services/connectors/base.py` | NEU: ABC + Dataclasses |
| `backend/services/connectors/registry.py` | NEU: Connector Factory |
| `backend/services/connectors/sma_ennexos_local.py` | NEU: SMA ennexOS |
| `backend/api/routes/connector.py` | NEU: Connect + Fetch Endpoints |
| `backend/models/anlage.py` | ÄNDERN: connector_config |
| `backend/core/database.py` | ÄNDERN: Migration |
| `backend/main.py` | ÄNDERN: Connector-Router |
| `frontend/src/api/connector.ts` | NEU: API Client |
| `frontend/src/pages/ConnectorSetupWizard.tsx` | NEU: Setup-Wizard |

### Phase 3 (Prefill, im eedc Repo)

| Datei | Aktion |
|---|---|
| `backend/services/vorschlag_service.py` | ÄNDERN: Neue Quellen |
| `frontend/src/pages/MonatsabschlussWizard.tsx` | ÄNDERN: Import-Buttons |

### Phase 4 (Polish, im eedc Repo)

| Datei | Aktion |
|---|---|
| `backend/services/scheduler.py` | ÄNDERN: Connector-Job |
| `backend/api/routes/import_export/json_operations.py` | ÄNDERN: Credential-Exclude |
| CHANGELOG.md | ÄNDERN |
| CLAUDE.md | ÄNDERN |
| README.md (eedc) | ÄNDERN |

---

## Reihenfolge & Abhängigkeiten

```
Phase 0: Repo-Setup ✅
Phase 5: Subtree Integration ✅

Phase 1: CSV-Import (keine externe Abhängigkeit!)
  ├── Parser-Architektur (ABC, Registry)
  ├── SMA Sunny Portal CSV Parser
  ├── Upload + Preview + Apply API
  └── DataImportWizard Frontend

Phase 2: SMA ennexOS Local Connector (braucht: Phase 1 für UI-Integration, Tripower X im LAN)
  ├── Connector-Architektur (ABC, Registry)
  ├── SMA ennexOS Local REST API Client
  ├── Datenmodell (connector_config)
  ├── Meter-Snapshot + Monatsdifferenz
  └── ConnectorSetupWizard Frontend

Phase 3: Monatsdaten-Prefill (braucht: Phase 1 oder 2)
  ├── VorschlagQuelle.PORTAL_IMPORT / LOCAL_CONNECTOR
  └── "Daten importieren" in MonatsabschlussWizard

Phase 4: Scheduler + Polish (braucht: Phase 3)
  ├── Connector-Snapshot CronJob
  ├── Credential-Sicherheit
  └── Dokumentation
```

**Vorteil:** Phase 1 hat **keine externen Abhängigkeiten** – nur eine CSV-Datei aus dem Sunny Portal reicht zum Testen.

## Erweiterbarkeit: Community-Beiträge

### Neuen Parser hinzufügen (Stufe 1)
```python
# backend/services/import_parsers/fronius_solarweb.py
from .base import PortalExportParser, ParserInfo, ParsedMonthData
from .registry import register_parser

@register_parser
class FroniusSolarWebParser(PortalExportParser):
    def info(self) -> ParserInfo:
        return ParserInfo(id="fronius_solarweb", name="Fronius Solar.web", ...)
    def can_parse(self, content, filename) -> bool: ...
    def parse(self, content) -> list[ParsedMonthData]: ...
```

### Neuen Connector hinzufügen (Stufe 2)
```python
# backend/services/connectors/fronius_solar_api.py
from .base import DeviceConnector, ConnectorInfo, MeterReading
from .registry import register_connector

@register_connector
class FroniusSolarAPIConnector(DeviceConnector):
    def info(self) -> ConnectorInfo:
        return ConnectorInfo(id="fronius_solar_api", name="Fronius Solar API", ...)
    async def connect(self, config) -> bool: ...
    async def read_meters(self, config) -> MeterReading: ...
```

### Neuen Cloud-Connector hinzufügen (Stufe 3, Zukunft)
```python
# backend/services/connectors/solaredge_cloud.py – SolarEdge API-Key basiert
# backend/services/connectors/enphase_cloud.py – Enphase OAuth2
# Gleiche ABC wie DeviceConnector, zusätzlich: auth_url(), exchange_token() etc.
```

## Feature-Ideen

### Personalisierter Post-Import-Workflow
Nach einem Portal-Import (oder Connector-Sync) fehlen oft noch Daten für andere Investitionen
(Wallbox, Wärmepumpe, E-Auto). Der Nutzer denkt "fertig", hat aber nur PV/Batterie/Netz importiert.

**Idee:** Nach Import einen "Monatscheck" anbieten, der alle Investitionen der Anlage durchgeht:
- PV-Daten: importiert (aus Portal) ✓
- Wallbox: "Noch keine Daten für Jan-Mär 2026 – jetzt eingeben?"
- Wärmepumpe: "Noch keine Daten..."

Umsetzung: Smarte Weiterleitung zum Monatsabschluss-Wizard, gefiltert auf fehlende Monate/Investitionen.
Könnte auch als eigenständiger "Daten-Status" Dashboard-Widget nützlich sein.

## Hinweise

- **Kein Breaking Change** für bestehende eedc-homeassistant Installationen
- Phase 1 ist sofort umsetzbar (kein Vertrag, keine API-Keys, nur CSV)
- Phase 2 erfordert Tripower X im lokalen Netzwerk + Modbus/API-Aktivierung
- Community kann Parser + Connectors für ihre Hardware beitragen (PR-basiert)
- Voraussetzungen und Verifikationsschritte sind in der Checkliste oben integriert
- Diese Datei wird mit jedem Implementierungsschritt aktualisiert
