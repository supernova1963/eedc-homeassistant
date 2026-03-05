# CLAUDE.md - Entwickler-Kontext für Claude Code

## Projektübersicht

**eedc** (Energie Effizienz Data Center) - Standalone PV-Analyse mit optionaler HA-Integration.

**GitHub:** https://github.com/supernova1963/eedc

## Git-Workflow (WICHTIG – gilt für alle Sessions und Rechner!)

1. **Immer auf `main` arbeiten** — keine Feature-Branches. Einzelentwickler-Projekt.
2. **`eedc` (dieses Repo) ist Source of Truth** für shared Code (backend/, frontend/). Hier zuerst ändern.
3. **Nach Push auf `eedc/main`** → sofort `subtree pull` in `eedc-homeassistant`.
4. **Versionsnummern + Release** nur wenn der User es explizit anfordert.
5. **`eedc-community`** ist unabhängig, aber bei Datenmodell-Änderungen beide Repos synchron anpassen.

## Verbundene Repositories

| Repository | Zweck | Technik |
| --- | --- | --- |
| **eedc** (dieses) | Standalone EEDC (Source of Truth) | FastAPI, React, SQLite |
| **[eedc-homeassistant](https://github.com/supernova1963/eedc-homeassistant)** | HA-Add-on + Website + Docs | HA-Config, Subtree |
| **[eedc-community](https://github.com/supernova1963/eedc-community)** | Anonymer Community-Benchmark-Server | FastAPI, React, PostgreSQL |

**Lokale Pfade:**
- eedc-homeassistant: `/home/gernot/claude/eedc-homeassistant`
- eedc-community: `/home/gernot/claude/eedc-community`

## Quick Reference

### Entwicklungsserver starten

```bash
# Backend (Terminal 1)
source backend/venv/bin/activate
uvicorn backend.main:app --reload --port 8099

# Frontend (Terminal 2)
cd frontend && npm run dev

# URLs: Frontend http://localhost:3000 | API Docs http://localhost:8099/api/docs
```

### Versionierung (bei Releases aktualisieren!)

```text
backend/core/config.py            → APP_VERSION
frontend/src/config/version.ts    → APP_VERSION
config.yaml                       → version
run.sh                            → Echo-Statement
```

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

## Deprecated (nicht löschen!)

> Die alten `ha_sensor_*` Felder im Anlage-Model dürfen NICHT aus der DB/dem Model entfernt werden (bestehende Installationen). Neuer Code nutzt ausschließlich `sensor_mapping`.
