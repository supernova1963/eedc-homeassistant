import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { TagStepper } from './TagStepper'
import type { TagRailEintrag } from './TagesRail'

// (B) detLAN-Vollbild-Bug 2026-06-30: Die Pfeile springen NUR zu Tagen mit Daten
// (= `entries`, inkl. des immer angehängten „heute"); echte Lücken werden über-
// sprungen, heute bleibt erreichbar.
const entries: TagRailEintrag[] = [
  { datum: '2026-06-20', pv_kwh: 10, heute: false },
  { datum: '2026-06-22', pv_kwh: 8, heute: false },
  { datum: '2026-06-25', pv_kwh: 0, heute: true }, // heute, ohne Ertrag
]

describe('TagStepper — Pfeile überspringen Lücken (B)', () => {
  it('„voriger Tag mit Daten" springt über die Lücke (21.) auf den 20.', () => {
    const onSelect = vi.fn()
    render(<TagStepper entries={entries} datum="2026-06-22" onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: 'voriger Tag mit Daten' }))
    expect(onSelect).toHaveBeenCalledWith('2026-06-20')
  })

  it('„nächster Tag mit Daten" springt über die Lücke (23./24.) auf heute (25.)', () => {
    const onSelect = vi.fn()
    render(<TagStepper entries={entries} datum="2026-06-22" onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: 'nächster Tag mit Daten' }))
    expect(onSelect).toHaveBeenCalledWith('2026-06-25')
  })

  it('am neuesten Tag (heute) ist „nächster Tag mit Daten" deaktiviert', () => {
    render(<TagStepper entries={entries} datum="2026-06-25" onSelect={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'nächster Tag mit Daten' })).toBeDisabled()
  })
})
