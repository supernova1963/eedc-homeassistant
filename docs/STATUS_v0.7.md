# EEDC Projekt Status

**Stand:** 2026-02-05
**Version:** 0.8.0

## Übersicht

EEDC (Energie Effizienz Data Center) ist ein Home Assistant Add-on zur PV-Analyse mit Monatsdaten, Prognosen und Wirtschaftlichkeitsberechnungen.

---

## Aktuell implementierte Features

### Feature: Setup-Wizard (v0.7.0-0.8.0)
**Status:** ✅ Implementiert und verbessert

Geführte Ersteinrichtung für neue Benutzer mit maximalem Automatisierungsgrad.

**v0.8.0 - Wizard Refactoring:**
- **Auto-Start bei leerer Datenbank:** Wizard startet automatisch wenn keine Anlagen vorhanden (unabhängig von LocalStorage)
- **Geocoding-Button:** Automatische Koordinatenermittlung aus PLZ/Ort via OpenStreetMap
- **Vereinfachter Discovery-Schritt:** Alle erkannten Geräte werden automatisch als Investitionen angelegt
- **Neuer Investitionen-Schritt:** Alle Investitionen auf einer Seite, gruppiert nach Typ
  - Bearbeiten aller Investitionen (Kaufdatum, Kaufpreis, technische Details)
  - Parent-Zuordnung (PV-Module → Wechselrichter, E-Auto → Wallbox)
  - Manuelles Hinzufügen/Löschen von Investitionen
- **Neuer Sensor-Config-Schritt:** Sensor-Zuordnung direkt im Wizard
  - Ersetzt die bisherige config.yaml `ha_sensors` Konfiguration
  - Vorschläge aus Discovery mit Umschaltung auf "Alle Sensoren"
  - Wird in Anlage-Tabelle gespeichert
- **PV-Module-Schritt entfernt:** PV-Module werden jetzt als Investitionen erfasst

**Wizard-Schritte (neu v0.8.0):**
1. **Willkommen** - Einführung und Übersicht
2. **Anlage erstellen** - Name, Leistung, Standort, Koordinaten (+ Geocoding-Button)
3. **HA-Verbindung prüfen** - Automatische Prüfung, überspringbar
4. **Strompreise konfigurieren** - Mit deutschen Standardwerten (30ct/8.2ct)
5. **Auto-Discovery** - Geräte erkennen & automatisch als Investitionen anlegen
6. **Investitionen vervollständigen** - Alle auf einer Seite bearbeiten/hinzufügen/löschen
7. **Sensor-Konfiguration** - HA-Sensoren für Monatsdaten-Import zuordnen
8. **Zusammenfassung** - Übersicht und Abschluss

**Features:**
- Automatischer Start bei erstem Besuch (keine Anlagen vorhanden)
- Fortschrittsanzeige (Desktop: Schritte, Mobile: Balken)
- Strompreis-Defaults basierend auf Anlagengröße (EEG-Vergütung)
- **Wechselrichter-Hersteller-Auswahl** für bessere Discovery
- State wird in LocalStorage gespeichert (Fortsetzung möglich)

**Unterstützte Geräte (v0.7.4+):**

*Wechselrichter:*
- SMA, Fronius, Kostal, Huawei/FusionSolar, Growatt, SolaX, Sungrow, GoodWe, Enphase

*Balkonkraftwerke:*
- EcoFlow (PowerStream, Delta Pro)
- Hoymiles (HMS, HMT)
- Anker SOLIX (Solarbank)
- APSystems (QS1, DS3, EZ1)
- Deye Mikrowechselrichter
- OpenDTU/AhoyDTU (Open-Source)

*Wärmepumpen:*
- Viessmann (Vitocal, ViCare)
- Daikin (Altherma)
- Vaillant (aroTHERM)
- Bosch (IDS, Compress)
- Mitsubishi (Ecodan, MELCloud)
- Panasonic (Aquarea, Heishamon)
- Stiebel Eltron (WPL, ISG)
- Nibe (S-Serie)
- Alpha Innotec (Luxtronik)
- Lambda
- iDM (Navigator)
- Toshiba (Estia)
- LG (Therma V)

*E-Autos & Wallboxen:*
- evcc (höchste Priorität)
- Smart #1
- Wallbox (native Integration)

**Dateien:**
- `frontend/src/hooks/useSetupWizard.ts` (State-Management - komplett überarbeitet)
- `frontend/src/components/setup-wizard/` (Wizard-Komponenten)
- `frontend/src/components/setup-wizard/steps/DiscoveryStep.tsx` (vereinfacht)
- `frontend/src/components/setup-wizard/steps/InvestitionenStep.tsx` (komplett neu)
- `frontend/src/components/setup-wizard/steps/SensorConfigStep.tsx` (neu)
- `frontend/src/components/setup-wizard/steps/SummaryStep.tsx` (angepasst)
- `frontend/src/components/setup-wizard/steps/AnlageStep.tsx` (Geocoding hinzugefügt)
- `frontend/src/components/AppWithSetup.tsx` (DB-Check vor LocalStorage)
- `backend/api/routes/anlagen.py` (Geocoding & Sensor-Config Endpoints)
- `backend/models/anlage.py` (ha_sensor_* Felder)

---

### Feature 2.16: String-basierte IST-Datenerfassung pro PV-Modul
**Status:** ✅ Implementiert

- `ha_entity_id` Feld zum Investition-Model hinzugefügt
- Neues `StringMonatsdaten` Model/Tabelle erstellt
- HA Integration API mit String-Sensor Endpoints erweitert
- Frontend-Formulare und APIs aktualisiert
- PrognoseVsIst-Seite mit Modul-SOLL-IST-Vergleich erweitert

**Dateien:**
- `backend/models/string_monatsdaten.py` (neu)
- `backend/models/investition.py` (ha_entity_id hinzugefügt)
- `backend/api/routes/ha_integration.py` (String-Endpoints)
- `frontend/src/components/forms/InvestitionForm.tsx`
- `frontend/src/pages/PrognoseVsIst.tsx`

### Feature 2.1: HA Energy-Integration
**Status:** ✅ Funktioniert für aktuelle Monate

- `_get_ha_statistics_monthly()` Helper-Funktion (History API)
- `POST /ha/statistics/monthly` Endpoint
- `POST /ha/import/monatsdaten` Endpoint mit `ueberschreiben` Option
- `GET /ha/import/preview/{anlage_id}` Endpoint
- Frontend API-Funktionen
- Import für aktuelle Monate (letzte ~10 Tage History) funktioniert

**Einschränkung:** Ältere Monate (> 10 Tage) können nicht importiert werden, da die HA History API nur kurzzeitige Daten liefert.

**Dateien:**
- `backend/api/routes/ha_integration.py`
- `frontend/src/api/ha.ts`

### UI: Sensor-Mapping in Settings
**Status:** ✅ Implementiert

- Zeigt alle 5 Sensor-Zuordnungen (PV, Einspeisung, Netzbezug, Batterie Ladung/Entladung)
- Zeigt konfigurierte Entity-IDs an
- Aufklappbare Liste verfügbarer HA Energy-Sensoren
- Info-Box zur Konfiguration über HA Add-on-Einstellungen

**Dateien:**
- `frontend/src/pages/Settings.tsx`
- `frontend/src/api/system.ts`
- `backend/main.py` (/api/settings erweitert)

### UI: Import-Vorschau auf Monatsdaten-Seite
**Status:** ✅ Implementiert

- "Aus HA importieren" Button in Toolbar
- Modal mit Jahr-Auswahl und Vorschau
- Vergleich DB-Daten vs. HA-Daten für jeden Monat
- Status-Anzeige: Vorhanden, Importierbar, Aktualisierbar
- Import einzelner Monate oder alle fehlenden

**Dateien:**
- `frontend/src/pages/Monatsdaten.tsx`

### Feature: HA Auto-Discovery (v0.6.0 → v0.8.0)
**Status:** ✅ Implementiert und erweitert

Automatische Erkennung von Home Assistant Geräten und Sensor-Mappings.

**Funktionen:**
- Erkennt Wechselrichter aller großen Hersteller (SMA, Fronius, Kostal, Huawei, etc.)
- Erkennt Balkonkraftwerke (EcoFlow, Hoymiles, Anker, APSystems, Deye, OpenDTU)
- Erkennt Wärmepumpen (Viessmann, Daikin, Vaillant, Bosch, Mitsubishi, Panasonic, Stiebel Eltron, Nibe, Alpha Innotec, Lambda, iDM, Toshiba, LG)
- Erkennt E-Autos und Wallboxen (evcc, Smart, Wallbox)
- Vorschläge für Sensor-Mappings (Monatsdaten-Import)
- **Empfohlen/Alle Toggle:** Benutzer können zwischen automatisch erkannten Sensoren und allen Energy-Sensoren wählen
- Vorschläge für Investitionen mit vorausgefüllten Parametern
- Duplikat-Erkennung (bereits konfigurierte Geräte markiert)
- evcc hat Priorität über native Wallbox/Smart Integrationen

**Aufruf:**
- **Beim ersten Start:** Setup-Wizard führt automatisch durch Discovery
- Nach Anlage-Erstellung: Discovery-Dialog erscheint automatisch
- Auf Anlagen-Seite: Such-Button (Lupe) neben jeder Anlage
- In Settings: "Geräte erkennen" Button im HA-Bereich

**API:**
- `GET /api/ha/discover?anlage_id={id}&manufacturer={filter}` - Discovery-Endpoint
- `GET /api/ha/manufacturers` - Liste unterstützter Hersteller
- `GET /api/anlagen/geocode/lookup?plz={plz}&ort={ort}` - Geocoding-Endpoint (neu)
- `GET/PATCH /api/anlagen/{id}/sensors` - Sensor-Konfiguration (neu)

**Dateien:**
- `backend/api/routes/ha_integration.py` (INTEGRATION_PATTERNS, Discovery-Logik)
- `backend/api/routes/anlagen.py` (Geocoding, Sensor-Config)
- `frontend/src/api/ha.ts` (Discovery Types und API)
- `frontend/src/api/anlagen.ts` (Geocode, SensorConfig)
- `frontend/src/hooks/useDiscovery.ts` (Discovery Hook)
- `frontend/src/components/discovery/` (Dialog-Komponenten)

### Dashboards (Phase 2)
**Status:** ✅ Implementiert

- **E-Auto Dashboard (2.4):** KPIs, Ladequellen, Kostenvergleich, V2H-Sektion
- **Speicher Dashboard (2.6):** Vollzyklen, Effizienz, Lade-/Entlade-Charts
- **Wallbox Dashboard (2.7):** PV-Anteil, Heimladung vs. Extern, ROI

**Dateien:**
- `frontend/src/pages/EAutoDashboard.tsx`
- `frontend/src/pages/SpeicherDashboard.tsx`
- `frontend/src/pages/WallboxDashboard.tsx`

---

## Bekannte Einschränkungen

### ⚠️ HA Long-Term Statistics nicht abrufbar

**Problem:**
Die Home Assistant REST API (`/api/history/period/`) gibt nur **kurzfristige History-Daten** zurück (ca. 10 Tage, je nach Recorder-Konfiguration). **Long-Term Statistics** (die im Energy Dashboard sichtbar sind) sind **nur über die WebSocket API** zugänglich.

**Auswirkung:**
- Import für aktuelle Monate (Jan/Feb 2026) funktioniert ✅
- Import für ältere Monate (2025 und früher) nicht möglich ❌

**Vorbereitete Lösung (derzeit deaktiviert):**
WebSocket-Client implementiert in `backend/services/ha_websocket.py`, funktioniert aber noch nicht zuverlässig im Add-on-Container. Die WebSocket-URL für Add-ons muss noch recherchiert werden.

**Mögliche zukünftige Lösungen:**
1. WebSocket-Verbindung debuggen und aktivieren
2. Direkter Datenbankzugriff auf HA SQLite (`statistics` Tabelle)
3. Custom Component für REST-Zugriff auf Statistics

---

## Sensor-Konfiguration

**Neu in v0.8.0:** Sensoren können jetzt im Setup-Wizard konfiguriert werden. Die Konfiguration wird in der Anlage-Tabelle gespeichert und ersetzt die config.yaml Einstellung.

Alternativ können Sensoren weiterhin in der Add-on-Konfiguration eingetragen werden:

```yaml
ha_sensors:
  pv_erzeugung: sensor.sn_3012412676_pv_gen_meter
  einspeisung: sensor.sn_3012412676_metering_total_yield
  netzbezug: sensor.sn_3012412676_metering_total_absorbed
  batterie_ladung: sensor.sn_3012412676_battery_charge_total
  batterie_entladung: sensor.sn_3012412676_battery_discharge_total
```

Die Sensoren müssen `state_class: total_increasing` haben, damit HA Long-Term Statistics speichert.

---

## Git Historie (Version 0.7.x - 0.8.x)

```
xxxx feat(wizard): Refactor wizard with full investment capture and sensor config (v0.8.0)
780a4c1 fix(wizard): Auto-start wizard when database is empty (v0.7.5)
668f89f docs: Update documentation for v0.7.4 release
1618457 feat(discovery): Add support for heat pumps and balcony power plants (v0.7.4)
b3040a7 chore: Bump add-on version to 0.7.3
f3a2d30 fix(wizard): Fix parameter field names for investments (v0.7.3)
6b03258 fix: Update frontend version display to 0.7.2
cbe7ebc chore: Include pre-built frontend in repository
...
```

---

## Nächste Schritte (gemäß PROJEKTPLAN.md)

### Phase 2 - Offen:
- [ ] 2.12 PDF-Export (jsPDF Integration)
- [ ] 2.5 Dashboard: Wärmepumpe (Backend für WP-Discovery jetzt vorbereitet)

### Optional für später:
- [ ] WebSocket für Long-Term Statistics zum Laufen bringen
- [ ] String-Import aus HA vervollständigen (benötigt Long-Term Statistics)

---

## Lokale Entwicklung

```bash
# Repository klonen/aktualisieren
cd /home/gernot/claude/eedc-homeassistant
git pull

# Backend starten
cd eedc/backend
source venv/bin/activate
uvicorn main:app --reload --port 8099

# Frontend starten (in neuem Terminal)
cd eedc/frontend
npm run dev

# Produktions-Build
npm run build
```

---

## Test-Umgebung des Benutzers

**Home Assistant Setup:**
- SMA Wechselrichter (Sensoren: `sensor.sn_3012412676_*`)
- evcc Integration (Wallbox + Fahrzeug)
- Smart #1 E-Auto Integration
- Wallbox Integration (wird durch evcc überdeckt)

**Getestete Funktionen:**
- ✅ Setup-Wizard führt durch komplette Ersteinrichtung
- ✅ Strompreise mit deutschen Standardwerten
- ✅ Auto-Discovery erkennt alle 4 Geräte (SMA WR, SMA Speicher, evcc Wallbox, evcc E-Auto)
- ✅ Sensor-Mappings werden korrekt vorgeschlagen
- ✅ "Alle" Toggle zeigt alle Energy-Sensoren für manuelle Auswahl
- ✅ Investitionen werden mit Details erstellt (Fix v0.7.3: Feldnamen-Konsistenz)
- ✅ E-Auto Batteriekapazität wird korrekt gespeichert

---

*Letzte Aktualisierung: 2026-02-05*
