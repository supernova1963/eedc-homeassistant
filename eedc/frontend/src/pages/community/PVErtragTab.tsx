/**
 * Community PV-Ertrag Tab
 *
 * Detaillierter Ertragsvergleich mit:
 * - Monatlicher Ertrag mit Community-Durchschnittslinie
 * - Perzentil-Anzeige (Wo stehe ich?)
 * - Performance-Kennzahlen
 * - Jahresübersicht
 */

import { useState, useEffect, useMemo } from 'react'
import {
  Sun,
  TrendingUp,
  TrendingDown,
  Calendar,
  Target,
  Award,
} from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import { communityApi } from '../../api'
import type { CommunityBenchmarkResponse, ZeitraumTyp, Verteilung, MonatlicheDurchschnitte } from '../../api/community'
import {
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ComposedChart,
  Line,
} from 'recharts'

interface PVErtragTabProps {
  anlageId: number
  zeitraum: ZeitraumTyp
}

export default function PVErtragTab({ anlageId, zeitraum }: PVErtragTabProps) {
  const [benchmark, setBenchmark] = useState<CommunityBenchmarkResponse | null>(null)
  const [distribution, setDistribution] = useState<Verteilung | null>(null)
  const [monthlyAverages, setMonthlyAverages] = useState<MonatlicheDurchschnitte | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Benchmark und Community-Daten laden
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      setError(null)
      try {
        const [benchmarkData, distData, monthlyData] = await Promise.all([
          communityApi.getBenchmark(anlageId, zeitraum),
          communityApi.getDistribution('spez_ertrag', 15).catch(() => null),
          communityApi.getMonthlyAverages(24).catch(() => null), // Letzte 24 Monate
        ])
        setBenchmark(benchmarkData)
        setDistribution(distData)
        setMonthlyAverages(monthlyData)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden')
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [anlageId, zeitraum])

  // Monatsdaten für Chart aufbereiten - mit echten monatlichen Community-Durchschnitten
  const chartData = useMemo(() => {
    if (!benchmark?.anlage.monatswerte) return []

    const monatsnamen = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez']

    // Map für schnellen Zugriff auf monatliche Durchschnitte
    const avgMap = new Map<string, number>()
    if (monthlyAverages?.monate) {
      monthlyAverages.monate.forEach(m => {
        avgMap.set(`${m.jahr}-${m.monat}`, m.spez_ertrag_avg)
      })
    }

    // Sortiere chronologisch und nimm die letzten 12 Monate
    const sortedMonatswerte = [...benchmark.anlage.monatswerte]
      .sort((a, b) => a.jahr - b.jahr || a.monat - b.monat)
      .slice(-12)

    return sortedMonatswerte.map(m => {
      const spezErtrag = m.spez_ertrag_kwh_kwp || 0

      // Versuche zuerst den exakten Monat, dann Durchschnitt desselben Monats aus Vorjahr
      let durchschnitt = avgMap.get(`${m.jahr}-${m.monat}`)
      if (durchschnitt === undefined) {
        durchschnitt = avgMap.get(`${m.jahr - 1}-${m.monat}`)
      }
      // Fallback: Jahresdurchschnitt / 12 (nur wenn keine monatlichen Daten)
      if (durchschnitt === undefined) {
        durchschnitt = benchmark.benchmark.spez_ertrag_durchschnitt / 12
      }

      const abweichung = durchschnitt > 0 ? ((spezErtrag - durchschnitt) / durchschnitt) * 100 : 0

      return {
        name: `${monatsnamen[m.monat - 1]} ${m.jahr % 100}`,
        monat: m.monat,
        jahr: m.jahr,
        ertrag: spezErtrag,
        durchschnitt: durchschnitt,
        abweichung: abweichung,
        isPositive: abweichung >= 0,
      }
    })
  }, [benchmark, monthlyAverages])

  // Jahres-Aggregation
  const jahresStats = useMemo(() => {
    if (!benchmark?.anlage.monatswerte) return null

    const monatswerte = benchmark.anlage.monatswerte
    const jahre = [...new Set(monatswerte.map(m => m.jahr))].sort()

    return jahre.map(jahr => {
      const jahrDaten = monatswerte.filter(m => m.jahr === jahr)
      const summeErtrag = jahrDaten.reduce((sum, m) => sum + (m.spez_ertrag_kwh_kwp || 0), 0)
      const anzahlMonate = jahrDaten.length

      return {
        jahr,
        spezErtrag: summeErtrag,
        anzahlMonate,
        vollstaendig: anzahlMonate === 12,
      }
    })
  }, [benchmark])

  // Perzentil berechnen
  const perzentil = useMemo(() => {
    if (!benchmark) return null
    const { rang_gesamt, anzahl_anlagen_gesamt } = benchmark.benchmark
    return Math.round((1 - rang_gesamt / anzahl_anlagen_gesamt) * 100)
  }, [benchmark])

  // Performance-Kennzahlen
  const performanceStats = useMemo(() => {
    if (!benchmark) return null

    const { spez_ertrag_anlage, spez_ertrag_durchschnitt, spez_ertrag_region } = benchmark.benchmark

    return {
      abweichungGesamt: ((spez_ertrag_anlage - spez_ertrag_durchschnitt) / spez_ertrag_durchschnitt) * 100,
      abweichungRegion: ((spez_ertrag_anlage - spez_ertrag_region) / spez_ertrag_region) * 100,
      differenzAbsolut: spez_ertrag_anlage - spez_ertrag_durchschnitt,
    }
  }, [benchmark])

  if (loading) {
    return <LoadingSpinner text="Lade PV-Ertragsdaten..." />
  }

  if (error) {
    return <Alert type="error">{error}</Alert>
  }

  if (!benchmark) {
    return null
  }

  return (
    <div className="space-y-6">
      {/* Performance-Übersicht */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Perzentil-Karte */}
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-lg bg-primary-100 dark:bg-primary-900/30">
              <Award className="h-5 w-5 text-primary-500" />
            </div>
            <span className="text-sm text-gray-500 dark:text-gray-400">Deine Position</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-gray-900 dark:text-white">
              Top {100 - (perzentil || 0)}%
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Besser als {perzentil}% der Community
          </p>
        </Card>

        {/* Abweichung Gesamt */}
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className={`p-2 rounded-lg ${
              (performanceStats?.abweichungGesamt || 0) >= 0
                ? 'bg-green-100 dark:bg-green-900/30'
                : 'bg-red-100 dark:bg-red-900/30'
            }`}>
              {(performanceStats?.abweichungGesamt || 0) >= 0 ? (
                <TrendingUp className="h-5 w-5 text-green-500" />
              ) : (
                <TrendingDown className="h-5 w-5 text-red-500" />
              )}
            </div>
            <span className="text-sm text-gray-500 dark:text-gray-400">vs. Community</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className={`text-3xl font-bold ${
              (performanceStats?.abweichungGesamt || 0) >= 0
                ? 'text-green-600 dark:text-green-400'
                : 'text-red-600 dark:text-red-400'
            }`}>
              {(performanceStats?.abweichungGesamt || 0) >= 0 ? '+' : ''}
              {performanceStats?.abweichungGesamt.toFixed(1)}%
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {performanceStats?.differenzAbsolut.toFixed(0)} kWh/kWp Differenz
          </p>
        </Card>

        {/* Abweichung Region */}
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className={`p-2 rounded-lg ${
              (performanceStats?.abweichungRegion || 0) >= 0
                ? 'bg-green-100 dark:bg-green-900/30'
                : 'bg-red-100 dark:bg-red-900/30'
            }`}>
              <Target className="h-5 w-5 text-blue-500" />
            </div>
            <span className="text-sm text-gray-500 dark:text-gray-400">vs. Region</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className={`text-3xl font-bold ${
              (performanceStats?.abweichungRegion || 0) >= 0
                ? 'text-green-600 dark:text-green-400'
                : 'text-red-600 dark:text-red-400'
            }`}>
              {(performanceStats?.abweichungRegion || 0) >= 0 ? '+' : ''}
              {performanceStats?.abweichungRegion.toFixed(1)}%
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Vergleich mit deinem Bundesland
          </p>
        </Card>
      </div>

      {/* Monatlicher Ertrag mit Community-Vergleich */}
      {chartData.length > 0 && (
        <Card>
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Sun className="h-5 w-5 text-primary-500" />
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                Monatlicher Ertrag vs. Community
              </h3>
            </div>
            <span className="text-sm text-gray-500">{benchmark.zeitraum_label}</span>
          </div>

          <div className="h-72">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="name"
                  tick={{ fill: '#6b7280', fontSize: 11 }}
                  interval={0}
                  angle={-45}
                  textAnchor="end"
                  height={60}
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
                  formatter={(value: number, name: string) => {
                    if (name === 'ertrag') return [`${value.toFixed(1)} kWh/kWp`, 'Dein Ertrag']
                    if (name === 'durchschnitt') return [`${value.toFixed(1)} kWh/kWp`, 'Ø Community']
                    return [value, name]
                  }}
                  contentStyle={{
                    background: 'rgba(255,255,255,0.95)',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                  }}
                />
                {/* Community-Durchschnitt als Linie */}
                <Line
                  type="monotone"
                  dataKey="durchschnitt"
                  stroke="#9ca3af"
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={false}
                  name="durchschnitt"
                />
                {/* Eigener Ertrag als Balken */}
                <Bar dataKey="ertrag" radius={[4, 4, 0, 0]} name="ertrag">
                  {chartData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.isPositive ? '#22c55e' : '#ef4444'}
                      fillOpacity={0.8}
                    />
                  ))}
                </Bar>
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="flex items-center justify-center gap-6 mt-4 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-4 h-3 bg-green-500 rounded" />
              <span className="text-gray-600 dark:text-gray-400">Über Monats-Ø</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-4 h-3 bg-red-500 rounded" />
              <span className="text-gray-600 dark:text-gray-400">Unter Monats-Ø</span>
            </div>
            <div className="flex items-center gap-2">
              <div className="w-6 h-0 border-t-2 border-dashed border-gray-400" />
              <span className="text-gray-600 dark:text-gray-400">Community Monats-Ø</span>
            </div>
          </div>
        </Card>
      )}

      {/* Jahresübersicht */}
      {jahresStats && jahresStats.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <Calendar className="h-5 w-5 text-primary-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Jahresübersicht
            </h3>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="text-left py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Jahr</th>
                  <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Spez. Ertrag</th>
                  <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">vs. Community</th>
                  <th className="text-right py-3 px-4 text-sm font-medium text-gray-500 dark:text-gray-400">Monate</th>
                </tr>
              </thead>
              <tbody>
                {jahresStats.map((js) => {
                  const abweichung = ((js.spezErtrag - benchmark.benchmark.spez_ertrag_durchschnitt) /
                    benchmark.benchmark.spez_ertrag_durchschnitt) * 100
                  const isPositive = abweichung >= 0

                  return (
                    <tr key={js.jahr} className="border-b border-gray-100 dark:border-gray-800 last:border-0">
                      <td className="py-3 px-4">
                        <span className="font-medium text-gray-900 dark:text-white">{js.jahr}</span>
                        {!js.vollstaendig && (
                          <span className="ml-2 text-xs text-gray-400">(unvollständig)</span>
                        )}
                      </td>
                      <td className="text-right py-3 px-4">
                        <span className="font-semibold text-gray-900 dark:text-white">
                          {js.spezErtrag.toFixed(0)} kWh/kWp
                        </span>
                      </td>
                      <td className="text-right py-3 px-4">
                        <span className={`font-medium ${
                          isPositive ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                        }`}>
                          {isPositive ? '+' : ''}{abweichung.toFixed(1)}%
                        </span>
                      </td>
                      <td className="text-right py-3 px-4 text-gray-500 dark:text-gray-400">
                        {js.anzahlMonate}/12
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Verteilungs-Histogramm */}
      {distribution && distribution.bins.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <Target className="h-5 w-5 text-purple-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Verteilung in der Community
            </h3>
          </div>

          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={distribution.bins.map(bin => ({
                range: `${bin.von.toFixed(0)}-${bin.bis.toFixed(0)}`,
                anzahl: bin.anzahl,
                isOwn: benchmark.benchmark.spez_ertrag_anlage >= bin.von &&
                       benchmark.benchmark.spez_ertrag_anlage < bin.bis,
              }))}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                <XAxis
                  dataKey="range"
                  tick={{ fill: '#6b7280', fontSize: 10 }}
                  angle={-45}
                  textAnchor="end"
                  height={60}
                />
                <YAxis tick={{ fill: '#6b7280', fontSize: 12 }} />
                <Tooltip
                  formatter={(value: number) => [`${value} Anlagen`, 'Anzahl']}
                  labelFormatter={(label) => `${label} kWh/kWp`}
                  contentStyle={{
                    background: 'rgba(255,255,255,0.95)',
                    border: '1px solid #e5e7eb',
                    borderRadius: '8px',
                  }}
                />
                <Bar dataKey="anzahl" radius={[4, 4, 0, 0]}>
                  {distribution.bins.map((bin, index) => {
                    const isOwn = benchmark.benchmark.spez_ertrag_anlage >= bin.von &&
                                  benchmark.benchmark.spez_ertrag_anlage < bin.bis
                    return (
                      <Cell
                        key={`cell-${index}`}
                        fill={isOwn ? '#8b5cf6' : '#d1d5db'}
                        fillOpacity={isOwn ? 1 : 0.7}
                      />
                    )
                  })}
                </Bar>
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div className="text-center">
              <p className="text-gray-500">Minimum</p>
              <p className="font-semibold">{distribution.statistik.min.toFixed(0)} kWh/kWp</p>
            </div>
            <div className="text-center">
              <p className="text-gray-500">Durchschnitt</p>
              <p className="font-semibold">{distribution.statistik.durchschnitt.toFixed(0)} kWh/kWp</p>
            </div>
            <div className="text-center">
              <p className="text-gray-500">Median</p>
              <p className="font-semibold">{distribution.statistik.median.toFixed(0)} kWh/kWp</p>
            </div>
            <div className="text-center">
              <p className="text-gray-500">Maximum</p>
              <p className="font-semibold">{distribution.statistik.max.toFixed(0)} kWh/kWp</p>
            </div>
          </div>

          <div className="flex items-center justify-center gap-4 mt-3 text-sm">
            <div className="flex items-center gap-2">
              <div className="w-4 h-3 bg-purple-500 rounded" />
              <span className="text-gray-600 dark:text-gray-400">Deine Position</span>
            </div>
          </div>
        </Card>
      )}

      {/* Performance-Hinweis */}
      <Card className="bg-gray-50 dark:bg-gray-800/50">
        <div className="flex items-start gap-3">
          <Sun className="h-5 w-5 text-primary-500 mt-0.5" />
          <div>
            <h4 className="font-medium text-gray-900 dark:text-white mb-1">
              Über den Vergleich
            </h4>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Der Community-Durchschnitt basiert auf {benchmark.benchmark.anzahl_anlagen_gesamt} Anlagen.
              Dein spezifischer Ertrag von <strong>{benchmark.benchmark.spez_ertrag_anlage.toFixed(0)} kWh/kWp</strong> liegt
              {' '}{(performanceStats?.abweichungGesamt || 0) >= 0 ? 'über' : 'unter'} dem Durchschnitt von
              {' '}<strong>{benchmark.benchmark.spez_ertrag_durchschnitt.toFixed(0)} kWh/kWp</strong>.
              Faktoren wie Ausrichtung ({benchmark.anlage.ausrichtung}), Neigung ({benchmark.anlage.neigung_grad}°)
              und regionale Sonneneinstrahlung beeinflussen die Ergebnisse.
            </p>
          </div>
        </div>
      </Card>
    </div>
  )
}
