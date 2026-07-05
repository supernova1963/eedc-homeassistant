/**
 * CommunityRegionalV4 — Regional-Sub-Tab der Community-Sicht als IA-V4-Blöcke.
 * Nutzt die geteilten Teile aus {@link CommunityRegionalTeile} (eine Code-Wahrheit
 * mit dem IST-`RegionalTab`), hier in die `BlockShell` gehängt.
 */
import { MapPin, Sun, Users } from 'lucide-react'
import { BlockShell, BlockStackSkeleton, type Block } from '../components/blocks'
import { Alert, Card } from '../components/ui'
import { ParkProvider, ParkFuss, usePark } from '../components/park'
import { fmtZahl } from '../lib'
import type { CommunityBenchmarkResponse } from '../api/community'
import {
  useRegionalDaten, RegionalKpiStrip, VergleichsChart, RegionaleEinordnung,
  ChoroplethBlock, RegionenTabelle, REG_PARK_IDS,
} from '../pages/community/CommunityRegionalTeile'

type Props = {
  benchmark: CommunityBenchmarkResponse | null
  loading: boolean
  error: string | null
}

export default function CommunityRegionalV4(props: Props) {
  return (
    <ParkProvider persistKey="v4-community-regional">
      <CommunityRegionalInner {...props} />
    </ParkProvider>
  )
}

function CommunityRegionalInner({ benchmark, loading, error }: Props) {
  const park = usePark()
  const d = useRegionalDaten(benchmark)

  if (loading || d.extraLoading) return <div className="p-3 sm:p-6"><BlockStackSkeleton label="Lade regionale Daten…" /></div>
  if (error) return <div className="p-3 sm:p-6"><Alert type="error">{error}</Alert></div>
  if (!benchmark || !d.regionalStats) return <div className="p-3 sm:p-6"><Card><p className="text-sm text-gray-500 dark:text-gray-400">Keine Community-Daten für diese Anlage.</p></Card></div>

  const rs = d.regionalStats

  // Element-Park-Doktrin: jede Anzeige ist einzeln parkbar (in den Teile-Sektionen
  // via <Parkbar> gewrappt); ein Block entfällt erst, wenn ALLE seine Element-IDs
  // geparkt sind.
  const alleGeparkt = (ids: readonly string[]) => ids.length > 0 && ids.every((id) => park.istGeparkt(id))

  const bloecke: (Block | null)[] = [
    !alleGeparkt(REG_PARK_IDS.position) ? {
      id: 'position', title: 'Regionale Position', icon: MapPin, farbe: 'text-blue-500',
      summary: rs.regionName, defaultOpen: true,
      render: () => <RegionalKpiStrip regionalStats={rs} />,
    } : null,
    !alleGeparkt(REG_PARK_IDS.vergleich) ? {
      id: 'vergleich', title: 'Spezifischer Ertrag im Vergleich', icon: Sun, farbe: 'text-yellow-500',
      summary: benchmark.zeitraum_label, defaultOpen: true,
      render: () => <VergleichsChart vergleichsData={d.vergleichsData} />,
    } : null,
    !alleGeparkt(REG_PARK_IDS.einordnung) ? {
      id: 'einordnung', title: 'Regionale Einordnung', icon: Users,
      summary: `${rs.abweichungCommunity >= 0 ? '+' : ''}${fmtZahl(rs.abweichungCommunity, 1)} % vs. Community`, defaultOpen: false,
      render: () => <RegionaleEinordnung benchmark={benchmark} regionalStats={rs} />,
    } : null,
    d.allRegions.length > 0 && !alleGeparkt(REG_PARK_IDS.karte) ? {
      id: 'karte', title: 'Spezifischer Ertrag nach Bundesland', icon: MapPin, farbe: 'text-blue-500',
      summary: `${fmtZahl(d.allRegions.length, 0)} Regionen`, defaultOpen: false,
      render: () => <ChoroplethBlock allRegions={d.allRegions} benchmark={benchmark} />,
    } : null,
    d.allRegions.length > 0 && !alleGeparkt(REG_PARK_IDS.tabelle) ? {
      id: 'tabelle', title: 'Alle Regionen im Vergleich', icon: MapPin, farbe: 'text-green-500',
      summary: `${fmtZahl(d.allRegions.length, 0)} Regionen im Ranking`, defaultOpen: false,
      render: () => <RegionenTabelle allRegions={d.allRegions} benchmark={benchmark} />,
    } : null,
  ]

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
      <BlockShell persistKey="v4-community-regional" bloecke={bloecke.filter(Boolean) as Block[]} sortierbar />
      {/* Element-Park-Fuß (SLICE 1): Hinweiszeile + „Geparkt (n)". Inert leer,
          bis etwas geparkt ist; rendert nichts ohne ParkProvider. */}
      <ParkFuss />
    </div>
  )
}
