/**
 * E4 (Entscheid Master H-E4-B, Option A): ein laufender Sprung aufs Feld (`SprungFeldKontext`) öffnet zugeklappte
 * Abschnitte — `FormSection variant="erweitert"` und `CollapsibleSection` (Solarprognose «Neue Prognose abrufen» mit den
 * Systemverlusten). Ohne Sprung bleibt alles wie bisher; die `CollapsibleSection` merkt sich das Öffnen durch den
 * Sprung nicht (kein Eintrag in `localStorage`), erst ein Klick des Anwenders.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import FormSection from './FormSection'
import CollapsibleSection from './CollapsibleSection'
import { SprungFeldKontext, basisFeldKey, feldSelektor } from '../../lib/sprungFeld'

beforeEach(() => localStorage.clear())

describe('Zugeklappte Abschnitte beim Sprung aufs Feld', () => {
  it('FormSection «erweitert»: mit Sprung offen, ohne zu', () => {
    const { unmount } = render(
      <SprungFeldKontext.Provider value={feldSelektor('x')}>
        <FormSection variant="erweitert" title="Weitere"><input name="x" /></FormSection>
      </SprungFeldKontext.Provider>,
    )
    expect(document.querySelector('[name="x"]')).not.toBeNull()
    unmount()
    render(<FormSection variant="erweitert" title="Weitere"><input name="x" /></FormSection>)
    expect(document.querySelector('[name="x"]')).toBeNull()
  })

  it('CollapsibleSection: mit Sprung offen, ohne Spur im Speicher; ein Klick merkt sich wieder', () => {
    render(
      <SprungFeldKontext.Provider value={feldSelektor('system_losses')}>
        <CollapsibleSection storageKey="t" title="Neue Prognose abrufen" defaultOpen={false}>
          <input name="system_losses" />
        </CollapsibleSection>
      </SprungFeldKontext.Provider>,
    )
    expect(document.querySelector('[name="system_losses"]')).not.toBeNull()
    expect(localStorage.getItem('eedc-collapse-t')).toBeNull()
    fireEvent.click(screen.getByText('Neue Prognose abrufen'))
    expect(localStorage.getItem('eedc-collapse-t')).toBe('closed')
  })

  it('CollapsibleSection ohne Sprung: zu wie bisher', () => {
    render(
      <CollapsibleSection storageKey="u" title="Neue Prognose abrufen" defaultOpen={false}>
        <input name="system_losses" />
      </CollapsibleSection>,
    )
    expect(document.querySelector('[name="system_losses"]')).toBeNull()
  })

  it('Selektor und Basis-Key', () => {
    expect(feldSelektor('jaz')).toBe('[name="jaz"], [name="param_jaz"], [data-feld="jaz"]')
    expect(basisFeldKey('betriebsmodus-3')).toBe('betriebsmodus')
    expect(basisFeldKey('ladung_kwh')).toBe('ladung_kwh')
    expect(basisFeldKey('-3')).toBe('-3')
  })
})
