/**
 * AuswertungenRoiV4 — ROI-/Wirtschaftlichkeits-Auswertung (A.5, Rebuild-lite, D3).
 *
 * Reine ROI-Analyse über die geteilte `RoiAnalyse`-SoT — OHNE Parameter-Slider
 * (Gernot-Entscheid D3): Strompreis/Einspeisevergütung kommen aus den Anlagen-
 * Einstellungen (`useAktuellerStrompreis`), der Benzinpreis-Default aus dem
 * Backend. Anlagen-Auswahl = globale v4-Shell (kein eigener Selektor).
 * KPIs · Amortisationskurve · ROI nach Typ · Speicher-C-Detail (#264) · Tabelle.
 */
import { LoadingSpinner, Card } from '../components/ui'
import { RoiAnalyse } from '../components/roi/RoiAnalyse'
import { useSelectedAnlage, useAktuellerStrompreis } from '../hooks'

export default function AuswertungenRoiV4() {
  const { anlagen, selectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const { strompreis } = useAktuellerStrompreis(selectedAnlageId ?? null)

  if (anlagenLoading) return <LoadingSpinner text="Lade ROI-Daten…" />
  if (anlagen.length === 0) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage angelegt.</p></Card>
      </div>
    )
  }

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      <h1 className="text-lg font-bold text-gray-900 dark:text-white">Wirtschaftlichkeit (ROI)</h1>
      {selectedAnlageId && (
        <RoiAnalyse
          anlageId={selectedAnlageId}
          strompreis={strompreis?.netzbezug_arbeitspreis_cent_kwh}
          einspeiseverguetung={strompreis?.einspeiseverguetung_cent_kwh}
        />
      )}
    </div>
  )
}
