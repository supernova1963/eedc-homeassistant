/**
 * RoiAnalyse — Smoke-Test der ausgelagerten ROI-Analyse (Sicherheitsnetz für die
 * Extraktion aus ROIDashboard). Prüft KPIs + Detail-Tabelle + onLoaded-Rückkanal.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { readFileSync } from 'node:fs'

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

vi.mock('../../api/aussichten', () => ({
  aussichtenApi: {
    getFinanzPrognose: vi.fn(() => Promise.resolve({
      amortisations_fortschritt_prozent: 40,
      amortisation_erreicht: false,
      bisherige_ertraege_euro: 6000,
      // Derselbe Nenner wie `gesamt_relevante_kosten` oben — das ist die
      // Zusicherung, die N-137 überhaupt erst möglich gemacht hat.
      investition_gesamt_euro: 15000,
      amortisation_prognose_jahr: 2032,
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

  it('N-90: die Leerwerte der ROI-Tabelle sind Halbgeviertstriche, keine Bindestriche', () => {
    // Style-Guide A3: Display-Token `—` (etabliert v3.29.1). In dieser Datei
    // standen sechs nicht migrierte ASCII-Bindestriche neben bereits
    // umgestellten Nachbarn — eine Anzeige, zwei Zeichen.
    const quelle = readFileSync('src/components/roi/RoiAnalyse.tsx', 'utf-8')
    // Leerwert-Formen, die es nicht mehr geben darf.
    expect(quelle).not.toMatch(/: '-'/)
    expect(quelle).not.toMatch(/>-</)
    expect(quelle).not.toMatch(/\? `[^`]*` : '-'/)
  })

  it('N-137: Amortisations-Fortschritt steht als eigene Kachel neben der Dauer', async () => {
    render(<RoiAnalyse anlageId={1} />)
    expect(await screen.findAllByText(/Amortisations-Fortschritt/)).not.toHaveLength(0)
    // 6.000 von 15.000 = 40 % — gemessen, nicht hochgerechnet.
    expect(screen.getAllByText('40,0').length).toBeGreaterThan(0)
    // Der Untertitel nennt Restbetrag und voraussichtliches Jahr.
    expect(screen.getAllByText(/noch 9\.000 €.*2032/).length).toBeGreaterThan(0)
  })

  it('N-137: ohne Fortschritts-Zahl entfällt die Kachel, der Rest steht', async () => {
    const { aussichtenApi } = await import('../../api/aussichten')
    vi.mocked(aussichtenApi.getFinanzPrognose).mockRejectedValueOnce(new Error('offline'))
    render(<RoiAnalyse anlageId={1} />)
    expect(await screen.findAllByText(/Gesamtinvestition/)).not.toHaveLength(0)
    expect(screen.queryByText(/Amortisations-Fortschritt/)).not.toBeInTheDocument()
  })
})
