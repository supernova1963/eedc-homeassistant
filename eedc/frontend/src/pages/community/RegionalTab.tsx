/**
 * Community Regional Tab
 *
 * Geografische Vergleiche:
 * - Regionale Position und Ranking
 * - Bundesland-Vergleich (tabellarisch)
 * - Regionale Insights
 *
 * Hinweis: Eine interaktive Karte (Choropleth) erfordert
 * zusätzliche Daten vom Community-Server und wird in einer
 * späteren Phase implementiert.
 */

import { useState, useEffect, useMemo } from 'react'
import {
  MapPin,
  Trophy,
  TrendingUp,
  TrendingDown,
  Users,
  Sun,
} from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import { communityApi } from '../../api'
import type { CommunityBenchmarkResponse, ZeitraumTyp, RegionStatistik } from '../../api/community'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'

// Bundesland-Daten
const BUNDESLAENDER: Record<string, { name: string; kurzname: string }> = {
  BW: { name: 'Baden-Württemberg', kurzname: 'BaWü' },
  BY: { name: 'Bayern', kurzname: 'Bayern' },
  BE: { name: 'Berlin', kurzname: 'Berlin' },
  BB: { name: 'Brandenburg', kurzname: 'Brandenb.' },
  HB: { name: 'Bremen', kurzname: 'Bremen' },
  HH: { name: 'Hamburg', kurzname: 'Hamburg' },
  HE: { name: 'Hessen', kurzname: 'Hessen' },
  MV: { name: 'Mecklenburg-Vorpommern', kurzname: 'MeckPom' },
  NI: { name: 'Niedersachsen', kurzname: 'Nieders.' },
  NW: { name: 'Nordrhein-Westfalen', kurzname: 'NRW' },
  RP: { name: 'Rheinland-Pfalz', kurzname: 'RhPf' },
  SL: { name: 'Saarland', kurzname: 'Saarland' },
  SN: { name: 'Sachsen', kurzname: 'Sachsen' },
  ST: { name: 'Sachsen-Anhalt', kurzname: 'SaAnh' },
  SH: { name: 'Schleswig-Holstein', kurzname: 'SchlHol' },
  TH: { name: 'Thüringen', kurzname: 'Thüring.' },
  AT: { name: 'Österreich', kurzname: 'Österr.' },
  CH: { name: 'Schweiz', kurzname: 'Schweiz' },
}

interface RegionalTabProps {
  anlageId: number
  zeitraum: ZeitraumTyp
}

export default function RegionalTab({ anlageId, zeitraum }: RegionalTabProps) {
  const [benchmark, setBenchmark] = useState<CommunityBenchmarkResponse | null>(null)
  const [allRegions, setAllRegions] = useState<RegionStatistik[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Benchmark und regionale Statistiken laden
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      setError(null)
      try {
        const [benchmarkData, regionsData] = await Promise.all([
          communityApi.getBenchmark(anlageId, zeitraum),
          communityApi.getRegionalStatistics().catch(() => []),
        ])
        setBenchmark(benchmarkData)
        setAllRegions(regionsData)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden')
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [anlageId, zeitraum])

  // Regionale Kennzahlen berechnen
  const regionalStats = useMemo(() => {
    if (!benchmark) return null

    const { spez_ertrag_anlage, spez_ertrag_region, spez_ertrag_durchschnitt, rang_region, anzahl_anlagen_region } = benchmark.benchmark
    const region = benchmark.anlage.region

    return {
      region,
      regionName: BUNDESLAENDER[region]?.name || region,
      spezErtrag: spez_ertrag_anlage,
      regionDurchschnitt: spez_ertrag_region,
      communityDurchschnitt: spez_ertrag_durchschnitt,
      rang: rang_region,
      anzahlAnlagen: anzahl_anlagen_region,
      abweichungRegion: ((spez_ertrag_anlage - spez_ertrag_region) / spez_ertrag_region) * 100,
      abweichungCommunity: ((spez_ertrag_region - spez_ertrag_durchschnitt) / spez_ertrag_durchschnitt) * 100,
      perzentilRegion: Math.round((1 - rang_region / anzahl_anlagen_region) * 100),
    }
  }, [benchmark])

  // Vergleichsdaten für Chart
  const vergleichsData = useMemo(() => {
    if (!regionalStats) return []

    return [
      {
        name: 'Du',
        wert: regionalStats.spezErtrag,
        fill: 'var(--color-primary-500, #3b82f6)',
      },
      {
        name: regionalStats.regionName,
        wert: regionalStats.regionDurchschnitt,
        fill: '#60a5fa',
      },
      {
        name: 'Community',
        wert: regionalStats.communityDurchschnitt,
        fill: '#9ca3af',
      },
    ]
  }, [regionalStats])

  if (loading) {
    return <LoadingSpinner text="Lade regionale Daten..." />
  }

  if (error) {
    return <Alert type="error">{error}</Alert>
  }

  if (!benchmark || !regionalStats) {
    return null
  }

  return (
    <div className="space-y-6">
      {/* Zeitraum-Hinweis */}
      <div className="flex items-center justify-end">
        <span className="text-sm text-gray-500 dark:text-gray-400">
          Betrachtungszeitraum: {benchmark.zeitraum_label}
        </span>
      </div>

      {/* Regionale Position */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Dein Bundesland */}
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30">
              <MapPin className="h-5 w-5 text-blue-500" />
            </div>
            <span className="text-sm text-gray-500 dark:text-gray-400">Dein Standort</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-2xl font-bold text-gray-900 dark:text-white">
              {regionalStats.regionName}
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            {regionalStats.anzahlAnlagen} Anlagen in der Region
          </p>
        </Card>

        {/* Rang in Region */}
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 rounded-lg bg-yellow-100 dark:bg-yellow-900/30">
              <Trophy className="h-5 w-5 text-yellow-500" />
            </div>
            <span className="text-sm text-gray-500 dark:text-gray-400">Rang in {BUNDESLAENDER[regionalStats.region]?.kurzname || regionalStats.region}</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-gray-900 dark:text-white">
              #{regionalStats.rang}
            </span>
            <span className="text-gray-500 dark:text-gray-400">
              von {regionalStats.anzahlAnlagen}
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Besser als {regionalStats.perzentilRegion}% in deiner Region
          </p>
        </Card>

        {/* Abweichung vom Regions-Durchschnitt */}
        <Card>
          <div className="flex items-center gap-3 mb-2">
            <div className={`p-2 rounded-lg ${
              regionalStats.abweichungRegion >= 0
                ? 'bg-green-100 dark:bg-green-900/30'
                : 'bg-red-100 dark:bg-red-900/30'
            }`}>
              {regionalStats.abweichungRegion >= 0 ? (
                <TrendingUp className="h-5 w-5 text-green-500" />
              ) : (
                <TrendingDown className="h-5 w-5 text-red-500" />
              )}
            </div>
            <span className="text-sm text-gray-500 dark:text-gray-400">vs. Region</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className={`text-3xl font-bold ${
              regionalStats.abweichungRegion >= 0
                ? 'text-green-600 dark:text-green-400'
                : 'text-red-600 dark:text-red-400'
            }`}>
              {regionalStats.abweichungRegion >= 0 ? '+' : ''}
              {regionalStats.abweichungRegion.toFixed(1)}%
            </span>
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Ø Region: {regionalStats.regionDurchschnitt.toFixed(0)} kWh/kWp
          </p>
        </Card>
      </div>

      {/* Vergleichs-Chart */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Sun className="h-5 w-5 text-primary-500" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Spezifischer Ertrag im Vergleich
          </h3>
        </div>

        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={vergleichsData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" horizontal={true} vertical={false} />
              <XAxis
                type="number"
                tick={{ fill: '#6b7280', fontSize: 12 }}
                domain={[0, 'auto']}
                label={{
                  value: 'kWh/kWp',
                  position: 'bottom',
                  style: { fill: '#6b7280', fontSize: 12 },
                }}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: '#6b7280', fontSize: 12 }}
                width={100}
              />
              <Tooltip
                formatter={(value: number) => [`${value.toFixed(0)} kWh/kWp`, 'Spez. Ertrag']}
                contentStyle={{
                  background: 'rgba(255,255,255,0.95)',
                  border: '1px solid #e5e7eb',
                  borderRadius: '8px',
                }}
              />
              <Bar dataKey="wert" radius={[0, 4, 4, 0]}>
                {vergleichsData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={entry.fill} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>

      {/* Regionale Insights */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Users className="h-5 w-5 text-primary-500" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Regionale Einordnung
          </h3>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Region vs. Community */}
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
            <h4 className="font-medium text-gray-900 dark:text-white mb-2">
              {regionalStats.regionName} vs. Community
            </h4>
            <div className="flex items-center gap-2 mb-2">
              <span className={`text-lg font-semibold ${
                regionalStats.abweichungCommunity >= 0
                  ? 'text-green-600 dark:text-green-400'
                  : 'text-red-600 dark:text-red-400'
              }`}>
                {regionalStats.abweichungCommunity >= 0 ? '+' : ''}
                {regionalStats.abweichungCommunity.toFixed(1)}%
              </span>
              <span className="text-gray-500 dark:text-gray-400">
                {regionalStats.abweichungCommunity >= 0 ? 'über' : 'unter'} dem Durchschnitt
              </span>
            </div>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Deine Region liegt {regionalStats.abweichungCommunity >= 0 ? 'über' : 'unter'} dem
              bundesweiten Community-Durchschnitt von {regionalStats.communityDurchschnitt.toFixed(0)} kWh/kWp.
            </p>
          </div>

          {/* Deine Anlage */}
          <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
            <h4 className="font-medium text-gray-900 dark:text-white mb-2">
              Deine Anlage
            </h4>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-gray-500 dark:text-gray-400">Ausrichtung:</span>
                <span className="text-gray-900 dark:text-white capitalize">{benchmark.anlage.ausrichtung}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 dark:text-gray-400">Neigung:</span>
                <span className="text-gray-900 dark:text-white">{benchmark.anlage.neigung_grad}°</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 dark:text-gray-400">Leistung:</span>
                <span className="text-gray-900 dark:text-white">{benchmark.anlage.kwp} kWp</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500 dark:text-gray-400">Installation:</span>
                <span className="text-gray-900 dark:text-white">{benchmark.anlage.installation_jahr}</span>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* Bundesländer-Übersicht */}
      {allRegions.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <MapPin className="h-5 w-5 text-green-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Alle Regionen im Vergleich
            </h3>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="text-left py-2 px-3 text-gray-500 font-medium">Region</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium">Anlagen</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium">Ø kWp</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium">Ø kWh/kWp</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium">Speicher</th>
                </tr>
              </thead>
              <tbody>
                {allRegions
                  .sort((a, b) => b.durchschnitt_spez_ertrag - a.durchschnitt_spez_ertrag)
                  .map((region, index) => {
                    const isOwn = region.region === benchmark?.anlage.region
                    return (
                      <tr
                        key={region.region}
                        className={`border-b border-gray-100 dark:border-gray-800 ${
                          isOwn ? 'bg-primary-50 dark:bg-primary-900/20' : ''
                        }`}
                      >
                        <td className="py-2 px-3">
                          <div className="flex items-center gap-2">
                            <span className={`text-xs font-medium w-5 text-center ${
                              index < 3 ? 'text-yellow-600' : 'text-gray-400'
                            }`}>
                              {index + 1}
                            </span>
                            <span className={`font-medium ${isOwn ? 'text-primary-600 dark:text-primary-400' : 'text-gray-900 dark:text-white'}`}>
                              {BUNDESLAENDER[region.region]?.name || region.region}
                            </span>
                            {isOwn && <span className="text-xs text-primary-500">(Du)</span>}
                          </div>
                        </td>
                        <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400">
                          {region.anzahl_anlagen}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400">
                          {region.durchschnitt_kwp.toFixed(1)}
                        </td>
                        <td className="py-2 px-3 text-right font-medium text-gray-900 dark:text-white">
                          {region.durchschnitt_spez_ertrag.toFixed(0)}
                        </td>
                        <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400">
                          {region.ausstattung?.speicher?.toFixed(0) || '-'}%
                        </td>
                      </tr>
                    )
                  })}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  )
}
