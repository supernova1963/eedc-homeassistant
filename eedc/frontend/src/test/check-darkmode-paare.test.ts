import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// A8-Gate (R3b Etappe 1, 2026-07-05): die Muted-Paarungen text-gray-500 →
// dark:text-gray-400 und text-gray-400 → dark:text-gray-500 sind verbindlich.
// Der Wächter `check-darkmode-paare.mjs` prüft className-Literale UND farbe-Props
// (BlockShell/FokusVollbild-Pfad) unter src/v4/** + V4-genutzten geteilten Dateien;
// Kontroll-Icon-Konvention ist per Allowlist eingefroren (Entscheid-Kandidat E6).
const FRONTEND_ROOT = process.cwd()

describe('Dark-Mode-Paarungen (A8: Muted-Text/Icons)', () => {
  it('keine ungepaarten text-gray-400/500 außerhalb der Allowlist', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-darkmode-paare.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
