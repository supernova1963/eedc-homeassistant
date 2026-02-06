# eedc Projekt Status

**Stand:** 2026-02-06
**Version:** 0.9.1 Beta

## Übersicht

eedc (Energie Effizienz Data Center) ist ein Home Assistant Add-on zur PV-Analyse mit Monatsdaten, Prognosen und Wirtschaftlichkeitsberechnungen.

---

## Aktueller Stand (v0.9.1 Beta)

### Änderungen in v0.9.1

**Bugfixes und Verbesserungen:**

1. **Zentrale Versionskonfiguration**
   - Version nur noch an einer Stelle definiert (Frontend: `config/version.ts`, Backend: `core/config.py`)
   - Alle UI-Elemente und API-Endpoints nutzen zentrale Version

2. **Dynamische Formularfelder**
   - MonatsdatenForm: V2H-Felder nur bei E-Autos mit v2h_faehig oder nutzt_v2h
   - MonatsdatenForm: Arbitrage-Felder nur bei Speichern mit arbitrage_faehig
   - PV-Module-Section korrekt angezeigt (nicht nur Wechselrichter)

3. **PV-Module Detailangaben**
   - Anzahl Module und Leistung pro Modul (Wp) in InvestitionForm
   - Berechnung kWp = Anzahl × Wp / 1000
   - Wichtig für KPI wie spezifischer Ertrag (kWh/kWp)

4. **Monatsdaten-Tabelle**
   - Konfigurierbare Spalten mit Toggle-Buttons
   - Spaltenauswahl wird in localStorage gespeichert
   - Neue Spalten: Direktverbrauch, Eigenverbrauch, Gesamtverbrauch, Autarkie, EV-Quote

5. **Import/Export Fixes**
   - 0-Werte werden jetzt korrekt importiert (z.B. E-Auto Extern 0 kWh)
   - Berechnete Felder funktionieren auch bei pv_erzeugung=0
   - V2H-Spalten nur wenn v2h_faehig ODER nutzt_v2h
   - Arbitrage-Spalten in Template/Export/Import

### Änderungen in v0.9.0

**Datenmodell-Bereinigung und Vereinfachung:**

1. **HA-Import Monatsdaten entfernt**
   - War zu unzuverlässig (Long-Term Statistics Einschränkungen)
   - Datenerfassung jetzt nur via CSV-Import oder manuell
   - HA wird weiterhin für Discovery (Geräte-Erkennung) verwendet

2. **Sensor-Konfiguration aus Wizard entfernt**
   - Nicht mehr benötigt ohne HA-Import
   - Wizard-Schritte reduziert von 8 auf 7

3. **Neues Zielbild dokumentiert** (siehe `docs/ZIELBILD_v0.9.md`)
   - Parent-Child Beziehungen: PV-Module → Wechselrichter (Pflicht), Speicher → Wechselrichter (Optional)
   - Personalisierte CSV-Vorlagen basierend auf angelegten Investitionen
   - Summenberechnung: Batterie-Felder aus Speicher-Investitionen, PV-Erzeugung aus PV-Modulen

### Was funktioniert gut

1. **Setup-Wizard mit Auto-Discovery**
   - Automatische Erkennung von HA-Geräten (Wechselrichter, Speicher, E-Autos, Wallboxen)
   - Strompreis-Konfiguration mit deutschen Standardwerten

2. **Investitionsverwaltung**
   - Alle Investitionstypen: Wechselrichter, PV-Module, Speicher, Wallbox, E-Auto, Wärmepumpe, Balkonkraftwerk
   - ROI-Berechnungen basierend auf Kaufpreis und Ertragsdaten

3. **Monatsdaten-Erfassung**
   - Manuelle Eingabe
   - CSV-Import (erweitert für Investitions-Monatsdaten)

4. **Dashboards und Auswertungen**
   - Haupt-Dashboard mit KPIs
   - E-Auto Dashboard
   - Speicher Dashboard
   - Wallbox Dashboard
   - PVGIS-Prognose

---

## Wizard-Schritte (v0.9.0)

1. **Willkommen** - Einführung
2. **Anlage erstellen** - Name, Leistung, Standort (+ Geocoding)
3. **HA-Verbindung prüfen** - Für Discovery, überspringbar
4. **Strompreise** - Mit deutschen Standardwerten
5. **Auto-Discovery** - Geräte erkennen & als Investitionen anlegen
6. **Investitionen vervollständigen** - Kaufpreis, Datum, Details
7. **Zusammenfassung** - Mit individualisierten nächsten Schritten

---

## Datenmodell (Zielbild v0.9)

Siehe `docs/ZIELBILD_v0.9.md` für Details.

### Kernkonzepte

```
ANLAGE (Summenfelder, berechnet wo Investitionsdaten vorhanden)
  │
  └── INVESTITIONEN (1:n)
        │
        ├── Wechselrichter
        │     ├── PV-Module (Pflicht: Parent)
        │     └── Speicher (Optional: Parent für Hybrid-WR)
        │
        ├── E-Auto (eigenständig)
        ├── Wallbox (eigenständig)
        ├── Wärmepumpe (eigenständig)
        └── Balkonkraftwerk (All-in-One)
```

### Datenfluss

```
CSV Import → Monatsdaten (Basis-Werte: Einspeisung, Netzbezug)
          → InvestitionMonatsdaten (E-Auto, Wallbox, Speicher, WP, PV-Module)

Summenberechnung:
  Monatsdaten.batterie_ladung_kwh = Σ(Speicher.ladung_kwh)
  Monatsdaten.pv_erzeugung_kwh = Σ(PV-Modul.pv_erzeugung_kwh)
```

---

## Bekannte Einschränkungen

#### PV-Module werden nicht automatisch erkannt
PV-Module haben keine eigenen HA-Sensoren und müssen manuell als Investition angelegt werden. Die Angaben zu Ausrichtung und Neigung sind wichtig für die PVGIS-Ertragsprognose.

---

## Nächste Schritte (Roadmap v0.9)

### Phase 2-5: Alle abgeschlossen ✅

Siehe v0.9.0 Changelog für Details. Alle geplanten Features implementiert:
- Parent-Child Beziehungen (PV→WR, Speicher→WR)
- Personalisierte CSV-Vorlagen
- PVGIS pro PV-Modul
- Dynamische Formulare

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
│   ├── ZIELBILD_v0.9.md    # Datenmodell-Zielbild
│   ├── DATENMODELL.md      # Analyse der Inkonsistenzen
│   ├── STATUS_v0.7.md      # Archiv
│   └── HANDOVER.md         # Entwickler-Handover
├── eedc/
│   ├── backend/
│   │   ├── api/routes/
│   │   │   ├── ha_integration.py   # Discovery (Import deprecated)
│   │   │   └── import_export.py    # CSV-Import
│   │   └── models/
│   └── frontend/
│       ├── src/
│       │   ├── components/setup-wizard/
│       │   ├── hooks/useSetupWizard.ts
│       │   └── pages/Monatsdaten.tsx
│       └── dist/
```

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

## Änderungshistorie

### v0.9.1 Beta (2026-02-06)
- **Zentrale Version:** Config in Frontend und Backend
- **Dynamische Formulare:** V2H und Arbitrage bedingt anzeigen
- **PV-Module Details:** Anzahl und Wp pro Modul
- **Spalten-Toggle:** Monatsdaten-Tabelle konfigurierbar
- **Bugfixes:** 0-Wert Import, berechnete Felder

### v0.9.0 (2026-02-06)
- **HA-Import entfernt:** Monatsdaten-Import aus HA deaktiviert
- **Sensor-Config entfernt:** Wizard vereinfacht, Schritt entfernt
- **Parent-Child Validierung:** PV→WR (Pflicht), Speicher→WR (Optional)
- **Personalisierte CSV-Vorlagen:** Dynamische Spalten
- **Summenberechnung:** PV und Batterie aus Investitionen

### v0.8.x (2026-02-05)
- Wizard Refactoring mit Auto-Discovery
- Investitions-Erfassung im Wizard

---

*Letzte Aktualisierung: 2026-02-06*
