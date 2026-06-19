import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MonatStepper } from './MonatStepper'
import type { RailEintrag } from './MonatsRail'

const E: RailEintrag[] = [
  { jahr: 2024, monat: 12, pv_kwh: 300 },
  { jahr: 2025, monat: 10, pv_kwh: 500 },
  { jahr: 2025, monat: 11, pv_kwh: 560 },
  { jahr: 2025, monat: 12, pv_kwh: 450 },
  { jahr: 2026, monat: 6, pv_kwh: 0, laufend: true },
]

describe('MonatStepper', () => {
  it('±1 Monat', () => {
    const onSelect = vi.fn()
    render(<MonatStepper entries={E} jahr={2025} monat={11} onSelect={onSelect} />)
    screen.getByLabelText('nächster Monat').click()
    expect(onSelect).toHaveBeenLastCalledWith(2025, 12)
    screen.getByLabelText('voriger Monat').click()
    expect(onSelect).toHaveBeenLastCalledWith(2025, 10)
  })

  it('ältester / neuester Monat (Sprung an die Ränder)', () => {
    const onSelect = vi.fn()
    render(<MonatStepper entries={E} jahr={2025} monat={11} onSelect={onSelect} />)
    screen.getByLabelText('ältester Monat').click()
    expect(onSelect).toHaveBeenLastCalledWith(2024, 12)
    screen.getByLabelText('neuester Monat').click()
    expect(onSelect).toHaveBeenLastCalledWith(2026, 6)
  })

  it('±1 Jahr nur wenn der Monat existiert, sonst deaktiviert', () => {
    const onSelect = vi.fn()
    const { rerender } = render(<MonatStepper entries={E} jahr={2025} monat={12} onSelect={onSelect} />)
    screen.getByLabelText('ein Jahr zurück').click() // 2024-12 existiert
    expect(onSelect).toHaveBeenLastCalledWith(2024, 12)
    rerender(<MonatStepper entries={E} jahr={2025} monat={11} onSelect={onSelect} />)
    expect(screen.getByLabelText('ein Jahr zurück')).toBeDisabled() // 2024-11 fehlt
  })

  it('Ränder deaktivieren die Zurück-Buttons', () => {
    const onSelect = vi.fn()
    render(<MonatStepper entries={E} jahr={2024} monat={12} onSelect={onSelect} />)
    expect(screen.getByLabelText('voriger Monat')).toBeDisabled()
    expect(screen.getByLabelText('ältester Monat')).toBeDisabled()
    expect(screen.getByLabelText('nächster Monat')).not.toBeDisabled()
  })

  it('Mitte öffnet die Monatsliste → Auswahl schließt sie', () => {
    const onSelect = vi.fn()
    render(<MonatStepper entries={E} jahr={2025} monat={12} onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: /Dez 2025/ })) // Liste öffnen (State-Re-Render)
    fireEvent.click(screen.getByRole('button', { name: /Okt 2025/ }))
    expect(onSelect).toHaveBeenLastCalledWith(2025, 10)
  })
})
