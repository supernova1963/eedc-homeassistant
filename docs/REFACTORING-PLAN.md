# Frontend-Refactoring Plan

> Erstellt: 2026-03-20 | Status: Phase 0–7 erledigt (2026-03-21) | Auslöser: Code-Audit

## Ziel

Die zwei größten Frontend-Dateien strukturiert zerlegen:
- `MonatsdatenForm.tsx` (1625 Zeilen) → ~250 Zeilen
- `Dashboard.tsx` (1283 Zeilen) → ~300 Zeilen

Gleichzeitig gemeinsame Abstraktionen schaffen (Hooks, Utils, Chart-Komponenten), die duplizierte Patterns in ~14 weiteren Seiten eliminieren.

## Prinzipien

- **Kein Big-Bang:** Jede Phase ist additiv, bestehende Imports brechen nicht
- **Barrel-Exports:** `index.ts` Re-Exports sichern Rückwärtskompatibilität
- **Validierung:** `npx tsc --noEmit` nach jeder Phase + visueller Check für Phase 5–6
- **Kein Over-Engineering:** Keine neuen Libraries, keine State-Management-Frameworks

## Ziel-Verzeichnisstruktur

```
src/
├── api/                          # (unverändert) API-Client-Module
│
├── components/
│   ├── ui/                       # (unverändert) Primitive UI-Komponenten
│   │
│   ├── charts/                   # NEU: Recharts-Wrapper
│   │   ├── ChartContainer.tsx    #   ResponsiveContainer + konsistente Größen
│   │   ├── BarChartCard.tsx      #   Card + BarChart mit Standard-Config
│   │   ├── LineChartCard.tsx     #   Card + LineChart mit Standard-Config
│   │   ├── SparklineBar.tsx      #   Mini-Balkenchart
│   │   ├── RingGauge.tsx         #   SVG Ring-Gauge (aus Dashboard extrahiert)
│   │   ├── chartConfig.ts        #   Farben, contentStyle, Label-Formatter
│   │   └── index.ts
│   │
│   ├── common/                   # NEU: Geteilte Composite-Komponenten
│   │   ├── AnlageSelector.tsx    #   Anlage-Dropdown + Auto-Select
│   │   ├── YearSelector.tsx      #   Jahr-Dropdown
│   │   ├── PageHeader.tsx        #   Titel + Selektoren + Actions
│   │   ├── DataLoadingState.tsx  #   Loading / Error / Empty Wrapper
│   │   └── index.ts
│   │
│   ├── dashboard/                # NEU: Aus Dashboard.tsx extrahiert
│   │   ├── HeroKPIs.tsx
│   │   ├── EnergieBilanzSection.tsx
│   │   ├── EffizienzQuotenSection.tsx
│   │   ├── SpeicherSection.tsx
│   │   ├── FinanzenSection.tsx
│   │   ├── CO2Section.tsx
│   │   ├── CommunityTeaser.tsx
│   │   └── index.ts
│   │
│   ├── monatsabschluss/          # NEU: Aus MonatsabschlussWizard.tsx extrahiert
│   │   ├── WizardNavigation.tsx
│   │   ├── BasisFelderStep.tsx
│   │   ├── InvestitionenStep.tsx
│   │   ├── SonstigesStep.tsx
│   │   ├── VorschlagBadge.tsx
│   │   ├── PlausibilitaetHinweis.tsx
│   │   └── index.ts
│   │
│   ├── forms/                    # (unverändert)
│   ├── layout/                   # (unverändert)
│   ├── live/                     # (unverändert)
│   ├── pv/                       # (unverändert)
│   ├── sensor-mapping/           # (unverändert)
│   └── setup-wizard/             # (unverändert)
│
├── hooks/
│   ├── useAnlagen.ts             # (unverändert)
│   ├── useMonatsdaten.ts         # (unverändert)
│   ├── useInvestitionen.ts       # (unverändert)
│   ├── useStrompreise.ts         # (unverändert)
│   ├── useSetupWizard.ts         # (unverändert)
│   ├── useHAAvailable.ts         # (unverändert)
│   ├── useSelectedAnlage.ts     # NEU: Anlage-Selektion + localStorage
│   ├── useApiData.ts            # NEU: Generischer async Datenfetch
│   ├── useYearSelection.ts     # NEU: Verfügbare Jahre + Selektion
│   └── index.ts
│
├── lib/                          # NEU: Pure Utility-Funktionen (kein React)
│   ├── formatting.ts            #   formatKWh, formatEuro, formatPercent, formatCO2
│   ├── colors.ts                #   Chart-Farbpalette, CSS-Variable-Referenzen
│   ├── constants.ts             #   MONAT_NAMEN, MONAT_KURZ, TYP_ICONS, TYP_LABELS
│   ├── calculations.ts         #   Autarkie, Eigenverbrauch, spez. Ertrag
│   └── index.ts
│
├── types/
│   ├── anlage.ts                # NEU: Anlage, AnlageCreate, AnlageUpdate
│   ├── monatsdaten.ts           # NEU: Monatsdaten, MonatsKennzahlen
│   ├── investition.ts           # NEU: Investition, InvestitionTyp
│   ├── strompreis.ts            # NEU: Strompreis, StrompreisVerwendung
│   ├── ha.ts                    # NEU: HASensor, HASensorMapping
│   ├── common.ts                # NEU: ImportResult, WetterProvider, etc.
│   └── index.ts                 #   Re-exportiert alles (rückwärtskompatibel)
│
└── pages/                        # Verschlankte Seiten (nur Orchestrierung)
    ├── Dashboard.tsx             #   ~300 Zeilen (von 1282)
    ├── MonatsabschlussWizard.tsx #   ~400 Zeilen (von 1264)
    └── ...
```

## Phasen

### Phase 0: Foundation (rein additiv, keine Breaking Changes) ✅ `ceba2de`

| Task | Beschreibung |
|------|-------------|
| 0.1 | `lib/constants.ts` — MONAT_NAMEN, MONAT_KURZ, TYP_ICONS, TYP_LABELS aus ~10 Dateien extrahieren |
| 0.2 | `lib/formatting.ts` — formatKWh, formatEuro, formatPercent, formatCO2 (alle `.toLocaleString('de-DE')` Patterns) |
| 0.3 | `lib/colors.ts` — Chart-Farbpalette (inline `#hex` Farben aus Pages) |
| 0.4 | `lib/calculations.ts` — Pure Functions für Autarkie, Eigenverbrauch, spez. Ertrag |
| 0.5 | `lib/index.ts` — Barrel-Export |

**Validierung:** `npx tsc --noEmit`, keine Imports geändert.

### Phase 1: Shared Hooks (additiv, dann schrittweise Adoption) ✅ `8a529b0`

| Task | Beschreibung |
|------|-------------|
| 1.1 | `hooks/useSelectedAnlage.ts` — Kapselt "Auto-Select erste Anlage" Pattern (in 14 Seiten dupliziert). Interface: `{ selectedAnlageId, setSelectedAnlageId, anlage, anlagen, loading }`. localStorage-Persistenz. |
| 1.2 | `hooks/useApiData.ts` — Generisch: `useApiData<T>(fetcher, deps) => { data, loading, error, refetch }`. Ersetzt useState+useEffect+try/catch Boilerplate in 30+ Seiten. |
| 1.3 | `hooks/useYearSelection.ts` — Leitet verfügbare Jahre aus Daten ab, verwaltet Selektion. |
| 1.4 | `hooks/index.ts` aktualisieren |

**Validierung:** `npx tsc --noEmit`. Eine Seite migrieren als Proof (z.B. PVAnlageDashboard).

### Phase 2: Chart-Komponenten (additiv) ✅ `3c8d968`

> BarChartCard/LineChartCard übersprungen — ChartTooltip deckt Tooltip-Pattern bereits ab, Chart-Konfigurationen sind zu spezifisch pro Seite.

| Task | Beschreibung |
|------|-------------|
| 2.1 | `charts/chartConfig.ts` — Recharts-Defaults: contentStyle mit CSS-Vars, Standard-Achsen |
| 2.2 | `charts/ChartContainer.tsx` — ResponsiveContainer-Wrapper |
| 2.3 | `charts/BarChartCard.tsx` — Card + BarChart mit Standard-Tooltip |
| 2.4 | `charts/LineChartCard.tsx` — Gleich für Line-Charts |
| 2.5 | `charts/SparklineBar.tsx` — Mini-Balken für Dashboard |
| 2.6 | `charts/RingGauge.tsx` — SVG Ring-Gauge (aus Dashboard) |
| 2.7 | `charts/index.ts` — Barrel-Export |

**Validierung:** Visueller Vergleich auf Dashboard, Auswertung-Tabs.

### Phase 3: Common Components (additiv) ✅ `1d1bcf3`

| Task | Beschreibung |
|------|-------------|
| 3.1 | `common/AnlageSelector.tsx` — Dropdown gebunden an useSelectedAnlage |
| 3.2 | `common/YearSelector.tsx` — Dropdown gebunden an useYearSelection |
| 3.3 | `common/PageHeader.tsx` — Titel + Selektoren + Action-Buttons |
| 3.4 | `common/DataLoadingState.tsx` — Loading/Error/Empty Wrapper |
| 3.5 | `common/index.ts` — Barrel-Export |

**Validierung:** `npx tsc --noEmit`.

### Phase 4: Types aufsplitten (mechanisch, rückwärtskompatibel) ⏭️ Übersprungen

> types/index.ts ist mit 222 Zeilen gut strukturiert und logisch gruppiert. Aufsplitten bringt keinen Mehrwert.

| Task | Beschreibung |
|------|-------------|
| 4.1 | `types/anlage.ts` — Anlage, AnlageCreate, AnlageUpdate, Versorger*, SensorConfig |
| 4.2 | `types/monatsdaten.ts` — Monatsdaten, MonatsKennzahlen |
| 4.3 | `types/investition.ts` — Investition, InvestitionTyp, InvestitionCreate |
| 4.4 | `types/strompreis.ts` — Strompreis, StrompreisVerwendung |
| 4.5 | `types/ha.ts` — HASensor, HASensorMapping |
| 4.6 | `types/common.ts` — ImportResult, WetterProvider, SteuerlicheBehandlung |
| 4.7 | `types/index.ts` — Re-exportiert alles (0 Import-Änderungen nötig) |

**Validierung:** `npx tsc --noEmit`.

### Phase 5: Dashboard zerlegen (der große Win) ✅ `6220804`

> Dashboard.tsx: 1297 → 595 Zeilen. 12 Komponenten extrahiert nach `components/dashboard/`.

| Task | Beschreibung |
|------|-------------|
| 5.1 | `dashboard/HeroKPIs.tsx` — Top-KPI-Leiste mit Sparklines und YoY-Vergleich |
| 5.2 | `dashboard/EnergieBilanzSection.tsx` — Energiebilanz-Chart + Monats-Sparkline |
| 5.3 | `dashboard/EffizienzQuotenSection.tsx` — Ring-Gauges für Autarkie + Eigenverbrauch |
| 5.4 | `dashboard/SpeicherSection.tsx` — Batterie-Metriken |
| 5.5 | `dashboard/FinanzenSection.tsx` — Finanz-KPIs + Amortisationsbalken |
| 5.6 | `dashboard/CO2Section.tsx` — CO2-Einsparung |
| 5.7 | `dashboard/CommunityTeaser.tsx` — Community-Sharing-Teaser |
| 5.8 | `pages/Dashboard.tsx` verschlanken — ~300 Zeilen: Datenfetch + Section-Komposition |

**Validierung:** Visueller Vergleich vorher/nachher. Alle Daten fließen via Props.

**Shared Interface aller Dashboard-Sections:**
```typescript
interface DashboardSectionProps {
  data: CockpitUebersicht
  prevYearData?: CockpitUebersicht | null
  selectedYear?: number
  onNavigate?: (path: string) => void
}
```

### Phase 6: MonatsabschlussWizard zerlegen ✅ `84aaf75`

> MonatsabschlussWizard.tsx: 1264 → 775 Zeilen. 9 Dateien extrahiert nach `components/monatsabschluss/`.

| Task | Beschreibung |
|------|-------------|
| 6.1 | `monatsabschluss/WizardNavigation.tsx` — Step-Indikatoren + Prev/Next-Buttons |
| 6.2 | `monatsabschluss/BasisFelderStep.tsx` — Kernfelder mit Vorschlag-Overlay |
| 6.3 | `monatsabschluss/InvestitionenStep.tsx` — Pro-Komponente Dateneingabe |
| 6.4 | `monatsabschluss/SonstigesStep.tsx` — Notizen, Sonderkosten |
| 6.5 | `monatsabschluss/VorschlagBadge.tsx` — Farbiges Quellen-Badge |
| 6.6 | `monatsabschluss/PlausibilitaetHinweis.tsx` — Plausibilitäts-Warnungen |
| 6.7 | `pages/MonatsabschlussWizard.tsx` verschlanken — ~400 Zeilen: Wizard-State + Step-Orchestrierung |

**Validierung:** Vollständiger Wizard-Durchlauf (alle Steps, Speichern).

**Shared Interface aller Wizard-Steps:**
```typescript
interface WizardStepProps {
  wizardState: WizardState
  onUpdate: (path: string, value: number | string | null) => void
  felder: Record<string, FeldStatus>
  investitionen: InvestitionStatus[]
  readOnly?: boolean
}
```

### Phase 7: Schrittweise Seiten-Migration (fortlaufend) — 10/27 Seiten ✅ `96e5f8c`

> Migriert: Dashboard, LiveDashboard, Auswertung, PVAnlageDashboard,
> SpeicherDashboard, WaermepumpeDashboard, EAutoDashboard, WallboxDashboard,
> BalkonkraftwerkDashboard, SonstigesDashboard. -93 Zeilen Boilerplate.

Seiten nach Größe priorisiert auf neue Hooks/Components migrieren:

| Priorität | Seite | Zeilen | Änderungen |
|-----------|-------|--------|------------|
| 1 | Monatsdaten.tsx | 972 | useSelectedAnlage, useApiData, DataLoadingState |
| 2 | HAStatistikImport.tsx | 887 | useSelectedAnlage, useApiData |
| 3 | MqttInboundSetup.tsx | 880 | useSelectedAnlage, useApiData |
| 4 | CustomImportWizard.tsx | 836 | useApiData, DataLoadingState |
| 5 | AktuellerMonat.tsx | 721 | useSelectedAnlage, Chart-Components |
| 6 | Komponenten-Dashboards | 300-625 | useSelectedAnlage, PageHeader, Charts |

Jede Seiten-Migration ist ein unabhängiger Commit.

## Komponenten-Interfaces

### Hooks

```typescript
// useSelectedAnlage
interface UseSelectedAnlageReturn {
  anlagen: Anlage[]
  selectedAnlageId: number | undefined
  selectedAnlage: Anlage | undefined
  setSelectedAnlageId: (id: number) => void
  loading: boolean
}

// useApiData<T>
interface UseApiDataReturn<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => Promise<void>
}
function useApiData<T>(
  fetcher: () => Promise<T>,
  deps: unknown[],
  options?: { enabled?: boolean }
): UseApiDataReturn<T>

// useYearSelection
interface UseYearSelectionReturn {
  selectedYear: number | undefined
  setSelectedYear: (year: number | undefined) => void
  availableYears: number[]
  setAvailableYears: (years: number[]) => void
}
```

### Common Components

```typescript
// AnlageSelector
interface AnlageSelectorProps {
  selectedAnlageId?: number
  onSelect: (anlageId: number) => void
  anlagen: Anlage[]
  className?: string
}

// PageHeader
interface PageHeaderProps {
  title: string
  icon?: React.ReactNode
  children?: React.ReactNode  // Slot für Selektoren + Actions
}

// DataLoadingState
interface DataLoadingStateProps {
  loading: boolean
  error: string | null
  isEmpty?: boolean
  emptyMessage?: string
  onRetry?: () => void
  children: React.ReactNode
}
```

### Chart Components

```typescript
// RingGauge
interface RingGaugeProps {
  value: number          // 0-100
  label: string
  size?: number          // default: 120
  strokeWidth?: number   // default: 10
  color?: string
}

// BarChartCard
interface BarChartCardProps {
  title: string
  data: Record<string, unknown>[]
  bars: Array<{ dataKey: string; name: string; color: string; stackId?: string }>
  xDataKey: string
  xFormatter?: (value: string) => string
  yFormatter?: (value: number) => string
  height?: number
}
```
