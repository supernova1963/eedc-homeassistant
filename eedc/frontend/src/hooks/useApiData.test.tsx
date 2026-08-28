import { describe, it, expect, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useApiData, _clearSwrCacheForTests } from './useApiData'

// R18-2 (SWR-Sicht-Cache): Invarianten des erweiterten useApiData.
// Regel: Ein Remount mit `swrKey` zeigt sofort die alten Daten (loading bleibt
// false) und revalidiert still; ein Skeleton gibt es nur beim echten Erst-Load.

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

beforeEach(() => _clearSwrCacheForTests())

describe('useApiData (Basis-Verhalten, unverändert ohne swrKey)', () => {
  it('lädt mit loading=true und liefert Daten', async () => {
    const { result } = renderHook(() => useApiData(async () => 42, []))
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.data).toBe(42))
    expect(result.current.loading).toBe(false)
    expect(result.current.reloading).toBe(false)
  })

  it('setzt error bei Fehler', async () => {
    const { result } = renderHook(() => useApiData(async () => { throw new Error('kaputt') }, []))
    await waitFor(() => expect(result.current.error).toBe('kaputt'))
    expect(result.current.data).toBeNull()
  })

  it('enabled=false lädt nicht', async () => {
    const { result } = renderHook(() => useApiData(async () => 1, [], { enabled: false }))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toBeNull()
  })
})

describe('useApiData + swrKey (R18-2: alte Daten statt Skeleton)', () => {
  it('Erst-Load: loading=true (Skeleton-Fall), Ergebnis landet im Cache', async () => {
    const { result } = renderHook(() => useApiData(async () => 'A', [], { swrKey: 'k1' }))
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.data).toBe('A'))
  })

  it('Remount mit Cache-Stand: Daten SOFORT (kein loading), still revalidiert', async () => {
    const erst = renderHook(() => useApiData(async () => 'alt', [], { swrKey: 'k2' }))
    await waitFor(() => expect(erst.result.current.data).toBe('alt'))
    erst.unmount()

    const d = deferred<string>()
    const zweit = renderHook(() => useApiData(() => d.promise, [], { swrKey: 'k2' }))
    // Alte Daten sofort sichtbar, KEIN Skeleton, Hintergrund-Refetch läuft.
    expect(zweit.result.current.data).toBe('alt')
    expect(zweit.result.current.loading).toBe(false)
    await waitFor(() => expect(zweit.result.current.reloading).toBe(true))
    d.resolve('frisch')
    await waitFor(() => expect(zweit.result.current.data).toBe('frisch'))
    expect(zweit.result.current.reloading).toBe(false)
  })

  it('Key-Wechsel ohne Cache-Stand: ehrlicher Erst-Load (loading=true, data=null)', async () => {
    const { result, rerender } = renderHook(
      ({ key }: { key: string }) => useApiData(async () => `daten:${key}`, [key], { swrKey: key }),
      { initialProps: { key: 'anlage-1' } },
    )
    await waitFor(() => expect(result.current.data).toBe('daten:anlage-1'))
    rerender({ key: 'anlage-2' })
    expect(result.current.data).toBeNull()
    expect(result.current.loading).toBe(true)
    await waitFor(() => expect(result.current.data).toBe('daten:anlage-2'))
  })

  it('Refetch-Fehler lässt alte Daten stehen (error gesetzt, kein Datenverlust)', async () => {
    let schlägtFehl = false
    const { result, unmount } = renderHook(() =>
      useApiData(async () => {
        if (schlägtFehl) throw new Error('offline')
        return 'stabil'
      }, [], { swrKey: 'k3' }))
    await waitFor(() => expect(result.current.data).toBe('stabil'))
    unmount()

    schlägtFehl = true
    const zweit = renderHook(() =>
      useApiData(async () => { throw new Error('offline') }, [], { swrKey: 'k3' }))
    await waitFor(() => expect(zweit.result.current.error).toBe('offline'))
    expect(zweit.result.current.data).toBe('stabil')
    expect(zweit.result.current.loading).toBe(false)
  })

  it('Race-Schutz: nur die jüngste Anfrage schreibt (Key-Wechsel überholt alten Response)', async () => {
    const langsam = deferred<string>()
    const { result, rerender } = renderHook(
      ({ key }: { key: string }) =>
        useApiData(() => (key === 'langsam' ? langsam.promise : Promise.resolve('schnell')), [key], { swrKey: key }),
      { initialProps: { key: 'langsam' } },
    )
    rerender({ key: 'schnell' })
    await waitFor(() => expect(result.current.data).toBe('schnell'))
    langsam.resolve('zu spät')
    await new Promise((r) => setTimeout(r, 20))
    expect(result.current.data).toBe('schnell')
  })
})

describe('useApiData + keepPreviousData (D7-2: In-Place-Update beim Zeitraum-Wechsel)', () => {
  it('Key-Wechsel ohne Cache lässt alte Daten stehen und lädt still nach', async () => {
    const { result, rerender } = renderHook(
      ({ key }: { key: string }) =>
        useApiData(async () => `monat:${key}`, [key], { swrKey: key, keepPreviousData: true }),
      { initialProps: { key: '2026-05' } },
    )
    await waitFor(() => expect(result.current.data).toBe('monat:2026-05'))
    rerender({ key: '2026-06' })
    // Alte Daten bleiben (kein Skeleton), still nachladen …
    expect(result.current.data).toBe('monat:2026-05')
    expect(result.current.loading).toBe(false)
    await waitFor(() => expect(result.current.data).toBe('monat:2026-06'))
  })
})
