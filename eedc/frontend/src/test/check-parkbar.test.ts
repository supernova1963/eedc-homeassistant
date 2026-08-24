import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Element-Park-Doktrin, Haelfte 1 — ATOMARITAET (Gernot 2026-07-09): EINE
// `<Parkbar>` umhuellt GENAU EINE atomare Anzeige, nie ein Buendel. Da
// „ist das Kind atomar?" nicht grep-bar ist, arbeitet der Pruefer als
// Allowlist-Tripwire ueber `scripts/parkbar-allowlist.json`.
//
// Warum dieser Wrapper (M14, Etappe E8, 2026-08-24): weder Vitest-Wrapper noch
// CI-Schritt — er lief nur in der Liste in `CLAUDE.md`. Das wiegt hier doppelt,
// weil der teuerste Park-Pruefer (`check:park-leertest`, 188 s) seit dem 23.08.
// bewusst NUR am Ausloeser laeuft; die beiden Quelltext-Waechter sind damit die
// staendige Deckung der Doktrin und duerfen nicht am Gedaechtnis haengen.
const FRONTEND_ROOT = process.cwd()

describe('Element-Park-Doktrin: Atomaritaet', () => {
  it('keine unbestaetigte Parkbar-Umhuellung (kein Composite-Buendel)', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-parkbar.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
