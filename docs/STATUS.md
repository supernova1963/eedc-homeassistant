# EEDC Projekt Status

**Stand:** 2026-02-04
**Version:** 0.5.0

## Übersicht

EEDC (Energie Effizienz Data Center) ist ein Home Assistant Add-on zur PV-Analyse mit Monatsdaten, Prognosen und Wirtschaftlichkeitsberechnungen.

---

## Aktuell implementierte Features

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
**Status:** ⚠️ Teilweise implementiert (siehe bekannte Probleme)

- `_get_ha_statistics_monthly()` Helper-Funktion
- `POST /ha/statistics/monthly` Endpoint
- `POST /ha/import/monatsdaten` Endpoint mit `ueberschreiben` Option
- `GET /ha/import/preview/{anlage_id}` Endpoint
- Frontend API-Funktionen

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

---

## Bekannte Probleme

### 🔴 KRITISCH: HA Long-Term Statistics nicht abrufbar

**Problem:**
Die Home Assistant REST API (`/api/history/period/`) gibt nur **kurzfristige History-Daten** zurück (ca. 10 Tage, je nach Recorder-Konfiguration). **Long-Term Statistics** (die im Energy Dashboard und Statistik-Grafiken sichtbar sind) sind **nur über die WebSocket API** zugänglich.

**Symptom:**
- Import für aktuelle Monate (z.B. Januar/Februar 2026) funktioniert
- Import für ältere Monate (z.B. 2025) zeigt "Keine Statistiken gefunden"
- Die Daten existieren in HA (sichtbar im Energy Dashboard), sind aber nicht über REST abrufbar

**Ursache:**
Home Assistant stellt keinen REST-Endpoint für Long-Term Statistics bereit. Der Endpoint `/api/history/statistics_during_period` existiert nicht als REST API, sondern nur als WebSocket-Befehl.

**Referenzen:**
- https://community.home-assistant.io/t/can-i-get-long-term-statistics-from-the-rest-api/761444
- https://github.com/home-assistant/core/issues/56052

**Mögliche Lösungen:**

1. **WebSocket-Verbindung implementieren**
   - Aufwand: Hoch
   - Erfordert persistente WebSocket-Verbindung zu HA
   - Vorteile: Vollständiger Zugriff auf Long-Term Statistics

2. **Direkter Datenbankzugriff**
   - Aufwand: Mittel
   - Add-on liest HA SQLite-Datenbank (`home-assistant_v2.db`) direkt
   - Tabelle: `statistics` und `statistics_meta`
   - Vorteile: Schnell, alle Daten verfügbar
   - Nachteile: Abhängig von HA-internem Schema

3. **Custom Component**
   - Aufwand: Mittel
   - Separate HA-Integration die Statistics als REST-Service bereitstellt
   - Vorteile: Saubere Trennung
   - Nachteile: Zusätzliche Installation nötig

---

## Sensor-Konfiguration

Die Sensoren werden korrekt mit `sensor.` Prefix in der Add-on-Konfiguration eingetragen:

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

## Nächste Schritte

1. **Lösung für Long-Term Statistics implementieren**
   - Empfehlung: Option 2 (Direkter Datenbankzugriff)
   - HA-Datenbank unter `/homeassistant/home-assistant_v2.db` einbinden
   - SQL-Abfragen für monatliche Aggregation der Statistics

2. **String-Import aus HA vervollständigen**
   - Aktuell Platzhalter-Antwort in `/ha/string-monatsdaten/import`
   - Benötigt ebenfalls Long-Term Statistics Zugriff

---

## Git Historie (relevant)

```
ff768e5 fix(ha): Revert to working History API implementation
7bffdac fix(ha): Use Long-Term Statistics API with multiple fallbacks
15e7977 fix(ha): Use History API to calculate monthly statistics
fc8ae54 fix(ui): Show warning when HA has no statistics data
c54f1bc feat(ui): Add HA sensor mapping display and import preview
46b0b04 feat(2.1): HA Long-Term Statistics API for monthly data import
0cc2e4a feat(2.16): String-based IST data collection per PV module
```

---

## Lokale Entwicklung fortsetzen

```bash
# Repository klonen/aktualisieren
cd /home/gernot/claude/eedc-homeassistant
git pull

# Backend starten
cd eedc/backend
source venv/bin/activate  # oder: python -m venv venv && pip install -r requirements.txt
uvicorn main:app --reload --port 8099

# Frontend starten (in neuem Terminal)
cd eedc/frontend
npm install  # falls nötig
npm run dev

# Oder: Produktions-Build
npm run build
```

---

## Dateien mit ungespeicherten Änderungen

Prüfen mit: `git status`
