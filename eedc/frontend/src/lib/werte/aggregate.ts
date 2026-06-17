/**
 * Footer-Aggregation der Werte-Tabelle: pro Metrik Summe (`sum`) oder
 * Durchschnitt (`avg`); `none` → null. null-Werte werden übersprungen, leere
 * Spalte → null. Verhaltensgleich aus `TabelleTab.aggregateRows`, jetzt
 * granularitäts-agnostisch über `WerteZeile`.
 */
import type { WerteMetrik } from './registry'
import type { WerteZeile } from './zeile'

export function aggregiere(
  rows: WerteZeile[],
  metriken: WerteMetrik[],
): Record<string, number | null> {
  const result: Record<string, number | null> = {}
  for (const m of metriken) {
    const vals = rows
      .map((r) => r.wert(m.key))
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
