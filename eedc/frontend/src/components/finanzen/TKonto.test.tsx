/**
 * TKonto — Smoke-Test des ausgelagerten SOLL/HABEN-T-Kontos (Sicherheitsnetz für
 * die Extraktion aus MonatsabschlussView). Prüft SOLL/HABEN-Struktur, Summen und
 * Gewinn/Verlust-Logik. Desktop- + Mobile-Tabelle rendern beide in jsdom (CSS
 * versteckt nicht) → getAllByText.
 */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TKonto } from './TKonto'
import { aktuellerMonat } from '../../test/factories'

const basis = aktuellerMonat(2025, 5, {
  anlage_name: 'Demo',
  einspeisung_kwh: 100, einspeise_preis_cent: 8, einspeise_erloes_euro: 8,
  eigenverbrauch_kwh: 120, ev_ersparnis_euro: 36,
  netzbezug_kwh: 50, netzbezug_preis_cent: 30, netzbezug_kosten_euro: 15,
  netto_ertrag_euro: 29, gesamtnettoertrag_euro: 29,
})

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
    }
    render(<TKonto d={mit51} />)
    expect(screen.getAllByText(/§51-Verlust: 20,0 kWh ohne Vergütung — 1,60 € entgangen/).length).toBeGreaterThan(0)
  })

  it('ohne Negativpreis-Einspeisung bleibt der §51-Hinweis weg', () => {
    render(<TKonto d={{ ...basis, einspeisung_neg_preis_kwh: 0, nicht_vergueteter_erloes_euro: 0 }} />)
    expect(screen.queryByText(/§51-Verlust/)).toBeNull()
  })

  it('zeigt Verlust, wenn Kosten die Erlöse übersteigen', () => {
    const verlust = { ...basis, einspeise_erloes_euro: 2, ev_ersparnis_euro: 3, netzbezug_kosten_euro: 40 }
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
    }
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
    }
    render(<TKonto d={d} />)
    expect(screen.queryByText(/Anlage — Sonstige Erträge/)).toBeNull()
    // Aggregat-Fallback-Zeile trägt den Wert stattdessen.
    expect(screen.getAllByText(/Sonstige Erträge/).length).toBeGreaterThan(0)
  })
})

/**
 * Das Vergleichs-Badge rechnet mit den ANGEZEIGTEN Beträgen (N-253).
 *
 * ⛔ Diese Hälfte des Funds galt im Register bis zum 29.08.2026 als „erledigt".
 *    Gemessen war sie es nicht: `Δ` bildete den Prozentwert unverändert aus den
 *    Rohwerten, während Wert und VJ-Wert eine Zeile höher mit `fmtCalc(…, 2)`
 *    als Euro-Betrag stehen. 250,00 € gegen 249,50 € ergab „▲ 0 %" — eine
 *    behauptete Nulländerung neben zwei sichtbar verschiedenen Beträgen.
 *
 * ⚑ Die letzte Probe ist die Gegenprobe zum zurückgebauten Rechenweg.
 */
describe('TKonto — Vergleichs-Badge gegen die angezeigten Beträge', () => {
  // Der Netto-Wert des T-Kontos entsteht aus den ZEILEN: Haben (8 + 36) − Soll (15)
  // = 29,00 €. Verglichen wird er gegen `vorjahr.gesamtnettoertrag_euro`; beide
  // stehen mit zwei Nachkommastellen als Euro-Betrag nebeneinander.
  const gegenVj = (vjNetto: number) =>
    aktuellerMonat(2025, 5, {
      anlage_name: 'Demo',
      einspeisung_kwh: 100, einspeise_preis_cent: 8, einspeise_erloes_euro: 8,
      eigenverbrauch_kwh: 120, ev_ersparnis_euro: 36,
      netzbezug_kwh: 50, netzbezug_preis_cent: 30, netzbezug_kosten_euro: 15,
      netto_ertrag_euro: 29, gesamtnettoertrag_euro: 29,
      vorjahr: { gesamtnettoertrag_euro: vjNetto },
    })

  it('sichtbar verschiedene Beträge behalten ihre Richtung', () => {
    // 29,00 € gegen 28,94 € — 0,2 %, gerundet „0 %", aber die Richtung steht.
    render(<TKonto d={gegenVj(28.94)} />)
    expect(screen.getAllByText(/▲ 0 %/).length).toBeGreaterThan(0)
  })

  it('gleich aussehende Beträge bekommen „=" statt einer erfundenen Richtung', () => {
    // 29,00 € und 28,998 € stehen beide als „29,00 €" da.
    render(<TKonto d={gegenVj(28.998)} />)
    expect(screen.getAllByText(/= 0 %/).length).toBeGreaterThan(0)
    expect(screen.queryAllByText(/▲/).length).toBe(0)
  })

  it('GEGENPROBE — der Rohwert-Weg hätte hier eine Richtung behauptet', () => {
    const roh = ((29 - 28.998) / Math.abs(28.998)) * 100
    expect(roh).toBeGreaterThan(0)   // der alte Code zeigte „▲ 0 %"
    render(<TKonto d={gegenVj(28.998)} />)
    expect(screen.queryAllByText(/▲/).length).toBe(0)
  })
})
