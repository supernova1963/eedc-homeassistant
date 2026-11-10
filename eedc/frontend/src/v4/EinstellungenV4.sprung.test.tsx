/**
 * E4 «Daten-Checker: Sprung aufs Feld» — die Lesestellen in `EinstellungenV4` (W-5): Komponenten
 * (`bearbeiten` · `neu` · `feld`) und Assistent (`wizard`). Je Parameter: er wirkt (Formular offen, Feld fokussiert bzw.
 * Assistent geöffnet), er verschwindet aus der Adresse, und ein zweiter Render öffnet nichts erneut.
 *
 * Die Komponenten-Verwaltung ist ein Stub (ein Gerät, ein «Formular» mit `name="param_jaz"`); Router, `EinstellungenV4`,
 * `useSprungParameter` und `useAufFeldSpringen` laufen echt.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'
import { useState } from 'react'

const oeffneWizard = vi.fn()
const oeffneBearbeiten = vi.fn()
const oeffneNeu = vi.fn()

vi.mock('../hooks/useHAAvailable', () => ({ useHAAvailable: () => false, useHAVerbunden: () => false }))
vi.mock('../hooks/useEinstellungenStatus', () => ({ useEinstellungenStatus: () => ({}) }))
vi.mock('./wizardHost', () => ({ useOeffneWizard: () => oeffneWizard }))
vi.mock('../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: { id: 1, anlagenname: 'Haus' } }),
}))
vi.mock('../pages/InvestitionenTeile', async (orig) => {
  const echt = await orig<Record<string, unknown>>()
  return {
    ...echt,
    useInvestitionenVerwaltung: () => {
      const [offen, setOffen] = useState(false)
      return {
        loading: false, investitionen: [{ id: 9, typ: 'waermepumpe', bezeichnung: 'WP' }], typCounts: {}, hinweise: null,
        geraeteDesTyps: () => [], frageLoeschen: vi.fn(),
        oeffneBearbeiten: (i: unknown) => { oeffneBearbeiten(i); setOffen(true) },
        oeffneNeu: (t: unknown) => { oeffneNeu(t); setOffen(true) },
        modals: offen ? <form><input name="bezeichnung" /><input name="param_jaz" /></form> : null,
      }
    },
  }
})

import EinstellungenV4 from './EinstellungenV4'

function Ort() {
  return <span data-testid="ort">{useLocation().search}</span>
}

function renderAt(adresse: string) {
  return render(
    <MemoryRouter initialEntries={[adresse]}>
      <Routes>
        <Route path="/einstellungen/:kategorie" element={<><EinstellungenV4 /><Ort /></>} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  Element.prototype.scrollIntoView = vi.fn()
})

describe('EinstellungenV4: Sprung-Parameter der Komponenten (E4)', () => {
  it('`bearbeiten` + `feld`: Formular des Geräts offen, Feld `param_jaz` fokussiert, Parameter weg', async () => {
    renderAt('/einstellungen/komponenten?bearbeiten=9&feld=jaz')
    await waitFor(() => expect(oeffneBearbeiten).toHaveBeenCalledTimes(1))
    expect(oeffneBearbeiten.mock.calls[0][0]).toMatchObject({ id: 9 })
    await waitFor(() => expect(document.activeElement).toBe(document.querySelector('[name="param_jaz"]')))
    await waitFor(() => expect(screen.getByTestId('ort').textContent).toBe(''))
    expect(oeffneBearbeiten).toHaveBeenCalledTimes(1)
  })

  it('`neu=<typ>` legt eine Komponente des Typs an; ein unbekannter Typ öffnet nichts', async () => {
    renderAt('/einstellungen/komponenten?neu=speicher')
    await waitFor(() => expect(oeffneNeu).toHaveBeenCalledWith('speicher'))
    await waitFor(() => expect(screen.getByTestId('ort').textContent).toBe(''))
  })

  it('`neu` mit unbekanntem Typ: nichts öffnet, der Parameter verschwindet', async () => {
    renderAt('/einstellungen/komponenten?neu=raumschiff')
    await waitFor(() => expect(screen.getByTestId('ort').textContent).toBe(''))
    expect(oeffneNeu).not.toHaveBeenCalled()
    expect(oeffneBearbeiten).not.toHaveBeenCalled()
  })
})

describe('EinstellungenV4: `wizard=` öffnet den Assistenten des Blocks (E4, Teil B Nr 1)', () => {
  it('`wizard=connector`: einmal geöffnet, Parameter weg, `block` bleibt', async () => {
    renderAt('/einstellungen/integration?block=import-buendel&wizard=connector')
    await waitFor(() => expect(oeffneWizard).toHaveBeenCalledWith('connector'))
    await waitFor(() => expect(screen.getByTestId('ort').textContent).toBe('?block=import-buendel'))
    expect(oeffneWizard).toHaveBeenCalledTimes(1)
  })

  it('ein fremder Assistent wird nicht geöffnet', async () => {
    renderAt('/einstellungen/integration?block=import-buendel&wizard=csv-import')
    await waitFor(() => expect(screen.getByTestId('ort').textContent).toBe('?block=import-buendel'))
    expect(oeffneWizard).not.toHaveBeenCalled()
  })
})
