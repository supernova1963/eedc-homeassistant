import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Drift-Gate (detLAN-Gegencheck 6, 2026-06-28): Der Achsen-Wächter
// (`check-achsen.mjs`: jede Wert-Achse trägt genau eine Einheit + de-DE
// tickFormatter) läuft jetzt auch als Vitest-Test — damit er in derselben
// CI-Stufe (`npm test`) blockt wie der Design-Wächter, statt nur manuell
// aufrufbar zu sein. Sonst kann eine neue Achse ohne Einheit/de-DE-Tick
// unbemerkt durch CI rutschen (genau die Klasse, gegen die R27 absichert).
// Der npm-Script `check:achsen` bleibt für den manuellen Aufruf bestehen.
const FRONTEND_ROOT = process.cwd()

describe('Achsen-Konformität (Einheit + de-DE tickFormatter)', () => {
  it('alle Wert-Achsen tragen genau eine Einheit + de-DE Tick', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-achsen.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
