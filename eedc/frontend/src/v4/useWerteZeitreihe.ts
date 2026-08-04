/**
 * useWerteZeitreihe — baut die `MonatsZeitreihe[]` für die WerteTabelle aus der
 * bereits im Auswertungen-Dispatcher geladenen Basis (`useAuswertungBasis`):
 * aggregierte Monatsdaten. Reine Ableitung über
 * den BESTEHENDEN Datenpfad `createMonatsZeitreihe` — KEINE eigenen Fetches mehr
 * (Paket Q, Doppel-Fetch-Bereinigung:
 * vorher holte der Hook listAggregiert + /strompreise/ + /strompreise/aktuell
 * parallel zur Basis nochmal). Einziger Konsument: AuswertungenTabelleV4.
 *
 * Die CO₂-Spalte kommt seit N-21 (2026-07-31) ebenfalls aus der Basis — als
 * fertiger Wert aus `/cockpit/nachhaltigkeit`, nicht mehr als Client-Formel
 * `erzeugung × 0,38`. Auch das ohne Eigen-Fetch: den Abruf hält der Sockel,
 * geteilt mit der CO₂-Sicht.
 *
 * **Tarif und Tarif-Historie braucht der Hook seit N-22 (2026-08-04) nicht mehr**
 * — die Finanzspalten kommen fertig aus `/monatsdaten/aggregiert`, gerechnet mit
 * demselben SoT wie Cockpit, PDF und HA-Export.
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
export type WerteZeitreiheBasis = Pick<AuswertungBasis, 'daten' | 'loading' | 'error' | 'co2'>

export function useWerteZeitreihe(
  basis: WerteZeitreiheBasis,
  anlage: TabProps['anlage'],
): WerteZeitreiheResult {
  const { daten, loading, co2 } = basis
  // Fehler-Semantik wie zuvor: nur ohne Daten anzeigen (bei Fehl-Revalidierung
  // bleiben die alten Daten stehen — SWR-Verhalten der Basis).
  const error = daten.length === 0 && basis.error ? 'Fehler beim Laden der Werte' : null

  // CO₂-Ausfall lässt die Tabelle stehen: die Spalte zeigt dann „—" (getMonatWert
  // → null), statt die ganze Sicht an einer optionalen Spalte scheitern zu lassen.
  const co2Monate = co2?.monate
  const rows = useMemo(
    () => createMonatsZeitreihe(daten, anlage, co2Monate),
    [daten, anlage, co2Monate],
  )
  const jahre = useMemo(
    () => [...new Set(rows.map((r) => r.jahr))].sort((a, b) => b - a),
    [rows],
  )

  return { rows, jahre, loading, error }
}
