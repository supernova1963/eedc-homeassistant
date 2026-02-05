# EEDC Projekt Status

**Stand:** 2026-02-05
**Version:** 0.8.1

## Übersicht

EEDC (Energie Effizienz Data Center) ist ein Home Assistant Add-on zur PV-Analyse mit Monatsdaten, Prognosen und Wirtschaftlichkeitsberechnungen.

---

## Aktueller Stand (v0.8.1)

### Was funktioniert gut

1. **Setup-Wizard mit Auto-Discovery**
   - Automatische Erkennung von HA-Geräten (Wechselrichter, Speicher, E-Autos, Wallboxen)
   - Sensor-Zuordnung für Energy-Daten
   - Strompreis-Konfiguration mit deutschen Standardwerten

2. **Investitionsverwaltung**
   - Alle Investitionstypen: Wechselrichter, PV-Module, Speicher, Wallbox, E-Auto, Wärmepumpe, Balkonkraftwerk
   - ROI-Berechnungen basierend auf Kaufpreis und Ertragsdaten

3. **Monatsdaten-Erfassung**
   - Manuelle Eingabe
   - CSV-Import
   - HA-Import (mit Einschränkungen, siehe unten)

4. **Dashboards und Auswertungen**
   - Haupt-Dashboard mit KPIs
   - E-Auto Dashboard
   - Speicher Dashboard
   - Wallbox Dashboard
   - PVGIS-Prognose

### Bekannte Einschränkungen

#### HA-Datenimport begrenzt auf ~10 Tage
Die Home Assistant REST API liefert nur kurzfristige History-Daten. Long-Term Statistics (die im HA Energy Dashboard sichtbar sind) sind nur über die WebSocket API zugänglich, die noch nicht stabil funktioniert.

**Praktische Auswirkung:**
- Import für aktuelle Monate (letzte ~10 Tage) funktioniert
- Import für ältere Monate nicht möglich
- **Empfehlung:** Monatsdaten manuell oder per CSV importieren

#### PV-Module werden nicht automatisch erkannt
PV-Module haben keine eigenen HA-Sensoren und müssen manuell als Investition angelegt werden. Die Angaben zu Ausrichtung und Neigung sind wichtig für die PVGIS-Ertragsprognose.

---

## Änderungen in v0.8.x

### v0.8.1 (2026-02-05)
- **Wizard vereinfacht:** Monatsdaten-Fokus entfernt
- **Individualisierte "Nächste Schritte":** Summary zeigt priorisierte Schritte basierend auf Konfiguration
- **Verbessertes Hinzufügen von Investitionen:** Scroll und Highlight bei neuen Einträgen
- **HA-Import UX verbessert:** Loading-Overlay und Detail-Feedback (welche Sensoren Daten lieferten)

### v0.8.0 (2026-02-05)
- **Wizard Refactoring:** Komplett überarbeiteter Setup-Wizard
- **Sensor-Konfiguration im Wizard:** Ersetzt config.yaml Einstellung
- **Investitionen-Schritt:** Alle Investitionen auf einer Seite bearbeiten
- **Auto-Start bei leerer DB:** Wizard startet automatisch wenn keine Anlagen vorhanden

---

## Wizard-Schritte (v0.8.1)

1. **Willkommen** - Einführung
2. **Anlage erstellen** - Name, Leistung, Standort (+ Geocoding)
3. **HA-Verbindung prüfen** - Automatisch, überspringbar
4. **Strompreise** - Mit deutschen Standardwerten
5. **Auto-Discovery** - Geräte erkennen & als Investitionen anlegen
6. **Investitionen vervollständigen** - Kaufpreis, Datum, Details
7. **Sensor-Konfiguration** - HA-Sensoren zuordnen
8. **Zusammenfassung** - Mit individualisierten nächsten Schritten
9. **Abschluss** - Erfolgsmeldung

---

## Unterstützte Geräte (Auto-Discovery)

### Wechselrichter
SMA, Fronius, Kostal, Huawei/FusionSolar, Growatt, SolaX, Sungrow, GoodWe, Enphase

### Balkonkraftwerke
EcoFlow, Hoymiles, Anker SOLIX, APSystems, Deye, OpenDTU/AhoyDTU

### Wärmepumpen
Viessmann, Daikin, Vaillant, Bosch, Mitsubishi, Panasonic, Stiebel Eltron, Nibe, Alpha Innotec, Lambda, iDM, Toshiba, LG

### E-Autos & Wallboxen
evcc (höchste Priorität), Smart, Wallbox

---

## Architektur

```
eedc-homeassistant/
├── docs/
│   ├── STATUS.md           # Dieses Dokument
│   ├── STATUS_v0.7.md      # Archiv
│   ├── HANDOVER.md         # Entwickler-Handover
│   └── DEVELOPMENT.md      # Development Guide
├── eedc/
│   ├── config.yaml         # HA Add-on Konfiguration
│   ├── backend/
│   │   ├── main.py         # FastAPI Entry
│   │   ├── api/routes/
│   │   │   ├── ha_integration.py   # Discovery, Import
│   │   │   └── anlagen.py          # Geocoding, Sensor-Config
│   │   ├── models/
│   │   └── services/
│   └── frontend/
│       ├── src/
│       │   ├── components/
│       │   │   ├── setup-wizard/   # Wizard-Komponenten
│       │   │   └── forms/
│       │   ├── hooks/
│       │   │   └── useSetupWizard.ts
│       │   └── pages/
│       └── dist/               # Build (wird committed)
```

---

## Nächste Schritte (Roadmap)

### Priorität 1: Datenqualität verbessern
- [ ] Monatsdaten-Seite: Bessere UX für manuelle Erfassung
- [ ] CSV-Import: Validierung und Fehlerbehandlung verbessern
- [ ] Investitionen-Seite: Direkter Zugang zu PV-Module hinzufügen

### Priorität 2: Auswertungen ausbauen
- [ ] Dashboard: Wärmepumpe (Backend vorbereitet)
- [ ] PDF-Export (jsPDF vorhanden)
- [ ] Jahresvergleich

### Priorität 3 (Zukunftsvision): HA-Integration vertiefen
- [ ] WebSocket für Long-Term Statistics aktivieren
- [ ] **EEDC-Gerät in HA erstellen** mit berechneten KPIs:
  - Eigenverbrauchsquote (%)
  - Autarkiegrad (%)
  - ROI-Status (%)
  - Amortisationsprognose (Datum)
  - CO2-Ersparnis (kg)
- [ ] Sensoren am Wechselrichter-Gerät ablegen

---

## Sensor-Konfiguration

Sensoren können im Setup-Wizard oder in der Add-on-Konfiguration eingetragen werden:

```yaml
ha_sensors:
  pv_erzeugung: sensor.xyz_pv_gen_meter
  einspeisung: sensor.xyz_metering_total_yield
  netzbezug: sensor.xyz_metering_total_absorbed
  batterie_ladung: sensor.xyz_battery_charge_total
  batterie_entladung: sensor.xyz_battery_discharge_total
```

**Wichtig:** Sensoren müssen `state_class: total_increasing` haben, damit HA Long-Term Statistics speichert.

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

# Frontend starten (neues Terminal)
cd eedc/frontend
npm run dev

# Produktions-Build
npm run build
```

---

## Git Historie (aktuelle Commits)

```
cbcad51 refactor(wizard): Simplify wizard, remove Monatsdaten focus, add dynamic next steps
59a1933 fix(import): Improve HA import UX with loading overlay and details feedback
11888bf fix(import): Use anlage-based sensor config for HA import
cc8a0c5 feat(wizard): Refactor wizard with full investment capture and sensor config (v0.8.0)
780a4c1 fix(wizard): Auto-start wizard when database is empty (v0.7.5)
```

---

*Letzte Aktualisierung: 2026-02-05*
