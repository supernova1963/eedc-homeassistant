/**
 * Ranking-Sperre bei verteilten Modulwerten (A4/b1).
 *
 * Sind die IST-Werte anteilig nach kWp aus der Gesamterzeugung gerechnet, hat
 * rechnerisch jedes Modul denselben spezifischen Ertrag — eine Platzierung wäre
 * eine Aussage, die die Daten nicht hergeben. Das Backend liefert deshalb
 * `bester_string = null` + `vergleich_hinweis`; hier wird geprüft, dass die
 * Anzeige das übernimmt UND dass der Client-eigene „alle Jahre"-Aggregationspfad
 * die Sperre nicht wieder aufhebt.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { renderHook } from '@testing-library/react'

const getPVStrings = vi.fn()
vi.mock('../../api/cockpit', () => ({ cockpitApi: { getPVStrings: (...a: unknown[]) => getPVStrings(...a) } }))

import { PvStringBestSchlecht, usePvStrings } from './PvStringsTeile'
import type { PVStringsResponse } from '../../api/cockpit'

const string = (id: number, bezeichnung: string, ist: number, ratio: number) => ({
  investition_id: id, bezeichnung, leistung_kwp: 5, ausrichtung: null, neigung_grad: null,
  wechselrichter_id: null, wechselrichter_name: null,
  prognose_jahr_kwh: 1000, ist_jahr_kwh: ist, abweichung_jahr_kwh: ist - 1000,
  abweichung_jahr_prozent: null, performance_ratio_jahr: ratio,
  spezifischer_ertrag_kwh_kwp: ist / 5, ist_quelle: 'gemessen' as const, monatswerte: [],
})

const antwort = (over: Partial<PVStringsResponse> = {}): PVStringsResponse => ({
  anlage_id: 1, jahr: 2025, hat_prognose: true, prognose_warnung: null, anlagen_leistung_kwp: 10,
  prognose_gesamt_kwh: 2000, ist_gesamt_kwh: 1000, abweichung_gesamt_kwh: -1000,
  abweichung_gesamt_prozent: -50,
  strings: [string(11, 'Süd', 700, 0.7), string(12, 'Nord', 300, 0.3)],
  bester_string: 'Süd', schlechtester_string: 'Nord',
  ist_quelle: 'gemessen', vergleich_hinweis: null,
  ...over,
})

beforeEach(() => vi.clearAllMocks())

// Stabile Referenz: `usePvStrings` hängt seinen Ladeeffekt an `verfuegbareJahre`
// — ein Inline-Literal löste bei jedem Render neu (Endlosschleife im Test).
const JAHRE = [2024, 2025]

describe('PvStringBestSchlecht', () => {
  it('zeigt die Platzierung bei gemessenen Werten', () => {
    render(<PvStringBestSchlecht data={antwort()} />)
    expect(screen.getByText('Süd')).toBeInTheDocument()
    expect(screen.getByText('Nord')).toBeInTheDocument()
  })

  it('ersetzt die Platzierung durch die Erklärung, wenn die Werte verteilt sind', () => {
    render(<PvStringBestSchlecht data={antwort({
      bester_string: null, schlechtester_string: null, ist_quelle: 'verteilt',
      vergleich_hinweis: 'Ein Vergleich einzelner Strings ist mit diesen Werten nicht möglich.',
    })} />)
    expect(screen.queryByText('Beste Performance')).not.toBeInTheDocument()
    expect(screen.getByText(/nicht möglich/)).toBeInTheDocument()
    expect(screen.getByLabelText('geschätzt (kWp-Anteil)')).toBeInTheDocument()
  })
})

describe('usePvStrings — „alle Jahre" aggregiert im Client', () => {
  it('zieht die Ranking-Sperre mit, sobald EIN Jahr verteilt ist', async () => {
    getPVStrings.mockImplementation((_id: number, jahr: number) => Promise.resolve(
      jahr === 2024
        ? antwort({ jahr: 2024, ist_quelle: 'verteilt', bester_string: null, schlechtester_string: null,
          vergleich_hinweis: 'Ein Vergleich einzelner Strings ist mit diesen Werten nicht möglich.' })
        : antwort({ jahr: 2025 })))
    const { result } = renderHook(() => usePvStrings(1, 'all', JAHRE))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data?.ist_quelle).toBe('verteilt')
    expect(result.current.data?.bester_string).toBeNull()
    expect(result.current.data?.vergleich_hinweis).toContain('nicht möglich')
  })

  it('behält die Platzierung, wenn alle Jahre gemessen sind', async () => {
    getPVStrings.mockResolvedValue(antwort())
    const { result } = renderHook(() => usePvStrings(1, 'all', JAHRE))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data?.ist_quelle).toBe('gemessen')
    expect(result.current.data?.bester_string).toBe('Süd')
  })
})
