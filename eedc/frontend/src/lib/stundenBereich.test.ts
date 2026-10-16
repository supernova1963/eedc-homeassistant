/**
 * HA-Bauform S4 (S4-E2 A): die Stunde als Bereich — Kanal-Tag (Beginn) und Bestandstag (Ende) in derselben Form.
 */
import { describe, it, expect } from 'vitest'
import { stundenBereich } from './stundenBereich'

describe('stundenBereich', () => {
  it('Beginn-Raster: Stunde 11 ist 11–12, die letzte Stunde 23–24', () => {
    expect(stundenBereich(11, 'beginn')).toBe('11–12')
    expect(stundenBereich(0, 'beginn')).toBe('0–1')
    expect(stundenBereich(23, 'beginn')).toBe('23–24')
  })

  it('Ende-Raster: Slot 11 ist 10–11, Slot 0 die letzte Stunde des Vortags 23–24', () => {
    expect(stundenBereich(11, 'ende')).toBe('10–11')
    expect(stundenBereich(1, 'ende')).toBe('0–1')
    expect(stundenBereich(0, 'ende')).toBe('23–24')
  })

  it('ohne Raster gilt der Bestand (Ende)', () => {
    expect(stundenBereich(11)).toBe('10–11')
  })

  it('dieselbe Stunde [10, 11) heißt in beiden Rastern gleich', () => {
    expect(stundenBereich(10, 'beginn')).toBe(stundenBereich(11, 'ende'))
  })
})
