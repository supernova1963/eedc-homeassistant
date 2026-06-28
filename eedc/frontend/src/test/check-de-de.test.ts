import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Drift-Gate (detLAN-Gegencheck 6, 2026-06-28): Der de-DE-Anzeige-Wächter
// (`check-de-de.mjs`: keine rohen .toFixed()/Math.round()-Zahlen, Tausenderpunkt,
// Dezimalkomma, TT.MM.JJJJ, locale-erzwungenes toLocale* — Scope v4 + components
// + die transitiv von dort eingezogenen pages/-Komponenten) läuft jetzt auch als
// Vitest-Test, blockt also in derselben CI-Stufe (`npm test`) wie der Design-
// Wächter. Sonst rutscht eine neue Punkt-statt-Komma-Anzeige unbemerkt durch CI.
// Der npm-Script `check:de-de` bleibt für den manuellen Aufruf bestehen.
const FRONTEND_ROOT = process.cwd()

describe('de-DE-Anzeige-Konformität (Tausenderpunkt/Komma/Datum)', () => {
  it('keine roh formatierten Anzeigen in v4 + components + v4-sichtbaren pages', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-de-de.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
