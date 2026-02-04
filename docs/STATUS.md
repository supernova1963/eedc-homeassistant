# EEDC Projekt Status

**Stand:** 2026-02-04
**Version:** 0.6.0

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

Die Sensoren werden in der Add-on-Konfiguration eingetragen:

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

## Git Historie (aktuell)

```
2a477f3 fix(ha): Revert to History API, make WebSocket optional
212a176 fix(ha): Correct WebSocket URL for HA Add-on environment
01f0202 fix(ui): Add null-safety to formatKwh functions in Monatsdaten
b4c197d feat(ha): Add WebSocket client for Long-Term Statistics
d38d6ca docs: Add STATUS.md with current project state and known issues
ff768e5 fix(ha): Revert to working History API implementation
```

---

## Nächste Schritte (gemäß PROJEKTPLAN.md)

### Phase 2 - Offen:
- [ ] 2.1 HA Energy - Long-Term Statistics (WebSocket debuggen oder Alternative)
- [ ] 2.4 Dashboard: E-Auto
- [ ] 2.5 Dashboard: Wärmepumpe
- [ ] 2.6 Dashboard: Speicher
- [ ] 2.7 Dashboard: Wallbox
- [ ] 2.12 PDF-Export

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
