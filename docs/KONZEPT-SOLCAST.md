# Konzept: Solcast PV Forecast Integration

> **Status:** Planung | **Issue:** #105 | **Zielversion:** v3.17.0
> **Erstellt:** 2026-04-19 | **Datengrundlage:** Live-Abfragen vom 19.04.2026

## Motivation

EEDC nutzt aktuell OpenMeteo für PV-Kurzfristprognosen (GTI-basiert, 16 Tage) und optional SFML-Sensoren aus HA. Solcast bietet satellitenbasierte PV-Prognosen mit 30-Minuten-Auflösung, Konfidenzband (p10/p90) und 7-Tage-Horizont. Die Integration soll als nativer API-Connector UND als HA-Sensor-Anbindung verfügbar sein.

## Datenquellen-Vergleich (Live-Daten, 19.04.2026, Nümbrecht)

### Anlagenparameter

| Parameter | Wert |
|-----------|------|
| Standort | Nümbrecht, NW (50.917°N, 7.590°E) |
| Leistung | 10 kW AC / 12.3 kWp DC |
| Ausrichtung | 180° (Süd) |
| Neigung | 36° |
| Loss Factor | 0.92 (8% Systemverluste) |

### Tagesprognosen im Direktvergleich

| Quelle | Heute (kWh) | Morgen (kWh) | Tag 3 (kWh) |
|--------|-------------|-------------|-------------|
| **Solcast API** (frisch abgerufen) | 57.4 | 64.1 | — (nur 48h bei `hours=48`) |
| **Solcast HA-Integration** (letzter Abruf 18.04. 19:08) | 53.5 | 41.1 | 58.7 |
| **OpenMeteo** (GTI × 12.3 kWp × 0.86 PR) | ~45.7 | ~59.7 | ~55.7 |

**Beobachtungen:**
- Solcast API und HA-Integration weichen um ~7% ab (unterschiedlicher Abrufzeitpunkt + HA-Dampening)
- OpenMeteo liegt ~15% unter Solcast API (andere Wolkenprognose, WMO-Code 63 = Regen)
- Morgen-Prognose: HA (41.1) vs. API (64.1) — große Abweichung weil HA-Daten 14h alt

### Datenformat-Unterschiede

| Eigenschaft | Solcast API | Solcast HA-Integration | OpenMeteo |
|-------------|-------------|------------------------|-----------|
| **Auflösung** | 30 Min | 30 Min + 1 Stunde | 1 Stunde |
| **Einheit** | kW (Leistung) | kW + kWh | W/m² (Einstrahlung) |
| **Was geliefert wird** | PV-Ertrag direkt | PV-Ertrag direkt | GTI-Strahlung |
| **Umrechnung nötig** | kW × 0.5h = kWh | Nein (fertig) | GTI × kWp × PR |
| **Konfidenzband** | p10 / p50 / p90 | p10 / p50 / p90 | Nein |
| **Horizont** | 7 Tage | 7 Tage | 16 Tage |
| **Wetterdaten** | Nein | Nein | Ja (Temperatur, Wolken, Niederschlag) |
| **Zeitzone** | UTC (`period_end`) | Lokal (`period_start`) | Konfigurierbar |
| **Authentifizierung** | Bearer Token | HA verwaltet | Keine |
| **Calls/Tag (Free)** | 10 (1 Standort, 2 Flächen) | 10 (automatisch verteilt) | Unbegrenzt |

### Stundenprofil-Vergleich (19.04.2026, ausgewählte Stunden MESZ)

| Stunde | Solcast API (kW) | Solcast HA (kW) | OpenMeteo (W/m² → ~kW) |
|--------|------------------|-----------------|-------------------------|
| 08:00 | 1.68 | 0.87 | ~0.4 |
| 10:00 | 7.10 | 5.08 | ~3.0 |
| 12:00 | 7.56 | 6.90 | ~5.6 |
| 14:00 | 6.05 | 6.69 | ~5.9 |
| 16:00 | 3.44 | 5.04 | ~3.1 |
| 18:00 | 0.27 | 1.85 | ~3.6 |

Die Unterschiede zwischen API und HA erklären sich durch: unterschiedlichen Abrufzeitpunkt, HA-Dampening, und die Kombination von Forecasts + Estimated Actuals in der HA-Integration.

### Warum Solcast API ≠ HA-Integration

1. **Abrufzeitpunkt:** HA cached Daten vom letzten API-Call (hier 14h alt). API liefert frische Daten.
2. **Dampening:** Die HA-Integration (BJReplay) vergleicht echte Erzeugung mit Solcast-Schätzung und berechnet automatische Korrekturfaktoren pro Stunde.
3. **Estimated Actuals:** HA kombiniert `/forecasts` (Zukunft) mit `/estimated_actuals` (Vergangenheit) zu einem nahtlosen Tagesprofil.
4. **Zeitreferenz:** API nutzt `period_end` in UTC, HA nutzt `period_start` in Lokalzeit.

## Die 3 Solcast-Fälle

### Fall 1: Free-Tier Key direkt in EEDC

**Zielgruppe:** Nutzer ohne HA-Solcast-Integration, Standalone-Nutzer

- 10 API-Calls/Tag, 1 Standort, max 2 Dachflächen (Ost/West)
- Kein ML-Tuning (seit 2021 für kostenlose Nutzer deaktiviert)
- EEDC kontrolliert Cache + Timing vollständig
- Standalone-fähig (kein HA nötig)

**Config-Beispiel:**
```json
{
  "solcast_config": {
    "modus": "api",
    "api_key": "fp6Z...",
    "resource_ids": [
      { "id": "8561-f0cf-1f30-de18", "name": "Süd" }
    ],
    "tier": "free"
  }
}
```

**Cache-TTL:** 2 Stunden (10 Calls/Tag = alle ~2.4h, konservativ)

### Fall 2: Paid Key direkt in EEDC

**Zielgruppe:** Nutzer mit bezahltem Solcast-Abo, die EEDC als primäre Plattform nutzen

- Hunderte bis tausende API-Calls/Tag
- Mehrere Standorte/Sites möglich
- **ML-Tuning (Solcast-seitig):** Modell wird mit echten Ertragsdaten des Standorts kalibriert → deutlich genauere Prognosen (Verschattung, lokale Besonderheiten)
- Forecast-Horizont bis 14 Tage
- Kürzere Update-Intervalle sinnvoll

**Config-Beispiel:**
```json
{
  "solcast_config": {
    "modus": "api",
    "api_key": "paid-key-xxx",
    "resource_ids": [
      { "id": "site-1-id", "name": "Süd" },
      { "id": "site-2-id", "name": "Ost/West" }
    ],
    "tier": "paid"
  }
}
```

**Cache-TTL:** 30 Minuten (genug Kontingent für häufige Updates)

**Vorteile gegenüber Free:**

| Aspekt | Free | Paid |
|--------|------|------|
| API-Calls/Tag | 10 | Hunderte+ |
| Sites/Standorte | 1 (2 Flächen) | Mehrere |
| ML-Tuning (Solcast-seitig) | Nein (seit 2021) | Ja |
| Update-Frequenz (sinnvoll) | ~2h | 15–30 Min |
| Forecast-Horizont | 7 Tage | 14 Tage |
| Genauigkeit (erfahrungsgemäß) | MAE ~25% | MAE <15% (mit Tuning) |

### Fall 3: Via HA-Sensor (kein eigener API-Call)

**Zielgruppe:** Nutzer die Solcast bereits in HA haben (z.B. Rainer mit Paid-Key), API-Kontingent nicht doppelt belasten wollen

- EEDC liest HA-Sensoren via REST-API (wie SFML heute)
- **Kein zusätzlicher Solcast-API-Call** durch EEDC
- HA-Integration verwaltet Abruf-Timing und Dampening
- Stundenprofil + p10/p90 aus Sensor-Attributen (`detailedHourly`)

**Config-Beispiel:**
```json
{
  "solcast_config": {
    "modus": "ha_sensor",
    "ha_sensor": {
      "today_kwh": "sensor.solcast_pv_forecast_prognose_heute",
      "tomorrow_kwh": "sensor.solcast_pv_forecast_prognose_morgen"
    }
  }
}
```

**Cache-TTL:** 5 Minuten (nur lokaler Sensor-Read, kein externer API-Call)

**HA-Sensoren und was sie liefern:**

| Sensor | Wert (Beispiel) | Einheit | Besonderheit |
|--------|-----------------|---------|--------------|
| `prognose_heute` | 53.5 | kWh | Attribut `detailedHourly` enthält Stundenprofil mit p10/p90 |
| `prognose_morgen` | 41.1 | kWh | dto. |
| `prognose_tag_3` bis `tag_7` | 58.7–48.8 | kWh | 7-Tage-Prognose |
| `verbleibende_leistung_heute` | 53.5 | kWh | Restprognose ab jetzt |
| `prognose_aktuelle_stunde` | 0 | **Wh** (!) | Achtung: Wh, nicht kWh! |
| `prognose_nachste_stunde` | 14 | **Wh** (!) | Achtung: Wh, nicht kWh! |
| `spitzenleistung_heute` | 6946 | W | Peak-Leistung |
| `zeitpunkt_spitzenleistung_heute` | 12:30 | — | Zeitpunkt des Peaks |
| `verwendete_api_abrufe` | 0/10 | — | Monitoring |
| `zeitpunkt_letzter_api_abruf` | (Attribut `auto_update_queue`) | — | Nächste geplante Abrufe |

**Wichtig — Attribut `detailedHourly` im Sensor `prognose_heute`:**
```json
[
  {"period_start": "2026-04-19T06:00:00+02:00", "pv_estimate": 0.0138, "pv_estimate10": 0.0034, "pv_estimate90": 0.0311},
  {"period_start": "2026-04-19T07:00:00+02:00", "pv_estimate": 0.2424, "pv_estimate10": 0.0416, "pv_estimate90": 0.5806},
  ...
  {"period_start": "2026-04-19T12:00:00+02:00", "pv_estimate": 6.9034, "pv_estimate10": 1.8456, "pv_estimate90": 10.0},
  ...
]
```

Dieses Attribut enthält das vollständige Stundenprofil mit Konfidenzband — alles was EEDC für die Chart-Darstellung braucht.

## Zusammenspiel mit bestehenden Datenquellen

```
                                    ┌─────────────────────────────┐
                                    │       EEDC Frontend         │
                                    │                             │
                                    │  WetterWidget: KPIs + Chart │
                                    │  PrognoseVsIst: Vergleich   │
                                    │  Aussichten: 7-Tage-Tabelle │
                                    └──────────┬──────────────────┘
                                               │
                                    ┌──────────▼──────────────────┐
                                    │     live_wetter.py          │
                                    │                             │
                                    │  asyncio.gather(            │
                                    │    open_meteo_forecast(),   │  ← immer (GTI + Wetter)
                                    │    solcast_fetch(),         │  ← Fall 1+2: API-Call
                                    │    ha_sensor_batch(),       │  ← Fall 3: Sensor-Read
                                    │  )                          │  ← + SFML (unverändert)
                                    └──────────┬──────────���───────┘
                                               │
                    ┌──────────────────────────┬┴───────────────────────┐
                    │                          │                        │
         ┌──────────▼───────────┐  ┌───��──────▼───────────┐  ┌────────▼───���──────┐
         │    OpenMeteo         │  │    Solcast            │  │    SFML           │
         │                     │  │                       │  │    (unverändert)  │
         │  GTI W/m² → kWh     │  │  Fall 1+2: API       │  │  HA-Sensor        │
         │  + Wetter (T,Wolken)│  │  Fall 3: HA-Sensor   │  │  sfml_today_kwh   │
         │  + 16 Tage Horizont │  │  + p10/p90 Band      │  │  sfml_tomorrow    │
         │  Unbegrenzte Calls  │  │  + Stundenprofil     │  │  sfml_accuracy    │
         └─────────────────────┘  └───────────────────────┘  └───────────────────┘

Rolle:                             Rolle:                      Rolle:
Wetter + Fallback-Prognose         Primäre PV-Prognose         Legacy/Alternative
(wenn kein Solcast)                (wenn konfiguriert)         (optional)
```

**Rangfolge der PV-Prognose:**
1. Solcast (wenn konfiguriert) → primäre Darstellungskurve
2. OpenMeteo GTI → Fallback + immer für Wetterdaten
3. SFML → unabhängige ML-Prognose (optional, parallel)

## Worauf bei der Implementierung zu achten ist

### API-Call-Budget schonen

- **Shared Cache:** Bei gleichem `api_key` + `resource_ids` über mehrere Anlagen → Cache-Key auf `resource_id`-Hash basieren, nicht auf `anlage_id`
- **Fall 3 (HA-Sensor):** Kein Solcast-API-Call nötig, nur HA-REST-Call
- **Tier-abhängiger TTL:** Free=2h, Paid=30min, HA-Sensor=5min

### Zeitzone-Handling

- Solcast API: `period_end` in **UTC**
- Solcast HA: `period_start` in **Lokalzeit** (Europe/Berlin)
- OpenMeteo: Konfigurierbar (EEDC nutzt Europe/Berlin)
- Alle Quellen auf Europe/Berlin normalisieren vor Vergleich/Darstellung

### Einheiten-Fallen

- Solcast API `pv_estimate`: **kW** (Leistung) → kWh = kW × 0.5h (30-Min-Periode)
- HA `prognose_aktuelle_stunde`: **Wh** (nicht kWh!)
- HA `prognose_heute`: **kWh**
- OpenMeteo `shortwave_radiation`: **W/m²** → kWh = (W/m² × Fläche × PR) / 1000

### OpenMeteo als Fallback

- OpenMeteo liefert Wetterdaten (Temperatur, Wolken, Niederschlag, Sonnenstunden) die Solcast nicht hat
- OpenMeteo wird IMMER abgerufen (für Wetter-Widget)
- PV-Prognose aus OpenMeteo nur als Fallback wenn kein Solcast konfiguriert

### Pydantic-Lesson-Learned

Neue Response-Felder (`solcast_prognose_kwh`, `solcast_p10_kwh`, etc.) MÜSSEN auch im Pydantic `LiveWetterResponse`-Model definiert werden, sonst werden sie vom `response_model` entfernt.

## Hintergrund

Diskussion zwischen Gernot und Rainer (April 2026):
- Rainer nutzt Solcast mit Paid-Key, hat umfassende Erfahrung mit verschiedenen Prognose-Quellen
- Solcast und OpenMeteo sind laut Rainer "Top 1+2"
- SFML (Tom-HA) braucht 3-4 Tage nach Wetterwechsel um sich zu kalibrieren → Solcast stabiler
- DWD und Solcast haben Satellitendaten + Rechenpower → genauer als lokale KI
- BKW-Nutzer profitieren besonders von guter Restprognose (Verbrauchsplanung nach 18:00)

Rainers CSV-Analyse (Jan–Apr 2026, 63 Tage): Solcast **ohne ML-Tuning** (Free) hat MAE 25.2% vs. OpenMeteo 22.4%. **Mit** ML-Tuning (Paid) ist Solcast deutlich besser.
