import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { EinstellungenModalHost, wizardTitel, type WizardKey } from './EinstellungenModalHost'

// IA-V4 Einstellungen-Umbau, Schritt 1: der Modal-Host für die Wizard-Seiten. Getestet mit
// einer Stub-Registry (kein Import der schweren IST-Wizards in jsdom) — geprüft wird nur die
// Host-Mechanik: geschlossen = nichts, offen = Modal mit Titel + Inhalt, Schließen ruft onClose.

const stubRegistry = {
  'csv-import': { titel: 'CSV importieren', Comp: () => <div>WIZARD-INHALT</div> },
} as unknown as Record<WizardKey, { titel: string; Comp: React.ComponentType }>

describe('EinstellungenModalHost (IA-V4 Einstellungen)', () => {
  it('rendert nichts, wenn kein Wizard offen ist', () => {
    const { container } = render(<EinstellungenModalHost offen={null} onClose={vi.fn()} registry={stubRegistry} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('öffnet den Wizard im Modal mit Titel und Inhalt', () => {
    render(<EinstellungenModalHost offen="csv-import" onClose={vi.fn()} registry={stubRegistry} />)
    expect(screen.getByRole('heading', { name: 'CSV importieren' })).toBeInTheDocument()
    expect(screen.getByText('WIZARD-INHALT')).toBeInTheDocument()
  })

  it('ruft onClose beim Schließen', () => {
    const onClose = vi.fn()
    render(<EinstellungenModalHost offen="csv-import" onClose={onClose} registry={stubRegistry} />)
    fireEvent.click(screen.getByRole('button', { name: 'Schließen' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('wizardTitel liefert den Klartext-Titel', () => {
    expect(wizardTitel('csv-import', stubRegistry)).toBe('CSV importieren')
  })
})
