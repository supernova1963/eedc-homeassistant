import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Migrations-Freeze-Gate (PLAN-V4-MAENGELBEHEBUNG.md Paket W, 2026-07-11):
// Registry-Klassifikation (migriert/offen), navigate→V3-Kanten und rohe
// Controls über den V4-erreichbaren Datei-Kreis (Katalog-Teile + Wizard-
// Registry + src/v4 + §H-Composites) sind exakt eingefroren. Jede Abweichung
// (neuer Verstoß ODER Abbau durch Migration) muss die Freeze-Listen im
// Wächter anfassen — die schrumpfenden Listen SIND die Rest-Arbeitsliste.
const FRONTEND_ROOT = process.cwd()

describe('V4-Migrations-Freeze (Paket W: Registry + navigate→V3 + Roh-Controls)', () => {
  it('Migrationsstand exakt auf Freeze-Stand', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-v4-migration.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
