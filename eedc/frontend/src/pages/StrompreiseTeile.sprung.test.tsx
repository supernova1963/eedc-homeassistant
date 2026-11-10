/**
 * E4 (5) «Daten-Checker: Sprung aufs Feld» — Strompreise (`?block=strompreise&tarif=…`) und Anlage (`?block=anlage&feld=…`).
 *
 * Strompreise: `tarif=neu&art=<verwendung>&ab=<datum>` öffnet «Neuen Tarif anlegen» mit Verwendung und Beginn vorbelegt
 * (Teil B Nr 144 «Lücke», Nr 140 `kein_strompreis`); `tarif=<id>&feld=<spalte>` öffnet den Tarif und fokussiert das
 * Feld. Anlage: `feld=installationsdatum` öffnet die gewählte Anlage, das Datumsfeld trägt den Fokus. Die Parameter
 * verschwinden; gilt `block` einem anderen Block, reagiert die Seite nicht.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom'

const tarif = {
  id: 4, anlage_id: 1, netzbezug_arbeitspreis_cent_kwh: 31, einspeiseverguetung_cent_kwh: 0, grundpreis_euro_monat: 10,
  gueltig_ab: '2025-01-01', gueltig_bis: null, tarifname: 'Grund', anbieter: 'X', vertragsart: '', verwendung: 'allgemein',
}
const anlage = { id: 1, anlagenname: 'Haus', leistung_kwp: 9.9, installationsdatum: null }

vi.mock('../hooks', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  useStrompreise: () => ({
    strompreise: [tarif], loading: false, error: null,
    createStrompreis: vi.fn(), updateStrompreis: vi.fn(), deleteStrompreis: vi.fn(),
  }),
  useAnlage: () => ({ anlage }),
  useAnlagen: () => ({ anlagen: [anlage], loading: false, error: null,
    createAnlage: vi.fn(), updateAnlage: vi.fn(), deleteAnlage: vi.fn() }),
  useSelectedAnlage: () => ({ selectedAnlageId: 1, selectedAnlage: anlage }),
}))

const { StrompreiseVerwaltung } = await import('./StrompreiseTeile')
const { AnlagenVerwaltung } = await import('./AnlagenTeile')

function Ort() {
  return <span data-testid="ort">{useLocation().search}</span>
}

function zeige(adresse: string, seite: 'strompreise' | 'anlage') {
  render(
    <MemoryRouter initialEntries={[adresse]}>
      <Routes>
        <Route path="/einstellungen/stammdaten" element={
          <>{seite === 'strompreise' ? <StrompreiseVerwaltung anlageId={1} /> : <AnlagenVerwaltung />}<Ort /></>
        } />
      </Routes>
    </MemoryRouter>,
  )
}

// Feste Uhr (Wächter N7): nur `Date` — die Wartezeit des Sprungs (`setTimeout`) läuft echt.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] })
  vi.setSystemTime(new Date('2026-11-10T12:00:00'))
  Element.prototype.scrollIntoView = vi.fn()
})
afterEach(() => { vi.useRealTimers() })

describe('Strompreise: Sprung (E4)', () => {
  it('`tarif=neu&art=waermepumpe&ab=2026-03-01`: Neuer Tarif, Verwendung und Beginn vorbelegt, Parameter weg', async () => {
    zeige('/einstellungen/stammdaten?block=strompreise&tarif=neu&art=waermepumpe&ab=2026-03-01', 'strompreise')
    await screen.findByText('Neuen Tarif anlegen')
    expect((screen.getByDisplayValue('waermepumpe') as HTMLInputElement).checked).toBe(true)
    expect(document.querySelector('[data-feld="gueltig_ab"]')!.textContent).toContain('1. März 2026')
    await waitFor(() => expect(screen.getByTestId('ort').textContent).toBe('?block=strompreise'))
  })

  it('`tarif=<id>&feld=gueltig_ab`: Tarif offen, Datumsfeld fokussiert', async () => {
    zeige('/einstellungen/stammdaten?block=strompreise&tarif=4&feld=gueltig_ab', 'strompreise')
    await screen.findByText('Tarif bearbeiten')
    await waitFor(() => expect(document.querySelector('[data-feld="gueltig_ab"]')!.contains(document.activeElement)).toBe(true))
    await waitFor(() => expect(screen.getByTestId('ort').textContent).toBe('?block=strompreise'))
  })

  it('ein Sprung für einen anderen Block öffnet hier nichts und bleibt in der Adresse', async () => {
    zeige('/einstellungen/stammdaten?block=anlage&feld=installationsdatum', 'strompreise')
    await screen.findByText('Neuer Tarif')
    expect(screen.queryByText('Tarif bearbeiten')).toBeNull()
    expect(screen.getByTestId('ort').textContent).toBe('?block=anlage&feld=installationsdatum')
  })
})

describe('Anlage: Sprung (E4)', () => {
  it('`feld=installationsdatum`: gewählte Anlage offen, Datumsfeld fokussiert, Parameter weg', async () => {
    zeige('/einstellungen/stammdaten?block=anlage&feld=installationsdatum', 'anlage')
    await screen.findByText('Anlage bearbeiten')
    await waitFor(() =>
      expect(document.querySelector('[data-feld="installationsdatum"]')!.contains(document.activeElement)).toBe(true))
    await waitFor(() => expect(screen.getByTestId('ort').textContent).toBe('?block=anlage'))
  })
})
