# EEDC Projekt Status

**Stand:** 2026-02-06
**Version:** 0.9.0

## Übersicht

EEDC (Energie Effizienz Data Center) ist ein Home Assistant Add-on zur PV-Analyse mit Monatsdaten, Prognosen und Wirtschaftlichkeitsberechnungen.

---

## Aktueller Stand (v0.9.0)

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

### Phase 2: Parent-Child implementieren ✅
- [x] Backend-Validierung: PV-Module müssen Wechselrichter haben (wenn vorhanden)
- [x] Backend-Validierung: Speicher optional zu Wechselrichter (Hybrid-WR)
- [x] Backend: `/parent-options/{anlage_id}` Endpoint
- [x] Frontend: PARENT_MAPPING korrigiert (E-Auto → Wallbox entfernt)
- [x] Frontend: PARENT_REQUIRED für Pflicht-Zuordnungen
- [x] Frontend: Verbesserte UI für Parent-Dropdown (Pflicht/Optional-Labels, Warnungen)

### Phase 3: Monatsdaten-Logik ✅
- [x] Personalisierte CSV-Vorlage mit Investitions-Spalten (z.B. `Sueddach_kWh`, `Speicher_Keller_Ladung_kWh`)
- [x] CSV-Import erkennt personalisierte Spalten und importiert zu passenden Investitionen
- [x] Summenberechnung: pv_erzeugung aus PV-Modul-Summe wenn keine explizite Spalte
- [x] Summenberechnung: batterie_ladung/entladung aus Speicher-Summe wenn keine explizite Spalte
- [x] CSV-Export mit personalisierten Spalten und Investitions-Monatsdaten
- [x] Legacy-Import für alte CSV-Formate bleibt erhalten

### Phase 4: PVGIS ✅ (bereits implementiert)
- [x] PVGIS-Abruf pro PV-Modul (`/api/pvgis/modul/{investition_id}`)
- [x] Anlage-Prognose = Summe PV-Modul-Prognosen (`/api/pvgis/prognose/{anlage_id}`)
- [x] Jedes PV-Modul mit eigener Ausrichtung und Neigung
- [x] Prognosen speichern und verwalten
- [ ] Dashboard: SOLL-IST Vergleich pro String (Frontend-Erweiterung)

### Phase 5: Aufräumen ✅
- [x] StringMonatsdaten-Model als deprecated markiert
- [x] Dokumentation aktualisiert: PV-Daten jetzt über InvestitionMonatsdaten
- [x] DB-Tabelle beibehalten für Rückwärtskompatibilität (bestehende Datenbanken)
- [x] Batterie-Felder in Monatsdaten: Werden jetzt aus Speicher-Investitionen summiert

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

### v0.9.0 (2026-02-06)
- **HA-Import entfernt:** Monatsdaten-Import aus HA deaktiviert
- **Sensor-Config entfernt:** Wizard vereinfacht, Schritt entfernt
- **Zielbild dokumentiert:** Klare Struktur für Parent-Child, CSV-Vorlagen
- **Parent-Child Validierung:** Backend und Frontend implementiert
  - PV-Module → Wechselrichter (Pflicht)
  - Speicher → Wechselrichter (Optional, für Hybrid-WR)
  - E-Auto nicht mehr Wallbox zugeordnet
- **Personalisierte CSV-Vorlagen:** Spalten basierend auf Investitions-Bezeichnungen
  - Template-Endpoint generiert dynamische Spalten
  - Import erkennt automatisch personalisierte vs. Legacy-Format
  - Export enthält alle Investitions-Monatsdaten
- **Summenberechnung:** PV-Erzeugung und Batterie-Daten aus Investitionen

### v0.8.1 (2026-02-05)
- Wizard vereinfacht: Monatsdaten-Fokus entfernt
- Individualisierte "Nächste Schritte" im Summary
- HA-Import UX verbessert (nun deprecated)

### v0.8.0 (2026-02-05)
- Wizard Refactoring mit vollständiger Investitions-Erfassung
- Sensor-Konfiguration im Wizard (nun entfernt)

---

*Letzte Aktualisierung: 2026-02-06*
