import { describe, it, expect } from 'vitest'
import { prepBkwJahresVerwendung } from './BkwJahresvergleich'
import type { InvestitionMonatsdaten } from '../../api/investitionen'

const md = (jahr: number, monat: number, vd: Record<string, number>): InvestitionMonatsdaten =>
  ({ jahr, monat, verbrauch_daten: vd }) as unknown as InvestitionMonatsdaten

describe('prepBkwJahresVerwendung', () => {
  it('summiert Verwendung (EV/Einspeisung) je Jahr, chronologisch', () => {
    const daten = prepBkwJahresVerwendung([
      md(2025, 1, { eigenverbrauch_kwh: 80, einspeisung_kwh: 20 }),
      md(2025, 2, { eigenverbrauch_kwh: 70, einspeisung_kwh: 30 }),
      md(2024, 12, { eigenverbrauch_kwh: 40, einspeisung_kwh: 60 }),
    ])
    expect(daten.map((d) => d.jahr)).toEqual([2024, 2025])
    const y2025 = daten[1]
    expect(y2025.eigenverbrauch).toBe(150)
    expect(y2025.einspeisung).toBe(50)
    expect(y2025.gesamt).toBe(200)
  })
})
