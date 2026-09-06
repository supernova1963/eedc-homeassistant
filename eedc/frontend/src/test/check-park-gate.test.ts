import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Element-Park-Doktrin, Haelfte 3 — das AUTO-HIDE-GATE (2026-09-06).
//
// Parkt der Anwender ALLE Elemente eines Blocks, muss der Block verschwinden.
// Bis zu diesem Tag hing diese Haelfte allein am `check:park-leertest`
// (Playwright gegen eine laufende Demo-Box, 188 s, kein CI-Lauf, nur am
// Ausloeser). Der meldete am 06.09. gruen ueber ein Park-Element, das er nie
// gesehen hatte — seine Routen-Liste kannte eine von sechs Community-Sichten,
// waehrend 12 der 17 Auto-Hide-Dateien dort liegen. Entscheid Gernot: ersetzen.
//
// Beim ERSTEN Lauf hat der Waechter einen toten Block ohne Gate gefunden
// (`MonatRahmen::communityBlock`, seit dem 20.06. ohne Aufrufer) — er sieht also
// etwas, und er sieht es baumweit statt auf 18 gepflegten Routen.
const FRONTEND_ROOT = process.cwd()

describe('Element-Park-Doktrin: Auto-Hide-Gate', () => {
  it('jeder Block und jede Huelle mit parkbaren Elementen verschwindet bei Voll-Park', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-park-gate.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
