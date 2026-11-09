import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Wächter «Dateilänge» im Client (Päckchen CC Nachlauf N3, 9.11.2026; Datei-Kriterium 900 netto-Codezeilen): keine neue
// Datei über 900, keine Datei der Baseline `dateilaenge-baseline.txt` über Baseline × 1,02, kein verwaister Eintrag (die
// Baseline schrumpft nur). Backend-Schwester: `backend/tests/test_dateilaenge.py`. Wrapper nach dem Muster von
// check-rechenstellen.test.ts — der Prüfer läuft damit in `npm test` (Einhängung M14, check-einhaengung.test.ts).
const FRONTEND_ROOT = process.cwd()

describe('Dateilänge im Client nur aus der Baseline (Datei-Kriterium 900 netto)', () => {
  it('keine neue Datei über 900, kein Wachstum über die Toleranz, keine verwaiste Baseline-Zeile', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-dateilaenge.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
