/**
 * **P-433-2b K2a (K2-4) — die «Kennung in der Steuerung» bleibt ein Text.**
 *
 * Das Stammdatum am E-Auto ist der Name, unter dem evcc/openWB das Auto meldet; der Treffer mit dem Textfeld
 * «Fahrzeug am Ladepunkt» der Wallbox vergleicht Text mit Text (Backend `kennung_in_steuerung`). Ohne den Eintrag in
 * `textFelder` machte `InvestitionForm` aus „4711" die Zahl 4711 und aus „3er" die Zahl 3 (`parseFloat`) — der Treffer
 * fiele still aus. Roundtrip gegen die Submit-Nutzlast (Bauform `n572-vorbelegung-drei-wege.test.tsx`).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'

import InvestitionForm from '../components/forms/InvestitionForm'
import { PARAM_E_AUTO } from '../lib/investitionParameter'
import type { Investition } from '../types'

vi.mock('../api/investitionen', () => ({
  investitionenApi: { list: vi.fn(() => Promise.resolve([])) },
}))

const LABEL = 'Kennung in der Steuerung (evcc vehicleName, openWB Fahrzeug)'

function eAuto(parameter: Record<string, unknown>): Investition {
  return { id: 11, anlage_id: 1, typ: 'e-auto', bezeichnung: 'Smart', anschaffungsdatum: '2024-03-01', aktiv: true, parameter }
}

async function speichernMit(investition: Investition, eingabe: string | null): Promise<Record<string, unknown>> {
  const onSubmit = vi.fn(() => Promise.resolve())
  render(<InvestitionForm anlageId={1} typ="e-auto" investition={investition} onSubmit={onSubmit} onCancel={() => {}} />)
  const input = screen.getByLabelText(LABEL) as HTMLInputElement
  expect(input.name).toBe(`param_${PARAM_E_AUTO.KENNUNG_IN_STEUERUNG}`)
  if (eingabe !== null) fireEvent.change(input, { target: { value: eingabe } })
  fireEvent.submit(document.querySelector('form')!)
  await waitFor(() => expect(onSubmit).toHaveBeenCalled())
  return ((onSubmit.mock.calls[0] as unknown[])[0] as { parameter?: Record<string, unknown> }).parameter ?? {}
}

describe('P-433-2b K2a — Kennung in der Steuerung im E-Auto-Formular', () => {
  it('eine Ziffernfolge bleibt Text (kein parseFloat)', async () => {
    expect((await speichernMit(eAuto({}), '4711')).kennung_in_steuerung).toBe('4711')
  })

  it('ein Name mit Zahl am Anfang bleibt ganz', async () => {
    expect((await speichernMit(eAuto({}), '3er Touring')).kennung_in_steuerung).toBe('3er Touring')
  })

  it('der gespeicherte Wert steht im Feld und lässt sich leeren', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    render(<InvestitionForm anlageId={1} typ="e-auto" investition={eAuto({ kennung_in_steuerung: 'id4' })} onSubmit={onSubmit} onCancel={() => {}} />)
    const input = screen.getByLabelText(LABEL) as HTMLInputElement
    expect(input.value).toBe('id4')
    fireEvent.change(input, { target: { value: '' } })
    fireEvent.submit(document.querySelector('form')!)
    await waitFor(() => expect(onSubmit).toHaveBeenCalled())
    const parameter = ((onSubmit.mock.calls[0] as unknown[])[0] as { parameter?: Record<string, unknown> }).parameter ?? {}
    expect(parameter.kennung_in_steuerung === undefined || parameter.kennung_in_steuerung === '').toBe(true)
  })
})
