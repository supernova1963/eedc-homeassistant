# Changelog

Alle wichtigen Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/),
und dieses Projekt folgt [Semantic Versioning](https://semver.org/lang/de/).

---

## [2.1.0] - 2026-02-21

### Hinzugefügt

- **Community als eigenständiger Hauptmenüpunkt**
  - Community jetzt auf Augenhöhe mit Cockpit, Auswertungen und Aussichten
  - Eigener Navigationsbereich statt Tab in Auswertungen
  - 6-Tab-Struktur: Übersicht, PV-Ertrag, Komponenten, Regional, Trends, Statistiken

- **Übersicht Tab**
  - **Gamification:** 7 Achievements (Autarkiemeister, Effizienzwunder, Solarprofi, Grüner Fahrer, Wärmekönig, Ertragswunder, Speichermeister)
  - **Fortschrittsanzeige** für nicht erreichte Achievements
  - **Radar-Chart:** Eigene Performance vs. Community auf 6 Achsen
  - **Rang-Badges:** Top 10%, Top 25%, Top 50%
  - **KPI-Tooltips:** Erklärungen für Community-Kennzahlen (Spez. Ertrag, JAZ, etc.)

- **PV-Ertrag Tab**
  - **Perzentil-Anzeige:** "Du bist besser als X% der Community"
  - **Abweichungs-KPIs:** vs. Community und vs. Region
  - **Monatlicher Ertrag Chart:** Mit echten monatlichen Community-Durchschnitten (statt Jahresdurchschnitt/12)
  - **Jahresübersicht:** Tabelle mit Abweichungen pro Jahr
  - **Verteilungs-Histogramm:** Eigene Position in der Community-Verteilung

- **Komponenten Tab**
  - **Speicher Deep-Dive:** Wirkungsgrad, Zyklen, PV-Anteil mit Community-Vergleich
  - **Wärmepumpe Deep-Dive:** JAZ-Vergleich nach Region, mit Hinweis bei weniger als 3 Anlagen
  - **E-Auto Deep-Dive:** PV-Anteil, Ladequellen-Chart (PV/Netz/Extern)
  - **Wallbox Deep-Dive:** Ladung und PV-Anteil
  - **Balkonkraftwerk Deep-Dive:** Spezifischer Ertrag und Eigenverbrauchsquote
  - **Zeitraum-Hinweis:** Betrachtungszeitraum wird konsistent angezeigt

- **Regional Tab**
  - **Regionale Position:** Rang im Bundesland
  - **Vergleichs-Chart:** Du / Region / Community als Balken
  - **Regionale Einordnung:** Anlagen-Details im Kontext

- **Trends Tab**
  - **Ertragsverlauf:** Area-Chart über alle Monate
  - **Saisonale Performance:** Frühling/Sommer/Herbst/Winter mit Icons
  - **Jahresvergleich:** Letztes vs. Vorletztes Jahr mit Veränderung
  - **Typischer Monatsverlauf:** Durchschnitt pro Monat über alle Jahre
  - **Community-Entwicklung:** Speicher-/WP-/E-Auto-Quoten über Zeit
  - **Degradations-Analyse:** Ertrag nach Anlagenalter

- **Statistiken Tab**
  - **Community-Zusammenfassung:** Übersicht über alle Teilnehmer
  - **Position in Community:** Rang und Perzentil
  - **Ausstattungs-Übersicht:** Komponenten-Verteilung

- **Backend-Erweiterungen**
  - **Proxy-Endpoints:** Alle Community-Server-Endpoints durchgereicht
  - `/api/community/statistics/global` - Globale Statistiken
  - `/api/community/statistics/monthly-averages` - Monatliche Durchschnitte
  - `/api/community/statistics/regional` - Regionale Statistiken
  - `/api/community/statistics/distributions/{metric}` - Verteilungsdaten
  - `/api/community/statistics/rankings/{category}` - Top-Listen
  - `/api/community/components/*` - Komponenten-Statistiken
  - `/api/community/trends/*` - Trend-Daten und Degradation

### Behoben

- **FastAPI Route-Ordering:** `/api/community/trends/degradation` wurde fälschlich von `/api/community/trends/{period}` gematcht
- **TypeScript-Typen:** Server-Feldnamen (`durchschnitt_zyklen` statt `avg_zyklen`) korrekt gemappt
- **Chronologische Sortierung:** Monatsdaten in PV-Ertrag und Trends Charts werden jetzt korrekt sortiert (älteste links, neueste rechts)
- **Monatliche Durchschnitte:** Community-Vergleich verwendet echte monatliche Werte statt Jahresdurchschnitt/12

### Geändert

- **Auswertungen:** Community-Tab entfernt (jetzt eigenständiger Menüpunkt)
- **Navigation:** Hauptmenü erweitert um Community-Eintrag
- **Tooltips:** Aussichten-Tabs und Community-Seite haben jetzt erklärende Tooltips

---

## [2.0.3] - 2026-02-20

### Hinzugefügt

- **Community-Vergleich Tab in Auswertungen**
  - Neuer "Community" Tab erscheint nach Teilen der Anlagendaten
  - Zeitraum-Auswahl: Letzter Monat, Letzte 12 Monate, Letztes vollständiges Jahr, Seit Installation
  - **PV-Benchmark:** Spezifischer Ertrag im Vergleich zu Community und Region
  - **Rang-Anzeige:** Position gesamt und regional
  - **Komponenten-Benchmarks:** Speicher (Zyklen, Wirkungsgrad), Wärmepumpe (JAZ), E-Auto (PV-Anteil)
  - **Monatlicher Ertrag Chart:** Visualisierung der letzten 12 Monate
  - **Zugangslogik:** Tab nur sichtbar wenn `community_hash` gesetzt (Daten geteilt)

- **Backend: Community-Benchmark Proxy**
  - Neuer Endpoint `GET /api/community/benchmark/{anlage_id}`
  - Proxy zum Community-Server (`/api/benchmark/anlage/{anlage_hash}`)
  - Gibt 403 zurück wenn Anlage nicht geteilt (Fairness-Prinzip: Erst teilen, dann vergleichen)
  - Unterstützt Zeitraum-Filter: `letzter_monat`, `letzte_12_monate`, `letztes_vollstaendiges_jahr`, `jahr`, `seit_installation`

### Geändert

- **Community-Seite (energy.raunet.eu) vereinfacht**
  - Entfernt: Zeitraum-Auswahl (immer Jahresertrag)
  - Entfernt: Komponenten-Benchmarks (jetzt im Add-on)
  - Hinzugefügt: Hinweis-Box mit Verweis auf EEDC Add-on für Details
  - Titel geändert: "Dein Anlagen-Benchmark" (statt "Dein PV-Anlagen Benchmark")

- **Frontend-Types erweitert**
  - `community_hash` Feld zum `Anlage` Interface hinzugefügt
  - Erweiterte TypeScript-Interfaces für Benchmark-Daten

---

## [2.0.2] - 2026-02-19

### Hinzugefügt

- **CSV-Import: Automatische Legacy-Migration**
  - Alte CSV-Dateien mit `PV_Erzeugung_kWh`, `Batterie_Ladung_kWh`, `Batterie_Entladung_kWh` werden automatisch migriert
  - PV-Erzeugung wird proportional nach kWp auf alle PV-Module verteilt
  - Batterie-Werte werden proportional nach Kapazität auf alle Speicher verteilt
  - Warnung wird angezeigt, wenn Legacy-Werte migriert wurden
  - Behebt Import-Fehler bei älteren Backup-Dateien

### Behoben

- **Auswertung/Energie KPIs zeigten falsche Werte**
  - Problem: PV-Erzeugung zeigte 0.3 MWh statt tatsächlicher Werte
  - Ursache: `useMonatsdatenStats` verwendete Legacy-Feld `Monatsdaten.pv_erzeugung_kwh`
  - Fix: Neue Hooks `useAggregierteDaten` und `useAggregierteStats` nutzen aggregierte Daten aus `InvestitionMonatsdaten`
  - Betroffen: Alle KPIs in Auswertung → Energie Tab

- **PrognoseVsIst nutzte Legacy-Felder**
  - Fix: Verwendet jetzt `/api/monatsdaten/aggregiert` Endpoint
  - Korrekte PV-Erzeugungswerte für SOLL-IST Vergleich

- **Swagger UI "Try it out" funktioniert jetzt im HA Ingress**
  - Problem: 404-Fehler beim Testen von API-Endpoints in Swagger UI
  - Ursache: Swagger verwendete falsche Base-URL im Ingress-Proxy
  - Fix: Dynamische Base-URL-Berechnung aus aktueller Browser-URL

---

## [2.0.1] - 2026-02-19

### Hinzugefügt

- **Selektiver Feld-Import im HA-Statistik Wizard**
  - **Import-Modi:** Schnellauswahl zwischen "Alles importieren", "Nur Basis" (Einspeisung/Netzbezug), "Nur Komponenten"
  - **Granulare Feld-Checkboxen:** Jedes Feld kann einzeln an-/abgewählt werden
  - Modus wechselt automatisch zu "Manuell" bei individueller Anpassung
  - Ermöglicht z.B. manuell korrigierte Einspeisung beizubehalten, aber PV-Werte zu importieren

- **Komponenten-Vergleich im HA-Statistik Import Wizard**
  - Zeigt nun alle InvestitionMonatsdaten (PV, Speicher, E-Auto, etc.) im Vergleich
  - Vorhanden vs. HA-Statistik mit Differenz-Berechnung
  - Gelbe Hervorhebung bei Abweichungen ≥1
  - Konflikt-Erkennung berücksichtigt jetzt auch Komponenten-Werte

- **Erweiterte Sensor-Mapping Felder**
  - **E-Auto:** Verbrauch gesamt (kWh), Ladung extern (kWh)
  - **Wallbox:** Ladevorgänge (Anzahl)
  - **Balkonkraftwerk:** Neuer Wizard-Step mit PV-Erzeugung, Eigenverbrauch, Speicher-Ladung/-Entladung

### Behoben

- **Sensor-Filter erlaubt Zähler ohne Einheit** - Sensoren wie `evcc_charging_sessions` mit `state_class: measurement` aber ohne `unit_of_measurement` werden jetzt korrekt angezeigt

---

## [2.0.0] - 2026-02-18

### ⚠️ BREAKING CHANGE - Neuinstallation erforderlich!

Diese Version benötigt **Lesezugriff auf `/config`** für die HA-Statistik-Funktion.
Das Volume-Mapping wurde geändert - eine einfache Aktualisierung reicht nicht!

**Vor dem Update:**
1. **JSON-Export** aller Anlagen erstellen (Anlagen-Seite → Download-Icon ⬇️ bei jeder Anlage)
2. Export-Datei sichern!

**Update durchführen:**
1. Add-on **stoppen**
2. Add-on **deinstallieren** (⚠️ Daten werden gelöscht!)
3. Repository aktualisieren (Add-ons → ⋮ → Nach Updates suchen)
4. Add-on **neu installieren**
5. Add-on **starten**
6. **JSON-Import** durchführen

### Hinzugefügt

- **HA-Statistik-Abfrage** - Direkte Abfrage der Home Assistant Langzeitstatistiken
  - Neuer Service `ha_statistics_service.py` für SQLite-Zugriff auf `/config/home-assistant_v2.db`
  - API-Endpoints unter `/api/ha-statistics/`:
    - `GET /status` - Prüft ob HA-Datenbank verfügbar ist
    - `GET /monatswerte/{anlage_id}/{jahr}/{monat}` - Monatswerte für einen Monat
    - `GET /verfuegbare-monate/{anlage_id}` - Alle Monate mit Daten
    - `GET /alle-monatswerte/{anlage_id}` - Bulk-Abfrage aller historischen Monatswerte
    - `GET /monatsanfang/{anlage_id}/{jahr}/{monat}` - Zählerstände für MQTT-Startwerte
  - Nutzt die sensor_mapping Zuordnungen um HA-Sensoren auf EEDC-Felder zu mappen
  - Ermöglicht rückwirkende Befüllung aller Monatsdaten seit Installationsdatum

- **HA-Statistik Import mit Überschreib-Schutz**
  - `GET /api/ha-statistics/import-vorschau/{anlage_id}` - Vorschau mit Konflikt-Erkennung
  - `POST /api/ha-statistics/import/{anlage_id}` - Import mit intelligenter Logik:
    - Neue Monate werden importiert
    - Leere Monatsdaten werden befüllt
    - Vorhandene Daten werden **nicht** überschrieben (außer explizit gewünscht)
    - Konflikte werden erkannt und angezeigt

- **Frontend: HA-Statistik Import UI**
  - Neue Seite: Einstellungen → Home Assistant → Statistik-Import
  - Bulk-Import aller historischen Monatswerte
  - Vorschau mit farbcodierter Konflikt-Erkennung
  - Option zum Überschreiben vorhandener Daten

- **Monatsabschluss-Wizard: HA-Werte laden**
  - Neuer Button "Werte aus HA-Statistik laden"
  - Lädt Monatswerte direkt aus der HA-Langzeitstatistik
  - Nur sichtbar wenn Sensor-Mapping konfiguriert ist

- **Sensor-Mapping: Startwerte aus HA-DB**
  - Nach Speichern: Option "Aus HA-Statistik laden (empfohlen)"
  - Verwendet gespeicherte Zählerstände vom Monatsanfang
  - Fallback: Aktuelle Sensorwerte verwenden

### Geändert

- **Volume-Mapping erweitert**: `config:ro` für Lesezugriff auf HA-Datenbank

### Behoben

- **Sensor-Mapping UI** - Importierte Sensoren werden jetzt angezeigt auch wenn HA nicht verfügbar
  - Zeigt sensor_id mit Hinweis "(nicht verfügbar)" wenn Sensor nicht in lokaler Liste

- **PVGIS MultipleResultsFound** - 500-Fehler wenn mehrere aktive PVGIS-Prognosen existierten
  - Query mit `.order_by().limit(1)` abgesichert in pvgis.py, cockpit.py, aussichten.py, solar_prognose.py

- **SensorMappingWizard Startwerte laden** - "Cannot convert undefined or null to object" Fehler
  - Interface-Feldnamen korrigiert (`startwerte` statt `werte`) und Null-Safety hinzugefügt

- **HAStatistikImport "NaN Monate importieren"** - Frontend-Interface an Backend-Feldnamen angepasst
  - `anzahl_monate`, `anzahl_importieren`, `anzahl_konflikte`, `anzahl_ueberspringen` korrekt gemappt

- **HAStatistikImport: Individuelle Monatsauswahl** - Checkbox pro Monat statt globaler Überschreiben-Option
  - Benutzer können gezielt einzelne Monate zum Import auswählen

- **Monatsdaten: "Aus HA laden" Button** - Direktes Laden einzelner Monate aus HA-Statistik
  - Modal zur Auswahl von Monat/Jahr aus verfügbaren HA-Statistik-Monaten
  - Bei existierenden Monaten: Vergleichs-Modal mit Diff-Anzeige vor dem Überschreiben
  - Farbcodierte Hervorhebung signifikanter Unterschiede (>10%)

- **HA-Statistik Investitions-Bezeichnungen** - Zeigt nun "BYD HVS 12.8 (speicher)" statt "()"
  - Backend lädt Investitions-Metadaten aus DB für korrektes Label

- **JSON-Import sensor_mapping** - Investitions-Mappings werden beim Import zurückgesetzt
  - IDs ändern sich beim Import, daher muss Sensor-Mapping neu konfiguriert werden
  - Warnung wird angezeigt mit Hinweis auf Neukonfiguration

- **Sensor-Mapping Wizard: Löschen-Button** - Mapping kann nun über Button im Header gelöscht werden
  - Bestätigungsdialog vor dem Löschen

- **Komponenten-Vergleich in "Aus HA laden"** - Zeigt nun Vorhanden vs. HA-Statistik Tabelle für alle Investitionen
  - Differenz-Berechnung wie bei Basis-Werten (Einspeisung, Netzbezug)
  - Zeigt auch Investitionen die nur in Bestandsdaten existieren (ohne HA-Mapping)

---

## [1.1.0-beta.8] - 2026-02-18

(Übersprungen - direkt zu 2.0.0 wegen Breaking Change)

---

## [1.1.0-beta.7] - 2026-02-18

### Behoben

- **JSON-Export Version 1.1 Bug** - Export-Version war fälschlicherweise auf "1.0" hardcoded
  - In beta.5 wurde das Pydantic-Model auf 1.1 aktualisiert, aber der Code der das Export-Objekt erstellt übergab explizit "1.0"
  - Dadurch wurde beim Import die Warnung "sensor_mapping nicht enthalten" angezeigt, obwohl es vorhanden war
  - Export gibt jetzt korrekt `export_version: "1.1"` aus

---

## [1.1.0-beta.6] - 2026-02-18

### Geändert

- **Cockpit PV-Anlage komplett überarbeitet** - zeigt jetzt Gesamtlaufzeit statt einzelne Jahre
  - Neuer API-Endpoint `/api/cockpit/pv-strings-gesamtlaufzeit` für aggregierte Daten
  - **SOLL vs IST pro Jahr**: Balkendiagramm zeigt für jedes Jahr SOLL und IST pro String
  - **Saisonaler Vergleich**: Jan-Dez Durchschnitt vs PVGIS-Prognose als Linien/Flächen-Chart
  - **Gesamtlaufzeit-Tabelle**: Performance-Statistik pro String über alle Jahre
  - Keine Jahr-Auswahl mehr nötig - konsistent mit Cockpit-Philosophie "Gesamtlaufzeit"

### Behoben

- **Dashboard Race Condition** - "Fehler beim Laden der Daten" erschien manchmal nach F5
  - `loading` State wird jetzt mit `true` initialisiert
  - Cockpit-Tabs sind wieder statisch (dynamische Tabs verursachten Race Conditions)

---

## [1.1.0-beta.5] - 2026-02-18

### Hinzugefügt

- **JSON-Export erweitert für vollständiges Backup/Restore** (Export-Version 1.1)
  - `sensor_mapping` - HA Sensor-Zuordnungen werden jetzt exportiert/importiert
  - `durchschnittstemperatur` - Wetterdaten in Monatsdaten
  - `sonderkosten_euro` / `sonderkosten_beschreibung` - Manuelle Sonderkosten
  - Rückwärtskompatibel: Export-Version 1.0 wird weiterhin importiert

### Geändert

- **Monatsdaten-Formular verbessert:**
  - PV-Erzeugung ist jetzt readonly wenn PV-Module mit Werten vorhanden sind (Summe wird automatisch berechnet)
  - Sonnenstunden akzeptiert jetzt Dezimalwerte (step=0.1 statt step=1) - behebt Validierungsfehler bei Auto-Fill

### Hinweis

Beim Import von Anlagen mit Sensor-Mapping:
- Die Zuordnungen werden übernommen, aber `mqtt_setup_complete` wird auf `false` gesetzt
- Nach dem Import muss das Sensor-Mapping erneut gespeichert werden, um die MQTT-Entities zu erstellen
- Grund: Die Investitions-IDs ändern sich beim Import

---

## [1.1.0-beta.4] - 2026-02-18

### Behoben

- **MQTT Entity-IDs** sind jetzt eindeutig durch `object_id` im Discovery-Payload
  - Entity-IDs enthalten jetzt den Key: `number.eedc_winterborn_mwd_inv1_ladung_kwh_start`
  - Vorher wurde die Entity-ID aus dem Namen generiert, was zu `_2` Suffixen führte
  - Friendly Names bleiben lesbar mit Investitionsnamen

### Hinweis

Nach dem Update: MQTT Discovery Topics löschen (`homeassistant/number/eedc_*` und
`homeassistant/sensor/eedc_*`), dann Sensor-Mapping erneut speichern.

---

## [1.1.0-beta.3] - 2026-02-18

### Behoben

- **MQTT Entity-Namen** enthalten jetzt den Investitionsnamen
  - Vorher: Doppelte Entities wenn Speicher und Wallbox beide `ladung_kwh` haben
  - Jetzt: "EEDC BYD HVS 12.8 Ladung Monatsanfang" statt "EEDC Speicher Ladung Monatsanfang"
  - Eindeutige Namen für jede Investition, keine `_2` Suffixe mehr in HA

### Hinweis

Nach dem Update: EEDC-Gerät in Home Assistant löschen und Sensor-Mapping erneut speichern,
damit die neuen Entity-Namen erstellt werden.

---

## [1.1.0-beta.2] - 2026-02-17

### Behoben

- **Datenbank-Migration** für neue Monatsdaten-Felder hinzugefügt
  - `durchschnittstemperatur` (FLOAT)
  - `sonderkosten_euro` (FLOAT)
  - `sonderkosten_beschreibung` (VARCHAR)
  - `notizen` (VARCHAR)
  - Behebt SQLite-Fehler "no such column: monatsdaten.durchschnittstemperatur" nach Update

---

## [1.1.0-beta.1] - 2026-02-17

### Hinzugefügt

- **Sensor-Mapping-Wizard** - Zuordnung von Home Assistant Sensoren zu EEDC-Feldern
  - Intuitive Wizard-Oberfläche mit dynamischen Steps
  - Unterstützte Schätzungsstrategien:
    - **sensor** - Direkter HA-Sensor
    - **kwp_verteilung** - Anteilig nach kWp (für PV-Module ohne eigenen Sensor)
    - **cop_berechnung** - COP × Stromverbrauch (für Wärmepumpen)
    - **ev_quote** - Nach Eigenverbrauchsquote (für E-Auto)
    - **manuell** - Eingabe im Monatsabschluss-Wizard
  - Speicherung in neuem `Anlage.sensor_mapping` JSON-Feld
  - Navigation: Einstellungen → Home Assistant → Sensor-Zuordnung

- **MQTT Auto-Discovery für Monatswerte**
  - EEDC erstellt automatisch MQTT-Entities in Home Assistant:
    - `number.eedc_{anlage}_mwd_{feld}_start` - Zählerstand vom Monatsanfang
    - `sensor.eedc_{anlage}_mwd_{feld}_monat` - Berechneter Monatswert via `value_template`
  - Keine YAML-Bearbeitung oder HA-Neustart nötig
  - Retained Messages für Persistenz

- **Monatsabschluss-Wizard** - Geführte monatliche Dateneingabe
  - **Intelligente Vorschläge** aus verschiedenen Quellen:
    - Vormonat (80% Konfidenz)
    - Vorjahr gleicher Monat (70% Konfidenz)
    - COP-Berechnung für Wärmepumpen (60% Konfidenz)
    - Durchschnitt letzte 12 Monate (50% Konfidenz)
  - **Plausibilitätsprüfungen** mit Warnungen:
    - Negativwerte bei Zählern
    - Große Abweichungen vs. Vorjahr (±50%)
    - Ungewöhnlich niedrige/hohe Werte
  - Dynamische Steps basierend auf Investitionstypen
  - Navigation: Einstellungen → Daten → Monatsabschluss

- **Scheduler für Cron-Jobs**
  - APScheduler-Integration für periodische Tasks
  - Monatswechsel-Snapshot: Am 1. jeden Monats um 00:01
  - Status-Endpoint: `GET /api/scheduler`
  - Manueller Trigger: `POST /api/scheduler/monthly-snapshot`

- **Neue API-Endpoints**
  - `/api/sensor-mapping/{anlage_id}` - CRUD für Sensor-Zuordnung
  - `/api/sensor-mapping/{anlage_id}/available-sensors` - Verfügbare HA-Sensoren
  - `/api/monatsabschluss/{anlage_id}/{jahr}/{monat}` - Status und Vorschläge
  - `/api/monatsabschluss/naechster/{anlage_id}` - Nächster offener Monat
  - `/api/scheduler` - Scheduler-Status

- **Neue Backend-Services**
  - `ha_mqtt_sync.py` - MQTT Synchronisations-Service
  - `scheduler.py` - Cron-Job Management
  - `vorschlag_service.py` - Intelligente Vorschläge

### Geändert

- **mqtt_client.py** erweitert um:
  - `publish_number_discovery()` - Erstellt number-Entities
  - `publish_calculated_sensor()` - Erstellt Sensoren mit value_template
  - `update_month_start_value()` - Aktualisiert Monatsanfang-Werte
  - `publish_monatsdaten()` - Publiziert finale Monatsdaten

- **Navigation** erweitert:
  - "Sensor-Zuordnung" unter Einstellungen → Home Assistant
  - "Monatsabschluss" unter Einstellungen → Daten

### Technisch

- **Neue Dependency:** `apscheduler>=3.10.0` für Cron-Jobs
- **DB-Migration:** Neue Spalte `sensor_mapping` (JSON) in `anlagen` Tabelle
- Scheduler startet automatisch mit dem Backend

---

## [1.0.0-beta.13] - 2026-02-17

### Hinzugefügt

- **Logo/Icon Integration**
  - Neues eedc-Logo und Icon durchgängig eingebunden
  - **HA Add-on:** `icon.png` (512x512) und `logo.png` für Add-on Store
  - **Frontend:** Neues Favicon, Icon + "eedc" Text in TopNavigation
  - **Setup-Wizard:** eedc-Icon im Header
  - **PDF-Export:** eedc-Icon in der Kopfzeile (ab Seite 2)
  - **README:** Logo zentriert am Anfang

- **Entwickler-Tools**
  - `scripts/kill-dev.sh`: Beendet alle Entwicklungs-Prozesse und gibt Ports frei
  - Prüft Ports 8099 (Backend), 5173-5176 (Frontend), 3000-3009 (Tests)

### Geändert

- **HA-Integration Bereinigung (Phase 0)**
  - `ha_integration.py`: Von 2037 auf 171 LOC reduziert (-92%)
  - Auto-Discovery komplett entfernt (ineffektiv, ~10% Erkennungsrate)
  - Discovery-UI Komponenten entfernt
  - `ha_sensor_*` Felder auf Anlage als DEPRECATED markiert

- **PDF-Export**
  - HA-Integration Abschnitt wird nur angezeigt wenn Sensoren konfiguriert sind
  - Icon statt Text "eedc" in Kopfzeile

- **Demo-Daten**
  - `ha_sensor_*` Beispielwerte entfernt (waren irreführend)

### Entfernt

- **Backend Services**
  - `ha_yaml_generator.py` (18 LOC Placeholder)
  - `ha_websocket.py` (261 LOC, unzuverlässig)

- **Backend Models**
  - `StringMonatsdaten` (redundant mit `InvestitionMonatsdaten.verbrauch_daten`)

- **Frontend Komponenten**
  - `components/discovery/*` (DeviceCard, DiscoveryDialog, SensorMappingPanel, etc.)
  - `hooks/useDiscovery.ts`
  - `setup-wizard/steps/DiscoveryStep.tsx`
  - `setup-wizard/steps/SensorConfigStep.tsx`

- **API Endpoints (aus ha_integration.py)**
  - `/ha/discover` - Auto-Discovery
  - `/ha/statistics/*` - Long-Term Statistics
  - `/ha/string-monatsdaten/*` - StringMonatsdaten CRUD
  - Diverse Discovery-bezogene Endpoints

---

## [1.0.0-beta.12] - 2026-02-16

### Hinzugefügt

- **PDF-Export: Vollständige Anlagen-Dokumentation**
  - Neuer PDF-Export-Button auf der Anlagen-Seite (orangefarbenes Dokument-Icon)
  - **Gesamtzeitraum als Standard:** Ohne Jahr-Parameter werden alle Jahre exportiert
  - **Vollständige Stammdaten:** Alle Komponenten mit Hersteller, Modell, Seriennummer, Garantie
  - **Ansprechpartner & Wartung:** Service-Kontakte und Wartungsverträge pro Komponente
  - **Versorger-Daten:** Stromversorger, Kundennummern, Zähler mit Zählpunkten
  - **Home Assistant Sensoren:** Konfigurierte Sensor-Mappings

- **PDF-Layout & Design**
  - **Kopfzeile (ab Seite 2):** Anlagenname | "EEDC Anlagenbericht [Zeitraum]" | eedc-Logo
  - **Fußzeile (alle Seiten):** Erstellungsdatum | GitHub-Repository | "Seite X von Y"
  - **Farbschema:** Darkblue-Hintergrund für Kapitel, Orangered für Unterüberschriften
  - **Wiederholende Tabellenköpfe:** Bei Seitenumbrüchen werden Spaltenüberschriften wiederholt

- **PDF-Inhalte**
  - Jahresübersicht mit allen KPIs (Energie, Autarkie, Finanzen, CO2)
  - Drei Diagramme: PV-Erzeugung (Balken + PVGIS-Linie), Energie-Fluss (gestapelt), Autarkie-Verlauf
  - Monatstabellen: Energie, Speicher, Wärmepumpe, E-Mobilität, Finanzen
  - PV-String Vergleich: SOLL (PVGIS) vs. IST mit Abweichung
  - Finanz-Prognose & Amortisations-Fortschritt

- **Erweiterte Demo-Daten**
  - Alle Investitionen mit vollständigen Stammdaten (Hersteller, Seriennummer, Garantie)
  - Ansprechpartner für Wechselrichter, E-Auto, Wärmepumpe
  - Wartungsverträge für Wechselrichter und Wärmepumpe
  - Versorger-Daten mit Zählernummern und Zählpunkten
  - Home Assistant Sensor-Mappings

### Geändert

- **PDF-Button verschoben:** Von Auswertung zu Anlagen-Seite (bei Stammdaten)
- **API-Endpoint `/api/import/pdf/{anlage_id}`:** `jahr`-Parameter ist jetzt optional

---

## [1.0.0-beta.11] - 2026-02-16

### Hinzugefügt

- **Setup-Wizard komplett überarbeitet**
  - Standalone-First: Alle Home Assistant Abhängigkeiten entfernt
  - Neuer 4-Schritte-Flow: Anlage → Strompreise → Komponenten → Zusammenfassung
  - **PVGIS-Integration:** Prognose direkt im Wizard abrufbar
  - **Direkte Navigation:** Nach Abschluss zur Monatsdaten-Erfassung statt Cockpit
  - Komponenten können nach PV-System-Erstellung weiter hinzugefügt werden

- **Erweiterte Komponenten-Felder im Wizard**
  - **Speicher:** Arbitrage-Checkbox (Netzstrom günstig laden, teuer einspeisen)
  - **E-Auto:** V2H-fähig Checkbox (Vehicle-to-Home)
  - **Wallbox:** V2H-fähig Checkbox (Bidirektionales Laden)
  - **Balkonkraftwerk:** Ausrichtung, Neigung, Mit Speicher (z.B. Anker SOLIX)
  - Alle technischen Felder als Pflichtfelder markiert

- **Schnellstart-Buttons für Komponenten**
  - Nach PV-System-Erstellung: Speicher, Wallbox, Wärmepumpe, E-Auto, Balkonkraftwerk
  - Bereits vorhandene Typen werden grün mit ✓ markiert
  - "Investition hinzufügen"-Dropdown für alle Typen weiterhin verfügbar

### Geändert

- **AnlageStep vereinfacht**
  - Entfernt: "Technische Daten (optional)" mit Ausrichtung/Neigung (jetzt in PV-Modulen)
  - Entfernt: "Wechselrichter-Hersteller" mit veraltetem HA-Hinweis
  - Fokus auf Grunddaten: Name, Leistung, Datum, Standort

- **SummaryStep verbessert**
  - PVGIS-Prognose Card mit Button zum Abrufen
  - Zeigt Jahresertrag wenn PVGIS abgerufen
  - "Wie geht es weiter?" Sektion mit Monatsdaten-Hinweis
  - CTA "Weiter zur Datenerfassung" statt "Einrichtung abschließen"

- **CompleteStep aktualisiert**
  - Hauptbutton "Monatsdaten erfassen" → navigiert zu /einstellungen/monatsdaten
  - Sekundärbutton "Zum Cockpit" für alternative Navigation

### Entfernt

- **Home Assistant Integration aus Setup-Wizard**
  - HAConnectionStep entfernt
  - DiscoveryStep entfernt
  - Automatische Sensor-Erkennung entfernt
  - Keine HA-Referenzen mehr in WelcomeStep

---

## [1.0.0-beta.10] - 2026-02-15

### Hinzugefügt

- **Multi-Provider Wetterdienst-Integration**
  - **Bright Sky (DWD):** Hochwertige Wetterdaten für Deutschland via DWD Open Data
  - **Open-Meteo:** Historische und Forecast-Daten weltweit
  - **Open-Meteo Solar:** GTI-basierte Berechnung für geneigte PV-Module
  - Automatische Provider-Auswahl: Bright Sky für DE, Open-Meteo sonst
  - Fallback-Kette bei Nichtverfügbarkeit → PVGIS TMY → Statische Defaults

- **GTI-basierte Solarprognose**
  - Global Tilted Irradiance (GTI) statt horizontaler Globalstrahlung
  - Berücksichtigt Neigung und Ausrichtung der PV-Module
  - Temperaturkorrektur für Wirkungsgradminderung bei Hitze
  - 7-Tage Prognose mit stündlichen/täglichen Werten pro PV-String

- **SCOP-Modus für Wärmepumpe**
  - Neuer dritter Effizienz-Modus neben JAZ und COP
  - EU-Energielabel SCOP-Werte (realistischer als Hersteller-COP)
  - Separate Eingabe für Heiz-SCOP und Warmwasser-SCOP
  - Vorlauftemperatur-Auswahl (35°C/55°C) passend zum EU-Label

- **Kurzfrist-Tab erweitert**
  - Umschalter zwischen Standard-Prognose und GTI-basierter Solarprognose
  - Visualisierung der erwarteten PV-Erträge pro String
  - Integration mit Open-Meteo Solar Forecast API

### Geändert

- **Einstellungen: PVGIS → Solarprognose**
  - Menüpunkt umbenannt von "PVGIS" zu "Solarprognose"
  - Zeigt verfügbare Wetter-Provider und deren Status
  - Kombiniert PVGIS-Langfristprognose mit Wetter-Provider-Info
  - Redirect von `/einstellungen/pvgis` zu `/einstellungen/solarprognose`

- **Demo-Daten aktualisiert**
  - Standort von Wien auf München geändert (für Bright Sky/DWD-Verfügbarkeit)
  - PV-Module mit GTI-Parametern (ausrichtung_grad, neigung_grad)
  - Balkonkraftwerk mit GTI-kompatiblen Parametern

- **API: Wetter-Endpoints erweitert**
  - `GET /api/wetter/provider/{anlage_id}` - Verfügbare Provider mit Status
  - `GET /api/wetter/vergleich/{anlage_id}/{jahr}/{monat}` - Provider-Vergleich
  - `GET /api/solar-prognose/{anlage_id}` - GTI-basierte PV-Prognose

### Bugfixes

- **GTI-Berechnung korrigiert**
  - Problem: Unrealistische Werte (z.B. 8845 kWh/Tag für 20 kWp)
  - Ursache: Fehlerhafte Einheitenumrechnung Wh→kWh
  - Fix: Korrekte Division durch 1000 in allen Berechnungspfaden

- **wetter_provider in Export/Import**
  - Feld wird jetzt korrekt im JSON-Export mitgeliefert
  - Import setzt Provider-Einstellung der Anlage

- **Bewölkungswerte in Kurzfrist-Prognose**
  - Problem: Spalte "Bewölkung" zeigte nur "- %" statt Werte
  - Ursache: Stündliche cloud_cover-Daten wurden nicht aggregiert
  - Fix: Tagesdurchschnitt aus stündlichen Werten berechnet

- **Standort-Info auf Solarprognose-Seite**
  - Problem: "Standort: Unbekannt" obwohl Koordinaten vorhanden
  - Fix: land/in_deutschland Felder zur StandortInfo hinzugefügt

- **SOLL-IST Vergleich bei mehreren PVGIS-Prognosen**
  - Problem: 500-Fehler wenn mehrere Prognosen für eine Anlage existieren
  - Ursache: `scalar_one_or_none()` bei mehreren Ergebnissen
  - Fix: `.limit(1)` um nur die neueste Prognose zu verwenden

---

## [1.0.0-beta.9] - 2026-02-14

### Hinzugefügt

- **Icons im Hauptmenü**
  - Cockpit, Auswertungen und Aussichten zeigen jetzt passende Icons
  - LayoutDashboard für Cockpit, BarChart3 für Auswertungen, TrendingUp für Aussichten

- **JSON-Import-Vorbereitung**
  - Import-Modul refaktoriert für JSON-Import (lokale Variante)

### Geändert

- **Import/Export-Modul refaktoriert**
  - Aufgeteilt von einer großen Datei (2500+ Zeilen) in modulares Package
  - Neue Struktur: `import_export/` mit separaten Dateien für CSV, JSON, Demo-Daten
  - Bessere Wartbarkeit und Testbarkeit

### Bugfixes

- **Garantiedatum wurde nicht gespeichert**
  - Problem: Datumsfelder wie `stamm_garantie_bis` wurden durch `parseFloat()` in Zahlen konvertiert
  - Lösung: Datumsfelder werden jetzt explizit als Strings behandelt
  - Betrifft: `stamm_garantie_bis`, `wartung_gueltig_bis`, `stamm_erstzulassung`, etc.

- **JSON-Export 404 in Home Assistant**
  - Problem: Download-Button verwendete absoluten Pfad `/api/...` statt relativen `./api/...`
  - Im HA Ingress-Modus führte das zu 404-Fehlern
  - Lösung: Verwendung von `importApi.getFullExportUrl()` mit korrektem relativen Pfad

---

## [1.0.0-beta.8] - 2026-02-13

### Hinzugefügt

- **Vollständiger JSON-Export für Support/Backup**
  - Neuer Endpoint `GET /api/import/export/{anlage_id}/full`
  - Exportiert komplette Anlage mit allen verknüpften Daten
  - Hierarchische Struktur: Anlage → Strompreise → Investitionen (mit Children) → Monatsdaten → PVGIS
  - Download-Button in der Anlagen-Übersicht (neben Bearbeiten/Löschen)

- **CSV-Import: Erweiterte Plausibilitätsprüfungen**
  - **Legacy-Spalten-Validierung:**
    - `PV_Erzeugung_kWh`, `Batterie_Ladung_kWh`, `Batterie_Entladung_kWh` sind Legacy
    - Fehler wenn NUR Legacy-Spalte vorhanden UND PV-Module/Speicher als Investitionen existieren
    - Fehler bei Mismatch zwischen Legacy-Wert und Summe der individuellen Komponenten
    - Warnung wenn redundant (gleiche Werte ±0.5 kWh Toleranz)
  - **Negative Werte blockiert:** Alle kWh/km/€-Felder müssen ≥ 0 sein
  - **Plausibilitätswarnungen:** Sonnenstunden > 400h/Monat, Globalstrahlung > 250 kWh/m²

- **Import-Feedback verbessert**
  - Warnungen werden jetzt zusätzlich zu Fehlern angezeigt
  - Unterschiedliche Farben: Grün (Erfolg), Gelb (mit Hinweisen), Rot (mit Fehlern)
  - Hilfetext zu Legacy-Spalten im Import-Bereich

### Geändert

- **ImportResult Schema erweitert** um `warnungen: list[str]`
- **Frontend Import.tsx** zeigt Warnungen in amber/gelber Farbe

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
