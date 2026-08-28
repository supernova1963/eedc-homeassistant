import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { DatumPicker } from './DatumPicker'

// Slice A (D13-4/9/11/12): der EINE Custom-DatumPicker ersetzt native date/month-
// Felder in der IA-V4. Diese Tests sichern das Kernverhalten beider Modi (Trigger-
// Label ausgeschrieben, Auswahl liefert das ISO-Format der nativen Inputs) und die
// min/max-Klemmung (D12-8), damit die Umstellung nicht still bricht.

describe('DatumPicker — Monats-Modus', () => {
  it('zeigt das gewählte Datum ausgeschrieben und liefert YYYY-MM bei Auswahl', () => {
    const onChange = vi.fn()
    render(<DatumPicker modus="monat" value="2026-06" onChange={onChange} ariaLabel="Monat" />)
    // Trigger trägt das ausgeschriebene Format (nicht „2026-06").
    expect(screen.getByRole('button', { name: 'Monat' })).toHaveTextContent('Juni 2026')
    fireEvent.click(screen.getByRole('button', { name: 'Monat' }))
    fireEvent.click(screen.getByRole('button', { name: 'Aug' }))
    expect(onChange).toHaveBeenCalledWith('2026-08')
  })
})

describe('DatumPicker — Tages-Modus', () => {
  it('zeigt „23. Juni 2026" und liefert YYYY-MM-DD bei Tagesauswahl', () => {
    const onChange = vi.fn()
    render(<DatumPicker modus="tag" value="2026-06-23" onChange={onChange} ariaLabel="Tag" />)
    expect(screen.getByRole('button', { name: 'Tag' })).toHaveTextContent('23. Juni 2026')
    fireEvent.click(screen.getByRole('button', { name: 'Tag' }))
    fireEvent.click(screen.getByRole('button', { name: '20' }))
    expect(onChange).toHaveBeenCalledWith('2026-06-20')
  })

  it('klemmt Tage außerhalb min/max (D12-8): der 10. ist vor min deaktiviert', () => {
    const onChange = vi.fn()
    render(<DatumPicker modus="tag" value="2026-06-23" min="2026-06-15" max="2026-06-28" onChange={onChange} ariaLabel="Tag" />)
    fireEvent.click(screen.getByRole('button', { name: 'Tag' }))
    const tag10 = screen.getByRole('button', { name: '10' })
    expect(tag10).toBeDisabled()
    fireEvent.click(tag10)
    expect(onChange).not.toHaveBeenCalled()
  })
})

describe('DatumPicker — ESC (Nachrang-Konvention)', () => {
  it('ESC schließt nur das Popover und meldet die Taste als verbraucht', () => {
    render(<DatumPicker modus="monat" value="2026-06" onChange={vi.fn()} ariaLabel="Monat" />)
    fireEvent.click(screen.getByRole('button', { name: 'Monat' }))
    expect(screen.getByRole('button', { name: 'Aug' })).toBeInTheDocument()

    // `fireEvent` liefert false, wenn ein Zuhörer preventDefault gerufen hat.
    const verbraucht = !fireEvent.keyDown(document, { key: 'Escape' })

    expect(screen.queryByRole('button', { name: 'Aug' })).not.toBeInTheDocument()
    // Ohne diese Meldung nähme ESC in Cockpit/Tag und /Monat zusätzlich das
    // umgebende `blocks/FokusVollbild` mit.
    expect(verbraucht).toBe(true)
  })
})
