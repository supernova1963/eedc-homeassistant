/**
 * Prognose vs. IST Auswertung (IST-Seite).
 *
 * Vergleicht PVGIS-Ertragsprognose mit tatsächlichen Monatsdaten. Komponiert die
 * geteilten Block-①-Bausteine aus `components/prognose/PrognoseVsIstTeile`
 * (eine Code-Wahrheit mit der v4-Auswertungen-Sicht); diese Seite trägt nur den
 * eigenen Kopf (Anlage-/Jahr-Wahl, Reload) + die Datenzustands-Hüllen.
 */
import { useState, useEffect } from 'react'
import { Target, Sun, AlertCircle, RefreshCw } from 'lucide-react'
import { Card, LoadingSpinner, Alert, Select } from '../components/ui'
import { KpiStrip } from '../components/blocks'
import { useSelectedAnlage } from '../hooks'
import {
  usePrognoseVsIst, pvgisKpiItems,
  PvgisSpeichern, PvgisMonatsChart, PvgisDetailTabelle, PvgisErklaerung,
} from '../components/prognose/PrognoseVsIstTeile'

export default function PrognoseVsIst() {
  const { anlagen, selectedAnlageId, setSelectedAnlageId, loading: anlagenLoading } = useSelectedAnlage()
  const [selectedJahr, setSelectedJahr] = useState<number>(new Date().getFullYear())
  const vm = usePrognoseVsIst(selectedAnlageId, selectedJahr)
  const verfuegbareJahre = vm.verfuegbareJahre

  // Jahr automatisch auf das neueste mit Daten setzen
  useEffect(() => {
    if (verfuegbareJahre.length > 0 && !verfuegbareJahre.includes(selectedJahr)) {
      setSelectedJahr(verfuegbareJahre[0])
    }
  }, [verfuegbareJahre, selectedJahr])

  if (anlagenLoading) return <LoadingSpinner text="Lade..." />

  if (anlagen.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Prognose vs. IST</h1>
        <Alert type="warning">Bitte zuerst eine Anlage anlegen.</Alert>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div className="flex items-center gap-3">
          <Target className="h-8 w-8 text-purple-500" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Prognose vs. IST</h1>
        </div>
        <div className="flex items-center gap-3">
          {anlagen.length > 1 && (
            <Select
              value={selectedAnlageId?.toString() || ''}
              onChange={(e) => setSelectedAnlageId(parseInt(e.target.value))}
              options={anlagen.map(a => ({ value: a.id.toString(), label: a.anlagenname }))}
            />
          )}
          {verfuegbareJahre.length > 0 && (
            <Select
              value={selectedJahr.toString()}
              onChange={(e) => setSelectedJahr(parseInt(e.target.value))}
              options={verfuegbareJahre.map(j => ({ value: j.toString(), label: j.toString() }))}
            />
          )}
          <button
            onClick={vm.reload}
            disabled={vm.loading}
            className="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            title="Aktualisieren"
          >
            <RefreshCw className={`h-5 w-5 ${vm.loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {vm.error && <Alert type="error">{vm.error}</Alert>}

      {vm.loading ? (
        <LoadingSpinner text="Lade Vergleichsdaten..." />
      ) : !vm.prognose ? (
        <Card>
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <Sun className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Keine PVGIS Prognose verfügbar.</p>
            <p className="text-sm mt-2">Bitte definiere PV-Module unter "Einstellungen → Investitionen".</p>
          </div>
        </Card>
      ) : vm.monatsdaten.length === 0 ? (
        <Card>
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            <AlertCircle className="h-12 w-12 mx-auto mb-4 opacity-50" />
            <p>Keine Monatsdaten für diese Anlage vorhanden.</p>
            <p className="text-sm mt-2">Erfasse Monatsdaten unter "Einstellungen → Monatsdaten".</p>
          </div>
        </Card>
      ) : (
        <>
          <PvgisSpeichern vm={vm} />
          <KpiStrip kpis={pvgisKpiItems(vm, selectedJahr)} />
          <PvgisMonatsChart vm={vm} jahr={selectedJahr} />
          <PvgisDetailTabelle vm={vm} />
          <PvgisErklaerung />
        </>
      )}
    </div>
  )
}
