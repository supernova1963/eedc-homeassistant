import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import Stepper from './Stepper'

// W1 (Style-Guide Teil D): EIN Stepper-SoT für Wizards. Diese Tests sichern die
// Kern-Semantik (erledigt=Häkchen, offen=Nummer, nur Erledigte klickbar), damit
// die Umstellung der Wizards nicht still bricht.

const SCHRITTE = [
  { titel: 'Verbinden' },
  { titel: 'Zeitraum' },
  { titel: 'Vorschau' },
  { titel: 'Ergebnis' },
]

describe('Stepper', () => {
  it('zeigt erledigte Schritte mit Häkchen und offene mit Nummer', () => {
    render(<Stepper schritte={SCHRITTE} aktuell={2} />)
    // Aktueller Schritt (Index 2) trägt seine Nummer „3", offener (Index 3) „4".
    expect(screen.getByText('3')).toBeInTheDocument()
    expect(screen.getByText('4')).toBeInTheDocument()
    // Erledigte (Index 0,1) tragen keine Nummer mehr (Häkchen-Icon statt Ziffer).
    expect(screen.queryByText('1')).not.toBeInTheDocument()
    expect(screen.queryByText('2')).not.toBeInTheDocument()
  })

  it('macht nur erledigte Schritte klickbar (Zurückspringen)', () => {
    const onKlick = vi.fn()
    render(<Stepper schritte={SCHRITTE} aktuell={2} onSchrittKlick={onKlick} />)
    // Erledigt → Button vorhanden und klickbar.
    fireEvent.click(screen.getByRole('button', { name: /Verbinden/ }))
    expect(onKlick).toHaveBeenCalledWith(0)
    // Offener Schritt „Ergebnis" ist kein Button.
    expect(screen.queryByRole('button', { name: /Ergebnis/ })).not.toBeInTheDocument()
  })

  it('rendert ohne Klick-Handler reine Anzeige (keine Buttons)', () => {
    render(<Stepper schritte={SCHRITTE} aktuell={2} />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
