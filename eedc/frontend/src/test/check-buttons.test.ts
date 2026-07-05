import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// B15-Gate (R3b Etappe 2, 2026-07-05): keine Ad-hoc-<button> in src/v4 — Aktions-
// Buttons über ui/Button, Segment-Gruppen über ui/SegmentControl, Schalter über
// ui/Switch, Reload über v4/ReloadButton. Der Wächter `check-buttons.mjs` friert
// den belegten Rest-Bestand (Player-Controls, Rails, Chips …) mit exakter
// Treffer-Zahl ein; jede Abweichung (neu ODER Abbau) muss die Allowlist anfassen.
const FRONTEND_ROOT = process.cwd()

describe('Button-SoT (B15: keine Ad-hoc-<button> in v4)', () => {
  it('rohe <button>-Vorkommen exakt auf Allowlist-Stand', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-buttons.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
