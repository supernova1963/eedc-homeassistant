/**
 * useWerteZeitreihe — lädt die Bausteine für die WerteTabelle (monatliche
 * Granularität) und baut die `MonatsZeitreihe[]` über den BESTEHENDEN
 * Cockpit-/Auswertungs-Datenpfad (`createMonatsZeitreihe` mit historisch
 * korrekten Monatstarifen). Gemeinsam genutzt von der /v4-Werkbank und dem
 * Cockpit-Embed, damit die Zeitreihen-Erzeugung nicht doppelt lebt.
 */
import { useMemo } from 'react'
import { monatsdatenApi, type AggregierteMonatsdaten } from '../api/monatsdaten'
import { useApiData, useStrompreise, useAktuellerStrompreis } from '../hooks'
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
  const { strompreise: alleTarife } = useStrompreise(anlageId)
  const { strompreis } = useAktuellerStrompreis(anlageId ?? null)

  // R18-2 (SWR): via Sicht-Cache — beim Sub-Tab-Wechsel stehen die alten Werte
  // sofort (kein Skeleton), still revalidiert.
  const datenQ = useApiData<AggregierteMonatsdaten[]>(
    () => monatsdatenApi.listAggregiert(anlageId!),
    [anlageId],
    { enabled: !!anlageId, swrKey: `v4-werte-zeitreihe:${anlageId}` },
  )
  const daten = useMemo(() => datenQ.data ?? [], [datenQ.data])
  const loading = datenQ.loading
  const error = datenQ.data == null && datenQ.error ? 'Fehler beim Laden der Werte' : null

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
