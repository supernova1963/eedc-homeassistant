# Konzept: Wallbox / E-Auto — Datenarchitektur

> Status: Entwurf (2026-04-16) | Kein Issue, noch in Konzeptphase

## Motivation

Die aktuelle Architektur speichert Heimladung (PV/Netz-Split) am **E-Auto** und aggregiert im Wallbox-Dashboard alles in einen Pool. Das funktioniert bei 1 Wallbox + 1 E-Auto, bricht aber bei realistischen Szenarien:

- Privatauto + Firmenwagen an derselben Wallbox (steuerlich trennbar)
- Mehrere Wallboxen (Garage + Carport)
- Gast-Ladungen ohne zugeordnetes E-Auto
- RFID-basierte Zuordnung (evcc, SMA eCharger, Wattpilot)

## Kernprinzip: Jeder speichert was er misst

### Wallbox = Infrastruktur (misst den Stromfluss)

```
verbrauch_daten:
  ladung_kwh          ← Zählerstand-Differenz (Gesamt am Ladepunkt)
  ladung_pv_kwh       ← davon PV (evcc/Sensor)
  ladung_netz_kwh     ← davon Netz (evcc/Sensor oder abgeleitet)
  ladevorgaenge       ← Zähler (alle Sessions am Ladepunkt)
```

### E-Auto = Fahrzeug (misst Nutzung + eigene Heimladung)

```
verbrauch_daten:
  km_gefahren          ← Tacho
  verbrauch_kwh        ← Gesamtverbrauch
  ladung_heim_kwh      ← Heimladung dieses Autos (NEU, per Vehicle-Sensor)
  ladung_heim_pv_kwh   ← davon PV (NEU, per Vehicle-Sensor)
  ladung_extern_kwh    ← Fremdladung
  ladung_extern_euro   ← Fremdladung Kosten
  v2h_entladung_kwh    ← Vehicle-to-Home
```

### Zuordnung über Sensor-Mapping, nicht über DB-Modell

Die RFID-Intelligenz bleibt bei evcc/Wallbox. EEDC konsumiert die
bereits aufgeschlüsselten Daten über die passenden Sensor-Topics:

```
Wallbox "Garage" (Loadpoint-Perspektive):
├── ladung_kwh      → evcc/loadpoints/1/chargeTotalImport
├── ladung_pv_kwh   → evcc/loadpoints/1/pvCharged
└── ladevorgaenge   → evcc/loadpoints/1/sessions

E-Auto "BMW i4" (Vehicle-Perspektive):
├── ladung_heim_kwh    → evcc/vehicles/BMW/chargeTotalImport
├── ladung_heim_pv_kwh → evcc/vehicles/BMW/pvCharged
└── ladevorgaenge      → evcc/vehicles/BMW/sessions

E-Auto "Firmenwagen" (Vehicle-Perspektive):
├── ladung_heim_kwh    → evcc/vehicles/Firma/chargeTotalImport
├── ladung_heim_pv_kwh → evcc/vehicles/Firma/pvCharged
└── ladevorgaenge      → evcc/vehicles/Firma/sessions
```

## Zwei Perspektiven, gleiche Realität

evcc liefert dieselben kWh aus zwei Blickwinkeln:

```
PRO LOADPOINT (= Wallbox)               PRO VEHICLE (= E-Auto)
evcc/loadpoints/1/pvCharged → 732 kWh   evcc/vehicles/BMW/pvCharged   → 520 kWh
                                         evcc/vehicles/Firma/pvCharged → 212 kWh
                                                                        ─────────
                                                                  Σ     732 kWh ✓
```

### Konsistenzregel

| Prüfung | Formel |
|---------|--------|
| Wallbox-Gesamt ≥ Σ E-Autos Heim | `WB.ladung_kwh ≥ Σ EAuto.ladung_heim_kwh` |
| PV-Gesamt ≥ Σ PV pro Auto | `WB.ladung_pv_kwh ≥ Σ EAuto.ladung_heim_pv_kwh` |

`≥` statt `=` weil Gast-Ladungen keinem E-Auto zugeordnet sein können.

## Dashboard-Darstellung (Ziel)

### Wallbox-Dashboard

```
SMA eCharger 22 (11 kW) · 34 Monate Daten
┌────────────────┬───────────────┬───────────────────┬──────────────┐
│ Heimladung     │ PV-Anteil     │ Ersparnis vs. Ext │ Ladevorgänge │
│ 1.200 kWh      │ 61%           │ -583 €            │ 48           │
└────────────────┴───────────────┴───────────────────┴──────────────┘
Aufschlüsselung (wenn Vehicle-Sensoren vorhanden):
  BMW i4:       880 kWh (59% PV) · 35 Vorgänge
  Firmenwagen:  320 kWh (66% PV) · 13 Vorgänge
```

### E-Auto-Dashboard

```
BMW i4
┌────────────┬──────────────┬──────────────┬──────────────┐
│ km         │ Heimladung   │ Extern       │ vs. Benzin   │
│ 12.400     │ 880 kWh      │ 340 kWh/170€ │ +1.240 €     │
└────────────┴──────────────┴──────────────┴──────────────┘
```

## Abgrenzung: Was NICHT Teil dieses Konzepts ist

- **RFID-Karten als eigene Entität** — Zuordnung bleibt bei evcc
- **Externe Ladekarten** (EnBW, ADAC etc.) — separates Thema, aktuell `ladung_extern_*` am E-Auto
- **Session-Level-Tracking** — EEDC bleibt bei Monatsaggregaten
- **Wallbox↔E-Auto Zuordnungs-UI** — nicht nötig, Sensor-Mapping reicht

## Migrationspfad

### Phase 1: Bug-Fix (jetzt)
- Ladevorgänge aus Wallbox-Monatsdaten lesen (nicht nur E-Auto)
- Kein Datenmodell-Umbau nötig

### Phase 2: Neue Felder am E-Auto (wenn Vehicle-Sensoren nachgefragt werden)
- `ladung_heim_kwh` und `ladung_heim_pv_kwh` als neue E-Auto-Felder
- Sensor-Mapping erweitern für evcc Vehicle-Topics
- Wallbox-Dashboard liest eigene Daten statt E-Auto-Pool
- Bestehende `ladung_pv_kwh`/`ladung_netz_kwh` am E-Auto bleiben als Fallback

### Phase 3: Aufschlüsselung im Wallbox-Dashboard (optional)
- Wenn E-Autos Vehicle-Sensoren haben, kann das Wallbox-Dashboard
  die Gesamt-kWh pro Fahrzeug aufschlüsseln
- Konsistenzprüfung WB-Gesamt vs. Σ E-Autos

### Kein Breaking Change
- Nutzer ohne evcc/RFID merken nichts — manuelle Eingabe funktioniert weiter
- 1:1-Setups (eine WB, ein Auto) bleiben identisch
- Pool-Aggregation bleibt Fallback wenn keine Vehicle-Sensoren gemappt sind

## Offene Fragen

1. Liefern SMA eCharger und Wattpilot ähnliche Per-Vehicle-Topics wie evcc?
2. Gibt es EEDC-Nutzer mit Multi-WB/Multi-E-Auto-Setup? (Joachim-xo prüfen)
3. Braucht das Monatsabschluss-Formular ein geändertes Layout für die neuen Felder?
