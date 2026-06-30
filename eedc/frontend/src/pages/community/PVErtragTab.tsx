/**
 * Community PV-Ertrag Tab (IST) — komponiert die geteilten Teile aus
 * {@link CommunityPVErtragTeile} in der IST-Card-Optik. EINE Code-Wahrheit mit
 * der IA-V4-Sicht (`CommunityPVErtragV4`).
 */
import { Sun, Calendar, Target } from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import type { CommunityBenchmarkResponse, ZeitraumTyp } from '../../api/community'
import {
  usePVErtragDaten, PvKpiStrip, MonatsErtragChart, JahresUebersicht,
  VerteilungHistogramm, VergleichHinweis,
} from './CommunityPVErtragTeile'

interface PVErtragTabProps {
  anlageId: number
  zeitraum: ZeitraumTyp
  benchmark: CommunityBenchmarkResponse | null
  benchmarkLoading: boolean
  benchmarkError: string | null
}

export default function PVErtragTab({ benchmark, benchmarkLoading, benchmarkError }: PVErtragTabProps) {
  const d = usePVErtragDaten(benchmark)

  if (benchmarkLoading || d.extraLoading) return <LoadingSpinner text="Lade PV-Ertragsdaten..." />
  if (benchmarkError) return <Alert type="error">{benchmarkError}</Alert>
  if (!benchmark) return null

  return (
    <div className="space-y-6">
      <PvKpiStrip perzentil={d.perzentil} performanceStats={d.performanceStats} />

      {d.chartData.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4"><Sun className="h-5 w-5 text-primary-500" /><h3 className="text-lg font-semibold text-gray-900 dark:text-white">Monatlicher Ertrag vs. Community</h3></div>
          <MonatsErtragChart benchmark={benchmark} chartData={d.chartData} />
        </Card>
      )}

      {d.jahresStats && d.jahresStats.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4"><Calendar className="h-5 w-5 text-primary-500" /><h3 className="text-lg font-semibold text-gray-900 dark:text-white">Jahresübersicht</h3></div>
          <JahresUebersicht benchmark={benchmark} jahresStats={d.jahresStats} />
        </Card>
      )}

      {d.distribution && d.distribution.bins.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4"><Target className="h-5 w-5 text-purple-500" /><h3 className="text-lg font-semibold text-gray-900 dark:text-white">Verteilung in der Community</h3></div>
          <VerteilungHistogramm benchmark={benchmark} distribution={d.distribution} />
        </Card>
      )}

      <Card className="bg-gray-50 dark:bg-gray-800/50">
        <h4 className="font-medium text-gray-900 dark:text-white mb-1">Über den Vergleich</h4>
        <VergleichHinweis benchmark={benchmark} performanceStats={d.performanceStats} />
      </Card>
    </div>
  )
}
