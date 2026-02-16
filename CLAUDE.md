# CLAUDE.md - Entwickler-Kontext für Claude Code

> **Hinweis:** Dies ist der Kontext für KI-gestützte Entwicklung. Für Benutzer-Dokumentation siehe [docs/BENUTZERHANDBUCH.md](docs/BENUTZERHANDBUCH.md), für Architektur siehe [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md).

## Projektübersicht

**eedc** (Energie Effizienz Data Center) - Standalone PV-Analyse mit optionaler HA-Integration.

**Version:** 1.0.0-beta.12 | **Status:** Feature-complete Beta (Tests ausstehend)

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
│   │   ├── import_export/         # Import/Export Package (CSV, JSON, Demo)
│   │   ├── monatsdaten.py         # CRUD + Berechnungen
│   │   └── investitionen.py       # Parent-Child, ROI (Jahres-Rendite p.a.)
│   ├── core/config.py             # APP_VERSION
│   └── services/
│       ├── wetter_service.py      # Multi-Provider Wetterdaten
│       ├── brightsky_service.py   # DWD-Daten via Bright Sky API
│       ├── solar_forecast_service.py  # Open-Meteo Solar GTI
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
// Modus A: Gesamt-JAZ (gemessen vor Ort - genauester Wert wenn verfügbar)
{ "effizienz_modus": "gesamt_jaz", "jaz": 3.5, "heizwaermebedarf_kwh": 12000, "warmwasserbedarf_kwh": 3000 }

// Modus B: SCOP (EU-Energielabel - realistischer als Hersteller-COP) - NEU in beta.10
{ "effizienz_modus": "scop", "scop_heizung": 4.5, "scop_warmwasser": 3.2, "vorlauftemperatur": "35", "heizwaermebedarf_kwh": 12000, "warmwasserbedarf_kwh": 3000 }

// Modus C: Getrennte COPs (präzise Betriebspunkte)
{ "effizienz_modus": "getrennte_cops", "cop_heizung": 3.9, "cop_warmwasser": 3.0, "heizwaermebedarf_kwh": 12000, "warmwasserbedarf_kwh": 3000 }
```

**Effizienz-Modi im Vergleich:**
- **JAZ (Jahresarbeitszahl):** Tatsächlich gemessener Wert am Standort - der genaueste Wert
- **SCOP (Seasonal COP):** EU-genormter saisonaler COP vom Energielabel - realistischer als momentane COPs
- **Getrennte COPs:** Separate Werte für Heizung und Warmwasser - präziser bei unterschiedlichen Vorlauftemperaturen

### Anlage.versorger_daten (JSON) - NEU in beta.6
```json
{
  "strom": {
    "name": "Stadtwerke München",
    "kundennummer": "12345678",
    "portal_url": "https://kundenportal.swm.de",
    "notizen": "",
    "zaehler": [
      {"bezeichnung": "Einspeisung", "nummer": "1EMH0012345678", "notizen": ""},
      {"bezeichnung": "Bezug", "nummer": "1EMH0087654321", "notizen": ""}
    ]
  },
  "gas": { "name": "...", "kundennummer": "...", "zaehler": [...] },
  "wasser": { "name": "...", "kundennummer": "...", "zaehler": [...] }
}
```

### Investition.parameter: Stammdaten-Felder (NEU in beta.6)
```json
{
  // Bestehende technische Parameter...

  // Gerätedaten
  "stamm_hersteller": "Fronius",
  "stamm_modell": "Symo GEN24 10.0",
  "stamm_seriennummer": "12345678",
  "stamm_garantie_bis": "2032-06-15",
  "stamm_mastr_id": "SEE123456789",  // Nur Wechselrichter
  "stamm_notizen": "",

  // Ansprechpartner
  "ansprechpartner_firma": "Solar Mustermann GmbH",
  "ansprechpartner_name": "Max Mustermann",
  "ansprechpartner_telefon": "+49 123 456789",
  "ansprechpartner_email": "service@solar-mustermann.de",
  "ansprechpartner_ticketsystem": "https://portal.solar-mustermann.de",
  "ansprechpartner_kundennummer": "K-12345",
  "ansprechpartner_vertragsnummer": "V-2024-001",

  // Wartungsvertrag
  "wartung_vertragsnummer": "WV-2024-001",
  "wartung_anbieter": "Solar Mustermann GmbH",
  "wartung_gueltig_bis": "2026-12-31",
  "wartung_kuendigungsfrist": "3 Monate",
  "wartung_leistungsumfang": "Jährliche Inspektion, Reinigung"
}
```

**Vererbung:** PV-Module und DC-Speicher (mit `parent_investition_id`) erben Ansprechpartner/Wartung vom Wechselrichter. Leere Felder zeigen "(erbt von Wechselrichter)".

## API Endpoints (häufig verwendet)

```
GET  /api/cockpit/uebersicht/{anlage_id}?jahr=2025   # Dashboard-Daten
GET  /api/cockpit/pv-strings/{anlage_id}?jahr=2025   # SOLL-IST Vergleich
POST /api/import/csv/{anlage_id}                     # CSV Import
GET  /api/import/template/{anlage_id}                # CSV Template-Info
GET  /api/import/export/{anlage_id}/full             # Vollständiger JSON-Export
GET  /api/wetter/monat/{anlage_id}/{jahr}/{monat}    # Wetter Auto-Fill
GET  /api/wetter/provider/{anlage_id}                # Verfügbare Wetter-Provider
GET  /api/wetter/vergleich/{anlage_id}/{jahr}/{monat} # Provider-Vergleich
GET  /api/solar-prognose/{anlage_id}?tage=7          # GTI-basierte PV-Prognose
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

## Wetterdienst-Integration

### Multi-Provider Architektur
EEDC unterstützt mehrere Wetterdatenquellen mit automatischer Provider-Auswahl:

| Provider | Beschreibung | Region | Daten |
|----------|-------------|--------|-------|
| **auto** (Standard) | Automatische Auswahl | - | - |
| **brightsky** | DWD-Daten via Bright Sky REST API | Deutschland | Historisch + MOSMIX |
| **open-meteo** | Open-Meteo Archive API | Weltweit | Historisch + Forecast |
| **open-meteo-solar** | Open-Meteo Solar mit GTI | Weltweit | Forecast + GTI |

### Fallback-Kette
1. Gewählter Provider → 2. Alternative → 3. PVGIS TMY → 4. Statische Defaults

### Anlage.wetter_provider
Neues Feld zur Provider-Auswahl pro Anlage. Migration wird automatisch bei Startup ausgeführt.

### API-Endpoints
```
GET /api/wetter/monat/{anlage_id}/{jahr}/{monat}?provider=auto
GET /api/wetter/provider/{anlage_id}           # Verfügbare Provider
GET /api/wetter/vergleich/{anlage_id}/{jahr}/{monat}  # Provider-Vergleich
GET /api/solar-prognose/{anlage_id}?tage=7&pro_string=false  # GTI-Prognose
```

### GTI (Global Tilted Irradiance)
Open-Meteo Solar berechnet GTI für geneigte PV-Module basierend auf:
- Neigung und Ausrichtung aus PV-Modul-Konfiguration
- Temperaturkorrektur (Wirkungsgradminderung bei Hitze)
- Systemverluste aus PVGIS-Einstellungen

## Offene Features

- [x] PDF-Export ✓ (beta.12)
- [ ] KI-Insights

## Letzte Änderungen (v1.0.0-beta.12)

**PDF-Export: Vollständige Anlagen-Dokumentation**
- Neuer PDF-Export-Button auf der Anlagen-Seite (Stammdaten)
- Gesamtzeitraum als Standard (alle Jahre seit Installation)
- Vollständige Stammdaten: Hersteller, Modell, Seriennummer, Garantie
- Ansprechpartner & Wartungsverträge pro Komponente
- Versorger-Daten mit Zählernummern und Zählpunkten

**PDF-Layout & Design**
- Kopfzeile (ab Seite 2): Anlagenname | Titel | eedc-Logo
- Fußzeile: Erstellungsdatum | GitHub-Repository | "Seite X von Y"
- Farbschema: Darkblue-Hintergrund, Orangered-Überschriften
- Wiederholende Tabellenköpfe bei Seitenumbrüchen

**Erweiterte Demo-Daten**
- Alle Investitionen mit vollständigen Stammdaten
- Ansprechpartner und Wartungsverträge
- Versorger-Daten mit Zählern

Siehe [CHANGELOG.md](CHANGELOG.md) für vollständige Versionshistorie.
