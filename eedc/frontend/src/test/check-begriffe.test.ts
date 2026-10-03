import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// N-603 — Anzeigetexte sagen „Gesamtverbrauch" oder „Restverbrauch", nie „Hausverbrauch" (Paket „Begriffe",
// 03.10.2026). Backend-Hälfte: `backend/tests/test_begriffe_anwendertexte.py`.
const FRONTEND_ROOT = process.cwd()

describe('Begriffe Verbrauch (N-603)', () => {
  it('kein „Hausverbrauch", „Haushalt" nur in den klassifizierten Ausnahmen', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-begriffe.mjs'], { cwd: FRONTEND_ROOT, stdio: 'pipe' }),
    ).not.toThrow()
  })
})
