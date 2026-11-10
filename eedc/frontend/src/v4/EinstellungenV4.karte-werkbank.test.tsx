/**
 * #440 (gruaGit) — «Beheben» führt bis zur Reparatur-Werkbank.
 *
 * Der Daten-Checker navigiert auf `/einstellungen/daten?block=energieprofil&karte=werkbank`. Abnahme (Entscheid Gernot
 * 10.11.2026, vier Bedingungen): (1) der Block öffnet, falls zugeklappt; (2) auch beim wiederholten Klick mit
 * unverändertem Parameter; (3) die Sicht scrollt zur Werkbank-Karte (`data-karte="werkbank"`); (4) der gemerkte
 * Klapp-Zustand ändert sich nur um das Öffnen dieses einen Blocks.
 *
 * Der Katalog ist hier ein Zwei-Block-Stub (kein Netz in jsdom); Router, `EinstellungenV4`, `BlockShell` und der Hook
 * `useKarteAnspringen` laufen echt.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useNavigate } from 'react-router-dom'
import { ladeBlockState } from '../components/blocks/BlockShell'

vi.mock('../hooks/useHAAvailable', () => ({ useHAAvailable: () => false, useHAVerbunden: () => false }))
vi.mock('../hooks/useEinstellungenStatus', () => ({ useEinstellungenStatus: () => ({}) }))
vi.mock('./wizardHost', () => ({ useOeffneWizard: () => null }))

vi.mock('../config/einstellungenKatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../config/einstellungenKatalog')>()
  const eintraege = [
    { id: 'datenchecker', name: 'Daten-Checker', icon: actual.EINSTELLUNGEN_KATALOG[0].icon, kategorie: 'daten',
      inhalt: () => <p>Checker-Inhalt</p> },
    { id: 'energieprofil', name: 'Energieprofil-Pflege', icon: actual.EINSTELLUNGEN_KATALOG[0].icon, kategorie: 'daten',
      inhalt: () => <div><p>Datenbestand</p><div data-karte="werkbank">Reparatur-Werkbank</div></div> },
  ]
  return {
    ...actual,
    eintraegeDerKategorie: () => eintraege,
    sucheEintraege: () => [],
    fehlendeHAVoraussetzung: () => null,
  }
})

import EinstellungenV4 from './EinstellungenV4'

const ZIEL = '/einstellungen/daten?block=energieprofil&karte=werkbank'
const PERSIST = 'v4-einst-daten'

/** Der «Beheben»-Knopf des Daten-Checkers als Stellvertreter: `navigate(link)` — wie `DatenCheckerTeile.tsx`. */
function Beheben() {
  const navigate = useNavigate()
  return <button type="button" onClick={() => navigate(ZIEL)}>Beheben</button>
}

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Beheben />
      <Routes>
        <Route path="/einstellungen/:kategorie" element={<EinstellungenV4 />} />
      </Routes>
    </MemoryRouter>,
  )
}

const scrollIntoView = vi.fn()

beforeEach(() => {
  localStorage.clear()
  scrollIntoView.mockClear()
  Element.prototype.scrollIntoView = scrollIntoView
})

describe('#440 — «Beheben» führt bis zur Reparatur-Werkbank', () => {
  it('(1)+(3) zugeklappter Block: Klick öffnet ihn und scrollt zur Werkbank-Karte', async () => {
    // Gemerkter Zustand: beide Blöcke zu.
    localStorage.setItem(`eedc-bloecke:${PERSIST}`, JSON.stringify({ order: ['datenchecker', 'energieprofil'], zu: ['datenchecker', 'energieprofil'] }))
    renderAt('/einstellungen/daten')
    expect(screen.queryByText('Reparatur-Werkbank')).toBeNull()
    fireEvent.click(screen.getByText('Beheben'))
    await waitFor(() => expect(screen.getByText('Reparatur-Werkbank')).toBeInTheDocument())
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1))
    expect(scrollIntoView.mock.contexts[0]).toBe(document.querySelector('[data-karte="werkbank"]'))
  })

  it('(4) der gemerkte Zustand ändert sich nur um diesen einen Block', async () => {
    localStorage.setItem(`eedc-bloecke:${PERSIST}`, JSON.stringify({ order: ['datenchecker', 'energieprofil'], zu: ['datenchecker', 'energieprofil'] }))
    renderAt('/einstellungen/daten')
    fireEvent.click(screen.getByText('Beheben'))
    await waitFor(() => expect(screen.getByText('Reparatur-Werkbank')).toBeInTheDocument())
    expect(ladeBlockState(PERSIST)).toEqual({ order: ['datenchecker', 'energieprofil'], zu: ['datenchecker'] })
  })

  it('(2) zweiter Klick mit gleichem Parameter, nachdem der Block wieder zugeklappt wurde: öffnet und scrollt erneut', async () => {
    renderAt(ZIEL)
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1))
    // Anwender klappt den Block zu …
    fireEvent.click(screen.getByRole('button', { name: 'einklappen' }))
    expect(screen.queryByText('Reparatur-Werkbank')).toBeNull()
    // … und klickt «Beheben» noch einmal — dieselbe Adresse.
    fireEvent.click(screen.getByText('Beheben'))
    await waitFor(() => expect(screen.getByText('Reparatur-Werkbank')).toBeInTheDocument())
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(2))
  })

  it('Klick bei offenem Block: scrollt zur Karte, auch beim dritten Mal', async () => {
    renderAt(ZIEL)
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(1))
    await act(async () => { fireEvent.click(screen.getByText('Beheben')) })
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(2))
    await act(async () => { fireEvent.click(screen.getByText('Beheben')) })
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(3))
  })

  it('ohne `karte` kein Scroll (der Block-Öffner allein bleibt wie bisher)', async () => {
    renderAt('/einstellungen/daten?block=energieprofil')
    await waitFor(() => expect(screen.getByText('Reparatur-Werkbank')).toBeInTheDocument())
    expect(scrollIntoView).not.toHaveBeenCalled()
  })
})
