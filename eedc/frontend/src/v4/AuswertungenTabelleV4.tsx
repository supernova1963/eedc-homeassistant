/**
 * AuswertungenTabelleV4 — die volle Werte-Werkbank im /v4-Baum (A.5 Sub 1).
 *
 * Konsumiert den Werte-SoT (`WerteTabelle`, Granularität „monat"): Spalten-Picker,
 * CSV-Export, Vorjahr-Vergleich, Footer-Aggregat. Ein BlockShell-Block „Monatswerte"
 * (einklappbar/Fokus); die Tabelle selbst ist ein **parkbares Element** (R6) —
 * geparkt → Block-Hülle ausgeblendet, Rückholen über „Geparkt (n)".
 */
import { useEffect, useMemo, useState } from 'react'
import { Table } from 'lucide-react'
import { LoadingSpinner, Card } from '../components/ui'
import { BlockShell, type Block } from '../components/blocks'
import { ParkProvider, ParkFuss, Parkbar, usePark } from '../components/park'
import { WerteTabelle } from '../components/werte'
import { monatsZeile } from '../lib/werte'
import { useSelectedAnlage } from '../hooks'
import { useWerteZeitreihe } from './useWerteZeitreihe'
import { AuswertungKopf } from './AuswertungKopf'

const SICHT_KEY = 'v4-auswertungen-tabelle'

export default function AuswertungenTabelleV4() {
  return (
    <ParkProvider persistKey={SICHT_KEY}>
      <TabelleInner />
    </ParkProvider>
  )
}

function TabelleInner() {
  const park = usePark()
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

  // Tabelle = parkbares Element. Geparkt → Block-Hülle ausblenden (Empty-Block-Hide).
  const tabelleGeparkt = park.istGeparkt('tabelle:monatswerte')
  const bloecke: Block[] = tabelleGeparkt ? [] : [{
    id: 'monatswerte', title: 'Monatswerte', icon: Table, farbe: 'text-gray-400',
    summary: jahr === 'alle' ? 'alle Jahre' : `${jahr}`, defaultOpen: true,
    render: () => (
      <Parkbar id="tabelle:monatswerte" titel="Monatswerte">
        <WerteTabelle
          rows={gefiltert.map(monatsZeile)}
          vorjahrRows={vorjahrRows ? vorjahrRows.map(monatsZeile) : null}
          granularitaet="monat"
          jahrLabel={jahr === 'alle' ? '' : jahr}
          vergleichLabel={vergleichsJahr}
          csvDateiname={`werte_${selectedAnlage?.anlagenname ?? 'export'}.csv`}
        />
      </Parkbar>
    ),
  }]

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

      <BlockShell key={`tabelle-${jahr}`} persistKey={SICHT_KEY} bloecke={bloecke} />
      <ParkFuss />
    </div>
  )
}
