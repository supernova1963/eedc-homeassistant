import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { REPARATUR_AENDERUNG_LABELS } from '../lib/constants'

/**
 * Die Reparatur-Werkbank beschriftet ihre Zähler auf Deutsch (Regel 0a).
 *
 * Belegter Gegenfall: Knallfrosch (Forum simon42 T89667 #304) schickte einen
 * Screenshot der Plan-Vorschau, auf dem „0 boundaries_changed · 0 slots_changed
 * · 0 counter_fields_changed" stand — die rohen Schlüssel des Backends, mitten
 * in einer sonst deutschen Oberfläche.
 *
 * Zwei Hälften, hier beide geprüft:
 *   1. Die Map deckt die Schlüssel ab, die das Backend liefert. Dass es genau
 *      diese drei sind, hält `test_repair_orchestrator.py` fest.
 *   2. Die Werkbank rendert keinen Schlüssel mehr roh, sondern über
 *      `aenderungLabel` — sonst wäre die Map da und würde nicht benutzt.
 */
const WERKBANK = join(
  process.cwd(), 'src', 'components', 'repair', 'RepairWorkbench.tsx',
)

/** Der Vertrag mit `repair_orchestrator._plan_reaggregate_day`. */
const BACKEND_SCHLUESSEL = [
  'boundaries_changed', 'slots_changed', 'counter_fields_changed',
]

describe('Reparatur-Werkbank: die Zähler tragen deutsche Namen', () => {
  it('die Label-Map deckt jeden Schlüssel des Backends ab', () => {
    for (const key of BACKEND_SCHLUESSEL) {
      expect(REPARATUR_AENDERUNG_LABELS[key], `kein Label für ${key}`).toBeTruthy()
      expect(REPARATUR_AENDERUNG_LABELS[key]).not.toContain('_')
    }
  })

  it('die Werkbank rendert keinen Schlüssel mehr roh', () => {
    const quelle = readFileSync(WERKBANK, 'utf8')
    // Die drei Rendering-Stellen liefen über `{k}` bzw. `{key}` direkt hinter
    // dem Zahlwert. Genau diese Form darf nicht zurückkommen.
    const roh = /<\/strong>\s*\{k(?:ey)?\}/.test(quelle)
    expect(roh, 'RepairWorkbench rendert einen Zähler-Schlüssel wieder roh').toBe(false)
    expect(quelle).toContain('aenderungLabel(k)')
  })
})
