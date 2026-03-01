# CLAUDE.md - Entwickler-Kontext für Claude Code

> Für Detail-Dokumentation siehe: [Architektur](docs/ARCHITEKTUR.md) | [Entwicklung](docs/DEVELOPMENT.md) | [Benutzerhandbuch](docs/BENUTZERHANDBUCH.md)

## Projektübersicht

**eedc** (Energie Effizienz Data Center) - Standalone PV-Analyse mit optionaler HA-Integration.

**Version:** 2.5.1 | **Status:** Stable Release

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

## git subtree: eedc ↔ eedc-homeassistant

Das `eedc/` Verzeichnis ist ein **git subtree** von `supernova1963/eedc`:

```
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

**Subtree-Workflow:**
```bash
cd /home/gernot/claude/eedc-homeassistant
git subtree pull --prefix=eedc https://github.com/supernova1963/eedc.git main --squash
# WICHTIG: Dockerfile-Konflikt manuell lösen (HA-Version behalten!)
```

**Regeln:**
- Shared Code (backend/, frontend/) → Änderungen im `eedc` Repo machen, dann `subtree pull`
- HA-spezifische Dateien (Dockerfile, config.yaml, run.sh) → Direkt in eedc-homeassistant ändern
- **KEIN `git subtree push`** verwenden (würde HA-Dateien ins Standalone-Repo pushen)

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

### Versionierung (bei Releases aktualisieren!)
```
eedc/backend/core/config.py        → APP_VERSION
eedc/frontend/src/config/version.ts → APP_VERSION
eedc/config.yaml                   → version
eedc/run.sh                        → Echo-Statement
```

### Release-Checkliste
```bash
# 1. Version in allen Dateien aktualisieren (siehe oben)
# 2. CHANGELOG.md aktualisieren + kopieren:
cp CHANGELOG.md eedc/CHANGELOG.md
# 3. Frontend Build
cd eedc/frontend && npm run build
# 4. Git Tag + Push
git tag -a vX.Y.Z -m "Version X.Y.Z" && git push && git push origin vX.Y.Z
# 5. GitHub Release erstellen
```

> **WICHTIG:** HA Add-ons lesen `eedc/CHANGELOG.md`, nicht Root! Immer beide synchron halten.

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

## Letzte Änderungen (v2.5.0)

**v2.5.0** - PVGIS Horizontprofil, Social-Media-Textvorlage, GitHub Releases:
- **PVGIS Horizontprofil:** `usehorizon=1`, eigenes Profil Upload/Abruf, Badge bei Prognosen
- **Social-Media-Textvorlage:** `GET /api/cockpit/share-text/{id}` – Kompakt/Ausführlich, bedingte Blöcke
- **GitHub Releases & Update-Hinweis:** Auto-Releases, Update-Banner im Frontend
- **Community-Fix:** Ausrichtung/Neigung aus Modelfeldern statt Parameter-JSON

**v2.4.0** - Steuerliche Behandlung, Spezialtarife, Sonstige Positionen, Firmenwagen:
- **Kleinunternehmerregelung:** `steuerliche_behandlung` + `ust_satz_prozent` auf Anlage-Model
- **Spezialtarife:** `verwendung` auf Strompreis-Model (`allgemein`/`waermepumpe`/`wallbox`)
- **Sonstige Positionen:** Investitionstyp `sonstiges` mit Kategorien (erzeuger/verbraucher/speicher)
- **Firmenwagen:** `ist_dienstlich` Flag an Wallbox und E-Auto
- **Realisierungsquote:** Panel in Auswertung/Investitionen
- **Grundpreis:** `grundpreis_euro_monat` in Netzbezugskosten

> **⚠️ BREAKING CHANGE (v2.0.0):** Neuinstallation des Add-ons erforderlich! Volume-Mapping `config:ro`.

Für Details siehe [CHANGELOG.md](CHANGELOG.md) und [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).
