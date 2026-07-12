/**
 * ErfassungZustandBadge (Monatsabschluss-V4, Bündel 1 / V-c) — hält das Zustands-
 * Vokabular fest: die vier Zustände tragen die aus der Status-Achse abgeleiteten
 * Töne (gemessen=grün, geschätzt=gelb, fehlt=grau, weicht-ab=orange) und dieselbe
 * Icon-/Label-Quelle. Signal-Rot ist bewusst KEIN Zustand hier (harten Fehlern
 * vorbehalten).
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ErfassungZustandBadge, { ZUSTAND_META, type ErfassungZustand } from './ErfassungZustandBadge'
import { ERFASSUNG_ZUSTAND } from '../../lib/colors'

describe('ErfassungZustandBadge — Zustands-Vokabular', () => {
  it('deckt genau die sechs Zustände ab (Meta ≡ Farb-SoT)', () => {
    const zustaende = Object.keys(ZUSTAND_META).sort()
    expect(zustaende).toEqual(['fehlt', 'gemessen', 'geprueft', 'geschaetzt', 'optional', 'weicht_ab'])
    expect(Object.keys(ERFASSUNG_ZUSTAND).sort()).toEqual(zustaende)
  })

  it('bildet die abgestimmten Töne ab und meidet Signal-Rot', () => {
    expect(ERFASSUNG_ZUSTAND.gemessen.text).toContain('green')
    expect(ERFASSUNG_ZUSTAND.geprueft.text).toContain('green') // geprüft teilt das Grün
    expect(ERFASSUNG_ZUSTAND.geschaetzt.text).toContain('yellow')
    expect(ERFASSUNG_ZUSTAND.fehlt.text).toContain('gray')
    expect(ERFASSUNG_ZUSTAND.optional.text).toContain('gray')
    expect(ERFASSUNG_ZUSTAND.weicht_ab.text).toContain('orange')
    // kein Zustand trägt Signal-Rot (bleibt harten Blockier-Fehlern vorbehalten)
    for (const z of Object.values(ERFASSUNG_ZUSTAND)) {
      expect(z.text).not.toContain('red')
      expect(z.badge).not.toContain('red')
    }
  })

  it('rendert Label + Quell-Zusatz als Pill', () => {
    render(<ErfassungZustandBadge zustand="geschaetzt" quelleLabel="Vorjahr" />)
    expect(screen.getByText('geschätzt (Vorjahr)')).toBeInTheDocument()
  })

  it('iconOnly rendert nur das Icon mit zugänglichem Label', () => {
    const { container } = render(<ErfassungZustandBadge zustand="fehlt" iconOnly />)
    expect(container.querySelector('span')).toBeNull()
    expect(screen.getByRole('img', { name: 'offen' })).toBeInTheDocument()
  })

  it('nutzt für jeden Zustand ein Icon aus der zentralen Meta-Quelle', () => {
    ;(Object.keys(ZUSTAND_META) as ErfassungZustand[]).forEach((z) => {
      expect(ZUSTAND_META[z].Icon).toBeTypeOf('object')
    })
  })
})
