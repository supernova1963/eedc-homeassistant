/**
 * AuswertungenRoiV4 — ROI-/Wirtschaftlichkeits-Auswertung (A.5 Sub 5, Rebuild-lite D3).
 *
 * Vier verschiebbare BlockShell-Blöcke (SPEC-AUSWERTUNGEN §0a), jeder aus einzeln
 * parkbaren Elementen (R6) — wie Sub 2/3/4:
 *   ① Wirtschaftlichkeit auf einen Blick — 3 KPIs (Investition · Einsparung ·
 *      Amortisation; CO₂-KPI entfällt, R4)
 *   ② Amortisation — Break-Even-Kurve
 *   ③ Verteilung & Vergleich — Typ-Balken (R18-5: Rangfolge + Werte) + Bar je Investition
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
import { Alert, EmptyState } from '../components/ui'
import { BlockShell, BlockStackSkeleton, KpiStrip, type Block } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar, usePark } from '../components/park'
import {
  useRoiAnalyse, roiKpiItems,
  RoiAmortisationChart, RoiTypBalken, RoiVergleichBar, RoiDetailTabelle, RoiHinweis,
} from '../components/roi/RoiAnalyse'
import { formatGeld } from '../lib'
import { useSelectedAnlage, useAktuellerStrompreis } from '../hooks'
import { AnlageLeer } from './OnboardingLeer'

const SICHT_KEY = 'v4-auswertungen-roi'

export default function AuswertungenRoiV4() {
  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <RoiInner />
    </ParkProvider>
  )
}

function RoiInner() {
  const park = usePark()
  const { anlagen, selectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const { strompreis } = useAktuellerStrompreis(selectedAnlageId ?? null)
  const vm = useRoiAnalyse({
    anlageId: selectedAnlageId ?? 0,
    strompreis: strompreis?.netzbezug_arbeitspreis_cent_kwh,
    einspeiseverguetung: strompreis?.einspeiseverguetung_cent_kwh,
    // R18-2 (SWR): beim Tab-Wechsel stehen die alten Daten sofort, kein Skeleton.
    swrKeyBasis: 'v4-ausw-roi',
  })

  if (anlagenLoading || vm.loading) {
    // B8 (S15): Sicht-Skeleton in BlockShell-Form (4 Blöcke deterministisch).
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <BlockStackSkeleton label="Lade ROI-Daten…" zu={3} />
      </div>
    )
  }
  if (anlagen.length === 0 || !selectedAnlageId) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <AnlageLeer titel="Noch keine Anlage angelegt." />
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

  // Auto-Hide (Phase 3b, Gernot 2026-07-09): Block entfällt, wenn ALLE seine real
  // gerenderten Park-Elemente geparkt sind (Block ① parkt je KPI via roiKpiItems-parkId).
  const sichtbar = (ids: string[]) => !ids.every((id) => park.istGeparkt(id))
  const bloecke: Block[] = [
    ...(sichtbar(['kpi:investition', 'kpi:einsparung', 'kpi:amortisation', 'kpi:amortisation-fortschritt']) ? [{
      id: 'wirtschaftlichkeit', title: 'Wirtschaftlichkeit auf einen Blick', icon: TrendingUp,
      farbe: 'text-green-500', defaultOpen: true,
      summary: `${formatGeld(roiData.gesamt_investition).text} investiert · ${roiData.gesamt_amortisation_jahre
        ? `${roiData.gesamt_amortisation_jahre} J. Amortisation${roiData.gesamt_amortisation_jahr ? ` (≈ ${roiData.gesamt_amortisation_jahr})` : ''}`
        : 'Amortisation offen'}`,
      render: () => <KpiStrip kpis={roiKpiItems(roiData, false, vm.fortschritt)} />,
    }] : []),
    ...(sichtbar(['chart:amortisation']) ? [{
      id: 'amortisation', title: 'Amortisation', icon: Clock, farbe: 'text-orange-500', defaultOpen: false,
      summary: 'Break-Even-Kurve (kumulierte Einsparung vs. Investition)',
      render: () => (
        <Parkbar id="chart:amortisation" titel="Amortisationsverlauf">
          <RoiAmortisationChart vm={vm} />
        </Parkbar>
      ),
    }] : []),
    ...(sichtbar(['chart:typ-pie', 'chart:vergleich-bar']) ? [{
      id: 'verteilung', title: 'Verteilung & Vergleich', icon: PieChart, farbe: 'text-blue-500', defaultOpen: false,
      summary: 'Einsparungen nach Typ · Investitionen im Vergleich (Balken)',
      render: () => (
        <div className="space-y-4">
          <Parkbar id="chart:typ-pie" titel="Einsparungen nach Typ"><RoiTypBalken vm={vm} /></Parkbar>
          <Parkbar id="chart:vergleich-bar" titel="Investitionen im Vergleich"><RoiVergleichBar vm={vm} /></Parkbar>
        </div>
      ),
    }] : []),
    ...(sichtbar(['tabelle:detail', 'info:roi-hinweis']) ? [{
      id: 'detail', title: 'Detailübersicht je Investition', icon: LayoutGrid, farbe: 'text-gray-400 dark:text-gray-500', defaultOpen: false,
      summary: 'Kosten · ROI · Amortisation je Investition (+ Speicher-Detail #264)',
      render: () => (
        <div className="space-y-4">
          <Parkbar id="tabelle:detail" titel="Detailübersicht"><RoiDetailTabelle vm={vm} zeigeCo2={false} /></Parkbar>
          <Parkbar id="info:roi-hinweis" titel="Hinweis zur Prognose"><RoiHinweis /></Parkbar>
        </div>
      ),
    }] : []),
  ]

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      <h1 className="text-lg font-bold text-gray-900 dark:text-white">Wirtschaftlichkeit (ROI)</h1>
      <BlockShell persistKey={SICHT_KEY} bloecke={bloecke} sortierbar />
      <ParkFuss />
    </div>
  )
}
