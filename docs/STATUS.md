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

### Phase 2: Parent-Child implementieren
- [ ] Validierung aktivieren: PV-Modul braucht Wechselrichter
- [ ] UI: Dropdown für Wechselrichter bei PV-Modul
- [ ] Optional: Speicher → Wechselrichter Zuordnung

### Phase 3: Monatsdaten-Logik
- [ ] Summenberechnung für Batterie-Felder implementieren
- [ ] pv_erzeugung aus PV-Modul-Summe wenn vorhanden
- [ ] Personalisierte CSV-Vorlage mit Investitions-Spalten

### Phase 4: PVGIS
- [ ] PVGIS-Abruf pro PV-Modul ermöglichen
- [ ] Anlage-Prognose = Summe PV-Modul-Prognosen
- [ ] Dashboard: SOLL-IST Vergleich pro String

### Phase 5: Aufräumen
- [ ] StringMonatsdaten-Tabelle entfernen (DB-Migration)
- [ ] Batterie-Direktfelder in Monatsdaten deprecaten

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

### v0.8.1 (2026-02-05)
- Wizard vereinfacht: Monatsdaten-Fokus entfernt
- Individualisierte "Nächste Schritte" im Summary
- HA-Import UX verbessert (nun deprecated)

### v0.8.0 (2026-02-05)
- Wizard Refactoring mit vollständiger Investitions-Erfassung
- Sensor-Konfiguration im Wizard (nun entfernt)

---

*Letzte Aktualisierung: 2026-02-06*
