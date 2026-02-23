# Community Feature - Vision & Implementierungsplan

> **Status:** Frontend v1.0 abgeschlossen (wartet auf Server-Erweiterungen) | **Version:** 1.0 | **Letzte Aktualisierung:** 2026-02-21

## Übersicht

Community wird als **eigenständiger Hauptmenüpunkt** auf Augenhöhe mit Cockpit, Auswertungen und Aussichten positioniert. Es soll das **Highlight und Differenzierungsmerkmal** von EEDC werden.

---

## Tab-Struktur (6 Tabs)

| Tab | Fokus | Status |
|-----|-------|--------|
| **Übersicht** | Ranking, Badges, Achievements, Quick-Stats | ⬜ Geplant |
| **PV-Ertrag** | Heatmaps, Zeitreihen, Verteilungen, Wetter-Korrelation | ⬜ Geplant |
| **Komponenten** | Deep-Dives für Speicher, WP, E-Auto, Wallbox, BKW | ⬜ Geplant |
| **Regional** | Bundesland-Karten, regionale Rankings, Wetter-Einfluss | ⬜ Geplant |
| **Trends** | Community-Trends, Degradation, Saisonale Muster | ⬜ Geplant |
| **Statistiken** | Verteilungen, Durchschnitte, Ausstattungsquoten | ⬜ Geplant |

---

## Tab 1: Übersicht (Dashboard-Charakter)

### Gamification & Engagement

- **Rang-Badges:** Top 10%, Top 25%, Top 50%
- **Achievements:**
  - "Autarkiemeister" - Autarkie > 80%
  - "Effizienzwunder" - Speicher-Wirkungsgrad > 95%
  - "Solarprofi" - Spez. Ertrag Top 10%
  - "Grüner Fahrer" - E-Auto PV-Anteil > 70%
  - "Wärmekönig" - JAZ > 4.0
  - "Dauerbrenner" - 12 Monate über Durchschnitt
- **Streak-Counter:** "X Monate über Durchschnitt"
- **Verbesserungs-Tipps:** KI-basierte Empfehlungen basierend auf Schwächen

### Quick-Stats Karten

- Aktuelle Position (gesamt + regional) mit Trend-Pfeil
- Stärken (Top 3 KPIs) / Schwächen (Bottom 3 KPIs)
- Vergleich vs. Vormonat / Vorjahr
- Community-Teilnehmer gesamt

### Visualisierungen

- Radar-Chart: Eigene Performance vs. Community-Durchschnitt (6 Achsen)
- Position auf Glockenkurve (wo liege ich?)

---

## Tab 2: PV-Ertrag (Detailvergleich)

### Haupt-Visualisierungen

1. **Monats-Heatmap**
   - 12 Monate × mehrere Jahre
   - Farbcodiert: Rot (unter Durchschnitt) → Grün (über Durchschnitt)
   - Zeigt sofort saisonale Muster und Ausreißer

2. **Verteilungskurve (Histogramm)**
   - Alle Community-Anlagen als Balken
   - Eigene Position hervorgehoben
   - Perzentil-Anzeige: "Du bist besser als X% der Anlagen"

3. **Zeitreihen-Vergleich**
   - Mein spez. Ertrag vs. Community-Durchschnitt
   - Gleitender Durchschnitt
   - Trend-Linien

4. **Wetter-Korrelation**
   - Scatter-Plot: Sonnenstunden vs. Ertrag
   - Eigene Anlage vs. Community-Trend
   - Zeigt Effizienz unabhängig vom Wetter

### Erweiterte Metriken

| Metrik | Beschreibung |
|--------|-------------|
| Performance Ratio (PR) | Tatsächlicher vs. theoretischer Ertrag |
| Normalisierter Ertrag | Nach Ausrichtung/Neigung normalisiert |
| Degradations-Rate | Jährlicher Ertragsrückgang |
| Konsistenz-Score | Wie gleichmäßig performt die Anlage? |

---

## Tab 3: Komponenten (Deep-Dives)

### Speicher

| KPI | Vergleich | Visualisierung |
|-----|-----------|----------------|
| Vollzyklen/Jahr | vs. Community | Balken |
| Wirkungsgrad | vs. Community nach Kapazitätsklasse | Boxplot |
| PV-Ladeanteil | vs. Community | Gauge |
| Optimierungspotenzial | Berechnet | Anzeige in € |

**Zusätzliche Analysen:**
- Ladestrategie-Vergleich (wann wird geladen?)
- Effizienz nach Kapazitätsklassen (5-10 kWh, 10-15 kWh, >15 kWh)
- Saisonale Nutzungsmuster

### Wärmepumpe

| KPI | Vergleich | Visualisierung |
|-----|-----------|----------------|
| JAZ | vs. Community + vs. Klimazone | Balken + Karte |
| Stromverbrauch | vs. ähnliche Gebäude | Balken |
| Heizenergie/Stromverbrauch | Effizienz-Ratio | Gauge |
| Saisonale Effizienz | Monatskurve | Line-Chart |

**Zusätzliche Analysen:**
- Vergleich nach WP-Typ (Luft-Wasser vs. Sole)
- Vergleich nach Vorlauftemperatur
- Warmwasser-Anteil am Gesamtverbrauch

### E-Auto

| KPI | Vergleich | Visualisierung |
|-----|-----------|----------------|
| PV-Ladeanteil | vs. Community | Gauge + Ranking |
| Verbrauch/100km | vs. Community | Balken |
| V2H-Nutzung | vs. Community (falls vorhanden) | Balken |
| Ladezeit-Verteilung | Wann wird geladen? | Stacked Bar |

**Zusätzliche Analysen:**
- Ladestrategien-Vergleich (PV-optimiert vs. sofort)
- Jahreslaufleistung im Vergleich
- Stromkosten-Ersparnis durch PV-Laden

### Wallbox

| KPI | Vergleich | Visualisierung |
|-----|-----------|----------------|
| PV-Ladeanteil | vs. Community | Gauge |
| Ladung/Monat | vs. Community nach kW-Klasse | Balken |
| Ladevorgänge | vs. Community | Trend |

### Balkonkraftwerk

| KPI | Vergleich | Visualisierung |
|-----|-----------|----------------|
| Spez. Ertrag | vs. Community | Balken + Ranking |
| Eigenverbrauchsquote | vs. Community | Gauge |
| Speicher-Nutzung | Falls vorhanden | Balken |

---

## Tab 4: Regional

### Deutschland-Karte (Choropleth)

- 16 Bundesländer farbcodiert nach Durchschnitts-Ertrag
- Eigenes Bundesland hervorgehoben
- Klickbar für Drill-Down

### Regionale Insights

| Insight | Darstellung |
|---------|-------------|
| Wetter-Einfluss | "Deine Region: -15% Sonnenstunden vs. Bayern" |
| Position in Region | "Rang 5 von 45 in Baden-Württemberg" |
| Regionale Besonderheiten | Durchschnittliche Ausrichtung, Speicher-Quote |

### Vergleichs-Optionen

- Eigenes Bundesland vs. Gesamt-Deutschland
- Eigenes Bundesland vs. anderes Bundesland (wählbar)
- Ähnliche Anlagen in der Region (nach kWp, Ausrichtung)

### Wetter-Korrelation Regional

- Sonnenstunden-Karte
- Ertrag normalisiert nach Wetter
- "Echte" Performance unabhängig vom Standort

---

## Tab 5: Trends

### Community-Trends

| Trend | Zeitraum | Visualisierung |
|-------|----------|----------------|
| Speicher-Adoption | 12 Monate | Line-Chart: % mit Speicher |
| WP-Adoption | 12 Monate | Line-Chart: % mit WP |
| Durchschnittliche Anlagengröße | Jahre | Line-Chart |
| Ertragsentwicklung | Jahre | Line-Chart |

### Saisonale Muster

- Heatmap: Alle Anlagen × 12 Monate
- Wann performt die Community am besten?
- Eigene saisonale Stärken/Schwächen

### Degradations-Analyse

- Ertrag nach Anlagenalter (gruppiert)
- Eigene Degradation vs. Durchschnitt
- Prognose für die Zukunft

### Technologie-Trends

- Wie entwickeln sich Speicher-Wirkungsgrade über Zeit?
- JAZ-Entwicklung bei Wärmepumpen
- E-Auto PV-Anteil-Entwicklung

### Persönliche Trends

- Position im Zeitverlauf (war ich schon mal besser?)
- Verbesserungs-/Verschlechterungs-Trend
- Monatliche Konsistenz

---

## Tab 6: Statistiken (Community-Insights)

### Verteilungen (Histogramme)

| Verteilung | X-Achse | Eigene Position |
|------------|---------|-----------------|
| Anlagengrößen | kWp | Markiert |
| Speicher-Kapazitäten | kWh | Markiert |
| Neigungswinkel | Grad | Markiert |
| Installationsjahre | Jahr | Markiert |

### Ausstattungsquoten (Pie-Charts / Balken)

| Ausstattung | Anzeige |
|-------------|---------|
| Speicher | X% haben Speicher, Ø Kapazität |
| Wärmepumpe | X% haben WP |
| E-Auto | X% haben E-Auto |
| Wallbox | X% haben Wallbox, Ø Leistung |
| Balkonkraftwerk | X% haben BKW |

### Durchschnittliche Konfiguration

- "Die typische Community-Anlage": 10 kWp, Süd, 30°, 8 kWh Speicher
- Vergleich mit eigener Konfiguration

### Anonyme Bestenlisten (Top 10)

| Kategorie | Anzeige |
|-----------|---------|
| Spez. Ertrag | Top 10 (anonym, eigene Position falls drin) |
| Autarkie | Top 10 |
| Speicher-Effizienz | Top 10 |
| WP-JAZ | Top 10 |
| E-Auto PV-Anteil | Top 10 |

---

## Ausstehende Erweiterungen (nach Server-Update)

Die folgenden Features sind im Frontend vorbereitet, benötigen aber erweiterte Daten vom Community-Server.
**Nach Server-Erweiterung hier abhaken und im Frontend implementieren.**

### PV-Ertrag Tab

| Feature | Benötigte Server-Daten | Status |
|---------|------------------------|--------|
| Monatliche Community-Durchschnitte | `GET /api/statistics/monthly-averages` | ⬜ Server-Endpoint fehlt |
| Echte Vergleichswerte pro Monat | Monatliche Durchschnittswerte aller Anlagen | ⬜ Server-Endpoint fehlt |
| Heatmap (Performance vs. Community) | Monatliche Vergleichsdaten | ⬜ Server-Endpoint fehlt |
| Verteilungskurve (Histogramm) | `GET /api/distributions/spez_ertrag` | ⬜ Server-Endpoint fehlt |

### Regional Tab

| Feature | Benötigte Server-Daten | Status |
|---------|------------------------|--------|
| Interaktive Deutschland-Karte | `GET /api/map/regional-stats` mit allen Bundesländern | ⬜ Server-Endpoint fehlt |
| Bundesland-Rankings (alle) | Durchschnittswerte pro Bundesland | ⬜ Server-Endpoint fehlt |
| Wetter-Korrelation nach Region | Sonnenstunden-Daten pro Region | ⬜ Server-Endpoint fehlt |
| Ähnliche Anlagen in der Nähe | Filter nach Region + kWp + Ausrichtung | ⬜ Server-Endpoint fehlt |

### Komponenten Tab

| Feature | Benötigte Server-Daten | Status |
|---------|------------------------|--------|
| Speicher: Vergleich nach Kapazitätsklassen | Gruppierte Durchschnitte (5-10, 10-15, >15 kWh) | ⬜ Server-Endpoint fehlt |
| WP: JAZ nach Klimazone | JAZ-Durchschnitte pro Region | ⬜ Server-Endpoint fehlt |
| E-Auto: Ladestrategien-Vergleich | Ladezeitverteilung Community | ⬜ Server-Endpoint fehlt |

### Trends Tab

| Feature | Benötigte Server-Daten | Status |
|---------|------------------------|--------|
| Community-weite Trends | `GET /api/trends/{period}` | ⬜ Server-Endpoint fehlt |
| Speicher/WP/E-Auto Adoption über Zeit | Historische Ausstattungsquoten | ⬜ Server-Endpoint fehlt |
| Degradations-Analyse nach Anlagenalter | Ertrag gruppiert nach Installationsjahr | ⬜ Server-Endpoint fehlt |

### Statistiken Tab

| Feature | Benötigte Server-Daten | Status |
|---------|------------------------|--------|
| Verteilungen (Histogramme) | `GET /api/distributions/{metric}` | ⬜ Server-Endpoint fehlt |
| Ausstattungsquoten | `GET /api/statistics/global` | ⬜ Server-Endpoint fehlt |
| Top-10 Bestenlisten | `GET /api/rankings/{category}` | ⬜ Server-Endpoint fehlt |

### Gamification (Phase 8)

| Feature | Benötigte Server-Daten | Status |
|---------|------------------------|--------|
| Achievements berechnen | `GET /api/achievements/{anlage_hash}` | ⬜ Server-Endpoint fehlt |
| Streak-Counter | Historische Rangdaten | ⬜ Server-Endpoint fehlt |

---

## Technische Anforderungen

### Community-Server Erweiterungen

| Endpoint | Methode | Beschreibung | Priorität |
|----------|---------|--------------|-----------|
| `/api/statistics/global` | GET | Globale Community-Stats | P1 |
| `/api/statistics/regional/{region}` | GET | Regional-spezifische Stats | P2 |
| `/api/distributions/{metric}` | GET | Verteilungsdaten (Histogramme) | P2 |
| `/api/trends/{period}` | GET | Zeitliche Trend-Daten | P3 |
| `/api/rankings/{category}` | GET | Top-Listen (anonym) | P2 |
| `/api/achievements/{anlage_hash}` | GET | Errungenschaften berechnen | P3 |
| `/api/comparison/historical/{anlage_hash}` | GET | Historischer Vergleich | P2 |
| `/api/map/regional-stats` | GET | Daten für Choropleth-Karte | P2 |

### Backend-Erweiterungen (eedc-homeassistant)

| Komponente | Beschreibung | Priorität |
|------------|--------------|-----------|
| Proxy-Endpoints | Alle neuen Server-Endpoints durchreichen | P1 |
| Caching-Layer | Statische Community-Daten cachen (TTL: 1h) | P2 |
| Lokale Berechnungen | Achievements, Trends aus lokalen Daten | P3 |

### Frontend-Komponenten

| Komponente | Bibliothek | Priorität |
|------------|------------|-----------|
| Tab-Navigation | Bestehend | P1 |
| Heatmap | Recharts CustomChart / react-heatmap-grid | P2 |
| Histogramm | Recharts BarChart | P2 |
| Choropleth-Karte | react-simple-maps / D3 | P3 |
| Radar-Chart | Recharts RadarChart | P2 |
| Gauge-Charts | Recharts / custom | P2 |
| Achievement-Badges | Custom SVG/CSS | P3 |

---

## Implementierungsphasen

### Phase 1: Grundgerüst (P1) ✅ Abgeschlossen
- [x] Community aus Auswertungen extrahieren
- [x] Hauptmenü-Eintrag hinzufügen
- [x] 6-Tab-Struktur aufbauen
- [x] Bestehende CommunityVergleich-Inhalte in "Übersicht" migrieren
- [x] Basis-Routing und Navigation

### Phase 2: Übersicht erweitern (P1) ✅ Abgeschlossen
- [x] Ranking-Badges (Top 10%, 25%, 50%)
- [x] Stärken/Schwächen-Anzeige
- [x] Radar-Chart: Eigene vs. Community
- [x] Komponenten-Benchmarks (kompakt)

### Phase 3: PV-Ertrag Tab (P2) ✅ Abgeschlossen (Basis)
- [x] Performance-Übersicht (Perzentil, vs Community, vs Region)
- [x] Monatlicher Ertrag mit Community-Vergleichslinie
- [x] Jahresübersicht mit Abweichungen
- [ ] Monats-Heatmap (wartet auf Server-Endpoint)
- [ ] Verteilungs-Histogramm (wartet auf Server-Endpoint)

### Phase 4: Regional Tab (P2) ✅ Abgeschlossen (Basis)
- [x] Regionale Position (Standort, Rang, Abweichung)
- [x] Vergleichs-Chart (Du/Region/Community)
- [x] Regionale Einordnung und Anlagen-Details
- [ ] Deutschland-Karte Choropleth (wartet auf Server-Endpoint)
- [ ] Bundesland-Rankings (wartet auf Server-Endpoint)

### Phase 5: Komponenten Tab (P2) ✅ Abgeschlossen
- [x] Speicher Deep-Dive (KPIs, Charts, Tipps)
- [x] Wärmepumpe Deep-Dive
- [x] E-Auto Deep-Dive (inkl. Ladequellen-Chart)
- [x] Wallbox Deep-Dive
- [x] Balkonkraftwerk Deep-Dive

### Phase 6: Statistiken Tab (P2) ✅ Abgeschlossen (Basis)
- [x] Community-Zusammenfassung
- [x] Position in Community und Region
- [x] Anlagen-Details und Ausstattungs-Übersicht
- [ ] Verteilungs-Histogramme (wartet auf Server-Endpoint)
- [ ] Ausstattungsquoten (wartet auf Server-Endpoint)
- [ ] Top-10-Listen (wartet auf Server-Endpoint)

### Phase 7: Trends Tab (P3) ✅ Abgeschlossen (Basis)
- [x] Ertragsverlauf (Area-Chart)
- [x] Saisonale Performance (Frühling/Sommer/Herbst/Winter)
- [x] Jahresvergleich
- [x] Typischer Monatsverlauf
- [ ] Community-Trends (wartet auf Server-Endpoint)
- [ ] Degradations-Analyse (wartet auf Server-Endpoint)

### Phase 8: Gamification (P3) ✅ Abgeschlossen
- [x] Achievement-System (7 Achievements)
- [x] Fortschrittsanzeige für nicht erreichte
- [ ] Streak-Counter (wartet auf Server-Endpoint)
- [ ] Weitere Achievements (wartet auf Server-Endpoint)

---

## Design-Richtlinien

### Farbschema

Community verwendet das **bestehende Primary-Farbschema** von EEDC - keine Sonderfarben.
Die Differenzierung erfolgt durch Inhalt und Funktionalität, nicht durch abweichende Farben.

| Verwendung | Farbe | Tailwind |
|------------|-------|----------|
| Akzent/Aktiv | Primary | `primary-500` (wie überall in EEDC) |
| Positiv/Besser | Grün | `green-500` |
| Negativ/Schlechter | Rot | `red-500` |
| Neutral | Grau | `gray-500` |

### Icons (Lucide)

| Bereich | Icon |
|---------|------|
| Community | `Users` |
| Ranking | `Trophy` |
| Trends | `TrendingUp` |
| Regional | `MapPin` / `Map` |
| Statistiken | `BarChart3` |
| Achievements | `Award` / `Medal` |

### Responsive Design

- Desktop: 6 Tabs horizontal
- Tablet: 6 Tabs horizontal (kompakter)
- Mobile: Tab-Dropdown oder Scroll-Tabs

---

## Offene Fragen / Entscheidungen

- [ ] Achievement-Kriterien final definieren
- [ ] Caching-Strategie für Community-Daten
- [ ] Kartenintegration: react-simple-maps vs. D3 vs. Leaflet
- [ ] Anonymitäts-Level für Top-Listen

---

---

## Detaillierter Implementierungsplan Phase 1

### Ziel
Community als eigenständigen Hauptmenüpunkt etablieren mit 6-Tab-Struktur.

### Schritt 1.1: Routing erweitern (App.tsx)

**Datei:** `eedc/frontend/src/App.tsx`

```typescript
// Neue Imports
import Community from './pages/Community'

// Neue Route (nach /aussichten)
<Route path="community" element={<Community />} />

// Legacy-Redirect für alten Pfad
<Route path="auswertungen/community" element={<Navigate to="/community" replace />} />
```

### Schritt 1.2: Hauptnavigation erweitern (TopNavigation.tsx)

**Datei:** `eedc/frontend/src/components/layout/TopNavigation.tsx`

```typescript
import { Users } from 'lucide-react'

// mainTabs erweitern:
const mainTabs = [
  { name: 'Cockpit', basePath: '/cockpit', icon: LayoutDashboard },
  { name: 'Auswertungen', basePath: '/auswertungen', icon: BarChart3 },
  { name: 'Aussichten', basePath: '/aussichten', icon: TrendingUp },
  { name: 'Community', basePath: '/community', icon: Users },  // NEU
]

// getActiveMainTab erweitern:
if (location.pathname.startsWith('/community')) return 'Community'

// Einstellungen-Menü: Community-Kategorie bleibt für "Daten teilen"
```

### Schritt 1.3: Community Hauptseite erstellen

**Neue Datei:** `eedc/frontend/src/pages/Community.tsx`

Struktur analog zu `Aussichten.tsx`:
- 6 Tabs: Übersicht, PV-Ertrag, Komponenten, Regional, Trends, Statistiken
- State für aktiven Tab
- Anlagen-Auswahl (wenn mehrere)
- Zeitraum-Filter
- Prüfung ob community_hash vorhanden

### Schritt 1.4: Tab-Komponenten erstellen

**Neuer Ordner:** `eedc/frontend/src/pages/community/`

```
community/
├── index.ts              # Re-exports
├── UebersichtTab.tsx     # Migration von CommunityVergleich.tsx
├── PVErtragTab.tsx       # Placeholder
├── KomponentenTab.tsx    # Placeholder
├── RegionalTab.tsx       # Placeholder
├── TrendsTab.tsx         # Placeholder
└── StatistikenTab.tsx    # Placeholder
```

### Schritt 1.5: Auswertung.tsx anpassen

**Datei:** `eedc/frontend/src/pages/Auswertung.tsx`

- Community-Tab entfernen (war bedingt angezeigt)
- `hatCommunityZugang` Check entfernen
- Import von CommunityVergleich entfernen
- Tabs auf 6 reduzieren

### Schritt 1.6: CommunityVergleich.tsx refactoren

**Datei:** `eedc/frontend/src/pages/CommunityVergleich.tsx`

→ Wird zu `UebersichtTab.tsx` migriert
→ `embedded` Prop entfällt (war für Auswertung)
→ Eigenständige Komponente mit anlageId als Prop

---

## Dateien-Checkliste Phase 1

| Datei | Aktion | Status |
|-------|--------|--------|
| `App.tsx` | Route hinzufügen | ✅ |
| `TopNavigation.tsx` | Tab hinzufügen | ✅ |
| `Community.tsx` | Neu erstellen | ✅ |
| `community/index.ts` | Neu erstellen | ✅ |
| `community/UebersichtTab.tsx` | Migration | ✅ |
| `community/PVErtragTab.tsx` | Placeholder | ✅ |
| `community/KomponentenTab.tsx` | Placeholder | ✅ |
| `community/RegionalTab.tsx` | Placeholder | ✅ |
| `community/TrendsTab.tsx` | Placeholder | ✅ |
| `community/StatistikenTab.tsx` | Placeholder | ✅ |
| `Auswertung.tsx` | Community-Tab entfernen | ✅ |
| `CommunityVergleich.tsx` | Deprecated / Redirect | ✅ |

---

## API-Änderungen Phase 1

Keine Backend-Änderungen in Phase 1 erforderlich.
Bestehende Endpoints werden weiterhin genutzt:
- `GET /api/community/benchmark/{anlage_id}`
- `GET /api/community/status`

---

## Änderungshistorie

| Datum | Version | Änderung |
|-------|---------|----------|
| 2026-02-21 | 0.1 | Initiale Vision erstellt |
| 2026-02-21 | 0.2 | Detaillierter Implementierungsplan Phase 1 hinzugefügt |
| 2026-02-21 | 0.3 | **Phase 1 abgeschlossen:** Community als Hauptmenüpunkt mit 6-Tab-Struktur |
| 2026-02-21 | 1.0 | **Phasen 1-8 abgeschlossen:** Alle 6 Tabs implementiert mit verfügbaren Daten, Achievements-System, Deep-Dives für alle Komponenten. Weitere Features warten auf Server-Erweiterungen. |

