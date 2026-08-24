import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Einstellungs-Sperre (#391/#393, 2026-08-22): ein roher schreibender `fetch`
// umgeht `api/client.ts` und `api/fetchApi.ts` — er schickt keinen
// Entsperr-Nachweis mit und behandelt keinen 423.
//
// Warum dieser Wrapper (M14, Etappe E8, 2026-08-24): weder Vitest-Wrapper noch
// CI-Schritt. Der Pruefer ist erst zwei Tage alt und haette die Luecke sonst
// von Anfang an mitgebracht — beim Bau waren es 22 solche Aufrufe in sechs
// Dateien, und nichts ausser diesem Waechter haelt den Zustand fest.
const FRONTEND_ROOT = process.cwd()

describe('Einstellungs-Sperre: kein schreibender fetch daran vorbei', () => {
  it('jeder schreibende fetch laeuft ueber client.ts oder fetchApi.ts', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-sperre-fetch.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
