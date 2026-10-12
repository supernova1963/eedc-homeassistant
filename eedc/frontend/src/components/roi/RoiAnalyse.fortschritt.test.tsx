/**
 * N-719 — der Tooltip der Kachel „Amortisations-Fortschritt" nennt Zähler und Nenner der Quote, wie der Server sie
 * rechnet (F-19): bisherige Erträge ohne beide Seiten der sonstigen Positionen ÷ Kapitaleinsatz.
 *
 * Gemessen am HEAD `0c3a89fa` (Fall S: PV 10.000 €, Reparatur 500 € als sonstige Ausgabe): Berechnung
 * „1.276 € ÷ 10.000 €" (Zeitraum-Bilanz ÷ Mehrkosten, ergäbe 12,8 %) neben „= 16,9 % gedeckt"; richtig
 * „1.776 € ÷ 10.500 €". Der Untertitel „noch 8.724 €" stimmte schon (beide Seiten gleich verschoben) und bleibt.
 *
 * Schwesterdateien: RoiAnalyse.test.tsx (Kachel steht), backend test_n719_amortisation_zaehler_in_der_antwort.py
 * (der Server liefert den Zähler).
 */
import { describe, it, expect, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api')>()),
  investitionenApi: {
    getROIDashboard: vi.fn(() => Promise.resolve({
      gesamt_investition: 10000, gesamt_relevante_kosten: 10000, gesamt_sonstige_ausgaben_euro: 500,
      gesamt_kapitaleinsatz: 10500, gesamt_jahres_einsparung: 900, gesamt_roi_prozent: 8.6,
      gesamt_amortisation_jahre: 11.7, amortisation_annahme: null, gesamt_co2_einsparung_kg: 0,
      basis_jahr: 2024, gesamt_amortisation_jahr: 2035, amortisations_verlauf: [], berechnungen: [],
    })),
  },
}))

vi.mock('../../api/aussichten', () => ({
  aussichtenApi: {
    getFinanzPrognose: vi.fn(() => Promise.resolve({
      amortisations_fortschritt_prozent: 16.9,
      amortisation_erreicht: false,
      bisherige_ertraege_euro: 1276,       // Zeitraum-Bilanz (mit der Reparatur abgezogen)
      investition_gesamt_euro: 10000,      // Mehrkosten
      kapitaleinsatz_euro: 10500,          // Nenner der Quote
      amortisation_ertraege_euro: 1776,    // Zähler der Quote
      amortisation_prognose_jahr: null,
    })),
  },
}))

import { roiKpiItems, useRoiAnalyse } from './RoiAnalyse'

describe('N-719 — Amortisations-Fortschritt: der Tooltip rechnet wie die Kachel', () => {
  it('nennt Zähler ÷ Kapitaleinsatz der Quote, der Untertitel bleibt', async () => {
    const { result } = renderHook(() => useRoiAnalyse({ anlageId: 1 }))
    await waitFor(() => expect(result.current.roiData).not.toBeNull())
    await waitFor(() => expect(result.current.fortschritt).not.toBeNull())
    const kachel = roiKpiItems(result.current.roiData!, false, result.current.fortschritt)
      .find((k) => k.title === 'Amortisations-Fortschritt')!
    expect(kachel.berechnung).toBe('1.776 € ÷ 10.500 €')
    expect(kachel.ergebnis).toBe('= 16,9 % gedeckt')
    expect(kachel.formel).toBe('Bisherige Erträge ÷ Kapitaleinsatz × 100')
    expect(kachel.subtitle).toBe('noch 8.724 €')
  })
})
