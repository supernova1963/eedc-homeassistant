/**
 * AuswertungenRoiV4 — Smoke-Test (A.5 Sub 5): die 4 Blöcke rendern, Block ① zeigt die
 * 3 KPIs (CO₂-KPI entfällt, R4), Geld trägt die R1/R2-Form (€ mit Tausenderpunkt, kein
 * k€). API/Hooks gestubbt → isoliert auf die Sicht-Komposition.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../hooks', () => ({
  useSelectedAnlage: () => ({
    anlagen: [{ id: 1, anlagenname: 'Test' }], selectedAnlageId: 1,
    selectedAnlage: { id: 1, anlagenname: 'Test' }, loading: false,
  }),
  useAktuellerStrompreis: () => ({
    strompreis: { netzbezug_arbeitspreis_cent_kwh: 30, einspeiseverguetung_cent_kwh: 8.2 },
  }),
}))

vi.mock('../api/investitionen', () => ({
  investitionenApi: {
    getROIDashboard: vi.fn().mockResolvedValue({
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
    }),
  },
}))

import AuswertungenRoiV4 from './AuswertungenRoiV4'

describe('AuswertungenRoiV4 (Sub 5)', () => {
  it('rendert die 4 Blöcke; Block ① ohne CO₂-KPI; Geld in € (R1/R2)', async () => {
    render(<AuswertungenRoiV4 />)
    // Block-Titel (BlockShell-Header) erscheinen nach dem ROI-Load.
    expect(await screen.findByText('Wirtschaftlichkeit auf einen Blick')).toBeInTheDocument()
    // „Amortisation" doppelt (KPI-Titel in Block ① + Block-②-Titel) → getAllByText.
    expect(screen.getAllByText('Amortisation').length).toBeGreaterThan(0)
    expect(screen.getByText('Verteilung & Vergleich')).toBeInTheDocument()
    expect(screen.getByText('Detailübersicht je Investition')).toBeInTheDocument()
    // Block ① ist offen → 3 KPIs, CO₂-KPI entfällt (R4).
    expect(screen.getByText('Gesamtinvestition')).toBeInTheDocument()
    expect(screen.getByText('Jährliche Einsparung')).toBeInTheDocument()
    expect(screen.queryByText('CO2-Einsparung')).not.toBeInTheDocument()
    // R1/R2: 20.000 € mit Tausenderpunkt (KPI-Wert + €-Einheit getrennt).
    expect(screen.getByText('20.000')).toBeInTheDocument()
  })
})
