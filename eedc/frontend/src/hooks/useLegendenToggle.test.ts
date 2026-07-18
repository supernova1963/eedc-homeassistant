/**
 * useLegendenToggle — SoT der Legenden-Toggle-Mechanik (Style-Guide B7).
 * Sichert: Toggle an/aus, dataKey-Fallback auf value, Reset NUR bei
 * resetSignal-WECHSEL (nicht beim Mount/Re-Render mit gleichem Signal).
 */
import { describe, it, expect } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { useLegendenToggle } from './useLegendenToggle'

describe('useLegendenToggle', () => {
  it('toggelt eine Serie aus und wieder ein', () => {
    const { result } = renderHook(() => useLegendenToggle())
    expect(result.current.istVersteckt('einspeisung')).toBe(false)

    act(() => result.current.toggleSerie('einspeisung'))
    expect(result.current.istVersteckt('einspeisung')).toBe(true)
    expect(result.current.istVersteckt('netzbezug')).toBe(false)

    act(() => result.current.toggleSerie('einspeisung'))
    expect(result.current.istVersteckt('einspeisung')).toBe(false)
  })

  it('onItemClick nutzt dataKey, fällt auf value zurück', () => {
    const { result } = renderHook(() => useLegendenToggle())
    act(() => result.current.onItemClick({ value: 'Einspeisung', dataKey: 'einspeisung' }))
    expect(result.current.istVersteckt('einspeisung')).toBe(true)

    act(() => result.current.onItemClick({ value: 'Autarkie' }))
    expect(result.current.istVersteckt('Autarkie')).toBe(true)
  })

  it('resettet bei resetSignal-Wechsel, nicht bei gleichem Signal', () => {
    const { result, rerender } = renderHook(({ signal }) => useLegendenToggle(signal), {
      initialProps: { signal: 'erzeugung' },
    })
    act(() => result.current.toggleSerie('einspeisung'))
    expect(result.current.istVersteckt('einspeisung')).toBe(true)

    rerender({ signal: 'erzeugung' })
    expect(result.current.istVersteckt('einspeisung')).toBe(true)

    rerender({ signal: 'verbrauch' })
    expect(result.current.istVersteckt('einspeisung')).toBe(false)
  })
})
