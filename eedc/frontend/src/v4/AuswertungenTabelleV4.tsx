/**
 * AuswertungenTabelleV4 — die volle Werte-Werkbank im /v4-Baum (Plan 3.1).
 *
 * Konsumiert den Werte-SoT (`WerteTabelle`, Granularität „monat"): Spalten-
 * Picker, CSV-Export, Vorjahr-Vergleich, Footer-Aggregat. Speist sich über
 * `useWerteZeitreihe` aus der Demo-DB (relativer API-Pfad). Die Produktiv-Seite
 * Auswertungen/Tabelle (`TabelleTab`) bleibt bis zum Flip (3.8) unangetastet.
 */
import { useState } from 'react'
import { LoadingSpinner, Card } from '../components/ui'
import { WerteTabelle } from '../components/werte'
import { monatsZeile } from '../lib/werte'
import { useSelectedAnlage } from '../hooks'
import { ViewShell } from './ViewShell'
import { useWerteZeitreihe } from './useWerteZeitreihe'

export default function AuswertungenTabelleV4() {
  const { anlagen, selectedAnlageId, selectedAnlage, loading: anlagenLoading } = useSelectedAnlage()
  const { rows, jahre, loading, error } = useWerteZeitreihe(selectedAnlageId, selectedAnlage)
  const [jahr, setJahr] = useState<number | 'alle'>('alle')

  if (anlagenLoading || loading) return <LoadingSpinner text="Lade Werte…" />
  if (anlagen.length === 0) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-sm text-gray-500 dark:text-gray-400">Noch keine Anlage angelegt.</p></Card>
      </div>
    )
  }
  if (error) {
    return (
      <div className="p-3 sm:p-6 max-w-[1920px] mx-auto">
        <Card><p className="text-red-500">{error}</p></Card>
      </div>
    )
  }

  const gefiltert = jahr === 'alle' ? rows : rows.filter((r) => r.jahr === jahr)
  const vorjahrRows = jahr === 'alle' ? null : rows.filter((r) => r.jahr === jahr - 1)

  return (
    <ViewShell>
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h1 className="text-lg font-bold text-gray-900 dark:text-white">Werte-Tabelle</h1>
        <select
          value={jahr === 'alle' ? '' : jahr}
          onChange={(e) => setJahr(e.target.value ? Number(e.target.value) : 'alle')}
          aria-label="Jahr filtern"
          className="input w-auto"
        >
          <option value="">Alle Jahre</option>
          {jahre.map((j) => <option key={j} value={j}>{j}</option>)}
        </select>
      </div>

      <Card>
        <WerteTabelle
          rows={gefiltert.map(monatsZeile)}
          vorjahrRows={vorjahrRows ? vorjahrRows.map(monatsZeile) : null}
          granularitaet="monat"
          jahrLabel={jahr === 'alle' ? '' : jahr}
          vergleichLabel={jahr === 'alle' ? null : jahr - 1}
          csvDateiname={`werte_${selectedAnlage?.anlagenname ?? 'export'}.csv`}
        />
      </Card>
    </div>
    </ViewShell>
  )
}
