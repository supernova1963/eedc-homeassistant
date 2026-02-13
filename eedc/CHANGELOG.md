# Changelog

Alle wichtigen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/),
und dieses Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

---

## [1.0.0-beta.7] - 2026-02-13

### Bugfixes

- **Kritisch: Datenbank-Migration für beta.6 Spalten fehlte**
  - Problem: Nach Update auf beta.6 fehlte die Migration für `mastr_id` und `versorger_daten`
  - Fehler: `no such column: anlagen.mastr_id` - Anlage wurde nicht mehr angezeigt
  - Fix: `run_migrations()` in `database.py` ergänzt um fehlende Spalten
  - Bestehende Daten bleiben erhalten, Spalten werden automatisch hinzugefügt

---

## [1.0.0-beta.6] - 2026-02-13

### Hinzugefügt

- **Erweiterte Stammdaten für Anlagen**
  - MaStR-ID (Marktstammdatenregister-ID) mit direktem Link zum MaStR
  - Versorger & Zähler als JSON-Struktur (Strom, Gas, Wasser)
  - Beliebig viele Zähler pro Versorger mit Bezeichnung und Nummer
  - Neue Komponente `VersorgerSection` für dynamische Verwaltung

- **Erweiterte Stammdaten für Investitionen**
  - **Gerätedaten:** Hersteller, Modell, Seriennummer, Garantie, MaStR-ID (nur WR)
  - **Ansprechpartner:** Firma, Name, Telefon, E-Mail, Ticketsystem, Kundennummer, Vertragsnummer
  - **Wartungsvertrag:** Vertragsnummer, Anbieter, Gültig bis, Kündigungsfrist, Leistungsumfang
  - Typ-spezifische Zusatzfelder (Garantie-Zyklen für Speicher, Kennzeichen für E-Auto, etc.)
  - Neue Komponente `InvestitionStammdatenSection` mit klappbaren Sektionen

- **Vererbungslogik für PV-System**
  - PV-Module und DC-Speicher erben Ansprechpartner/Wartung vom Wechselrichter
  - Hinweis "(erbt von Wechselrichter)" bei leeren Feldern
  - Nur bei Children mit `parent_investition_id` aktiv

### Geändert

- **Anlage-Datenmodell erweitert**
  - `mastr_id: Optional[str]` - MaStR-ID der Anlage
  - `versorger_daten: Optional[dict]` - JSON mit Versorgern und Zählern

- **Investition.parameter JSON erweitert**
  - Neue Felder: `stamm_*`, `ansprechpartner_*`, `wartung_*`
  - Alle Stammdaten im bestehenden `parameter` JSON gespeichert

### Dokumentation

- CHANGELOG.md: Stammdaten-Erweiterung dokumentiert
- README.md: Version aktualisiert
- CLAUDE.md: Datenstrukturen für Versorger/Investition-Stammdaten
- ARCHITEKTUR.md: JSON-Strukturen dokumentiert
- BENUTZERHANDBUCH.md: Neue Formularsektionen erklärt
- DEVELOPMENT.md: DB-Migration dokumentiert

---

## [1.0.0-beta.5] - 2026-02-13

### Hinzugefügt

- **Aussichten: 4 neue Prognose-Tabs**
  - **Kurzfristig (7 Tage)**: Wetterbasierte Ertragsschätzung mit Open-Meteo
  - **Langfristig (12 Monate)**: PVGIS-basierte Jahresprognose mit Performance-Ratio
  - **Trend-Analyse**: Jahresvergleich, saisonale Muster, Degradationsberechnung
  - **Finanzen**: Amortisations-Fortschritt, Komponenten-Beiträge, Mehrkosten-Ansatz

- **Mehrkosten-Ansatz für ROI-Berechnung**
  - Wärmepumpe: Kosten minus Gasheizung (`alternativ_kosten_euro` Parameter)
  - E-Auto: Kosten minus Verbrenner (`alternativ_kosten_euro` Parameter)
  - PV-System: Volle Kosten (keine Alternative)
  - Alternativkosten-Einsparungen als zusätzliche Erträge (WP vs. Gas, E-Auto vs. Benzin)

### Geändert

- **ROI-Metriken klarer benannt**
  - Cockpit/Auswertung: `jahres_rendite_prozent` (Jahres-Ertrag / Investition)
  - Aussichten/Finanzen: `amortisations_fortschritt_prozent` (Kum. Erträge / Investition)
  - Unterschiedliche Metriken für unterschiedliche Zwecke klar dokumentiert

- **API-Endpoints für Aussichten**
  - `GET /api/aussichten/kurzfristig/{anlage_id}` - 7-Tage Wetterprognose
  - `GET /api/aussichten/langfristig/{anlage_id}` - 12-Monats-Prognose
  - `GET /api/aussichten/trend/{anlage_id}` - Trend-Analyse
  - `GET /api/aussichten/finanzen/{anlage_id}` - Finanz-Prognose

### Dokumentation

- README.md: Aussichten-Feature dokumentiert
- CLAUDE.md: ROI-Metriken erklärt, Aussichten-Endpoints hinzugefügt
- ARCHITEKTUR.md: Aussichten-Modul dokumentiert
- BENUTZERHANDBUCH.md: Aussichten-Tabs erklärt
- DEVELOPMENT.md: Aussichten-API dokumentiert

---

## [1.0.0-beta.4] - 2026-02-12

### Hinzugefügt

- **Monatsdaten-Seite: Aggregierte Darstellung mit allen Komponenten**
  - Neuer API-Endpoint `/api/monatsdaten/aggregiert/{anlage_id}`
  - Zählerwerte (Einspeisung, Netzbezug) aus Monatsdaten
  - Komponenten-Daten (PV, Speicher, WP, E-Auto, Wallbox) aus InvestitionMonatsdaten aggregiert
  - Berechnete Felder (Direktverbrauch, Eigenverbrauch, Autarkie, EV-Quote)
  - Gruppierte Spaltenauswahl mit Ein-/Ausblenden pro Gruppe
  - Farbcodierung: Zählerwerte (blau), Komponenten (amber), Berechnungen (grün)

- **Balkonkraftwerk: Eigenverbrauch-Erfassung**
  - Neues Feld `eigenverbrauch_kwh` in InvestitionMonatsdaten
  - CSV-Template erweitert: `{BKW}_Eigenverbrauch_kWh`
  - Einspeisung wird automatisch berechnet (Erzeugung - Eigenverbrauch)
  - Dashboard zeigt Einspeisung als "unvergütet"

### Geändert

- **Demo-Daten bereinigt (Architektur-Konsistenz)**
  - `Monatsdaten.pv_erzeugung_kwh` entfernt (war Legacy)
  - `batterie_ladung_kwh`, `batterie_entladung_kwh` entfernt (Legacy)
  - Berechnete Felder entfernt (werden dynamisch berechnet)
  - **Prinzip:** Monatsdaten = NUR Zählerwerte; InvestitionMonatsdaten = ALLE Komponenten

- **BKW-Dashboard: Feldnamen-Kompatibilität**
  - Akzeptiert sowohl `pv_erzeugung_kwh` als auch `erzeugung_kwh`

### Dokumentation

- BENUTZERHANDBUCH.md: Aggregierte Monatsdaten und BKW-Eigenverbrauch dokumentiert
- ARCHITEKTUR.md: Datenstrukturen korrigiert (WP: stromverbrauch_kwh, BKW: pv_erzeugung_kwh)
- Alle Dokumente auf Version 1.0.0-beta.4 aktualisiert

---

## [1.0.0-beta.3] - 2026-02-12

### Bugfixes

- **Jahr-Filter in Auswertungen → Komponenten funktioniert jetzt**
  - Problem: Jahr-Auswahl hatte keine Auswirkung auf angezeigte Daten
  - Fix: Jahr-Parameter wird jetzt durch alle Schichten durchgereicht (Backend API → Frontend API → KomponentenTab)
  - Betroffen: `cockpit.py`, `cockpit.ts`, `KomponentenTab.tsx`, `Auswertung.tsx`

---

## [1.0.0-beta.2] - 2026-02-12

### Hinzugefügt

- **Wärmepumpe: Erweiterte Effizienz-Konfiguration**
  - Modus-Auswahl zwischen JAZ und getrennten COPs für Heizung/Warmwasser
  - JAZ (Jahresarbeitszahl): Ein Wert für alles - einfacher (Standard)
  - Getrennte COPs: Separate Werte für Heizung (~3,9) und Warmwasser (~3,0) - präziser
  - Automatische Migration: Bestehende Anlagen nutzen JAZ-Modus

### Geändert

- **ROI-Berechnung Wärmepumpe** berücksichtigt jetzt den gewählten Effizienz-Modus
- **Demo-Daten** zeigen Wärmepumpe mit getrennten COPs als Beispiel

### Dokumentation

- CLAUDE.md: WP-Datenmodell-Beispiele ergänzt
- ARCHITEKTUR.md: WP-Parameter aktualisiert
- BENUTZERHANDBUCH.md: WP-Konfiguration und CSV-Spalten dokumentiert

---

## [1.0.0-beta.1] - 2026-02-11

### Kritische Bugfixes

Diese Version behebt kritische Bugs im SOLL-IST Vergleich und der Datenpersistenz.

#### SOLL-IST Vergleich zeigte falsche Werte

**Problem:** Der SOLL-IST Vergleich im Cockpit → PV-Anlage zeigte falsche IST-Werte (z.B. 0.3 MWh statt ~14 MWh).

**Ursachen und Fixes:**

1. **Legacy-Feld entfernt** - `Monatsdaten.pv_erzeugung_kwh` wurde noch verwendet statt `InvestitionMonatsdaten.verbrauch_daten.pv_erzeugung_kwh`
   - Betroffen: `cockpit.py`, `investitionen.py`, `ha_export.py`, `main.py`

2. **SQLAlchemy flag_modified()** - JSON-Feld-Updates wurden nicht persistiert
   - SQLAlchemy erkennt Änderungen an JSON-Feldern nicht automatisch
   - Fix: `flag_modified(obj, "verbrauch_daten")` nach Änderung
   - Betroffen: `import_export.py`

3. **Jahr-Parameter fehlte** - `PVStringVergleich` erhielt kein `jahr` und verwendete 2026 statt 2025
   - Fix: `latestYear` aus Monatsdaten berechnen und übergeben
   - Betroffen: `PVAnlageDashboard.tsx`

### Geändert

- **CSV-Template bereinigt**
  - Entfernt: `PV_Erzeugung_kWh` (Legacy), `Globalstrahlung_kWh_m2`, `Sonnenstunden` (auto-generiert)
  - Import akzeptiert Legacy-Spalten weiterhin als Fallback

- **run.sh Version korrigiert** - War hardcoded auf 0.9.3

### Dokumentation

- **Vollständige Dokumentation erstellt**
  - `README.md` komplett überarbeitet für v1.0.0
  - `docs/BENUTZERHANDBUCH.md` - Umfassendes Benutzerhandbuch
  - `docs/ARCHITEKTUR.md` - Technische Architektur-Dokumentation
  - `CHANGELOG.md` - Vollständige Versionshistorie
  - `docs/DEVELOPMENT.md` - Entwickler-Setup aktualisiert

### Datenarchitektur-Klarstellung

```
Monatsdaten (Tabelle):
  - einspeisung_kwh      ✓ Primär (Zählerwert)
  - netzbezug_kwh        ✓ Primär (Zählerwert)
  - pv_erzeugung_kwh     ✗ LEGACY - nicht mehr verwenden!
  - batterie_*           ✗ LEGACY - nicht mehr verwenden!

InvestitionMonatsdaten (Tabelle):
  - verbrauch_daten (JSON):
    - pv_erzeugung_kwh   ✓ Primär für PV-Module
    - ladung_kwh         ✓ Primär für Speicher
    - entladung_kwh      ✓ Primär für Speicher
```

---

## [0.9.9] - 2026-02-10

### Architektur-Änderung: Standalone-Fokus

**EEDC ist jetzt primär Standalone ohne HA-Abhängigkeit für die Datenerfassung.**

### Entfernt

- Komplexer HA-Import Wizard (YAML-Generator, Template-Sensoren, Utility Meter, Automationen)
- HA-Sensor-Auswahl und Mapping-Logik
- EVCC-Berechnungen (spezielle Template-Sensoren)
- REST Command / Automation für automatischen Import

### Beibehalten

- CSV-Import (volle Funktionalität)
- Manuelles Formular für Monatsdaten
- Wetter-API (Open-Meteo/PVGIS - HA-unabhängig!)
- HA-Export via MQTT (optional)

### Begründung

Die komplexe HA-Integration erwies sich als zu kompliziert:
- EVCC liefert andere Datenstrukturen als erwartet
- Utility Meter können nicht programmatisch Geräten zugeordnet werden
- Jede Haus-Automatisierung ist anders → Kein "One Size Fits All"

---

## [0.9.8] - 2026-02-09

### Hinzugefügt

- **Wetter-API für automatische Globalstrahlung/Sonnenstunden**
  - `GET /api/wetter/monat/{anlage_id}/{jahr}/{monat}`
  - `GET /api/wetter/monat/koordinaten/{lat}/{lon}/{jahr}/{monat}`
  - Datenquellen: Open-Meteo Archive API (historisch), PVGIS TMY (Fallback)

- **Auto-Fill Button im Monatsdaten-Formular**
  - Globalstrahlung und Sonnenstunden werden automatisch gefüllt
  - Zeigt Datenquelle an (Open-Meteo oder PVGIS TMY)

---

## [0.9.7] - 2026-02-09

### Große Daten-Bereinigung: InvestitionMonatsdaten als primäre Quelle

Diese Version löst ein fundamentales Architekturproblem: Die inkonsistente Mischung von `Monatsdaten` und `InvestitionMonatsdaten` in den Cockpit-Endpoints.

#### Neue Architektur

- **Monatsdaten** = NUR Anlagen-Energiebilanz (Einspeisung, Netzbezug, PV-Erzeugung)
- **InvestitionMonatsdaten** = ALLE Komponenten-Details (Speicher, E-Auto, WP, PV-Module, etc.)

#### Backend-Änderungen

- `get_cockpit_uebersicht`: Speicher-Daten jetzt aus InvestitionMonatsdaten
- `get_nachhaltigkeit`: Zeitreihe aus InvestitionMonatsdaten
- `get_komponenten_zeitreihe`: Erweiterte Felder für alle Komponenten
- `get_speicher_dashboard`: Arbitrage-Auswertung hinzugefügt

#### Neue Auswertungsfelder

| Komponente | Neue Felder |
|------------|-------------|
| **Speicher** | Arbitrage (Netzladung), Ladepreis, Arbitrage-Gewinn |
| **E-Auto** | V2H-Entladung, Ladequellen (PV/Netz/Extern), Externe Kosten |
| **Wärmepumpe** | Heizung vs. Warmwasser getrennt |
| **Balkonkraftwerk** | Speicher-Ladung/Entladung |
| **Alle** | Sonderkosten aggregiert |

#### Frontend-Erweiterungen

- **KomponentenTab (Auswertungen)**:
  - Speicher: Arbitrage-Badge + KPI + gestapeltes Chart
  - E-Auto: V2H-Badge, Ladequellen-Breakdown, gestapeltes Chart
  - Wärmepumpe: Heizung/Warmwasser getrennt (KPIs + gestapeltes Chart)
  - Balkonkraftwerk: "mit Speicher"-Badge + Speicher-KPIs

- **SpeicherDashboard (Cockpit)**:
  - Arbitrage-Sektion mit KPIs (Netzladung, Ø Ladepreis, Gewinn)
  - Gestapeltes Chart zeigt PV-Ladung vs. Netz-Ladung

#### Migration für bestehende Installationen

- Warnung in Monatsdaten-Ansicht wenn Legacy-Daten (Monatsdaten.batterie_*) vorhanden
- Auto-Migration beim Bearbeiten: Legacy-Werte werden automatisch in das Formular übernommen
- Benutzer muss Monatsdaten einmal öffnen und speichern um Daten zu migrieren

#### Demo-Daten erweitert

- PV-Module mit saisonaler Verteilung pro String (Süd/Ost/West)
- Speicher mit Arbitrage-Daten (ab 2025)
- Wallbox mit Ladedaten

---

## [0.9.6] - 2026-02-08

### Cockpit-Struktur verbessert

- Neuer Tab "PV-Anlage" mit detaillierter PV-System-Übersicht
  - Wechselrichter mit zugeordneten PV-Modulen und DC-Speichern
  - kWp-Gesamtleistung pro Wechselrichter
  - Spezifischer Ertrag (kWh/kWp) pro String
  - String-Vergleich nach Ausrichtung (Süd, Ost, West)
- Tab "Übersicht" zeigt jetzt ALLE Komponenten aggregiert
- Komponenten-Kacheln mit Schnellstatus und Klick-Navigation

### KPI-Tooltips

- Alle Cockpit-Dashboards zeigen Formel, Berechnung, Ergebnis per Hover
- SpeicherDashboard, WaermepumpeDashboard, EAutoDashboard
- BalkonkraftwerkDashboard, WallboxDashboard, SonstigesDashboard

---

## [0.9.5] - 2026-02-07

### PV-System ROI-Aggregation

- Wechselrichter + PV-Module + DC-Speicher als "PV-System" aggregiert
- ROI auf Systemebene statt pro Einzelkomponente
- Aufklappbare Komponenten-Zeilen im Frontend
- Einsparung proportional nach kWp auf Module verteilt

### Konfigurationswarnungen

- Warnsymbol bei PV-Modulen ohne Wechselrichter-Zuordnung
- Warnsymbol bei Wechselrichtern ohne zugeordnete PV-Module

### Bugfixes

- Jahr-Filter für Investitionen ROI-Dashboard funktionsfähig
- Investitions-Monatsdaten werden jetzt korrekt gespeichert

---

## [0.9.4] - 2026-02-06

- Jahr-Filter für ROI-Dashboard
- Unterjährigkeits-Korrektur bei Jahresvergleich
- PV_Erzeugung_kWh in CSV-Template

---

## [0.9.3] - 2026-02-05

### HA Sensor Export

- REST API: `/api/ha/export/sensors/{anlage_id}` für HA rest platform
- MQTT Discovery: Native HA-Entitäten via MQTT Auto-Discovery
- YAML-Generator: `/api/ha/export/yaml/{anlage_id}` für configuration.yaml
- Frontend: HAExportSettings.tsx mit MQTT-Config, Test, Publish

### Auswertungen Tabs

- Übersicht = Jahresvergleich (Monats-Charts, Δ%-Indikatoren, Jahrestabelle)
- PV-Anlage = Kombinierte Übersicht + PV-Details
- Investitionen = ROI-Dashboard, Amortisationskurve, Kosten nach Kategorie

---

## [0.9.2] - 2026-02-04

- Balkonkraftwerk Dashboard (Erzeugung, Eigenverbrauch, opt. Speicher)
- Sonstiges Dashboard (Flexible Kategorie: Erzeuger/Verbraucher/Speicher)
- Sonderkosten-Felder für alle Investitionstypen
- Demo-Daten erweitert (Balkonkraftwerk 800Wp + Speicher, Mini-BHKW)

---

## [0.9.1] - 2026-02-03

- Zentrale Versionskonfiguration
- Dynamische Formulare (V2H/Arbitrage bedingt)
- PV-Module mit Anzahl/Wp
- Monatsdaten-Spalten konfigurierbar
- Bugfixes: 0-Wert Import, berechnete Felder

---

## [0.9.0] - 2026-02-01

### Initiales Beta-Release

- FastAPI Backend mit SQLAlchemy 2.0 + SQLite
- React 18 Frontend mit Tailwind CSS + Recharts
- Home Assistant Add-on Konfiguration
- 7-Schritt Setup-Wizard
- Anlagen-, Strompreis-, Investitions-Verwaltung
- Monatsdaten mit CSV-Import/Export
- Cockpit mit aggregierten KPIs
- Auswertungen (Jahresvergleich, ROI, CO₂)
