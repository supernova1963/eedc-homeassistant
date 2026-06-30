/**
 * Community Trends Tab (IST) — komponiert die geteilten Teile aus
 * {@link CommunityTrendsTeile} in der IST-Card-Optik. EINE Code-Wahrheit mit
 * der IA-V4-Sicht (`CommunityTrendsV4`).
 *
 * Zeitliche Entwicklungen basierend auf verfügbaren Monatswerten:
 * - Monatlicher Ertragsverlauf
 * - Saisonale Performance-Analyse
 * - Jahresvergleich
 * - Persönliche Entwicklung
 */
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import type { CommunityBenchmarkResponse, ZeitraumTyp } from '../../api/community'
import {
  useTrendsDaten, ErtragsverlaufChart, SaisonalePerformance, JahresvergleichBlock,
  TypischerMonatsverlauf, CommunityEntwicklung, DegradationBlock,
  TrendingUp, Calendar, Sun, BarChart3,
} from './CommunityTrendsTeile'

interface TrendsTabProps {
  anlageId: number
  zeitraum: ZeitraumTyp
  benchmark: CommunityBenchmarkResponse | null
  benchmarkLoading: boolean
  benchmarkError: string | null
}

export default function TrendsTab({ benchmark, benchmarkLoading, benchmarkError }: TrendsTabProps) {
  const d = useTrendsDaten(benchmark)

  if (benchmarkLoading || d.extraLoading) return <LoadingSpinner text="Lade Trend-Daten..." />
  if (benchmarkError) return <Alert type="error">{benchmarkError}</Alert>
  if (!benchmark) return null

  return (
    <div className="space-y-6">
      {/* Ertragsverlauf */}
      {d.ertragsverlauf.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4"><TrendingUp className="h-5 w-5 text-primary-500" /><h3 className="text-lg font-semibold text-gray-900 dark:text-white">Ertragsverlauf</h3></div>
          <ErtragsverlaufChart benchmark={benchmark} ertragsverlauf={d.ertragsverlauf} />
        </Card>
      )}

      {/* Saisonale Analyse */}
      {d.saisonaleAnalyse && (
        <Card>
          <div className="flex items-center gap-2 mb-4"><Calendar className="h-5 w-5 text-primary-500" /><h3 className="text-lg font-semibold text-gray-900 dark:text-white">Saisonale Performance</h3></div>
          <SaisonalePerformance saisonaleAnalyse={d.saisonaleAnalyse} />
        </Card>
      )}

      {/* Jahresvergleich */}
      {d.jahresvergleich && (
        <Card>
          <div className="flex items-center gap-2 mb-4"><BarChart3 className="h-5 w-5 text-primary-500" /><h3 className="text-lg font-semibold text-gray-900 dark:text-white">Jahresvergleich</h3></div>
          <JahresvergleichBlock jahresvergleich={d.jahresvergleich} />
        </Card>
      )}

      {/* Monatliche Durchschnitte */}
      {d.monatlicherDurchschnitt.some(m => m.anzahl > 1) && (
        <Card>
          <div className="flex items-center gap-2 mb-4"><Sun className="h-5 w-5 text-primary-500" /><h3 className="text-lg font-semibold text-gray-900 dark:text-white">Typischer Monatsverlauf</h3></div>
          <TypischerMonatsverlauf monatlicherDurchschnitt={d.monatlicherDurchschnitt} ertragsverlauf={d.ertragsverlauf} />
        </Card>
      )}

      {/* Community-Trends: Ausstattungsquoten */}
      {d.communityTrends && d.communityTrends.trends.speicher_quote.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4"><TrendingUp className="h-5 w-5 text-green-500" /><h3 className="text-lg font-semibold text-gray-900 dark:text-white">Community-Entwicklung</h3></div>
          <CommunityEntwicklung communityTrends={d.communityTrends} />
        </Card>
      )}

      {/* Degradations-Analyse */}
      {d.degradation && d.degradation.nach_alter.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4"><BarChart3 className="h-5 w-5 text-orange-500" /><h3 className="text-lg font-semibold text-gray-900 dark:text-white">Degradation nach Anlagenalter</h3></div>
          <DegradationBlock degradation={d.degradation} />
        </Card>
      )}
    </div>
  )
}
