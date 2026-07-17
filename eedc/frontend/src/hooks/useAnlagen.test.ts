import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useAnlagen, ladeAnlagen, invalidateAnlagenCache } from './useAnlagen'
import { anlagenApi } from '../api'

// Paket Q (Doppel-Fetch-Bereinigung): AppWithSetup lädt über ladeAnlagen()
// cache-first — der Gate-Check füllt den Shared Cache, die App-Shell fetcht
// /api/anlagen/ danach NICHT erneut. SoT: Memory project_doppel_fetches.

vi.mock('../api', () => ({
  anlagenApi: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
  },
}))

const listMock = vi.mocked(anlagenApi.list)
const ANLAGEN = [{ id: 1, name: 'Demo' }] as unknown as Awaited<ReturnType<typeof anlagenApi.list>>

beforeEach(() => {
  invalidateAnlagenCache()
  vi.clearAllMocks()
  listMock.mockResolvedValue(ANLAGEN)
})

describe('ladeAnlagen (cache-first Loader)', () => {
  it('dedupliziert: zweiter Aufruf nach Auflösung trifft den Cache, nicht die API', async () => {
    await ladeAnlagen()
    await ladeAnlagen()
    expect(listMock).toHaveBeenCalledTimes(1)
  })

  it('dedupliziert auch parallele Aufrufe (Shared Promise)', async () => {
    await Promise.all([ladeAnlagen(), ladeAnlagen()])
    expect(listMock).toHaveBeenCalledTimes(1)
  })

  it('Gegenprobe: nach invalidateAnlagenCache wird WIEDER gefetcht', async () => {
    await ladeAnlagen()
    invalidateAnlagenCache()
    await ladeAnlagen()
    expect(listMock).toHaveBeenCalledTimes(2)
  })

  it('Fehler wird durchgereicht und cached NICHT (nächster Aufruf versucht es neu)', async () => {
    listMock.mockRejectedValueOnce(new Error('offline'))
    await expect(ladeAnlagen()).rejects.toThrow('offline')
    await expect(ladeAnlagen()).resolves.toEqual(ANLAGEN)
    expect(listMock).toHaveBeenCalledTimes(2)
  })
})

describe('useAnlagen nach ladeAnlagen (AppWithSetup-Szenario)', () => {
  it('nutzt den vorgefüllten Cache: kein weiterer API-Call, sofort loading=false', async () => {
    await ladeAnlagen()
    const { result } = renderHook(() => useAnlagen())
    expect(result.current.loading).toBe(false)
    expect(result.current.anlagen).toEqual(ANLAGEN)
    expect(listMock).toHaveBeenCalledTimes(1)
  })

  it('Gegenprobe: OHNE Vorbefüllung fetcht der Hook selbst (genau einmal)', async () => {
    const { result } = renderHook(() => useAnlagen())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.anlagen).toEqual(ANLAGEN)
    expect(listMock).toHaveBeenCalledTimes(1)
  })
})
