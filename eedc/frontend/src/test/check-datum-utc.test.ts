import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// F-5 (rapahl, 06.08.2026): `toISOString().slice(0,10)` serialisiert in UTC —
// zwischen 00:00 und 02:00 Ortszeit ist das noch gestern, während das Backend
// mit `date.today()` rechnet. Datums-Keys kommen aus `src/lib/datum.ts`
// (`heuteIso` / `toIsoDatum` / `verschiebeIsoTage`).
//
// Warum dieser Wrapper (M2, Etappe E1, 2026-08-23): `check:datum-utc` stand in
// package.json und lief **nirgends automatisch** — dasselbe Loch wie bei
// `check:co2-roh` daneben. Gerade dieser Prüfer bewacht einen Fehler, der nur
// in zwei Nachtstunden sichtbar wird; auf einen erinnerten Aufruf ist er
// besonders schlecht angewiesen.
const FRONTEND_ROOT = process.cwd()

describe('Datums-Keys aus der lokalen Uhr, nicht aus UTC (F-5)', () => {
  it('kein toISOString()-Datums-Key außerhalb der Allowlist', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-datum-utc.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
