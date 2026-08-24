import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Style-Guide Teil D / M1: In `src/components/forms/**` (rekursiv) sind die
// SoT-Controls Pflicht — keine rohen `<select>`/`<textarea>`/`<input>`/`<label>`.
//
// Warum dieser Wrapper (M14, Etappe E8, 2026-08-24): `check:form-controls` stand
// in package.json, hatte KEINEN Vitest-Wrapper und KEINEN CI-Schritt — er lief
// damit ausschliesslich in der handgefuehrten Liste in `CLAUDE.md`. Ein Pruefer,
// den nur eine Doku-Liste kennt, ist eine Gedaechtnisstuetze und kein Waechter;
// dieselbe Klasse wie der `lint`-Befund vom 12.08. und die CI-only-Routenschwelle
// (M1). Von den 27 `check:*` traf das am 24.08. auf VIER zu — die drei anderen
// stehen daneben.
//
// Die dokumentierte Baseline „1 noch offen (WelcomeStep.tsx)" traegt das Skript
// selbst; sie faerbt den Exit-Code nicht. Waechst sie, wird dieser Fall rot.
const FRONTEND_ROOT = process.cwd()

describe('Formular-Controls nur als SoT-Komponente (Style-Guide D/M1)', () => {
  it('keine rohen Primitive in den migrierten components/forms/**', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-form-controls.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
