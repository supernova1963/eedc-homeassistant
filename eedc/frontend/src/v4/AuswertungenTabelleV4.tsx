/**
 * AuswertungenTabelleV4 — die volle Werte-Werkbank im /v4-Baum (Plan 3.1).
 *
 * Konsumiert den Werte-SoT (`WerteTabelle`, Granularität „monat"): Spalten-
 * Picker, CSV-Export, Vorjahr-Vergleich, Footer-Aggregat. Speist sich über
 * `useWerteZeitreihe` aus der Demo-DB (relativer API-Pfad). Die Produktiv-Seite
 * Auswertungen/Tabelle (`TabelleTab`) bleibt bis zum Flip (3.8) unangetastet.
 */
import { useEffect, useMemo, useState } from 'react'
import { LoadingSpinner, Card } from '../components/ui'
import { WerteTabelle } from '../components/werte'
import { monatsZeile } from '../lib/werte'
import { useSelectedAnlage } from '../hooks'
import { useWerteZeitreihe } from './useWerteZeitreihe'
import { AuswertungKopf } from './AuswertungKopf'

export default function AuswertungenTabelleV4() {
  const { anlagen, selectedAnlageId, selectedAnlage, loading: anlagenLoading } = useSelectedAnlage()
  const { rows, jahre, loading, error } = useWerteZeitreihe(selectedAnlageId, selectedAnlage)
  const [jahr, setJahr] = useState<number | 'alle'>('alle')
  // Vergleichsjahr frei wählbar (IST-Parität TabelleTab `compareYear`); nur bei
  // konkretem Jahr aktiv, Auto-Default = Vorjahr (sonst nächstverfügbares).
  const [vergleichsJahr, setVergleichsJahr] = useState<number | null>(null)

  const verfuegbareVergleichsJahre = useMemo(
    () => (jahr === 'alle' ? [] : jahre.filter((j) => j !== jahr)),
    [jahr, jahre],
  )
  useEffect(() => {
    if (jahr === 'alle' || verfuegbareVergleichsJahre.length === 0) { setVergleichsJahr(null); return }
    setVergleichsJahr(verfuegbareVergleichsJahre.includes(jahr - 1) ? jahr - 1 : verfuegbareVergleichsJahre[0])
  }, [jahr, verfuegbareVergleichsJahre])

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
  const vorjahrRows = vergleichsJahr == null ? null : rows.filter((r) => r.jahr === vergleichsJahr)

  return (
    <div className="p-3 sm:p-6 max-w-[1920px] mx-auto space-y-4">
      <AuswertungKopf titel="Werte-Werkbank" jahr={jahr} setJahr={setJahr} jahre={jahre}>
        {jahr !== 'alle' && verfuegbareVergleichsJahre.length > 0 && (
          <select
            value={vergleichsJahr ?? ''}
            onChange={(e) => setVergleichsJahr(e.target.value ? Number(e.target.value) : null)}
            aria-label="Vergleichsjahr wählen"
            className="input w-auto"
          >
            {verfuegbareVergleichsJahre.map((j) => <option key={j} value={j}>vs. {j}</option>)}
          </select>
        )}
      </AuswertungKopf>

      <Card>
        <WerteTabelle
          rows={gefiltert.map(monatsZeile)}
          vorjahrRows={vorjahrRows ? vorjahrRows.map(monatsZeile) : null}
          granularitaet="monat"
          jahrLabel={jahr === 'alle' ? '' : jahr}
          vergleichLabel={vergleichsJahr}
          csvDateiname={`werte_${selectedAnlage?.anlagenname ?? 'export'}.csv`}
        />
      </Card>
    </div>
  )
}
