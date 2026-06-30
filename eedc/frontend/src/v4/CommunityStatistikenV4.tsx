/**
 * CommunityStatistikenV4 — Statistiken-Sub-Tab der Community-Sicht als IA-V4-Blöcke.
 * Nutzt die geteilten Teile aus {@link CommunityStatistikenTeile} (eine Code-Wahrheit
 * mit dem IST-`StatistikenTab`), hier in die `BlockShell` gehängt.
 */
import { Users, Award, Zap, BarChart3 } from 'lucide-react'
import { BlockShell, type Block } from '../components/blocks'
import { LoadingSpinner, Alert, Card } from '../components/ui'
import { ParkProvider, ParkFuss, usePark } from '../components/park'
import type { CommunityBenchmarkResponse } from '../api/community'
import {
  useStatistikenDaten,
  CommunityUebersicht,
  DeinePosition,
  DeineAnlage,
  Ausstattungsquoten,
  Top10Bestenliste,
  STAT_PARK_IDS,
} from '../pages/community/CommunityStatistikenTeile'

type Props = {
  benchmark: CommunityBenchmarkResponse | null
  loading: boolean
  error: string | null
}

export default function CommunityStatistikenV4(props: Props) {
  return (
    <ParkProvider persistKey="v4-community-statistiken">
      <CommunityStatistikenInner {...props} />
    </ParkProvider>
  )
}

function CommunityStatistikenInner({ benchmark, loading, error }: Props) {
  const park = usePark()
  const d = useStatistikenDaten(benchmark)

  if (loading || d.extraLoading) return <div className="p-3 sm:p-6"><LoadingSpinner text="Lade Community-Statistiken…" /></div>
  if (error) return <div className="p-3 sm:p-6"><Alert type="error">{error}</Alert></div>
  if (!benchmark || !d.communityStats) return <div className="p-3 sm:p-6"><Card><p className="text-sm text-gray-500 dark:text-gray-400">Keine Community-Daten für diese Anlage.</p></Card></div>

  const communityStats = d.communityStats

  // Element-Park-Doktrin: jede Anzeige ist einzeln parkbar (in den Teile-Sektionen
  // via <Parkbar> gewrappt); ein Block entfällt erst, wenn ALLE seine Element-IDs
  // geparkt sind.
  const alleGeparkt = (ids: readonly string[]) => ids.length > 0 && ids.every((id) => park.istGeparkt(id))

  const bloecke: (Block | null)[] = [
    !alleGeparkt(STAT_PARK_IDS.uebersicht) ? {
      id: 'uebersicht', title: 'Community-Übersicht', icon: Users,
      summary: benchmark.zeitraum_label, defaultOpen: true,
      render: () => <CommunityUebersicht communityStats={communityStats} />,
    } : null,
    d.position && !alleGeparkt(STAT_PARK_IDS.position) ? {
      id: 'position', title: 'Deine Position in der Community', icon: Award, farbe: 'text-yellow-500',
      defaultOpen: true,
      render: () => <DeinePosition position={d.position!} communityStats={communityStats} />,
    } : null,
    !alleGeparkt(STAT_PARK_IDS.anlage) ? {
      id: 'anlage', title: 'Deine Anlage', icon: Zap,
      defaultOpen: false,
      render: () => <DeineAnlage benchmark={benchmark} ausstattung={d.ausstattung} />,
    } : null,
    d.globalStats && !alleGeparkt(STAT_PARK_IDS.quoten) ? {
      id: 'quoten', title: 'Ausstattungsquoten der Community', icon: BarChart3, farbe: 'text-purple-500',
      defaultOpen: false,
      render: () => <Ausstattungsquoten globalStats={d.globalStats!} />,
    } : null,
    d.ranking && d.ranking.ranking.length > 0 && !alleGeparkt(STAT_PARK_IDS.top10) ? {
      id: 'top10', title: 'Top 10 – Spezifischer Ertrag', icon: Award, farbe: 'text-yellow-500',
      defaultOpen: false,
      render: () => <Top10Bestenliste ranking={d.ranking!} />,
    } : null,
  ]

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
      <BlockShell persistKey="v4-community-statistiken" bloecke={bloecke.filter(Boolean) as Block[]} sortierbar />
      {/* Element-Park-Fuß (SLICE 1): Hinweiszeile + „Geparkt (n)". Inert leer,
          bis etwas geparkt ist; rendert nichts ohne ParkProvider. */}
      <ParkFuss />
    </div>
  )
}
