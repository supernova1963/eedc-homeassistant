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

  it('weist den §51-Verlust an der Einspeise-Zeile aus und kürzt die Herleitung', () => {
    // Bis v4.0.0 versprach das Anlage-Formular den Ausweis „im Cockpit", ohne
    // dass ihn irgendeine Sicht rendert; die Herleitung zeigte zudem die volle
    // Einspeisung, obwohl der Erlös bereits gekürzt war.
    const mit51 = {
      ...basis, einspeise_erloes_euro: 6.4,
      einspeisung_neg_preis_kwh: 20, nicht_vergueteter_erloes_euro: 1.6,
    } as AktuellerMonatResponse
    render(<TKonto d={mit51} />)
    expect(screen.getAllByText(/§51-Verlust: 20,0 kWh ohne Vergütung — 1,60 € entgangen/).length).toBeGreaterThan(0)
  })

  it('ohne Negativpreis-Einspeisung bleibt der §51-Hinweis weg', () => {
    render(<TKonto d={{ ...basis, einspeisung_neg_preis_kwh: 0, nicht_vergueteter_erloes_euro: 0 } as AktuellerMonatResponse} />)
    expect(screen.queryByText(/§51-Verlust/)).toBeNull()
  })

  it('zeigt Verlust, wenn Kosten die Erlöse übersteigen', () => {
    const verlust = { ...basis, einspeise_erloes_euro: 2, ev_ersparnis_euro: 3, netzbezug_kosten_euro: 40 } as AktuellerMonatResponse
    render(<TKonto d={verlust} />)
    expect(screen.getAllByText(/Verlust/).length).toBeGreaterThan(0)
  })

  // G19-1: Basis-Positionen (Anlage-Ebene) — eigene Zeilen NUR im per-Inv-Modus
  // (im Fallback stecken sie bereits im Aggregat, R15-5: kein zweiter Posten).
  it('zeigt Anlage-Zeilen für Basis-Positionen im per-Inv-Modus', () => {
    const d = {
      ...basis,
      investitionen_financials: [{
        investition_id: 7, bezeichnung: 'Speicher', typ: 'speicher',
        betriebskosten_monat_euro: 0, erloes_euro: null, ersparnis_euro: 10,
        ersparnis_label: 'Ersparnis', formel: null, berechnung: null,
        sonstige_ertraege_euro: 0, sonstige_ausgaben_euro: 0,
      }],
      sonstige_ertraege_euro: 120, sonstige_ausgaben_euro: 30, sonstige_netto_euro: 90,
      anlage_sonstige_ertraege_euro: 120, anlage_sonstige_ausgaben_euro: 30,
    } as unknown as AktuellerMonatResponse
    render(<TKonto d={d} />)
    expect(screen.getAllByText(/Anlage — Sonstige Erträge/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Anlage — Sonstige Ausgaben/).length).toBeGreaterThan(0)
  })

  it('zeigt im Fallback-Modus KEINE Anlage-Zeilen (Aggregat deckt sie ab)', () => {
    const d = {
      ...basis,
      investitionen_financials: [],
      sonstige_ertraege_euro: 120, sonstige_ausgaben_euro: 0, sonstige_netto_euro: 120,
      anlage_sonstige_ertraege_euro: 120, anlage_sonstige_ausgaben_euro: 0,
    } as unknown as AktuellerMonatResponse
    render(<TKonto d={d} />)
    expect(screen.queryByText(/Anlage — Sonstige Erträge/)).toBeNull()
    // Aggregat-Fallback-Zeile trägt den Wert stattdessen.
    expect(screen.getAllByText(/Sonstige Erträge/).length).toBeGreaterThan(0)
  })
})
