/**
 * N-370 — Die JAZ-Spalte zeigt, womit sie gerechnet hat (Style-Guide **A6**).
 *
 * Nach N-369 las die Spalte ihren Wert aus dem Layer — richtig, aber neben
 * Rohwerten, aus denen er sich nicht mehr nachrechnen ließ: Strom 316, Wärme 210,
 * daneben eine JAZ von 2,20, und `210 ÷ 316` ergibt 0,66. **Vorher war die Zeile
 * konsistent und falsch, danach richtig und unerklärlich** — und das ist die
 * schlechtere Lage, weil ein Melder, der nachrechnet, jetzt nichts mehr findet,
 * woran er sich festhalten kann.
 *
 * Drei Regelhälften, drei Sprengsätze:
 *  1. **Zeigen, wo es nötig ist** — fehlt die Herleitung bei abweichendem Nenner,
 *     ist der Fund wieder da.
 *  2. **Aus dem LAYER, nicht nachgerechnet** — wer sie aus den Anzeigefeldern baut,
 *     schreibt `210 ÷ 316` unter eine Zahl, die 2,20 sagt (die W-3-Klasse).
 *  3. **Schweigen, wo die Zeile aufgeht** — sonst steht unter jeder Zahl eine
 *     Rechnung, die dasselbe sagt wie die Spalten daneben.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../ui', async (echt) => ({
  ...(await echt<Record<string, unknown>>()),
}))

import { WaermepumpeMonatsTabelle } from './WaermepumpeCharts'
import type { InvestitionMonatsdaten } from '../../api/investitionen'

const md = (jahr: number, monat: number, strom: number, heiz: number, ww: number) => ({
  id: jahr * 100 + monat, jahr, monat,
  verbrauch_daten: { stromverbrauch_kwh: strom, heizenergie_kwh: heiz, warmwasser_kwh: ww },
}) as unknown as InvestitionMonatsdaten

describe('N-370 — die Arbeitszahl je Monat ist nachrechenbar', () => {
  it('SPRENGSATZ 1 — bereinigter Nenner: die Herleitung steht da', () => {
    // dietmar1968s Fall (T89667 #290): 316 kWh Strom, davon rund 220 für die
    // Klimaanlage. Der Layer rechnet mit 96, die Spalte zeigt 316.
    render(<WaermepumpeMonatsTabelle
      monatsdaten={[md(2026, 8, 316, 150, 60)]}
      jazJeMonat={[{
        jahr: 2026, monat: 8, wert: 2.2, grund: null,
        zaehler_kwh: 210, nenner_kwh: 96,
      }]}
    />)
    expect(screen.getByText('2,20')).toBeInTheDocument()
    expect(screen.getByText('210 ÷ 96 kWh')).toBeInTheDocument()
    // Und der erklärende Satz steht sichtbar unter der Tabelle, nicht im Tooltip.
    expect(screen.getByText(/Strom fürs Kühlen, Lüften oder Entfeuchten zählt nicht mit/))
      .toBeInTheDocument()
  })

  it('SPRENGSATZ 2 — die Zahlen kommen aus dem LAYER, nicht aus den Anzeigefeldern', () => {
    // Wer die Herleitung aus `(heiz + ww)` und `strom` nachbaut, schreibt hier
    // „210 ÷ 316" — eine Rechnung, die auf 0,66 führt statt auf die 2,20 daneben.
    render(<WaermepumpeMonatsTabelle
      monatsdaten={[md(2026, 8, 316, 150, 60)]}
      jazJeMonat={[{
        jahr: 2026, monat: 8, wert: 2.2, grund: null,
        zaehler_kwh: 210, nenner_kwh: 96,
      }]}
    />)
    expect(screen.queryByText('210 ÷ 316 kWh')).not.toBeInTheDocument()
  })

  it('SPRENGSATZ 3 — geht die Zeile auf, schweigt die Zelle', () => {
    // Kein funktionsfremder Anteil: Q und E SIND die Spalten daneben. Eine zweite
    // Zeile mit denselben Zahlen wäre Rauschen (Präzedenz W-17b,
    // `WaermepumpeModusSplit`: „Stimmen beide überein, entfällt die Zeile").
    render(<WaermepumpeMonatsTabelle
      monatsdaten={[md(2026, 8, 100, 150, 60)]}
      jazJeMonat={[{
        jahr: 2026, monat: 8, wert: 2.1, grund: null,
        zaehler_kwh: 210, nenner_kwh: 100,
      }]}
    />)
    expect(screen.getByText('2,10')).toBeInTheDocument()
    expect(screen.queryByText('210 ÷ 100 kWh')).not.toBeInTheDocument()
    // Ohne Herleitung in der Tabelle steht auch der erklärende Satz nicht da.
    expect(screen.queryByText(/Strom fürs Kühlen, Lüften oder Entfeuchten zählt nicht mit/))
      .not.toBeInTheDocument()
  })

  it('rundet auf DERSELBEN Ebene wie die Spalten daneben', () => {
    // 315,6 gegen 316,0: gerundet identisch. Stünde hier „210 ÷ 316 kWh", sagte die
    // Herleitung sichtbar dasselbe wie die Zeile — und der Leser suchte den
    // Unterschied, den es nicht gibt.
    render(<WaermepumpeMonatsTabelle
      monatsdaten={[md(2026, 8, 316, 150, 60)]}
      jazJeMonat={[{
        jahr: 2026, monat: 8, wert: 0.67, grund: null,
        zaehler_kwh: 210, nenner_kwh: 315.6,
      }]}
    />)
    expect(screen.queryByText(/÷/)).not.toBeInTheDocument()
  })

  it('gesperrte Arbeitszahl: keine Herleitung aus einem „—"', () => {
    // Präzedenz `MonatBilanz.tsx:156` / `fa270c6f`: ohne Wert keine Rechnung.
    render(<WaermepumpeMonatsTabelle
      monatsdaten={[md(2026, 8, 316, 150, 60)]}
      jazJeMonat={[{
        jahr: 2026, monat: 8, wert: null, grund: 'Wärme ist gerechnet, nicht gemessen',
        zaehler_kwh: null, nenner_kwh: null,
      }]}
    />)
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.queryByText(/÷/)).not.toBeInTheDocument()
  })
})
