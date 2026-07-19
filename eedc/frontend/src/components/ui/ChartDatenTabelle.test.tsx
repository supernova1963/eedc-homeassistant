/**
 * ChartDatenTabelle (Paket CT) — Verhaltens-Gate der Tabellen-Ablesung:
 * Header `Label (Einheit)` (B2) · de-DE-Zellformat + `—`-Leerwert (A3/C2) ·
 * Summenzeile NUR für summierbare Einheiten (kWh/km/€, nie % / kW) ·
 * Zeilen in Chart-Reihenfolge · CSV = Rohwerte (max. 4 NK) inkl. Σ-Zeile.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { ChartDatenTabelle, type ChartTabelleSpalte } from './ChartDatenTabelle'
import * as exportUtils from '../../utils/export'

const SPALTEN: ChartTabelleSpalte[] = [
  { key: 'einspeisung', label: 'Einspeisung', einheit: 'kWh' },
  { key: 'autarkie', label: 'Autarkie', einheit: '%' },
]

const DATEN = [
  { tag: 1, einspeisung: 1234.5, autarkie: 80.1 },
  { tag: 2, einspeisung: 2.4, autarkie: null },
]

function bau(spalten: ChartTabelleSpalte[] = SPALTEN, daten: Array<Record<string, unknown>> = DATEN) {
  return render(
    <ChartDatenTabelle xLabel="Tag" xKey="tag" spalten={spalten} daten={daten} csvDateiname="test.csv" />,
  )
}

describe('ChartDatenTabelle — Paket CT', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('Header: X-Spalte + `Label (Einheit)` in runden Klammern (B2)', () => {
    bau()
    expect(screen.getByText('Tag')).toBeInTheDocument()
    expect(screen.getByText('Einspeisung (kWh)')).toBeInTheDocument()
    expect(screen.getByText('Autarkie (%)')).toBeInTheDocument()
  })

  it('Zellen: de-DE-Format (Tausenderpunkt + Komma), Leerwert = —', () => {
    bau()
    expect(screen.getByText('1.234,5')).toBeInTheDocument()
    expect(screen.getByText('2,4')).toBeInTheDocument()
    // autarkie-null-Zelle + Σ-Zelle der %-Spalte zeigen beide das A3-Leerzeichen.
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(1)
  })

  it('Zeilen bleiben in Chart-Reihenfolge (1:1-Ablesung, kein Umsortieren)', () => {
    const { container } = bau()
    const zellen = [...container.querySelectorAll('tbody tr td:first-child')].map((td) => td.textContent)
    expect(zellen).toEqual(['1', '2'])
  })

  it('Summenzeile: Σ nur für kWh/km/€ — %-Spalte zeigt —', () => {
    const { container } = bau()
    const fuss = container.querySelector('tfoot')!
    expect(within(fuss as HTMLElement).getByText('1.236,9')).toBeInTheDocument() // 1234.5 + 2.4
    expect(within(fuss as HTMLElement).getByText('—')).toBeInTheDocument()
  })

  it('keine Summenzeile, wenn keine Spalte summierbar ist (z. B. kW-Live)', () => {
    const { container } = bau([{ key: 'pv', label: 'PV', einheit: 'kW', nachkomma: 2 }],
      [{ tag: 1, pv: 3.21 }])
    expect(container.querySelector('tfoot')).toBeNull()
  })

  it('`summierbar: false` übersteuert die Einheiten-Heuristik', () => {
    const { container } = bau([{ key: 'stand', label: 'Zählerstand', einheit: 'kWh', summierbar: false }],
      [{ tag: 1, stand: 100 }])
    expect(container.querySelector('tfoot')).toBeNull()
  })

  it('CSV: Rohwerte mit Punkt-Kappung (4 NK) + Σ-Zeile, Header mit Einheit', () => {
    const spy = vi.spyOn(exportUtils, 'exportToCSV').mockImplementation(() => {})
    bau([...SPALTEN], [
      { tag: 1, einspeisung: 0.30000000000000004, autarkie: 80.1 },
      { tag: 2, einspeisung: 2, autarkie: null },
    ])
    fireEvent.click(screen.getByRole('button', { name: /CSV/ }))
    expect(spy).toHaveBeenCalledTimes(1)
    const [headers, rows, dateiname] = spy.mock.calls[0]
    expect(headers).toEqual(['Tag', 'Einspeisung (kWh)', 'Autarkie (%)'])
    expect(rows[0]).toEqual(['1', 0.3, 80.1])
    expect(rows[1]).toEqual(['2', 2, ''])
    expect(rows[2]).toEqual(['Σ 2 Tag', 2.3, '']) // Summen nur summierbare Spalten
    expect(dateiname).toBe('test.csv')
  })
})
