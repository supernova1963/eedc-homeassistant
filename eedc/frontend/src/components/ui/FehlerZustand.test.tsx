import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import FehlerZustand from './FehlerZustand'

// R3b S15: DER B8-Fehler-Baustein — Alert-error-Optik + optionales Retry.
// Strukturkritische Invarianten: IST-Text unverändert, Retry-Knopf nur mit
// onRetry (kein Fassade-Knopf), Klick löst den Callback aus.

describe('FehlerZustand (SoT, B8)', () => {
  it('rendert den IST-Fehlertext unverändert in Alert-error-Optik', () => {
    render(<FehlerZustand text="Fehler beim Laden der Tageswerte" />)
    expect(screen.getByText('Fehler beim Laden der Tageswerte')).toBeInTheDocument()
    // Kein Retry-Knopf ohne onRetry — keine Fassade-Affordance.
    expect(screen.queryByRole('button', { name: /Erneut versuchen/ })).not.toBeInTheDocument()
  })

  it('bietet Retry nur mit onRetry an und löst ihn per Klick aus', () => {
    const onRetry = vi.fn()
    render(<FehlerZustand text="Fehler beim Laden des Jahres" onRetry={onRetry} />)
    const knopf = screen.getByRole('button', { name: /Erneut versuchen/ })
    fireEvent.click(knopf)
    expect(onRetry).toHaveBeenCalledTimes(1)
  })

  it('rendert die optionale Überschrift (Alert-title)', () => {
    render(<FehlerZustand titel="Werte-Werkbank" text="Fehler beim Laden der Werte" />)
    expect(screen.getByText('Werte-Werkbank')).toBeInTheDocument()
  })
})
