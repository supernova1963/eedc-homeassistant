/**
 * CommunityTrendsV4 — Trends-Sub-Tab der Community-Sicht als IA-V4-Blöcke.
 * Nutzt die geteilten Teile aus {@link CommunityTrendsTeile} (eine Code-Wahrheit
 * mit dem IST-`TrendsTab`), hier in die `BlockShell` gehängt.
 */
import { TrendingUp, Calendar, BarChart3, Sun } from 'lucide-react'
import { BlockShell, type Block } from '../components/blocks'
import { LoadingSpinner, Alert, Card } from '../components/ui'
import { ParkProvider, ParkFuss, usePark } from '../components/park'
import type { CommunityBenchmarkResponse } from '../api/community'
import {
  useTrendsDaten, ErtragsverlaufChart, SaisonalePerformance, JahresvergleichBlock,
  TypischerMonatsverlauf, CommunityEntwicklung, DegradationBlock, TR_PARK_IDS,
} from '../pages/community/CommunityTrendsTeile'

type Props = {
  benchmark: CommunityBenchmarkResponse | null
  loading: boolean
  error: string | null
}

export default function CommunityTrendsV4(props: Props) {
  return (
    <ParkProvider persistKey="v4-community-trends">
      <CommunityTrendsInner {...props} />
    </ParkProvider>
  )
}

function CommunityTrendsInner({ benchmark, loading, error }: Props) {
  const park = usePark()
  const d = useTrendsDaten(benchmark)

  if (loading || d.extraLoading) return <div className="p-3 sm:p-6"><LoadingSpinner text="Lade Trend-Daten…" /></div>
  if (error) return <div className="p-3 sm:p-6"><Alert type="error">{error}</Alert></div>
  if (!benchmark) return <div className="p-3 sm:p-6"><Card><p className="text-sm text-gray-500 dark:text-gray-400">Keine Community-Daten für diese Anlage.</p></Card></div>

  // Element-Park-Doktrin: jede Anzeige ist einzeln parkbar (in den Teile-Sektionen
  // via <Parkbar> gewrappt); ein Block entfällt erst, wenn ALLE seine Element-IDs
  // geparkt sind.
  const alleGeparkt = (ids: readonly string[]) => ids.length > 0 && ids.every((id) => park.istGeparkt(id))

  const bloecke: (Block | null)[] = [
    d.ertragsverlauf.length > 0 && !alleGeparkt(TR_PARK_IDS.verlauf) ? {
      id: 'verlauf', title: 'Ertragsverlauf', icon: TrendingUp,
      summary: benchmark.zeitraum_label, defaultOpen: true,
      render: () => <ErtragsverlaufChart benchmark={benchmark} ertragsverlauf={d.ertragsverlauf} />,
    } : null,
    d.saisonaleAnalyse && !alleGeparkt(TR_PARK_IDS.saisonal) ? {
      id: 'saisonal', title: 'Saisonale Performance', icon: Calendar, defaultOpen: true,
      render: () => <SaisonalePerformance saisonaleAnalyse={d.saisonaleAnalyse!} />,
    } : null,
    d.jahresvergleich && !alleGeparkt(TR_PARK_IDS.jahresvergleich) ? {
      id: 'jahresvergleich', title: 'Jahresvergleich', icon: BarChart3, defaultOpen: false,
      render: () => <JahresvergleichBlock jahresvergleich={d.jahresvergleich!} />,
    } : null,
    d.monatlicherDurchschnitt.some(m => m.anzahl > 1) && !alleGeparkt(TR_PARK_IDS.monatsverlauf) ? {
      id: 'monatsverlauf', title: 'Typischer Monatsverlauf', icon: Sun, defaultOpen: false,
      render: () => <TypischerMonatsverlauf monatlicherDurchschnitt={d.monatlicherDurchschnitt} ertragsverlauf={d.ertragsverlauf} />,
    } : null,
    d.communityTrends && d.communityTrends.trends.speicher_quote.length > 0 && !alleGeparkt(TR_PARK_IDS.community) ? {
      id: 'community', title: 'Community-Entwicklung', icon: TrendingUp, farbe: 'text-green-500', defaultOpen: false,
      render: () => <CommunityEntwicklung communityTrends={d.communityTrends!} />,
    } : null,
    d.degradation && d.degradation.nach_alter.length > 0 && !alleGeparkt(TR_PARK_IDS.degradation) ? {
      id: 'degradation', title: 'Degradation nach Anlagenalter', icon: BarChart3, farbe: 'text-orange-500', defaultOpen: false,
      render: () => <DegradationBlock degradation={d.degradation!} />,
    } : null,
  ]

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
      <BlockShell persistKey="v4-community-trends" bloecke={bloecke.filter(Boolean) as Block[]} sortierbar />
      {/* Element-Park-Fuß (SLICE 1): Hinweiszeile + „Geparkt (n)". Inert leer,
          bis etwas geparkt ist; rendert nichts ohne ParkProvider. */}
      <ParkFuss />
    </div>
  )
}
