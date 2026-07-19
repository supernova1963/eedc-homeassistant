/**
 * R20-6 (Rainer): Betrag-Felder der Sonstigen Positionen normalisieren bei Blur
 * auf 2 Nachkommastellen (de-DE, „8" → „8,00"). Test am SUT-Symbol.
 */
import { describe, it, expect } from 'vitest'
import { useState } from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { SonstigePositionenFields } from './SonstigePositionenFields'
import type { SonstigePosition } from '../../types'

const pos = (over: Partial<SonstigePosition> = {}): SonstigePosition => ({
  bezeichnung: 'Zählergebühr', betrag: 0, typ: 'ausgabe', ...over,
})

/** Zustandsbehafteter Host — wie das echte Formular reflektiert er `onChange`
 *  zurück in `positionen` (die Betrag-Formatierung braucht den geführten Wert). */
function Host({ initial }: { initial: SonstigePosition[] }) {
  const [positionen, setPositionen] = useState(initial)
  return <SonstigePositionenFields positionen={positionen} onChange={setPositionen} />
}

const betragFeld = () => screen.getByLabelText(/^Betrag Position 1/) as HTMLInputElement

describe('SonstigePositionenFields — Betrag-Format (R20-6)', () => {
  it('zeigt den Bestandswert mit 2 Nachkommastellen (de-DE)', () => {
    render(<Host initial={[pos({ betrag: 8 })]} />)
    expect(betragFeld().value).toBe('8,00')
  })

  it('normalisiert bei Blur „8" → „8,00"', () => {
    render(<Host initial={[pos({ betrag: 0 })]} />)
    const feld = betragFeld()
    fireEvent.focus(feld)
    fireEvent.change(feld, { target: { value: '8' } })
    fireEvent.blur(feld)
    expect(feld.value).toBe('8,00')
  })

  it('akzeptiert Komma-Eingabe „12,5" → „12,50"', () => {
    render(<Host initial={[pos({ betrag: 0 })]} />)
    const feld = betragFeld()
    fireEvent.focus(feld)
    fireEvent.change(feld, { target: { value: '12,5' } })
    fireEvent.blur(feld)
    expect(feld.value).toBe('12,50')
  })

  it('parst Tausenderpunkt + Komma „1.234,56" korrekt', () => {
    render(<Host initial={[pos({ betrag: 0 })]} />)
    const feld = betragFeld()
    fireEvent.focus(feld)
    fireEvent.change(feld, { target: { value: '1.234,56' } })
    fireEvent.blur(feld)
    expect(feld.value).toBe('1.234,56')
  })
})
