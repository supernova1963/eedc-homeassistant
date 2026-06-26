/**
 * RoiAnalyse — Smoke-Test der ausgelagerten ROI-Analyse (Sicherheitsnetz für die
 * Extraktion aus ROIDashboard). Prüft KPIs + Detail-Tabelle + onLoaded-Rückkanal.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api')>()),
  investitionenApi: {
    getROIDashboard: vi.fn(() => Promise.resolve({
      gesamt_investition: 20000,
      gesamt_relevante_kosten: 15000,
      gesamt_jahres_einsparung: 1500,
      gesamt_roi_prozent: 10,
      gesamt_amortisation_jahre: 10,
      gesamt_co2_einsparung_kg: 2000,
      benzinpreis_hinweis_euro: 1.7,
      berechnungen: [{
        investition_id: 1, investition_typ: 'speicher', investition_bezeichnung: 'BYD HVS 10',
        relevante_kosten: 8000, anschaffungskosten: 8000, anschaffungskosten_alternativ: 0,
        jahres_einsparung: 600, roi_prozent: 7.5, amortisation_jahre: 13, co2_einsparung_kg: 0,
        detail_berechnung: null, komponenten: [],
      }],
    })),
  },
}))

import { RoiAnalyse } from './RoiAnalyse'

describe('RoiAnalyse', () => {
  it('lädt + rendert KPIs, Detailzeile und meldet onLoaded', async () => {
    const onLoaded = vi.fn()
    render(<RoiAnalyse anlageId={1} onLoaded={onLoaded} />)
    // KPIs erscheinen nach dem Laden.
    expect(await screen.findAllByText(/Gesamtinvestition/)).not.toHaveLength(0)
    expect(screen.getAllByText(/Amortisation/).length).toBeGreaterThan(0)
    // Detail-Zeile der einzelnen Investition.
    expect(screen.getAllByText(/BYD HVS 10/).length).toBeGreaterThan(0)
    // Rückkanal liefert den Benzinpreis-Hinweis.
    await waitFor(() => expect(onLoaded).toHaveBeenCalled())
    expect(onLoaded.mock.calls[0][0].benzinpreis_hinweis_euro).toBe(1.7)
  })
})
