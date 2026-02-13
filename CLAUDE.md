# CLAUDE.md - Entwickler-Kontext für Claude Code

> **Hinweis:** Dies ist der Kontext für KI-gestützte Entwicklung. Für Benutzer-Dokumentation siehe [docs/BENUTZERHANDBUCH.md](docs/BENUTZERHANDBUCH.md), für Architektur siehe [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).

## Projektübersicht

**eedc** (Energie Effizienz Data Center) - Standalone PV-Analyse mit optionaler HA-Integration.

**Version:** 1.0.0-beta.5 | **Status:** Feature-complete Beta (Tests ausstehend)

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

### Release-Checkliste
```bash
# 1. Version in allen Dateien aktualisieren (siehe oben)

# 2. CHANGELOG.md aktualisieren - WICHTIG: BEIDE Dateien!
#    - /CHANGELOG.md (Repository-Root)
#    - /eedc/CHANGELOG.md (Home Assistant Add-on liest diese!)
#    Am einfachsten: Root-Changelog pflegen, dann kopieren:
cp CHANGELOG.md eedc/CHANGELOG.md

# 3. Dokumentationen Version aktualisieren
#    - CLAUDE.md, BENUTZERHANDBUCH.md, ARCHITEKTUR.md, DEVELOPMENT.md

# 4. Frontend Build erstellen
cd eedc/frontend && npm run build

# 5. Git Commit, Tag erstellen und pushen
git add -A
git commit -m "feat: Version X.Y.Z - Beschreibung"
git tag -a vX.Y.Z -m "Version X.Y.Z - Beschreibung"
git push && git push origin vX.Y.Z

# 6. GitHub Release erstellen
gh release create vX.Y.Z \
  --title "vX.Y.Z - Titel" \
  --prerelease \  # nur für Beta/Alpha
  --notes "Release Notes hier..."

# Releases: https://github.com/supernova1963/eedc-homeassistant/releases
```

> **WICHTIG:** Home Assistant Add-ons lesen das Changelog aus `eedc/CHANGELOG.md`,
> nicht aus dem Repository-Root! Bei Releases immer beide Dateien synchron halten.

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
│   │   ├── cockpit.py             # Dashboard-Aggregation (jahres_rendite_prozent)
│   │   ├── aussichten.py          # Prognosen: Kurzfristig, Langfristig, Trend, Finanzen
│   │   ├── import_export.py       # CSV Import (flag_modified!)
│   │   ├── monatsdaten.py         # CRUD + Berechnungen
│   │   └── investitionen.py       # Parent-Child, ROI (Jahres-Rendite p.a.)
│   ├── core/config.py             # APP_VERSION
│   └── services/
│       ├── wetter_service.py      # Open-Meteo + PVGIS TMY
│       ├── prognose_service.py    # Prognose-Berechnungen
│       └── mqtt_client.py         # HA Export
│
└── frontend/src/
    ├── pages/
    │   ├── Dashboard.tsx          # Cockpit-Übersicht
    │   ├── Auswertung.tsx         # 6 Analyse-Tabs
    │   ├── Aussichten.tsx         # 4 Prognose-Tabs
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

// Wärmepumpe
{ "stromverbrauch_kwh": 450, "heizenergie_kwh": 1800, "warmwasser_kwh": 200 }

// Balkonkraftwerk (mit optionalem Speicher)
{ "pv_erzeugung_kwh": 65.0, "eigenverbrauch_kwh": 60.0, "speicher_ladung_kwh": 15, "speicher_entladung_kwh": 14 }

// Wallbox
{ "ladung_kwh": 180 }
```

### Wärmepumpe: Effizienz-Parameter (Investition.parameter)
```json
// Modus A: Gesamt-JAZ (Standard, einfacher)
{ "effizienz_modus": "gesamt_jaz", "jaz": 3.5, "heizwaermebedarf_kwh": 12000, "warmwasserbedarf_kwh": 3000 }

// Modus B: Getrennte COPs (präziser)
{ "effizienz_modus": "getrennte_cops", "cop_heizung": 3.9, "cop_warmwasser": 3.0, "heizwaermebedarf_kwh": 12000, "warmwasserbedarf_kwh": 3000 }
```

## API Endpoints (häufig verwendet)

```
GET  /api/cockpit/uebersicht/{anlage_id}?jahr=2025   # Dashboard-Daten
GET  /api/cockpit/pv-strings/{anlage_id}?jahr=2025   # SOLL-IST Vergleich
POST /api/import/csv/{anlage_id}                     # CSV Import
GET  /api/import/template/{anlage_id}                # CSV Template-Info
GET  /api/wetter/monat/{anlage_id}/{jahr}/{monat}    # Wetter Auto-Fill
GET  /api/monatsdaten/aggregiert/{anlage_id}         # Aggregierte Monatsdaten

# Aussichten (Prognosen)
GET  /api/aussichten/kurzfristig/{anlage_id}         # 7-Tage Wetterprognose
GET  /api/aussichten/langfristig/{anlage_id}         # 12-Monats-Prognose (PVGIS)
GET  /api/aussichten/trend/{anlage_id}               # Trend-Analyse + Degradation
GET  /api/aussichten/finanzen/{anlage_id}            # Finanz-Prognose + Amortisation
```

## ROI-Metriken (WICHTIG: Unterschiedliche Bedeutungen!)

| Metrik | Wo | Formel | Bedeutung |
|--------|-----|--------|-----------|
| **Jahres-Rendite** | Cockpit, Auswertung/Investitionen | `Jahres-Ertrag / Investition × 100` | Rendite pro Jahr (p.a.) |
| **Amortisations-Fortschritt** | Aussichten/Finanzen | `Kum. Erträge / Investition × 100` | Wie viel % bereits abbezahlt |

### Mehrkosten-Ansatz für Investitionen
Bei der ROI-Berechnung werden **Mehrkosten** gegenüber Alternativen berücksichtigt:
- **PV-System**: Volle Kosten (keine Alternative)
- **Wärmepumpe**: Kosten minus Gasheizung (`alternativ_kosten_euro` Parameter)
- **E-Auto**: Kosten minus Verbrenner (`alternativ_kosten_euro` Parameter)

## Bekannte Fallstricke

| Problem | Lösung |
|---------|--------|
| JSON-Änderungen werden nicht gespeichert | `flag_modified(obj, "field_name")` aufrufen |
| 0-Werte verschwinden | `is not None` statt `if val` |
| SOLL-IST zeigt falsches Jahr | `jahr` Parameter explizit übergeben |
| Legacy pv_erzeugung_kwh wird verwendet | InvestitionMonatsdaten abfragen |
| ROI-Werte unterschiedlich | Cockpit = Jahres-%, Aussichten = Kumuliert-% |

## Offene Features

- [ ] PDF-Export
- [ ] KI-Insights

## Letzte Änderungen (v1.0.0-beta.5)

**Aussichten (Prognosen) - Neues Modul mit 4 Tabs**
1. **Kurzfristig**: 7-Tage Wetterprognose (Open-Meteo)
2. **Langfristig**: 12-Monats PVGIS-Prognose mit Performance-Ratio
3. **Trend**: Jahresvergleich, saisonale Muster, Degradationsberechnung
4. **Finanzen**: Amortisations-Fortschritt mit Mehrkosten-Ansatz

**Mehrkosten-Ansatz für ROI**
- WP: Kosten minus Gasheizung (`alternativ_kosten_euro`)
- E-Auto: Kosten minus Verbrenner (`alternativ_kosten_euro`)
- PV-System: Volle Kosten

**ROI-Metriken klarer benannt**
- Cockpit/Auswertung: `jahres_rendite_prozent`
- Aussichten/Finanzen: `amortisations_fortschritt_prozent`

Siehe [CHANGELOG.md](CHANGELOG.md) für vollständige Versionshistorie.
