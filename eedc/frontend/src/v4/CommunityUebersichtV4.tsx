/**
 * CommunityUebersichtV4 — Übersicht-Sub-Tab der Community-Sicht als IA-V4-Blöcke.
 *
 * Nutzt dieselben geteilten Teile wie der IST-`UebersichtTab`
 * ({@link CommunityUebersichtTeile}) — eine Code-Wahrheit, hier nur in die
 * `BlockShell` (einklappbar · Fokus/Vollbild · sortierbar) gehängt.
 */
import { Trophy, ThumbsUp, BarChart3, Sparkles, Battery } from 'lucide-react'
import { BlockShell, BlockStackSkeleton, type Block } from '../components/blocks'
import { Alert, Card } from '../components/ui'
import { ParkProvider, ParkFuss, usePark } from '../components/park'
import { fmtZahl, KOMPONENTEN_IDENTITAET } from '../lib'
import type { CommunityBenchmarkResponse } from '../api/community'
import {
  useUebersichtDaten, RankingHauptKpi, StaerkenSchwaechen, PerformanceProfil,
  AchievementsBlock, KomponentenBenchmarks,
  UEB_PARK_IDS, uebAchievementParkIds, uebKomponentenParkIds,
} from '../pages/community/CommunityUebersichtTeile'

type Props = {
  benchmark: CommunityBenchmarkResponse | null
  loading: boolean
  error: string | null
}

export default function CommunityUebersichtV4(props: Props) {
  return (
    <ParkProvider persistKey="v4-community-uebersicht">
      <CommunityUebersichtInner {...props} />
    </ParkProvider>
  )
}

function CommunityUebersichtInner({ benchmark, loading, error }: Props) {
  const park = usePark()
  const d = useUebersichtDaten(benchmark)

  if (loading) return <div className="p-3 sm:p-6"><BlockStackSkeleton label="Lade Community-Daten…" /></div>
  if (error) return <div className="p-3 sm:p-6"><Alert type="error">{error}</Alert></div>
  if (!benchmark) return <div className="p-3 sm:p-6"><Card><p className="text-sm text-gray-500 dark:text-gray-400">Keine Community-Daten für diese Anlage.</p></Card></div>

  const b = benchmark.benchmark

  // Element-Park-Doktrin: jede Anzeige ist einzeln parkbar (in den Teile-Sektionen
  // via <Parkbar> gewrappt); ein Block entfällt erst, wenn ALLE seine Element-IDs
  // geparkt sind. Datenabhängige Blöcke (Achievements, Komponenten) liefern ihre
  // IDs per Funktion (gleiche Slugs wie die gerenderten Elemente).
  const alleGeparkt = (ids: readonly string[]) => ids.length > 0 && ids.every((id) => park.istGeparkt(id))
  const achIds = uebAchievementParkIds(d.achievements)
  const kompIds = uebKomponentenParkIds(benchmark)

  const bloecke: (Block | null)[] = [
    !alleGeparkt(UEB_PARK_IDS.ranking) ? {
      id: 'ranking', title: 'Dein PV-Ertrag im Vergleich', icon: Trophy, farbe: 'text-yellow-500',
      summary: `${fmtZahl(b.spez_ertrag_anlage, 0)} kWh/kWp · Rang ${fmtZahl(b.rang_gesamt, 0)} von ${fmtZahl(b.anzahl_anlagen_gesamt, 0)}`,
      defaultOpen: true,
      render: () => <RankingHauptKpi benchmark={benchmark} rankingBadge={d.rankingBadge} />,
    } : null,
    (d.staerken.length > 0 || d.schwaechen.length > 0) && !alleGeparkt(UEB_PARK_IDS.performance) ? {
      id: 'performance', title: 'Deine Performance', icon: ThumbsUp, farbe: 'text-green-500',
      summary: `${fmtZahl(d.staerken.length, 0)} Stärken · ${fmtZahl(d.schwaechen.length, 0)} mit Potenzial`,
      defaultOpen: true,
      render: () => <StaerkenSchwaechen staerken={d.staerken} schwaechen={d.schwaechen} />,
    } : null,
    d.radarData.length >= 3 && !alleGeparkt(UEB_PARK_IDS.profil) ? {
      id: 'profil', title: 'Performance-Profil', icon: BarChart3,
      summary: 'Radar: Du vs. Community', defaultOpen: false,
      render: () => <PerformanceProfil radarData={d.radarData} />,
    } : null,
    (d.achievements.erreichte.length > 0 || d.achievements.nichtErreichte.length > 0) && !alleGeparkt(achIds) ? {
      id: 'achievements', title: 'Achievements', icon: Sparkles, farbe: 'text-yellow-500',
      summary: `${fmtZahl(d.achievements.erreichte.length, 0)} von ${fmtZahl(d.achievements.erreichte.length + d.achievements.nichtErreichte.length, 0)} erreicht`,
      defaultOpen: false,
      render: () => <AchievementsBlock achievements={d.achievements} />,
    } : null,
    benchmark.benchmark_erweitert && !alleGeparkt(kompIds) ? {
      // A2-4-Rest (R3b E3): Battery = Speicher-Identitäts-Icon → Identitätsfarbe des
      // Icons (Sammel-Block), nicht hartes Grün.
      id: 'komponenten', title: 'Komponenten-Benchmarks', icon: Battery, farbe: KOMPONENTEN_IDENTITAET['speicher'].farbe,
      summary: 'Speicher · BKW · WP · Wallbox · E-Auto vs. Community', defaultOpen: false,
      render: () => <KomponentenBenchmarks benchmark={benchmark} />,
    } : null,
  ]

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
      <BlockShell persistKey="v4-community-uebersicht" bloecke={bloecke.filter(Boolean) as Block[]} sortierbar />
      {/* Element-Park-Fuß (SLICE 1): Hinweiszeile + „Geparkt (n)". Inert leer,
          bis etwas geparkt ist; rendert nichts ohne ParkProvider. */}
      <ParkFuss />
    </div>
  )
}
