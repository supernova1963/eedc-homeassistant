/**
 * N-265 — eine gespeicherte Anlagen-ID, die es nicht mehr gibt.
 *
 * Der Befund in einem Satz: **eedc merkte sich eine Anlage, die es gelöscht
 * hatte, und meldete die Folge als „Anlage nicht gefunden".** Die Validierung
 * der gespeicherten ID stieg mit `if (anlagen.length === 0) return` genau in dem
 * Fall aus, für den es sie gibt; der Speicher-Key wurde nirgends geräumt. Wer
 * seine einzige Anlage löschte, behielt eine tote ID — als Zahl `truthy`, damit
 * durch jedes `== null` der aufrufenden Seiten hindurch, und sichtbar erst als
 * roher Backend-404 beim Speichern einer Komponente.
 *
 * Melder: T89667 #170 (Ersteinrichtung). Sein eigener Ausweg ist die Bestätigung
 * des Mechanismus — eine NEUE Anlage füllte die Liste, damit lief die Prüfung
 * endlich und ersetzte die tote ID.
 *
 * ⚠ Die Gegenrichtung ist genauso wichtig: „Liste leer" heißt NICHT „keine
 * Anlage". `useAnlagen` startet mit `[]` und meldet auch einen Ladefehler so.
 * Wer hier ohne diese Unterscheidung räumt, wirft bei jedem Backend-Aussetzer
 * eine gültige Auswahl weg.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useSelectedAnlage, gespeicherteAnlageId } from './useSelectedAnlage'
import type { Anlage } from '../types'

const STORAGE_KEY = 'eedc-selected-anlage-id'

const useAnlagenMock = vi.fn()
vi.mock('./useAnlagen', () => ({ useAnlagen: () => useAnlagenMock() }))

const anlage = (id: number): Anlage => ({ id, anlagenname: `Anlage ${id}` } as Anlage)

/** Rückgabe von `useAnlagen` — Default: fertig geladen, eine Anlage. */
function quelle(over: { anlagen?: Anlage[]; loading?: boolean; error?: string | null } = {}) {
  return {
    anlagen: over.anlagen ?? [anlage(1)],
    loading: over.loading ?? false,
    error: over.error ?? null,
    refresh: vi.fn(),
  }
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
  useAnlagenMock.mockReturnValue(quelle())
})

describe('N-265 — die tote ID wird verworfen', () => {
  it('räumt State UND Speicher, wenn die Liste fertig geladen und leer ist', async () => {
    localStorage.setItem(STORAGE_KEY, '42')
    useAnlagenMock.mockReturnValue(quelle({ anlagen: [] }))

    const { result } = renderHook(() => useSelectedAnlage())

    await waitFor(() => expect(result.current.selectedAnlageId).toBeUndefined())
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull()
  })

  it('der Melder-Weg: nach dem Anlegen einer neuen Anlage zeigt die Auswahl auf DIESE', async () => {
    // Ausgangslage des Melders: tote ID im Speicher, keine Anlage vorhanden.
    localStorage.setItem(STORAGE_KEY, '42')
    useAnlagenMock.mockReturnValue(quelle({ anlagen: [] }))
    const { result, rerender } = renderHook(() => useSelectedAnlage())
    await waitFor(() => expect(result.current.selectedAnlageId).toBeUndefined())

    // Er legt eine neue Anlage an (id 7) — und landet auf ihr, nicht auf 42.
    useAnlagenMock.mockReturnValue(quelle({ anlagen: [anlage(7)] }))
    rerender()

    await waitFor(() => expect(result.current.selectedAnlageId).toBe(7))
    expect(localStorage.getItem(STORAGE_KEY)).toBe('7')
  })
})

describe('N-265 — Gegenprobe: eine leere Liste ist nicht immer eine Aussage', () => {
  it('räumt NICHT, solange geladen wird', async () => {
    localStorage.setItem(STORAGE_KEY, '42')
    useAnlagenMock.mockReturnValue(quelle({ anlagen: [], loading: true }))

    const { result } = renderHook(() => useSelectedAnlage())

    await waitFor(() => expect(result.current.loading).toBe(true))
    expect(result.current.selectedAnlageId).toBe(42)
    expect(localStorage.getItem(STORAGE_KEY)).toBe('42')
  })

  it('räumt NICHT, wenn die Liste wegen eines Ladefehlers leer ist', async () => {
    localStorage.setItem(STORAGE_KEY, '42')
    useAnlagenMock.mockReturnValue(quelle({ anlagen: [], error: 'offline' }))

    const { result } = renderHook(() => useSelectedAnlage())

    await waitFor(() => expect(result.current.anlagen).toEqual([]))
    expect(result.current.selectedAnlageId).toBe(42)
    expect(localStorage.getItem(STORAGE_KEY)).toBe('42')
  })
})

describe('N-265 — das Bestandsverhalten bleibt', () => {
  it('eine gültige gespeicherte ID wird nicht angefasst', async () => {
    localStorage.setItem(STORAGE_KEY, '3')
    useAnlagenMock.mockReturnValue(quelle({ anlagen: [anlage(1), anlage(3)] }))

    const { result } = renderHook(() => useSelectedAnlage())

    await waitFor(() => expect(result.current.selectedAnlage?.id).toBe(3))
    expect(localStorage.getItem(STORAGE_KEY)).toBe('3')
  })

  it('eine unbekannte ID bei NICHT leerer Liste fällt weiterhin auf die erste Anlage', async () => {
    localStorage.setItem(STORAGE_KEY, '42')
    useAnlagenMock.mockReturnValue(quelle({ anlagen: [anlage(5), anlage(6)] }))

    const { result } = renderHook(() => useSelectedAnlage())

    await waitFor(() => expect(result.current.selectedAnlageId).toBe(5))
    expect(localStorage.getItem(STORAGE_KEY)).toBe('5')
  })
})

describe('N-265 — gespeicherteAnlageId verwirft, was keine ID sein kann', () => {
  it('NaN kommt nicht durch — der Fall, den `== null` nicht fängt', () => {
    // ⚠ Der Beleg für die Notwendigkeit: das alte `parseInt(stored, 10)` liefert
    // hier NaN, und `NaN == null` ist FALSE. Die Zahl hätte als vorhandene
    // Auswahl gegolten und wäre als `anlage_id` in einen Request gewandert.
    expect(Number.parseInt('kaputt', 10)).toBeNaN()
    expect(Number.parseInt('kaputt', 10) == null).toBe(false)

    expect(gespeicherteAnlageId('kaputt')).toBeUndefined()
  })

  it('leerer Speicher, leerer String und 0 ergeben keine Auswahl', () => {
    expect(gespeicherteAnlageId(null)).toBeUndefined()
    expect(gespeicherteAnlageId('')).toBeUndefined()
    expect(gespeicherteAnlageId('0')).toBeUndefined()
    expect(gespeicherteAnlageId('-3')).toBeUndefined()
  })

  it('eine echte ID kommt durch', () => {
    expect(gespeicherteAnlageId('7')).toBe(7)
  })
})
