import { describe, it, expect, vi } from 'vitest'
import { renderHook } from '@testing-library/react'

// Paket Q: useWerteZeitreihe ist reine Ableitung aus der Dispatcher-Basis —
// keine eigenen Fetches. Die Zeitreihen-Erzeugung (createMonatsZeitreihe)
// bleibt der bestehende Datenpfad und ist hier gestubbt (eigener SoT).

vi.mock('../pages/auswertung/types', () => ({
  createMonatsZeitreihe: vi.fn((daten: { jahr: number; monat: number }[]) =>
    daten.map((d) => ({ jahr: d.jahr, monat: d.monat }))),
}))

import { useWerteZeitreihe, type WerteZeitreiheBasis } from './useWerteZeitreihe'
import { createMonatsZeitreihe } from '../pages/auswertung/types'

const ANLAGE = { id: 1 } as Parameters<typeof useWerteZeitreihe>[1]

function basis(over: Partial<WerteZeitreiheBasis>): WerteZeitreiheBasis {
  return {
    daten: [], strompreis: null, alleTarife: [], loading: false, error: null,
    ...over,
  } as WerteZeitreiheBasis
}

describe('useWerteZeitreihe (reine Basis-Ableitung, Paket Q)', () => {
  it('leitet rows über createMonatsZeitreihe ab und sortiert jahre absteigend', () => {
    const daten = [{ jahr: 2024, monat: 3 }, { jahr: 2026, monat: 1 }, { jahr: 2026, monat: 2 }] as WerteZeitreiheBasis['daten']
    const { result } = renderHook(() => useWerteZeitreihe(basis({ daten }), ANLAGE))
    expect(result.current.rows).toHaveLength(3)
    expect(result.current.jahre).toEqual([2026, 2024])
    expect(vi.mocked(createMonatsZeitreihe)).toHaveBeenCalledWith(daten, ANLAGE, null, [])
  })

  it('reicht loading der Basis durch', () => {
    const { result } = renderHook(() => useWerteZeitreihe(basis({ loading: true }), ANLAGE))
    expect(result.current.loading).toBe(true)
  })

  it('Fehler nur ohne Daten (SWR: alte Daten bleiben bei Fehl-Revalidierung stehen)', () => {
    const leer = renderHook(() => useWerteZeitreihe(basis({ error: 'kaputt' }), ANLAGE))
    expect(leer.result.current.error).toBe('Fehler beim Laden der Werte')

    const mitDaten = renderHook(() =>
      useWerteZeitreihe(basis({ error: 'kaputt', daten: [{ jahr: 2026, monat: 1 }] as WerteZeitreiheBasis['daten'] }), ANLAGE))
    expect(mitDaten.result.current.error).toBeNull()
    expect(mitDaten.result.current.rows).toHaveLength(1)
  })
})
