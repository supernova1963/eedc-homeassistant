/**
 * InvestitionForm — Submit-Nutzlast.
 *
 * Kern des Tests ist der Vertrag mit dem Backend (`model_dump(exclude_unset=True)`):
 * Beim BEARBEITEN muss ein leeres Feld als `null` gesendet werden, sonst fällt der
 * Schlüssel aus dem JSON und der Altwert bleibt stehen — genau daran scheiterte das
 * Lösen einer Wechselrichter-Zuordnung (JayJay, Forum v4.0.0). Beim ANLEGEN bleibt
 * `undefined` richtig, damit die Backend-Defaults greifen.
 * Backend-Hälfte: `backend/tests/test_investition_felder_leeren.py`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import InvestitionForm from './InvestitionForm'
import type { Investition } from '../../types'

const wechselrichter: Investition = {
  id: 3, anlage_id: 1, typ: 'wechselrichter', bezeichnung: 'Hybrid-WR', aktiv: true,
}

vi.mock('../../api/investitionen', () => ({
  investitionenApi: { list: vi.fn(() => Promise.resolve([wechselrichter])) },
}))

const speicher: Investition = {
  id: 7, anlage_id: 1, typ: 'speicher', bezeichnung: 'AC-Speicher',
  anschaffungsdatum: '2024-06-01', aktiv: true, parent_investition_id: 3,
  parameter: { kapazitaet_kwh: 10 },
}

/** Speichern auslösen und die an onSubmit übergebene Nutzlast zurückgeben. */
async function submit(onSubmit: ReturnType<typeof vi.fn>) {
  fireEvent.submit(document.querySelector('form')!)
  await waitFor(() => expect(onSubmit).toHaveBeenCalled())
  return onSubmit.mock.calls[0][0] as Record<string, unknown>
}

describe('InvestitionForm — Submit-Nutzlast', () => {
  beforeEach(() => vi.clearAllMocks())

  it('löst die Parent-Zuordnung, wenn „Keine Zuordnung" gewählt wird', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    render(<InvestitionForm anlageId={1} typ="speicher" investition={speicher} onSubmit={onSubmit} onCancel={() => {}} />)

    const select = await screen.findByLabelText(/Gehört zu/i)
    fireEvent.change(select, { target: { value: '' } })

    const nutzlast = await submit(onSubmit)
    // Der Schlüssel MUSS mitgehen — sonst greift exclude_unset und der alte
    // Wechselrichter bleibt für immer stehen.
    expect('parent_investition_id' in nutzlast).toBe(true)
    expect(nutzlast.parent_investition_id).toBeNull()
  })

  it('sendet beim Bearbeiten null für nicht gefüllte optionale Felder', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    render(<InvestitionForm anlageId={1} typ="speicher" investition={speicher} onSubmit={onSubmit} onCancel={() => {}} />)

    const nutzlast = await submit(onSubmit)
    expect(nutzlast.anschaffungskosten_alternativ).toBeNull()
    expect(nutzlast.stilllegungsdatum).toBeNull()
    // Gefüllte Felder behalten ihren Wert.
    expect(nutzlast.anschaffungsdatum).toBe('2024-06-01')
  })

  it('blockiert das Anlegen ohne Anschaffungsdatum', async () => {
    // v4.0.1: Das Datum ist die Grenze jeder Auswertung und der Nullpunkt der
    // Amortisationskurve — ohne es darf keine Komponente mehr entstehen.
    const onSubmit = vi.fn(() => Promise.resolve())
    render(<InvestitionForm anlageId={1} typ="speicher" onSubmit={onSubmit} onCancel={() => {}} />)

    fireEvent.change(screen.getByLabelText(/Bezeichnung/i), { target: { value: 'Neuer Speicher' } })
    fireEvent.submit(document.querySelector('form')!)

    await waitFor(() => expect(screen.getByText(/Bitte das Anschaffungsdatum angeben/i)).toBeInTheDocument())
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('sendet beim Anlegen undefined statt null (Backend-Defaults greifen)', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    render(<InvestitionForm anlageId={1} typ="speicher" onSubmit={onSubmit} onCancel={() => {}} />)

    fireEvent.change(screen.getByLabelText(/Bezeichnung/i), { target: { value: 'Neuer Speicher' } })
    // Datum über den Kalender setzen (DatumPicker ist ein Dialog, kein Input).
    fireEvent.click(screen.getByLabelText('Anschaffungsdatum'))
    fireEvent.click(await screen.findByRole('button', { name: '15' }))

    const nutzlast = await submit(onSubmit)
    expect(nutzlast.anschaffungsdatum).toBeTruthy()
    expect(nutzlast.anschaffungskosten_alternativ).toBeUndefined()
    expect(nutzlast.parent_investition_id).toBeUndefined()
  })
})
