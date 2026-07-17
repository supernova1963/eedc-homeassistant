/**
 * useWerteZeitreihe — baut die `MonatsZeitreihe[]` für die WerteTabelle aus der
 * bereits im Auswertungen-Dispatcher geladenen Basis (`useAuswertungBasis`):
 * aggregierte Monatsdaten + Strompreis + Tarif-Historie. Reine Ableitung über
 * den BESTEHENDEN Datenpfad `createMonatsZeitreihe` (historisch korrekte
 * Monatstarife) — KEINE eigenen Fetches mehr (Paket Q, Doppel-Fetch-Bereinigung:
 * vorher holte der Hook listAggregiert + /strompreise/ + /strompreise/aktuell
 * parallel zur Basis nochmal). Einziger Konsument: AuswertungenTabelleV4.
 */
import { useMemo } from 'react'
import { createMonatsZeitreihe, type MonatsZeitreihe, type TabProps } from '../pages/auswertung/types'
import type { AuswertungBasis } from './useAuswertungBasis'

export interface WerteZeitreiheResult {
  rows: MonatsZeitreihe[]
  /** Vorhandene Jahre, absteigend. */
  jahre: number[]
  loading: boolean
  error: string | null
}

/** Basis-Ausschnitt, den die Ableitung braucht (Prop-Typ des Dispatchers). */
export type WerteZeitreiheBasis = Pick<AuswertungBasis, 'daten' | 'strompreis' | 'alleTarife' | 'loading' | 'error'>

export function useWerteZeitreihe(
  basis: WerteZeitreiheBasis,
  anlage: TabProps['anlage'],
): WerteZeitreiheResult {
  const { daten, strompreis, alleTarife, loading } = basis
  // Fehler-Semantik wie zuvor: nur ohne Daten anzeigen (bei Fehl-Revalidierung
  // bleiben die alten Daten stehen — SWR-Verhalten der Basis).
  const error = daten.length === 0 && basis.error ? 'Fehler beim Laden der Werte' : null

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
