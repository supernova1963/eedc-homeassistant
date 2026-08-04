import { describe, it, expect } from 'vitest'
import { formatDatum, formatZeitraumKurz, jaNein } from './datum'

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

describe('formatZeitraumKurz (#360: gemessener Connector-Zeitraum)', () => {
  it('gleicher Monat → Von-Tag verkürzt, Bis-Datum vollständig', () => {
    expect(formatZeitraumKurz('2025-07-28T14:03:00', '2025-07-30T09:12:00')).toBe('28.–30.07.2025')
  })
  it('gleiches Jahr, anderer Monat → Von mit Monat', () => {
    expect(formatZeitraumKurz('2025-06-28', '2025-07-03')).toBe('28.06.–03.07.2025')
  })
  it('Jahreswechsel → beide Daten vollständig', () => {
    expect(formatZeitraumKurz('2024-12-28', '2025-01-03')).toBe('28.12.2024–03.01.2025')
  })
  it('ohne/mit kaputtem Bis-Datum bleibt das Von-Datum allein', () => {
    expect(formatZeitraumKurz('2025-07-28', null)).toBe('28.07.2025')
    expect(formatZeitraumKurz('2025-07-28', 'kein-datum')).toBe('28.07.2025')
  })
  it('ohne Von-Datum → Fallback —', () => {
    expect(formatZeitraumKurz(null, '2025-07-30')).toBe('—')
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
