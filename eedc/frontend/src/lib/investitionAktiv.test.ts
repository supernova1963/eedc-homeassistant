/**
 * istAktivImMonat — Frontend-Spiegel des Backend-SoT (investition.py). Deckt die
 * 3-Achsen-Semantik ab: aktiv-Flag, Anschaffungs- und Stilllegungs-Fenster, inkl.
 * der teil-aktiven Rand-Monate.
 */
import { describe, it, expect } from 'vitest'
import { istAktivImMonat, type AktivPruefbar } from './investitionAktiv'

const inv = (p: Partial<AktivPruefbar>): AktivPruefbar => ({ aktiv: true, ...p })

describe('istAktivImMonat', () => {
  it('aktiv === false blendet immer aus (auch historisch)', () => {
    expect(istAktivImMonat(inv({ aktiv: false, anschaffungsdatum: '2020-01-01' }), 2024, 6)).toBe(false)
  })

  it('undefined aktiv gilt als aktiv (frisch, nicht persistiert)', () => {
    expect(istAktivImMonat({ anschaffungsdatum: '2023-06-01' }, 2024, 6)).toBe(true)
  })

  it('vor Anschaffung → raus (WP 2024-04 im Jan 2024)', () => {
    expect(istAktivImMonat(inv({ anschaffungsdatum: '2024-04-01' }), 2024, 1)).toBe(false)
  })

  it('Anschaffungsmonat zählt teil-aktiv mit', () => {
    expect(istAktivImMonat(inv({ anschaffungsdatum: '2024-04-15' }), 2024, 4)).toBe(true)
  })

  it('nach Anschaffung → drin', () => {
    expect(istAktivImMonat(inv({ anschaffungsdatum: '2023-06-01' }), 2024, 6)).toBe(true)
  })

  it('nach Stilllegung → raus', () => {
    expect(istAktivImMonat(inv({ anschaffungsdatum: '2020-01-01', stilllegungsdatum: '2024-03-31' }), 2024, 5)).toBe(false)
  })

  it('Stilllegungsmonat zählt teil-aktiv mit', () => {
    expect(istAktivImMonat(inv({ anschaffungsdatum: '2020-01-01', stilllegungsdatum: '2024-05-10' }), 2024, 5)).toBe(true)
  })

  it('innerhalb des Lebensfensters → drin', () => {
    expect(istAktivImMonat(inv({ anschaffungsdatum: '2023-06-01', stilllegungsdatum: '2025-12-31' }), 2024, 6)).toBe(true)
  })

  it('ohne Datumsgrenzen → immer drin', () => {
    expect(istAktivImMonat(inv({}), 2019, 2)).toBe(true)
  })

  it('Februar-Monatsende korrekt (Schaltjahr 2024-02-29)', () => {
    // Anschaffung am 29.02.2024 → im Feb 2024 teil-aktiv, im Jan 2024 nicht.
    expect(istAktivImMonat(inv({ anschaffungsdatum: '2024-02-29' }), 2024, 2)).toBe(true)
    expect(istAktivImMonat(inv({ anschaffungsdatum: '2024-02-29' }), 2024, 1)).toBe(false)
  })

  it('ohne validen Monat entscheidet nur das aktiv-Flag', () => {
    expect(istAktivImMonat(inv({ anschaffungsdatum: '2030-01-01' }), NaN, NaN)).toBe(true)
    expect(istAktivImMonat(inv({ aktiv: false }), NaN, NaN)).toBe(false)
  })
})
