/**
 * E-Auto-Hub-Blöcke (IA v4) — ④ Verlauf · ⑤ Vergleich · Wirtschaftlichkeit.
 * Self-fetch über anlageId + aktives Gerät; rendern die geteilten IST-Komponenten
 * aus `components/eauto` (eine Code-Wahrheit mit `EAutoDashboard`).
 */
import { useEffect, useState } from 'react'
import {
  EAutoKmVerlauf, EAutoLadungVerlauf, EAutoMonatsTabelle, EAutoKostenvergleich, EAutoJahresvergleich,
} from '../components/eauto'
import { investitionenApi, type EAutoDashboardResponse } from '../api/investitionen'
import type { Investition } from '../types'

function useEAutoGeraet(anlageId: number, inv?: Investition) {
  const [ds, setDs] = useState<EAutoDashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let ab = false
    setLoading(true)
    investitionenApi.getEAutoDashboard(anlageId)
      .then((liste) => { if (!ab) setDs(liste.find((d) => d.investition.id === inv?.id) ?? liste[0] ?? null) })
      .catch(() => { if (!ab) setDs(null) })
      .finally(() => { if (!ab) setLoading(false) })
    return () => { ab = true }
  }, [anlageId, inv?.id])
  return { ds, loading }
}

const Lade = () => <p className="text-sm text-gray-400 dark:text-gray-500">Lade…</p>
const Leer = ({ text }: { text: string }) => <p className="text-sm text-gray-500 dark:text-gray-400">{text}</p>

/** ④ Verlauf: km/Monat + Ladung/Monat (PV/Netz/Extern) + Monatstabelle. */
export function EAutoVerlaufIST({ anlageId, inv }: { anlageId: number; inv?: Investition }) {
  const { ds, loading } = useEAutoGeraet(anlageId, inv)
  if (loading) return <Lade />
  if (!ds || ds.monatsdaten.length === 0) return <Leer text="Keine Verlaufsdaten erfasst." />
  return (
    <div className="space-y-4">
      <div className="grid lg:grid-cols-2 gap-4">
        <div>
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Kilometer pro Monat</h4>
          <EAutoKmVerlauf monatsdaten={ds.monatsdaten} />
        </div>
        <div>
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Ladung pro Monat nach Quelle</h4>
          <EAutoLadungVerlauf monatsdaten={ds.monatsdaten} />
        </div>
      </div>
      <details className="border-t border-gray-100 dark:border-gray-800 pt-3">
        <summary className="cursor-pointer text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
          Monatsdaten anzeigen ({ds.monatsdaten.length})
        </summary>
        <div className="mt-3"><EAutoMonatsTabelle monatsdaten={ds.monatsdaten} /></div>
      </details>
    </div>
  )
}

/** ⑤ Vergleich: Ladung nach Quelle pro Jahr (PV-Anteil-Entwicklung). */
export function EAutoVergleichIST({ anlageId, inv }: { anlageId: number; inv?: Investition }) {
  const { ds, loading } = useEAutoGeraet(anlageId, inv)
  if (loading) return <Lade />
  if (!ds || ds.monatsdaten.length === 0) return <Leer text="Keine Vergleichsdaten erfasst." />
  return <EAutoJahresvergleich monatsdaten={ds.monatsdaten} embed />
}

/** Wirtschaftlichkeit: Kostenvergleich E-Auto vs. Verbrenner + Ersparnis. */
export function EAutoWirtschaftlichkeitIST({ anlageId, inv }: { anlageId: number; inv?: Investition }) {
  const { ds, loading } = useEAutoGeraet(anlageId, inv)
  if (loading) return <Lade />
  if (!ds) return <Leer text="Keine Wirtschaftlichkeitsdaten erfasst." />
  return <EAutoKostenvergleich zusammenfassung={ds.zusammenfassung} />
}
