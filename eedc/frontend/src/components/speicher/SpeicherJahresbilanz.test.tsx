import { describe, it, expect } from 'vitest'
import { prepSpeicherJahresbilanz } from './SpeicherJahresbilanz'
import type { InvestitionMonatsdaten } from '../../api/investitionen'

const md = (jahr: number, monat: number, vd: Record<string, number>): InvestitionMonatsdaten =>
  ({ jahr, monat, verbrauch_daten: vd }) as unknown as InvestitionMonatsdaten

describe('prepSpeicherJahresbilanz', () => {
  it('bildet die Bilanz je Jahr: PV/Netz-Ladung, Entladung, Verlust = Ladung − Entladung', () => {
    const daten = prepSpeicherJahresbilanz([
      md(2025, 1, { ladung_kwh: 100, entladung_kwh: 80, speicher_ladung_netz_kwh: 30 }),
      md(2025, 2, { ladung_kwh: 100, entladung_kwh: 90, speicher_ladung_netz_kwh: 0 }),
      md(2024, 12, { ladung_kwh: 50, entladung_kwh: 40, speicher_ladung_netz_kwh: 10 }),
    ])
    // chronologisch aufsteigend
    expect(daten.map((d) => d.jahr)).toEqual([2024, 2025])
    const y2025 = daten[1]
    expect(y2025.ladungGesamt).toBe(200)
    expect(y2025.netzLadung).toBe(30)
    expect(y2025.pvLadung).toBe(170) // (100−30) + (100−0)
    expect(y2025.entladung).toBe(170)
    expect(y2025.verlust).toBe(30) // 200 − 170
    // Bilanz-Invariante: Ladung-Säule = Entladung-Säule (gleich hoch)
    expect(y2025.pvLadung + y2025.netzLadung).toBe(y2025.entladung + y2025.verlust)
  })

  it('Verlust nie negativ (kumulativer SoC-Übertrag)', () => {
    const [y] = prepSpeicherJahresbilanz([
      md(2025, 1, { ladung_kwh: 50, entladung_kwh: 80, speicher_ladung_netz_kwh: 0 }),
    ])
    expect(y.verlust).toBe(0)
  })
})
