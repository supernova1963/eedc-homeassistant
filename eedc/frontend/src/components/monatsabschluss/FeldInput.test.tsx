import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import FeldInput from './FeldInput'
import type { FeldStatus } from '../../api'

// E3-Regressionstest (Mängelbehebung 2026-07-11): Der SoT-Swap (Input/Button)
// darf das Vorschlagswerte-System — den Kern-Nutzen des Monatsabschlusses —
// nicht verändern: Placeholder aus dem 1. Vorschlag, „Übernehmen" nur bei
// leerem Wert, Vorschlags-Chips setzen den Wert, Warnungen färben den Rand.

const feld = (over: Partial<FeldStatus> = {}): FeldStatus => ({
  feld: 'einspeisung_kwh',
  label: 'Einspeisung',
  einheit: 'kWh',
  aktueller_wert: null,
  vorschlaege: [
    { wert: 123.4, quelle: 'ha_statistics', beschreibung: 'Aus HA-Statistik' },
    { wert: 120, quelle: 'vorjahr', beschreibung: 'Vorjahreswert' },
  ],
  warnungen: [],
  ...over,
} as FeldStatus)

describe('FeldInput (Monatsabschluss-Vorschlagswerte)', () => {
  it('zeigt den 1. Vorschlag als Placeholder und übernimmt ihn per Button', () => {
    const onChange = vi.fn()
    render(<FeldInput feld={feld()} value={null} onChange={onChange} />)
    expect(screen.getByLabelText('Einspeisung')).toHaveAttribute('placeholder', 'Vorschlag: 123.4')
    fireEvent.click(screen.getByRole('button', { name: 'Übernehmen' }))
    expect(onChange).toHaveBeenCalledWith(123.4)
  })

  it('blendet „Übernehmen" aus, sobald ein Wert gesetzt ist', () => {
    render(<FeldInput feld={feld()} value={99} onChange={vi.fn()} />)
    expect(screen.queryByRole('button', { name: 'Übernehmen' })).toBeNull()
  })

  it('Vorschlags-Chips setzen ihren Wert (mit Quelle beschriftet)', () => {
    const onChange = vi.fn()
    render(<FeldInput feld={feld()} value={null} onChange={onChange} />)
    const chip = screen.getByRole('button', { name: /120 kWh/ })
    fireEvent.click(chip)
    expect(onChange).toHaveBeenCalledWith(120)
  })

  it('compact blendet die Vorschlags-Chips aus (Übernehmen bleibt)', () => {
    render(<FeldInput feld={feld()} value={null} onChange={vi.fn()} compact />)
    expect(screen.getByRole('button', { name: 'Übernehmen' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /120 kWh/ })).toBeNull()
  })

  it('Warnungen: amber-Rand (Input warnung) + Meldung sichtbar', () => {
    render(
      <FeldInput
        feld={feld({ warnungen: [{ schwere: 'warning', meldung: 'Wert weicht stark ab' }] as FeldStatus['warnungen'] })}
        value={5}
        onChange={vi.fn()}
      />,
    )
    expect(screen.getByLabelText('Einspeisung').className).toContain('border-amber-300')
    expect(screen.getByText('Wert weicht stark ab')).toBeInTheDocument()
  })

  it('Eingabe liefert parseFloat bzw. null beim Leeren', () => {
    const onChange = vi.fn()
    const { rerender } = render(<FeldInput feld={feld()} value={null} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Einspeisung'), { target: { value: '42.5' } })
    expect(onChange).toHaveBeenCalledWith(42.5)
    rerender(<FeldInput feld={feld()} value={42.5} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Einspeisung'), { target: { value: '' } })
    expect(onChange).toHaveBeenCalledWith(null)
  })
})
