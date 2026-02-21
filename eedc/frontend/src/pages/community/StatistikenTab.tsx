/**
 * Community Statistiken Tab
 *
 * Community-weite Insights basierend auf verfügbaren Benchmark-Daten:
 * - Community-Zusammenfassung
 * - Deine Position in der Community
 * - Ausstattungsvergleich
 * - Regionale Verteilung (aggregiert)
 *
 * Hinweis: Detaillierte Verteilungen und Top-10-Listen
 * erfordern erweiterte Server-Endpoints.
 */

import { useState, useEffect, useMemo } from 'react'
import {
  BarChart3,
  Users,
  Sun,
  Battery,
  Home,
  Car,
  Plug,
  MapPin,
  TrendingUp,
  CheckCircle2,
  XCircle,
  Calendar,
  Zap,
  Award,
} from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import { communityApi } from '../../api'
import type { CommunityBenchmarkResponse, ZeitraumTyp, GlobaleStatistik, Ranking } from '../../api/community'

// Bundesland-Namen
const REGION_NAMEN: Record<string, string> = {
  BW: 'Baden-Württemberg',
  BY: 'Bayern',
  BE: 'Berlin',
  BB: 'Brandenburg',
  HB: 'Bremen',
  HH: 'Hamburg',
  HE: 'Hessen',
  MV: 'Mecklenburg-Vorpommern',
  NI: 'Niedersachsen',
  NW: 'Nordrhein-Westfalen',
  RP: 'Rheinland-Pfalz',
  SL: 'Saarland',
  SN: 'Sachsen',
  ST: 'Sachsen-Anhalt',
  SH: 'Schleswig-Holstein',
  TH: 'Thüringen',
  AT: 'Österreich',
  CH: 'Schweiz',
}

interface StatistikenTabProps {
  anlageId: number
  zeitraum: ZeitraumTyp
}

export default function StatistikenTab({ anlageId, zeitraum }: StatistikenTabProps) {
  const [benchmark, setBenchmark] = useState<CommunityBenchmarkResponse | null>(null)
  const [globalStats, setGlobalStats] = useState<GlobaleStatistik | null>(null)
  const [ranking, setRanking] = useState<Ranking | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Benchmark und globale Statistiken laden
  useEffect(() => {
    const loadData = async () => {
      setLoading(true)
      setError(null)
      try {
        // Alle Daten parallel laden
        const [benchmarkData, globalData, rankingData] = await Promise.all([
          communityApi.getBenchmark(anlageId, zeitraum),
          communityApi.getGlobalStatistics().catch(() => null),
          communityApi.getRanking('spez_ertrag', 10).catch(() => null),
        ])
        setBenchmark(benchmarkData)
        setGlobalStats(globalData)
        setRanking(rankingData)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Fehler beim Laden')
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [anlageId, zeitraum])

  // Community-Statistiken aus Benchmark ableiten
  const communityStats = useMemo(() => {
    if (!benchmark) return null

    return {
      anzahlAnlagen: benchmark.benchmark.anzahl_anlagen_gesamt,
      anzahlRegion: benchmark.benchmark.anzahl_anlagen_region,
      durchschnittErtrag: benchmark.benchmark.spez_ertrag_durchschnitt,
      regionErtrag: benchmark.benchmark.spez_ertrag_region,
      region: benchmark.anlage.region,
      regionName: REGION_NAMEN[benchmark.anlage.region] || benchmark.anlage.region,
    }
  }, [benchmark])

  // Ausstattungs-Vergleich (was hat deine Anlage vs. was ist möglich)
  const ausstattung = useMemo(() => {
    if (!benchmark) return []

    return [
      {
        name: 'Speicher',
        icon: <Battery className="h-5 w-5" />,
        vorhanden: !!benchmark.anlage.speicher_kwh,
        details: benchmark.anlage.speicher_kwh ? `${benchmark.anlage.speicher_kwh} kWh` : null,
        color: 'green',
      },
      {
        name: 'Wärmepumpe',
        icon: <Home className="h-5 w-5" />,
        vorhanden: benchmark.anlage.hat_waermepumpe,
        details: null,
        color: 'blue',
      },
      {
        name: 'E-Auto',
        icon: <Car className="h-5 w-5" />,
        vorhanden: benchmark.anlage.hat_eauto,
        details: null,
        color: 'purple',
      },
      {
        name: 'Wallbox',
        icon: <Plug className="h-5 w-5" />,
        vorhanden: benchmark.anlage.hat_wallbox,
        details: benchmark.anlage.wallbox_kw ? `${benchmark.anlage.wallbox_kw} kW` : null,
        color: 'cyan',
      },
      {
        name: 'Balkonkraftwerk',
        icon: <Sun className="h-5 w-5" />,
        vorhanden: benchmark.anlage.hat_balkonkraftwerk,
        details: benchmark.anlage.bkw_wp ? `${benchmark.anlage.bkw_wp} Wp` : null,
        color: 'amber',
      },
    ]
  }, [benchmark])

  // Positionsberechnung
  const position = useMemo(() => {
    if (!benchmark) return null

    const { rang_gesamt, anzahl_anlagen_gesamt, rang_region, anzahl_anlagen_region } = benchmark.benchmark
    const perzentilGesamt = Math.round((1 - rang_gesamt / anzahl_anlagen_gesamt) * 100)
    const perzentilRegion = Math.round((1 - rang_region / anzahl_anlagen_region) * 100)

    return {
      rangGesamt: rang_gesamt,
      vonGesamt: anzahl_anlagen_gesamt,
      perzentilGesamt,
      rangRegion: rang_region,
      vonRegion: anzahl_anlagen_region,
      perzentilRegion,
    }
  }, [benchmark])

  if (loading) {
    return <LoadingSpinner text="Lade Community-Statistiken..." />
  }

  if (error) {
    return <Alert type="error">{error}</Alert>
  }

  if (!benchmark || !communityStats) {
    return null
  }

  return (
    <div className="space-y-6">
      {/* Community-Zusammenfassung */}
      <Card>
        <div className="flex items-center gap-2 mb-6">
          <Users className="h-6 w-6 text-primary-500" />
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Community-Übersicht
          </h2>
          <span className="ml-auto text-sm text-gray-500">{benchmark.zeitraum_label}</span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard
            label="Anlagen gesamt"
            value={communityStats.anzahlAnlagen}
            icon={<Users className="h-5 w-5 text-primary-500" />}
          />
          <StatCard
            label="Ø Spez. Ertrag"
            value={communityStats.durchschnittErtrag}
            suffix="kWh/kWp"
            icon={<Sun className="h-5 w-5 text-yellow-500" />}
          />
          <StatCard
            label={`In ${communityStats.regionName}`}
            value={communityStats.anzahlRegion}
            suffix="Anlagen"
            icon={<MapPin className="h-5 w-5 text-blue-500" />}
          />
          <StatCard
            label="Ø Region"
            value={communityStats.regionErtrag}
            suffix="kWh/kWp"
            icon={<BarChart3 className="h-5 w-5 text-green-500" />}
          />
        </div>
      </Card>

      {/* Deine Position */}
      {position && (
        <Card>
          <div className="flex items-center gap-2 mb-6">
            <Award className="h-6 w-6 text-yellow-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Deine Position in der Community
            </h3>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Gesamt-Ranking */}
            <div className="bg-gradient-to-br from-primary-50 to-primary-100 dark:from-primary-900/20 dark:to-primary-800/20 rounded-xl p-6">
              <div className="flex items-center gap-2 mb-4">
                <Users className="h-5 w-5 text-primary-500" />
                <span className="text-primary-700 dark:text-primary-300 font-medium">
                  Community-weit
                </span>
              </div>
              <div className="flex items-baseline gap-2 mb-2">
                <span className="text-4xl font-bold text-primary-600 dark:text-primary-400">
                  #{position.rangGesamt}
                </span>
                <span className="text-primary-500 dark:text-primary-400">
                  von {position.vonGesamt}
                </span>
              </div>
              <ProgressBar value={position.perzentilGesamt} color="primary" />
              <p className="text-sm text-primary-600 dark:text-primary-400 mt-2">
                Besser als {position.perzentilGesamt}% der Community
              </p>
            </div>

            {/* Regional-Ranking */}
            <div className="bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-800/20 rounded-xl p-6">
              <div className="flex items-center gap-2 mb-4">
                <MapPin className="h-5 w-5 text-blue-500" />
                <span className="text-blue-700 dark:text-blue-300 font-medium">
                  In {communityStats.regionName}
                </span>
              </div>
              <div className="flex items-baseline gap-2 mb-2">
                <span className="text-4xl font-bold text-blue-600 dark:text-blue-400">
                  #{position.rangRegion}
                </span>
                <span className="text-blue-500 dark:text-blue-400">
                  von {position.vonRegion}
                </span>
              </div>
              <ProgressBar value={position.perzentilRegion} color="blue" />
              <p className="text-sm text-blue-600 dark:text-blue-400 mt-2">
                Besser als {position.perzentilRegion}% in deiner Region
              </p>
            </div>
          </div>
        </Card>
      )}

      {/* Deine Anlage im Detail */}
      <Card>
        <div className="flex items-center gap-2 mb-6">
          <Zap className="h-6 w-6 text-primary-500" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Deine Anlage
          </h3>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <DetailCard
            label="Leistung"
            value={`${benchmark.anlage.kwp} kWp`}
            icon={<Sun className="h-5 w-5 text-yellow-500" />}
          />
          <DetailCard
            label="Ausrichtung"
            value={benchmark.anlage.ausrichtung}
            icon={<TrendingUp className="h-5 w-5 text-blue-500" />}
            capitalize
          />
          <DetailCard
            label="Neigung"
            value={`${benchmark.anlage.neigung_grad}°`}
            icon={<BarChart3 className="h-5 w-5 text-green-500" />}
          />
          <DetailCard
            label="Installation"
            value={String(benchmark.anlage.installation_jahr)}
            icon={<Calendar className="h-5 w-5 text-gray-500" />}
          />
        </div>

        {/* Ausstattung */}
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
          Ausstattung
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {ausstattung.map((item) => (
            <div
              key={item.name}
              className={`flex items-center gap-2 p-3 rounded-lg ${
                item.vorhanden
                  ? `bg-${item.color}-50 dark:bg-${item.color}-900/20 border border-${item.color}-200 dark:border-${item.color}-800`
                  : 'bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700'
              }`}
            >
              <div className={item.vorhanden ? `text-${item.color}-500` : 'text-gray-400'}>
                {item.icon}
              </div>
              <div className="flex-1 min-w-0">
                <p className={`text-sm font-medium ${
                  item.vorhanden
                    ? 'text-gray-900 dark:text-white'
                    : 'text-gray-400 dark:text-gray-500'
                }`}>
                  {item.name}
                </p>
                {item.details && (
                  <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                    {item.details}
                  </p>
                )}
              </div>
              {item.vorhanden ? (
                <CheckCircle2 className={`h-4 w-4 text-${item.color}-500`} />
              ) : (
                <XCircle className="h-4 w-4 text-gray-300 dark:text-gray-600" />
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* Ausstattungsquoten aus globalStats */}
      {globalStats && (
        <Card>
          <div className="flex items-center gap-2 mb-6">
            <BarChart3 className="h-6 w-6 text-purple-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Ausstattungsquoten der Community
            </h3>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <QuoteCard label="Speicher" value={globalStats.ausstattungsquoten.speicher} color="green" />
            <QuoteCard label="Wärmepumpe" value={globalStats.ausstattungsquoten.waermepumpe} color="blue" />
            <QuoteCard label="E-Auto" value={globalStats.ausstattungsquoten.eauto} color="purple" />
            <QuoteCard label="Wallbox" value={globalStats.ausstattungsquoten.wallbox} color="cyan" />
            <QuoteCard label="Balkonkraftwerk" value={globalStats.ausstattungsquoten.balkonkraftwerk} color="amber" />
          </div>

          {/* Typische Anlage */}
          <div className="mt-6 p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              Die typische Community-Anlage
            </h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <span className="text-gray-500">Leistung:</span>
                <span className="ml-2 font-medium">{globalStats.typische_anlage.kwp} kWp</span>
              </div>
              <div>
                <span className="text-gray-500">Ausrichtung:</span>
                <span className="ml-2 font-medium capitalize">{globalStats.typische_anlage.ausrichtung}</span>
              </div>
              <div>
                <span className="text-gray-500">Neigung:</span>
                <span className="ml-2 font-medium">{globalStats.typische_anlage.neigung_grad}°</span>
              </div>
              {globalStats.typische_anlage.speicher_kwh && (
                <div>
                  <span className="text-gray-500">Speicher:</span>
                  <span className="ml-2 font-medium">{globalStats.typische_anlage.speicher_kwh} kWh</span>
                </div>
              )}
            </div>
          </div>
        </Card>
      )}

      {/* Top-10 Bestenliste */}
      {ranking && ranking.ranking.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-6">
            <Award className="h-6 w-6 text-yellow-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Top 10 - Spezifischer Ertrag
            </h3>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-gray-200 dark:border-gray-700">
                  <th className="text-left py-2 px-3 text-gray-500 font-medium">Rang</th>
                  <th className="text-left py-2 px-3 text-gray-500 font-medium">Region</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium">kWp</th>
                  <th className="text-right py-2 px-3 text-gray-500 font-medium">kWh/kWp</th>
                </tr>
              </thead>
              <tbody>
                {ranking.ranking.map((eintrag) => (
                  <tr key={eintrag.rang} className="border-b border-gray-100 dark:border-gray-800">
                    <td className="py-2 px-3">
                      <span className={`inline-flex items-center justify-center w-6 h-6 rounded-full text-xs font-bold ${
                        eintrag.rang === 1 ? 'bg-yellow-100 text-yellow-700' :
                        eintrag.rang === 2 ? 'bg-gray-200 text-gray-700' :
                        eintrag.rang === 3 ? 'bg-orange-100 text-orange-700' :
                        'bg-gray-100 text-gray-600'
                      }`}>
                        {eintrag.rang}
                      </span>
                    </td>
                    <td className="py-2 px-3 text-gray-900 dark:text-white">
                      {REGION_NAMEN[eintrag.region] || eintrag.region}
                    </td>
                    <td className="py-2 px-3 text-right text-gray-600 dark:text-gray-400">
                      {eintrag.kwp.toFixed(1)}
                    </td>
                    <td className="py-2 px-3 text-right font-medium text-gray-900 dark:text-white">
                      {eintrag.wert.toFixed(0)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {ranking.eigener_rang && (
            <div className="mt-4 p-3 bg-primary-50 dark:bg-primary-900/20 rounded-lg text-center">
              <span className="text-primary-700 dark:text-primary-300">
                Dein Rang: <strong>#{ranking.eigener_rang}</strong> mit <strong>{ranking.eigener_wert?.toFixed(0)} kWh/kWp</strong>
              </span>
            </div>
          )}
        </Card>
      )}
    </div>
  )
}

// Hilfskomponente für Ausstattungsquoten
function QuoteCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className={`p-4 rounded-lg bg-${color}-50 dark:bg-${color}-900/20`}>
      <p className="text-sm text-gray-600 dark:text-gray-400 mb-1">{label}</p>
      <p className={`text-2xl font-bold text-${color}-600 dark:text-${color}-400`}>
        {value.toFixed(1)}%
      </p>
    </div>
  )
}

// =============================================================================
// Hilfskomponenten
// =============================================================================

function StatCard({
  label,
  value,
  suffix,
  icon,
}: {
  label: string
  value: number
  suffix?: string
  icon: React.ReactNode
}) {
  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-2">
        {icon}
        <span className="text-sm text-gray-500 dark:text-gray-400">{label}</span>
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-2xl font-bold text-gray-900 dark:text-white">
          {typeof value === 'number' && value >= 1000
            ? value.toLocaleString('de-DE')
            : value.toFixed(value < 10 ? 1 : 0)}
        </span>
        {suffix && (
          <span className="text-sm text-gray-500 dark:text-gray-400">{suffix}</span>
        )}
      </div>
    </div>
  )
}

function DetailCard({
  label,
  value,
  icon,
  capitalize,
}: {
  label: string
  value: string
  icon: React.ReactNode
  capitalize?: boolean
}) {
  return (
    <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-1">
        {icon}
        <span className="text-xs text-gray-500 dark:text-gray-400">{label}</span>
      </div>
      <span className={`text-lg font-semibold text-gray-900 dark:text-white ${capitalize ? 'capitalize' : ''}`}>
        {value}
      </span>
    </div>
  )
}

function ProgressBar({ value, color }: { value: number; color: 'primary' | 'blue' }) {
  const colorClasses = {
    primary: 'bg-primary-500',
    blue: 'bg-blue-500',
  }

  return (
    <div className="w-full bg-white/50 dark:bg-gray-700/50 rounded-full h-2">
      <div
        className={`h-2 rounded-full ${colorClasses[color]} transition-all duration-500`}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  )
}
