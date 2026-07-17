import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { usePrognoseVsIst } from './PrognoseVsIstTeile'
import { monatsdatenApi, pvgisApi } from '../../api'
import type { AggregierteMonatsdaten } from '../../api/monatsdaten'

// Paket Q (Doppel-Fetch-Bereinigung): der V4-Dispatcher hält die aggregierten
// Monatsdaten in useAuswertungBasis und reicht sie als 3. Argument herein —
// dann darf der Hook listAggregiert NICHT selbst rufen. Ohne 3. Argument
// (V3 pages/PrognoseVsIst) bleibt der Eigen-Fetch-Vertrag erhalten.
// Bewusst vi.spyOn statt vi.mock aufs api-Barrel: das Modul-Mocking des
// Barrels ließ den jsdom-Worker im Import-Graph dieses Files OOM-sterben.

const MD = [
  { jahr: 2026, monat: 5 }, { jahr: 2025, monat: 5 },
] as unknown as AggregierteMonatsdaten[]
// ⚠️ Identitäts-Vertrag des 3. Arguments (wie jede Effekt-Dependency): Aufrufer
// müssen eine RENDER-STABILE Referenz übergeben (State/useMemo) — ein Inline-
// Literal erzeugt eine Refetch-Schleife. Genau das passierte hier im ersten
// Wurf (inline [] → Endlos-Loop → jsdom-Worker-OOM).
const LEER: AggregierteMonatsdaten[] = []

let listSpy: ReturnType<typeof vi.fn>

beforeEach(() => {
  listSpy = vi.spyOn(monatsdatenApi, 'listAggregiert').mockResolvedValue(MD) as unknown as ReturnType<typeof vi.fn>
  vi.spyOn(pvgisApi, 'getAktivePrognose').mockResolvedValue(
    { jahresertrag_kwh: 1000, monatswerte: [] } as unknown as Awaited<ReturnType<typeof pvgisApi.getAktivePrognose>>,
  )
})
afterEach(() => vi.restoreAllMocks())

describe('usePrognoseVsIst — vorgeladene Monatsdaten (Paket Q)', () => {
  it('mit vorgeladenen Daten: KEIN listAggregiert-Call, Daten kommen aus dem Argument', async () => {
    const { result } = renderHook(() => usePrognoseVsIst(1, 2026, MD))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(listSpy).not.toHaveBeenCalled()
    expect(result.current.monatsdaten).toEqual(MD)
    expect(result.current.verfuegbareJahre).toEqual([2026, 2025])
  })

  it('leeres Array gilt als vorgeladen (ehrlich leer) — kein Fallback-Fetch', async () => {
    const { result } = renderHook(() => usePrognoseVsIst(1, 2026, LEER))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(listSpy).not.toHaveBeenCalled()
    expect(result.current.monatsdaten).toEqual([])
  })

  it('Gegenprobe (V3-Vertrag): ohne 3. Argument fetcht der Hook selbst', async () => {
    const { result } = renderHook(() => usePrognoseVsIst(1, 2026))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(listSpy).toHaveBeenCalledTimes(1)
    expect(result.current.monatsdaten).toEqual(MD)
  })
})
