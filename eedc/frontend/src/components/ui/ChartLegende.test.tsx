import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ChartLegende from './ChartLegende'

// Farbwerte als CSS-Keywords (kein Inline-Hex im Test — Design-Wächter); die
// Komponente reicht den String nur an `style.backgroundColor` durch.
const payload = [
  { value: 'pv', color: 'orange', dataKey: 'pv', type: 'line' },
  { value: 'netz', color: 'red', dataKey: 'netz', type: 'line', inactive: true },
]

describe('ChartLegende', () => {
  it('rendert Viereck-Swatch (rounded-sm, kein Kreis) + monochromen Text', () => {
    const { container } = render(<ChartLegende payload={payload} />)
    const swatches = container.querySelectorAll('span.rounded-sm')
    expect(swatches.length).toBe(2)
    // kein runder Marker (S1: Viereck statt Kreis)
    expect(container.querySelector('.rounded-full')).toBeNull()
    // Text monochrom (Theme-Token, nicht serienfarbig); Default-Label aus dem
    // CHART_LABELS-Kanon (Regel D): dataKey 'pv' → 'PV'.
    expect(screen.getByText('PV').className).toContain('text-gray-600')
  })

  it('formatter mappt dataKey → Anzeigename', () => {
    render(<ChartLegende payload={payload} formatter={(v) => (v === 'pv' ? 'PV-Erzeugung' : v)} />)
    expect(screen.getByText('PV-Erzeugung')).toBeInTheDocument()
  })

  it('inaktive Serie wird gedimmt (opacity-40)', () => {
    render(<ChartLegende payload={payload} />)
    const li = screen.getByText('netz').closest('li')
    expect(li?.className).toContain('opacity-40')
  })

  it('onItemClick feuert mit dem Eintrag (Serie an/aus)', () => {
    const onItemClick = vi.fn()
    render(<ChartLegende payload={payload} onItemClick={onItemClick} />)
    fireEvent.click(screen.getByText('PV'))
    expect(onItemClick).toHaveBeenCalledWith(expect.objectContaining({ dataKey: 'pv' }))
  })

  it('rendert nichts ohne payload', () => {
    const { container } = render(<ChartLegende payload={[]} />)
    expect(container.firstChild).toBeNull()
  })
})
