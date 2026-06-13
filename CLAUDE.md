# CLAUDE.md - Entwickler-Kontext für Claude Code

> Für Detail-Dokumentation siehe: [Architektur](docs/ARCHITEKTUR.md) | [Entwicklung](docs/DEVELOPMENT.md) | [Benutzerhandbuch](docs/BENUTZERHANDBUCH.md)

## Projektübersicht

**eedc** (Energie Effizienz Data Center) - Standalone PV-Analyse mit optionaler HA-Integration.

**Version:** 3.29.2 | **Status:** Stable Release

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
./scripts/release.sh 3.17.0
```

Das Script macht automatisch:
1. Bumpt Version in allen 5 Dateien
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

## Design-Konventionen (Regel 0a — Pflicht bei allem Neuen)

> SoT: [`docs/KONZEPT-STYLE-GUIDE.md`](docs/KONZEPT-STYLE-GUIDE.md) (Regel Nr. 0 + 0a am Anfang). Farb-SoT: `frontend/src/lib/colors.ts`.

Bei **allem mit Darstellung** (Seite, Komponente, Chart, Tabelle, Tooltip, Button, Badge, Bericht, Text, Sensor-Name …) gilt: (1) **Regel/SoT existiert → anwenden** (keine lokale/harte Formatierung daneben); (2) **keine, aber sinnvoll → Regel definieren + Zentrale erweitern in derselben Arbeit**; (3) **echter Einzelfall → Maintainer-Freigabe + Code-Kommentar + Ausnahmen-Liste**.

- **Keine Inline-Hex-Farben** außerhalb `lib/colors.ts`. **Pflicht-Check bei Frontend-Arbeit:** `cd eedc/frontend && npm run check:design` (muss 0 melden) — Allowlist-Eintrag = bewusste Freigabe.
- **Eine Datenrolle = eine Farbe** (`lib/colors.ts`); **eine Komponenten-Klasse = eine SoT-Komponente** (KPICard, Button, ChartTooltip, Modal …) — nie eine zweite Komponente für ein bestehendes Pattern.
- **Typ-Reihenfolge** immer aus `INVESTITION_TYP_ORDER`/`compareTyp` bzw. Backend `sort_investitionen_nach_typ`. **Datums-Listen/Tabellen** Default absteigend (neueste zuerst). **% mit Leerzeichen**, **„eedc"** klein.

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

**v3.29.x** (2026-05-13/14) — Aggregations-Hardening + UX-Bündel vor Menüstruktur-Konzept:

- **Anschaffungs-/Stilllegungsdatum-Filter durchgängig (v3.29.0/v3.29.1, #236 #239):** alle Read-Sites (Cockpit, Energieprofil, HA-Stats-Aggregation, Monatsbericht-Sektionen) respektieren jetzt `inv.installationsdatum`/`stilllegungsdatum`. Folgewelle nach #236 zeigte: Filter auf einer Schicht reicht nicht bei parallelen Pfaden.
- **SoT-Helper `get_inv_value` für `leistung_kwp` (#229):** PV-String-Verteilung liest jetzt Spalten-Wert mit Fallback auf `parameter`-JSON statt Gleichverteilung.
- **UX-Cluster #233 (P13–P18):** chirurgische Fixes Display-Token `'—'`, kWh-Einheiten im WP-Dashboard (#237), Daten-Checker Inbetriebnahme-Monat ausgeschlossen (#240), Sparkline-Tooltip mit Monatsname (#241).
- **eedc-Schreibweise (v3.29.2):** ~130 Treffer in Code + Hilfe-Docs auf Wort „eedc" vereinheitlicht; `\bEEDC\b`-Wortgrenze schützt Identifier wie `EEDC_Prognose` automatisch.

**v3.28.0** (2026-05-13) — Reparatur-Werkbank: Mehrere Tage neu aggregieren (#230).

**v3.27.x** (2026-05-10/12) — Etappe 3d + Tester-Päckchen:

- **Etappe 3d Daten-Provenance & Reparatur-Werkbank (v3.27.0):** Anomalie-Erkennung mit punktuellem Reparatur-Pfad; bewusst KEIN globaler Heiler-Knopf.
- **UX-Sprint A1+A2+A3 + Power-Sensor-Bug (v3.27.1, #200):** Wizard + Live-Heute + Stats-API ziehen jetzt `_is_energy_sensor` konsistent durch (kW darf nicht in kWh-Slot).
- **WP-Aggregation: Split-Strommessung + Counter-Spike-Cap (v3.27.4, #230):** MartyBr-Bug-Report mit Screenshot als Vorlage.
- **UX-Cluster detLAN (v3.27.5, #207 #215 #217 #218 #494) + Folge-Päckchen Tester-Bugs (v3.27.3, #220 #222 #226 #227 #228).**

**v3.26.x** (2026-05-06/09) — Korrekturprofil + HA-Energy-Import + Etappe 3c:

- **EEDC-Korrekturprofil O1+O2 (v3.26.0–v3.26.2):** Päckchen 1 (Recency) + Päckchen 2 (Sonnenstand × Wetter live) parallel zum Legacy-Skalar als Diagnose. Live-Pfad-Switch wird in Prognosequellen-Wahl Schritt 2 mitgemacht.
- **HA-Energiekonfiguration importieren (v3.26.5, #197):** Setup-Vereinfachung Olli0103 — Energy-Dashboard-Konfig aus HA wird im Setup-Wizard übernommen.
- **Etappe 3c Energieprofil Read-/Write-Architektur konsolidiert (v3.26.8):** zentraler SoT-Helper statt Drift-Patches; siehe `docs/archive/KONZEPT-DATENPIPELINE.md`.
- **Reload-Vorschau Counter-Boundary + „Nur neu rechnen" (v3.26.6):** Vorschau heilt sich selbst.

**v3.25.x** (2026-04-29/05-05) — Live-Snapshot 5-Min + Investitions-Parameter-SoT:

- **Live-Snapshot 5-Min Backend (v3.25.3–v3.25.6):** Phase 1 Backend für Live-Tagesverlauf-Service ausgeliefert + validiert (Off-by-one-Fix state→sum). Frontend-Umstellung noch offen.
- **Investitions-Parameter Single Source of Truth (v3.25.0):** `lib/investitionParameter.ts` + `core/investition_parameter.py` als gemeinsame Konstanten-Map; DB-Migration `_migrate_investitionen_parameter_keys_v325` korrigiert 7 Drift-Bugs (V2H, Jahresfahrleistung, PV-Ladeanteil, Vergleichsverbrauch, Speicher-Arbitrage, Wallbox-Leistung, WP-Preis-Default).
- **Pool-Bug Quick-Fix Wallbox+E-Auto (v3.25.11):** Drift-Konsistenz zwischen `cockpit/uebersicht.py` und `aktueller_monat._aggregate` angeglichen.

**v3.24.x** (2026-04-27/29) — WP-Kompressor-Starts + In-App-Hilfe + Sensor-LTS:

- **WP-Kompressor-Starts (v3.24.0, #136):** optionaler Total-Increasing-Sensor pro WP, neue `KUMULATIVE_COUNTER_FELDER`-Architektur trennt Counter strikt von kWh-Feldern. KPI-Kacheln in Monatsbericht + WP-Dashboard (v3.24.4, #169).
- **Sensor-Filter aufgeweicht + „ohne Statistik"-Badge (v3.24.1, #136 Folge):** Nibe-Roh-Counter ohne `state_class` jetzt auswählbar, Frontend-Fallback-Link, Daten-Checker-Kategorie SENSOR_MAPPING_LTS — siehe `feedback_ha_lts_keine_zeitmaschine.md`.
- **In-App-Hilfe als pflegbares Werk (v3.24.2):** Sweep aller acht Hilfe-Dokumente (BENUTZERHANDBUCH, HANDBUCH_INSTALLATION/BEDIENUNG/EINSTELLUNGEN/INFOTHEK, BERECHNUNGEN, SENSOR-REFERENZ, GLOSSAR) auf v3.24-Stand. Sidebar-Eintrag „Was ist neu" (v3.24.5, Discussion #130 Folge Safi105).
- **PV-Cockpit: Speicher-Kapazität + WR-Eigenleistung sichtbar (v3.24.4/v3.24.6, #172 detLAN):** Key-Drift `batteriekapazitaet_kwh` vs. `kapazitaet_kwh` korrigiert, Orphan-Speicher-Block ergänzt.

**v3.23.x** (2026-04-25/27) — MAE/MBE + MQTT-Daten-Checker + Mobile-Hardening:

- **MAE + Bias trennen im Genauigkeits-Tracking (v3.22.0/v3.23.x, #151):** drei Quellen (OpenMeteo/EEDC/Solcast), Bias neutral gefärbt, Spaltenstruktur stabil auch ohne Lernfaktor.
- **MQTT-Topic-Abdeckung im Daten-Checker (v3.23.7, #134):** Drift zwischen dynamischer Konsumenten-Seite und statischer Publisher-Seite wird sichtbar; bei nicht aktivem Subscriber stillschweigend übersprungen (v3.23.8 detLAN/rapahl).
- **Klickbarer Reparatur-Popover bei IST-Lücke (v3.23.0, #147):** Button „Tag neu berechnen" + Fallback-Link Sensor-Mapping. Restart-Recovery für verpasste :05/:55-Snapshot-Jobs.
- **iOS Safari `h-dvh` + COP→JAZ-Harmonisierung (v3.23.6/v3.23.4, #161/#167):** siehe `feedback_ios_companion_app.md` und Wizard-Sweep für Key-Drift (`batterie_kwh`→`batteriekapazitaet_kwh` u. a.).

**v3.19.0–v3.22.0** (2026-04-22/25) — Architekturwechsel + Slot-Konvention + WP-Gaspreis:

- **kWh aus Zähler-Snapshots statt Leistungs-Integration (v3.19.0, #135):** kritischer Architekturwechsel — stündliche `sensor_snapshots`-Tabelle, Self-Healing, ±5–15 % Drift weg.
- **Performance Ratio nutzt GTI statt GHI (v3.20.0, #139):** physikalisch unmögliche PR-Werte >1.2 im Winter korrigiert.
- **Slot-Konvention auf Backward vereinheitlicht (v3.20.0, #144):** OpenMeteo/Solcast/IST jetzt alle Slot N = Energie [N-1, N), Industriestandard.
- **WP-Alternativvergleich + Monats-Gaspreis (v3.21.0, #141) + aufklappbare Energieprofil-Sektionen (#148).**

**v3.17.0–v3.18.0** (2026-04-21) — Dynamische Benzinpreise + Energieprofil-Tab:

- **Dynamische Benzinpreise aus EU Weekly Oil Bulletin (v3.17.0):** echte monatliche Kraftstoffpreise statt statischem Parameter, History seit 2005.
- **Energieprofil-Tab + anlage-spezifische Datenverwaltung (v3.18.0, #133):** Tages-Tabelle mit Spalten-Selektor, Pro-Tag-Reaggregation, Vollbackfill aus HA-Statistik.

**v3.16.x** (April 2026) — Solcast PV Forecast (v3.16.4): Prognosen-Vergleich-Tab (OpenMeteo / EEDC kalibriert / Solcast / IST); Sensor-Mapping Strompreis (Tibber/aWATTar/EPEX), Stündliche Strompreis-Mitschrift; Infothek Etappe 3.6 (v3.16.2).

**Ältere Meilensteine:** PDF-Dokumente + Infothek N:M (v3.15), Stilllegungsdatum (v3.14), Monatsberichte + Energieprofil Etappe 3 (v3.12/3.13), Import-Strategie (v3.10), Live Dashboard Generalüberholung (v3.9), L2-Cache (v3.7), Infothek (v3.5), Wettermodell-Kaskade (v3.4), GTI-Prognose (v3.3), Live Dashboard + MQTT-Inbound (v3.0).

Für Details siehe [CHANGELOG.md](CHANGELOG.md) und [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).

## Roadmap & offene Punkte

Single Source of Truth: **GitHub Issue [#110 — Roadmap Anfrage](https://github.com/supernova1963/eedc-homeassistant/issues/110)**.

Aktuellen Stand bei Bedarf abrufen via `gh issue view 110 --repo supernova1963/eedc-homeassistant`.
