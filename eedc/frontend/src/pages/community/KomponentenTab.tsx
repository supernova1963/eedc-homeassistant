/**
 * Community Komponenten Tab (IST) — komponiert die geteilten Teile aus
 * {@link CommunityKomponentenTeile} in der IST-Card-Optik (Icon-Box + Titel +
 * Untertitel + RangBadge je Komponente). EINE Code-Wahrheit mit der IA-V4-Sicht
 * (`CommunityKomponentenV4`).
 *
 * Deep-Dives folgen INVESTITION_TYP_ORDER: Speicher → BKW → WP → Wallbox → E-Auto
 * (#215 detLAN: BKW gehört nach Speicher, nicht ans Ende; #211 detLAN: Wallbox
 * vor E-Auto).
 */
import { Battery } from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import type { CommunityBenchmarkResponse, ZeitraumTyp } from '../../api/community'
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
  Sun,
  Home,
  Plug,
  Car,
} from './CommunityKomponentenTeile'

interface KomponentenTabProps {
  anlageId: number
  zeitraum: ZeitraumTyp
  benchmark: CommunityBenchmarkResponse | null
  benchmarkLoading: boolean
  benchmarkError: string | null
}

export default function KomponentenTab({ zeitraum, benchmark, benchmarkLoading, benchmarkError }: KomponentenTabProps) {
  const d = useKomponentenDaten(benchmark)

  if (benchmarkLoading) {
    return <LoadingSpinner text="Lade Komponenten-Daten..." />
  }

  if (benchmarkError) {
    // Bei "letzter Monat" ohne Daten freundlichere Meldung
    if (zeitraum === 'letzter_monat') {
      return (
        <Card>
          <div className="text-center py-8">
            <Battery className="h-12 w-12 text-gray-300 mx-auto mb-3" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
              Keine Daten für letzten Monat
            </h3>
            <p className="text-gray-500 dark:text-gray-400">
              Für den letzten Monat liegen noch keine Komponenten-Daten vor.
              Wähle einen längeren Zeitraum für den Vergleich.
            </p>
          </div>
        </Card>
      )
    }
    return <Alert type="error">{benchmarkError}</Alert>
  }

  if (!benchmark) {
    return null
  }

  if (d.verfuegbareKomponenten.length === 0) {
    return (
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
    )
  }

  const speicher = benchmark.benchmark_erweitert?.speicher
  const bkw = benchmark.benchmark_erweitert?.balkonkraftwerk
  const wp = benchmark.benchmark_erweitert?.waermepumpe
  const wallbox = benchmark.benchmark_erweitert?.wallbox
  const eauto = benchmark.benchmark_erweitert?.eauto

  return (
    <div className="space-y-6">
      {/* Zeitraum-Hinweis */}
      <div className="flex items-center justify-end">
        <span className="text-sm text-gray-500 dark:text-gray-400">
          Betrachtungszeitraum: {benchmark.zeitraum_label}
        </span>
      </div>

      {/* Speicher Deep-Dive */}
      {d.verfuegbareKomponenten.includes('speicher') && speicher && (
        <Card>
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-green-100 dark:bg-green-900/30">
                <Battery className="h-6 w-6 text-green-500" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Speicher</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">{speicherUntertitel(benchmark)}</p>
              </div>
            </div>
            {speicher.zyklen_jahr?.rang && speicher.zyklen_jahr.von && (
              <RangBadge rang={speicher.zyklen_jahr.rang} von={speicher.zyklen_jahr.von} />
            )}
          </div>
          <SpeicherDeepDive benchmark={benchmark} communityStats={d.speicherByClass} />
        </Card>
      )}

      {/* Balkonkraftwerk Deep-Dive */}
      {d.verfuegbareKomponenten.includes('bkw') && bkw && (
        <Card>
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-amber-100 dark:bg-amber-900/30">
                <Sun className="h-6 w-6 text-amber-500" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Balkonkraftwerk</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">{bkwUntertitel(benchmark)}</p>
              </div>
            </div>
            {bkw.spez_ertrag?.rang && bkw.spez_ertrag.von && (
              <RangBadge rang={bkw.spez_ertrag.rang} von={bkw.spez_ertrag.von} />
            )}
          </div>
          <BKWDeepDive benchmark={benchmark} />
        </Card>
      )}

      {/* Wärmepumpe Deep-Dive */}
      {d.verfuegbareKomponenten.includes('waermepumpe') && wp && (
        <Card>
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-blue-100 dark:bg-blue-900/30">
                <Home className="h-6 w-6 text-blue-500" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Wärmepumpe</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">Effizienz-Analyse</p>
              </div>
            </div>
            {wp.jaz?.rang && wp.jaz.von && (
              <RangBadge rang={wp.jaz.rang} von={wp.jaz.von} />
            )}
          </div>
          <WaermepumpeDeepDive benchmark={benchmark} communityStats={d.wpByRegion} />
        </Card>
      )}

      {/* Wallbox Deep-Dive (vor E-Auto, #211 detLAN) */}
      {d.verfuegbareKomponenten.includes('wallbox') && wallbox && (
        <Card>
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-cyan-100 dark:bg-cyan-900/30">
                <Plug className="h-6 w-6 text-cyan-500" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Wallbox</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">{wallboxUntertitel(benchmark)}</p>
              </div>
            </div>
            {wallbox.pv_anteil?.rang && wallbox.pv_anteil.von && (
              <RangBadge rang={wallbox.pv_anteil.rang} von={wallbox.pv_anteil.von} />
            )}
          </div>
          <WallboxDeepDive benchmark={benchmark} />
        </Card>
      )}

      {/* E-Auto Deep-Dive */}
      {d.verfuegbareKomponenten.includes('eauto') && eauto && (
        <Card>
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-purple-100 dark:bg-purple-900/30">
                <Car className="h-6 w-6 text-purple-500" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">E-Auto</h3>
                <p className="text-sm text-gray-500 dark:text-gray-400">Lade- und Verbrauchsanalyse</p>
              </div>
            </div>
            {eauto.pv_anteil?.rang && eauto.pv_anteil.von && (
              <RangBadge rang={eauto.pv_anteil.rang} von={eauto.pv_anteil.von} />
            )}
          </div>
          <EAutoDeepDive benchmark={benchmark} communityStats={d.eautoByUsage} />
        </Card>
      )}
    </div>
  )
}
