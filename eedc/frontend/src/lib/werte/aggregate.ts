/**
 * Footer-Aggregation der Werte-Tabelle: pro Metrik Summe (`sum`) oder
 * Durchschnitt (`avg`); `none` → null. null-Werte werden übersprungen, leere
 * Spalte → null. Verhaltensgleich aus `TabelleTab.aggregateRows`.
 */
import type { MonatsZeitreihe } from '../../pages/auswertung/types'
import { WERTE_METRIKEN, getMonatWert } from './registry'

export function aggregiere(rows: MonatsZeitreihe[]): Record<string, number | null> {
  const result: Record<string, number | null> = {}
  for (const m of WERTE_METRIKEN) {
    const vals = rows
      .map((r) => getMonatWert(r, m.key))
      .filter((v): v is number => v != null)
    if (vals.length === 0) {
      result[m.key] = null
      continue
    }
    if (m.aggregation === 'sum') result[m.key] = vals.reduce((s, v) => s + v, 0)
    else if (m.aggregation === 'avg') result[m.key] = vals.reduce((s, v) => s + v, 0) / vals.length
    else result[m.key] = null
  }
  return result
}
