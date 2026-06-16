/**
 * Delta-Bewertung (Vergleich cur vs. cmp): ist die Veränderung „gut", „schlecht"
 * oder „neutral"? Richtungslogik aus `TabelleTab.DeltaCell` herausgelöst, damit
 * die Färbung an einer Stelle definiert ist (P2-Ampel-Geist).
 *
 * - `higherIsBetter === undefined` → neutral außer bei exakt 0 (== neutral).
 * - sonst: Anstieg gut, wenn höher besser; Rückgang gut, wenn niedriger besser.
 */
export type DeltaUrteil = 'gut' | 'schlecht' | 'neutral'

export function bewerteDelta(
  current: number | null,
  prev: number | null,
  higherIsBetter?: boolean,
): DeltaUrteil {
  if (current == null || prev == null) return 'neutral'
  const delta = current - prev
  if (delta === 0) return 'neutral'
  if (higherIsBetter === undefined) return 'neutral'
  const positiv = delta > 0
  const gut = higherIsBetter ? positiv : !positiv
  return gut ? 'gut' : 'schlecht'
}
