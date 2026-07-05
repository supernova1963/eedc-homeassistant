import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// B2-Gate (R3b Etappe 2, 2026-07-05): Tabellen-Header tragen die Kanon-Farbe
// text-gray-500 dark:text-gray-400 (nicht die gedrehte hellere Paarung, S13)
// und Einheiten im Header stehen in RUNDEN Klammern „Name (Einheit)" (B2/#237).
// Scope: src/v4 + V4-geteilte Tabellen-SoTs + IASkeleton (Preview-SoT).
const FRONTEND_ROOT = process.cwd()

describe('Tabellen-Konventionen (B2: Header-Farbe + Einheiten-Klammern)', () => {
  it('keine gedrehten Header-Grau-Paare und keine eckigen Einheiten-Klammern', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-tabellen.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
