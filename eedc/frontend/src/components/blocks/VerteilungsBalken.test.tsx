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
