/**
 * CommunityPVErtragV4 — PV-Ertrag-Sub-Tab der Community-Sicht als IA-V4-Blöcke.
 * Nutzt die geteilten Teile aus {@link CommunityPVErtragTeile} (eine Code-Wahrheit
 * mit dem IST-`PVErtragTab`), hier in die `BlockShell` gehängt.
 */
import { Award, Sun, Calendar, Target } from 'lucide-react'
import { STATUS_ICONS } from '../lib'
import { BlockShell, type Block } from '../components/blocks'
import { LoadingSpinner, Alert, Card } from '../components/ui'
import { ParkProvider, ParkFuss, usePark } from '../components/park'
import { fmtZahl } from '../lib'
import type { CommunityBenchmarkResponse } from '../api/community'
import {
  usePVErtragDaten, PvKpiStrip, MonatsErtragChart, JahresUebersicht,
  VerteilungHistogramm, VergleichHinweis, PV_PARK_IDS,
} from '../pages/community/CommunityPVErtragTeile'

type Props = {
  benchmark: CommunityBenchmarkResponse | null
  loading: boolean
  error: string | null
}

export default function CommunityPVErtragV4(props: Props) {
  return (
    <ParkProvider persistKey="v4-community-pv-ertrag">
      <CommunityPVErtragInner {...props} />
    </ParkProvider>
  )
}

function CommunityPVErtragInner({ benchmark, loading, error }: Props) {
  const park = usePark()
  const d = usePVErtragDaten(benchmark)

  if (loading || d.extraLoading) return <div className="p-3 sm:p-6"><LoadingSpinner text="Lade PV-Ertragsdaten…" /></div>
  if (error) return <div className="p-3 sm:p-6"><Alert type="error">{error}</Alert></div>
  if (!benchmark) return <div className="p-3 sm:p-6"><Card><p className="text-sm text-gray-500 dark:text-gray-400">Keine Community-Daten für diese Anlage.</p></Card></div>

  // Element-Park-Doktrin: jede Anzeige ist einzeln parkbar (in den Teile-Sektionen
  // via <Parkbar> gewrappt); ein Block entfällt erst, wenn ALLE seine Element-IDs
  // geparkt sind.
  const alleGeparkt = (ids: readonly string[]) => ids.length > 0 && ids.every((id) => park.istGeparkt(id))

  const bloecke: (Block | null)[] = [
    !alleGeparkt(PV_PARK_IDS.kennzahlen) ? {
      id: 'kennzahlen', title: 'Kennzahlen', icon: Award, farbe: 'text-blue-500',
      summary: d.perzentil != null ? `Top ${fmtZahl(100 - d.perzentil, 0)} % · besser als ${fmtZahl(d.perzentil, 0)} %` : undefined,
      defaultOpen: true,
      render: () => <PvKpiStrip perzentil={d.perzentil} performanceStats={d.performanceStats} />,
    } : null,
    d.chartData.length > 0 && !alleGeparkt(PV_PARK_IDS.monatsertrag) ? {
      id: 'monatsertrag', title: 'Monatlicher Ertrag vs. Community', icon: Sun, farbe: 'text-yellow-500',
      summary: benchmark.zeitraum_label, defaultOpen: true,
      render: () => <MonatsErtragChart benchmark={benchmark} chartData={d.chartData} />,
    } : null,
    d.jahresStats && d.jahresStats.length > 0 && !alleGeparkt(PV_PARK_IDS.jahresuebersicht) ? {
      id: 'jahresuebersicht', title: 'Jahresübersicht', icon: Calendar,
      summary: `${fmtZahl(d.jahresStats.length, 0)} Jahre`, defaultOpen: false,
      render: () => <JahresUebersicht benchmark={benchmark} jahresStats={d.jahresStats!} />,
    } : null,
    d.distribution && d.distribution.bins.length > 0 && !alleGeparkt(PV_PARK_IDS.verteilung) ? {
      id: 'verteilung', title: 'Verteilung in der Community', icon: Target, farbe: 'text-purple-500',
      summary: 'Wo stehst du im Feld?', defaultOpen: false,
      render: () => <VerteilungHistogramm benchmark={benchmark} distribution={d.distribution!} />,
    } : null,
    !alleGeparkt(PV_PARK_IDS.hinweis) ? {
      id: 'hinweis', title: 'Über den Vergleich', icon: STATUS_ICONS.info, defaultOpen: false,
      render: () => <VergleichHinweis benchmark={benchmark} performanceStats={d.performanceStats} />,
    } : null,
  ]

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
      <BlockShell persistKey="v4-community-pv-ertrag" bloecke={bloecke.filter(Boolean) as Block[]} sortierbar />
      {/* Element-Park-Fuß (SLICE 1): Hinweiszeile + „Geparkt (n)". Inert leer,
          bis etwas geparkt ist; rendert nichts ohne ParkProvider. */}
      <ParkFuss />
    </div>
  )
}
