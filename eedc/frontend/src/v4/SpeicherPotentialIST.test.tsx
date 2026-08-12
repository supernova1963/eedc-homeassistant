/**
 * Der Block muss die gedeckelte Zahl **einordnen**, nicht nur anzeigen.
 *
 * „0 kWh" ohne Satz daneben liest sich wie ein fehlender Wert. Genau deshalb gibt
 * es den Befund-Text — und deshalb prüfen diese Tests ihn, nicht die Kacheln.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { SpeicherPotentialIST } from './SpeicherPotentialIST'
import { investitionenApi, type SpeicherPotentialResponse } from '../api/investitionen'

vi.mock('../components/park', () => ({
  Parkbar: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  usePark: () => ({ istGeparkt: () => false }),
}))

const ANTWORT = (teil: Partial<SpeicherPotentialResponse> = {}): SpeicherPotentialResponse => ({
  nutzbares_zusatzpotential_kwh: 0,
  ueberschuss_kwh: 471.6,
  stunden_voll: 114,
  zyklen_gesamt: 14,
  zyklen_leergelaufen: 0,
  deckelung_greift: true,
  tage_mit_daten: 12,
  von: '2026-06-10',
  bis: '2026-06-21',
  monate: [{
    jahr: 2026, monat: 6,
    nutzbares_zusatzpotential_kwh: 0, ueberschuss_kwh: 471.6,
    stunden_voll: 114, zyklen_gesamt: 14, zyklen_leergelaufen: 0,
    soc_bins: [0, 0, 0, 4, 12, 20, 30, 40, 68, 114],
  }],
  anzahl_speicher: 1,
  kapazitaet_kwh: 9.2,
  soc_voll_prozent: 95,
  soc_leer_prozent: 5,
  ...teil,
})

describe('SpeicherPotentialIST', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('sagt bei 0 kWh ausdrücklich, dass mehr Kapazität nichts gebracht hätte', async () => {
    // Der real gemessene Juni-Fall: 471,6 kWh Überschuss, aber keine leere Nacht.
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT())

    render(<SpeicherPotentialIST anlageId={1} />)

    await waitFor(() => {
      expect(screen.getByText(/nichts gebracht/i)).toBeInTheDocument()
    })
    // Die Obergrenze wird genannt — aber als Kontext, nicht als Versprechen.
    expect(screen.getByText(/472 kWh/)).toBeInTheDocument()
  })

  it('nennt bei echtem Potential die Nächte als Begrenzung', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT({
      nutzbares_zusatzpotential_kwh: 29.3,
      ueberschuss_kwh: 227.0,
      zyklen_gesamt: 8,
      zyklen_leergelaufen: 4,
    }))

    render(<SpeicherPotentialIST anlageId={1} />)

    await waitFor(() => {
      expect(screen.getByText(/4 von 8 Mal/)).toBeInTheDocument()
    })
    expect(screen.getByText(/29 kWh/)).toBeInTheDocument()
  })

  it('unterscheidet „kein Potential" von „keine Daten"', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(ANTWORT({
      tage_mit_daten: 0, monate: [], zyklen_gesamt: 0, ueberschuss_kwh: 0,
    }))

    render(<SpeicherPotentialIST anlageId={1} />)

    await waitFor(() => {
      expect(screen.getByText(/fehlen Stundenwerte/i)).toBeInTheDocument()
    })
    expect(screen.queryByText(/nichts gebracht/i)).not.toBeInTheDocument()
  })

  it('sagt bei mehreren Speichern, dass nur EIN Gerät ausgewertet wird', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(
      ANTWORT({ anzahl_speicher: 2 }),
    )

    render(<SpeicherPotentialIST anlageId={1} />)

    await waitFor(() => {
      // N-239: der Ladestand kommt vom ERSTEN gemappten Sensor, nicht aus einer
      // Mischung — die Sicht darf keine anlagenweite Aussage behaupten.
      expect(screen.getByText(/nicht die Anlage/i)).toBeInTheDocument()
    })
  })

  it('meldet die Park-ID erst, wenn wirklich etwas zu zeigen ist', async () => {
    vi.spyOn(investitionenApi, 'getSpeicherPotential').mockResolvedValue(
      ANTWORT({ tage_mit_daten: 0, monate: [] }),
    )
    const melde = vi.fn()

    render(<SpeicherPotentialIST anlageId={1} melde={melde} />)

    await waitFor(() => expect(melde).toHaveBeenCalled())
    expect(melde).toHaveBeenLastCalledWith([])
  })
})
