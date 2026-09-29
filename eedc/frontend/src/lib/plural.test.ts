import { describe, it, expect } from 'vitest'
import { plural, mitAnzahl } from './plural'

describe('plural', () => {
  it('nimmt bei genau 1 die Einzahl', () => {
    expect(plural(1, 'Feld', 'Felder')).toBe('Feld')
  })

  it('nimmt bei mehr als 1 die Mehrzahl', () => {
    expect(plural(2, 'Feld', 'Felder')).toBe('Felder')
    expect(plural(65, 'Feld', 'Felder')).toBe('Felder')
  })

  // ⭐ Der Fall, der die Zentrale erst nötig macht: 0 ist im Deutschen Mehrzahl
  // („0 Felder"), nicht Einzahl. Ein `anzahl < 2`-Vergleich wäre hier falsch.
  it('nimmt bei 0 die Mehrzahl', () => {
    expect(plural(0, 'Feld', 'Felder')).toBe('Felder')
  })

  it('trägt den Fall mit, weil beide Formen vom Aufrufer kommen', () => {
    // Dativ: „in 1 Monat" ⇄ „in 3 Monaten"
    expect(plural(1, 'Monat', 'Monaten')).toBe('Monat')
    expect(plural(3, 'Monat', 'Monaten')).toBe('Monaten')
  })
})

describe('mitAnzahl', () => {
  it('setzt die Zahl vor die passende Form', () => {
    expect(mitAnzahl(1, 'Feld', 'Felder')).toBe('1 Feld')
    expect(mitAnzahl(3, 'Feld', 'Felder')).toBe('3 Felder')
    expect(mitAnzahl(0, 'Feld', 'Felder')).toBe('0 Felder')
  })

  it('lässt die Zahl unformatiert — Tausenderpunkte sind nicht seine Aufgabe', () => {
    expect(mitAnzahl(1234, 'Anlage', 'Anlagen')).toBe('1234 Anlagen')
  })
})
