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

describe('prepSpeicherJahresbilanz', () => {
  it('bildet die Bilanz je Jahr: PV/Netz-Ladung, Entladung, Verlust = Ladung − Entladung', () => {
    const daten = prepSpeicherJahresbilanz([
      mw(2025, 1, { ladung_kwh: 100, entladung_kwh: 80, netzladung_kwh: 30 }),
      mw(2025, 2, { ladung_kwh: 100, entladung_kwh: 90, netzladung_kwh: 0 }),
      mw(2024, 12, { ladung_kwh: 50, entladung_kwh: 40, netzladung_kwh: 10 }),
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
      mw(2025, 1, { ladung_kwh: 50, entladung_kwh: 80, netzladung_kwh: 0 }),
    ])
    expect(y.verlust).toBe(0)
  })

  it('N-642: die Netzladung kommt aus der Reihe — der Legacy-Schlüssel der Rohzeile zählt nicht mehr', () => {
    // M04 Juni (Achsen-Matrix): Ladung 120, Kanon `ladung_netz_kwh` 30. Gelesen wurde
    // `speicher_ladung_netz_kwh` (seit v3.25 nicht mehr geschrieben) ⇒ Netz 0, PV 120.
    const [y] = prepSpeicherJahresbilanz([mw(2026, 6, { ladung_kwh: 120, entladung_kwh: 60, netzladung_kwh: 30 })])
    expect(y.netzLadung).toBe(30)
    expect(y.pvLadung).toBe(90)
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
