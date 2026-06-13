import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { KPICard } from './KPICard'

// E1-P3 Teil 0: erste Zielscheibe der Frontend-Test-Infra — die KPICard-SoT
// aus E1-P2. Kein Coverage-Ziel, nur die strukturkritischen Invarianten der
// einen Kachel-Komponente (Größen sm/md/lg, Einheit, Tooltip-Slot).

describe('KPICard (SoT, B9)', () => {
  it('rendert Titel, Wert und Einheit', () => {
    render(<KPICard title="PV-Erzeugung" value={1234} unit="kWh" />)
    expect(screen.getByText('PV-Erzeugung')).toBeInTheDocument()
    // Zahl wird de-DE formatiert (1.234)
    expect(screen.getByText('1.234')).toBeInTheDocument()
    expect(screen.getByText('kWh')).toBeInTheDocument()
  })

  it('rendert ein String-Value unverändert', () => {
    render(<KPICard title="Status" value="—" />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('rendert das Subtitle wenn gesetzt', () => {
    render(<KPICard title="Autarkie" value={72} unit="%" subtitle="ggü. Vormonat" />)
    expect(screen.getByText('ggü. Vormonat')).toBeInTheDocument()
  })

  it('macht die Kachel klickbar (onClick → button)', () => {
    let geklickt = false
    render(<KPICard title="Netto-Ertrag" value={42} onClick={() => { geklickt = true }} />)
    const btn = screen.getByRole('button')
    btn.click()
    expect(geklickt).toBe(true)
  })

  it('rendert alle drei Größen ohne Fehler', () => {
    for (const size of ['sm', 'md', 'lg'] as const) {
      const { unmount } = render(<KPICard title={`size-${size}`} value={1} size={size} />)
      expect(screen.getByText(`size-${size}`)).toBeInTheDocument()
      unmount()
    }
  })
})
