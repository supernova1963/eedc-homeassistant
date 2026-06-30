/**
 * Community Regional Tab (IST) — komponiert die geteilten Teile aus
 * {@link CommunityRegionalTeile} in der IST-Card-Optik. EINE Code-Wahrheit mit
 * der IA-V4-Sicht (`CommunityRegionalV4`).
 *
 * Geografische Vergleiche:
 * - Regionale Position und Ranking
 * - Bundesland-Karte (Choropleth nach spez. Ertrag)
 * - Bundesland-Vergleich (tabellarisch)
 * - Regionale Insights
 */
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import type { CommunityBenchmarkResponse, ZeitraumTyp } from '../../api/community'
import {
  useRegionalDaten, RegionalKpiStrip, VergleichsChart, RegionaleEinordnung,
  ChoroplethBlock, RegionenTabelle, MapPin, Sun, Users,
} from './CommunityRegionalTeile'

interface RegionalTabProps {
  anlageId: number
  zeitraum: ZeitraumTyp
  benchmark: CommunityBenchmarkResponse | null
  benchmarkLoading: boolean
  benchmarkError: string | null
}

export default function RegionalTab({ benchmark, benchmarkLoading, benchmarkError }: RegionalTabProps) {
  const d = useRegionalDaten(benchmark)

  if (benchmarkLoading || d.extraLoading) return <LoadingSpinner text="Lade regionale Daten..." />
  if (benchmarkError) return <Alert type="error">{benchmarkError}</Alert>
  if (!benchmark || !d.regionalStats) return null

  return (
    <div className="space-y-6">
      {/* Zeitraum-Hinweis */}
      <div className="flex items-center justify-end">
        <span className="text-sm text-gray-500 dark:text-gray-400">
          Betrachtungszeitraum: {benchmark.zeitraum_label}
        </span>
      </div>

      {/* Regionale Position */}
      <RegionalKpiStrip regionalStats={d.regionalStats} />

      {/* Vergleichs-Chart */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Sun className="h-5 w-5 text-primary-500" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Spezifischer Ertrag im Vergleich
          </h3>
        </div>
        <VergleichsChart vergleichsData={d.vergleichsData} />
      </Card>

      {/* Regionale Insights */}
      <Card>
        <div className="flex items-center gap-2 mb-4">
          <Users className="h-5 w-5 text-primary-500" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
            Regionale Einordnung
          </h3>
        </div>
        <RegionaleEinordnung benchmark={benchmark} regionalStats={d.regionalStats} />
      </Card>

      {/* Deutschland-Karte (Choropleth) */}
      {d.allRegions.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <MapPin className="h-5 w-5 text-blue-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Spezifischer Ertrag nach Bundesland
            </h3>
          </div>
          <ChoroplethBlock allRegions={d.allRegions} benchmark={benchmark} />
        </Card>
      )}

      {/* Bundesländer-Übersicht */}
      {d.allRegions.length > 0 && (
        <Card>
          <div className="flex items-center gap-2 mb-4">
            <MapPin className="h-5 w-5 text-green-500" />
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
              Alle Regionen im Vergleich
            </h3>
          </div>
          <RegionenTabelle allRegions={d.allRegions} benchmark={benchmark} />
        </Card>
      )}
    </div>
  )
}
