import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// B17/A5-Gate (R3b Etappe 1, 2026-07-05): Status-Icons kommen aus STATUS_ICONS
// (lib/komponentenStyle.ts) als EINER Quelle. Der Wächter `check-status-icons.mjs`
// blockt Direkt-Importe der Kanon-Icons + bekannter Drift-Varianten (CheckCircle2/
// AlertCircle/Sparkles) aus lucide-react unter src/v4/** + geteilten Dateien.
// Dekorative Nicht-Status-Verwendung → Allowlist.
const FRONTEND_ROOT = process.cwd()

describe('Status-Icon-SoT (B17/A5: STATUS_ICONS als eine Quelle)', () => {
  it('keine Status-Icon-Direkt-Importe außerhalb der Allowlist', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-status-icons.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
