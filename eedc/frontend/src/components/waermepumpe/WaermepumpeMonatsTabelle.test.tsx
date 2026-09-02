/**
 * N-369 — Die JAZ-Spalte der Wärmepumpen-Monatstabelle rechnet nicht selbst.
 *
 * Bis zum 02.09.2026 stand hier `(heiz + ww) / strom` — eine rohe Division auf den
 * Rohfeldern, und damit genau das, was ADR-002/**P12** verbietet. Sie wusste weder
 * vom funktionsfremden Strom (Kühlen · Lüften · Entfeuchten) noch von gerechneter
 * statt gemessener Wärme, und ohne Strom stand dort `0,00` statt „—".
 *
 * ⚠ Gefunden hat es NICHT der Wächter: `check:cop-roh` sucht `<waerme> / <strom>`
 * über Namen, hier stand im Zähler eine **Klammer-Summe**. Beide Hälften — Spalte
 * und Wächter — haben deshalb ihren eigenen Sprengsatz.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../ui', async (echt) => ({
  ...(await echt<Record<string, unknown>>()),
}))

import { WaermepumpeMonatsTabelle } from './WaermepumpeCharts'
import type { InvestitionMonatsdaten } from '../../api/investitionen'

/** Eine Monatszeile, deren ROHE Division 0,7 ergäbe (Klimaanlage am selben Zähler). */
const md = (jahr: number, monat: number, strom: number, heiz: number, ww: number) => ({
  id: jahr * 100 + monat, jahr, monat,
  verbrauch_daten: { stromverbrauch_kwh: strom, heizenergie_kwh: heiz, warmwasser_kwh: ww },
}) as unknown as InvestitionMonatsdaten

describe('N-369 — JAZ-Spalte liest, statt zu rechnen', () => {
  it('zeigt den Wert aus dem Layer, NICHT die rohe Division', () => {
    // Roh gerechnet wären das (150 + 60) / 300 = 0,70. Der Layer sagt 2,20,
    // weil er den funktionsfremden Strom abzieht — genau der Melderfall.
    render(<WaermepumpeMonatsTabelle
      monatsdaten={[md(2026, 8, 300, 150, 60)]}
      jazJeMonat={[{ jahr: 2026, monat: 8, wert: 2.2, grund: null }]}
    />)
    expect(screen.getByText('2,20')).toBeInTheDocument()
    expect(screen.queryByText('0,70')).not.toBeInTheDocument()
  })

  it('gesperrte Arbeitszahl: „—" mit Grund, nicht irgendeine Zahl', () => {
    render(<WaermepumpeMonatsTabelle
      monatsdaten={[md(2026, 8, 300, 150, 60)]}
      jazJeMonat={[{ jahr: 2026, monat: 8, wert: null, grund: 'Wärmepumpe und Klimaanlage in einer Zahl' }]}
    />)
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.queryByText('0,70')).not.toBeInTheDocument()
  })

  it('ohne Strom steht „—", nicht 0,00 — eine Null hieße „gemessen, nichts herausgekommen"', () => {
    // Die Split-Klimaanlage: Strom ja, Wärme bauartbedingt nein. Vorher: 0,00.
    render(<WaermepumpeMonatsTabelle
      monatsdaten={[md(2026, 8, 220, 0, 0)]}
      jazJeMonat={[{ jahr: 2026, monat: 8, wert: null, grund: 'kein Wärmemengenzähler zugeordnet' }]}
    />)
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.queryByText('0,00')).not.toBeInTheDocument()
  })

  it('ohne Layer-Eintrag für den Monat: „—", keine erfundene Zahl', () => {
    render(<WaermepumpeMonatsTabelle monatsdaten={[md(2026, 8, 300, 150, 60)]} jazJeMonat={[]} />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('ordnet je (Jahr, Monat) zu — nicht nach Listenposition', () => {
    // Die Listen sind unabhängig sortiert: Tabelle aufsteigend, Layer absteigend.
    render(<WaermepumpeMonatsTabelle
      monatsdaten={[md(2026, 7, 100, 100, 0), md(2026, 8, 300, 150, 60)]}
      jazJeMonat={[
        { jahr: 2026, monat: 8, wert: 2.2, grund: null },
        { jahr: 2026, monat: 7, wert: 3.9, grund: null },
      ]}
    />)
    const zeilen = screen.getAllByRole('row')
    // Zeile 1 ist der Kopf; Juli muss 3,90 tragen, August 2,20.
    expect(zeilen[1].textContent).toContain('3,90')
    expect(zeilen[2].textContent).toContain('2,20')
  })

  // Die MENGEN bleiben unberührt — E1: Mengen summiert, Kennzahlen getrennt.
  it('Strom, Heizung und Warmwasser stehen unverändert da', () => {
    render(<WaermepumpeMonatsTabelle
      monatsdaten={[md(2026, 8, 300, 150, 60)]}
      jazJeMonat={[{ jahr: 2026, monat: 8, wert: null, grund: 'gesperrt' }]}
    />)
    const zeile = screen.getAllByRole('row')[1].textContent ?? ''
    expect(zeile).toContain('300')
    expect(zeile).toContain('150')
    expect(zeile).toContain('60')
  })
})
