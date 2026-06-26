/**
 * PV-Anlage Tab — String-Performance-Analyse über Zeit (IST-Seite).
 *
 * Komponiert die geteilten Block-②/③-Bausteine aus `components/prognose/
 * PvStringsTeile` (eine Code-Wahrheit mit der v4-Auswertungen-Sicht). Diese Datei
 * trägt nur Datenladung (Hook), Datenzustands-Hüllen + die Komposition.
 */
import { Sun, AlertTriangle } from 'lucide-react'
import { Card, LoadingSpinner, Alert } from '../../components/ui'
import { KpiStrip } from '../../components/blocks'
import {
  usePvStrings, pvStringsKpiItems, exportPvStringsCsv,
  PvStringHeaderZeile, PvStringBestSchlecht, PvStringSollIstBar,
  PvStringMonatsverlauf, PvStringTabelle, PvStringMehrjahr,
} from '../../components/prognose/PvStringsTeile'

interface PVAnlageTabProps {
  anlageId: number
  selectedYear: number | 'all'
  verfuegbareJahre: number[]
  zeitraumLabel?: string
}

export function PVAnlageTab({ anlageId, selectedYear, verfuegbareJahre, zeitraumLabel }: PVAnlageTabProps) {
  const { data, loading, error, jahresvergleichData } = usePvStrings(anlageId, selectedYear, verfuegbareJahre)

  if (loading) return <LoadingSpinner text="Lade PV-String Daten..." />
  if (error) return <Alert type="error">{error}</Alert>

  if (!data || data.strings.length === 0) {
    return (
      <Card className="text-center py-8">
        <Sun className="h-12 w-12 mx-auto text-gray-400 dark:text-gray-500 mb-4" />
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">Keine PV-Module gefunden</h3>
        <p className="text-gray-500 dark:text-gray-400">Bitte PV-Module unter Einstellungen → Investitionen anlegen.</p>
      </Card>
    )
  }

  if (!data.hat_prognose) {
    return (
      <Alert type="warning">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4" />
          <span>Keine PVGIS-Prognose vorhanden. Bitte unter Einstellungen → PVGIS eine Prognose abrufen, um den SOLL-IST Vergleich zu nutzen.</span>
        </div>
      </Alert>
    )
  }

  return (
    <div className="space-y-6">
      <PvStringHeaderZeile data={data} zeitraumLabel={zeitraumLabel} onCsv={() => exportPvStringsCsv(data, selectedYear)} />
      <KpiStrip kpis={pvStringsKpiItems(data, zeitraumLabel)} />
      <PvStringBestSchlecht data={data} />
      <PvStringSollIstBar data={data} />
      <PvStringMonatsverlauf data={data} selectedYear={selectedYear} />
      {selectedYear === 'all' && jahresvergleichData.length > 1 && (
        <PvStringMehrjahr data={data} jahresvergleichData={jahresvergleichData} />
      )}
      <PvStringTabelle data={data} />
    </div>
  )
}
