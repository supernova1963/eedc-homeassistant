/**
 * W-5/W-3 (Etappe E5): der Client bildet den Pfad eines Sprung-Ziels wie das Backend (`link_aus_ziel`) — jedes Ziel des
 * Exports `backend/tests/fixtures/sprungziele.json` (Abschnitt `pfade`, aus den Ziel-Bauern erzeugt) ergibt denselben Pfad.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import type { CheckZiel } from '../api/datenChecker'
import { zielPfad } from './zielPfad'

const EXPORT = JSON.parse(readFileSync(join(__dirname, '../../../backend/tests/fixtures/sprungziele.json'), 'utf8')) as {
  pfade: { ziel: CheckZiel; pfad: string }[]
}

describe('zielPfad', () => {
  it('bildet jeden Pfad des Backend-Exports', () => {
    expect(EXPORT.pfade.length).toBeGreaterThan(50)
    for (const { ziel, pfad } of EXPORT.pfade) expect(zielPfad(ziel)).toBe(pfad)
  })
  it('ohne Ziel kein Pfad', () => {
    expect(zielPfad(null)).toBeNull()
    expect(zielPfad(undefined)).toBeNull()
  })
})
