/**
 * Wallbox-Hub-Block (IA v4) — „Wirtschaftlichkeit" (Kostenvergleich Heim vs. extern
 * + ROI + Amortisation). ④ Verlauf (Heimladung/Monat) und ⑤ (Heimladung/Jahr)
 * bleiben generisch (Adapter), da die Wallbox-IMD nur die Heimladungs-Summe je
 * Monat trägt — der PV/Netz-Split ist aggregat (aus E-Auto abgeleitet).
 */
import { useEffect, useState } from 'react'
import { WallboxWirtschaftlichkeit } from '../components/wallbox'
import { investitionenApi, type WallboxDashboardResponse } from '../api/investitionen'
import type { Investition } from '../types'

export function WallboxWirtschaftlichkeitIST({ anlageId, inv }: { anlageId: number; inv?: Investition }) {
  const [ds, setDs] = useState<WallboxDashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let ab = false
    setLoading(true)
    investitionenApi.getWallboxDashboard(anlageId)
      .then((liste) => { if (!ab) setDs(liste.find((d) => d.investition.id === inv?.id) ?? liste[0] ?? null) })
      .catch(() => { if (!ab) setDs(null) })
      .finally(() => { if (!ab) setLoading(false) })
    return () => { ab = true }
  }, [anlageId, inv?.id])

  if (loading) return <p className="text-sm text-gray-400 dark:text-gray-500">Lade…</p>
  if (!ds) return <p className="text-sm text-gray-500 dark:text-gray-400">Keine Wirtschaftlichkeitsdaten erfasst.</p>
  return <WallboxWirtschaftlichkeit zusammenfassung={ds.zusammenfassung} investition={ds.investition} />
}
