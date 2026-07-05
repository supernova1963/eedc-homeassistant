import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BlockStackSkeleton } from './BlockStackSkeleton'

// R3b S15: B8-Lade-Skeleton in BlockShell-Form. Strukturkritische Invarianten:
// IST-Ladetext bleibt für Screenreader erhalten (sr-only + aria), Blockzahl
// steuerbar (deterministische Sichten), Pillen-Zeile optional.

describe('BlockStackSkeleton (SoT, B8)', () => {
  it('trägt den IST-Ladetext als role=status + sr-only (Screenreader-Parität)', () => {
    render(<BlockStackSkeleton label="Lade Monat…" />)
    const status = screen.getByRole('status', { name: 'Lade Monat…' })
    expect(status).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByText('Lade Monat…')).toHaveClass('sr-only')
  })

  it('rendert offen=null nur zugeklappte Block-Köpfe (deterministische Sichten)', () => {
    const { container } = render(<BlockStackSkeleton label="Lade Komponenten…" offen={null} zu={7} />)
    expect(container.querySelectorAll('.rounded-xl.border').length).toBe(7)
  })

  it('rendert die optionale Pillen-Zeile (Tab-Platzhalter, 32-px-Maß)', () => {
    const { container } = render(<BlockStackSkeleton label="Lade Komponenten…" pillen={4} />)
    expect(container.querySelectorAll('.h-8.w-24').length).toBe(4)
  })
})
