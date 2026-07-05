import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// B8-Gate (R3b S15-Slice, 2026-07-05): Erst-Loads = Skeleton (ui/Skeleton,
// BlockStackSkeleton), Fehler = ui/FehlerZustand, Onboarding-Leer = v4/
// OnboardingLeer. Der Wächter `check-b8.mjs` friert den legitimen Restbestand
// (Suspense-Fallback, S11-Live-Ausnahme, Klasse-(c)-Leercards) mit exakter
// Treffer-Zahl ein; jede Abweichung (neu ODER Abbau) muss die Allowlist anfassen.
const FRONTEND_ROOT = process.cwd()

describe('B8-Zustände (S15: Skeleton/FehlerZustand/OnboardingLeer)', () => {
  it('Lade-/Fehler-/Leer-Zustände in src/v4 exakt auf Allowlist-Stand', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-b8.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
