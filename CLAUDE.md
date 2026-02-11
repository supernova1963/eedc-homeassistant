# CLAUDE.md - Entwickler-Kontext für Claude Code

> **Hinweis:** Dies ist der Kontext für KI-gestützte Entwicklung. Für Benutzer-Dokumentation siehe [docs/BENUTZERHANDBUCH.md](docs/BENUTZERHANDBUCH.md), für Architektur siehe [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).

## Projektübersicht

**eedc** (Energie Effizienz Data Center) - Standalone PV-Analyse mit optionaler HA-Integration.

**Version:** 1.0.0-beta.1 | **Status:** Feature-complete Beta

## Quick Reference

### Entwicklungsserver starten
```bash
# Backend (Terminal 1)
cd eedc && source backend/venv/bin/activate
uvicorn backend.main:app --reload --port 8099

# Frontend (Terminal 2)
cd eedc/frontend && npm run dev

# URLs
# Frontend: http://localhost:5173
# API Docs: http://localhost:8099/api/docs
```

### Versionierung (bei Releases aktualisieren!)
```
eedc/backend/core/config.py      → APP_VERSION
eedc/frontend/src/config/version.ts → APP_VERSION
eedc/config.yaml                 → version
eedc/run.sh                      → Echo-Statement
```

## Architektur-Prinzipien

1. **Standalone-First:** Keine HA-Abhängigkeit für Kernfunktionen
2. **Datenquellen getrennt:**
   - `Monatsdaten` = Zählerwerte (Einspeisung, Netzbezug)
   - `InvestitionMonatsdaten` = Komponenten-Details (PV, Speicher, E-Auto, etc.)
3. **Legacy-Felder NICHT verwenden:**
   - `Monatsdaten.pv_erzeugung_kwh` → Nutze `InvestitionMonatsdaten`
   - `Monatsdaten.batterie_*` → Nutze `InvestitionMonatsdaten`

## Kritische Code-Patterns

### SQLAlchemy JSON-Felder
```python
from sqlalchemy.orm.attributes import flag_modified

# WICHTIG: Nach Änderung an JSON-Feldern immer flag_modified aufrufen!
obj.verbrauch_daten["key"] = value
flag_modified(obj, "verbrauch_daten")  # Ohne das wird die Änderung NICHT persistiert!
db.commit()
```

### 0-Werte prüfen
```python
# FALSCH - 0 wird als False gewertet
if val:
    ...

# RICHTIG
if val is not None:
    ...
```

## Dateistruktur (wichtigste Dateien)

```
eedc/
├── backend/
│   ├── main.py                    # FastAPI Entry + /stats
│   ├── api/routes/
│   │   ├── cockpit.py             # Dashboard-Aggregation
│   │   ├── import_export.py       # CSV Import (flag_modified!)
│   │   ├── monatsdaten.py         # CRUD + Berechnungen
│   │   └── investitionen.py       # Parent-Child, ROI
│   ├── core/config.py             # APP_VERSION
│   └── services/
│       ├── wetter_service.py      # Open-Meteo + PVGIS TMY
│       └── mqtt_client.py         # HA Export
│
└── frontend/src/
    ├── pages/
    │   ├── Dashboard.tsx          # Cockpit-Übersicht
    │   ├── Auswertung.tsx         # 6 Analyse-Tabs
    │   └── PVAnlageDashboard.tsx  # String-Vergleich (Jahr-Parameter!)
    ├── components/
    │   ├── forms/MonatsdatenForm.tsx  # Dynamische Felder
    │   └── pv/PVStringVergleich.tsx   # SOLL-IST
    └── config/version.ts          # APP_VERSION
```

## Datenmodell (Kurzfassung)

### Parent-Child Beziehungen
```
Wechselrichter (Parent)
├── PV-Module (Child) [PFLICHT]
└── DC-Speicher (Child) [optional, Hybrid-WR]

AC-Speicher, E-Auto, WP, Wallbox, BKW = eigenständig
```

### InvestitionMonatsdaten.verbrauch_daten (JSON)
```json
// PV-Module
{ "pv_erzeugung_kwh": 450.5 }

// Speicher
{ "ladung_kwh": 200, "entladung_kwh": 185, "ladung_netz_kwh": 50 }

// E-Auto
{ "km_gefahren": 1200, "ladung_pv_kwh": 130, "ladung_netz_kwh": 86, "v2h_entladung_kwh": 25 }
```

## API Endpoints (häufig verwendet)

```
GET  /api/cockpit/uebersicht/{anlage_id}?jahr=2025   # Dashboard-Daten
GET  /api/cockpit/pv-strings/{anlage_id}?jahr=2025   # SOLL-IST Vergleich
POST /api/import/csv/{anlage_id}                     # CSV Import
GET  /api/import/template/{anlage_id}                # CSV Template-Info
GET  /api/wetter/monat/{anlage_id}/{jahr}/{monat}    # Wetter Auto-Fill
```

## Bekannte Fallstricke

| Problem | Lösung |
|---------|--------|
| JSON-Änderungen werden nicht gespeichert | `flag_modified(obj, "field_name")` aufrufen |
| 0-Werte verschwinden | `is not None` statt `if val` |
| SOLL-IST zeigt falsches Jahr | `jahr` Parameter explizit übergeben |
| Legacy pv_erzeugung_kwh wird verwendet | InvestitionMonatsdaten abfragen |

## Offene Features

- [ ] PDF-Export
- [ ] KI-Insights

## Letzte Änderungen (v1.0.0-beta.1)

Kritische Fixes für SOLL-IST Vergleich:
1. Legacy `pv_erzeugung_kwh` → `InvestitionMonatsdaten`
2. `flag_modified()` für JSON-Persistenz
3. Jahr-Parameter in PVStringVergleich
4. CSV-Template bereinigt (Legacy-Spalten entfernt)

Siehe [CHANGELOG.md](CHANGELOG.md) für vollständige Versionshistorie.
