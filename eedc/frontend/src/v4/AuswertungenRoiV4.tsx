/**
 * AuswertungenRoiV4 — ROI-/Wirtschaftlichkeits-Auswertung (A.5 Sub 5, Rebuild-lite D3).
 *
 * Vier verschiebbare BlockShell-Blöcke (SPEC-AUSWERTUNGEN §0a), jeder aus einzeln
 * parkbaren Elementen (R6) — wie Sub 2/3/4:
 *   ① Wirtschaftlichkeit auf einen Blick — 3 KPIs (Investition · Einsparung ·
 *      Amortisation; CO₂-KPI entfällt, R4)
 *   ② Amortisation — Break-Even-Kurve
 *   ③ Verteilung & Vergleich — Pie nach Typ + Bar je Investition
 *   ④ Detailübersicht je Investition — Tabelle (+ Speicher-C-Panel #264,
 *      Formel-Tooltips) ohne CO₂-Spalte (R4) + Disclaimer
 *
 * Die Render-Bausteine + der Daten-Hook liegen geteilt in `components/roi/RoiAnalyse`
 * (eine Code-Wahrheit mit der IST-Seite ROIDashboard). D3: prop-getrieben — Strompreis/
 * Einspeisevergütung aus den Anlagen-Einstellungen (`useAktuellerStrompreis`), KEINE
 * Parameter-Slider, Anlagen-Auswahl = globale v4-Shell. Format via `lib/einheiten.ts`
 * (R1/R2: Geld in € mit Tausenderpunkt, kein k€). Ein `getROIDashboard`-Call (Hook am
 * Sicht-Sockel), von allen Blöcken geteilt.
 */
import { TrendingUp, Clock, PieChart, LayoutGrid, PiggyBank } from 'lucide-react'
import { LoadingSpinner, Card, Alert, EmptyState } from '../components/ui'
import { BlockShell, KpiStrip, type Block } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar } from '../components/park'
import {
  useRoiAnalyse, roiKpiItems,
  RoiAmortisationChart, RoiTypPie, RoiVergleichBar, RoiDetailTabelle, RoiHinweis,
} from '../components/roi/RoiAnalyse'
import { formatGeld } from '../lib'
import { useSelectedAnlage, useAktuellerStrompreis } from '../hooks'

const SICHT_KEY = 'v4-auswertungen-roi'

export default function AuswertungenRoiV4() {
  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <RoiInner />
    </ParkProvider>
  )
}

function RoiInner() {
  const { anlagen, selectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const { strompreis } = useAktuellerStrompreis(selectedAnlageId ?? null)
  const vm = useRoiAnalyse({
    anlageId: selectedAnlageId ?? 0,
    strompreis: strompreis?.netzbezug_arbeitspreis_cent_kwh,
    einspeiseverguetung: strompreis?.einspeiseverguetung_cent_kwh,
  })

  if (anlagenLoading || vm.loading) return <LoadingSpinner text="Lade ROI-Daten…" />
  if (anlagen.length === 0 || !selectedAnlageId) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage angelegt.</p></Card>
      </div>
    )
  }
  if (vm.error) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Alert type="error" onClose={() => vm.setError(null)}>{vm.error}</Alert>
      </div>
    )
  }
  if (vm.roiData && vm.roiData.berechnungen.length === 0) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <EmptyState
          icon={PiggyBank}
          title="Keine aktiven Investitionen"
          description="Erfasse Investitionen auf der Investitionen-Seite, um deren Wirtschaftlichkeit zu analysieren."
        />
      </div>
    )
  }
  if (!vm.roiData) return null
  const roiData = vm.roiData

  const bloecke: Block[] = [
    {
      id: 'wirtschaftlichkeit', title: 'Wirtschaftlichkeit auf einen Blick', icon: TrendingUp,
      farbe: 'text-green-500', defaultOpen: true,
      summary: `${formatGeld(roiData.gesamt_investition).text} investiert · ${roiData.gesamt_amortisation_jahre ? `${roiData.gesamt_amortisation_jahre} J. Amortisation` : 'Amortisation offen'}`,
      render: () => <KpiStrip kpis={roiKpiItems(roiData, false)} />,
    },
    {
      id: 'amortisation', title: 'Amortisation', icon: Clock, farbe: 'text-orange-500', defaultOpen: false,
      summary: 'Break-Even-Kurve (kumulierte Einsparung vs. Investition)',
      render: () => (
        <Parkbar id="chart:amortisation" titel="Amortisationsverlauf">
          <RoiAmortisationChart vm={vm} />
        </Parkbar>
      ),
    },
    {
      id: 'verteilung', title: 'Verteilung & Vergleich', icon: PieChart, farbe: 'text-blue-500', defaultOpen: false,
      summary: 'Einsparungen nach Typ (Pie) · Investitionen im Vergleich (Bar)',
      render: () => (
        <div className="space-y-4">
          <Parkbar id="chart:typ-pie" titel="Einsparungen nach Typ"><RoiTypPie vm={vm} /></Parkbar>
          <Parkbar id="chart:vergleich-bar" titel="Investitionen im Vergleich"><RoiVergleichBar vm={vm} /></Parkbar>
        </div>
      ),
    },
    {
      id: 'detail', title: 'Detailübersicht je Investition', icon: LayoutGrid, farbe: 'text-gray-400', defaultOpen: false,
      summary: 'Kosten · ROI · Amortisation je Investition (+ Speicher-Detail #264)',
      render: () => (
        <div className="space-y-4">
          <Parkbar id="tabelle:detail" titel="Detailübersicht"><RoiDetailTabelle vm={vm} zeigeCo2={false} /></Parkbar>
          <Parkbar id="info:roi-hinweis" titel="Hinweis zur Prognose"><RoiHinweis /></Parkbar>
        </div>
      ),
    },
  ]

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      <h1 className="text-lg font-bold text-gray-900 dark:text-white">Wirtschaftlichkeit (ROI)</h1>
      <BlockShell persistKey={SICHT_KEY} bloecke={bloecke} sortierbar />
      <ParkFuss />
    </div>
  )
}
