import { describe, it, expect } from 'vitest'
import { prepEAutoJahresLadung } from './EAutoJahresvergleich'
import type { InvestitionMonatsdaten } from '../../api/investitionen'

const md = (jahr: number, monat: number, vd: Record<string, number>): InvestitionMonatsdaten =>
  ({ jahr, monat, verbrauch_daten: vd }) as unknown as InvestitionMonatsdaten

describe('prepEAutoJahresLadung', () => {
  it('summiert Ladung je Jahr nach Quelle, chronologisch', () => {
    const daten = prepEAutoJahresLadung([
      md(2025, 1, { ladung_pv_kwh: 100, ladung_netz_kwh: 40, ladung_extern_kwh: 10 }),
      md(2025, 2, { ladung_pv_kwh: 50, ladung_netz_kwh: 20 }),
      md(2024, 12, { ladung_pv_kwh: 30, ladung_netz_kwh: 30 }),
    ])
    expect(daten.map((d) => d.jahr)).toEqual([2024, 2025])
    const y2025 = daten[1]
    expect(y2025.pv).toBe(150)
    expect(y2025.netz).toBe(60)
    expect(y2025.extern).toBe(10)
    expect(y2025.gesamt).toBe(220)
  })
})
