/**
 * Community Statistiken Tab (IST) — komponiert die geteilten Teile aus
 * {@link CommunityStatistikenTeile} in der IST-Card-Optik. EINE Code-Wahrheit
 * mit der IA-V4-Sicht (`CommunityStatistikenV4`).
 *
 * Community-weite Insights basierend auf verfügbaren Benchmark-Daten:
 * - Community-Übersicht
 * - Deine Position in der Community
 * - Deine Anlage + Ausstattung
 * - Ausstattungsquoten der Community
 * - Top-10 Bestenliste
 */
import { Users, Award, Zap, BarChart3 } from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import type { CommunityBenchmarkResponse, ZeitraumTyp } from '../../api/community'
import {
  useStatistikenDaten,
  CommunityUebersicht,
  DeinePosition,
  DeineAnlage,
  Ausstattungsquoten,
  Top10Bestenliste,
} from './CommunityStatistikenTeile'

interface StatistikenTabProps {
  anlageId: number
  zeitraum: ZeitraumTyp
  benchmark: CommunityBenchmarkResponse | null
  benchmarkLoading: boolean
  benchmarkError: string | null
}

export default function StatistikenTab({ benchmark, benchmarkLoading, benchmarkError }: StatistikenTabProps) {
  const d = useStatistikenDaten(benchmark)

  if (benchmarkLoading || d.extraLoading) return <LoadingSpinner text="Lade Community-Statistiken..." />
  if (benchmarkError) return <Alert type="error">{benchmarkError}</Alert>
  if (!benchmark || !d.communityStats) return null

  return (
    <div className="space-y-6">
      {/* Community-Übersicht */}
      <Card>
        <div className="flex items-center gap-2 mb-6">
          <Users className="h-6 w-6 text-primary-500" />
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
            Community-Übersicht
          </h2>
          <span className="ml-auto text-sm text-gray-500">{benchmark.zeitraum_label}</span>
        </div>
        <CommunityUebersicht communityStats={d.communityStats} />
      </Card>

      {/* Deine Position */}
      {d.position && (
        <Card>
          <div className="flex items-center gap-2 mb-6">
            <Award className="h-6 w-6 text-yellow-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Deine Position in der Community
            </h3>
          </div>
          <DeinePosition position={d.position} communityStats={d.communityStats} />
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
        <DeineAnlage benchmark={benchmark} ausstattung={d.ausstattung} />
      </Card>

      {/* Ausstattungsquoten aus globalStats */}
      {d.globalStats && (
        <Card>
          <div className="flex items-center gap-2 mb-6">
            <BarChart3 className="h-6 w-6 text-purple-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Ausstattungsquoten der Community
            </h3>
          </div>
          <Ausstattungsquoten globalStats={d.globalStats} />
        </Card>
      )}

      {/* Top-10 Bestenliste */}
      {d.ranking && d.ranking.ranking.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-6">
            <Award className="h-6 w-6 text-yellow-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Top 10 - Spezifischer Ertrag
            </h3>
          </div>
          <Top10Bestenliste ranking={d.ranking} />
        </Card>
      )}
    </div>
  )
}
