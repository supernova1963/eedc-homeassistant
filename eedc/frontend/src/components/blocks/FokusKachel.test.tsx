import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FokusKachel } from './FokusKachel'

describe('FokusKachel', () => {
  it('zeigt Inhalt + ⤢ und schaltet auf Vollbild (Zurück) um', () => {
    render(
      <FokusKachel titel="Energiefluss">
        <p>Karten-Inhalt</p>
      </FokusKachel>,
    )
    expect(screen.getByText('Karten-Inhalt')).toBeInTheDocument()
    expect(screen.queryByText('Zurück')).not.toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Energiefluss: Fokus / Vollbild'))
    // Im Vollbild: Titel-Header + Zurück, Inhalt nur einmal (im Overlay).
    expect(screen.getByText('Zurück')).toBeInTheDocument()
    expect(screen.getByText('Energiefluss')).toBeInTheDocument()
    expect(screen.getAllByText('Karten-Inhalt')).toHaveLength(1)

    fireEvent.click(screen.getByText('Zurück'))
    expect(screen.queryByText('Zurück')).not.toBeInTheDocument()
    expect(screen.getByText('Karten-Inhalt')).toBeInTheDocument()
  })

  it('blendet den Titel in der Kartenkopfzeile nur mit zeigeTitel ein', () => {
    const { rerender } = render(<FokusKachel titel="Temperaturen"><span>x</span></FokusKachel>)
    expect(screen.queryByText('Temperaturen')).not.toBeInTheDocument() // nur im Vollbild

    rerender(<FokusKachel titel="Temperaturen" zeigeTitel><span>x</span></FokusKachel>)
    expect(screen.getByText('Temperaturen')).toBeInTheDocument()
  })
})
