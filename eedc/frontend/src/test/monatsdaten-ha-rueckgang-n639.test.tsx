/**
 * N-639 (Frank85, PN 08.10.2026): der Vergleichsdialog „Aus HA laden" nennt einen negativen HA-Wert.
 *
 * Fällt die Summe eines Sensors in HAs Langzeitstatistik (Anpassung nach unten), liefert „Aus HA laden" für den Monat
 * einen negativen Wert — bei Frank Einspeisung −39,9 und Netzbezug −321,1 für Juni 2025. eedc rechnet wie das
 * HA-Energie-Dashboard und übernimmt ihn; der Dialog zeigt dann unter den Tabellen den Hinweis (SoT `Alert`, Kurzform
 * der Daten-Checker-Meldung „Zählerstände – Rückgang in Home Assistant"). Ohne negativen Wert kein Hinweis.
 *
 * Der Dialog wird über den echten Weg geöffnet: „Aus HA laden" → „Werte laden" für einen Monat, der schon Daten hat.
 * Die Uhr ist gestellt (Vorauswahl des Dialogs = Vormonat der Uhr), damit keine Probe an der echten Stunde hängt (N-167).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { useEffect, useState } from 'react'
import type { Monatswerte } from '../api/haStatistics'

const zustand: { haWerte: Monatswerte | null } = { haWerte: null }

vi.mock('../hooks', () => ({
  useMonatsdaten: () => ({
    monatsdaten: [{ id: 4, anlage_id: 1, jahr: 2025, monat: 6, einspeisung_kwh: 20.2, netzbezug_kwh: 218.6 }],
    loading: false, error: null,
    createMonatsdaten: vi.fn(), updateMonatsdaten: vi.fn(), deleteMonatsdaten: vi.fn(),
  }),
  useInvestitionen: () => ({ investitionen: [], loading: false }),
  useAnlage: () => ({ anlage: null }),
  // Wie der echte Hook: lädt einmal und liefert die Daten (Status „verfügbar", leere Monatsliste).
  useApiData: (fn: () => Promise<unknown>) => {
    const [data, setData] = useState<unknown>(null)
    useEffect(() => { fn().then(setData) }, [])  // eslint-disable-line react-hooks/exhaustive-deps
    return { data, loading: false, error: null }
  },
}))

vi.mock('../v4/wizardHost', () => ({ useOeffneWizard: () => null }))

vi.mock('../api/monatsdaten', () => ({ monatsdatenApi: { listAggregiert: () => Promise.resolve([]) } }))

vi.mock('../api/investitionen', () => ({
  investitionenApi: { getMonatsdatenByMonth: () => Promise.resolve([]) },
}))

vi.mock('../api/haStatistics', () => ({
  haStatisticsApi: {
    getStatus: () => Promise.resolve({ verfuegbar: true }),
    getVerfuegbareMonate: () => Promise.resolve([{ jahr: 2025, monat: 6, monat_name: 'Juni', hat_daten: true }]),
    getMonatswerte: () => Promise.resolve(zustand.haWerte),
  },
}))

const { MonatsdatenVerwaltung } = await import('../pages/MonatsdatenTeile')

const werte = (einsp: number, netz: number): Monatswerte => ({
  jahr: 2025, monat: 6, monat_name: 'Juni',
  basis: [
    { feld: 'einspeisung_kwh', label: 'Einspeisung', wert: einsp, einheit: 'kWh' },
    { feld: 'netzbezug_kwh', label: 'Netzbezug', wert: netz, einheit: 'kWh' },
    { feld: 'pv_erzeugung_kwh', label: 'PV Erzeugung Gesamt', wert: 161.4, einheit: 'kWh' },
  ],
  investitionen: [],
})

async function oeffneVergleich() {
  render(<MemoryRouter><MonatsdatenVerwaltung anlageId={1} /></MemoryRouter>)
  fireEvent.click(await screen.findByRole('button', { name: /Aus HA laden/ }))
  fireEvent.click(await screen.findByRole('button', { name: /Werte laden/ }))
  await screen.findByText('Vergleich: Juni 2025')
}

describe('Vergleichsdialog „Aus HA laden": Rückgang in Home Assistant (N-639)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date(2025, 6, 15, 12))   // Juli 2025 ⇒ Vorauswahl Juni 2025
  })
  afterEach(() => { vi.useRealTimers() })

  it('ein negativer HA-Wert ⇒ Hinweis mit den Feldern und dem Weg in Home Assistant', async () => {
    zustand.haWerte = werte(-39.9, -321.1)
    await oeffneVergleich()
    expect(screen.getByText('Rückgang in Home Assistant: Einspeisung, Netzbezug')).toBeTruthy()
    const hinweis = screen.getByText(/Home Assistant liefert hier einen negativen Wert/)
    expect(hinweis.textContent).toContain('Entwicklerwerkzeuge → Statistik')
    expect(hinweis.textContent).toContain('Wert anpassen')
    expect(hinweis.textContent).toContain('nachts von selbst ab')
  })

  it('ohne negativen Wert kein Hinweis (Gegenprobe: der Dialog steht)', async () => {
    zustand.haWerte = werte(39.9, 321.1)
    await oeffneVergleich()
    await waitFor(() => expect(screen.getByText('Basis-Werte (kWh)')).toBeTruthy())
    expect(screen.queryByText(/Rückgang in Home Assistant/)).toBeNull()
    expect(screen.queryByText(/negativen Wert/)).toBeNull()
  })
})
