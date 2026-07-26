import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { VerteilungsBalken } from './VerteilungsBalken'

describe('VerteilungsBalken', () => {
  it('rendert Label · Wert · Prozent je Segment (Anteil an der Summe)', () => {
    render(
      <VerteilungsBalken
        titel="Test"
        segmente={[
          { label: 'A', wert: 30, farbe: 'bg-red-500' },
          { label: 'B', wert: 10, farbe: 'bg-blue-500' },
        ]}
      />,
    )
    expect(screen.getByText('Test')).toBeInTheDocument()
    expect(screen.getByText('30 kWh · 75 %')).toBeInTheDocument() // 30/40
    expect(screen.getByText('10 kWh · 25 %')).toBeInTheDocument() // 10/40
  })

  it('kennzeichnet gerechnete Werte über das Zustands-SoT-Badge + Erklärsatz (A3/a1)', () => {
    render(
      <VerteilungsBalken
        titel="Erzeugung nach Modul"
        herkunft={{
          zustand: 'geschaetzt',
          quelleLabel: 'kWp-Anteil',
          hinweis: 'Nicht gemessen, sondern anteilig nach kWp verteilt.',
        }}
        segmente={[{ label: 'Süddach', wert: 30, farbe: 'bg-red-500' }]}
      />,
    )
    // Badge = ErfassungZustandBadge iconOnly (aria-label „geschätzt (kWp-Anteil)")
    expect(screen.getByLabelText('geschätzt (kWp-Anteil)')).toBeInTheDocument()
    expect(screen.getByText('Nicht gemessen, sondern anteilig nach kWp verteilt.')).toBeInTheDocument()
  })

  it('ohne herkunft keine Kennzeichnung (gemessene Aufteilungen bleiben unmarkiert)', () => {
    render(<VerteilungsBalken titel="Verwendung" segmente={[{ label: 'A', wert: 5, farbe: 'bg-red-500' }]} />)
    expect(screen.queryByLabelText(/geschätzt/)).not.toBeInTheDocument()
  })

  it('rendert nichts bei Summe 0 (alle Segmente null/0)', () => {
    const { container } = render(
      <VerteilungsBalken
        segmente={[
          { label: 'A', wert: 0, farbe: 'bg-red-500' },
          { label: 'B', wert: null, farbe: 'bg-blue-500' },
        ]}
      />,
    )
    expect(container.firstChild).toBeNull()
  })
})
