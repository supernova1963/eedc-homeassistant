import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Client-Hälfte von ADR-001/DI-2 (N-21): `berechne_co2_bilanz` ist die einzige
// Konstruktions-Stelle einer CO₂-Menge (Eigenverbrauch × Strommix + WP + E-Mob);
// der Client liest sie aus `/cockpit/nachhaltigkeit` und rechnet nicht selbst.
// `CO2_FAKTOR_KG_KWH` darf nur noch *angezeigt* werden.
//
// Warum dieser Wrapper (M2, Etappe E1, 2026-08-23): `check:co2-roh` stand in
// package.json, hatte aber als einziger der beiden Backend-Regel-Wächter
// keinen Vitest-Wrapper — es lief damit **nirgends automatisch**, weder in CI
// noch im lokalen Testlauf. Ein Prüfer, den nur eine Doku-Liste kennt, ist eine
// Gedächtnisstütze und kein Wächter (dieselbe Klasse wie der `lint`-Befund vom
// 12.08. und die CI-only-Routenschwelle M1).
const FRONTEND_ROOT = process.cwd()

describe('CO₂-Mengen nur aus dem Backend (ADR-001/DI-2)', () => {
  it('kein Client-Code rechnet mit CO2_FAKTOR_KG_KWH', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-co2-roh.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
