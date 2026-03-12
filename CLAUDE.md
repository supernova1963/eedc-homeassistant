# CLAUDE.md - Entwickler-Kontext für Claude Code

> Für Detail-Dokumentation siehe: [Architektur](docs/ARCHITEKTUR.md) | [Entwicklung](docs/DEVELOPMENT.md) | [Benutzerhandbuch](docs/BENUTZERHANDBUCH.md)

## Projektübersicht

**eedc** (Energie Effizienz Data Center) - Standalone PV-Analyse mit optionaler HA-Integration.

**Version:** 2.8.4 | **Status:** Stable Release

## Verbundene Repositories

| Repository | Zweck | Technik |
| --- | --- | --- |
| **eedc-homeassistant** (dieses) | HA-Add-on + Website + Docs | HA-Config, Subtree |
| **[eedc](https://github.com/supernova1963/eedc)** | Standalone EEDC (Source of Truth) | FastAPI, React, SQLite |
| **[eedc-community](https://github.com/supernova1963/eedc-community)** | Anonymer Community-Benchmark-Server | FastAPI, React, PostgreSQL |

**Lokale Pfade:**
- eedc: `/home/gernot/claude/eedc`
- eedc-community: `/home/gernot/claude/eedc-community`

**Live:** https://energy.raunet.eu (Community) | https://supernova1963.github.io/eedc-homeassistant/ (Website)

## Git-Workflow (WICHTIG – gilt für alle Sessions und Rechner!)

### 5 Regeln

1. **Immer auf `main` arbeiten** — keine Feature-Branches. Einzelentwickler-Projekt, Branches erzeugen nur Chaos.
2. **`eedc` ist Source of Truth** für shared Code (backend/, frontend/). Dort zuerst committen und pushen.
3. **Nach Push auf `eedc/main`** → sofort `subtree pull` in `eedc-homeassistant`. Nicht aufschieben.
4. **Versionsnummern + Release** nur wenn der User es explizit anfordert. Dann alle 4 Dateien synchron bumpen.
5. **`eedc-community`** ist unabhängig, aber bei Datenmodell-Änderungen beide Repos synchron anpassen.
6. **Versionen synchron halten** – `eedc` und `eedc-homeassistant` bekommen immer die gleiche Versionsnummer. Release in `eedc` → sofort Subtree Pull + Release in `eedc-homeassistant`.

### Verboten ohne explizite Aufforderung durch den User!

- **`git push`** (in ALLEN Repos) – niemals eigenständig pushen
- **`git subtree pull/push`** – Sync nur auf Anweisung
- **Releases, Tags, Versionsnummern ändern**
- **Änderungen in anderen Repos** – nur dieses Repo bearbeiten, es sei denn der User fordert es explizit

### Subtree-Sync (eedc → eedc-homeassistant)

- Shared Code (backend/, frontend/) → Änderungen im `eedc` Repo machen, dann Subtree Pull
- HA-spezifische Dateien (Dockerfile, config.yaml, run.sh) → Direkt in eedc-homeassistant ändern
- CHANGELOG → Nur Root-CHANGELOG editieren, wird per Script nach `eedc/` kopiert
- **KEIN `git subtree push`** verwenden (würde HA-Dateien ins Standalone-Repo pushen)
- **KEIN `git pull --rebase`** in eedc-homeassistant (Subtree-Commits vertragen kein Rebase)

### Verzeichnisstruktur

```text
eedc-homeassistant/
├── eedc/                    ← git subtree von supernova1963/eedc
│   ├── backend/             ← Shared Code (aus Subtree)
│   ├── frontend/            ← Shared Code (aus Subtree)
│   ├── Dockerfile           ← HA-spezifisch (NICHT aus Subtree!)
│   ├── config.yaml          ← HA-spezifisch
│   ├── run.sh               ← HA-spezifisch
│   ├── icon.png / logo.png  ← HA-spezifisch
│   ├── CHANGELOG.md         ← HA-spezifisch
│   ├── docker-compose.yml   ← Aus Subtree (Standalone)
│   └── README.md            ← Aus Subtree (Standalone)
├── website/                 ← Astro Starlight Website
├── docs/                    ← Single Source of Truth für Dokumentation
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

### Release-Workflow (automatisiert per Scripts!)

Detaillierte Anleitung: [docs/RELEASE-WORKFLOW.md](docs/RELEASE-WORKFLOW.md)

```bash
# Schritt 1: In eedc (Source of Truth)
cd /home/gernot/claude/eedc
./scripts/release.sh 2.8.6          # Bumpt config.py + version.ts, committed + taggt
git push && git push origin v2.8.6  # MANUELL im Terminal!

# Schritt 2: In eedc-homeassistant
cd /home/gernot/claude/eedc-homeassistant
./scripts/sync-and-release.sh 2.8.6 # Subtree Pull + HA-Bump + CHANGELOG-Sync + Tag
git push && git push origin v2.8.6  # MANUELL im Terminal!
```

**Versionsdateien (4 Stück, werden von den Scripts automatisch gebumpt):**
| Datei | Gebumpt durch |
|---|---|
| `eedc/backend/core/config.py` | `release.sh` |
| `eedc/frontend/src/config/version.ts` | `release.sh` |
| `eedc/config.yaml` | `sync-and-release.sh` |
| `eedc/run.sh` | `sync-and-release.sh` |

> **WICHTIG:** HA Add-ons lesen `eedc/CHANGELOG.md`, nicht Root! `sync-and-release.sh` kopiert automatisch.

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

**v2.8.0** - Cloud-Import-Provider + Custom-Import:

- **5 neue Cloud-Import-Provider:** SolarEdge, Fronius SolarWeb, Huawei FusionSolar, Growatt, Deye/Solarman (alle ungetestet)
- **Custom-Import:** Beliebige CSV/JSON mit Feld-Mapping importieren, Templates speicherbar
- **Kostal/SMA Local entfernt** (nur Zählerstände, keine historischen Daten)

**v2.7.1** - Monatsabschluss als zentrale Datenerfassungs-Anlaufstelle:

- **Einstellungen-Menü umgebaut:** Daten-SubTabs auf 3 reduziert (Monatsdaten, Monatsabschluss, Einrichtung), Solarprognose zu Stammdaten verschoben
- **Einrichtung-Hub:** Neue zentrale Seite für Datenquellen-Konfiguration (HA, Connector, Cloud, CSV)
- **Monatsabschluss-Wizard:** Datenquellen-Status-Chips, Cloud-Fetch-Button, Datenherkunft-Anzeige, "Keine Quellen"-Hinweis
- **Monatsabschluss-Schnellzugriff:** Kalender-Icon mit Badge in der Hauptnavigation
- **Cloud-Fetch-Endpoint:** `POST /monatsabschluss/{id}/{j}/{m}/cloud-fetch` für Live-Abruf aus Cloud-APIs

**v2.6.0** - Dynamischer Tarif, Portal-Import, Geräte-Connectors:

- **Dynamischer Tarif:** Monatlicher Ø-Strompreis aus HA-Sensor oder manuell
- **Portal-Import:** CSV-Upload von SMA Sunny Portal, SMA eCharger, EVCC, Fronius Solarweb
- **9 Geräte-Connectors:** SMA ennexOS, SMA WebConnect, Fronius Solar API, go-eCharger, Shelly 3EM, OpenDTU, Kostal Plenticore, sonnenBatterie, Tasmota SML
- **getestet-Flag:** Parser und Connectors zeigen im UI an ob mit echten Geräten verifiziert

Für Details siehe [CHANGELOG.md](CHANGELOG.md) und [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).
