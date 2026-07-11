/**
 * SegmentControl — Wächter-Test der D18-1-Regel (detlan #210):
 * Ein Segment-Umschalter darf Optionen NIE hart abschneiden — passen sie nicht
 * in die verfügbare Breite, brechen sie um. Konkret: der Gruppen-Container
 * trägt `flex-wrap` + `max-w-full` (jsdom misst kein Layout — die Klassen SIND
 * hier die Regel; die Pixel-Probe lief per Playwright @375 px gegen den
 * Vergleich-Modus mit 6 Presets). Dazu Grundverhalten: alle Optionen sichtbar,
 * `aria-pressed` markiert die aktive.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { SegmentControl } from './SegmentControl'

const OPTIONEN = [
  { key: 'verbrauch', label: 'Verbrauch' },
  { key: 'erzeugung', label: 'Erzeugung' },
  { key: 'ertrag', label: 'Ertrag' },
  { key: 'batterie', label: 'Batterie' },
  { key: 'autarkie', label: 'Autarkie' },
  { key: 'ev', label: 'EV-Quote' },
] as const

describe('SegmentControl (SoT B15 + D18-1)', () => {
  it('rendert ALLE Optionen; aria-pressed markiert die aktive', () => {
    const onChange = vi.fn()
    render(<SegmentControl ariaLabel="Vergleich-Kennzahl" optionen={OPTIONEN} value="ertrag" onChange={onChange} />)
    for (const o of OPTIONEN) expect(screen.getByRole('button', { name: o.label })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ertrag' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Batterie' })).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(screen.getByRole('button', { name: 'Batterie' }))
    expect(onChange).toHaveBeenCalledWith('batterie')
  })

  it('D18-1: die Gruppe bricht um statt abzuschneiden (flex-wrap + max-w-full)', () => {
    render(<SegmentControl ariaLabel="Vergleich-Kennzahl" optionen={OPTIONEN} value="ertrag" onChange={() => {}} />)
    const gruppe = screen.getByRole('group', { name: 'Vergleich-Kennzahl' })
    expect(gruppe.className).toContain('flex-wrap')
    expect(gruppe.className).toContain('max-w-full')
  })
})
