/**
 * Wärmepumpen-Hub-Blöcke (IA v4) — ④ Verlauf · ⑤ Vergleich · Wirtschaftlichkeit.
 * Self-fetch über anlageId + aktives Gerät; rendern die geteilten IST-Komponenten
 * aus `components/waermepumpe` (eine Code-Wahrheit mit `WaermepumpeDashboard`).
 */
import { useEffect, useState } from 'react'
import {
  WaermepumpeMonatsverlauf, WaermepumpeMonatsTabelle, WaermepumpeVergleich, WaermepumpeKostenvergleich,
  WaermepumpeModusSplit, hatModusSplit, wpHatVergleich,
} from '../components/waermepumpe'
import { Parkbar } from '../components/park'
import { investitionenApi, type WaermepumpeDashboardResponse } from '../api/investitionen'
import type { MeldeFn } from './komponentenAnalyse'
import type { Investition } from '../types'

const KEINE: string[] = []
const VERLAUF_IDS = ['chart:wp-waerme', 'tabelle:wp-monate']
const VERLAUF_IDS_MIT_SPLIT = [...VERLAUF_IDS, 'block:wp-modus-split']
const VERGLEICH_IDS = ['chart:wp-vergleich']
const WIRT_IDS = ['chart:wp-kostenvergleich']

function useWpGeraet(anlageId: number, inv?: Investition) {
  const [ds, setDs] = useState<WaermepumpeDashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let ab = false
    setLoading(true)
    investitionenApi.getWaermepumpeDashboard(anlageId)
      .then((liste) => { if (!ab) setDs(liste.find((d) => d.investition.id === inv?.id) ?? liste[0] ?? null) })
      .catch(() => { if (!ab) setDs(null) })
      .finally(() => { if (!ab) setLoading(false) })
    return () => { ab = true }
  }, [anlageId, inv?.id])
  return { ds, loading }
}

const Lade = () => <p className="text-sm text-gray-400 dark:text-gray-500">Lade…</p>
const Leer = ({ text }: { text: string }) => <p className="text-sm text-gray-500 dark:text-gray-400">{text}</p>

/** ④ Verlauf: Wärmeerzeugung/Monat (Area) + Monatsdaten-Tabelle (Strom/Heizung/WW/JAZ). */
export function WaermepumpeVerlaufIST({ anlageId, inv, melde }: { anlageId: number; inv?: Investition; melde?: MeldeFn }) {
  const { ds, loading } = useWpGeraet(anlageId, inv)
  const leer = loading || !ds || ds.monatsdaten.length === 0
  const zeigtSplit = !leer && hatModusSplit(ds?.zusammenfassung)
  useEffect(() => {
    melde?.(leer ? KEINE : (zeigtSplit ? VERLAUF_IDS_MIT_SPLIT : VERLAUF_IDS))
  }, [leer, zeigtSplit, melde])
  if (loading) return <Lade />
  if (!ds || ds.monatsdaten.length === 0) return <Leer text="Keine Verlaufsdaten erfasst." />
  return (
    <div className="space-y-4">
      {/* #263 K-2 (S4): nur mit erfasstem Modus — ohne ihn fehlt der Block
          ganz, statt mit Nullen dazustehen (Konzept §4). */}
      {zeigtSplit && (
        <Parkbar id="block:wp-modus-split" titel="Aufteilung Heizen/Kühlen">
          <WaermepumpeModusSplit zusammenfassung={ds.zusammenfassung} />
        </Parkbar>
      )}
      <Parkbar id="chart:wp-waerme" titel="Wärmeerzeugung pro Monat"><WaermepumpeMonatsverlauf monatsdaten={ds.monatsdaten} /></Parkbar>
      <Parkbar id="tabelle:wp-monate" titel="Monatsdaten-Tabelle">
        <details className="border-t border-gray-100 dark:border-gray-800 pt-3">
          <summary className="cursor-pointer text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
            Monatsdaten anzeigen ({ds.monatsdaten.length})
          </summary>
          <div className="mt-3"><WaermepumpeMonatsTabelle monatsdaten={ds.monatsdaten} jazJeMonat={ds.zusammenfassung.jaz_je_monat} /></div>
        </details>
      </Parkbar>
    </div>
  )
}

/** ⑤ Vergleich: Monats-/Saisonvergleich mit JAZ⇄Strom-Toggle. */
export function WaermepumpeVergleichIST({ anlageId, inv, melde }: { anlageId: number; inv?: Investition; melde?: MeldeFn }) {
  const { ds, loading } = useWpGeraet(anlageId, inv)
  const leer = loading || !ds || ds.monatsdaten.length === 0
  useEffect(() => { melde?.(leer ? KEINE : VERGLEICH_IDS) }, [leer, melde])
  if (loading) return <Lade />
  if (!ds || ds.monatsdaten.length === 0) return <Leer text="Keine Vergleichsdaten erfasst." />
  return <Parkbar id="chart:wp-vergleich" titel="Monats-/Saisonvergleich"><WaermepumpeVergleich monatsdaten={ds.monatsdaten} jazJeMonat={ds.zusammenfassung.jaz_je_monat} hatGetrennteStrom={ds.zusammenfassung.gesamt_strom_heizen_kwh !== undefined} /></Parkbar>
}

/** Wirtschaftlichkeit: Kostenvergleich WP vs. Gas/Öl + Ersparnis. */
export function WaermepumpeWirtschaftlichkeitIST({ anlageId, inv, melde }: { anlageId: number; inv?: Investition; melde?: MeldeFn }) {
  const { ds, loading } = useWpGeraet(anlageId, inv)
  const leer = loading || !ds
  useEffect(() => { melde?.(leer ? KEINE : WIRT_IDS) }, [leer, melde])
  if (loading) return <Lade />
  if (!ds) return <Leer text="Keine Wirtschaftlichkeitsdaten erfasst." />
  // F-42: Der Titel darf nichts versprechen, was der Block nicht zeigt — ohne
  // ersetzte Heizung gibt es keinen Vergleich, sondern nur die Stromkosten.
  const titel = wpHatVergleich(ds.zusammenfassung) ? 'Kostenvergleich WP vs. Gas/Öl' : 'Stromkosten'
  return <Parkbar id="chart:wp-kostenvergleich" titel={titel}><WaermepumpeKostenvergleich zusammenfassung={ds.zusammenfassung} /></Parkbar>
}
