# Konzept: Solar Forecast ML — Leichtgewichtige Integration

> Status: Entwurf v2 | Aktualisiert: 2026-03-21 | Auslöser: User-Anfragen (2 User)

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

## Benötigte SFML-Sensoren

Nur 3 Sensoren (statt 20+):

| Sensor | Beschreibung | Verwendung |
|--------|-------------|------------|
| `solar_forecast_ml_today` | Tages-Forecast (kWh) | Header-KPI + Chart-Skalierung |
| `solar_forecast_ml_tomorrow` | Morgen-Forecast (kWh) | Optional: Morgen-Vorschau |
| `solar_forecast_ml_model_accuracy` | Genauigkeit (%) | Optional: Tooltip-Info |

Für die **stündliche Chart-Linie** wird die HA-History des `solar_forecast_ml_today`-Sensors benötigt (oder ein dedizierter Stunden-Sensor, falls vorhanden).

## Technische Umsetzung

### Sensor-Mapping (Backend)

Neue optionale Felder in der bestehenden Sensor-Mapping-Kategorie:

```python
# In sensor_mapping — neue optionale Felder
"ml_forecast_today": "ML Tages-Forecast (kWh)",      # entity_id
"ml_forecast_tomorrow": "ML Morgen-Forecast (kWh)",   # entity_id
"ml_model_accuracy": "ML Modell-Genauigkeit (%)",     # entity_id
```

### Wetter-Endpoint (Backend)

Bestehender `/api/live/{id}/wetter`-Endpoint erweitern:
- Wenn `ml_forecast_today` gemappt → Sensor-Wert lesen und in Response aufnehmen
- Neue Felder in `LiveWetterResponse`: `ml_forecast_kwh`, `ml_accuracy_pct`

### WetterWidget (Frontend)

- `ml_forecast_kwh` als KPI neben der EEDC-Prognose anzeigen
- Stündliche ML-Werte als dritte Linie im Chart (wenn verfügbar)
- Alles hinter `if (data.ml_forecast_kwh != null)` — kein Fallback nötig

### Kein Standalone-Support

ML-Forecast-Sensoren kommen aus HA. Im Standalone-Modus sind die Felder nicht verfügbar und nichts wird angezeigt — kein spezieller Fallback nötig.

## Aufwand

| Komponente | Geschätzt |
|-----------|-----------|
| Sensor-Mapping-Felder | 15 min |
| Backend: Sensor lesen + Response erweitern | 30 min |
| Frontend: KPI im Header | 20 min |
| Frontend: Chart-Linie | 30 min |
| Testen | 30 min |
| **Gesamt** | **~2h** |

## Abgrenzung

- **Kein eigener Tab/Seite** — Integration in bestehende Views
- **Keine ML-Diagnose** — Accuracy/RMSE/Training gehört zu SFML Stats
- **Keine Schatten/Wetter-Sensoren** — EEDC hat eigene Wetterdaten
- **Rein optional** — ohne SFML ändert sich nichts an EEDC
- **Kein Standalone** — nur mit HA-Integration verfügbar
