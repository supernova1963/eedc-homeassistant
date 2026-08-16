import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import AnlageStep from './AnlageStep'

// Bewertungsgrenze E5 (2026-08-16): Die Inbetriebnahme der Anlage ist im Setup
// Pflicht — sie ist der Anker dafür, ab wann eedc Zählerwerte erwartet. Ohne ihn
// fällt der Erwartungsrahmen auf die Erzeuger bzw. auf die vorhandenen Daten
// selbst zurück, und eine Lücke am Anfang der Historie sieht dann niemand mehr.
//
// ⚠ Nur HIER Pflicht: Das Einstellungs-Formular zeigt bei fehlendem Datum nur
// eine Warnung und speichert weiter (Entscheid Gernot) — wer eine Bestandsanlage
// bearbeitet, will meist etwas anderes ändern und soll nicht aufgehalten werden.

function aufbau(overrides: Partial<Parameters<typeof AnlageStep>[0]> = {}) {
  const onSubmit = vi.fn().mockResolvedValue(undefined)
  render(
    <AnlageStep
      isLoading={false}
      error={null}
      onSubmit={onSubmit}
      onGeocode={vi.fn().mockResolvedValue(null)}
      onBack={vi.fn()}
      {...overrides}
    />
  )
  return { onSubmit }
}

function fuelleBasis() {
  fireEvent.change(screen.getByLabelText(/Anlagenname|Name der Anlage/i), {
    target: { name: 'anlagenname', value: 'Testanlage' },
  })
  fireEvent.change(screen.getByLabelText(/Leistung/i), {
    target: { name: 'leistung_kwp', value: '10' },
  })
}

describe('AnlageStep — Inbetriebnahme ist Pflicht', () => {
  it('sendet nicht ab, solange kein Datum gesetzt ist, und sagt warum', async () => {
    const { onSubmit } = aufbau()
    fuelleBasis()
    fireEvent.click(screen.getByRole('button', { name: /Weiter|Anlage erstellen/i }))

    // Auf den VOLLEN Satz prüfen: Der Hinweistext unter dem Feld trägt dieselbe
    // Begründung, ein Teilstring träfe beide und misst dann nicht die Blockade.
    await waitFor(() => {
      expect(
        screen.getAllByText(/Bitte tragen Sie die Inbetriebnahme Ihrer Anlage ein/i).length
      ).toBeGreaterThan(0)
    })
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('sendet ab, sobald ein Datum gewählt ist', async () => {
    const { onSubmit } = aufbau()
    fuelleBasis()

    // Datum über den DatumPicker-SoT wählen (kein natives Feld).
    fireEvent.click(screen.getByRole('button', { name: 'Inbetriebnahme (Anlage)' }))
    fireEvent.click(screen.getAllByRole('button', { name: '15' })[0])

    fireEvent.click(screen.getByRole('button', { name: /Weiter|Anlage erstellen/i }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0][0].installationsdatum).toBeTruthy()
  })
})
