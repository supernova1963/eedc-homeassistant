/**
 * ROI-Tabelle: „nicht bewertet" statt Fake-0 (N-87).
 *
 * Eine Split-Klimaanlage bekommt vom Backend keine konstruierte Ersparnis mehr
 * (sie ersetzt keine Heizung). Die Zeile darf deshalb NICHT „0 €" zeigen — das
 * wäre die Behauptung „spart nichts", während in Wahrheit der Wert fehlt.
 * Erwartet ist der Leerwert `—` samt sichtbarem Grund.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api')>()),
  investitionenApi: {
    getROIDashboard: vi.fn(() => Promise.resolve({
      gesamt_investition: 8000,
      gesamt_relevante_kosten: 8000,
      gesamt_sonstige_ausgaben_euro: 0,
      gesamt_kapitaleinsatz: 8000,
      gesamt_jahres_einsparung: 0,
      gesamt_roi_prozent: null,
      gesamt_amortisation_jahre: null,
      gesamt_co2_einsparung_kg: 0,
      benzinpreis_hinweis_euro: 1.7,
      berechnungen: [{
        investition_id: 1, investition_typ: 'waermepumpe', investition_bezeichnung: 'Daikin Split',
        relevante_kosten: 8000, kapitaleinsatz: 8000, anschaffungskosten: 8000, anschaffungskosten_alternativ: 0,
        jahres_einsparung: 0, roi_prozent: null, amortisation_jahre: null, co2_einsparung_kg: null,
        detail_berechnung: {
          nicht_bewertet: true,
          hinweis: 'Klimaanlage (Luft-Luft): eine Wirtschaftlichkeit gegenüber Gas oder Öl wird hier nicht berechnet.',
        },
        komponenten: [],
      }],
    })),
  },
}))

import { RoiAnalyse } from './RoiAnalyse'

describe('RoiAnalyse — nicht bewertete Komponente', () => {
  it('zeigt den Grund sichtbar an der Zeile, nicht nur im Tooltip', async () => {
    render(<RoiAnalyse anlageId={1} />)
    expect(await screen.findAllByText(/Daikin Split/)).not.toHaveLength(0)
    expect(screen.getAllByText(/nicht bewertet/).length).toBeGreaterThan(0)
  })

  it('zeigt in der Komponenten-Zeile Leerwerte statt einer 0-€-Ersparnis', async () => {
    render(<RoiAnalyse anlageId={1} />)
    const name = (await screen.findAllByText(/Daikin Split/))[0]
    const zeile = name.closest('tr')
    expect(zeile).not.toBeNull()

    const zellen = Array.from(zeile!.querySelectorAll('td')).map((td) => td.textContent?.trim())
    // Die Kosten stehen weiter da — unbewertet heißt nicht unsichtbar.
    expect(zellen.some((t) => t?.includes('8.000'))).toBe(true)
    // Ersparnis, ROI, Amortisation und CO₂ sind Leerwerte, keine Nullen.
    expect(zellen).toContain('—')
    expect(zellen.some((t) => t === '0 €')).toBe(false)
    expect(zellen.some((t) => t === '0 %')).toBe(false)
  })
})
