# Konzept: Solar Forecast ML — Leichtgewichtige Integration

> **ARCHIVIERT** — Alle Phasen umgesetzt.
> Phase 1 (v3.4.0): WetterWidget KPI + Chart-Linie | Phase 2 (v3.4.1): Cockpit-Vergleich + Morgen-Vorschau | Auslöser: User-Anfragen (2 User)

## Kontext

User haben [Solar Forecast ML](https://github.com/Zara-Toorox/Solar-Forecast-ML) (SFML) in HA installiert und möchten die ML-Prognose im EEDC-Kontext sehen.

### SFML-Ökosystem (Zara-Toorox)

| Projekt | Zweck | Plattform |
|---------|-------|-----------|
| **Solar Forecast ML** | Lokale KI-PV-Prognose (LSTM) | Pi4+, ARM, x86 |
| **SFML Stats** | Vollständiges Dashboard (matplotlib) | **nur x86_64** |
| **Solar Forecast GPM** | Strompreis-Optimierung, Batterie-Ladesteuerung | x86_64 |
| **Solar Forecast EAI** | WP-Verbrauchsprognose (lokale KI) | Pi4+, ARM, x86 |

### Warum leichtgewichtig statt eigenem ML-Tab?

- **SFML Stats** bietet bereits ein vollständiges Dashboard mit Forecast vs. IST, Modelldiagnose und Reports — das nachzubauen wäre redundant
- SFML Stats läuft **nur auf x86_64** — EEDC schließt die Lücke auf ARM/Pi
- Unser Mehrwert liegt im **Kontext** (Monatsdaten, ROI, Multi-Anlagen), nicht in ML-Diagnose
- Minimaler Aufwand (~2h), kein Wartungsrisiko, rein optional

## Lösung: Integration in bestehende Views

Kein neuer Tab. Stattdessen SFML-Daten in **drei bestehende Stellen** einblenden:

### 1. Wetter-Widget (Live-Seite) — ML-Forecast-Linie

```
PV-Ertrag vs. Verbrauch — IST + Prognose

kW
12 │         ╱‾‾‾╲
   │       ╱  ·····╲·····        ← ML-Forecast (gepunktet, lila)
 8 │     ╱──────────╲────        ← EEDC-Prognose (gestrichelt, orange)
   │   ╱══════════════╲          ← IST (solid, gelb)
 4 │ ╱                  ╲
   │╱                    ╲
 0 └──────────────────────────
   06   09   12   15   18  Uhr

   ═══ PV (IST)   --- PV (EEDC)   ··· PV (ML)
```

- Dritte Prognose-Linie neben IST und EEDC-Prognose
- Farbe: Lila/Violett (gepunktet), um sich von Orange (EEDC) abzuheben
- Nur sichtbar wenn SFML-Sensoren gemappt sind

### 2. Wetter-Widget Header — ML-KPI

```
Wetter heute
☀ 11°  💧 1°/12°  ☀ 11.0h Sonne  ⚡ ~57.2 kWh PV  ⚡ ML: ~54.8 kWh
```

- Zusätzlicher KPI `ML: ~XX kWh` neben der EEDC-Prognose
- Tooltip: "Solar Forecast ML Tagesprognose" + Genauigkeit wenn verfügbar

### 3. Cockpit — Prognose-Vergleich (optional, Phase 2)

Kleiner Vergleichsblock in der Monatsübersicht:
- EEDC-Forecast vs. ML-Forecast vs. IST (Abweichung in %)
- Erst sinnvoll wenn Langzeitdaten vorliegen

## Tatsächlich verwendete SFML-Sensoren

Konfiguriert über Sensor-Mapping → Live-Sensoren → Solar Forecast ML:

| Mapping-Key | Tatsächlicher Sensor | Beschreibung |
|-------------|---------------------|-------------|
| `sfml_today_kwh` | `sensor.prognose_heute` | Tages-Forecast (kWh) — KPI + Chart-Skalierung |
| `sfml_tomorrow_kwh` | `sensor.solar_forecast_ml_tomorrow` | Morgen-Forecast (kWh) — Morgen-Vorschau im WetterWidget |
| `sfml_accuracy_pct` | `sensor.solar_forecast_ml_o_genauigkeit_30_tage` | Genauigkeit (%) — Tooltip-Info |

Die **stündliche Chart-Linie** wird durch Verteilung des Tages-kWh-Werts auf die bestehende GTI-Kurvenform berechnet (kein separater Stunden-Sensor nötig).

## Technische Umsetzung (Phase 1 — erledigt v3.4.0)

### Geänderte Dateien

| Datei | Änderung |
|-------|----------|
| `backend/api/routes/live_dashboard.py` | `VerbrauchsStunde.pv_ml_prognose_kw`, `LiveWetterResponse.sfml_prognose_kwh/sfml_accuracy_pct`, SFML-Sensor-Lesen im Wetter-Endpoint |
| `frontend/src/api/liveDashboard.ts` | TypeScript-Types erweitert |
| `frontend/src/components/live/WetterWidget.tsx` | Lila KPI, gepunktete Chart-Linie, Gradient, Legende, Tooltip |
| `frontend/src/components/sensor-mapping/BasisSensorenStep.tsx` | SFML-Felder im Wizard |

### Verteilung Tages-kWh auf Stunden

Kein separater Stunden-Sensor nötig. Die bestehende GTI-Kurve wird skaliert:
```
sfml_factor = sfml_today_kwh / sum(pv_ertrag_kw)
pv_ml_prognose_kw[h] = pv_ertrag_kw[h] * sfml_factor
```

## Phase 2: Cockpit-Vergleich (umgesetzt 2026-03-22)

Vergleichsblock in der Prognose-vs-IST-Seite:
- EEDC-Forecast vs. ML-Forecast vs. IST (Abweichung in %)
- Jahres-KPIs mit farbcodierten Abweichungen
- Monatliches Balkendiagramm (EEDC- vs. ML-Abweichung)
- Detailtabelle mit "Bessere Prognose"-Indikator pro Monat
- Nur sichtbar wenn SFML-Daten vorhanden (automatisch ausgeblendet ohne SFML)
- Hinweis bei < 30 Tagen ML-Daten

### Datenpersistierung (neu in Phase 2)

`TagesZusammenfassung.sfml_prognose_kwh` speichert die tägliche ML-Prognose
beim Wetter-Endpoint-Aufruf (analog zu `pv_prognose_kwh` für EEDC).
Cockpit-Endpoint aggregiert dann monatlich.

### Geänderte Dateien (Phase 2)

| Datei | Änderung |
|-------|----------|
| `backend/models/tages_energie_profil.py` | `sfml_prognose_kwh` Spalte in TagesZusammenfassung |
| `backend/api/routes/live_dashboard.py` | `_speichere_prognose()` speichert auch SFML-Wert |
| `backend/api/routes/cockpit.py` | Neuer Endpoint `/prognose-vergleich/{anlage_id}` |
| `frontend/src/api/cockpit.ts` | `PrognoseVergleich` Types + API-Funktion |
| `frontend/src/pages/PrognoseVsIst.tsx` | Vergleichsblock mit Chart + Tabelle |

## Abgrenzung

- **Kein eigener Tab/Seite** — Integration in bestehende Views
- **Keine ML-Diagnose** — Accuracy/RMSE/Training gehört zu SFML Stats
- **Rein optional** — ohne SFML ändert sich nichts an EEDC
- **Kein Standalone** — nur mit HA-Integration verfügbar
