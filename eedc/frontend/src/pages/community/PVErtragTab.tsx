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
import { useChartTheme } from '../../context/ThemeContext'
import { MONAT_KURZ, STATUS_COLORS, EIGENE_SERIE_FARBEN, SERIE_NEUTRAL, ACHSEN_TICK, ACHSEN_MARGIN_TOP, achsenEinheit, achsenTick } from '../../lib'
import {
  Sun,
  TrendingUp,
  TrendingDown,
  Calendar,
  Target,
  Award,
} from 'lucide-react'
import { Card, LoadingSpinner, Alert, KPICard } from '../../components/ui'
import ChartTooltip from '../../components/ui/ChartTooltip'
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
  benchmark: CommunityBenchmarkResponse | null
  benchmarkLoading: boolean
  benchmarkError: string | null
}

export default function PVErtragTab({ benchmark, benchmarkLoading, benchmarkError }: PVErtragTabProps) {
  const achsen = useChartTheme()
  const [distribution, setDistribution] = useState<Verteilung | null>(null)
  const [monthlyAverages, setMonthlyAverages] = useState<MonatlicheDurchschnitte | null>(null)
  const [extraLoading, setExtraLoading] = useState(false)

  const loading = benchmarkLoading || extraLoading
  const error = benchmarkError

  // Zusätzliche Community-Daten laden (Distribution + Monatsdurchschnitte)
  useEffect(() => {
    const loadExtra = async () => {
      setExtraLoading(true)
      try {
        const [distData, monthlyData] = await Promise.all([
          communityApi.getDistribution('spez_ertrag', 15).catch(() => null),
          communityApi.getMonthlyAverages(24).catch(() => null),
        ])
        setDistribution(distData)
        setMonthlyAverages(monthlyData)
      } catch {
        // Ignoriere Fehler bei Zusatzdaten
      } finally {
        setExtraLoading(false)
      }
    }
    loadExtra()
  }, [])

  // Monatsdaten für Chart aufbereiten - mit echten monatlichen Community-Durchschnitten
  const chartData = useMemo(() => {
    if (!benchmark?.anlage.monatswerte) return []

    const monatsnamen = MONAT_KURZ.slice(1)

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
    // Absteigend sortieren (#211 P3 detLAN: neueste oben)
    const jahre = [...new Set(monatswerte.map(m => m.jahr))].sort((a, b) => b - a)

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
        <KPICard
          title="Deine Position"
          value={`Top ${100 - (perzentil || 0)} %`}
          subtitle={`Besser als ${perzentil} % der Community`}
          color="blue"
          icon={Award}
        />

        {/* Abweichung Gesamt */}
        <KPICard
          title="vs. Community"
          value={`${(performanceStats?.abweichungGesamt || 0) >= 0 ? '+' : ''}${performanceStats?.abweichungGesamt.toFixed(1)}`}
          unit="%"
          subtitle={`${performanceStats?.differenzAbsolut.toFixed(0)} kWh/kWp Differenz`}
          color={(performanceStats?.abweichungGesamt || 0) >= 0 ? 'green' : 'red'}
          icon={(performanceStats?.abweichungGesamt || 0) >= 0 ? TrendingUp : TrendingDown}
        />

        {/* Abweichung Region */}
        <KPICard
          title="vs. Region"
          value={`${(performanceStats?.abweichungRegion || 0) >= 0 ? '+' : ''}${performanceStats?.abweichungRegion.toFixed(1)}`}
          unit="%"
          subtitle="Vergleich mit deinem Bundesland"
          color={(performanceStats?.abweichungRegion || 0) >= 0 ? 'green' : 'red'}
          icon={Target}
        />
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
              <ComposedChart data={chartData} margin={{ top: ACHSEN_MARGIN_TOP }}>
                <CartesianGrid strokeDasharray="3 3" stroke={achsen.grid} />
                <XAxis
                  dataKey="name"
                  tick={ACHSEN_TICK}
                  interval={0}
                  angle={-45}
                  textAnchor="end"
                  height={60}
                  /* achsen-allow: Zeit-/Kategorie-Achse (Monat) */
                />
                <YAxis
                  tick={ACHSEN_TICK}
                  tickFormatter={achsenTick}
                  label={achsenEinheit('kWh/kWp')}
                />
                <Tooltip
                  content={<ChartTooltip
                    formatter={(value, name) => {
                      if (name === 'ertrag') return `${value.toFixed(1)} kWh/kWp`
                      if (name === 'durchschnitt') return `${value.toFixed(1)} kWh/kWp`
                      return String(value)
                    }}
                  />}
                />
                {/* Community-Durchschnitt als Linie */}
                <Line
                  type="monotone"
                  dataKey="durchschnitt"
                  stroke={achsen.referenz}
                  strokeWidth={2}
                  strokeDasharray="5 5"
                  dot={false}
                  name="durchschnitt"
                />
                {/* Eigener Ertrag als Balken */}
                <Bar dataKey="ertrag" radius={[2, 2, 0, 0]} name="ertrag">
                  {chartData.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={entry.isPositive ? STATUS_COLORS.ok : STATUS_COLORS.kritisch}
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
                          <span className="ml-2 text-xs text-gray-400 dark:text-gray-500">(unvollständig)</span>
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
                          {isPositive ? '+' : ''}{abweichung.toFixed(1)} %
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
              }))} margin={{ top: ACHSEN_MARGIN_TOP }}>
                <CartesianGrid strokeDasharray="3 3" stroke={achsen.grid} />
                <XAxis
                  dataKey="range"
                  tick={ACHSEN_TICK}
                  angle={-45}
                  textAnchor="end"
                  height={60}
                  /* achsen-allow: Kategorie-Achse (Ertragsklassen kWh/kWp) */
                />
                <YAxis tick={ACHSEN_TICK} tickFormatter={achsenTick} label={achsenEinheit('Anlagen')} />
                <Tooltip
                  content={<ChartTooltip
                    formatter={(value) => `${value} Anlagen`}
                    labelFormatter={(label) => `${label} kWh/kWp`}
                  />}
                />
                <Bar dataKey="anzahl" radius={[2, 2, 0, 0]}>
                  {distribution.bins.map((bin, index) => {
                    const isOwn = benchmark.benchmark.spez_ertrag_anlage >= bin.von &&
                                  benchmark.benchmark.spez_ertrag_anlage < bin.bis
                    return (
                      <Cell
                        key={`cell-${index}`}
                        fill={isOwn ? EIGENE_SERIE_FARBEN.du : SERIE_NEUTRAL}
                        fillOpacity={isOwn ? 1 : 0.7}
                      />
                    )
                  })}
                </Bar>
              </ComposedChart>
            </ResponsiveContainer>
          </div>

          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4 text-sm">
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
