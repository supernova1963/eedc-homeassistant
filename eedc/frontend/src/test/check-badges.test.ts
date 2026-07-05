import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// B17-Gate (R3b Etappe 1, 2026-07-05): Badges/Chips/Pills = rounded-full|lg,
// dezente Tönung bg-{c}-50 dark:bg-{c}-900/20 (Grau: dark:bg-gray-700), kein
// ALL-CAPS. Der Wächter `check-badges.mjs` (Badge-Kapsel-Heuristik px+py-0.5|1,
// <button>-Kapseln = B15-Domäne ausgenommen, Allowlist mit Treffer-Zahl) läuft
// auch als Vitest-Test, damit er in derselben CI-Stufe blockt wie die übrigen Wächter.
const FRONTEND_ROOT = process.cwd()

describe('Badge-Konformität (B17: Form, Tönung, Casing)', () => {
  it('keine B17-Badge-Verstöße außerhalb der Allowlist', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-badges.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
