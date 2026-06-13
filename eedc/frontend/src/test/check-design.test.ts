import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// E1-P3 Teil 0: Der Konformitäts-Wächter (P1, keine Inline-Hex außerhalb
// lib/colors.ts) läuft jetzt auch als Vitest-Test — damit er in derselben
// Suite/CI-Stufe blockt wie die Routing-/Komponenten-Tests (ersetzt den
// verworfenen „A0-Token-Integrationstest"). Der npm-Script `check:design`
// bleibt für den manuellen Aufruf bestehen; hier wird exakt dasselbe Skript
// ausgeführt und auf Exit-Code 0 geprüft. Vitest läuft im Frontend-Root.
const FRONTEND_ROOT = process.cwd()

describe('Design-Konformität (Inline-Hex-Wächter)', () => {
  it('findet keine Inline-Hex-Farben außerhalb der Farb-Zentrale', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-design-konformitaet.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
