/**
 * Speicher-Hub-Blöcke (IA v4) — ④ Verlauf + ⑤ Vergleich des Speicher-Typs.
 * Holen das IST-Speicher-Dashboard (self-fetch über anlageId), wählen das im Hub
 * aktive Gerät (`inv`) und rendern die geteilten IST-Komponenten
 * ({@link SpeicherVerlaufCharts} / {@link SpeicherJahresbilanz}) — „Umbau, keine
 * Verschlechterung". Ein gemeinsamer Fetch-Hook hält die Lade-Logik DRY.
 */
import { useEffect, useState } from 'react'
import { SpeicherVerlaufCharts, SpeicherJahresbilanz } from '../components/speicher'
import { investitionenApi, type SpeicherDashboardResponse } from '../api/investitionen'
import type { Investition } from '../types'

/** Lädt das Speicher-Dashboard + wählt das aktive Gerät (sonst das erste). */
function useSpeicherGeraet(anlageId: number, inv?: Investition) {
  const [ds, setDs] = useState<SpeicherDashboardResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let ab = false
    setLoading(true)
    investitionenApi.getSpeicherDashboard(anlageId)
      .then((liste) => {
        if (ab) return
        setDs(liste.find((d) => d.investition.id === inv?.id) ?? liste[0] ?? null)
      })
      .catch(() => { if (!ab) setDs(null) })
      .finally(() => { if (!ab) setLoading(false) })
    return () => { ab = true }
  }, [anlageId, inv?.id])

  return { ds, loading }
}

function Lade() {
  return <p className="text-sm text-gray-400 dark:text-gray-500">Lade…</p>
}
function Leer({ text }: { text: string }) {
  return <p className="text-sm text-gray-500 dark:text-gray-400">{text}</p>
}

/** Block ④ Verlauf: 3 IST-Charts (η-12M, Vollzyklen, Ladung/Entladung+Arbitrage) + Tabelle. */
export function SpeicherVerlaufIST({ anlageId, inv }: { anlageId: number; inv?: Investition }) {
  const { ds, loading } = useSpeicherGeraet(anlageId, inv)
  if (loading) return <Lade />
  if (!ds || ds.monatsdaten.length === 0) return <Leer text="Keine Verlaufsdaten erfasst." />
  return (
    <SpeicherVerlaufCharts
      monatsdaten={ds.monatsdaten}
      zusammenfassung={ds.zusammenfassung}
      effizienzVerlauf={ds.effizienz_verlauf}
      embed
    />
  )
}

/** Block ⑤ Vergleich: Jahresbilanz (Ladung nach Herkunft ⟷ Entladung + Verlust). */
export function SpeicherVergleichIST({ anlageId, inv }: { anlageId: number; inv?: Investition }) {
  const { ds, loading } = useSpeicherGeraet(anlageId, inv)
  if (loading) return <Lade />
  if (!ds || ds.monatsdaten.length === 0) return <Leer text="Keine Jahresdaten erfasst." />
  return <SpeicherJahresbilanz monatsdaten={ds.monatsdaten} embed />
}
