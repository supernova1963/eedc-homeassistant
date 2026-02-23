# Community Server - Benötigte API-Endpoints

> **Ziel:** Erweiterung von eedc-community (energy.raunet.eu) für die vollständige Community-Feature-Unterstützung in eedc-homeassistant.

---

## Aktueller Stand

### Vorhandene Endpoints (funktionieren bereits)

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/api/status` | GET | Server-Status |
| `/api/share` | POST | Anlagen-Daten anonym teilen |
| `/api/delete/{hash}` | DELETE | Geteilte Daten löschen |
| `/api/benchmark/{hash}` | GET | Benchmark für eine Anlage |

### Benchmark-Response (aktuell)

```json
{
  "anlage": {
    "kwp": 10.0,
    "region": "BY",
    "ausrichtung": "sued",
    "neigung_grad": 30,
    "installation_jahr": 2022,
    "speicher_kwh": 10.0,
    "hat_waermepumpe": true,
    "hat_eauto": true,
    "hat_wallbox": true,
    "hat_balkonkraftwerk": false,
    "monatswerte": [...]
  },
  "benchmark": {
    "spez_ertrag_anlage": 950.5,
    "spez_ertrag_durchschnitt": 920.0,
    "spez_ertrag_region": 935.0,
    "rang_gesamt": 15,
    "anzahl_anlagen_gesamt": 150,
    "rang_region": 5,
    "anzahl_anlagen_region": 25
  },
  "benchmark_erweitert": {
    "speicher": {...},
    "waermepumpe": {...},
    "eauto": {...},
    "wallbox": {...},
    "balkonkraftwerk": {...}
  },
  "zeitraum": "12_monate",
  "zeitraum_label": "Letzte 12 Monate"
}
```

---

## Benötigte neue Endpoints

### Priorität 1: Globale Statistiken

#### `GET /api/statistics/global`

Community-weite Statistiken für den Statistiken-Tab.

**Response:**
```json
{
  "anzahl_anlagen": 150,
  "anzahl_regionen": 12,
  "durchschnitt": {
    "kwp": 9.5,
    "spez_ertrag": 920.0,
    "speicher_kwh": 8.5,
    "autarkie_prozent": 65.0,
    "eigenverbrauch_prozent": 45.0
  },
  "ausstattungsquoten": {
    "speicher": 75.5,
    "waermepumpe": 35.2,
    "eauto": 42.0,
    "wallbox": 38.5,
    "balkonkraftwerk": 12.0
  },
  "typische_anlage": {
    "kwp": 10.0,
    "ausrichtung": "sued",
    "neigung_grad": 30,
    "speicher_kwh": 10.0
  },
  "stand": "2026-02-21T12:00:00Z"
}
```

---

### Priorität 2: Verteilungen & Rankings

#### `GET /api/distributions/{metric}`

Verteilungsdaten für Histogramme.

**Parameter:**
- `metric`: `kwp`, `spez_ertrag`, `speicher_kwh`, `autarkie`, `jaz`, `eauto_pv_anteil`

**Response:**
```json
{
  "metric": "spez_ertrag",
  "einheit": "kWh/kWp",
  "bins": [
    { "von": 700, "bis": 750, "anzahl": 5 },
    { "von": 750, "bis": 800, "anzahl": 12 },
    { "von": 800, "bis": 850, "anzahl": 25 },
    { "von": 850, "bis": 900, "anzahl": 35 },
    { "von": 900, "bis": 950, "anzahl": 40 },
    { "von": 950, "bis": 1000, "anzahl": 20 },
    { "von": 1000, "bis": 1050, "anzahl": 10 },
    { "von": 1050, "bis": 1100, "anzahl": 3 }
  ],
  "statistik": {
    "min": 720,
    "max": 1080,
    "median": 895,
    "durchschnitt": 890,
    "stdabweichung": 85
  }
}
```

#### `GET /api/rankings/{category}?limit=10`

Anonyme Top-Listen.

**Parameter:**
- `category`: `spez_ertrag`, `autarkie`, `speicher_effizienz`, `jaz`, `eauto_pv_anteil`
- `limit`: Anzahl (default: 10)

**Response:**
```json
{
  "category": "spez_ertrag",
  "label": "Spezifischer Ertrag",
  "einheit": "kWh/kWp",
  "zeitraum": "12_monate",
  "ranking": [
    { "rang": 1, "wert": 1080, "region": "BY", "kwp": 12.0 },
    { "rang": 2, "wert": 1065, "region": "BW", "kwp": 8.5 },
    { "rang": 3, "wert": 1052, "region": "BY", "kwp": 15.0 },
    ...
  ],
  "eigener_rang": 15,
  "eigener_wert": 950.5
}
```

---

### Priorität 2: Regionale Daten

#### `GET /api/statistics/regional`

Alle Regionen mit Durchschnittswerten (für Karte).

**Response:**
```json
{
  "regionen": [
    {
      "code": "BY",
      "name": "Bayern",
      "anzahl_anlagen": 35,
      "durchschnitt_spez_ertrag": 945.0,
      "durchschnitt_autarkie": 68.0
    },
    {
      "code": "BW",
      "name": "Baden-Württemberg",
      "anzahl_anlagen": 28,
      "durchschnitt_spez_ertrag": 935.0,
      "durchschnitt_autarkie": 65.0
    },
    ...
  ],
  "gesamt_durchschnitt": 920.0
}
```

#### `GET /api/statistics/regional/{region}`

Detail-Statistiken für eine Region.

**Response:**
```json
{
  "region": "BY",
  "name": "Bayern",
  "anzahl_anlagen": 35,
  "statistiken": {
    "spez_ertrag": { "durchschnitt": 945, "min": 780, "max": 1080 },
    "autarkie": { "durchschnitt": 68, "min": 35, "max": 92 },
    "speicher_quote": 82.0,
    "waermepumpe_quote": 40.0
  },
  "top_5": [
    { "rang": 1, "spez_ertrag": 1080, "kwp": 12.0 },
    ...
  ]
}
```

---

### Priorität 2: Monatliche Durchschnitte

#### `GET /api/statistics/monthly-averages?monate=12`

Monatliche Community-Durchschnitte für Chart-Vergleiche.

**Response:**
```json
{
  "monate": [
    { "jahr": 2025, "monat": 3, "spez_ertrag_avg": 65.0, "anzahl_anlagen": 142 },
    { "jahr": 2025, "monat": 4, "spez_ertrag_avg": 95.0, "anzahl_anlagen": 145 },
    { "jahr": 2025, "monat": 5, "spez_ertrag_avg": 120.0, "anzahl_anlagen": 148 },
    ...
  ]
}
```

---

### Priorität 3: Trends

#### `GET /api/trends/{period}`

Zeitliche Entwicklungen.

**Parameter:**
- `period`: `12_monate`, `24_monate`, `gesamt`

**Response:**
```json
{
  "period": "12_monate",
  "trends": {
    "anzahl_anlagen": [
      { "monat": "2025-03", "wert": 120 },
      { "monat": "2025-04", "wert": 125 },
      ...
    ],
    "durchschnitt_kwp": [
      { "monat": "2025-03", "wert": 9.2 },
      { "monat": "2025-04", "wert": 9.4 },
      ...
    ],
    "speicher_quote": [
      { "monat": "2025-03", "wert": 70.0 },
      { "monat": "2025-04", "wert": 72.5 },
      ...
    ],
    "waermepumpe_quote": [...],
    "eauto_quote": [...]
  }
}
```

#### `GET /api/trends/degradation`

Ertrags-Analyse nach Anlagenalter.

**Response:**
```json
{
  "nach_alter": [
    { "alter_jahre": 1, "anzahl": 25, "durchschnitt_spez_ertrag": 950 },
    { "alter_jahre": 2, "anzahl": 35, "durchschnitt_spez_ertrag": 940 },
    { "alter_jahre": 3, "anzahl": 30, "durchschnitt_spez_ertrag": 925 },
    { "alter_jahre": 4, "anzahl": 20, "durchschnitt_spez_ertrag": 915 },
    { "alter_jahre": 5, "anzahl": 15, "durchschnitt_spez_ertrag": 900 }
  ],
  "durchschnittliche_degradation_prozent_jahr": 1.2
}
```

---

### Priorität 3: Erweiterte Komponenten-Vergleiche

#### `GET /api/components/speicher/by-class`

Speicher-Vergleich nach Kapazitätsklassen.

**Response:**
```json
{
  "klassen": [
    {
      "von_kwh": 5,
      "bis_kwh": 10,
      "anzahl": 45,
      "durchschnitt_wirkungsgrad": 88.5,
      "durchschnitt_zyklen": 280,
      "durchschnitt_netz_anteil": 15.0
    },
    {
      "von_kwh": 10,
      "bis_kwh": 15,
      "anzahl": 35,
      "durchschnitt_wirkungsgrad": 90.2,
      "durchschnitt_zyklen": 250,
      "durchschnitt_netz_anteil": 12.0
    },
    {
      "von_kwh": 15,
      "bis_kwh": null,
      "anzahl": 20,
      "durchschnitt_wirkungsgrad": 91.0,
      "durchschnitt_zyklen": 220,
      "durchschnitt_netz_anteil": 10.0
    }
  ]
}
```

#### `GET /api/components/waermepumpe/by-region`

JAZ nach Region (Klimazone).

**Response:**
```json
{
  "regionen": [
    { "region": "BY", "anzahl": 15, "durchschnitt_jaz": 3.8 },
    { "region": "BW", "anzahl": 12, "durchschnitt_jaz": 3.9 },
    { "region": "NW", "anzahl": 8, "durchschnitt_jaz": 3.6 },
    ...
  ]
}
```

---

## Implementierungsreihenfolge

### Phase 1 (Basis-Erweiterung)
1. `GET /api/statistics/global` - Globale Stats
2. `GET /api/statistics/monthly-averages` - Monatliche Durchschnitte

### Phase 2 (Verteilungen & Rankings)
3. `GET /api/distributions/{metric}` - Histogramm-Daten
4. `GET /api/rankings/{category}` - Top-Listen
5. `GET /api/statistics/regional` - Regionale Übersicht

### Phase 3 (Deep-Dives)
6. `GET /api/statistics/regional/{region}` - Regional-Details
7. `GET /api/components/speicher/by-class` - Speicher nach Klasse
8. `GET /api/components/waermepumpe/by-region` - WP nach Region

### Phase 4 (Trends)
9. `GET /api/trends/{period}` - Zeitliche Trends
10. `GET /api/trends/degradation` - Degradations-Analyse

---

## Technische Hinweise

### Caching
- Globale Statistiken: Cache 1 Stunde
- Regionale Daten: Cache 1 Stunde
- Rankings: Cache 15 Minuten
- Trends: Cache 6 Stunden

### Performance
- Verteilungen vorberechnen (Cronjob)
- Rankings bei Share/Delete aktualisieren
- Regionale Aggregationen materialisieren

### Anonymität
- Keine Anlage-Hashes in Rankings
- Nur Region + kWp als Identifikation
- Min. 3 Anlagen pro Gruppe für Anzeige

---

## Frontend-Anpassungen nach Server-Update

Nach Implementierung der Endpoints in eedc-community müssen folgende Frontend-Komponenten erweitert werden:

| Tab | Komponente | Neuer Endpoint |
|-----|------------|----------------|
| PV-Ertrag | Heatmap | `monthly-averages` |
| PV-Ertrag | Histogramm | `distributions/spez_ertrag` |
| Regional | Deutschland-Karte | `statistics/regional` |
| Regional | Bundesland-Detail | `statistics/regional/{region}` |
| Komponenten | Speicher-Klassen | `components/speicher/by-class` |
| Komponenten | WP nach Region | `components/waermepumpe/by-region` |
| Statistiken | Ausstattungsquoten | `statistics/global` |
| Statistiken | Top-10-Listen | `rankings/{category}` |
| Trends | Community-Trends | `trends/{period}` |
| Trends | Degradation | `trends/degradation` |

---

## Implementierungs-Checkliste

### Phase 1: Server-Basis (eedc-community)

| # | Aufgabe | Status |
|---|---------|--------|
| 1.1 | `GET /api/statistics/global` implementieren | ✅ |
| 1.2 | `GET /api/statistics/monthly-averages` implementieren | ✅ |
| 1.3 | `GET /api/statistics/regional` implementieren | ✅ |
| 1.4 | `GET /api/statistics/regional/{region}` implementieren | ✅ |
| 1.5 | Server deployen & testen | ✅ |

### Phase 2: Server-Erweiterung Verteilungen & Rankings

| # | Aufgabe | Status |
|---|---------|--------|
| 2.1 | `GET /api/statistics/distributions/{metric}` implementieren | ✅ |
| 2.2 | `GET /api/statistics/rankings/{category}` implementieren | ✅ |
| 2.3 | Server deployen & testen | ✅ |

### Phase 3: Server-Erweiterung Deep-Dives

| # | Aufgabe | Status |
|---|---------|--------|
| 3.1 | `GET /api/components/speicher/by-class` implementieren | ✅ |
| 3.2 | `GET /api/components/waermepumpe/by-region` implementieren | ✅ |
| 3.3 | `GET /api/components/eauto/by-usage` implementieren | ✅ |
| 3.4 | Server deployen & testen | ✅ |

### Phase 4: Server-Erweiterung Trends

| # | Aufgabe | Status |
|---|---------|--------|
| 4.1 | `GET /api/trends/{period}` implementieren | ✅ |
| 4.2 | `GET /api/trends/degradation` implementieren | ✅ |
| 4.3 | Server deployen & testen | ✅ |

### Phase 5: Frontend-Integration (eedc-homeassistant)

| # | Aufgabe | Abhängigkeit | Status |
|---|---------|--------------|--------|
| 5.1 | Backend: Proxy-Endpoints für neue Server-APIs | Phase 1-4 | ✅ |
| 5.2 | Statistiken Tab: Ausstattungsquoten einbauen | 1.1 | ✅ |
| 5.3 | PV-Ertrag Tab: Monatliche Vergleichslinie (echte Daten) | 1.2 | ✅ |
| 5.4 | PV-Ertrag Tab: Histogramm implementieren | 2.1 | ✅ |
| 5.5 | Statistiken Tab: Top-10-Listen einbauen | 2.2 | ✅ |
| 5.6 | Regional Tab: Deutschland-Karte implementieren | 2.3 | ✅ |
| 5.7 | Regional Tab: Bundesland-Details erweitern (WP/E-Auto/Wallbox/BKW) | 3.1 | ✅ |
| 5.8 | Komponenten Tab: Speicher nach Kapazitätsklassen | 3.2 | ✅ |
| 5.9 | Komponenten Tab: WP JAZ nach Region | 3.3 | ✅ |
| 5.10 | Trends Tab: Community-Trends einbauen | 4.1 | ✅ |
| 5.11 | Trends Tab: Degradations-Analyse einbauen | 4.2 | ✅ |

### Phase 6: Finalisierung

| # | Aufgabe | Status |
|---|---------|--------|
| 6.1 | Vollständiger Test aller Features | ✅ |
| 6.2 | Dokumentation aktualisieren | ✅ |
| 6.3 | Release vorbereiten | ✅ |
