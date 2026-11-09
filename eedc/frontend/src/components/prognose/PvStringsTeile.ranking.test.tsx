/**
 * Ranking-Sperre bei verteilten Modulwerten (A4/b1).
 *
 * Sind die IST-Werte anteilig nach kWp aus der Gesamterzeugung gerechnet, hat
 * rechnerisch jedes Modul denselben spezifischen Ertrag — eine Platzierung wäre
 * eine Aussage, die die Daten nicht hergeben. Das Backend liefert deshalb
 * `bester_string = null` + `vergleich_hinweis`; hier wird geprüft, dass die
 * Anzeige das übernimmt UND dass der „alle Jahre"-Pfad die Sperre nicht wieder aufhebt.
 *
 * Päckchen BB4 (9.11.2026): „alle Jahre" faltet nicht mehr im Client, sondern liest die Laufzeit-Route — dort
 * entscheidet `_ranking` (dieselbe Funktion wie die Jahresroute, Probe `test_pv_strings_kwp_verteilung.py`); der
 * Adapter reicht Platzierung, Quelle und Hinweis unverändert durch.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { renderHook } from '@testing-library/react'

const getPVStrings = vi.fn()
const getPVStringsGesamtlaufzeit = vi.fn()
vi.mock('../../api/cockpit', () => ({ cockpitApi: {
  getPVStrings: (...a: unknown[]) => getPVStrings(...a),
  getPVStringsGesamtlaufzeit: (...a: unknown[]) => getPVStringsGesamtlaufzeit(...a),
} }))

import { PvStringBestSchlecht, usePvStrings } from './PvStringsTeile'
import type { PVStringsResponse, PVStringsGesamtlaufzeitResponse } from '../../api/cockpit'

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

const laufzeit = (over: Partial<PVStringsGesamtlaufzeitResponse> = {}): PVStringsGesamtlaufzeitResponse => ({
  anlage_id: 1, hat_prognose: true, prognose_warnung: null, anlagen_leistung_kwp: 10,
  erstes_jahr: 2024, letztes_jahr: 2025, anzahl_jahre: 2, anzahl_monate: 24,
  prognose_gesamt_kwh: 4000, ist_gesamt_kwh: 2000, abweichung_gesamt_kwh: -2000, abweichung_gesamt_prozent: -50,
  spezifischer_ertrag_zeitraum_kwh_kwp: 200,
  strings: [11, 12].map((id) => ({
    investition_id: id, bezeichnung: id === 11 ? 'Süd' : 'Nord', leistung_kwp: 5, ausrichtung: null,
    neigung_grad: null, wechselrichter_name: null, prognose_gesamt_kwh: 2000, ist_gesamt_kwh: id === 11 ? 1400 : 600,
    abweichung_gesamt_prozent: null, performance_ratio_gesamt: id === 11 ? 0.7 : 0.3,
    spezifischer_ertrag_kwh_kwp: null, ist_quelle: 'gemessen' as const, jahreswerte: [], saisonalwerte: [],
    abweichung_gesamt_kwh: 0, monatswerte_summe: [],
  })),
  saisonal_aggregiert: [], bester_string: 'Süd', schlechtester_string: 'Nord',
  ist_quelle: 'gemessen', vergleich_hinweis: null,
  ...over,
})

describe('usePvStrings — „alle Jahre" aus der Laufzeit-Route (BB4)', () => {
  it('übernimmt die Ranking-Sperre der Route (ein verteiltes Jahr sperrt)', async () => {
    getPVStrings.mockResolvedValue(antwort())
    getPVStringsGesamtlaufzeit.mockResolvedValue(laufzeit({
      ist_quelle: 'verteilt', bester_string: null, schlechtester_string: null,
      vergleich_hinweis: 'Ein Vergleich einzelner Strings ist mit diesen Werten nicht möglich.',
    }))
    const { result } = renderHook(() => usePvStrings(1, 'all', JAHRE))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data?.ist_quelle).toBe('verteilt')
    expect(result.current.data?.bester_string).toBeNull()
    expect(result.current.data?.vergleich_hinweis).toContain('nicht möglich')
  })

  it('behält die Platzierung der Route, wenn alles gemessen ist', async () => {
    getPVStrings.mockResolvedValue(antwort())
    getPVStringsGesamtlaufzeit.mockResolvedValue(laufzeit())
    const { result } = renderHook(() => usePvStrings(1, 'all', JAHRE))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data?.ist_quelle).toBe('gemessen')
    expect(result.current.data?.bester_string).toBe('Süd')
    expect(result.current.data?.schlechtester_string).toBe('Nord')
  })
})
