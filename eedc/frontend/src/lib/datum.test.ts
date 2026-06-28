import { describe, it, expect } from 'vitest'
import { formatDatum, jaNein } from './datum'

// Drift-Gate (detLAN-Gegencheck 6, 2026-06-28): Runtime-Absicherung des Datums-/
// Boolean-Anzeige-SoT. `check-de-de.mjs` flaggt rohe ISO-Datums-Anzeigen statisch;
// dieser Test sichert das tatsächliche Format (TT.MM.JJJJ, TZ-robust, Ja/Nein).
describe('formatDatum (R1: de-DE TT.MM.JJJJ)', () => {
  it('reine Datums-ISO → TT.MM.JJJJ', () => {
    expect(formatDatum('2023-06-01')).toBe('01.06.2023')
    expect(formatDatum('2026-12-31')).toBe('31.12.2026')
  })
  it('TZ-robust: Datum kippt nicht auf den Vortag', () => {
    // ohne Mittag-Anker würde UTC-Mitternacht in DE-Zeit auf 31.05. kippen.
    expect(formatDatum('2023-06-01')).toBe('01.06.2023')
  })
  it('voller ISO-String mit Zeit → Datum', () => {
    expect(formatDatum('2023-06-01T08:30:00Z')).toBe('01.06.2023')
  })
  it('leer/null/undefined → Fallback —', () => {
    expect(formatDatum(null)).toBe('—')
    expect(formatDatum(undefined)).toBe('—')
    expect(formatDatum('')).toBe('—')
  })
})

describe('jaNein (Boolean → Ja/Nein)', () => {
  it('true/false → Ja/Nein', () => {
    expect(jaNein(true)).toBe('Ja')
    expect(jaNein(false)).toBe('Nein')
  })
  it('null/undefined → Fallback —', () => {
    expect(jaNein(null)).toBe('—')
    expect(jaNein(undefined)).toBe('—')
  })
})
