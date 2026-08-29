import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// N-149 (KONZEPT-MOBILE §M3): Die Mobil-Kartenliste hat genau EINEN Bauort,
// `components/ui/MobilKarte.tsx`. Der Wächter `check-mobilkarte.mjs` läuft auch
// als Vitest-Test, damit er in derselben CI-Stufe (`npm test`) blockt wie die
// übrigen Konformitäts-Wächter — und damit `check-einhaengung` ihn findet.
//
// Der Fund ist entstanden, weil das Muster viermal im Baum stand und niemand es
// bemerkte; sein Trigger heißt wörtlich „die fünfte Stelle". Genau die soll hier
// auffallen, bevor sie eingecheckt ist.
const FRONTEND_ROOT = process.cwd()

describe('Mobil-Karte hat einen Bauort (N-149)', () => {
  it('keine handgebaute Kartenliste neben dem SoT', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-mobilkarte.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
