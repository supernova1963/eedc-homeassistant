/**
 * Balkonkraftwerk-Hub-Blöcke (IA v4) — ④ Verlauf · ⑤ Vergleich.
 * Self-fetch über anlageId + aktives Gerät; rendern die geteilten IST-Komponenten
 * aus `components/balkonkraftwerk` (eine Code-Wahrheit mit `BalkonkraftwerkDashboard`).
 */
import { useEffect, useState } from 'react'
import {
  BkwErzeugungVerlauf, BkwSpeicherVerlauf, BkwMonatsTabelle, BkwJahresvergleich,
} from '../components/balkonkraftwerk'
import { investitionenApi, type BalkonkraftwerkDashboardResponse } from '../api/investitionen'
import type { Investition } from '../types'

function useBkwGeraet(anlageId: number, inv?: Investition) {
  const [ds, setDs] = useState<BalkonkraftwerkDashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let ab = false
    setLoading(true)
    investitionenApi.getBalkonkraftwerkDashboard(anlageId)
      .then((liste) => { if (!ab) setDs(liste.find((d) => d.investition.id === inv?.id) ?? liste[0] ?? null) })
      .catch(() => { if (!ab) setDs(null) })
      .finally(() => { if (!ab) setLoading(false) })
    return () => { ab = true }
  }, [anlageId, inv?.id])
  return { ds, loading }
}

const Lade = () => <p className="text-sm text-gray-400 dark:text-gray-500">Lade…</p>
const Leer = ({ text }: { text: string }) => <p className="text-sm text-gray-500 dark:text-gray-400">{text}</p>

/** ④ Verlauf: Erzeugung/Monat (EV+Einspeisung) + integ. Speicher (wenn vorhanden) + Tabelle. */
export function BkwVerlaufIST({ anlageId, inv }: { anlageId: number; inv?: Investition }) {
  const { ds, loading } = useBkwGeraet(anlageId, inv)
  if (loading) return <Lade />
  if (!ds || ds.monatsdaten.length === 0) return <Leer text="Keine Verlaufsdaten erfasst." />
  const hatSpeicher = ds.zusammenfassung.hat_speicher
  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Erzeugung pro Monat (Eigenverbrauch + Einspeisung)</h4>
        <BkwErzeugungVerlauf monatsdaten={ds.monatsdaten} />
      </div>
      {hatSpeicher && (
        <div>
          <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Integrierter Speicher — Ladung / Entladung</h4>
          <BkwSpeicherVerlauf monatsdaten={ds.monatsdaten} />
        </div>
      )}
      <details className="border-t border-gray-100 dark:border-gray-800 pt-3">
        <summary className="cursor-pointer text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
          Monatsdaten anzeigen ({ds.monatsdaten.length})
        </summary>
        <div className="mt-3"><BkwMonatsTabelle monatsdaten={ds.monatsdaten} hatSpeicher={hatSpeicher} /></div>
      </details>
    </div>
  )
}

/** ⑤ Vergleich: Verwendung der Erzeugung pro Jahr (EV-Quoten-Entwicklung). */
export function BkwVergleichIST({ anlageId, inv }: { anlageId: number; inv?: Investition }) {
  const { ds, loading } = useBkwGeraet(anlageId, inv)
  if (loading) return <Lade />
  if (!ds || ds.monatsdaten.length === 0) return <Leer text="Keine Vergleichsdaten erfasst." />
  return <BkwJahresvergleich monatsdaten={ds.monatsdaten} embed />
}
