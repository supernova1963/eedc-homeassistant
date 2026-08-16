import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import AnlageForm from './AnlageForm'
import type { Anlage } from '../../types'

// Bewertungsgrenze E5 (2026-08-16): Das Inbetriebnahme-Datum ist inzwischen mehr
// als nachrichtlich — es sagt, ab wann eedc Zählerwerte erwartet. Hier ist es
// trotzdem bewusst KEIN Pflichtfeld (Entscheid Gernot): Wer eine Bestandsanlage
// bearbeitet, will meist etwas ganz anderes ändern und soll dabei nicht
// aufgehalten werden. Es gibt eine Warnung — und das Speichern läuft weiter.
// Pflicht ist es nur im Setup-Wizard (`setup-wizard/steps/AnlageStep.test.tsx`),
// den Bestand holt der Daten-Checker (STAMMDATEN, seit demselben Tag ERROR).

vi.mock('../../hooks/useHAAvailable', () => ({ useHAVerbunden: () => false }))
vi.mock('../../api/wetter', () => ({ wetterApi: { getProvider: vi.fn() } }))
vi.mock('../../api/anlagen', () => ({ anlagenApi: { geocode: vi.fn() } }))
vi.mock('./VersorgerSection', () => ({ default: () => null }))
vi.mock('./AnlagenfotoSection', () => ({ default: () => null }))

const WARNUNG = /Fehlt — ohne dieses Datum weiß eedc nicht/i

function anlage(installationsdatum: string | undefined): Anlage {
  return {
    id: 1,
    anlagenname: 'Bestandsanlage',
    leistung_kwp: 9.8,
    installationsdatum,
  } as Anlage
}

describe('AnlageForm — Inbetriebnahme fehlt', () => {
  it('warnt, wenn das Datum fehlt', () => {
    render(<AnlageForm anlage={anlage(undefined)} onSubmit={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.getByText(WARNUNG)).toBeInTheDocument()
  })

  it('schweigt, wenn das Datum gepflegt ist', () => {
    render(<AnlageForm anlage={anlage('2023-06-01')} onSubmit={vi.fn()} onCancel={vi.fn()} />)
    expect(screen.queryByText(WARNUNG)).not.toBeInTheDocument()
  })

  it('speichert trotz fehlendem Datum — die Warnung blockiert nicht', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<AnlageForm anlage={anlage(undefined)} onSubmit={onSubmit} onCancel={vi.fn()} />)

    // Eine ganz andere Änderung, so wie im echten Fall (PLZ nachtragen).
    fireEvent.change(screen.getByLabelText(/PLZ/i), {
      target: { name: 'standort_plz', value: '12345' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Speichern|Aktualisieren/i }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0][0].standort_plz).toBe('12345')
    expect(onSubmit.mock.calls[0][0].installationsdatum).toBeUndefined()
  })
})
