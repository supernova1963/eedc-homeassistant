# Konzept: ML-Prognose Integration (Solar Forecast ML)

> Status: Entwurf | Erstellt: 2026-03-20 | Auslöser: User-Anfragen

## Problem

User haben [Solar Forecast ML](https://github.com/Zara-Toorox/Solar-Forecast-ML) in HA installiert und sehen ~20 Sensor-Entities mit Rohzahlen. Es fehlt:
- Grafische Aufbereitung im Kontext der eigenen PV-Anlage
- Forecast vs. tatsächliche Produktion im Zeitverlauf
- Einordnung der Modell-Qualität (wird das Modell besser? Wie saisonabhängig?)
- Verknüpfung mit Eigenverbrauch, Einspeisung, Speicher

## Lösung

Neuer Tab **"ML-Prognose"** unter Aussichten, der über Sensor-Mapping die Solar-Forecast-ML Entities einliest und anlagenbezogen visualisiert.

**Fokus:** Die ML-Prognose steht im Mittelpunkt, IST-Daten dienen als Referenz. Kein direkter Vergleich mit der EEDC-eigenen Prognose — die bleibt eigenständig im KurzfristTab.

## Verfügbare Sensoren

### Forecast

| Sensor | Beschreibung | Nutzung in EEDC |
|--------|-------------|-----------------|
| `solar_forecast_ml_today` | Tages-Forecast (kWh) | Hauptprognose, Vergleich mit IST |
| `solar_forecast_ml_tomorrow` | Morgen (kWh) | Vorschau-Karte |
| `solar_forecast_ml_day_after_tomorrow` | Übermorgen (kWh) | Vorschau-Karte |
| `solar_forecast_ml_next_hour` | Nächste Stunde (kWh) | Live-KPI |
| `solar_forecast_ml_peak_production_hour` | Beste Stunde heute | Highlight im Tagesverlauf |

### Produktion

| Sensor | Beschreibung | Nutzung in EEDC |
|--------|-------------|-----------------|
| `solar_forecast_ml_production_time` | Start/Ende/Dauer | Produktionsfenster-Balken |
| `solar_forecast_ml_max_peak_today` | Spitzenleistung heute (W) | KPI-Card |
| `solar_forecast_ml_max_peak_all_time` | Allzeit-Peak (W) | Referenz-KPI |
| `solar_forecast_ml_expected_daily_production` | Tages-Soll | Soll/IST-Fortschritt |

### Statistik

| Sensor | Beschreibung | Nutzung in EEDC |
|--------|-------------|-----------------|
| `solar_forecast_ml_average_yield` | Kumulierter Durchschnitt | Langzeit-KPI |
| `solar_forecast_ml_average_yield_7_days` | 7-Tage-Schnitt | Trend-Chart |
| `solar_forecast_ml_average_yield_30_days` | 30-Tage-Schnitt | Trend-Chart |
| `solar_forecast_ml_monthly_yield` | Monats-Summe | Monats-KPI |
| `solar_forecast_ml_weekly_yield` | Wochen-Summe | Wochen-KPI |

### KI & Diagnostik

| Sensor | Beschreibung | Nutzung in EEDC |
|--------|-------------|-----------------|
| `solar_forecast_ml_model_state` | Aktives Modell (AI / Rule-Based) | Status-Badge |
| `solar_forecast_ml_model_accuracy` | Genauigkeit (%) | Haupt-KPI + Verlauf |
| `solar_forecast_ml_ai_rmse` | Modellqualität (Text) | Qualitäts-Badge |
| `solar_forecast_ml_training_samples` | Trainings-Datensätze | Info-KPI |
| `solar_forecast_ml_ml_metrics` | MAE, RMSE, R² | Detail-Metriken |

### Schatten & Wetter

| Sensor | Beschreibung | Nutzung in EEDC |
|--------|-------------|-----------------|
| `solar_forecast_ml_shadow_current` | Aktueller Schattenlevel | Status-Indikator |
| `solar_forecast_ml_performance_loss` | Schatten-Verlust (%) | KPI-Card |
| `solar_forecast_ml_cloudiness_trend_1h` | 1h-Wolkentrend | Trend-Pfeil |
| `solar_forecast_ml_cloudiness_trend_3h` | 3h-Wolkentrend | Trend-Pfeil |
| `solar_forecast_ml_cloudiness_volatility` | Wetter-Stabilität | Stabilitäts-Index |

## UI-Konzept

### Sektion 1: Tages-Überblick (Hero)

```
┌─────────────────────────────────────────────────────────────┐
│  ML-Prognose Heute         Morgen          Übermorgen       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ 12.4 kWh │  │ 8.2 kWh  │  │ 14.1 kWh │  │ 11.3 kWh │  │
│  │ Forecast  │  │ IST bisher│ │ Morgen   │  │ Übermorgen│   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
│                                                             │
│  Modell: AI ✓  |  Genauigkeit: 94%  |  Nächste Stunde: 1.8 │
└─────────────────────────────────────────────────────────────┘
```

**KPI-Cards:**
- ML-Forecast heute (kWh) — Hauptwert
- IST bisher (kWh) — aus EEDC-eigenen Daten (Live oder Monatsdaten)
- Forecast morgen + übermorgen — Vorschau
- Modell-Status (AI/Rule-Based), Genauigkeit, Next-Hour als Fußzeile

### Sektion 2: Tagesverlauf — Forecast vs. IST

```
kWh
 3 │          ████
   │       ████████ ░░
 2 │     ████████████░░░░
   │   ████████████████░░░░
 1 │ ████████████████████░░░░
   │████████████████████████░░
 0 └──────────────────────────
   06  08  10  12  14  16  18  Uhr

   ████ IST-Produktion   ░░░░ ML-Forecast (Rest)
   ─── Produktionsfenster (Start → Ende)
   ★ Peak-Stunde
```

**Chart-Typ:** Stacked Area / ComposedChart
- IST-Produktion als gefüllte Fläche (gelb)
- ML-Forecast als Umriss / halbtransparente Fläche darüber (orange gestrichelt)
- Vertikale Linie bei "jetzt"
- Peak-Stunde markiert
- Produktionsfenster (Start/Ende) als Hintergrund-Band

**Datenquelle:** IST aus EEDC Live-Daten (MQTT/HA), Forecast aus ML-Sensoren. Stundenwerte aus HA-History.

### Sektion 3: Modell-Qualität

```
┌─────────────────────────────────────────────────┐
│  Modell-Qualität                                │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ 94.2%    │  │ 0.42 kWh │  │ 0.89     │      │
│  │ Accuracy │  │ RMSE     │  │ R²       │      │
│  │ ▲ +2.1%  │  │ ▼ -0.08  │  │ ▲ +0.03  │      │
│  └──────────┘  └──────────┘  └──────────┘      │
│                                                  │
│  Accuracy-Verlauf (30 Tage)                     │
│  100% ┬─────────────────────────────────        │
│   90% ┤  ~~∿∿~~──~~∿∿──────∿∿──────────        │
│   80% ┤                                         │
│   70% ┼─────────────────────────────────        │
│       Feb 20    Mär 01    Mär 10    Mär 20      │
│                                                  │
│  Training: 847 Samples  |  Qualität: Excellent   │
└─────────────────────────────────────────────────┘
```

**KPI-Cards:** Accuracy, RMSE, R² — jeweils mit Trend-Pfeil (Verbesserung/Verschlechterung)
**Line-Chart:** Accuracy über 30 Tage (aus HA-History des `model_accuracy` Sensors)
**Info:** Training-Samples, Modellqualitäts-Badge

### Sektion 4: Schatten & Wetter

```
┌─────────────────────────────────────────────────┐
│  Wetter & Verschattung                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ Leicht   │  │ -3.2%    │  │ Stabil   │      │
│  │ Schatten │  │ Verlust  │  │ Wetter   │      │
│  └──────────┘  └──────────┘  └──────────┘      │
│                                                  │
│  Wolkentrend:  1h ☀→⛅  |  3h ⛅→☁             │
│                                                  │
│  Tages-Heatmap (Schatten-Intensität)            │
│  06 ░░░░████████████████░░░░░░ 20               │
│     klar  leicht  mittel  stark                  │
└─────────────────────────────────────────────────┘
```

**KPI-Cards:** Aktueller Schatten-Level, Performance-Loss, Wetter-Stabilität
**Trends:** 1h + 3h Wolkentrend als Pfeile/Icons
**Heatmap:** Tagesverlauf der Verschattung (aus HA-History)

### Sektion 5: Ertrags-Trends

```
┌─────────────────────────────────────────────────┐
│  Ertrags-Statistik                              │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐      │
│  │ 8.4 kWh  │  │ 7.1 kWh  │  │ 156 kWh  │     │
│  │ Ø 7 Tage │  │ Ø 30 Tage│  │ Monat    │      │
│  └──────────┘  └──────────┘  └──────────┘      │
│                                                  │
│  Rolling Average + Tagesproduktion              │
│  kWh                                            │
│  15 │    *                                      │
│  10 │  * * *  *     *  *                        │
│   5 │ * ──────── * ────────── *                 │
│   0 └──────────────────────────                 │
│     Mär 01        Mär 10        Mär 20          │
│                                                  │
│     * Tagesertrag   ─── 7d-Schnitt              │
└─────────────────────────────────────────────────┘
```

**KPI-Cards:** 7d-Schnitt, 30d-Schnitt, Monats-Summe, Wochen-Summe
**Scatter + Line:** Tägliche Erträge als Punkte, 7d/30d-Schnitt als Linien

## Technische Umsetzung

### Anbindung

Über das **bestehende Sensor-Mapping** — keine neue Infrastruktur nötig:

1. Neue Mapping-Kategorie `ml_forecast` im Sensor-Mapping-Wizard
2. User ordnet seine `solar_forecast_ml_*` Entities den EEDC-Feldern zu
3. Backend liest Werte via bestehenden HA-Statistics-Service (für History) bzw. HA-State-API (für Live-Werte)

### Neue Dateien

**Backend:**
- `api/routes/ml_forecast.py` — Endpoints für ML-Prognose-Daten
- `services/ml_forecast_service.py` — Liest ML-Sensoren via HA, aggregiert History

**Frontend:**
- `pages/aussichten/MLPrognoseTab.tsx` — Neuer Tab unter Aussichten
- `components/ml-forecast/` — Extrahierte Sektionen (ForecastHero, ModelQuality, ShadowWeather, YieldTrends)

### Sensor-Mapping-Erweiterung

```python
# Neue Felder in sensor_mapping
ML_FORECAST_FIELDS = {
    "ml_forecast_today": "Tages-Forecast (kWh)",
    "ml_forecast_tomorrow": "Morgen-Forecast (kWh)",
    "ml_forecast_next_hour": "Nächste Stunde (kWh)",
    "ml_model_accuracy": "Modell-Genauigkeit (%)",
    "ml_model_state": "Modell-Status",
    "ml_rmse": "RMSE",
    "ml_shadow_current": "Schatten-Level",
    "ml_performance_loss": "Schatten-Verlust (%)",
    "ml_peak_today": "Spitzenleistung heute (W)",
    "ml_production_time": "Produktionszeit",
    # ... weitere nach Bedarf
}
```

### HA-History für Charts

Für die Verlaufs-Charts (Accuracy, Tagesverlauf, Rolling Averages) wird die HA-History-API genutzt:
- `GET /api/history/period/<start_time>?filter_entity_id=sensor.solar_forecast_ml_*`
- Der bestehende `ha_statistics_service.py` kann erweitert werden

### Erkennung

Optional: Automatische Erkennung ob Solar Forecast ML installiert ist, indem nach `sensor.solar_forecast_ml_*` Entities gesucht wird. Wenn vorhanden, Tab einblenden und Mapping vorschlagen.

## Abgrenzung

- **Kein direkter Vergleich** EEDC-Prognose vs. ML-Prognose — beide stehen eigenständig
- IST-Daten als neutrale Referenz, nicht als Schiedsrichter
- Der Tab ist optional — nur sichtbar wenn ML-Sensoren gemappt sind
- Kein Import von ML-Forecast-Werten in Monatsdaten oder Cockpit

## Offene Fragen

1. Liefert Solar Forecast ML stündliche Werte oder nur Tageswerte? (Für Tagesverlauf-Chart relevant)
2. Welche Sensoren haben History in HA? (Manche könnten `state_class: measurement` fehlen)
3. Gibt es neben Solar Forecast ML weitere ML-Tools mit ähnlichen Sensoren? (Solcast, Forecast.Solar)
4. Soll der Tab auch im Standalone-Modus (ohne HA) sichtbar sein? (Vermutlich nein)
