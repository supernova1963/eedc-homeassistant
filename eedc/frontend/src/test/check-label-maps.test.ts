import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Regel-0/S7-Gate (R3b Etappe 2, 2026-07-05): Enum→Label-Maps (Provenance,
// Sonstiges-Kategorie) und Wochentagsnamen leben EINMAL in lib/constants.ts —
// der Wächter `check-label-maps.mjs` blockt lokale Neu-Kopien der
// zentralisierten Vokabulare (Drift-Belege: Roh-Enums in der UI, drei
// Wochentags-Index-Semantiken).
const FRONTEND_ROOT = process.cwd()

describe('Label-Map-SoT (Regel 0: keine lokalen Vokabular-Kopien)', () => {
  it('keine Wochentags-/Kategorie-/Provenance-Map außerhalb lib/constants', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-label-maps.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
