import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// A9-Gate (Regel-Paket 2026-07-03): Überlauf zeigt ScrollSchatten-Fade statt
// Scroll-Balken. Der Wächter `check-scrollschatten.mjs` (roher `overflow-*-auto`
// unter src/v4/** + geteilten SoT-Komponenten, Allowlist = dokumentierte
// Seiten-/Sicht-Scroller) läuft auch als Vitest-Test, damit er in derselben
// CI-Stufe (`npm test`) blockt wie Design-/Achsen-/DatumPicker-/v4links-Wächter.
const FRONTEND_ROOT = process.cwd()

describe('ScrollSchatten-Konformität (A9: Fade statt Scroll-Balken)', () => {
  it('kein roher overflow-auto außerhalb der Allowlist', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-scrollschatten.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
