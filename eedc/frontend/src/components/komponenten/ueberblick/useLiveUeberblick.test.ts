/**
 * Poll des Hub-Überblicks (P-433-2 E1, W10): Takte wie Cockpit → Live, kein
 * Poll bei unsichtbarer Seite, sofortiger Abruf bei Rückkehr, Unmount räumt die
 * Intervalle.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'

vi.mock('../../../api/liveDashboard', () => ({
  liveDashboardApi: {
    getData: vi.fn(() => Promise.resolve({ komponenten: [] })),
    getWetter: vi.fn(() => Promise.resolve({ aktuell: null })),
  },
}))
vi.mock('../../../api/energie_profil', () => ({
  energieProfilApi: { getTagDetail: vi.fn(() => Promise.resolve({ wp_geraete: [] })) },
}))

import { liveDashboardApi } from '../../../api/liveDashboard'
import { energieProfilApi } from '../../../api/energie_profil'
import { UEBERBLICK_LIVE_TAKT, UEBERBLICK_TAG_TAKT, UEBERBLICK_WETTER_TAKT, useLiveUeberblick } from './useLiveUeberblick'

let sichtbarkeit: DocumentVisibilityState = 'visible'
const setzeSichtbarkeit = (s: DocumentVisibilityState) => {
  sichtbarkeit = s
  document.dispatchEvent(new Event('visibilitychange'))
}

const getData = vi.mocked(liveDashboardApi.getData)
const getWetter = vi.mocked(liveDashboardApi.getWetter)
const getTag = vi.mocked(energieProfilApi.getTagDetail)

beforeEach(() => {
  vi.useFakeTimers()
  sichtbarkeit = 'visible'
  vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => sichtbarkeit)
  getData.mockClear(); getWetter.mockClear(); getTag.mockClear()
})
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('useLiveUeberblick', () => {
  it('Takte wie Cockpit → Live: Live 5 s, Wetter 5 min; Tag-Detail 5 min', () => {
    expect([UEBERBLICK_LIVE_TAKT, UEBERBLICK_WETTER_TAKT, UEBERBLICK_TAG_TAKT]).toEqual([5_000, 300_000, 300_000])
  })

  it('holt beim Mount alles einmal und pollt Live im 5-s-Takt (mit Demo-Schalter)', async () => {
    renderHook(() => useLiveUeberblick(3, true))
    expect(getData).toHaveBeenCalledTimes(1)
    expect(getData).toHaveBeenLastCalledWith(3, true)
    expect(getWetter).toHaveBeenCalledTimes(1)
    expect(getTag).toHaveBeenCalledTimes(1)
    await act(async () => { vi.advanceTimersByTime(15_000) })
    expect(getData).toHaveBeenCalledTimes(4)
    expect(getWetter).toHaveBeenCalledTimes(1)
    await act(async () => { vi.advanceTimersByTime(300_000) })
    expect(getWetter).toHaveBeenCalledTimes(2)
    expect(getTag).toHaveBeenCalledTimes(2)
  })

  it('unsichtbare Seite: kein Poll; Rückkehr: sofort abrufen und wieder takten', async () => {
    renderHook(() => useLiveUeberblick(3, false))
    expect(getData).toHaveBeenCalledTimes(1)
    act(() => setzeSichtbarkeit('hidden'))
    await act(async () => { vi.advanceTimersByTime(60_000) })
    expect(getData).toHaveBeenCalledTimes(1)
    act(() => setzeSichtbarkeit('visible'))
    expect(getData).toHaveBeenCalledTimes(2)
    expect(getWetter).toHaveBeenCalledTimes(2)
    expect(getTag).toHaveBeenCalledTimes(2)
    await act(async () => { vi.advanceTimersByTime(5_000) })
    expect(getData).toHaveBeenCalledTimes(3)
  })

  it('beim Mount auf unsichtbarer Seite: ein Abruf, aber kein Takt', async () => {
    sichtbarkeit = 'hidden'
    renderHook(() => useLiveUeberblick(3, false))
    await act(async () => { vi.advanceTimersByTime(30_000) })
    expect(getData).toHaveBeenCalledTimes(1)
  })

  it('Unmount räumt Intervalle und Listener (eingeklappter oder geparkter Block pollt nicht)', async () => {
    const { unmount } = renderHook(() => useLiveUeberblick(3, false))
    unmount()
    await act(async () => { vi.advanceTimersByTime(600_000) })
    expect(getData).toHaveBeenCalledTimes(1)
    act(() => setzeSichtbarkeit('visible'))
    expect(getData).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })
})
