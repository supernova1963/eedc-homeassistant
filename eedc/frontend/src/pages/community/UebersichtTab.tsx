/**
 * Community Übersicht Tab (IST) — komponiert die geteilten Teile aus
 * {@link CommunityUebersichtTeile} in der IST-Card-Optik. EINE Code-Wahrheit mit
 * der IA-V4-Sicht (`CommunityUebersichtV4`), die dieselben Teile als Blöcke rendert.
 */
import { Trophy, Sparkles } from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import type { CommunityBenchmarkResponse, ZeitraumTyp } from '../../api/community'
import {
  useUebersichtDaten, RankingHauptKpi, StaerkenSchwaechen, PerformanceProfil,
  AchievementsBlock, KomponentenBenchmarks,
} from './CommunityUebersichtTeile'

interface UebersichtTabProps {
  anlageId: number
  zeitraum: ZeitraumTyp
  benchmark: CommunityBenchmarkResponse | null
  benchmarkLoading: boolean
  benchmarkError: string | null
}

export default function UebersichtTab({ benchmark, benchmarkLoading: loading, benchmarkError: error }: UebersichtTabProps) {
  const d = useUebersichtDaten(benchmark)

  if (loading) return <LoadingSpinner text="Lade Community-Daten..." />
  if (error) return <Alert type="error">{error}</Alert>
  if (!benchmark) return null

  return (
    <div className="space-y-6">
      <Card>
        <div className="flex items-center gap-2 mb-6">
          <Trophy className="h-6 w-6 text-yellow-500" />
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Dein PV-Ertrag im Vergleich</h2>
        </div>
        <RankingHauptKpi benchmark={benchmark} rankingBadge={d.rankingBadge} />
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {(d.staerken.length > 0 || d.schwaechen.length > 0) && (
          <Card>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Deine Performance</h3>
            <StaerkenSchwaechen staerken={d.staerken} schwaechen={d.schwaechen} />
          </Card>
        )}
        {d.radarData.length >= 3 && (
          <Card>
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Performance-Profil</h3>
            <PerformanceProfil radarData={d.radarData} />
          </Card>
        )}
      </div>

      {(d.achievements.erreichte.length > 0 || d.achievements.nichtErreichte.length > 0) && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <Sparkles className="h-5 w-5 text-yellow-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Achievements</h3>
          </div>
          <AchievementsBlock achievements={d.achievements} />
        </Card>
      )}

      {benchmark.benchmark_erweitert && <KomponentenBenchmarks benchmark={benchmark} />}
    </div>
  )
}
