/**
 * Community-Trends — geteilte Teile (Daten-Hook + Präsentations-Sektionen).
 * EINE Code-Wahrheit für IST (`TrendsTab`) und IA-V4 (`CommunityTrendsV4`).
 * Sektionen rendern Inhalt OHNE äußere Card/Block-Hülle (Aufrufer wickelt).
 * Zahlen de-DE (`fmtZahl`), Farben/Achsen aus der Zentrale.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  TrendingUp, Calendar, Sun, Snowflake, Cloud, Leaf, Info, BarChart3,
  ArrowUpRight, ArrowDownRight, Minus,
} from 'lucide-react'
import { ChartLegende } from '../../components/ui'
import { Parkbar } from '../../components/park'
import ChartTooltip from '../../components/ui/ChartTooltip'
import { useChartTheme } from '../../context/ThemeContext'
import { useSchmaleAchse } from '../../hooks'
import { communityApi } from '../../api'
import type { CommunityBenchmarkResponse, TrendDaten, DegradationsAnalyse } from '../../api/community'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Area, AreaChart, Legend,
} from 'recharts'
import {
  MONAT_KURZ, MONAT_NAMEN, EIGENE_SERIE_FARBEN, TYP_COLORS,
  ACHSEN_MARGIN_TOP, xAchse, yAchse, achsenEinheit, achsenTick, fmtZahl,
} from '../../lib'

const MONATSNAMEN = MONAT_KURZ.slice(1)     // 0-basiert
const MONATSNAMEN_LANG = MONAT_NAMEN.slice(1) // 0-basiert

// Jahreszeiten
export const JAHRESZEITEN = {
  fruehling: { name: 'Frühling', monate: [3, 4, 5], icon: Leaf, color: 'green' },
  sommer: { name: 'Sommer', monate: [6, 7, 8], icon: Sun, color: 'yellow' },
  herbst: { name: 'Herbst', monate: [9, 10, 11], icon: Cloud, color: 'orange' },
  winter: { name: 'Winter', monate: [12, 1, 2], icon: Snowflake, color: 'blue' },
}

// Element-Park (IA-V4, Element-Park-Doktrin Gernot 2026-06-27): JEDE Anzeige
// (KPI, Chart, Beschriftung/Legende, Tabelle, Hinweis) ist einzeln parkbar.
// `Parkbar` ist OHNE ParkProvider inert → der IST-`TrendsTab` (v3, kein Provider)
// bleibt optisch identisch; nur die V4-Sicht aktiviert die Geste. IDs view-eindeutig
// (persistKey 'v4-community-trends'); der V4-Builder blendet einen Block aus, wenn
// ALLE seine Element-IDs geparkt sind (alleGeparkt).
export const TR_PARK_IDS = {
  verlauf: ['tr-verlauf-chart'],
  saisonal: ['tr-saison-fruehling', 'tr-saison-sommer', 'tr-saison-herbst', 'tr-saison-winter'],
  jahresvergleich: ['tr-jahr-vorjahr', 'tr-jahr-aktuell', 'tr-jahr-veraenderung'],
  monatsverlauf: ['tr-monatsverlauf-chart', 'tr-monatsverlauf-caption'],
  community: ['tr-community-chart', 'tr-community-caption'],
  degradation: ['tr-degradation-chart', 'tr-degradation-info'],
} as const

export interface TrendsDaten {
  communityTrends: TrendDaten | null
  degradation: DegradationsAnalyse | null
  ertragsverlauf: { name: string; monat: number; jahr: number; ertrag: number; autarkie: number | null; eigenverbrauch: number | null }[]
  jahresvergleich: {
    letztesJahr: number; vorletztesJahr: number; ertragLetzt: number; ertragVorletzt: number; differenz: number; differenzProzent: number
  } | null
  saisonaleAnalyse: { key: string; name: string; icon: typeof Sun; color: string; durchschnittMonat: number; anzahlMonate: number }[] | null
  monatlicherDurchschnitt: { monat: number; name: string; durchschnitt: number; anzahl: number }[]
  extraLoading: boolean
}

// ─── Daten-Hook (lädt Trends + Degradation; leitet Verlaufs-Aggregate ab) ──────

export function useTrendsDaten(benchmark: CommunityBenchmarkResponse | null): TrendsDaten {
  const [communityTrends, setCommunityTrends] = useState<TrendDaten | null>(null)
  const [degradation, setDegradation] = useState<DegradationsAnalyse | null>(null)
  const [extraLoading, setExtraLoading] = useState(false)

  // Community-Trends und Degradation laden (unabhängig vom Benchmark)
  useEffect(() => {
    const loadExtra = async () => {
      setExtraLoading(true)
      try {
        const [trendsData, degradationData] = await Promise.all([
          communityApi.getTrends('12_monate').catch(() => null),
          communityApi.getDegradation().catch(() => null),
        ])
        setCommunityTrends(trendsData)
        setDegradation(degradationData)
      } finally {
        setExtraLoading(false)
      }
    }
    loadExtra()
  }, [])

  // Ertragsverlauf aufbereiten - chronologisch sortiert
  const ertragsverlauf = useMemo(() => {
    if (!benchmark?.anlage.monatswerte) return []

    // Sortiere chronologisch (älteste zuerst)
    const sortedMonatswerte = [...benchmark.anlage.monatswerte]
      .sort((a, b) => a.jahr - b.jahr || a.monat - b.monat)

    return sortedMonatswerte.map(m => ({
      name: `${MONATSNAMEN[m.monat - 1]} ${m.jahr % 100}`,
      monat: m.monat,
      jahr: m.jahr,
      ertrag: m.spez_ertrag_kwh_kwp || 0,
      autarkie: m.autarkie_prozent || null,
      eigenverbrauch: m.eigenverbrauch_prozent || null,
    }))
  }, [benchmark])

  // Jahresvergleich
  const jahresvergleich = useMemo(() => {
    if (!benchmark?.anlage.monatswerte) return null

    const monatswerte = benchmark.anlage.monatswerte
    const jahre = [...new Set(monatswerte.map(m => m.jahr))].sort()

    if (jahre.length < 2) return null

    // Gruppieren nach Jahr
    const jahresDaten: Record<number, { summe: number; anzahl: number }> = {}
    monatswerte.forEach(m => {
      if (!jahresDaten[m.jahr]) {
        jahresDaten[m.jahr] = { summe: 0, anzahl: 0 }
      }
      jahresDaten[m.jahr].summe += m.spez_ertrag_kwh_kwp || 0
      jahresDaten[m.jahr].anzahl += 1
    })

    // Vergleich der letzten zwei vollständigen Jahre
    const vollstaendigeJahre = jahre.filter(j => jahresDaten[j].anzahl === 12)

    if (vollstaendigeJahre.length < 2) return null

    const letztesJahr = vollstaendigeJahre[vollstaendigeJahre.length - 1]
    const vorletztesJahr = vollstaendigeJahre[vollstaendigeJahre.length - 2]

    const ertragLetzt = jahresDaten[letztesJahr].summe
    const ertragVorletzt = jahresDaten[vorletztesJahr].summe
    const differenz = ertragLetzt - ertragVorletzt
    const differenzProzent = (differenz / ertragVorletzt) * 100

    return {
      letztesJahr,
      vorletztesJahr,
      ertragLetzt,
      ertragVorletzt,
      differenz,
      differenzProzent,
    }
  }, [benchmark])

  // Saisonale Analyse
  const saisonaleAnalyse = useMemo(() => {
    if (!benchmark?.anlage.monatswerte) return null

    const monatswerte = benchmark.anlage.monatswerte

    // Gruppieren nach Jahreszeit
    const jahreszeitenDaten: Record<string, { summe: number; anzahl: number }> = {}

    Object.entries(JAHRESZEITEN).forEach(([key, jz]) => {
      jahreszeitenDaten[key] = { summe: 0, anzahl: 0 }
      monatswerte.forEach(m => {
        if (jz.monate.includes(m.monat)) {
          jahreszeitenDaten[key].summe += m.spez_ertrag_kwh_kwp || 0
          jahreszeitenDaten[key].anzahl += 1
        }
      })
    })

    return Object.entries(JAHRESZEITEN).map(([key, jz]) => {
      const daten = jahreszeitenDaten[key]
      const durchschnitt = daten.anzahl > 0 ? daten.summe / daten.anzahl : 0

      return {
        key,
        name: jz.name,
        icon: jz.icon,
        color: jz.color,
        durchschnittMonat: durchschnitt,
        anzahlMonate: daten.anzahl,
      }
    })
  }, [benchmark])

  // Monatliche Durchschnitte (über alle Jahre)
  const monatlicherDurchschnitt = useMemo(() => {
    if (!benchmark?.anlage.monatswerte) return []

    const monatswerte = benchmark.anlage.monatswerte

    const monatsDaten: Record<number, { summe: number; anzahl: number }> = {}
    for (let i = 1; i <= 12; i++) {
      monatsDaten[i] = { summe: 0, anzahl: 0 }
    }

    monatswerte.forEach(m => {
      monatsDaten[m.monat].summe += m.spez_ertrag_kwh_kwp || 0
      monatsDaten[m.monat].anzahl += 1
    })

    return Object.entries(monatsDaten).map(([monat, daten]) => ({
      monat: parseInt(monat),
      name: MONATSNAMEN[parseInt(monat) - 1],
      durchschnitt: daten.anzahl > 0 ? daten.summe / daten.anzahl : 0,
      anzahl: daten.anzahl,
    }))
  }, [benchmark])

  return {
    communityTrends, degradation, ertragsverlauf, jahresvergleich,
    saisonaleAnalyse, monatlicherDurchschnitt, extraLoading,
  }
}

// ─── Sektion: Ertragsverlauf (AreaChart) ──────────────────────────────────────

export function ErtragsverlaufChart({ benchmark, ertragsverlauf }: {
  benchmark: CommunityBenchmarkResponse
  ertragsverlauf: TrendsDaten['ertragsverlauf']
}) {
  const achsen = useChartTheme()
  const schmal = useSchmaleAchse()
  return (
    <Parkbar id="tr-verlauf-chart" titel="Ertragsverlauf">
    <div>
      <div className="flex items-center justify-end mb-2">
        <span className="text-sm text-gray-500">{benchmark.zeitraum_label}</span>
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={ertragsverlauf} margin={{ top: ACHSEN_MARGIN_TOP }}>
            <defs>
              <linearGradient id="colorErtrag" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={EIGENE_SERIE_FARBEN.du} stopOpacity={0.3} />
                <stop offset="95%" stopColor={EIGENE_SERIE_FARBEN.du} stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke={achsen.grid} />
            <XAxis
              dataKey="name"
              {...xAchse(schmal)}
              interval={Math.floor(ertragsverlauf.length / 12)}
              /* achsen-allow: Zeit-/Kategorie-Achse */
            />
            <YAxis
              {...yAchse(schmal)}
              tickFormatter={achsenTick}
              label={achsenEinheit('kWh/kWp')}
            />
            <Tooltip content={<ChartTooltip unit="kWh/kWp" decimals={1} />} />
            <Area
              type="monotone"
              dataKey="ertrag"
              stroke={EIGENE_SERIE_FARBEN.du}
              strokeWidth={2}
              fill="url(#colorErtrag)"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
    </Parkbar>
  )
}

// ─── Sektion: Saisonale Performance (Karten) ──────────────────────────────────

export function SaisonalePerformance({ saisonaleAnalyse }: {
  saisonaleAnalyse: NonNullable<TrendsDaten['saisonaleAnalyse']>
}) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
      {saisonaleAnalyse.map((jz) => {
        const Icon = jz.icon
        const colorClasses: Record<string, { bg: string; text: string; icon: string }> = {
          green: { bg: 'bg-green-50 dark:bg-green-900/20', text: 'text-green-700 dark:text-green-300', icon: 'text-green-500' },
          yellow: { bg: 'bg-yellow-50 dark:bg-yellow-900/20', text: 'text-yellow-700 dark:text-yellow-300', icon: 'text-yellow-500' },
          orange: { bg: 'bg-orange-50 dark:bg-orange-900/20', text: 'text-orange-700 dark:text-orange-300', icon: 'text-orange-500' },
          blue: { bg: 'bg-blue-50 dark:bg-blue-900/20', text: 'text-blue-700 dark:text-blue-300', icon: 'text-blue-500' },
        }
        const colors = colorClasses[jz.color]

        return (
          <Parkbar key={jz.key} id={`tr-saison-${jz.key}`} titel={jz.name}>
          <div className={`rounded-xl p-4 ${colors.bg}`}>
            <div className="flex items-center gap-2 mb-3">
              <Icon className={`h-5 w-5 ${colors.icon}`} />
              <span className={`font-medium ${colors.text}`}>{jz.name}</span>
            </div>
            <div className="flex items-baseline gap-1">
              <span className="text-2xl font-bold text-gray-900 dark:text-white">
                {fmtZahl(jz.durchschnittMonat, 0)}
              </span>
              <span className="text-sm text-gray-500">kWh/kWp</span>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Ø pro Monat ({jz.anzahlMonate} Monate)
            </p>
          </div>
          </Parkbar>
        )
      })}
    </div>
  )
}

// ─── Sektion: Jahresvergleich (Karten) ────────────────────────────────────────

export function JahresvergleichBlock({ jahresvergleich }: {
  jahresvergleich: NonNullable<TrendsDaten['jahresvergleich']>
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {/* Vorjahr */}
      <Parkbar id="tr-jahr-vorjahr" titel="Vorjahr">
      <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4">
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">{jahresvergleich.vorletztesJahr}</p>
        <div className="flex items-baseline gap-1">
          <span className="text-2xl font-bold text-gray-900 dark:text-white">
            {fmtZahl(jahresvergleich.ertragVorletzt, 0)}
          </span>
          <span className="text-sm text-gray-500">kWh/kWp</span>
        </div>
      </div>
      </Parkbar>

      {/* Aktuelles Jahr */}
      <Parkbar id="tr-jahr-aktuell" titel="Aktuelles Jahr">
      <div className="bg-primary-50 dark:bg-primary-900/20 rounded-xl p-4">
        <p className="text-sm text-primary-600 dark:text-primary-400 mb-1">{jahresvergleich.letztesJahr}</p>
        <div className="flex items-baseline gap-1">
          <span className="text-2xl font-bold text-primary-600 dark:text-primary-400">
            {fmtZahl(jahresvergleich.ertragLetzt, 0)}
          </span>
          <span className="text-sm text-primary-500">kWh/kWp</span>
        </div>
      </div>
      </Parkbar>

      {/* Veränderung */}
      <Parkbar id="tr-jahr-veraenderung" titel="Veränderung">
      <div className={`rounded-xl p-4 ${
        jahresvergleich.differenzProzent >= 0
          ? 'bg-green-50 dark:bg-green-900/20'
          : 'bg-red-50 dark:bg-red-900/20'
      }`}>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">Veränderung</p>
        <div className="flex items-center gap-2">
          {jahresvergleich.differenzProzent >= 0 ? (
            <ArrowUpRight className="h-6 w-6 text-green-500" />
          ) : jahresvergleich.differenzProzent <= -0.5 ? (
            <ArrowDownRight className="h-6 w-6 text-red-500" />
          ) : (
            <Minus className="h-6 w-6 text-gray-400 dark:text-gray-500" />
          )}
          <div>
            <span className={`text-2xl font-bold ${
              jahresvergleich.differenzProzent >= 0
                ? 'text-green-600 dark:text-green-400'
                : 'text-red-600 dark:text-red-400'
            }`}>
              {jahresvergleich.differenzProzent >= 0 ? '+' : ''}
              {fmtZahl(jahresvergleich.differenzProzent, 1)} %
            </span>
            <p className="text-xs text-gray-500">
              {jahresvergleich.differenz >= 0 ? '+' : ''}{fmtZahl(jahresvergleich.differenz, 0)} kWh/kWp
            </p>
          </div>
        </div>
      </div>
      </Parkbar>
    </div>
  )
}

// ─── Sektion: Typischer Monatsverlauf (LineChart) ─────────────────────────────

export function TypischerMonatsverlauf({ monatlicherDurchschnitt, ertragsverlauf }: {
  monatlicherDurchschnitt: TrendsDaten['monatlicherDurchschnitt']
  ertragsverlauf: TrendsDaten['ertragsverlauf']
}) {
  const achsen = useChartTheme()
  const schmal = useSchmaleAchse()
  return (
    <div>
      <Parkbar id="tr-monatsverlauf-chart" titel="Typischer Monatsverlauf (Diagramm)">
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={monatlicherDurchschnitt} margin={{ top: ACHSEN_MARGIN_TOP }}>
            <CartesianGrid strokeDasharray="3 3" stroke={achsen.grid} />
            <XAxis
              dataKey="name"
              {...xAchse(schmal)}
              /* achsen-allow: Zeit-/Kategorie-Achse */
            />
            <YAxis
              {...yAchse(schmal)}
              domain={[0, 'auto']}
              tickFormatter={achsenTick}
              label={achsenEinheit('kWh/kWp')}
            />
            <Tooltip
              content={<ChartTooltip
                unit="kWh/kWp"
                decimals={1}
                labelFormatter={(label) => MONATSNAMEN_LANG[MONATSNAMEN.indexOf(label as string)]}
              />}
            />
            <Legend content={<ChartLegende formatter={() => 'Durchschnittlicher Ertrag'} />} />
            <Line
              type="monotone"
              dataKey="durchschnitt"
              stroke={EIGENE_SERIE_FARBEN.du}
              strokeWidth={3}
              dot={{ fill: EIGENE_SERIE_FARBEN.du, strokeWidth: 2 }}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      </Parkbar>

      <Parkbar id="tr-monatsverlauf-caption" titel="Typischer Monatsverlauf (Hinweis)">
      <p className="text-sm text-gray-500 text-center mt-2">
        Basierend auf {ertragsverlauf.length} Monaten Daten
      </p>
      </Parkbar>
    </div>
  )
}

// ─── Sektion: Community-Entwicklung (LineChart) ───────────────────────────────

export function CommunityEntwicklung({ communityTrends }: {
  communityTrends: NonNullable<TrendsDaten['communityTrends']>
}) {
  const achsen = useChartTheme()
  const schmal = useSchmaleAchse()
  return (
    <div>
      <Parkbar id="tr-community-chart" titel="Community-Entwicklung (Diagramm)">
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={communityTrends.trends.speicher_quote.map((p, i) => ({
            monat: p.monat,
            speicher: p.wert,
            waermepumpe: communityTrends.trends.waermepumpe_quote[i]?.wert || 0,
            eauto: communityTrends.trends.eauto_quote[i]?.wert || 0,
          }))} margin={{ top: ACHSEN_MARGIN_TOP }}>
            <CartesianGrid strokeDasharray="3 3" stroke={achsen.grid} />
            <XAxis
              dataKey="monat"
              {...xAchse(schmal)}
              interval={1}
              /* achsen-allow: Zeit-/Kategorie-Achse */
            />
            <YAxis
              {...yAchse(schmal)}
              domain={[0, 100]}
              tickFormatter={achsenTick}
              label={achsenEinheit('%')}
            />
            <Tooltip content={<ChartTooltip
              unit="%"
              decimals={1}
              nameFormatter={(name) => {
                const labels: Record<string, string> = {
                  speicher: 'Speicher-Quote',
                  waermepumpe: 'Wärmepumpen-Quote',
                  eauto: 'E-Auto-Quote',
                }
                return labels[name] || name
              }}
            />} />
            <Legend content={<ChartLegende
              formatter={(value) => {
                const labels: Record<string, string> = {
                  speicher: 'Speicher-Quote',
                  waermepumpe: 'Wärmepumpen-Quote',
                  eauto: 'E-Auto-Quote',
                }
                return labels[value] || value
              }}
            />} />
            <Line type="monotone" dataKey="speicher" stroke={TYP_COLORS['speicher']} strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="waermepumpe" stroke={TYP_COLORS['waermepumpe']} strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="eauto" stroke={TYP_COLORS['e-auto']} strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      </Parkbar>

      <Parkbar id="tr-community-caption" titel="Community-Entwicklung (Hinweis)">
      <p className="text-sm text-gray-500 text-center mt-2">
        Anteil der Community-Anlagen mit jeweiliger Ausstattung
      </p>
      </Parkbar>
    </div>
  )
}

// ─── Sektion: Degradation nach Anlagenalter (LineChart) ───────────────────────

export function DegradationBlock({ degradation }: {
  degradation: NonNullable<TrendsDaten['degradation']>
}) {
  const achsen = useChartTheme()
  const schmal = useSchmaleAchse()
  return (
    <div>
      <Parkbar id="tr-degradation-chart" titel="Degradation (Diagramm)">
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={degradation.nach_alter} margin={{ top: ACHSEN_MARGIN_TOP }}>
            <CartesianGrid strokeDasharray="3 3" stroke={achsen.grid} />
            <XAxis
              dataKey="alter_jahre"
              {...xAchse(schmal)}
              tickFormatter={(v) => `${fmtZahl(v, 0)} Jahre`}
              /* achsen-allow: Zeit-/Kategorie-Achse (Anlagenalter), Format pro Tick (de-DE) */
            />
            <YAxis
              {...yAchse(schmal)}
              domain={['dataMin - 50', 'dataMax + 50']}
              tickFormatter={achsenTick}
              label={achsenEinheit('kWh/kWp')}
            />
            <Tooltip
              content={<ChartTooltip
                formatter={(value, name) => {
                  if (name === 'durchschnitt_spez_ertrag') return `${fmtZahl(value, 0)} kWh/kWp`
                  if (name === 'anzahl') return `${value} Anlagen`
                  return String(value)
                }}
                labelFormatter={(label) => `${label} Jahre alt`}
              />}
            />
            <Legend content={<ChartLegende formatter={() => 'Durchschnittlicher spez. Ertrag'} />} />
            <Line
              type="monotone"
              dataKey="durchschnitt_spez_ertrag"
              stroke={TYP_COLORS['pv-system']}
              strokeWidth={3}
              dot={{ fill: TYP_COLORS['pv-system'], strokeWidth: 2 }}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
      </Parkbar>

      <Parkbar id="tr-degradation-info" titel="Ø-Degradation">
      <div className="mt-4 p-4 bg-orange-50 dark:bg-orange-900/20 rounded-lg">
        <div className="flex items-center gap-2">
          <Info className="h-5 w-5 text-orange-500" />
          <span className="font-medium text-orange-900 dark:text-orange-100">
            Durchschnittliche Degradation: {fmtZahl(degradation.durchschnittliche_degradation_prozent_jahr, 2)} % / Jahr
          </span>
        </div>
        <p className="text-sm text-orange-700 dark:text-orange-300 mt-1">
          Basierend auf {degradation.nach_alter.reduce((sum, a) => sum + a.anzahl, 0)} Anlagen unterschiedlichen Alters
        </p>
      </div>
      </Parkbar>
    </div>
  )
}

// Re-Export der Icons für den Komposer (Card-Köpfe).
export { TrendingUp, Calendar, Sun, BarChart3 }
