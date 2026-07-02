import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// „V4 verlinkt V3 NIE"-Gate (Gernot-Fund 2026-07-02): der Wächter
// `check-v4links.mjs` (kein `#/…`-Hash-Link-Literal unter src/v4/, das nicht auf
// eine `/v4/*`-Route zeigt) läuft auch als Vitest-Test — damit er in derselben
// CI-Stufe (`npm test`) blockt wie die Design-/Achsen-/DatumPicker-Wächter. Er
// fängt genau den Blind-Spot, den die manuelle navigate-Inventur übersah: Links
// über Konstanten (`href={EDIT_INFOTHEK}`) statt `href="#/…"`-Literale.
const FRONTEND_ROOT = process.cwd()

describe('V4-Link-Konformität (keine V4→V3-Hash-Links in v4/)', () => {
  it('alle v4-internen Hash-Links zeigen auf /v4/-Routen', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-v4links.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
