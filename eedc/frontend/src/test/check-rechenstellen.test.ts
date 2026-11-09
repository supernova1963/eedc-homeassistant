import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Wächter «Rechenstellen» im Client (Päckchen Z3, 9.11.2026; ADR-001 «eine Formel, ein Ort»): kein neuer
// Rechenausdruck der Gestalten E/E · E-E · E*G · E*L · E/P · G/E in Sichten und Hooks außerhalb der Baseline
// `rechenstellen-baseline.txt`, die nur schrumpft (ein verwaister Eintrag ist ebenfalls rot). Backend-Schwester:
// `backend/tests/test_dezentrale_rechenstellen.py`. Wrapper nach dem Muster von check-co2-roh.test.ts — der Prüfer
// läuft damit in `npm test` (Einhängung M14, check-einhaengung.test.ts).
const FRONTEND_ROOT = process.cwd()

describe('Rechenstellen im Client nur aus der Baseline (ADR-001)', () => {
  it('keine neue Client-Rechnung, keine verwaiste Baseline-Zeile', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-rechenstellen.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
