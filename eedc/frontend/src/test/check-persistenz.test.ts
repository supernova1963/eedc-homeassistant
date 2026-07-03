import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// C4-Gate (Regel-Paket 2026-07-03): Persistenz nur über SoT-Module, Keys nach
// `eedc-<bereich>`-Schema. Der Wächter `check-persistenz.mjs` friert den
// localStorage-Bestand ein (Datei → Treffer-Anzahl) — jede neue Streu-Persistenz
// schlägt in derselben CI-Stufe (`npm test`) an wie die übrigen Wächter.
const FRONTEND_ROOT = process.cwd()

describe('Persistenz-Konformität (C4: localStorage nur SoT/eingefroren)', () => {
  it('kein neuer direkter localStorage-Zugriff außerhalb der SoT-Module', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-persistenz.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
