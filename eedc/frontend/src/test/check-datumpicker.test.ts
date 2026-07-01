import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Drift-Gate (Slice A, D13-4/9/11/12, detLAN #105/#106/#107): Der DatumPicker-
// Wächter (`check-datumpicker.mjs`: kein natives <input type=date|month> unter
// src/v4/, dort ist der DatumPicker-SoT Pflicht) läuft auch als Vitest-Test —
// damit er in derselben CI-Stufe (`npm test`) blockt wie Design-/Achsen-Wächter.
// Sonst kann eine neue V4-Sicht wieder ein native Datumsfeld einführen und die
// zwei-Picker-Welten (Icon-/Stil-Drift), gegen die Slice A absichert, kehren
// unbemerkt zurück. Der npm-Script `check:datumpicker` bleibt manuell nutzbar.
const FRONTEND_ROOT = process.cwd()

describe('DatumPicker-Konformität (kein natives date/month in v4/)', () => {
  it('alle IA-V4 Datums-/Monatsfelder nutzen den DatumPicker-SoT', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-datumpicker.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
