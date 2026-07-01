import { describe, it, expect, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { FormBlock, type FormBlockFeld } from './FormBlock'

// IA-V4 Einstellungen-Umbau, Schritt 1: die editierbare FormBlock-SoT. Geprüft werden die
// tragenden Invarianten (Dirty→Speichern, Validierung, onSave-Werte, Park-Inertheit, Toggle).

const textFeld = (over: Partial<Extract<FormBlockFeld, { typ: 'text' }>> = {}): FormBlockFeld => ({
  id: 'name', label: 'Name', typ: 'text', wert: 'Haus', ...over,
})

describe('FormBlock (SoT, IA-V4 Einstellungen)', () => {
  it('rendert Felder; Speichern ist ohne Änderung deaktiviert', () => {
    render(<FormBlock felder={[textFeld()]} onSave={vi.fn()} />)
    expect(screen.getByDisplayValue('Haus')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeDisabled()
  })

  it('aktiviert Speichern bei Änderung und übergibt die Werte an onSave', async () => {
    const onSave = vi.fn()
    render(<FormBlock felder={[textFeld()]} onSave={onSave} />)
    fireEvent.change(screen.getByDisplayValue('Haus'), { target: { value: 'Haus Neu' } })
    const btn = screen.getByRole('button', { name: /Speichern/ })
    expect(btn).toBeEnabled()
    await act(async () => { fireEvent.click(btn) })
    expect(onSave).toHaveBeenCalledWith({ name: 'Haus Neu' })
  })

  it('blockiert Speichern und zeigt Fehler bei leerem Pflichtfeld (nach Berührung)', () => {
    render(<FormBlock felder={[textFeld({ wert: '', pflicht: true })]} onSave={vi.fn()} />)
    const input = screen.getByRole('textbox')
    fireEvent.change(input, { target: { value: 'A' } })   // dirty, gültig → aktiv
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeEnabled()
    fireEvent.change(input, { target: { value: '' } })     // berührt + leer → Fehler
    expect(screen.getByText('Pflichtfeld')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeDisabled()
  })

  it('respektiert eine eigene validate-Funktion', () => {
    const feld = textFeld({ wert: 'ok', validate: (v) => ((v as string).length < 3 ? 'zu kurz' : null) })
    render(<FormBlock felder={[feld]} onSave={vi.fn()} />)
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'ab' } })
    expect(screen.getByText('zu kurz')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeDisabled()
  })

  it('rendert ein parkId-Feld auch ohne ParkProvider (inert)', () => {
    render(<FormBlock felder={[textFeld({ parkId: 'einst-name' })]} onSave={vi.fn()} />)
    expect(screen.getByDisplayValue('Haus')).toBeInTheDocument()
  })

  it('schaltet ein Toggle-Feld und macht den Block dirty', () => {
    render(
      <FormBlock
        felder={[{ id: 'aktiv', label: 'Aktiv', typ: 'toggle', wert: false }]}
        onSave={vi.fn()}
      />,
    )
    const sw = screen.getByRole('switch')
    expect(sw).toHaveAttribute('aria-checked', 'false')
    fireEvent.click(sw)
    expect(sw).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('button', { name: /Speichern/ })).toBeEnabled()
  })
})
