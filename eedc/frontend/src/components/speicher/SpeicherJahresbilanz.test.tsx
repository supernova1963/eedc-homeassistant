import { describe, it, expect } from 'vitest'
import { prepSpeicherJahresbilanz } from './SpeicherJahresbilanz'
import { prepSpeicherMonate } from './SpeicherVerlaufCharts'
import type { SpeicherMonatsWert } from '../../api/investitionen'

/** Ein Monat der bewerteten Reihe (`monatsreihe`, N-641/N-642) — die Form, die das Backend sendet:
 *  `pv_ladung_kwh` = Ladung − Netzladung (nie < 0), `vollzyklen` = Entladung ÷ Kapazität. */
const mw = (jahr: number, monat: number, w: Partial<SpeicherMonatsWert>): SpeicherMonatsWert => {
  const ladung = w.ladung_kwh ?? 0
  const netz = w.netzladung_kwh ?? 0
  return {
    jahr, monat, ladung_kwh: ladung, entladung_kwh: 0, netzladung_kwh: netz,
    pv_ladung_kwh: Math.max(0, ladung - netz), vollzyklen: null, ...w,
  }
}

describe('prepSpeicherJahresbilanz (Päckchen BB: die Faltung liegt im Backend)', () => {
  it('benennt die Jahre der Antwort nur um — Σ und Verlust kommen fertig (`jahresbilanz`)', () => {
    // Werte, die der Client NICHT selbst ableiten könnte (Verlust ≠ Ladung − Entladung): er darf nichts nachrechnen.
    const daten = prepSpeicherJahresbilanz([
      { jahr: 2024, pv_ladung_kwh: 40, netzladung_kwh: 10, entladung_kwh: 40, ladung_gesamt_kwh: 50, verlust_kwh: 7 },
      { jahr: 2025, pv_ladung_kwh: 170, netzladung_kwh: 30, entladung_kwh: 170, ladung_gesamt_kwh: 200, verlust_kwh: 30 },
    ])
    expect(daten.map((d) => d.jahr)).toEqual([2024, 2025])
    expect(daten[0]).toEqual({ jahr: 2024, pvLadung: 40, netzLadung: 10, entladung: 40, verlust: 7, ladungGesamt: 50 })
  })

  it('ohne Jahre leer', () => {
    expect(prepSpeicherJahresbilanz([])).toEqual([])
  })
})

describe('prepSpeicherMonate (N-641/N-642)', () => {
  it('Vollzyklen je Monat sind die der Reihe (Entladung ÷ Kapazität), nicht Ladung ÷ Kapazität', () => {
    // M02 Juni: Ladung 90, Entladung 60, 10 kWh — der Verlauf stand auf 9,0, die Kachel auf 6,0.
    const [z] = prepSpeicherMonate([mw(2026, 6, { ladung_kwh: 90, entladung_kwh: 60, vollzyklen: 6 })])
    expect(z).toMatchObject({ name: 'Jun 26', ladung: 90, entladung: 60, zyklen: 6 })
  })

  it('ohne gepflegte Kapazität (null) bleibt der Zyklen-Balken bei 0 wie bisher (N127)', () => {
    const [z] = prepSpeicherMonate([mw(2026, 6, { ladung_kwh: 30, entladung_kwh: 20, vollzyklen: null })])
    expect(z.zyklen).toBe(0)
  })

  it('Netz- und PV-Ladung je Monat aus der Reihe', () => {
    const [z] = prepSpeicherMonate([mw(2026, 6, { ladung_kwh: 120, netzladung_kwh: 30 })])
    expect(z.arbitrage).toBe(30)
    expect(z.pvLadung).toBe(90)
  })
})
