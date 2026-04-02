# CLAUDE.md - Entwickler-Kontext für Claude Code

> Für Detail-Dokumentation siehe: [Architektur](docs/ARCHITEKTUR.md) | [Entwicklung](docs/DEVELOPMENT.md) | [Benutzerhandbuch](docs/BENUTZERHANDBUCH.md)

## Projektübersicht

**eedc** (Energie Effizienz Data Center) - Standalone PV-Analyse mit optionaler HA-Integration.

**Version:** 3.3.6 | **Status:** Stable Release

## Verbundene Repositories

| Repository | Zweck | Technik |
| --- | --- | --- |
| **eedc-homeassistant** (dieses) | Source of Truth, HA-Add-on, Website, Docs | FastAPI, React, SQLite |
| **[eedc](https://github.com/supernova1963/eedc)** | Standalone-Distribution für Nutzer ohne HA | Spiegel von eedc/ |
| **[eedc-community](https://github.com/supernova1963/eedc-community)** | Anonymer Community-Benchmark-Server | FastAPI, React, PostgreSQL |

**Lokale Pfade:**
- eedc: `/home/gernot/claude/eedc`
- eedc-community: `/home/gernot/claude/eedc-community`

**Live:** https://energy.raunet.eu (Community) | https://supernova1963.github.io/eedc-homeassistant/ (Website)

## Git-Workflow (WICHTIG – gilt für alle Sessions und Rechner!)

### Regeln

1. **Immer auf `main` arbeiten** — keine Feature-Branches. Einzelentwickler-Projekt.
2. **eedc-homeassistant ist Source of Truth** — ALLE Änderungen (backend, frontend, docs, HA-Config) hier machen. Nie direkt in `eedc`.
3. **`eedc`-Repo wird nur per Release-Script synchronisiert** — kein manuelles Editieren, kein Subtree.
4. **Versionsnummern + Release** nur wenn der User es explizit anfordert.
5. **`eedc-community`** ist unabhängig, aber bei Datenmodell-Änderungen beide Repos synchron anpassen.

### Verboten!

- **Direkt im `eedc`-Repo arbeiten** — das ist nur ein Spiegel, wird per Script synchronisiert
- **`git subtree pull/push`** — wird nicht mehr verwendet
- **Releases, Tags, Versionsnummern ändern** — nur auf explizite User-Aufforderung
- **`git push`** — nur auf User-Aufforderung oder über `scripts/release.sh`

### Verzeichnisstruktur

```text
eedc-homeassistant/           ← Source of Truth
├── eedc/                     ← Gesamte Anwendung
│   ├── backend/              ← FastAPI Backend (Python)
│   ├── frontend/             ← React Frontend (TypeScript)
│   ├── Dockerfile            ← HA-spezifisch (mit Labels, jq, run.sh)
│   ├── config.yaml           ← HA Add-on Konfiguration
│   ├── run.sh                ← HA Container-Startscript
│   ├── icon.png / logo.png   ← HA Add-on Icons
│   ├── CHANGELOG.md          ← Kopie von Root (per Script)
│   ├── docker-compose.yml    ← Für Standalone-Nutzung
│   └── README.md             ← Projekt-README
├── website/                  ← Astro Starlight Website
├── scripts/                  ← Release + Utility Scripts
├── docs/                     ← Single Source of Truth für Dokumentation
├── CHANGELOG.md              ← Master-CHANGELOG (hier editieren!)
├── CLAUDE.md
└── repository.yaml
```

## Quick Reference

### Entwicklungsserver starten

```bash
# Backend (Terminal 1)
cd eedc && source backend/venv/bin/activate
uvicorn backend.main:app --reload --port 8099

# Frontend (Terminal 2)
cd eedc/frontend && npm run dev

# URLs: Frontend http://localhost:3000 | API Docs http://localhost:8099/api/docs
```

### Release-Workflow (ein Script für alles!)

```bash
cd /home/gernot/claude/eedc-homeassistant
./scripts/release.sh 2.8.6
```

Das Script macht automatisch:
1. Bumpt Version in allen 4 Dateien
2. Kopiert CHANGELOG nach eedc/
3. Committed + taggt + pusht eedc-homeassistant
4. Synchronisiert backend/ + frontend/ nach eedc-Standalone
5. Committed + taggt + pusht eedc

**Versionsdateien (5 Stück, alle in eedc/):**

| Datei | Zweck |
| --- | --- |
| `backend/core/config.py` | APP_VERSION (Backend) |
| `frontend/src/config/version.ts` | APP_VERSION (Frontend) |
| `config.yaml` | HA Add-on Version |
| `run.sh` | Startup-Banner |
| `Dockerfile` | `io.hass.version` Label |

> **WICHTIG:** HA Add-ons lesen `eedc/CHANGELOG.md`. Das Release-Script kopiert automatisch.

### Website (Astro Starlight)

```bash
cd website && npm run dev    # http://localhost:4321/eedc-homeassistant/
cd website && npm run build  # Synct automatisch docs/ → website/ (via scripts/sync-docs.sh)
```

**Technik:** Astro Starlight (v0.37), GitHub Pages, German-only
**Deployment:** Automatisch via `.github/workflows/deploy-website.yml` bei Push auf `main`
**Single Source of Truth:** Dokumentationen in `docs/` pflegen, `scripts/sync-docs.sh` generiert Website-Versionen mit Frontmatter.

**Starlight-Hinweis:** Invertierte Farbskala im Light Mode! `--sl-color-white` = Text, `--sl-color-black` = Hintergrund. Grau-Skala in `custom.css` definieren.

## Architektur-Prinzipien

1. **Standalone-First:** Keine HA-Abhängigkeit für Kernfunktionen
2. **Datenquellen getrennt:** `Monatsdaten` = Zählerwerte, `InvestitionMonatsdaten` = Komponenten-Details
3. **Legacy-Felder NICHT verwenden:** `Monatsdaten.pv_erzeugung_kwh` und `Monatsdaten.batterie_*` → Nutze `InvestitionMonatsdaten`

## Kritische Code-Patterns

### SQLAlchemy JSON-Felder

```python
from sqlalchemy.orm.attributes import flag_modified
obj.verbrauch_daten["key"] = value
flag_modified(obj, "verbrauch_daten")  # Ohne das wird die Änderung NICHT persistiert!
db.commit()
```

### 0-Werte prüfen

```python
# FALSCH: if val:     → 0 wird als False gewertet
# RICHTIG: if val is not None:
```

## Bekannte Fallstricke

| Problem | Lösung |
|---------|--------|
| JSON-Änderungen werden nicht gespeichert | `flag_modified(obj, "field_name")` aufrufen |
| 0-Werte verschwinden | `is not None` statt `if val` |
| SOLL-IST zeigt falsches Jahr | `jahr` Parameter explizit übergeben |
| Legacy pv_erzeugung_kwh wird verwendet | InvestitionMonatsdaten abfragen |
| ROI-Werte unterschiedlich | Cockpit = Jahres-%, Aussichten = Kumuliert-% |

## Community-Datenfluss

```
EEDC Add-on                              Community Server
┌──────────────────────┐                 ┌──────────────────┐
│ CommunityShare.tsx   │ ── POST ──────→ │ /api/submit      │
│ CommunityVergleich   │ ── Proxy ─────→ │ /api/benchmark/  │
│   .tsx (embedded)    │                 │   anlage/{hash}  │
│ "Im Browser öffnen"  │ ── Link ──────→ │ /?anlage=HASH    │
└──────────────────────┘                 └──────────────────┘
```

> **Beachte:** Änderungen am Datenmodell müssen in **beiden** Repositories synchron angepasst werden:
> Schemas in `eedc-community/backend/schemas.py` und Aufbereitung in `eedc/backend/services/community_service.py`.

## Deprecated (nicht löschen!)

> Die alten `ha_sensor_*` Felder im Anlage-Model dürfen NICHT aus der DB/dem Model entfernt werden (bestehende Installationen). Neuer Code nutzt ausschließlich `sensor_mapping`.

## Letzte Änderungen

**v3.3.x** - Frontend-Refactoring, Community, Energiefluss:

- **Frontend-Refactoring (v3.3.4–v3.3.6):** 7-Phasen-Refactoring: `lib/` Utils, shared Hooks (`useSelectedAnlage`, `useApiData`), Chart-Komponenten, Common-Components (`PageHeader`, `DataLoadingState`), Dashboard + Wizard zerlegt, alle 27 Seiten migriert
- **Energiefluss 3D (v3.3.3):** 3D-Perspektivhintergrund, leuchtende Flusslinien mit Elektronen-Partikeln
- **GTI-Prognose (v3.3.0):** PV-Ertragsprognose mit Global Tilted Irradiance, Multi-String, Lernfaktor, Temperaturkorrektur

**v3.0.0–v3.0.3** - Live Dashboard, MQTT-Inbound, Energiefluss:

- **Live Dashboard:** Echtzeit-Leistungsanzeige mit Gauges, animiertem Energiefluss-Diagramm, Heute/Gestern-kWh
- **MQTT-Inbound:** Universelle Datenbrücke für beliebige Smarthome-Systeme
- **Sensor-Mapping:** Ersetzt alte `ha_sensor_*` Felder, konfigurierbar im Wizard

Für Details siehe [CHANGELOG.md](CHANGELOG.md) und [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).

## Parkplatz — Offene Punkte & zurückgestellte Ideen

> Dieser Abschnitt ist rechnerübergreifend. Nach jeder Session: kurz eintragen, committen, pushen.
> Format: `- **Thema** — Was/Warum/Stand`

### Bugs / Offene Issues

- **Issue #90** (OPEN) — Statistik-Import zeigt aktuellen (unvollständigen) Monat + WP-Sensor-Mapping Bugs (Rainer/simon42-Feedback). Analyse liegt im Issue, noch nicht gefixt.
- **MariaDB CONVERT_TZ Bug** — Import-Vorschau wirft 500, weil `CONVERT_TZ()` auf HA-MariaDB `NULL` zurückgibt. Betrifft nur MariaDB-Nutzer. Noch offen.

### Live-Dashboard Performance — NÄCHSTE AKTION (Option A)

**Diagnose (2026-04-02, vollständig analysiert):**

`get_live_data()` ruft bei jedem Live-Refresh (alle paar Sekunden) `_safe_get_tages_kwh()` zweimal auf:

- `gestern` → gecacht ✓
- `heute` → **kein Cache** ✗ → bei jedem Aufruf voller HA-History-API-Call für alle Sensoren von Mitternacht bis jetzt

Relevante Stellen:

- `eedc/backend/services/live_power_service.py` Zeile 644–645: die beiden `_safe_get_tages_kwh`-Aufrufe
- `eedc/backend/services/live_power_service.py` Zeile 743–781: `_safe_get_tages_kwh()` — gestern-Cache ist ab Zeile 752, heute hat keinen
- `eedc/backend/services/live_power_service.py` Zeile 1780–1796: `_get_gestern_kwh_cache()` / `_set_gestern_kwh_cache()` — das ist das Cache-Pattern das für heute zu kopieren ist

**Fix (Option A) — heute-kWh Cache mit 60s TTL:**

1. Analog zu `_gestern_kwh_cache` ein `_heute_kwh_cache` Dict + Timestamp anlegen (Zeile ~1780ff)
2. `_get_heute_kwh_cache()` / `_set_heute_kwh_cache()` als neue Methoden (60s TTL statt bis Mitternacht)
3. In `_safe_get_tages_kwh()` bei `tage_zurueck == 0` denselben Cache-Check einbauen wie bei `tage_zurueck >= 1`

**Testumgebung:** HA-Sensor-Zuordnung in der lokalen Testinstanz rausnehmen (damit nicht auf HA-API zugegriffen wird und der MQTT-Fallback / Cache greift).

**Option B (Refactoring, nach Option A):** Vollständige Ablösung HA-History für Live-Dashboard. Details siehe nächster Abschnitt.

### Live-Dashboard Performance — Option B Refactoring-Plan

**Analyse (2026-04-02):** Die MQTT-Infrastruktur ist weiter als erwartet. Kein echter Neubau nötig — nur Umpriorisierung + eine neue Tabelle.

**Ist-Zustand der Datenquellen:**

| Datenbedarf | Aktuell | MQTT-Pfad vorhanden? |
|---|---|---|
| Live-Wattage (W) | MQTT-Cache | fertig |
| Heute/Gestern kWh | HA-History bei jedem Refresh | MqttEnergySnapshot — nie genutzt |
| Tagesverlauf-Chart | HA-History (separater Endpoint) | fehlt |
| Verbrauchsprofil | TagesEnergieProfil stündlich, sentinel-gecacht | ausreichend, kein Handlungsbedarf |

**`MqttEnergySnapshot`** (bereits vorhanden in `eedc/backend/services/mqtt_energy_history_service.py`):

- Macht alle 5 Min Snapshots der Energy-Cache-Werte in SQLite
- `get_tages_kwh()` liefert heute/gestern kWh mit denselben Keys wie HA-Pfad
- Wird nie genutzt, weil HA immer zuerst antwortet (Priorität falsch herum)
- **Lücke:** `_KEY_TO_CATEGORY` kennt nur `pv_gesamt_kwh`, `einspeisung_kwh`, `netzbezug_kwh` — per-Komponenten-Keys (Batterie, Wallbox) fehlen, obwohl die MQTT Energy Automation sie bereits publisht

**Schritt 1 — Option A (Quick-Fix, separater Schritt):**
60s TTL-Cache für `heute_kwh` — stoppt den HA-History-Flood sofort.

**Schritt 2 — MqttEnergySnapshot als primäre Quelle für heute/gestern kWh:**

1. `_KEY_TO_CATEGORY` in `mqtt_energy_history_service.py` um Komponenten-Keys erweitern: `inv/{id}_{name}/ladung_kwh`, `inv/{id}_{name}/entladung_kwh`, etc.
2. Priorität in `_safe_get_tages_kwh()` (Zeile 757ff) umdrehen: MQTT zuerst, HA als Fallback
3. Kein HA-History-Call mehr für heute/gestern kWh

**Schritt 3 — Tagesverlauf-Chart aus lokaler DB (einziger echter Neubau):**

- Neuer periodischer Task (alle 5 Min): MQTT Live-W-Werte als Snapshot speichern — neue Tabelle `MqttLiveSnapshot` mit `(anlage_id, timestamp, key, value_w)`
- `get_tagesverlauf()` (Zeile 1127 in `live_power_service.py`) liest dann aus lokaler DB statt HA-History
- Modell analog zu `MqttEnergySnapshot`, Retention 2 Tage reicht

**Testumgebung für Option B:**
HA-Sensor-Zuordnung rausnehmen → Code fällt auf MQTT-Pfad durch → leerer Tagesverlauf zeigt wo Schritt 3 noch fehlt, gefüllte kWh-Werte bestätigen Schritt 2.

### Zurückgestellte Features / Ideen

- **WP-Temperaturkorrektur Verbrauchsprognose** — Wärmepumpen-Verbrauch temperaturabhängig skalieren (Heizgradtage). Zurückgestellt bis GTI-Prognose stabil validiert ist.
- **Kraftstoffpreis E-Auto — Monatsdurchschnitt** — Statt statischem `benzinpreis_euro` monatliche Preishistorie pflegen. Diskutiert 2026-04-01, zurückgestellt. Öffentliche Quelle für DE-Durchschnittspreise noch zu klären.

### Ungeklärte Punkte (anderer Rechner)

- **Umfrage** — Intensiv diskutiert auf dem anderen Rechner, Inhalt hier nicht bekannt. Bitte beim nächsten Mal kurz zusammenfassen und hier eintragen.
