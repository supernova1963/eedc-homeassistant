/**
 * Der Client muss ZWEI Server-Stände bedienen (#387).
 *
 * Am 01.09.2026 wird nur der Community-**Server** umgestellt — das Add-on
 * bleibt auf der Version, die heute ausgeliefert wird. Diese Datei hält fest,
 * dass die Anzeige beides trägt, ohne dass jemand den Client anfasst:
 *
 * - **bis zum 01.09.** sendet der Server `basis_monate` nicht ⇒ keine
 *   Kennzeichnung, keine Textänderung, alles wie bisher;
 * - **ab dem 01.09.** sendet er es ⇒ ein hochgerechneter Wert sagt, worauf er
 *   beruht.
 *
 * Ohne den ersten Fall wäre die Auslieferung ein Blindflug: Der Server, gegen
 * den v4.0.22 zuerst läuft, kennt die Felder gar nicht.
 */

import { describe, expect, it } from 'vitest'
import {
  hatJahresfenster,
  jahresfensterHinweis,
  jahresfensterKennzeichnung,
} from './communityFenster'
import type { BenchmarkData } from '../api/community'

const basis = {
  spez_ertrag_durchschnitt: 840,
  spez_ertrag_region: 865,
  anzahl_anlagen_gesamt: 112,
  anzahl_anlagen_region: 23,
} as unknown as BenchmarkData

function b(over: Partial<BenchmarkData>): BenchmarkData {
  return { ...basis, ...over } as BenchmarkData
}

describe('Server-Stand bis zum 01.09.2026 (rechnet flach, sendet basis_monate nicht)', () => {
  it('zeigt keine Kennzeichnung', () => {
    expect(jahresfensterKennzeichnung(b({ spez_ertrag_anlage: 1207.8 }))).toBeNull()
  })

  it('zeigt keinen Hinweis — es gibt ja einen Wert', () => {
    expect(jahresfensterHinweis(b({ spez_ertrag_anlage: 1207.8 }))).toBeNull()
  })
})

describe('Server-Stand ab dem 01.09.2026 (rechnet saisonal, sendet basis_monate)', () => {
  it('kennzeichnet einen hochgerechneten Wert', () => {
    const text = jahresfensterKennzeichnung(
      b({ spez_ertrag_anlage: 979, basis_monate: 5, fenster_monate: 12 }),
    )
    expect(text).toBe('hochgerechnet aus 5 von 12 Monaten')
  })

  it('kennzeichnet ein volles Jahr NICHT', () => {
    expect(
      jahresfensterKennzeichnung(
        b({ spez_ertrag_anlage: 1118.7, basis_monate: 12, fenster_monate: 12 }),
      ),
    ).toBeNull()
  })

  it('ersetzt den Wert nicht, sondern steht daneben', () => {
    const daten = b({ spez_ertrag_anlage: 979, basis_monate: 5 })
    expect(hatJahresfenster(daten)).toBe(true)
    expect(jahresfensterHinweis(daten)).toBeNull()
  })
})

describe('der einzige Fall ohne Jahreswert', () => {
  it('nennt veraltete Daten beim Namen und sagt, was hilft', () => {
    const text = jahresfensterHinweis(
      b({ spez_ertrag_anlage: null, basis_veraltet: true }) as BenchmarkData,
    )
    expect(text).toContain('älter als ein Jahr')
    expect(text).toContain('erneut')
  })

  it('macht keine Zusage, wann der Vergleich kommt', () => {
    const text = jahresfensterHinweis(b({ spez_ertrag_anlage: null }) as BenchmarkData) ?? ''
    expect(text).not.toMatch(/\b(Woche|Monat 20|Termin|bald)\b/)
  })
})
