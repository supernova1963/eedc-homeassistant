import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Drift-Gate: der Chart-SoT-Wächter (`check-charts.mjs`: R1 Pie nur über
// AnteilDonut, R2 Legenden über ChartLegende, R3 Y-Achsen-Breite aus der
// Zentrale statt Recharts-Default 60 — D18-3, detlan #210) läuft auch als
// Vitest-Test, damit er in derselben CI-Stufe (`npm test`) blockt wie der
// Design-Wächter. Der npm-Script `check:charts` bleibt für den manuellen Aufruf.
const FRONTEND_ROOT = process.cwd()

describe('Chart-SoT-Konformität (Pie-SoT + ChartLegende + Y-Achsen-Breite)', () => {
  it('R1–R3 halten (Hand-Pies, rohe Legenden, YAxis ohne Breite = Verstoß)', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-charts.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
