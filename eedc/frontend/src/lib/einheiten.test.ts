import { describe, it, expect } from 'vitest'
import {
  fmtZahl, formatEnergie, formatCo2, formatGeld, formatTarif,
  formatProzent, formatSpezErtrag, formatEffizienz, energieAchse, co2Achse,
} from './einheiten'

// IA-V4 A.5 R2-SoT (Gernot-Abnahme 2026-06-25): Schwelle ≥1.000, NK je Einheit.

describe('fmtZahl (R1: de-DE mit Tausenderpunkt)', () => {
  it('Tausenderpunkt + feste NK', () => {
    expect(fmtZahl(1234, 0)).toBe('1.234')
    expect(fmtZahl(1234.5, 2)).toBe('1.234,50')
    expect(fmtZahl(2, 2)).toBe('2,00')
  })
  it('Fallback bei null/NaN', () => {
    expect(fmtZahl(null)).toBe('—')
    expect(fmtZahl(undefined)).toBe('—')
    expect(fmtZahl(NaN)).toBe('—')
  })
})

describe('formatEnergie (kWh→MWh ab ≥1.000, MWh 2 NK)', () => {
  it('< 1.000 → kWh, 0 NK', () => {
    expect(formatEnergie(847)).toEqual({ wert: '847', einheit: 'kWh', text: '847 kWh' })
  })
  it('≥ 1.000 → MWh, 2 NK (Gernot-Beispiel 2.000 → 2,00 MWh)', () => {
    expect(formatEnergie(2000)).toEqual({ wert: '2,00', einheit: 'MWh', text: '2,00 MWh' })
    expect(formatEnergie(1500)).toEqual({ wert: '1,50', einheit: 'MWh', text: '1,50 MWh' })
  })
  it('≥ 1.000.000 → GWh', () => {
    expect(formatEnergie(2_500_000).einheit).toBe('GWh')
    expect(formatEnergie(2_500_000).wert).toBe('2,50')
  })
  it('referenz erzwingt gemeinsame Einheit (Achsen-Konsistenz)', () => {
    // Achsen-Max 5.000 → alle Werte in MWh, auch der kleine 800er.
    expect(formatEnergie(800, 5000)).toEqual({ wert: '0,80', einheit: 'MWh', text: '0,80 MWh' })
  })
})

describe('energieAchse (eine Einheit für ganze Achse vom Max)', () => {
  it('Max ≥ 1.000 → MWh-Ticks', () => {
    const a = energieAchse(4200)
    expect(a.einheit).toBe('MWh')
    expect(a.tick(2000)).toBe('2,00')
  })
  it('Max < 1.000 → kWh-Ticks', () => {
    const a = energieAchse(800)
    expect(a.einheit).toBe('kWh')
    expect(a.tick(500)).toBe('500')
  })
})

describe('formatCo2 (kg→t ab ≥1.000, t 2 NK)', () => {
  it('< 1.000 → kg', () => expect(formatCo2(847)).toEqual({ wert: '847', einheit: 'kg', text: '847 kg' }))
  it('≥ 1.000 → t (12.500 kg → 12,50 t)', () =>
    expect(formatCo2(12500)).toEqual({ wert: '12,50', einheit: 't', text: '12,50 t' }))
  it('co2Achse', () => expect(co2Achse(5000).einheit).toBe('t'))
})

describe('fixe Einheiten (NK je Rolle)', () => {
  it('Geld-Summe 0 NK', () => expect(formatGeld(1234.56)).toEqual({ wert: '1.235', einheit: '€', text: '1.235 €' }))
  it('Tarif 2 NK', () => expect(formatTarif(28.5)).toEqual({ wert: '28,50', einheit: 'ct/kWh', text: '28,50 ct/kWh' }))
  it('Prozent 1 NK', () => expect(formatProzent(94.25)).toEqual({ wert: '94,3', einheit: '%', text: '94,3 %' }))
  it('Spez. Ertrag 0 NK', () => expect(formatSpezErtrag(1050.7).text).toBe('1.051 kWh/kWp'))
  it('Effizienz 2 NK', () => expect(formatEffizienz(3.456).wert).toBe('3,46'))
  it('null → —', () => expect(formatGeld(null).text).toBe('—'))
})
