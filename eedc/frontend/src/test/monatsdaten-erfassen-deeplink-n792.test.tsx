/**
 * N-792 (ottokar, simon42 PN T95600 #2/#6): «Beheben» an einem Befund eines vorhandenen Monats öffnete das Formular
 * «Monatsdaten erfassen» — dessen Speichern endete mit 409 «Monatsdaten für M/JJJJ existieren bereits».
 *
 * Ursache: der Deep-Link-Effekt `?erfassen=YYYY-MM` lief, bevor die Monatsliste geladen war; `oeffneMonat` fand keine
 * Zeile und wählte das Create-Preset. Seit dem Fix wartet der Effekt auf die Liste (Muster `?bearbeiten=`).
 *
 * Der Hook `useMonatsdaten` ist steuerbar: er startet wie der echte mit `loading = true` und leerer Liste; die Probe
 * liefert die Liste nach dem Mount nach.
 */
import { describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { useEffect, useState } from 'react'

interface Zustand { monatsdaten: Array<Record<string, unknown>>; loading: boolean }
const steuer: { setze: ((z: Zustand) => void) | null } = { setze: null }

vi.mock('../hooks', () => ({
  useMonatsdaten: () => {
    const [z, setZ] = useState<Zustand>({ monatsdaten: [], loading: true })
    useEffect(() => { steuer.setze = setZ }, [])
    return {
      ...z, error: null,
      createMonatsdaten: vi.fn(), updateMonatsdaten: vi.fn(), deleteMonatsdaten: vi.fn(),
    }
  },
  useInvestitionen: () => ({ investitionen: [], loading: false }),
  useAnlage: () => ({ anlage: null }),
  useApiData: (fn: () => Promise<unknown>) => {
    const [data, setData] = useState<unknown>(null)
    useEffect(() => { fn().then(setData) }, [])  // eslint-disable-line react-hooks/exhaustive-deps
    return { data, loading: false, error: null }
  },
}))

// Das Formular selbst ist hier nicht Gegenstand — die Probe prüft, WELCHES sich öffnet (Titel + Zeile).
vi.mock('../components/forms', () => ({
  MonatsdatenForm: ({ monatsdaten, voreingestellterMonat, fokusFeld }: {
    monatsdaten?: { id: number }; voreingestellterMonat?: { jahr: number; monat: number } | null; fokusFeld?: string | null
  }) => (
    <div data-testid="formular" data-fokus={fokusFeld ?? ''}>
      {monatsdaten ? `bearbeiten ${monatsdaten.id}` : `erfassen ${voreingestellterMonat?.monat}/${voreingestellterMonat?.jahr}`}
    </div>
  ),
}))

vi.mock('../v4/wizardHost', () => ({ useOeffneWizard: () => null }))

vi.mock('../api/monatsdaten', () => ({ monatsdatenApi: { listAggregiert: () => Promise.resolve([]) } }))

vi.mock('../api/investitionen', () => ({
  investitionenApi: { getMonatsdatenByMonth: () => Promise.resolve([]) },
}))

vi.mock('../api/haStatistics', () => ({
  haStatisticsApi: {
    getStatus: () => Promise.resolve({ verfuegbar: false }),
    getVerfuegbareMonate: () => Promise.resolve([]),
    getMonatswerte: () => Promise.resolve(null),
  },
}))

const { MonatsdatenVerwaltung } = await import('../pages/MonatsdatenTeile')

const JANUAR = { id: 7, anlage_id: 1, jahr: 2026, monat: 1, einspeisung_kwh: 31.5, netzbezug_kwh: 402.0 }
const DEZEMBER = { id: 6, anlage_id: 1, jahr: 2025, monat: 12, einspeisung_kwh: 12.0, netzbezug_kwh: 455.0 }

function Ort() {
  const ort = useLocation()
  return <span data-testid="ort">{ort.search}</span>
}

function zeige(adresse = '/einstellungen/daten?erfassen=2026-01') {
  render(
    <MemoryRouter initialEntries={[adresse]}>
      <Routes>
        <Route path="/einstellungen/daten" element={<><MonatsdatenVerwaltung anlageId={1} /><Ort /></>} />
      </Routes>
    </MemoryRouter>,
  )
}

function liefere(monatsdaten: Array<Record<string, unknown>>) {
  act(() => { steuer.setze?.({ monatsdaten, loading: false }) })
}

describe('Deep-Link ?erfassen= wartet auf die Monatsliste (N-792)', () => {
  it('A: Liste trifft nach dem Mount ein, Monat vorhanden ⇒ Bearbeiten-Form, nie das Erfassen-Formular', async () => {
    zeige()
    // Während des Ladens bleibt der Parameter stehen und nichts öffnet sich.
    expect(screen.getByTestId('ort').textContent).toBe('?erfassen=2026-01')
    expect(screen.queryByText(/Monatsdaten erfassen/)).toBeNull()
    liefere([JANUAR, DEZEMBER])
    await screen.findByText('Monatsdaten bearbeiten')
    expect(screen.getByTestId('formular').textContent).toBe('bearbeiten 7')
    expect(screen.queryByText('Monatsdaten erfassen - Jan 2026')).toBeNull()
  })

  it('B: Monat fehlt in der Liste ⇒ Erfassen-Formular für Jan 2026', async () => {
    zeige()
    liefere([DEZEMBER])
    await screen.findByText('Monatsdaten erfassen - Jan 2026')
    expect(screen.getByTestId('formular').textContent).toBe('erfassen 1/2026')
    expect(screen.queryByText('Monatsdaten bearbeiten')).toBeNull()
  })

  it('C: Parameter entfernt, kein zweites Öffnen bei erneutem Render', async () => {
    zeige()
    liefere([JANUAR, DEZEMBER])
    await screen.findByText('Monatsdaten bearbeiten')
    await waitFor(() => expect(screen.getByTestId('ort').textContent).toBe(''))
    fireEvent.click(screen.getByRole('button', { name: 'Schließen' }))
    await waitFor(() => expect(screen.queryByText('Monatsdaten bearbeiten')).toBeNull())
    // Neue Liste ⇒ erneuter Render des Effekts; der Parameter ist weg, nichts öffnet sich wieder.
    liefere([{ ...JANUAR, einspeisung_kwh: 32.0 }, DEZEMBER])
    await waitFor(() => expect(screen.getByTestId('ort').textContent).toBe(''))
    expect(screen.queryByText('Monatsdaten bearbeiten')).toBeNull()
    expect(screen.queryByText(/Monatsdaten erfassen/)).toBeNull()
    expect(screen.queryByTestId('formular')).toBeNull()
  })

  it('D (E4): `geraet` und `feld` gehen als Sprung-Ziel ans Formular, alle drei Parameter verschwinden', async () => {
    zeige('/einstellungen/daten?erfassen=2026-01&geraet=3&feld=ladung_kwh')
    expect(screen.getByTestId('ort').textContent).toBe('?erfassen=2026-01&geraet=3&feld=ladung_kwh')
    liefere([JANUAR, DEZEMBER])
    await screen.findByText('Monatsdaten bearbeiten')
    expect(screen.getByTestId('formular').getAttribute('data-fokus')).toContain('inv-3-ladung_kwh')
    await waitFor(() => expect(screen.getByTestId('ort').textContent).toBe(''))
  })

  it('E (E4): `geraet` allein springt zum ersten Feld des Geräts', async () => {
    zeige('/einstellungen/daten?erfassen=2026-01&geraet=3')
    liefere([JANUAR])
    await screen.findByText('Monatsdaten bearbeiten')
    expect(screen.getByTestId('formular').getAttribute('data-fokus')).toBe('[data-feld^="inv-3-"]')
  })
})
