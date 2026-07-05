import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Regel-D-Gate (B7/A6, R3b Etappe 3, 2026-07-05): Chart-Tooltips unter src/v4
// laufen über die eedcTooltipProps-Factory (EINE Stelle für Cursor + Content) —
// der Wächter `check-chart-tooltip.mjs` blockt manuelles content={<ChartTooltip
// und Hand-Cursor (belegter Drift: vergessener Cursor → Recharts-Default-Grau).
const FRONTEND_ROOT = process.cwd()

describe('Chart-Tooltip-Factory (Regel D)', () => {
  it('kein manuelles ChartTooltip-Verdrahten in src/v4', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-chart-tooltip.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
