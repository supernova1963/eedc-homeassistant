import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// B6/S9-Gate (R3b Etappe 3, 2026-07-05): Sub-Block-Disclosure per nativem
// <details> trägt EINEN Stil-Kanon (border-t gray-100 pt-3 + Summary-Klassen +
// „… anzeigen ({N})"-Formel, bewusst ohne Persistenz). Der Wächter
// `check-details.mjs` prüft src/v4 + V4-geteilte Dateien per Token-SET-Vergleich.
const FRONTEND_ROOT = process.cwd()

describe('Details-Disclosure-Kanon (B6/S9)', () => {
  it('alle <details>/<summary> im Scope folgen dem Kanon', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-details.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
