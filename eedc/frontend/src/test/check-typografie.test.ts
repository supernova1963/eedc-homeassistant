import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// A1-Gate (R3b Etappe 1, 2026-07-05): Typografie bleibt auf der 9-Stufen-Skala
// (+ v4-Zusatz-Zeilen titel-sicht/titel-block/micro). Der Wächter
// `check-typografie.mjs` blockt text-4xl+, text-xl und arbiträre Pixel-Größen
// außer 10/11 px unter src/v4/** + V4-genutzten geteilten Dateien.
const FRONTEND_ROOT = process.cwd()

describe('Typografie-Skala (A1)', () => {
  it('keine Klassen oberhalb/außerhalb der Skala außerhalb der Allowlist', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-typografie.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
