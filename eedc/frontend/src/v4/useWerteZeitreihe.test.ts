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

const CO2_LEER = { monate: [], gesamtKg: 0, loading: false, error: null, refresh: vi.fn() }

function basis(over: Partial<WerteZeitreiheBasis>): WerteZeitreiheBasis {
  return {
    daten: [], loading: false, error: null,
    co2: CO2_LEER,
    ...over,
  } as WerteZeitreiheBasis
}

describe('useWerteZeitreihe (reine Basis-Ableitung, Paket Q)', () => {
  it('leitet rows über createMonatsZeitreihe ab und sortiert jahre absteigend', () => {
    const daten = [{ jahr: 2024, monat: 3 }, { jahr: 2026, monat: 1 }, { jahr: 2026, monat: 2 }] as WerteZeitreiheBasis['daten']
    const { result } = renderHook(() => useWerteZeitreihe(basis({ daten }), ANLAGE))
    expect(result.current.rows).toHaveLength(3)
    expect(result.current.jahre).toEqual([2026, 2024])
    expect(vi.mocked(createMonatsZeitreihe)).toHaveBeenCalledWith(daten, ANLAGE, [])
  })

  it('N-21: reicht die kanonische CO₂-Reihe der Basis durch, statt sie rechnen zu lassen', () => {
    // Der Hook holt sie NICHT selbst (Paket Q) — sie kommt aus dem Sockel, geteilt
    // mit der CO₂-Sicht. Und er baut sie nicht um: was ankommt, geht weiter.
    const monate = [{ jahr: 2026, monat: 1, co2_pv_kg: 42 }] as WerteZeitreiheBasis['co2']['monate']
    const daten = [{ jahr: 2026, monat: 1 }] as WerteZeitreiheBasis['daten']
    renderHook(() => useWerteZeitreihe(basis({ daten, co2: { ...CO2_LEER, monate } }), ANLAGE))
    expect(vi.mocked(createMonatsZeitreihe)).toHaveBeenLastCalledWith(daten, ANLAGE, monate)
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
