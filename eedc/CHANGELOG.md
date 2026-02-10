# Changelog

## [0.9.8] - 2026-02-10

### Hinzugefügt
- **Wetter-API für automatische Globalstrahlung/Sonnenstunden**
  - Open-Meteo Archive API für historische Wetterdaten (kostenlos, ohne API-Key)
  - PVGIS TMY (Typical Meteorological Year) als Fallback für aktuelle/zukünftige Monate
  - Automatische Umrechnung: MJ/m² → kWh/m², Sekunden → Stunden
  - Backend: `services/wetter_service.py` mit `fetch_open_meteo_archive()`, `fetch_pvgis_tmy_monat()`
  - Neue Endpoints: `GET /api/wetter/monat/{anlage_id}/{jahr}/{monat}`, `GET /api/wetter/monat/koordinaten/{lat}/{lon}/{jahr}/{monat}`
  - Frontend: Auto-Fill Button in MonatsdatenForm für Wetterdaten

- **HA-Import Wizard für automatisierte Monatsdaten-Erfassung**
  - 4-Schritt-Wizard: Investitionen → Sensoren zuordnen → YAML → Anleitung
  - **HA-Sensor-Auswahl mit intelligenten Vorschlägen**
    - Abruf aller `total_increasing` Sensoren aus Home Assistant
    - Keyword-basierte Vorschläge pro Feld (z.B. "battery", "charge" für Speicher-Ladung)
    - Suchbare Dropdowns mit Sensor-Details (Einheit, Friendly Name)
    - Persistente Speicherung der Sensor-Zuordnungen in Investitions-Parametern
    - Generiertes YAML verwendet echte Sensor-IDs statt Platzhalter
  - **Erweiterte Mapping-Optionen (EVCC-Kompatibilität)**
    - Mapping-Typen: Sensor, Berechnen, Nicht erfassen, Nur manuell
    - EVCC-Berechnungen: Solar% → Ladung PV/Netz (Template-Sensoren)
    - Optionale Felder können übersprungen werden
    - Manuelle Felder (externe Ladung/Kosten) werden gekennzeichnet
    - Erweiterte Sensor-Filter: Auch Counter und Prozent-Sensoren
  - YAML-Generator erstellt komplette Home Assistant Konfiguration:
    - `template` Sensoren für berechnete Felder (EVCC Solar%)
    - `utility_meter` für monatliche Aggregation
    - `rest_command` für Daten-Import zu EEDC
    - `automation` für monatliches Auslösen
  - Sensor-Feld-Mapping pro Investitionstyp (PV-Module, E-Auto, Wärmepumpe, etc.)
  - Backend: `services/ha_yaml_generator.py`, `api/routes/ha_import.py`
  - Frontend: `pages/HAImportSettings.tsx` mit Sensor-Auswahl und YAML-Anzeige
  - Neuer Tab "HA-Import" unter Einstellungen

- **Automatische Wetterdaten bei CSV-Import**
  - Globalstrahlung und Sonnenstunden werden automatisch abgerufen wenn leer
  - Nutzt Anlage-Koordinaten für Open-Meteo/PVGIS-Abfrage
  - Neuer Parameter `auto_wetter` (default: true) im Import-Endpoint

- **Demo-Daten korrigiert und erweitert**
  - Wallbox: `ladung_pv_kwh` entfernt (gehört zu E-Auto)
  - Balkonkraftwerk: `erzeugung_kwh` → `pv_erzeugung_kwh` korrigiert
  - Mini-BHKW (Sonstiges): Extra-Felder entfernt
  - Sonderkosten hinzugefügt für Wärmepumpe, Speicher, E-Auto
  - Globalstrahlung und Sonnenstunden zu Monatsdaten hinzugefügt

### Neue Dateien
- `backend/services/wetter_service.py` - Open-Meteo + PVGIS TMY Client
- `backend/api/routes/wetter.py` - Wetter-API Endpoints
- `backend/api/routes/ha_import.py` - HA Import Endpoints
- `backend/services/ha_yaml_generator.py` - YAML Generator für HA
- `frontend/src/api/wetter.ts` - Wetter API Client
- `frontend/src/api/haImport.ts` - HA Import API Client
- `frontend/src/pages/HAImportSettings.tsx` - HA Import Wizard Seite

### Geändert
- `backend/main.py` - Neue Router registriert: `/api/wetter`, `/api/ha-import`
- `frontend/src/components/forms/MonatsdatenForm.tsx` - Wetter Auto-Fill Button
- `frontend/src/components/layout/SubTabs.tsx` - Neuer Tab "HA-Import"
- `frontend/src/App.tsx` - Route für HAImportSettings registriert
- `backend/api/routes/import_export.py` - Demo-Daten Korrekturen

---

## [0.9.7] - 2026-02-09

### Hinzugefügt
- **Große Daten-Bereinigung: InvestitionMonatsdaten als primäre Quelle**
  - `Monatsdaten` = NUR Anlagen-Energiebilanz (Einspeisung, Netzbezug)
  - `InvestitionMonatsdaten` = ALLE Komponenten-Details
- **Backend-Änderungen**
  - `get_cockpit_uebersicht`: Speicher jetzt aus InvestitionMonatsdaten
  - `get_nachhaltigkeit`: Zeitreihe aus InvestitionMonatsdaten
  - `get_komponenten_zeitreihe`: Erweiterte Felder für alle Komponenten
  - `get_speicher_dashboard`: Arbitrage-Auswertung hinzugefügt
- **Neue Auswertungsfelder**
  - Speicher: Arbitrage (Netzladung), Ladepreis, Arbitrage-Gewinn
  - E-Auto: V2H-Entladung, Ladequellen (PV/Netz/Extern), Externe Kosten
  - Wärmepumpe: Heizung vs. Warmwasser getrennt
  - Balkonkraftwerk: Speicher-Ladung/Entladung
  - Alle: Sonderkosten aggregiert
- **Frontend-Erweiterungen**
  - KomponentenTab (Auswertungen): Arbitrage, V2H, Ladequellen, gestapelte Charts
  - SpeicherDashboard (Cockpit): Arbitrage-Sektion mit KPIs und gestapeltem Chart
  - Monatsdaten: Migrations-Warnung bei Legacy-Daten
  - MonatsdatenForm: Auto-Migration von Legacy-Speicherdaten
- **Demo-Daten erweitert**
  - PV-Module mit saisonaler Verteilung pro String (Süd/Ost/West)
  - Speicher mit Arbitrage-Daten (ab 2025)
  - Wallbox mit Ladedaten

### Migration
- Warnung wenn Legacy-Daten (Monatsdaten.batterie_*) vorhanden
- Beim Bearbeiten werden Legacy-Werte automatisch ins Formular übernommen
- Speichern migriert die Daten zu InvestitionMonatsdaten

---

## [0.9.6] - 2026-02-08

### Hinzugefügt
- **Cockpit-Struktur verbessert**
  - Neuer Tab "PV-Anlage" mit detaillierter PV-System-Übersicht
    - Wechselrichter mit zugeordneten PV-Modulen und DC-Speichern
    - kWp-Gesamtleistung pro Wechselrichter
    - Spezifischer Ertrag (kWh/kWp) pro String
    - String-Vergleich nach Ausrichtung (Süd, Ost, West)
  - Tab "Übersicht" zeigt jetzt ALLE Komponenten aggregiert
    - PV-Erzeugung mit Klick-Navigation zu PV-Anlage
    - Wärmepumpe, Speicher, E-Auto, Wallbox, Balkonkraftwerk
    - Komponenten-Kacheln mit Schnellstatus
- **Tooltips für alle Cockpit-KPIs**
  - Alle Dashboards: formel, berechnung, ergebnis per Hover sichtbar
  - SpeicherDashboard: Vollzyklen, Effizienz, Durchsatz, Ersparnis
  - WaermepumpeDashboard: COP, Wärme, Strom, Ersparnis
  - EAutoDashboard: km, Verbrauch, PV-Anteil, Ersparnis
  - BalkonkraftwerkDashboard: Erzeugung, Eigenverbrauch, Ersparnis, CO₂
  - WallboxDashboard: Heimladung, PV-Anteil, Ersparnis, Ladevorgänge
  - SonstigesDashboard: Erzeuger/Verbraucher/Speicher-spezifische KPIs

### Geändert
- Navigation: PV-Anlage als eigenständiger Cockpit-Tab (vorher in Auswertungen)

---

## [0.9.5] - 2026-02-08

### Hinzugefügt
- **PV-System ROI-Aggregation** - Realistische ROI-Berechnung auf Systemebene
  - Wechselrichter + PV-Module + DC-Speicher als "PV-System" aggregiert
  - ROI auf Systemebene statt pro Einzelkomponente (realistischer!)
  - Aufklappbare Komponenten-Zeilen im Frontend (Chevron-Icon)
  - Einsparung proportional nach kWp auf Module verteilt
  - Backend: Zwei-Pass-Gruppierung in `get_roi_dashboard()`
  - Neuer Typ `pv-system` mit `komponenten[]` Array
- **Konfigurationswarnungen im ROI-Dashboard**
  - Warnsymbol (⚠) bei PV-Modulen ohne Wechselrichter-Zuordnung
  - Warnsymbol bei Wechselrichtern ohne zugeordnete PV-Module
  - Zusammenfassende Warnbox mit Handlungsempfehlungen
- **ROI-Tabelle mit Tooltips** - Formeln und Berechnungen per Hover sichtbar

### Behoben
- Jahr-Filter für Investitionen ROI-Dashboard funktionsfähig
- Unterjährigkeits-Problem bei "Alle Jahre" durch Jahresmittelung gelöst
- PV_Erzeugung_kWh Spalte in CSV-Template für Balkonkraftwerk+PV-Module
- **Investitions-Monatsdaten werden jetzt korrekt gespeichert** (kritisch!)
  - MonatsdatenCreate/Update Schemas um `investitionen_daten` Feld erweitert
  - Neue Helper-Funktion `_save_investitionen_monatsdaten()` in monatsdaten.py
  - Behebt: Wärmepumpe, Speicher, E-Auto Dashboards zeigten leere Daten

---

## [0.9.4] - 2026-02-07

### Behoben
- Jahr-Filter für ROI-Dashboard
- Unterjährigkeits-Korrektur bei Jahresvergleich
- PV_Erzeugung_kWh in CSV-Template

---

## [0.9.3] - 2026-02-06

### Hinzugefügt
- **HA Sensor Export** - Berechnete KPIs an Home Assistant exportieren
  - REST API: `/api/ha/export/sensors/{anlage_id}` für HA rest platform
  - MQTT Discovery: Native HA-Entitäten via MQTT Auto-Discovery
  - YAML-Generator: `/api/ha/export/yaml/{anlage_id}` für configuration.yaml
  - Frontend: HAExportSettings.tsx mit MQTT-Config, Test, Publish
- **Auswertungen Tabs neu strukturiert**
  - Übersicht = Jahresvergleich (Monats-Charts, Δ%-Indikatoren, Jahrestabelle)
  - PV-Anlage = Kombinierte Übersicht + PV-Details
  - Investitionen = ROI-Dashboard, Amortisationskurve, Kosten nach Kategorie
- **Sensor-Definitionen zentralisiert** in `ha_sensors_export.py`
- **MQTT-Konfiguration** in Addon config.yaml
- **SubTabs für Einstellungen** - Bessere Navigation

---

## [0.9.2] - 2026-02-05

### Hinzugefügt
- **Balkonkraftwerk Dashboard** - Erzeugung, Eigenverbrauch, Einspeisung, opt. Speicher
- **Sonstiges Dashboard** - Flexible Kategorie (Erzeuger/Verbraucher/Speicher)
- **Sonderkosten-Felder** - Für alle Investitionstypen (Reparatur, Wartung)
- **Demo-Daten erweitert** - Balkonkraftwerk (800Wp + Speicher) + Mini-BHKW

### Behoben
- Navigation korrigiert: SubTabs statt veralteter Sidebar
- Feldnamen-Mappings: Frontend/Backend Konsistenz

---

## [0.9.1] - 2026-02-05

### Hinzugefügt
- Zentrale Versionskonfiguration
- Dynamische Formulare (V2H/Arbitrage bedingt)
- PV-Module mit Anzahl/Wp
- Monatsdaten-Spalten konfigurierbar

### Behoben
- 0-Wert Import
- Berechnete Felder

---

## [0.4.0] - 2026-02-04

### Hinzugefügt
- **PVGIS Integration** - EU PVGIS API (v5.2) für PV-Ertragsprognosen
  - Prognose-Abruf pro PV-Modul mit individueller Ausrichtung/Neigung
  - Aggregierte Jahres- und Monatsprognosen
  - Optimum-Berechnung für maximalen Ertrag
  - Speichern/Laden/Aktivieren von Prognosen
- **PV-Module als Investitionen** - Modulare PV-Anlagen-Struktur
  - Jedes PV-Modul kann eigene Ausrichtung, Neigung und Leistung haben
  - Unterstützung für Multi-Dach-Anlagen (z.B. Süd + Ost + West)
  - Erweiterte Demo-Anlage mit 3 PV-Modulen (20 kWp gesamt)
- **Prognose vs. IST Vergleich** - Neue Auswertungsseite
  - Monatlicher Vergleich PVGIS-Prognose mit tatsächlicher Erzeugung
  - Abweichungs-Analyse mit Bewertung
  - Hochrechnung auf Jahresbasis
- **PVGIS Einstellungen** - Neue Settings-Seite
  - Übersicht aller PV-Module mit PVGIS-Parametern
  - Prognose-Vorschau mit Monatswerten
  - Optimum-Anzeige für maximalen Ertrag

### Geändert
- `Investition` Model erweitert um `leistung_kwp`, `ausrichtung`, `neigung_grad`
- `Anlage.ausrichtung` und `Anlage.neigung_grad` als DEPRECATED markiert (nun bei PV-Modulen)
- Demo-Daten enthalten nun 3 PV-Module statt einer pauschalen Anlagen-Leistung

---

## [0.3.0] - 2026-02-03

### Hinzugefügt
- **Home Assistant Ingress Integration** - Nahtlose Sidebar-Integration
- HashRouter für HA-Kompatibilität
- Relative API-Pfade
- CSV Auto-Delimiter Erkennung

---

## [0.2.0] - 2026-02-03

### Hinzugefügt
- **ROI-Dashboard** - Wirtschaftlichkeitsanalyse aller Investitionen
  - Amortisationsberechnung
  - KPI-Cards mit Formeln
  - Amortisations-Chart
  - Einsparungen nach Typ (Pie-Chart)
  - Detailtabelle
- **System-Stats API** - Health-Check und Datenbank-Statistiken
- **Settings-UI** - Echte DB-Stats, HA-Status-Anzeige

---

## [0.1.0] - 2026-02-03

### Hinzugefügt
- MVP Release
- Anlagen-Verwaltung (CRUD)
- Strompreis-Verwaltung mit Zeiträumen
- Investitionen-Verwaltung (alle Typen)
- Monatsdaten-Erfassung (Formular + CSV-Import)
- Basis-Kennzahlen (Autarkie, Eigenverbrauch, spez. Ertrag, CO2)
- Dashboard mit KPIs und Trend-Charts
- Auswertung mit 4 Tabs (Übersicht, PV, Finanzen, CO2)
- Dark Mode Support
- Home Assistant Add-on Konfiguration
- HA Backup (SQLite in /data Volume)
