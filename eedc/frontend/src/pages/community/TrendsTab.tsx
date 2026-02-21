/**
 * Community Trends Tab
 *
 * Zeitliche Entwicklungen basierend auf verfügbaren Monatswerten:
 * - Monatlicher Ertragsverlauf
 * - Saisonale Performance-Analyse
 * - Jahresvergleich
 * - Persönliche Entwicklung
 *
 * Hinweis: Community-weite Trends und Degradationsanalysen
 * erfordern erweiterte Server-Endpoints.
 */

import { useState, useEffect, useMemo } from 'react'
import {
  TrendingUp,
  Calendar,
  Sun,
  Snowflake,
  Cloud,
  Leaf,
  Info,
  BarChart3,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
} from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import { communityApi } from '../../api'
import type { CommunityBenchmarkResponse, ZeitraumTyp, TrendDaten, DegradationsAnalyse } from '../../api/community'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Area,
  AreaChart,
  Legend,
} from 'recharts'

// Monatsnamen
const MONATSNAMEN = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']
const MONATSNAMEN_LANG = [
  'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
  'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'
]

// Jahreszeiten
const JAHRESZEITEN = {
  fruehling: { name: 'Frühling', monate: [3, 4, 5], icon: Leaf, color: 'green' },
  sommer: { name: 'Sommer', monate: [6, 7, 8], icon: Sun, color: 'yellow' },
  herbst: { name: 'Herbst', monate: [9, 10, 11], icon: Cloud, color: 'orange' },
  winter: { name: 'Winter', monate: [12, 1, 2], icon: Snowflake, color: 'blue' },
}

interface TrendsTabProps {
  anlageId: number
  zeitraum: ZeitraumTyp
}

export default function TrendsTab({ anlageId, zeitraum }: TrendsTabProps) {
  const [benchmark, setBenchmark] = useState<CommunityBenchmarkResponse | null>(null)
  const [communityTrends, setCommunityTrends] = useState<TrendDaten | null>(null)
  const [degradation, setDegradation] = useState<DegradationsAnalyse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Benchmark und Community-Trends laden
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      setError(null)
      try {
        // Alle Daten parallel laden
        const [benchmarkData, trendsData, degradationData] = await Promise.all([
          communityApi.getBenchmark(anlageId, zeitraum),
          communityApi.getTrends('12_monate').catch(() => null),
          communityApi.getDegradation().catch(() => null),
        ])
        setBenchmark(benchmarkData)
        setCommunityTrends(trendsData)
        setDegradation(degradationData)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden')
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [anlageId, zeitraum])

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

  if (loading) {
    return <LoadingSpinner text="Lade Trend-Daten..." />
  }

  if (error) {
    return <Alert type="error">{error}</Alert>
  }

  if (!benchmark) {
    return null
  }

  return (
    <div className="space-y-6">
      {/* Ertragsverlauf */}
      {ertragsverlauf.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <TrendingUp className="h-5 w-5 text-primary-500" />
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                Ertragsverlauf
              </h3>
            </div>
            <span className="text-sm text-gray-500">{benchmark.zeitraum_label}</span>
          </div>

          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={ertragsverlauf}>
                <defs>
                  <linearGradient id="colorErtrag" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="var(--color-primary-500, #3b82f6)" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="var(--color-primary-500, #3b82f6)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="name"
                  tick={{ fill: '#6b7280', fontSize: 11 }}
                  interval={Math.floor(ertragsverlauf.length / 12)}
                />
                <YAxis
                  tick={{ fill: '#6b7280', fontSize: 12 }}
                  label={{
                    value: 'kWh/kWp',
                    angle: -90,
                    position: 'insideLeft',
                    style: { fill: '#6b7280', fontSize: 12 },
                  }}
                />
                <Tooltip
                  formatter={(value: number) => [`${value.toFixed(1)} kWh/kWp`, 'Spez. Ertrag']}
                  contentStyle={{
                    background: 'rgba(255,255,255,0.95)',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="ertrag"
                  stroke="var(--color-primary-500, #3b82f6)"
                  strokeWidth={2}
                  fill="url(#colorErtrag)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
      )}

      {/* Saisonale Analyse */}
      {saisonaleAnalyse && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <Calendar className="h-5 w-5 text-primary-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Saisonale Performance
            </h3>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
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
                <div key={jz.key} className={`rounded-xl p-4 ${colors.bg}`}>
                  <div className="flex items-center gap-2 mb-3">
                    <Icon className={`h-5 w-5 ${colors.icon}`} />
                    <span className={`font-medium ${colors.text}`}>{jz.name}</span>
                  </div>
                  <div className="flex items-baseline gap-1">
                    <span className="text-2xl font-bold text-gray-900 dark:text-white">
                      {jz.durchschnittMonat.toFixed(0)}
                    </span>
                    <span className="text-sm text-gray-500">kWh/kWp</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1">
                    Ø pro Monat ({jz.anzahlMonate} Monate)
                  </p>
                </div>
              )
            })}
          </div>
        </Card>
      )}

      {/* Jahresvergleich */}
      {jahresvergleich && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="h-5 w-5 text-primary-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Jahresvergleich
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {/* Vorjahr */}
            <div className="bg-gray-50 dark:bg-gray-800 rounded-xl p-4">
              <p className="text-sm text-gray-500 dark:text-gray-400 mb-1">{jahresvergleich.vorletztesJahr}</p>
              <div className="flex items-baseline gap-1">
                <span className="text-2xl font-bold text-gray-900 dark:text-white">
                  {jahresvergleich.ertragVorletzt.toFixed(0)}
                </span>
                <span className="text-sm text-gray-500">kWh/kWp</span>
              </div>
            </div>

            {/* Aktuelles Jahr */}
            <div className="bg-primary-50 dark:bg-primary-900/20 rounded-xl p-4">
              <p className="text-sm text-primary-600 dark:text-primary-400 mb-1">{jahresvergleich.letztesJahr}</p>
              <div className="flex items-baseline gap-1">
                <span className="text-2xl font-bold text-primary-600 dark:text-primary-400">
                  {jahresvergleich.ertragLetzt.toFixed(0)}
                </span>
                <span className="text-sm text-primary-500">kWh/kWp</span>
              </div>
            </div>

            {/* Veränderung */}
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
                  <Minus className="h-6 w-6 text-gray-400" />
                )}
                <div>
                  <span className={`text-2xl font-bold ${
                    jahresvergleich.differenzProzent >= 0
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-red-600 dark:text-red-400'
                  }`}>
                    {jahresvergleich.differenzProzent >= 0 ? '+' : ''}
                    {jahresvergleich.differenzProzent.toFixed(1)}%
                  </span>
                  <p className="text-xs text-gray-500">
                    {jahresvergleich.differenz >= 0 ? '+' : ''}{jahresvergleich.differenz.toFixed(0)} kWh/kWp
                  </p>
                </div>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Monatliche Durchschnitte */}
      {monatlicherDurchschnitt.some(m => m.anzahl > 1) && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <Sun className="h-5 w-5 text-primary-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Typischer Monatsverlauf
            </h3>
          </div>

          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={monatlicherDurchschnitt}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="name"
                  tick={{ fill: '#6b7280', fontSize: 11 }}
                />
                <YAxis
                  tick={{ fill: '#6b7280', fontSize: 12 }}
                  domain={[0, 'auto']}
                />
                <Tooltip
                  formatter={(value: number, name: string) => {
                    if (name === 'durchschnitt') return [`${value.toFixed(1)} kWh/kWp`, 'Ø Ertrag']
                    return [value, name]
                  }}
                  labelFormatter={(label) => MONATSNAMEN_LANG[MONATSNAMEN.indexOf(label as string)]}
                  contentStyle={{
                    background: 'rgba(255,255,255,0.95)',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                  }}
                />
                <Legend formatter={() => 'Durchschnittlicher Ertrag'} />
                <Line
                  type="monotone"
                  dataKey="durchschnitt"
                  stroke="var(--color-primary-500, #3b82f6)"
                  strokeWidth={3}
                  dot={{ fill: 'var(--color-primary-500, #3b82f6)', strokeWidth: 2 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <p className="text-sm text-gray-500 text-center mt-2">
            Basierend auf {ertragsverlauf.length} Monaten Daten
          </p>
        </Card>
      )}

      {/* Community-Trends: Ausstattungsquoten */}
      {communityTrends && communityTrends.trends.speicher_quote.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="h-5 w-5 text-green-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Community-Entwicklung
            </h3>
          </div>

          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={communityTrends.trends.speicher_quote.map((p, i) => ({
                monat: p.monat,
                speicher: p.wert,
                waermepumpe: communityTrends.trends.waermepumpe_quote[i]?.wert || 0,
                eauto: communityTrends.trends.eauto_quote[i]?.wert || 0,
              }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="monat"
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  interval={1}
                />
                <YAxis
                  tick={{ fill: '#6b7280', fontSize: 12 }}
                  domain={[0, 100]}
                  unit="%"
                />
                <Tooltip
                  formatter={(value: number, name: string) => {
                    const labels: Record<string, string> = {
                      speicher: 'Speicher',
                      waermepumpe: 'Wärmepumpe',
                      eauto: 'E-Auto',
                    }
                    return [`${value.toFixed(1)}%`, labels[name] || name]
                  }}
                  contentStyle={{
                    background: 'rgba(255,255,255,0.95)',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                  }}
                />
                <Legend
                  formatter={(value) => {
                    const labels: Record<string, string> = {
                      speicher: 'Speicher-Quote',
                      waermepumpe: 'Wärmepumpen-Quote',
                      eauto: 'E-Auto-Quote',
                    }
                    return labels[value] || value
                  }}
                />
                <Line type="monotone" dataKey="speicher" stroke="#22c55e" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="waermepumpe" stroke="#3b82f6" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="eauto" stroke="#a855f7" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <p className="text-sm text-gray-500 text-center mt-2">
            Anteil der Community-Anlagen mit jeweiliger Ausstattung
          </p>
        </Card>
      )}

      {/* Degradations-Analyse */}
      {degradation && degradation.nach_alter.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="h-5 w-5 text-orange-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Degradation nach Anlagenalter
            </h3>
          </div>

          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={degradation.nach_alter}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="alter_jahre"
                  tick={{ fill: '#6b7280', fontSize: 12 }}
                  label={{ value: 'Anlagenalter (Jahre)', position: 'bottom', offset: -5, fill: '#6b7280' }}
                />
                <YAxis
                  tick={{ fill: '#6b7280', fontSize: 12 }}
                  domain={['dataMin - 50', 'dataMax + 50']}
                  label={{
                    value: 'kWh/kWp',
                    angle: -90,
                    position: 'insideLeft',
                    style: { fill: '#6b7280' },
                  }}
                />
                <Tooltip
                  formatter={(value: number, name: string) => {
                    if (name === 'durchschnitt_spez_ertrag') return [`${value.toFixed(0)} kWh/kWp`, 'Ø Ertrag']
                    if (name === 'anzahl') return [value, 'Anlagen']
                    return [value, name]
                  }}
                  labelFormatter={(label) => `${label} Jahre alt`}
                  contentStyle={{
                    background: 'rgba(255,255,255,0.95)',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                  }}
                />
                <Legend formatter={() => 'Durchschnittlicher spez. Ertrag'} />
                <Line
                  type="monotone"
                  dataKey="durchschnitt_spez_ertrag"
                  stroke="#f97316"
                  strokeWidth={3}
                  dot={{ fill: '#f97316', strokeWidth: 2 }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-4 p-4 bg-orange-50 dark:bg-orange-900/20 rounded-lg">
            <div className="flex items-center gap-2">
              <Info className="h-5 w-5 text-orange-500" />
              <span className="font-medium text-orange-900 dark:text-orange-100">
                Durchschnittliche Degradation: {degradation.durchschnittliche_degradation_prozent_jahr.toFixed(2)}% / Jahr
              </span>
            </div>
            <p className="text-sm text-orange-700 dark:text-orange-300 mt-1">
              Basierend auf {degradation.nach_alter.reduce((sum, a) => sum + a.anzahl, 0)} Anlagen unterschiedlichen Alters
            </p>
          </div>
        </Card>
      )}
    </div>
  )
}
