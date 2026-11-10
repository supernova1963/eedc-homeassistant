import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Wächter W-10 «Eine Mechanik» (Etappe E3 Daten-Checker, Bauplan §4): der Daten-Checker (`pages/DatenCheckerTeile.tsx`,
// `components/datenchecker/BefundHandgriff.tsx`) ruft keine Wrapper-Route und kein `window.confirm` — jede Aktion geht
// über `repairApi.plan` → Vorschau → `repairApi.execute`. Wrapper nach dem Muster von check-dateilaenge.test.ts — der
// Prüfer läuft damit in `npm test` (Einhängung M14, check-einhaengung.test.ts).
const FRONTEND_ROOT = process.cwd()

describe('Daten-Checker: eine Mechanik für jede Aktion (W-10)', () => {
  it('kein direkter Wrapper-Aufruf in Seite und Zeile', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-eine-mechanik.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
