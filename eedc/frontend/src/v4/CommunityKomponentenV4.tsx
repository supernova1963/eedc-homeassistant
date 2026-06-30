/**
 * CommunityKomponentenV4 — Komponenten-Sub-Tab der Community-Sicht als IA-V4-Blöcke.
 * Nutzt die geteilten Teile aus {@link CommunityKomponentenTeile} (eine Code-Wahrheit
 * mit dem IST-`KomponentenTab`), hier in die `BlockShell` gehängt. Je verfügbarer
 * Komponente ein Block in INVESTITION_TYP_ORDER:
 * Speicher → BKW → WP → Wallbox → E-Auto.
 */
import { Battery, Sun, Home, Plug, Car } from 'lucide-react'
import { BlockShell, type Block } from '../components/blocks'
import { LoadingSpinner, Alert, Card } from '../components/ui'
import { ParkProvider, ParkFuss, usePark } from '../components/park'
import type { CommunityBenchmarkResponse } from '../api/community'
import {
  useKomponentenDaten,
  SpeicherDeepDive,
  BKWDeepDive,
  WaermepumpeDeepDive,
  WallboxDeepDive,
  EAutoDeepDive,
  RangBadge,
  speicherUntertitel,
  bkwUntertitel,
  wallboxUntertitel,
  speicherParkIds,
  bkwParkIds,
  waermepumpeParkIds,
  wallboxParkIds,
  eautoParkIds,
} from '../pages/community/CommunityKomponentenTeile'

type Props = {
  benchmark: CommunityBenchmarkResponse | null
  loading: boolean
  error: string | null
}

export default function CommunityKomponentenV4(props: Props) {
  return (
    <ParkProvider persistKey="v4-community-komponenten">
      <CommunityKomponentenInner {...props} />
    </ParkProvider>
  )
}

function CommunityKomponentenInner({ benchmark, loading, error }: Props) {
  const park = usePark()
  const d = useKomponentenDaten(benchmark)

  if (loading || d.extraLoading) return <div className="p-3 sm:p-6"><LoadingSpinner text="Lade Komponenten-Daten…" /></div>
  if (error) return <div className="p-3 sm:p-6"><Alert type="error">{error}</Alert></div>
  if (!benchmark) return <div className="p-3 sm:p-6"><Card><p className="text-sm text-gray-500 dark:text-gray-400">Keine Community-Daten für diese Anlage.</p></Card></div>

  const speicher = benchmark.benchmark_erweitert?.speicher
  const bkw = benchmark.benchmark_erweitert?.balkonkraftwerk
  const wp = benchmark.benchmark_erweitert?.waermepumpe
  const wallbox = benchmark.benchmark_erweitert?.wallbox
  const eauto = benchmark.benchmark_erweitert?.eauto

  let ersterOffen = true
  const naechsterDefaultOpen = () => {
    if (ersterOffen) { ersterOffen = false; return true }
    return false
  }

  // Element-Park-Doktrin: jede Anzeige ist einzeln parkbar (in den Teile-Sektionen
  // via <Parkbar> gewrappt; KPI-Karten INNEN nach dem null-Guard). Ein Komponenten-
  // Block entfällt erst, wenn ALLE seine Element-IDs geparkt sind — die IDs liefern
  // die datenabhängigen `*ParkIds`-Funktionen (gleiche Render-Bedingungen).
  const alleGeparkt = (ids: readonly string[]) => ids.length > 0 && ids.every((id) => park.istGeparkt(id))

  const bloecke: (Block | null)[] = [
    d.verfuegbareKomponenten.includes('speicher') && speicher && !alleGeparkt(speicherParkIds(benchmark, d.speicherByClass)) ? {
      id: 'speicher', title: 'Speicher', icon: Battery, farbe: 'text-green-500',
      summary: speicherUntertitel(benchmark),
      badge: speicher.zyklen_jahr?.rang && speicher.zyklen_jahr.von
        ? <RangBadge rang={speicher.zyklen_jahr.rang} von={speicher.zyklen_jahr.von} /> : undefined,
      defaultOpen: naechsterDefaultOpen(),
      render: () => <SpeicherDeepDive benchmark={benchmark} communityStats={d.speicherByClass} />,
    } : null,
    d.verfuegbareKomponenten.includes('bkw') && bkw && !alleGeparkt(bkwParkIds(benchmark)) ? {
      id: 'bkw', title: 'Balkonkraftwerk', icon: Sun, farbe: 'text-amber-500',
      summary: bkwUntertitel(benchmark),
      badge: bkw.spez_ertrag?.rang && bkw.spez_ertrag.von
        ? <RangBadge rang={bkw.spez_ertrag.rang} von={bkw.spez_ertrag.von} /> : undefined,
      defaultOpen: naechsterDefaultOpen(),
      render: () => <BKWDeepDive benchmark={benchmark} />,
    } : null,
    d.verfuegbareKomponenten.includes('waermepumpe') && wp && !alleGeparkt(waermepumpeParkIds(benchmark, d.wpByRegion)) ? {
      id: 'waermepumpe', title: 'Wärmepumpe', icon: Home, farbe: 'text-blue-500',
      summary: 'Effizienz-Analyse',
      badge: wp.jaz?.rang && wp.jaz.von
        ? <RangBadge rang={wp.jaz.rang} von={wp.jaz.von} /> : undefined,
      defaultOpen: naechsterDefaultOpen(),
      render: () => <WaermepumpeDeepDive benchmark={benchmark} communityStats={d.wpByRegion} />,
    } : null,
    d.verfuegbareKomponenten.includes('wallbox') && wallbox && !alleGeparkt(wallboxParkIds(benchmark)) ? {
      id: 'wallbox', title: 'Wallbox', icon: Plug, farbe: 'text-cyan-500',
      summary: wallboxUntertitel(benchmark),
      badge: wallbox.pv_anteil?.rang && wallbox.pv_anteil.von
        ? <RangBadge rang={wallbox.pv_anteil.rang} von={wallbox.pv_anteil.von} /> : undefined,
      defaultOpen: naechsterDefaultOpen(),
      render: () => <WallboxDeepDive benchmark={benchmark} />,
    } : null,
    d.verfuegbareKomponenten.includes('eauto') && eauto && !alleGeparkt(eautoParkIds(benchmark, d.eautoByUsage)) ? {
      id: 'eauto', title: 'E-Auto', icon: Car, farbe: 'text-purple-500',
      summary: 'Lade- und Verbrauchsanalyse',
      badge: eauto.pv_anteil?.rang && eauto.pv_anteil.von
        ? <RangBadge rang={eauto.pv_anteil.rang} von={eauto.pv_anteil.von} /> : undefined,
      defaultOpen: naechsterDefaultOpen(),
      render: () => <EAutoDeepDive benchmark={benchmark} communityStats={d.eautoByUsage} />,
    } : null,
  ]

  const sichtbar = bloecke.filter(Boolean) as Block[]

  // Empty-State an der ECHTEN Datenlage festmachen (verfügbare Komponenten),
  // nicht an `sichtbar` — sonst kippt eine voll-geparkte Sicht in den Leer-Zustand
  // und der ParkFuß zum Zurückholen wäre weg.
  if (d.verfuegbareKomponenten.length === 0) {
    return (
      <div className="p-3 sm:p-6">
        <Card>
          <div className="text-center py-12">
            <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-gray-100 dark:bg-gray-800 mb-4">
              <Battery className="h-8 w-8 text-gray-400 dark:text-gray-500" />
            </div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-3">
              Keine Komponenten-Daten
            </h2>
            <p className="text-gray-600 dark:text-gray-400 max-w-md mx-auto">
              Für Komponenten-Vergleiche benötigst du mindestens eine Zusatzkomponente
              (Speicher, Wärmepumpe, Wallbox, E-Auto oder Balkonkraftwerk) mit erfassten Monatsdaten.
            </p>
          </div>
        </Card>
      </div>
    )
  }

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
      <BlockShell persistKey="v4-community-komponenten" bloecke={sichtbar} sortierbar />
      {/* Element-Park-Fuß (SLICE 1): Hinweiszeile + „Geparkt (n)". Inert leer,
          bis etwas geparkt ist; rendert nichts ohne ParkProvider. */}
      <ParkFuss />
    </div>
  )
}
