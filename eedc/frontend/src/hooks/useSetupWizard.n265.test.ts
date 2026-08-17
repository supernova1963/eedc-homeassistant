/**
 * N-265, zweite Hälfte — der Wizard verschluckte die Auskunft, die er brauchte.
 *
 * `useSetupWizard` lädt beim Start die gemerkte Anlage. Genau dort ERFÄHRT eedc,
 * dass es sie nicht mehr gibt — und warf die Auskunft bis 17.08.2026 mit
 * `.catch(() => {})` weg. Die tote ID blieb im Wizard-State stehen; sie ist als
 * Zahl `truthy` und kam damit durch jeden `if (!wizardState.anlageId)`-Wächter
 * der Schreibpfade. Sichtbar wurde sie erst beim Speichern, als roher
 * Backend-404 „Anlage nicht gefunden" (Melder: T89667 #170).
 *
 * ⚠ Die Gegenprobe trägt den Fix: NUR ein 404 ist eine Aussage über die Anlage.
 * Wer auf jeden Fehler räumt, wirft bei einem Neustart oder Netz-Aussetzer den
 * Wizard-Fortschritt weg.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useSetupWizard } from './useSetupWizard'
import { ApiError } from '../api/client'
import { anlagenApi } from '../api/anlagen'

const WIZARD_STATE_KEY = 'eedc_setup_wizard_state'

vi.mock('../api/anlagen', () => ({ anlagenApi: { get: vi.fn(), create: vi.fn(), geocode: vi.fn() } }))
vi.mock('../api/strompreise', () => ({ strompreiseApi: { create: vi.fn() } }))
vi.mock('../api/investitionen', () => ({ investitionenApi: { list: vi.fn().mockResolvedValue([]), create: vi.fn(), update: vi.fn() } }))
vi.mock('../api/pvgis', () => ({ pvgisApi: { speicherePrognose: vi.fn() } }))

const getMock = vi.mocked(anlagenApi.get)

/** Wizard-Fortschritt, wie ihn der Melder im Speicher hatte: mitten drin. */
function fortschrittImSpeicher() {
  localStorage.setItem(WIZARD_STATE_KEY, JSON.stringify({
    completed: false,
    currentStep: 'investitionen',
    anlageId: 42,
    strompreisId: 8,
    createdInvestitionen: [11, 12],
    skippedSteps: [],
  }))
}

beforeEach(() => {
  localStorage.clear()
  vi.clearAllMocks()
})

describe('N-265 — der 404 wird ausgewertet statt verschluckt', () => {
  it('räumt die tote Anlage samt ihrer kaskadierten IDs und geht zurück auf „anlage"', async () => {
    fortschrittImSpeicher()
    getMock.mockRejectedValue(new ApiError('Anlage nicht gefunden', 404))

    const { result } = renderHook(() => useSetupWizard())

    await waitFor(() => expect(result.current.step).toBe('anlage'))
    expect(result.current.wizardState.anlageId).toBeNull()
    // Tarif und Investitionen sterben mit der Anlage (`models/anlage.py:150-155`),
    // ihre gemerkten IDs zeigen danach ebenfalls ins Leere.
    expect(result.current.wizardState.strompreisId).toBeNull()
    expect(result.current.wizardState.createdInvestitionen).toEqual([])
  })

  it('danach kann kein Schreibpfad mehr die tote ID senden — „Weiter" ist gesperrt', async () => {
    fortschrittImSpeicher()
    getMock.mockRejectedValue(new ApiError('Anlage nicht gefunden', 404))

    const { result } = renderHook(() => useSetupWizard())

    await waitFor(() => expect(result.current.step).toBe('anlage'))
    // `canProceed` hängt auf dem Anlage-Schritt an `!!wizardState.anlageId`:
    // Der Wizard verlangt jetzt eine Anlage, statt eine tote weiterzureichen.
    expect(result.current.canProceed).toBe(false)
  })
})

describe('N-265 — Gegenprobe: nur der 404 ist eine Aussage über die Anlage', () => {
  it('ein Serverfehler (500) lässt den Fortschritt unangetastet', async () => {
    fortschrittImSpeicher()
    getMock.mockRejectedValue(new ApiError('Interner Fehler', 500))

    const { result } = renderHook(() => useSetupWizard())

    await waitFor(() => expect(getMock).toHaveBeenCalled())
    expect(result.current.step).toBe('investitionen')
    expect(result.current.wizardState.anlageId).toBe(42)
    expect(result.current.wizardState.strompreisId).toBe(8)
    expect(result.current.wizardState.createdInvestitionen).toEqual([11, 12])
  })

  it('ein Netzfehler ohne HTTP-Status lässt den Fortschritt unangetastet', async () => {
    fortschrittImSpeicher()
    getMock.mockRejectedValue(new TypeError('Failed to fetch'))

    const { result } = renderHook(() => useSetupWizard())

    await waitFor(() => expect(getMock).toHaveBeenCalled())
    expect(result.current.step).toBe('investitionen')
    expect(result.current.wizardState.anlageId).toBe(42)
  })

  it('der Normalfall bleibt: eine existierende Anlage wird geladen, nichts geräumt', async () => {
    fortschrittImSpeicher()
    getMock.mockResolvedValue({ id: 42, anlagenname: 'Balkon' } as Awaited<ReturnType<typeof anlagenApi.get>>)

    const { result } = renderHook(() => useSetupWizard())

    await waitFor(() => expect(result.current.anlage?.id).toBe(42))
    expect(result.current.step).toBe('investitionen')
    expect(result.current.wizardState.anlageId).toBe(42)
  })
})
