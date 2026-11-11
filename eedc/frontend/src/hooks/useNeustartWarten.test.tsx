/**
 * E5.7 L5 (Lab rc29): nach «Neustart» fragt eedc `/api/health` alle 2 s — `healthy` ⇒ Seite neu laden; nach 90 s ohne
 * Antwort der Satz, und der Knopf ist wieder frei. Gefälschte Uhr.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { act, renderHook } from '@testing-library/react'

const health = vi.fn()
vi.mock('../api/system', () => ({ systemApi: { health: () => health() } }))

import { NEUSTART_ZU_LANG, useNeustartWarten } from './useNeustartWarten'

describe('useNeustartWarten', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(2026, 10, 11, 9))
    health.mockReset()
  })
  afterEach(() => { vi.useRealTimers() })

  it('lädt neu, sobald eedc wieder antwortet', async () => {
    const neuLaden = vi.fn()
    health.mockRejectedValueOnce(new Error('weg')).mockResolvedValueOnce({ status: 'healthy' })
    const { result } = renderHook(() => useNeustartWarten(neuLaden))
    act(() => { void result.current.warten() })
    expect(result.current.wartet).toBe(true)
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(neuLaden).not.toHaveBeenCalled()
    await act(async () => { await vi.advanceTimersByTimeAsync(2000) })
    expect(neuLaden).toHaveBeenCalledTimes(1)
  })

  it('nach 90 s ohne Antwort: der Satz, der Knopf ist wieder frei', async () => {
    const neuLaden = vi.fn()
    health.mockRejectedValue(new Error('weg'))
    const { result } = renderHook(() => useNeustartWarten(neuLaden))
    act(() => { void result.current.warten() })
    await act(async () => { await vi.advanceTimersByTimeAsync(92000) })
    expect(neuLaden).not.toHaveBeenCalled()
    expect(result.current.wartet).toBe(false)
    expect(result.current.hinweis).toBe(NEUSTART_ZU_LANG)
  })

  it('E6.B G1: wartet ab dem ersten Moment, fragt aber erst nach dem Neustart-Aufruf', async () => {
    const neuLaden = vi.fn()
    health.mockResolvedValue({ status: 'healthy' })  // das alte eedc antwortet noch
    let aufrufZurueck: () => void = () => {}
    const aufruf = vi.fn(() => new Promise<void>((r) => { aufrufZurueck = r }))
    const { result } = renderHook(() => useNeustartWarten(neuLaden))
    act(() => { void result.current.warten(aufruf) })
    expect(aufruf).toHaveBeenCalledTimes(1)
    expect(result.current.wartet).toBe(true)
    await act(async () => { await vi.advanceTimersByTimeAsync(6000) })
    expect(health).not.toHaveBeenCalled()
    expect(neuLaden).not.toHaveBeenCalled()
    await act(async () => { aufrufZurueck(); await vi.advanceTimersByTimeAsync(2000) })
    expect(neuLaden).toHaveBeenCalledTimes(1)
  })
})
