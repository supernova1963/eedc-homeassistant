/**
 * useWerteZeitreihe — lädt die Bausteine für die WerteTabelle (monatliche
 * Granularität) und baut die `MonatsZeitreihe[]` über den BESTEHENDEN
 * Cockpit-/Auswertungs-Datenpfad (`createMonatsZeitreihe` mit historisch
 * korrekten Monatstarifen). Gemeinsam genutzt von der /v4-Werkbank und dem
 * Cockpit-Embed, damit die Zeitreihen-Erzeugung nicht doppelt lebt.
 */
import { useEffect, useMemo, useState } from 'react'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'
import { useStrompreise, useAktuellerStrompreis } from '../hooks'
import { createMonatsZeitreihe, type MonatsZeitreihe, type TabProps } from '../pages/auswertung/types'

export interface WerteZeitreiheResult {
  rows: MonatsZeitreihe[]
  /** Vorhandene Jahre, absteigend. */
  jahre: number[]
  loading: boolean
  error: string | null
}

export function useWerteZeitreihe(
  anlageId: number | undefined,
  anlage: TabProps['anlage'],
): WerteZeitreiheResult {
  const [daten, setDaten] = useState<AggregierteMonatsdaten[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const { strompreise: alleTarife } = useStrompreise(anlageId)
  const { strompreis } = useAktuellerStrompreis(anlageId ?? null)

  useEffect(() => {
    if (!anlageId) return
    let abgebrochen = false
    setLoading(true)
    setError(null)
    monatsdatenApi
      .listAggregiert(anlageId)
      .then((d) => { if (!abgebrochen) setDaten(d) })
      .catch(() => { if (!abgebrochen) setError('Fehler beim Laden der Werte') })
      .finally(() => { if (!abgebrochen) setLoading(false) })
    return () => { abgebrochen = true }
  }, [anlageId])

  const rows = useMemo(
    () => createMonatsZeitreihe(daten, anlage, strompreis, alleTarife),
    [daten, anlage, strompreis, alleTarife],
  )
  const jahre = useMemo(
    () => [...new Set(rows.map((r) => r.jahr))].sort((a, b) => b - a),
    [rows],
  )

  return { rows, jahre, loading, error }
}
