/**
 * TKonto — Smoke-Test des ausgelagerten SOLL/HABEN-T-Kontos (Sicherheitsnetz für
 * die Extraktion aus MonatsabschlussView). Prüft SOLL/HABEN-Struktur, Summen und
 * Gewinn/Verlust-Logik. Desktop- + Mobile-Tabelle rendern beide in jsdom (CSS
 * versteckt nicht) → getAllByText.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TKonto } from './TKonto'
import type { AktuellerMonatResponse } from '../../api/aktuellerMonat'

const basis = {
  anlage_id: 1, anlage_name: 'Demo', jahr: 2025, monat: 5, monat_name: 'Mai',
  aktualisiert_um: '', quellen: {},
  einspeisung_kwh: 100, einspeise_preis_cent: 8, einspeise_erloes_euro: 8,
  eigenverbrauch_kwh: 120, ev_ersparnis_euro: 36,
  netzbezug_kwh: 50, netzbezug_preis_cent: 30, netzbezug_kosten_euro: 15,
  netto_ertrag_euro: 29, gesamtnettoertrag_euro: 29,
  betriebskosten_anteilig_euro: 0, sonstige_ertraege_euro: 0, sonstige_ausgaben_euro: 0, sonstige_netto_euro: 0,
  investitionen_financials: [],
  komponenten_geraete: {}, feld_quellen: {}, vorjahr: null,
} as unknown as AktuellerMonatResponse

describe('TKonto', () => {
  it('rendert SOLL/HABEN-Struktur + Summen + Gewinn (Haben 44 > Soll 15)', () => {
    render(<TKonto d={basis} />)
    expect(screen.getAllByText(/Einspeise-Erlöse/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Netzbezug-Kosten/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Σ Soll/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Σ Haben/).length).toBeGreaterThan(0)
    // Haben (8 + 36) > Soll (15) → Gewinn
    expect(screen.getAllByText(/Gewinn/).length).toBeGreaterThan(0)
  })

  it('zeigt Verlust, wenn Kosten die Erlöse übersteigen', () => {
    const verlust = { ...basis, einspeise_erloes_euro: 2, ev_ersparnis_euro: 3, netzbezug_kosten_euro: 40 } as AktuellerMonatResponse
    render(<TKonto d={verlust} />)
    expect(screen.getAllByText(/Verlust/).length).toBeGreaterThan(0)
  })
})
