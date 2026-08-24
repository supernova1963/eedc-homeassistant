import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Element-Park-Doktrin, Haelfte 2 — VOLLSTAENDIGKEIT: jede Anzeige in einer
// Park-Sicht IST parkbar. `check:parkbar` sieht eine FEHLENDE Parkbar
// prinzipiell nicht (er prueft nur vorhandene) — genau dort rutschten
// un-parkbare Anzeigen durch.
//
// Warum dieser Wrapper (M14, Etappe E8, 2026-08-24): wie die Schwester daneben
// lief er weder in Vitest noch in CI. Begruendung dort.
const FRONTEND_ROOT = process.cwd()

describe('Element-Park-Doktrin: Vollstaendigkeit', () => {
  it('keine un-parkbare Anzeige in einer Park-Sicht', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-parkbar-vollstaendig.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
