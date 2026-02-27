# EEDC Standalone + Cloud-Provider-Integration

## Kontext

EEDC existiert aktuell nur als HA-Add-on (`eedc-homeassistant`). Das alte standalone `eedc` Repo (Supabase/Next.js) ist deprecated/archived. Ziel:

1. **`eedc` Repo reaktivieren** - Neues standalone EEDC (FastAPI/React, gleiche Codebasis)
2. **Cloud-Provider-Integration** - SMA ennexOS als Pilot (Anlage automatisch einrichten + Monatsdaten vorbefüllen)
3. **Shared Core** - `eedc` als Source of Truth, `eedc-homeassistant` nutzt es via git subtree

### Architektur-Entscheidung: Ein Codebase, zwei Deployment-Modi

Der Code bleibt **in einem Repository** (`eedc`). HA-spezifische Features werden **conditional geladen** basierend auf Umgebungserkennung:

```python
# Auto-detect: HA-Add-on hat SUPERVISOR_TOKEN
HA_INTEGRATION = bool(os.environ.get("SUPERVISOR_TOKEN"))
```

- **`eedc`** = Standalone-Modus (kein SUPERVISOR_TOKEN → HA-Features aus, Cloud-Provider an)
- **`eedc-homeassistant`** = subtree von `eedc` + HA-Config. Als Add-on hat es SUPERVISOR_TOKEN → alles aktiv

**Warum nicht physische Code-Trennung?**
- 3 Mixed-Files (monatsabschluss.py, scheduler.py, vorschlag_service.py) haben optionale HA-Hooks
- Conditional Loading ist simpler als zwei Codebases zu synchronisieren
- HA-Code hat bereits graceful degradation (MQTT_AVAILABLE Flag, try/except Imports)

### Repo-Übersicht (Zielzustand)

```
supernova1963/eedc                  # Standalone (reaktiviert)
├── backend/                        # FastAPI
├── frontend/                       # React/Vite
├── docker-compose.yml              # Standalone Deployment
├── Dockerfile                      # Standalone Docker
└── README.md

supernova1963/eedc-homeassistant    # HA-Add-on
├── eedc/                           # ← git subtree von supernova1963/eedc
│   ├── backend/
│   └── frontend/
├── config.yaml                     # HA-Add-on Manifest
├── Dockerfile                      # HA-spezifisches Docker
├── run.sh                          # HA-aware Startup
├── website/
└── docs/

supernova1963/eedc-community        # Community-Server (unverändert)
```

---

## Phase 0: Repo-Restrukturierung

### 0.1 Altes eedc Repo umbenennen

```bash
gh repo rename eedc-legacy --repo supernova1963/eedc
# Danach: supernova1963/eedc ist frei
```

### 0.2 Neues eedc Repo erstellen

Inhalt von `eedc-homeassistant/eedc/` wird die Basis (ohne HA-Add-on Config).

```bash
# Neues Repo erstellen
gh repo create supernova1963/eedc --public --description "EEDC - Energie Effizienz Data Center: Standalone PV-Analyse"

# Lokalen Klon erstellen
cd /home/gernot/claude
mkdir eedc && cd eedc && git init

# Code aus eedc-homeassistant/eedc/ kopieren
cp -r /home/gernot/claude/eedc-homeassistant/eedc/backend .
cp -r /home/gernot/claude/eedc-homeassistant/eedc/frontend .
cp -r /home/gernot/claude/eedc-homeassistant/eedc/data .
```

### 0.3 Conditional Loading einbauen

**`backend/core/config.py` - Feature-Flags:**
```python
# Deployment-Modus Erkennung
HA_INTEGRATION_AVAILABLE = bool(os.environ.get("SUPERVISOR_TOKEN"))
CLOUD_PROVIDER_ENABLED = True  # Immer verfügbar
```

**`backend/main.py` - Conditional Router Registration:**
```python
# Core Routes (immer)
app.include_router(cockpit.router, prefix="/api")
app.include_router(aussichten.router, prefix="/api")
app.include_router(anlagen.router, prefix="/api")
app.include_router(monatsdaten.router, prefix="/api")
app.include_router(investitionen.router, prefix="/api")
app.include_router(strompreise.router, prefix="/api")
app.include_router(monatsabschluss.router, prefix="/api")
app.include_router(wetter.router, prefix="/api")
app.include_router(solar_prognose.router, prefix="/api")
app.include_router(pvgis.router, prefix="/api")
app.include_router(community.router, prefix="/api")
app.include_router(import_export_router, prefix="/api")
app.include_router(cloud_provider.router, prefix="/api")  # NEU

# HA-spezifische Routes (nur im Add-on)
if settings.HA_INTEGRATION_AVAILABLE:
    from backend.api.routes import ha_statistics, ha_export, sensor_mapping, ha_integration
    app.include_router(ha_statistics.router, prefix="/api")
    app.include_router(ha_export.router, prefix="/api")
    app.include_router(sensor_mapping.router, prefix="/api")
    app.include_router(ha_integration.router, prefix="/api")
```

**Frontend: Navigation conditional machen**

`frontend/src/components/layout/SubTabs.tsx` und `TopNavigation.tsx`:
- "Home Assistant" Gruppe nur anzeigen wenn `/api/ha-integration/status` erreichbar
- Neues: "Cloud-Provider" Tab (immer sichtbar, da Core-Feature)
- Gruppe umbenennen: "Datenquellen" (enthält Cloud + optional HA)

**Dateien für Phase 0:**

| Datei | Aktion |
|---|---|
| `backend/core/config.py` | Feature-Flags hinzufügen |
| `backend/main.py` | Conditional Router-Loading |
| `frontend/src/components/layout/SubTabs.tsx` | HA-Tabs conditional, Cloud-Tab hinzufügen |
| `frontend/src/components/layout/TopNavigation.tsx` | HA-Kategorie conditional |
| `frontend/src/hooks/useHAAvailable.ts` | NEU: Hook zur HA-Erkennung (API-Call) |
| `docker-compose.yml` | NEU: Standalone Deployment |
| `Dockerfile` | NEU: Standalone Docker (simpler als HA-Version) |
| `README.md` | NEU: Standalone-Dokumentation |

### 0.4 Standalone Docker

**`docker-compose.yml` (NEU):**
```yaml
services:
  eedc:
    build: .
    ports:
      - "8099:8099"
    volumes:
      - eedc-data:/data
    environment:
      - TZ=Europe/Berlin
volumes:
  eedc-data:
```

**`Dockerfile` (NEU, vereinfacht):**
Basiert auf dem HA-Dockerfile, aber ohne HA-spezifische Labels/Healthcheck.
Multi-stage: Node (Frontend Build) → Python (Runtime).

### 0.5 git subtree Setup (eedc-homeassistant)

```bash
cd /home/gernot/claude/eedc-homeassistant

# Bestehenden eedc/ Ordner entfernen (aus Git, nicht physisch)
git rm -r eedc/backend eedc/frontend eedc/data
git commit -m "refactor: Prepare for eedc subtree integration"

# eedc Repo als Subtree einbinden
git subtree add --prefix=eedc https://github.com/supernova1963/eedc.git main --squash

# HA-spezifische Dateien bleiben im Root:
# eedc-homeassistant/
# ├── eedc/           ← subtree
# ├── config.yaml     ← HA-Add-on
# ├── Dockerfile      ← HA Docker (bleibt bestehen)
# ├── run.sh          ← HA Startup (bleibt bestehen)
# └── ...
```

**Zukünftiger Sync-Workflow:**
```bash
# Änderungen aus eedc holen:
git subtree pull --prefix=eedc https://github.com/supernova1963/eedc.git main --squash

# Änderungen zurück zu eedc pushen:
git subtree push --prefix=eedc https://github.com/supernova1963/eedc.git main
```

---

## Phase 1: SMA Client Foundation (in eedc Repo)

### 1.1 Datenmodell

**`backend/models/anlage.py` - Neues Feld:**
```python
cloud_provider_config: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
```

**`backend/core/database.py` - Migration:**
```python
('cloud_provider_config', 'JSON'),
```

**JSON-Struktur:**
```json
{
  "provider": "sma_ennexos",
  "plant_id": "12345",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "token_expires_at": "2026-03-01T10:00:00Z",
  "device_mapping": { "SMA_INV_001": 5 },
  "auto_fetch_enabled": false,
  "last_fetch_timestamp": null,
  "setup_complete": true
}
```

### 1.2 Provider-Package

```
backend/services/cloud_providers/
├── __init__.py
├── base.py              # ABC CloudProvider + Dataclasses
├── registry.py          # get_provider(), list_providers()
├── token_manager.py     # Token-Refresh (provider-übergreifend)
└── sma_ennexos.py       # SMA ennexOS Implementation
```

**ABC `CloudProvider` (base.py):**
- `get_auth_url()` → OAuth2 URL
- `exchange_code()` → Tokens erhalten
- `refresh_access_token()` → Token erneuern
- `discover_plants()` → Anlagen erkennen
- `discover_devices(plant_id)` → Geräte (WR, Module, Speicher)
- `get_monthly_data(plant_id, device_ids, jahr, monat)` → Monatswerte
- `get_available_months(plant_id)` → Verfügbare Monate
- `test_connection()` → Verbindungstest

**Dataclasses:** CloudPlantInfo, CloudDeviceInfo, CloudMonthlyData

**SMA ennexOS (`sma_ennexos.py`):**
- OAuth2 Code Grant (manueller Copy-Paste, da lokal kein Redirect)
- Sandbox: `sandbox-auth.smaapis.de` / `sandbox.smaapis.de`
- Produktion: `auth.smaapis.de` / `smaapis.de`
- httpx (bereits in requirements.txt)
- 5-Min-Messintervalle → Aggregation zu Monatssummen

**SMA Messdaten-Mapping:**
| SMA | EEDC |
|---|---|
| pvGeneration | pv_erzeugung_kwh |
| batteryCharging | ladung_kwh |
| batteryDischarging | entladung_kwh |
| gridFeedIn | einspeisung_kwh |
| gridConsumption | netzbezug_kwh |

### 1.3 API-Routen

**`backend/api/routes/cloud_provider.py` (NEU):**

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/api/cloud/providers` | Verfügbare Provider |
| GET | `/api/cloud/status/{anlage_id}` | Verbindungsstatus |
| POST | `/api/cloud/auth/init/{provider}` | OAuth2 starten → Auth-URL |
| POST | `/api/cloud/auth/callback` | Code einlösen → Tokens |
| DELETE | `/api/cloud/disconnect/{anlage_id}` | Verbindung trennen |

**Registrierung in `backend/main.py`:**
```python
from backend.api.routes import cloud_provider
app.include_router(cloud_provider.router, prefix="/api")
```

**Voraussetzung:** SMA Developer Portal Registrierung (developer.sma.de)

---

## Phase 2: System Discovery + Smart Setup Wizard

### 2.1 Backend

**Zusätzliche Endpoints in `cloud_provider.py`:**

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/api/cloud/discover/{anlage_id}` | System erkennen |
| POST | `/api/cloud/import-system/{anlage_id}` | Investitionen erstellen |

**Import-Logik:**
1. Cloud-Devices abrufen
2. Pro WR: `Investition(typ="wechselrichter")` mit auto-fill
3. Pro PV-String: `Investition(typ="pv-module", parent_investition_id=WR)`
4. Pro Speicher: Child (Hybrid-WR) oder standalone (AC)
5. Manuelle Felder (Kosten, Datum) aus Request mergen
6. `device_mapping` speichern + `flag_modified()`

**Auto-Fill vs. Manuell:**
| Feld | Quelle |
|---|---|
| stamm_hersteller, stamm_modell, stamm_seriennummer | Cloud API |
| max_leistung_kw, leistung_kwp, kapazitaet_kwh | Cloud API |
| ausrichtung, neigung_grad, anzahl_module | Cloud API |
| anschaffungskosten_gesamt, betriebskosten_jahr | Manuell |
| anschaffungsdatum, Strompreise | Manuell |

### 2.2 Frontend

**`frontend/src/pages/CloudSetupWizard.tsx` (NEU):**

5-Schritt Wizard (Vorbild: SensorMappingWizard):
1. **Provider wählen** - Dropdown + Info was die Integration kann
2. **Authentifizierung** - "SMA Login öffnen" + Code-Eingabefeld
3. **System-Vorschau** - Erkannte Geräte als Baum, Checkboxen
4. **Kosten ergänzen** - Pro Gerät: Anschaffungskosten, Datum
5. **Zusammenfassung** - Übersicht + Auto-Fetch Toggle + "Einrichten"

**`frontend/src/api/cloudProvider.ts` (NEU):**
API Client für alle Cloud-Endpoints.

**Navigation:**
- `SubTabs.tsx`: Neue Gruppe "Datenquellen" mit Cloud-Provider Tab (immer) + HA-Tabs (conditional)
- `TopNavigation.tsx`: Gleiche Struktur
- `App.tsx`: Route `/einstellungen/cloud-setup` → CloudSetupWizard

---

## Phase 3: Monatsdaten-Prefill

### 3.1 Backend

**`backend/services/vorschlag_service.py` (Zeile 24):**
```python
CLOUD_API = "cloud_api"  # Konfidenz: 90 (zwischen HA_SENSOR:95 und VORMONAT:80)
```

**Zusätzliche Endpoints in `cloud_provider.py`:**

| Methode | Pfad | Beschreibung |
|---|---|---|
| GET | `/api/cloud/monatswerte/{anlage_id}/{jahr}/{monat}` | Monatsdaten abrufen |
| GET | `/api/cloud/verfuegbare-monate/{anlage_id}` | Verfügbare Monate |

Separater Endpoint (nicht in Monatsabschluss eingebaut), da Cloud-Abrufe mehrere Sekunden dauern können.

### 3.2 Frontend

**`frontend/src/pages/MonatsabschlussWizard.tsx`:**
- Neuer Button "Werte aus Cloud laden" (neben bestehendem "Werte aus HA laden")
- Nur sichtbar wenn `cloud_provider_config.setup_complete === true`
- Lädt Werte asynchron → zeigt als Vorschläge → User übernimmt einzeln

---

## Phase 4: Scheduler + Sicherheit + Polish

### 4.1 Scheduler

**`backend/services/scheduler.py`:**
- Neuer CronJob `cloud_monthly_fetch` (1. des Monats, 00:15)
- Nur für Anlagen mit `auto_fetch_enabled: true`
- Cached Cloud-Werte als Vorschläge (NICHT automatischer Monatsabschluss)

### 4.2 Sicherheit

**`backend/api/routes/import_export/json_operations.py`:**
- `cloud_provider_config` aus JSON-Export ausschließen (Tokens!)

**Token-Management:**
- Auto-Refresh via `token_manager.py` vor jedem API-Call
- Bei Refresh-Token-Ablauf: UI-Hinweis "Erneut anmelden"

---

## Zusammenfassung: Alle Dateien

### Phase 0 (Repo-Setup)

| Datei (im neuen eedc Repo) | Aktion |
|---|---|
| `backend/core/config.py` | Feature-Flags (HA_INTEGRATION_AVAILABLE) |
| `backend/main.py` | Conditional Router-Loading |
| `frontend/src/components/layout/SubTabs.tsx` | HA conditional, Datenquellen-Gruppe |
| `frontend/src/components/layout/TopNavigation.tsx` | HA conditional |
| `frontend/src/hooks/useHAAvailable.ts` | NEU: HA-Erkennung |
| `docker-compose.yml` | NEU: Standalone Deployment |
| `Dockerfile` | NEU: Standalone Docker |
| `README.md` | NEU |

### Phase 1-4 (Cloud-Provider, im eedc Repo)

| Datei | Aktion | Phase |
|---|---|---|
| `backend/services/cloud_providers/__init__.py` | NEU | 1 |
| `backend/services/cloud_providers/base.py` | NEU | 1 |
| `backend/services/cloud_providers/registry.py` | NEU | 1 |
| `backend/services/cloud_providers/token_manager.py` | NEU | 1 |
| `backend/services/cloud_providers/sma_ennexos.py` | NEU | 1 |
| `backend/models/anlage.py` | ÄNDERN (cloud_provider_config) | 1 |
| `backend/core/database.py` | ÄNDERN (Migration) | 1 |
| `backend/api/routes/cloud_provider.py` | NEU | 1+2+3 |
| `backend/main.py` | ÄNDERN (Cloud-Router) | 1 |
| `frontend/src/pages/CloudSetupWizard.tsx` | NEU | 2 |
| `frontend/src/api/cloudProvider.ts` | NEU | 2 |
| `frontend/src/App.tsx` | ÄNDERN (Route) | 2 |
| `backend/services/vorschlag_service.py` | ÄNDERN (CLOUD_API) | 3 |
| `frontend/src/pages/MonatsabschlussWizard.tsx` | ÄNDERN (Cloud-Button) | 3 |
| `backend/services/scheduler.py` | ÄNDERN (Cloud-Job) | 4 |
| `backend/api/routes/import_export/json_operations.py` | ÄNDERN (Token-Exclude) | 4 |

### Phase 5 (Subtree, in eedc-homeassistant)

| Aktion |
|---|
| `git subtree add --prefix=eedc` von eedc Repo |
| HA-Dateien (config.yaml, Dockerfile, run.sh) bleiben im Root |
| Dokumentation: Subtree-Workflow in CLAUDE.md |

---

## Reihenfolge & Abhängigkeiten

```
Phase 0: Repo-Setup
  ├── 0.1 Altes eedc → eedc-legacy umbenennen
  ├── 0.2 Neues eedc Repo erstellen + Code kopieren
  ├── 0.3 Conditional Loading einbauen
  ├── 0.4 Standalone Dockerfile + docker-compose
  └── 0.5 Testen: eedc standalone läuft ohne HA

Phase 1: SMA Client Foundation (braucht: Phase 0 + SMA Developer Account)
  ├── Provider-Package + ABC
  ├── SMA ennexOS Client (OAuth2 + API-Calls)
  ├── Datenmodell (cloud_provider_config)
  └── API-Routen (Auth + Status)

Phase 2: Smart Setup Wizard (braucht: Phase 1 + Sandbox-Credentials)
  ├── Discovery + Import Endpoints
  ├── CloudSetupWizard.tsx (5 Schritte)
  └── Navigation-Integration

Phase 3: Monatsdaten-Prefill (braucht: Phase 2)
  ├── VorschlagQuelle.CLOUD_API
  ├── Monatswerte-Endpoints
  └── "Werte aus Cloud laden" Button

Phase 4: Scheduler + Polish (braucht: Phase 3)
  ├── Auto-Fetch CronJob
  ├── Token-Sicherheit (Export-Exclude)
  └── Dokumentation

Phase 5: Subtree Integration (braucht: Phase 0, unabhängig von 1-4)
  └── eedc-homeassistant nutzt eedc als Subtree
```

**Hinweis:** Phase 5 kann parallel zu Phase 1-4 erfolgen, sobald Phase 0 abgeschlossen ist.

## Voraussetzungen (VOR Implementierung)

1. **SMA Developer Portal** (developer.sma.de) registrieren + Sandbox-Credentials anfordern
2. **GitHub**: Altes eedc Repo umbenennen (Adminrechte nötig)

## Verifikation

- **Phase 0:** `docker-compose up` → EEDC läuft standalone, HA-Tabs nicht sichtbar, Cloud-Tab sichtbar
- **Phase 1:** `GET /api/cloud/providers` → SMA ennexOS in Liste. OAuth2 mit SMA Sandbox testen
- **Phase 2:** Wizard: Provider → Auth → Discover → Kosten → Investitionen korrekt angelegt
- **Phase 3:** Monatsabschluss → "Werte aus Cloud laden" → Vorschläge erscheinen
- **Phase 4:** Scheduler-Job manuell triggern, JSON-Export ohne Tokens prüfen
- **Phase 5:** `git subtree pull` in eedc-homeassistant, HA-Add-on funktioniert weiterhin
