/**
 * „Alle Jahre" in der PV-String-Sicht — die Zeilen sind nicht in jedem Jahr dieselben (N-613).
 *
 * Seit die Abtretung eines Balkonkraftwerks an seine Modul-Kinder je Monat gilt,
 * hat ein BKW, dem später Module zugeordnet wurden, eine eigene Zeile nur in den
 * Jahren, in denen es noch selbst trägt. Der Client-Pfad „alle Jahre" baute seine
 * Zeilen aus dem ERSTEN Jahr der Liste — eine Zeile, die dort fehlt, fiel mit
 * ihrer Erzeugung aus dem Gesamtwert.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

const getPVStrings = vi.fn()
vi.mock('../../api/cockpit', () => ({ cockpitApi: { getPVStrings: (...a: unknown[]) => getPVStrings(...a) } }))

import { usePvStrings } from './PvStringsTeile'
import type { PVStringsResponse } from '../../api/cockpit'

const zeile = (id: number, bezeichnung: string, kwp: number, soll: number, ist: number) => ({
  investition_id: id, bezeichnung, leistung_kwp: kwp, ausrichtung: null, neigung_grad: null,
  wechselrichter_id: null, wechselrichter_name: null,
  prognose_jahr_kwh: soll, ist_jahr_kwh: ist, abweichung_jahr_kwh: ist - soll,
  abweichung_jahr_prozent: null, performance_ratio_jahr: soll > 0 ? ist / soll : null,
  spezifischer_ertrag_kwh_kwp: ist / kwp, ist_quelle: 'gemessen' as const, monatswerte: [],
})

const antwort = (jahr: number, strings: PVStringsResponse['strings']): PVStringsResponse => ({
  anlage_id: 1, jahr, hat_prognose: true, prognose_warnung: null, anlagen_leistung_kwp: 0.8,
  prognose_gesamt_kwh: strings.reduce((s, x) => s + x.prognose_jahr_kwh, 0),
  ist_gesamt_kwh: strings.reduce((s, x) => s + x.ist_jahr_kwh, 0),
  abweichung_gesamt_kwh: 0, abweichung_gesamt_prozent: null, strings,
  bester_string: null, schlechtester_string: null, ist_quelle: 'gemessen', vergleich_hinweis: null,
})

// Die Jahresreihenfolge der Seite ist absteigend (neueste zuerst) — das BKW steht
// nur im ÄLTEREN Jahr und damit gerade NICHT im ersten der Liste.
const JAHRE = [2026, 2025]

beforeEach(() => vi.clearAllMocks())

describe('usePvStrings — „alle Jahre" mit einer Zeile, die nicht in jedem Jahr steht', () => {
  it('zählt das Balkonkraftwerk aus dem Jahr, in dem es noch selbst trug, mit', async () => {
    getPVStrings.mockImplementation((_id: number, jahr: number) => Promise.resolve(
      jahr === 2025
        ? antwort(2025, [zeile(1, 'Balkon', 0.8, 1000, 70), zeile(2, 'Kind 1', 0.4, 0, 0), zeile(3, 'Kind 2', 0.4, 0, 0)])
        : antwort(2026, [zeile(2, 'Kind 1', 0.4, 500, 35), zeile(3, 'Kind 2', 0.4, 500, 35)])))
    const { result } = renderHook(() => usePvStrings(1, 'all', JAHRE))
    await waitFor(() => expect(result.current.loading).toBe(false))
    const data = result.current.data
    expect(data?.ist_gesamt_kwh).toBe(140)
    expect(data?.prognose_gesamt_kwh).toBe(2000)
    expect(data?.strings.map((s) => s.bezeichnung)).toEqual(['Kind 1', 'Kind 2', 'Balkon'])
    expect(data?.strings.find((s) => s.bezeichnung === 'Balkon')?.ist_jahr_kwh).toBe(70)
  })

  it('lässt die Zeilen unverändert, wenn sie in jedem Jahr dieselben sind', async () => {
    getPVStrings.mockImplementation((_id: number, jahr: number) => Promise.resolve(
      antwort(jahr, [zeile(11, 'Süd', 6, 600, 550), zeile(12, 'West', 4, 400, 380)])))
    const { result } = renderHook(() => usePvStrings(1, 'all', JAHRE))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data?.strings.map((s) => s.bezeichnung)).toEqual(['Süd', 'West'])
    expect(result.current.data?.ist_gesamt_kwh).toBe(1860)
  })
})
