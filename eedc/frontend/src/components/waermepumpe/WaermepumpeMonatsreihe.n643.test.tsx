/**
 * N-643 — *Komponenten → Wärmepumpe* ④ Verlauf und Monatstabelle lesen die bewertete Monatsreihe.
 *
 * Bis 4.1.3 lasen beide `heizenergie_kwh`/`warmwasser_kwh` roh. Ein gemeinsamer Wärmezähler (`waerme_kwh`,
 * Achsen-Matrix M05: 648 kWh) und die Heizwärme eines Klimageräts aus Betriebsart-Zählern (N-398, M06: 54 kWh)
 * standen dort als 0, während die Kacheln dieselbe Wärme zählten. Ohne Warmwasser-Achse trägt die Fläche
 * „Wärme" die Wärme gesamt (S2) — auch dann, wenn die Heizwärme 0 ist.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../ui', async (echt) => ({
  ...(await echt<Record<string, unknown>>()),
}))

import { WaermepumpeMonatsTabelle, prepWpMonate } from './WaermepumpeCharts'
import type { WpMonatsWert } from '../../api/investitionen'

const mw = (w: Partial<WpMonatsWert>): WpMonatsWert => ({
  jahr: 2026, monat: 6, strom_kwh: 0, heizung_kwh: 0, warmwasser_kwh: 0, waerme_kwh: 0, ...w,
})

describe('prepWpMonate (N-643)', () => {
  it('gemeinsamer Wärmezähler: die Zeile trägt die Wärme gesamt, die Heizwärme bleibt 0', () => {
    const [z] = prepWpMonate([mw({ strom_kwh: 216, waerme_kwh: 648 })], false)
    expect(z).toMatchObject({ name: 'Jun 26', heizung: 0, warmwasser: 0, waerme: 648 })
  })

  it('Betriebsart-Nutzenergie (Klima): Heizung aus der Reihe statt 0', () => {
    const [z] = prepWpMonate([mw({ strom_kwh: 54, heizung_kwh: 54, waerme_kwh: 54 })], false)
    expect(z.heizung).toBe(54)
    expect(z.waerme).toBe(54)
  })

  it('mit Warmwasser-Achse: Heizung + Warmwasser aus der Reihe', () => {
    const [z] = prepWpMonate([mw({ heizung_kwh: 540, warmwasser_kwh: 108, waerme_kwh: 648 })], true)
    expect([z.heizung, z.warmwasser]).toEqual([540, 108])
  })

  it('ohne Warmwasser-Achse liest die Zeile kein Warmwasser (N-379)', () => {
    const [z] = prepWpMonate([mw({ heizung_kwh: 50, warmwasser_kwh: 20, waerme_kwh: 70 })], false)
    expect(z.warmwasser).toBe(0)
  })
})

describe('WaermepumpeMonatsTabelle (N-643)', () => {
  it('ohne Warmwasser-Achse steht in der Spalte „Wärme" die Wärme gesamt — 648, nicht 0', () => {
    render(<WaermepumpeMonatsTabelle
      monatsreihe={[mw({ strom_kwh: 216, waerme_kwh: 648 })]}
      jazJeMonat={[{ jahr: 2026, monat: 6, wert: 3, grund: null, zaehler_kwh: 648, nenner_kwh: 216 }]}
      hatWarmwasserAchse={false}
    />)
    const zeile = screen.getAllByRole('row')[1].textContent ?? ''
    expect(zeile).toContain('216')
    expect(zeile).toContain('648')
    // Die Zeile geht auf (Q = 648 = Wärme-Spalte, E = 216 = Strom-Spalte) ⇒ keine Herleitung.
    expect(screen.queryByText(/÷/)).not.toBeInTheDocument()
  })

  it('mit Warmwasser-Achse: Heizung und Warmwasser getrennt aus der Reihe', () => {
    render(<WaermepumpeMonatsTabelle
      monatsreihe={[mw({ strom_kwh: 216, heizung_kwh: 540, warmwasser_kwh: 108, waerme_kwh: 648 })]}
      jazJeMonat={[]}
    />)
    const zeile = screen.getAllByRole('row')[1].textContent ?? ''
    expect(zeile).toContain('540')
    expect(zeile).toContain('108')
  })
})
