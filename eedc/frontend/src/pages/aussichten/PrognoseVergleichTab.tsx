/**
 * Prognosen-Vergleich Tab: Evaluierungs-Cockpit für PV-Prognosen (IST-Seite).
 *
 * Vergleicht OpenMeteo (roh), eedc (kalibriert), Solcast und IST. Komponiert die
 * geteilten Block-④/⑤-Bausteine aus `components/prognose/PrognoseVergleichTeile`
 * (eine Code-Wahrheit mit der v4-Auswertungen-Sicht); Datenladung + Steuer-States
 * im Hook `usePrognoseVergleich`.
 */
import { LoadingSpinner, Alert } from '../../components/ui'
import {
  usePrognoseVergleich,
  PvgKpiMatrix, PvgStatusHinweise, PvgLernfaktorO12, PvgStratifizierung, PvgHeatmap,
  PvgStundenprofil, Pvg24hTabelle, Pvg7TageTabelle, PvgGenauigkeitsTracking,
} from '../../components/prognose/PrognoseVergleichTeile'

interface Props {
  anlageId: number
}

export default function PrognoseVergleichTab({ anlageId }: Props) {
  const vm = usePrognoseVergleich(anlageId)

  if (vm.loading) return <div className="flex justify-center py-12"><LoadingSpinner /></div>
  if (vm.error) return <Alert type="error">{vm.error}</Alert>
  if (!vm.data) return null

  return (
    <div className="space-y-6">
      <PvgKpiMatrix vm={vm} />
      <PvgStatusHinweise vm={vm} />
      <PvgLernfaktorO12 vm={vm} />
      <PvgStratifizierung vm={vm} />
      <PvgHeatmap vm={vm} />
      <PvgStundenprofil vm={vm} />
      <Pvg24hTabelle vm={vm} />
      <Pvg7TageTabelle vm={vm} />
      <PvgGenauigkeitsTracking vm={vm} />
    </div>
  )
}
