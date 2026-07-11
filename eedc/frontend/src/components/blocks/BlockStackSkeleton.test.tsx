import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { BlockStackSkeleton } from './BlockStackSkeleton'

// R3b S15: B8-Lade-Skeleton in BlockShell-Form. Strukturkritische Invarianten:
// IST-Ladetext für Screenreader sofort (sr-only + aria) UND sichtbar nach ~400 ms
// (R18-13, rapahl #213/#218 — Wartezeit erklären statt stumm), Blockzahl
// steuerbar (deterministische Sichten), Pillen-Zeile optional.

afterEach(() => vi.useRealTimers())

describe('BlockStackSkeleton (SoT, B8 + R18-13)', () => {
  it('trägt den IST-Ladetext als role=status + sr-only (Screenreader-Parität)', () => {
    render(<BlockStackSkeleton label="Lade Monat…" />)
    const status = screen.getByRole('status', { name: 'Lade Monat…' })
    expect(status).toHaveAttribute('aria-busy', 'true')
    const kopien = screen.getAllByText('Lade Monat…')
    expect(kopien.some((el) => el.classList.contains('sr-only'))).toBe(true)
  })

  it('blendet den sichtbaren Ladetext erst nach ~400 ms ein (R18-13, kein Flackern)', () => {
    vi.useFakeTimers()
    render(<BlockStackSkeleton label="Lade Aussicht…" />)
    const sichtbar = () =>
      screen.getAllByText('Lade Aussicht…').find((el) => !el.classList.contains('sr-only'))!
    // Platz sofort reserviert (kein Layout-Sprung), aber noch unsichtbar …
    expect(sichtbar()).toHaveClass('opacity-0')
    // … und nach der Verzögerung eingeblendet.
    act(() => vi.advanceTimersByTime(450))
    expect(sichtbar()).toHaveClass('opacity-100')
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
