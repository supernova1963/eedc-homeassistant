import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Regel 0a, repo-weiter Roh-Control-Freeze: rohe Controls nur als freigegebene
// SoT-/Infra-Implementierung. Nachfolger des mit dem v4.0.0-Flip stillgelegten
// `check:v4-migration` (Teil 3).
//
// Warum dieser Wrapper (M14, Etappe E8, 2026-08-24): `check:roh-controls` lief
// als EIGENER CI-Schritt, aber in keinem Vitest-Lauf. Das ist die Gegenrichtung
// des `lint`-Befunds vom 12.08. — ein Pruefer, den nur CI kennt, meldet erst
// NACH dem Push und ordnet den Fehler keinem einzelnen Commit mehr zu. Mit
// diesem Wrapper laeuft er lokal ueber `npm test` mit; der eigene CI-Schritt
// entfaellt dafuer (E8/M14: eine Einhaengung, nicht zwei).
const FRONTEND_ROOT = process.cwd()

describe('Roh-Control-Freeze repo-weit (Regel 0a)', () => {
  it('kein rohes Control ausserhalb der SoT-/Infra-Freigaben', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-roh-controls.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
