/**
 * useDeepLinkFokus — SoT-Probe des Fokus-Deep-Link-Vertrags (FD-1).
 *
 * Sichert: `?fokus=` wird gelesen, `ansicht` nur als `tabelle`, fremde
 * Parameter bleiben unbeachtet, der Wert ist ein **Instanz-Memo** (ein
 * Hash-Wechsel nach dem Mount ändert ihn nicht, ein neuer Mount liest neu).
 *
 * ⚠ Die Proben setzen `window.location.hash` — NICHT `renderMitProvidern({ route })`.
 * Der füllt nur `MemoryRouter.initialEntries` und lässt `window.location`
 * unberührt; eine Probe darüber würde nichts über den Hook aussagen.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useDeepLinkFokus, leseDeepLinkFokus } from './useDeepLinkFokus'

const URSPRUNG = window.location.hash

describe('leseDeepLinkFokus (reine Auswertung)', () => {
  it('liest fokus und ansicht aus dem Hash-Query', () => {
    expect(leseDeepLinkFokus('#/cockpit/jahr?fokus=bilanz')).toEqual({
      fokusId: 'bilanz', ansicht: 'chart', deepLink: true,
    })
    expect(leseDeepLinkFokus('#/cockpit/jahr?fokus=bilanz&ansicht=tabelle')).toEqual({
      fokusId: 'bilanz', ansicht: 'tabelle', deepLink: true,
    })
  })

  it('ohne fokus ist es kein Deep-Link', () => {
    expect(leseDeepLinkFokus('#/cockpit/jahr')).toEqual({
      fokusId: null, ansicht: 'chart', deepLink: false,
    })
    expect(leseDeepLinkFokus('')).toEqual({ fokusId: null, ansicht: 'chart', deepLink: false })
    // Leerer Wert zählt nicht als Wunsch — sonst stünde das Hinweis-Overlay ohne Grund.
    expect(leseDeepLinkFokus('#/cockpit/jahr?fokus=').deepLink).toBe(false)
    expect(leseDeepLinkFokus('#/cockpit/jahr?fokus=%20%20').deepLink).toBe(false)
  })

  it('ansicht nimmt NUR `tabelle` an', () => {
    expect(leseDeepLinkFokus('#/x?fokus=a&ansicht=chart').ansicht).toBe('chart')
    expect(leseDeepLinkFokus('#/x?fokus=a&ansicht=Tabelle').ansicht).toBe('chart')
    expect(leseDeepLinkFokus('#/x?fokus=a&ansicht=unfug').ansicht).toBe('chart')
  })

  it('fremde Parameter laufen mit, ohne den Deep-Link zu stören', () => {
    const w = leseDeepLinkFokus('#/cockpit/monat?jahr=2025&monat=3&fokus=co2&h=kurz')
    expect(w).toEqual({ fokusId: 'co2', ansicht: 'chart', deepLink: true })
  })

  it('IDs mit Doppelpunkt (Live-Kacheln) überstehen die Auswertung', () => {
    expect(leseDeepLinkFokus('#/cockpit/live?fokus=live:tagesverlauf').fokusId).toBe('live:tagesverlauf')
    // Prozent-kodiert (so schreibt der Einbetten-Knopf sie) — dasselbe Ergebnis.
    expect(leseDeepLinkFokus('#/cockpit/live?fokus=live%3Atagesverlauf').fokusId).toBe('live:tagesverlauf')
  })
})

describe('useDeepLinkFokus (Instanz-Memo)', () => {
  beforeEach(() => { window.location.hash = '' })
  afterEach(() => { window.location.hash = URSPRUNG })

  it('liest beim Mount aus window.location.hash', () => {
    window.location.hash = '#/cockpit/jahr?fokus=bilanz&ansicht=tabelle'
    const { result } = renderHook(() => useDeepLinkFokus())
    expect(result.current).toEqual({ fokusId: 'bilanz', ansicht: 'tabelle', deepLink: true })
  })

  it('ein Hash-Wechsel NACH dem Mount ändert den Wert nicht — und ein neuer Mount liest neu', () => {
    window.location.hash = '#/cockpit/jahr?fokus=bilanz'
    const { result, rerender } = renderHook(() => useDeepLinkFokus())
    window.location.hash = '#/cockpit/jahr?fokus=co2'
    rerender()
    expect(result.current.fokusId).toBe('bilanz')

    const zweiter = renderHook(() => useDeepLinkFokus())
    expect(zweiter.result.current.fokusId).toBe('co2')
  })
})
